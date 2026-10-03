from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from houseos.db import Base
from houseos.models import User
from houseos.music import QueueItem, QueueState
from houseos.worker import preparation_window, reconcile_player_restart


def test_window_and_restart_reconciliation(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "music.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            User(id="resident", name="Resident", username="resident", password_hash="unused", role="resident")
        )
        db.add(QueueState(id=1, current_id="0", desired="playing"))
        for i in range(10):
            db.add(
                QueueItem(
                    id=str(i),
                    owner_id="resident",
                    source_url="https://example.com/song",
                    position=i,
                    status="playing" if i == 0 else "pending_metadata",
                    metadata_json={},
                )
            )
        db.commit()
        assert [i.id for i in preparation_window(db)] == ["0", "1", "2"]
    with (
        patch("houseos.worker.SessionLocal", lambda: Session(engine)),
        patch("houseos.worker.fetch"),
    ):
        assert (
            reconcile_player_restart({"status": "observed", "idle": False, "item_id": "0", "paused": False})
            is True
        )
        with Session(engine) as db:
            assert db.get(QueueState, 1).desired == "playing"
            db.get(QueueState, 1).desired = "paused"
            db.commit()
        assert (
            reconcile_player_restart(
                {"status": "observed", "idle": False, "item_id": "other", "paused": False}
            )
            is None
        )
        with Session(engine) as db:
            assert db.get(QueueState, 1).desired == "paused"
            assert db.get(QueueState, 1).current_id is None
    engine.dispose()


def test_metadata_is_claimed_beyond_preload_window(tmp_path, monkeypatch):
    from houseos import worker
    from houseos.models import Job

    engine = create_engine("sqlite:///" + str(tmp_path / "metadata.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(worker, "settings", SimpleNamespace(runtime_root=tmp_path))
    with Session(engine) as db:
        db.add(
            User(id="resident", name="Resident", username="resident", password_hash="unused", role="resident")
        )
        db.add(QueueState(id=1, current_id="0", desired="playing"))
        for i in range(12):
            db.add(
                QueueItem(
                    id=str(i),
                    owner_id="resident",
                    source_url="https://example.com/song",
                    position=i,
                    status="playing" if i == 0 else "pending_metadata",
                    metadata_json={},
                )
            )
        db.add(
            Job(
                id="last-job",
                logical_key="last",
                kind="music.metadata",
                actor_id="resident",
                payload={"item_id": "11"},
            )
        )
        db.commit()
    claimed = worker.claim("test", ("music.metadata",))
    assert claimed and claimed[3]["item_id"] == "11"
    engine.dispose()


def test_metadata_is_looked_up_in_play_order(tmp_path, monkeypatch):
    """A playlist import makes many lookups at once: the next song to play goes first."""
    from datetime import timedelta
    from houseos import worker
    from houseos.db import utcnow
    from houseos.models import Job

    engine = create_engine("sqlite:///" + str(tmp_path / "order.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(worker, "settings", SimpleNamespace(runtime_root=tmp_path))
    now = utcnow() - timedelta(minutes=1)
    with Session(engine) as db:
        db.add(User(id="r", name="R", username="r", password_hash="unused", role="resident"))
        db.add(QueueState(id=1, desired="playing"))
        for i in range(6):
            db.add(
                QueueItem(
                    id=str(i),
                    owner_id="r",
                    source_url="https://example.com/s",
                    position=i,
                    status="pending_metadata",
                    metadata_json={},
                )
            )
            # Created in reverse: the last song's lookup is the oldest job.
            db.add(
                Job(
                    logical_key="metadata:" + str(i),
                    kind="music.metadata",
                    actor_id="r",
                    payload={"item_id": str(i)},
                    next_run=now - timedelta(seconds=i),
                )
            )
        db.commit()
    order = [worker.claim("test", ("music.metadata",))[3]["item_id"] for _ in range(3)]
    assert order == ["0", "1", "2"]
    engine.dispose()


def test_planned_update_restart_resumes_music(tmp_path, monkeypatch):
    from houseos import worker

    engine = create_engine("sqlite:///" + str(tmp_path / "planned.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(worker, "settings", SimpleNamespace(runtime_root=tmp_path))
    (tmp_path / "run").mkdir()
    (tmp_path / "run/resume-music").touch()
    with Session(engine) as db:
        db.add(User(id="r", name="R", username="r", password_hash="unused", role="resident"))
        db.add(QueueState(id=1, current_id="0", desired="playing"))
        db.add(
            QueueItem(
                id="0",
                owner_id="r",
                source_url="https://example.com/a",
                position=0,
                status="playing",
                metadata_json={"last_position": 42},
            )
        )
        db.commit()
    reconcile_player_restart({"status": "unavailable"})
    with Session(engine) as db:
        q, item = db.get(QueueState, 1), db.get(QueueItem, "0")
        assert (q.desired, q.current_id, item.status) == ("playing", None, "ready")
        assert item.metadata_json["resume_position"] == 42
    assert not (tmp_path / "run/resume-music").exists()  # once only: a crash later still pauses
    engine.dispose()
