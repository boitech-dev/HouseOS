"""Docker installs: Control Room buttons for houseos.sh (update, back up, GPU voice, own address).

The optional helper service (compose.helper.yml) holds the Docker socket and runs only these
fixed actions. The app asks through signed notes in the state volume: only the processes that
hold the encryption key (never the fetcher, the sound player or the AI clients) can sign one.
"""

import hashlib
import hmac
import ipaddress
import json
import time
import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .auth import Input, require_admin
from .config import settings
from .db import get_db, utcnow
from .events import emit
from .models import Integration, Operation, User

router = APIRouter(prefix="/admin/house-actions", tags=["control-room"])
EFFECTS = {
    "update": "Download the new version of HouseOS, rebuild it and restart it. Music, films and "
    "this page stop for a few minutes (longer on a Raspberry Pi).",
    "backup": "Copy the database, the keys and the files into the backups folder next to HouseOS. "
    "Everything pauses for about a minute.",
    "gpu-on": "Voice typing moves to the NVIDIA graphics card: faster and more accurate. Voice "
    "restarts; the first start downloads a larger speech model.",
    "gpu-off": "Voice typing moves back to the processor. Voice restarts.",
    "own-address": "HouseOS gets its own address on your network, like any other device. "
    "HouseOS restarts; afterwards open it at the new address.",
    "own-address-off": "HouseOS goes back to using this computer's address. HouseOS restarts.",
}


def folder(name):
    return settings.runtime_root / "run" / name


def signing_key():
    # Derived, so the encryption key itself never signs anything; the helper derives the same.
    return bytes.fromhex(hashlib.sha256(b"houseos-helper:" + settings.encryption_key.encode()).hexdigest())


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def helper_alive():
    try:
        return time.time() - float(folder("helper-out").joinpath("alive").read_text()) < 30
    except (OSError, ValueError):
        return False


class Updates(Input):
    auto: bool


def update_config(db):
    row = db.get(Integration, "house_updates")
    return dict(row.config or {}) if row else {}


def save_update_config(db, **values):
    row = db.get(Integration, "house_updates", with_for_update=True)
    if row is None:
        row = Integration(name="house_updates", config={})
        db.add(row)
    row.config = {**(row.config or {}), **values}


def send(action, arg="", request_id=None):
    """One signed note for the helper; it runs only its fixed actions."""
    request_id = request_id or str(uuid.uuid4())
    note = json.dumps({"id": request_id, "action": action, "arg": arg, "ts": int(time.time())})
    signature = hmac.new(signing_key(), note.encode(), hashlib.sha256).hexdigest()
    inbox = folder("helper-in")
    inbox.mkdir(mode=0o700, parents=True, exist_ok=True)
    (inbox / (request_id + ".tmp")).write_text(json.dumps({"body": note, "sig": signature}))
    (inbox / (request_id + ".tmp")).rename(inbox / (request_id + ".json"))
    return request_id


def available():
    """(current version, new version) when the helper's last look found one, else None."""
    about = (read(folder("helper-out") / "check.json") or {}).get("results", {})
    if about.get("behind") in (None, "", "0"):
        return None
    return about.get("current") or "", about.get("latest") or about.get("behind") + " changes"


def house_busy(db, music=True):
    """Music playing or a film on a screen: never the moment to restart. music=False for a
    restart that resumes the song where it was (the resume-music marker), so only films count."""
    from sqlalchemy import text

    songs = "(select count(*) from music_queue where desired = 'playing' and current_id is not null) + "
    return bool(
        db.execute(
            text(
                "select "
                + (songs if music else "")
                + "(select count(*) from cinema_workflows where state in "
                "('playing_observed', 'paused', 'command_sent', 'preparing'))"
            )
        ).scalar()
    )


def update_watch(db):
    """Maintenance, every minute: tell the admins (in their inbox, from Nox) once per new version,
    and with automatic updates on, start it at night when nothing plays."""
    if not settings.storage_container:
        return
    found = available()
    if not found:
        return
    from zoneinfo import ZoneInfo

    from .household import notify
    from .house_settings import get_house_settings

    current, latest = found
    config = update_config(db)
    if config.get("noticed") != latest:
        for admin in db.scalars(select(User).where(User.role == "admin")):
            notify(db, admin.id, latest[:36], "update", "update:" + latest)
        save_update_config(db, noticed=latest)
    hour = (
        utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(get_house_settings(db)["timezone"])).hour
    )
    if (
        config.get("auto")
        and config.get("auto_started") != latest
        and 3 <= hour < 5
        and helper_alive()
        and not house_busy(db)
    ):
        send("update")
        save_update_config(db, auto_started=latest)
        emit(db, "audit.house_action_requested", {"action": "update", "automatic": True})


