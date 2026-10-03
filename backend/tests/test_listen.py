"""Listen: radio plays when chosen, fair turns are visible, artwork is proxied safely and
playlists import past 50 songs in the background."""

import time
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from houseos import core, music as m, worker
from houseos.auth import Actor
from houseos.config import settings
from houseos.db import new_id
from houseos.models import Job, Operation, Record


class Session:
    """Worker/background code opens its own sessions; route them to the test session."""

    def __init__(self, db, q):
        self.db, self.q = db, q

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, model, identity):
        return self.q if model is m.QueueState else self.db.get(model, identity)

    def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        return self.q if entity is m.QueueState else self.db.scalar(statement)

    def __getattr__(self, name):
        return getattr(self.db, name)


def add(db, actor, source):
    return m.enqueue(m.Add(source_url=source, idempotency_key=new_id()), actor, db)


def song():
    return "https://soundcloud.com/test-" + new_id() + "/song"


def test_a_chosen_radio_station_plays_without_a_hidden_approval(music_domain, monkeypatch, tmp_path):
    db, (alice, _, _), q = music_domain
    result = add(db, alice, "radio:" + str(uuid.uuid4()))
    item = db.get(m.QueueItem, result["item_id"])
    assert item.metadata_json["live_approved"] and q.current_id == item.id
    job = db.scalar(select(Job).where(Job.logical_key == "metadata:" + item.id))
    job.state, job.generation = "running", 1
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(
        worker,
        "fetch",
        lambda *a, **k: {
            "status": "needs_confirmation",
            "code": "LIVE_STREAM_REQUIRES_APPROVAL",
            "is_live": True,
            "title": "FIP",
            "thumbnail": "https://cdn.example/fip.png",
        },
    )
    worker.run_job((job.id, 1, job.kind, dict(job.payload)))
    db.refresh(item)
    assert (item.status, item.error_code, item.title) == ("ready", None, "FIP")
    assert item.metadata_json["thumbnail"] == "https://cdn.example/fip.png"

    # The one-hour live window starts when the station actually starts.
    calls = []
    monkeypatch.setattr(settings, "audio_enabled", True)
    monkeypatch.setattr(
        worker, "fetch", lambda action, *a, **k: calls.append(action) or {"status": "completed"}
    )
    monkeypatch.setattr(worker, "bridge", lambda action, **k: {"status": "command_sent"})
    q.desired = "playing"
    worker.advance()
    db.refresh(item)
    assert calls == ["live_start"] and item.status == "buffering"
    assert 3500 < item.metadata_json["live_authorized_until"] - time.time() <= 3600
    assert not item.metadata_json["live_approved"]


def test_other_live_streams_still_ask_first(music_domain):
    db, (alice, _, _), q = music_domain
    item = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    assert not item.metadata_json["live_approved"]


def test_fair_turns_play_next_pin_shuffle_and_reorder_rights(music_domain, monkeypatch):
    db, (alice, bob, _), q = music_domain
    q.volume = 50
    monkeypatch.setattr(m, "bridge", lambda *a, **k: {"status": "unavailable"})
    playing = add(db, alice, song())["item_id"]
    a2, a3 = add(db, alice, song())["item_id"], add(db, alice, song())["item_id"]
    b1 = add(db, bob, song())["item_id"]
    state = m.state(alice, db)
    assert state["fair"] and state["current_id"] == playing
    order = [(i["id"], i["round"]) for i in state["items"][1:]]
    assert order == [(b1, 1), (a2, 1), (a3, 2)]  # Bob's turn first: Alice is playing now

    m.play_next(a3, m.QueueVersion(expected_version=q.version), alice, db)
    assert [i["id"] for i in m.state(alice, db)["items"][1:]] == [b1, a3, a2]
    with pytest.raises(HTTPException) as denied:
        m.play_next(b1, m.QueueVersion(expected_version=q.version), alice, db)
    assert denied.value.status_code == 403
    admin = Actor(alice.id, alice.name, "admin", alice.permissions)
    m.play_next(a2, m.QueueVersion(expected_version=q.version), admin, db)
    items = m.state(alice, db)["items"]
    assert items[1]["id"] == a2 and items[1]["pinned"] and items[1]["round"] is None

    before = {i: db.get(m.QueueItem, i).position for i in (b1,)}
    result = m.shuffle_mine(m.QueueVersion(expected_version=q.version), alice, db)
    assert result["shuffled"] == 2 and db.get(m.QueueItem, b1).position == before[b1]

    # Anyone moves anyone's waiting song, a guest too: fair turns only decided where it landed.
    guest = Actor(bob.id, bob.name, "guest", frozenset({"music.read", "music.queue"}))
    m.reorder(a3, m.Reorder(expected_version=q.version), guest, db)  # to the end
    assert m.state(alice, db)["items"][-1]["id"] == a3


