"""Expiring recipient grants apply to list/read/attachments and exact confirmations."""

import hashlib
import pytest
from fastapi import HTTPException
from datetime import timedelta, timezone

from sqlalchemy import select

from houseos import files as f
from houseos.auth import require_actor
from houseos.db import new_id, utcnow


def test_expiring_grant_scopes_link_preview_attachment_and_renewal(file_app):
    client, db, (alice, bob, _), root, app = file_app
    content = b"%PDF-1.4\n% preview fixture\n%%EOF"
    row = f.FileEntry(
        id=new_id(),
        owner_id=alice.id,
        scope="personal",
        name="private.pdf",
        mime="application/pdf",
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
    )
    db.add(row)
    db.commit()
    (root / "blobs" / row.id).write_bytes(content)
    expiry = (utcnow() + timedelta(hours=2)).replace(tzinfo=timezone.utc).isoformat()
    prepared = client.post(
        f"/api/v1/files/{row.id}/actions/prepare",
        json={"version": 1, "action": "share", "recipient_id": bob.id, "grant_expires_at": expiry},
    ).json()
    assert prepared["preview"]["grant_expires_at"] == expiry
    assert client.post("/api/v1/files/confirmations/" + prepared["confirmation_id"]).status_code == 200
    app.dependency_overrides[require_actor] = lambda: bob
    assert client.get(f"/api/v1/files/{row.id}/info").status_code == 200
    preview = client.get(f"/api/v1/files/{row.id}/preview")
    assert preview.status_code == 200 and preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-security-policy"] == "sandbox; default-src 'none'"
    assert preview.headers["content-disposition"].startswith("inline")
    grant = db.scalar(select(f.FileGrant).where(f.FileGrant.file_id == row.id))
    grant.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get(f"/api/v1/files/{row.id}/preview").status_code == 404
    assert client.get(f"/api/v1/files/{row.id}/info").status_code == 404
    assert client.get("/api/v1/files?scope=shared").json()["items"] == []
    with pytest.raises(HTTPException):
        f.assert_attachment_access(db, alice, [row.id], [bob.id])
    app.dependency_overrides[require_actor] = lambda: alice
    assert client.get(f"/api/v1/files/{row.id}/grants").json()["items"][0]["expired"] is True
    renewed = client.post(
        f"/api/v1/files/{row.id}/actions/prepare",
        json={"version": 2, "action": "share", "recipient_id": bob.id, "grant_expires_at": expiry},
    ).json()
    assert client.post("/api/v1/files/confirmations/" + renewed["confirmation_id"]).status_code == 200
    app.dependency_overrides[require_actor] = lambda: bob
    assert client.get(f"/api/v1/files/{row.id}/download").status_code == 200


def test_expiry_during_confirmation_is_rejected(file_app):
    client, db, (alice, bob, _), root, app = file_app
    row = f.FileEntry(id=new_id(), owner_id=alice.id, scope="personal", name="a.txt", size=0)
    db.add(row)
    db.commit()
    prepared = client.post(
        f"/api/v1/files/{row.id}/actions/prepare",
        json={
            "version": 1,
            "action": "share",
            "recipient_id": bob.id,
            "grant_expires_at": (utcnow() + timedelta(minutes=1)).replace(tzinfo=timezone.utc).isoformat(),
        },
    ).json()
    confirmation = db.get(f.FileConfirmation, prepared["confirmation_id"])
    confirmation.data = {
        **confirmation.data,
        "grant_expires_at": (utcnow() - timedelta(seconds=1)).replace(tzinfo=timezone.utc).isoformat(),
    }
    db.commit()
    assert client.post("/api/v1/files/confirmations/" + prepared["confirmation_id"]).status_code == 409
    assert db.scalar(select(f.FileGrant).where(f.FileGrant.file_id == row.id)) is None
