"""Genres and missing artwork for every song the house has played, a few at a time.

Run by the maintenance service each minute: each song (one `music.history` record) is looked
at once. Its evidence (the source's genre and tags, a station's tags, Deezer's album genres)
is kept on the record so stats can re-read it with the house's own genres at any time. Songs
played before this existed are caught up the same way; nothing runs on the play path."""

import time
from datetime import timedelta

from sqlalchemy import select

from .db import utcnow
from .models import Integration, Record
from .music import QueueItem, history_key
from .music_genre import deezer, genre_of, youtube_thumbnail

BATCH = 20  # songs per minute: a few Deezer requests each, far under its 50 per 5 s
# Bumped when the matching improves: songs still "other", or filed by a guess Deezer never
# confirmed, are looked at once more.
MATCHER = 4  # 3: the artist's genre when Deezer lacks the song; 4: Deezer asked whatever the guess
state = {"idle_until": 0.0}


def family(data, extra=()):
    """A history record's genre: from its evidence when it has some, else what was guessed
    when it was first played."""
    evidence = data.get("evidence") or {}
    return genre_of(evidence, extra) if evidence.get("checked_at") else (data.get("genre") or "other")


def latest_item(db, url):
    return db.scalar(
        select(QueueItem).where(QueueItem.source_url == url).order_by(QueueItem.created_at.desc()).limit(1)
    )


def evidence_for(db, url, item, lookup, client, known=None):
    """What is known about one song or station; raises on a network error (tried later).
    `known`: the record's own title and uploader, for a kept song never queued."""
    meta = item.metadata_json if item else {}
    known = known or {}
    found = dict(meta.get("genre_evidence") or {})
    found.update(
        {
            "title": item.title if item else known.get("title") or "",
            "uploader": meta.get("uploader") or known.get("uploader") or "",
            **({"artist": meta["artist"]} if meta.get("artist") else {}),
        }
    )
    if url.startswith("radio:"):
        if not found.get("tags"):
            from .radio import resolve

            try:
                tags = resolve(url[6:]).get("tags", "")
            except ValueError:  # the directory no longer lists it: nothing more to learn
                tags = ""
            found["tags"] = [t.strip() for t in tags.split(",") if t.strip()][:15]
        return found
    # Deezer whenever the source names no genre itself: a guess from tags or title words
    # ("Sultans Of Swing" → jazz, a label's "Jazz" tag on Rosalía) never stands in for it.
    if lookup and not found.get("genre") and not found.get("genres"):
        match = deezer(found["title"], found["uploader"], found.get("artist", ""), client)
        found.update({key: match[key] for key in ("genres", "cover") if match.get(key)})
    return found


def give_artwork(db, url, item, evidence):
    """A still for songs recorded without one: YouTube's own, else the album cover."""
    if not item:
        return
    known = db.scalars(select(QueueItem.metadata_json).where(QueueItem.source_url == url)).all()
    if any((meta or {}).get("thumbnail") for meta in known):
        return
    art = youtube_thumbnail(url) or evidence.get("cover")
    if art:
        item.metadata_json = {**item.metadata_json, "thumbnail": art}


def songs(db):
    """(id, data) of every record that carries a song's genre: each played song's history, and
    each kept song never played (its genre is kept on its download record)."""
    played = db.execute(
        select(Record.id, Record.data).where(Record.kind == "music.history", Record.deleted_at.is_(None))
    ).all()
    seen = {identity for identity, _ in played}
    kept = [
        (identity, data)
        for identity, data in db.execute(
            select(Record.id, Record.data).where(Record.kind == "music.download", Record.deleted_at.is_(None))
        ).all()
        if data.get("state") == "ready"
        and data.get("source_url")
        and history_key(data["source_url"]) not in seen
    ]
    return played + kept


def sort_requested(db):
    row = db.get(Integration, "music_genres")
    return bool(row and (row.config or {}).get("sort_requested"))


def sort_again(db):
    """Every song still "other" is looked at once more, from the next minute (the button in
    Listen → Auto play). Returns how many. The caller commits."""
    count = 0
    for identity, data in songs(db):
        if (data.get("genre") or "other") != "other":
            continue
        row = db.get(Record, identity, with_for_update=True)
        evidence = {k: v for k, v in (row.data.get("evidence") or {}).items() if k != "retry_at"}
        row.data = {**row.data, "genre": "other", "evidence": {**evidence, "matcher": 0}}
        count += 1
    row = db.get(Integration, "music_genres", with_for_update=True)
    if row is None:
        row = Integration(name="music_genres", config={})
        db.add(row)
    row.config = {**(row.config or {}), "sort_requested": count > 0}
    return count


def enrich(db, limit=BATCH):
    import httpx

    from .house_settings import get_house_settings

    if time.monotonic() < state["idle_until"] and not sort_requested(db):
        return 0
    house = get_house_settings(db)
    now = utcnow().isoformat() + "Z"
    # ponytail: scans every song's record once a minute while work remains, then naps 10 min.
    rows = songs(db)

    def due(data):
        evidence = data.get("evidence") or {}
        if evidence.get("retry_at", "") > now:
            return False
        guessed = (data.get("genre") or "other") == "other" or not (
            evidence.get("genre") or evidence.get("genres")
        )
        stale = guessed and evidence.get("matcher", 1) < MATCHER
        return not evidence.get("checked_at") or stale

    todo = [identity for identity, data in rows if due(data)][:limit]
    if not todo:
        state["idle_until"] = time.monotonic() + 600
        if sort_requested(db):
            db.get(Integration, "music_genres", with_for_update=True).config = {"sort_requested": False}
            db.commit()
        return 0
    done = 0
    with httpx.Client(timeout=6, headers={"Accept-Language": "en"}) as client:
        for identity in todo:
            row = db.get(Record, identity)
            url = row.data["source_url"]
            item = latest_item(db, url)
            try:
                evidence = evidence_for(db, url, item, house["music_genre_lookup"], client, row.data)
                evidence.update(checked_at=now, matcher=MATCHER)
                update = {
                    "evidence": {k: v for k, v in evidence.items() if k != "cover"},
                    "genre": genre_of(evidence, house["music_genres"]),
                }
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                evidence = {}  # try again in a few hours; the first guess stays meanwhile
                update = {"evidence": {"retry_at": (utcnow() + timedelta(hours=6)).isoformat() + "Z"}}
            give_artwork(db, url, item, evidence)
            row = db.get(Record, identity, with_for_update=True, populate_existing=True)
            row.data = {**row.data, **update}
            db.commit()
            done += 1
    return done
