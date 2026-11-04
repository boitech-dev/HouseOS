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
    made = c.post(
        "/api/v1/admin/agents",
        json={"name": "Assistant", "user_id": admin.id, "groups": ["board"], "tools": "all"},
    )
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


def test_calls_are_recorded_for_the_agents_screen_and_widgets_read_the_house_with_the_token(
    client, monkeypatch
):
    from houseos import agent_now

    monkeypatch.setattr(agent_now, "ROUNDS", 1)  # the test client reads a stream once it ends
    c, db = client
    admin = User(
        id=new_id(), name="Ada", username="ada2", password_hash="x", role="admin", permissions=list(RESIDENT)
    )
    db.add(admin)
    db.commit()
    app.dependency_overrides[require_actor] = lambda: Actor(admin.id, "Ada", "admin", RESIDENT)
    made = c.post(
        "/api/v1/admin/agents", json={"name": "Widget", "user_id": admin.id, "groups": ["board"]}
    ).json()
    app.dependency_overrides.pop(require_actor)
    token, bearer = made["token"], {"Authorization": "Bearer " + made["token"]}

    # A widget's button: a tool by name, plain JSON back, from any site (bearer, no cookie).
    done = c.post("/api/v1/agent/act", headers={**bearer, "Origin": "https://assistant.example"},
                  json={"tool": "board_add", "arguments": {"kind": "grocery", "text": "Rice"}})  # fmt: skip
    assert done.status_code == 200 and done.json()["ok"], done.text
    assert done.headers["access-control-allow-origin"] == "*"
    assert c.options("/api/v1/agent/now", headers={"Origin": "https://assistant.example"}).status_code == 204
    refused = c.post("/api/v1/agent/act", headers=bearer, json={"tool": "music_control", "arguments": {}})
    assert refused.status_code == 403  # not in its groups

    # The snapshot: only its groups; the token also works as ?access_token= (EventSource).
    now = c.get("/api/v1/agent/now?parts=board,music", headers=bearer).json()
    assert "board" in now and "music" not in now and "at" in now
    assert "Rice" in json.dumps(now["board"]["groceries"])
    assert c.get("/api/v1/agent/now?access_token=" + token).status_code == 200
    assert c.get("/api/v1/agent/now").status_code == 401
    assert c.get("/api/v1/agent/now?parts=weather", headers=bearer).status_code == 422
    lines = c.get("/api/v1/agent/stream?parts=board", headers=bearer).text.splitlines()
    assert lines[0] == "event: now" and "Rice" in lines[1]

    # What it did, for Control Room → Agents: when, which tool, a summary without private text.
    app.dependency_overrides[require_actor] = lambda: Actor(admin.id, "Ada", "admin", RESIDENT)
    calls = c.get(f"/api/v1/admin/agents/{made['id']}/calls").json()["items"]
    app.dependency_overrides.pop(require_actor)
    first = calls[-1]
    assert first["tool"] == "board_add" and first["ok"] and isinstance(first["ms"], int)
    assert first["args"] == {"kind": "grocery", "text": "<4 characters>"}  # words a person wrote stay out


def test_the_lean_set_answers_everyday_asks_in_one_call_each(client):
    c, db = client
    admin = User(
        id=new_id(), name="Bea", username="bea", password_hash="x", role="admin", permissions=list(RESIDENT)
    )
    db.add(admin)
    db.commit()
    app.dependency_overrides[require_actor] = lambda: Actor(admin.id, "Bea", "admin", RESIDENT)
    made = c.post(
        "/api/v1/admin/agents", json={"name": "Lean", "user_id": admin.id, "groups": ["board", "music"]}
    ).json()
    app.dependency_overrides.pop(require_actor)
    assert made["tools"] == "essential"  # the default
    token = made["token"]
    hello = rpc(c, token, "initialize", {"protocolVersion": "2025-11-25"}).json()["result"]
    assert "music_play" in hello["instructions"] and len(hello["instructions"]) < 1800
    before = hello["serverInfo"]["version"]  # ends with the tool list's fingerprint
    names = [t["name"] for t in rpc(c, token, "tools/list").json()["result"]["tools"]]
    assert names[0] == "house_now" and {"music_play", "board_add", "music_control"} <= set(names)
    assert "music_search" not in names and "household_create" not in names and len(names) <= 12

    # Groceries, a task for someone, an event at a time: one call each, said in one line.
    said = rpc(
        c,
        token,
        "tools/call",
        {"name": "board_add", "arguments": {"kind": "grocery", "text": "Rice", "more": ["Eggs"]}},
    ).json()["result"]
    assert not said["isError"] and "Added 2" in said["content"][0]["text"]
    task = {"kind": "task", "text": "Bins out", "date": "2026-11-03", "who": "Be"}
    assert (
        "Task added"
        in rpc(c, token, "tools/call", {"name": "board_add", "arguments": task}).json()["result"]["content"][
            0
        ]["text"]
    )
    event = {"kind": "event", "text": "Dinner", "date": "2026-11-03", "time": "19:30", "minutes": 90}
    assert (
        "calendar"
        in rpc(c, token, "tools/call", {"name": "board_add", "arguments": event}).json()["result"]["content"][
            0
        ]["text"]
    )
    nobody = rpc(c, token, "tools/call", {"name": "board_add", "arguments": {**task, "who": "Zed"}}).json()[
        "result"
    ]
    assert nobody["isError"] and "Which resident" in nobody["content"][0]["text"]
    now = rpc(c, token, "tools/call", {"name": "house_now", "arguments": {}}).json()["result"]["content"][0][
        "text"
    ]
    assert "Rice" in now and "Bins out" in now

    # All of them, when the admin switches the token.
    app.dependency_overrides[require_actor] = lambda: Actor(admin.id, "Bea", "admin", RESIDENT)
    assert c.put("/api/v1/admin/agents/" + made["id"], json={"tools": "all"}).json()["tools"] == "all"
    app.dependency_overrides.pop(require_actor)
    assert "music_search" in [t["name"] for t in rpc(c, token, "tools/list").json()["result"]["tools"]]
    after = rpc(c, token, "initialize", {"protocolVersion": "2025-11-25"}).json()["result"]["serverInfo"][
        "version"
    ]
    assert after != before  # its tools changed: a client sees it at its next initialize


def test_music_play_turns_words_into_queued_songs_in_one_call(monkeypatch):
    from houseos import assistant_tools as t, music

    monkeypatch.setattr(
        music,
        "search",
        lambda q, source, actor, db, limit: {
            "items": [{"id": f"c{n}", "title": f"Song {n}"} for n in range(5)]
        },
    )
    queued = []

    def add(body, actor, db):
        queued.append(body.candidate_ids)
        return {
            "status": "accepted",
            "items": [{"item_id": i, "title": "Song " + i[1:]} for i in body.candidate_ids],
            "autoplay_requested": True,
        }

    monkeypatch.setattr(music, "add_candidates", add)
    said = t.music_play(t.MusicPlay(query="songs by Someone", count=3), None, None)
    assert queued == [["c0", "c1", "c2"]] and said["message"].startswith("Starting now: “Song 0”")
