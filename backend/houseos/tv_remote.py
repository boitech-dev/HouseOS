"""A remote for each TV the house knows, with only the buttons that TV really has.

Each screen can have two remotes ("targets"): the **TV itself**, when Home Assistant controls
it (power, input, volume and its own arrows), and the **device** HouseOS casts to (a
Chromecast, Google TV or DLNA TV: its volume and playback, and its arrows once paired).

- Arrows, OK, back and home (plus volume, play/pause and power) use the Android TV Remote
  protocol through androidtvremote2, as Home Assistant's "Android TV Remote" does: Google TV,
  Chromecast with Google TV, the Google TV Streamer and most Android TVs. Paired once: the TV
  shows a code and the resident types it.
- Without that, volume, mute and play/pause go through Cast (cinema_cast) or DLNA.
- Power and input go through Home Assistant when its TV is mapped to this device (cinema_tv).

Pairing identity: androidtvremote2 loads its client certificate and key from files, so HouseOS
keeps one identity in <runtime_root>/run/tv-remote (folder 0700, files 0600). `run/` is the
api's writable state on both installs; storing it encrypted in the database would still need
a plaintext copy on disk for every connection. It only lets HouseOS press keys on TVs that
accepted it, never leaves the server and no endpoint returns it.

Connections live in the api process: one asyncio loop thread, one connection per paired TV,
kept up by the library's own reconnect loop."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import cinema, cinema_tv  # noqa: F401 (cinema first: it and cinema_tv import each other)
from .atomic import write_json
from .auth import Actor, Input, require_actor
from .cinema_models import CinemaDevice
from .config import settings
from .db import get_db
from .playback import MediaError

router = APIRouter(prefix="/tv", tags=["tv"])
# Android TV Remote key names (KEYCODE_ + name); nothing else is ever sent.
REMOTE_KEYS = (
    "DPAD_UP",
    "DPAD_DOWN",
    "DPAD_LEFT",
    "DPAD_RIGHT",
    "DPAD_CENTER",
    "BACK",
    "HOME",
    "VOLUME_UP",
    "VOLUME_DOWN",
    "VOLUME_MUTE",
    "MEDIA_PLAY_PAUSE",
    "POWER",
)
Key = Literal[REMOTE_KEYS + ("INPUT", "VOLUME_SET")]  # VOLUME_SET: an exact level (0–100)
NAVIGATION = {"DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER", "BACK", "HOME"}
REMOTE_PORT = 6466
STEP = 5  # volume step (percent) over Cast and DLNA
PROBE_SECONDS = 10

LOCK = threading.Lock()
LOOP: asyncio.AbstractEventLoop | None = None
REMOTES: dict = {}  # device id -> connected AndroidTVRemote
UP: dict = {}  # device id -> connection currently up
PAIRING: dict = {}  # device id -> (client waiting for the code, started at)
PROBES: dict = {}  # device id -> (monotonic time, probe)


def unreachable():
    return MediaError(
        "TV_UNREACHABLE", "The TV didn't answer. Check it is on and on the same Wi-Fi.", "control", True
    )


def unpaired():
    return MediaError(
        "TV_REMOTE_NOT_PAIRED", "The remote isn't set up on this TV yet. Choose Set up the remote.", "setup"
    )


def unsupported():
    return MediaError("TV_KEY_UNSUPPORTED", "This TV doesn't have that button in HouseOS.", "control")


def allowed(actor):
    """The Smart home permission, or the Cinema one that already covers the TV."""
    if actor.role != "admin" and not {"home.control", "cinema.use"} & set(actor.permissions):
        raise HTTPException(403, "Permission denied")


# ---------- pairing identity and paired TVs ----------
def folder():
    path = settings.runtime_root / "run" / "tv-remote"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def paired_ids():
    try:
        return set(json.loads((folder() / "paired.json").read_text()))
    except (OSError, ValueError):
        return set()


def set_paired(device_id, paired):
    ids = paired_ids() | {device_id} if paired else paired_ids() - {device_id}
    write_json(folder() / "paired.json", sorted(ids))
    PROBES.pop(device_id, None)


# ---------- the connection loop ----------
def run(coroutine, timeout):
    """Run a coroutine on the remote loop, at most `timeout` seconds; library errors become sentences."""
    global LOOP
    with LOCK:
        if LOOP is None:
            LOOP = asyncio.new_event_loop()
            threading.Thread(target=LOOP.run_forever, name="tv-remote", daemon=True).start()
    future = asyncio.run_coroutine_threadsafe(asyncio.wait_for(coroutine, timeout), LOOP)
    try:
        return future.result(timeout + 1)
    except MediaError:
        raise
    except ImportError:
        raise MediaError(
            "TV_REMOTE_UNAVAILABLE", "This server needs an update before it can be a TV remote.", "setup"
        ) from None
    except Exception as exc:
        future.cancel()
        if type(exc).__name__ == "InvalidAuth":  # androidtvremote2's, without importing it here
            raise unpaired() from None
        raise unreachable() from None


async def client(address):
    from androidtvremote2 import AndroidTVRemote

    folder_path = folder()
    remote = AndroidTVRemote(
        "HouseOS", str(folder_path / "client.pem"), str(folder_path / "client.key"), address
    )
    if await remote.async_generate_cert_if_missing():
        for name in ("client.pem", "client.key"):
            os.chmod(folder_path / name, 0o600)
    return remote


def forget(device_id):
    remote = REMOTES.pop(device_id, None)
    UP.pop(device_id, None)
    if remote:
        remote.disconnect()


async def connected(device_id, address):
    """The live connection to a paired TV, (re)connecting when it is down."""
    from androidtvremote2 import InvalidAuth

    remote = REMOTES.get(device_id)
    if remote and (remote.host != address or not UP.get(device_id)):
        forget(device_id)
        remote = None
    if remote:
        return remote
    remote = await client(address)
    try:
        await remote.async_connect()
    except InvalidAuth:
        set_paired(device_id, False)  # the TV no longer knows HouseOS
        raise
    REMOTES[device_id], UP[device_id] = remote, True
    remote.add_is_available_updated_callback(lambda up: UP.__setitem__(device_id, up))
    remote.keep_reconnecting(lambda: (set_paired(device_id, False), forget(device_id)))
    return remote


async def send_keys(device_id, address, key, times):
    remote = await connected(device_id, address)
    for _ in range(times):
        remote.send_key_command(key)


async def remote_state(device_id, address):
    remote = await connected(device_id, address)
    volume = remote.volume_info or {}
    return {
        "on": remote.is_on,
        "app": remote.current_app,
        "volume": round(100 * volume["level"] / volume["max"]) if volume.get("max") else None,
        "muted": volume.get("muted"),
    }


async def start_pairing(device_id, address):
    old = PAIRING.pop(device_id, None)
    if old:
        old[0].disconnect()
    remote = await client(address)
    await remote.async_start_pairing()
    PAIRING[device_id] = (remote, time.monotonic())


async def finish_pairing(device_id, code):
    from androidtvremote2 import InvalidAuth

    remote, started = PAIRING.pop(device_id, (None, 0))
    if not remote or time.monotonic() - started > 300:
        raise MediaError("TV_PAIRING_EXPIRED", "The code expired. Start again to get a new one.", "setup")
    try:
        await remote.async_finish_pairing(code)
    except InvalidAuth:
        remote.disconnect()
        raise MediaError(
            "TV_PAIRING_CODE", "That code didn't match. Start again to get a new code.", "setup"
        ) from None
    forget(device_id)


# ---------- what each TV supports ----------
def port_open(address, port, timeout=0.8):
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False


def cast_state(address):
    from .cinema_cast import connect, fresh_media_status

    cast = connect(address)
    try:
        status = cast.status
        try:
            media = fresh_media_status(cast)
        except Exception:
            media = None
        live = media is not None and media.player_state in {"PLAYING", "PAUSED", "BUFFERING"}
        return {
            "app": status.display_name,
            "volume": round(status.volume_level * 100),
            "muted": status.volume_muted,
            "on": False if status.is_stand_by is True else None,
            "title": media.title if live else None,
            "playing": media.player_state == "PLAYING" if media else None,
        }
    finally:
        cast.disconnect()


def probe(device_id, adapter, address, paired):
    """Network look at one TV (no database): reachability, pairability and cheap state."""
    cached = PROBES.get(device_id)
    if cached and time.monotonic() - cached[0] < PROBE_SECONDS:
        return cached[1]
    result = {"reachable": None, "pairable": False, "state": {}}
    if adapter == "cast":
        result["reachable"] = port_open(address, 8009)
        if result["reachable"]:
            try:
                result["state"] = cast_state(address)
            except Exception:
                pass
    if adapter in {"cast", "dlna"}:
        result["pairable"] = paired or port_open(address, REMOTE_PORT)
    if paired:
        try:
            result["state"].update(
                {k: v for k, v in run(remote_state(device_id, address), 4).items() if v is not None}
            )
            result["reachable"] = True
        except MediaError as exc:
            result["remote_error"] = exc.code
            if exc.code == "TV_UNREACHABLE":
                result["reachable"] = False
    PROBES[device_id] = (time.monotonic(), result)
    return result


# The TV's own remote keys, when its Home Assistant integration offers them as buttons
# (button.<tv>_up, _ok, …, as Hisense VIDAA does): arrows before the Google/Android TV
# remote is paired.
HA_BUTTONS = {
    "DPAD_UP": ("up",),
    "DPAD_DOWN": ("down",),
    "DPAD_LEFT": ("left",),
    "DPAD_RIGHT": ("right",),
    "DPAD_CENTER": ("ok", "select", "enter"),
    "BACK": ("back", "return"),
    "HOME": ("home",),
}


def ha_buttons(db, device):
    """{key: (service path, data)} for the mapped TV's arrows, OK, back and home in Home
    Assistant: its integration's remote (LG, Samsung, Sony, Roku, Apple TV…, see home.REMOTES),
    else button entities named like its keys (Hisense VIDAA)."""
    from . import home

    base, headers, entity = cinema_tv.bridge(db, device)
    home.entities(base, headers["Authorization"].removeprefix("Bearer "))
    brand = home.remote(entity)
    if brand:
        domain, service, target, field, names = brand
        return {
            key: (f"/api/services/{domain}/{service}", {**target, field: name}) for key, name in names.items()
        }
    prefix = "button." + entity.split(".", 1)[1] + "_"
    found = {
        str(state.get("entity_id")): state.get("state")
        for state in cinema_tv.private_json(base, "/api/states", headers=headers, timeout=4)
        if str(state.get("entity_id", "")).startswith(prefix)
    }
    keys = {}
    for key, names in HA_BUTTONS.items():
        entity_id = next(
            (prefix + n for n in names if found.get(prefix + n) not in {None, "unavailable"}), None
        )
        if entity_id:
            keys[key] = ("/api/services/button/press", {"entity_id": entity_id})
    # ponytail: only a full set of arrows + OK counts; partial sets are ignored.
    return (
        keys
        if all(k in keys for k in ("DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER"))
        else {}
    )


def home_assistant(db, device):
    """The Home Assistant TV mapped to this device, or None."""
    try:
        cinema_tv.bridge(db, device)
    except Exception:
        return None
    try:
        observed = cinema_tv.tv_observation(db, device)
    except Exception:
        return {"state": "unavailable", "inputs": [], "buttons": {}}
    try:
        observed["buttons"] = ha_buttons(db, device)
    except Exception:
        observed["buttons"] = {}
    return observed


# Home Assistant media_player feature bits.
VOLUME_SET, VOLUME_MUTE, VOLUME_STEP = 4, 8, 1024


def capabilities(adapter, paired, pairable):
    """The cast/DLNA device's own remote."""
    cast, dlna = adapter == "cast", adapter == "dlna"
    return {
        "dpad": paired,
        "volume": paired or cast or dlna,
        "volume_level": cast or dlna,  # an exact level: a slider, not steps
        "mute": paired or cast or dlna,
        "playback": paired or cast,
        "power": paired,
        "input": False,
        "remote_pairable": pairable,
        "paired": paired,
    }


