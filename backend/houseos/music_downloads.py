"""One durable shared audio file per canonical source on the approved storage disk."""

import os
import shutil
import stat
from contextlib import contextmanager
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from .config import settings
from .db import SessionLocal
from .models import Record
from .music import QueueItem, canonical_source
from . import files, music_duplicates

KIND = "music.download"
MAX_SIZE = 400 * 1024**2


def identity(source):
    return str(uuid5(NAMESPACE_URL, "houseos-music:" + canonical_source(source)))


@contextmanager
def library_fd():
    with files.root_fd() as root:
        try:
            os.mkdir("music-downloads", 0o750, dir_fd=root)
        except FileExistsError:
            pass
        fd = os.open("music-downloads", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            if os.fstat(fd).st_dev != os.fstat(root).st_dev:
                raise OSError("Music library is not on the approved storage drive")
            yield fd
        finally:
            os.close(fd)


@contextmanager
def source_lock(source):
    import fcntl

    path = settings.runtime_root / "audio" / (".retain-" + identity(source) + ".lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def copy_atomic(source_fd, target_fd, name):
    """Copy only regular bounded audio; publication and directory entry are durable."""
    info = os.fstat(source_fd)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SIZE:
        raise ValueError("AUDIO_DOWNLOAD_LIMIT")
    temporary = "." + str(uuid4()) + ".part"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=target_fd)
    try:
        with os.fdopen(fd, "wb") as target, os.fdopen(os.dup(source_fd), "rb") as source:
            shutil.copyfileobj(source, target, 1024 * 1024)
            target.flush()
            if os.fstat(target.fileno()).st_size != info.st_size:
                raise ValueError("AUDIO_DOWNLOAD_CHANGED")
            os.fsync(target.fileno())
        os.replace(temporary, name, src_dir_fd=target_fd, dst_dir_fd=target_fd)
        os.fsync(target_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=target_fd)
        except FileNotFoundError:
            pass
    return info.st_size


def restore(db, source, item_id):
    record = db.get(Record, identity(source))
    if not record or record.kind != KIND or record.deleted_at or record.data.get("state") != "ready":
        return None
    item_id = str(UUID(item_id))
    try:
        with source_lock(source), library_fd() as folder:
            try:
                fd = os.open(record.id + ".media", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
            except FileNotFoundError:
                record.data = {**record.data, "state": "missing"}
                db.commit()
                return None
            try:
                if os.fstat(fd).st_size != record.data.get("size"):
                    return None
                audio = os.open(settings.runtime_root / "audio", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    name = item_id + ".media"
                    # Never replace an existing file that a player could already have open.
                    try:
                        staged = os.stat(name, dir_fd=audio, follow_symlinks=False)
                    except FileNotFoundError:
                        staged = None
                    if staged:
                        if not stat.S_ISREG(staged.st_mode) or staged.st_size != record.data["size"]:
                            return None
                    else:
                        if (
                            shutil.disk_usage(settings.runtime_root / "audio").free
                            < record.data["size"] + 2 * 1024**3
                        ):
                            return None
                        canonical = record.id + ".media"
                        try:
                            complete = os.stat(canonical, dir_fd=audio, follow_symlinks=False)
                        except FileNotFoundError:
                            complete = None
                        if complete is None:
                            # Runtime aliases share one inode. Permanent storage is never pruned.
                            sizes = {}
                            for entry in (settings.runtime_root / "audio").glob("*.media"):
                                try:
                                    info = entry.lstat()
                                except FileNotFoundError:
                                    continue
                                if stat.S_ISREG(info.st_mode):
                                    sizes[(info.st_dev, info.st_ino)] = info.st_size
                            if sum(sizes.values()) + record.data["size"] > 10 * 1024**3:
                                return None
                            copy_atomic(fd, audio, canonical)
                            complete = os.stat(canonical, dir_fd=audio, follow_symlinks=False)
                        if not stat.S_ISREG(complete.st_mode) or complete.st_size != record.data["size"]:
                            return None
                        if name != canonical:
                            try:
                                os.link(
                                    canonical, name, src_dir_fd=audio, dst_dir_fd=audio, follow_symlinks=False
                                )
                            except FileExistsError:
                                existing = os.stat(name, dir_fd=audio, follow_symlinks=False)
                                if (
                                    not stat.S_ISREG(existing.st_mode)
                                    or existing.st_size != record.data["size"]
                                ):
                                    return None
                            os.fsync(audio)
                finally:
                    os.close(audio)
            finally:
                os.close(fd)
        return {
            "status": "completed",
            "bytes": record.data["size"],
            "retained": True,
            **{key: record.data.get(key) for key in ("title", "duration", "uploader", "source_url")},
        }
    except (OSError, ValueError, HTTPException):
        return None


def retain(source, item_id):
    """Publish a completed cache file. Failure never removes audio or stops playback. A house
    that keeps no songs (music_keep_downloads off) publishes nothing."""
    from .house_settings import get_house_settings

    with SessionLocal() as db:
        if not get_house_settings(db)["music_keep_downloads"]:
            return {"retained": False}
    key = identity(source)
    try:
        with source_lock(source), library_fd() as folder:
            with SessionLocal() as db:
                item = db.get(QueueItem, str(UUID(item_id)))
                if (
                    not item
                    or item.status == "removed"
                    or item.source_url != canonical_source(source)
                    or item.metadata_json.get("is_live")
                ):
                    return {"retained": False, "retention_error": "MUSIC_NOT_RETAINABLE"}
                fd = os.open(
                    settings.runtime_root / "audio" / (str(UUID(item_id)) + ".media"),
                    os.O_RDONLY | os.O_NOFOLLOW,
                )
                try:
                    size = os.fstat(fd).st_size
                    if not stat.S_ISREG(os.fstat(fd).st_mode) or not 0 < size <= MAX_SIZE:
                        raise ValueError("AUDIO_DOWNLOAD_LIMIT")
                    files.lock_quota(db)
                    record = db.get(Record, key)
                    if record and record.deleted_at is None and record.data.get("state") == "ready":
                        try:
                            existing = os.stat(key + ".media", dir_fd=folder, follow_symlinks=False)
                            if stat.S_ISREG(existing.st_mode) and existing.st_size == record.data["size"]:
                                return {"retained": True, "download_id": key}
                        except FileNotFoundError:
                            pass
                    # Reconcile an interrupted reservation before calculating shared capacity.
                    if record:
                        record.data = {**record.data, "state": "failed"}
                        db.flush()
                    used, reserved = files.media_usage(db, locked=True)
                    if used + reserved + size > settings.media_quota_bytes:
                        return {"retained": False, "retention_error": "MUSIC_LIBRARY_FULL"}
                    disk = os.fstatvfs(folder)
                    if disk.f_bavail * disk.f_frsize < size + 2 * 1024**3:
                        return {"retained": False, "retention_error": "STORAGE_SPACE_LOW"}
                    if not record:
                        record = Record(
                            id=key, kind=KIND, owner_id=item.owner_id, visibility="house", data={}
                        )
                        db.add(record)
                    record.deleted_at = None
                    record.data = {
                        "state": "reserved",
                        "source_url": canonical_source(source),
                        "title": item.title,
                        "duration": item.metadata_json.get("duration"),
                        "uploader": item.metadata_json.get("uploader"),
                        "size": size,
                        "path": "music-downloads/" + key + ".media",
                        "item_id": item.id,
                    }
                    db.commit()
                    try:
                        copy_atomic(fd, folder, key + ".media")
                    except (OSError, ValueError):
                        try:
                            os.unlink(key + ".media", dir_fd=folder)
                        except FileNotFoundError:
                            pass
                        record.data = {**record.data, "state": "failed"}
                        db.commit()
                        raise
                    record.data = {**record.data, "state": "ready"}
                    record.version += 1
                    db.commit()
                    music_duplicates.flag(db, key, item.owner_id)
                    return {"retained": True, "download_id": key}
                finally:
                    os.close(fd)
    except (OSError, ValueError, HTTPException):
        # Reserved records survive interruption and are retried by the same canonical key.
        return {"retained": False, "retention_error": "MUSIC_RETENTION_FAILED"}
