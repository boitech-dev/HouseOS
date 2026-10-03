"""Admin storage inventory and explicit, version-bound reclamation; no content access."""

import os
import shutil
import stat
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, func
from .auth import Input, require_admin, require_actor, require_permission
from .config import settings
from .db import get_db, utcnow
from .events import emit
from .files import (
    FileEntry,
    UploadReservation,
    lock_quota,
    media_usage,
    storage_check,
    unlink_blob,
    file_changed,
)
from .house_settings import get_house_settings
from .models import Record, User

router = APIRouter(tags=["storage"])


@router.get("/admin/storage")
def inventory(
    actor=Depends(require_admin),
    db=Depends(get_db),
    offset: int = Query(0, ge=0),
    owner: str = "",
    kind: str = "all",
):
    storage_check()
    disk = shutil.disk_usage(settings.data_root)
    people = []
    policy = get_house_settings(db)
    for user in db.scalars(select(User).order_by(User.name)):
        used = int(
            db.scalar(
                select(func.coalesce(func.sum(FileEntry.size), 0)).where(
                    FileEntry.owner_id == user.id,
                    FileEntry.scope != "media",
                    FileEntry.storage_removed_at.is_(None),
                )
            )
        )
        reserved = int(
            db.scalar(
                select(func.coalesce(func.sum(UploadReservation.size), 0)).where(
                    UploadReservation.owner_id == user.id,
                    UploadReservation.scope != "media",
                    UploadReservation.status.in_(["reserved", "uploading", "finalizing"]),
                )
            )
        )
        people.append(
            {
                "id": user.id,
                "name": user.name,
                "used_bytes": used,
                "reserved_bytes": reserved,
                "quota_bytes": policy["file_quota_bytes"],
            }
        )
    used, reserved = media_usage(db)
    query = select(FileEntry).where(FileEntry.is_folder.is_(False), FileEntry.storage_removed_at.is_(None))
    if owner:
        query = query.where(FileEntry.owner_id == owner)
    if kind == "media":
        query = query.where(FileEntry.scope == "media")
    if kind == "personal":
        query = query.where(FileEntry.scope != "media")
    # Metadata only: admin storage permission does not provide private download links.
    entries = [
        {
            "id": r.id,
            "kind": "file",
            "name": r.name,
            "owner_id": r.owner_id,
            "size": r.size,
            "scope": r.scope,
            "version": r.version,
            "trashed": r.trashed_at is not None,
            "path": str(settings.data_root / "blobs" / r.id),
        }
        for r in db.scalars(query.order_by(FileEntry.size.desc(), FileEntry.id).offset(offset).limit(51))
    ]
    local = []
    if kind != "personal":
        q = select(Record).where(
            Record.kind == "cinema.local_media",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
        if owner:
            q = q.where(Record.owner_id == owner)
        for r in db.scalars(q.order_by(Record.created_at.desc()).offset(offset).limit(51)):
            if r.data.get("state") == "ready":
                local.append(
                    {
                        "id": r.id,
                        "kind": "cinema",
                        "name": Path(r.data.get("_path", "")).name,
                        "owner_id": r.owner_id,
                        "size": r.data.get("size", 0),
                        "scope": "media",
                        "version": r.version,
                        "trashed": False,
                        "path": r.data.get("_path"),
                        "state": "ready",
                    }
                )
    music = []
    if kind != "personal":
        q = select(Record).where(
            Record.kind == "music.download",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
        if owner:
            q = q.where(Record.owner_id == owner)
        for row in db.scalars(q.order_by(Record.created_at.desc()).offset(offset).limit(51)):
            music.append(
                {
                    "id": row.id,
                    "kind": "music",
                    "name": row.data.get("title", "Downloaded song"),
                    "owner_id": row.owner_id,
                    "size": row.data.get("size", 0),
                    "scope": "media",
                    "version": row.version,
                    "trashed": False,
                    "path": str(settings.data_root / "music-downloads" / (row.id + ".media")),
                    "state": "ready",
                }
            )
    return {
        "root": str(settings.data_root),
        "disk": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free},
        "people": people,
        "media": {"used_bytes": used, "reserved_bytes": reserved, "quota_bytes": settings.media_quota_bytes},
        "items": entries[:50],
        "movies": local[:50],
        "music": music[:50],
        "next_offset": offset + 50 if len(entries) > 50 or len(local) > 50 or len(music) > 50 else None,
        "note": "Disk usage includes other applications. Trash still occupies storage. Downloaded music is retained on the storage drive; the active playback copy stays on NVMe.",
    }


@router.get("/admin/storage/summary")
def summary(actor=Depends(require_admin), db=Depends(get_db)):
    """What the house keeps, counted by kind with its size: the Storage page opens on this, not
    on a list of every file."""
    storage_check()
    disk = shutil.disk_usage(settings.data_root)

    def kept(kind):
        count, size = db.execute(
            select(func.count(), func.coalesce(func.sum(Record.data["size"].as_integer()), 0)).where(
                Record.kind == kind, Record.deleted_at.is_(None), Record.data["state"].as_string() == "ready"
            )
        ).one()
        return int(count), int(size)

    groups = {}
    trashed = FileEntry.trashed_at.is_not(None)
    for scope, in_trash, count, size in db.execute(
        select(FileEntry.scope, trashed, func.count(), func.coalesce(func.sum(FileEntry.size), 0))
        .where(FileEntry.is_folder.is_(False), FileEntry.storage_removed_at.is_(None))
        .group_by(FileEntry.scope, trashed)
    ):
        key = (
            "trash"
            if in_trash
            else "shared"
            if scope in ("house", "drop")
            else "uploads"
            if scope == "media"
            else "personal"
        )
        count0, size0 = groups.get(key, (0, 0))
        groups[key] = (count0 + int(count), size0 + int(size))
    songs, films = kept("music.download"), kept("cinema.local_media")
    stored = [
        int(r.data.get("size") or 0)
        for r in db.scalars(select(Record).where(Record.kind == "game.rom", Record.deleted_at.is_(None)))
        if r.data.get("source") != "folder" and r.data.get("state") == "ready"
    ]
    kinds = [
        ("songs", "media", *songs),
        ("films", "media", *films),
        ("games", "games", len(stored), sum(stored)),
        ("personal", "personal", *groups.get("personal", (0, 0))),
        ("shared", "personal", *groups.get("shared", (0, 0))),
        ("uploads", "media", *groups.get("uploads", (0, 0))),
        ("trash", "all", *groups.get("trash", (0, 0))),
    ]
    return {
        "disk": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free},
        "kinds": [
            {"key": key, "browse": browse, "count": count, "bytes": size}
            for key, browse, count, size in kinds
        ],
    }