def tv_capabilities(ha):
    """The TV itself, through Home Assistant."""
    features = ha.get("features") or 0
    return {
        "dpad": bool(ha.get("buttons")),
        "volume": bool(features & (VOLUME_SET | VOLUME_STEP)),
        # A soundbar plays the sound: the TV's own level changes nothing heard, only steps do.
        "volume_level": bool(features & VOLUME_SET) and not ha.get("external_speakers"),
        "mute": bool(features & VOLUME_MUTE),
        "playback": False,
        "power": True,
        "input": bool(ha.get("inputs")),
        "remote_pairable": False,
        "paired": False,
    }


def supports(caps, key):
    if key in NAVIGATION:
        return caps["dpad"]
    return {
        "VOLUME_UP": caps["volume"],
        "VOLUME_DOWN": caps["volume"],
        "VOLUME_MUTE": caps["mute"],
        "VOLUME_SET": caps["volume_level"],
        "MEDIA_PLAY_PAUSE": caps["playback"],
        "POWER": caps["power"],
        "INPUT": caps["input"],
    }.get(key, False)


def tvs(db):
    """Devices shown as TVs: Cast and DLNA screens, not speakers or speaker groups."""
    rows = db.scalars(select(CinemaDevice).where(CinemaDevice.adapter.in_(("cast", "dlna"))).limit(50))
    return [row for row in rows if (row.capabilities or {}).get("kind") not in {"audio", "group"}]


