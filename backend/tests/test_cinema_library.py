from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import test_cinema
from houseos import cinema_library as library, files
from houseos.auth import Actor
from houseos.models import Record


@pytest.fixture
def movie_upload(tmp_path, monkeypatch):
    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    fixture.actor = Actor(
        "resident-one",
        "One",
        "resident",
        frozenset({"cinema.use", "files.write", "files.read", "files.shared.write"}),
    )
    root = tmp_path / "storage"
    (root / "blobs").mkdir(parents=True)
    (root / "media" / "movies").mkdir(parents=True)
    monkeypatch.setattr(library.settings, "data_root", root)
    monkeypatch.setattr(library.settings, "runtime_root", tmp_path / "runtime")
    monkeypatch.setattr(files, "storage_check", lambda: {"device": root.stat().st_dev})
    monkeypatch.setattr(library, "probe_file", lambda *_: {"video": {"codec": "h264"}, "duration": 60})
    identity = str(uuid4())
    (root / "blobs" / identity).write_bytes(b"synthetic-video-fixture")
    with Session(fixture.engine) as db:
        db.add(
            files.FileEntry(
                id=identity, owner_id=fixture.actor.id, scope="media", name="Film.mp4", size=23, version=1
            )
        )
        db.commit()
    yield fixture, root, identity
    fixture.tearDown()


def test_upload_moves_once_into_persistent_library_without_double_quota(movie_upload):
    fixture, root, identity = movie_upload
    body = {"file_id": identity, "version": 1, "media_id": fixture.title_id}
    with Session(fixture.engine) as db:
        assert files.media_usage(db) == (23, 0)
    response = fixture.client.post("/api/v1/cinema/library/import", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "ready" and result["library_index"] == "pending_observation"
    assert "_path" not in result
    assert not (root / "blobs" / identity).exists()
    assert len(list((root / "media" / "movies").iterdir())) == 1
    assert fixture.client.post("/api/v1/cinema/library/import", json=body).json() == result
    with Session(fixture.engine) as db:
        assert files.media_usage(db) == (23, 0)
        entry = db.get(files.FileEntry, identity)
        assert entry.storage_removed_at and entry.deleted_at
        record = db.get(Record, result["id"])
        assert record.data["media_id"] == fixture.title_id
        library.reconcile_index(db, [{"Id": "wrong-film", "Path": "/media/movies/wrong.mp4"}])
        assert record.data["library_index"] == "pending_observation"
        db.get(library.CinemaTitle, fixture.title_id).data = {"jellyfin_id": "actual-library-film"}
        db.flush()
        library.reconcile_index(
            db, [{"Id": "actual-library-film", "Path": "/media/movies/" + record.data["_filename"]}]
        )
        assert record.data["library_index"] == "indexed"
        assert record.data["jellyfin_id"] == "actual-library-film"
        assert record.data["library_media_id"] == fixture.title_id


def test_failed_commit_restores_upload_and_crash_intent_can_resume(movie_upload):
    fixture, root, identity = movie_upload
    with Session(fixture.engine, expire_on_commit=False) as db:
        original = db.commit
        commits = 0

        def commit():
            nonlocal commits
            commits += 1
            if commits == 2:
                raise RuntimeError("fixture database failure")
            original()

        with patch.object(db, "commit", side_effect=commit):
            with pytest.raises(RuntimeError):
                library.import_movie(library.LibraryImport(file_id=identity, version=1), fixture.actor, db)
        assert (root / "blobs" / identity).exists()
        assert list((root / "media" / "movies").iterdir()) == []
        record = db.query(Record).filter(Record.kind == "cinema.local_media").one()
        assert record.data["state"] == "importing"
        # Simulate death after the atomic move but before the completion transaction.
        (root / "blobs" / identity).rename(root / "media" / "movies" / record.data["_filename"])
        response = library.import_movie(library.LibraryImport(file_id=identity, version=1), fixture.actor, db)
        assert response["state"] == "ready"
        assert files.media_usage(db) == (23, 0)


def test_private_other_owner_changed_and_symlink_uploads_are_not_imported(movie_upload):
    fixture, root, identity = movie_upload
    endpoint = "/api/v1/cinema/library/import"
    assert fixture.client.post(endpoint, json={"file_id": identity, "version": 2}).status_code == 409
    with Session(fixture.engine) as db:
        db.get(files.FileEntry, identity).scope = "personal"
        db.commit()
    assert fixture.client.post(endpoint, json={"file_id": identity, "version": 1}).status_code == 422
    with Session(fixture.engine) as db:
        db.get(files.FileEntry, identity).scope = "media"
        db.commit()
    (root / "blobs" / identity).unlink()
    (root / "blobs" / identity).symlink_to("/etc/passwd")
    assert fixture.client.post(endpoint, json={"file_id": identity, "version": 1}).status_code == 409
    assert list((root / "media" / "movies").iterdir()) == []
    fixture.actor = Actor(
        "resident-two",
        "Two",
        "resident",
        frozenset({"cinema.use", "files.write", "files.read", "files.shared.write"}),
    )
    assert fixture.client.post(endpoint, json={"file_id": identity, "version": 1}).status_code == 403