class Reclaim(Input):
    version: int = Field(ge=1)
    kind: str = Field(pattern="^(file|cinema|music)$")
    action: str = Field(pattern="^(trash|restore|delete)$")
    confirmed: bool = False


@router.post("/admin/storage/{identity}/reclaim")
def reclaim(identity: str, body: Reclaim, actor=Depends(require_admin), db=Depends(get_db)):
    if not body.confirmed:
        raise HTTPException(422, "Review the exact item and confirm the storage action")
    storage_check()
    lock_quota(db)
    if body.kind == "file":
        row = db.scalar(
            select(FileEntry)
            .where(
                FileEntry.id == identity,
                FileEntry.is_folder.is_(False),
                FileEntry.storage_removed_at.is_(None),
            )
            .with_for_update()
        )
        if not row:
            raise HTTPException(404, "File not found")
        if row.version != body.version:
            raise HTTPException(409, "File changed; refresh storage")
        if body.action == "delete":
            if row.trashed_at is None:
                raise HTTPException(409, "Move this file to Trash first")
            unlink_blob(row)
            row.deleted_at = row.storage_removed_at = utcnow()
        else:
            row.trashed_at = utcnow() if body.action == "trash" else None
        row.version += 1
        file_changed(db, row)
    elif body.kind == "music":
        forget_song(db, identity, body.version, body.action)
    else:
        forget_movie(db, identity, body.version, body.action)
    emit(
        db,
        "audit.storage_reclaim",
        {"id": identity, "kind": body.kind, "action": body.action},
        user_id=actor.id,
    )
    db.commit()
    return {"status": "completed"}


