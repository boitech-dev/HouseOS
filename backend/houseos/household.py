"""Household records, recipient-scoped inbox and deterministic recurrence.

Domain functions are shared by HTTP and assistant tools. No provider calls here.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Actor, require_actor, require_permission
from .db import Base, get_db, new_id, utcnow
from .events import emit
from .models import Record, User

router = APIRouter(prefix="/household", tags=["household"])
KINDS = {"board", "tasks", "groceries", "calendar", "messages", "captures"}


class HouseholdMutex(Base):
    __tablename__ = "household_mutex"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


def lock_household(db: Session):
    if not db.scalar(select(HouseholdMutex).where(HouseholdMutex.id == 1).with_for_update()):
        try:
            with db.begin_nested():
                db.add(HouseholdMutex(id=1))
                db.flush()
        except IntegrityError:
            pass
    db.scalar(select(HouseholdMutex).where(HouseholdMutex.id == 1).with_for_update())


class HouseholdReceipt(Base):
    __tablename__ = "household_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[str] = mapped_column(String(36))


class MessageRecipient(Base):
    __tablename__ = "message_recipients"
    __table_args__ = (UniqueConstraint("message_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HouseholdNotification(Base):
    __tablename__ = "household_notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    record_id: Mapped[str] = mapped_column(String(36))
    category: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskOccurrence(Base):
    __tablename__ = "task_occurrences"
    __table_args__ = (UniqueConstraint("template_id", "due_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id"))
    due_date: Mapped[str] = mapped_column(String(10))


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoardData(Strict):
    title: str = Field(default="", max_length=160)
    body: str = Field(default="", max_length=10000)
    pinned: bool = False
    # A note's paper: one of the theme's note tones (--note-<tone>), "" for the plain one.
    color: Literal["", "sun", "leaf", "sky", "rose", "lilac", "sand"] = ""
    importance: Literal["normal", "important", "urgent"] = "normal"
    expires_at: datetime | None = None
    resolved: bool = False
    attachments: list[str] = Field(default_factory=list, max_length=10)


class TaskData(Strict):
    title: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=5000)
    assignee_id: str | None = None
    due_date: date | None = None
    due_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str = "UTC"  # normalize_data fills in the house setting when omitted
    fold: Literal[0, 1] | None = None
    status: Literal["open", "in_progress", "done", "cancelled"] = "open"
    recurrence: Literal["daily", "weekly", "monthly"] | None = None
    template_id: str | None = None
    private: bool = False  # only its author sees it


class GroceryData(Strict):
    label: str = Field(min_length=1, max_length=160)
    quantity: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=40)
    category: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=2000)
    purchased: bool = False


class CalendarData(Strict):
    title: str = Field(min_length=1, max_length=160)
    all_day: bool = False
    start: str
    end: str
    timezone: str = "UTC"  # normalize_data fills in the house setting when omitted
    start_fold: Literal[0, 1] | None = None
    end_fold: Literal[0, 1] | None = None
    location: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=5000)
    participants: list[str] = Field(default_factory=list, max_length=100)
    reminder_minutes: list[int] = Field(default_factory=list, max_length=5)
    recurrence: Literal["daily", "weekly", "monthly"] | None = None
    private: bool = False  # a personal event: only its author sees it


class MessageData(Strict):
    title: str = Field(default="", max_length=160)
    body: str = Field(min_length=1, max_length=10000)
    recipient_ids: list[str] = Field(min_length=1, max_length=100)
    attachments: list[str] = Field(default_factory=list, max_length=10)
    sent_with_assistant: bool = False


class CaptureData(Strict):
    text: str = Field(default="", max_length=10000)
    url: str | None = Field(default=None, max_length=2048)


SCHEMAS = {
    "board": BoardData,
    "tasks": TaskData,
    "groceries": GroceryData,
    "calendar": CalendarData,
    "messages": MessageData,
    "captures": CaptureData,
}


class CreateRecord(Strict):
    data: dict
    idempotency_key: str = Field(min_length=8, max_length=100)
    allow_duplicate: bool = False


class EditRecord(Strict):
    version: int = Field(ge=1)
    data: dict


class Version(Strict):
    version: int = Field(ge=1)


class TaskAction(Version):
    action: Literal["claim", "complete", "reopen", "snooze", "reassign", "decline"]
    assignee_id: str | None = None
    due_date: date | None = None


class VersionedId(Version):
    id: str


class GroceryBatch(Strict):
    items: list[VersionedId] = Field(min_length=1, max_length=100)
    purchased: bool
    idempotency_key: str = Field(min_length=8, max_length=100)


def local_instant(value: str, zone: str, fold: int | None = None) -> datetime:
    """Reject gaps and require explicit choice for repeated wall-clock times."""
    try:
        tz = ZoneInfo(zone)
        dt = datetime.fromisoformat(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, "Invalid date or IANA timezone")
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    candidates = []
    for f in (0, 1):
        aware = dt.replace(tzinfo=tz, fold=f)
        back = aware.astimezone(timezone.utc).astimezone(tz)
        if back.replace(tzinfo=None) == dt and back.fold == f:
            candidates.append((f, aware.astimezone(timezone.utc).replace(tzinfo=None)))
    if not candidates:
        raise HTTPException(422, "This local time does not exist because clocks change")
    if len(candidates) == 2 and fold is None:
        raise HTTPException(422, "This local time occurs twice; choose fold 0 or 1")
    for f, result in candidates:
        if fold is None or f == fold:
            return result
    raise HTTPException(422, "Invalid clock-change choice")


def next_due(original: date, recurrence: str, step: int = 1) -> date:
    if recurrence == "daily":
        return original + timedelta(days=step)
    if recurrence == "weekly":
        return original + timedelta(weeks=step)
    month_index = original.year * 12 + original.month - 1 + step
    year, month = divmod(month_index, 12)
    return date(year, month + 1, min(original.day, calendar.monthrange(year, month + 1)[1]))


def kind_permission(actor: Actor, kind: str, write=False):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown household collection")
    capability = (
        ("messages.send" if write else "messages.read")
        if kind == "messages"
        else ("household.write" if write else "household.read")
    )
    require_permission(actor, capability)


PRIVATE_KINDS = {"tasks", "calendar"}


def visible_query(actor: Actor, kind: str):
    query = select(Record).where(Record.kind == "household." + kind, Record.deleted_at.is_(None))
    if kind == "messages":
        recipients = select(MessageRecipient.message_id).where(MessageRecipient.user_id == actor.id)
        return query.where(or_(Record.owner_id == actor.id, Record.id.in_(recipients)))
    if kind == "captures":
        return query.where(Record.owner_id == actor.id)
    return query.where(or_(Record.visibility == "house", Record.owner_id == actor.id))


def get_record(db: Session, actor: Actor, kind: str, record_id: str) -> Record:
    kind_permission(actor, kind)
    row = db.scalar(visible_query(actor, kind).where(Record.id == record_id))
    if not row:
        raise HTTPException(404, "Record not found")
    return row


def record_json(row: Record):
    return {
        "id": row.id,
        "kind": row.kind.removeprefix("household."),
        "owner_id": row.owner_id,
        "visibility": row.visibility,
        "data": row.data,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def validate_people(db: Session, ids: list[str]):
    unique = set(ids)
    if unique and len(
        db.scalars(select(User.id).where(User.id.in_(unique), User.active.is_(True))).all()
    ) != len(unique):
        raise HTTPException(422, "One or more residents are unavailable")


def normalize_data(db: Session, actor: Actor, kind: str, data: dict) -> dict:
    if kind in {"tasks", "calendar"} and "timezone" not in data:
        from .house_settings import get_house_settings

        data = {**data, "timezone": get_house_settings(db)["timezone"]}
    try:
        result = SCHEMAS[kind].model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(
            422, [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        )
    for field in ("title", "label"):
        if field in result:
            result[field] = result[field].strip()
            if not result[field] and kind not in {"messages", "board"}:
                raise HTTPException(422, "A nonempty title or label is required")
    if kind == "board" and not (result["title"] or result["body"].strip()):
        raise HTTPException(422, "Write a message before sending")
    if kind == "messages" and not result["body"].strip():
        raise HTTPException(422, "A nonempty message is required")
    people = []
    if kind == "tasks":
        try:
            ZoneInfo(result["timezone"])
        except ZoneInfoNotFoundError:
            raise HTTPException(422, "Invalid IANA timezone")
        if result["template_id"]:
            raise HTTPException(422, "Template identity is server-owned")
        if result["assignee_id"]:
            people.append(result["assignee_id"])
            if result["private"] and result["assignee_id"] != actor.id:
                raise HTTPException(422, "A private task is yours alone; share it to assign someone")
        if result["due_time"]:
            if not result["due_date"]:
                raise HTTPException(422, "A timed task requires a due date")
            result["due_at"] = (
                local_instant(
                    result["due_date"] + "T" + result["due_time"], result["timezone"], result["fold"]
                ).isoformat()
                + "Z"
            )
        if result["recurrence"] and not result["due_date"]:
            raise HTTPException(422, "A recurring task requires a first due date")
    if kind == "calendar":
        people = result["participants"]
        if result["private"] and set(people) - {actor.id}:
            raise HTTPException(
                422, "A private event is yours alone; share it with the house to invite people"
            )
        if any(n < 0 or n > 43200 for n in result["reminder_minutes"]):
            raise HTTPException(422, "Reminder must be between 0 and 43200 minutes")
        try:
            ZoneInfo(result["timezone"])
            if result["all_day"]:
                start, end = date.fromisoformat(result["start"]), date.fromisoformat(result["end"])
            else:
                for field in ("start", "end"):
                    supplied = datetime.fromisoformat(result[field])
                    if supplied.tzinfo is not None:
                        local = supplied.astimezone(ZoneInfo(result["timezone"]))
                        result[field] = local.replace(tzinfo=None).isoformat()
                        result[field + "_fold"] = local.fold
                start = local_instant(result["start"], result["timezone"], result["start_fold"])
                end = local_instant(result["end"], result["timezone"], result["end_fold"])
                result.update(start_utc=start.isoformat() + "Z", end_utc=end.isoformat() + "Z")
            if end <= start:
                raise ValueError()
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, "Event end must be after start; all-day end is exclusive")
    if kind == "messages":
        people = sorted(set(result["recipient_ids"]))
        result["recipient_ids"] = people
    validate_people(db, people)
    if result.get("attachments"):
        from .files import assert_attachment_access

        assert_attachment_access(
            db, actor, result["attachments"], people, shared=(kind == "board"), grant=(kind == "messages")
        )
    if kind == "board" and result["expires_at"]:
        dt = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise HTTPException(422, "Expiry requires timezone")
    return result


def notify(db: Session, user_id: str, record_id: str, category: str, key: str):
    if not db.scalar(
        select(HouseholdNotification.id).where(
            HouseholdNotification.user_id == user_id, HouseholdNotification.dedupe_key == key
        )
    ):
        db.add(HouseholdNotification(user_id=user_id, record_id=record_id, category=category, dedupe_key=key))
        emit(db, "inbox.changed", {"record_id": record_id, "category": category}, user_id=user_id)


def changed(db: Session, actor: Actor, row: Record):
    payload = {"id": row.id, "kind": row.kind.removeprefix("household."), "version": row.version}
    if row.visibility == "house":
        emit(db, "household.changed", payload)
    else:
        recipients = set(row.data.get("recipient_ids", [])) | {actor.id}
        for person in recipients:
            emit(db, "household.changed", payload, user_id=person)


def create_record(db: Session, actor: Actor, kind: str, body: CreateRecord):
    kind_permission(actor, kind, True)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"kind": kind, "data": body.data, "allow_duplicate": body.allow_duplicate}, sort_keys=True
        ).encode()
    ).hexdigest()
    previous = db.scalar(
        select(HouseholdReceipt).where(
            HouseholdReceipt.actor_id == actor.id, HouseholdReceipt.request_key == body.idempotency_key
        )
    )
    if previous:
        if previous.fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency key already used for a different request")
        return record_json(get_record(db, actor, kind, previous.record_id))
    data = normalize_data(db, actor, kind, body.data)
    if kind == "groceries" and not body.allow_duplicate:
        lock_household(db)
        candidates = db.scalars(visible_query(actor, kind).with_for_update()).all()
        duplicates = [
            r.id
            for r in candidates
            if not r.data.get("purchased")
            and r.data["label"].strip().casefold() == data["label"].strip().casefold()
        ]
        if duplicates:
            raise HTTPException(
                409,
                {
                    "code": "DUPLICATE_REVIEW",
                    "candidate_ids": duplicates[:10],
                    "message": "Review existing items or explicitly add separately",
                },
            )
    row = Record(
        id=new_id(),
        kind="household." + kind,
        owner_id=actor.id,
        visibility="private" if kind in {"messages", "captures"} or data.get("private") else "house",
        data=data,
        version=1,
    )
    db.add(row)
    db.flush()
    db.add(
        HouseholdReceipt(
            actor_id=actor.id, request_key=body.idempotency_key, fingerprint=fingerprint, record_id=row.id
        )
    )
    if kind == "messages":
        for person in data["recipient_ids"]:
            db.add(MessageRecipient(message_id=row.id, user_id=person))
            notify(db, person, row.id, "message", row.id)
    if kind == "tasks" and data.get("assignee_id"):
        notify(db, data["assignee_id"], row.id, "assignment", row.id + ":1")
    changed(db, actor, row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(
            select(HouseholdReceipt).where(
                HouseholdReceipt.actor_id == actor.id, HouseholdReceipt.request_key == body.idempotency_key
            )
        )
        if previous and previous.fingerprint == fingerprint:
            return record_json(get_record(db, actor, kind, previous.record_id))
        raise HTTPException(409, "Concurrent creation conflict; refresh and retry")
    db.refresh(row)
    return record_json(row)


def update_record(db: Session, actor: Actor, kind: str, record_id: str, body: EditRecord):
    kind_permission(actor, kind, True)
    row = get_record(db, actor, kind, record_id)
    if kind == "messages":
        raise HTTPException(405, "Sent messages cannot be rewritten")
    if kind == "tasks" and row.data.get("recurrence") and body.data.get("status") == "done":
        raise HTTPException(422, "Complete a dated occurrence, not the recurrence template")
    if (
        kind in {"board", "captures"}
        and row.owner_id != actor.id
        and not (kind == "board" and actor.role == "admin")
    ):
        raise HTTPException(403, "Only the author may edit this record")
    if row.data.get("template_id") and "recurrence" in body.data:
        raise HTTPException(422, "An occurrence cannot become a recurrence template")
    fields = SCHEMAS[kind].model_fields
    data = {k: v for k, v in row.data.items() if k in fields and k != "template_id"}
    data.update(body.data)
    data = normalize_data(db, actor, kind, data)
    if bool(data.get("private")) != bool(row.data.get("private")) and row.owner_id != actor.id:
        raise HTTPException(403, "Only the author may make this private or shared")
    if row.data.get("template_id"):
        data["template_id"] = row.data["template_id"]
    if kind == "tasks":  # who finished it and when: the Home titles count this
        done = data["status"] == "done"
        first = done and row.data.get("status") != "done"
        data["completed_by"] = actor.id if first else row.data.get("completed_by") if done else None
        data["completed_at"] = (
            utcnow().isoformat() + "Z" if first else row.data.get("completed_at") if done else None
        )
    if kind == "groceries":
        data["purchased_by"] = actor.id if data["purchased"] else None
        data["purchased_at"] = utcnow().isoformat() + "Z" if data["purchased"] else None
        data["undo"] = {"purchased": row.data.get("purchased", False), "version": body.version + 1}
    count = db.execute(
        update(Record)
        .where(Record.id == row.id, Record.version == body.version, Record.deleted_at.is_(None))
        .values(
            data=data,
            version=body.version + 1,
            updated_at=utcnow(),
            **(
                {"visibility": "private" if data.get("private") else "house"} if kind in PRIVATE_KINDS else {}
            ),
        )
    ).rowcount
    if count != 1:
        db.rollback()
        raise HTTPException(409, "Record changed; reload before editing")
    db.refresh(row)
    changed(db, actor, row)
    if kind == "tasks" and data.get("assignee_id") and data.get("assignee_id") != actor.id:
        notify(db, data["assignee_id"], row.id, "assignment", row.id + ":" + str(row.version))
    db.commit()
    return record_json(row)


@router.get("/inbox")
def inbox(
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
    unread: bool = False,
    limit: int = Query(100, ge=1, le=200),
):
    require_permission(actor, "messages.read")
    query = select(HouseholdNotification).where(HouseholdNotification.user_id == actor.id)
    if unread:
        query = query.where(HouseholdNotification.read_at.is_(None))
    rows = db.scalars(query.order_by(HouseholdNotification.created_at.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": r.id,
                "record_id": r.record_id,
                "category": r.category,
                "created_at": r.created_at,
                "read_at": r.read_at,
            }
            for r in rows
        ]
    }


@router.post("/inbox/{notification_id}/read")
def read_notification(
    notification_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    require_permission(actor, "messages.read")
    row = db.scalar(
        select(HouseholdNotification).where(
            HouseholdNotification.id == notification_id, HouseholdNotification.user_id == actor.id
        )
    )
    if not row:
        raise HTTPException(404, "Notification not found")
    row.read_at = utcnow()
    emit(db, "inbox.changed", {"id": row.id}, user_id=actor.id)
    db.commit()
    return {"id": row.id, "read_at": row.read_at}


def conversation_key(owner_id, recipient_ids):
    """Everyone in the exchange, sender included: the same people are the same conversation."""
    people = sorted({owner_id, *recipient_ids})
    return hashlib.sha256("|".join(people).encode()).hexdigest()[:24], people


def my_messages(db, actor):
    # ponytail: the newest 5000 messages grouped in memory; a table of conversations if a
    # house ever writes far more than that.
    return db.scalars(
        visible_query(actor, "messages").order_by(Record.created_at.desc(), Record.id.desc()).limit(5000)
    ).all()


def unread_messages(db, actor):
    return set(
        db.scalars(
            select(HouseholdNotification.record_id).where(
                HouseholdNotification.user_id == actor.id,
                HouseholdNotification.category == "message",
                HouseholdNotification.read_at.is_(None),
            )
        )
    )


@router.get("/conversations")
def conversations(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Every exchange you are part of, the latest first, with its unread count."""
    require_permission(actor, "messages.read")
    unread = unread_messages(db, actor)
    found = {}
    for row in my_messages(db, actor):
        key, people = conversation_key(row.owner_id, row.data.get("recipient_ids") or [])
        entry = found.setdefault(
            key,
            {"key": key, "people": people, "last": record_json(row), "count": 0, "unread": 0},
        )
        entry["count"] += 1
        entry["unread"] += row.id in unread
    names = {
        u.id: {"id": u.id, "name": u.name, "avatar": (u.preferences or {}).get("avatar")}
        for u in db.scalars(select(User).where(User.id.in_({p for e in found.values() for p in e["people"]})))
    }
    for entry in found.values():
        entry["people"] = [names.get(p, {"id": p, "name": "Former resident"}) for p in entry["people"]]
    return {"items": list(found.values())}


