"""Without Docker: put the checkout's code and built screens into a new release folder, then point
<state>/current at it (<state>/previous keeps the one before). Restart the app services afterwards.

    HOUSEOS_RUNTIME_ROOT=/opt/houseos/state python3 docs/native/release.py

Run from the checkout after `npm run build` in frontend/. The release's deploy/ is this folder."""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

here = Path(__file__).resolve().parent
checkout = next(p for p in here.parents if (p / "backend/houseos").is_dir())
screens = checkout / "frontend/dist"
assert (screens / "index.html").is_file(), "Build the screens first: cd frontend && npm run build"
runtime = Path(os.environ.get("HOUSEOS_RUNTIME_ROOT", "/opt/houseos/state"))
release = runtime / "releases" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
release.mkdir(parents=True)
caches = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache", ".venv")
shutil.copytree(checkout / "backend", release / "backend", ignore=caches)
shutil.copytree(screens, release / "frontend")
shutil.copytree(here, release / "deploy", ignore=caches)
# The theme kit on the server checks installed themes against Base and the slot list.
shutil.copytree(checkout / "themes", release / "themes", ignore=shutil.ignore_patterns("shots"))
for name, target in (("previous", (runtime / "current").resolve()), ("current", release)):
    if name == "previous" and not (runtime / "current").is_symlink():
        continue
    temp = runtime / (name + ".new")
    temp.unlink(missing_ok=True)
    temp.symlink_to(target)
    os.replace(temp, runtime / name)
print("Release assembled:", release)
