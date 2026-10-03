from datetime import timedelta
import pytest
from houseos.db import utcnow, new_id
from houseos.config import settings
from houseos.models import User, SessionToken, Integration, Usage
from houseos.music import canonical_source
from houseos.auth import Actor, RESIDENT
from houseos.assistant import reserve, strict_schema


def admin(client):
    c, db = client
    response = c.post(
        "/api/v1/auth/bootstrap",
        json={
            "name": "Test Admin",
            "username": "testadmin",
            "password": "test-only-password-very-long",
            "setup_token": settings.bootstrap_token,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    c.headers["X-CSRF-Token"] = result["csrf_token"]
    return result["user"]


def test_bootstrap_sessions_csrf_and_no_secret_reflection(client):
    c, db = client
    assert c.get("/api/v1/auth/status").json() == {"setup_required": True}
    response = c.post("/api/v1/auth/bootstrap", json={"password": "secret-invalid"})
    assert "secret-invalid" not in response.text
    user = admin(client)
    assert c.get("/api/v1/auth/me").json()["user"]["id"] == user["id"]
    assert c.get("/api/v1/auth/status").json() == {"setup_required": False}
    c.headers.pop("X-CSRF-Token")
    assert c.put("/api/v1/preferences", json={}).status_code == 403
    c.headers["X-CSRF-Token"] = c.get("/api/v1/auth/me").json()["csrf_token"]
    assert (
        c.put("/api/v1/preferences", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    )
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 401


def test_a_screen_guest_may_use_the_tv_and_welcomes_are_remembered(client):
    c, db = client
    admin(client)
    invite = c.post("/api/v1/auth/invites", json={"preset": "screen", "expires_hours": 2}).json()
    assert invite["permissions"] == ["cinema.use", "music.queue", "music.read"]
    assert c.put("/api/v1/preferences", json={"onboarded": "admin", "tour_seen": True}).status_code == 200
    saved = c.get("/api/v1/preferences").json()
    assert saved["onboarded"] == "admin" and saved["tour_seen"] is True
    assert c.put("/api/v1/preferences", json={"onboarded": "boss"}).status_code == 422


def test_invite_expiry_guest_grants_and_revocation(client):
    c, db = client
    admin(client)
    response = c.post("/api/v1/auth/invites", json={"preset": "party", "expires_hours": 2})
    assert response.status_code == 200, response.text
    invite = response.json()
    admin_cookie = c.cookies.get("houseos_session")
    admin_csrf = c.headers["X-CSRF-Token"]
    response = c.post(
        "/api/v1/auth/redeem",
        json={
            "token": invite["token"],
            "name": "Guest",
            "username": "guest123",
            "password": "another-test-password",
        },
    )
    assert response.status_code == 200, response.text
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert c.get("/api/v1/people").status_code == 403
    assert c.get("/api/v1/assistant/conversations").status_code == 403
    assert c.get("/api/v1/admin/users").status_code == 403
    guest_cookie = c.cookies.get("houseos_session")
    c.cookies.clear()
    c.cookies.set("houseos_session", admin_cookie)
    c.headers["X-CSRF-Token"] = admin_csrf
    # A window lights only for people with HouseOS open (their live connection polled recently).
    from houseos import core
    import time

    people = c.get("/api/v1/people").json()
    core.PRESENT[people[0]["id"]] = time.monotonic()
    lit = {p["id"]: p["home"] for p in c.get("/api/v1/people").json()}
    assert lit[people[0]["id"]] and not any(v for k, v in lit.items() if k != people[0]["id"])
    core.PRESENT.clear()
    assert c.delete("/api/v1/auth/invites/" + invite["id"] + "?revoke_membership=true").status_code == 200
    c.cookies.clear()
    c.cookies.set("houseos_session", guest_cookie)
    assert c.get("/api/v1/auth/me").status_code == 401


def test_music_idempotency_unsafe_sources_and_conflicts(client):
    c, db = client
    admin(client)
    for url in [
        "http://127.0.0.1/",
        "https://youtube.com@127.0.0.1/",
        "file:///etc/passwd",
        "https://soundcloud.com/a/sets/b",
    ]:
        with pytest.raises(Exception):
            canonical_source(url)
    key = new_id()
    body = {"source_url": "https://youtu.be/K4DyBUG242c", "idempotency_key": key}
    first = c.post("/api/v1/music/queue", json=body)
    assert first.status_code == 200, first.text
    assert c.post("/api/v1/music/queue", json=body).json()["item_id"] == first.json()["item_id"]
    assert (
        c.post(
            "/api/v1/music/control",
            json={"action": "play", "expected_version": 1, "idempotency_key": new_id()},
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/v1/music/control",
            json={"action": "play", "expected_version": 2, "idempotency_key": new_id()},
        ).status_code
        == 409
    )


def test_budget_reservation_and_private_usage(client):
    c, db = client
    user = admin(client)
    cfg = {
        "model": "configured-model",
        "input_microusd_per_million": 1_000_000,
        "output_microusd_per_million": 1_000_000,
        "daily_budget_microusd": 10_000,
        "user_daily_budget_microusd": 10_000,
    }
    db.add(Integration(name="openai", enabled=True, config=cfg))
    db.commit()
    actor = Actor(user["id"], "Admin", "admin", RESIDENT)
    identity = reserve(db, actor, "openai", cfg, [{"role": "user", "content": "hello"}], [])
    assert db.get(Usage, identity).reserved_microusd > 800
    cfg["daily_budget_microusd"] = 1
    db.get(Integration, "openai").config = dict(cfg)
    db.commit()
    with pytest.raises(Exception) as exceeded:
        reserve(db, actor, "openai", cfg, [], [])
    assert exceeded.value.status_code == 429
    report = c.get("/api/v1/usage").json()
    assert report["totals"]["unpriced_requests"] == 1
    assert not report["content_included"]


def test_strict_tool_schema():
    schema = strict_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}, "amount": {"type": "number", "default": 1}},
            "required": ["name"],
        }
    )
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["name", "amount"]
    assert {"type": "null"} in schema["properties"]["amount"]["anyOf"]


