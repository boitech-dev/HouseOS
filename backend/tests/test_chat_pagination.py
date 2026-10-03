"""Actual database pagination and private ownership; no provider calls."""

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from houseos import assistant as a
from houseos.db import new_id
from houseos.models import Record, Operation


def test_long_history_pages_are_chronological_and_private(domain):
    db, (alice, bob, _) = domain
    convo = Record(id=new_id(), owner_id=alice.id, kind="conversation", data={"title": "Long sequence"})
    other = Record(id=new_id(), owner_id=bob.id, kind="conversation", data={"title": "Private"})
    db.add_all([convo, other])
    db.flush()
    # All rows share a timestamp: ordering must use sequence, never random IDs.
    timestamp = datetime(2026, 9, 20, 12)
    for sequence in range(1, 206):
        db.add(
            a.ChatMessage(
                conversation_id=convo.id,
                owner_id=alice.id,
                sequence=sequence,
                role="user" if sequence % 2 else "assistant",
                content=str(sequence),
                created_at=timestamp,
            )
        )
    db.add(
        a.ChatMessage(
            conversation_id=other.id,
            owner_id=bob.id,
            sequence=1,
            role="user",
            content="PRIVATE",
            created_at=timestamp,
        )
    )
    db.commit()
    latest = a.conversation(convo.id, alice, db, offset=0, limit=100)
    previous = a.conversation(convo.id, alice, db, offset=latest["next_offset"], limit=100)
    oldest = a.conversation(convo.id, alice, db, offset=previous["next_offset"], limit=100)
    combined = oldest["messages"] + previous["messages"] + latest["messages"]
    assert [int(row["content"]) for row in combined] == list(range(1, 206))
    assert oldest["next_offset"] is None
    assert len({row["id"] for row in combined}) == 205
    assert [row.content for row in a.recent_messages(db, convo, alice, 10)] == [
        str(n) for n in range(196, 206)
    ]
    with pytest.raises(HTTPException) as denied:
        a.conversation(convo.id, bob, db, offset=0, limit=100)
    assert denied.value.status_code == 404
    assert all(row["id"] != convo.id for row in a.conversations(bob, db))


def test_approved_excerpt_gets_next_sequence_under_existing_conversation_lock(domain, monkeypatch):
    from datetime import timedelta
    from houseos.db import utcnow

    db, (alice, _, _) = domain
    convo = Record(id=new_id(), owner_id=alice.id, kind="conversation", data={})
    db.add(convo)
    db.flush()
    db.add(
        a.ChatMessage(
            conversation_id=convo.id, owner_id=alice.id, role="assistant", content="Earlier reply", sequence=9
        )
    )
    op = Operation(
        actor_id=alice.id,
        kind="assistant.file_excerpt",
        state="needs_confirmation",
        data={"conversation_id": convo.id, "file_id": new_id(), "version": 1},
        expires_at=utcnow() + timedelta(minutes=1),
    )
    db.add(op)
    db.commit()
    monkeypatch.setattr("houseos.files.read_excerpt", lambda *args, **kw: {"text": "approved text"})
    a.confirm_file_excerpt(op.id, alice, db)
    rows = list(
        db.scalars(
            select(a.ChatMessage)
            .where(a.ChatMessage.conversation_id == convo.id)
            .order_by(a.ChatMessage.sequence)
        )
    )
    assert [row.sequence for row in rows] == [9, 10]
    assert "approved text" in rows[-1].content
