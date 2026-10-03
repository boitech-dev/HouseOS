"""Explicit upload-backup scope and disk budget; bulk movie cache is excluded."""

from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, func
from .auth import Input, require_admin
from .db import get_db, utcnow
from .models import Integration, Operation
from .files import FileEntry
from .events import emit

router = APIRouter(prefix="/admin/backups", tags=["backups"])
DEFAULT = {"uploads_enabled": False, "scopes": ["personal", "house"], "max_bytes": 5 * 1024**3}


@router.get("/policy")
def policy(actor=Depends(require_admin), db=Depends(get_db)):
    row = db.get(Integration, "backup_policy")
    cfg = {**DEFAULT, **(row.config if row else {})}
    size = db.scalar(
        select(func.coalesce(func.sum(FileEntry.size), 0)).where(
            FileEntry.is_folder.is_(False),
            FileEntry.storage_removed_at.is_(None),
            FileEntry.scope.in_(cfg["scopes"]),
        )
    )
    return {
        **cfg,
        "selected_bytes": size,
        "destination": "Encrypted incremental upload copies on NVMe",
        "schedule": "Daily 04:15",
        "retention": "No automatic pruning; older copies survive deletion",
        "bulk_cinema_included": False,
    }


class Policy(Input):
    uploads_enabled: bool
    scopes: list[Literal["personal", "house", "drop", "media"]] = Field(min_length=1, max_length=4)
    max_bytes: int = Field(ge=1024**3, le=100 * 1024**3)
    current_password: str | None = Field(default=None, max_length=256)


@router.post("/policy/prepare")
def prepare(body: Policy, actor=Depends(require_admin), db=Depends(get_db)):
    data = body.model_dump(exclude={"current_password"})
    data["scopes"] = sorted(set(data["scopes"]))
    op = Operation(
        actor_id=actor.id,
        kind="backup.policy",
        state="needs_confirmation",
        data=data,
        expires_at=utcnow() + timedelta(minutes=2),
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "preview": {
            **data,
            "effect": "Apply to the next scheduled backup; never delete existing archives",
            "disaster_recovery": "Same machine; no off-machine copy",
        },
    }


@router.post("/policy/confirm/{identity}")
def confirm(identity: str, actor=Depends(require_admin), db=Depends(get_db)):
    op = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if not op or op.kind != "backup.policy" or op.state != "needs_confirmation" or op.expires_at <= utcnow():
        raise HTTPException(409, "Confirmation expired or consumed")
    row = db.get(Integration, "backup_policy")
    if not row:
        row = Integration(name="backup_policy")
        db.add(row)
    row.config = dict(op.data)
    row.enabled = True
    op.state = "completed"
    emit(db, "audit.backup_policy", {"operation_id": op.id, "status": "completed"}, actor.id)
    db.commit()
    return {"status": "completed"}
