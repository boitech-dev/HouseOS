"""Upload locks belong under the API service's writable runtime/run boundary."""

from uuid import uuid4
import pytest
from fastapi import HTTPException
from houseos.files import upload_lock
from houseos.config import settings


def test_upload_lock_uses_writable_run_directory_and_excludes_concurrent_request(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    identity = str(uuid4())
    with upload_lock(identity):
        assert (tmp_path / "run" / "upload-locks" / identity).is_file()
        assert not (tmp_path / "upload-locks").exists()
        with pytest.raises(HTTPException) as error:
            with upload_lock(identity):
                pass
        assert error.value.status_code == 409
    with upload_lock(identity):
        pass


def test_an_upload_stuck_finalizing_is_released_after_it_expires(file_app):
    import asyncio
    from datetime import timedelta

    from houseos import files as f
    from houseos.db import utcnow

    _, db, actors, root, _ = file_app
    past = utcnow() - timedelta(hours=1)
    rows = [
        f.UploadReservation(
            owner_id=actors[0].id,
            request_key="k" + n,
            name=n + ".bin",
            scope="personal",
            size=3,
            status="finalizing",
            expires_at=past,
        )
        for n in ("moved", "stored")
    ]
    db.add_all(rows)
    db.commit()
    (root / "blobs" / rows[0].id).write_bytes(b"abc")  # moved into place, the restart came first
    db.add(
        f.FileEntry(
            id=rows[1].id,
            owner_id=actors[0].id,
            scope="personal",
            parent_id="",
            name="stored.bin",
            size=3,
            mime="application/octet-stream",
            is_folder=False,
        )
    )
    db.commit()
    asyncio.run(f.expire_uploads(db))
    assert [db.get(f.UploadReservation, r.id).status for r in rows] == ["cancelled", "stored"]
    assert not (root / "blobs" / rows[0].id).exists() and db.get(f.FileEntry, rows[1].id)
