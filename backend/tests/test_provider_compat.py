"""Self-hosted and other OpenAI-compatible servers: addresses, errors, slow loads. Fixtures only."""

import json
import httpx
import pytest
from fastapi import HTTPException
from houseos import assistant as a, provider_checks as checks
from test_providers import mock_catalog


def server(chat, ollama=False, shown=None):
    """A fake model server; `chat` answers /chat/completions (or Ollama's /api/chat)."""

    def reply(request):
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"}) if ollama else httpx.Response(404)
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "gemma:2b"}, {"id": "qwen3:8b"}]})
        if path == "/api/show":
            return httpx.Response(200, json={"capabilities": shown[json.loads(request.content)["model"]]})
        if path in {"/v1/chat/completions", "/api/chat"}:
            return chat(request)
        return httpx.Response(404)

    return reply


def probe_call(request):
    call = {
        "id": "c",
        "type": "function",
        "function": {"name": "houseos_probe", "arguments": '{"echo":"houseos"}'},
    }
    return httpx.Response(200, json={"choices": [{"message": {"content": "", "tool_calls": [call]}}]})


def test_address_without_path_uses_v1_and_a_wrong_path_says_so(setup, monkeypatch):
    db, (actor, _) = setup
    a._ollama.clear()
    mock_catalog(monkeypatch, server(probe_call))
    result = checks.connect("compatible", checks.Connect(base_url="http://192.0.2.13:1234"), actor, db)
    assert result["model"] == "gemma:2b" and result["tested"] == "verified"
    with pytest.raises(HTTPException) as error:
        checks.refresh("compatible", checks.CatalogRefresh(base_url="http://192.0.2.13:1234/api"), actor, db)
    assert "/v1" in error.value.detail


def test_the_providers_reason_reaches_the_admin(setup, monkeypatch):
    db, (actor, _) = setup
    a._ollama.clear()
    refused = {"error": {"message": "tools param requires --jinja flag", "type": "server_error"}}
    mock_catalog(monkeypatch, server(lambda request: httpx.Response(500, json=refused)))
    result = checks.connect("compatible", checks.Connect(base_url="http://192.0.2.14:8080/v1"), actor, db)
    assert result["tested"] == "failed" and result["test_detail"] == "tools param requires --jinja flag"


def test_provider_error_hides_keys_and_link_parameters():
    body = {
        "error": {
            "message": "Key sk-or-v1-abcdef123456 has no credit. Top up at "
            "https://openrouter.ai/credits?token=secret123. Bearer abc.def " + "x" * 400
        }
    }
    error = httpx.HTTPStatusError("402", request=None, response=httpx.Response(402, json=body))
    said = a.provider_error(error, "abcdef123456")
    assert "abcdef" not in said and "secret123" not in said and "abc.def" not in said
    assert "https://openrouter.ai/credits" in said and len(said) <= 200
    assert a.provider_error(httpx.HTTPStatusError("x", request=None, response=httpx.Response(500))) is None
    ollama = httpx.Response(400, json={"error": "gemma:2b does not support tools"})
    assert a.provider_error(httpx.HTTPStatusError("x", request=None, response=ollama)) == (
        "gemma:2b does not support tools"
    )


def test_a_loading_model_gets_a_minute_and_a_plain_retry_hint(setup, monkeypatch):
    db, (actor, _) = setup
    a._ollama.clear()
    waited = []

    def slow(request):
        waited.append(request.extensions["timeout"]["read"])
        raise httpx.ReadTimeout("loading", request=request)

    mock_catalog(monkeypatch, server(slow))
    result = checks.connect("compatible", checks.Connect(base_url="http://192.0.2.15:1234/v1"), actor, db)
    assert result["test_code"] == "PROVIDER_TIMEOUT" and waited == [60]


def test_ollama_picks_a_model_that_can_use_tools(setup, monkeypatch):
    db, (actor, _) = setup
    a._ollama.clear()
    chat = lambda request: httpx.Response(  # noqa: E731
        200,
        json={
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "houseos_probe", "arguments": {"echo": "houseos"}}}],
            }
        },
    )
    shown = {"gemma:2b": ["completion"], "qwen3:8b": ["completion", "tools"]}
    mock_catalog(monkeypatch, server(chat, ollama=True, shown=shown))
    result = checks.connect("compatible", checks.Connect(base_url="http://192.0.2.16:11434"), actor, db)
    assert result["model"] == "qwen3:8b" and result["tested"] == "verified"
