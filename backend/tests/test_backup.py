"""Backup helpers run only against disposable fixture files and a temporary age key."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def backups(tmp_path, monkeypatch):
    root = Path(__file__).parents[2]  # a recipient copy keeps it in docs/native/
    path = next(
        p for p in (root / "deploy/backup_uploads.py", root / "docs/native/backup_uploads.py") if p.exists()
    )
    spec = importlib.util.spec_from_file_location("houseos_backup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    monkeypatch.setattr(module, "SOURCE", source)
    monkeypatch.setattr(module, "TARGET", target)
    monkeypatch.setattr(
        module.shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100 * 1024**3, 0, 100 * 1024**3)
    )
    return module, source, target


def test_metadata_is_not_published_when_file_fsync_fails(backups, monkeypatch):
    module, _, target = backups
    path = target / "manifest.json"
    path.write_text('{"old":true}')
    monkeypatch.setattr(
        module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("fixture fsync failure"))
    )
    with pytest.raises(OSError):
        module.durable_json(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}


def test_encrypted_upload_roundtrip_incremental_and_corruption_rejection(backups, tmp_path):
    module, source, target = backups
    if not shutil.which("age") or not shutil.which("age-keygen"):
        pytest.skip("age executable is required for local encryption evidence")
    key = tmp_path / "fixture.agekey"
    subprocess.run(
        ["age-keygen", "-o", str(key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    recipient = subprocess.run(
        ["age-keygen", "-y", str(key)], check=True, capture_output=True, text=True
    ).stdout.strip()
    content = b"Synthetic upload backup fixture; no resident content."
    identity = "b7d180b0-3bb4-4143-a9a0-3584f9b2c089"
    checksum = hashlib.sha256(content).hexdigest()
    (source / identity).write_bytes(content)
    rows = [{"id": identity, "size": len(content), "checksum": checksum}]
    assert module.copy_uploads(rows, recipient, 1024)["new_encrypted_copies"] == 1
    encrypted = target / f"{identity}-{checksum}.age"
    decrypted = subprocess.run(
        ["age", "-d", "-i", str(key), str(encrypted)], check=True, capture_output=True
    ).stdout
    assert decrypted == content and content not in encrypted.read_bytes()
    assert module.copy_uploads(rows, recipient, 1024)["new_encrypted_copies"] == 0
    encrypted.write_bytes(b"corrupt ciphertext")
    with pytest.raises(ValueError, match="CORRUPT"):
        module.copy_uploads(rows, recipient, 1024)


def test_source_and_partial_symlinks_are_rejected(backups, tmp_path):
    module, source, target = backups
    identity = "b7d180b0-3bb4-4143-a9a0-3584f9b2c089"
    checksum = hashlib.sha256(b"fixture").hexdigest()
    other = tmp_path / "protected-fixture"
    other.write_bytes(b"fixture")
    (source / identity).symlink_to(other)
    rows = [{"id": identity, "size": 7, "checksum": checksum}]
    with pytest.raises(OSError):
        module.copy_uploads(rows, "invalid-but-never-used", 1024)
    (source / identity).unlink()
    (source / identity).write_bytes(b"fixture")
    (target / f"{identity}-{checksum}.part").symlink_to(other)
    with pytest.raises(FileExistsError):
        module.copy_uploads(rows, "invalid-but-never-used", 1024)
    assert other.read_bytes() == b"fixture"
