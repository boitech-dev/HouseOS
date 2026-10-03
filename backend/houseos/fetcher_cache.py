"""Private short-lived extraction tickets; URLs never leave the fetch identity."""

import hashlib
import json
import os
import shutil
import threading
import time
from uuid import UUID

from .atomic import write_json

# Fixed stripes bound memory even when many distinct songs are requested.
LOCKS = [threading.RLock() for _ in range(64)]
TTL = 300


def key(url):
    return hashlib.sha256(url.encode()).hexdigest()


def source_lock(url):
    return LOCKS[int(key(url)[:8], 16) % len(LOCKS)]


def resolve(root, url, base, run, refresh=False):
    with source_lock(url):
        folder = root / ".resolutions"
        folder.mkdir(mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        path = folder / (key(url) + ".json")
        now = time.time()
        if not refresh:
            try:
                if now - path.stat().st_mtime < TTL:
                    return path, json.loads(path.read_bytes())
            except (OSError, ValueError):
                pass
        info = json.loads(
            run(base + ["-f", "bestaudio/best", "--skip-download", "--dump-single-json", "--", url], 45)
        )
        write_json(path, info)
        # Other in-flight users hold a parsed object; missing tickets re-resolve safely.
        files = []
        for entry in folder.glob("*.json"):
            try:
                files.append((entry.stat().st_mtime, entry))
            except FileNotFoundError:
                continue
        for index, (modified, entry) in enumerate(sorted(files, reverse=True)):
            if entry != path and (index >= 128 or now - modified >= TTL):
                entry.unlink(missing_ok=True)
        return path, info


def prune(root, pins, maximum=10 * 1024**3, reserve=400 * 1024**2):
    """Evict oldest completed audio inode groups, never current/next or partials."""
    protected = {str(UUID(value)) + ".media" for value in pins}
    groups = {}
    for path in root.glob("*.media"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            info = path.stat()
            groups.setdefault((info.st_dev, info.st_ino), []).append((path, info))
        except FileNotFoundError:
            continue
    total = sum(entries[0][1].st_size for entries in groups.values())
    maximum = min(maximum, max(0, total + shutil.disk_usage(root).free - 2 * 1024**3))
    removed = []
    for entries in sorted(groups.values(), key=lambda values: max(v[1].st_mtime for v in values)):
        if total + reserve <= maximum:
            break
        if any(path.name in protected for path, _ in entries):
            continue
        # External hardlinks may represent explicitly retained media: do not touch.
        if entries[0][1].st_nlink > len(entries):
            continue
        for path, _ in entries:
            path.unlink(missing_ok=True)
            removed.append(path.stem)
        total -= entries[0][1].st_size
    return {"status": "completed", "bytes": total, "removed_item_ids": removed}
