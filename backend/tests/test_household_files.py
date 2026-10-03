"""Domain/HTTP tests on isolated SQLite; real local tusd for byte transport.

SQLite proves logic only; MariaDB locking is a separate integration gate.
"""

import hashlib
import os
import socket
import subprocess
import time
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from houseos import cinema as c, files as f, household as h  # cinema: its tables exist too
from houseos.auth import Actor, require_actor
from houseos.config import settings
from houseos.db import new_id
from houseos.models import User, Record


def create(db, actor, kind, data, key=None, **kwargs):
    return h.create_record(
        db, actor, kind, h.CreateRecord(data=data, idempotency_key=key or new_id(), **kwargs)
    )


def test_private_messages_and_idempotency(domain):
    db, (alice, bob, cara) = domain
    key = new_id()
    data = {"body": "Parcel in kitchen", "recipient_ids": [bob.id]}
    sent = create(db, alice, "messages", data, key)
    assert create(db, alice, "messages", data, key)["id"] == sent["id"]
    assert h.get_record(db, bob, "messages", sent["id"]).data["body"] == data["body"]
    with pytest.raises(HTTPException) as denied:
        h.get_record(db, cara, "messages", sent["id"])
    assert denied.value.status_code == 404
    assert len(h.inbox(bob, db, False, 100)["items"]) == 1
    assert h.inbox(cara, db, False, 100)["items"] == []
    with pytest.raises(HTTPException):
        create(db, alice, "messages", dict(data, body="Changed"), key)


def test_versions_grocery_review_and_undo(domain):
    db, (alice, bob, _) = domain
    note = create(db, alice, "board", {"title": "Quiet"})
    edited = h.update_record(db, alice, "board", note["id"], h.EditRecord(version=1, data={"pinned": True}))
    assert edited["version"] == 2
    with pytest.raises(HTTPException) as conflict:
        h.update_record(db, alice, "board", note["id"], h.EditRecord(version=1, data={"title": "stale"}))
    assert conflict.value.status_code == 409
    item = create(db, alice, "groceries", {"label": "Milk"})
    with pytest.raises(HTTPException) as duplicate:
        create(db, bob, "groceries", {"label": "milk"})
    assert duplicate.value.detail["code"] == "DUPLICATE_REVIEW"
    bought = h.update_record(
        db, bob, "groceries", item["id"], h.EditRecord(version=1, data={"purchased": True})
    )
    assert bought["data"]["purchased_by"] == bob.id
    undone = h.grocery_undo(item["id"], h.Version(version=2), bob, db)
    assert not undone["data"]["purchased"]


def test_notes_take_a_colour_and_pinned_ones_come_first(domain):
    db, (alice, _, _) = domain
    marker = new_id()[:8]
    pinned = create(db, alice, "board", {"title": marker + " pinned", "pinned": True, "color": "sun"})
    create(db, alice, "board", {"title": marker + " newer"})
    listed = h.list_records("board", alice, db, q=marker, limit=5, offset=0, include_expired=True)["items"]
    assert [row["id"] for row in listed][0] == pinned["id"] and listed[0]["data"]["color"] == "sun"
    with pytest.raises(Exception):
        create(db, alice, "board", {"title": "x", "color": "#ff0000"})  # only the theme's tones


def test_dst_and_occurrences(domain):
    db, (alice, _, _) = domain
    with pytest.raises(HTTPException):
        h.local_instant("2026-03-29T02:30:00", "Europe/Paris")
    with pytest.raises(HTTPException):
        h.local_instant("2026-10-25T02:30:00", "Europe/Paris")
    assert h.local_instant("2026-10-25T02:30:00", "Europe/Paris", 0) != h.local_instant(
        "2026-10-25T02:30:00", "Europe/Paris", 1
    )
    assert h.next_due(date(2026, 1, 31), "monthly", 2) == date(2026, 3, 31)
    today = date.today()
    template = create(
        db, alice, "tasks", {"title": "Bins", "due_date": today.isoformat(), "recurrence": "weekly"}
    )
    assert h.generate_occurrences(db, today) == 1
    assert h.generate_occurrences(db, today) == 0
    occurrence = db.scalar(select(h.TaskOccurrence).where(h.TaskOccurrence.template_id == template["id"]))
    h.task_action(occurrence.record_id, h.TaskAction(version=1, action="complete"), alice, db)
    assert db.get(Record, template["id"]).data["status"] == "open"


