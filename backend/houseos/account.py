"""Own-account profile, complete streamed export and exact, reversible-byte deletion."""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, UTC
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator
from sqlalchemy import delete, select, update, or_
from sqlalchemy.orm import Session

from .auth import Input, passwords, refresh_actor, require_actor, account_usable
from .db import get_db, utcnow
from .events import emit
from .models import Invite, Job, Operation, Record, SessionToken, Usage, User

router = APIRouter(prefix="/account", tags=["account"])
PERSONAL_KINDS = {
    "conversation",
    "memory",
    "household.captures",
    "saved_track",
    "music_candidate",
    "music.playlist",
    "music.skip_vote",
    "music.veto",
}
PREFERENCE_KEYS = {
    "motion",
    "seen_release",
    "onboarded",
    "tour_seen",
    "theme",
    "scheme",
    "timezone",
    "notifications",
    "notification_settings",
    "language",
    "avatar",
    "memory_enabled",
    "ai_daily_budgets",
    "time_display",
    "sounds",
    "home_favorites",
    "welcome_dismissed",
}
RETENTION = (
    "Shared posts, tasks, messages already delivered to recipients, shared files, usage/audit totals and sanitized operational history retain a former-resident attribution. "
    "Personal files move to Trash; bytes are not immediately erased. Protected backups may retain prior content until their configured expiry. "
    "Already-running physical playback may continue; no remote device is silently stopped."
)


class Profile(Input):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    language: str | None = Field(default=None, pattern="^[a-z]{2,3}$")
    avatar: Literal["crest", "moon", "raven", "bat", "rose", "ghost"] | None = None
    memory_enabled: bool | None = None
    welcome_dismissed: bool | None = None  # the admin's first-run welcome: "Don't show again"

    @field_validator("name")
    @classmethod
    def visible_name(cls, value):
        if value is not None:
            value = value.strip()
            if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("Use a visible display name")
        return value


def public_profile(user, default_language="en"):
    prefs = user.preferences or {}
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "language": prefs.get("language", default_language),
        "avatar": prefs.get("avatar", "crest"),
        "memory_enabled": prefs.get("memory_enabled", True),
        "welcome_dismissed": bool(prefs.get("welcome_dismissed", False)),
    }


@router.get("/profile")
def profile(actor=Depends(require_actor), db=Depends(get_db)):
    from .house_settings import resident_defaults

    return public_profile(db.get(User, actor.id), resident_defaults(db, actor.role)["language"])


@router.patch("/profile")
def edit_profile(body: Profile, actor=Depends(require_actor), db=Depends(get_db)):
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if not user or not user.active:
        raise HTTPException(401, "Account is inactive")
    values = body.model_dump(exclude_none=True)
    if "language" in values:
        from .languages import ensure_ready

        ensure_ready(db, values["language"])
    if "name" in values:
        user.name = values.pop("name")
    user.preferences = {**(user.preferences or {}), **values}
    emit(db, "account.updated", {"fields": sorted(body.model_fields_set)}, actor.id)
    db.commit()
    from .house_settings import resident_defaults

    return public_profile(user, resident_defaults(db, actor.role)["language"])


