"""Native CLI adapter contract: no paid calls or user authentication performed."""

import asyncio
import json
import pytest
from houseos.claude_bridge import studio_images, Claude, output_schema
from houseos.codex_bridge import BridgeError


class Stub(Claude):
    def __init__(self, answer):
        super().__init__("/tmp/houseos-claude-fixture")
        self.answer = answer
        self.invocations = []

    async def invoke(self, arguments, content="", limit=4096, timeout=50, **_):
        self.invocations.append((arguments, content, limit))
        if "status" in arguments:
            return {"loggedIn": True, "authMethod": "oauth", "email": "private@example.test"}
        return self.answer


def request(app):
    return asyncio.run(
        app.action(
            {
                "action": "round",
                "model": "sonnet",
                "messages": [{"role": "user", "content": "List groceries"}],
                "schemas": [
                    {
                        "name": "list_groceries",
                        "description": "Read groceries",
                        "parameters": {"type": "object"},
                    }
                ],
            }
        )
    )


def test_native_cli_only_proposes_tools_and_has_no_host_tools():
    app = Stub(
        {
            "subtype": "success",
            "structured_output": {"reply": "", "calls": [{"name": "list_groceries", "args": {}}]},
            "usage": {"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 20},
        }
    )
    result = request(app)
    assert len(app.invocations) == 1  # one CLI start per round: no sign-in pre-check
    assert result["calls"][0]["name"] == "list_groceries"
    assert result["wire"]["content"][0]["type"] == "tool_use"
    assert result["usage"]["input_tokens"] == 120
    args, content, limit = app.invocations[-1]
    assert args[args.index("--tools") + 1] == ""
    assert "--no-session-persistence" in args and "--strict-mcp-config" in args
    assert args[args.index("--setting-sources") + 1] == ""
    assert json.loads(content)[0]["content"] == "List groceries"
    env = app.environment()
    assert set(env) == {
        "PATH",
        "HOME",
        "CLAUDE_CONFIG_DIR",
        "LANG",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    }
    assert "ANTHROPIC_API_KEY" not in env


def test_only_the_studio_lane_searches_the_web_and_carries_images():
    answer = {
        "type": "result",
        "subtype": "success",
        "structured_output": {"reply": "Three directions.", "calls": []},
    }
    app = Stub(answer)
    image = {"media_type": "image/jpeg", "data": "aGVsbG8="}
    body = {
        "action": "round",
        "model": "opus",
        "lane": "studio",
        "web_search": True,
        "images": [image],
        "max_output_tokens": 16000,
        "timeout_seconds": 300,
        "messages": [{"role": "user", "content": "A theme like this photo"}],
        "schemas": [],
    }
    assert asyncio.run(app.action(body))["reply"] == "Three directions."
    args, content, limit = app.invocations[-1]
    assert args[args.index("--tools") + 1] == "WebSearch" and "--allowedTools" in args
    assert args[args.index("--input-format") + 1] == "stream-json" and limit == 16000
    message = json.loads(content)["message"]["content"]
    assert json.loads(message[0]["text"])[0]["content"] == "A theme like this photo"
    assert message[1] == {"type": "image", "source": {"type": "base64", **image}}
    # Everyday Nox: no search, no images, the usual cap, even if a caller asks.
    request(app := Stub({"subtype": "success", "structured_output": {"reply": "ok", "calls": []}}))
    args, _, limit = app.invocations[-1]
    assert args[args.index("--tools") + 1] == "" and "--input-format" not in args and limit == 4096
    for bad in (
        [image] * 5,
        [{"media_type": "image/svg+xml", "data": "PHN2Zz4="}],
        [{"media_type": "image/png", "data": "<script>"}],
    ):
        with pytest.raises(BridgeError):
            studio_images(bad)


def test_schema_refs_are_scoped_and_unknown_tool_fails():
    schema = output_schema(
        [
            {
                "name": "known",
                "parameters": {
                    "$defs": {"X": {"type": "string"}},
                    "properties": {"value": {"$ref": "#/$defs/X"}},
                },
            }
        ]
    )
    ref = schema["properties"]["calls"]["items"]["anyOf"][0]["properties"]["args"]["properties"]["value"][
        "$ref"
    ]
    assert ref == "#/properties/calls/items/anyOf/0/properties/args/$defs/X"
    with pytest.raises(BridgeError):
        request(
            Stub(
                {
                    "structured_output": {
                        "reply": "",
                        "calls": [{"name": "Bash", "args": {"command": "whoami"}}],
                    }
                }
            )
        )


def test_status_and_aliases_are_honest_and_private():
    app = Stub({})
    status = asyncio.run(app.action({"action": "status"}))
    version = status.pop("version")  # the client's own version, when it can be read
    assert version is None or isinstance(version, str)
    assert status == {"status": "ok", "logged_in": True, "auth_mode": "oauth"}
    aliases = asyncio.run(app.action({"action": "models"}))
    assert aliases["catalog_kind"] == "documented_native_aliases"
    assert aliases["availability_verified"] is False
    with pytest.raises(BridgeError):
        asyncio.run(app.action({"action": "arbitrary-command"}))


def test_cli_transport_handles_split_json_and_clean_environment(tmp_path, monkeypatch):
    binary = tmp_path / "fixture-cli"
    binary.write_text("""#!/usr/bin/python3
import json,os,sys,time
assert '--safe-mode' in sys.argv
assert 'ANTHROPIC_API_KEY' not in os.environ
assert 'DATABASE_URL' not in os.environ
sys.stdout.write('{"loggedIn":');sys.stdout.flush();time.sleep(0.02)
sys.stdout.write('false,"authMethod":null}')
""")
    binary.chmod(0o700)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak-fixture")
    monkeypatch.setenv("DATABASE_URL", "must-not-leak-fixture")

    async def check():
        app = Claude(tmp_path / "profile", str(binary))
        await app.start()
        assert (await app.status())["logged_in"] is False

    asyncio.run(check())


def test_entire_cli_round_obeys_callers_deadline():
    class Slow(Stub):
        async def invoke(self, *args, **kwargs):
            await asyncio.sleep(10)

    async def check():
        start = asyncio.get_running_loop().time()
        with pytest.raises(BridgeError, match="CLAUDE_TIMEOUT"):
            await Slow({}).action(
                {"action": "round", "model": "sonnet", "messages": [{}], "timeout_seconds": 1}
            )
        assert asyncio.get_running_loop().time() - start < 1

    asyncio.run(check())


def test_a_round_that_loses_the_sign_in_says_so():
    """An expired sign-in fails the round and the CLI forgets it: sign in again, not 'try again'."""

    class Expired(Stub):
        async def invoke(self, arguments, content="", limit=4096, timeout=50, **_):
            if "status" in arguments:
                return {"loggedIn": False}
            raise BridgeError("CLAUDE_REQUEST_FAILED")

    with pytest.raises(BridgeError, match="CLAUDE_SIGN_IN_REQUIRED"):
        request(Expired({}))
    with pytest.raises(BridgeError, match="CLAUDE_TURN_FAILED"):
        request(Stub({"is_error": True, "subtype": "error_during_execution", "result": "API Error: 500"}))
