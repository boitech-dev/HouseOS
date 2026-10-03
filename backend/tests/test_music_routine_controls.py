"""Ordinary authorized controls do not need a second confirmation."""

from fastapi import HTTPException
import pytest
from sqlalchemy.orm import Session
from houseos import music
from houseos.models import Operation
from houseos.auth import Actor


def test_volume_jump_and_global_controls_are_direct_but_clear_is_confirmed(monkeypatch):
    from test_music_library import MusicLibraryTests

    case = MusicLibraryTests()
    case.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.control"}))
    with Session(case.engine, expire_on_commit=False) as db:
        queue = db.get(music.QueueState, 1)
        queue.volume, queue.version = 10, 8
        db.commit()
        # An unrelated queue change cannot block a simple global volume instruction.
        result = music.control(
            music.Control(action="volume", value=65, expected_version=1, idempotency_key="routine-volume"),
            actor,
            db,
        )
        assert result["status"] == "accepted" and "confirmation_id" not in result
        assert db.get(music.QueueState, 1).volume == 65
        assert db.get(Operation, result["operation_id"]).kind == "music.control"
        for action in ("pause", "mute", "sleep"):
            assert (
                music.control(
                    music.Control(
                        action=action, value=1, expected_version=1, idempotency_key="routine-" + action
                    ),
                    actor,
                    db,
                )["status"]
                == "accepted"
            )
        with pytest.raises(HTTPException):
            music.control(
                music.Control(action="seek", value=5, expected_version=1, idempotency_key="stale-seek"),
                actor,
                db,
            )
        db.rollback()
        version = db.get(music.QueueState, 1).version
        clear = music.control(
            music.Control(action="clear", expected_version=version, idempotency_key="confirm-clear"),
            actor,
            db,
        )
        assert clear["status"] == "needs_confirmation"


def test_fast_skips_each_skip_one_song_at_once():
    from test_music_library import MusicLibraryTests

    case = MusicLibraryTests()
    case.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.control"}))
    with Session(case.engine, expire_on_commit=False) as db:
        for n in range(1, 6):
            db.add(music.QueueItem(id=f"s{n}", owner_id="one", source_url=f"https://x.invalid/{n}",
                                   title=f"Song {n}", position=n, status="ready"))  # fmt: skip
        q = db.get(music.QueueState, 1)
        q.current_id, q.desired = "s1", "playing"
        db.get(music.QueueItem, "s1").status = "playing"
        db.commit()
        # A press with a stale view skips one; a gathered burst of two skips two; s4 is current.
        music.control(
            music.Control(action="skip", expected_version=0, idempotency_key="fast-skip-1"), actor, db
        )
        music.control(
            music.Control(action="skip", value=2, expected_version=0, idempotency_key="fast-skip-2"),
            actor,
            db,
        )
        statuses = [db.get(music.QueueItem, f"s{n}").status for n in range(1, 6)]
        assert statuses == ["skipped", "skipped", "skipped", "ready", "ready"]
        assert db.get(music.QueueState, 1).current_id == "s4"  # shown at once; the player loads it
