"""Requested provider defaults, effort and deterministic discovery contracts."""

import httpx
import pytest
from fastapi import HTTPException
from houseos import assistant as a
from houseos import assistant_tools as t
from houseos.integrations import check_config


def test_effort_and_resident_context_reach_provider(monkeypatch):
    captured = {}

    def send(request):
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Ready ✅"}}], "usage": {}},
            request=request,
        )

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(send), **kw))
    reply, *_ = a.provider_round(
        "openrouter",
        {
            "model": "deepseek/deepseek-v4-flash",
            "api_key": "fixture",
            "reasoning_effort": "low",
            "_resident_context": "\nResident username: fixture",
        },
        [],
        [],
    )
    assert reply == "Ready ✅"
    assert captured["reasoning"] == {"effort": "low"}
    assert "Resident username: fixture" in captured["messages"][0]["content"]
    assert captured["provider"]["require_parameters"] is True
    check_config("budgets", {"default_provider": "openrouter"})
    with pytest.raises(HTTPException):
        check_config("budgets", {"default_provider": "made-up"})
    with pytest.raises(HTTPException):
        check_config("openrouter", {"reasoning_effort": "pretend"})


def test_discovery_tools_are_typed_and_music_can_select_soundcloud():
    assert t.MusicSearch(query="test", source="soundcloud").source == "soundcloud"
    for context, names in [("music", {"radio_search", "radio_queue"}), ("cinema", {"cinema_browse"})]:
        registry = a.tool_registry(context)
        assert names <= registry.keys()
        for name in names:
            schema = t.strict_schema(registry[name][0].model_json_schema())
            assert schema["type"] == "object"


def test_event_stream_releases_database_before_yield(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from datetime import timedelta
    from houseos import core
    from houseos.db import utcnow
    from houseos.models import SessionToken

    state = {"open": False}

    class DB:
        def __enter__(self):
            state["open"] = True
            return self

        def __exit__(self, *args):
            state["open"] = False

        def get(self, kind, key):
            return (
                SimpleNamespace(expires_at=utcnow() + timedelta(hours=1))
                if kind is SessionToken
                else SimpleNamespace(active=True, expires_at=None, role="resident")
            )

        def scalars(self, q):
            return [SimpleNamespace(id=1, topic="fixture", payload={})]

        def scalar(self, q):
            return 7

    monkeypatch.setattr(core, "SessionLocal", DB)
    request = SimpleNamespace(headers={"last-event-id": "0"}, cookies={})
    # The sign-in check's own session is closed before the stream starts.
    login = SimpleNamespace(closed=False)
    login.close = lambda: setattr(login, "closed", True)
    response = core.events(request, SimpleNamespace(id="fixture"), login)
    assert login.closed

    async def run():
        message = await anext(response.body_iterator)
        assert "fixture" in message and not state["open"]
        await response.body_iterator.aclose()

    asyncio.run(run())
    # A fresh connection (no Last-Event-ID) starts at the newest event instead of replaying history.
    fresh = core.events(SimpleNamespace(headers={}, cookies={}), SimpleNamespace(id="fixture"), login)

    async def first():
        message = await anext(fresh.body_iterator)
        await fresh.body_iterator.aclose()
        return message

    message = asyncio.run(first())
    assert "fixture" not in message and "id: 7" in message