def json_value(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()
    raise TypeError("Unsupported export value")


def export_body(bind, actor):
    """Keyset-page every dataset, rechecking session each page; no silent row cap."""
    from .assistant import ChatMessage
    from .cinema import CinemaPreference, CinemaState
    from .files import FileEntry, entry_json
    from .household import MessageRecipient

    started = utcnow()
    with Session(bind) as db:
        actor = refresh_actor(db, actor)
        user = db.get(User, actor.id)
        header = {
            "format": "houseos-account-v1",
            "started_at": started,
            "consistency": "Live keyset read, not a point-in-time snapshot; concurrent changes may appear or be omitted. Complete means all sections finished without truncation.",
            "account": public_profile(user),
            "preferences": {
                key: value for key, value in (user.preferences or {}).items() if key in PREFERENCE_KEYS
            },
            "excluded": [
                "password hashes",
                "sessions and tokens",
                "provider secrets",
                "other residents' private data",
                "file bytes",
                "raw internal media URLs",
            ],
        }
    yield json.dumps(header, default=json_value, ensure_ascii=False)[:-1]

    def record(row):
        return {
            "id": row.id,
            "kind": row.kind,
            "data": row.data,
            "version": row.version,
            "created_at": row.created_at,
        }

    sections = [
        (
            "memories",
            Record,
            select(Record).where(
                Record.owner_id == actor.id, Record.kind == "memory", Record.deleted_at.is_(None)
            ),
            record,
        ),
        (
            "conversations",
            Record,
            select(Record).where(
                Record.owner_id == actor.id, Record.kind == "conversation", Record.deleted_at.is_(None)
            ),
            lambda row: {
                "id": row.id,
                "title": row.data.get("title"),
                "created_at": row.created_at,
                "recent_message_order": row.data.get("message_ids", []),
            },
        ),
        (
            "conversation_messages",
            ChatMessage,
            select(ChatMessage)
            .join(Record, Record.id == ChatMessage.conversation_id)
            .where(ChatMessage.owner_id == actor.id, Record.deleted_at.is_(None)),
            lambda row: {
                "id": row.id,
                "conversation_id": row.conversation_id,
                "role": row.role,
                "content": row.content,
                "cards": row.cards,
                "created_at": row.created_at,
            },
        ),
        (
            "authored_household",
            Record,
            select(Record).where(
                Record.owner_id == actor.id,
                Record.kind.in_(
                    [
                        "household.board",
                        "household.tasks",
                        "household.groceries",
                        "household.calendar",
                        "household.messages",
                        "household.captures",
                    ]
                ),
                Record.deleted_at.is_(None),
            ),
            record,
        ),
        (
            "received_messages",
            Record,
            select(Record)
            .join(MessageRecipient, MessageRecipient.message_id == Record.id)
            .where(
                MessageRecipient.user_id == actor.id,
                Record.kind == "household.messages",
                Record.owner_id != actor.id,
                Record.deleted_at.is_(None),
            ),
            record,
        ),
        (
            "shared_watchlist",
            Record,
            select(Record).where(
                Record.owner_id == actor.id,
                Record.kind == "cinema.shared_watchlist",
                Record.deleted_at.is_(None),
            ),
            record,
        ),
        (
            "saved_music",
            Record,
            select(Record).where(
                Record.owner_id == actor.id,
                Record.kind.in_(["saved_track", "music.playlist"]),
                Record.deleted_at.is_(None),
            ),
            record,
        ),
        (
            "file_metadata",
            FileEntry,
            select(FileEntry).where(FileEntry.owner_id == actor.id, FileEntry.deleted_at.is_(None)),
            entry_json,
        ),
        (
            "cinema_state",
            CinemaState,
            select(CinemaState).where(CinemaState.owner_id == actor.id),
            lambda row: {"id": row.id, "media_id": row.media_id, "data": row.data, "version": row.version},
        ),
        (
            "usage",
            Usage,
            select(Usage).where(Usage.user_id == actor.id),
            lambda row: {
                key: getattr(row, key)
                for key in (
                    "id",
                    "provider",
                    "model",
                    "input_tokens",
                    "output_tokens",
                    "cached_tokens",
                    "cost_microusd",
                    "status",
                    "latency_ms",
                    "tool_calls",
                    "created_at",
                )
            },
        ),
    ]
    for name, model, query, serialize in sections:
        yield ',"' + name + '":['
        cursor, first = None, True
        while True:
            with Session(bind) as db:
                refresh_actor(db, actor)
                page = query.where(model.id > cursor) if cursor else query
                rows = db.scalars(page.order_by(model.id).limit(200)).all()
                data = [(row.id, serialize(row)) for row in rows]
            for identity, item in data:
                yield ("" if first else ",") + json.dumps(item, default=json_value, ensure_ascii=False)
                cursor, first = identity, False
            if len(data) < 200:
                break
        yield "]"
    with Session(bind) as db:
        refresh_actor(db, actor)
        prefs = db.get(CinemaPreference, actor.id)
        yield ',"cinema_preferences":' + json.dumps(prefs.data if prefs else {}, default=json_value)
    yield ',"complete":true}'


@router.get("/export")
def export(actor=Depends(require_actor), db=Depends(get_db)):
    return StreamingResponse(
        export_body(db.get_bind(), actor),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="houseos-account.json"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


class Reauthenticate(Input):
    current_password: str | None = Field(default=None, max_length=256)


def deletion_snapshot(db, user, lock=False):
    from .assistant import ChatMessage
    from .cinema import CinemaState
    from .files import FileEntry

    digest = hashlib.sha256(
        json.dumps(
            {"id": user.id, "name": user.name, "role": user.role, "preferences": user.preferences},
            sort_keys=True,
        ).encode()
    )
    scopes = [
        (
            "private_records",
            select(Record.id, Record.version).where(
                Record.owner_id == user.id,
                Record.kind.in_(PERSONAL_KINDS),
                Record.visibility == "private",
                Record.deleted_at.is_(None),
            ),
        ),
        (
            "conversation_messages",
            select(ChatMessage.id, ChatMessage.created_at).where(ChatMessage.owner_id == user.id),
        ),
        (
            "personal_files",
            select(FileEntry.id, FileEntry.version).where(
                FileEntry.owner_id == user.id, FileEntry.scope == "personal", FileEntry.deleted_at.is_(None)
            ),
        ),
        ("cinema_state", select(CinemaState.id, CinemaState.version).where(CinemaState.owner_id == user.id)),
    ]
    counts = {}
    for name, query in scopes:
        counts[name] = 0
        for row in db.execute(
            (query.with_for_update() if lock else query).order_by(query.selected_columns[0])
        ):
            digest.update(json.dumps([name, *row], default=json_value).encode())
            counts[name] += 1
    return {"fingerprint": digest.hexdigest(), "counts": counts}


def active_account(db, actor):
    user = db.get(User, actor.id)
    if not account_usable(user):
        raise HTTPException(401, "Account is inactive or expired")
    return user


@router.post("/delete/prepare")
def prepare_delete(body: Reauthenticate, actor=Depends(require_actor), db=Depends(get_db)):
    user = active_account(db, actor)
    snapshot = deletion_snapshot(db, user)
    row = Operation(
        actor_id=actor.id,
        kind="account.delete",
        state="needs_confirmation",
        expires_at=utcnow() + timedelta(minutes=2),
        data=snapshot,
    )
    db.add(row)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": row.id,
        "preview": {
            "action": "Delete my HouseOS account",
            **snapshot["counts"],
            "retention": RETENTION,
            "requires": "Finish or cancel active uploads first. A changed private-data set requires a new preview. The last administrator cannot delete their account.",
        },
    }


@router.post("/delete/confirm/{identity}")
def confirm_delete(identity: str, body: Reauthenticate, actor=Depends(require_actor), db=Depends(get_db)):
    from .assistant import ChatMessage, ChatReceipt
    from .cinema import CinemaPreference, CinemaState
    from .files import FileEntry, FileGrant, UploadReservation, lock_quota
    from .notifications import PushSubscription

    lock_quota(db)  # Serialize against creation of new uploads before deactivating the owner.
    admins = db.scalars(
        select(User)
        .where(
            User.role == "admin",
            User.active.is_(True),
            or_(User.expires_at.is_(None), User.expires_at > utcnow()),
        )
        .order_by(User.id)
        .with_for_update()
    ).all()
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    active_account(db, actor)
    if user.role == "admin" and len(admins) <= 1:
        raise HTTPException(409, "The last administrator cannot delete their account")
    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "account.delete"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Confirmation expired or consumed")
    if db.scalar(
        select(UploadReservation.id)
        .where(
            UploadReservation.owner_id == actor.id,
            UploadReservation.status.in_(["reserved", "uploading", "finalizing"]),
        )
        .with_for_update()
        .limit(1)
    ):
        raise HTTPException(409, "Finish or cancel active uploads before deleting the account")
    if deletion_snapshot(db, user, lock=True) != row.data:
        raise HTTPException(409, "Private data changed; review a new deletion preview")
    now = utcnow()
    personal_files = select(FileEntry.id).where(
        FileEntry.owner_id == actor.id, FileEntry.scope == "personal", FileEntry.deleted_at.is_(None)
    )
    db.execute(delete(FileGrant).where(FileGrant.file_id.in_(personal_files)))
    db.execute(
        update(FileEntry)
        .where(FileEntry.owner_id == actor.id, FileEntry.scope == "personal", FileEntry.deleted_at.is_(None))
        .values(trashed_at=now, version=FileEntry.version + 1)
    )
    db.execute(delete(ChatMessage).where(ChatMessage.owner_id == actor.id))
    db.execute(update(ChatReceipt).where(ChatReceipt.owner_id == actor.id).values(state="deleted", result={}))
    db.execute(
        update(Record)
        .where(Record.owner_id == actor.id, Record.kind.in_(PERSONAL_KINDS), Record.visibility == "private")
        .values(data={}, deleted_at=now, version=Record.version + 1)
    )
    db.execute(delete(CinemaState).where(CinemaState.owner_id == actor.id))
    db.execute(delete(CinemaPreference).where(CinemaPreference.owner_id == actor.id))
    db.execute(delete(SessionToken).where(SessionToken.user_id == actor.id))
    db.execute(
        update(PushSubscription)
        .where(PushSubscription.user_id == actor.id)
        .values(active=False, encrypted_payload="")
    )
    db.execute(
        update(Invite).where(Invite.creator_id == actor.id, Invite.redeemed_by.is_(None)).values(revoked=True)
    )
    db.execute(
        update(Job)
        .where(Job.actor_id == actor.id, Job.state == "pending")
        .values(state="cancelled", error_code="ACCOUNT_DELETED")
    )
    db.execute(
        update(Job)
        .where(Job.actor_id == actor.id, Job.state == "running")
        .values(state="unverified", error_code="ACCOUNT_DELETED")
    )
    db.execute(
        update(Operation)
        .where(Operation.actor_id == actor.id, Operation.id != identity)
        .values(data={}, result={"code": "ACCOUNT_DELETED"}, state="cancelled")
    )
    user.name, user.username = "Former resident", "deleted-" + user.id
    user.active, user.role, user.permissions, user.preferences, user.expires_at = False, "guest", [], {}, now
    user.password_hash = passwords.hash(secrets.token_urlsafe(32))
    row.state, row.result = (
        "completed",
        {"status": "completed", "retention": RETENTION, "files": "moved_to_trash"},
    )
    emit(
        db,
        "files.account_trashed",
        {"owner_id": user.id, "count": row.data["counts"]["personal_files"]},
        user.id,
    )
    emit(
        db,
        "audit.account_deleted",
        {
            "user_id": user.id,
            "personal_files": row.data["counts"]["personal_files"],
            "retention": "shared attribution and backups retained",
        },
        user.id,
    )
    db.commit()
    return row.result
