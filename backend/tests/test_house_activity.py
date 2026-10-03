"""Control Room → Logs: the house's events told as sentences, filtered, newest first."""

from houseos.events import emit
from houseos.music import QueueItem
from test_core import admin


def test_events_become_sentences_and_plumbing_stays_out(client):
    c, db = client
    admin(client)
    from houseos.models import User

    owner = db.query(User).first().id
    db.add(QueueItem(id="song-1", owner_id=owner, source_url="https://x.invalid", title="Balade", position=1))
    emit(db, "music.metadata", {"item_id": "song-1", "status": "resolving"})  # plumbing
    emit(db, "music.playback", {"item_id": "song-1", "status": "playing"})
    emit(db, "audit.tool_call", {"tool_name": "music_add_candidates", "status": "accepted"})
    emit(db, "system.note", {"text": "Film index rebuilt: {count} titles", "level": "good", "count": 42})
    emit(db, "audit.application_error", {"correlation_id": "abcdef123456", "status": "failed"})
    db.commit()
    lines = c.get("/api/v1/admin/activity").json()["items"]
    assert [line["category"] for line in lines] == ["system", "system", "nox", "music"]
    assert lines[-1]["template"] == "Playing {title}" and lines[-1]["values"] == {"title": "Balade"}
    assert lines[0]["level"] == "problem" and lines[1]["values"] == {"count": 42}
    only = c.get("/api/v1/admin/activity?problems=true").json()["items"]
    assert [line["template"] for line in only] == ["Something went wrong (ref. {ref})"]
    assert [x["category"] for x in c.get("/api/v1/admin/activity?category=nox").json()["items"]] == ["nox"]
    assert len(c.get("/api/v1/admin/activity?search=balade").json()["items"]) == 1


def test_repeats_group_and_later_successes_mark_problems_fixed(client):
    c, db = client
    admin(client)
    from houseos.models import User

    owner = db.query(User).first().id
    db.add(
        QueueItem(
            id="auto-1",
            owner_id=owner,
            source_url="https://x.invalid/1",
            title="Lost",
            position=1,
            metadata_json={"auto": True},
        )
    )
    db.add(
        QueueItem(id="song-2", owner_id=owner, source_url="https://x.invalid/2", title="Found", position=2)
    )
    for _ in range(3):  # auto play tried the same removed song three times
        emit(db, "music.metadata", {"item_id": "auto-1", "status": "failed", "code": "SOURCE_REMOVED"})
    emit(
        db,
        "system.note",
        {
            "text": "A background chore failed: {step} ({where})",
            "level": "problem",
            "step": "enrich",
            "where": "x.py:1",
        },
    )
    emit(db, "music.playback", {"item_id": "song-2", "status": "playing"})
    emit(db, "audit.music_add", {"item_id": "song-2"}, owner)
    db.commit()
    lines = c.get("/api/v1/admin/activity").json()["items"]
    added, playing, chore, lost = lines
    assert added["template"] == "Added {title} to the queue" and added["values"]["title"] == "Found"
    assert added["who"] and added["actor"] is None
    assert lost["count"] == 3 and lost["actor"] == "Auto play" and lost["values"]["code"] == "SOURCE_REMOVED"
    assert lost["care"] == "handled" and lost["resolved_at"] == playing["at"]
    assert chore["care"] == "needs" and chore["tried"] == "A background chore"
    needs = c.get("/api/v1/admin/activity?needs=true").json()["items"]
    assert [line["id"] for line in needs] == [chore["id"]]
