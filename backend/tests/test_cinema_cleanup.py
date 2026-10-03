"""Temporary cinema cache cleanup never touches active playback or saved libraries."""

from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from houseos import cinema
from houseos.cinema_cleanup import maintain_cinema_cache


@pytest.fixture
def cache(tmp_path, monkeypatch):
    import test_cinema

    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    fixture.workflow()
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    identity = str(uuid4())
    job_id = str(uuid4())
    with Session(fixture.engine) as db:
        row = db.get(cinema.CinemaWorkflow, "workflow-one")
        row.id = identity
        row.state = "completed"
        row.data = {**row.data, "_prepared": {"path": "not-trusted-for-deletion"}}
        db.add(
            cinema.CinemaPreparation(
                id=job_id,
                workflow_id=identity,
                owner_id=row.owner_id,
                workflow_version=1,
                state="done",
                finished_at=cinema.utcnow(),
            )
        )
        db.commit()
    directory = tmp_path / "cinema" / identity
    directory.mkdir(parents=True)
    (directory / "segment.m4s").write_bytes(b"temporary")
    saved = tmp_path / "saved-library"
    saved.mkdir()
    (saved / "movie.mp4").write_bytes(b"keep")
    yield fixture, identity, job_id, directory, saved
    fixture.tearDown()


def test_terminal_cache_removed_saved_library_preserved(cache):
    fixture, identity, job_id, directory, saved = cache
    (directory / "link").symlink_to(saved, target_is_directory=True)
    with Session(fixture.engine) as db:
        assert maintain_cinema_cache(db) == 1
        db.commit()
        assert db.get(cinema.CinemaPreparation, job_id).state == "purged"
        assert "_prepared" not in db.get(cinema.CinemaWorkflow, identity).data
    assert not directory.exists() and (saved / "movie.mp4").read_bytes() == b"keep"


@pytest.mark.parametrize("guard", ["playing", "job", "relay", "device", "symlink"])
def test_active_and_symlink_roots_are_preserved(cache, guard):
    fixture, identity, job_id, directory, saved = cache
    with Session(fixture.engine) as db:
        if guard == "playing":
            db.get(cinema.CinemaWorkflow, identity).state = "playing_observed"
        elif guard == "job":
            db.get(cinema.CinemaPreparation, job_id).state = "running"
        elif guard == "relay":
            db.add(
                cinema.CinemaRelay(
                    token_hash="a" * 64,
                    workflow_id=identity,
                    device_address="192.0.2.17",
                    path=str(directory),
                    mime="video/mp4",
                    expires_at=cinema.utcnow() + timedelta(hours=1),
                )
            )
        elif guard == "device":
            db.get(cinema.CinemaDevice, fixture.device_id).owner_workflow = identity
        else:
            (directory / "segment.m4s").unlink()
            directory.rmdir()
            directory.symlink_to(saved, target_is_directory=True)
        db.commit()
        assert maintain_cinema_cache(db) == 0
        assert db.get(cinema.CinemaPreparation, job_id).state != "purged"
    assert directory.exists() and (saved / "movie.mp4").exists()
