"""Writing a small JSON file so that readers see the old or the new file, never half of one."""

import json
import os
import tempfile


def write_json(path, data, mode=0o600):
    """Replaces `path` atomically (same folder, then rename), readable only by `mode`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
