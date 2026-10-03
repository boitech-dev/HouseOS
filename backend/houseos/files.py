"""Actor-scoped metadata and durable uploads through a private tusd transport.

All user paths are logical names. Bytes use opaque IDs and no-follow directory FDs.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Actor, require_actor, require_admin, require_permission, account_usable
from .config import settings
from .db import Base, get_db, new_id, utcnow
from .events import emit
from .house_settings import get_house_settings
from .models import User, Record

router = APIRouter(prefix="/files", tags=["files"])
SCOPES = {"personal", "house", "drop", "media"}
TUS_HEADERS = {"Tus-Resumable": "1.0.0", "Cache-Control": "no-store"}
MAX_CHUNK = 16 * 1024 * 1024


class FileEntry(Base):
    __tablename__ = "file_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(240))
    is_folder: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    storage_removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (UniqueConstraint("owner_id", "request_key"),)


class FileGrant(Base):
    __tablename__ = "file_grants"
    __table_args__ = (UniqueConstraint("file_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("file_entries.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class FileConfirmation(Base):
    __tablename__ = "file_confirmations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("file_entries.id"))
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UploadReservation(Base):
    __tablename__ = "upload_reservations"
    __table_args__ = (UniqueConstraint("owner_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(240))
    parent_id: Mapped[str] = mapped_column(String(36), default="")
    scope: Mapped[str] = mapped_column(String(16))
    size: Mapped[int] = mapped_column(BigInteger)
    drop_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tus_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="reserved", index=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StorageQuota(Base):
    __tablename__ = "storage_quotas"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    limit_bytes: Mapped[int] = mapped_column(BigInteger, default=100 * 1024**3)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def safe_name(name: str) -> str:
    name = name.strip()
    if (
        not name
        or name in {".", ".."}
        or name.startswith(".")
        or any(c in name for c in "/\\\x00")
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
        or len(name.encode()) > 240
    ):
        raise ValueError("Use a visible filename without path separators or control characters")
    return name


class NewFolder(Strict):
    name: str = Field(min_length=1, max_length=240)
    scope: Literal["personal", "house", "drop", "media"] = "personal"
    parent_id: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)
    expires_hours: int | None = Field(default=None, ge=1, le=720)
    _name = field_validator("name")(safe_name)


class UploadCreate(NewFolder):
    size: int = Field(ge=0)


class FileEdit(Strict):
    version: int = Field(ge=1)
    name: str | None = None
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return safe_name(value) if value is not None else None


class PrepareFileAction(Strict):
    version: int = Field(ge=1)
    action: Literal["trash", "restore", "share", "unshare", "scope", "purge"]
    recipient_id: str | None = None
    scope: Literal["personal", "house", "drop", "media"] | None = None
    grant_expires_at: AwareDatetime | None = None


def active_grant():
    return or_(FileGrant.expires_at.is_(None), FileGrant.expires_at > utcnow())


def scoped_query(actor: Actor, *, include_trash=False):
    grants = select(FileGrant.file_id).where(FileGrant.user_id == actor.id, active_grant())
    query = (
        select(FileEntry)
        .where(FileEntry.deleted_at.is_(None))
        .where(
            or_(
                FileEntry.owner_id == actor.id,
                FileEntry.scope.in_(["house", "drop", "media"]),
                FileEntry.id.in_(grants),
            )
        )
    )
    if not include_trash:
        query = query.where(
            FileEntry.trashed_at.is_(None),
            or_(FileEntry.expires_at.is_(None), FileEntry.expires_at > utcnow()),
        )
    return query


def accessible_entry(
    db: Session, actor: Actor, file_id: str, *, include_trash=False, write=False, operation_id=None
):
    require_permission(actor, "files.write" if write else "files.read")
    row = db.scalar(scoped_query(actor, include_trash=include_trash).where(FileEntry.id == file_id))
    if not row:
        raise HTTPException(404, "File not found")
    if write and row.owner_id != actor.id and not (actor.role == "admin" and row.scope != "personal"):
        raise HTTPException(403, "Only the owner may change this file")
    if write:
        operations = db.scalars(
            select(Record).where(
                Record.kind == "files.bulk_confirmation",
                Record.id != (operation_id or ""),
                cast(Record.data, Text).contains(row.id, autoescape=True),
            )
        ).all()
        if any(
            op.data.get("state") == "executing" and any(t["id"] == row.id for t in op.data.get("targets", []))
            for op in operations
        ):
            raise HTTPException(409, "A confirmed file operation is still executing")
    # A trashed ancestor hides all descendants without rewriting their state.
    seen = {row.id}
    parent = row.parent_id
    for _ in range(100):
        if not parent:
            return row
        if parent in seen:
            raise HTTPException(409, "Invalid folder hierarchy")
        seen.add(parent)
        p = db.scalar(select(FileEntry).where(FileEntry.id == parent))
        if p and (
            p.deleted_at is not None
            or (
                not include_trash
                and (p.trashed_at is not None or (p.expires_at and p.expires_at <= utcnow()))
            )
        ):
            p = None
        if not p:
            raise HTTPException(404, "File not found")
        parent = p.parent_id
    raise HTTPException(409, "Folder nesting limit reached")


def entry_json(row: FileEntry):
    return {
        "id": row.id,
        "name": row.name,
        "is_folder": row.is_folder,
        "scope": row.scope,
        "parent_id": row.parent_id or None,
        "owner_id": row.owner_id,
        "size": row.size,
        "mime": row.mime,
        "checksum": row.checksum,
        "version": row.version,
        "trashed_at": row.trashed_at,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "deleted_at": row.deleted_at,
    }


def scope_write(actor: Actor, scope: str):
    require_permission(actor, "files.write")
    if scope not in SCOPES:
        raise HTTPException(422, "Invalid file scope")
    if scope != "personal":
        require_permission(actor, "files.shared.write")


def destination(db: Session, actor: Actor, scope: str, parent_id: str | None):
    scope_write(actor, scope)
    if parent_id:
        parent = accessible_entry(db, actor, parent_id, write=True)
        if not parent.is_folder or parent.scope != scope:
            raise HTTPException(422, "Choose a folder within the same scope")
    return parent_id or ""


def ensure_unique_name(
    db: Session, owner_id: str, scope: str, parent_id: str, name: str, except_id: str = ""
):
    query = select(FileEntry.id).where(
        FileEntry.scope == scope,
        FileEntry.parent_id == parent_id,
        FileEntry.name == name,
        FileEntry.trashed_at.is_(None),
        FileEntry.deleted_at.is_(None),
        FileEntry.id != except_id,
    )
    if scope == "personal":
        query = query.where(FileEntry.owner_id == owner_id)
    pending = select(UploadReservation.id).where(
        UploadReservation.scope == scope,
        UploadReservation.parent_id == parent_id,
        UploadReservation.name == name,
        UploadReservation.status.in_(["reserved", "uploading", "finalizing"]),
        UploadReservation.id != except_id,
    )
    if scope == "personal":
        pending = pending.where(UploadReservation.owner_id == owner_id)
    if db.scalar(query.with_for_update()) or db.scalar(pending.with_for_update()):
        raise HTTPException(409, "A file or active upload with that name already exists in this folder")


def lock_quota(db: Session):
    # One household's upload/name mutations serialize briefly; bytes never hold this lock.
    if not db.scalar(select(StorageQuota).where(StorageQuota.id == "household").with_for_update()):
        try:
            with db.begin_nested():
                db.add(StorageQuota(id="household"))
                db.flush()
        except IntegrityError:
            pass
    return db.scalar(select(StorageQuota).where(StorageQuota.id == "household").with_for_update())


# findmnt's answer per mounted device for 10 s: a fork per file request adds up. The device
# comparison still runs on every call.
FINDMNT: dict[int, tuple[float, dict]] = {}


def storage_check() -> dict:
    mount = str(settings.storage_mount)
    expected = settings.storage_uuid
    root = Path(settings.data_root)
    try:
        if not root.is_absolute() or root == Path(mount) or not root.is_relative_to(mount):
            raise ValueError()
        if settings.storage_container:
            # The volume must really be mounted (not the container's own layer) and writable.
            if not os.path.ismount(mount) or os.statvfs(mount).f_flag & os.ST_RDONLY:
                raise ValueError()
            device = os.stat(mount).st_dev
            if root.exists() and os.stat(root).st_dev != device:
                raise ValueError()
            return {"status": "healthy", "mount": mount, "device": device}
        device = os.stat("/dev/disk/by-uuid/" + expected).st_rdev
        if os.stat(mount).st_dev != device:
            raise ValueError()
        seen = FINDMNT.get(device)
        if not seen or time.monotonic() - seen[0] > 10:
            result = subprocess.run(
                ["findmnt", "--json", "--target", mount, "--output", "UUID,TARGET,OPTIONS"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            seen = FINDMNT[device] = (time.monotonic(), json.loads(result.stdout)["filesystems"][0])
        fs = seen[1]
        # systemd makes the storage mount read-only while granting the dedicated data root writes.
        if fs["uuid"] != expected or fs["target"] != mount or os.statvfs(root).f_flag & os.ST_RDONLY:
            raise ValueError()
        if root.exists() and os.stat(root).st_dev != device:
            raise ValueError()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        raise HTTPException(
            503,
            {
                "code": "STORAGE_UNAVAILABLE",
                "message": "The approved storage filesystem is unavailable; no write was attempted",
            },
        )
    return {"status": "healthy", "mount": mount, "device": device}


@contextmanager
def root_fd():
    evidence = storage_check()
    # Walk from / with O_NOFOLLOW at every component, preventing parent symlink swaps.
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in Path(settings.data_root).parts[1:]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        if "device" in evidence and os.fstat(fd).st_dev != evidence["device"]:
            raise HTTPException(503, "Storage changed while opening the approved root")
        yield fd
    except OSError:
        raise HTTPException(503, "Storage root is unavailable or unsafe")
    finally:
        os.close(fd)


@contextmanager
def subdir_fd(name: str):
    with root_fd() as root:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            yield fd
        finally:
            os.close(fd)


@contextmanager
def upload_lock(upload_id: str):
    # Kernel releases this lock on process death; it protects all app workers on this host.
    if not re.fullmatch(r"[a-f0-9-]{36}", upload_id):
        raise HTTPException(404, "Upload not found")
    directory = Path(settings.runtime_root) / "run" / "upload-locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / upload_id, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409, "Another request is updating this upload")
        yield
    finally:
        os.close(fd)


def usage(db: Session, actor: Actor, *, locked=False):
    used_query = select(func.coalesce(func.sum(FileEntry.size), 0)).where(
        FileEntry.owner_id == actor.id, FileEntry.scope != "media", FileEntry.storage_removed_at.is_(None)
    )
    reserved_query = select(func.coalesce(func.sum(UploadReservation.size), 0)).where(
        UploadReservation.owner_id == actor.id,
        UploadReservation.scope != "media",
        UploadReservation.status.in_(["reserved", "uploading", "finalizing"]),
    )
    used = db.scalar(used_query.with_for_update() if locked else used_query)
    reserved = db.scalar(reserved_query.with_for_update() if locked else reserved_query)
    return int(used), int(reserved)


def media_usage(db, *, locked=False):
    used_query = select(func.coalesce(func.sum(FileEntry.size), 0)).where(
        FileEntry.scope == "media", FileEntry.storage_removed_at.is_(None)
    )
    reserved_query = select(func.coalesce(func.sum(UploadReservation.size), 0)).where(
        UploadReservation.scope == "media",
        UploadReservation.status.in_(["reserved", "uploading", "finalizing"]),
    )
    local_query = select(Record).where(
        Record.kind.in_(["cinema.local_media", "music.download", "game.rom"]), Record.deleted_at.is_(None)
    )
    # Current reads after the shared quota lock; a prior RR snapshot must not admit excess reservations.
    used = int(db.scalar(used_query.with_for_update() if locked else used_query))
    reserved = int(db.scalar(reserved_query.with_for_update() if locked else reserved_query))
    for row in db.scalars(local_query.with_for_update() if locked else local_query):
        if row.data.get("source") == "folder":  # a games folder is read in place, not house storage
            continue
        if row.data.get("state") == "ready":
            used += int(row.data.get("size", 0))
        elif row.data.get("state") in {"reserved", "downloading"}:
            reserved += int(row.data.get("size", 0))
    return used, reserved


def upload_json(row: UploadReservation):
    return {
        "id": row.id,
        "status": row.status,
        "size": row.size,
        "expires_at": row.expires_at,
        "upload_url": "/api/v1/files/uploads/" + row.id + "/content",
    }


def owned_upload(db: Session, actor: Actor, upload_id: str, *, allow_expired=False):
    require_permission(actor, "files.write")
    row = db.scalar(
        select(UploadReservation).where(
            UploadReservation.id == upload_id, UploadReservation.owner_id == actor.id
        )
    )
    if not row:
        raise HTTPException(404, "Upload not found")
    scope_write(actor, row.scope)
    if row.expires_at < utcnow() and row.status != "stored" and not allow_expired:
        raise HTTPException(410, "Upload expired; cancel and start again")
    return row


def cancel_upload(db: Session, upload_id: str):
    db.execute(update(UploadReservation).where(UploadReservation.id == upload_id).values(status="cancelled"))
    db.commit()


def tus_url(row: UploadReservation):
    if not row.tus_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", row.tus_id):
        raise HTTPException(503, "Upload transport has not initialized this transfer")
    return settings.tusd_url.rstrip("/") + "/files/" + row.tus_id


def file_changed(db: Session, row: FileEntry):
    payload = {"id": row.id, "version": row.version}
    if row.scope != "personal":
        emit(db, "files.changed", payload)
    else:
        emit(db, "files.changed", payload, user_id=row.owner_id)
        for user_id in db.scalars(
            select(FileGrant.user_id).where(FileGrant.file_id == row.id, active_grant())
        ).all():
            emit(db, "files.changed", payload, user_id=user_id)


def assert_attachment_access(
    db: Session, actor: Actor, ids: list[str], recipients: list[str], *, shared=False, grant=False
):
    """Attachments must be readable by everyone who receives them. With `grant`, sending
    your own file to people is the share: they get 30 days of read access."""
    for file_id in ids:
        row = accessible_entry(db, actor, file_id)
        if row.is_folder:
            raise HTTPException(422, "Attachments must be files")
        if shared and row.scope == "personal":
            raise HTTPException(422, "House notes require house-visible attachments")
        if row.scope == "personal":
            grants = {
                g.user_id: g
                for g in db.scalars(select(FileGrant).where(FileGrant.file_id == row.id, active_grant()))
            }
            missing = set(recipients) - set(grants) - {row.owner_id}
            if missing and grant and row.owner_id == actor.id:
                for user_id in missing:
                    stale = db.scalar(
                        select(FileGrant).where(FileGrant.file_id == row.id, FileGrant.user_id == user_id)
                    )
                    if stale:
                        stale.expires_at = utcnow() + timedelta(days=30)
                    else:
                        db.add(
                            FileGrant(
                                file_id=row.id, user_id=user_id, expires_at=utcnow() + timedelta(days=30)
                            )
                        )
                    emit(db, "files.changed", {"id": row.id}, user_id=user_id)
            elif missing:
                raise HTTPException(422, "Share the attachment explicitly with every recipient first")


class FileTarget(Strict):
    id: str
    version: int = Field(ge=1)


class BulkFileAction(Strict):
    items: list[FileTarget] = Field(min_length=1, max_length=100)
    action: Literal["trash", "restore", "purge"]


class FilePolicyInput(Strict):
    permanent_delete_enabled: bool = False
    trash_retention_days: int = Field(default=30, ge=30, le=365)
    current_password: str | None = Field(default=None, max_length=256)


def file_policy(db: Session):
    row = db.scalar(select(Record).where(Record.kind == "files.policy", Record.deleted_at.is_(None)))
    return row.data if row else {"permanent_delete_enabled": False, "trash_retention_days": 30}


@router.get("/admin/policy")
def get_policy(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    return file_policy(db)


@router.put("/admin/policy")
def configure_policy(
    body: FilePolicyInput, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    lock_quota(db)
    row = db.scalar(
        select(Record).where(Record.kind == "files.policy", Record.deleted_at.is_(None)).with_for_update()
    )
    data = body.model_dump(exclude={"current_password"})
    if row:
        row.data = data
        row.version += 1
    else:
        db.add(
            Record(
                id=new_id(),
                kind="files.policy",
                owner_id=actor.id,
                visibility="private",
                data=data,
                version=1,
            )
        )
    emit(
        db,
        "files.policy",
        {
            "permanent_delete_enabled": data["permanent_delete_enabled"],
            "trash_retention_days": data["trash_retention_days"],
        },
        user_id=actor.id,
    )
    db.commit()
    return data


def collect_targets(db: Session, actor: Actor, body: BulkFileAction):
    selected = []
    visited = set()
    for target in body.items:
        root = accessible_entry(db, actor, target.id, include_trash=True, write=True)
        if root.version != target.version:
            raise HTTPException(409, "A selected file changed; refresh")
        if body.action == "purge" and root.trashed_at is None:
            raise HTTPException(422, "Move files to Trash before permanently deleting them")
        stack = [root]
        while stack:
            row = stack.pop()
            if row.id in visited:
                continue
            visited.add(row.id)
            if len(visited) > 500:
                raise HTTPException(413, "Select smaller groups (maximum 500 entries)")
            accessible_entry(db, actor, row.id, include_trash=True, write=True)
            selected.append(
                {
                    "id": row.id,
                    "version": row.version,
                    "name": row.name,
                    "size": row.size,
                    "is_folder": row.is_folder,
                }
            )
            if row.is_folder:
                stack.extend(
                    db.scalars(
                        select(FileEntry).where(FileEntry.parent_id == row.id, FileEntry.deleted_at.is_(None))
                    ).all()
                )
    return selected


@router.post("/bulk/prepare")
def prepare_bulk(body: BulkFileAction, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "files.write")
    targets = collect_targets(db, actor, body)
    preview = {
        "action": body.action,
        "targets": targets,
        "count": len(targets),
        "bytes": sum(t["size"] for t in targets),
        "irreversible": body.action == "purge",
    }
    row = Record(
        id=new_id(),
        kind="files.bulk_confirmation",
        owner_id=actor.id,
        visibility="private",
        data={
            **preview,
            "expires_at": (utcnow() + timedelta(minutes=5)).isoformat(),
            "state": "prepared",
            "completed_ids": [],
        },
        version=1,
    )
    db.add(row)
    db.commit()
    return {"confirmation_id": row.id, "preview": preview, "expires_at": row.data["expires_at"]}


def unlink_blob(entry: FileEntry):
    if entry.is_folder:
        return
    with subdir_fd("blobs") as fd:
        try:
            found = os.stat(entry.id, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return  # Recovery after unlink before DB commit.
        if not stat.S_ISREG(found.st_mode):
            raise HTTPException(503, "Refusing to remove an unexpected storage entry")
        os.unlink(entry.id, dir_fd=fd)
        os.fsync(fd)


def execute_bulk(db: Session, actor: Actor, confirmation_id: str):
    require_permission(actor, "files.write")
    row = db.scalar(
        select(Record)
        .where(
            Record.id == confirmation_id,
            Record.kind == "files.bulk_confirmation",
            Record.owner_id == actor.id,
        )
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Confirmation not found")
    data = row.data
    if data["state"] == "completed":
        raise HTTPException(409, "Confirmation already used")
    if data["state"] == "prepared" and datetime.fromisoformat(data["expires_at"]) < utcnow():
        raise HTTPException(409, "Confirmation expired")
    lock_quota(db)
    entries = []
    completed = set(data["completed_ids"])
    for target in data["targets"]:
        if target["id"] in completed:
            continue
        entry = accessible_entry(db, actor, target["id"], include_trash=True, write=True, operation_id=row.id)
        if entry.version != target["version"]:
            raise HTTPException(409, "A selected file changed; prepare a new preview")
        entries.append(entry)
    selected_ids = {target["id"] for target in data["targets"]}
    for entry in entries:
        if entry.is_folder:
            child_ids = set(
                db.scalars(
                    select(FileEntry.id).where(
                        FileEntry.parent_id == entry.id, FileEntry.deleted_at.is_(None)
                    )
                ).all()
            )
            if not child_ids <= selected_ids:
                raise HTTPException(409, "Folder contents changed; prepare a new exact preview")
    if data["action"] == "purge":
        row.data = dict(data, state="executing")
        db.commit()
        # Permanently remove exact approved bytes one at a time; interrupted operations
        # report partial progress and resume only this persisted list, never a new tree walk.
        with upload_lock(row.id):
            # Children precede parents so interrupted folder deletion remains recoverable.
            def depth(entry):
                result, parent = 0, entry.parent_id
                while parent and result < 100:
                    result += 1
                    ancestor = db.get(FileEntry, parent)
                    parent = ancestor.parent_id if ancestor else ""
                return result

            for entry in sorted(entries, key=depth, reverse=True):
                storage_check()
                unlink_blob(entry)
                entry.deleted_at = utcnow()
                entry.storage_removed_at = utcnow()
                entry.version += 1
                completed.add(entry.id)
                row.data = {**row.data, "completed_ids": sorted(completed)}
                file_changed(db, entry)
                db.commit()
    else:
        target_ids = {e.id for e in entries}
        for entry in entries:
            if data["action"] == "restore":
                if entry.parent_id and entry.parent_id not in target_ids:
                    destination(db, actor, entry.scope, entry.parent_id)
                ensure_unique_name(db, entry.owner_id, entry.scope, entry.parent_id, entry.name, entry.id)
            updates = {
                "trashed_at": utcnow() if data["action"] == "trash" else None,
                "version": entry.version + 1,
            }
            if data["action"] == "restore" and entry.expires_at and entry.expires_at <= utcnow():
                updates["expires_at"] = utcnow() + timedelta(days=7)
            count = db.execute(
                update(FileEntry)
                .where(FileEntry.id == entry.id, FileEntry.version == entry.version)
                .values(**updates)
            ).rowcount
            if count != 1:
                db.rollback()
                raise HTTPException(409, "A selected file changed; nothing was applied")
            db.refresh(entry)
            file_changed(db, entry)
            completed.add(entry.id)
    row.data = {**row.data, "state": "completed", "completed_ids": sorted(completed)}
    row.version += 1
    db.commit()
    return {"status": "completed", "action": data["action"], "affected_ids": sorted(completed)}


class ReadRootInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=1024)
    reader_ids: list[str] = Field(default_factory=list, max_length=100)
    current_password: str | None = Field(default=None, max_length=256)


@contextmanager
def readonly_fd(path: str):
    storage_check()
    requested = Path(path)
    allowed = settings.import_root
    if (
        not requested.is_absolute()
        or requested == allowed
        or not requested.is_relative_to(allowed)
        or ".." in requested.parts
        or requested.is_relative_to(settings.data_root)
    ):
        raise HTTPException(422, "Choose a specific existing media folder outside HouseOS storage")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in requested.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        # The import folder may be its own disk or NAS share; never cross into another mount inside it.
        if os.fstat(fd).st_dev != os.stat(allowed).st_dev:
            raise HTTPException(503, "Selected folder is not on the approved filesystem")
        yield fd
    except OSError:
        raise HTTPException(503, "Selected root is unavailable or unsafe")
    finally:
        os.close(fd)


def get_read_root(db: Session, actor: Actor, root_id: str):
    require_permission(actor, "files.read")
    row = db.scalar(
        select(Record).where(
            Record.id == root_id,
            Record.kind == "files.read_root",
            Record.visibility == "house",
            Record.deleted_at.is_(None),
        )
    )
    if not row or (
        row.data.get("reader_ids") and actor.id not in row.data["reader_ids"] and row.owner_id != actor.id
    ):
        raise HTTPException(404, "Root not found")
    return row


def root_token(root_id, parts):
    from .notifications import cipher

    return cipher().encrypt(json.dumps({"root_id": root_id, "parts": parts}).encode()).decode()


def root_parts(root_id, token):
    if not token:
        return []
    from .notifications import cipher
    from cryptography.fernet import InvalidToken

    try:
        data = json.loads(cipher().decrypt(token.encode(), ttl=3600))
        if data["root_id"] != root_id or not isinstance(data["parts"], list) or len(data["parts"]) > 40:
            raise ValueError()
        for part in data["parts"]:
            if not isinstance(part, str) or safe_name(part) != part:
                raise ValueError()
        return data["parts"]
    except (ValueError, TypeError, KeyError, InvalidToken):
        raise HTTPException(404, "File reference expired or unavailable")


@router.get("/roots")
def read_roots(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "files.read")
    rows = db.scalars(
        select(Record).where(
            Record.kind == "files.read_root", Record.deleted_at.is_(None), Record.visibility == "house"
        )
    ).all()
    return {
        "items": [
            {"id": r.id, "name": r.data["name"], "read_only": True, "version": r.version}
            for r in rows
            if not r.data.get("reader_ids") or actor.id in r.data["reader_ids"] or actor.id == r.owner_id
        ]
    }


@router.post("/roots/prepare")
def prepare_read_root(
    body: ReadRootInput, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    from .household import validate_people

    validate_people(db, body.reader_ids)
    with readonly_fd(body.path):
        pass  # Validate exactly this directory; no recursive scan or adoption.
    data = {
        "name": body.name,
        "path": body.path,
        "reader_ids": sorted(set(body.reader_ids)),
        "expires_at": (utcnow() + timedelta(minutes=5)).isoformat(),
        "state": "prepared",
    }
    row = Record(
        id=new_id(),
        kind="files.root_confirmation",
        owner_id=actor.id,
        visibility="private",
        data=data,
        version=1,
    )
    db.add(row)
    db.commit()
    return {
        "confirmation_id": row.id,
        "preview": {
            "name": body.name,
            "path": body.path,
            "reader_ids": body.reader_ids,
            "visibility": "selected residents" if body.reader_ids else "all residents with file access",
            "read_only": True,
        },
        "expires_at": data["expires_at"],
    }


@router.post("/roots/confirm/{confirmation_id}")
def confirm_read_root(
    confirmation_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    row = db.scalar(
        select(Record)
        .where(
            Record.id == confirmation_id,
            Record.owner_id == actor.id,
            Record.kind == "files.root_confirmation",
        )
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Confirmation not found")
    if row.data["state"] != "prepared" or datetime.fromisoformat(row.data["expires_at"]) < utcnow():
        raise HTTPException(409, "Confirmation expired or already used")
    with readonly_fd(row.data["path"]):
        pass
    root = Record(
        id=new_id(),
        owner_id=actor.id,
        kind="files.read_root",
        visibility="house",
        data={k: row.data[k] for k in ("name", "path", "reader_ids")},
        version=1,
    )
    db.add(root)
    row.data = dict(row.data, state="completed")
    db.commit()
    return {"id": root.id, "name": root.data["name"], "read_only": True, "version": root.version}


@router.delete("/roots/{root_id}")
def revoke_read_root(
    root_id: str, version: int, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    count = db.execute(
        update(Record)
        .where(
            Record.id == root_id,
            Record.kind == "files.read_root",
            Record.deleted_at.is_(None),
            Record.version == version,
        )
        .values(deleted_at=utcnow(), version=version + 1)
    ).rowcount
    if count != 1:
        raise HTTPException(409, "Root changed or unavailable")
    db.commit()
    return {"revoked": True, "files_unchanged": True}


@contextmanager
def root_child_fd(root, parts, *, is_directory):
    with readonly_fd(root.data["path"]) as parent:
        fd = os.dup(parent)
        try:
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW
                if index < len(parts) - 1 or is_directory:
                    flags |= os.O_DIRECTORY
                nxt = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
            yield fd
        except OSError:
            raise HTTPException(404, "Entry unavailable")
        finally:
            os.close(fd)


@router.get("/roots/{root_id}/entries")
def root_entries(
    root_id: str,
    directory_id: str | None = None,
    offset: int = Query(0, ge=0, le=100000),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    root = get_read_root(db, actor, root_id)
    parts = root_parts(root_id, directory_id)
    items = []
    scanned = 0
    with root_child_fd(root, parts, is_directory=True) as fd:
        with os.scandir(fd) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                try:
                    safe_name(entry.name)
                except ValueError:
                    continue
                meta = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(meta.st_mode) and not stat.S_ISDIR(meta.st_mode):
                    continue
                scanned += 1
                if scanned <= offset:
                    continue
                items.append(
                    {
                        "id": root_token(root.id, parts + [entry.name]),
                        "name": entry.name,
                        "size": meta.st_size if stat.S_ISREG(meta.st_mode) else 0,
                        "is_folder": stat.S_ISDIR(meta.st_mode),
                        "read_only": True,
                    }
                )
                if len(items) >= 200:
                    break
    return {
        "items": sorted(items, key=lambda i: (not i["is_folder"], i["name"].casefold())),
        "root_id": root.id,
        "parent_id": root_token(root.id, parts[:-1]) if parts else None,
        "limit": 200,
        "offset": offset,
        "next_offset": offset + len(items) if len(items) == 200 else None,
        "truncated": len(items) == 200,
    }


@router.get("/roots/{root_id}/download")
def root_download(
    root_id: str,
    file_id: str,
    request: Request,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    root = get_read_root(db, actor, root_id)
    parts = root_parts(root_id, file_id)
    if not parts:
        raise HTTPException(422, "Choose a file")
    with root_child_fd(root, parts, is_directory=False) as fd:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise HTTPException(422, "Choose a regular file")
        held = os.dup(fd)
    db.close()  # a download can last minutes: give the connection back first
    return stream_fd(held, meta.st_size, parts[-1], "application/octet-stream", request, inline=False)


@router.get("")
def list_files(
    scope: Literal["personal", "house", "drop", "media", "shared", "trash"] = "personal",
    parent_id: str | None = None,
    q: str = "",
    limit: int = Query(100, ge=1, le=200),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
    offset: int = 0,
    owner: str | None = Query(None, max_length=36),
):
    require_permission(actor, "files.read")
    query = scoped_query(actor, include_trash=(scope == "trash"))
    if scope == "trash":
        query = query.where(FileEntry.owner_id == actor.id, FileEntry.trashed_at.is_not(None))
    elif scope == "shared":
        query = query.where(FileEntry.scope == "personal", FileEntry.owner_id != actor.id)
    else:
        query = query.where(FileEntry.scope == scope)
        if not q or parent_id:
            query = query.where(FileEntry.parent_id == (parent_id or ""))
        if scope == "personal":
            query = query.where(FileEntry.owner_id == actor.id)
    if parent_id:
        accessible_entry(db, actor, parent_id)
    if owner and scope in {"house", "drop", "media"}:
        query = query.where(FileEntry.owner_id == owner)
    if q:
        query = query.where(FileEntry.name.contains(q, autoescape=True))
    if not 0 <= offset <= 100000:
        raise HTTPException(422, "Invalid file page offset")
    rows = db.scalars(
        query.order_by(FileEntry.is_folder.desc(), FileEntry.name, FileEntry.id)
        .offset(offset)
        .limit(limit + 1)
    ).all()
    visible = []
    for row in rows[:limit]:
        try:
            accessible_entry(db, actor, row.id, include_trash=(scope == "trash"))
            visible.append(entry_json(row))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return {
        "items": visible,
        "scope": scope,
        "parent_id": parent_id,
        "next_offset": offset + limit if len(rows) > limit else None,
    }


@router.get("/quota")
def quota(actor: Actor = Depends(require_actor), db: Session = Depends(get_db), scope: str = "personal"):
    require_permission(actor, "files.read")
    used, reserved = usage(db, actor)
    policy = get_house_settings(db)
    limit = policy["file_quota_bytes"]
    if scope == "media":
        used, reserved = media_usage(db)
        limit = settings.media_quota_bytes
    try:
        storage_check()
        status = "healthy"
    except HTTPException:
        status = "unavailable"
    return {
        "used_bytes": used,
        "reserved_bytes": reserved,
        "quota_bytes": limit,
        "max_upload_bytes": policy["max_upload_bytes"],
        "storage_status": status,
    }


@router.post("/folders", status_code=201)
def folder(body: NewFolder, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    parent = destination(db, actor, body.scope, body.parent_id)
    old = db.scalar(
        select(FileEntry).where(FileEntry.owner_id == actor.id, FileEntry.request_key == body.idempotency_key)
    )
    if old:
        if (old.name, old.scope, old.parent_id, old.is_folder) != (body.name, body.scope, parent, True):
            raise HTTPException(409, "Idempotency key already used")
        return entry_json(old)
    storage_check()
    lock_quota(db)
    ensure_unique_name(db, actor.id, body.scope, parent, body.name)
    row = FileEntry(
        id=new_id(),
        owner_id=actor.id,
        scope=body.scope,
        parent_id=parent,
        name=body.name,
        is_folder=True,
        size=0,
        request_key=body.idempotency_key,
        expires_at=(utcnow() + timedelta(hours=body.expires_hours or 168)) if body.scope == "drop" else None,
    )
    db.add(row)
    db.flush()
    file_changed(db, row)
    db.commit()
    db.refresh(row)
    return entry_json(row)


@router.post("/uploads", status_code=201)
def reserve_upload(body: UploadCreate, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    parent = destination(db, actor, body.scope, body.parent_id)
    storage_check()
    lock_quota(db)
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if not account_usable(user):
        raise HTTPException(401, "Account is inactive")
    row = db.scalar(
        select(UploadReservation)
        .where(UploadReservation.owner_id == actor.id, UploadReservation.request_key == body.idempotency_key)
        .with_for_update()
    )
    if row and (row.name, row.scope, row.parent_id, row.size) != (body.name, body.scope, parent, body.size):
        raise HTTPException(409, "Idempotency key already used")
    if not row:
        policy = get_house_settings(db)
        if body.size > policy["max_upload_bytes"]:
            raise HTTPException(413, "File exceeds the configured single-upload limit")
        used, reserved = (
            media_usage(db, locked=True) if body.scope == "media" else usage(db, actor, locked=True)
        )
        limit = settings.media_quota_bytes if body.scope == "media" else policy["file_quota_bytes"]
        if used + reserved + body.size > limit:
            raise HTTPException(413, "Storage quota would be exceeded")
        with root_fd() as fd:
            fs = os.fstatvfs(fd)
        available = fs.f_bavail * fs.f_frsize
        margin = max(2 * 1024**3, int(fs.f_blocks * fs.f_frsize * 0.05))
        outstanding = int(
            db.scalar(
                select(func.coalesce(func.sum(UploadReservation.size), 0))
                .where(UploadReservation.status.in_(["reserved", "uploading", "finalizing"]))
                .with_for_update()
            )
        )
        if available - outstanding - body.size < margin:
            raise HTTPException(507, "Storage free-space reserve would be exceeded")
        ensure_unique_name(db, actor.id, body.scope, parent, body.name)
        row = UploadReservation(
            id=new_id(),
            owner_id=actor.id,
            request_key=body.idempotency_key,
            name=body.name,
            scope=body.scope,
            parent_id=parent,
            size=body.size,
            status="reserved",
            drop_expires_at=(utcnow() + timedelta(hours=body.expires_hours or 168))
            if body.scope == "drop"
            else None,
            expires_at=utcnow() + timedelta(hours=24),
        )
        db.add(row)
    db.commit()
    with upload_lock(row.id):
        db.refresh(row)
        if not row.tus_id and row.status == "reserved":
            try:
                with httpx.Client(timeout=15, trust_env=False) as client:
                    response = client.post(
                        settings.tusd_url.rstrip("/") + "/files/",
                        headers={**TUS_HEADERS, "Upload-Length": str(row.size)},
                    )
                location = urlparse(response.headers.get("Location", "")).path.rstrip("/").split("/")[-1]
                if response.status_code != 201 or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", location):
                    raise ValueError()
            except (httpx.HTTPError, ValueError):
                raise HTTPException(
                    503,
                    {
                        "code": "UPLOAD_TRANSPORT_UNAVAILABLE",
                        "upload_id": row.id,
                        "message": "Reservation retained; retry this request to initialize transfer",
                    },
                )
            row.tus_id = location
            row.status = "uploading"
            db.commit()
        return upload_json(row)


@router.get("/uploads/{upload_id}")
def upload_status(upload_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    row = owned_upload(db, actor, upload_id, allow_expired=True)
    result = upload_json(row)
    if row.status == "stored":
        result["file"] = entry_json(accessible_entry(db, actor, row.id))
    return result


@router.api_route("/uploads/{upload_id}/content", methods=["HEAD", "PATCH", "DELETE", "OPTIONS"])
async def upload_content(
    upload_id: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    # Async only to stream the chunk: SQL runs in threads, and no connection is held while it moves.
    row = await run_in_threadpool(
        owned_upload, db, actor, upload_id, allow_expired=request.method == "DELETE"
    )
    await run_in_threadpool(db.close)
    if request.method == "OPTIONS":
        return Response(
            status_code=204, headers={**TUS_HEADERS, "Tus-Version": "1.0.0", "Tus-Extension": "termination"}
        )
    if request.headers.get("Tus-Resumable") != "1.0.0":
        return Response(status_code=412, headers={**TUS_HEADERS, "Tus-Version": "1.0.0"})
    if row.status == "stored":
        if request.method == "HEAD":
            return Response(
                status_code=200,
                headers={**TUS_HEADERS, "Upload-Offset": str(row.size), "Upload-Length": str(row.size)},
            )
        raise HTTPException(409, "Upload is already stored")
    if row.status == "cancelled":
        raise HTTPException(410, "Upload cancelled")
    await run_in_threadpool(storage_check)  # runs findmnt on a host install
    with upload_lock(row.id):
        if request.method == "DELETE" and not row.tus_id:
            await run_in_threadpool(cancel_upload, db, row.id)
            return Response(status_code=204, headers=TUS_HEADERS)
        headers = dict(TUS_HEADERS)
        content = None
        if request.method == "PATCH":
            if request.headers.get("Content-Type") != "application/offset+octet-stream":
                raise HTTPException(415, "Use application/offset+octet-stream")
            try:
                length = int(request.headers["Content-Length"])
                offset = int(request.headers["Upload-Offset"])
            except (KeyError, ValueError):
                raise HTTPException(411, "Content-Length and Upload-Offset required")
            if length < 0 or length > MAX_CHUNK or offset < 0 or offset + length > row.size:
                raise HTTPException(413, "Chunk exceeds reserved size or 16 MiB chunk limit")
            headers.update(
                {
                    "Content-Length": str(length),
                    "Upload-Offset": str(offset),
                    "Content-Type": "application/offset+octet-stream",
                }
            )

            async def bounded_body():
                count = 0
                async for chunk in request.stream():
                    count += len(chunk)
                    if count > length:
                        raise HTTPException(413, "Chunk size exceeded")
                    yield chunk
                if count != length:
                    raise HTTPException(400, "Incomplete chunk")

            content = bounded_body()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), trust_env=False) as client:
                response = await client.request(
                    request.method, tus_url(row), headers=headers, content=content
                )
        except httpx.HTTPError:
            raise HTTPException(503, "Transfer interrupted; query its offset before retrying")
        if request.method == "DELETE" and response.status_code in (204, 404, 410):
            await run_in_threadpool(cancel_upload, db, row.id)
            return Response(status_code=204, headers=TUS_HEADERS)
        safe_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower()
            in {"upload-offset", "upload-length", "tus-resumable", "tus-version", "upload-expires"}
        }
        safe_headers["Cache-Control"] = "no-store"
        if response.status_code >= 400:
            return Response(status_code=response.status_code, headers=safe_headers)
        return Response(status_code=response.status_code, headers=safe_headers)


def sniff_mime(header: bytes):
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio/wav"
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if header.startswith(b"ID3"):
        return "audio/mpeg"
    if header[4:8] == b"ftyp":
        return "video/mp4"
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    return "application/octet-stream"


def checksum_fd(fd):
    digest, header = hashlib.sha256(), b""
    while chunk := os.read(fd, 1024 * 1024):
        if not header:
            header = chunk[:32]
        digest.update(chunk)
    os.fsync(fd)
    return digest.hexdigest(), header


@router.post("/uploads/{upload_id}/finalize")
def finalize_upload(upload_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    row = owned_upload(db, actor, upload_id)
    if row.status == "stored":
        return {"status": "stored", "file": entry_json(accessible_entry(db, actor, row.id))}
    if row.status not in {"uploading", "finalizing"}:
        raise HTTPException(409, "Upload is not ready for finalization")
    storage_check()
    with upload_lock(row.id):
        with subdir_fd("blobs") as blobfd:
            try:
                stat_result = os.stat(row.id, dir_fd=blobfd, follow_symlinks=False)
                already_moved = True
                if not stat.S_ISREG(stat_result.st_mode):
                    raise HTTPException(409, "Unsafe destination")
            except FileNotFoundError:
                already_moved = False
            if not already_moved:
                try:
                    with httpx.Client(timeout=10, trust_env=False) as client:
                        response = client.head(tus_url(row), headers=TUS_HEADERS)
                    if (
                        response.status_code != 200
                        or int(response.headers.get("Upload-Offset", "-1")) != row.size
                    ):
                        raise HTTPException(409, "Upload bytes are incomplete")
                except (httpx.HTTPError, ValueError):
                    raise HTTPException(503, "Cannot verify upload completion")
            destination(db, actor, row.scope, row.parent_id)
            row.status = "finalizing"
            db.commit()
            with subdir_fd("staging") as stagefd:
                filefd = os.open(
                    row.id if already_moved else row.tus_id,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=blobfd if already_moved else stagefd,
                )
                try:
                    actual = os.fstat(filefd)
                    if not stat.S_ISREG(actual.st_mode) or actual.st_size != row.size:
                        raise HTTPException(409, "Stored byte count does not match reservation")
                    checksum, header = checksum_fd(filefd)
                finally:
                    os.close(filefd)
                if row.checksum and row.checksum != checksum:
                    raise HTTPException(409, "Recovery checksum mismatch")
                row.checksum = checksum
                db.commit()
                if not already_moved:
                    os.rename(row.tus_id, row.id, src_dir_fd=stagefd, dst_dir_fd=blobfd)
                    os.fsync(stagefd)
                    os.fsync(blobfd)
                lock_quota(db)
                destination(db, actor, row.scope, row.parent_id)
                ensure_unique_name(db, actor.id, row.scope, row.parent_id, row.name, row.id)
                entry = db.get(FileEntry, row.id)
                if not entry:
                    entry = FileEntry(
                        id=row.id,
                        owner_id=actor.id,
                        scope=row.scope,
                        parent_id=row.parent_id,
                        name=row.name,
                        size=row.size,
                        mime=sniff_mime(header),
                        checksum=row.checksum,
                        is_folder=False,
                        expires_at=row.drop_expires_at,
                    )
                    db.add(entry)
                    db.flush()
                    file_changed(db, entry)
                row.status = "stored"
                db.commit()
                db.refresh(entry)
                # Only metadata of this known upload; no bulk staging deletion here.
                for suffix in (".info", ".lock"):
                    try:
                        os.unlink(row.tus_id + suffix, dir_fd=stagefd)
                    except FileNotFoundError:
                        pass
                os.fsync(stagefd)
                return {"status": "stored", "file": entry_json(entry)}


@router.patch("/{file_id}")
def edit_file(
    file_id: str, body: FileEdit, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = accessible_entry(db, actor, file_id, write=True)
    lock_quota(db)
    row = accessible_entry(db, actor, file_id, write=True)
    parent = (
        destination(db, actor, row.scope, body.parent_id)
        if "parent_id" in body.model_fields_set
        else row.parent_id
    )
    if parent == row.id:
        raise HTTPException(422, "A folder cannot contain itself")
    if parent:
        p = db.get(FileEntry, parent)
        for _ in range(100):
            if not p:
                break
            if p.id == row.id:
                raise HTTPException(422, "Cannot move a folder into its descendant")
            p = db.get(FileEntry, p.parent_id) if p.parent_id else None
    name = body.name if body.name is not None else row.name
    ensure_unique_name(db, row.owner_id, row.scope, parent, name, row.id)
    count = db.execute(
        update(FileEntry)
        .where(FileEntry.id == row.id, FileEntry.version == body.version)
        .values(name=name, parent_id=parent, version=body.version + 1)
    ).rowcount
    if count != 1:
        db.rollback()
        raise HTTPException(409, "File changed; refresh")
    db.refresh(row)
    file_changed(db, row)
    db.commit()
    db.refresh(row)
    return entry_json(row)


@router.post("/{file_id}/actions/prepare")
def prepare_action(
    file_id: str,
    body: PrepareFileAction,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    if body.action == "purge":
        return prepare_bulk(
            BulkFileAction(items=[FileTarget(id=file_id, version=body.version)], action="purge"), actor, db
        )
    row = accessible_entry(db, actor, file_id, include_trash=True, write=True)
    if row.version != body.version:
        raise HTTPException(409, "File changed; refresh")
    if row.is_folder and body.action in {"trash", "restore"}:
        return prepare_bulk(
            BulkFileAction(items=[FileTarget(id=file_id, version=body.version)], action=body.action),
            actor,
            db,
        )
    if body.action in {"share", "unshare"}:
        if row.is_folder:
            raise HTTPException(
                422, "Share individual files explicitly; folder-wide grants are not inherited"
            )
        if not body.recipient_id or not db.scalar(
            select(User.id).where(User.id == body.recipient_id, User.active.is_(True))
        ):
            raise HTTPException(422, "Choose an active resident")
    if body.grant_expires_at:
        if body.action != "share" or body.grant_expires_at.astimezone(UTC).replace(tzinfo=None) <= utcnow():
            raise HTTPException(422, "Sharing expiry must be in the future and applies only to share actions")
    if body.action == "scope":
        if not body.scope:
            raise HTTPException(422, "Choose the destination scope")
        scope_write(actor, body.scope)
        if row.is_folder and db.scalar(select(FileEntry.id).where(FileEntry.parent_id == row.id)):
            raise HTTPException(
                422, "Move files explicitly; nonempty folders cannot change visibility in one operation"
            )
    preview = {
        "action": body.action,
        "file_id": row.id,
        "name": row.name,
        "version": row.version,
        "recipient_id": body.recipient_id,
        "scope": body.scope,
        "scope_change": body.action == "scope" and body.scope != row.scope,
        "grant_expires_at": body.grant_expires_at.isoformat() if body.grant_expires_at else None,
    }
    confirmation = FileConfirmation(
        id=new_id(),
        actor_id=actor.id,
        file_id=row.id,
        version=row.version,
        action=body.action,
        data=preview,
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db.add(confirmation)
    db.commit()
    return {"confirmation_id": confirmation.id, "preview": preview, "expires_at": confirmation.expires_at}


@router.post("/confirmations/{confirmation_id}")
def confirm_action(
    confirmation_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    require_permission(actor, "files.write")
    confirmation = db.scalar(
        select(FileConfirmation)
        .where(FileConfirmation.id == confirmation_id, FileConfirmation.actor_id == actor.id)
        .with_for_update()
    )
    if not confirmation:
        return execute_bulk(db, actor, confirmation_id)
    if confirmation.executed_at or confirmation.expires_at < utcnow():
        raise HTTPException(409, "Confirmation expired or already used")
    row = accessible_entry(db, actor, confirmation.file_id, include_trash=True, write=True)
    lock_quota(db)
    row = accessible_entry(db, actor, confirmation.file_id, include_trash=True, write=True)
    if row.version != confirmation.version:
        raise HTTPException(409, "File changed; prepare a new confirmation")
    action = confirmation.action
    previous_scope = row.scope
    if action == "trash":
        row.trashed_at = utcnow()
    elif action == "restore":
        destination(db, actor, row.scope, row.parent_id)
        ensure_unique_name(db, row.owner_id, row.scope, row.parent_id, row.name, row.id)
        row.trashed_at = None
        if row.expires_at and row.expires_at <= utcnow():
            row.expires_at = utcnow() + timedelta(days=7)
    elif action in {"share", "unshare"}:
        user_id = confirmation.data["recipient_id"]
        if not db.scalar(select(User.id).where(User.id == user_id, User.active.is_(True))):
            raise HTTPException(409, "Recipient is no longer active")
        grant = db.scalar(select(FileGrant).where(FileGrant.file_id == row.id, FileGrant.user_id == user_id))
        if action == "share":
            expiry = confirmation.data.get("grant_expires_at")
            expires_at = (
                datetime.fromisoformat(expiry).astimezone(UTC).replace(tzinfo=None) if expiry else None
            )
            if expires_at and expires_at <= utcnow():
                raise HTTPException(409, "Sharing expiry elapsed; prepare a new confirmation")
            if grant:
                grant.expires_at = expires_at
            else:
                db.add(FileGrant(file_id=row.id, user_id=user_id, expires_at=expires_at))
        elif action == "unshare" and grant:
            db.delete(grant)
        emit(db, "files.changed", {"id": row.id}, user_id=user_id)
    elif action == "scope":
        scope_write(actor, confirmation.data["scope"])
        ensure_unique_name(db, row.owner_id, confirmation.data["scope"], "", row.name, row.id)
        if row.scope != confirmation.data["scope"]:
            if confirmation.data["scope"] == "media":
                used, reserved = media_usage(db, locked=True)
                if used + reserved + row.size > settings.media_quota_bytes:
                    raise HTTPException(413, "Shared media quota would be exceeded")
            elif row.scope == "media":
                owner = db.get(User, row.owner_id)
                used, reserved = usage(db, Actor(owner.id, owner.name, owner.role, frozenset()), locked=True)
                if used + reserved + row.size > get_house_settings(db)["file_quota_bytes"]:
                    raise HTTPException(413, "Personal quota would be exceeded")
        row.scope = confirmation.data["scope"]
        row.parent_id = ""
    # Guard the file generation as well as consuming the confirmation.
    new_values = {
        "scope": row.scope,
        "parent_id": row.parent_id,
        "trashed_at": row.trashed_at,
        "expires_at": row.expires_at,
        "version": confirmation.version + 1,
    }
    db.expire(row)
    changed_count = db.execute(
        update(FileEntry)
        .where(FileEntry.id == confirmation.file_id, FileEntry.version == confirmation.version)
        .values(**new_values)
    ).rowcount
    if changed_count != 1:
        db.rollback()
        raise HTTPException(409, "File changed; prepare a new confirmation")
    db.refresh(row)
    confirmation.executed_at = utcnow()
    if previous_scope != "personal" and row.scope == "personal":
        emit(db, "files.changed", {"id": row.id, "removed_from_shared": True})
    file_changed(db, row)
    db.commit()
    db.refresh(row)
    return entry_json(row)


def read_excerpt(
    db: Session, actor: Actor, file_id: str, offset: int = 0, limit: int = 4000, version: int | None = None
):
    """Read bounded UTF-8 text only after the caller's explicit disclosure confirmation."""
    row = accessible_entry(db, actor, file_id)
    if version is not None and row.version != version:
        raise HTTPException(409, "File changed; review a new excerpt before disclosure")
    if not 0 <= offset <= 1_048_576 or not 1 <= limit <= 8000:
        raise HTTPException(422, "Excerpt bounds are invalid")
    if (
        row.is_folder
        or row.size > 1_048_576
        or Path(row.name).suffix.lower() not in {".txt", ".md", ".csv", ".log", ".json"}
    ):
        raise HTTPException(415, "Excerpts support UTF-8 txt, md, csv, log and json files up to 1 MiB")
    with subdir_fd("blobs") as directory:
        try:
            fd = os.open(row.id, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except OSError:
            raise HTTPException(503, "File bytes unavailable or unsafe") from None
    try:
        actual = os.fstat(fd)
        if not stat.S_ISREG(actual.st_mode) or actual.st_size != row.size:
            raise HTTPException(503, "File integrity check failed")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(1_048_577)
        if len(raw) != row.size or hashlib.sha256(raw).hexdigest() != row.checksum:
            raise HTTPException(503, "File integrity check failed")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(415, "This file is not supported UTF-8 text") from None
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise HTTPException(415, "Binary content is not supported")
        excerpt = text[offset : offset + limit]
        end = offset + len(excerpt)
        return {
            "file_id": row.id,
            "version": row.version,
            "offset": offset,
            "next_offset": end if end < len(text) else None,
            "text": excerpt,
            "truncated": end < len(text),
            "untrusted_content": True,
            "disclosure": "Only this explicitly approved excerpt may be sent to the selected assistant provider.",
        }
    finally:
        os.close(fd)


@router.get("/{file_id}/info")
def file_info(file_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    return entry_json(accessible_entry(db, actor, file_id))


@router.get("/{file_id}/grants")
def file_grants(file_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    row = accessible_entry(db, actor, file_id, write=True)
    grants = db.execute(
        select(FileGrant.user_id, User.name, FileGrant.expires_at)
        .join(User, User.id == FileGrant.user_id)
        .where(FileGrant.file_id == row.id)
    ).all()
    return {
        "items": [
            {
                "user_id": user_id,
                "name": name,
                "expires_at": expires_at,
                "expired": bool(expires_at and expires_at <= utcnow()),
            }
            for user_id, name, expires_at in grants
        ]
    }


def file_bytes(db: Session, actor: Actor, file_id: str, request: Request, *, preview=False):
    row = accessible_entry(db, actor, file_id)
    if row.is_folder:
        raise HTTPException(422, "Folders have no downloadable bytes")
    inline = preview and (
        row.mime.startswith("image/")
        or row.mime.startswith("audio/")
        or row.mime in {"video/mp4", "application/pdf"}
    )
    if preview and not inline:
        raise HTTPException(415, "This type is download-only for safety")
    with subdir_fd("blobs") as fd:
        try:
            filefd = os.open(row.id, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except FileNotFoundError:
            raise HTTPException(503, "File bytes unavailable")
    actual = os.fstat(filefd)
    if not stat.S_ISREG(actual.st_mode) or actual.st_size != row.size:
        os.close(filefd)
        raise HTTPException(503, "File integrity check failed")
    db.close()  # a download can last minutes: give the connection back first
    return stream_fd(filefd, row.size, row.name, row.mime, request, inline=inline)


def stream_fd(filefd, size, name, mime, request, *, inline):
    start, end = 0, size - 1
    status = 200
    range_header = request.headers.get("range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or (not match[1] and not match[2]):
            os.close(filefd)
            raise HTTPException(416, "Invalid byte range", headers={"Content-Range": f"bytes */{size}"})
        if match[1]:
            start = int(match[1])
            end = min(int(match[2]) if match[2] else end, end)
        else:
            start = max(0, size - int(match[2]))
        if start > end or start >= size:
            os.close(filefd)
            raise HTTPException(416, "Unsatisfiable range", headers={"Content-Range": f"bytes */{size}"})
        status = 206
    headers = {
        "Content-Disposition": ("inline" if inline else "attachment")
        + "; filename*=UTF-8''"
        + quote(name, safe=""),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "private, no-store",
        "Accept-Ranges": "bytes",
        "Content-Length": str(max(0, end - start + 1)),
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def stream():
        try:
            os.lseek(filefd, start, os.SEEK_SET)
            remaining = max(0, end - start + 1)
            while remaining:
                chunk = os.read(filefd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            os.close(filefd)

    return StreamingResponse(
        stream(),
        status_code=status,
        media_type=mime if inline else "application/octet-stream",
        headers=headers,
    )


AUDIO_TYPES = [
    (b"\x1aE\xdf\xa3", ".webm", "audio/webm"),
    (b"OggS", ".ogg", "audio/ogg"),
    (b"ID3", ".mp3", "audio/mpeg"),
    (b"fLaC", ".flac", "audio/flac"),
]


def audio_type(head: bytes):
    if head[4:8] == b"ftyp":
        return ".m4a", "audio/mp4"
    return next(
        ((ext, mime) for magic, ext, mime in AUDIO_TYPES if head.startswith(magic)), (".mp3", "audio/mpeg")
    )


def film_kind(title, parent):
    """film, series or anime, the way Watch splits them (anime: a MyAnimeList id)."""
    top = parent or title
    if top is None:
        return "film"
    if top.canonical_id.startswith("mal:"):
        return "anime"
    if top.canonical_id.startswith("web:"):  # Watch → Web
        return "web"
    return "series" if top.kind in {"series", "episode"} else "film"


def library_songs(db):
    """Every kept song with what the house knows about it, and who played it."""
    from .music import history_key, source_metadata

    rows = db.execute(
        select(Record, User.name)
        .join(User, User.id == Record.owner_id)
        .where(
            Record.kind == "music.download",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
    ).all()
    keys = [history_key(row.data.get("source_url", "")) for row, _ in rows]
    plays = {row.id: row.data for row in db.scalars(select(Record).where(Record.id.in_(keys)))}
    players = {}
    for key, owner in db.execute(
        select(Record.data["key"].as_string(), Record.owner_id).where(
            Record.kind == "music.play", Record.data["key"].as_string().in_(keys)
        )
    ):
        players.setdefault(key, set()).add(owner)
    art = source_metadata(db, [row.data.get("source_url", "") for row, _ in rows])
    items = []
    for (row, name), key in zip(rows, keys):
        played = plays.get(key, {})
        items.append(
            {
                "id": row.id,
                "title": row.data.get("title") or "Song",
                "artist": played.get("artist") or row.data.get("uploader"),
                "uploader": row.data.get("uploader"),
                "genre": played.get("genre") or "other",
                "plays": played.get("plays") or (1 if played else 0),
                "duration": row.data.get("duration"),
                "size": row.data.get("size", 0),
                "first_by": name,
                "owner_id": row.owner_id,
                "version": row.version,
                "played_by": sorted(players.get(key, set()) | {row.owner_id}),
                "created_at": row.created_at,
                "last_played": played.get("played_at"),
                "download": "/api/v1/files/library/music/" + row.id + "/download",
                "source_url": row.data.get("source_url"),
                "art": art.get(row.data.get("source_url"), {}).get("art"),
            }
        )
    return items


def library_films(db):
    """Every saved film or episode, named and sorted from the cinema catalogue."""
    from .cinema_models import CinemaTitle

    rows = db.execute(
        select(Record, User.name)
        .join(User, User.id == Record.owner_id)
        .where(
            Record.kind == "cinema.local_media",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
    ).all()
    titles = {
        t.id: t
        for t in db.scalars(
            select(CinemaTitle).where(CinemaTitle.id.in_({r.data.get("media_id") for r, _ in rows} - {None}))
        )
    }
    parents = {
        t.id: t
        for t in db.scalars(
            select(CinemaTitle).where(
                CinemaTitle.id.in_({t.data.get("parent_id") for t in titles.values()} - {None})
            )
        )
    }
    items = []
    for row, name in rows:
        media = row.data.get("media_id")
        title = titles.get(media)
        parent = parents.get(title.data.get("parent_id")) if title else None
        top = parent or title
        label = row.data.get("title") or (title.title if title else "") or "Film"
        if parent and title and title.data.get("season") is not None:
            label = f"{parent.title} · S{title.data['season']:02d}E{title.data.get('episode') or 0:02d}"
        items.append(
            {
                "id": row.id,
                "title": label,
                "type": film_kind(title, parent),
                "year": (top.data.get("year") if top else None),
                "genre": list((top.data.get("genres") if top else None) or []),
                "size": row.data.get("size", 0),
                "saved_by": name,
                "owner_id": row.owner_id,
                "version": row.version,
                "played_by": [row.owner_id],
                "created_at": row.created_at,
                "poster": "/api/v1/cinema/titles/" + media + "/poster" if media else None,
                "media_id": (top.id if top else media) if media else None,
                "watch": "/watch?title=" + (top.id if top else media) if media else None,
                "browser": "/api/v1/files/library/films/" + row.id + "/browser",
                "download": "/api/v1/files/library/films/" + row.id + "/download",
                "player_link": "/files/library/films/" + row.id + "/player-link",
            }
        )
    return items


LIBRARY_SORTS = {
    "recent": (lambda i: str(i["created_at"]), True),
    "title": (lambda i: i["title"].casefold(), False),
    "plays": (lambda i: i.get("plays") or 0, True),
    "played": (lambda i: i.get("last_played") or "", True),
    "artist": (lambda i: (i.get("artist") or "~").casefold(), False),
    "year": (lambda i: i.get("year") or 0, True),
    "size": (lambda i: i.get("size") or 0, True),
}


@router.get("/library")
def library(
    kind: Literal["music", "movies"] = "music",
    q: Annotated[str, Query(max_length=100)] = "",
    sort: Literal["recent", "title", "plays", "played", "artist", "year", "size"] = "recent",
    genre: Annotated[str, Query(max_length=80)] = "",
    by: Annotated[str, Query(max_length=36)] = "",
    type: Literal["", "film", "series", "anime"] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """What the house keeps on its own disk: songs saved after a first play, films saved
    locally. Residents only; guests see the queue, not the archive. Sorted and filtered here;
    `facets` counts genres and types (and `people` who played) over the whole library."""
    require_permission(actor, "files.read")
    if actor.role == "guest":
        raise HTTPException(403, "The house library is for residents")
    # ponytail: the whole library is read and filtered in memory; a few thousand items is
    # instant, index genre/person in SQL if a house ever keeps tens of thousands.
    everything = library_songs(db) if kind == "music" else library_films(db)
    genres = lambda i: i["genre"] if isinstance(i["genre"], list) else [i["genre"]]  # noqa: E731
    facets = {"genres": {}, "types": {}, "people": {}}
    for item in everything:
        for g in genres(item):
            facets["genres"][g] = facets["genres"].get(g, 0) + 1
        if item.get("type"):
            facets["types"][item["type"]] = facets["types"].get(item["type"], 0) + 1
        for person in item["played_by"]:
            facets["people"][person] = facets["people"].get(person, 0) + 1
    needle = q.casefold()
    items = [
        i
        for i in everything
        if (not needle or needle in (i["title"] + " " + (i.get("artist") or "")).casefold())
        and (not genre or genre in genres(i))
        and (not by or by in i["played_by"])
        and (not type or i.get("type") == type)
    ]
    key, descending = LIBRARY_SORTS[sort]
    items.sort(key=key, reverse=descending)
    page = [
        {**i, "can_delete": i.get("owner_id") == actor.id or actor.role == "admin"}
        for i in items[offset : offset + 60]
    ]
    return {
        "items": page,
        "total": len(items),
        "facets": {
            "genres": sorted(
                ({"genre": g, "count": n} for g, n in facets["genres"].items()), key=lambda g: -g["count"]
            ),
            "types": facets["types"],
            "people": facets["people"],
        },
        "next_offset": offset + 60 if len(items) > offset + 60 else None,
    }


DUPLICATE_FIELDS = (
    "id", "title", "uploader", "duration", "size", "plays", "last_played", "source_url", "download", "art",
    "version", "first_by",
)  # fmt: skip


class NotDuplicates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=2, max_length=50)


@router.get("/library/duplicates")
def library_duplicates(actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    """Admins: kept songs that may be one song twice. Each group lists the one to keep first
    (most played, then kept first); `delete` is the library's own DELETE for that song."""
    from .music_duplicates import dismissed, groups

    found = []
    for group in groups(library_songs(db), dismissed(db)):
        group.sort(key=lambda s: (-(s["plays"] or 0), str(s["created_at"])))
        songs = [
            {
                **{key: song.get(key) for key in DUPLICATE_FIELDS},
                "kept_at": song["created_at"],
                "suggested": n == 0,
                "delete": f"/files/library/music/{song['id']}?version={song['version']}",
            }
            for n, song in enumerate(group)
        ]
        found.append({"ids": sorted(song["id"] for song in group), "songs": songs})
    return {"groups": found, "count": len(found)}


@router.post("/library/duplicates/dismiss")
def not_duplicates(body: NotDuplicates, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    """Admins: these songs aren't one song; they aren't flagged together again."""
    from .music_duplicates import KIND, group_key

    ids = sorted(set(body.ids))
    if len(ids) < 2:
        raise HTTPException(422, "Name at least two songs")
    row = db.get(Record, group_key(ids))
    if not row:
        row = Record(id=group_key(ids), kind=KIND, owner_id=actor.id, visibility="house", data={})
        db.add(row)
    row.data = {"ids": ids, "dismissed": True}
    db.commit()
    return {"status": "completed"}


@router.get("/library/music/{identity}/download")
def library_song(
    identity: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    require_permission(actor, "files.read")
    if actor.role == "guest":
        raise HTTPException(403, "The house library is for residents")
    row = db.get(Record, identity)
    if not row or row.kind != "music.download" or row.deleted_at or row.data.get("state") != "ready":
        raise HTTPException(404, "Song not kept here")
    with subdir_fd("music-downloads") as fd:
        try:
            filefd = os.open(row.id + ".media", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except FileNotFoundError:
            raise HTTPException(503, "Song bytes unavailable")
    actual = os.fstat(filefd)
    if not stat.S_ISREG(actual.st_mode):
        os.close(filefd)
        raise HTTPException(503, "Song bytes unavailable")
    ext, mime = audio_type(os.pread(filefd, 12, 0))
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", row.data.get("title") or "song").strip()[:120] or "song"
    db.close()  # a download can last minutes: give the connection back first
    return stream_fd(filefd, actual.st_size, name + ext, mime, request, inline=False)


# What browsers play without any conversion (Chrome, Firefox, Safari on the common ground).
BROWSER_VIDEO = {"h264", "vp8", "vp9", "av1"}
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}
FILM_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska"}


def saved_film(db, actor, identity):
    require_permission(actor, "files.read")
    if actor.role == "guest":
        raise HTTPException(403, "The house library is for residents")
    row = db.get(Record, identity)
    if not row or row.kind != "cinema.local_media" or row.deleted_at or row.data.get("state") != "ready":
        raise HTTPException(404, "Film not saved here")
    return row


@router.get("/library/films/{identity}/browser")
def film_in_browser(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Whether this saved film plays in a browser as it is (checked once, then remembered).
    Nothing is converted: a film whose sound or picture a browser cannot play is sent to the TV."""
    from .playback import MediaError, probe_file

    row = saved_film(db, actor, identity)
    known = row.data.get("_browser")
    if known is None:
        path = Path(row.data.get("_path") or "")
        try:
            media = probe_file(path, timeout=15)
            video = str((media.get("video") or {}).get("codec") or "")
            audio = [str(track.get("codec") or "") for track in media.get("audio") or []]
            known = {
                "video": video,
                "audio": audio,
                "playable": path.suffix.lower() in FILM_TYPES
                and video in BROWSER_VIDEO
                and bool(audio)
                and audio[0] in BROWSER_AUDIO,
            }
        except (MediaError, OSError):
            known = {"playable": False, "video": "", "audio": []}
        row.data = {**row.data, "_browser": known}
        db.commit()
    return {
        "playable": known["playable"],
        "stream": f"/api/v1/files/library/films/{identity}/stream" if known["playable"] else None,
        "reason": None
        if known["playable"]
        else "This film's sound or picture format doesn't play in a browser. Stream it in VLC, download it, or send it to the TV.",
    }


def film_bytes(row):
    """An open, regular file for a saved film (never through a link), and its size."""
    path = Path(row.data["_path"])
    try:
        filefd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise HTTPException(503, "Film bytes unavailable") from None
    actual = os.fstat(filefd)
    if not stat.S_ISREG(actual.st_mode):
        os.close(filefd)
        raise HTTPException(503, "Film bytes unavailable")
    return filefd, actual.st_size, path


def film_type(path):
    return FILM_TYPES.get(path.suffix.lower(), "application/octet-stream")  # players sniff the rest


@router.get("/library/films/{identity}/download")
def film_download(
    identity: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    """The saved file itself, to keep on this device (any format: a phone's player may play it)."""
    filefd, size, path = film_bytes(saved_film(db, actor, identity))
    db.close()  # a download can last many minutes: give the connection back first
    return stream_fd(filefd, size, path.name, film_type(path), request, inline=False)


PLAYER_LINK_SECONDS = 12 * 3600


@router.post("/library/films/{identity}/player-link")
def film_player_link(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """A link another app can open (VLC and other players send no sign-in cookie): encrypted, for
    this person and this sign-in only, and it stops working after 12 hours or when they sign out."""
    from .notifications import cipher

    row = saved_film(db, actor, identity)
    token = (
        cipher()
        .encrypt(json.dumps({"film": row.id, "user": actor.id, "session": actor.session_hash}).encode())
        .decode()
    )
    name = quote(Path(row.data["_path"]).name, safe="")
    return {"url": f"/api/v1/files/film-link/{token}/{name}", "expires_in": PLAYER_LINK_SECONDS}


@router.get("/film-link/{token}/{name}")
def film_by_link(token: str, name: str, request: Request, db: Session = Depends(get_db)):
    from cryptography.fernet import InvalidToken

    from .auth import delegated_user
    from .notifications import cipher

    try:
        grant = json.loads(cipher().decrypt(token.encode(), ttl=PLAYER_LINK_SECONDS))
    except (InvalidToken, ValueError):
        raise HTTPException(404, "This link has expired: open the film again for a new one") from None
    user = delegated_user(db, grant.get("user"), grant.get("session"), "files.read")
    if not user or user.role == "guest":
        raise HTTPException(404, "This link has expired: open the film again for a new one")
    row = db.get(Record, grant.get("film"))
    if not row or row.kind != "cinema.local_media" or row.deleted_at or row.data.get("state") != "ready":
        raise HTTPException(404, "Film not saved here")
    filefd, size, path = film_bytes(row)
    db.close()
    return stream_fd(filefd, size, path.name, film_type(path), request, inline=True)


@router.get("/library/films/{identity}/stream")
def film_stream(
    identity: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = saved_film(db, actor, identity)
    if not (row.data.get("_browser") or {}).get("playable"):
        raise HTTPException(409, "Check this film first: it may not play in a browser")
    filefd, size, path = film_bytes(row)
    db.close()  # a download can last minutes: give the connection back first
    return stream_fd(filefd, size, path.name, FILM_TYPES[path.suffix.lower()], request, inline=True)


@router.get("/{file_id}/download")
def download(
    file_id: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    return file_bytes(db, actor, file_id, request)


THUMB_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.get("/{file_id}/thumb")
def thumbnail(file_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """A small JPEG of a picture for the file list, made once per version and kept a month."""
    from .cinema import IMAGE_KEEP, keep, poster_jpeg

    row = accessible_entry(db, actor, file_id)
    if row.is_folder or row.mime not in THUMB_TYPES or row.size > 40 * 1024**2:
        raise HTTPException(404, "No thumbnail")
    # ponytail: named by id and version, so a deleted file's thumbnail ages out after a month.
    path = settings.runtime_root / "cinema/images" / f"file-{row.id}-{row.version}.jpg"
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"}
    try:
        if time.time() - path.stat().st_mtime < IMAGE_KEEP:
            return Response(path.read_bytes(), media_type="image/jpeg", headers=headers)
    except OSError:
        pass
    with subdir_fd("blobs") as fd:
        try:
            filefd = os.open(row.id, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except FileNotFoundError:
            raise HTTPException(404, "No thumbnail") from None
    db.close()
    with os.fdopen(filefd, "rb") as stream:
        content = stream.read(row.size + 1)
    try:
        jpeg = poster_jpeg(content, (160, 160))
    except (OSError, ValueError):
        raise HTTPException(404, "No thumbnail") from None
    keep(path, jpeg)
    return Response(jpeg, media_type="image/jpeg", headers=headers)


@router.get("/{file_id}/preview")
def preview(
    file_id: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    return file_bytes(db, actor, file_id, request, preview=True)


async def expire_uploads(db: Session):
    """Delete only expired app-owned transfer bytes, then release their reservation."""
    storage_check()
    rows = db.scalars(
        select(UploadReservation)
        .where(
            UploadReservation.expires_at < utcnow(), UploadReservation.status.in_(["reserved", "uploading"])
        )
        .limit(50)
    ).all()
    cancelled = 0
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        for row in rows:
            try:
                with upload_lock(row.id):
                    if row.tus_id:
                        try:
                            response = await client.delete(tus_url(row), headers=TUS_HEADERS)
                        except httpx.HTTPError:
                            continue
                        if response.status_code not in (204, 404, 410):
                            continue
                    row.status = "cancelled"
                    db.commit()
                    cancelled += 1
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
    return cancelled


def maintain_files(db: Session):
    """Expiry is recoverable trash; irreversible cleanup requires explicit admin policy."""
    storage_check()
    lock_quota(db)
    now = utcnow()
    expired = db.scalars(
        select(FileEntry)
        .where(FileEntry.expires_at <= now, FileEntry.trashed_at.is_(None), FileEntry.deleted_at.is_(None))
        .with_for_update()
        .limit(100)
    ).all()
    for entry in expired:
        entry.trashed_at = now
        entry.version += 1
        file_changed(db, entry)
    db.commit()
    policy = file_policy(db)
    removed = 0
    if policy.get("permanent_delete_enabled"):
        cutoff = now - timedelta(days=max(30, int(policy.get("trash_retention_days", 30))))
        entries = db.scalars(
            select(FileEntry).where(FileEntry.trashed_at <= cutoff, FileEntry.deleted_at.is_(None)).limit(20)
        ).all()
        # Use the same persisted exact-scope deletion workflow as interactive confirmations.
        for entry in entries:
            owner = db.get(User, entry.owner_id)
            if not owner or not owner.active:
                continue
            from .auth import user_permissions

            actor = Actor(owner.id, owner.name, owner.role, user_permissions(owner))
            try:
                prepared = prepare_bulk(
                    BulkFileAction(items=[FileTarget(id=entry.id, version=entry.version)], action="purge"),
                    actor,
                    db,
                )
                result = execute_bulk(db, actor, prepared["confirmation_id"])
                removed += len(result["affected_ids"])
            except HTTPException:
                db.rollback()
    return {
        "expired_to_trash": len(expired),
        "permanently_removed": removed,
        "retention_enabled": bool(policy.get("permanent_delete_enabled")),
    }


def reconcile_staging(db: Session):
    """Bounded cleanup of app staging orphans; known finalizing uploads are retained."""
    cutoff = (utcnow() - timedelta(hours=48)).replace(tzinfo=UTC).timestamp()
    examined = removed = 0
    with subdir_fd("staging") as stagefd:
        with os.scandir(stagefd) as entries:
            for item in entries:
                examined += 1
                if examined > 2000:
                    break
                match = re.fullmatch(r"([A-Za-z0-9_-]{1,100})(?:\.(?:info|lock))?", item.name)
                if not match or item.is_symlink():
                    continue
                meta = item.stat(follow_symlinks=False)
                if not stat.S_ISREG(meta.st_mode) or meta.st_mtime >= cutoff:
                    continue
                known = db.scalar(select(UploadReservation.id).where(UploadReservation.tus_id == match[1]))
                if known:
                    continue
                os.unlink(item.name, dir_fd=stagefd)
                removed += 1
        if removed:
            os.fsync(stagefd)
    return {"examined": min(examined, 2000), "orphan_staging_files_removed": removed}
