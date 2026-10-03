"""Auto DJ: when the queue runs dry, the house keeps playing on its own, one pick at a time.
Either songs it already keeps (all, or by genre, by who kept or played them, and when), or a rotation of radio stations that
each play a few songs or a few minutes. A real request always goes first. No model involved."""

import random
import time
from datetime import timedelta
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import func, select
from .auth import Input, require_actor, require_permission, delegated_user
from .db import get_db, utcnow
from .events import emit
from .models import Integration, Job, Record, User
from .music import (
    router,
    queue,
    QueueItem,
    ACTIVE_QUEUE_STATUSES,
    history_key,
    pending_order,
    source_metadata,
    start_sleep_timer,
)
from .config import settings

# Auto play keeps a plan of its next songs (the house can see, reorder and trim it). Songs heard
# lately stay out of fresh picks; songs taken out of the plan stay out until the plan is redone.
PLAN = 50
HEARD = 50
SKIPPED = 300


class Station(Input):
    id: str = Field(min_length=36, max_length=36)
    name: str = Field(default="", max_length=120)
    songs: int | None = Field(default=None, ge=1, le=50)
    minutes: int | None = Field(default=None, ge=1, le=240)

    @model_validator(mode="after")
    def some_limit(self):
        if not self.songs and not self.minutes:
            self.minutes = 30
        return self


class Auto(Input):
    mode: Literal["off", "library", "radio"]
    genres: list[str] = Field(default_factory=list, max_length=30)
    # Only songs these residents kept or played (none: everyone's), within the last `days`.
    people: list[str] = Field(default_factory=list, max_length=50)
    days: Literal[7, 30, 90, 365] | None = None
    stations: list[Station] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def radio_needs_stations(self):
        if self.mode == "radio" and not self.stations:
            raise ValueError("Pick at least one station")
        return self


def config(db):
    row = db.get(Integration, "music_playback")
    return ((row.config or {}) if row else {}).get("auto") or {"mode": "off"}


def save(db, value):
    row = db.get(Integration, "music_playback", with_for_update=True)
    if row is None:
        row = Integration(name="music_playback", config={})
        db.add(row)
    row.config = {**(row.config or {}), "auto": value}


def kept_songs(db):
    """(source_url, title, genre) of every song the house keeps on its disk."""
    rows = db.scalars(
        select(Record).where(
            Record.kind == "music.download",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
    ).all()
    songs = {row.data["source_url"]: row.data.get("title") for row in rows if row.data.get("source_url")}
    # A played song's genre is on its history; a kept song never played keeps its own.
    genres = {row.data["source_url"]: row.data.get("genre") for row in rows if row.data.get("source_url")}
    for row in db.scalars(select(Record).where(Record.id.in_([history_key(url) for url in songs]))):
        genres[row.data.get("source_url")] = row.data.get("genre")
    return [(url, title, genres.get(url) or "other") for url, title in songs.items()]


def kept_by(db, urls):
    """{source_url: {person: when they last kept or played it}} for these kept songs."""
    keys = {history_key(url): url for url in urls}
    found = {url: {} for url in urls}

    def note(url, person, when):
        if url in found and when and (person not in found[url] or when > found[url][person]):
            found[url][person] = when

    for url, owner, created in db.execute(
        select(Record.data["source_url"].as_string(), Record.owner_id, Record.created_at).where(
            Record.kind == "music.download",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
    ):
        note(url, owner, created)
    key = Record.data["key"].as_string()
    for song, owner, last in db.execute(
        select(key, Record.owner_id, func.max(Record.created_at))
        .where(Record.kind == "music.play")
        .group_by(key, Record.owner_id)
    ):
        note(keys.get(song), owner, last)
    return found


def candidates(db, current):
    """{source_url: (title, genre)} of the kept songs auto play may pick with these settings."""
    genres = set(current.get("genres") or ())
    songs = {url: (title, genre) for url, title, genre in kept_songs(db) if not genres or genre in genres}
    people, days = set(current.get("people") or ()), current.get("days")
    if not people and not days:
        return songs
    since = utcnow() - timedelta(days=days) if days else None
    facts = kept_by(db, list(songs))
    return {
        url: song
        for url, song in songs.items()
        if any(
            (not people or person in people) and (since is None or when >= since)
            for person, when in facts[url].items()
        )
    }


def heard_lately(db):
    return set(
        db.scalars(
            select(Record.data["key"].as_string())
            .where(Record.kind == "music.play")
            .order_by(Record.created_at.desc())
            .limit(HEARD)
        )
    )


def planned(db, current, songs, fresh=False):
    """The next PLAN songs: the saved order first, then random kept songs not heard lately."""
    skipped = set(current.get("skipped") or ())
    plan = [] if fresh else [u for u in dict.fromkeys(current.get("upcoming") or []) if u in songs]
    if len(plan) < PLAN:
        heard = heard_lately(db)
        queued = set(
            db.scalars(select(QueueItem.source_url).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES)))
        )
        pool = [u for u in songs if u not in plan and u not in skipped and u not in queued]
        pool = [u for u in pool if history_key(u) not in heard] or pool
        random.shuffle(pool)
        plan += pool[: PLAN - len(plan)]
    return plan