def test_filename_mount_and_mime_fail_closed(monkeypatch):
    for name in ("../x", ".env", "/etc/passwd", "a\\b", "new\nline"):
        with pytest.raises(ValueError):
            f.safe_name(name)
    assert f.sniff_mime(b'<svg onload="alert(1)">') == "application/octet-stream"
    monkeypatch.setattr(settings, "storage_uuid", "not-the-approved-drive")
    with pytest.raises(HTTPException) as failure:
        f.storage_check()
    assert failure.value.status_code == 503


def test_file_acl_confirmations_and_symlinks(file_app):
    client, db, (alice, bob, cara), root, app = file_app
    folder = client.post(
        "/api/v1/files/folders", json={"name": "Private", "idempotency_key": new_id()}
    ).json()
    entry = f.FileEntry(
        id=new_id(), owner_id=alice.id, parent_id=folder["id"], scope="personal", name="secret.txt", size=6
    )
    db.add(entry)
    db.commit()
    (root / "blobs" / entry.id).write_bytes(b"secret")
    app.dependency_overrides[require_actor] = lambda: bob
    assert client.get(f"/api/v1/files/{entry.id}/download").status_code == 404
    app.dependency_overrides[require_actor] = lambda: alice
    prepared = client.post(
        f"/api/v1/files/{entry.id}/actions/prepare",
        json={"version": 1, "action": "share", "recipient_id": bob.id},
    ).json()
    assert client.post(f"/api/v1/files/confirmations/{prepared['confirmation_id']}").status_code == 200
    assert client.post(f"/api/v1/files/confirmations/{prepared['confirmation_id']}").status_code == 409
    app.dependency_overrides[require_actor] = lambda: bob
    assert client.get(f"/api/v1/files/{entry.id}/download").content == b"secret"
    assert client.get(f"/api/v1/files/{entry.id}/download", headers={"Range": "bytes=1-3"}).content == b"ecr"
    app.dependency_overrides[require_actor] = lambda: cara
    assert client.get(f"/api/v1/files/{entry.id}/download").status_code == 404
    app.dependency_overrides[require_actor] = lambda: alice
    (root / "blobs" / entry.id).unlink()
    (root / "blobs" / entry.id).symlink_to("/etc/passwd")
    # Never follow links to host paths, even if metadata is valid.
    assert client.get(f"/api/v1/files/{entry.id}/download").status_code == 503


