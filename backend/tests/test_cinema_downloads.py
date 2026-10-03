from sqlalchemy.orm import Session
from houseos.cinema import CinemaWorkflow, CinemaTitle
from houseos.db import utcnow
import test_cinema


def test_downloads_survive_navigation_and_are_owner_scoped():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with Session(f.engine) as db:
            title = CinemaTitle(
                id="download-title", canonical_id="fixture:download", title="Download", kind="movie", data={}
            )
            db.add(title)
            for identity, owner, kind in [
                ("mine", "resident-one", "save_local"),
                ("other", "other-user", "save_local"),
                ("play", "resident-one", "playback"),
            ]:
                db.add(
                    CinemaWorkflow(
                        id=identity,
                        owner_id=owner,
                        media_id=title.id,
                        state="preparing",
                        version=3,
                        idempotency_key=identity,
                        data={"_kind": kind, "download": {"bytes": 20, "total": 100, "phase": "downloading"}},
                        updated_at=utcnow(),
                    )
                )
            db.commit()
        response = f.client.get("/api/v1/cinema/downloads")
        assert response.status_code == 200
        rows = response.json()["items"]
        assert [r["id"] for r in rows] == ["mine"]
        assert rows[0]["download"]["bytes"] == 20
        cancelled = f.client.post("/api/v1/cinema/workflows/mine/cancel", json={"version": 3})
        assert cancelled.status_code == 200
        assert f.client.get("/api/v1/cinema/downloads").json()["items"][0]["state"] == "cancelled"
    finally:
        f.tearDown()


def test_progress_keeps_revision_and_cannot_overwrite_cancellation():
    from types import SimpleNamespace
    from houseos.cinema_prepare import download_progress
    from houseos.playback import MediaError
    import pytest

    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with Session(f.engine, expire_on_commit=False) as db:
            row = CinemaWorkflow(
                id="progress",
                owner_id=f.actor.id,
                media_id="fixture",
                state="preparing",
                version=3,
                idempotency_key="progress",
                data={},
            )
            db.add(row)
            db.commit()
            job = SimpleNamespace(workflow_version=3)
            download_progress(db, row, job, 50, 100, "downloading")
            assert row.version == 3 and row.data["download"]["bytes"] == 50
            row.state = "cancelled"
            row.version = 4
            db.commit()
            with pytest.raises(MediaError):
                download_progress(db, row, job, 70, 100, "downloading")
            assert row.state == "cancelled" and row.data["download"]["bytes"] == 50
    finally:
        f.tearDown()


def test_text_subtitles_preferred_without_overriding_explicit_track():
    import pytest
    import test_playback
    from houseos.playback import compatibility, MediaError

    f = test_playback.PlaybackTests()
    f.setUp()
    f.media["subtitles"] = [
        {"id": "4", "codec": "hdmv_pgs_subtitle", "language": "fr", "default": True},
        *f.media["subtitles"],
    ]
    request = {"subtitles_on": True, "subtitle_language": "fr"}
    assert compatibility(f.media, f.caps, request)["subtitle"]["id"] == "2"
    with pytest.raises(MediaError):
        compatibility(f.media, f.caps, {**request, "subtitle_track": "4"})


def test_discovery_runs_while_preparation_is_busy(monkeypatch):
    import threading
    from contextlib import nullcontext
    from houseos import cinema_worker as worker
    import pytest

    started = threading.Event()
    release = threading.Event()
    observed = []

    def prepare():
        started.set()
        assert release.wait(3)

    def operation(db):
        assert started.wait(1)
        observed.append(not release.is_set())
        release.set()

    class Stop(BaseException):
        pass

    def stop(_):
        raise Stop()

    monkeypatch.setattr(worker, "prepare", prepare)
    monkeypatch.setattr(worker, "web", lambda: None)  # Watch → Web's lane: nothing waiting
    monkeypatch.setattr("houseos.cinema_web.recover", lambda db: None)
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(None))
    monkeypatch.setattr(worker, "process_one_operation", operation)
    monkeypatch.setattr(worker.time, "sleep", stop)
    with pytest.raises(Stop):
        worker.main()
    assert observed == [True]
