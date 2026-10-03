"""Setup mode's generic API tools: only the allowlisted settings routes, only for admins; reads
run as the admin, and proposals only the admin's own browser sends (cookie and CSRF) on Confirm."""

import json
from datetime import timedelta

import pytest
from fastapi import HTTPException

from houseos import assistant as a, tool_api as api
from houseos.assistant_tools import ContextSwitch, switch_context
from houseos.auth import Actor, user_permissions
from houseos.config import settings
from houseos.db import new_id, utcnow
from houseos.models import Operation, Record, User
from test_assistant_profiles import seed
from test_core import admin as bootstrap_admin
from test_nox_setup_mode import fake_provider, resident


def run(name, actor, db, **args):
    model, _, handler = api.TOOLS[name]
    return handler(model(**args), actor, db)


def paths(result):
    return {(row["method"], row["path"]) for row in result["routes"]}


def test_every_allowed_setting_is_a_route_and_reads_back(setup, quiet):
    db, (alice, _) = setup
    rows = {(row["method"], row["path"]) for row in api.routes() if row["allowed"]}
    assert rows == api.ALLOWED  # a renamed route fails here, not silently
    for method, path in api.ALLOWED:
        if method == "GET":
            # runs as the admin; /home answers 409 until Home Assistant is connected
            assert run("house_api_read", alice, db, path=path)["http_status"] in {200, 409}, path


def test_the_listing_is_the_allowlist_and_for_admins(setup):
    db, (alice, _) = setup
    assert ("PUT", "/admin/house-settings") in paths(
        run("house_api_routes", alice, db, search="house settings")
    )
    assert ("POST", "/auth/invites") in paths(run("house_api_routes", alice, db, search="invite"))
    found = paths(run("house_api_routes", alice, db, search="changes confirm prepare restart backup"))
    assert not [p for _, p in found if any(w in p for w in ("change", "confirm", "prepare", "service"))]
    assert run("house_api_routes", alice, db)["areas"]["house-settings"] == 2
    with pytest.raises(HTTPException):
        run("house_api_routes", resident(db), db, search="house settings")


def test_a_read_runs_as_the_admin_and_only_on_settings(setup):
    db, (alice, _) = setup
    read = run("house_api_read", alice, db, path="/api/v1/admin/house-settings")
    assert read["http_status"] == 200 and "quiet_start" in read["data"]
    assert run("house_api_read", resident(db), db, path="/admin/house-settings")["http_status"] == 403
    for private in (
        "/household/conversations",  # messages
        "/household/inbox",
        "/personal-space/config",  # personal space
        "/files",  # files
        "/files/x/info",
        "/admin/jobs",  # an admin screen, but not a setting
        "/admin/changes",
        "/auth/sessions",
        "/no/such/thing",
    ):
        refused = run("house_api_read", alice, db, path=private)
        assert refused["http_status"] == 404 and "data" not in refused, private


def test_path_tricks_are_refused(setup):
    db, (alice, _) = setup
    for trick in (
        "/admin/house-settings/../changes",
        "/admin/./house-settings",
        "/admin/%2e%2e/changes",
        "/admin\\house-settings",
        "/admin/house-settings#x",
        "/admin/house-settings?x=1#y",
        "/admin/house settings",
    ):
        assert run("house_api_read", alice, db, path=trick)["http_status"] == 422, trick
        proposed = run("house_api_propose", alice, db, method="PUT", path=trick, body="{}", summary="x")
        assert proposed["status"] == "invalid", trick


