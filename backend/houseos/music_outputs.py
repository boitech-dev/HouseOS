"""Where the music plays besides this computer: phones and computers in Speaker mode, and one
speaker or TV on the Wi-Fi (Cast or DLNA). mpv (audio.py) stays the house clock; every other
output follows it."""

import hashlib
import os
import secrets
import socket
import stat
import subprocess
import sys
import time
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import require_actor, require_permission
from .config import settings
from .db import SessionLocal, get_db, utcnow
from .models import Integration
from .music import ACTIVE_QUEUE_STATUSES, QueueItem, QueueState, bridge, pending_order, router
from .playback import MediaError

OUTPUT = "music_output"  # {"device_id": ..., "grant": {...}}: the admin's choice, the relay grant
HEARTBEAT = "relay_heartbeat"
SERVER_ONLY = "This plays on the server's speakers only."
RADIO_SERVER_ONLY = "This station plays on the server's speakers only."
relay_router = APIRouter(prefix="/receiver/music", tags=["receiver"])
NETWORK_ADAPTERS = ("cast", "dlna")  # the enrolled devices music can follow the house on


def output_choice(db):
    """The admin's choice; `device_id` is the network speaker or TV music plays on, if any."""
    row = db.get(Integration, OUTPUT)
    config = dict(row.config or {}) if row else {}
    if "device_id" not in config:  # an older setting: only a Cast device
        config["device_id"] = config.get("cast_device_id")
    return config


def save_output_choice(db, **values):
    row = db.scalar(select(Integration).where(Integration.name == OUTPUT).with_for_update())
    if row is None:
        row = Integration(name=OUTPUT, config={})
        db.add(row)
    row.config = {**(row.config or {}), **values}


# ---------- the relay's LAN address ----------
def lan_address(target="8.8.8.8"):
    """This computer's address on the route to `target`; a UDP connect sends nothing.
    HOUSEOS_LAN_ADDRESS wins: with a VPN or a Tailscale exit node, that route leaves the house."""
    if settings.lan_address:
        return settings.lan_address
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((target, 9))
        return probe.getsockname()[0]


def relay_port():
    # The relay is started by uvicorn with --port (8991 in Docker, set in deploy/ natively).
    return int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000


def write_relay_heartbeat(db, target="8.8.8.8"):
    base = settings.receiver_base_url or "http://" + lan_address(target) + ":" + str(relay_port())
    row = db.get(Integration, HEARTBEAT)
    if row is None:
        row = Integration(name=HEARTBEAT)
        db.add(row)
    row.config = {"observed_at": utcnow().isoformat() + "Z", "base_url": base}
    db.commit()
    return base


def relay_heartbeat():
    """Relay process thread: every 10 s, say where speakers and TVs can reach this relay."""
    from .cinema_models import CinemaDevice

    while True:
        try:
            with SessionLocal() as db:
                device = db.scalar(
                    select(CinemaDevice.address).where(CinemaDevice.adapter.in_(NETWORK_ADAPTERS)).limit(1)
                )
                write_relay_heartbeat(db, device or "8.8.8.8")
        except Exception as exc:  # a missing route or database blip; try again next beat
            print("relay_heartbeat_failed", type(exc).__name__, flush=True)
        time.sleep(10)


def relay_base_url(db=None):
    """The configured relay address, else the one a running relay reported in the last minute."""
    if settings.receiver_base_url:
        return settings.receiver_base_url
    if db is None:
        with SessionLocal() as fresh:
            return relay_base_url(fresh)
    row = db.get(Integration, HEARTBEAT)
    if not row or not row.updated_at or row.updated_at < utcnow() - timedelta(seconds=60):
        return ""
    return (row.config or {}).get("base_url") or ""


