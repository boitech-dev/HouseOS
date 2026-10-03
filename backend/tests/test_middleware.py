"""Production middleware must retain stricter endpoint content boundaries."""

import os
from contextlib import contextmanager

from houseos import files, household
from houseos.auth import Actor, RESIDENT
from houseos.db import new_id
from test_core import admin


def test_file_csp_survives_real_application_middleware(client, tmp_path, monkeypatch):
    c, db = client
    user = admin(client)
    content = b"%PDF-1.4\n%%EOF"
    row = files.FileEntry(
        id=new_id(),
        owner_id=user["id"],
        scope="personal",
        name="fixture.pdf",
        size=len(content),
        mime="application/pdf",
    )
    db.add(row)
    db.commit()
    (tmp_path / row.id).write_bytes(content)

    @contextmanager
    def directory(name):
        fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield fd
        finally:
            os.close(fd)

    monkeypatch.setattr(files, "subdir_fd", directory)
    preview = c.get("/api/v1/files/" + row.id + "/preview")
    assert preview.status_code == 200
    assert preview.headers["Content-Security-Policy"] == "sandbox; default-src 'none'"
    ordinary = c.get("/api/v1/auth/me")
    assert "default-src 'self'" in ordinary.headers["Content-Security-Policy"]


def test_snooze_preserves_task_timezone_time_and_version(client):
    c, db = client
    user = admin(client)
    actor = Actor(user["id"], "Test Admin", "admin", RESIDENT)
    record = household.create_record(
        db,
        actor,
        "tasks",
        household.CreateRecord(
            data={
                "title": "Laundry",
                "due_date": "2026-10-24",
                "due_time": "10:00",
                "timezone": "Europe/Paris",
            },
            idempotency_key=new_id(),
        ),
    )
    result = c.post(
        "/api/v1/household/tasks/" + record["id"] + "/action",
        json={"version": record["version"], "action": "snooze", "due_date": "2026-10-25"},
    )
    assert result.status_code == 200
    assert result.json()["data"]["timezone"] == "Europe/Paris"
    assert result.json()["data"]["due_time"] == "10:00"
    assert result.json()["data"]["due_date"] == "2026-10-25"
    assert (
        c.post(
            "/api/v1/household/tasks/" + record["id"] + "/action",
            json={"version": record["version"], "action": "snooze", "due_date": "2026-10-26"},
        ).status_code
        == 409
    )