def waiting_ids(db, actor):
    state = m.state(actor, db)
    return [i["id"] for i in state["items"] if i["id"] != state["current_id"]]


def test_moves_stick_and_new_songs_land_fairly(music_domain, monkeypatch):
    db, (alice, bob, cara), q = music_domain
    q.volume = 50
    monkeypatch.setattr(m, "bridge", lambda *a, **k: {"status": "unavailable"})
    add(db, cara, song())  # plays now
    a1, a2 = add(db, alice, song())["item_id"], add(db, alice, song())["item_id"]
    b1 = add(db, bob, song())["item_id"]
    assert waiting_ids(db, alice) == [a1, b1, a2]
    m.reorder(a2, m.Reorder(expected_version=q.version, before_item_id=a1), bob, db)  # Bob's move wins
    assert waiting_ids(db, alice) == [a2, a1, b1]
    b2 = add(db, bob, song())["item_id"]  # Bob's second song: round 2, after everyone's first
    assert waiting_ids(db, alice) == [a2, a1, b1, b2]


def test_one_veto_each_back_after_three_hours(music_domain, monkeypatch):
    from datetime import timedelta

    db, (alice, bob, _), q = music_domain
    q.volume = 50
    monkeypatch.setattr(m, "bridge", lambda *a, **k: {"status": "unavailable"})
    monkeypatch.setattr("houseos.worker.fetch", lambda *a, **k: {"status": "ok"}, raising=False)
    playing = add(db, alice, song())["item_id"]
    waiting, mine = add(db, alice, song())["item_id"], add(db, bob, song())["item_id"]
    with pytest.raises(HTTPException) as own:
        m.veto(mine, m.QueueVersion(expected_version=q.version), bob, db)
    assert own.value.status_code == 409  # your own song: just remove it
    assert m.veto(waiting, m.QueueVersion(expected_version=q.version), bob, db)["result"] == "removed"
    assert db.get(m.QueueItem, waiting).status == "removed"
    state = m.state(alice, db)
    assert state["last_veto"]["by"] == bob.name and m.state(bob, db)["veto_back_at"]
    with pytest.raises(HTTPException) as again:
        m.veto(playing, m.QueueVersion(expected_version=q.version), bob, db)
    assert again.value.detail["code"] == "VETO_RELOADING"
    used = db.scalars(select(Record).where(Record.kind == "music.veto", Record.owner_id == bob.id)).all()
    for row in used:
        row.created_at -= timedelta(hours=3, minutes=1)
    db.commit()
    assert m.veto(playing, m.QueueVersion(expected_version=q.version), bob, db)["result"] == "skipped"
    assert q.desired == "playing"  # the worker moves on to the next song


