from . import ipc
import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, urlencode
from typing import Literal, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import and_, select, func, or_, Index, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .auth import Input, require_actor, require_permission
from .db import Base, new_id, utcnow, get_db
from .models import Job, Operation, Record, User, Integration
from .events import emit
from .config import settings

router = APIRouter(prefix="/music", tags=["music"])
STALE_MESSAGE = "The queue changed meanwhile; read it again and retry."


class QueueState(Base):
    __tablename__ = "music_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    desired: Mapped[str] = mapped_column(String(16), default="paused")
    volume: Mapped[int] = mapped_column(Integer, default=90)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    sleep_at: Mapped[object] = mapped_column(DateTime, nullable=True)


class QueueItem(Base):
    __tablename__ = "music_items"
    __table_args__ = (
        Index("ix_music_source_latest", "source_url", "created_at", mysql_length={"source_url": 191}),
        Index("ix_music_queue", "status", "position"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500), default="Resolving source…")
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending_metadata")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


# Paid streaming services: nothing here can play their links.
STREAMING_HOSTS = (
    "spotify.com",
    "spotify.link",
    "deezer.com",
    "deezer.page.link",
    "music.apple.com",
    "tidal.com",
)


def streaming_link(u):
    host = u.hostname or ""
    if any(host == h or host.endswith("." + h) for h in STREAMING_HOSTS):
        raise HTTPException(
            422,
            "Spotify, Deezer, Apple Music and Tidal links can't play here: type the song and artist instead.",
        )


