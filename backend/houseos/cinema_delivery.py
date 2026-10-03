"""Scoped byte delivery with bounded authorization rechecks for every open stream."""

import os
import re
import stat
import time
from sqlalchemy.orm import Session
from .db import utcnow
from .playback import MediaError


def local_stream(path, byte_range=None, *, head=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise MediaError("MEDIA_UNAVAILABLE", "Prepared media is unavailable.", "delivery")
    size, start, end = info.st_size, 0, info.st_size - 1
    status = 200
    if byte_range:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
        if not match or not any(match.groups()):
            os.close(descriptor)
            raise MediaError("INVALID_RANGE", "Only one valid byte range is supported.", "delivery")
        first, last = match.groups()
        if first:
            start, end = int(first), min(int(last), end) if last else end
        else:
            start = max(0, size - int(last))
        if start > end or start >= size:
            os.close(descriptor)
            return 416, {"Content-Range": f"bytes */{size}", "Content-Length": "0"}, iter(())
        status = 206
    length = max(0, end - start + 1)
    headers = {"Content-Length": str(length), "Accept-Ranges": "bytes"}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if head:
        os.close(descriptor)
        return status, headers, iter(())

    def chunks():
        with os.fdopen(descriptor, "rb") as stream:
            stream.seek(start)
            left = length
            while left:
                data = stream.read(min(256 * 1024, left))
                if not data:
                    break
                left -= len(data)
                yield data

    return status, headers, chunks()


def grant_authorized(bind, token_hash):
    from .cinema import CinemaRelay, CinemaWorkflow, CinemaDevice
    from .auth import delegated_user

    with Session(bind) as fresh:
        grant = fresh.get(CinemaRelay, token_hash)
        if not grant or grant.expires_at <= utcnow():
            return False
        workflow = fresh.get(CinemaWorkflow, grant.workflow_id)
        if not workflow or workflow.state not in {"preparing", "command_sent", "playing_observed", "paused"}:
            return False
        device = fresh.get(CinemaDevice, workflow.device_id)
        if not device or device.owner_workflow != workflow.id:
            return False
        return (
            delegated_user(
                fresh, workflow.owner_id, workflow.data.get("_authorization_session"), "cinema.use"
            )
            is not None
        )


def revocable_chunks(chunks, bind, token_hash, authorized=None):
    authorized = authorized or grant_authorized
    last_check, since_check = 0, 1024**2
    try:
        for block in chunks:
            if time.monotonic() - last_check >= 1 or since_check >= 1024**2:
                if not authorized(bind, token_hash):
                    return
                last_check, since_check = time.monotonic(), 0
            since_check += len(block)
            yield block
    finally:
        close = getattr(chunks, "close", None)
        if close:
            close()


def refresh_rd_relay(bind, token_hash):
    """One durable renewal of the same approved torrent/file. Never add/select/replay."""
    from sqlalchemy import select
    from cryptography.fernet import Fernet
    from .cinema import CinemaRelay, CinemaWorkflow
    from .cinema_sources import resolve_media
    from .config import settings

    if not grant_authorized(bind, token_hash):
        raise MediaError("PERMISSION_REVOKED", "Playback delivery is no longer authorized.", "delivery")
    with Session(bind, expire_on_commit=False) as db:
        grant = db.get(CinemaRelay, token_hash)
        if not grant:
            raise MediaError("PERMISSION_REVOKED", "Playback delivery was revoked.", "delivery")
        workflow = db.scalar(
            select(CinemaWorkflow).where(CinemaWorkflow.id == grant.workflow_id).with_for_update()
        )
        if not workflow:
            raise MediaError("PERMISSION_REVOKED", "Playback delivery was revoked.", "delivery")
        source = next(
            (
                item
                for item in workflow.data.get("_sources", [])
                if item["id"] == workflow.data.get("_selected_source")
            ),
            None,
        )
        if (
            not source
            or source.get("jellyfin_item")
            or (
                source.get("provider") != "stream_addon"
                and (not source.get("torrent_id") or not source.get("file_id"))
            )
        ):
            raise MediaError("SOURCE_EXPIRED", "This source needs a new playback preview.", "delivery")
        if workflow.data.get("_relay_refresh_attempts", 0) >= 1:
            raise MediaError(
                "SOURCE_EXPIRED",
                "The one authorized source renewal was already attempted. Choose a new playback plan.",
                "delivery",
            )
        workflow.data = {**workflow.data, "_relay_refresh_attempts": 1}
        workflow_id, source_id = workflow.id, source["id"]
        db.commit()  # Claim before network calls; an uncertain renewal is not replayed.
        try:
            url, size = resolve_media(db, source, refresh=True)
            if size and source.get("size") and size != source["size"]:
                raise MediaError(
                    "PLAN_STALE",
                    "The renewed source size changed. Prepare a fresh playback plan.",
                    "delivery",
                )
            if not grant_authorized(bind, token_hash):
                raise MediaError(
                    "PERMISSION_REVOKED", "Playback was revoked during source renewal.", "delivery"
                )
            db.expire_all()
            current = db.scalar(
                select(CinemaWorkflow).where(CinemaWorkflow.id == workflow_id).with_for_update()
            )
            grant = db.get(CinemaRelay, token_hash)
            if not grant or not current or current.data.get("_selected_source") != source_id:
                raise MediaError("PLAN_STALE", "Playback changed during source renewal.", "delivery")
            grant.encrypted_url = Fernet(settings.encryption_key.encode()).encrypt(url.encode()).decode()
            current.data = {**current.data, "_relay_refreshed_at": utcnow().isoformat()}
            db.commit()
            return url
        except MediaError as exc:
            db.rollback()
            current = db.get(CinemaWorkflow, workflow_id)
            if current:
                current.data = {
                    **current.data,
                    "error": exc.public(),
                    "recovery_actions": ["choose_source", "inspect_destination"],
                }
                db.commit()
            raise
