"""What this install has, measured: service probes, the first-run checklist, service health.

Every answer comes from a real probe (a heartbeat row written by the service, a ping on its
private socket, an HTTP answer), never from configuration alone. The same probes drive the
Setup checklist, Control Room → Services and Nox's voice button.
"""

import socket
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from . import ipc
from .auth import require_actor, require_admin
from .config import settings
from .db import get_db, utcnow
from .models import Integration, User

router = APIRouter(tags=["setup"])
RUN = settings.runtime_root / "run"

# name, docker compose service, how often it proves it is alive (seconds; None = socket/HTTP)
SERVICES = (
    ("api", "api", None),
    ("worker", "worker", 30),
    ("maintenance", "maintenance", 180),
    ("fetch", "fetch", None),
    ("audio", "audio", None),
    ("upload", "tusd", None),
    ("media", "relay", 60),
    ("cinema-worker", "cinema-worker", 60),
    ("cinema-observer", "cinema-observer", 60),
    ("voice", "voice", None),
    ("codex", "codex", None),
    ("claude", "claude", None),
)
ESSENTIAL = {"house", "access", "ai", "speakers", "sources", "invite"}
OPTIONAL: dict[str, str] = {}  # every service is part of the one Docker stack


BEATS = {"media": "relay"}  # the media relay's heartbeat row predates the service's name


def heartbeat(db, name, window):
    row = db.get(Integration, BEATS.get(name, name).replace("-", "_") + "_heartbeat")
    try:
        seen = datetime.fromisoformat(row.config["observed_at"].rstrip("Z"))
    except (AttributeError, KeyError, TypeError, ValueError):
        return {"status": "off"}
    fresh = utcnow() - seen < timedelta(seconds=window)
    return {"status": "ok" if fresh else "down", "observed_at": row.config["observed_at"], **row.config}


def ping(path, payload=None, timeout=1.5):
    """{"status": "off"} when nothing listens there, "down" when it no longer answers."""
    try:
        if not path.exists():
            return {"status": "off"}
    except OSError:  # a folder this process may not look into: not ours to reach
        return {"status": "off"}
    if payload is None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(str(path))
            return {"status": "ok"}
        except OSError:
            return {"status": "down"}
    reply = ipc.request(path, payload, timeout=timeout, failure={"status": "down"})
    return reply if reply.get("status") == "down" else {**reply, "status": "ok"}


def probe(db, name, window):
    if name == "api":
        return {"status": "ok"}
    if window:
        return heartbeat(db, name, window)
    if name == "fetch":
        return ping(RUN / "fetch.sock", {"action": "ping"})
    if name == "audio":
        from .music import bridge

        reply = bridge("outputs")
        if reply.get("status") in {"unavailable", "failed"}:
            return {"status": "off" if not settings.audio_socket.exists() else "down"}
        return {"status": "ok", "sound_server": reply.get("sound_server"), "selected": reply.get("selected")}
    if name == "upload":
        try:
            answer = httpx.options(settings.tusd_url + "/files/", timeout=1.5, trust_env=False)
            return {"status": "ok" if answer.status_code < 500 else "down"}
        except httpx.HTTPError:
            return {"status": "off"}
    if name == "voice":
        reply = ping(RUN / "voice.sock", {"command": "status"}, timeout=2)
        return {k: reply[k] for k in ("status", "loaded", "device", "preparing") if k in reply}
    if name in {"codex", "claude"}:
        return ping(getattr(settings, name + "_socket"))
    return {"status": "off"}


def probes(db) -> dict:
    return {name: probe(db, name, window) for name, _, window in SERVICES}


def ai_ready(db) -> bool:
    from .assistant_profiles import assignment

    selected = assignment(db, "general")
    row = db.get(Integration, selected["provider"])
    if not (row and row.enabled and selected.get("model")):
        return False
    mode = row.config.get("auth_mode", "api")
    return bool(row.encrypted_secret or mode != "api" or row.config.get("base_url"))


def smart_home_ready(db) -> bool:
    try:
        from .home import available

        return bool(available(db))
    except Exception:  # a Home Assistant that is down is a Smart home tab problem, not a crash here
        return False


def steps(db, request: Request) -> list[dict]:
    seen = probes(db)
    docker = settings.storage_container
    ok = {name for name, value in seen.items() if value["status"] == "ok"}
    enabled = {r.name for r in db.scalars(select(Integration).where(Integration.enabled.is_(True)))}
    people = db.scalar(select(func.count()).select_from(User))
    from .models import Invite
    from .cinema_models import CinemaDevice

    invited = people > 1 or db.scalar(select(func.count()).select_from(Invite))
    devices = db.scalar(select(func.count()).select_from(CinemaDevice))
    sound = seen["audio"].get("sound_server")
    from .music_outputs import output_choice

    cast_output = bool(output_choice(db).get("device_id"))
    https = request.url.scheme == "https"

    def step(key, done, tab, *, optional=False, unavailable=False, detail=None):
        state = "unavailable" if unavailable else "done" if done else "optional" if optional else "todo"
        return {"key": key, "state": state, "tab": tab, "detail": detail}

    return [
        step("house", db.get(Integration, "house_settings") is not None, "house"),
        step("access", https, "access", detail=None if https else "http"),
        step("ai", ai_ready(db), "ai"),
        step(
            "speakers",
            "audio" in ok and (sound in {"pulse", "alsa"} or cast_output),
            "speakers",
            optional="audio" in ok,
            unavailable="audio" not in ok,
            detail=sound,
        ),
        step("sources", "fetch" in ok, "services", unavailable="fetch" not in ok),
        step(
            "films",
            bool(enabled & {"stream_addon", "jellyfin", "real_debrid"}),
            "integrations",
            optional=True,
            unavailable=docker and "cinema-worker" not in ok,
        ),
        step("tv", bool(devices), "devices", optional=True),
        step("smart_home", smart_home_ready(db), "integrations", optional=True),
        step(
            "voice",
            "voice" in ok and not seen["voice"].get("preparing"),
            "services",
            optional=True,
            detail="preparing" if seen["voice"].get("preparing") else seen["voice"].get("device"),
        ),
        step("invite", bool(invited), "invites"),
        step("backups", False, "recovery", optional=True, detail="docker" if docker else "native"),
    ]


@router.get("/admin/setup")
def setup(request: Request, actor=Depends(require_admin), db=Depends(get_db)):
    items = steps(db, request)
    return {
        "container": settings.storage_container,
        "steps": items,
        "done": sum(s["state"] == "done" for s in items if s["key"] in ESSENTIAL),
        "needed": len(ESSENTIAL),
    }


def service_rows(db) -> list[dict]:
    """Control Room → Services in a container install: measured, with the restart command."""
    seen = probes(db)
    rows = []
    for name, compose, _ in SERVICES:
        state = seen[name]
        rows.append(
            {
                "name": name,
                "status": state["status"],
                "detail": {
                    k: v for k, v in state.items() if k in {"sound_server", "loaded", "device", "preparing"}
                },
                "restartable": name != "upload",
                "profile": OPTIONAL.get(name),
            }
        )
    return rows


@router.get("/assistant/voice/status")
def voice_status(actor=Depends(require_actor)):
    """Is speech-to-text running on this install, and where (for the microphone button)."""
    state = probe(None, "voice", None)
    ready = state["status"] == "ok" and not state.get("preparing")
    return {"available": ready, "preparing": bool(state.get("preparing")), "device": state.get("device")}
