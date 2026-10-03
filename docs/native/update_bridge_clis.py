#!/usr/bin/python3
"""Keep the AI helpers' sign-in clients current: new models need recent versions. Runs daily
(houseos-bridge-update.timer) and when an admin asks (houseos-bridge-update.path).

Claude Code updates itself in the desktop user's install; the helper runs a root-owned copy of the
newest version, swapped in whole. Codex updates through npm. The Claude helper starts the client
for each request, so it needs no restart; the Codex helper keeps one running and restarts."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

VERSIONS = Path("/home/YOUR_USER/.local/share/claude/versions")
BINARY = Path("/usr/local/lib/houseos/claude")
REQUESTS = Path("/opt/houseos/state/run")


def newest(folder: Path = VERSIONS) -> Path:
    found = [p for p in folder.iterdir() if re.fullmatch(r"\d+\.\d+\.\d+", p.name)]
    return max(found, key=lambda p: tuple(map(int, p.name.split("."))))


def install(source: Path, target: Path = BINARY) -> bool:
    """Copy `source` over `target` atomically (root-owned, 0755); False when already the same."""
    if target.is_file() and target.read_bytes() == source.read_bytes():
        return False
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as copy, source.open("rb") as data:
        shutil.copyfileobj(data, copy)
    os.chown(copy.name, 0, 0)
    os.chmod(copy.name, 0o755)
    os.replace(copy.name, target)
    return True


def codex_version() -> str:
    return subprocess.run(["codex", "--version"], capture_output=True, text=True).stdout.strip()


def main():
    for engine in ("claude", "codex"):
        (REQUESTS / f"bridge-update-{engine}").unlink(missing_ok=True)
    subprocess.run(
        ["runuser", "-u", "YOUR_DESKTOP_USER", "--", "env", "HOME=/home/YOUR_USER", "/home/YOUR_USER/.local/bin/claude", "update"],
        timeout=600,
        check=False,
    )
    if install(newest()):
        print("Claude helper now runs", newest().name)
    before = codex_version()
    subprocess.run(["npm", "install", "-g", "--no-fund", "--no-audit", "@openai/codex@latest"], timeout=600, check=False)
    if codex_version() != before:
        print("Codex helper now runs", codex_version())
        subprocess.run(["systemctl", "try-restart", "houseos-codex.service"], check=False)


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Run as root (houseos-bridge-update.service).")
    main()