def describe(db, devices):
    paired = paired_ids()
    with ThreadPoolExecutor(8) as pool:
        probes = list(pool.map(lambda d: probe(d.id, d.adapter, d.address, d.id in paired), devices))
    items = []
    for device, found in zip(devices, probes):
        is_paired = device.id in paired_ids()  # a probe may have found the pairing gone
        ha = home_assistant(db, device)
        if ha:
            level = ha.get("volume")
            items.append(
                {
                    "id": device.id,
                    "target": "tv",
                    "name": ha.get("display_name") or device.name,
                    "adapter": "home_assistant",
                    "via": device.name,
                    "capabilities": tv_capabilities(ha),
                    "inputs": ha.get("inputs", []),
                    # Where films switch the TV; "" = never switch, None = not chosen yet.
                    "film_input": (device.capabilities or {}).get("tv_input"),
                    "film_input_now": film_input(device, ha),
                    "state": {
                        "reachable": ha.get("state") not in {"unavailable", None},
                        "on": None
                        if ha.get("state") in {"unavailable", "unknown", None}
                        else ha["state"] != "off",
                        "input": ha.get("input"),
                        "volume": round(level * 100) if isinstance(level, (int, float)) else None,
                        "muted": ha.get("muted"),
                    },
                }
            )
        state = dict(found["state"])
        state["reachable"] = found["reachable"]
        items.append(
            {
                "id": device.id,
                "target": "device",
                "name": device.name,
                "adapter": device.adapter,
                "capabilities": capabilities(device.adapter, is_paired, found["pairable"]),
                "inputs": [],
                "state": state,
            }
        )
    return items