from . import music_catalog  # noqa: E402 (after the routes' imports: music_catalog imports music)


@router.get("/auto")
def auto_state(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    counts, kept = {}, kept_songs(db)
    for _, _, genre in kept:
        counts[genre] = counts.get(genre, 0) + 1
    current = config(db)
    # Who can be picked: everyone who kept or played a kept song, with how many.
    tally = {}
    for people in kept_by(db, [url for url, _, _ in kept]).values():
        for person in people:
            tally[person] = tally.get(person, 0) + 1
    # Guests see the queue, not who in the house played what.
    names = (
        {}
        if actor.role == "guest"
        else dict(db.execute(select(User.id, User.name).where(User.id.in_(tally))).all())
    )
    return {
        **{key: current.get(key) for key in ("genres", "stations", "people", "days")},
        "people_kept": sorted(
            ({"id": p, "name": names[p], "count": n} for p, n in tally.items() if p in names),
            key=lambda p: -p["count"],
        ),
        "mode": current.get("mode", "off"),
        "kept": sum(counts.values()),
        "genres_kept": sorted(
            ({"genre": g, "count": n} for g, n in counts.items()), key=lambda g: -g["count"]
        ),
        "can_change": actor.role != "guest",
        "sorting": music_catalog.sort_requested(db),
    }


@router.post("/auto/sort-genres")
def sort_genres(actor=Depends(require_actor), db=Depends(get_db)):
    """Residents: look again at every song still in "other" (Deezer, a few songs a minute)."""
    require_permission(actor, "music.control")
    if actor.role == "guest":
        raise HTTPException(403, "Sorting songs is for residents")
    from .house_settings import get_house_settings

    if not get_house_settings(db)["music_genre_lookup"]:
        raise HTTPException(409, "Turn on “Find each song's genre online” in Control Room → House first")
    count = music_catalog.sort_again(db)
    db.commit()
    return {"songs": count, "minutes": -(-count // music_catalog.BATCH)}


@router.put("/auto")
def set_auto(body: Auto, actor=Depends(require_actor), db=Depends(get_db)):
    """Residents only: the kept songs are the house archive, and this plays for everyone."""
    require_permission(actor, "music.control")
    if actor.role == "guest":
        raise HTTPException(403, "Auto play is for residents")
    q = queue(db)
    if body.mode == "library" and not candidates(db, body.model_dump()):
        raise HTTPException(409, {"code": "AUTO_NOTHING_KEPT", "message": "No kept song matches"})
    # The plan starts over; its version keeps counting, so an old page can't overwrite it.
    version = config(db).get("plan_version", 0) + 1
    save(db, {**body.model_dump(), "by": actor.id, "next": 0, "plan_version": version})
    started = False
    if body.mode != "off" and not q.current_id:
        if not settings.audio_enabled:
            raise HTTPException(409, "Select an available speaker output and enable music in Control Room")
        # Turning it on while nothing plays is the request to hear it.
        q.desired, q.failures, started = "playing", 0, True
        start_sleep_timer(db, q)
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": "accepted", "mode": body.mode, "started": started}


def stuck(db):
    """The last three picks all failed: stop rather than churn through the archive."""
    last = db.scalars(select(QueueItem).order_by(QueueItem.created_at.desc()).limit(3)).all()
    return len(last) == 3 and all(i.metadata_json.get("auto") and i.status == "failed" for i in last)


def fill(db, q):
    """Called by the worker when music should play and nothing waits: queue one pick.
    Returns the new item, or None. The caller commits."""
    current = config(db)
    if current.get("mode", "off") == "off":
        return None
    # Read again under the row lock: a resident may be reordering the plan right now.
    db.get(Integration, "music_playback", with_for_update=True)
    current = config(db)
    mode = current.get("mode", "off")
    if mode == "off":
        return None
    by = delegated_user(db, current.get("by"), None, "music.queue")
    if not by or stuck(db):
        save(db, {**current, "mode": "off"})
        return None
    waiting = set(db.scalars(select(QueueItem.source_url).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))))
    loading = select(QueueItem.id).where(QueueItem.status.in_(["pending_metadata", "resolving", "buffering"]))
    if db.scalar(loading.limit(1)):  # the last pick (or a request) is still getting ready
        return None
    if mode == "library":
        songs = candidates(db, current)
        plan = planned(db, current, songs)
        url = next((u for u in plan if u not in waiting), None)
        if not url:
            return None
        plan.remove(url)
        save(db, {**current, "upcoming": plan, "plan_version": current.get("plan_version", 0) + 1})
        title = songs[url][0]
        meta = {"auto": "library"}
    else:
        stations = current.get("stations") or []
        station = stations[current.get("next", 0) % len(stations)]
        save(db, {**current, "next": current.get("next", 0) + 1})
        url, title = "radio:" + station["id"], station.get("name") or "Radio"
        meta = {
            "auto": "radio",
            "live_approved": True,  # choosing the rotation was the request to play it
            "rotation": {"songs": station.get("songs"), "minutes": station.get("minutes")},
        }
    position = (
        max(
            db.scalars(select(QueueItem.position).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))),
            default=0,
        )
        + 1
    )
    item = QueueItem(
        owner_id=by.id, source_url=url, title=(title or "Song")[:500], position=position, metadata_json=meta
    )
    db.add(item)
    db.flush()
    db.add(
        Job(
            logical_key="metadata:" + item.id,
            kind="music.metadata",
            actor_id=by.id,
            payload={"item_id": item.id},
        )
    )
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    return item


