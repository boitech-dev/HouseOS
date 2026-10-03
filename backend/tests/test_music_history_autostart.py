"""Real MariaDB regression: queue intent, canonical URLs, minimal observed history."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from houseos import music as m, music_library as lib, fetcher
from houseos.db import new_id, utcnow
from houseos.models import Record, Operation


def url():
    return "https://soundcloud.com/test-" + new_id() + "/song"


def add(db, actor, source):
    return m.enqueue(m.Add(source_url=source, idempotency_key=new_id()), actor, db)


def test_enqueue_autostart_and_paused_request_replacement(music_domain):
    db, (alice, _, _), q = music_domain
    body = m.Add(source_url="https://m.youtube.com/watch?v=BaW_jenozKc&t=1m30s", idempotency_key=new_id())
    result = m.enqueue(body, alice, db)
    assert result["autoplay_requested"] and q.desired == "playing"
    item = db.get(m.QueueItem, result["item_id"])
    assert item.source_url == "https://www.youtube.com/watch?v=BaW_jenozKc"
    assert item.metadata_json["resume_position"] == 90
    assert m.enqueue(body, alice, db)["item_id"] == item.id
    with pytest.raises(HTTPException):
        m.enqueue(body.model_copy(update={"start_position": 95}), alice, db)
    q.desired = "paused"
    item.status = "paused"
    item.metadata_json = {**item.metadata_json, "last_position": 42}
    db.commit()
    replacement = add(db, alice, url())
    assert replacement["autoplay_requested"] and q.desired == "playing"
    assert q.current_id == replacement["item_id"]
    assert item.status == "ready" and item.metadata_json["resume_position"] == 42
    assert not add(db, alice, url())["autoplay_requested"]
    assert q.current_id == replacement["item_id"]
    assert q.sleep_at > utcnow() + timedelta(hours=4, minutes=59)


def test_playlist_and_local_paths_autostart(music_domain, monkeypatch):
    db, (alice, _, _), q = music_domain
    op = Operation(
        actor_id=alice.id,
        kind="music.playlist",
        state="needs_confirmation",
        expires_at=utcnow() + timedelta(minutes=5),
        idempotency_key=new_id(),
        data={"items": [{"source_url": url(), "title": "Song"}]},
    )
    db.add(op)
    db.commit()
    assert m.import_playlist(op.id, alice, db)["autoplay_requested"]
    db.execute(delete(m.QueueItem).where(m.QueueItem.owner_id == alice.id))
    db.commit()
    q.desired, q.current_id = "paused", None
    entry = SimpleNamespace(id=new_id(), version=1, name="Local song")
    monkeypatch.setattr(lib, "local_entry", lambda *args: entry)
    op = Operation(
        actor_id=alice.id,
        kind="music.local",
        state="needs_confirmation",
        expires_at=utcnow() + timedelta(minutes=5),
        idempotency_key=new_id(),
        data={"file_id": entry.id, "version": 1},
    )
    db.add(op)
    db.commit()
    assert lib.local_confirm(op.id, alice, db)["autoplay_requested"]
    assert q.desired == "playing"


def test_observed_history_minimal_dedup_private_favorites_and_pagination(music_domain):
    db, (alice, bob, _), q = music_domain
    sources = [url() for _ in range(7)]
    for index, source in enumerate(sources):
        item = m.QueueItem(
            owner_id=alice.id,
            source_url=source,
            title=f"Song {index}",
            position=index,
            status="completed",
            metadata_json={"duration": 90},
        )
        db.add(item)
        db.flush()
        valid = {"status": "observed", "item_id": item.id, "idle": False, "paused": False}
        for bad in ({}, dict(valid, paused=True), dict(valid, idle=True), dict(valid, item_id="other")):
            m.record_played(db, item, bad)
            assert not item.metadata_json.get("history_recorded")
        m.record_played(db, item, valid)
        db.flush()
        row = db.get(Record, m.history_key(source))
        assert set(row.data) == {"source_url", "played_at", "plays", "genre"} and row.data["plays"] == 1
        version = row.version
        m.record_played(db, item, valid)
        assert row.version == version
    db.commit()
    again = m.QueueItem(
        owner_id=bob.id,
        source_url=sources[0],
        title="Newest metadata",
        position=9,
        status="completed",
        metadata_json={"duration": 91},
    )
    db.add(again)
    db.flush()
    m.record_played(db, again, {"status": "observed", "item_id": again.id, "idle": False, "paused": False})
    saved = m.save_canonical_track(db, alice, sources[0])
    assert m.save_canonical_track(db, alice, sources[0]).id == saved.id
    db.commit()
    first = m.history(0, 5, alice, db)
    assert first["next_offset"] == 5 and len(first["items"]) == 5
    newest = first["items"][0]
    assert newest["requester"]["id"] == bob.id and newest["title"] == "Newest metadata"
    assert newest["favorite"]
    assert not m.history(0, 5, bob, db)["items"][0]["favorite"]
    assert len(m.history(5, 100, alice, db)["items"]) >= 2
    # Scrolling on with the cursor: every row once, in the same order, whatever arrives meanwhile.
    seen, page = [], m.history(0, 3, alice, db)
    while True:
        seen += [row["id"] for row in page["items"]]
        if not page["next_before"]:
            break
        page = m.history(0, 3, alice, db, None, page["next_before"])
    assert seen == [row["id"] for row in m.history(0, 100, alice, db)["items"]]
    assert len(list(db.scalars(select(Record).where(Record.id == m.history_key(sources[0]))))) == 1
    duplicate = Record(kind="saved_track", owner_id=alice.id, data={"source_url": sources[0]})
    db.add(duplicate)
    db.commit()
    m.delete_saved(saved.id, alice, db)
    assert not m.saved(alice, db)


@pytest.mark.parametrize(
    "source,seconds",
    [
        ("https://youtu.be/BaW_jenozKc?t=95", 95),
        ("https://music.youtube.com/watch?v=BaW_jenozKc&start=10", 10),
        ("https://www.youtube.com/live/BaW_jenozKc#t=1h2m3s", 3723),
        ("https://www.youtube.com/embed/BaW_jenozKc?time_continue=45", 45),
    ],
)
def test_youtube_offsets(source, seconds):
    assert m.canonical_source(source) == "https://www.youtube.com/watch?v=BaW_jenozKc"
    assert m.requested_start(source) == seconds


def test_shortlink_redirect_boundaries(monkeypatch):
    from houseos import cinema_adapters
    from urllib.parse import urlsplit

    target = ["https://soundcloud.com/Example/Track?si=tracking"]
    calls = []

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, *args, **kwargs):
            calls.append(args)

        def getresponse(self):
            return SimpleNamespace(status=302, getheader=lambda *args: target[0])

        def close(self):
            pass

    monkeypatch.setattr(cinema_adapters, "public_url", lambda value: (urlsplit(value), "93.184.216.34"))
    monkeypatch.setattr(cinema_adapters, "PinnedHTTPS", Connection)
    assert (
        fetcher.resolve_share_link("https://on.soundcloud.com/abcDEF")
        == "https://soundcloud.com/example/track"
    )
    for blocked in [
        "http://soundcloud.com/a/b",
        "https://127.0.0.1/a",
        "https://evil.example/a",
        "https://user:s@ soundcloud.com/a/b",
    ]:
        target[0] = blocked
        with pytest.raises(ValueError):
            fetcher.resolve_share_link("https://on.soundcloud.com/abcDEF")
    target[0] = "https://on.soundcloud.com/loop123"
    calls.clear()
    with pytest.raises(ValueError):
        fetcher.resolve_share_link("https://on.soundcloud.com/abcDEF")
    assert len(calls) == 4


def test_worker_records_only_exact_observed_playing(music_domain, monkeypatch, tmp_path):
    from houseos import worker
    from houseos.config import settings

    db, (alice, _, _), q = music_domain
    item = m.QueueItem(
        owner_id=alice.id,
        source_url=url(),
        title="Worker observation",
        position=1,
        status="playing",
        metadata_json={},
    )
    db.add(item)
    db.commit()
    q.current_id, q.desired = item.id, "playing"

    class WorkerSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def scalar(self, statement):
            return q

        def get(self, *args):
            return db.get(*args)

        def commit(self):
            db.commit()

        def __getattr__(self, name):
            return getattr(db, name)

    monkeypatch.setattr(worker, "SessionLocal", WorkerSession)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "audio_enabled", True)
    snapshot = {"status": "command_sent"}
    monkeypatch.setattr(
        worker, "bridge", lambda action: snapshot if action == "state" else {"status": "command_sent"}
    )
    worker.advance()
    assert not db.get(Record, m.history_key(item.source_url))
    q.desired = "playing"
    snapshot.update(status="observed", item_id="wrong", idle=False, paused=False, position=1)
    worker.advance()
    assert q.desired == "paused" and not db.get(Record, m.history_key(item.source_url))
    q.desired = "playing"
    snapshot.update(item_id=item.id, paused=True)
    worker.advance()
    assert not db.get(Record, m.history_key(item.source_url))
    snapshot["paused"] = False
    worker.advance()
    assert db.get(Record, m.history_key(item.source_url)).owner_id == alice.id
    # A newly requested song waits for its own metadata, then replaces the paused old song.
    item.status = "ready"
    requested = m.QueueItem(
        owner_id=alice.id,
        source_url=url(),
        title="New request",
        position=-1,
        status="pending_metadata",
        metadata_json={},
    )
    db.add(requested)
    db.commit()
    q.current_id = requested.id
    calls = []
    monkeypatch.setattr(worker, "fetch", lambda *args, **kwargs: {"status": "completed"})
    monkeypatch.setattr(
        worker,
        "bridge",
        lambda action, **kwargs: calls.append((action, kwargs)) or {"status": "command_sent"},
    )
    worker.advance()
    assert not calls and item.status == "ready"
    requested.status = "ready"
    db.commit()
    worker.advance()
    assert calls == [("load", {"item_id": requested.id, "position": 0})]
    assert requested.status == "buffering" and item.status == "ready"


def test_fair_rounds_and_skip_resumes(music_domain, monkeypatch):
    from houseos import house_settings

    db, (alice, bob, cara), q = music_domain
    monkeypatch.setattr(
        house_settings,
        "get_house_settings",
        lambda db: {"music_round_robin": True, "music_sleep_minutes": 300},
    )
    rows = []
    for position, actor in enumerate([alice, alice, alice, bob, bob, cara]):
        item = m.QueueItem(
            owner_id=actor.id,
            source_url=url(),
            title="Queued",
            position=position,
            status="ready",
            metadata_json={},
        )
        db.add(item)
        db.flush()
        rows.append(item)
    q.current_id, q.desired = rows[0].id, "paused"
    # Where fair turns place songs as they arrive (the queue keeps that order afterwards).
    assert [row.owner_id for row in m.fair_order(db, q, rows[1:])] == [
        bob.id,
        cara.id,
        alice.id,
        bob.id,
        alice.id,
    ]
    assert [row.id for row in m.fair_order(db, q, rows[1:]) if row.owner_id == alice.id] == [
        rows[1].id,
        rows[2].id,
    ]
    result = m.control(
        m.Control(action="skip", expected_version=q.version, idempotency_key=new_id()), alice, db
    )
    assert result["status"] == "accepted" and q.desired == "playing"
    with pytest.raises(HTTPException):
        m.control(
            m.Control(action="sleep", value=1441, expected_version=q.version, idempotency_key=new_id()),
            alice,
            db,
        )
    m.control(
        m.Control(action="sleep", value=300, expected_version=q.version, idempotency_key=new_id()), alice, db
    )
    assert q.sleep_at > utcnow() + timedelta(hours=4, minutes=59)


def test_atomic_batch_candidates_and_idempotency(music_domain):
    db, (alice, bob, _), q = music_domain
    candidates = []
    for index in range(3):
        row = Record(
            kind="music_candidate", owner_id=alice.id, data={"source_url": url(), "title": f"Choice {index}"}
        )
        db.add(row)
        db.flush()
        candidates.append(row)
    foreign = Record(
        kind="music_candidate", owner_id=bob.id, data={"source_url": url(), "title": "Private choice"}
    )
    db.add(foreign)
    db.commit()
    with pytest.raises(HTTPException):
        m.add_candidates(
            m.CandidateBatch(candidate_ids=[candidates[0].id, foreign.id], idempotency_key=new_id()),
            alice,
            db,
        )
    assert not list(db.scalars(select(m.QueueItem).where(m.QueueItem.owner_id == alice.id)))
    body = m.CandidateBatch(candidate_ids=[r.id for r in candidates], idempotency_key=new_id())
    result = m.add_candidates(body, alice, db)
    assert result["status"] == "accepted" and result["count"] == 3 and result["autoplay_requested"]
    assert [r["title"] for r in result["items"]] == ["Choice 0", "Choice 1", "Choice 2"]
    assert m.add_candidates(body, alice, db) == result
    assert len(list(db.scalars(select(m.QueueItem).where(m.QueueItem.owner_id == alice.id)))) == 3
    assert q.current_id == result["items"][0]["item_id"]


def test_clear_stops_current_and_late_command_preserves_new_song(music_domain, monkeypatch, tmp_path):
    from threading import Thread, Event
    from houseos import worker
    from houseos.config import settings
    from houseos.models import Job

    db, (alice, _, _), q = music_domain
    entries = []
    for status in ["playing", "ready", "pending_metadata", "awaiting_confirmation", "failed"]:
        item = m.QueueItem(
            owner_id=alice.id,
            source_url=url(),
            title=status,
            status=status,
            position=len(entries),
            metadata_json={},
        )
        db.add(item)
        db.flush()
        entries.append(item)
    q.current_id, q.desired = entries[0].id, "playing"
    op = m.control_effect(db, alice, q, "clear", None)
    db.commit()
    assert all(item.status == "removed" for item in entries) and q.desired == "paused"
    job = db.scalar(select(Job).where(Job.logical_key == "control:" + op.id))
    job.state, job.generation = "running", 1
    db.commit()

    class WorkerSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, identity):
            return q if model is m.QueueState else db.get(model, identity)

        def scalar(self, statement):
            return (
                q if statement.column_descriptions[0].get("entity") is m.QueueState else db.scalar(statement)
            )

        def __getattr__(self, name):
            return getattr(db, name)

    monkeypatch.setattr(worker, "SessionLocal", WorkerSession)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    calls = []
    monkeypatch.setattr(
        worker,
        "bridge",
        lambda action, **kw: (
            calls.append(action)
            or ({"status": "observed", "idle": True} if action == "state" else {"status": "command_sent"})
        ),
    )
    monkeypatch.setattr(worker, "fetch", lambda *args, **kw: {"status": "completed"})
    worker.run_job((job.id, 1, job.kind, dict(job.payload)))
    assert calls == ["stop", "state"] and q.current_id is None
    assert db.get(Operation, op.id).result["stop_observed"]
    # A clear waiting behind an in-flight load must recheck the newest queue identity.
    q.current_id = entries[0].id
    op = m.control_effect(db, alice, q, "clear", None)
    db.commit()
    job = db.scalar(select(Job).where(Job.logical_key == "control:" + op.id))
    job.state, job.generation = "running", 1
    db.commit()
    payload = (job.id, 1, job.kind, dict(job.payload))
    started = Event()
    calls.clear()

    def run():
        started.set()
        worker.run_job(payload)

    with worker.PLAYER_COMMANDS:
        thread = Thread(target=run)
        thread.start()
        assert started.wait(1)
        q.current_id = "new-requested-item"
        q.desired = "playing"
        assert not calls
    thread.join(3)
    assert not thread.is_alive()
    assert not calls and q.current_id == "new-requested-item"
    assert db.get(Job, job.id).error_code == "PLAYBACK_GENERATION_CHANGED"


def test_previous_selects_real_history_and_preserves_current(music_domain):
    db, (alice, _, _), q = music_domain
    prior = m.QueueItem(
        owner_id=alice.id,
        source_url=url(),
        title="Prior song",
        position=0,
        status="completed",
        metadata_json={},
    )
    current = m.QueueItem(
        owner_id=alice.id,
        source_url=url(),
        title="Current song",
        position=1,
        status="playing",
        metadata_json={"last_position": 18},
    )
    db.add_all([prior, current])
    db.flush()
    for item in [prior, current]:
        m.record_played(db, item, {"status": "observed", "idle": False, "paused": False, "item_id": item.id})
    q.current_id, q.desired = current.id, "playing"
    db.commit()
    result = m.control(
        m.Control(action="previous", expected_version=q.version, idempotency_key=new_id()), alice, db
    )
    selected = db.get(m.QueueItem, q.current_id)
    assert result["status"] == "accepted" and selected.source_url == prior.source_url
    assert selected.id != prior.id and selected.status == "pending_metadata"
    assert current.status == "ready" and current.metadata_json["resume_position"] == 18


def test_previous_keeps_going_back_instead_of_swapping_two_songs(music_domain):
    db, (alice, _, _), q = music_domain
    songs = [
        m.QueueItem(
            owner_id=alice.id, source_url=url(), title=t, position=i, status="completed", metadata_json={}
        )
        for i, t in enumerate(["First", "Second", "Third"])
    ]
    db.add_all(songs)
    db.flush()
    for step, item in enumerate(songs):
        m.record_played(db, item, {"status": "observed", "idle": False, "paused": False, "item_id": item.id})
        db.get(Record, m.history_key(item.source_url)).updated_at = utcnow() - timedelta(minutes=10 - step)
    q.current_id, q.desired = songs[2].id, "playing"
    db.commit()
    heard = []
    for _ in range(2):
        m.control(
            m.Control(action="previous", expected_version=q.version, idempotency_key=new_id()), alice, db
        )
        now = db.get(m.QueueItem, q.current_id)
        heard.append(now.source_url)
        # It plays: history moves it to the top, as a real play does.
        m.record_played(db, now, {"status": "observed", "idle": False, "paused": False, "item_id": now.id})
        db.commit()
    assert heard == [songs[1].source_url, songs[0].source_url]


def test_worker_tolerates_briefly_busy_audio_bridge(music_domain, monkeypatch, tmp_path):
    from houseos import worker
    from houseos.config import settings

    db, (alice, _, _), q = music_domain
    item = m.QueueItem(
        owner_id=alice.id,
        source_url=url(),
        title="Busy bridge",
        position=1,
        status="playing",
        metadata_json={},
    )
    db.add(item)
    db.commit()
    q.current_id, q.desired = item.id, "playing"

    class WorkerSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def scalar(self, statement):
            return q

        def __getattr__(self, name):
            return getattr(db, name)

    monkeypatch.setattr(worker, "SessionLocal", WorkerSession)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "audio_enabled", True)
    monkeypatch.setattr(worker, "bridge_misses", 0)
    monkeypatch.setattr(
        worker, "bridge", lambda action, **kw: {"status": "unavailable", "code": "AUDIO_BRIDGE_UNAVAILABLE"}
    )
    for _ in range(worker.BRIDGE_MISS_LIMIT - 1):
        worker.advance()
        assert q.desired == "playing"
    worker.advance()
    assert q.desired == "paused"
    # An answered poll resets the count.
    q.desired = "playing"
    monkeypatch.setattr(
        worker,
        "bridge",
        lambda action, **kw: {
            "status": "observed",
            "item_id": item.id,
            "idle": False,
            "paused": False,
            "position": 1,
        },
    )
    worker.advance()
    assert worker.bridge_misses == 0 and q.desired == "playing"
