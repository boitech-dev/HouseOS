"""One-step AI connections, request-count limits and typed service addresses. Fixtures only."""

import asyncio
import json
import os
import httpx
import pytest
from fastapi import HTTPException
from houseos import assistant as a, assistant_profiles as profiles, integrations, provider_checks as checks
from houseos.claude_bridge import Claude
from houseos.codex_bridge import BridgeError
from houseos.integrations import endpoint_url
from houseos.models import Integration, Usage
from test_providers import mock_catalog

LOCAL = "http://127.0.0.1:11434/v1"


def ollama(request):
    """A self-hosted OpenAI-compatible server: two models, one of them for embeddings only."""
    assert "authorization" not in request.headers
    if request.url.path == "/api/version":  # an OpenAI-compatible server that is not Ollama
        return httpx.Response(404)
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "nomic-embed-text:latest"}, {"id": "qwen3:8b"}]})
    body = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions" and "provider" not in body
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "houseos_probe", "arguments": '{"echo":"houseos"}'},
    }
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [call]}}],
            "usage": {"prompt_tokens": 170, "completion_tokens": 20},
        },
    )


def test_self_hosted_connects_in_one_step(setup, monkeypatch):
    db, (actor, _) = setup
    mock_catalog(monkeypatch, ollama)
    result = checks.connect("compatible", checks.Connect(base_url=LOCAL + "/"), actor, db)
    assert result == {
        "status": "connected",
        "provider": "compatible",
        "model": "qwen3:8b",
        "tested": "verified",
    }
    row = db.get(Integration, "compatible")
    assert row.enabled and row.config["base_url"] == LOCAL and row.encrypted_secret == ""
    assert [item["id"] for item in db.get(Integration, "catalog.compatible").config["items"]] == ["qwen3:8b"]
    status = profiles.profiles(actor, db)
    assert status["items"][0] | {"ready": True, "tested": True} == status["items"][0]
    assert status["items"][0]["provider"] == "compatible"
    assert a.status(actor, db)["available"] is True
    # Self-hosted models count requests, never dollars.
    assert db.get(Usage, db.query(Usage.id).scalar()).reserved_microusd == 0


def test_unreachable_self_hosted_server_is_a_sentence(setup, monkeypatch):
    db, (actor, _) = setup
    mock_catalog(monkeypatch, lambda request: httpx.Response(502))
    with pytest.raises(HTTPException) as error:
        checks.connect("compatible", checks.Connect(base_url=LOCAL), actor, db)
    assert error.value.detail.startswith("Could not reach this server")


def test_fallback_assignment_is_the_first_working_connection(setup):
    db, (actor, _) = setup
    db.add_all(
        [
            Integration(
                name="openai",
                enabled=True,
                config={"auth_mode": "codex", "owner_user_id": actor.id, "model": "gpt"},
            ),
            Integration(
                name="anthropic", enabled=True, config={"model": "claude-haiku"}, encrypted_secret="x"
            ),
            Integration(name="openrouter", enabled=True, config={"model": "router"}),  # no key yet
        ]
    )
    db.commit()
    assert profiles.assignment(db, "general")["provider"] == "anthropic"
    db.get(Integration, "anthropic").enabled = False
    assert profiles.assignment(db, "general") == {
        "provider": "openai",
        "model": "gpt",
        "reasoning_effort": None,
    }
    db.get(Integration, "openrouter").encrypted_secret = "x"
    assert profiles.assignment(db, "general")["model"] == "router"


def test_unpriced_models_count_requests(setup):
    db, (actor, bob) = setup
    cfg = {"model": "gpt-5-mini", "daily_request_limit": 5, "user_daily_request_limit": 1}
    db.add(Integration(name="openai", enabled=True, config=cfg))
    db.commit()
    assert db.get(Usage, a.reserve(db, actor, "openai", dict(cfg), [], [])).reserved_microusd == 0
    with pytest.raises(HTTPException) as limit:
        a.reserve(db, actor, "openai", dict(cfg), [], [])
    assert limit.value.status_code == 429
    # A per-person allowance, not a shared one.
    record = db.get(Usage, a.reserve(db, bob, "openai", dict(cfg), [], []))
    evidence = a.record_usage_evidence(db, record, cfg, {"input_tokens": 3, "output_tokens": 1})
    assert evidence["cost_kind"] == "unknown" and record.status == "completed"