def rotation_over(db, item, now=None):
    """An auto station has had its turn: its songs or its minutes are done, or someone asked
    for a song. Stations that never say what is on fall back to 6 minutes a song."""
    rotation = item.metadata_json.get("rotation") or {}
    since = item.metadata_json.get("auto_since")
    if not since:
        return False
    elapsed = ((now or time.time()) - since) / 60
    songs, minutes = rotation.get("songs"), rotation.get("minutes")
    # The first title is a song already under way, so N songs end when title N+1 starts.
    if songs and item.metadata_json.get("titles_heard", 0) > songs:
        return True
    if elapsed >= (minutes or songs * 6):
        return True
    return (
        db.scalar(
            select(QueueItem.id)
            .where(QueueItem.status.in_(["ready", "pending_metadata"]), QueueItem.id != item.id)
            .limit(1)
        )
        is not None
    )


def queued_picks(db, actor):
    """Auto play's picks already in the queue, in play order: the list goes on from them."""
    q = queue(db)
    rows = db.scalars(select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES))).all()
    picks = [row for row in pending_order(db, q, rows) if row.metadata_json.get("auto") == "library"]
    meta = source_metadata(db, [row.source_url for row in picks])
    return [
        {
            "id": row.id,
            "source_url": row.source_url,
            "title": row.title,
            **{
                k: v
                for k, v in (meta.get(row.source_url) or {}).items()
                if k in {"art", "uploader", "duration"}
            },
            "removable": row.owner_id == actor.id or actor.role == "admin",
        }
        for row in picks
    ]


