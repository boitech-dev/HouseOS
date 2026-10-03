"""Short observation/checkpoint loop; separate from slow preparation and music control."""

import logging
import time
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
    db.commit()
    if time.monotonic() - PRUNED["web"] > 300:  # Watch → Web's files, every five minutes
        from .cinema_web import prune_web_videos

        PRUNED["web"] = time.monotonic()
        prune_web_videos(db)


PRUNED = {"web": 0.0}


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