@router.get("/conversations/{key}")
def conversation(
    key: str,
    before: str = Query("", max_length=36),
    limit: int = Query(30, ge=1, le=100),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """One exchange, newest first, `limit` at a time after the `before` message id.
    Opening it marks its messages read."""
    require_permission(actor, "messages.read")
    rows = [
        r
        for r in my_messages(db, actor)
        if conversation_key(r.owner_id, r.data.get("recipient_ids") or [])[0] == key
    ]
    if before:  # the id of the oldest message already shown
        ids = [r.id for r in rows]
        rows = rows[ids.index(before) + 1 :] if before in ids else []
    page = rows[:limit]
    if not before:
        seen = [r.id for r in rows]
        for note in db.scalars(
            select(HouseholdNotification).where(
                HouseholdNotification.user_id == actor.id,
                HouseholdNotification.category == "message",
                HouseholdNotification.record_id.in_(seen),
                HouseholdNotification.read_at.is_(None),
            )
        ):
            note.read_at = utcnow()
        emit(db, "inbox.changed", {"conversation": key}, user_id=actor.id)
        db.commit()
    return {
        "items": [record_json(r) for r in page],
        "next_before": page[-1].id if len(rows) > limit else None,
    }


@router.post("/groceries/batch")
def grocery_batch(body: GroceryBatch, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "household.write")
    if len({i.id for i in body.items}) != len(body.items):
        raise HTTPException(422, "Select each item once")
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    old = db.scalar(
        select(HouseholdReceipt).where(
            HouseholdReceipt.actor_id == actor.id, HouseholdReceipt.request_key == body.idempotency_key
        )
    )
    if old:
        if old.fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency key already used")
        return {"undo_id": old.record_id, "already_applied": True}
    before = []
    try:
        for item in body.items:
            row = get_record(db, actor, "groceries", item.id)
            before.append(
                {
                    "id": row.id,
                    "purchased": row.data.get("purchased", False),
                    "purchased_by": row.data.get("purchased_by"),
                    "purchased_at": row.data.get("purchased_at"),
                    "version": item.version + 1,
                }
            )
            data = dict(
                row.data,
                purchased=body.purchased,
                purchased_by=actor.id if body.purchased else None,
                purchased_at=utcnow().isoformat() + "Z" if body.purchased else None,
            )
            data.pop("undo", None)
            count = db.execute(
                update(Record)
                .where(Record.id == row.id, Record.version == item.version, Record.deleted_at.is_(None))
                .values(data=data, version=item.version + 1, updated_at=utcnow())
            ).rowcount
            if count != 1:
                raise HTTPException(409, "An item changed; review the whole batch again")
            db.refresh(row)
            changed(db, actor, row)
        undo = Record(
            id=new_id(),
            owner_id=actor.id,
            kind="household.grocery_undo",
            visibility="private",
            data={
                "items": before,
                "expires_at": (utcnow() + timedelta(minutes=5)).isoformat(),
                "used": False,
            },
            version=1,
        )
        db.add(undo)
        db.flush()
        db.add(
            HouseholdReceipt(
                actor_id=actor.id,
                request_key=body.idempotency_key,
                fingerprint=fingerprint,
                record_id=undo.id,
            )
        )
        db.commit()
        return {"undo_id": undo.id, "items": [{"id": i["id"], "version": i["version"]} for i in before]}
    except (HTTPException, IntegrityError):
        db.rollback()
        raise HTTPException(409, "The batch changed or was already submitted; refresh")


@router.post("/groceries/undo-batch/{undo_id}")
def undo_grocery_batch(undo_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "household.write")
    undo = db.scalar(
        select(Record)
        .where(Record.id == undo_id, Record.kind == "household.grocery_undo", Record.owner_id == actor.id)
        .with_for_update()
    )
    if not undo:
        raise HTTPException(404, "Undo not found")
    if undo.data["used"] or datetime.fromisoformat(undo.data["expires_at"]) < utcnow():
        raise HTTPException(409, "Undo already used or expired")
    try:
        for item in undo.data["items"]:
            row = get_record(db, actor, "groceries", item["id"])
            data = dict(
                row.data,
                purchased=item["purchased"],
                purchased_by=item["purchased_by"],
                purchased_at=item["purchased_at"],
            )
            count = db.execute(
                update(Record)
                .where(Record.id == row.id, Record.version == item["version"], Record.deleted_at.is_(None))
                .values(data=data, version=item["version"] + 1, updated_at=utcnow())
            ).rowcount
            if count != 1:
                raise HTTPException(409, "An item changed; batch undo would overwrite it")
            db.refresh(row)
            changed(db, actor, row)
        undo.data = dict(undo.data, used=True)
        db.commit()
        return {"undone": True}
    except HTTPException:
        db.rollback()
        raise


def calendar_occurrences(row: Record, start: date, end: date):
    data = row.data
    first = date.fromisoformat(data["start"][:10])
    recurrence = data.get("recurrence")
    if recurrence and first < start:
        if recurrence == "daily":
            initial = max(0, (start - first).days - 1)
        elif recurrence == "weekly":
            initial = max(0, (start - first).days // 7 - 1)
        else:
            initial = max(0, (start.year - first.year) * 12 + start.month - first.month - 1)
    else:
        initial = 0
    for step in range(initial, initial + 370):
        due = next_due(first, recurrence, step) if recurrence else first
        if due > end:
            break
        delta = due - first
        item = dict(data)
        item["occurrence_id"] = row.id + ":" + due.isoformat()
        item["id"] = row.id
        item["version"] = row.version
        item["owner_id"], item["visibility"] = row.owner_id, row.visibility
        if data["all_day"]:
            item["start"] = due.isoformat()
            item["end"] = (date.fromisoformat(data["end"]) + delta).isoformat()
            ends = date.fromisoformat(item["end"])
        else:
            local_start = datetime.fromisoformat(data["start"]) + delta
            local_end = datetime.fromisoformat(data["end"]) + delta
            item["start"], item["end"] = local_start.isoformat(), local_end.isoformat()
            try:
                item["start_utc"] = (
                    local_instant(item["start"], data["timezone"], data.get("start_fold")).isoformat() + "Z"
                )
                item["end_utc"] = (
                    local_instant(item["end"], data["timezone"], data.get("end_fold")).isoformat() + "Z"
                )
            except HTTPException:
                item.pop("start_utc", None)
                item.pop("end_utc", None)
                item["schedule_error"] = "DST_REVIEW_REQUIRED"
            ends = local_end.date()
        if ends >= start and due <= end:
            yield item
        if not recurrence:
            break


@router.get("/calendar/agenda")
def agenda(start: date, end: date, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "household.read")
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Choose a range of at most one year")
    rows = db.scalars(visible_query(actor, "calendar")).all()
    items = [item for row in rows for item in calendar_occurrences(row, start, end)]
    from .house_settings import get_house_settings

    return {
        "items": sorted(items, key=lambda i: i["start"]),
        "timezone": get_house_settings(db)["timezone"],
        "statement": "Only recorded house events are shown",
    }


def house_today(db):
    """Today in the house's timezone, not the server's."""
    from .house_settings import get_house_settings

    return datetime.now(ZoneInfo(get_house_settings(db)["timezone"])).date()


def calendar_digest(db: Session, actor: Actor):
    """This week first, then a few notable things further out, plus the tasks due soon.
    Plain code on the agenda: Nox and the UI only present it."""
    today = house_today(db)
    week_end, horizon = today + timedelta(days=6), today + timedelta(days=30)
    rows = db.scalars(visible_query(actor, "calendar")).all()

    def entry(item):
        return {
            "title": item["title"],
            "start": item["start"],
            "all_day": item["all_day"],
            "location": item.get("location", ""),
            "for_you": actor.id in item.get("participants", []) or bool(item.get("private")),
            "private": bool(item.get("private")),
        }

    week, later = [], []
    for row in rows:
        for item in calendar_occurrences(row, today, horizon):
            day = date.fromisoformat(item["start"][:10])
            if day <= week_end:
                week.append(entry(item))
            elif (
                (
                    item["all_day"]
                    and item["end"][:10] > item["start"][:10]
                    and item["end"] != (day + timedelta(days=1)).isoformat()
                )
                or item.get("reminder_minutes")
                or actor.id in item.get("participants", [])
            ):
                later.append(entry(item))
    tasks = [
        {
            "title": row.data["title"],
            "due_date": row.data["due_date"],
            "for_you": row.data.get("assignee_id") == actor.id,
        }
        for row in db.scalars(visible_query(actor, "tasks")).all()
        if row.data.get("status") in {"open", "in_progress"}
        and not row.data.get("recurrence")
        and row.data.get("due_date")
        and row.data["due_date"] <= week_end.isoformat()
    ]
    return {
        "today": today.isoformat(),
        "week": sorted(week, key=lambda i: i["start"]),
        "later": sorted(later, key=lambda i: i["start"])[:3],
        "tasks": sorted(tasks, key=lambda i: i["due_date"])[:10],
    }


@router.get("/calendar/digest")
def digest(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "household.read")
    return calendar_digest(db, actor)


@router.get("/calendar/export.ics")
def calendar_export(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    from fastapi.responses import Response

    require_permission(actor, "household.read")

    def escape(text):
        return (
            str(text)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r", "")
        )

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HouseOS//House Calendar//EN"]
    # Export explicit bounded occurrences; no ambiguous timezone reinterpretation by clients.
    today = house_today(db)
    start, end = today - timedelta(days=30), today + timedelta(days=366)
    for row in db.scalars(visible_query(actor, "calendar")).all():
        for item in calendar_occurrences(row, start, end):
            if item.get("schedule_error"):
                continue
            lines += [
                "BEGIN:VEVENT",
                "UID:" + item["occurrence_id"] + "@houseos",
                "DTSTAMP:" + row.updated_at.strftime("%Y%m%dT%H%M%SZ"),
                "SUMMARY:" + escape(item["title"]),
            ]
            if item["all_day"]:
                lines += [
                    "DTSTART;VALUE=DATE:" + item["start"].replace("-", ""),
                    "DTEND;VALUE=DATE:" + item["end"].replace("-", ""),
                ]
            else:
                for key, label in (("start_utc", "DTSTART"), ("end_utc", "DTEND")):
                    dt = datetime.fromisoformat(item[key].replace("Z", "+00:00"))
                    lines.append(label + ":" + dt.strftime("%Y%m%dT%H%M%SZ"))
            lines += [
                "LOCATION:" + escape(item.get("location", "")),
                "DESCRIPTION:" + escape(item.get("notes", "")),
                "END:VEVENT",
            ]
    lines += ["END:VCALENDAR"]
    return Response(
        "\r\n".join(lines) + "\r\n",
        media_type="text/calendar",
        headers={
            "Content-Disposition": 'attachment; filename="house-calendar.ics"',
            "Cache-Control": "private, no-store",
        },
    )


def view_of(kind, data):
    """Which list a task or grocery belongs to: what is left to do, what is done."""
    if kind == "groceries":
        return "bought" if data.get("purchased") else "open"
    if data.get("recurrence"):
        return "recurring"
    return "done" if data.get("status") in {"done", "cancelled"} else "open"


def list_view(db, query, kind, state, limit, offset):
    """Tasks to do (soonest due first), done (latest first) or recurring; groceries to buy or
    bought. ponytail: filtered in memory over the newest 2000, fine for a house's lists."""
    rows = [
        r
        for r in db.scalars(query.order_by(Record.created_at.desc()).limit(2000))
        if view_of(kind, r.data) == state
    ]
    if state == "open" and kind == "tasks":
        # A repeating task's copies are made a month ahead: To do shows the next week's.
        soon = (house_today(db) + timedelta(days=7)).isoformat()
        rows = [r for r in rows if not r.data.get("template_id") or (r.data.get("due_date") or "") <= soon]
    if state == "done":
        rows.sort(key=lambda r: r.data.get("completed_at") or "", reverse=True)
    elif state == "bought":
        rows.sort(key=lambda r: r.data.get("purchased_at") or "", reverse=True)
    elif kind == "tasks" and state == "open":
        rows.sort(key=lambda r: r.data.get("due_at") or (r.data.get("due_date") or "9999") + "T99")
    return {
        "items": [record_json(r) for r in rows[offset : offset + limit]],
        "offset": offset,
        "limit": limit,
        "has_more": len(rows) > offset + limit,
        "total": len(rows),
    }


@router.get("/{kind}")
def list_records(
    kind: str,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
    q: str = "",
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_expired: bool = False,
    state: Literal["", "open", "done", "recurring", "bought"] = "",
):
    kind_permission(actor, kind)
    query = visible_query(actor, kind)
    if q:
        from sqlalchemy import cast, Text

        query = query.where(cast(Record.data, Text).contains(q, autoescape=True))
    if state and kind in {"tasks", "groceries"}:
        return list_view(db, query, kind, state, limit, offset)
    order = [Record.created_at.desc(), Record.id.desc()]
    if kind == "board":  # pinned notes first
        order.insert(0, Record.data["pinned"].as_boolean().desc())
    rows = db.scalars(query.order_by(*order).offset(offset).limit(limit + 1)).all()
    now = utcnow().replace(tzinfo=timezone.utc)
    items = []
    authors = (
        {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({r.owner_id for r in rows}))).all()}
        if kind == "board"
        else {}
    )
    for row in rows[:limit]:
        if (
            kind == "board"
            and not include_expired
            and row.data.get("expires_at")
            and (row.data.get("importance") != "urgent" or row.data.get("resolved"))
        ):
            if datetime.fromisoformat(row.data["expires_at"].replace("Z", "+00:00")) < now:
                continue
        item = record_json(row)
        if kind == "board":
            item["author_name"] = authors.get(row.owner_id, "Former resident")
        items.append(item)
    return {"items": items, "offset": offset, "limit": limit, "has_more": len(rows) > limit}


@router.post("/{kind}", status_code=201)
def create(
    kind: str, body: CreateRecord, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    return create_record(db, actor, kind, body)


@router.get("/{kind}/{record_id}")
def detail(kind: str, record_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    return record_json(get_record(db, actor, kind, record_id))


@router.patch("/{kind}/{record_id}")
def edit(
    kind: str,
    record_id: str,
    body: EditRecord,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    return update_record(db, actor, kind, record_id, body)


@router.delete("/{kind}/{record_id}")
def remove(
    kind: str,
    record_id: str,
    version: int,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    kind_permission(actor, kind, True)
    row = get_record(db, actor, kind, record_id)
    if row.owner_id != actor.id and not (actor.role == "admin" and row.visibility == "house"):
        raise HTTPException(403, "Only the author can remove this record")
    if kind == "messages":
        raise HTTPException(405, "Sent messages cannot be deleted from recipients' inboxes")
    result = db.execute(
        update(Record)
        .where(Record.id == row.id, Record.version == version, Record.deleted_at.is_(None))
        .values(deleted_at=utcnow(), version=version + 1)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Record changed; refresh")
    db.refresh(row)
    changed(db, actor, row)
    db.commit()
    return {"id": row.id, "deleted": True}


@router.post("/tasks/{record_id}/action")
def task_action(
    record_id: str, body: TaskAction, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    changes = {}
    if body.action == "claim":
        changes["assignee_id"] = actor.id
    elif body.action == "complete":
        changes["status"] = "done"
    elif body.action == "reopen":  # back from Done to the list
        changes["status"] = "open"
    elif body.action == "snooze":
        if not body.due_date:
            raise HTTPException(422, "Snooze requires a date")
        changes["due_date"] = body.due_date.isoformat()
    elif body.action == "decline":
        row = get_record(db, actor, "tasks", record_id)
        if row.data.get("assignee_id") != actor.id:
            raise HTTPException(403, "Only the assignee can decline")
        changes["assignee_id"] = None
    else:
        changes["assignee_id"] = body.assignee_id
    return update_record(db, actor, "tasks", record_id, EditRecord(version=body.version, data=changes))


@router.post("/groceries/{record_id}/undo")
def grocery_undo(
    record_id: str, body: Version, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = get_record(db, actor, "groceries", record_id)
    undo = row.data.get("undo")
    if not undo or undo["version"] != body.version:
        raise HTTPException(409, "This change can no longer be undone")
    return update_record(
        db,
        actor,
        "groceries",
        record_id,
        EditRecord(version=body.version, data={"purchased": undo["purchased"]}),
    )


def generate_occurrences(db: Session, horizon: date):
    """Worker entrypoint. Unique template/date guards repeated maintenance runs."""
    lock_household(db)
    templates = db.scalars(
        select(Record).where(Record.kind == "household.tasks", Record.deleted_at.is_(None)).with_for_update()
    ).all()
    today = house_today(db)
    if horizon > today + timedelta(days=366):
        raise ValueError("Occurrence horizon is bounded to one year")
    # Copies already made; none older than ~93 days is made again (see floor). The unique
    # template/date constraint still guards a race.
    made = set(
        db.execute(
            select(TaskOccurrence.template_id, TaskOccurrence.due_date).where(
                TaskOccurrence.due_date >= (today - timedelta(days=100)).isoformat()
            )
        ).tuples()
    )
    created = 0
    for template in templates:
        data = template.data
        if not data.get("recurrence") or not data.get("due_date") or data.get("status") == "cancelled":
            continue
        first = date.fromisoformat(data["due_date"])
        floor = today - timedelta(days=31)
        initial = 0
        if first < floor:
            if data["recurrence"] == "daily":
                initial = max(0, (floor - first).days)
            elif data["recurrence"] == "weekly":
                initial = max(0, (floor - first).days // 7)
            else:
                initial = max(0, (floor.year - first.year) * 12 + floor.month - first.month - 1)
        for step in range(initial, initial + 400):
            due = next_due(first, data["recurrence"], step)
            if due > horizon:
                break
            if (template.id, due.isoformat()) in made:
                continue
            occurrence_data = dict(
                data, recurrence=None, template_id=template.id, due_date=due.isoformat(), status="open"
            )
            if data.get("due_time"):
                try:
                    occurrence_data["due_at"] = (
                        local_instant(
                            due.isoformat() + "T" + data["due_time"], data["timezone"], data.get("fold")
                        ).isoformat()
                        + "Z"
                    )
                except HTTPException:
                    # A future DST ambiguity is visible, never silently shifted.
                    occurrence_data.pop("due_at", None)
                    occurrence_data["schedule_error"] = "DST_REVIEW_REQUIRED"
            try:
                with db.begin_nested():
                    row = Record(
                        id=new_id(),
                        kind="household.tasks",
                        owner_id=template.owner_id,
                        visibility=template.visibility,
                        data=occurrence_data,
                        version=1,
                    )
                    db.add(row)
                    db.flush()
                    db.add(
                        TaskOccurrence(template_id=template.id, record_id=row.id, due_date=due.isoformat())
                    )
                    db.flush()
                    if data.get("assignee_id"):
                        notify(db, data["assignee_id"], row.id, "assignment", row.id)
                    emit(db, "household.changed", {"id": row.id, "kind": "tasks", "version": 1})
                created += 1
            except IntegrityError:
                continue
    db.commit()
    return created


def maintain_household(db: Session):
    """Bounded worker maintenance; inbox persists even if browser/push are offline."""
    today = house_today(db)
    occurrences = generate_occurrences(db, today + timedelta(days=30))
    now = utcnow()
    reminders = 0
    residents = db.scalars(
        select(User.id).where(User.active.is_(True), User.role.in_(["resident", "admin"]))
    ).all()
    for row in db.scalars(
        select(Record).where(Record.kind == "household.calendar", Record.deleted_at.is_(None))
    ).all():
        for item in calendar_occurrences(row, today - timedelta(days=7), today + timedelta(days=1)):
            if item.get("schedule_error"):
                continue
            if item["all_day"]:
                instant = local_instant(item["start"] + "T09:00:00", item["timezone"])
            else:
                instant = datetime.fromisoformat(item["start_utc"].removesuffix("Z"))
            for minutes in item.get("reminder_minutes", []):
                due = instant - timedelta(minutes=minutes)
                if not now - timedelta(days=7) <= due <= now:
                    continue
                for user_id in item.get("participants") or residents:
                    key = item["occurrence_id"] + ":reminder:" + str(minutes)
                    if not db.scalar(
                        select(HouseholdNotification.id).where(
                            HouseholdNotification.user_id == user_id, HouseholdNotification.dedupe_key == key
                        )
                    ):
                        notify(
                            db,
                            user_id,
                            row.id,
                            "reminder_catchup" if now - due > timedelta(minutes=5) else "reminder",
                            key,
                        )
                        reminders += 1
    db.commit()
    return {"task_occurrences": occurrences, "reminders": reminders}
