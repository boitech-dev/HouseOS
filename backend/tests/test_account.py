"""Account privacy and complete export on actor-scoped fixtures; no provider calls."""

import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from houseos import account, assistant, files
from houseos import notifications  # noqa: F401 - register push table before fixture create_all
from houseos.auth import Actor, passwords
from houseos.db import new_id, utcnow
from houseos.models import Record, SessionToken, User
from test_household_files import create


def password(db, actor):
    user = db.get(User, actor.id)
    user.password_hash = passwords.hash("fixture-password")
    db.commit()
    return account.Reauthenticate(current_password="fixture-password")


def test_profile_and_memory_disable_preserve_other_preferences(domain):
    db, (alice, _, _) = domain
    user = db.get(User, alice.id)
    user.preferences = {"motion": "still", "ai_daily_budgets": {"openai": 500}}
    db.commit()
    assistant.save_memory(assistant.Memory(text="Stored explicitly"), alice, db)
    result = account.edit_profile(
        account.Profile(name="  Alice New  ", language="fr", avatar="moon", memory_enabled=False), alice, db
    )
    assert result["name"] == "Alice New" and result["memory_enabled"] is False
    assert db.get(User, alice.id).preferences["ai_daily_budgets"] == {"openai": 500}
    assert assistant.enabled_memories(alice, db) == []
    assert len(assistant.memories(alice, db)) == 1  # management/export remains available
    with pytest.raises(HTTPException):
        assistant.save_memory(assistant.Memory(text="Must not save"), alice, db)
    with pytest.raises(ValidationError):
        account.Profile(avatar="https://arbitrary.site/tracker", role="admin")


def test_export_pages_all_memories_and_excludes_other_users_and_secrets(domain):
    db, (alice, bob, _) = domain
    for index in range(405):
        db.add(Record(owner_id=alice.id, kind="memory", data={"text": f"Own memory {index}"}))
    db.add(Record(owner_id=bob.id, kind="memory", data={"text": "BOB_PRIVATE_MARKER"}))
    db.add(Record(owner_id=alice.id, kind="music.playlist", data={"name": "Own playlist", "items": []}))
    db.commit()
    document = json.loads("".join(account.export_body(db.get_bind(), alice)))
    assert document["complete"] is True and len(document["memories"]) == 405
    assert document["saved_music"][0]["data"]["name"] == "Own playlist"
    raw = json.dumps(document)
    assert "BOB_PRIVATE_MARKER" not in raw and "password_hash" not in document["account"]
    assert "encrypted_secret" not in raw and "session_hash" not in raw