def test_real_tusd_resume_finalize(file_app, monkeypatch):
    client, db, (alice, bob, _), root, app = file_app
    binary = Path(os.environ.get("HOUSEOS_STATE", "/opt/houseos/state")) / "bin/tusd"
    if not binary.exists():
        pytest.skip("App-private tusd binary unavailable")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [
            str(binary),
            "-host",
            "127.0.0.1",
            "-port",
            str(port),
            "-upload-dir",
            str(root / "staging"),
            "-disable-download",
            "-verbose=false",
            "-show-startup-logs=false",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    monkeypatch.setattr(settings, "tusd_url", f"http://127.0.0.1:{port}")
    try:
        for _ in range(50):
            try:
                httpx.options(settings.tusd_url + "/files/", timeout=0.2)
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        data = b"A real resumed upload" * 1000
        create = {"name": "sample.txt", "size": len(data), "idempotency_key": new_id()}
        response = client.post("/api/v1/files/uploads", json=create)
        assert response.status_code == 201, response.text
        upload = response.json()
        assert client.post("/api/v1/files/uploads", json=create).json()["id"] == upload["id"]
        url = upload["upload_url"]
        headers = {
            "Tus-Resumable": "1.0.0",
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "0",
        }
        assert client.patch(url, content=data[:100], headers=headers).status_code == 204
        assert client.head(url, headers={"Tus-Resumable": "1.0.0"}).headers["Upload-Offset"] == "100"
        assert client.patch(url, content=data[100:], headers=headers).status_code == 409
        app.dependency_overrides[require_actor] = lambda: bob
        assert client.head(url, headers={"Tus-Resumable": "1.0.0"}).status_code == 404
        app.dependency_overrides[require_actor] = lambda: alice
        headers["Upload-Offset"] = "100"
        assert client.patch(url, content=data[100:], headers=headers).status_code == 204
        final = client.post(f"/api/v1/files/uploads/{upload['id']}/finalize")
        assert final.status_code == 200, final.text
        assert final.json()["file"]["checksum"] == hashlib.sha256(data).hexdigest()
        assert client.post(f"/api/v1/files/uploads/{upload['id']}/finalize").json() == final.json()
        downloaded = client.get(f"/api/v1/files/{upload['id']}/download")
        assert downloaded.content == data
        assert client.get("/api/v1/files/quota").json()["reserved_bytes"] == 0
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_atomic_batch_and_calendar_recurrence(domain):
    db, (alice, _, _) = domain
    milk = create(db, alice, "groceries", {"label": "Milk"})
    eggs = create(db, alice, "groceries", {"label": "Eggs"})
    batch = h.GroceryBatch(
        items=[{"id": milk["id"], "version": 1}, {"id": eggs["id"], "version": 7}],
        purchased=True,
        idempotency_key=new_id(),
    )
    with pytest.raises(HTTPException):
        h.grocery_batch(batch, alice, db)
    assert not db.get(Record, milk["id"]).data["purchased"]
    batch.items[1].version = 1
    result = h.grocery_batch(batch, alice, db)
    assert h.undo_grocery_batch(result["undo_id"], alice, db)["undone"]
    with pytest.raises(HTTPException):
        h.undo_grocery_batch(result["undo_id"], alice, db)
    event = create(
        db,
        alice,
        "calendar",
        {
            "title": "House tea",
            "start": "2026-03-22T10:00:00",
            "end": "2026-03-22T11:00:00",
            "timezone": "Europe/Paris",  # the clocks change on 29 March
            "recurrence": "weekly",
        },
    )
    items = h.agenda(date(2026, 3, 22), date(2026, 3, 29), alice, db)["items"]
    assert len(items) == 2
    assert items[0]["start_utc"].endswith("09:00:00Z")
    assert items[1]["start_utc"].endswith("08:00:00Z")
    assert items[0]["id"] == event["id"]
    normalized = h.normalize_data(
        db,
        alice,
        "calendar",
        {
            "title": "Offset event",
            "start": "2026-03-22T09:00:00Z",
            "end": "2026-03-22T10:00:00Z",
            "timezone": "Europe/Paris",
            "recurrence": "weekly",
        },
    )
    assert normalized["start"] == "2026-03-22T10:00:00"
    assert normalized["start_utc"] == "2026-03-22T09:00:00Z"


def test_confirmed_bulk_purge_and_drop_expiry(file_app):
    from datetime import timedelta
    from houseos.db import utcnow

    client, db, (alice, _, _), root, app = file_app
    entry = f.FileEntry(
        id=new_id(),
        owner_id=alice.id,
        scope="drop",
        name="expired.txt",
        size=4,
        expires_at=utcnow() - timedelta(hours=1),
    )
    db.add(entry)
    db.commit()
    (root / "blobs" / entry.id).write_bytes(b"drop")
    assert client.get(f"/api/v1/files/{entry.id}/download").status_code == 404
    result = f.maintain_files(db)
    assert result["expired_to_trash"] == 1
    assert result["permanently_removed"] == 0
    assert (root / "blobs" / entry.id).exists()
    preview = client.post(
        "/api/v1/files/bulk/prepare",
        json={"items": [{"id": entry.id, "version": entry.version}], "action": "purge"},
    )
    assert preview.status_code == 200, preview.text
    prepared = preview.json()
    assert prepared["preview"]["irreversible"]
    done = client.post("/api/v1/files/confirmations/" + prepared["confirmation_id"])
    assert done.status_code == 200, done.text
    assert not (root / "blobs" / entry.id).exists()
    assert db.get(f.FileEntry, entry.id).storage_removed_at is not None
    assert client.post("/api/v1/files/confirmations/" + prepared["confirmation_id"]).status_code == 409


def test_readonly_selected_root_containment(file_app, monkeypatch):
    import shutil
    from cryptography.fernet import Fernet
    from houseos.auth import passwords

    client, db, (alice, bob, _), root, app = file_app
    chosen = settings.import_root / ("houseos-readtest-" + new_id())
    if not settings.import_root.is_dir():
        pytest.skip("No import root on this machine (HOUSEOS_IMPORT_ROOT)")
    chosen.mkdir()
    try:
        (chosen / "fixture.txt").write_bytes(b"fixture")
        (chosen / "escape").symlink_to("/etc")
        admin = Actor(alice.id, alice.name, "admin", alice.permissions)
        user = db.get(User, alice.id)
        user.password_hash = passwords.hash("fixture-only-password")
        db.commit()
        monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
        app.dependency_overrides[require_actor] = lambda: admin
        bad = client.post(
            "/api/v1/files/roots/prepare",
            json={"name": "Bad", "path": "/etc", "current_password": "fixture-only-password"},
        )
        assert bad.status_code == 422
        prepared = client.post(
            "/api/v1/files/roots/prepare",
            json={
                "name": "Test root",
                "path": str(chosen),
                "reader_ids": [bob.id],
                "current_password": "fixture-only-password",
            },
        )
        assert prepared.status_code == 200, prepared.text
        selected = client.post("/api/v1/files/roots/confirm/" + prepared.json()["confirmation_id"])
        assert selected.status_code == 200, selected.text
        rid = selected.json()["id"]
        app.dependency_overrides[require_actor] = lambda: bob
        listing = client.get(f"/api/v1/files/roots/{rid}/entries").json()["items"]
        assert [x["name"] for x in listing] == ["fixture.txt"]
        assert (
            client.get(f"/api/v1/files/roots/{rid}/download", params={"file_id": listing[0]["id"]}).content
            == b"fixture"
        )
        assert (
            client.get(
                f"/api/v1/files/roots/{rid}/entries", params={"directory_id": f.root_token(rid, ["escape"])}
            ).status_code
            == 404
        )
        app.dependency_overrides[require_actor] = lambda: admin
        assert client.delete(f"/api/v1/files/roots/{rid}?version=1").status_code == 200
        app.dependency_overrides[require_actor] = lambda: bob
        assert (
            client.get(
                f"/api/v1/files/roots/{rid}/download", params={"file_id": listing[0]["id"]}
            ).status_code
            == 404
        )
        assert (chosen / "fixture.txt").read_bytes() == b"fixture"
    finally:
        assert chosen.name.startswith("houseos-readtest-")
        shutil.rmtree(chosen)


def test_mariadb_concurrent_versions_and_duplicate_review(domain):
    if os.environ.get("HOUSEOS_TEST_MARIADB") != "1":
        pytest.skip("MariaDB concurrency requires isolated database environment")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db, (alice, bob, _) = domain
    note = create(db, alice, "board", {"title": "Original"})
    barrier = Barrier(2)

    def edit(title):
        with Session(db.get_bind(), expire_on_commit=False) as worker:
            barrier.wait()
            try:
                h.update_record(
                    worker, alice, "board", note["id"], h.EditRecord(version=1, data={"title": title})
                )
                return 200
            except HTTPException as exc:
                worker.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ("First", "Second")))
    assert sorted(results) == [200, 409]
    db.rollback()
    barrier = Barrier(2)
    label = "concurrent-" + new_id()

    def add(actor):
        with Session(db.get_bind(), expire_on_commit=False) as worker:
            barrier.wait()
            try:
                create(worker, actor, "groceries", {"label": label})
                return 201
            except HTTPException as exc:
                worker.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(add, (alice, bob)))
    assert sorted(results) == [201, 409]