def test_artwork_only_from_known_hosts_except_station_logos(music_domain, monkeypatch):
    from houseos import cinema

    db, (alice, _, _), q = music_domain
    import asyncio

    monkeypatch.setattr(cinema, "image_on_disk", lambda url: b"jpeg:" + url.encode())
    item = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    for url, ok in [
        ("https://i.ytimg.com/vi/x/hqdefault.jpg", True),
        ("https://i1.sndcdn.com/artworks-x.jpg", True),
        ("https://evil.example/x.jpg", False),
        ("http://i.ytimg.com/vi/x/hq.jpg", False),
    ]:
        item = db.get(m.QueueItem, item.id)  # the route closes its session after reading
        item.metadata_json = {**item.metadata_json, "thumbnail": url}
        db.commit()
        if ok:
            assert asyncio.run(m.art("queue", item.id, alice, db)).body == b"jpeg:" + url.encode()
        else:
            with pytest.raises(HTTPException):
                asyncio.run(m.art("queue", item.id, alice, db))
    station = db.get(m.QueueItem, add(db, alice, "radio:" + str(uuid.uuid4()))["item_id"])
    station.metadata_json = {**station.metadata_json, "thumbnail": "https://radio.example/logo.png"}
    db.commit()
    assert asyncio.run(m.art("queue", station.id, alice, db)).status_code == 200
    assert m.item_json(station)["art"] == "/api/v1/music/art/queue/" + station.id


def test_long_playlists_import_in_pages_with_progress_and_cancel(music_domain, monkeypatch):
    from houseos import db as database

    db, (alice, _, _), q = music_domain
    source = "https://www.youtube.com/playlist?list=PL" + new_id().replace("-", "")[:20]
    tracks = [
        {
            "source_url": "https://www.youtube.com/watch?v=" + new_id()[:11],
            "title": f"Track {i}",
            "thumbnail": None,
        }
        for i in range(120)
    ]

    def fetch(action, source_url=None, item_id=None, start=1, **k):
        assert action == "playlist"
        return {"status": "completed", "items": tracks[start - 1 : start + 49], "total": 120}

    monkeypatch.setattr(worker, "fetch", fetch)
    monkeypatch.setattr(database, "SessionLocal", Session(db, q))
    preview = m.preview_playlist(m.Add(source_url=source, idempotency_key=new_id()), alice, db)
    assert preview["total"] == 120 and len(preview["items"]) == 50
    confirmed = m.import_playlist(preview["confirmation_id"], alice, db)
    assert confirmed["status"] == "running" and confirmed["added"] == 50
    for expected in (100, 120):
        job = db.scalar(
            select(Job).where(
                Job.kind == "music.playlist_import", Job.actor_id == alice.id, Job.state == "pending"
            )
        )
        assert core.activity(alice, db)["items"][0]["kind"] == "importing_playlist"
        job.state, job.generation = "running", 1
        db.commit()
        m.import_playlist_page(job.id, 1, dict(job.payload))
        assert db.get(Operation, confirmed["operation_id"]).result["added"] == expected
    assert db.get(Operation, confirmed["operation_id"]).state == "completed"
    queued = db.scalars(select(m.QueueItem).where(m.QueueItem.owner_id == alice.id)).all()
    assert len({row.source_url for row in queued}) == 120

    # Cancelling keeps what was queued and stops the next page.
    tracks[:] = [{**t, "source_url": t["source_url"] + "x"} for t in tracks]
    preview = m.preview_playlist(m.Add(source_url=source, idempotency_key=new_id()), alice, db)
    running = m.import_playlist(preview["confirmation_id"], alice, db)
    assert m.cancel_playlist_import(running["operation_id"], alice, db)["status"] == "cancelled"
    job = db.scalar(
        select(Job).where(
            Job.kind == "music.playlist_import", Job.actor_id == alice.id, Job.state == "pending"
        )
    )
    job.state, job.generation = "running", 1
    db.commit()
    m.import_playlist_page(job.id, 1, dict(job.payload))
    db.refresh(job)
    assert job.state == "cancelled"
    assert db.get(Operation, running["operation_id"]).result["added"] == 50


def metadata_run(db, q, item, monkeypatch, tmp_path, result):
    job = db.scalar(select(Job).where(Job.logical_key == "metadata:" + item.id))
    job.state, job.generation = "running", 1
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(worker, "fetch", lambda *a, **k: result)
    worker.run_job((job.id, 1, job.kind, dict(job.payload)))
    db.refresh(item)


