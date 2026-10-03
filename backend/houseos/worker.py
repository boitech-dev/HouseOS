from . import ipc
import threading
import time
from collections import defaultdict
from threading import Lock, RLock
from datetime import timedelta
from sqlalchemy import select, or_, and_, case, text
from .db import SessionLocal, utcnow, new_id, engine
from .models import Job, Operation, Record
from .music import UNNAMED, QueueItem, QueueState, bridge
from .auth import delegated_user
from .config import settings
from .events import emit, heartbeat
from .music_genre import genre_of

LEASE_CONNECTION_ID = None
PLAYER_COMMANDS = RLock()
# The audio bridge serves one client at a time; a state poll can time out while UI polls
# queue behind it. Pause only after consecutive misses, not on one busy moment.
BRIDGE_MISS_LIMIT = 3
bridge_misses = 0
AUDIO_DOWNLOADS = RLock()  # the fetcher downloads one song at a time
# ponytail: one small lock per song ever prepared (a few KB a year); a bounded map if that matters.
SONG_LOCKS: dict[str, Lock] = defaultdict(Lock)


def job_authorized(db, job):
    from .auth import user_permissions

    user = delegated_user(db, job.actor_id, job.payload.get("session_hash"))
    if not user:
        return False
    if job.kind == "service.restart":
        return user.role == "admin"
    if job.kind == "music.control" and job.payload.get("vote_threshold"):
        from .music_library import authorized_vote_job

        return authorized_vote_job(db, job)
    capability = "music.queue" if job.kind in {"music.metadata", "music.playlist_import"} else "music.control"
    return user.role == "admin" or capability in user_permissions(user)


def cached_music(source, item_id):
    """Reuse complete, previously observed shared music, never expiring stream URLs."""
    if not source or not source.startswith(("https://www.youtube.com/", "https://soundcloud.com/")):
        return None
    from .music_downloads import restore

    with SessionLocal() as db:
        known = remembered(db, source)
        item = db.get(QueueItem, item_id)
        staged = settings.runtime_root / "audio" / (item_id + ".media")
        if item and item.metadata_json.get("downloaded") and staged.is_file():  # preloaded already
            meta = item.metadata_json
            return {
                "status": "completed",
                "bytes": staged.stat().st_size,
                "retained": bool(meta.get("retained")),
                "title": item.title,
                "source_url": source,
                **{key: meta.get(key) for key in ("duration", "uploader")},
                **known,
            }
        retained = restore(db, source, item_id)
        if retained:
            return {**known, **retained}
        rows = list(
            db.scalars(
                select(QueueItem)
                .where(
                    QueueItem.source_url == source,
                    QueueItem.metadata_json["history_recorded"].as_boolean() == True,
                )
                .order_by(QueueItem.created_at.desc())
                .limit(20)
            )
        )
    for previous in rows:
        if previous.metadata_json.get("is_live"):
            continue
        result = fetch("reuse", item_id=item_id, cached_item_id=previous.id)
        if result.get("status") == "completed":
            return {
                **result,
                "title": previous.title,
                "source_url": source,
                "duration": previous.metadata_json.get("duration"),
                "uploader": previous.metadata_json.get("uploader"),
                **known,
            }
    return None


def remembered(db, source):
    """Artwork, artist and genre from an earlier play: a song replayed from the house's own copy
    skips the internet lookup, so it would otherwise lose them."""
    for previous in db.scalars(
        select(QueueItem)
        .where(QueueItem.source_url == source)
        .order_by(QueueItem.created_at.desc())
        .limit(20)
    ):
        meta = previous.metadata_json
        if meta.get("thumbnail"):
            return {
                "thumbnail": meta["thumbnail"],
                **({"artist": meta["artist"]} if meta.get("artist") else {}),
                **({"genre": meta["genre"]} if meta.get("genre") not in (None, "other") else {}),
            }
    return {}


def fetch(action, source_url=None, item_id=None, **extra):
    timeout = 320 if action == "download" else 2 if action == "cancel_download" else 55
    return ipc.fetcher(action, timeout=timeout, source_url=source_url, item_id=item_id, **extra)


def preparation_window(db, limit=2):
    """Current plus next two tracks, using the same fair order as playback."""
    from .music import pending_order, ACTIVE_QUEUE_STATUSES

    q = db.get(QueueState, 1)
    if not q:
        return []
    rows = list(
        db.scalars(
            select(QueueItem).where(QueueItem.status.in_(ACTIVE_QUEUE_STATUSES)).order_by(QueueItem.position)
        )
    )
    current = next((item for item in rows if item.id == q.current_id), None)
    upcoming = pending_order(db, q, rows)
    return ([current] if current else []) + (
        upcoming if limit is None else upcoming[: limit if current else limit + 1]
    )


