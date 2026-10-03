"""Explicitly transfer a completed shared upload into the persistent movie library."""

import os
import re
import stat
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .auth import Actor, require_actor, require_permission
from .cinema import CinemaTitle, allowed, call, router
from .config import settings
from .db import get_db, utcnow
from .files import accessible_entry, file_changed, lock_quota, root_fd, subdir_fd, upload_lock
from .models import Record
from .playback import VIDEO_SUFFIXES, probe_file


class LibraryImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    media_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, min_length=1, max_length=200)


def public_import(record):
    return {
        "id": record.id,
        "state": record.data["state"],
        "library_index": record.data.get("library_index", "pending_observation"),
        "title": record.data["title"],
    }


@router.post("/library/import")
def import_movie(body: LibraryImport, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    require_permission(actor, "files.write")
    require_permission(actor, "files.shared.write")
    identity = str(uuid5(NAMESPACE_URL, "houseos:cinema-upload:" + body.file_id))
    with upload_lock(body.file_id):
        prior = db.get(Record, identity)
        if prior and prior.owner_id != actor.id and actor.role != "admin":
            raise HTTPException(404, "Upload not found")
        if prior and prior.data.get("state") == "ready":
            return public_import(prior)
        entry = accessible_entry(db, actor, body.file_id, write=True)
        if entry.version != body.version:
            raise HTTPException(409, "The upload changed. Refresh and try again.")
        if entry.scope != "media" or entry.is_folder:
            raise HTTPException(422, "Choose a completed upload in shared media storage.")
        suffix = Path(entry.name).suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            raise HTTPException(422, "Choose a supported movie file such as MKV or MP4.")
        media = db.get(CinemaTitle, body.media_id) if body.media_id else None
        if body.media_id and (not media or media.kind != "movie"):
            raise HTTPException(422, "Select the exact movie title for this upload.")
        title = body.title or (media.title if media else Path(entry.name).stem)
        name = (
            (re.sub(r"[^\w .()-]", "_", title, flags=re.UNICODE)[:160].strip(". ") or "Movie")
            + "-"
            + entry.id
            + suffix
        )
        if prior:
            name = prior.data["_filename"]
            title = prior.data["title"]
        with subdir_fd("blobs") as blobs, root_fd() as root:
            media_fd = os.open("media", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                movies = os.open("movies", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=media_fd)
            finally:
                os.close(media_fd)
            try:
                if os.fstat(blobs).st_dev != os.fstat(movies).st_dev:
                    raise HTTPException(503, "Movie storage is not on the approved filesystem.")
                try:
                    source_stat = os.stat(entry.id, dir_fd=blobs, follow_symlinks=False)
                except FileNotFoundError:
                    source_stat = None
                try:
                    target_stat = os.stat(name, dir_fd=movies, follow_symlinks=False)
                except FileNotFoundError:
                    target_stat = None
                recovering = prior is not None and source_stat is None and target_stat is not None
                if not recovering and target_stat is not None:
                    raise HTTPException(409, "A library file already occupies this location.")
                info = target_stat if recovering else source_stat
                if not info or not stat.S_ISREG(info.st_mode) or info.st_size != entry.size:
                    raise HTTPException(409, "The uploaded bytes are missing or changed.")
                if not recovering:
                    inspected = call(probe_file, Path(settings.data_root) / "blobs" / entry.id)
                    if not inspected.get("video") or not inspected.get("duration"):
                        raise HTTPException(422, "This upload does not contain a playable video.")
                lock_quota(db)
                db.refresh(entry)
                if entry.version != body.version or entry.deleted_at or entry.trashed_at:
                    raise HTTPException(409, "The upload changed during inspection.")
                if prior is None:
                    prior = Record(
                        id=identity,
                        kind="cinema.local_media",
                        owner_id=actor.id,
                        visibility="house",
                        data={
                            "state": "importing",
                            "title": title,
                            "media_id": body.media_id,
                            "size": entry.size,
                            "_source_file_id": entry.id,
                            "_filename": name,
                            "_path": str(Path(settings.data_root) / "media" / "movies" / name),
                        },
                        version=1,
                    )
                    db.add(prior)
                    # Durable intent makes a process crash after rename recoverable by retry.
                    db.commit()
                    lock_quota(db)
                    db.refresh(entry)
                    if entry.version != body.version or entry.deleted_at or entry.trashed_at:
                        raise HTTPException(409, "The upload changed during import.")
                if not recovering:
                    current = os.stat(entry.id, dir_fd=blobs, follow_symlinks=False)
                    if (current.st_dev, current.st_ino, current.st_size) != (
                        info.st_dev,
                        info.st_ino,
                        info.st_size,
                    ):
                        raise HTTPException(409, "The uploaded file changed during inspection.")
                    os.rename(entry.id, name, src_dir_fd=blobs, dst_dir_fd=movies)
                    os.fsync(blobs)
                    os.fsync(movies)
                try:
                    prior.data = {
                        **prior.data,
                        "state": "ready",
                        "checksum": entry.checksum,
                        "library_index": "pending_observation",
                    }
                    entry.deleted_at = entry.storage_removed_at = utcnow()
                    entry.version += 1
                    file_changed(db, entry)
                    db.commit()
                except Exception:
                    db.rollback()
                    if not recovering:
                        os.rename(name, body.file_id, src_dir_fd=movies, dst_dir_fd=blobs)
                        os.fsync(blobs)
                        os.fsync(movies)
                    raise
                return public_import(prior)
            finally:
                os.close(movies)


def reconcile_index(db, items):
    """Record only exact file paths observed in a real Jellyfin library response."""
    from sqlalchemy import or_, select

    observed = {
        item["Path"]: item["Id"]
        for item in items
        if isinstance(item, dict) and isinstance(item.get("Path"), str) and item.get("Id")
    }
    if not observed:
        return
    records = db.scalars(
        select(Record)
        .where(
            Record.kind == "cinema.local_media",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
            or_(
                Record.data["library_index"].as_string() != "indexed",
                Record.data["library_media_id"].as_string().is_(None),
            ),
        )
        .limit(500)
    )
    for record in records:
        try:
            relative = Path(record.data.get("_path", "")).relative_to(Path(settings.data_root) / "media")
        except ValueError:
            continue
        if ".." in relative.parts:
            continue
        identity = observed.get("/media/" + relative.as_posix())
        if identity:
            title = db.scalar(
                select(CinemaTitle).where(CinemaTitle.data["jellyfin_id"].as_string() == identity).limit(1)
            )
            record.data = {
                **record.data,
                "library_index": "indexed",
                "jellyfin_id": identity,
                "library_media_id": title.id if title else None,
            }