def test_unlisted_routes_are_never_proposed(setup):
    db, (alice, _) = setup
    for method, path in (
        ("POST", "/admin/changes/abc/apply"),
        ("POST", "/admin/house-actions/confirm/abc"),
        ("POST", "/admin/house-actions/update/prepare"),
        ("POST", "/admin/services/confirmations/abc"),
        ("POST", "/admin/services/shutdown/prepare"),
        ("POST", "/admin/audio/confirm/abc"),
        ("POST", "/admin/backups/policy/prepare"),
        ("DELETE", "/cinema/devices/abc"),
        ("DELETE", "/admin/languages/pl"),
        ("POST", "/auth/password"),
        ("POST", "/assistant/chat"),
        ("POST", "/files/uploads"),
    ):
        refused = run("house_api_propose", alice, db, method=method, path=path, body="{}", summary="x")
        assert refused["status"] == "not_found", path
    assert not db.query(Operation).filter(Operation.kind == api.PROPOSAL).count()


def test_secret_values_never_come_back_from_a_read():
    found = []
    assert api.hidden(
        {"api_key": "sk-live", "model": "m", "items": [{"token": "t", "idempotency_key": "k"}]}, found
    ) == {
        "api_key": "[hidden]",
        "model": "m",
        "items": [{"token": "[hidden]", "idempotency_key": "k"}],
    }
    assert found == ["api_key", "token"]


def test_a_proposal_stores_exactly_what_the_card_shows(setup):
    db, (alice, _) = setup
    body = {"name": "Maison Bleue", "quiet_start": "22:00"}
    card = run(
        "house_api_propose", alice, db, method="PUT", path="/admin/house-settings", body=json.dumps(body),
        summary="Rename the house and start quiet hours at 22:00",
    )  # fmt: skip
    assert card["status"] == "needs_confirmation" and card["confirmation_path"].startswith(
        "/assistant/proposals/"
    )
    assert card["preview"]["route"] == "Save Settings"  # the route's own words lead the card
    assert card["detail"] == "Rename the house and start quiet hours at 22:00"
    assert card["preview"]["request"] == "PUT /admin/house-settings"
    assert card["preview"]["lines"] == ["name: Maison Bleue", "quiet_start: 22:00"]
    op = db.get(Operation, card["confirmation_id"])
    assert op.actor_id == alice.id and op.state == "needs_confirmation"
    assert op.expires_at > utcnow() + timedelta(minutes=9)
    assert op.data == {"method": "PUT", "path": "/admin/house-settings", "query": "", "body": body,
                       "summary": "Rename the house and start quiet hours at 22:00"}  # fmt: skip
    # Nothing changed yet: only the person's browser sends it.
    assert run("house_api_read", alice, db, path="/admin/house-settings")["data"]["name"] != "Maison Bleue"
    unchanged = run("house_api_propose", alice, db, method="PUT", path="/admin/house-settings",
                    body=json.dumps({"quiet_end": "08:00"}), summary="Quiet hours end at 8")  # fmt: skip
    assert unchanged["status"] == "completed" and "nothing would change" in unchanged["detail"]


def test_refusals_store_nothing(setup):
    db, (alice, _) = setup
    carol = resident(db)

    def propose(actor=alice, **args):
        return run("house_api_propose", actor, db, summary="x", **args)

    secret = propose(
        method="PUT", path="/admin/integrations/openai", body=json.dumps({"config": {"api_key": "sk-1"}})
    )
    assert secret["status"] == "refused" and secret["href"] == "/control?tab=ai"
    assert (
        propose(
            method="PUT",
            path="/admin/users/x",
            body='{"role": "resident", "active": true, "current_password": "p"}',
        )["status"]
        == "refused"
    )
    assert (
        propose(carol, method="PUT", path="/admin/house-settings", body='{"name": "x"}')["status"] == "denied"
    )
    assert (
        propose(method="PUT", path="/admin/house-settings", body='{"motion": "wild"}')["status"] == "invalid"
    )
    assert propose(method="PUT", path="/admin/house-settings", body="{not json")["status"] == "invalid"
    assert not db.query(Operation).filter(Operation.kind == api.PROPOSAL).count()