def canonical_source(value):
    try:
        if isinstance(value, str) and value.startswith("radio:"):
            from uuid import UUID

            return "radio:" + str(UUID(value[6:]))
        u = urlparse(value)
        streaming_link(u)
        if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
            raise ValueError()
        host = (u.hostname or "").lower()
        if host == "youtu.be":
            video = u.path.strip("/")
        elif host in {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"}:
            video = (
                parse_qs(u.query).get("v", [""])[0]
                if u.path == "/watch"
                else u.path.split("/")[2]
                if re.fullmatch(r"/(shorts|live|embed)/[A-Za-z0-9_-]{11}/?", u.path)
                else ""
            )
        elif host == "on.soundcloud.com":
            if not re.fullmatch(r"/[A-Za-z0-9_-]{4,200}/?", u.path):
                raise ValueError()
            return "https://on.soundcloud.com" + u.path.rstrip("/")
        elif host in {"soundcloud.com", "www.soundcloud.com"}:
            parts = u.path.strip("/").split("/")
            if len(parts) != 2 or "sets" in parts or any(not p for p in parts):
                raise ValueError()
            return "https://soundcloud.com/" + "/".join(parts).lower()
        else:
            raise ValueError()
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ValueError()
        return "https://www.youtube.com/watch?" + urlencode({"v": video})
    except (ValueError, TypeError):
        raise HTTPException(422, "Use a supported HTTPS YouTube video or SoundCloud track URL")


def playlist_source(value):
    import re

    u = urlparse(value)
    streaming_link(u)
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
        raise HTTPException(422, "Invalid playlist URL")
    if u.hostname in {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"}:
        identity = parse_qs(u.query).get("list", [""])[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{10,100}", identity):
            return "https://www.youtube.com/playlist?" + urlencode({"list": identity})
    if u.hostname == "music.youtube.com" and re.fullmatch(r"/browse/MPREb_[A-Za-z0-9_-]{5,60}", u.path):
        return "https://music.youtube.com" + u.path  # an album on YouTube Music
    if u.hostname in {"soundcloud.com", "www.soundcloud.com"} and re.fullmatch(
        r"/[\w-]+/sets/[\w-]+/?", u.path
    ):
        return "https://soundcloud.com" + u.path
    raise HTTPException(422, "Use a supported YouTube playlist or SoundCloud set URL")


def queue(db):
    row = db.scalar(select(QueueState).where(QueueState.id == 1).with_for_update())
    if not row:
        raise HTTPException(503, "Music queue requires initialization")
    return row


def read_queue(db):
    """The queue for reading: no row lock (the worker holds that one while it waits on the
    player, and every client reads this every few seconds)."""
    db.commit()  # the latest state, not this transaction's older snapshot
    row = db.scalar(select(QueueState).where(QueueState.id == 1).execution_options(populate_existing=True))
    if not row:
        raise HTTPException(503, "Music queue requires initialization")
    return row


def item_json(item):
    return {
        "id": item.id,
        "title": item.title,
        "owner_id": item.owner_id,
        "source_url": item.source_url,
        "position": item.position,
        "status": item.status,
        "error_code": item.error_code,
        "error_message": {
            "YOUTUBE_SIGN_IN_REQUIRED": "YouTube is blocking this server for now (a bot check); the song itself is fine. Songs already at home still play.",
            "YOUTUBE_RATE_LIMITED": "YouTube is slowing this server down for a while. Wait a bit; songs already at home still play.",
            "YOUTUBE_AGE_RESTRICTED": "Age-restricted: YouTube plays it only to signed-in adults. Try another version of the song.",
            "SOURCE_REGION_BLOCKED": "Blocked in this country. Try another version of the song.",
            "SOURCE_REMOVED": "This video was removed or made private.",
            "TRACK_TOO_LONG": "Tracks longer than four hours cannot play here.",
            "PLAYBACK_INTERRUPTED": "The song stopped before its end. Add it again to retry.",
        }.get(item.error_code),
        "downloaded": bool(item.metadata_json.get("downloaded")),
        "retained": bool(item.metadata_json.get("retained")),
        "download_state": item.metadata_json.get("download_state"),
        "retention_error": item.metadata_json.get("retention_error"),
        "duration": item.metadata_json.get("duration"),
        "requires_approval": item.status == "awaiting_confirmation",
        "is_live": bool(item.metadata_json.get("is_live")),
        "uploader": item.metadata_json.get("uploader"),
        "art": "/api/v1/music/art/queue/" + item.id if item.metadata_json.get("thumbnail") else None,
        "live_until": item.metadata_json.get("live_authorized_until"),
        "pinned": bool(item.metadata_json.get("pinned_at")),
        "streamed": bool(item.metadata_json.get("long_stream")),
        "now_title": item.metadata_json.get("now_title"),  # what a radio says is on air
        "genre": item.metadata_json.get("genre"),
        "auto": item.metadata_json.get("auto"),  # queued by auto play, not by a person
    }


def bridge(command, **kwargs):
    return ipc.request(
        settings.audio_socket,
        {"command": command, **kwargs},
        # A load measures the song's loudness first unless the bridge did it ahead (it measures
        # staged songs in the background); a long unmeasured song took more than 3 s and was
        # marked failed while the speakers played it. ffmpeg is capped at 60 s.
        timeout=65 if command == "load" else 3,
        failure={"status": "unavailable", "code": "AUDIO_BRIDGE_UNAVAILABLE"},
    )


@router.get("")
def state(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    q = read_queue(db)
    rows = db.scalars(
        select(QueueItem)
        .where(QueueItem.status.not_in(["removed", "completed", "skipped"]))
        # A failed song someone asked for stays in sight to retry or remove; auto play's own
        # failed picks are nobody's request, so they don't linger as "Up next".
        .where(or_(QueueItem.status != "failed", QueueItem.metadata_json["auto"].as_string().is_(None)))
        .order_by(QueueItem.position)
        .limit(500)
    ).all()
    current = [row for row in rows if row.id == q.current_id]
    ordered = pending_order(db, q, rows)
    rows = current + ordered
    from .house_settings import get_house_settings

    fair = get_house_settings(db)["music_round_robin"]
    # Whose turn: with fair rotation each person's n-th pending song plays in round n.
    rounds, turns = {}, {}
    for row in ordered:
        if row.metadata_json.get("pinned_at") or row.metadata_json.get("auto"):
            continue  # auto play's picks wait at the end, outside the rounds
        turns[row.owner_id] = turns.get(row.owner_id, 0) + 1
        rounds[row.id] = turns[row.owner_id]
    requesters = {
        identity: {"id": identity, "name": name, "avatar": (preferences or {}).get("avatar", "crest")}
        for identity, name, preferences in db.execute(
            select(User.id, User.name, User.preferences).where(User.id.in_({row.owner_id for row in rows}))
        )
    }
    # Who kept each song on the house (Listen offers them, or an admin, to delete it).
    from .music_downloads import identity as kept_id

    keys = {
        row.id: kept_id(row.source_url)
        for row in rows
        if row.source_url.startswith(("https://www.youtube.com/", "https://soundcloud.com/"))
    }
    keepers = dict(
        db.execute(
            select(Record.id, Record.owner_id).where(
                Record.id.in_(set(keys.values())),
                Record.kind == "music.download",
                Record.deleted_at.is_(None),
                Record.data["state"].as_string() == "ready",
            )
        ).all()
    )
    snapshot = {
        "version": q.version,
        "current_id": q.current_id,
        "desired": q.desired,
        "volume": q.volume,
        "sleep_at": q.sleep_at,
        "repeat_mode": repeat_mode(db),
        "items": [
            {
                **item_json(i),
                "requester": requesters.get(i.owner_id),
                "round": rounds.get(i.id) if fair else None,
                "kept_by": keepers.get(keys.get(i.id)),
            }
            for i in rows
        ],
        "fair": fair,
        "autoplay_on_add": q.desired != "playing" or not q.current_id,
        "veto_back_at": (back := veto_back_at(db, actor)) and back.isoformat() + "Z",
        "last_veto": last_veto(db),
    }
    db.rollback()  # give the connection back before the player bridge read
    snapshot["observation"] = bridge("state")
    observed_volume = snapshot["observation"].get("volume_target")
    if observed_volume is None:
        observed_volume = snapshot["observation"].get("volume")
    if snapshot["observation"].get("status") == "observed" and isinstance(observed_volume, (int, float)):
        snapshot["volume"] = round(max(0, min(100, observed_volume)))
    snapshot["physical_verified"] = bool(snapshot["observation"].get("physical_verified"))
    # Where the music comes out, so nobody listens to silence without being told.
    from .music_outputs import output_choice

    cast = output_choice(db).get("device_id")
    db.rollback()
    silent = (
        snapshot["observation"].get("resolved_output") in ("none", None)
        and snapshot["observation"].get("status") == "observed"
    )
    snapshot["plays_on"] = "cast" if cast else "nowhere" if silent else "computer"
    if cast:  # why the chosen speaker or TV is silent, if it is
        snapshot["output_problem"] = output_choice(db).get("problem")
    return snapshot


class Add(Input):
    source_url: str = Field(max_length=2048)
    start_position: float | None = Field(default=None, ge=0, le=14400)
    idempotency_key: str = Field(min_length=8, max_length=100)


ACTIVE_QUEUE_STATUSES = [
    "pending_metadata",
    "ready",
    "resolving",
    "playing",
    "paused",
    "awaiting_confirmation",
    "buffering",
]


def requested_start(source):
    url = urlparse(source)
    if (url.hostname or "").lower() not in {
        "youtu.be",
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }:
        return 0
    query = {**parse_qs(url.fragment), **parse_qs(url.query)}
    value = query.get("t", query.get("start", query.get("time_continue", ["0"])))[0]
    if re.fullmatch(r"\d+(?:s)?", value):
        seconds = int(value.rstrip("s"))
    else:
        match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", value)
        if not match or not any(match.groups()):
            raise HTTPException(422, "Invalid YouTube start time")
        seconds = sum(int(part or 0) * scale for part, scale in zip(match.groups(), [3600, 60, 1]))
    if seconds > 14400:
        raise HTTPException(422, "Start time must be within four hours")
    return seconds


def resolve_source_url(source):
    url = canonical_source(source)
    if url.startswith("https://on.soundcloud.com/"):
        from .worker import fetch

        result = fetch("canonical", url)
        if result.get("status") != "completed":
            raise HTTPException(
                422,
                {
                    "code": result.get("code", "SOURCE_LINK_UNRESOLVED"),
                    "message": "The SoundCloud share link could not be resolved. Try its full track URL.",
                },
            )
        url = canonical_source(result.get("source_url", ""))
        if not url.startswith("https://soundcloud.com/"):
            raise HTTPException(422, "SoundCloud share link did not identify a track")
    return url


def start_sleep_timer(db, q):
    if not q.sleep_at or q.sleep_at <= utcnow():
        from .house_settings import get_house_settings

        minutes = get_house_settings(db)["music_sleep_minutes"]
        q.sleep_at = utcnow() + timedelta(minutes=minutes) if minutes else None


def activate_added(db, q, added, pending):
    """An explicit request starts its new song when idle/paused; active playback continues.
    The songs not started land where fair turns put them."""
    started = start_added(db, q, added, pending)
    place_fairly(db, q, added)
    return started


def start_added(db, q, added, pending):
    if not added or q.desired == "playing" and q.current_id:
        return False
    previous = db.get(QueueItem, q.current_id) if q.current_id else None
    if previous and previous.id not in {item.id for item in added}:
        if previous.status in {"playing", "paused", "buffering", "resolving"}:
            previous.status = "ready"
        previous.metadata_json = {
            **previous.metadata_json,
            "resume_position": previous.metadata_json.get("last_position") or 0,
        }
    first_position = min([item.position for item in pending], default=0) - len(added)
    for index, item in enumerate(added):
        item.position = first_position + index
    q.current_id, q.desired, q.failures = added[0].id, "playing", 0
    start_sleep_timer(db, q)
    return True


def pending_order(db, q, rows):
    """What plays next: songs pinned "right after this one", then the queue's own order. Fair
    turns already decided where each song landed (`place_fairly`); anyone may move it since."""
    pending = [row for row in rows if row.id != q.current_id]
    pinned = sorted(
        (row for row in pending if row.metadata_json.get("pinned_at")),
        key=lambda row: row.metadata_json["pinned_at"],
    )
    return pinned + sorted(
        (row for row in pending if not row.metadata_json.get("pinned_at")), key=lambda row: row.position
    )


def fair_order(db, q, pending):
    """Stable per-user FIFO rounds, beginning after the current/last player's turn."""
    groups = {}
    for row in pending:
        groups.setdefault(row.owner_id, []).append(row)
    current = db.get(QueueItem, q.current_id) if q.current_id else None
    last_turn = dict(
        db.execute(
            select(Record.owner_id, func.max(Record.data["played_at"].as_string()))
            .where(Record.kind == "music.history", Record.owner_id.in_(groups))
            .group_by(Record.owner_id)
        ).all()
    )
    owners = sorted(
        groups,
        key=lambda owner: (
            owner == (current.owner_id if current else None),
            last_turn.get(owner) or "",
            groups[owner][0].position,
        ),
    )
    ordered = []
    while owners:
        for owner in owners:
            ordered.append(groups[owner].pop(0))
        owners = [owner for owner in owners if groups[owner]]
    return ordered


def waiting_line(db, q):
    """The queue after the current song, in order, without pinned songs."""
    rows = db.scalars(
        select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES)).order_by(QueueItem.position)
    ).all()
    return [row for row in pending_order(db, q, rows) if not row.metadata_json.get("pinned_at")]


def place_fairly(db, q, added):
    """New songs land where fair turns put them (each person's nth song in round n), without
    undoing anyone's moves: a fair order restricted to the songs already waiting is unchanged
    by one more song, so inserting at its fair index keeps a fair queue fair."""
    from .house_settings import get_house_settings

    fair = get_house_settings(db)["music_round_robin"]
    new = {item.id for item in added}
    waiting = [row for row in waiting_line(db, q) if row.id not in new]
    # Auto play's picks are nobody's request: they always wait behind every song someone asked
    # for, and take no one's turn.
    autos = [row for row in waiting if row.metadata_json.get("auto")]
    line = [row for row in waiting if not row.metadata_json.get("auto")]
    for item in added:
        if item.id == q.current_id or item.metadata_json.get("pinned_at"):
            continue
        if item.metadata_json.get("auto"):
            autos.append(item)
        elif fair:
            line.insert(fair_order(db, q, line + [item]).index(item), item)
        else:
            line.append(item)
    for position, row in enumerate(line + autos):
        row.position = position


@router.post("/queue")
def enqueue(body: Add, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    request_source = canonical_source(body.source_url)
    position = body.start_position if body.start_position is not None else requested_start(body.source_url)
    if request_source.startswith("radio:") and position:
        raise HTTPException(422, "Live radio cannot start at a seek position")
    old = db.scalar(
        select(Operation).where(
            Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
        )
    )
    if old:
        if (
            old.kind != "music.add"
            or request_source not in {old.data.get("request_source"), old.data.get("source_url")}
            or old.data.get("start_position", 0) != position
        ):
            raise HTTPException(409, "Idempotency key already used for another action")
        return {"status": old.state, "operation_id": old.id, **old.result}
    db.rollback()  # Share-link redirects resolve without holding a queue/database lock.
    url = resolve_source_url(request_source)
    if request_source != url:
        from .auth import refresh_actor

        actor = refresh_actor(db, actor)
        require_permission(actor, "music.queue")
    q = queue(db)
    old = db.scalar(
        select(Operation).where(
            Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
        )
    )
    if old:
        if (
            old.kind != "music.add"
            or old.data.get("source_url") != url
            or old.data.get("start_position", 0) != position
        ):
            raise HTTPException(409, "Idempotency key already used for another action")
        return {"status": old.state, "operation_id": old.id, **old.result}
    pending = db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))).all()
    if len(pending) >= 500 or (actor.role == "guest" and sum(x.owner_id == actor.id for x in pending) >= 10):
        raise HTTPException(409, "Queue limit reached")
    q.version += 1
    item = QueueItem(
        owner_id=actor.id,
        source_url=url,
        position=max([entry.position for entry in pending], default=0) + 1,
        metadata_json={
            "session_hash": actor.session_hash,
            "resume_position": position,
            "requested_start": position,
            # Choosing a radio station is the request to play it; other live streams ask first.
            "live_approved": url.startswith("radio:"),
        },
    )
    db.add(item)
    db.flush()
    replaced = replace_radio(db, q, item)
    auto = replaced or activate_added(db, q, [item], pending)
    operation = Operation(
        actor_id=actor.id,
        kind="music.add",
        state="accepted",
        data={"source_url": url, "request_source": request_source, "start_position": position},
        idempotency_key=body.idempotency_key,
        result={"item_id": item.id, "autoplay_requested": bool(auto)},
    )
    db.add(operation)
    db.add(
        Job(
            logical_key="metadata:" + item.id,
            kind="music.metadata",
            actor_id=actor.id,
            payload={"item_id": item.id, "session_hash": actor.session_hash},
        )
    )
    emit(db, "music.queue_changed", {"version": q.version})
    emit(db, "audit.music_add", {"item_id": item.id}, actor.id)
    db.commit()
    if replaced:
        from .worker import fetch

        fetch("live_stop", item_id=replaced)
    return {"status": "accepted", "operation_id": operation.id, **operation.result}


