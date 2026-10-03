"""Publish only non-sensitive backup metadata to the app service."""

import json
from backup_uploads import durable_json
from pathlib import Path

runtime = Path("/opt/houseos/state")
source = json.loads((runtime / "backup-status.json").read_text())
keys = [
    "created_at",
    "restore_verified",
    "key_recovery_verified",
    "user_file_backup",
    "disaster_recovery",
    "retention",
    "keep",
    "backups",
]
target = runtime / "run/backup-status.json"
durable_json(target, {k: source.get(k) for k in keys})
target.chmod(0o644)