def test_expired_admin_does_not_satisfy_last_admin_guard(client):
    c, db = client
    user = admin(client)
    db.add(
        User(
            name="Expired",
            username="expired-admin",
            password_hash="not-used",
            role="admin",
            expires_at=utcnow() - timedelta(seconds=1),
        )
    )
    db.commit()
    result = c.put(
        "/api/v1/admin/users/" + user["id"],
        json={"active": False, "role": "resident", "current_password": "test-only-password-very-long"},
    )
    assert result.status_code == 409


def test_admin_operations_use_session_not_repeated_password(client, monkeypatch):
    from houseos import audio_admin, control_room
    from sqlalchemy import delete

    c, db = client
    admin_user = admin(client)
    other = User(name="Resident", username="resident-admin-test", password_hash="unused", role="resident")
    db.add(other)
    db.commit()
    monkeypatch.setattr(
        audio_admin, "bridge", lambda command: {"items": [{"id": "fixture-speaker"}], "selected": None}
    )
    monkeypatch.setattr(
        control_room, "broker", lambda *args: {"status": "observed", "invocation_id": "fixture"}
    )
    requests = [
        ("put", "/admin/users/" + other.id + "/budgets", {"daily_microusd": {"openai": 1000}}),
        ("put", "/admin/users/" + other.id, {"active": True, "role": "resident"}),
        ("post", "/admin/audio/prepare", {"action": "select", "sink": "fixture-speaker"}),
        ("post", "/admin/services/worker/prepare-restart", {}),
        (
            "post",
            "/admin/backups/policy/prepare",
            {"uploads_enabled": True, "scopes": ["personal"], "max_bytes": 1024**3},
        ),
    ]
    for method, path, body in requests:
        response = getattr(c, method)("/api/v1" + path, json=body)
        assert response.status_code == 200, response.text
        if method == "post":
            assert response.json()["status"] == "needs_confirmation"
    # Session CSRF, current role and session revocation still protect every operation.
    csrf = c.headers.pop("X-CSRF-Token")
    assert (
        c.put("/api/v1/admin/users/" + other.id + "/budgets", json={"daily_microusd": {}}).status_code == 403
    )
    c.headers["X-CSRF-Token"] = csrf
    db.get(User, admin_user["id"]).role = "resident"
    db.commit()
    for method, path, body in requests:
        assert getattr(c, method)("/api/v1" + path, json=body).status_code == 403
    db.get(User, admin_user["id"]).role = "admin"
    db.execute(delete(SessionToken).where(SessionToken.user_id == admin_user["id"]))
    db.commit()
    for method, path, body in requests:
        assert getattr(c, method)("/api/v1" + path, json=body).status_code == 401


def test_account_deletion_uses_session_and_exact_preview_without_password(client):
    c, db = client
    user = admin(client)
    prepared = c.post("/api/v1/account/delete/prepare", json={})
    assert prepared.status_code == 200, prepared.text
    identity = prepared.json()["confirmation_id"]
    # Sole-admin protection survives removal of the redundant password prompt.
    assert c.post("/api/v1/account/delete/confirm/" + identity, json={}).status_code == 409
    db.add(User(name="Other Admin", username="other-active-admin", role="admin", password_hash="unused"))
    db.commit()
    result = c.post("/api/v1/account/delete/confirm/" + identity, json={})
    assert result.status_code == 200, result.text
    assert not db.get(User, user["id"]).active
    assert c.get("/api/v1/auth/me").status_code == 401
    assert c.post("/api/v1/account/delete/confirm/" + identity, json={}).status_code == 401


def test_partial_preferences_preserve_clock_sounds_and_language(client):
    c, db = client
    admin(client)
    assert c.patch("/api/v1/account/profile", json={"language": "fr"}).status_code == 200
    assert c.put("/api/v1/preferences", json={"time_display": "12h", "sounds": True}).status_code == 200
    assert c.put("/api/v1/preferences", json={"motion": "still"}).status_code == 200
    result = c.get("/api/v1/preferences").json()
    assert result["time_display"] == "12h" and result["sounds"] is True and result["language"] == "fr"


def test_admin_signs_someone_out_everywhere(client):
    from houseos.core import PRESENT

    c, db = client
    me = admin(client)
    other = User(name="Resident", username="resident-sign-out", password_hash="unused", role="resident")
    db.add(other)
    db.commit()
    db.add(SessionToken(user_id=other.id, token_hash="fixture-sign-out", csrf_token="fixture", expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    PRESENT[other.id] = 1e12
    assert c.post(f"/api/v1/admin/users/{me['id']}/sign-out").status_code == 409  # not yourself
    assert c.post("/api/v1/admin/users/nobody/sign-out").status_code == 404
    result = c.post(f"/api/v1/admin/users/{other.id}/sign-out")
    assert result.status_code == 200 and result.json()["sessions_revoked"] == 1
    assert other.id not in PRESENT
    db.get(User, me["id"]).role = "resident"
    db.commit()
    assert c.post(f"/api/v1/admin/users/{other.id}/sign-out").status_code == 403