# ---------- one song's audio file ----------
def audio_file(item_id, suffix=".media"):
    """The prepared file for an item, never a link or a live stream pipe (those play on the server).
    `.dlna` is its MP3 copy for renderers that cannot play the original format."""
    try:
        path = settings.runtime_root / "audio" / (str(UUID(item_id)) + suffix)
        info = path.lstat()
    except (ValueError, OSError):
        raise HTTPException(404, "This song's audio is not ready yet") from None
    if stat.S_ISFIFO(info.st_mode):
        raise HTTPException(409, SERVER_ONLY)
    if not stat.S_ISREG(info.st_mode):
        raise HTTPException(404, "This song's audio is not ready yet")
    return path


def audio_type(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        head = stream.read(12)
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:
        return "audio/aac"
    if head.startswith(b"ID3") or len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:
        return "audio/mpeg"
    return "application/octet-stream"


def audio_response(path, request, chunks_guard=None):
    from .cinema_delivery import local_stream

    try:
        status, headers, chunks = local_stream(
            path, request.headers.get("range"), head=request.method == "HEAD"
        )
    except MediaError:
        raise HTTPException(416, "That part of the song is unavailable") from None
    except OSError:
        raise HTTPException(404, "This song's audio is not ready yet") from None
    return StreamingResponse(
        chunks_guard(chunks) if chunks_guard else chunks,
        status_code=status,
        media_type=audio_type(path),
        headers={**headers, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


def current_and_next(db):
    q = db.get(QueueState, 1)
    if not q:
        return set()
    rows = list(db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))))
    return {q.current_id, *(row.id for row in pending_order(db, q, rows)[:1])} - {None}


def station_stream(source_url, allow_http=False):
    """A radio's own stream for a follower: https only for a phone (a secure page cannot play
    http); a speaker or TV fetches plain http anyway (`allow_http`)."""
    from .radio import cached_station

    try:
        station = cached_station(source_url[6:], int(time.time() // 3600))
    except (ValueError, TypeError, KeyError):
        return None, None
    url = station.get("url") or ""
    mime = {"AAC": "audio/aac", "AAC+": "audio/aac", "OGG": "audio/ogg"}.get(
        station.get("codec"), "audio/mpeg"
    )
    secure = url.startswith("https://") or (allow_http and url.startswith("http://"))
    return (url, mime) if secure else (None, None)


@router.api_route("/audio/{item_id}", methods=["GET", "HEAD"])
def follower_audio(item_id: str, request: Request, actor=Depends(require_actor), db=Depends(get_db)):
    """Speaker mode: the playing or next song for a resident's phone or computer."""
    require_permission(actor, "music.read")
    item = db.get(QueueItem, item_id) if item_id in current_and_next(db) else None
    if not item:
        raise HTTPException(404, "Only the song playing now or next can play here")
    source = item.source_url
    db.rollback()
    if source.startswith("radio:"):
        url, _ = station_stream(source)
        if not url:
            raise HTTPException(409, RADIO_SERVER_ONLY)
        return RedirectResponse(url, status_code=307)
    return audio_response(audio_file(item_id), request)


# ---------- the Cast relay (dedicated LAN listener, relay.py) ----------
def grant_valid(bind, token_hash):
    """Re-checked while the device reads: the song is still current and the device still chosen."""
    with Session(bind) as db:
        choice = output_choice(db)
        grant = choice.get("grant") or {}
        q = db.get(QueueState, 1)
        return (
            grant.get("token_hash") == token_hash
            and grant.get("expires_at", 0) > time.time()
            and grant.get("device_id") == choice.get("device_id")
            and q is not None
            and q.current_id == grant.get("item_id")
        )


@relay_router.api_route("/{token}/audio", methods=["GET", "HEAD"])
def cast_audio(token: str, request: Request, db=Depends(get_db)):
    from .cinema_delivery import revocable_chunks

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    grant = output_choice(db).get("grant") or {}
    if (
        not grant_valid(db.get_bind(), token_hash)
        or not request.client
        or request.client.host != grant.get("address")
    ):
        raise HTTPException(404, "Media unavailable")
    try:
        path = audio_file(grant["item_id"], grant.get("suffix", ".media"))
    except HTTPException:
        raise HTTPException(404, "Media unavailable") from None
    response = audio_response(
        path, request, lambda chunks: revocable_chunks(chunks, db.get_bind(), token_hash, grant_valid)
    )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "Content-Range,Accept-Ranges,Content-Length"
    # DLNA renderers (Samsung, LG…) want to be told the file is seekable, streamed audio.
    response.headers["transferMode.dlna.org"] = "Streaming"
    response.headers["contentFeatures.dlna.org"] = (
        "DLNA.ORG_OP=01;DLNA.ORG_FLAGS=01700000000000000000000000000000"
    )
    return response


# ---------- the network speaker follower (worker process) ----------
DRIFT = 2.0
OBSERVE_EVERY = 15
# What the device was last told. Only the worker's single follower thread touches it.
FOLLOW: dict = {}
# What every DLNA renderer plays; anything else (YouTube's WebM/Opus) gets an MP3 copy.
DLNA_READY = {"audio/mpeg", "audio/mp4", "audio/aac", "audio/flac", "audio/wav"}


def mp3_copy(path):
    """<id>.dlna beside <id>.media: one song at a time, made once (a few seconds per song)."""
    target = path.with_suffix(".dlna")
    if not target.exists():
        for old in path.parent.glob("*.dlna*"):  # the last song's copy, or a failed one
            old.unlink(missing_ok=True)
        partial = path.with_suffix(".dlna.part")
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path), "-vn", "-c:a", "libmp3lame"]
            + ["-q:a", "2", "-f", "mp3", str(partial)],
            check=True,
            timeout=300,
        )
        os.replace(partial, target)
    return target