def plan_view(db, actor, current, plan, songs):
    meta = source_metadata(db, plan)
    return {
        "queued": queued_picks(db, actor),
        "mode": current.get("mode", "off"),
        "version": current.get("plan_version", 0),
        "can_change": actor.role != "guest",
        "items": [
            {
                "source_url": url,
                "title": (meta.get(url) or {}).get("title") or songs[url][0] or "Song",
                "genre": songs[url][1],
                **{k: v for k, v in (meta.get(url) or {}).items() if k in {"art", "uploader", "duration"}},
            }
            for url in plan
        ],
    }


@router.get("/auto/upcoming")
def upcoming(actor=Depends(require_actor), db=Depends(get_db)):
    """What auto play will pick next, in order (library mode). Asking fixes the plan, so the
    list shown is the list played."""
    require_permission(actor, "music.read")
    current = config(db)
    if current.get("mode") != "library":
        return {"mode": current.get("mode", "off"), "version": 0, "items": [], "can_change": False}
    songs = candidates(db, current)
    plan = planned(db, current, songs)
    if plan != (current.get("upcoming") or []):
        db.get(Integration, "music_playback", with_for_update=True)
        current = config(db)
        plan = planned(db, current, songs)
        # A new version: a page still showing the shorter list can't mark the new songs removed.
        current = {**current, "upcoming": plan, "plan_version": current.get("plan_version", 0) + 1}
        save(db, current)
        db.commit()
    return plan_view(db, actor, current, plan, songs)


class Plan(Input):
    version: int = Field(ge=0)
    # The whole new order (moved or trimmed); None with shuffle=True draws a new plan.
    urls: list[str] | None = Field(default=None, max_length=PLAN + 10)
    shuffle: bool = False


@router.put("/auto/upcoming")
def change_upcoming(body: Plan, actor=Depends(require_actor), db=Depends(get_db)):
    """Residents reorder, remove or reshuffle the next songs. A song removed stays out of the
    plan's future picks (up to the last SKIPPED removals)."""
    require_permission(actor, "music.control")
    if actor.role == "guest":
        raise HTTPException(403, "Auto play is for residents")
    db.get(Integration, "music_playback", with_for_update=True)
    current = config(db)
    if current.get("mode") != "library":
        raise HTTPException(
            409, {"code": "AUTO_NOT_LIBRARY", "message": "Auto play isn't playing kept songs"}
        )
    if body.version != current.get("plan_version", 0):
        raise HTTPException(
            409, {"code": "PLAN_CHANGED", "message": "A song started meanwhile; here is the new list"}
        )
    songs = candidates(db, current)
    before = [u for u in current.get("upcoming") or [] if u in songs]
    if body.shuffle:  # a new list: songs removed before may come back
        skipped = []
        plan = planned(db, {**current, "skipped": []}, songs, fresh=True)
    else:
        plan = [u for u in dict.fromkeys(body.urls or []) if u in songs]
        removed = [u for u in before if u not in plan]
        skipped = [*(current.get("skipped") or []), *removed][-SKIPPED:]
    current = {**current, "upcoming": plan, "skipped": skipped, "plan_version": body.version + 1}
    save(db, current)
    db.commit()
    return plan_view(db, actor, current, plan, songs)
