"""Fixed-path privileged upload reader; only encrypted copies leave the data root."""

import hashlib, json, os, pwd, re, shutil, stat, subprocess, sys
from pathlib import Path

SOURCE = Path("/mnt/house-storage/houseos/blobs")
TARGET = Path("/opt/houseos/state/user-file-backups")


def fsync_path(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_json(path, value):
    """Publish complete metadata only after both its content and directory are durable."""
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_path(path.parent)


def file_hash(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("INVALID_BACKUP_FILE")
        return hashlib.file_digest(stream, "sha256").hexdigest()


def copy_uploads(rows, recipient, limit):
    TARGET.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.getuid() == 0:
        owner = pwd.getpwnam("YOUR_DESKTOP_USER")
        os.chown(TARGET, owner.pw_uid, owner.pw_gid)
    total = sum(row["size"] for row in rows)
    if total > limit:
        raise ValueError("UPLOAD_BACKUP_SCOPE_EXCEEDS_BUDGET")
    todo = []
    for row in rows:
        if (
            not re.fullmatch(r"[0-9a-f-]{36}", row["id"])
            or not re.fullmatch(r"[0-9a-f]{64}", row["checksum"])
            or type(row["size"]) is not int
            or row["size"] < 0
        ):
            raise ValueError("INVALID_BACKUP_ENTRY")
        target = TARGET / (row["id"] + "-" + row["checksum"] + ".age")
        record = target.with_suffix(".json")
        if target.exists():
            saved = json.loads(record.read_text())
            if saved.get("sha256") != file_hash(target):
                raise ValueError("EXISTING_UPLOAD_BACKUP_CORRUPT")
        else:
            todo.append((row, target, record))
    if shutil.disk_usage(TARGET).free < sum(row["size"] for row, _, _ in todo) + 20 * 1024**3:
        raise ValueError("UPLOAD_BACKUP_DISK_RESERVE")
    for row, target, record in todo:
        directory_fd = os.open(SOURCE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(row["id"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
        partial = target.with_suffix(".part")
        proc = None
        output_fd = None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != row["size"]:
                raise ValueError("UPLOAD_BACKUP_SOURCE_CHANGED")
            output_fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            proc = subprocess.Popen(
                ["age", "-r", recipient], stdin=subprocess.PIPE, stdout=output_fd, stderr=subprocess.DEVNULL
            )
            checksum = hashlib.sha256()
            with os.fdopen(fd, "rb", closefd=False) as source:
                while chunk := source.read(1024 * 1024):
                    checksum.update(chunk)
                    proc.stdin.write(chunk)
            proc.stdin.close()
            if proc.wait(timeout=30) != 0 or checksum.hexdigest() != row["checksum"]:
                raise ValueError("UPLOAD_BACKUP_CHECKSUM_FAILED")
            os.fsync(output_fd)
            os.close(output_fd)
            output_fd = None
            os.replace(partial, target)
            durable_json(record, {"id": row["id"], "size": row["size"], "sha256": file_hash(target)})
            for path in (target, record):
                path.chmod(0o600)
                if os.getuid() == 0:
                    os.chown(path, owner.pw_uid, owner.pw_gid)
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            if output_fd is not None:
                os.close(output_fd)
            os.close(fd)
    directory = os.open(TARGET, os.O_RDONLY | os.O_DIRECTORY)
    os.fsync(directory)
    os.close(directory)
    return {"status": "completed", "files": len(rows), "bytes": total, "new_encrypted_copies": len(todo)}


if __name__ == "__main__":
    try:
        mount = subprocess.run(
            ["findmnt", "-n", "-o", "UUID", "-T", "/mnt/house-storage"], capture_output=True, text=True, timeout=3
        )
        if mount.stdout.strip() != "SET_YOUR_STORAGE_UUID":
            raise ValueError("STORAGE_UNAVAILABLE")
        payload = json.load(sys.stdin)
        print(json.dumps(copy_uploads(payload["rows"], payload["recipient"], payload["max_bytes"])))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": "UPLOAD_BACKUP_FAILED",
                    "message": "Review scope, disk reserve and protected backup source; no plaintext copy written",
                }
            )
        )
        raise SystemExit(1)
