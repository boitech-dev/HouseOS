"""Control Room's houseos.sh buttons: admin-confirmed, and signed so the helper can trust them."""

import json
import subprocess
import time

from houseos.config import settings
from test_core import admin


def test_actions_need_the_helper_and_reach_it_signed(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "storage_container", True)
    monkeypatch.setattr(settings, "encryption_key", "test-key-for-the-helper")
    c, db = client
    admin(client)
    assert c.get("/api/v1/admin/house-actions").json()["helper"] is False
    assert c.post("/api/v1/admin/house-actions/update/prepare", json={}).status_code == 409

    out = tmp_path / "run" / "helper-out"
    out.mkdir(parents=True)
    (out / "alive").write_text(str(int(time.time())))
    (out / "check.json").write_text(json.dumps({"state": "done", "results": {"behind": "2", "gpu": "off"}}))
    body = c.get("/api/v1/admin/house-actions").json()
    assert body["helper"] is True and body["about"]["behind"] == "2"
    assert c.post("/api/v1/admin/house-actions/rm-rf/prepare", json={}).status_code == 404
    bad = c.post("/api/v1/admin/house-actions/own-address/prepare", json={"address": "8.8.8.8"})
    assert bad.status_code == 422

    prepared = c.post(
        "/api/v1/admin/house-actions/own-address/prepare", json={"address": "192.168.1.250"}
    ).json()
    assert "own address" in prepared["effect"]
    assert c.post("/api/v1/admin/house-actions/confirm/" + prepared["confirmation_id"]).status_code == 200
    assert c.post("/api/v1/admin/house-actions/confirm/" + prepared["confirmation_id"]).status_code == 409
    [note] = (tmp_path / "run" / "helper-in").glob("*.json")
    signed = json.loads(note.read_text())
    request = json.loads(signed["body"])
    assert request["action"] == "own-address" and request["arg"] == "192.168.1.250"

    # The same check the helper runs (houseos.sh, cmd_helper).
    check = subprocess.run(
        [
            "bash",
            "-c",
            """key=$(printf 'houseos-helper:%s' "$KEY" | sha256sum | cut -d' ' -f1)
printf '%s' "$BODY" | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$key" -r | cut -d' ' -f1""",
        ],
        env={"KEY": "test-key-for-the-helper", "BODY": signed["body"], "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert check.stdout.strip() == signed["sig"]


def test_one_backup_at_a_time_with_the_number_to_keep(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "storage_container", True)
    monkeypatch.setattr(settings, "encryption_key", "test-key-for-the-helper")
    c, db = client
    admin(client)
    out = tmp_path / "run" / "helper-out"
    out.mkdir(parents=True)
    (out / "alive").write_text(str(int(time.time())))
    c.put("/api/v1/admin/house-settings", json={"backup_keep": 7})
    first = c.post("/api/v1/admin/house-actions/backup/prepare", json={}).json()
    second = c.post("/api/v1/admin/house-actions/backup/prepare", json={}).json()
    assert c.post("/api/v1/admin/house-actions/confirm/" + first["confirmation_id"]).status_code == 200
    # A double tap: the second is refused, in words.
    refused = c.post("/api/v1/admin/house-actions/confirm/" + second["confirmation_id"])
    assert refused.status_code == 409 and "ten minutes" in refused.json()["detail"]
    [note] = (tmp_path / "run" / "helper-in").glob("*.json")
    assert json.loads(json.loads(note.read_text())["body"])["arg"] == "7"
    status = {"created_at": "2026-01-01T00:00:00Z", "backups": [{"name": "2026-01-01_000000"}], "keep": 7}
    (tmp_path / "run" / "backup-status.json").write_text(json.dumps(status))
    assert c.get("/api/v1/admin/recovery").json()["backups"] == [{"name": "2026-01-01_000000"}]


def test_a_new_version_reaches_the_admins_inbox_once_and_updates_itself_at_night(
    client, monkeypatch, tmp_path
):
    from datetime import datetime

    from sqlalchemy import select

    from houseos import house_actions
    from houseos.household import HouseholdNotification

    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "storage_container", True)
    monkeypatch.setattr(settings, "encryption_key", "test-key-for-the-helper")
    c, db = client
    admin(client)
    out = tmp_path / "run" / "helper-out"
    out.mkdir(parents=True)
    (out / "alive").write_text(str(int(time.time())))
    (out / "check.json").write_text(
        json.dumps({"state": "done", "results": {"behind": "3", "current": "2.0.0", "latest": "2.1.0"}})
    )
    assert c.post("/api/v1/admin/house-actions/check").status_code == 200  # "look now": a signed note
    assert c.put("/api/v1/admin/house-actions/updates", json={"auto": True}).json() == {"auto": True}
    for note in (tmp_path / "run" / "helper-in").glob("*.json"):
        note.unlink()
    monkeypatch.setattr(house_actions, "utcnow", lambda: datetime(2026, 9, 26, 12, 0))  # midday UTC
    for _ in range(2):
        house_actions.update_watch(db)
        db.commit()
    notices = db.scalars(
        select(HouseholdNotification).where(HouseholdNotification.category == "update")
    ).all()
    assert [n.record_id for n in notices] == ["2.1.0"]  # once, for the new version
    assert not list((tmp_path / "run" / "helper-in").glob("*.json"))  # not in the day
    monkeypatch.setattr(house_actions, "utcnow", lambda: datetime(2026, 9, 26, 3, 30))  # UTC house
    house_actions.update_watch(db)
    db.commit()
    [note] = (tmp_path / "run" / "helper-in").glob("*.json")
    assert json.loads(json.loads(note.read_text())["body"])["action"] == "update"
    house_actions.update_watch(db)  # once per version
    db.commit()
    assert len(list((tmp_path / "run" / "helper-in").glob("*.json"))) == 1