def test_only_its_owner_takes_a_proposal_once_before_it_expires(setup):
    db, (alice, bob) = setup
    card = run("house_api_propose", alice, db, method="PUT", path="/admin/house-settings",
               body='{"name": "Villa"}', summary="Rename the house")  # fmt: skip
    identity = card["confirmation_id"]
    with pytest.raises(HTTPException) as other:
        api.take(identity, bob, db)
    assert other.value.status_code == 404
    with pytest.raises(HTTPException) as early:
        api.outcome(identity, api.Outcome(ok=True, status=200), alice, db)
    assert early.value.status_code == 409
    assert api.take(identity, alice, db) == {
        "method": "PUT",
        "path": "/admin/house-settings",
        "body": {"name": "Villa"},
    }
    with pytest.raises(HTTPException) as again:
        api.take(identity, alice, db)
    assert again.value.status_code == 409
    late = run("house_api_propose", alice, db, method="PUT", path="/admin/house-settings",
               body='{"name": "Late"}', summary="Rename")  # fmt: skip
    db.get(Operation, late["confirmation_id"]).expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException) as expired:
        api.take(late["confirmation_id"], alice, db)
    assert expired.value.status_code == 409
    [shown] = a.resolved_cards([late], alice, db)
    assert shown["state"] == "expired" and shown["confirmation_id"] is None


def test_the_browser_sends_it_with_the_persons_cookie_and_csrf(client):
    c, db = client
    user = db.get(User, bootstrap_admin(client)["id"])
    owner = Actor(user.id, user.name, user.role, user_permissions(user))
    card = run("house_api_propose", owner, db, method="PUT", path="/admin/house-settings",
               body='{"name": "Maison Bleue"}', summary="Rename the house")  # fmt: skip
    base = "/api/v1/assistant/proposals/" + card["confirmation_id"]
    csrf = c.headers.pop("X-CSRF-Token")
    assert c.post(base + "/take").status_code == 403  # the normal CSRF check: no token, no request
    c.headers["X-CSRF-Token"] = csrf
    request = c.post(base + "/take").json()
    sent = c.request(request["method"], "/api/v1" + request["path"], json=request["body"])
    assert sent.status_code == 200, sent.text
    assert c.get("/api/v1/admin/house-settings").json()["name"] == "Maison Bleue"
    assert c.post(base + "/outcome", json={"ok": True, "status": 200}).json() == {"status": "completed"}
    assert c.post(base + "/take").status_code == 409
    [shown] = a.resolved_cards([card], owner, db)
    assert shown["status"] == "completed" and "done" in shown["message"]


def test_a_new_host_drops_the_stored_key(client, monkeypatch):
    """Through the Control Room's own route: a key never follows a changed address."""
    from cryptography.fernet import Fernet

    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    c, db = client
    bootstrap_admin(client)
    url = "/api/v1/admin/integrations/home_assistant"

    def has_secret():
        rows = c.get("/api/v1/admin/integrations").json()
        return next(r for r in rows if r["name"] == "home_assistant")["has_secret"]

    home = {"base_url": "http://ha.lan:8123"}
    assert c.put(url, json={"enabled": True, "config": home, "secret": "tok"}).status_code == 200
    assert c.put(url, json={"enabled": False, "config": home}).status_code == 200
    assert has_secret()  # same host: the key stays
    moved = {"base_url": "http://elsewhere.example:8123"}
    assert c.put(url, json={"enabled": True, "config": moved}).status_code == 200
    assert not has_secret()
    # The same host on another port or scheme is another place too; the default is its address.
    for config, kept in (({}, True), ({"base_url": "http://127.0.0.1:8123"}, True),
                         ({"base_url": "http://127.0.0.1:8124"}, False), ({"base_url": "https://127.0.0.1:8123"}, False)):  # fmt: skip
        assert c.put(url, json={"enabled": True, "config": {}, "secret": "tok"}).status_code == 200
        assert c.put(url, json={"enabled": True, "config": config}).status_code == 200
        assert has_secret() is kept, config


