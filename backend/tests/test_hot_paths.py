"""Checks for the hot-path shortcuts: each one must still give the answer the long way did."""

import json
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from houseos import files
from houseos.config import settings


def test_findmnt_is_remembered_but_the_device_is_compared_every_time(monkeypatch, tmp_path):
    device, runs = [7], []

    def fake_stat(path, *args, **kwargs):
        return SimpleNamespace(st_rdev=7, st_dev=device[0])

    def fake_run(*args, **kwargs):
        runs.append(args)
        return SimpleNamespace(stdout=json.dumps({"filesystems": [{"uuid": "u", "target": str(tmp_path)}]}))

    monkeypatch.setattr(settings, "storage_container", False)
    monkeypatch.setattr(settings, "storage_mount", tmp_path)
    monkeypatch.setattr(settings, "storage_uuid", "u")
    (tmp_path / "houseos").mkdir()
    monkeypatch.setattr(settings, "data_root", tmp_path / "houseos")
    monkeypatch.setattr(files, "FINDMNT", {})
    monkeypatch.setattr(files.subprocess, "run", fake_run)
    fake_os = SimpleNamespace(stat=fake_stat, statvfs=os.statvfs, ST_RDONLY=os.ST_RDONLY)
    monkeypatch.setattr(files, "os", fake_os)
    assert files.storage_check()["status"] == "healthy"
    assert files.storage_check()["status"] == "healthy"
    assert len(runs) == 1
    device[0] = 8  # another disk mounted there: refused at once, without findmnt
    with pytest.raises(HTTPException):
        files.storage_check()
    assert len(runs) == 1


def test_stats_count_from_rows_read_once():
    from datetime import timedelta

    from sqlalchemy.orm import Session

    from houseos import stats
    from houseos.db import utcnow
    from houseos.models import Record

    with Session(queue_db()) as db:
        roms = (
            ("Zelda", {}),
            ("ZELDA!", {}),
            ("Mario", {"hidden": True}),
            ("Metroid", {"duplicate_of": "x"}),
        )
        for title, extra in roms:
            db.add(Record(kind="game.rom", owner_id="u", data={"system": "nes", "title": title, **extra}))
        old = utcnow() - timedelta(days=30)
        db.add(Record(kind="household.calendar", owner_id="u", visibility="house", created_at=old, data={}))
        db.add(Record(kind="household.calendar", owner_id="u", visibility="house", data={}))
        db.commit()
        assert stats.game_numbers(db)["library"] == 1  # versions together; hidden and duplicates out
        rows = stats.house_records(db)
        since = utcnow() - timedelta(days=7)
        assert stats.house_counters(db, rows=rows)["planner"] == {"u": 2}
        assert stats.house_counters(db, since, rows)["planner"] == stats.house_counters(db, since)["planner"]
        assert stats.house_counters(db, since, rows)["planner"] == {"u": 1}


def queue_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from houseos.db import Base
    from houseos.models import User

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id="u", name="U", username="u", password_hash="x", role="resident"))
        db.commit()
    return engine


def test_a_limited_window_is_a_prefix_of_the_whole_queue():
    from sqlalchemy.orm import Session

    from houseos.music import QueueItem, QueueState
    from houseos.worker import preparation_window

    engine = queue_db()
    with Session(engine) as db:
        db.add(QueueState(id=1, desired="playing"))
        for i in range(6):
            meta = {"pinned_at": "2026-01-01"} if i == 4 else {}
            db.add(
                QueueItem(
                    id=str(i), owner_id="u", source_url="s", position=i, status="ready", metadata_json=meta
                )
            )
        db.commit()
        for current in (None, "2"):
            db.get(QueueState, 1).current_id = current
            whole = [item.id for item in preparation_window(db, limit=None)]
            for n in range(7):
                assert [item.id for item in preparation_window(db, limit=n)] == whole[: n + 1]


def test_a_removed_download_is_cancelled_once(monkeypatch):
    from sqlalchemy.orm import Session

    from houseos import worker
    from houseos.music import QueueItem

    engine = queue_db()
    with Session(engine) as db:
        meta = {"download_state": "downloading"}
        db.add(
            QueueItem(
                id="gone", owner_id="u", source_url="s", position=1, status="removed", metadata_json=meta
            )
        )
        db.commit()
    asked = []
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(worker, "fetch", lambda action, **kw: asked.append(action) or {"status": "failed"})
    worker.cancel_removed_downloads()
    worker.cancel_removed_downloads()  # the fetcher is down: not asked again every tick
    assert asked == ["cancel_download"]
