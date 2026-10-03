"""Watch → Web: a pasted or shared video link, downloaded by the fetcher (public internet
only, no secrets), played on a screen through the films' own pipeline, deleted 6 h after its last
play. One Record (kind cinema.web_video) per link and person; the cinema worker's web lane does
the slow part, one video at a time."""

import hashlib
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ipc
from .auth import Actor, delegated_user, require_actor, user_permissions
from .cinema import (
    CinemaDevice,
    CinemaPreference,
    CinemaWorkflow,
    Launch,
    allowed,
    boot_identity,
    launch,
    router,
    upsert_title,
)
from .db import get_db, new_id, utcnow
from .events import emit
from .fetcher_web import DIR, partial_bytes
from .models import Record
from .playback import MediaError, effective_request, probe_file

KIND = "cinema.web_video"
KEEP = timedelta(hours=6)  # after its last play, unless still on a screen
FOLDER_LIMIT = 20 * 1024**3
WORKING = {"queued", "reading", "downloading"}
ENDED = {"stopped", "completed", "cancelled", "failed", "recovery_required"}


def find_link(text):
    """The link in what was pasted or shared ("Look! https://youtu.be/x?si=…", "youtu.be/x",
    "www.site.com/v/1"): the first address, without trailing punctuation, https by default."""
    text = str(text or "").strip()
    found = re.search(r"https?://\S+", text, re.I) or re.search(
        r"(?<![\w@.-])(?:[\w-]+\.)+[a-z]{2,}/\S*", text, re.I
    )
    if not found:
        raise HTTPException(422, {"code": "WEB_VIDEO_LINK_INVALID", "message": "No link in what was pasted."})
    url = found.group(0).rstrip(".,;:!?)]}>\"'»")
    if not re.match(r"https?://", url, re.I):
        url = "https://" + url
    parts = urlsplit(url)
    if not parts.hostname or parts.username or parts.password or len(url) > 2000:
        raise HTTPException(422, {"code": "WEB_VIDEO_LINK_INVALID", "message": "This link can't be read."})
    return url


def fetch(action, row, **extra):
    """One request to the fetcher; a download may take up to an hour."""
    timeout = 3660 if action == "web_video" else 90
    return ipc.fetcher(action, timeout=timeout, source_url=row.data.get("url"), item_id=row.id, **extra)


def video_path(row):
    name = row.data.get("file")
    path = DIR / name if name and "/" not in name else None
    return path if path and path.is_file() and not path.is_symlink() else None


def stream_folder(row):
    """A video played while it downloaded: its HLS pieces (fetcher_web.stream)."""
    folder = DIR / row.id
    return folder if row.data.get("stream") and (folder / "master.m3u8").is_file() else None


def complete(folder):
    try:
        return "#EXT-X-ENDLIST" in (folder / "video.m3u8").read_text()
    except OSError:
        return False


def kept(row):
    folder = stream_folder(row)
    return bool(video_path(row) or (folder and complete(folder)))


def size_of(row):
    path, folder = video_path(row), stream_folder(row)
    if path:
        return path.stat().st_size
    return sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) if folder else 0


def on_screen(db, row):
    """Its latest play is still on (or being sent to) a screen: it holds that screen. A play that
    never got the screen (refused, still waiting to be confirmed) is not on it."""
    flow = db.get(CinemaWorkflow, row.data.get("workflow_id") or "")
    if not flow or flow.state in ENDED or flow.updated_at <= utcnow() - timedelta(hours=12):
        return False
    device = db.get(CinemaDevice, flow.device_id) if flow.device_id else None
    return bool(device and device.owner_workflow == flow.id)


def public_web(db, row):
    data = row.data
    flow = db.get(CinemaWorkflow, data.get("workflow_id") or "")
    progress = None
    if data.get("state") == "downloading" and data.get("bytes"):
        progress = min(0.99, partial_bytes(row.id) / data["bytes"])
    # When its file goes: 6 h after it was last played (never while it plays).
    delete_at = (
        (datetime.fromisoformat(data["played_at"]) + KEEP).isoformat() + "Z"
        if data.get("played_at") and kept(row)
        else None
    )
    return {
        "id": row.id,
        "url": data.get("url"),
        "title": data.get("title") or "",
        "site": data.get("site") or "",
        "uploader": data.get("uploader") or "",
        "duration": data.get("duration"),
        "height": data.get("height"),
        "state": data.get("state"),
        "progress": progress,
        "error": data.get("error"),
        "kept": kept(row),
        "delete_at": delete_at,
        "device_id": data.get("device_id"),
        "needs_replace": bool(data.get("needs_replace")),
        "workflow_id": data.get("workflow_id"),
        "workflow_state": flow.state if flow else None,
        "poster": "/api/v1/cinema/titles/" + data["title_id"] + "/poster"
        if data.get("title_id") and data.get("thumbnail")
        else None,
        "played_at": data.get("played_at"),
        "created_at": row.created_at,
    }