def replace_radio(db, q, item):
    """A station chosen while a station plays takes over at once; songs still queue. Returns
    the replaced station's item id."""
    current = db.get(QueueItem, q.current_id) if q.current_id else None
    if not (
        item.source_url.startswith("radio:")
        and current
        and current.source_url.startswith("radio:")
        # A station still connecting counts: picking another one means "no, this one".
        and current.status not in {"completed", "failed", "removed", "skipped"}
    ):
        return None
    current.status = "completed"
    current.metadata_json = {**current.metadata_json, "ended_reason": "replaced_by_station"}
    item.position = min(current.position, item.position) - 1
    q.current_id, q.desired, q.failures = item.id, "playing", 0
    start_sleep_timer(db, q)
    return current.id


class Reorder(Input):
    expected_version: int
    before_item_id: str | None = None


@router.patch("/queue/{item_id}")
def reorder(item_id: str, body: Reorder, actor=Depends(require_actor), db=Depends(get_db)):
    """Anyone in the queue may move any waiting song: fair turns only decide where it lands."""
    require_permission(actor, "music.queue")
    q = queue(db)
    if q.version != body.expected_version:
        raise HTTPException(409, {"code": "STALE_QUEUE", "message": STALE_MESSAGE, "version": q.version})
    items = db.scalars(
        select(QueueItem)
        .where(
            QueueItem.status.in_(["ready", "pending_metadata"]),
            QueueItem.id != q.current_id if q.current_id else True,
        )
        .order_by(QueueItem.position)
    ).all()
    item = next((x for x in items if x.id == item_id), None)
    if not item:
        raise HTTPException(409, "Only pending items can move")
    items.remove(item)
    before = next((i for i, x in enumerate(items) if x.id == body.before_item_id), None)
    if body.before_item_id and before is None:
        raise HTTPException(409, "Target is no longer pending")
    items.insert(before if before is not None else len(items), item)
    for position, row in enumerate(items):
        row.position = position
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": "completed", "version": q.version}


@router.delete("/queue/{item_id}")
def remove(
    item_id: str, expected_version: int | None = None, actor=Depends(require_actor), db=Depends(get_db)
):
    """One song out, named by its id: no queue version to match (removing several quickly
    would refuse every one after the first). Removing it twice is fine."""
    require_permission(actor, "music.queue")
    q = queue(db)
    item = db.get(QueueItem, item_id)
    if not item or (item.owner_id != actor.id and actor.role != "admin"):
        raise HTTPException(404, "Own queue item not found")
    if item.status == "removed":
        return {"status": "completed", "version": q.version}
    if item.status not in {"ready", "pending_metadata", "failed", "awaiting_confirmation"}:
        raise HTTPException(409, "Use playback controls for the current item")
    item.status = "removed"
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    from .worker import fetch

    fetch("cancel_download", item_id=item_id)
    return {"status": "completed", "version": q.version}


class QueueVersion(Input):
    expected_version: int


def own_pending(db, q, owner_id):
    return db.scalars(
        select(QueueItem)
        .where(
            QueueItem.owner_id == owner_id,
            QueueItem.status.in_(["ready", "pending_metadata"]),
            QueueItem.id != q.current_id if q.current_id else True,
        )
        .order_by(QueueItem.position)
    ).all()


@router.post("/queue/{item_id}/next")
def play_next(item_id: str, body: QueueVersion, actor=Depends(require_actor), db=Depends(get_db)):
    """Your song becomes your next one. An administrator can also pin anyone's song to play
    straight after the current one."""
    require_permission(actor, "music.queue")
    q = queue(db)
    if q.version != body.expected_version:
        raise HTTPException(409, {"code": "STALE_QUEUE", "message": STALE_MESSAGE, "version": q.version})
    item = db.get(QueueItem, item_id)
    if not item or item.id == q.current_id or item.status not in {"ready", "pending_metadata"}:
        raise HTTPException(409, "Only a waiting song can move")
    if item.owner_id == actor.id and actor.role != "admin":
        # Takes the place of your first waiting song; everyone else's songs stay where they are.
        line = waiting_line(db, q)
        first = next(row for row in line if row.owner_id == actor.id)
        line.remove(item)
        line.insert(line.index(first) if first is not item else 0, item)
        for position, row in enumerate(line):
            row.position = position
        result = "first_of_yours"
    elif actor.role == "admin":
        item.metadata_json = {**item.metadata_json, "pinned_at": utcnow().isoformat()}
        result = "pinned_next"
    else:
        raise HTTPException(403, "You can only move your own songs")
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": "completed", "result": result, "version": q.version}


@router.post("/queue/shuffle-mine")
def shuffle_mine(body: QueueVersion, actor=Depends(require_actor), db=Depends(get_db)):
    """Shuffle only your own waiting songs; everyone else's order and turns are unchanged."""
    import random

    require_permission(actor, "music.queue")
    q = queue(db)
    if q.version != body.expected_version:
        raise HTTPException(409, {"code": "STALE_QUEUE", "message": STALE_MESSAGE, "version": q.version})
    mine = own_pending(db, q, actor.id)
    positions = [row.position for row in mine]
    random.shuffle(mine)
    for row, position in zip(mine, positions):
        row.position = position
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": "completed", "shuffled": len(mine), "version": q.version}


