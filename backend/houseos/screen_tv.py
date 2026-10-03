"""Show on the TV: a YouTube link, played full screen on this computer's screen, which Sunshine
streams to Moonlight on the TV.

One press (a phone's share sheet, a button on YouTube, Nox) does all of it:
- the TV: turned on through Home Assistant, then Moonlight opened straight on this computer's
  desktop (on LG webOS, with launch parameters Moonlight TV reads; elsewhere, its input);
- the computer: the desktop helper (docs/native/houseos_screen.py, run as the desktop user)
  waits for the stream, opens the video in the browser and puts it full screen.

The helper asks for work with a long poll and reports back; both live in the api process (one
process on both installs), so a restart only drops a request that was a few seconds old.

Shortcuts, userscripts and the helper can't sign in or send the browser's Origin: they carry the
house's screen key instead (`Authorization: Bearer …`, created in Control Room → Devices). The
key only reaches these routes, never a session, and acts as the administrator who created it."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy.orm import Session

from . import home, tv_remote
from .atomic import write_json
from .auth import Actor, Input, delegated_user, require_actor, require_admin, user_permissions
from .config import settings
from .db import get_db
from .events import emit

router = APIRouter(prefix="/tv/screen", tags=["tv"])

MOONLIGHT = "Moonlight"  # the app's name in the TV's sources
WEBOS_MOONLIGHT = "com.limelight.webos"  # Moonlight TV's id on LG webOS
HELPER_FRESH = 90  # seconds since the helper last asked (it may be busy with a video for a minute)
CLAIM_WAIT = 8  # seconds the helper has to take a request
TV_BOOT = 25  # seconds a TV may take to answer after turning on
WAIT_MAX = 25  # the helper's long poll

YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
LIST_ID = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
LINK = re.compile(r"https?://[^\s<>\"']+")
TIME = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")

CHANGED = threading.Condition()
HELPER: dict = {}  # the helper's last report: at, name, host_uuid, app_id, streaming, browser
JOB: dict = {}  # the latest request (one at a time: a newer one replaces it)


# ---------- the link ----------
def seconds(value):
    """YouTube's t= ("90", "90s", "1m30s", "1h2m3s") in whole seconds, or 0."""
    match = TIME.match((value or "").strip().lower())
    if not match or not any(match.groups()):
        return 0
    hours, minutes, secs = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + secs


def youtube(text, at=None):
    """The YouTube video in a shared text or link, as {id, url, start}; None when there isn't one.
    Only the video, its playlist and its start time are kept (no tracking parameters)."""
    for link in LINK.findall(text or ""):
        parts = urlsplit(link.rstrip(".,;)!?"))
        host = (parts.hostname or "").lower().removeprefix("www.")
        if host not in YOUTUBE_HOSTS:
            continue
        query = parse_qs(parts.query)
        path = [p for p in parts.path.split("/") if p]
        if host == "youtu.be":
            video = path[0] if path else ""
        elif path[:1] in (["shorts"], ["live"], ["embed"]) and len(path) > 1:
            video = path[1]
        else:
            video = (query.get("v") or [""])[0]
        if not VIDEO_ID.match(video):
            continue
        start = int(at) if at and at > 0 else seconds((query.get("t") or query.get("start") or [""])[0])
        keep = {"v": video}
        playlist = (query.get("list") or [""])[0]
        if LIST_ID.match(playlist):
            keep["list"] = playlist
        if start:
            keep["t"] = f"{start}s"
        return {"id": video, "url": "https://www.youtube.com/watch?" + urlencode(keep), "start": start}
    return None


# ---------- the screen key ----------
def folder():
    path = settings.runtime_root / "run" / "screen"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def saved_key():
    try:
        return json.loads((folder() / "key.json").read_text())
    except (OSError, ValueError):
        return {}


def digest(key):
    return hashlib.sha256(key.encode()).hexdigest()


def bearer(request):
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value[:7].lower() == "bearer " else None


def key_actor(db, key):
    """The administrator who created the screen key, while the key and their account hold."""
    saved = saved_key()
    if not key or not saved.get("hash") or not secrets.compare_digest(digest(key), saved["hash"]):
        raise HTTPException(
            401, {"code": "SCREEN_KEY_REFUSED", "message": "This screen key isn't valid any more."}
        )
    user = delegated_user(db, saved.get("user_id"))
    if not user or user.role != "admin":
        raise HTTPException(
            401, {"code": "SCREEN_KEY_REFUSED", "message": "This screen key isn't valid any more."}
        )
    return Actor(user.id, user.name, user.role, user_permissions(user), None)


def helper_caller(request: Request, db: Session = Depends(get_db)):
    return key_actor(db, bearer(request))


def caller(request: Request, db: Session = Depends(get_db)):
    """A request with the screen key uses only the key (it skipped the Origin check); the app
    itself uses its sign-in."""
    if request.headers.get("authorization") is not None:
        return key_actor(db, bearer(request))
    return require_actor(request, db)