def own(db, actor, identity):
    row = db.get(Record, identity)
    if not row or row.kind != KIND or row.owner_id != actor.id or row.deleted_at:
        raise HTTPException(404, "Video not found")
    return row


def screen(db, device_id):
    device = db.get(CinemaDevice, device_id) if device_id else None
    if not device or device.adapter == "dlna":  # DLNA renderers here are speakers
        raise HTTPException(404, "Screen not found")
    return device


class WebVideo(BaseModel):
    text: str = Field(min_length=1, max_length=4000)  # the link, or a whole shared message
    device_id: str = Field(min_length=1, max_length=36)
    replace: bool = False


class Replay(BaseModel):
    device_id: str = Field(min_length=1, max_length=36)
    replace: bool = False


@router.get("/web")
def web_videos(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Your recent links, newest first."""
    allowed(actor)
    rows = db.scalars(
        select(Record)
        .where(Record.kind == KIND, Record.owner_id == actor.id, Record.deleted_at.is_(None))
        .order_by(Record.updated_at.desc())
        .limit(30)
    )
    return {"items": [public_web(db, row) for row in rows]}


def queue_play(db, actor, row, device, replace):
    row.data = {
        **row.data,
        "state": "queued",
        "device_id": device.id,
        "replace": replace,
        "needs_replace": False,
        "error": None,
        "session": actor.session_hash,
    }
    row.updated_at = utcnow()
    row.version = (row.version or 0) + 1
    emit(db, "cinema.web", {"id": row.id}, user_id=actor.id)
    db.commit()
    return public_web(db, row)


@router.post("/web")
def add_web_video(body: WebVideo, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Play a link on a screen: read, downloaded, then played (the web lane does it)."""
    allowed(actor)
    url = find_link(body.text)
    device = screen(db, body.device_id)
    # The same link again: the same card (and its file, if still here), moved to the top.
    row = db.scalar(
        select(Record)
        .where(
            Record.kind == KIND,
            Record.owner_id == actor.id,
            Record.deleted_at.is_(None),
            Record.data["url"].as_string() == url,
        )
        .limit(1)
    )
    if row and row.data.get("state") in WORKING:
        return public_web(db, row)
    if not row:
        row = Record(id=new_id(), kind=KIND, owner_id=actor.id, visibility="private", data={"url": url})
        db.add(row)
    return queue_play(db, actor, row, device, body.replace)


@router.post("/web/{identity}/play")
def replay_web_video(
    identity: str, body: Replay, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    """Play again (downloaded again if it was deleted meanwhile), or replace what is on."""
    allowed(actor)
    row = own(db, actor, identity)
    flow = db.get(CinemaWorkflow, row.data.get("workflow_id") or "")
    if (
        body.replace
        and row.data.get("needs_replace")
        and flow
        and flow.state == "awaiting_playback_confirmation"
    ):
        # Something else was on: it is replaced now, even while this one still downloads.
        result = launch(
            flow.id,
            Launch(
                version=flow.version,
                source_id=flow.data["_selected_source"],
                device_id=flow.device_id,
                subtitle_track="off",
                replace=True,
            ),
            actor,
            db,
        )
        db.refresh(row)
        row.data = {**row.data, "needs_replace": False, "played_at": utcnow().isoformat()}
        if result.get("state") in {"failed", "recovery_required"}:
            row.data = {**row.data, "error": (result.get("error") or {}).get("code") or "PLAYBACK_FAILED"}
        db.commit()
        return public_web(db, row)
    if row.data.get("state") in WORKING:
        raise HTTPException(409, "This video is still getting ready.")
    return queue_play(db, actor, row, screen(db, body.device_id), body.replace)


@router.delete("/web/{identity}")
def remove_web_video(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Forget a link and its file (stops its download; refused while it plays)."""
    allowed(actor)
    row = own(db, actor, identity)
    if on_screen(db, row):
        raise HTTPException(409, "It is on a screen: stop it there first.")
    result = fetch("web_remove", row)
    if result.get("status") != "completed":
        raise HTTPException(503, "The downloader didn't answer. Try again in a moment.")
    row.deleted_at = utcnow()
    row.version += 1
    db.commit()
    return {"status": "completed"}


# ---------- the web lane (cinema worker) ----------


def fail(db, row, code):
    row.data = {**row.data, "state": "failed", "error": code}
    row.updated_at = utcnow()
    db.commit()


def recover(db):
    """At the worker's start: a video half read or downloaded was cut by the restart."""
    for row in db.scalars(
        select(Record).where(
            Record.kind == KIND,
            Record.deleted_at.is_(None),
            Record.data["state"].as_string().in_(["reading", "downloading"]),
        )
    ):
        row.data = {**row.data, "state": "failed", "error": "WEB_VIDEO_INTERRUPTED"}
    db.commit()


def process_one_web(db):
    """Read, download and play the oldest waiting link. True when there was one."""
    row = db.scalar(
        select(Record)
        .where(Record.kind == KIND, Record.deleted_at.is_(None), Record.data["state"].as_string() == "queued")
        .order_by(Record.updated_at)
        .limit(1)
    )
    if not row:
        return False
    user = delegated_user(db, row.owner_id, row.data.get("session"), "cinema.use")
    if not user:
        fail(db, row, "PERMISSION_REVOKED")
        return True
    actor = Actor(user.id, user.name, user.role, frozenset(user_permissions(user)), row.data.get("session"))
    if kept(row):  # still here: played again at once
        play(db, row, actor)
        return True
    row.data = {**row.data, "state": "reading", "file": None, "stream": None, "inspection": None}
    db.commit()
    info = fetch("web_info", row)
    if info.get("status") != "completed":
        fail(db, row, info.get("code") or "SOURCE_UNAVAILABLE")
        return True
    title = info.get("title") or urlsplit(row.data["url"]).hostname or "Video"
    row.data = {
        **row.data,
        **{key: info.get(key) for key in ("site", "uploader", "duration", "height", "bytes", "thumbnail")},
        "title": title,
        "state": "downloading",
    }
    db.commit()
    if info.get("streamable") and stream_and_play(db, row, actor):
        return True
    done = fetch("web_video", row, bytes=info.get("bytes"))
    db.refresh(row)
    if row.deleted_at:  # removed while it downloaded
        return True
    if done.get("status") != "completed":
        fail(db, row, done.get("code") or "SOURCE_UNAVAILABLE")
        return True
    row.data = {**row.data, "file": done["file"]}
    db.commit()
    play(db, row, actor)
    return True


def stream_and_play(db, row, actor):
    """Play while it downloads: the fetcher cuts the video into HLS pieces as they arrive; once the
    first ones are here it goes to the screen (the films' streaming route) and the rest follows.
    False when it can't be read that way after all: then it is downloaded whole first."""
    from .cinema_progressive import ready, write_master

    folder, result = DIR / row.id, {}
    worker = threading.Thread(
        target=lambda: result.update(fetch("web_stream", row, bytes=row.data.get("bytes"))), daemon=True
    )
    worker.start()
    plan = {"subtitle_mode": "off", "duration": row.data.get("duration") or 0}
    while worker.is_alive() and not ready(folder, plan):
        time.sleep(0.5)
    if not ready(folder, plan):
        worker.join()
        return False
    try:
        write_master(folder, plan, row.data.get("bytes") or 0)
    except MediaError:
        worker.join()
        return False
    row.data = {**row.data, "stream": row.id}
    db.commit()
    play(db, row, actor, downloading=True)
    worker.join()
    db.refresh(row)
    if row.deleted_at:
        return True
    if result.get("status") != "completed":
        # The TV plays what arrived; the rest can't come. Play again downloads it anew.
        row.data = {**row.data, "stream": None, "inspection": None}
        fail(db, row, result.get("code") or "WEB_VIDEO_INTERRUPTED")
        return True
    row.data = {**row.data, "state": "failed" if row.data.get("error") else "ready"}
    db.commit()
    return True


def stream_inspection(folder, duration):
    """What the video is, from its first piece (the init segment and the first fragment)."""
    probe = folder / "probe.mp4"
    probe.write_bytes((folder / "init.mp4").read_bytes() + (folder / "video0.m4s").read_bytes())
    try:
        inspection = probe_file(probe, timeout=30)
    finally:
        probe.unlink(missing_ok=True)
    return {**inspection, "duration": duration or inspection.get("duration")}


def play(db, row, actor, downloading=False):
    """The video on the chosen screen with the films' own launch: a whole file as a house file,
    or its HLS pieces as a prepared stream (still growing while it downloads)."""
    path, folder = video_path(row), stream_folder(row)
    try:
        inspection = row.data.get("inspection") or (
            stream_inspection(folder, row.data.get("duration")) if folder else probe_file(path, timeout=30)
        )
    except (MediaError, OSError) as error:
        return fail(db, row, getattr(error, "code", "MEDIA_PROBE_FAILED"))
    canonical = "web:" + hashlib.sha256(row.data["url"].encode()).hexdigest()[:40]
    title = upsert_title(
        db,
        canonical,
        row.data.get("title") or "Video",
        "web",
        {
            "layers": ["WEB"],
            "description": " · ".join(filter(None, [row.data.get("uploader"), row.data.get("site")]))[:300],
            **({"_poster_url": row.data["thumbnail"]} if row.data.get("thumbnail") else {}),
            **({"runtime": round(row.data["duration"] / 60)} if row.data.get("duration") else {}),
        },
    )
    source = {
        "id": new_id(),
        "release": (row.data.get("title") or "Video")[:300],
        "layer": "WEB",
        "web_video": row.id,
        "inspection": inspection,
        "size": size_of(row) if path else row.data.get("bytes") or size_of(row),
        "state": "preflight_usable",
    }
    preference = db.get(CinemaPreference, actor.id)
    request = effective_request(preference.data if preference else {}, {})
    flow = CinemaWorkflow(
        id=new_id(),
        owner_id=actor.id,
        media_id=title.id,
        device_id=row.data["device_id"],
        idempotency_key="web:" + new_id(),
        data={
            "request": request,
            "_initial_request": request,
            "_sources": [source],
            "_selected_source": source["id"],
            "_authorization_session": actor.session_hash,
            "_boot_id": boot_identity(),
            "_autoplay_expires_at": (utcnow() + timedelta(hours=2)).isoformat(),
            "_autoplay_depth": 0,
            # A stream plays from its pieces: the relay serves them, nothing is prepared again.
            **(
                {
                    "_prepared": {
                        "path": str(folder / "master.m3u8"),
                        "streaming": True,
                        "timeline_version": 2,
                        "position_offset": 0,
                        "subtitle_path": None,
                        "web": True,
                    }
                }
                if folder
                else {}
            ),
        },
    )
    db.add(flow)
    row.data = {**row.data, "inspection": inspection, "title_id": title.id, "workflow_id": flow.id}
    db.commit()
    try:
        result = launch(
            flow.id,
            Launch(
                version=flow.version,
                source_id=source["id"],
                device_id=row.data["device_id"],
                subtitle_track="off",
                replace=bool(row.data.get("replace")),
            ),
            actor,
            db,
        )
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        return fail(db, row, detail.get("code") or "PLAYBACK_FAILED")
    db.refresh(row)
    if result.get("state") in {"failed", "recovery_required"}:
        code = (result.get("error") or {}).get("code") or "PLAYBACK_FAILED"
        if downloading:  # the download goes on: the card says why the TV didn't start
            row.data = {**row.data, "error": code}
            db.commit()
            return
        return fail(db, row, code)
    row.data = {
        **row.data,
        "state": "downloading" if downloading else "ready",
        "error": None,
        "played_at": utcnow().isoformat(),
        # Something else is on that screen: the card asks before replacing it.
        "needs_replace": result.get("state") == "awaiting_playback_confirmation",
    }
    db.commit()


def prune_web_videos(db):
    """Files go 6 h after their last play (never while on a screen), oldest idle first when the
    folder passes 20 GB. The cards stay: Play again downloads it again."""
    rows = db.scalars(
        select(Record).where(Record.kind == KIND, Record.deleted_at.is_(None)).order_by(Record.updated_at)
    )
    kept = [(row, size_of(row)) for row in rows if row.data.get("file") or row.data.get("stream")]
    total = sum(size for _, size in kept)
    removed = 0
    for row, size in kept:
        if row.data.get("state") in WORKING or on_screen(db, row):
            continue
        last = row.data.get("played_at") or row.updated_at.isoformat()
        stale = last < (utcnow() - KEEP).isoformat()
        if not (stale or total > FOLDER_LIMIT):
            continue
        if fetch("web_remove", row).get("status") != "completed":
            break  # the downloader is away: next time
        total -= size
        row.data = {**row.data, "file": None, "stream": None, "inspection": None}
        removed += 1
    db.commit()
    return removed


def web_file(db, identity):
    """resolve_media's answer for a web video: its file, while the house still has it."""
    row = db.get(Record, identity)
    path = video_path(row) if row and row.kind == KIND else None
    if not path:
        raise MediaError(
            "MEDIA_UNAVAILABLE",
            "This video was deleted from the house. Play it again from Watch → Web.",
            "resolve",
        )
    return path