VETO_RELOAD = timedelta(hours=3)


def veto_back_at(db, actor):
    """When this person's veto is usable again (None: now)."""
    last = db.scalar(
        select(func.max(Record.created_at)).where(Record.kind == "music.veto", Record.owner_id == actor.id)
    )
    return last + VETO_RELOAD if last and last + VETO_RELOAD > utcnow() else None


def last_veto(db):
    """The latest veto of the past ten minutes, for everyone to see who used theirs on what."""
    row = db.scalar(
        select(Record)
        .where(Record.kind == "music.veto", Record.created_at > utcnow() - timedelta(minutes=10))
        .order_by(Record.created_at.desc())
        .limit(1)
    )
    if not row:
        return None
    name = db.scalar(select(User.name).where(User.id == row.owner_id))
    return {"by": name, "title": row.data.get("title"), "at": row.created_at.isoformat() + "Z"}


@router.post("/queue/{item_id}/veto")
def veto(item_id: str, body: QueueVersion, actor=Depends(require_actor), db=Depends(get_db)):
    """Everyone has one veto, back three hours after use: it skips someone else's song that is
    playing, or takes it out of the queue if it is waiting."""
    require_permission(actor, "music.queue")
    q = queue(db)
    if q.version != body.expected_version:
        raise HTTPException(409, {"code": "STALE_QUEUE", "message": STALE_MESSAGE, "version": q.version})
    item = db.get(QueueItem, item_id)
    if not item or item.status not in {*ACTIVE_QUEUE_STATUSES, "failed"}:
        raise HTTPException(409, "This song is no longer in the queue")
    if item.owner_id == actor.id:
        raise HTTPException(409, "Remove your own song instead")
    if back := veto_back_at(db, actor):
        raise HTTPException(409, {"code": "VETO_RELOADING", "available_at": back.isoformat() + "Z"})
    db.add(Record(kind="music.veto", owner_id=actor.id, data={"item_id": item.id, "title": item.title}))
    item.metadata_json = {**item.metadata_json, "vetoed_by": actor.name}
    if item.id == q.current_id:
        control_effect(db, actor, q, "skip", None)
        result = "skipped"
    else:
        item.status = "removed"
        q.version += 1
        result = "removed"
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    if result == "removed":
        from .worker import fetch

        fetch("cancel_download", item_id=item_id)
    return {"status": "completed", "result": result, "version": q.version}


ART_HOSTS = (
    ".ytimg.com",
    ".ggpht.com",
    ".googleusercontent.com",
    ".sndcdn.com",
    ".bcbits.com",
    ".dzcdn.net",  # Deezer album covers, for songs recorded without a still (music_catalog)
)


@router.get("/art/{kind}/{identity}")
async def art(
    kind: Literal["queue", "candidate"], identity: str, actor=Depends(require_actor), db=Depends(get_db)
):
    """Track artwork through the same sanitising image cache as film posters (small JPEG)."""
    from .cinema import image_response

    require_permission(actor, "music.read")
    url, is_radio = None, False
    if kind == "queue":
        item = db.get(QueueItem, identity)
        if item:
            url, is_radio = item.metadata_json.get("thumbnail"), item.source_url.startswith("radio:")
    else:
        record = db.get(Record, identity)
        if record and record.kind == "music_candidate" and record.owner_id == actor.id:
            url = record.data.get("thumbnail")
    db.close()  # one quick read; never hold a connection while an image is fetched
    host = urlparse(url or "").hostname or ""
    # Station logos live anywhere; everything else only on the known artwork hosts.
    if not url or not url.startswith("https://") or not (is_radio or host.endswith(ART_HOSTS)):
        raise HTTPException(404, "No artwork")
    return await image_response(url, 86400)


def repeat_mode(db):
    row = db.get(Integration, "music_playback")
    return (row.config or {}).get("repeat_mode", "off") if row else "off"


def complete_track(db, q, item):
    """Repeat only a naturally finished song; skip and clear never call this."""
    mode = repeat_mode(db)
    if mode in {"one", "queue"} and not item.metadata_json.get("is_live"):
        item.status = "ready"
        item.metadata_json = {**item.metadata_json, "resume_position": 0, "history_recorded": False}
        if mode == "queue":
            last = (
                db.scalar(
                    select(func.max(QueueItem.position)).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))
                )
                or 0
            )
            item.position, q.current_id = last + 1, None
        q.version += 1
        emit(db, "music.queue_changed", {"version": q.version})
    else:
        item.status, q.current_id = "completed", None


class Control(Input):
    action: Literal[
        "play", "pause", "stop", "seek", "volume", "mute", "skip", "previous", "clear", "sleep", "repeat"
    ]
    value: Annotated[float, Field(ge=0, le=86400)] | Literal["off", "one", "queue"] | None = None
    expected_version: int
    idempotency_key: str = Field(min_length=8, max_length=100)

    @model_validator(mode="after")
    def check_value(self):
        if self.action == "repeat":
            if self.value not in {"off", "one", "queue"}:
                raise ValueError("Choose repeat off, one, or queue")
        elif isinstance(self.value, str):
            raise ValueError("This control requires a numeric value")
        return self


def control_effect(db, actor, q, action, value):
    target = q.current_id
    if action in {"play", "pause"}:
        if action == "play" and not settings.audio_enabled:
            raise HTTPException(409, "Select an available speaker output and enable music in Control Room")
        q.desired = "playing" if action == "play" else "paused"
    elif action == "skip":
        # A burst of presses arrives as one skip of `value` songs (the page gathers them): all
        # are skipped at once, the song after them is current straight away, and only that one
        # is loaded (the worker stops the playing one and cancels the skipped ones' downloads).
        current = db.get(QueueItem, q.current_id) if q.current_id else None
        ready = list(db.scalars(select(QueueItem).where(QueueItem.status == "ready")))
        line = ([current] if current and current.status in ACTIVE_QUEUE_STATUSES else []) + pending_order(
            db, q, ready
        )
        if current is None and q.desired != "playing":
            line = []  # from silence, a skip starts the next song
        skipped = line[: min(50, max(1, int(value or 1)))]
        for row in skipped:
            row.status = "skipped"
        if skipped:
            target = skipped[0].id
            q.current_id = line[len(skipped)].id if len(line) > len(skipped) else None
        q.desired = "playing"
    elif action == "stop":
        # Release the speakers; Play resumes this song where it stopped.
        q.desired = "paused"
        current = db.get(QueueItem, q.current_id) if q.current_id else None
        if current and current.status in {"playing", "paused", "buffering", "resolving"}:
            position = current.metadata_json.get("last_position") or 0
            current.status = "ready"
            current.metadata_json = {**current.metadata_json, "resume_position": position}
    elif action == "previous":
        current = db.get(QueueItem, q.current_id) if q.current_id else None
        # Playing a song moves it to the top of history, so each step back remembers where it
        # left off (`back_before`); without it, Previous twice would swap between two songs.
        before = (current.metadata_json.get("back_before") if current else None) or None
        prior = db.scalar(
            select(Record)
            .where(
                Record.kind == "music.history",
                Record.deleted_at.is_(None),
                ~Record.data["source_url"].as_string().like("houseos-file:%"),
                ~Record.data["source_url"].as_string().like("radio:%"),
                Record.data["source_url"].as_string() != (current.source_url if current else ""),
                *([Record.updated_at < datetime.fromisoformat(before)] if before else []),
            )
            .order_by(Record.updated_at.desc(), Record.data["played_at"].as_string().desc())
            .limit(1)
        )
        if not prior:
            raise HTTPException(409, "No previous public track is available")
        source = canonical_source(prior.data["source_url"])
        if source.startswith("radio:"):
            raise HTTPException(409, "Previous history is live radio; choose a song from listening history")
        pending = list(db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))))
        if len(pending) >= 500:
            raise HTTPException(409, "Queue limit reached")
        metadata = source_metadata(db, [source]).get(source, {})
        item = QueueItem(
            owner_id=actor.id,
            source_url=source,
            title=metadata.get("title", "Resolving source…"),
            position=0,
            metadata_json={"session_hash": actor.session_hash, "back_before": prior.updated_at.isoformat()},
        )
        db.add(item)
        db.flush()
        db.add(
            Job(
                logical_key="metadata:" + item.id,
                kind="music.metadata",
                actor_id=actor.id,
                payload={"item_id": item.id, "session_hash": actor.session_hash},
            )
        )
        q.desired = "paused"
        activate_added(db, q, [item], pending)
    elif action == "repeat":
        # Locked: auto play keeps its plan in the same row; an unlocked write could undo it.
        row = db.get(Integration, "music_playback", with_for_update=True)
        if row is None:
            row = Integration(name="music_playback")
            db.add(row)
        row.config = {**(row.config or {}), "repeat_mode": value}
    elif action == "volume":
        from .house_settings import get_house_settings

        q.volume = int(min(value or 0, get_house_settings(db)["music_volume_cap"]))
    elif action == "sleep":
        if value is not None and value > 1440:
            raise HTTPException(422, "Sleep timer is limited to 24 hours")
        q.sleep_at = utcnow() + timedelta(minutes=value or 0) if value else None
    elif action == "clear":
        q.desired, q.sleep_at = "paused", None
        for item in db.scalars(
            select(QueueItem).where(QueueItem.status.not_in(["removed", "completed", "skipped"]))
        ):
            item.status = "removed"
    if action in {"play", "skip"}:
        start_sleep_timer(db, q)
    q.version += 1
    op = Operation(
        actor_id=actor.id, kind="music.control", state="accepted", data={"action": action, "value": value}
    )
    db.add(op)
    db.flush()
    db.add(
        Job(
            logical_key="control:" + op.id,
            kind="music.control",
            actor_id=actor.id,
            payload={
                "operation_id": op.id,
                "action": action,
                "value": value,
                "current_id": target if action == "skip" else q.current_id,
                "session_hash": actor.session_hash,
            },
        )
    )
    emit(db, "music.queue_changed", {"version": q.version})
    return op