def test_mariadb_quota_reservation_race(file_app, monkeypatch):
    if os.environ.get("HOUSEOS_TEST_MARIADB") != "1":
        pytest.skip("MariaDB concurrency requires isolated database environment")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from types import SimpleNamespace

    client, db, (alice, _, _), root, app = file_app
    monkeypatch.setattr(
        f, "get_house_settings", lambda db: {"file_quota_bytes": 100, "max_upload_bytes": 100}
    )

    class Transport:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, *a, **kw):
            return SimpleNamespace(
                status_code=201, headers={"Location": "/files/" + new_id().replace("-", "")}
            )

    monkeypatch.setattr(f.httpx, "Client", Transport)
    barrier = Barrier(2)

    def reserve(name):
        with Session(db.get_bind(), expire_on_commit=False) as worker:
            # Deliberately establish an old RR snapshot before waiting on the quota lock.
            worker.scalar(select(User.id).where(User.id == alice.id))
            barrier.wait()
            try:
                f.reserve_upload(f.UploadCreate(name=name, size=60, idempotency_key=new_id()), alice, worker)
                return 201
            except HTTPException as exc:
                worker.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ("one.bin", "two.bin")))
    assert sorted(results) == [201, 413]


def test_staging_orphan_reconciliation_and_purge_scope_change(file_app):
    import os
    from datetime import timedelta
    from houseos.db import utcnow

    client, db, (alice, _, _), root, app = file_app
    unknown = root / "staging" / ("a" * 32)
    unknown.write_bytes(b"old partial")
    old = (utcnow() - timedelta(hours=49)).timestamp()
    os.utime(unknown, (old, old))
    fresh = root / "staging" / ("b" * 32)
    fresh.write_bytes(b"recent")
    assert f.reconcile_staging(db)["orphan_staging_files_removed"] == 1
    assert fresh.exists() and not unknown.exists()
    folder = client.post("/api/v1/files/folders", json={"name": "Group", "idempotency_key": new_id()}).json()
    first = client.post(
        f"/api/v1/files/{folder['id']}/actions/prepare", json={"version": 1, "action": "trash"}
    ).json()
    # A new child changes the approved scope even though the parent itself was not edited.
    child = client.post(
        "/api/v1/files/folders",
        json={"name": "New child", "parent_id": folder["id"], "idempotency_key": new_id()},
    )
    assert child.status_code == 201
    assert client.post("/api/v1/files/confirmations/" + first["confirmation_id"]).status_code == 409
    assert db.get(f.FileEntry, folder["id"]).trashed_at is None


