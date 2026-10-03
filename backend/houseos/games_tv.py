"""Games on the TV: Sunshine streams this computer's game to Moonlight on the TV (or a
phone, a laptop), and the controller plugged into that screen plays it. HouseOS writes which game
to start and for whom (run/next.json); the launcher Sunshine starts (deploy/houseos_game.py) plays
it in RetroArch with that person's saves, and reports back (run/tv.json). Native Linux installs
only: a container can't reach the screen or the graphics card this needs."""

import json
import os
import time
from pathlib import Path

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .atomic import write_json
from .auth import Actor, require_actor
from .config import settings
from .db import get_db
from .fetcher_games import DIR as CACHE
from .games import allowed, bios_dir, fetch, game_path, game_row, router, saves
from .games_systems import SYSTEMS
from .models import Record

RUN = CACHE / "run"
SUNSHINE = "https://127.0.0.1:47990"
_ready = {"at": 0.0, "value": False}


def host():
    try:
        return json.loads((RUN / "host.json").read_text())
    except (OSError, ValueError):
        return {}


def sunshine_up():
    import socket

    try:
        socket.create_connection(("127.0.0.1", 47989), timeout=0.5).close()
        return True
    except OSError:
        return False


def host_ready():
    """TV play is set up here: the launcher said RetroArch is installed, and Sunshine answers."""
    if time.monotonic() - _ready["at"] > 30:
        _ready.update(at=time.monotonic(), value=bool(host().get("retroarch")) and sunshine_up())
    return _ready["value"]


def on_tv():
    try:
        now = json.loads((RUN / "tv.json").read_text())
    except (OSError, ValueError):
        return None
    return now if now.get("state") == "playing" and time.time() - now.get("at", 0) < 20 else None


def sunshine(method, path, body=None):
    """Sunshine's own admin API on this computer (its password is in the house's secrets)."""
    import httpx

    user, password = os.environ.get("HOUSEOS_SUNSHINE_USER"), os.environ.get("HOUSEOS_SUNSHINE_PASSWORD")
    if not user or not password:
        raise HTTPException(503, {"code": "GAMES_TV_NOT_SET_UP", "message": "TV play isn't set up here."})
    try:
        reply = httpx.request(
            method, SUNSHINE + path, json=body, auth=(user, password), verify=False, timeout=5
        )  # its certificate is its own, on this very computer
        reply.raise_for_status()
        return reply.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, {"code": "GAMES_TV_UNAVAILABLE", "message": "Sunshine isn't answering."})


@router.get("/tv")
def tv_status(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    now = on_tv()
    playing = None
    if now:
        row = db.get(Record, now.get("game_id") or "")
        playing = {
            "game_id": now.get("game_id"),
            "title": row.data.get("title") if row else None,
            "player": now.get("player"),
            "mine": now.get("user_id") == actor.id,
            "since": now.get("since"),
        }
    try:
        picked = json.loads((RUN / "next.json").read_text())
    except (OSError, ValueError):
        picked = {}
    return {
        "ready": host_ready(),
        "native": not settings.storage_container,
        "playing": playing,
        "waiting": bool(picked) and not now and time.time() - picked.get("at", 0) < 1800,
        "picked": {"game_id": picked.get("game_id"), "title": picked.get("title")} if picked else None,
    }


class Play(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str = Field(min_length=36, max_length=36)


@router.post("/tv/play")
def tv_play(body: Play, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Pick the game the TV plays: open Moonlight → HouseOS (or, if a game is on, it switches)."""
    allowed(actor)
    if not host_ready():
        raise HTTPException(409, {"code": "GAMES_TV_NOT_SET_UP", "message": "TV play isn't set up here."})
    row = game_row(db, body.game_id)
    system = SYSTEMS.get(row.data.get("system") or "")
    if not system or not system.get("tv"):
        raise HTTPException(
            422, {"code": "GAMES_TV_UNSUPPORTED", "message": "This console can't play on the TV."}
        )
    core = CACHE / "cores" / (system["tv"] + "_libretro.so")
    if not core.is_file():  # the first game of a console fetches its emulator
        result = fetch("games_core", core=system["tv"], timeout=300)
        if result.get("status") != "completed" or not core.is_file():
            raise HTTPException(
                503, {"code": "GAMES_CORE_UNAVAILABLE", "message": "The emulator didn't download."}
            )
    path = game_path(db, row)
    folder = saves(actor.id, row.id)
    folder.mkdir(parents=True, exist_ok=True)
    picked = {
        "at": time.time(),
        "game_id": row.id,
        "title": row.data.get("title"),
        "system": row.data.get("system"),
        "user_id": actor.id,
        "player": actor.name,
        "path": str(path),
        "core": str(core),
        "saves": str(folder),
        "bios": str(bios_dir()),
    }
    write_json(RUN / "next.json", picked, 0o660)  # the desktop user's game script reads it
    (RUN / "stop").unlink(missing_ok=True)
    return {"state": "switching" if on_tv() else "waiting", "title": picked["title"]}


@router.post("/tv/stop")
def tv_stop(actor: Actor = Depends(require_actor)):
    allowed(actor)
    RUN.mkdir(parents=True, exist_ok=True)
    Path(RUN / "stop").touch()
    return {"state": "stopping"}


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin: str = Field(pattern=r"^\d{4}$")
    name: str = Field(min_length=1, max_length=60)


def admin(actor):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")


@router.post("/tv/pair")
def tv_pair(body: Pair, actor: Actor = Depends(require_actor)):
    """Moonlight shows a 4-digit code the first time: typing it here pairs that screen."""
    admin(actor)
    reply = sunshine("POST", "/api/pin", {"pin": body.pin, "name": body.name})
    if not reply.get("status") in (True, "true"):
        raise HTTPException(409, {"code": "GAMES_PAIR_FAILED", "message": "That code didn't work."})
    return {"paired": True}


@router.get("/tv/devices")
def tv_devices(actor: Actor = Depends(require_actor)):
    admin(actor)
    reply = sunshine("GET", "/api/clients/list")
    return {"items": [{"id": c.get("uuid"), "name": c.get("name")} for c in reply.get("named_certs", [])]}


@router.delete("/tv/devices/{device_id}")
def tv_unpair(device_id: str, actor: Actor = Depends(require_actor)):
    admin(actor)
    sunshine("POST", "/api/clients/unpair", {"uuid": device_id})
    return {"removed": device_id}