def test_account_delete_revokes_private_access_preserves_shared_and_trashes_files(domain):
    db, (alice, bob, _) = domain
    body = password(db, alice)
    note = create(db, alice, "board", {"title": "Keep shared board"})
    message = create(db, alice, "messages", {"body": "Keep delivered message", "recipient_ids": [bob.id]})
    memory = assistant.save_memory(assistant.Memory(text="Private memory"), alice, db)
    personal = files.FileEntry(owner_id=alice.id, scope="personal", name="personal.txt", size=2)
    shared = files.FileEntry(owner_id=alice.id, scope="house", name="shared.txt", size=2)
    db.add_all([personal, shared])
    db.flush()
    db.add(files.FileGrant(file_id=personal.id, user_id=bob.id))
    db.add(
        SessionToken(
            token_hash="a" + new_id().replace("-", "") + new_id().replace("-", "")[:31],
            user_id=alice.id,
            csrf_token="fixture",
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    db.commit()
    prepared = account.prepare_delete(body, alice, db)
    assert prepared["preview"]["personal_files"] == 1
    result = account.confirm_delete(prepared["confirmation_id"], body, alice, db)
    assert result["status"] == "completed"
    db.expire_all()
    assert db.get(User, alice.id).active is False and db.get(User, alice.id).name == "Former resident"
    assert db.get(Record, memory["id"]).data == {}
    assert db.get(Record, note["id"]).data["title"] == "Keep shared board"
    assert db.get(Record, message["id"]).data["body"] == "Keep delivered message"
    assert db.get(files.FileEntry, personal.id).trashed_at is not None
    assert db.get(files.FileEntry, personal.id).storage_removed_at is None
    assert db.get(files.FileEntry, shared.id).trashed_at is None
    assert not db.scalars(select(SessionToken).where(SessionToken.user_id == alice.id)).all()
    assert not db.scalars(select(files.FileGrant).where(files.FileGrant.file_id == personal.id)).all()
    with pytest.raises(HTTPException):
        account.confirm_delete(prepared["confirmation_id"], body, alice, db)


def test_account_delete_requires_unchanged_preview_and_own_actor(domain):
    db, (alice, bob, _) = domain
    body = password(db, alice)
    password(db, bob)
    prepared = account.prepare_delete(body, alice, db)
    with pytest.raises(HTTPException) as wrong:
        account.confirm_delete(prepared["confirmation_id"], body, bob, db)
    assert wrong.value.status_code == 409
    db.rollback()
    assistant.save_memory(assistant.Memory(text="Added after preview"), alice, db)
    with pytest.raises(HTTPException) as changed:
        account.confirm_delete(prepared["confirmation_id"], body, alice, db)
    assert changed.value.status_code == 409 and "changed" in changed.value.detail
    assert db.get(User, alice.id).active is True


def test_account_delete_refuses_active_upload(domain):
    db, (alice, _, _) = domain
    body = password(db, alice)
    db.add(
        files.UploadReservation(
            owner_id=alice.id,
            request_key=new_id(),
            name="active.txt",
            parent_id="",
            scope="personal",
            size=5,
            status="uploading",
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    db.commit()
    prepared = account.prepare_delete(body, alice, db)
    with pytest.raises(HTTPException) as blocked:
        account.confirm_delete(prepared["confirmation_id"], body, alice, db)
    assert blocked.value.status_code == 409 and "uploads" in blocked.value.detail


def test_last_administrator_guard_on_isolated_sqlite():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from houseos.db import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            id=new_id(),
            username="only-admin",
            name="Admin",
            role="admin",
            password_hash=passwords.hash("fixture-password"),
        )
        db.add(user)
        db.commit()
        actor = Actor(user.id, user.name, "admin", frozenset())
        body = account.Reauthenticate(current_password="fixture-password")
        prepared = account.prepare_delete(body, actor, db)
        with pytest.raises(HTTPException) as stopped:
            account.confirm_delete(prepared["confirmation_id"], body, actor, db)
        assert stopped.value.status_code == 409 and "last administrator" in stopped.value.detail
        db.rollback()
        assert db.get(User, user.id).active is True
    engine.dispose()


def test_file_pagination_has_deterministic_nonoverlapping_pages(domain):
    db, (alice, _, _) = domain
    for name in ("C.pdf", "A.pdf", "B.pdf"):
        db.add(files.FileEntry(owner_id=alice.id, scope="personal", name=name))
    db.commit()
    first = files.list_files("personal", None, "", 2, alice, db, 0)
    second = files.list_files("personal", None, "", 2, alice, db, first["next_offset"])
    assert [item["name"] for item in first["items"] + second["items"]] == ["A.pdf", "B.pdf", "C.pdf"]
    assert second["next_offset"] is None


def test_release_evaluation_is_substantive_and_not_claimed_live_pass():
    from pathlib import Path

    fixture = json.loads((Path(__file__).parent / "fixtures/assistant_evaluation.json").read_text())
    assert len(fixture["cases"]) >= 30
    assert {case["language"] for case in fixture["cases"]} >= {"en", "fr"}
    assert len({case["id"] for case in fixture["cases"]}) == len(fixture["cases"])
    assert all(
        case["live_result"]["status"] == "not_run" and case["expected"]["outcome"]
        for case in fixture["cases"]
    )


def test_export_revocation_never_emits_complete_marker(domain):
    from test_security import with_session
    from sqlalchemy.orm import Session
    from sqlalchemy import delete

    db, (alice, _, _) = domain
    alice = with_session(db, alice)
    stream = account.export_body(db.get_bind(), alice)
    first = next(stream)
    with Session(db.get_bind()) as other:
        other.execute(delete(SessionToken).where(SessionToken.token_hash == alice.session_hash))
        other.commit()
    with pytest.raises(HTTPException) as revoked:
        "".join(stream)
    assert revoked.value.status_code == 401 and '"complete":true' not in first
