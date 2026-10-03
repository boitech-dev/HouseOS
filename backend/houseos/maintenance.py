"""Bounded housekeeping separate from audio control and video preparation."""

import asyncio
import time
from datetime import timedelta
from sqlalchemy import delete, select
from .db import SessionLocal, utcnow
from .models import Event, Job, Operation, SessionToken
from .auth import LoginAttempt
from .events import failure_site, heartbeat
from .household import maintain_household
from .files import expire_uploads, maintain_files, reconcile_staging
from .notifications import deliver_pending
from .control_room import reconcile_restarts
from .house_actions import update_watch
from .personal_space import refresh_configured_spaces
from . import anime_offline, film_index, languages
from .music_catalog import enrich


failures: dict = {}  # step → failures in a row
retry_at: dict = {}  # step → when a failed step runs again
noted_at: dict = {}  # step → when its failure was last posted to Activity
LIVE_OPERATION_STATES = ("accepted", "pending", "running", "executing", "preparing", "needs_confirmation")
last_prune = 0.0


def prune(db, table, key, condition, batch=2000):
    """Delete in small batches found by a non-locking read, so writers never queue behind a
    scan of an unindexed column."""
    while ids := db.scalars(select(key).where(condition).order_by(key).limit(batch)).all():
        db.execute(delete(table).where(key.in_(ids)))
        db.commit()


def prune_history(db):
    """Hourly retention: live-update events 14 days, audit events 180 days, finished jobs
    30 days, finished operations 90 days, expired sessions and stale login throttles 1 day."""
    global last_prune
    if time.monotonic() - last_prune < 3600:
        return
    now = utcnow()
    prune(db, Event, Event.id, ~Event.topic.like("audit.%") & (Event.created_at < now - timedelta(days=14)))
    prune(db, Event, Event.id, Event.topic.like("audit.%") & (Event.created_at < now - timedelta(days=180)))
    prune(
        db, Job, Job.id, Job.state.not_in(("pending", "running")) & (Job.next_run < now - timedelta(days=30))
    )
    prune(
        db,
        Operation,
        Operation.id,
        Operation.state.not_in(LIVE_OPERATION_STATES) & (Operation.updated_at < now - timedelta(days=90)),
    )
    prune(db, SessionToken, SessionToken.token_hash, SessionToken.expires_at < now - timedelta(days=1))
    prune(db, LoginAttempt, LoginAttempt.key, LoginAttempt.window_at < now - timedelta(days=1))
    last_prune = time.monotonic()


# Named functions, not lambdas: a failure note names the step by its __name__.
def expire_uploads_step(db):
    asyncio.run(expire_uploads(db))


def deliver_notifications(db):
    deliver_pending(db, limit=10)


def games_sweep(db):
    from .games import sweep

    sweep(db)


STEPS = (
    prune_history,
    maintain_household,
    expire_uploads_step,
    maintain_files,
    reconcile_staging,
    deliver_notifications,
    reconcile_restarts,
    update_watch,
    refresh_configured_spaces,
    enrich,
    film_index.refresh,
    languages.refresh,
    anime_offline.refresh,  # daily, so nobody waits for the anime list's download in Watch
    games_sweep,  # games folders rescanned daily; new games named and pictured
)


def run_steps():
    # Each step gets its own transaction so one failure never skips the others.
    for step in STEPS:
        if time.monotonic() < retry_at.get(step, 0):
            continue
        try:
            with SessionLocal() as db:
                step(db)
                db.commit()
            if failures.pop(step, None) and step in noted_at:  # the log marks its failure fixed
                noted_at.pop(step)
                from .activity import note

                note("A background chore works again: {step}", "good", step=getattr(step, "__name__", "step"))
        except Exception as exc:
            print("maintenance_step_failed", failure_site(exc), flush=True)
            # Back off 1, 2, 4, 8 then 15 min; post at most hourly: every note refreshes every tab.
            failures[step] = failures.get(step, 0) + 1
            retry_at[step] = time.monotonic() + min(900, 30 * 2 ** failures[step])
            if time.monotonic() - noted_at.get(step, -3600) < 3600:
                continue
            noted_at[step] = time.monotonic()
            try:
                from .activity import note

                name = getattr(step, "__name__", "step")
                note(
                    "A background chore failed: {step} ({where})",
                    "problem",
                    step=name,
                    where=failure_site(exc)[:120],
                )
            except Exception:  # noqa: BLE001 - the journal line above is enough
                pass


def main():
    from .events import restart_on_request

    restart_on_request("maintenance")
    while True:
        run_steps()
        try:
            heartbeat("maintenance", every=0)
        except Exception as exc:
            print("maintenance_heartbeat_failed", failure_site(exc), flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
