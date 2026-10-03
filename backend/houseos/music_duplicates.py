"""Songs the house kept twice: two links to one song (the video, a lyrics upload, a remaster),
told apart by code from their titles, channels and lengths. An admin keeps one; "not
duplicates" is remembered so the same songs aren't flagged again.

The music catalogue keeps no canonical track id (Deezer's genres and cover only), so titles
and lengths are all there is to compare."""

import logging
import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .events import emit
from .models import Record
from .music_genre import artist_and_track, channel_artist, fold

KIND = "music.duplicates"  # one per group: flagged once, and `dismissed` when not duplicates
SECONDS = 4  # two uploads of one song differ by an intro or a silence, not more
# What uploads add around a title outside brackets (brackets and "feat." go in `clean`).
NOISE = re.compile(
    r"\b(official\s+(music\s+)?video|official\s+audio|official\s+lyric\s+video|lyric\s+video"
    r"|music\s+video|lyrics|visuali[sz]er|(\d{4}\s+)?remaster(ed)?(\s+\d{4})?(\s+version)?|hd|hq|4k)\b",
    re.I,
)


def forms(song):
    """The (artist, track, swapped) readings of a kept song's title: "A - T" is read both ways."""
    title = NOISE.sub("", song.get("title") or "")
    named, track = artist_and_track(title)  # an artist only when the title says "A - T"
    if named:
        return [(fold(named), fold(track), False), (fold(track), fold(named), True)]
    return [(fold(channel_artist(song.get("uploader"))), fold(track), False)]


def same_song(a, b):
    """Possibly one song: the same track by the same artist (named in the title, else the
    channel's) when both are known, and lengths within a few seconds when both are known."""
    if a.get("duration") and b.get("duration") and abs(float(a["duration"]) - float(b["duration"])) > SECONDS:
        return False
    for artist_a, track_a, swapped_a in forms(a):
        for artist_b, track_b, swapped_b in forms(b):
            if track_a and track_a == track_b:
                # A swapped reading ("Track - Artist") only counts with the artist it swapped to.
                if artist_a == artist_b or not (swapped_a or swapped_b or (artist_a and artist_b)):
                    return True
    return False


def group_key(ids):
    return str(uuid5(NAMESPACE_URL, "houseos-duplicates:" + ",".join(sorted(ids))))


def groups(songs, apart=()):
    """Groups of possible duplicates (A~B, B~C: one group), biggest first. Songs are dicts with
    id, title, uploader, duration; `apart` are id sets an admin said aren't duplicates."""
    by_track = {}
    for index, song in enumerate(songs):
        for track in {form[1] for form in forms(song)}:
            by_track.setdefault(track, []).append(index)
    parent = list(range(len(songs)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for track, found in by_track.items():
        for n, i in enumerate(found):
            for j in found[n + 1 :]:
                pair = {songs[i]["id"], songs[j]["id"]}
                if track and not any(pair <= set(ids) for ids in apart) and same_song(songs[i], songs[j]):
                    parent[root(i)] = root(j)
    together = {}
    for i in range(len(songs)):
        together.setdefault(root(i), []).append(songs[i])
    return sorted((g for g in together.values() if len(g) > 1), key=len, reverse=True)


def dismissed(db):
    return [
        row.data.get("ids") or []
        for row in db.scalars(select(Record).where(Record.kind == KIND, Record.deleted_at.is_(None)))
        if row.data.get("dismissed")
    ]


def kept(db):
    rows = db.execute(
        select(Record.id, Record.data).where(
            Record.kind == "music.download",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string() == "ready",
        )
    ).all()
    return [
        {"id": identity, **{k: data.get(k) for k in ("title", "uploader", "duration")}}
        for identity, data in rows
    ]


def flag(db, song_id, owner_id):
    """A song was just kept: one quiet notice (a record and a line in the diary) the first time
    its group of duplicates exists. Never raises: keeping the song matters more."""
    try:
        group = next((g for g in groups(kept(db), dismissed(db)) if any(s["id"] == song_id for s in g)), None)
        if not group or db.get(Record, group_key([s["id"] for s in group])):
            return
        title = next(s["title"] for s in group if s["id"] == song_id) or "a song"
        ids = sorted(s["id"] for s in group)
        db.add(Record(id=group_key(ids), kind=KIND, owner_id=owner_id, visibility="house", data={"ids": ids}))
        emit(db, "music.duplicate_kept", {"title": title, "ids": ids})
        db.commit()
    except Exception:  # noqa: BLE001 - a notice never fails the retention that called it
        db.rollback()
        logging.getLogger(__name__).exception("Duplicate check failed")