# ---------- pressing a button ----------
def ha_service(db, device, service, payload):
    base, headers, entity = cinema_tv.bridge(db, device)
    cinema_tv.private_json(
        base,
        "/api/services/media_player/" + service,
        headers=headers,
        method="POST",
        payload={"entity_id": entity, **payload},
        timeout=5,
    )


def dlna_volume(device, key):
    from . import dlna

    where = dlna.target(device)
    if key == "VOLUME_MUTE":
        muted = dlna.soap(where, dlna.RC, "GetMute", InstanceID=0, Channel="Master").get("CurrentMute")
        dlna.soap(where, dlna.RC, "SetMute", InstanceID=0, Channel="Master", DesiredMute=int(muted != "1"))
        return
    level = int(
        dlna.soap(where, dlna.RC, "GetVolume", InstanceID=0, Channel="Master").get("CurrentVolume") or 0
    )
    step = STEP if key == "VOLUME_UP" else -STEP
    dlna.dlna_control(where, "volume", max(0, min(100, level + step)))


def ha_button(db, device, press, times):
    base, headers, _ = cinema_tv.bridge(db, device)
    path, payload = press
    for _ in range(times):
        cinema_tv.private_json(base, path, headers=headers, method="POST", payload=payload, timeout=5)


def press_tv(db, device, key, value=None, times=1):
    """A key for the TV itself, through Home Assistant."""
    ha = home_assistant(db, device)
    if ha is None:
        raise unsupported()
    if not supports(tv_capabilities(ha), key):
        raise unsupported()
    if ha.get("state") in {"unavailable", None}:
        raise unreachable()
    if key == "INPUT":
        if value not in ha["inputs"]:
            raise MediaError("TV_INPUT_UNKNOWN", "Choose one of the inputs this TV reports.", "control")
        ha_service(db, device, "select_source", {"source": value})
    elif key == "POWER":
        ha_service(db, device, "turn_on" if ha.get("state") == "off" else "turn_off", {})
    elif key == "VOLUME_SET":
        ha_service(db, device, "volume_set", {"volume_level": round(exact_volume(value) / 100, 2)})
    elif key in NAVIGATION:
        ha_button(db, device, ha["buttons"][key], times)
    elif key == "VOLUME_MUTE":
        ha_service(db, device, "volume_mute", {"is_volume_muted": not ha.get("muted")})
    elif (ha.get("features") or 0) & VOLUME_STEP:
        for _ in range(times):
            ha_service(db, device, "volume_up" if key == "VOLUME_UP" else "volume_down", {})
    else:
        step = times * STEP / 100 * (1 if key == "VOLUME_UP" else -1)
        level = max(0.0, min(1.0, (ha.get("volume") or 0) + step))
        ha_service(db, device, "volume_set", {"volume_level": round(level, 2)})
    return {"status": "sent", "via": "home_assistant", "key": key, **({"input": value} if value else {})}


