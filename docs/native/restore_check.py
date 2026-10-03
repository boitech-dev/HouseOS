"""Restore only a newly provisioned empty houseos_restore schema; preserve all other DBs."""

import hashlib
import json
import os
import sys
import subprocess
import tarfile
import tempfile
from pathlib import Path
import pymysql  # noqa: F401 (fail early when the driver is missing)

runtime = Path("/opt/houseos/state")
state = json.loads((runtime / "backup-status.json").read_text())
archive = Path(state["database_backup"])
if hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() != state["sha256"]:
    raise SystemExit("Backup checksum mismatch")
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix="houseos-restore-", dir=runtime / "cache") as tmp:
    tmp = Path(tmp)
    tarpath = tmp / "state.tar"
    result = subprocess.run(
        [
            "age",
            "-d",
            "-i",
            "/etc/houseos/houseos-backup.agekey",
            "-o",
            str(tarpath),
            str(archive),
        ],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit("Backup decryption failed")
    with tarfile.open(tarpath) as tar:
        for name in ["database.sql", "secrets/houseos.env"]:
            tar.extract(name, tmp, filter="data")
    check = subprocess.run(
        [
            "docker",
            "exec",
            "mariadb",
            "sh",
            "-c",
            'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\'houseos_restore\'"',
        ],
        capture_output=True,
        text=True,
    )
    if check.returncode or check.stdout.strip() != "0":
        raise SystemExit("Restore-check schema must be empty; no overwrite performed")
    with (tmp / "database.sql").open("rb") as stream:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "mariadb",
                "sh",
                "-c",
                'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" houseos_restore',
            ],
            stdin=stream,
            capture_output=True,
        )
    if result.returncode:
        raise SystemExit("Isolated restore failed; details suppressed")
    restored = dict(
        line.split("=", 1) for line in (tmp / "secrets/houseos.env").read_text().splitlines() if "=" in line
    )
    from cryptography.fernet import Fernet

    cipher = Fernet(restored["HOUSEOS_ENCRYPTION_KEY"].encode())
    url = os.environ.get("DATABASE_URL", "").replace("mysql://", "mysql+pymysql://", 1)
    if not url.endswith("/houseos_restore"):
        raise SystemExit("Use the protected isolated restore connection")
    from sqlalchemy import create_engine, text

    engine = create_engine(url, hide_parameters=True)
    with engine.connect() as connection:
        values = (
            connection.execute(text("SELECT encrypted_secret FROM integrations WHERE encrypted_secret <> ''"))
            .scalars()
            .all()
        )
        for value in values:
            cipher.decrypt(value.encode())
    state["restore_verified"] = True
    state["restore_schema"] = "houseos_restore"
    state["key_recovery_verified"] = True
    (runtime / "backup-status.json").write_text(json.dumps(state, indent=2) + "\n")
    subprocess.run([sys.executable, "/opt/houseos/source/deploy/publish_backup_status.py"], check=True)
    print("Isolated HouseOS restore and recovered integration-encryption key verified")
