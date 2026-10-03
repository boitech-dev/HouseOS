import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session
from houseos.auth import Actor
from houseos import music


def test_repeat_modes_recycle_existing_items_without_duplicate_history():
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.control"}))
    with Session(fixture.engine, expire_on_commit=False) as db:
        q = db.get(music.QueueState, 1)
        song = music.QueueItem(
            id="song",
            owner_id="one",
            source_url="https://www.youtube.com/watch?v=abcdefghijk",
            position=1,
            status="playing",
            metadata_json={"history_recorded": True},
        )
        upcoming = music.QueueItem(
            id="next",
            owner_id="one",
            source_url="https://www.youtube.com/watch?v=lmnopqrstuv",
            position=2,
            status="ready",
        )
        db.add_all([song, upcoming])
        q.current_id = "song"
        db.commit()
        for mode in ("one", "queue", "off"):
            result = music.control(
                music.Control(
                    action="repeat", value=mode, expected_version=q.version, idempotency_key="repeat-" + mode
                ),
                actor,
                db,
            )
            assert result["status"] == "accepted"
            assert music.repeat_mode(db) == mode
            q.current_id, song.status = "song", "playing"
            music.complete_track(db, q, song)
            if mode == "one":
                assert q.current_id == "song" and song.status == "ready"
                assert song.metadata_json["resume_position"] == 0
            elif mode == "queue":
                assert q.current_id is None and song.position > upcoming.position and song.status == "ready"
            else:
                assert song.status == "completed" and q.current_id is None
        db.commit()
        assert db.query(music.QueueItem).filter(music.QueueItem.id.in_(["song", "next"])).count() == 2


def test_control_values_are_validated_by_action():
    for action, value in [("repeat", 12), ("volume", "queue"), ("repeat", None), ("volume", float("nan"))]:
        with pytest.raises(ValidationError):
            music.Control(action=action, value=value, expected_version=1, idempotency_key="invalid-test")


def test_retained_music_counts_toward_shared_media_quota():
    from test_music_library import MusicLibraryTests
    from houseos.models import Record
    from houseos.files import media_usage

    fixture = MusicLibraryTests()
    fixture.setUp()
    with Session(fixture.engine) as db:
        db.add(
            Record(
                kind="music.download",
                owner_id="one",
                visibility="house",
                data={"state": "ready", "size": 4096},
            )
        )
        db.add(
            Record(
                kind="music.download",
                owner_id="one",
                visibility="house",
                data={"state": "reserved", "size": 2048},
            )
        )
        db.commit()
        used, reserved = media_usage(db)
        assert used >= 4096 and reserved >= 2048


def test_repeat_job_changes_policy_without_touching_player(tmp_path):
    from unittest.mock import patch
    from types import SimpleNamespace
    from test_music_library import MusicLibraryTests
    from houseos import worker
    from houseos.models import Operation

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.control"}))
    with Session(fixture.engine) as db:
        result = music.control(
            music.Control(
                action="repeat", value="queue", expected_version=1, idempotency_key="worker-repeat"
            ),
            actor,
            db,
        )
    with (
        patch.object(worker, "SessionLocal", lambda: Session(fixture.engine)),
        patch.object(worker, "settings", SimpleNamespace(runtime_root=tmp_path)),
        patch.object(worker, "bridge") as player,
    ):
        job = worker.claim("repeat-test", ("music.control",))
        assert job is not None
        worker.run_job(job)
        player.assert_not_called()
    with Session(fixture.engine) as db:
        assert db.get(Operation, result["operation_id"]).state == "completed"
