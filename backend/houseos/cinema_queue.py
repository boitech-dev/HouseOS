"""Private Cinema queue; exact identities, ordinary records, no automatic playback."""

import hashlib
from fastapi import Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import Actor, require_actor
from .db import get_db
from .models import Record, User
from .events import emit
from .db import utcnow
from .cinema import router, allowed, Body, CinemaTitle, public_title


class QueueAdd(Body):
    media_id: str = Field(min_length=1, max_length=36)
    season: int | None = Field(default=None, ge=0, le=100)
    episode: int | None = Field(default=None, ge=1, le=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.get("/queue")
def list_queue(
    actor: Actor = Depends(require_actor), db: Session = Depends(get_db), offset: int = Query(0, ge=0, le=200)
):
    allowed(actor)
    offset = offset if isinstance(offset, int) else 0
    rows = list(
        db.scalars(
            select(Record)
            .where(Record.kind == "cinema.queue", Record.owner_id == actor.id, Record.deleted_at.is_(None))
            .order_by(Record.created_at, Record.id)
            .offset(offset)
            .limit(21)
        )
    )
    items = []
    for row in rows[:20]:
        title = db.get(CinemaTitle, row.data["media_id"])
        if title:
            items.append({"queue_id": row.id, **public_title(title), **row.data})
    all_ids = list(
        db.scalars(
            select(Record.id)
            .where(Record.kind == "cinema.queue", Record.owner_id == actor.id, Record.deleted_at.is_(None))
            .order_by(Record.id)
        )
    )
    return {
        "items": items,
        "next_offset": offset + 20 if len(rows) > 20 else None,
        "total": len(all_ids),
        "revision": hashlib.sha256(",".join(all_ids).encode()).hexdigest(),
    }


@router.post("/queue")
def enqueue_title(body: QueueAdd, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    title = db.get(CinemaTitle, body.media_id)
    if not title:
        raise HTTPException(404, "Title not found")
    if title.kind == "series" and (body.season is None or body.episode is None):
        raise HTTPException(422, "Choose the exact episode before adding it to your queue")
    if title.kind == "episode":
        if (body.season is not None and body.season != title.data.get("season")) or (
            body.episode is not None and body.episode != title.data.get("episode")
        ):
            raise HTTPException(422, "The selected episode does not match this title")
        body = body.model_copy(
            update={"season": title.data.get("season"), "episode": title.data.get("episode")}
        )
    elif title.kind != "series" and (body.season is not None or body.episode is not None):
        raise HTTPException(422, "Movies do not have season or episode numbers")
    if (
        title.kind == "series"
        and title.data.get("episodes")
        and not any(
            e.get("season") == body.season and e.get("episode") == body.episode
            for e in title.data["episodes"]
        )
    ):
        raise HTTPException(422, "This episode is not in the series catalog")
    data = body.model_dump(exclude={"idempotency_key"})
    identity = hashlib.sha256((actor.id + ":cinema.queue:" + body.idempotency_key).encode()).hexdigest()[:36]
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    existing = db.get(Record, identity)
    if existing:
        if existing.data != data:
            raise HTTPException(409, "This request key belongs to a different queue item")
        return {"status": "removed" if existing.deleted_at else "queued", "queue_id": existing.id}
    count = len(
        db.scalars(
            select(Record.id).where(
                Record.kind == "cinema.queue", Record.owner_id == actor.id, Record.deleted_at.is_(None)
            )
        ).all()
    )
    if count >= 200:
        raise HTTPException(409, "Your Cinema queue holds up to 200 titles")
    db.add(Record(id=identity, kind="cinema.queue", owner_id=actor.id, visibility="private", data=data))
    emit(db, "cinema.queue", {"queue_id": identity}, user_id=actor.id)
    db.commit()
    return {"status": "queued", "queue_id": identity}


@router.delete("/queue/{identity}")
def remove_queued(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    row = db.scalar(
        select(Record).where(
            Record.id == identity, Record.kind == "cinema.queue", Record.owner_id == actor.id
        )
    )
    if not row:
        raise HTTPException(404, "Queue item not found")
    row.deleted_at = utcnow()
    emit(db, "cinema.queue", {}, user_id=actor.id)
    db.commit()
    return {"status": "removed"}


class QueueClear(Body):
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/queue/clear")
def clear_queue(body: QueueClear, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    key = hashlib.sha256((actor.id + ":cinema.clear:" + body.idempotency_key).encode()).hexdigest()[:36]
    previous = db.get(Record, key)
    if previous:
        if previous.data["revision"] != body.revision:
            raise HTTPException(409, "This request key belongs to another queue snapshot")
        return previous.data["result"]
    rows = list(
        db.scalars(
            select(Record)
            .where(Record.kind == "cinema.queue", Record.owner_id == actor.id, Record.deleted_at.is_(None))
            .order_by(Record.id)
            .with_for_update()
        )
    )
    revision = hashlib.sha256(",".join(row.id for row in rows).encode()).hexdigest()
    if revision != body.revision:
        raise HTTPException(409, "Your queue changed; review it before clearing")
    for row in rows:
        row.deleted_at = utcnow()
    result = {"status": "cleared", "removed": len(rows)}
    db.add(
        Record(
            id=key,
            kind="cinema.queue_clear",
            owner_id=actor.id,
            visibility="private",
            data={"revision": revision, "result": result},
        )
    )
    emit(db, "cinema.queue", result, user_id=actor.id)
    db.commit()
    return result
