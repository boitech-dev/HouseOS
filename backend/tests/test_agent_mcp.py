"""Other assistants over MCP (/mcp): a token an admin makes acts as one person in its groups."""

import json

from houseos.auth import RESIDENT, Actor, require_actor
from houseos.db import new_id
from houseos.main import app
from houseos.models import User


def rpc(c, token, method, params=None, id=1):
    headers = {"Authorization": "Bearer " + token} if token else {}
    return c.post(
        "/mcp", json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}, headers=headers
    )


def test_an_agent_token_lists_and_calls_only_its_groups_until_revoked(client):
    c, db = client
    admin = User(
        id=new_id(), name="Ada", username="ada", password_hash="x", role="admin", permissions=list(RESIDENT)
    )
    db.add(admin)
    db.commit()
    app.dependency_overrides[require_actor] = lambda: Actor(admin.id, "Ada", "admin", RESIDENT)
    made = c.post("/api/v1/admin/agents", json={"name": "Ronda", "user_id": admin.id, "groups": ["board"]})
    assert made.status_code == 200, made.text
    token = made.json()["token"]
    assert "token" not in json.dumps(c.get("/api/v1/admin/agents").json()["items"])  # shown once
    app.dependency_overrides.pop(require_actor)

    assert rpc(c, "", "initialize").status_code == 401
    assert rpc(c, "hos_wrong", "initialize").status_code == 401
    hello = rpc(c, token, "initialize", {"protocolVersion": "2025-03-26"}).json()["result"]
    assert hello["protocolVersion"] == "2025-03-26" and hello["serverInfo"]["name"] == "houseos"
    for asked, answered in (("2025-11-25", "2025-11-25"), ("1999-01-01", "2025-06-18")):
        assert (
            rpc(c, token, "initialize", {"protocolVersion": asked}).json()["result"]["protocolVersion"]
            == answered
        )
    assert c.get("/mcp").status_code == 405  # no event stream here
    later = c.post("/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "ping"},
                   headers={"Authorization": "Bearer " + token, "MCP-Protocol-Version": "2025-11-25"})  # fmt: skip
    assert later.json()["result"] == {}
    assert c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers={"Authorization": "Bearer " + token}).status_code == 202  # fmt: skip

    tools = rpc(c, token, "tools/list").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    create = next(t for t in tools if t["name"] == "household_create")["inputSchema"]["properties"]["item"]
    assert {"board", "tasks", "groceries", "calendar"} <= set(create["properties"]["kind"]["enum"])
    assert "label" in create["properties"]["data"]["properties"]  # every form's fields
    assert "household_create" in names and not names & {"music_get_state", "messages_send"}
    for tool in tools:  # every tool says what it may do, in a schema every model reads
        assert {"title", "readOnlyHint", "destructiveHint", "openWorldHint"} <= set(tool["annotations"])
        text = json.dumps(tool["inputSchema"])
        assert tool["inputSchema"]["type"] == "object"
        assert not any(
            k in text for k in ('"$ref"', '"$defs"', '"anyOf"', '"oneOf"', '"allOf"', "idempotency_key")
        )
        assert len(tool["name"]) <= 48 and tool["name"] == tool["name"].lower()

    made = rpc(c, token, "tools/call", {"name": "household_create",
               "arguments": {"item": {"kind": "groceries", "data": {"label": "Oat milk"}}}}).json()["result"]  # fmt: skip
    assert not made["isError"], made
    found = rpc(c, token, "tools/call", {"name": "household_list", "arguments": {"kind": "groceries"}}).json()
    assert "Oat milk" in found["result"]["content"][0]["text"]

    refused = rpc(c, token, "tools/call", {"name": "music_get_state", "arguments": {}}).json()["result"]
    assert refused["isError"] and "board" in refused["content"][0]["text"]
    unknown = rpc(c, token, "tools/call", {"name": "nope", "arguments": {}}).json()
    assert unknown["error"]["code"] == -32602
    bad = rpc(
        c, token, "tools/call", {"name": "household_create", "arguments": {"item": {"kind": "nope"}}}
    ).json()
    assert bad["result"]["isError"]

    app.dependency_overrides[require_actor] = lambda: Actor(admin.id, "Ada", "admin", RESIDENT)
    listed = c.get("/api/v1/admin/agents").json()["items"]
    assert listed[0]["calls"] == 4 and listed[0]["last_used_at"]
    assert c.delete("/api/v1/admin/agents/" + listed[0]["id"]).status_code == 200
    app.dependency_overrides.pop(require_actor)
    assert rpc(c, token, "tools/list").status_code == 401


def test_every_group_tool_is_one_of_nox_s_and_none_reaches_setup():
    from houseos import agent_mcp as m
    from houseos.assistant_tools import BUNDLES, tool_catalogue

    names = {n for group in m.GROUPS.values() for n in group}
    assert names <= set(tool_catalogue())
    assert not names & set(BUNDLES["setup"])  # settings, keys, addresses, code: never here
    assert m.READ | m.DESTRUCTIVE | m.OPEN_WORLD | set(m.DOES_IT) <= names