def film_input(device, ha):
    """The TV input this cast device is plugged into: the one a resident chose, else an input
    named after it (Chromecast, Google TV, Cast), else None."""
    inputs = (ha or {}).get("inputs") or []
    chosen = (device.capabilities or {}).get("tv_input")
    if chosen in inputs:
        return chosen
    if chosen == "":  # "never switch"
        return None
    guess = [name for name in inputs if any(w in name.casefold() for w in ("cast", "google", "chrome"))]
    return guess[0] if len(guess) == 1 else None


def wake_for_film(db, device):
    """Before a film is cast: turn the mapped TV on and put it on the cast device's input. Best
    effort (the film is sent either way); returns what was done, for the activity diary."""
    try:
        ha = cinema_tv.tv_observation(db, device)
    except Exception:
        return []  # no TV mapped through Home Assistant, or it isn't answering
    if ha.get("state") in {"unavailable", "unknown", None}:
        return []
    done = []
    if ha.get("state") == "off":
        ha_service(db, device, "turn_on", {})
        done.append("turned on")
        deadline = time.monotonic() + 8  # the TV lists its inputs again once it is up
        while time.monotonic() < deadline:
            time.sleep(0.5)
            try:
                ha = cinema_tv.tv_observation(db, device)
            except Exception:
                continue
            if ha.get("state") not in {"off", "unavailable"}:
                break
    target = film_input(device, ha)
    if target and ha.get("input") != target:
        ha_service(db, device, "select_source", {"source": target})
        done.append("switched to " + target)
    return done