def cast_media(db, device, item):
    """(url, mime, live) for the device, or None when this song plays on the server only."""
    if item.source_url.startswith("radio:"):
        url, mime = station_stream(item.source_url, allow_http=True)
        return (url, mime, True) if url else None
    try:
        path = audio_file(item.id)
    except HTTPException:
        return None
    base = relay_base_url(db)
    if not base:
        return None
    suffix = ".media"
    if device.adapter == "dlna" and audio_type(path) not in DLNA_READY:
        try:
            path, suffix = mp3_copy(path), ".dlna"
        except (OSError, subprocess.SubprocessError) as exc:
            print("music_dlna_copy_failed", type(exc).__name__, flush=True)
            return None
    token = secrets.token_urlsafe(32)
    duration = item.metadata_json.get("duration") or 0
    save_output_choice(
        db,
        grant={
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "item_id": item.id,
            "device_id": device.id,
            "address": device.address,
            "expires_at": time.time() + max(3600, duration + 3600),
            "suffix": suffix,
        },
    )
    db.commit()
    return base + "/receiver/music/" + token + "/audio", audio_type(path), False


def transport(adapter):
    """(load, control, observe) for Cast or DLNA: the same contract, so one follower serves both."""
    if adapter == "dlna":
        from . import dlna

        return dlna.dlna_music, dlna.dlna_control, dlna.dlna_observe
    from . import cinema_cast

    return cinema_cast.cast_music, cinema_cast.cast_control, cinema_cast.cast_observe


def device_volume(adapter, address):
    """The speaker or TV's own volume (0–100), or None when it won't say."""
    if adapter == "dlna":
        from .dlna import dlna_volume

        return dlna_volume(address)
    from .cinema_cast import cast_observe

    try:
        return cast_observe(address).get("volume")
    except Exception:
        return None


def follow_cast():
    """One step: bring the chosen speaker or TV in line with the house clock. Never raises: a
    missing speaker is retried every 30 s without holding up the music worker."""
    now = time.monotonic()
    if now < FOLLOW.get("retry_at", 0):
        return
    try:
        with SessionLocal() as db:
            step(db, now)
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print("music_cast_failed", code, flush=True)
        FOLLOW.clear()
        FOLLOW["retry_at"] = now + 30
        trouble(code)


def trouble(code):
    """Tell Listen why the chosen speaker is silent (None: it plays). Best effort."""
    try:
        with SessionLocal() as db:
            if output_choice(db).get("problem") != code:
                save_output_choice(db, problem=code)
                db.commit()
    except Exception:
        pass


