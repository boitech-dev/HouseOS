"""Explicit household title sharing; playback history and preferences stay private."""

import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from .auth import require_actor, require_permission, user_permissions, account_usable
from .cinema import CinemaTitle, public_title
from .db import get_db, utcnow
from .events import emit
from .models import Record, User

router = APIRouter(prefix="/cinema/shared-watchlist", tags=["cinema"])
KIND = "cinema.shared_watchlist"


def permitted(actor, write=False):
    require_permission(actor, "cinema.use")
    require_permission(actor, "household.write" if write else "household.read")


@router.get("")
def list_shared(
    actor=Depends(require_actor), db=Depends(get_db), offset: Annotated[int, Query(ge=0, le=100000)] = 0
):
    permitted(actor)
    # Explicit record projection only: never join or serialize CinemaState.
    rows = db.execute(
        select(Record, User)
        .join(User, User.id == Record.owner_id)
        .where(
            Record.kind == KIND,
            Record.visibility == "house",
            Record.deleted_at.is_(None),
            User.active.is_(True),
            or_(User.expires_at.is_(None), User.expires_at > utcnow()),
        )
        .order_by(Record.created_at.desc(), Record.id)
        .offset(offset)
        .limit(101)
    ).all()
    items = []
    for row, user in rows[:100]:
        if user.role != "admin" and not {"cinema.use", "household.write"} <= user_permissions(user):
            continue
        title = db.get(CinemaTitle, row.data.get("media_id"))
        if title:
            items.append(
                {
                    "id": row.id,
                    "media": public_title(title),
                    "shared_by": {"id": user.id, "name": user.name},
                    "mine": user.id == actor.id,
                }
            )
    return {"items": items, "next_offset": offset + 100 if len(rows) > 100 else None}


def record_id(actor, identity):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "houseos:shared-watchlist:" + actor.id + ":" + identity))


def owner_lock(db, actor):
    user = db.scalar(
        select(User).where(User.id == actor.id).with_for_update().execution_options(populate_existing=True)
    )
    if not account_usable(user):
        raise HTTPException(401, "Account is inactive or expired")
    if user.role != "admin" and not {"cinema.use", "household.write"} <= user_permissions(user):
        raise HTTPException(403, "Permission denied")


@router.put("/{identity}")
def share(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    permitted(actor, True)
    owner_lock(db, actor)  # Serializes idempotent creation/removal for this contributor.
    if not db.get(CinemaTitle, identity):
        raise HTTPException(404, "Title not found")
    row = db.get(Record, record_id(actor, identity))
    if row is None:
        row = Record(
            id=record_id(actor, identity),
            kind=KIND,
            owner_id=actor.id,
            visibility="house",
            data={"media_id": identity},
        )
        db.add(row)
    else:
        row.deleted_at = None
    emit(db, "cinema.watchlist_shared", {"media_id": identity})
    db.commit()
    return {"status": "shared", "media_id": identity}


@router.delete("/{identity}")
def unshare(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    permitted(actor, True)
    owner_lock(db, actor)
    row = db.get(Record, record_id(actor, identity))
    if row and row.deleted_at is None:
        row.deleted_at = utcnow()
        emit(db, "cinema.watchlist_unshared", {"media_id": identity})
    db.commit()
    return {"status": "not_shared", "media_id": identity}