# ---------- the helper on the computer ----------
def helper_up():
    return time.time() - HELPER.get("at", 0) < HELPER_FRESH


def take_job():
    if JOB.get("state") == "waiting":
        JOB["state"] = "taken"
        return {key: JOB[key] for key in ("id", "url", "start", "expect_stream")}
    return None


@router.get("/next")
def next_job(
    host_uuid: str = "",
    app_id: int = 0,
    streaming: bool = False,
    name: str = "",
    browser: str = "",
    wait: int = WAIT_MAX,
    actor: Actor = Depends(helper_caller),
):
    """The helper's long poll: what it reports about the computer, and the next video if any."""
    report = {
        "at": time.time(),
        "host_uuid": host_uuid if re.fullmatch(r"[0-9A-Fa-f-]{36}", host_uuid) else "",
        "app_id": app_id if 0 < app_id < 2**31 else 0,
        "streaming": streaming,
        "name": name[:60],
        "browser": browser[:40],
    }
    deadline = time.monotonic() + max(0, min(wait, WAIT_MAX))
    with CHANGED:
        HELPER.update(report)
        job = take_job()
        while job is None and (left := deadline - time.monotonic()) > 0:
            CHANGED.wait(left)
            HELPER["at"] = time.time()
            job = take_job()
        CHANGED.notify_all()
    return {"job": job}


class Report(Input):
    state: str = Field(pattern=r"^(claimed|opened|failed)$")
    streaming: bool | None = None
    detail: str | None = Field(default=None, max_length=300)


@router.post("/jobs/{job_id}")
def job_report(job_id: str, body: Report, actor: Actor = Depends(helper_caller)):
    with CHANGED:
        if JOB.get("id") != job_id:
            return {"current": False}
        JOB.update(state=body.state, detail=body.detail, updated_at=time.time())
        if body.streaming is not None:
            JOB["streaming"] = body.streaming
            HELPER["streaming"] = body.streaming
        CHANGED.notify_all()
    return {"current": True}


# ---------- the TV ----------
def find_tv(base, headers, config):
    """The one Home Assistant TV HouseOS may control that lists Moonlight among its sources."""
    found = []
    for state in home.ha(base, headers, "/api/states"):
        entity = str(state.get("entity_id", ""))
        if not entity.startswith("media_player."):
            continue
        if MOONLIGHT not in ((state.get("attributes") or {}).get("source_list") or []):
            continue
        try:
            home.exposed_domain(config, entity)
        except HTTPException:
            continue
        found.append(state)
    return found[0] if len(found) == 1 else None


def tv_service(base, headers, domain, service, data):
    return home.ha(
        base, headers, f"/api/services/{domain}/{service}", method="POST", payload=data, timeout=10
    )


def open_moonlight(base, headers, entity, host_uuid, app_id):
    """Moonlight straight on this computer's desktop (LG webOS); else just Moonlight."""
    if host_uuid and app_id:
        launch = {"id": WEBOS_MOONLIGHT, "params": {"host_uuid": host_uuid, "host_app_id": app_id}}
        for attempt in range(3):  # a TV that just woke up may refuse for a moment
            try:
                tv_service(
                    base,
                    headers,
                    "webostv",
                    "command",
                    {"entity_id": entity, "command": "system.launcher/launch", "payload": launch},
                )
                return "opened Moonlight on the computer"
            except HTTPException:
                time.sleep(2 * (attempt + 1))
    tv_service(base, headers, "media_player", "select_source", {"entity_id": entity, "source": MOONLIGHT})
    return "opened Moonlight"


def bring_tv(db, streaming, host_uuid, app_id):
    """Turn the TV on and onto the stream. Returns {name, done}; name is None without a TV."""
    try:
        base, headers, config = home.connection(db)
    except HTTPException:
        return {"name": None, "done": []}
    tv = find_tv(base, headers, config)
    if not tv:
        return {"name": None, "done": []}
    entity = tv["entity_id"]
    name = (tv.get("attributes") or {}).get("friendly_name") or entity
    done = []
    if tv.get("state") in {"off", "standby", "unavailable"}:
        tv_service(base, headers, "media_player", "turn_on", {"entity_id": entity})
        done.append("turned on")
        deadline = time.monotonic() + TV_BOOT
        while tv.get("state") in {"off", "standby", "unavailable"} and time.monotonic() < deadline:
            time.sleep(1)
            try:
                tv = home.read_state(base, headers, entity)
            except HTTPException:
                continue
        if tv.get("state") in {"off", "standby", "unavailable"}:
            raise HTTPException(
                504,
                {
                    "code": "SCREEN_TV_ASLEEP",
                    "message": "The TV didn't wake up. Home Assistant needs a way to turn it on (Wake on LAN).",
                },
            )
    on_moonlight = (tv.get("attributes") or {}).get("source") == MOONLIGHT
    if on_moonlight and streaming:
        done.append("already on the computer")
        return {"name": name, "done": done}
    if on_moonlight:  # open but not streaming: launch parameters only count on a fresh start
        try:
            tv_service(
                base,
                headers,
                "webostv",
                "command",
                {"entity_id": entity, "command": "system.launcher/close", "payload": {"id": WEBOS_MOONLIGHT}},
            )
            time.sleep(1.5)
        except HTTPException:
            pass
    done.append(open_moonlight(base, headers, entity, host_uuid, app_id))
    return {"name": name, "done": done}


