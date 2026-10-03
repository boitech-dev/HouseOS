"""Protocol checks use stub RPC only; real handshake does not initiate a model turn."""

import asyncio
import json
import pytest
from houseos.codex_bridge import AppServer, BridgeError, CONFIG


class Stub(AppServer):
    def __init__(self, events):
        super().__init__("/tmp/isolated-codex-fixture")
        self.sent = []
        self.fixture = events

    async def rpc(self, method, params=None, timeout=20):
        self.sent.append((method, params))
        if method == "account/read":
            return {"account": {"type": "chatgpt", "email": "private@example.test"}}
        if method == "thread/start":
            return {"thread": {"id": "fixture-thread"}}
        if method == "turn/start":
            for event in self.fixture:
                self.events.put_nowait(event)
            return {"turn": {"id": "fixture-turn"}}
        return {}


def run(events):
    app = Stub(events)
    result = asyncio.run(
        app.action(
            {
                "action": "round",
                "model": "fixture-model",
                "messages": [{"role": "user", "content": "What is queued?"}],
                "schemas": [
                    {"name": "music_status", "description": "Read queue", "parameters": {"type": "object"}}
                ],
            }
        )
    )
    return app, result


def test_native_dynamic_tool_is_returned_without_execution():
    app, result = run(
        [
            {
                "id": 72,
                "method": "item/tool/call",
                "params": {
                    "threadId": "fixture-thread",
                    "callId": "call-1",
                    "tool": "music_status",
                    "arguments": {},
                },
            }
        ]
    )
    assert result["calls"] == [{"id": "call-1", "name": "music_status", "args": {}}]
    assert result["wire"][0]["type"] == "function_call"
    assert result["usage"] == {}  # Unknown usage never becomes fabricated zero.
    assert app.sent[-1][0] == "thread/unsubscribe"
    thread = next(params for method, params in app.sent if method == "thread/start")
    assert thread["ephemeral"] and thread["environments"] == []
    assert thread["config"]["features.shell_tool"] is False
    assert thread["config"]["features.memories"] is False
    assert thread["config"]["agents.enabled"] is False
    assert thread["dynamicTools"][0]["name"] == "music_status"
    assert not any(method in {"command/exec", "tool/output"} for method, _ in app.sent)


def test_unknown_tools_and_capabilities_fail_closed():
    for event in [
        {"id": 2, "method": "item/tool/call", "params": {"tool": "shell", "arguments": {}}},
        {"method": "item/started", "params": {"item": {"type": "commandExecution"}}},
    ]:
        with pytest.raises(BridgeError):
            run([event])


def test_completed_reply_and_reported_usage():
    _, result = run(
        [
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {"total": {"inputTokens": 100, "outputTokens": 8, "cachedInputTokens": 20}}
                },
            },
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": "There are no queued tracks."}},
            },
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ]
    )
    assert result["reply"] == "There are no queued tracks."
    assert result["calls"] == [] and result["usage"]["cached_tokens"] == 20


def test_status_redacts_identity_and_unknown_rpc_denied():
    app = Stub([])
    assert asyncio.run(app.action({"action": "status"})) == {
        "status": "ok",
        "logged_in": True,
        "auth_mode": "chatgpt",
    }
    with pytest.raises(BridgeError):
        asyncio.run(app.action({"action": "command/exec"}))
    assert CONFIG["project_doc_max_bytes"] == 0


def test_entire_native_round_obeys_callers_deadline():
    class Slow(Stub):
        async def rpc(self, *args, **kwargs):
            await asyncio.sleep(10)

    async def check():
        start = asyncio.get_running_loop().time()
        with pytest.raises(BridgeError, match="CODEX_TIMEOUT"):
            await Slow([]).round({"model": "fixture", "messages": [{}], "timeout_seconds": 1})
        assert asyncio.get_running_loop().time() - start < 1

    asyncio.run(check())


def test_a_long_studio_round_never_makes_everyday_nox_busy(tmp_path):
    from houseos.codex_bridge import serve

    class Slow:
        def __init__(self):
            self.release = asyncio.Event()

        async def start(self):
            pass

        async def close(self):
            pass

        async def action(self, body):
            if body.get("lane") == "studio":
                await self.release.wait()
            return {"lane": body.get("lane", "default")}

    async def ask(path, body):
        reader, writer = await asyncio.open_unix_connection(str(path))
        writer.write(json.dumps(body).encode() + b"\n")
        await writer.drain()
        return json.loads(await reader.readline())

    async def scenario():
        app, path = Slow(), tmp_path / "bridge.sock"
        server = asyncio.create_task(serve(app, path, lanes=("default", "studio")))
        while not path.exists():
            await asyncio.sleep(0.01)
        studio = asyncio.create_task(ask(path, {"action": "round", "lane": "studio"}))
        await asyncio.sleep(0.05)
        everyday = await asyncio.wait_for(ask(path, {"action": "round"}), 2)
        app.release.set()
        done = await studio
        server.cancel()
        return everyday, done

    everyday, studio = asyncio.run(scenario())
    assert everyday == {"lane": "default"} and studio == {"lane": "studio"}