def test_hours_long_tracks_stream_without_approval(music_domain, monkeypatch, tmp_path):
    db, (alice, _, _), q = music_domain
    long = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    metadata_run(
        db, q, long, monkeypatch, tmp_path, {"status": "completed", "title": "Calm", "duration": 10822}
    )
    assert (long.status, long.error_code) == ("ready", None)
    assert long.metadata_json["long_stream"] and m.item_json(long)["streamed"]
    huge = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    metadata_run(
        db, q, huge, monkeypatch, tmp_path, {"status": "completed", "title": "Huge", "duration": 20000}
    )
    assert (huge.status, huge.error_code) == ("failed", "TRACK_TOO_LONG")

    # It starts through the owned pipe (no download), and its lease is renewed while it plays.
    calls = []

    def fetch(action, *a, **k):
        calls.append(action)
        if action == "live_status":
            return {"state": "streaming", "expires_at": time.time() + 300}
        return {"status": "completed"}

    q.current_id, q.desired = long.id, "playing"
    db.commit()
    monkeypatch.setattr(worker, "fetch", fetch)
    monkeypatch.setattr(settings, "audio_enabled", True)
    monkeypatch.setattr(worker, "bridge", lambda action, **k: {"status": "command_sent"})
    worker.advance()
    db.refresh(long)
    assert calls == ["long_start"] and long.status == "buffering"
    monkeypatch.setattr(
        worker,
        "bridge",
        lambda action, **k: {"status": "observed", "idle": False, "paused": False, "item_id": long.id},
    )
    worker.long_checked.clear()
    worker.advance()
    assert calls[-2:] == ["live_status", "live_renew"]


def test_a_song_waiting_for_approval_never_blocks_the_queue(music_domain, monkeypatch, tmp_path):
    db, (alice, _, _), q = music_domain
    waiting = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    waiting.status, waiting.error_code = "awaiting_confirmation", "LIVE_STREAM_REQUIRES_APPROVAL"
    db.commit()
    ready = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    ready.status = "ready"
    q.current_id, q.desired = waiting.id, "playing"
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(settings, "audio_enabled", True)
    monkeypatch.setattr(worker, "prepare_audio", lambda source, item: {"status": "completed"})
    monkeypatch.setattr(worker, "bridge", lambda action, **k: {"status": "command_sent"})
    worker.advance()
    db.refresh(waiting)
    assert q.current_id not in (None, waiting.id)
    assert db.get(m.QueueItem, q.current_id).status == "buffering"
    assert waiting.status == "awaiting_confirmation"


def test_a_busy_fetcher_does_not_fail_a_pre_download(music_domain, monkeypatch):
    db, (alice, _, _), q = music_domain
    playing = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    nxt = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    playing.status, nxt.status = "playing", "ready"
    q.current_id = playing.id
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(
        worker, "prepare_audio", lambda source, item: {"status": "failed", "code": "SOURCE_BUSY"}
    )
    worker.prefetch_next()
    db.refresh(nxt)
    assert not nxt.metadata_json["prefetch_attempted"] and nxt.metadata_json["download_state"] is None


def test_a_song_that_stops_early_is_not_counted_as_played(music_domain, monkeypatch):
    db, (alice, _, _), q = music_domain
    item = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    item.status = "playing"
    item.metadata_json = {**item.metadata_json, "duration": 300, "last_position": 42}
    q.current_id, q.desired, q.failures = item.id, "playing", 0
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(settings, "audio_enabled", True)
    monkeypatch.setattr(worker, "bridge", lambda action, **k: {"status": "observed", "idle": True})
    worker.advance()
    db.refresh(item)
    assert (item.status, item.error_code) == ("failed", "PLAYBACK_INTERRUPTED")
    assert q.current_id is None and q.failures == 1