def test_admins_accounts_off_and_deleting_for_good_stay_on_their_screen(setup):
    db, (alice, bob) = setup
    carol = resident(db)

    def propose(**args):
        return run("house_api_propose", alice, db, summary="x", **args)

    person = {"role": "resident", "active": True, "permissions": []}
    for path, body in (
        (f"/admin/users/{carol.id}", {**person, "role": "admin"}),
        (f"/admin/users/{carol.id}", {**person, "active": False}),
        (f"/admin/users/{bob.id}", person),  # an admin now
    ):
        refused = propose(method="PUT", path=path, body=json.dumps(body))
        assert refused["code"] == "ON_ITS_SCREEN" and refused["href"] == "/control?tab=users", body
    policy = propose(method="PUT", path="/files/admin/policy", body='{"permanent_delete_enabled": true}')
    assert policy["code"] == "ON_ITS_SCREEN" and policy["href"] == "/control?tab=storage"
    ended = propose(method="DELETE", path="/auth/invites/abc?revoke_membership=true")
    assert ended["code"] == "ON_ITS_SCREEN" and ended["href"] == "/control?tab=invites"
    access = propose(method="POST", path="/admin/access", body='{"origin": "https://x.example"}')
    assert access["status"] == "not_found"
    assert not db.query(Operation).filter(Operation.kind == api.PROPOSAL).count()
    # A card names the person, not only their id.
    card = propose(
        method="PUT", path=f"/admin/users/{carol.id}", body=json.dumps({**person, "role": "guest"})
    )
    assert card["status"] == "needs_confirmation"
    assert card["preview"]["lines"][:2] == ["user_id → Carol", "role: guest"]


def test_addresses_are_set_on_their_screen(setup):
    """A new address would send the house's keys, prompts or media to another server."""
    db, (alice, _) = setup
    for path, body, tab in (
        (
            "/admin/integrations/compatible",
            {"enabled": True, "config": {"base_url": "http://evil.example"}},
            "ai",
        ),
        ("/admin/integrations/cast", {"enabled": True, "config": {"host": "10.0.0.9"}}, "integrations"),
        ("/admin/house-settings", {"games_find_url": "https://evil.example"}, "house"),
    ):
        refused = run(
            "house_api_propose", alice, db, method="PUT", path=path, body=json.dumps(body), summary="x"
        )
        assert refused["code"] == "SECRET_ON_SCREEN" and refused["href"].startswith(f"/control?tab={tab}"), (
            path
        )
    assert not db.query(Operation).filter(Operation.kind == api.PROPOSAL).count()


def test_setup_is_never_entered_from_a_chat(setup):
    db, (alice, _) = setup
    shown = switch_context(ContextSwitch(context="setup"), alice, db)
    assert shown["status"] == "completed" and shown["card"]["href"] == "/assistant?mode=setup"
    with pytest.raises(HTTPException):
        switch_context(ContextSwitch(context="setup"), resident(db), db)
    assert "switch_context" not in a.tool_registry("setup")
    assert not set(api.TOOLS) & set(a.tool_registry("general"))


def test_a_config_request_in_chat_gets_the_setup_mode_button(setup, quiet, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    seen = {}
    propose = {"method": "PUT", "path": "/admin/house-settings", "body": '{"name": "Villa"}', "summary": "x"}
    fake_provider(monkeypatch, [
        ("", [{"id": "1", "name": "house_api_propose", "args": propose}]),
        ("", [{"id": "2", "name": "switch_context", "args": {"context": "setup"}}]),
        ("Tap the button to open setup mode.", []),
    ], seen)  # fmt: skip
    message = "Rename the house to Villa"
    result = a.chat(a.Chat(message=message, idempotency_key=new_id()), alice, db)
    [button] = [c for c in result["cards"] if c.get("href") == "/assistant?mode=setup"]
    assert button["ask"] == message and button["domain"] == "setup"
    assert db.get(Record, result["conversation_id"]).data["assistant_context"] != "setup"
    assert "house_api_propose" not in seen["tools"]
    assert not db.query(Operation).filter(Operation.kind == api.PROPOSAL).count()