@router.post("/control")
def control(body: Control, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.control")
    q = queue(db)
    existing = db.scalar(
        select(Operation).where(
            Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
        )
    )
    if existing:
        if existing.data.get("action") != body.action or existing.data.get("value") != body.value:
            raise HTTPException(409, "Idempotency key already used for another action")
        return {"status": existing.state, "operation_id": existing.id}
    if body.action in {"seek", "previous", "clear"} and q.version != body.expected_version:
        raise HTTPException(409, "Queue changed; refresh")
    if body.action == "clear":
        op = Operation(
            actor_id=actor.id,
            kind="music.confirm",
            state="needs_confirmation",
            data=body.model_dump(),
            expires_at=utcnow() + timedelta(seconds=120),
            idempotency_key=body.idempotency_key,
        )
        db.add(op)
        db.commit()
        return {
            "status": "needs_confirmation",
            "confirmation_id": op.id,
            "preview": {"action": body.action, "value": body.value},
        }
    op = control_effect(db, actor, q, body.action, body.value)
    op.idempotency_key = body.idempotency_key
    db.commit()
    return {"status": "accepted", "operation_id": op.id}


@router.post("/confirm/{operation_id}")
def confirm(operation_id: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.control")
    q = queue(db)
    op = db.scalar(
        select(Operation)
        .where(Operation.id == operation_id, Operation.actor_id == actor.id)
        .with_for_update()
    )
    if not op or op.kind != "music.confirm" or op.state != "needs_confirmation" or op.expires_at <= utcnow():
        raise HTTPException(409, "Confirmation unavailable or expired")
    if op.data["expected_version"] != q.version:
        raise HTTPException(409, "Queue changed; prepare a new action")
    effect = control_effect(db, actor, q, op.data["action"], op.data["value"])
    op.state, op.result = "completed", {"operation_id": effect.id}
    db.commit()
    return {"status": "accepted", "operation_id": effect.id}


def history_key(source_url):
    return hashlib.sha256(("music.history:" + source_url).encode()).hexdigest()[:36]


def record_played(db, item, observation):
    """Called once only after the exact item is positively observed playing, under queue lock."""
    if (
        observation.get("status") != "observed"
        or observation.get("item_id") != item.id
        or observation.get("idle") is not False
        or observation.get("paused") is not False
        or item.metadata_json.get("history_recorded")
    ):
        return
    row = db.get(Record, history_key(item.source_url))
    meta = item.metadata_json
    known = row.data if row else {}
    data = {
        **{key: known[key] for key in ("evidence",) if key in known},  # genre evidence stays
        "source_url": item.source_url,
        "played_at": utcnow().isoformat() + "Z",
        "plays": ((known.get("plays") or 1) if row else 0) + 1,
        # A genre already worked out for this song (music_catalog) beats the first guess.
        "genre": (known.get("genre") if known.get("evidence") else None) or meta.get("genre") or "other",
        **({"artist": meta["artist"]} if meta.get("artist") else {}),
    }
    # One row per play: "played by", the house stats and the favourites all read it.
    db.add(
        Record(
            kind="music.play",
            owner_id=item.owner_id,
            visibility="house",
            data={
                "key": history_key(item.source_url),
                "item": item.id,  # its last position is the time heard (radio included)
                "genre": data["genre"],
                "duration": meta.get("duration"),
                **({"radio": True} if item.source_url.startswith("radio:") else {}),
            },
        )
    )
    if row:
        row.owner_id, row.data, row.updated_at = item.owner_id, data, utcnow()
        row.version += 1
    else:
        db.add(
            Record(
                id=history_key(item.source_url),
                kind="music.history",
                owner_id=item.owner_id,
                visibility="house",
                data=data,
            )
        )
    item.metadata_json = {**item.metadata_json, "history_recorded": True}
    emit(db, "music.history_changed", {"source_id": history_key(item.source_url)})


def saved_records(db, actor):
    return list(
        db.scalars(
            select(Record)
            .where(Record.kind == "saved_track", Record.owner_id == actor.id, Record.deleted_at.is_(None))
            .order_by(Record.created_at.desc())
            .limit(500)
        )
    )


def source_metadata(db, sources):
    """One bounded batch; display data stays in the existing queue metadata cache."""
    if not sources:
        return {}
    ranked = (
        select(
            QueueItem.id,
            QueueItem.source_url,
            QueueItem.title,
            QueueItem.metadata_json,
            func.row_number()
            .over(
                partition_by=QueueItem.source_url,
                order_by=(QueueItem.created_at.desc(), QueueItem.position.desc(), QueueItem.id.desc()),
            )
            .label("latest"),
        )
        .where(
            QueueItem.source_url.in_(sources),
            QueueItem.title.not_in(["Resolving source…", "Source unavailable"]),
        )
        .subquery()
    )
    return {
        url: {
            "title": title,
            "uploader": metadata.get("uploader"),
            "duration": metadata.get("duration"),
            "art": "/api/v1/music/art/queue/" + identity if metadata.get("thumbnail") else None,
        }
        for identity, url, title, metadata in db.execute(
            select(ranked.c.id, ranked.c.source_url, ranked.c.title, ranked.c.metadata_json).where(
                ranked.c.latest == 1
            )
        )
    }


@router.get("/history")
def history(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    actor=Depends(require_actor),
    db=Depends(get_db),
    by: str | None = Query(None, max_length=36),
    before: str | None = Query(None, max_length=200),
):
    """Newest first. `before` (from `next_before`) continues after a row, so plays that arrive
    while someone scrolls neither repeat nor skip rows; `offset` still works."""
    require_permission(actor, "music.read")
    offset = offset if isinstance(offset, int) else 0
    limit = limit if isinstance(limit, int) else 50
    query = (
        select(Record, User.name, User.preferences)
        .join(User, User.id == Record.owner_id)
        .where(Record.kind == "music.history", Record.deleted_at.is_(None))
    )
    if isinstance(by, str) and by:
        # Everything this person ever played, not only songs they were last to play.
        played = select(Record.data["key"].as_string()).where(
            Record.kind == "music.play", Record.owner_id == by
        )
        query = query.where(or_(Record.owner_id == by, Record.id.in_(played)))
    played = Record.data["played_at"].as_string()
    if isinstance(before, str) and before:
        try:
            stamp, played_at, identity = before.split("|", 2)
            stamp = datetime.fromisoformat(stamp)
        except ValueError:
            raise HTTPException(422, "Invalid history position") from None
        # Rows after the cursor in (updated_at, played_at, id) descending order.
        query = query.where(
            or_(
                Record.updated_at < stamp,
                and_(Record.updated_at == stamp, played < played_at),
                and_(Record.updated_at == stamp, played == played_at, Record.id < identity),
            )
        )
        offset = 0
    rows = list(
        db.execute(
            query.order_by(Record.updated_at.desc(), played.desc(), Record.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
    )
    metadata = source_metadata(db, [row.data["source_url"] for row, _, _ in rows[:limit]])
    saved = {row.data["source_url"]: row.id for row in saved_records(db, actor)}
    last = rows[limit - 1][0] if len(rows) > limit else None
    return {
        "items": [
            {
                "id": row.id,
                **row.data,
                **metadata.get(row.data["source_url"], {"title": None}),
                "requester": {
                    "id": row.owner_id,
                    "name": name,
                    "avatar": (preferences or {}).get("avatar", "crest"),
                },
                "plays": row.data.get("plays") or 1,
                "favorite": row.data["source_url"] in saved,
                "saved_id": saved.get(row.data["source_url"]),
                "favorite_supported": not row.data["source_url"].startswith("houseos-file:"),
                "replay_supported": not row.data["source_url"].startswith("houseos-file:"),
            }
            for row, name, preferences in rows[:limit]
        ],
        "next_offset": offset + limit if len(rows) > limit else None,
        "next_before": (
            f"{last.updated_at.isoformat()}|{last.data.get('played_at') or ''}|{last.id}" if last else None
        ),
    }


def queue_favorites(db, actor, count=10):
    """The house's own greatest hits: `count` random picks from the 100 most played songs,
    queued as the actor so fairness and limits apply as for any request. No model involved."""
    import random

    q = queue(db)
    pending = list(db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))))
    top = list(
        db.scalars(
            select(Record)
            .where(
                Record.kind == "music.history",
                Record.deleted_at.is_(None),
                Record.data["source_url"].as_string().like("https://%"),
            )
            .order_by(func.coalesce(Record.data["plays"].as_integer(), 1).desc(), Record.updated_at.desc())
            .limit(100)
        )
    )
    waiting = {item.source_url for item in pending}
    choices = [row for row in top if row.data["source_url"] not in waiting]
    picks = random.sample(choices, k=min(count, len(choices)))
    titles = source_metadata(db, [row.data["source_url"] for row in picks])
    added = queue_songs(
        db,
        q,
        actor.id,
        actor.session_hash,
        actor.role,
        [{"source_url": row.data["source_url"], **titles.get(row.data["source_url"], {})} for row in picks],
        pending,
    )
    if added:
        auto = activate_added(db, q, added, pending)
        q.version += 1
        emit(db, "music.queue_changed", {"version": q.version})
    else:
        auto = False
    db.commit()
    return {
        "status": "accepted" if added else "empty",
        "count": len(added),
        "items": [{"item_id": item.id, "title": item.title} for item in added],
        "autoplay_requested": auto,
    }


@router.get("/quick-songs")
def quick_songs(actor=Depends(require_actor), db=Depends(get_db)):
    """Songs to start an empty queue with, drawn anew on each visit: two of the house's most
    played of the last 3 days, and one it loved 5-10 days ago but hasn't heard since."""
    import random
    from collections import Counter

    require_permission(actor, "music.read")
    now = utcnow()
    plays = db.execute(
        select(Record.data["key"].as_string(), Record.created_at)
        .where(Record.kind == "music.play", Record.created_at >= now - timedelta(days=10))
        .order_by(Record.created_at.desc())
        .limit(5000)
    ).all()
    lately = Counter(key for key, at in plays if at >= now - timedelta(days=3))
    since = {key for key, at in plays if at > now - timedelta(days=5)}  # "not heard since"
    before = Counter(key for key, at in plays if key not in since)
    rows = {
        row.id: row
        for row in db.scalars(
            select(Record).where(Record.kind == "music.history", Record.id.in_([*lately, *before]))
        )
    }
    playable = lambda key: key in rows and rows[key].data["source_url"].startswith("http")  # noqa: E731
    top = [key for key, _ in lately.most_common(8) if playable(key)]
    back = [key for key, _ in before.most_common(10) if playable(key)]
    picks = [(key, "lately") for key in random.sample(top, k=min(2, len(top)))]
    picks += [(key, "missed") for key in random.sample(back, k=min(1, len(back)))]
    urls = [rows[key].data["source_url"] for key, _ in picks]
    meta = source_metadata(db, urls)
    return {
        "items": [
            {
                "source_url": url,
                "why": why,
                "genre": rows[key].data.get("genre"),
                **meta.get(url, {"title": None}),
            }
            for (key, why), url in zip(picks, urls)
        ]
    }


class Favorites(Input):
    count: int = Field(default=10, ge=1, le=20)


@router.post("/favorites/queue")
def favorites_queue(body: Favorites, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    return queue_favorites(db, actor, body.count)


def source_genres(db, sources):
    """The genre the house worked out for each song lives on its history row."""
    keys = [history_key(source) for source in sources]
    if not keys:
        return {}
    return {
        row.data.get("source_url"): row.data.get("genre")
        for row in db.scalars(select(Record).where(Record.id.in_(keys)))
    }


@router.get("/saved")
def saved(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    rows = saved_records(db, actor)
    sources = {row.data["source_url"] for row in rows}
    metadata = source_metadata(db, sources)
    genres = source_genres(db, sources)
    seen, result = set(), []
    for row in rows:
        source = row.data["source_url"]
        if source not in seen:
            result.append(
                {
                    **row.data,
                    **metadata.get(source, {"title": source}),
                    "genre": genres.get(source),
                    "id": row.id,
                }
            )
            seen.add(source)
    return result


def save_canonical_track(db, actor, url, item=None):
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    row = db.scalar(
        select(Record).where(
            Record.kind == "saved_track",
            Record.owner_id == actor.id,
            Record.data["source_url"].as_string() == url,
            Record.deleted_at.is_(None),
        )
    )
    if row:
        return row
    data = {"source_url": url}
    row = Record(kind="saved_track", owner_id=actor.id, data=data)
    db.add(row)
    db.flush()
    return row


@router.post("/saved")
def save_track(body: Add, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    db.rollback()
    url = resolve_source_url(body.source_url)
    from .auth import refresh_actor

    actor = refresh_actor(db, actor)
    require_permission(actor, "music.queue")
    row = save_canonical_track(db, actor, url)
    db.commit()
    return {"status": "completed", "id": row.id}


@router.get("/current/favorite")
def current_favorite(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    q = db.get(QueueState, 1)
    item = db.get(QueueItem, q.current_id) if q and q.current_id else None
    if not item:
        return {"item_id": None, "supported": False, "favorite": False, "saved_id": None}
    row = next(
        (row for row in saved_records(db, actor) if row.data.get("source_url") == item.source_url), None
    )
    return {
        "item_id": item.id,
        "source_url": item.source_url,
        "supported": not item.source_url.startswith("houseos-file:"),
        "favorite": row is not None,
        "saved_id": row.id if row else None,
    }


class CurrentFavorite(Input):
    item_id: str = Field(max_length=36)


@router.post("/current/favorite")
def favorite_current(body: CurrentFavorite, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    q = queue(db)
    if q.current_id != body.item_id:
        raise HTTPException(409, "The current track changed; refresh before saving it")
    item = db.get(QueueItem, q.current_id)
    if not item or item.source_url.startswith("houseos-file:"):
        raise HTTPException(422, "Local file access stays in Files; this shortcut saves public music sources")
    row = save_canonical_track(db, actor, item.source_url, item)
    db.commit()
    return {"status": "completed", "id": row.id, "saved_id": row.id, "favorite": True, "item_id": item.id}


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    source: Literal["youtube", "soundcloud"] = "youtube",
    actor=Depends(require_actor),
    db=Depends(get_db),
    limit: int = Query(default=5, ge=1, le=50),
):
    require_permission(actor, "music.read")
    from .worker import fetch

    limit = limit if isinstance(limit, int) else 5
    result = fetch("search", query=q, source=source, limit=limit)
    home = kept_matches(db, q)
    if result.get("status") != "completed" and not home:
        return result
    # Songs the house already keeps come first (they start at once, offline too), then the rest.
    kept = {song["source_url"] for song in home}
    online = [c for c in result.get("items", []) if c.get("source_url") not in kept][:limit]
    items = []
    for candidate in [*home, *online]:
        record = Record(kind="music_candidate", owner_id=actor.id, data=candidate)
        db.add(record)
        db.flush()
        items.append({"id": record.id, **candidate})
    db.commit()
    return {"status": "completed", "items": items}


def kept_matches(db, query, most=3):
    """Songs kept on the house disk whose title or channel has every word searched (or a word
    starting with it), newest first."""
    from .music_genre import fold

    words = fold(query).split()
    if not words:
        return []
    # ponytail: scans the kept songs' rows in Python; a title index if a house keeps 50,000+.
    rows = db.scalars(
        select(Record)
        .where(
            Record.kind == "music.download",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
        .order_by(Record.updated_at.desc())
    )
    found = []
    for row in rows:
        data = row.data
        heard = fold(f"{data.get('title') or ''} {data.get('uploader') or ''}").split()
        if data.get("source_url") and all(any(h.startswith(word) for h in heard) for word in words):
            found.append(data)
            if len(found) == most:
                break
    art = source_metadata(db, [data["source_url"] for data in found])
    return [
        {
            "source_url": data["source_url"],
            "title": data.get("title") or "Song",
            "uploader": data.get("uploader"),
            "duration": data.get("duration"),
            "art": art.get(data["source_url"], {}).get("art"),
            "at_home": True,
        }
        for data in found
    ]


def song_query(url: str, title: str, description: str) -> str:
    """Search words from a streaming service's page. Spotify's title is the song alone and its
    description starts with the artist ("Artist · Album · Song · 2020"); the others say "Song by
    Artist", "Song - Artist" or "Song - Song by Artist | Apple Music"."""
    song = re.split(r" \| | on Apple Music| - Apple Music", title)[0]
    if "spotify" in url and "·" in description:
        return f"{song} {description.split('·')[0].strip()}"
    return re.sub(r"\s+-\s+song by\s+|\s+by\s+|\s+-\s+", " ", song).strip()


@router.get("/link-song")
def link_song(url: str = Query(max_length=2048), actor=Depends(require_actor)):
    """A Spotify, Apple Music, Deezer or Tidal link can't play here: the song it names, as words
    to search YouTube with (Listen then offers versions to pick)."""
    require_permission(actor, "music.read")
    from .worker import fetch

    page = fetch("song_page", url)
    if page.get("status") != "completed" or not page.get("title"):
        raise HTTPException(422, "That link doesn't say which song it is: type the song and artist instead.")
    return {"status": "completed", "query": song_query(url, page["title"], page.get("description", ""))}


class CandidateAdd(Input):
    candidate_id: str
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/candidates")
def add_candidate(body: CandidateAdd, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    row = db.scalar(
        select(Record).where(
            Record.id == body.candidate_id,
            Record.owner_id == actor.id,
            Record.kind == "music_candidate",
            Record.created_at > utcnow() - timedelta(hours=1),
        )
    )
    if not row:
        raise HTTPException(410, "Search result expired; search again")
    return enqueue(Add(source_url=row.data["source_url"], idempotency_key=body.idempotency_key), actor, db)


class CandidateBatch(Input):
    avoid_duplicates: bool = False
    candidate_ids: list[str] = Field(min_length=1, max_length=10)
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/candidates/batch")
def add_candidates(body: CandidateBatch, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    q = queue(db)
    previous = db.scalar(
        select(Operation).where(
            Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
        )
    )
    if previous:
        if (
            previous.kind != "music.batch"
            or previous.data.get("candidate_ids") != body.candidate_ids
            or previous.data.get("avoid_duplicates", False) != body.avoid_duplicates
        ):
            raise HTTPException(409, "Idempotency key already used for another action")
        return {"status": previous.state, "operation_id": previous.id, **previous.result}
    records = {
        row.id: row
        for row in db.scalars(
            select(Record).where(
                Record.id.in_(body.candidate_ids),
                Record.owner_id == actor.id,
                Record.kind == "music_candidate",
                Record.created_at > utcnow() - timedelta(hours=1),
            )
        )
    }
    if any(identity not in records for identity in body.candidate_ids):
        raise HTTPException(410, "A search result expired or is unavailable; search again")
    pending = list(db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))))
    candidates, seen = [], {item.source_url for item in pending} if body.avoid_duplicates else set()
    for identity in body.candidate_ids:
        candidate = records[identity].data
        source = canonical_source(candidate["source_url"])
        if source.startswith("https://on.soundcloud.com/"):
            raise HTTPException(422, "Search candidates must identify a canonical track")
        if source not in seen:
            candidates.append((source, str(candidate.get("title") or "Resolving source…")[:500]))
            seen.add(source)
    if (
        len(pending) + len(candidates) > 500
        or actor.role == "guest"
        and sum(item.owner_id == actor.id for item in pending) + len(candidates) > 10
    ):
        raise HTTPException(409, "Batch exceeds queue allowance")
    base = max([item.position for item in pending], default=0)
    added = []
    for index, (source, title) in enumerate(candidates):
        item = QueueItem(
            owner_id=actor.id,
            source_url=source,
            title=title,
            position=base + index + 1,
            metadata_json={"session_hash": actor.session_hash},
        )
        db.add(item)
        db.flush()
        added.append(item)
        db.add(
            Job(
                logical_key="metadata:" + item.id,
                kind="music.metadata",
                actor_id=actor.id,
                payload={"item_id": item.id, "session_hash": actor.session_hash},
            )
        )
    auto = activate_added(db, q, added, pending)
    result = {
        "count": len(added),
        "duplicates_skipped": len(body.candidate_ids) - len(added),
        "items": [{"item_id": item.id, "title": item.title} for item in added],
        "autoplay_requested": auto,
    }
    operation = Operation(
        actor_id=actor.id,
        kind="music.batch",
        state="accepted",
        idempotency_key=body.idempotency_key,
        data={"candidate_ids": body.candidate_ids, "avoid_duplicates": body.avoid_duplicates},
        result=result,
    )
    db.add(operation)
    db.flush()
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": "accepted", "operation_id": operation.id, **result}


@router.post("/playlists/preview")
def preview_playlist(body: Add, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    from .worker import fetch

    source = playlist_source(body.source_url)
    result = fetch("playlist", source)
    if result.get("status") != "completed":
        return result
    total = result.get("total") if isinstance(result.get("total"), int) else len(result.get("items", []))
    op = Operation(
        actor_id=actor.id,
        kind="music.playlist",
        state="needs_confirmation",
        data={**result, "source_url": source, "total": total},
        expires_at=utcnow() + timedelta(minutes=5),
        idempotency_key=body.idempotency_key,
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "items": result["items"],
        "total": total,
        "title": result.get("title"),
    }


PLAYLIST_PAGE = 50


def queue_songs(db, q, owner_id, session_hash, role, candidates, pending, limit=500):
    """Queue new songs in order, skipping songs already waiting or playing. Stops at the
    house limit (500 songs, 10 per guest) and returns the created items."""
    seen = {item.source_url for item in pending}
    room = limit - len(pending)
    if role == "guest":
        room = min(room, 10 - sum(item.owner_id == owner_id for item in pending))
    created = []
    base = max([item.position for item in pending], default=0)
    for candidate in candidates:
        if len(created) >= room:
            break
        if candidate.get("source_url") in seen:
            continue
        seen.add(candidate["source_url"])
        item = QueueItem(
            owner_id=owner_id,
            source_url=candidate["source_url"],
            position=base + len(created) + 1,
            title=str(candidate.get("title") or "Resolving source…")[:500],
            status="pending_metadata",
            metadata_json={
                "session_hash": session_hash,
                "thumbnail": candidate.get("thumbnail"),
                **({"playlist_id": candidate["playlist_id"]} if candidate.get("playlist_id") else {}),
            },
        )
        db.add(item)
        db.flush()
        created.append(item)
        db.add(
            Job(
                logical_key="metadata:" + item.id,
                kind="music.metadata",
                actor_id=owner_id,
                payload={"item_id": item.id, "session_hash": session_hash},
            )
        )
    if created:  # the log says who added them
        emit(db, "audit.music_add", {"item_id": created[0].id, "count": len(created)}, owner_id)
    return created


@router.post("/playlists/{identity}/confirm")
def import_playlist(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    """Queue the first page now; the rest of a long playlist imports in the background."""
    require_permission(actor, "music.queue")
    q = queue(db)
    op = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if not op or op.kind != "music.playlist" or op.state != "needs_confirmation" or op.expires_at <= utcnow():
        raise HTTPException(409, "Playlist preview expired or consumed")
    pending = db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))).all()
    created = queue_songs(db, q, actor.id, actor.session_hash, actor.role, op.data["items"], pending)
    if not created and op.data["items"]:
        raise HTTPException(409, "These songs are already queued, or the queue is full")
    auto = activate_added(db, q, created, pending)
    total = op.data.get("total") or len(op.data["items"])
    # Saved playlists carry all their songs; only a linked playlist has more pages to fetch.
    more = "source_url" in op.data and total > PLAYLIST_PAGE and len(op.data["items"]) >= PLAYLIST_PAGE
    op.state = "running" if more else "completed"
    op.result = {
        "added": len(created),
        "total": total,
        "item_ids": [item.id for item in created],
        "autoplay_requested": auto,
    }
    if more:
        db.add(
            Job(
                logical_key="playlist:" + op.id + ":" + str(PLAYLIST_PAGE + 1),
                kind="music.playlist_import",
                actor_id=actor.id,
                payload={
                    "operation_id": op.id,
                    "source_url": op.data["source_url"],
                    "start": PLAYLIST_PAGE + 1,
                    "session_hash": actor.session_hash,
                },
            )
        )
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": op.state, "operation_id": op.id, **op.result}


@router.post("/playlists/{identity}/cancel")
def cancel_playlist_import(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    """Stop importing; songs already queued stay in the queue."""
    require_permission(actor, "music.queue")
    op = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if not op or op.kind != "music.playlist":
        raise HTTPException(404, "Playlist import not found")
    if op.state == "running":
        op.state = "cancelled"
        emit(db, "music.queue_changed", {"import": op.id})
        db.commit()
    return {"status": op.state, **(op.result or {})}


def import_playlist_page(job_id, generation, data):
    """Worker step: fetch the next 50 songs of a playlist and queue them fairly."""
    from .db import SessionLocal
    from .worker import fetch

    with SessionLocal() as db:
        row, op = db.get(Job, job_id), db.get(Operation, data["operation_id"])
        if not row or row.generation != generation or row.state != "running":
            return
        if not op or op.state != "running":
            row.state = "cancelled"
            db.commit()
            return
    page = fetch("playlist", data["source_url"], start=data["start"])
    with SessionLocal() as db:
        row, op = db.get(Job, job_id), db.get(Operation, data["operation_id"])
        if not row or row.generation != generation or row.state != "running":
            return
        user = db.get(User, row.actor_id)
        if not op or op.state != "running" or not user:
            row.state = "cancelled"
            db.commit()
            return
        result = dict(op.result or {})
        if page.get("status") != "completed":
            row.state, row.error_code = "failed", page.get("code", "PLAYLIST_PAGE_FAILED")
            op.state, op.result = "completed", {**result, "stopped": page.get("code", "PLAYLIST_PAGE_FAILED")}
            db.commit()
            return
        q = queue(db)
        if data.get("playlist_id"):  # a playlist kept as a house playlist, not queued
            from .music_library import append_to_playlist

            added, full = append_to_playlist(db, data["playlist_id"], user.id, page.get("items", []))
        else:
            pending = db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))).all()
            created = queue_songs(
                db, q, user.id, data.get("session_hash"), user.role, page.get("items", []), pending
            )
            place_fairly(db, q, created)
            added, full = len(created), len(pending) + len(created) >= 500
        result["added"] = result.get("added", 0) + added
        next_start = data["start"] + PLAYLIST_PAGE
        more = len(page.get("items", [])) >= PLAYLIST_PAGE and next_start <= (result.get("total") or 0)
        if more and not full:
            db.add(
                Job(
                    logical_key="playlist:" + op.id + ":" + str(next_start),
                    kind="music.playlist_import",
                    actor_id=user.id,
                    payload={**data, "start": next_start},
                )
            )
        else:
            op.state = "completed"
            if full and more:
                result["stopped"] = "QUEUE_FULL"
        op.result = result
        row.state = "completed"
        q.version += 1
        emit(db, "music.queue_changed", {"version": q.version})
        db.commit()


# Titles that name no song (an import that had none): no "other versions" to search for.
UNNAMED = {"Source unavailable", "Resolving source…", "None", "Unknown title", ""}


@router.get("/unavailable")
def unavailable(actor=Depends(require_actor), db=Depends(get_db)):
    """Your songs that turned out removed or private: they left the queue; pick another version."""
    require_permission(actor, "music.read")
    rows = db.scalars(
        select(Record)
        .where(Record.kind == "music.unavailable", Record.owner_id == actor.id, Record.deleted_at.is_(None))
        .order_by(Record.created_at.desc())
        .limit(50)
    )
    return {"items": [{"id": row.id, **row.data} for row in rows if row.data.get("title") not in UNNAMED]}


class Replacement(Input):
    source_url: str = Field(max_length=2048)
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/unavailable/{identity}/replace")
def replace_unavailable(identity: str, body: Replacement, actor=Depends(require_actor), db=Depends(get_db)):
    """Queue the chosen version, and put it in the gone song's place in its playlist."""
    require_permission(actor, "music.queue")
    row = own_unavailable(db, actor, identity)
    playlist = row.data.get("playlist_id")
    if playlist:
        from .music_library import swap_in_playlist

        swap_in_playlist(db, actor, playlist, row.data["source_url"], canonical_source(body.source_url))
    row.deleted_at = utcnow()
    db.commit()
    return enqueue(Add(source_url=body.source_url, idempotency_key=body.idempotency_key), actor, db)


@router.delete("/unavailable/{identity}")
def dismiss_unavailable(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    own_unavailable(db, actor, identity).deleted_at = utcnow()
    db.commit()
    return {"status": "dismissed"}


def own_unavailable(db, actor, identity):
    row = db.get(Record, identity)
    if not row or row.kind != "music.unavailable" or row.owner_id != actor.id or row.deleted_at:
        raise HTTPException(404, "Not found")
    return row


@router.delete("/saved/{identity}")
def delete_saved(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    row = db.scalar(
        select(Record).where(Record.id == identity, Record.owner_id == actor.id, Record.kind == "saved_track")
    )
    if not row:
        raise HTTPException(404, "Saved track not found")
    # Remove legacy duplicates together so toggling off cannot reveal an older copy.
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    duplicates = db.scalars(
        select(Record).where(
            Record.owner_id == actor.id,
            Record.kind == "saved_track",
            Record.data["source_url"].as_string() == row.data["source_url"],
            Record.deleted_at.is_(None),
        )
    ).all()
    for duplicate in duplicates:
        duplicate.deleted_at = utcnow()
    db.commit()
    return {"status": "completed"}


from . import music_library, radio, music_outputs, music_auto  # noqa: F401 (register library/vote/radio/output/auto routes)
