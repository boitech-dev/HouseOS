"""Short observation/checkpoint loop; separate from slow preparation and music control."""

import logging
import time
from datetime import timedelta
from sqlalchemy import select
from .db import SessionLocal, utcnow
from .cinema import CinemaWorkflow, CinemaRelay, reconcile_playback
from .cinema_cleanup import maintain_cinema_cache
from .models import Record

log = logging.getLogger("houseos.cinema.observer")


def maintenance(db):
    now = utcnow()
    for grant in db.scalars(select(CinemaRelay).where(CinemaRelay.expires_at <= now).limit(100)):
        db.delete(grant)
    for record in db.scalars(
        select(Record)
        .where(
            Record.kind == "cinema.local_media",
            Record.deleted_at.is_(None),
            Record.data["state"].as_string().in_(["reserved", "downloading"]),
        )
        .limit(500)
    ):
        if record.data.get("state") not in {"reserved", "downloading"}:
            continue
        workflow = db.get(CinemaWorkflow, record.data.get("workflow_id"))
        if (
            not workflow
            or workflow.state in {"cancelled", "failed", "recovery_required"}
            or workflow.state == "awaiting_playback_confirmation"
            and record.data.get("expires_at", "") < now.isoformat()
        ):
            record.data = {**record.data, "state": "expired"}
    maintain_cinema_cache(db)
    clear_watched_copies(db)
    db.commit()
    if time.monotonic() - PRUNED["web"] > 300:  # Watch → Web's files, every five minutes
        from .cinema_web import prune_web_videos

        PRUNED["web"] = time.monotonic()
        prune_web_videos(db)


PRUNED = {"web": 0.0}
KEEP_UNWATCHED = timedelta(days=7)


def clear_watched_copies(db):
    """A film downloaded to watch without buffering ("Download first") goes once watched to the
    end, or a week after it was ready; never while it plays (forget_movie refuses then)."""
    from fastapi import HTTPException

    from .cinema import CinemaState, watched_through
    from .storage_admin import forget_movie

    copies = db.scalars(
        select(Record)
        .where(
            Record.kind == "cinema.local_media",
            Record.deleted_at.is_(None),
            Record.data["then_delete"].as_boolean().is_(True),
            Record.data["state"].as_string() == "ready",
        )
        .limit(50)
    ).all()
    for copy in copies:
        ready_at = copy.data.get("ready_at") or ""
        seen = db.scalar(
            select(CinemaState).where(
                CinemaState.owner_id == copy.owner_id, CinemaState.media_id == copy.data.get("media_id")
            )
        )
        watched = bool(
            seen
            and watched_through(seen.data)
            and seen.last_watched_at
            and seen.last_watched_at.isoformat() > ready_at
        )
        if watched or ready_at < (utcnow() - KEEP_UNWATCHED).isoformat():
            try:
                forget_movie(db, copy.id, copy.version)
                db.commit()
            except HTTPException:
                db.rollback()  # playing or preparing right now: next time


def main():
    from .events import restart_on_request

    restart_on_request("cinema-observer")
    logging.basicConfig(level=logging.INFO)
    while True:
        started = time.monotonic()
        try:
            with SessionLocal() as db:
                maintenance(db)
                reconcile_playback(db)
            from .events import heartbeat

            heartbeat("cinema_observer")
        except Exception as exc:
            # DB/provider exception strings can contain URLs or parameters; log only the site.
            from .events import failure_site

            log.error("CINEMA_OBSERVATION_CYCLE_FAILED %s", failure_site(exc))
        time.sleep(max(1, 5 - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