def test_explicit_excerpt_bounds_integrity_and_share_revocation(file_app):
    client, db, (alice, bob, _), root, app = file_app
    raw = "Résumé du foyer\n".encode() * 400
    entry = f.FileEntry(
        id=new_id(),
        owner_id=alice.id,
        parent_id="",
        scope="personal",
        name="notes.md",
        size=len(raw),
        checksum=hashlib.sha256(raw).hexdigest(),
    )
    db.add(entry)
    db.commit()
    path = root / "blobs" / entry.id
    path.write_bytes(raw)
    result = f.read_excerpt(db, alice, entry.id, limit=21, version=1)
    assert len(result["text"]) == 21 and result["next_offset"] == 21
    assert result["untrusted_content"] and result["truncated"]
    with pytest.raises(HTTPException):
        f.read_excerpt(db, bob, entry.id)
    with pytest.raises(HTTPException):
        f.read_excerpt(db, alice, entry.id, version=2)
    prepared = client.post(
        f"/api/v1/files/{entry.id}/actions/prepare",
        json={"version": 1, "action": "share", "recipient_id": bob.id},
    ).json()
    assert client.post(f"/api/v1/files/confirmations/{prepared['confirmation_id']}").status_code == 200
    assert client.get(f"/api/v1/files/{entry.id}/grants").json()["items"] == [
        {"user_id": bob.id, "name": "Bob", "expires_at": None, "expired": False}
    ]
    assert f.read_excerpt(db, bob, entry.id, limit=10)["text"]
    prepared = client.post(
        f"/api/v1/files/{entry.id}/actions/prepare",
        json={"version": 2, "action": "unshare", "recipient_id": bob.id},
    ).json()
    assert client.post(f"/api/v1/files/confirmations/{prepared['confirmation_id']}").status_code == 200
    assert client.get(f"/api/v1/files/{entry.id}/grants").json()["items"] == []
    with pytest.raises(HTTPException):
        f.read_excerpt(db, bob, entry.id)
    path.write_bytes(b"X" * len(raw))
    with pytest.raises(HTTPException) as invalid:
        f.read_excerpt(db, alice, entry.id)
    assert invalid.value.status_code == 503
    path.unlink()
    path.symlink_to("/etc/passwd")
    with pytest.raises(HTTPException):
        f.read_excerpt(db, alice, entry.id)


def test_wall_text_only_author_and_pages(domain):
    db, actors = domain
    a, b, _ = actors
    marker = new_id()
    made = [
        h.create_record(
            db,
            a if i % 2 else b,
            "board",
            h.CreateRecord(data={"body": f"{marker} Wall message {i}"}, idempotency_key=new_id()),
        )
        for i in range(7)
    ]
    from datetime import datetime, timedelta

    for i, row in enumerate(made):
        db.get(Record, row["id"]).created_at = datetime(2026, 1, 1) + timedelta(seconds=i)
    db.commit()
    first = h.list_records("board", a, db, q=marker, limit=5, offset=0, include_expired=True)
    second = h.list_records("board", a, db, q=marker, limit=5, offset=5, include_expired=True)
    assert first["has_more"] and not second["has_more"]
    assert len(first["items"]) == 5 and len(second["items"]) == 2
    assert {r["id"] for r in first["items"]}.isdisjoint(r["id"] for r in second["items"])
    assert first["items"][0]["id"] == made[-1]["id"]
    assert first["items"][0]["author_name"] == "Bob"
    assert first["items"][0]["data"]["title"] == ""
    with pytest.raises(HTTPException):
        h.create_record(db, a, "board", h.CreateRecord(data={"body": "  "}, idempotency_key=new_id()))


