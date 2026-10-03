"""Self-hosted models get room for Nox's instructions, or a plain explanation why not."""

import json

import httpx
import pytest
from fastapi import HTTPException

from houseos import assistant


def test_ollama_gets_enough_context_and_tool_calls_come_back_openai_shaped(monkeypatch):
    seen = {}

    def handle(request):
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.33.3"})
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "household_create", "arguments": {"kind": "groceries"}}}
                    ],
                },
                "prompt_eval_count": 6100,
                "eval_count": 30,
            },
        )

    transport = httpx.MockTransport(handle)
    real = httpx.Client
    monkeypatch.setattr(assistant.httpx, "Client", lambda **kw: real(transport=transport, **kw))
    monkeypatch.setattr(assistant, "endpoint_url", lambda url, **kw: url)
    assistant._ollama.clear()
    cfg = {"base_url": "http://ollama.lan:11434/v1", "model": "qwen3:8b", "_policy": "x" * 20000}
    earlier = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "music_get_state", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": "{}"},
    ]
    reply, calls, replay, usage = assistant.provider_round(
        "compatible", cfg, earlier, [{"name": "household_create"}]
    )
    assert seen["options"]["num_ctx"] >= 8192 and seen["stream"] is False
    assert seen["messages"][2]["tool_calls"][0]["function"]["arguments"] == {}  # native objects
    assert calls == [{"id": "call_0", "name": "household_create", "args": {"kind": "groceries"}}]
    assert json.loads(replay["tool_calls"][0]["function"]["arguments"]) == {"kind": "groceries"}
    assert usage["input_tokens"] == 6100


def test_a_truncated_prompt_is_explained():
    with pytest.raises(HTTPException) as refused:
        assistant.require_room(2048, "x" * 30000, [], [])
    assert "context size" in refused.value.detail["message"]
    assistant.require_room(9000, "x" * 30000, [], [])  # roomy servers are left alone
    assistant.require_room(None, "x" * 30000, [], [])  # servers that don't report usage too