def exact_volume(value):
    """A volume level from a slider: a whole percent, 0–100, or refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
        raise MediaError("TV_VOLUME_INVALID", "Choose a volume between 0 and 100.", "control")
    return round(value)


def press(db, device, key, value=None, times=1, target="device"):
    """Send one allowlisted key the best way this target supports. Returns how it was sent."""
    PROBES.pop(device.id, None)
    if target == "tv":
        return press_tv(db, device, key, value, times)
    if key == "INPUT":
        raise unsupported()
    if key == "VOLUME_SET":  # an exact level over Cast or DLNA, even with the remote paired
        if device.adapter == "cast":
            from .cinema_cast import cast_control

            cast_control(device.address, "volume", exact_volume(value))
        elif device.adapter == "dlna":
            from . import dlna

            dlna.dlna_control(dlna.target(device), "volume", exact_volume(value))
        else:
            raise unsupported()
        return {"status": "sent", "via": device.adapter, "key": key, "level": exact_volume(value)}
    if device.id in paired_ids():
        run(send_keys(device.id, device.address, key, times), 5)
        return {"status": "sent", "via": "remote", "key": key}
    if key in NAVIGATION or key == "POWER":
        raise unpaired() if device.adapter == "cast" else unsupported()
    if device.adapter == "cast":
        from .cinema_cast import cast_control

        action = {"VOLUME_UP": "volume_step", "VOLUME_DOWN": "volume_step", "VOLUME_MUTE": "mute"}.get(
            key, "toggle"
        )
        for _ in range(times):
            cast_control(device.address, action, -STEP if key == "VOLUME_DOWN" else STEP)
        return {"status": "sent", "via": "cast", "key": key}
    if device.adapter == "dlna" and key.startswith("VOLUME_"):
        for _ in range(times):
            dlna_volume(device, key)
        return {"status": "sent", "via": "dlna", "key": key}
    raise unsupported()


def device_or_404(db, device_id):
    device = db.get(CinemaDevice, device_id)
    if not device or device.adapter not in {"cast", "dlna"}:
        raise HTTPException(404, "TV not found")
    return device


def call(function, *args):
    try:
        return function(*args)
    except MediaError as exc:
        raise HTTPException(422, exc.public()) from None


class Press(Input):
    key: Key
    input: str | None = Field(default=None, max_length=80)
    level: int | None = Field(default=None, ge=0, le=100)  # for VOLUME_SET
    target: Literal["device", "tv"] = "device"


class FilmInput(Input):
    input: str = Field(
        default="",
        max_length=80,
        description="exact input label the Chromecast is plugged into (e.g. HDMI 2); empty = never switch",
    )


class PairCode(Input):
    code: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")


@router.get("")
def list_tvs(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    return {"items": describe(db, tvs(db))}


@router.post("/{device_id}/remote")
def press_key(
    device_id: str, body: Press, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    allowed(actor)
    value = body.level if body.key == "VOLUME_SET" else body.input
    return call(press, db, device_or_404(db, device_id), body.key, value, 1, body.target)


@router.post("/{device_id}/remote/pair")
def pair(device_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    device = device_or_404(db, device_id)
    call(run, start_pairing(device.id, device.address), 10)
    return {"status": "code_shown", "message": "Look at your TV: type the code it shows."}


@router.post("/{device_id}/remote/pair/finish")
def pair_finish(
    device_id: str, body: PairCode, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    allowed(actor)
    device = device_or_404(db, device_id)
    call(run, finish_pairing(device.id, body.code.upper()), 10)
    set_paired(device.id, True)
    return {"status": "paired"}


@router.put("/{device_id}/film-input")
def set_film_input(
    device_id: str, body: FilmInput, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    """The TV input a film switches to on this screen (HDMI 2 when the Chromecast is there)."""
    allowed(actor)
    device = device_or_404(db, device_id)
    device.capabilities = {**(device.capabilities or {}), "tv_input": body.input}
    db.commit()
    return {"film_input": body.input}