def test_openai_catalog_keeps_chat_models_only(setup, monkeypatch):
    db, (actor, _) = setup
    ids = [
        "gpt-5-mini",
        "text-embedding-3-small",
        "tts-1",
        "whisper-1",
        "dall-e-3",
        "gpt-4o-realtime-preview",
    ]
    mock_catalog(monkeypatch, lambda request: httpx.Response(200, json={"data": [{"id": i} for i in ids]}))
    items = checks.refresh("openai", checks.CatalogRefresh(api_key="fixture"), actor, db)["items"]
    assert [item["id"] for item in items] == ["gpt-5-mini"]
    assert checks.recommended(
        "anthropic", [{"id": "claude-haiku-4-5-20251001", "tool_support": "requires_probe"}]
    )


@pytest.mark.parametrize(
    "value, path, message",
    [
        ("http://jellyfin:8096", False, None),
        ("https://media.example.org", False, None),
        ("http://192.168.1.20:8123/", False, None),
        ("http://host.docker.internal:11434/v1", True, None),
        ("http://jellyfin:8096/web", False, "without a path"),
        ("ftp://jellyfin", False, "http://"),
        ("http://user:secret@jellyfin:8096", False, "password"),
        ("http://jellyfin:8096?x=1", False, "password"),
        ("http://169.254.169.254", False, "not allowed"),
        ("http://[fe80::1]:8096", False, "not allowed"),
        ("http://224.0.0.1", False, "not allowed"),
        ("http://jellyfin:99999", False, "port"),
    ],
)
def test_endpoint_url(value, path, message):
    if message is None:
        assert endpoint_url(value, path=path) == value.rstrip("/")
    else:
        with pytest.raises(ValueError, match=message):
            endpoint_url(value, path=path)


def test_docker_refuses_loopback(monkeypatch):
    assert endpoint_url("http://127.0.0.1:8096")
    monkeypatch.setattr(integrations.settings, "storage_container", True)
    for value in ("http://localhost:8096", "http://127.0.0.1:8096", "http://[::1]:8096"):
        with pytest.raises(ValueError, match="host.docker.internal"):
            endpoint_url(value)
    with pytest.raises(HTTPException) as error:
        integrations.check_config("jellyfin", {"base_url": "http://localhost:8096"})
    assert "host.docker.internal" in error.value.detail


def test_cast_accepts_any_private_lan_host_until_a_network_is_set(monkeypatch):
    monkeypatch.setattr(integrations.settings, "cast_lan_cidr", "")
    integrations.check_config("cast", {"host": "10.0.0.7"})
    for host in ("127.0.0.1", "169.254.1.1", "8.8.8.8"):
        with pytest.raises(HTTPException):
            integrations.check_config("cast", {"host": host})


def test_jellyfin_test_authenticates_and_lists_users(setup, monkeypatch):
    db, (actor, _) = setup
    integrations.save_integration(
        "jellyfin",
        integrations.IntegrationInput(
            enabled=True, config={"base_url": "http://192.168.1.20:8096"}, secret="key"
        ),
        actor,
        db,
    )

    answers = [httpx.Response(401), httpx.Response(200, json=[{"Id": "u1", "Name": "Alice", "Policy": {}}])]

    def reply(request):
        assert str(request.url) == "http://192.168.1.20:8096/Users"
        assert 'Token="key"' in request.headers["authorization"]
        return answers.pop()

    mock_catalog(monkeypatch, reply)
    result = integrations.test_integration("jellyfin", actor, db)
    assert result["status"] == "reachable" and result["users"] == [{"id": "u1", "name": "Alice"}]
    assert integrations.test_integration("jellyfin", actor, db)["status"] == "authentication_failed"


def test_home_assistant_test_uses_its_token(setup, monkeypatch):
    db, (actor, _) = setup
    integrations.save_integration(
        "home_assistant",
        integrations.IntegrationInput(
            enabled=True, config={"base_url": "http://192.0.2.18:8123"}, secret="ha"
        ),
        actor,
        db,
    )

    def reply(request):
        assert request.headers["authorization"] == "Bearer ha"
        if str(request.url) == "http://192.0.2.18:8123/api/states":  # its TVs, to pick one
            return httpx.Response(
                200,
                json=[
                    {"entity_id": "light.hall", "attributes": {}},
                    {"entity_id": "media_player.tv", "attributes": {"friendly_name": "Salon TV"}},
                ],
            )
        assert str(request.url) == "http://192.0.2.18:8123/api/"
        return httpx.Response(200, json={"message": "API running."})

    mock_catalog(monkeypatch, reply)
    result = integrations.test_integration("home_assistant", actor, db)
    assert result["status"] == "reachable"
    assert result["players"] == [{"id": "media_player.tv", "name": "Salon TV"}]


