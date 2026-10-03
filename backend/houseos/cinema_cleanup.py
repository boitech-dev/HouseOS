"""Reclaim private streaming/preparation caches after terminal workflows only."""

import os
from pathlib import Path
import shutil
from uuid import UUID
from sqlalchemy import select
from .config import settings
from .db import utcnow


def maintain_cinema_cache(db):
    from .cinema import CinemaWorkflow, CinemaPreparation, CinemaRelay, CinemaDevice
    from .cinema_progressive import ACTIVE

    terminal = {"stopped", "completed", "cancelled", "failed", "recovery_required"}
    candidates = (
        select(CinemaPreparation.workflow_id)
        .join(CinemaWorkflow, CinemaWorkflow.id == CinemaPreparation.workflow_id)
        .where(CinemaPreparation.state.in_(["done", "failed"]), CinemaWorkflow.state.in_(terminal))
        .distinct()
        .limit(50)
    )
    root = Path(settings.runtime_root) / "cinema"
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return 0
    removed = 0
    try:
        for identity in db.scalars(candidates):
            try:
                if str(UUID(identity)) != identity:
                    continue
            except (ValueError, TypeError):
                continue
            workflow = db.scalar(
                select(CinemaWorkflow).where(CinemaWorkflow.id == identity).with_for_update()
            )
            if not workflow or workflow.state not in terminal:
                continue
            jobs = list(
                db.scalars(select(CinemaPreparation).where(CinemaPreparation.workflow_id == identity))
            )
            if any(job.state in {"queued", "running"} or job.id in ACTIVE for job in jobs):
                continue
            if db.scalar(select(CinemaDevice.id).where(CinemaDevice.owner_workflow == identity).limit(1)):
                continue
            if db.scalar(
                select(CinemaRelay.token_hash)
                .where(CinemaRelay.workflow_id == identity, CinemaRelay.expires_at > utcnow())
                .limit(1)
            ):
                continue
            # fd-relative rmtree refuses a symlink root and never follows links within it.
            if not shutil.rmtree.avoids_symlink_attacks:
                continue
            try:
                shutil.rmtree(identity, dir_fd=descriptor)
            except FileNotFoundError:
                pass
            except OSError:
                continue
            for job in jobs:
                job.state = "purged"
            workflow.data = {
                key: value
                for key, value in workflow.data.items()
                if key not in {"_prepared", "_stream_job_id"}
            }
            removed += 1
    finally:
        os.close(descriptor)
    return removed