def step(db, now):
    from .cinema_models import CinemaDevice
    from .dlna import target

    device_id = output_choice(db).get("device_id")
    device = db.get(CinemaDevice, device_id) if device_id else None
    adapter = device.adapter if device and device.adapter in NETWORK_ADAPTERS else None
    # What the transport calls the device: its address, or a DLNA renderer's description URL.
    port = (device.capabilities or {}).get("port") if adapter == "cast" else None
    cast = f"{device.address}:{port}" if port and port != 8009 else device.address if device else None
    address = (target(device) if adapter == "dlna" else cast) if adapter else None
    film = bool(device and device.owner_workflow)
    q = db.get(QueueState, 1)
    item = db.get(QueueItem, q.current_id) if q and q.current_id else None
    volume = q.volume if q else None
    if FOLLOW.get("address") and ((FOLLOW["address"], FOLLOW["adapter"]) != (address, adapter) or film):
        if not film and FOLLOW.get("url"):  # a film took the screen: leave it alone
            transport(FOLLOW["adapter"])[1](FOLLOW["address"], "stop", 0)
        FOLLOW.clear()
    if not address or film:
        return
    load, control, observe = transport(adapter)
    clock = bridge("state")
    audible = (
        clock.get("status") == "observed"
        and clock.get("idle") is False
        and item is not None
        and clock.get("item_id") == item.id
    )
    if not audible:
        if FOLLOW.get("url"):
            control(address, "stop", 0)
        FOLLOW.update(address=address, adapter=adapter, item=None, url=None)
        return
    paused, position = bool(clock.get("paused")), float(clock.get("position") or 0)
    if FOLLOW.get("item") != item.id:
        media = cast_media(db, device, item)
        FOLLOW.update(address=address, adapter=adapter, item=item.id, url=None, volume=volume)
        if media is None:  # plays on the server only; the device stays on the last song, stopped
            trouble("SERVER_ONLY_SONG")
            return
        url, mime, live = media
        # Making a DLNA copy takes seconds: start where the house is now, not where it was.
        clock, now = bridge("state"), time.monotonic()
        if clock.get("item_id") == item.id:
            paused, position = bool(clock.get("paused")), float(clock.get("position") or 0)
        load(address, url, mime, 0 if live else position, paused, live, item.title)
        FOLLOW.update(url=url, live=live, paused=paused, position=position, at=now, observed=now)
        FOLLOW.pop("level", None)  # the device's own volume: read again before the next change
        trouble(None)
        return
    if not FOLLOW.get("url"):
        return
    if paused != FOLLOW["paused"]:
        control(address, "pause" if paused else "resume", 0)
    if volume is not None and volume != FOLLOW.get("volume"):
        # Moved from the device's own level, never jumped to the house's: a TV at 15 goes to
        # 20 when the house slider moves up 5, not to 90.
        if FOLLOW.get("level") is None:
            FOLLOW["level"] = device_volume(adapter, address)
        if FOLLOW["level"] is not None and FOLLOW.get("volume") is not None:
            FOLLOW["level"] = max(0, min(100, FOLLOW["level"] + volume - FOLLOW["volume"]))
            control(address, "volume", FOLLOW["level"])
    expected = FOLLOW["position"] + (0 if FOLLOW["paused"] else now - FOLLOW["at"])
    if not FOLLOW["live"] and abs(position - expected) > DRIFT:
        control(address, "seek", position)  # someone moved the song on the house player
        FOLLOW["observed"] = now
    elif not FOLLOW["live"] and now - FOLLOW["observed"] > OBSERVE_EVERY:
        seen = observe(address)
        FOLLOW["observed"] = now
        # An empty track address says nothing (some players forget it): only another song counts.
        if seen.get("item_id") not in (None, hashlib.sha256(FOLLOW["url"].encode()).hexdigest()):
            FOLLOW["url"] = None  # someone else is using the device: stop following this song
        elif seen.get("position") is not None and abs(seen["position"] - position) > DRIFT:
            control(address, "seek", position)
    FOLLOW.update(paused=paused, volume=volume, position=position, at=now)
