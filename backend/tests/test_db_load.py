"""Load on the shared database: no pooled connection held across network waits, heartbeats
throttled, failing chores backed off, the anime list refreshed without being kept in memory."""

import asyncio
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from houseos import activity, anime_offline, cinema, maintenance, radio
from houseos import db as database
from houseos import files as f
from houseos.auth import RESIDENT, Actor
from houseos.db import new_id, utcnow

ACTOR = Actor("u", "U", "resident", RESIDENT)


class FakeDb:
    closed = False

    def close(self):
        self.closed = True


def test_image_routes_release_the_connection_before_fetching(monkeypatch):
    db = FakeDb()

    async def fetch(url, max_age=0):
        assert db.closed, "a cold Watch page would hold one pooled connection per poster"
        return "image"

    monkeypatch.setattr(cinema, "image_response", fetch)
    monkeypatch.setattr(cinema, "poster_source", lambda identity: ("https://x.example/p.jpg", None, None))
    assert asyncio.run(cinema.poster("title", ACTOR, db)) == "image"
    db.closed = False
    monkeypatch.setattr(radio, "cached_station", lambda *a: {"favicon": "https://x.example/l.png"})
    assert asyncio.run(radio.station_art(str(uuid.uuid4()), ACTOR, db)) == "image"


def test_upload_proxy_holds_no_connection_and_cancel_is_saved(domain, tmp_path, monkeypatch):
    db, (alice, _, _) = domain
    monkeypatch.setattr(f, "storage_check", lambda: None)
    monkeypatch.setattr(f.settings, "runtime_root", tmp_path)
    row = f.UploadReservation(
        id=new_id(),
        owner_id=alice.id,
        request_key=new_id(),
        name="a.bin",
        scope="personal",
        size=10,
        status="uploading",
        tus_id="abc",
        expires_at=utcnow() + timedelta(hours=1),
    )
    db.add(row)
    db.commit()

    class Transport:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def request(self, method, *a, **kw):
            assert not db.in_transaction(), "the chunk proxy must not hold a pooled connection"
            return SimpleNamespace(status_code=204 if method == "DELETE" else 200, headers={})

    monkeypatch.setattr(f.httpx, "AsyncClient", Transport)
    request = SimpleNamespace(method="HEAD", headers={"Tus-Resumable": "1.0.0"})
    assert asyncio.run(f.upload_content(row.id, request, alice, db)).status_code == 200
    request.method = "DELETE"
    assert asyncio.run(f.upload_content(row.id, request, alice, db)).status_code == 204
    with Session(db.get_bind()) as check:
        assert check.get(f.UploadReservation, row.id).status == "cancelled"


def test_heartbeat_writes_at_most_once_per_interval(monkeypatch):
    from houseos.events import heartbeat

    writes = []

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, model, name):
            return None

        def merge(self, row):
            writes.append(row.name)

        def commit(self):
            pass

    monkeypatch.setattr(database, "SessionLocal", Db)
    memo = {}
    for _ in range(5):  # the music worker ticks every second
        heartbeat("worker", every=10, _last=memo)
    assert writes == ["worker_heartbeat"]  # the row core.py and house_setup.py read


def test_failing_chore_backs_off_and_notes_at_most_hourly(monkeypatch):
    now = [1000.0]
    calls, notes = [], []

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def commit(self):
            pass

    def broken(db):
        calls.append(now[0])
        raise RuntimeError("offline")

    monkeypatch.setattr(maintenance, "STEPS", (broken,))
    monkeypatch.setattr(maintenance, "SessionLocal", Db)
    monkeypatch.setattr(maintenance.time, "monotonic", lambda: now[0])
    for name in ("failures", "retry_at", "noted_at"):
        monkeypatch.setattr(maintenance, name, {})
    monkeypatch.setattr(activity, "note", lambda *a, **kw: notes.append(a))
    for _ in range(40):  # 40 minutes of the 60 s maintenance loop
        maintenance.run_steps()
        now[0] += 60
    # Tried at 0, 1, 3, 7, 15 then every 15 min (was: every minute); one Activity note, not 40.
    assert [int(t - 1000) // 60 for t in calls] == [0, 1, 3, 7, 15, 30]
    assert len(notes) == 1


def test_anime_refresh_does_not_retry_a_failed_download_every_minute(tmp_path, monkeypatch):
    fetches = []

    def offline(*a, **kw):
        fetches.append(1)
        raise OSError("offline")

    monkeypatch.setattr(anime_offline, "settings", SimpleNamespace(runtime_root=tmp_path))
    monkeypatch.setattr(anime_offline, "public_fetch", offline)
    monkeypatch.setattr(anime_offline, "_retry_at", 0.0)
    with pytest.raises(anime_offline.MediaError):
        anime_offline.refresh()
    assert anime_offline.refresh() is None  # the next maintenance minute: no second 64 MB try
    assert fetches == [1]