# ---------- showing a video ----------
def show(db, actor, text, at=None):
    """The whole press: the video to the computer, the TV onto the computer. Returns what was
    done; "sent" means the computer took it, not that the video plays yet."""
    tv_remote.allowed(actor)
    video = youtube(text, at)
    if not video:
        raise HTTPException(
            422, {"code": "SCREEN_NOT_YOUTUBE", "message": "That isn't a YouTube video link."}
        )
    if not helper_up():
        raise HTTPException(
            409,
            {
                "code": "SCREEN_HELPER_OFFLINE",
                "message": "The computer isn't ready: check it is on, with someone signed in to its desktop.",
            },
        )
    try:
        base, headers, config = home.connection(db)
        expect_stream = find_tv(base, headers, config) is not None
    except HTTPException:
        expect_stream = False
    job_id = secrets.token_urlsafe(12)
    with CHANGED:
        JOB.clear()
        JOB.update(
            id=job_id,
            url=video["url"],
            start=video["start"],
            video=video["id"],
            expect_stream=expect_stream,
            state="waiting",
            at=time.time(),
            by=actor.name,
        )
        CHANGED.notify_all()
        deadline = time.monotonic() + CLAIM_WAIT
        while JOB.get("id") == job_id and JOB["state"] in {"waiting", "taken"}:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            CHANGED.wait(left)
        claimed = JOB.get("id") == job_id and JOB["state"] in {"claimed", "opened"}
        streaming = bool(JOB.get("streaming", HELPER.get("streaming")))
        if not claimed and JOB.get("id") == job_id:
            JOB["state"] = "failed"
            JOB["detail"] = JOB.get("detail") or "The computer didn't take the video."
    if not claimed:
        raise HTTPException(
            503,
            {
                "code": "SCREEN_HELPER_SILENT",
                "message": "The computer didn't take the video. Try again in a moment.",
            },
        )
    tv = (
        bring_tv(db, streaming, HELPER.get("host_uuid"), HELPER.get("app_id"))
        if expect_stream
        else {"name": None, "done": []}
    )
    emit(db, "audit.tv.screen_show", {"video": video["id"], "tv": tv["done"]}, actor.id)
    db.commit()
    return {"status": "sent", "video": video, "tv": tv}


class Show(Input):
    url: str = Field(min_length=10, max_length=2000, description="a YouTube link, or text containing one")
    at: float | None = Field(default=None, ge=0, le=86400, description="start here (seconds)")


@router.post("/show")
def show_route(body: Show, actor: Actor = Depends(caller), db: Session = Depends(get_db)):
    return show(db, actor, body.url, body.at)


@router.get("")
def status(actor: Actor = Depends(require_actor)):
    """Whether Show on the TV works now: the helper, the computer's stream, the latest request."""
    tv_remote.allowed(actor)
    up = helper_up()
    reply = {
        "ready": up,
        "computer": {
            "name": HELPER.get("name") or None,
            "streaming": bool(HELPER.get("streaming")) if up else False,
            "stream_host": bool(HELPER.get("host_uuid") and HELPER.get("app_id")) if up else False,
            "browser": HELPER.get("browser") or None,
            "seen_at": HELPER.get("at"),
        },
        "last": {key: JOB.get(key) for key in ("state", "video", "detail", "at", "by")} if JOB else None,
    }
    if actor.role == "admin":
        saved = saved_key()
        reply["key"] = (
            {"created_at": saved.get("created_at"), "by": saved.get("by")} if saved.get("hash") else None
        )
    return reply


@router.post("/key")
def create_key(actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    """A new screen key (the previous one stops working). Shown once; only its hash is kept."""
    key = "hos_screen_" + secrets.token_urlsafe(32)
    write_json(
        folder() / "key.json",
        {"hash": digest(key), "user_id": actor.id, "by": actor.name, "created_at": time.time()},
    )
    emit(db, "audit.tv.screen_key", {"action": "created"}, actor.id)
    db.commit()
    return {"key": key}


@router.delete("/key")
def delete_key(actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    (folder() / "key.json").unlink(missing_ok=True)
    emit(db, "audit.tv.screen_key", {"action": "removed"}, actor.id)
    db.commit()
    return {"removed": True}
