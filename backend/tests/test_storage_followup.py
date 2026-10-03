import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from houseos import storage_admin as s, files, household
from houseos.auth import Actor, require_actor
from houseos.db import get_db, new_id
from houseos.models import Record


def test_shared_quota_inventory_and_versioned_admin_reclamation(domain, monkeypatch, tmp_path):
    db, (alice, bob, _) = domain
    monkeypatch.setattr(s, "storage_check", lambda: None)
    monkeypatch.setattr(s.settings, "data_root", tmp_path)
    personal = files.FileEntry(id=new_id(), owner_id=bob.id, name="private.bin", size=20, scope="personal")
    shared = files.FileEntry(id=new_id(), owner_id=alice.id, name="music.flac", size=30, scope="media")
    local = Record(
        id=new_id(),
        owner_id=alice.id,
        kind="cinema.local_media",
        visibility="house",
        data={"size": 40, "state": "ready", "_path": str(tmp_path / "media/movies/movie.mkv")},
    )
    reserve = files.UploadReservation(
        id=new_id(),
        owner_id=alice.id,
        request_key=new_id(),
        name="new.flac",
        scope="media",
        size=50,
        status="reserved",
        expires_at=files.utcnow(),
    )
    db.add_all([personal, shared, local, reserve])
    db.commit()
    assert files.media_usage(db) == (70, 50)
    assert files.usage(db, alice) == (0, 0)
    admin = Actor(alice.id, alice.name, "admin", alice.permissions)
    app = FastAPI()
    app.include_router(s.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_actor] = lambda: bob
    with TestClient(app) as client:
        assert client.get("/admin/storage").status_code == 403
        app.dependency_overrides[require_actor] = lambda: admin
        kept = client.get("/admin/storage/summary").json()
        assert {k["key"] for k in kept["kinds"]} == {"songs", "films", "games", "personal", "shared", "uploads", "trash"}
        assert sum(k["count"] for k in kept["kinds"]) >= 1 and kept["disk"]["total_bytes"] > 0
        body = client.get("/admin/storage").json()
        assert body["media"]["quota_bytes"] == 200 * 1024**3
        # The shared test database holds other files; look at this owner's own page.
        owned = client.get("/admin/storage", params={"owner": personal.owner_id}).json()
        row = next(r for r in owned["items"] if r["id"] == personal.id)
        assert "download_url" not in row and row["path"].endswith(personal.id)
        url = "/admin/storage/" + personal.id + "/reclaim"
        request = {"version": personal.version, "kind": "file", "action": "trash", "confirmed": True}
        assert client.post(url, json={**request, "confirmed": False}).status_code == 422
        assert client.post(url, json=request).status_code == 200
        assert client.post(url, json=request).status_code == 409
        removed = []
        monkeypatch.setattr(s, "unlink_blob", lambda r: removed.append(r.id))
        assert (
            client.post(url, json={**request, "version": personal.version, "action": "delete"}).status_code
            == 200
        )
        assert removed == [personal.id] and personal.storage_removed_at
        # An arbitrary path in a corrupt record cannot become an admin unlink primitive.
        local.data = {**local.data, "_path": "/etc/hosts"}
        db.commit()
        assert (
            client.post(
                "/admin/storage/" + local.id + "/reclaim",
                json={"version": local.version, "kind": "cinema", "action": "delete", "confirmed": True},
            ).status_code
            == 409
        )
    db.delete(local)
    db.commit()


def test_message_title_and_recipients(domain):
    db, (alice, bob, _) = domain
    data = household.normalize_data(
        db, alice, "messages", {"title": "Tea time", "body": "Meet downstairs", "recipient_ids": [bob.id]}
    )
    assert data["title"] == "Tea time" and data["recipient_ids"] == [bob.id]


def test_upload_quota_uses_correct_bucket_before_transport(domain, monkeypatch):
    from fastapi import HTTPException

    db, (alice, _, _) = domain
    monkeypatch.setattr(files, "storage_check", lambda: None)
    monkeypatch.setattr(
        files, "get_house_settings", lambda db: {"file_quota_bytes": 20, "max_upload_bytes": 1000}
    )
    monkeypatch.setattr(files.settings, "media_quota_bytes", 200)
    personal = files.FileEntry(id=new_id(), owner_id=alice.id, name="personal.bin", size=20, scope="personal")
    movie = Record(
        id=new_id(), owner_id=alice.id, kind="cinema.local_media", data={"size": 200, "state": "reserved"}
    )
    db.add_all([personal, movie])
    db.commit()
    for scope in ["personal", "media"]:
        with pytest.raises(HTTPException) as error:
            files.reserve_upload(
                files.UploadCreate(name="one.bin", scope=scope, size=1, idempotency_key=new_id()), alice, db
            )
        assert error.value.status_code == 413
        db.rollback()
    db.delete(movie)
    db.commit()


def test_media_quota_current_read_after_existing_snapshot(domain):
    from sqlalchemy.orm import Session

    db, (alice, _, _) = domain
    if db.bind.dialect.name != "mysql":
        pytest.skip("MariaDB repeatable-read concurrency check")
    before = files.media_usage(db)
    identity = new_id()
    with Session(db.get_bind()) as other:
        other.add(
            Record(
                id=identity,
                owner_id=alice.id,
                kind="cinema.local_media",
                data={"size": 123, "state": "reserved"},
            )
        )
        other.commit()
    assert files.media_usage(db) == before  # Ordinary RR read still sees the stale snapshot.
    files.lock_quota(db)
    assert files.media_usage(db, locked=True) == (before[0], before[1] + 123)
    db.rollback()
    db.delete(db.get(Record, identity))
    db.commit()


def test_resident_storage_totals_hide_metadata_and_music_delete_is_scoped(domain, monkeypatch, tmp_path):
    db, (alice, bob, _) = domain
    monkeypatch.setattr(s, "storage_check", lambda: None)
    monkeypatch.setattr(s.settings, "data_root", tmp_path)
    row = Record(
        id=new_id(),
        owner_id=alice.id,
        kind="music.download",
        visibility="house",
        data={"state": "ready", "title": "private-test-title", "size": 3},
    )
    row.data = {**row.data, "path": f"music-downloads/{row.id}.media"}
    root = tmp_path / "music-downloads"
    root.mkdir()
    media = root / (row.id + ".media")
    media.write_bytes(b"abc")
    db.add(row)
    db.commit()
    app = FastAPI()
    app.include_router(s.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_actor] = lambda: Actor(bob.id, bob.name, "resident", ["music.read"])
    with TestClient(app) as client:
        response = client.get("/music/storage")
        assert response.status_code == 200
        assert response.json()["categories"]["music"] == 3
        assert (
            "private-test-title" not in response.text
            and "source_url" not in response.text
            and "owner_id" not in response.text
        )
        assert client.get("/admin/storage").status_code == 403
        app.dependency_overrides[require_actor] = lambda: Actor(
            alice.id, alice.name, "admin", alice.permissions
        )
        assert any(item["id"] == row.id for item in client.get("/admin/storage").json()["music"])
        request = {"kind": "music", "version": row.version, "action": "delete", "confirmed": True}
        url = f"/admin/storage/{row.id}/reclaim"
        row.data = {**row.data, "path": "/etc/hosts"}
        db.commit()
        assert client.post(url, json=request).status_code == 409 and media.exists()
        row.data = {**row.data, "path": f"music-downloads/{row.id}.media"}
        db.commit()
        assert client.post(url, json=request).status_code == 200
        assert not media.exists() and row.deleted_at is not None
