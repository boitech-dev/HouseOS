"""Small typed tool bundles reusing household/file services; never shell or raw paths."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, AwareDatetime

from . import files, household
from .auth import Input
from .db import new_id


class Search(Input):
    query: str = Field(default="", max_length=200)


class HouseRead(Search):
    kind: Literal["board", "tasks", "groceries", "calendar", "messages", "captures"]
    record_id: str | None = None
    offset: int = Field(default=0, ge=0, le=10000)


class BoardCreate(Input):
    kind: Literal["board"]
    data: household.BoardData


class TaskCreate(Input):
    kind: Literal["tasks"]
    data: household.TaskData


class GroceryCreate(Input):
    kind: Literal["groceries"]
    data: household.GroceryData


class CalendarCreate(Input):
    kind: Literal["calendar"]
    data: household.CalendarData


class CaptureCreate(Input):
    kind: Literal["captures"]
    data: household.CaptureData


class HouseCreate(Input):
    item: BoardCreate | TaskCreate | GroceryCreate | CalendarCreate | CaptureCreate


class BoardPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, max_length=10000)
    pinned: bool | None = None
    importance: Literal["normal", "important", "urgent"] | None = None
    expires_at: str | None = None
    resolved: bool | None = None
    attachments: list[str] | None = Field(default=None, max_length=10)


class TaskPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=5000)
    assignee_id: str | None = None
    due_date: date | None = None
    due_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = None
    fold: Literal[0, 1] | None = None
    status: Literal["open", "in_progress", "done", "cancelled"] | None = None
    recurrence: Literal["daily", "weekly", "monthly"] | None = None


class GroceryPatch(Input):
    label: str | None = Field(default=None, min_length=1, max_length=160)
    quantity: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=2000)
    purchased: bool | None = None


class CalendarPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    start: str | None = None
    end: str | None = None
    all_day: bool | None = None
    timezone: str | None = None
    start_fold: Literal[0, 1] | None = None
    end_fold: Literal[0, 1] | None = None
    location: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=5000)
    participants: list[str] | None = Field(default=None, max_length=100)
    reminder_minutes: list[int] | None = Field(default=None, max_length=5)
    recurrence: Literal["daily", "weekly", "monthly"] | None = None


class EditIdentity(Input):
    id: str
    version: int = Field(ge=1)


class BoardEdit(EditIdentity):
    kind: Literal["board"]
    data: BoardPatch


class TaskEdit(EditIdentity):
    kind: Literal["tasks"]
    data: TaskPatch


class GroceryEdit(EditIdentity):
    kind: Literal["groceries"]
    data: GroceryPatch


class CalendarEdit(EditIdentity):
    kind: Literal["calendar"]
    data: CalendarPatch


class HouseEdit(Input):
    item: BoardEdit | TaskEdit | GroceryEdit | CalendarEdit
    clear_fields: list[Literal["expires_at", "assignee_id", "due_date", "due_time", "recurrence"]] = Field(
        default_factory=list, max_length=5
    )


class TaskAction(household.TaskAction):
    id: str


class Agenda(Input):
    start: date
    end: date


class GroceryPurchase(Input):
    items: list[household.VersionedId] = Field(min_length=1, max_length=100)
    purchased: bool


class Inbox(Input):
    unread: bool = False


class FileSearch(Search):
    scope: Literal["personal", "house", "drop", "media", "shared", "trash"] = "personal"
    parent_id: str | None = None


class FileExcerpt(Input):
    file_id: str
    version: int = Field(ge=1)
    offset: int = Field(default=0, ge=0, le=1000000)
    limit: int = Field(default=2000, ge=1, le=4000)


def prepare_excerpt(body, actor, db):
    from .assistant import prepare_file_excerpt

    return prepare_file_excerpt(body, actor, db)


class Folder(Input):
    name: str = Field(min_length=1, max_length=240)
    scope: Literal["personal", "house", "drop", "media"] = "personal"
    parent_id: str | None = None


class FileMove(EditIdentity):
    name: str | None = None
    parent_id: str | None = None
    to_root: bool = False


class FileAction(EditIdentity):
    action: Literal["trash", "restore", "share", "unshare", "scope", "purge"]
    recipient_id: str | None = None
    scope: Literal["personal", "house", "drop", "media"] | None = None
    grant_expires_at: AwareDatetime | None = None


class Identity(Input):
    id: str


def summary(record):
    data = record.get("data", {})
    useful = {
        k: v
        for k, v in data.items()
        if k
        in {
            "title",
            "label",
            "quantity",
            "unit",
            "status",
            "purchased",
            "assignee_id",
            "due_date",
            "due_time",
            "start",
            "end",
            "timezone",
            "pinned",
            "importance",
            "recipient_ids",
            "template_id",
            "recurrence",
        }
    }
    for field in ("body", "note", "notes", "text", "url"):
        if data.get(field):
            useful[field] = data[field][:350]
    return {"id": record["id"], "kind": record["kind"], "version": record["version"], "summary": useful}


def read_house(body, actor, db):
    if body.record_id:
        return summary(household.record_json(household.get_record(db, actor, body.kind, body.record_id)))
    result = household.list_records(body.kind, actor, db, body.query, 10, body.offset)
    return {
        "items": [summary(item) for item in result["items"]],
        "limit": 10,
        "next_offset": body.offset + 10 if len(result["items"]) == 10 else None,
    }


def create_house(body, actor, db):
    item = body.item
    data = item.data.model_dump(mode="json", exclude_unset=True)
    row = household.create_record(
        db, actor, item.kind, household.CreateRecord(data=data, idempotency_key=new_id())
    )
    return {"status": "completed", **summary(row)}


def edit_house(body, actor, db):
    item = body.item
    values = item.data.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    nullable = {
        "board": {"expires_at"},
        "tasks": {"assignee_id", "due_date", "due_time", "recurrence"},
        "calendar": {"recurrence"},
        "groceries": set(),
    }
    if not set(body.clear_fields) <= nullable[item.kind]:
        raise HTTPException(422, "This field cannot be cleared for that record kind")
    values.update({field: None for field in body.clear_fields})
    if item.kind == "calendar" and set(values) & {
        "start",
        "end",
        "all_day",
        "timezone",
        "start_fold",
        "end_fold",
        "participants",
        "recurrence",
    }:
        from .assistant import prepare_calendar_edit

        return prepare_calendar_edit(item.id, item.version, values, actor, db)
    row = household.update_record(
        db, actor, item.kind, item.id, household.EditRecord(version=item.version, data=values)
    )
    return {"status": "completed", **summary(row)}


def people_lookup(body, actor, db):
    from .core import people

    return {
        "items": [
            person for person in people(actor, db) if body.query.casefold() in person["name"].casefold()
        ][:5]
    }


def send_message(body, actor, db):
    # Assistant-composed messages always return root's exact recipient/body preview.
    from .assistant import prepare_message

    return prepare_message(body, actor, db)


def file_preview(body, actor, db):
    result = files.prepare_action(
        body.id,
        files.PrepareFileAction(
            version=body.version,
            action=body.action,
            recipient_id=body.recipient_id,
            scope=body.scope,
            grant_expires_at=body.grant_expires_at,
        ),
        actor,
        db,
    )
    return {
        "status": "needs_confirmation",
        "confirmation_path": "/files/confirmations/" + result["confirmation_id"],
        **result,
    }


def file_move(body, actor, db):
    values = body.model_dump(exclude={"id", "to_root"}, exclude_unset=True, exclude_none=True)
    if body.to_root:
        values["parent_id"] = None
    result = files.edit_file(body.id, files.FileEdit(**values), actor, db)
    return {
        "status": "completed",
        "id": result["id"],
        "version": result["version"],
        "name": result["name"],
        "parent_id": result["parent_id"],
    }


def build_tools(context):
    """10 household or 8 files tools; all responses are actor-scoped and compact."""
    if context == "household":
        return {
            "users_lookup": (
                Search,
                "Find up to five residents by name; ask when ambiguous.",
                people_lookup,
            ),
            "household_list": (
                HouseRead,
                "Read a record or up to ten summaries visible to this resident.",
                read_house,
            ),
            "household_create": (
                HouseCreate,
                "Create an explicitly requested house record: a grocery item, task, board note or calendar event; resolve dates and assignees first.",
                create_house,
            ),
            "household_update": (
                HouseEdit,
                "Edit only supplied fields using the exact current record version.",
                edit_house,
            ),
            "task_action": (
                TaskAction,
                "Claim, complete, reopen (a done task), snooze, decline or reassign one current task occurrence.",
                lambda b, a, d: {
                    "status": "completed",
                    **summary(
                        household.task_action(
                            b.id, household.TaskAction(**b.model_dump(exclude={"id"})), a, d
                        )
                    ),
                },
            ),
            "groceries_purchase": (
                GroceryPurchase,
                "Apply the exact explicitly requested purchased/not-purchased list with atomic version checks and undo.",
                lambda b, a, d: household.grocery_batch(
                    household.GroceryBatch(**b.model_dump(), idempotency_key=new_id()), a, d
                ),
            ),
            "groceries_undo": (
                Identity,
                "Undo this resident's exact recent batch; intervening changes are preserved.",
                lambda b, a, d: household.undo_grocery_batch(b.id, a, d),
            ),
            "calendar_agenda": (
                Agenda,
                "Read actual recorded house events, not inferred availability. Use bounded date ranges.",
                lambda b, a, d: {
                    "items": [
                        {
                            k: v
                            for k, v in item.items()
                            if k
                            in {"id", "occurrence_id", "title", "start", "end", "timezone", "schedule_error"}
                        }
                        for item in household.agenda(b.start, b.end, a, d)["items"][:10]
                    ],
                    "statement": "Only recorded house events are shown",
                },
            ),
            "messages_send": (
                household.MessageData,
                "Prepare an exact recipient/body confirmation; sending is a separate user approval.",
                send_message,
            ),
            "inbox_list": (
                Inbox,
                "Read up to ten private notification references; not delivery/read receipts for others.",
                lambda b, a, d: household.inbox(a, d, b.unread, 10),
            ),
        }
    if context == "files":
        from .assistant_tools import route

        return {
            "files_search": (
                FileSearch,
                "Search authorized filename/metadata only. No contents or machine paths.",
                lambda b, a, d: route(
                    files.list_files, scope=b.scope, parent_id=b.parent_id, q=b.query, limit=10, actor=a, db=d
                ),
            ),
            "files_folder": (
                Folder,
                "Create the explicitly requested folder in an allowed scope; personal is the default.",
                lambda b, a, d: files.folder(
                    files.NewFolder(**b.model_dump(), idempotency_key=new_id()), a, d
                ),
            ),
            "files_move": (
                FileMove,
                "Rename or move an owned file within its current scope with exact version. Scope changes need preview.",
                file_move,
            ),
            "files_prepare": (
                FileAction,
                "Prepare exact share/unshare/scope/trash/restore/permanent-delete preview. Never execute approval itself.",
                file_preview,
            ),
            "files_roots": (
                Input,
                "List configured read-only media roots visible to the resident, without host paths.",
                lambda b, a, d: files.read_roots(a, d),
            ),
            "files_read_excerpt": (
                FileExcerpt,
                "Prepare explicit cloud disclosure of a bounded UTF-8 file excerpt. User confirmation required; no content returned yet.",
                prepare_excerpt,
            ),
            "files_quota": (
                Input,
                "Read this resident's quota and actual storage availability.",
                lambda b, a, d: files.quota(a, d),
            ),
            "users_lookup": (
                Search,
                "Find up to five residents by name; ask when ambiguous.",
                people_lookup,
            ),
        }
    return {}