def test_missing_bridge_is_a_state_not_an_error(setup, monkeypatch):
    db, (actor, _) = setup
    from houseos import codex_client

    monkeypatch.setattr(codex_client.ipc, "request", lambda *args, **kwargs: kwargs["failure"])
    assert checks.native_status("openai", actor, db) == {"status": "unavailable", "logged_in": False}


FAKE_CLI = """#!/usr/bin/python3
import json, os, sys
args = sys.argv[1:]
if args == ["setup-token"]:
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ
    sys.stdout.write("\\x1b[1mWelcome\\x1b[1Cto\\x1b[1CClaude\\x1b[0m\\n\\n")
    sys.stdout.write("https://claude.com/cai/oauth/authorize?code=true&state=fixture\\n\\n")
    sys.stdout.write("Paste\\x1b[1Ccode\\x1b[1Chere\\x1b[1Cif\\x1b[1Cprompted\\x1b[1C>\\x1b[1C")
    sys.stdout.flush()
    code = sys.stdin.readline().strip()
    if code == "stale-code#state":  # the real CLI: an OAuth error, then Enter for a new page
        sys.stdout.write("OAuth error: Request failed with status code 400Press Enter to retry.")
        sys.stdout.flush()
        sys.stdin.readline()
        sys.stdout.write("https://claude.com/cai/oauth/authorize?code=true&state=fresh\\n\\n")
        sys.stdout.write("Paste\\x1b[1Ccode\\x1b[1Chere\\x1b[1Cif\\x1b[1Cprompted\\x1b[1C>\\x1b[1C")
        sys.stdout.flush()
        code = sys.stdin.readline().strip()
    if code in {"fixture-code#state", "fresh-code#state"}:
        # Coloured, and the next line drawn with a cursor move: no plain whitespace after it.
        print("Your OAuth token (valid for 1 year):\\n\\n\\x1b[33msk-ant-oat01-" + "f" * 40
              + "\\x1b[39m\\x1b[1BStore\\x1b[1Cit securely.")
elif "status" in args:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    print(json.dumps({"loggedIn": bool(token), "authMethod": "oauth_token" if token else "none"}))
    sys.exit(0 if token else 1)
else:
    sys.exit(1)  # "auth logout" with nothing stored by the CLI itself
"""


def test_claude_headless_sign_in_keeps_token_private(tmp_path):
    binary = tmp_path / "claude"
    binary.write_text(FAKE_CLI)
    binary.chmod(0o700)

    async def check():
        app = Claude(tmp_path / "profile", str(binary))
        await app.start()
        started = await app.action({"action": "login_start"})
        assert started == {
            "status": "pending",
            "verification_url": "https://claude.com/cai/oauth/authorize?code=true&state=fixture",
            "needs_code": True,
        }
        assert await app.action({"action": "login_code", "code": "fixture-code#state"}) == {
            "status": "signed_in"
        }
        assert os.stat(app.token_file).st_mode & 0o777 == 0o600
        assert app.environment()["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-" + "f" * 40
        assert (await app.status())["logged_in"] is True
        assert await app.action({"action": "logout"}) == {"status": "signed_out"}
        assert not app.token_file.exists()
        # A refused code gives a fresh sign-in page in the same window, then the new code works.
        await app.action({"action": "login_start"})
        again = await app.action({"action": "login_code", "code": "stale-code#state"})
        assert again == {
            "status": "code_rejected",
            "verification_url": "https://claude.com/cai/oauth/authorize?code=true&state=fresh",
            "needs_code": True,
        }
        assert await app.action({"action": "login_code", "code": "fresh-code#state"}) == {
            "status": "signed_in"
        }
        assert app.environment()["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-" + "f" * 40
        await app.action({"action": "login_start"})
        with pytest.raises(BridgeError, match="CLAUDE_LOGIN_FAILED"):
            await app.action({"action": "login_code", "code": "wrong-code#state"})
        with pytest.raises(BridgeError, match="CLAUDE_TOKEN_INVALID"):
            await app.action({"action": "login_token", "token": "sk-ant-api03-not-a-subscription"})
        assert await app.action({"action": "login_token", "token": "sk-ant-oat01-" + "p" * 40}) == {
            "status": "signed_in"
        }

    asyncio.run(check())


def test_a_sign_in_code_may_take_claude_most_of_a_minute(monkeypatch):
    from houseos import codex_client

    seen = {}
    monkeypatch.setattr(codex_client.ipc, "request", lambda path, body, **kw: seen.update(kw) or {"ok": 1})
    codex_client.request("login_code", code="x")
    assert seen["timeout"] == 62  # the bridge waits 55 s for the token; its requests end at 65 s
    codex_client.request("login_start")
    assert seen["timeout"] == 25