def test_temporary_fetch_trouble_retries_instead_of_failing(music_domain, monkeypatch, tmp_path):
    db, (alice, _, _), q = music_domain
    item = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    job = db.scalar(select(Job).where(Job.logical_key == "metadata:" + item.id))
    job.state, job.generation, job.attempts = "running", 1, 1
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(worker, "fetch", lambda *a, **k: {"status": "failed", "code": "SOURCE_BUSY"})
    worker.run_job((job.id, 1, job.kind, dict(job.payload)))
    db.refresh(job)
    db.refresh(item)
    assert job.state == "pending" and item.status == "pending_metadata"


def test_a_paused_mix_keeps_its_pipe(music_domain, monkeypatch):
    db, (alice, _, _), q = music_domain
    item = db.get(m.QueueItem, add(db, alice, song())["item_id"])
    item.status = "paused"
    item.metadata_json = {**item.metadata_json, "long_stream": True}
    q.current_id, q.desired = item.id, "paused"
    db.commit()
    calls = []

    def fetch(action, *a, **k):
        calls.append(action)
        return {"state": "streaming", "expires_at": time.time() + 60}

    monkeypatch.setattr(worker, "SessionLocal", Session(db, q))
    monkeypatch.setattr(worker, "fetch", fetch)
    worker.long_checked.clear()
    worker.advance()
    assert calls == ["live_status", "live_renew"]


def test_fetch_errors_name_the_real_reason(capsys):
    from houseos.fetcher import failure_code

    assert failure_code("ERROR: [youtube] x: Sign in to confirm your age") == "YOUTUBE_AGE_RESTRICTED"
    assert (
        failure_code("ERROR: [youtube] x: Sign in to confirm you're not a bot") == "YOUTUBE_SIGN_IN_REQUIRED"
    )
    assert failure_code("ERROR: [youtube] x: Video unavailable") == "SOURCE_REMOVED"
    assert (
        failure_code("ERROR: [youtube:tab] PLf3: YouTube said: The playlist does not exist.")
        == "PLAYLIST_NOT_FOUND"
    )
    assert failure_code("ERROR: The uploader has not made this video available in your country") == (
        "SOURCE_REGION_BLOCKED"
    )
    assert failure_code("ERROR: unable to download https://rr1.googlevideo.com/x?sig=1: HTTP Error 403") == (
        "SOURCE_URL_EXPIRED"
    )
    assert "googlevideo" not in capsys.readouterr().out  # URLs never reach the journal


def test_a_finished_stream_can_play_again(tmp_path):
    import os
    import uuid
    from houseos import fetcher_live

    identity = str(uuid.uuid4())
    fetcher_live.ACTIVE[identity] = {"item_id": identity, "state": "stopped", "expires_at": 0, "bytes": 1}
    os.mkfifo(tmp_path / (identity + ".media"))
    result = fetcher_live.execute(tmp_path, "live_start", identity, ["/bin/true"])
    assert result["status"] == "completed" and (tmp_path / (identity + ".media")).is_fifo()
    fetcher_live.execute(tmp_path, "live_stop", identity)
    fetcher_live.ACTIVE.pop(identity, None)


def test_auto_play_picks_always_wait_behind_requests(music_domain, monkeypatch):
    db, (alice, bob, cara), q = music_domain
    q.volume = 50
    monkeypatch.setattr(m, "bridge", lambda *a, **k: {"status": "unavailable"})
    add(db, cara, song())  # plays now
    a1 = add(db, alice, song())["item_id"]
    pick = m.QueueItem(
        owner_id=alice.id, source_url=song(), position=99, status="ready", metadata_json={"auto": "library"}
    )
    db.add(pick)
    db.commit()
    b1 = add(db, bob, song())["item_id"]
    a2 = add(db, alice, song())["item_id"]
    assert waiting_ids(db, alice) == [a1, b1, a2, pick.id]  # the pick took nobody's turn
    rounds = {i["id"]: i["round"] for i in m.state(alice, db)["items"]}
    assert rounds[pick.id] is None and rounds[a2] == 2
