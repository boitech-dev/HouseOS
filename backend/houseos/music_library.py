"""User-owned playlists, explicit local-audio sharing, and bounded guest skip votes."""

from datetime import timedelta
from pathlib import Path
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from typing import Annotated
from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import Input, Actor, require_actor, require_permission, user_permissions, delegated_user
from .db import get_db, new_id, utcnow, SessionLocal
from .models import Record, Operation, User, SessionToken, Job
from .music import (
    router,
    queue,
    QueueItem,
    canonical_source,
    activate_added,
    source_metadata,
    source_genres,
)
from .config import settings
from .events import emit
from .playback import media_command, MEDIA_ENV, run_media_command, MediaError


PLAYLIST_SONGS = 500


class NamedPlaylist(Input):
    name: str = Field(min_length=1, max_length=120)
    item_ids: list[str] = Field(default_factory=list, max_length=PLAYLIST_SONGS)
    source_urls: list[Annotated[str, Field(max_length=2048)]] = Field(
        default_factory=list, max_length=PLAYLIST_SONGS
    )


class PlaylistEdit(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_urls: list[Annotated[str, Field(max_length=2048)]] | None = Field(
        default=None, max_length=PLAYLIST_SONGS
    )  # new order


class PlaylistSong(Input):
    source_url: str = Field(max_length=2000)


class PlaylistQueue(Input):
    ids: list[str] = Field(min_length=1, max_length=20)
    shuffle: bool = False


def playlist_json(row):
    return {"id": row.id, "version": row.version, **row.data}


def own_playlist(db, actor, identity, lock=False):
    """Playlists are private: someone else's reads as missing."""
    query = select(Record).where(
        Record.id == identity,
        Record.kind == "music.playlist",
        Record.owner_id == actor.id,
        Record.deleted_at.is_(None),
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        raise HTTPException(404, "Playlist not found")
    return row


def playlist_songs(db, urls, known=()):
    """Validated songs in order, once each, keeping titles already known."""
    titles = {song["source_url"]: song.get("title") for song in known}
    order = list(dict.fromkeys(canonical_source(url) for url in urls))
    if any(not url.startswith("https://") for url in order):
        raise HTTPException(422, "Playlists hold YouTube or SoundCloud songs")
    found = source_metadata(db, [url for url in order if not titles.get(url)])
    return [
        {"source_url": url, "title": (titles.get(url) or found.get(url, {}).get("title") or "")[:500]}
        for url in order
    ]


@router.get("/library/playlists")
def playlists(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    return {
        "items": [
            playlist_json(row)
            for row in db.scalars(
                select(Record)
                .where(
                    Record.kind == "music.playlist", Record.owner_id == actor.id, Record.deleted_at.is_(None)
                )
                .order_by(Record.updated_at.desc())
                .limit(100)
            )
        ]
    }


@router.post("/library/playlists")
def save_playlist(body: NamedPlaylist, actor=Depends(require_actor), db=Depends(get_db)):
    """A new playlist: empty, from queue entries, or from song links."""
    require_permission(actor, "music.queue")
    items = []
    for identity in body.item_ids:
        item = db.get(QueueItem, identity)
        if not item or not item.source_url.startswith("https://"):
            raise HTTPException(
                422, "Saved playlists currently support validated YouTube/SoundCloud queue items"
            )
        items.append({"source_url": canonical_source(item.source_url), "title": item.title[:500]})
    items = playlist_songs(db, [x["source_url"] for x in items] + body.source_urls, items)
    row = new_playlist(db, actor, body.name, items)
    db.commit()
    return playlist_json(row)


def new_playlist(db, actor, name, items):
    if len(items) > PLAYLIST_SONGS:
        raise HTTPException(422, "A playlist holds up to 500 songs")
    db.scalar(select(User).where(User.id == actor.id).with_for_update())  # one count at a time
    existing = db.scalars(
        select(Record.id).where(
            Record.kind == "music.playlist", Record.owner_id == actor.id, Record.deleted_at.is_(None)
        )
    ).all()
    if len(existing) >= 100:
        raise HTTPException(409, "Playlist limit reached")
    row = Record(kind="music.playlist", owner_id=actor.id, data={"name": name.strip()[:120], "items": items})
    db.add(row)
    db.flush()
    return row


class PlaylistImport(Input):
    url: str = Field(max_length=2048)
    name: str | None = Field(default=None, max_length=120)


@router.post("/library/playlists/import")
def import_as_playlist(body: PlaylistImport, actor=Depends(require_actor), db=Depends(get_db)):
    """A YouTube or SoundCloud playlist kept as a house playlist: its first 50 songs now, the
    rest in the background. Songs the house already keeps play from its own copy; the others
    download the first time they play (and stay, when the house keeps songs)."""
    require_permission(actor, "music.queue")
    from .music import PLAYLIST_PAGE, playlist_source
    from .worker import fetch

    source = playlist_source(body.url)
    page = fetch("playlist", source)
    if page.get("status") != "completed":
        raise HTTPException(503, page.get("code") or "PLAYLIST_UNAVAILABLE")
    songs = page.get("items", [])
    name = (body.name or page.get("title") or "Imported playlist").strip() or "Imported playlist"
    row = new_playlist(db, actor, name, playlist_songs(db, [song["source_url"] for song in songs], songs))
    total = page["total"] if isinstance(page.get("total"), int) else len(songs)
    if len(songs) >= PLAYLIST_PAGE and total > PLAYLIST_PAGE:
        op = Operation(
            actor_id=actor.id,
            kind="music.playlist",
            state="running",
            data={"source_url": source, "total": total},
            result={"added": len(songs), "total": total},
        )
        db.add(op)
        db.flush()
        db.add(
            Job(
                logical_key="playlist:" + op.id + ":" + str(PLAYLIST_PAGE + 1),
                kind="music.playlist_import",
                actor_id=actor.id,
                payload={
                    "operation_id": op.id,
                    "source_url": source,
                    "start": PLAYLIST_PAGE + 1,
                    "session_hash": actor.session_hash,
                    "playlist_id": row.id,
                },
            )
        )
    db.commit()
    return {**playlist_json(row), "total": total, "unavailable": page.get("unavailable", 0)}


def swap_in_playlist(db, actor, identity, old, new):
    """A song replaced where it stood (a removed video's other version). Quietly nothing when
    the playlist is gone or no longer holds it."""
    row = db.scalar(
        select(Record)
        .where(Record.id == identity, Record.kind == "music.playlist", Record.owner_id == actor.id)
        .where(Record.deleted_at.is_(None))
        .with_for_update()
    )
    urls = [song["source_url"] for song in row.data["items"]] if row else []
    if old not in urls:
        return
    urls[urls.index(old)] = new
    known = [song for song in row.data["items"] if song["source_url"] != old]
    row.data, row.version = {**row.data, "items": playlist_songs(db, urls, known)}, row.version + 1


def append_to_playlist(db, identity, owner_id, songs):
    """An import's next page, added at the end of its playlist. Returns (added, full)."""
    row = db.scalar(
        select(Record)
        .where(
            Record.id == identity,
            Record.kind == "music.playlist",
            Record.owner_id == owner_id,
            Record.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not row:
        return 0, True
    known = row.data["items"]
    urls = [song["source_url"] for song in known + songs]
    merged = playlist_songs(db, urls, known + songs)[:PLAYLIST_SONGS]
    row.data, row.version = {**row.data, "items": merged}, row.version + 1
    return len(merged) - len(known), len(merged) >= PLAYLIST_SONGS


@router.get("/library/playlists/{identity}")
def playlist_detail(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    """One playlist with each song's art, length and genre."""
    require_permission(actor, "music.read")
    row = own_playlist(db, actor, identity)
    from .music_downloads import KIND, identity as kept_id

    sources = [song["source_url"] for song in row.data["items"]]
    metadata, genres = source_metadata(db, sources), source_genres(db, sources)
    ids = {source: kept_id(source) for source in sources}
    home = set(
        db.scalars(
            select(Record.id).where(
                Record.id.in_(list(ids.values())),
                Record.kind == KIND,
                Record.deleted_at.is_(None),
                Record.data["state"].as_string() == "ready",
            )
        )
    )
    return {
        **playlist_json(row),
        "items": [
            {
                **metadata.get(song["source_url"], {}),
                **song,
                "genre": genres.get(song["source_url"]),
                "at_home": ids[song["source_url"]] in home,  # plays from the house's own copy
            }
            for song in row.data["items"]
        ],
    }


@router.patch("/library/playlists/{identity}")
def edit_playlist(identity: str, body: PlaylistEdit, actor=Depends(require_actor), db=Depends(get_db)):
    """Rename, and/or give the songs in their new order (leaving one out removes it)."""
    require_permission(actor, "music.queue")
    row = own_playlist(db, actor, identity, lock=True)
    if row.version != body.expected_version:
        raise HTTPException(409, "This playlist changed; reload it")
    data = dict(row.data)
    if body.name is not None:
        data["name"] = body.name.strip()
    if body.source_urls is not None:
        data["items"] = playlist_songs(db, body.source_urls, row.data["items"])
    row.data, row.version = data, row.version + 1
    db.commit()
    return playlist_json(row)


@router.post("/library/playlists/{identity}/songs")
def add_to_playlist(identity: str, body: PlaylistSong, actor=Depends(require_actor), db=Depends(get_db)):
    """Adds one song at the end; a song already there stays where it is."""
    require_permission(actor, "music.queue")
    row = own_playlist(db, actor, identity, lock=True)
    known = row.data["items"]
    songs = playlist_songs(db, [song["source_url"] for song in known] + [body.source_url], known)
    if len(songs) > PLAYLIST_SONGS:
        raise HTTPException(409, "A playlist holds up to 500 songs")
    added = len(songs) > len(row.data["items"])
    if added:
        row.data, row.version = {**row.data, "items": songs}, row.version + 1
        db.commit()
    return {"status": "completed", "added": added, **playlist_json(row)}


def prepare_playlists(db, actor, ids, shuffle=False):
    """Review before queueing: the songs of these playlists, once each, up to 500. Confirming
    (/music/playlists/{id}/confirm) queues them fairly under the usual limits."""
    import random

    require_permission(actor, "music.queue")
    rows = [own_playlist(db, actor, identity) for identity in dict.fromkeys(ids)]
    songs = list(
        {
            song["source_url"]: {**song, "playlist_id": row.id}  # a song that's gone can be swapped there
            for row in rows
            for song in row.data["items"]
        }.values()
    )
    if not songs:
        raise HTTPException(422, "These playlists have no songs yet")
    if shuffle:
        random.shuffle(songs)
    op = Operation(
        actor_id=actor.id,
        kind="music.playlist",
        state="needs_confirmation",
        data={"items": songs[:PLAYLIST_SONGS]},
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "names": [row.data["name"] for row in rows],
        "items": op.data["items"],
        "total": len(songs),
        "maximum": PLAYLIST_SONGS,
    }


@router.post("/library/playlists/queue")
def queue_playlists(body: PlaylistQueue, actor=Depends(require_actor), db=Depends(get_db)):
    return prepare_playlists(db, actor, body.ids, body.shuffle)


@router.post("/library/playlists/{identity}/preview")
def playlist_preview(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    return prepare_playlists(db, actor, [identity])


@router.delete("/library/playlists/{identity}")
def delete_playlist(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    own_playlist(db, actor, identity, lock=True).deleted_at = utcnow()
    db.commit()
    return {"status": "completed"}


class LocalPreview(Input):
    file_id: str = Field(max_length=36)
    idempotency_key: str = Field(min_length=8, max_length=100)


def local_entry(db, actor, identity):
    from .files import accessible_entry

    entry = accessible_entry(db, actor, identity)
    if entry.is_folder or not entry.mime.startswith("audio/") or entry.size > 500 * 1024**2:
        raise HTTPException(422, "Choose a finalized audio file up to 500 MiB")
    return entry


@router.post("/local/preview")
def local_preview(body: LocalPreview, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    entry = local_entry(db, actor, body.file_id)
    old = db.scalar(
        select(Operation).where(
            Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
        )
    )
    if old:
        if old.kind != "music.local" or old.data.get("file_id") != body.file_id:
            raise HTTPException(409, "Idempotency key already used")
        return {"status": old.state, "confirmation_id": old.id, "preview": old.result}
    preview = {
        "title": entry.name,
        "size": entry.size,
        "effect": "Play this file on the shared household speakers. Its title and sound become visible/audible to others; file access permissions stay unchanged.",
    }
    op = Operation(
        actor_id=actor.id,
        kind="music.local",
        state="needs_confirmation",
        data={"file_id": entry.id, "version": entry.version},
        result=preview,
        idempotency_key=body.idempotency_key,
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db.add(op)
    db.commit()
    return {"status": op.state, "confirmation_id": op.id, "preview": preview}


@router.post("/local/{identity}/confirm")
def local_confirm(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    q = queue(db)
    op = db.scalar(
        select(Operation)
        .where(Operation.id == identity, Operation.actor_id == actor.id, Operation.kind == "music.local")
        .with_for_update()
    )
    if not op or op.state != "needs_confirmation" or op.expires_at <= utcnow():
        raise HTTPException(409, "Local-audio preview expired or consumed")
    entry = local_entry(db, actor, op.data["file_id"])
    if entry.version != op.data["version"]:
        raise HTTPException(409, "File changed; prepare again")
    pending = db.scalars(
        select(QueueItem).where(
            QueueItem.status.in_(
                [
                    "pending_metadata",
                    "ready",
                    "resolving",
                    "playing",
                    "paused",
                    "buffering",
                    "awaiting_confirmation",
                ]
            )
        )
    ).all()
    if (
        len(pending) >= 500
        or actor.role == "guest"
        and sum(item.owner_id == actor.id for item in pending) >= 10
    ):
        raise HTTPException(409, "Queue limit reached")
    item = QueueItem(
        id=new_id(),
        owner_id=actor.id,
        source_url="houseos-file:" + entry.id,
        title=entry.name,
        status="ready",
        position=max([x.position for x in pending], default=0) + 1,
        metadata_json={
            "file_version": entry.version,
            "session_hash": actor.session_hash,
            "local_approved": True,
        },
    )
    db.add(item)
    db.flush()
    auto = activate_added(db, q, [item], pending)
    op.state, op.result = "completed", {"item_id": item.id, "autoplay_requested": auto}
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {"status": "completed", "item_id": item.id, "autoplay_requested": auto}


def authorized_local(db, item):
    token_hash = item.metadata_json.get("session_hash")
    user = delegated_user(db, item.owner_id, token_hash, "music.queue")
    if not user:
        raise HTTPException(403, "Local playback authorization expired")
    actor = Actor(user.id, user.name, user.role, frozenset(user_permissions(user)), token_hash)
    entry = local_entry(db, actor, item.source_url.removeprefix("houseos-file:"))
    if not item.metadata_json.get("local_approved") or entry.version != item.metadata_json.get(
        "file_version"
    ):
        raise HTTPException(409, "File changed after playback preview")
    return entry


def stage_local_audio(item_id):
    from .files import subdir_fd

    try:
        with SessionLocal() as db:
            item = db.get(QueueItem, item_id)
            if not item or item.status != "resolving":
                return {"status": "cancelled", "code": "QUEUE_CHANGED"}
            entry = authorized_local(db, item)
            size, checksum = entry.size, entry.checksum
            with subdir_fd("blobs") as directory:
                fd = os.open(entry.id, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            actual = os.fstat(fd)
            if not stat.S_ISREG(actual.st_mode) or actual.st_size != size:
                os.close(fd)
                raise OSError("invalid file")
        root = settings.runtime_root / "audio"
        root.mkdir(parents=True, exist_ok=True)
        if (
            shutil.disk_usage(root).free < 4 * 1024**3
            or sum(path.stat().st_size for path in root.iterdir() if path.is_file()) > 10 * 1024**3
        ):
            os.close(fd)
            return {"status": "failed", "code": "AUDIO_CACHE_FULL"}
        with tempfile.TemporaryDirectory(prefix="local-", dir=root) as temp:
            source, output = Path(temp) / "source.bin", Path(temp) / "output.flac"
            digest = hashlib.sha256()
            with os.fdopen(fd, "rb") as incoming, source.open("xb") as outgoing:
                total = 0
                for chunk in iter(lambda: incoming.read(1024**2), b""):
                    total += len(chunk)
                    if total > size:
                        raise OSError("file changed")
                    digest.update(chunk)
                    outgoing.write(chunk)
            if total != size or checksum and digest.hexdigest() != checksum:
                raise OSError("file changed")
            inspected = subprocess.run(
                media_command(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-protocol_whitelist",
                        "file",
                        "-format_whitelist",
                        "mp3,wav,flac,ogg,mov,matroska,webm,aac",
                        "-show_format",
                        "-of",
                        "json",
                        str(source),
                    ],
                    source,
                ),
                capture_output=True,
                timeout=20,
                check=True,
                env=MEDIA_ENV,
            )
            duration = float(json.loads(inspected.stdout).get("format", {}).get("duration") or 0)
            if not 0 < duration <= 14400:
                return {"status": "failed", "code": "LOCAL_AUDIO_DURATION_UNSUPPORTED"}
            args = [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-protocol_whitelist",
                "file",
                "-format_whitelist",
                "mp3,wav,flac,ogg,mov,matroska,webm,aac",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-c:a",
                "flac",
                "-sample_fmt",
                "s16",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(output),
            ]
            run_media_command(media_command(args, source, Path(temp)), timeout=180)
            with SessionLocal() as db:
                item = db.get(QueueItem, item_id)
                authorized_local(db, item)
                if item.status != "resolving":
                    return {"status": "cancelled", "code": "QUEUE_CHANGED"}
            os.chmod(output, 0o640)
            os.replace(output, root / (item_id + ".media"))
        return {"status": "completed"}
    except (HTTPException, OSError, ValueError, MediaError, subprocess.SubprocessError):
        return {"status": "failed", "code": "LOCAL_AUDIO_UNAVAILABLE"}


class QueueRevision(Input):
    expected_version: int = Field(ge=1)


def valid_skip_votes(db, item_id):
    votes = db.scalars(
        select(Record).where(
            Record.kind == "music.skip_vote",
            Record.created_at > utcnow() - timedelta(minutes=5),
            Record.deleted_at.is_(None),
        )
    ).all()
    result = []
    for vote in votes:
        if vote.data.get("item_id") != item_id:
            continue
        user = db.get(User, vote.owner_id)
        token = db.get(SessionToken, vote.data["session_hash"]) if vote.data.get("session_hash") else None
        if (
            user
            and user.active
            and (not user.expires_at or user.expires_at > utcnow())
            and "music.queue" in user_permissions(user)
            and (
                not vote.data.get("session_hash")
                or token
                and token.user_id == user.id
                and token.expires_at > utcnow()
            )
        ):
            result.append(vote)
    return result


@router.post("/queue/{identity}/skip-vote")
def skip_vote(identity: str, body: QueueRevision, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    q = queue(db)
    if q.current_id != identity or q.version != body.expected_version:
        raise HTTPException(409, "Current track changed")
    votes = valid_skip_votes(db, identity)
    if not any(vote.owner_id == actor.id for vote in votes):
        vote = Record(
            kind="music.skip_vote",
            owner_id=actor.id,
            data={"item_id": identity, "session_hash": actor.session_hash},
        )
        db.add(vote)
        db.flush()
        votes.append(vote)
    existing = db.scalar(
        select(Operation).where(
            Operation.kind == "music.vote_skip", Operation.idempotency_key == "vote-skip:" + identity
        )
    )
    if len(votes) >= 3 and not existing:
        op = Operation(
            id=new_id(),
            actor_id=actor.id,
            kind="music.vote_skip",
            state="accepted",
            data={"item_id": identity},
            idempotency_key="vote-skip:" + identity,
        )
        db.add(op)
        db.add(
            Job(
                logical_key="control:" + op.id,
                kind="music.control",
                actor_id=actor.id,
                payload={
                    "operation_id": op.id,
                    "action": "skip",
                    "value": None,
                    "current_id": identity,
                    "session_hash": actor.session_hash,
                    "vote_threshold": True,
                },
            )
        )
        existing = op
    emit(db, "music.skip_votes", {"item_id": identity, "votes": len(votes), "threshold": 3})
    db.commit()
    return {
        "status": "accepted" if existing else "awaiting_votes",
        "votes": len(votes),
        "threshold": 3,
        "operation_id": existing.id if existing else None,
    }


def authorized_vote_job(db, job):
    op = db.get(Operation, job.payload.get("operation_id"))
    return bool(
        op
        and op.kind == "music.vote_skip"
        and op.data.get("item_id") == job.payload.get("current_id")
        and job.payload.get("action") == "skip"
        and len(valid_skip_votes(db, op.data["item_id"])) >= 3
    )


@router.post("/queue/{identity}/approve-live")
def approve_live(identity: str, body: QueueRevision, actor=Depends(require_actor), db=Depends(get_db)):
    import time

    require_permission(actor, "music.queue")
    q = queue(db)
    item = db.get(QueueItem, identity)
    if not item:
        raise HTTPException(404, "Queue item not found")
    if item.owner_id != actor.id and "music.control" not in actor.permissions and actor.role != "admin":
        raise HTTPException(403, "Only the person who added this stream can allow it")
    if (
        q.version != body.expected_version
        or item.status != "awaiting_confirmation"
        or not item.metadata_json.get("is_live")
    ):
        raise HTTPException(409, "Live-stream preview changed or is unavailable")
    item.metadata_json = {**item.metadata_json, "live_authorized_until": time.time() + 3600}
    item.status, item.error_code = "ready", None
    q.version += 1
    emit(db, "music.queue_changed", {"version": q.version})
    db.commit()
    return {
        "status": "completed",
        "version": q.version,
        "maximum_live_seconds": 3600,
        "maximum_bytes": 400 * 1024**2,
        "seeking": False,
    }


@router.post("/queue/{identity}/renew-live")
def renew_live(identity: str, body: QueueRevision, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.control")
    q = queue(db)
    item = db.get(QueueItem, identity)
    if (
        q.version != body.expected_version
        or q.current_id != identity
        or not item
        or not item.metadata_json.get("is_live")
        or item.status not in {"playing", "paused", "buffering"}
    ):
        raise HTTPException(409, "Live session changed or is not active")
    db.rollback()
    from .worker import fetch

    return fetch("live_renew", item_id=identity)
