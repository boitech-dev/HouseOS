"""Small shared helpers: where things go, and JSON written atomically (a parallel build never
reads half a file)."""
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
THEME = ROOT / "themes" / "pocket-hatchling"
ART = THEME / "art"
HERE = Path(__file__).resolve().parent


def write_json(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