def claim(owner, kinds=("music.metadata", "music.control", "service.restart")):
    if (settings.runtime_root / "run/shutdown.json").exists():
        return None
    with SessionLocal() as db:
        now = utcnow()
        eligible = (
            [item.id for item in preparation_window(db, limit=None)] if "music.metadata" in kinds else []
        )
        # Songs are looked up in play order: after a playlist import, the next song to play (or one
        # someone just added ahead) never waits behind the whole playlist.
        order = [Job.next_run]
        if eligible:
            rank = {"metadata:" + item_id: i for i, item_id in enumerate(eligible)}
            order.insert(0, case(rank, value=Job.logical_key, else_=len(rank)))
        job = db.scalar(
            select(Job)
            .where(
                Job.kind.in_(kinds),
                Job.next_run <= now,
                or_(Job.kind != "music.metadata", Job.payload["item_id"].as_string().in_(eligible)),
                or_(Job.state == "pending", and_(Job.state == "running", Job.lease_until < now)),
            )
            .order_by(*order)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        if job.state == "running" and job.kind != "music.metadata":
            job.state, job.error_code = "unverified", "INTERRUPTED_RECONCILE_BEFORE_RETRY"
            db.commit()
            return None
        if not job_authorized(db, job):
            job.state, job.error_code = "cancelled", "ACTOR_REVOKED"
            fail_pending_item(db, job)
            db.commit()
            return None
        job.state, job.lease_owner, job.lease_until = "running", owner, now + timedelta(minutes=7)
        job.generation += 1
        job.attempts += 1
        result = (job.id, job.generation, job.kind, dict(job.payload))
        db.commit()
        return result


# The fetcher was momentarily busy or restarting: worth another try, not a failure.
TEMPORARY = {"SOURCE_BUSY", "FETCH_UNAVAILABLE", "YOUTUBE_RATE_LIMITED", "SOURCE_TIMEOUT"}


def fail_pending_item(db, job):
    if job.kind == "music.metadata":
        item = db.get(QueueItem, job.payload.get("item_id"))
        if item and item.status == "pending_metadata":
            item.status, item.error_code = "failed", job.error_code
            emit(db, "music.metadata", {"item_id": item.id, "status": item.status})


def run_job(job):
    if job[2] == "music.control":
        # Serialize command preflight through acknowledgement against prepared loads.
        # Queue additions can proceed, but cannot load a new song between clear's check and stop.
        with PLAYER_COMMANDS:
            return _run_job(job)
    return _run_job(job)


def _run_job(job):
    if (settings.runtime_root / "run/shutdown.json").exists():
        return
    job_id, generation, kind, data = job
    with SessionLocal() as db:
        row = db.get(Job, job_id)
        if not row or row.generation != generation or row.state != "running":
            return
        if not job_authorized(db, row):
            row.state, row.error_code = "cancelled", "AUTHORIZATION_CHANGED"
            fail_pending_item(db, row)
            db.commit()
            return
        if kind == "music.control" and data["action"] == "volume":
            from .house_settings import get_house_settings

            cap = get_house_settings(db)["music_volume_cap"]
            data["value"] = min(data.get("value") or 0, cap)
            q = db.get(QueueState, 1)
            if q and data["value"] != min(q.volume, cap):
                row.state, row.error_code = "cancelled", "VOLUME_SUPERSEDED"
                operation = db.get(Operation, data.get("operation_id")) if data.get("operation_id") else None
                if operation:
                    operation.state, operation.result = "cancelled", {"code": "VOLUME_SUPERSEDED"}
                db.commit()
                return
        if kind == "music.control" and data["action"] in {"skip", "seek", "play", "clear", "stop"}:
            q = db.get(QueueState, 1)
            # A skip already took its song out of the queue (music.control_effect): stop the player.
            skipped = (
                data["action"] == "skip" and data.get("current_id") and db.get(QueueItem, data["current_id"])
            )
            if (not q or q.current_id != data.get("current_id")) and not (
                skipped and skipped.status == "skipped"
            ):
                row.state, row.error_code = "cancelled", "PLAYBACK_GENERATION_CHANGED"
                operation = db.get(Operation, data.get("operation_id")) if data.get("operation_id") else None
                if operation:
                    operation.state, operation.result = "cancelled", {"code": "PLAYBACK_GENERATION_CHANGED"}
                db.commit()
                return
    result = {"status": "failed", "code": "UNSUPPORTED_JOB"}
    if kind == "music.metadata":
        with SessionLocal() as db:
            item = db.get(QueueItem, data["item_id"])
            source = item.source_url if item and item.status == "pending_metadata" else None
        result = (
            (cached_music(source, data["item_id"]) or fetch("metadata", source))
            if source
            else {"status": "cancelled"}
        )
    elif kind == "music.control":
        action = data["action"]
        if action == "previous":
            result = {
                "status": "accepted",
                "message": "Previous track is preparing; query playback for observation",
            }
        elif action in {"sleep", "repeat"}:
            result = {"status": "completed"}
        elif action == "clear":
            result = bridge("stop")
            if data.get("current_id") and result.get("status") == "command_sent":
                fetch("live_stop", item_id=data["current_id"])
            if result.get("status") == "command_sent":
                observed = bridge("state")
                result = (
                    {"status": "completed", "stop_observed": True}
                    if observed.get("status") == "observed" and observed.get("idle") is True
                    else {"status": "unverified", "code": "STOP_NOT_OBSERVED"}
                )
        elif action in {"skip", "stop"}:
            # A fast skip may find the next song already loaded: only the skipped one is stopped.
            loaded = bridge("state").get("item_id") if action == "skip" else data.get("current_id")
            result = bridge("stop") if loaded == data.get("current_id") else {"status": "completed"}
            if data.get("current_id") and result.get("status") in {"command_sent", "completed"}:
                fetch("live_stop", item_id=data["current_id"])
        else:
            result = bridge(action, value=data.get("value"))
    elif kind == "service.restart":
        from .control_room import broker
        from .cinema import CinemaWorkflow

        with SessionLocal() as db:
            q = db.get(QueueState, 1)
            active = db.scalar(
                select(CinemaWorkflow.id)
                .where(CinemaWorkflow.state.in_(["playing_observed", "paused", "preparing", "command_sent"]))
                .limit(1)
            )
            if active or q and q.desired == "playing":
                result = {"status": "failed", "code": "MEDIA_ACTIVITY_CHANGED"}
            else:
                before = broker("status", data["service"])
                if before.get("status") != "observed":
                    result = {"status": "failed", "code": "SERVICE_BROKER_UNAVAILABLE"}
                else:
                    op = db.get(Operation, data["operation_id"])
                    op.data = {**op.data, "invocation_before": before.get("invocation_id")}
                    op.state = "executing"
                    db.commit()
                    result = broker("restart", data["service"])
    with SessionLocal() as db:
        row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not row or row.generation != generation or row.state != "running":
            return
        if kind == "music.metadata" and result.get("code") in TEMPORARY and row.attempts < 5:
            row.state, row.error_code = "pending", result["code"]
            row.next_run = utcnow() + timedelta(seconds=10 * row.attempts)
            db.commit()
            return
        row.state = (
            "completed" if result.get("status") in {"completed", "command_sent", "accepted"} else "failed"
        )
        row.error_code = result.get("code")
        if kind == "music.metadata":
            item = db.get(QueueItem, data["item_id"])
            if item and item.status == "pending_metadata":
                item.status = "ready" if result.get("status") == "completed" else "failed"
                item.metadata_json = {
                    **item.metadata_json,
                    **{k: result.get(k) for k in ("duration", "uploader", "is_live")},
                    **({"thumbnail": result["thumbnail"]} if result.get("thumbnail") else {}),
                }
                if result.get("title"):  # songs, and stations (they ask to be approved)
                    from .house_settings import get_house_settings

                    evidence = {
                        **({"genre": result["genre"]} if result.get("genre") else {}),
                        **({"tags": result["tags"][:15]} if result.get("tags") else {}),
                    }
                    item.metadata_json = {
                        **item.metadata_json,
                        "genre": genre_of(
                            {**result, "title": result.get("title") or item.title},
                            get_house_settings(db)["music_genres"],
                        ),
                        # What the source said, for music_catalog and later house genres.
                        **({"genre_evidence": evidence} if evidence else {}),
                        **({"artist": result["artist"]} if result.get("artist") else {}),
                    }
                if result.get("status") == "completed" and (result.get("duration") or 0) > 14400:
                    item.status, result["code"] = "failed", "TRACK_TOO_LONG"
                elif (
                    result.get("status") == "completed"
                    and (result.get("duration") or 0) > LONG_TRACK
                    and not result.get("bytes")
                ):
                    # Hours-long mixes stream straight to the speakers instead of downloading.
                    item.metadata_json = {**item.metadata_json, "long_stream": True}
                if result.get("code") == "LIVE_STREAM_REQUIRES_APPROVAL":
                    # Starting a radio station is the request; other live streams ask first.
                    approved = item.metadata_json.get("live_approved")
                    item.status = "ready" if approved else "awaiting_confirmation"
                    result = {**result, "code": None} if approved else result
                duration = result.get("duration")
                start = item.metadata_json.get("requested_start", 0)
                if result.get("status") == "completed" and start and duration and start >= duration:
                    item.status, result["code"] = "failed", "AUDIO_START_OUT_OF_RANGE"
                if result.get("is_live") and start:
                    item.status, result["code"] = "failed", "LIVE_SEEK_UNSUPPORTED"
                # A failure keeps the title the song was queued with (a search result's, a playlist's).
                item.title = result.get("title") or (
                    item.title if item.title != "Resolving source…" else "Source unavailable"
                )
                item.error_code = result.get("code")
                told = item.status
                if (
                    told == "failed"
                    and item.error_code == "SOURCE_REMOVED"
                    and not item.metadata_json.get("auto")
                ):
                    # Gone for good (removed or made private): out of the queue, into one quiet
                    # notice where its owner picks another version (GET /music/unavailable) -
                    # unless nothing names it: there is nothing to search another version by.
                    item.status = "removed"
                    if item.title not in UNNAMED:
                        db.add(
                            Record(
                                kind="music.unavailable",
                                owner_id=item.owner_id,
                                data={
                                    "title": item.title,
                                    "source_url": item.source_url,
                                    "playlist_id": item.metadata_json.get("playlist_id"),
                                },
                            )
                        )
                emit(db, "music.metadata", {"item_id": item.id, "status": told, "code": item.error_code})
        elif kind == "music.control":
            op = db.get(Operation, data["operation_id"])
            op.state = (
                "unverified" if result.get("status") == "command_sent" else result.get("status", "failed")
            )
            op.result = result
            if data["action"] == "clear" and result.get("stop_observed"):
                q = db.scalar(select(QueueState).where(QueueState.id == 1).with_for_update())
                if q and q.current_id == data.get("current_id"):
                    q.current_id = None
                    emit(db, "music.queue_changed", {"version": q.version})
            if data["action"] == "skip" and result.get("status") in {"command_sent", "completed"}:
                q = db.scalar(select(QueueState).where(QueueState.id == 1).with_for_update())
                if q and q.current_id == data.get("current_id"):
                    item = db.get(QueueItem, q.current_id) if q.current_id else None
                    if item:
                        item.status = "skipped"
                    q.current_id = None
                    q.version += 1
                    emit(db, "music.queue_changed", {"version": q.version})
        elif kind == "service.restart":
            op = db.get(Operation, data["operation_id"])
            op.state = "unverified" if result.get("status") == "accepted" else "failed"
            op.result = {
                "service": data["service"],
                "command_status": result.get("status"),
                "message": "Query service health to verify restart",
            }
        db.commit()


def item_authorized(db, item):
    return (
        delegated_user(db, item.owner_id, item.metadata_json.get("session_hash"), "music.queue") is not None
    )


def preparation_state(item_id, state, result=None):
    with SessionLocal() as db:
        item = db.get(QueueItem, item_id)
        if item and item.status != "removed":
            result = result or {}
            item.metadata_json = {
                **item.metadata_json,
                "download_state": state,
                "downloaded": state == "ready",
                "retained": bool(result.get("retained")),
                "retention_error": result.get("retention_error"),
            }
            emit(db, "music.metadata", {"item_id": item.id, "status": item.status})
            db.commit()


def paused_itself(db, code):
    """The house paused the music on its own: said in the log (why, and when it played again)."""
    emit(db, "music.paused_itself", {"status": "failed", "code": code})


def prepare_audio(source, item_id):
    # A song already at home is ready at once: only downloads wait for the one transfer lane, so
    # skipping to a preloaded song never waits behind a later song's download.
    with SONG_LOCKS[item_id]:
        with SessionLocal() as db:
            item = db.get(QueueItem, item_id)
            if not item or item.status == "removed" or not item_authorized(db, item):
                return {"status": "cancelled", "code": "DOWNLOAD_CANCELLED"}
        cached = cached_music(source, item_id)
        if cached:
            return ready_from_cache(source, item_id, cached)
        with AUDIO_DOWNLOADS:
            result = _prepare_audio(source, item_id)
        with SessionLocal() as db:
            item = db.get(QueueItem, item_id)
            if not item or item.status == "removed":
                fetch("cancel_download", item_id=item_id)
                return {"status": "cancelled", "code": "DOWNLOAD_CANCELLED"}
        return result


def ready_from_cache(source, item_id, cached):
    if not cached.get("retained"):
        from .music_downloads import retain

        cached.update(retain(source, item_id))
    preparation_state(item_id, "ready", cached)
    return cached


# Songs far ahead (after the next three) download one at a time with a pause after each new
# download: a long playlist preloaded at once (hundreds of downloads in an hour) makes YouTube ask
# the house to prove it isn't a bot. Songs already at home don't wait.
FAR_AHEAD, FAR_PACE, AUTO_AHEAD = 3, 40, 5
last_download = [0.0]


def preload_count(db):
    """How many songs to download ahead: the house's choice (None: the whole queue), at most 3
    when it keeps none."""
    from .house_settings import get_house_settings

    chosen = get_house_settings(db)
    ahead = chosen["music_preload"] or None
    return ahead if chosen["music_keep_downloads"] else min(3, ahead or 3)


def _prepare_audio(source, item_id):
    cached = cached_music(source, item_id)  # again: it may have arrived while this waited
    if cached:
        return ready_from_cache(source, item_id, cached)
    with SessionLocal() as db:
        pins = {item.id for item in preparation_window(db, limit=preload_count(db) or 2)}
        pins.update(
            db.scalars(
                select(QueueItem.id).where(
                    QueueItem.status.in_(["playing", "paused", "buffering", "resolving"])
                )
            )
        )
    fetch("cache_prune", pins=list(pins | {item_id}))
    # Archive restore may have declined because the disposable cache was full.
    cached = cached_music(source, item_id)
    if cached:
        preparation_state(item_id, "ready", cached)
        return cached
    preparation_state(item_id, "downloading")
    last_download[0] = time.monotonic()
    result = fetch("download", source, item_id)
    if result.get("status") == "completed":
        from .music_downloads import retain

        result.update(retain(source, item_id))
    preparation_state(item_id, "ready" if result.get("status") == "completed" else "failed", result)
    return result


LONG_TRACK = 5400
long_checked: dict[str, float] = {}


def renew_long_stream(item_id):
    """Keep an hours-long mix flowing: extend its one-hour pipe lease before it lapses."""
    if time.monotonic() - long_checked.get(item_id, 0) < 60:
        return
    long_checked.clear()
    long_checked[item_id] = time.monotonic()
    status = fetch("live_status", item_id=item_id)
    if status.get("state") == "streaming" and status.get("expires_at", 0) - time.time() < 900:
        fetch("live_renew", item_id=item_id)


radio_checked = {}
radio_busy = threading.Lock()


def radio_now_title(item_id, source_url):
    """Every 30 s, ask the station what song is on so the player can show (and find) it."""
    if time.monotonic() - radio_checked.get(item_id, 0) < 30 or not radio_busy.acquire(blocking=False):
        return
    try:
        radio_checked.clear()
        radio_checked[item_id] = time.monotonic()
        title = fetch("radio_title", source_url).get("title")
    finally:
        radio_busy.release()
    with SessionLocal() as db:
        item = db.get(QueueItem, item_id)
        if item and item.metadata_json.get("now_title") != title:
            heard = item.metadata_json.get("titles_heard", 0) + bool(title)  # for the radio rotation
            item.metadata_json = {**item.metadata_json, "now_title": title, "titles_heard": heard}
            emit(db, "music.metadata", {"item_id": item.id, "status": item.status})
            db.commit()


last_prune = [0.0]


def prefetch_next():
    """Download the next few songs (house setting music_preload) so each starts at once. Auto
    play keeps five songs waiting while one plays, preloaded too. A house that keeps
    no songs deletes each one once it's past."""
    from .house_settings import get_house_settings

    with SessionLocal() as db:
        q = db.get(QueueState, 1)
        if not q:
            return
        ahead = preload_count(db)
        whole = preparation_window(db, limit=None)  # a limited window is a prefix of it
        window = whole if ahead is None else whole[: ahead + 1]
        # Auto play keeps AUTO_AHEAD songs waiting, so a burst of skips lands on a ready song.
        if q.current_id and q.desired == "playing" and len(whole) <= AUTO_AHEAD:
            from .music_auto import config, fill

            if config(db).get("mode") == "library" and fill(db, q):
                db.commit()
                return
        if not get_house_settings(db)["music_keep_downloads"] and time.monotonic() - last_prune[0] > 60:
            last_prune[0] = time.monotonic()
            fetch("cache_prune", pins=[entry.id for entry in window], keep_none=True)
        item = next(
            (
                item
                for item in window
                if item.id != q.current_id
                and item.status in {"ready", "pending_metadata"}
                and not item.metadata_json.get("is_live")
                and not item.metadata_json.get("long_stream")
                and item_authorized(db, item)
                and not item.metadata_json.get("downloaded")
                and not item.metadata_json.get("prefetch_attempted")
            ),
            None,
        )
        if not item or item.status != "ready":
            return
        upcoming = [entry for entry in window if entry.id != q.current_id]
        if upcoming.index(item) >= FAR_AHEAD and time.monotonic() - last_download[0] < FAR_PACE:
            return  # a far song waits its turn (see FAR_PACE)
        identity, source = item.id, item.source_url
        if source.startswith(("radio:", "houseos-file:")):
            return
        item.metadata_json = {
            **item.metadata_json,
            "prefetched_at": time.time(),
            "prefetch_attempted": True,
            "download_state": "downloading",
        }
        emit(db, "music.metadata", {"item_id": item.id, "status": "preparing"})
        db.commit()
    result = prepare_audio(source, identity)
    with SessionLocal() as db:
        item = db.get(QueueItem, identity)
        valid = (
            item
            and item.status == "ready"
            and identity in {entry.id for entry in preparation_window(db, limit=preload_count(db))}
            and item_authorized(db, item)
        )
        if item and result.get("code") == "SOURCE_BUSY":
            # The fetcher was busy with another song: try again on a later tick.
            item.metadata_json = {**item.metadata_json, "prefetch_attempted": False, "download_state": None}
            db.commit()
            return
        if item:
            item.metadata_json = {
                **item.metadata_json,
                "download_state": "ready" if result.get("status") == "completed" else "failed",
            }
            if valid:
                item.metadata_json = {
                    **item.metadata_json,
                    "downloaded": result.get("status") == "completed",
                    "retained": bool(result.get("retained")),
                    "retention_error": result.get("retention_error"),
                }
            emit(db, "music.metadata", {"item_id": item.id, "status": item.status})
            db.commit()


def advance():
    global bridge_misses
    if (settings.runtime_root / "run/shutdown.json").exists():
        return
    with SessionLocal() as db:
        q = db.get(QueueState, 1)
        current = db.get(QueueItem, q.current_id) if q and q.current_id else None
        streaming = (
            current.id
            if current
            and current.metadata_json.get("long_stream")
            and current.status in {"playing", "paused", "buffering"}
            else None
        )
        radio = (
            (current.id, current.source_url)
            if current and current.source_url.startswith("radio:") and current.status == "playing"
            else None
        )
    if streaming:  # paused or playing, an hours-long mix keeps its pipe
        renew_long_stream(streaming)
    if radio and not radio_busy.locked():  # a slow station never holds up the queue
        threading.Thread(target=radio_now_title, args=radio, daemon=True).start()
    with SessionLocal() as db:
        q = db.scalar(select(QueueState).where(QueueState.id == 1).with_for_update())
        if not q:
            return
        if q.sleep_at and q.sleep_at <= utcnow():
            q.desired, q.sleep_at = "paused", None
            db.commit()
            bridge("pause")
            return
        if q.desired != "playing" or not settings.audio_enabled:
            return
        current = db.get(QueueItem, q.current_id) if q.current_id else None
        if current and current.status in {"playing", "paused", "buffering"}:
            snapshot = bridge("state")
            unanswered = snapshot.get("code") == "AUDIO_BRIDGE_UNAVAILABLE"
            bridge_misses = bridge_misses + 1 if unanswered else 0
            if unanswered and bridge_misses < BRIDGE_MISS_LIMIT:
                return
            if snapshot.get("status") != "observed":
                q.desired = "paused"
                paused_itself(db, snapshot.get("code") or "AUDIO_BRIDGE_UNAVAILABLE")
            elif snapshot.get("idle") is True:
                from .music import complete_track

                duration = current.metadata_json.get("duration") or 0
                heard = current.metadata_json.get("last_position") or 0
                cut_short = duration > 0 and heard < duration - max(15, duration * 0.05)
                if current.status == "buffering" or (cut_short and not current.metadata_json.get("is_live")):
                    # mpv could not open it, or the stream died early: say so, move on.
                    current.error_code = snapshot.get("code") or (
                        "PLAYBACK_FAILED" if current.status == "buffering" else "PLAYBACK_INTERRUPTED"
                    )
                    current.status = "failed"
                    q.current_id = None
                    q.failures += 1
                    q.version += 1
                    emit(db, "music.queue_changed", {"version": q.version})
                else:
                    complete_track(db, q, current)
            else:
                if snapshot.get("item_id") != current.id:
                    q.desired = "paused"
                    current.error_code = "PLAYBACK_ITEM_MISMATCH"
                    paused_itself(db, "PLAYBACK_ITEM_MISMATCH")
                    db.commit()
                    bridge("pause")
                    return
                observed = "paused" if snapshot.get("paused") else "playing"
                if current.status != observed:
                    emit(db, "music.playback", {"item_id": current.id, "status": observed})
                current.status = observed
                if current.metadata_json.get("auto") == "radio" and observed == "playing":
                    from .music_auto import rotation_over

                    if not current.metadata_json.get("auto_since"):
                        current.metadata_json = {**current.metadata_json, "auto_since": time.time()}
                    elif not current.metadata_json.get("rotation_done") and rotation_over(db, current):
                        # Its turn is over: stop it; the next tick completes it and moves on.
                        current.metadata_json = {**current.metadata_json, "rotation_done": True}
                        db.commit()
                        bridge("stop")
                        fetch("live_stop", item_id=current.id)
                        return
                if current.status == "playing" and not current.metadata_json.get("history_recorded"):
                    from .music import record_played

                    record_played(db, current, snapshot)
                current.metadata_json = {**current.metadata_json, "last_position": snapshot.get("position")}
            db.commit()
            return
        # A song waiting for someone's approval never holds up the rest of the queue.
        if current and current.status == "awaiting_confirmation":
            q.current_id, current = None, None
        # An explicit new request owns this pending slot until its metadata is known.
        if current and current.status == "pending_metadata":
            db.commit()
            return
        # Only this function resolves, one song at a time, so a song still "resolving" here was
        # left by an earlier pass that stopped halfway (a pause, a restart): try it again, or it
        # sits on "Finding the audio…" forever.
        if current and current.status == "resolving":
            current.status = "ready"
        from .music import pending_order

        ready = list(
            db.scalars(select(QueueItem).where(QueueItem.status == "ready").order_by(QueueItem.position))
        )
        item = (
            current
            if current and current.status == "ready"
            else next(iter(pending_order(db, q, ready)), None)
        )
        if current and current.status in {"failed", "removed"}:
            q.current_id, q.desired = None, "paused"
            db.commit()
            return
        if not item:
            from .music_auto import fill

            if fill(db, q):  # auto play: one pick, played once its details are known
                db.commit()
            return
        item.status, q.current_id = "resolving", item.id
        resolve_generation = new_id()
        item.metadata_json = {**item.metadata_json, "resolve_generation": resolve_generation}
        item_id, source = item.id, item.source_url
        is_live = bool(item.metadata_json.get("is_live"))
        long_stream = bool(item.metadata_json.get("long_stream"))
        live_authorized = item.metadata_json.get("live_authorized_until", 0)
        if is_live and item.metadata_json.get("live_approved") and live_authorized <= time.time():
            live_authorized = time.time() + 3600
            item.metadata_json = {
                **item.metadata_json,
                "live_authorized_until": live_authorized,
                "live_approved": False,
            }
        db.commit()
    if is_live:
        result = (
            fetch("live_start", source, item_id)
            if live_authorized > time.time()
            else {"status": "needs_confirmation", "code": "LIVE_STREAM_REQUIRES_APPROVAL"}
        )
    elif long_stream:
        result = fetch("long_start", source, item_id)
    elif source.startswith("houseos-file:"):
        from .music_library import stage_local_audio

        result = stage_local_audio(item_id)
    else:
        result = prepare_audio(source, item_id)
    with PLAYER_COMMANDS, SessionLocal() as db:
        q = db.scalar(select(QueueState).where(QueueState.id == 1).with_for_update())
        item = db.get(QueueItem, item_id)
        if q.sleep_at and q.sleep_at <= utcnow():
            q.desired, q.sleep_at = "paused", None
            db.commit()
        if (
            (settings.runtime_root / "run/shutdown.json").exists()
            or q.current_id != item_id
            or q.desired != "playing"
            or item.status != "resolving"
            or item.metadata_json.get("resolve_generation") != resolve_generation
        ):
            if is_live or long_stream:
                fetch("live_stop", item_id=item_id)
            return
        if result.get("status") == "completed":
            valid = item_authorized(db, item)
            lease_valid = (
                LEASE_CONNECTION_ID is None
                or db.scalar(text(f"SELECT IS_USED_LOCK({WORKER_LOCK})")) == LEASE_CONNECTION_ID
            )
            if not valid or not lease_valid:
                result = {"status": "failed", "code": "PLAYBACK_AUTHORIZATION_REVOKED"}
            if result.get("status") == "completed" and source.startswith("houseos-file:"):
                from .music_library import authorized_local
                from fastapi import HTTPException

                try:
                    authorized_local(db, item)
                except HTTPException:
                    result = {"status": "failed", "code": "LOCAL_AUTHORIZATION_REVOKED"}
            if result.get("status") == "completed":
                result = bridge(
                    "load", item_id=item_id, position=item.metadata_json.get("resume_position", 0)
                )
        if result.get("status") == "command_sent":
            item.status, q.failures = "buffering", 0
            item.metadata_json = {**item.metadata_json, "resume_position": 0}
        elif result.get("status") == "needs_confirmation":
            item.status, item.error_code = "awaiting_confirmation", result.get("code")
            q.current_id = None
        elif result.get("code") in TEMPORARY:
            if is_live or long_stream:
                fetch("live_stop", item_id=item_id)
            item.status = "ready"
        else:
            if is_live or long_stream:
                fetch("live_stop", item_id=item_id)
            item.status, item.error_code = "failed", result.get("code", "PLAYBACK_FAILED")
            q.current_id = None
            q.failures += 1
            if q.failures >= 3:
                q.desired = "paused"
                paused_itself(db, "THREE_SONGS_FAILED")
        emit(db, "music.playback", {"item_id": item_id, "status": item.status, "code": item.error_code})
        db.commit()


def cancel_removed_downloads():
    with SessionLocal() as db:
        removed = list(
            db.scalars(
                select(QueueItem).where(
                    QueueItem.status.in_(["removed", "skipped"]),
                    QueueItem.metadata_json["download_state"].as_string() == "downloading",
                )
            )
        )
        for item in removed:  # once each: a fetcher that is down must not stall every tick
            cancelled = fetch("cancel_download", item_id=item.id).get("status") == "completed"
            state = "cancelled" if cancelled else "cancel_failed"
            item.metadata_json = {**item.metadata_json, "download_state": state}
        db.commit()


class WorkerTasks:
    """Independent title lookup, sequential preloading and playback observation."""

    def __init__(self):
        from concurrent.futures import ThreadPoolExecutor

        self.pools = {
            lane: ThreadPoolExecutor(max_workers=1, thread_name_prefix="music-" + lane)
            for lane in ("metadata", "import", "download", "prepare", "cast")
        }
        self.running = {}

    def tick(self, owner):
        cancel_removed_downloads()
        control = claim(owner, ("music.control", "service.restart"))
        if control:
            run_job(control)
        for lane, pool in self.pools.items():
            finished = self.running.get(lane)
            if finished is not None and not finished.done():
                continue
            self.running[lane] = None
            if finished is not None:
                finished.result()
            if lane == "metadata":
                job = claim(owner, ("music.metadata",))
                work = job and (run_job, job)
            elif lane == "import":
                from .music import import_playlist_page

                job = claim(owner, ("music.playlist_import",))
                work = job and (import_playlist_page, job[0], job[1], job[3])
            elif lane == "cast":
                from .music_outputs import follow_cast

                work = (follow_cast,)  # a Cast speaker follows the house clock
            else:
                work = (prefetch_next if lane == "download" else advance,)
            if work:
                self.running[lane] = pool.submit(*work)

    def close(self):
        for pool in self.pools.values():
            pool.shutdown(wait=False, cancel_futures=True)


def planned_restart():
    """True once after `houseos.sh update` asked for it: music that was playing comes back."""
    marker = settings.runtime_root / "run" / "resume-music"
    try:
        fresh = time.time() - marker.stat().st_mtime < 1800
        marker.unlink()
        return fresh
    except OSError:
        return False


def reconcile_player_restart(observation):
    planned = planned_restart()
    with SessionLocal() as db:
        q = db.get(QueueState, 1)
        if not q:
            return
        current = db.get(QueueItem, q.current_id) if q.current_id else None
        if (
            current
            and q.desired == "playing"
            and item_authorized(db, current)
            and observation.get("status") == "observed"
            and observation.get("idle") is False
            and observation.get("item_id") == current.id
            and observation.get("paused") is False
        ):
            current.status = "playing"
            db.commit()
            return True
        # A song asked for moments before the restart has not started yet: the request stands.
        if (
            current
            and q.desired == "playing"
            and current.status in {"pending_metadata", "ready"}
            and current.created_at > utcnow() - timedelta(minutes=2)
        ):
            return True
        if not (planned and q.desired == "playing"):
            q.desired = "paused"
        if current and current.status in {"playing", "paused", "buffering", "resolving"}:
            same_player = (
                observation.get("status") == "observed"
                and observation.get("idle") is False
                and observation.get("item_id") == current.id
            )
            if same_player:
                current.status = "paused"
            elif current.metadata_json.get("is_live"):
                current.status, current.error_code = "failed", "LIVE_SESSION_INTERRUPTED_REQUEUE_STATION"
                q.current_id = None
            else:
                position = current.metadata_json.get("last_position") or 0
                position = position if isinstance(position, (int, float)) and 0 <= position <= 14400 else 0
                current.metadata_json = {**current.metadata_json, "resume_position": position}
                current.status, current.error_code = "ready", None
                q.current_id = None
        db.commit()


# One music worker per database (MariaDB named locks are server-wide, so the name includes it).
WORKER_LOCK = "CONCAT('houseos_music_worker:', DATABASE())"


def main():
    from .events import restart_on_request

    restart_on_request("worker")
    global LEASE_CONNECTION_ID
    import os

    owner = new_id()
    guard = engine.connect()
    if guard.scalar(text(f"SELECT GET_LOCK({WORKER_LOCK}, 0)")) != 1:
        raise SystemExit("Another HouseOS music worker owns this destination")
    LEASE_CONNECTION_ID = guard.scalar(text("SELECT CONNECTION_ID()"))
    # Reconcile the exact surviving item; never infer completion from a fresh empty mpv.
    if not reconcile_player_restart(bridge("state")):
        bridge("pause")
    tasks = WorkerTasks()
    while True:
        try:
            if guard.scalar(text(f"SELECT IS_USED_LOCK({WORKER_LOCK}) = CONNECTION_ID()")) != 1:
                os._exit(1)  # end every thread; systemd removes this unit's child processes
        except Exception:
            os._exit(1)
        try:
            tasks.tick(owner)
            # Readers allow 30 s; a write every second was most of the shared MariaDB's UPDATEs.
            heartbeat("worker", every=10)
        except Exception as exc:
            from .events import failure_site

            print("worker_iteration_failed", failure_site(exc), flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