def test_pictures_get_a_small_thumbnail_others_do_not(file_app):
    import io
    from PIL import Image

    client, db, (alice, bob, _), root, app = file_app
    picture = io.BytesIO()
    Image.new("RGB", (1200, 800), "orange").save(picture, format="PNG")
    photo = f.FileEntry(
        id=new_id(),
        owner_id=alice.id,
        scope="personal",
        name="p.png",
        mime="image/png",
        size=len(picture.getvalue()),
    )
    note = f.FileEntry(
        id=new_id(), owner_id=alice.id, scope="personal", name="n.txt", mime="text/plain", size=2
    )
    db.add_all([photo, note])
    db.commit()
    (root / "blobs" / photo.id).write_bytes(picture.getvalue())
    (root / "blobs" / note.id).write_bytes(b"hi")
    thumb = client.get(f"/api/v1/files/{photo.id}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 160
    assert client.get(f"/api/v1/files/{photo.id}/thumb").content == thumb.content  # from the cache
    assert client.get(f"/api/v1/files/{note.id}/thumb").status_code == 404
    app.dependency_overrides[require_actor] = lambda: bob
    assert client.get(f"/api/v1/files/{photo.id}/thumb").status_code == 404  # not shared with bob


def test_a_kept_film_downloads_and_streams_in_another_player(file_app, monkeypatch):
    from cryptography.fernet import Fernet

    client, db, actors, root, app = file_app
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    film = root / "media/movies/Night Film.mkv"
    film.parent.mkdir(parents=True)
    film.write_bytes(b"0123456789")
    row = Record(
        owner_id=actors[1].id,
        kind="cinema.local_media",
        visibility="house",
        data={"state": "ready", "size": 10, "_path": str(film)},
    )
    db.add(row)
    db.commit()
    got = client.get(f"/api/v1/files/library/films/{row.id}/download")
    assert got.content == b"0123456789" and got.headers["content-disposition"].startswith("attachment")
    link = client.post(f"/api/v1/files/library/films/{row.id}/player-link").json()["url"]
    assert link.endswith("/Night%20Film.mkv")
    # The player sends no sign-in: the link alone plays it, a range at a time.
    app.dependency_overrides.pop(require_actor)
    part = client.get(link, headers={"Range": "bytes=2-4"})
    assert part.status_code == 206 and part.content == b"234"
    assert client.get(link.replace("film-link/", "film-link/x")).status_code == 404
    db.get(User, actors[0].id).active = False  # its person gone: the link stops
    db.commit()
    assert client.get(link).status_code == 404


def test_a_film_picked_in_watch_opens_in_a_player_without_a_copy(file_app, monkeypatch):
    from cryptography.fernet import Fernet

    client, db, actors, root, app = file_app
    app.include_router(c.router, prefix="/api/v1")
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    film = root / "media/movies/Night Film.mkv"
    film.parent.mkdir(parents=True)
    film.write_bytes(b"0123456789")
    kept = Record(owner_id=actors[0].id, kind="cinema.local_media", visibility="house",
                  data={"state": "ready", "size": 10, "_path": str(film)})  # fmt: skip
    title = c.CinemaTitle(
        id=new_id(), canonical_id="test-" + new_id(), title="Night Film", kind="movie", data={}
    )
    db.add_all([kept, title])
    db.flush()
    source = {"id": "s1", "local_record": kept.id, "inspection": {"container": "matroska,webm"}}
    flow = c.CinemaWorkflow(id=new_id(), owner_id=actors[0].id, media_id=title.id, state="awaiting_choice",
                            version=1, idempotency_key=new_id(), data={"_sources": [source]})  # fmt: skip
    db.add(flow)
    db.commit()
    assert (
        client.post(f"/api/v1/cinema/workflows/{flow.id}/player-link", json={"source_id": "nope"}).status_code
        == 409
    )
    link = client.post(f"/api/v1/cinema/workflows/{flow.id}/player-link", json={"source_id": "s1"}).json()[
        "url"
    ]
    assert link.endswith("/Night%20Film.mkv")
    # The player sends no sign-in: the link alone streams it, a range at a time, nothing is copied.
    app.dependency_overrides.pop(require_actor)
    part = client.get(link, headers={"Range": "bytes=2-4"})
    assert part.status_code == 206 and part.content == b"234"
    assert client.get(link.replace("player/", "player/x")).status_code == 404
    db.get(User, actors[0].id).active = False  # its person gone: the link stops
    db.commit()
    assert client.get(link).status_code == 404
