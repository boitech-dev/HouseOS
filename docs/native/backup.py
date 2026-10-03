"""Encrypted app-only backup; run as the desktop user, never through an AI tool."""

import json
import os
import subprocess
import tarfile
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from backup_uploads import durable_json, fsync_path, file_hash

project = Path("/opt/houseos/source")
secrets = Path("/etc/houseos")
runtime = Path("/opt/houseos/state")
key = secrets / "houseos-backup.agekey"
if not key.exists():
    raise SystemExit("Protected backup identity is missing")
mount = subprocess.run(
    ["findmnt", "-n", "-o", "UUID", "-T", "/mnt/house-storage"], capture_output=True, text=True, timeout=5
)
if mount.stdout.strip() != "SET_YOUR_STORAGE_UUID":
    raise SystemExit("Expected backup drive absent")
recipient = subprocess.run(
    ["age-keygen", "-y", str(key)], capture_output=True, text=True, check=True
).stdout.strip()
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
destination = Path("/mnt/house-storage/backups")
destination.mkdir(mode=0o700, parents=True, exist_ok=True)
os.umask(0o077)
sys.path.insert(0, str(runtime / "current/backend"))
for line in (secrets / "houseos.env").read_text().splitlines():
    if "=" in line:
        name, value = line.split("=", 1)
        os.environ[name] = value
from houseos.db import SessionLocal
from houseos.models import Integration, Event
from houseos.files import FileEntry
from sqlalchemy import select, func

with SessionLocal() as db:
    files_before = db.scalar(select(func.coalesce(func.max(Event.id), 0)).where(Event.topic.like("files.%")))
with tempfile.TemporaryDirectory(prefix="houseos-backup-", dir=runtime / "cache") as temp:
    temp = Path(temp)
    with (temp / "database.sql").open("wb") as output:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "mariadb",
                "sh",
                "-c",
                'exec mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers houseos',
            ],
            stdout=output,
            stderr=subprocess.PIPE,
        )
    if result.returncode:
        raise SystemExit("HouseOS dump failed; details suppressed")
    # Immutable upload blobs are copied separately; root helper accepts UUIDs only.
    upload_status = {
        "status": "disabled",
        "message": "Upload-content backup is not enabled; database backup excludes file bytes",
    }
    with SessionLocal() as db:
        policy = db.get(Integration, "backup_policy")
        if policy and policy.config.get("uploads_enabled"):
            rows = [
                {"id": r.id, "size": r.size, "checksum": r.checksum}
                for r in db.scalars(
                    select(FileEntry).where(
                        FileEntry.is_folder.is_(False),
                        FileEntry.storage_removed_at.is_(None),
                        FileEntry.scope.in_(policy.config.get("scopes", ["personal", "house"])),
                    )
                )
            ]
            payload = {
                "recipient": recipient,
                "rows": rows,
                "max_bytes": policy.config.get("max_bytes", 5 * 1024**3),
            }
            run = subprocess.run(
                ["sudo", str(runtime / "venvs/app/bin/python"), str(project / "deploy/backup_uploads.py")],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
            )
            try:
                upload_status = json.loads(run.stdout)
            except ValueError:
                upload_status = {"status": "failed", "code": "UPLOAD_BACKUP_FAILED"}
            db.rollback()
            files_after = db.scalar(
                select(func.coalesce(func.max(Event.id), 0)).where(Event.topic.like("files.%"))
            )
            if files_after != files_before:
                upload_status = {
                    "status": "unverified",
                    "code": "FILES_CHANGED_DURING_BACKUP",
                    "message": "Encrypted copies retained; repeat during an idle file window before relying on full file recovery",
                }
            (temp / "upload-backup.json").write_text(
                json.dumps({"policy": policy.config, "entries": rows, "result": upload_status})
            )
    archive = temp / "state.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(temp / "database.sql", arcname="database.sql")
        if (temp / "upload-backup.json").exists():
            tar.add(temp / "upload-backup.json", arcname="upload-backup.json")
        for name in ["houseos.env", "houseos-jellyfin.env"]:
            if (secrets / name).exists():
                tar.add(secrets / name, arcname="secrets/" + name)
        tar.add(project / "deploy", arcname="deploy")
        tar.add(project / "backend/uv.lock", arcname="uv.lock")
    target = destination / ("houseos-state-" + stamp + ".tar.age")
    target_partial = target.with_suffix(".part")
    result = subprocess.run(
        ["age", "-r", recipient, "-o", str(target_partial), str(archive)], capture_output=True
    )
    if result.returncode:
        raise SystemExit("Backup encryption failed")
    fsync_path(target_partial)
    os.replace(target_partial, target)
    fsync_path(destination)
    source_dir = runtime / "source-backups"
    source_dir.mkdir(mode=0o700, exist_ok=True)
    source = source_dir / ("houseos-source-" + stamp + ".tar.age")
    tarproc = subprocess.Popen(
        [
            "tar",
            "-C",
            str(project),
            "--exclude=node_modules",
            "--exclude=__pycache__",
            "--exclude=.pytest_cache",
            "--exclude=evidence/private",
            "--exclude=.ruff_cache",
            "--exclude=frontend/dist",
            "--exclude=.git",
            "-cf",
            "-",
            ".",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    source_partial = source.with_suffix(".part")
    encrypted = subprocess.run(
        ["age", "-r", recipient, "-o", str(source_partial)], stdin=tarproc.stdout, capture_output=True
    )
    tarproc.stdout.close()
    _, errors = tarproc.communicate()
    if tarproc.returncode or encrypted.returncode:
        raise SystemExit("Source backup failed")
    fsync_path(source_partial)
    os.replace(source_partial, source)
    fsync_path(source_dir)
    # Older backups go only when an admin chose "keep the last N" (Control Room → Recovery).
    with SessionLocal() as db:
        from houseos.house_settings import get_house_settings

        keep = get_house_settings(db)["backup_keep"]
    kept = sorted(destination.glob("houseos-state-*.tar.age"))
    if keep:
        for old in kept[:-keep]:
            when = old.name.removeprefix("houseos-state-").removesuffix(".tar.age")
            for path in (old, destination / f"manifest-{when}.json", source_dir / f"houseos-source-{when}.tar.age"):
                path.unlink(missing_ok=True)
        kept = kept[-keep:]
    manifest = {
        "created_at": stamp,
        "database_backup": str(target),
        "sha256": file_hash(target),
        "source_backup": str(source),
        "source_sha256": file_hash(source),
        "restore_verified": False,
        "user_file_backup": upload_status,
        "disaster_recovery": "same machine; no off-machine copy",
        "retention": f"Keeps the last {keep}" if keep else "Keeps every backup",
        "keep": keep,
        "backups": [{"name": path.name, "bytes": path.stat().st_size} for path in kept[-20:]],
    }
    durable_json(destination / ("manifest-" + stamp + ".json"), manifest)
    durable_json(runtime / "backup-status.json", manifest)
    subprocess.run([sys.executable, str(project / "deploy/publish_backup_status.py")], check=True)
    print(json.dumps(manifest, indent=2))