def forget_song(db, identity, version, action="delete"):
    """Delete one kept song and its file (version-bound, never a link or another path)."""
    row = db.scalar(
        select(Record)
        .where(Record.id == identity, Record.kind == "music.download", Record.deleted_at.is_(None))
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Downloaded song not found")
    if row.version != version or row.data.get("state") != "ready":
        raise HTTPException(409, "Song changed or is still downloading")
    if action != "delete":
        raise HTTPException(422, "Downloaded songs support explicit deletion only")
    expected = Path("music-downloads") / (row.id + ".media")
    if row.data.get("path") != str(expected):
        raise HTTPException(409, "Unexpected library location; no file was removed")
    root = settings.data_root / "music-downloads"
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            info = os.stat(expected.name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise HTTPException(409, "Unexpected storage entry")
            os.unlink(expected.name, dir_fd=fd)
            os.fsync(fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(fd)
    row.deleted_at = utcnow()
    row.version += 1
    return row


def forget_movie(db, identity, version, action="delete"):
    """Delete one saved film and its file; refused while it plays or prepares."""
    from .cinema import CinemaWorkflow

    row = db.scalar(
        select(Record)
        .where(Record.id == identity, Record.kind == "cinema.local_media", Record.deleted_at.is_(None))
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Movie not found")
    if row.version != version or row.data.get("state") != "ready":
        raise HTTPException(409, "Movie changed or is still downloading")
    if action != "delete":
        raise HTTPException(422, "Local movies support explicit deletion only")
    if db.scalar(
        select(CinemaWorkflow.id)
        .where(
            CinemaWorkflow.media_id.in_(
                [value for value in (row.data.get("media_id"), row.data.get("library_media_id")) if value]
            ),
            CinemaWorkflow.state.in_(
                [
                    "preparing",
                    "playing_observed",
                    "paused",
                    "buffering",
                    "unverified",
                    "command_sent",
                    "recovery_required",
                ]
            ),
        )
        .limit(1)
    ):
        raise HTTPException(409, "Stop active playback of this movie before deleting it")
    path = Path(row.data.get("_path", ""))
    root = path.parent
    if root not in {
        settings.data_root / "media" / "movies",
        settings.data_root / "media" / "shows",
    } or path.name in {"", "."}:
        raise HTTPException(409, "Unexpected library location; no file was removed")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            found = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(found.st_mode):
                raise HTTPException(409, "Unexpected storage entry")
            os.unlink(path.name, dir_fd=fd)
            os.fsync(fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(fd)
    row.deleted_at = utcnow()
    row.version += 1
    return row


@router.delete("/files/library/{kind}/{identity}")
def delete_kept(
    kind: Literal["music", "movies"],
    identity: str,
    version: int = Query(ge=1),
    actor=Depends(require_actor),
    db=Depends(get_db),
):
    """Files → House music / Films: whoever kept it (or an admin) removes it from the disk."""
    if actor.role == "guest":
        raise HTTPException(403, "The house library is for residents")
    row = db.get(Record, identity)
    if not row or row.kind != ("music.download" if kind == "music" else "cinema.local_media"):
        raise HTTPException(404, "Not in the house library")
    if row.owner_id != actor.id and actor.role != "admin":
        raise HTTPException(403, "Only the person who kept it, or an admin, can delete it")
    storage_check()
    lock_quota(db)
    (forget_song if kind == "music" else forget_movie)(db, identity, version)
    emit(db, "audit.storage_reclaim", {"id": identity, "kind": kind, "action": "delete"}, user_id=actor.id)
    emit(db, "files.changed", {"id": identity})
    db.commit()
    return {"status": "completed"}


@router.delete("/music/queue/{item_id}/kept")
def delete_queued_song(item_id: str, actor=Depends(require_actor), db=Depends(get_db)):
    """Listen: delete a queued song's kept file from the house. The song playing now plays to its
    end (the player reads its own copy); a waiting one also leaves the queue when it is yours."""
    from .music import QueueItem, queue
    from .music_downloads import identity

    if actor.role == "guest":
        raise HTTPException(403, "The house library is for residents")
    item = db.get(QueueItem, item_id)
    if not item:
        raise HTTPException(404, "Queue item not found")
    row = db.get(Record, identity(item.source_url))
    if not row or row.kind != "music.download" or row.deleted_at or row.data.get("state") != "ready":
        raise HTTPException(404, "This song isn't kept on the house")
    if row.owner_id != actor.id and actor.role != "admin":
        raise HTTPException(403, "Only the person who kept it, or an admin, can delete it")
    storage_check()
    left = item.status in {"ready", "pending_metadata", "failed", "awaiting_confirmation"} and (
        item.owner_id == actor.id or actor.role == "admin"
    )
    q = queue(db) if left else None  # the queue's lock first, as the worker takes it
    lock_quota(db)
    forget_song(db, row.id, row.version)
    emit(db, "audit.storage_reclaim", {"id": row.id, "kind": "music", "action": "delete"}, user_id=actor.id)
    emit(db, "files.changed", {"id": row.id})
    if left:
        item.status = "removed"
        q.version += 1
        emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    if left:
        from .worker import fetch

        fetch("cancel_download", item_id=item_id)
    return {"status": "completed", "left_queue": left}


@router.get("/music/storage")
def storage_summary(actor=Depends(require_actor), db=Depends(get_db)):
    """House-wide byte totals only: no owners, private names, paths or download links."""
    require_permission(actor, "music.read")
    storage_check()
    disk = shutil.disk_usage(settings.data_root)
    files = int(
        db.scalar(
            select(func.coalesce(func.sum(FileEntry.size), 0)).where(
                FileEntry.is_folder.is_(False), FileEntry.storage_removed_at.is_(None)
            )
        )
    )

    def ready_bytes(kind):
        size = Record.data["size"].as_integer()
        ready = select(func.coalesce(func.sum(size), 0)).where(
            Record.kind == kind,
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
            size > 0,
        )
        return int(db.scalar(ready))

    music, movies = ready_bytes("music.download"), ready_bytes("cinema.local_media")
    categories = {
        "music": music,
        "movies": movies,
        "files": files,
        "other": max(0, disk.used - music - movies - files),
    }
    return {
        "disk": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free},
        "categories": categories,
        "category_accounting": "Tracked file sizes; other includes system files, other applications and filesystem overhead.",
    }