class Request(Input):
    address: str | None = None


def argument(action, body, db):
    if action == "backup":  # how many backups to keep (older ones go only when the admin chose)
        from .house_settings import get_house_settings

        return str(get_house_settings(db)["backup_keep"])
    if action != "own-address":
        return ""
    try:
        address = ipaddress.IPv4Address((body.address or "").strip())
    except ValueError:
        raise HTTPException(422, "Give an address such as 192.168.1.250")
    if not address.is_private or address.is_loopback:
        raise HTTPException(422, "Use a free address on your home network, such as 192.168.1.250")
    return str(address)


@router.get("")
def status(actor=Depends(require_admin), db=Depends(get_db)):
    out = folder("helper-out")
    tasks = []
    if out.is_dir():
        for path in sorted(out.glob("*-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            task = read(path)
            if task:
                log = out / (path.stem + ".log")
                task["log"] = log.read_text()[-4000:] if log.exists() else ""
                tasks.append(task)
    check = read(out / "check.json") or {}
    auto = bool(update_config(db).get("auto"))
    db.rollback()
    return {
        "container": settings.storage_container,
        "auto": auto,
        "helper": helper_alive(),
        "about": check.get("results", {}),
        "checked": check.get("state") == "done",
        "effects": EFFECTS,
        "available": available(),
        "tasks": tasks,
    }


@router.post("/{action}/prepare")
def prepare(action: str, body: Request, actor=Depends(require_admin), db=Depends(get_db)):
    if action not in EFFECTS:
        raise HTTPException(404, "Unknown action")
    if not helper_alive():
        raise HTTPException(
            409, "The HouseOS helper is not running: on the server, run ./houseos.sh buttons on"
        )
    op = Operation(
        actor_id=actor.id,
        kind="house.action",
        state="needs_confirmation",
        data={"action": action, "arg": argument(action, body, db)},
        expires_at=utcnow() + timedelta(minutes=2),
    )
    db.add(op)
    db.commit()
    return {"status": "needs_confirmation", "confirmation_id": op.id, "effect": EFFECTS[action]}


def backup_guard(db):
    """One backup at a time, and not twice in ten minutes: a double tap never makes two."""
    from datetime import datetime
    from .core import backup_status

    made = backup_status().get("created_at")
    recent = utcnow() - timedelta(minutes=10)
    asked = db.scalar(
        select(Operation.id)
        .where(Operation.kind == "house.action", Operation.state == "accepted", Operation.created_at > recent)
        .where(Operation.data["action"].as_string() == "backup")
        .limit(1)
    )
    if asked or (made and datetime.fromisoformat(made.replace("Z", "+00:00")).replace(tzinfo=None) > recent):
        raise HTTPException(409, "A backup was just made or is running: wait ten minutes before another")


@router.post("/confirm/{identity}")
def confirm(identity: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "house.action"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Confirmation expired or consumed")
    action = row.data["action"]
    if action == "backup":
        backup_guard(db)
    request_id = send(
        "own-address" if action == "own-address-off" else action,
        "off" if action == "own-address-off" else row.data["arg"],
    )
    row.state, row.result = "accepted", {"request": request_id}
    emit(db, "audit.house_action_requested", {"action": action, "operation_id": row.id}, actor.id)
    db.commit()
    return {"status": "accepted", "request": request_id}


@router.post("/check")
def check_now(actor=Depends(require_admin)):
    """Look for a new version now (harmless: nothing is installed)."""
    if not helper_alive():
        raise HTTPException(
            409, "The HouseOS helper is not running: on the server, run ./houseos.sh buttons on"
        )
    send("check")
    return {"status": "checking"}


@router.put("/updates")
def set_updates(body: Updates, actor=Depends(require_admin), db=Depends(get_db)):
    save_update_config(db, auto=body.auto)
    emit(db, "audit.house_updates", {"auto": body.auto}, actor.id)
    db.commit()
    return {"auto": body.auto}
