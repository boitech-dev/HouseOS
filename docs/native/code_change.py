#!/usr/bin/env python3
"""Apply, undo or keep a code change an admin approved in Control Room → Changes (native installs).

houseos-code.path starts houseos-code.service, as the source checkout's owner, when the app leaves
a signed note in <runtime>/run/helper-in (the same notes the Docker helper reads; there, houseos.sh
`code` does this). Results go to run/helper-out/<request>.json and .log for the Changes page.

Apply: refused unless the draft still has the digest of the diff the admin approved, touches only
what code_rules allows, and the checkout is clean, at the draft's base, with each file as the diff
showed it. Backup: the tag houseos-backup/<id>, naming the running release. Then the files, one
commit "Nox: <summary>", the checks (ruff, the SQLite suite against the same suite before the
change, the frontend build) in a jail: read-only but for the build's output, no network; a failure
puts the checkout back and deploys nothing. Then release.py, a restart through the control broker
(music resumes where it was; the sound path keeps playing), and a health check: unhealthy goes back
to the backup by itself. Keep deletes the backup; Undo returns to it."""

import hashlib
import hmac
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

# The running release's rules, this one file only: importing the houseos package would run its
# __init__ (app code) here, outside the jail, as the checkout's owner.
_spec = importlib.util.spec_from_file_location(
    "code_rules", Path(__file__).resolve().parents[1] / "backend/houseos/code_rules.py"
)
rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rules)
allowed, digest = rules.allowed, rules.digest

RUNTIME = Path(os.environ.get("HOUSEOS_RUNTIME_ROOT", "/var/lib/houseos"))
SOURCE = Path(os.environ.get("HOUSEOS_SOURCE_ROOT") or ".").resolve()
PYTHON = str(RUNTIME / "venvs/app/bin/python")
BROKER = "/run/houseos-control/control.sock"
HEALTH = "http://127.0.0.1:8990/api/v1/health"
# App services only; audio, fetch and media (the sound and TV path) keep playing and take new code
# at their own next restart. The worker restarts last, right after the resume-music note.
SERVICES = ("api", "maintenance", "cinema-worker", "cinema-observer", "voice", "codex", "worker")
ID = re.compile(r"[0-9a-f]{12}")
IDENTITY = ("-c", "user.name=Nox", "-c", "user.email=nox@example.invalid", "-c", "core.hooksPath=/dev/null")
# Checks and builds never see the app's keys or database (the tests would use it).
CLEAN = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
}
# house_actions.house_busy's films: the app refuses while one plays; checked again before a restart.
FILM = (
    "select count(*) from cinema_workflows where state in "
    "('playing_observed', 'paused', 'command_sent', 'preparing')"
)
LOG = []


class Failed(Exception):
    pass


def sandbox():
    """The checks run the drafted code (bubblewrap). They see only the system, the checkout, the
    app's Python (its venv and the interpreter it names) and node_modules, all read-only: no
    /mnt/house-storage (media, backups), no home, no HouseOS state, no /run (Docker, D-Bus, the control
    broker, HouseOS's own sockets), no network, no other processes. Writable: the screens' build
    output, and a throwaway layer over node_modules and the TypeScript cache. The app's own sandbox
    tests can't nest in it: they fail before and after alike, like the MariaDB-only ones."""
    venv = Path(PYTHON).parents[1]
    home = re.search(r"^home\s*=\s*(.+)$", (venv / "pyvenv.cfg").read_text(), re.M).group(1)
    args = ["bwrap", "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc"]
    for system in ("/bin", "/sbin", "/lib", "/lib64", "/lib32"):
        args += ["--ro-bind-try", system, system]
    args += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
    for readable in (SOURCE, venv, Path(home.strip()).parent):
        args += ["--ro-bind", readable, readable]
    args += ["--overlay-src", RUNTIME / "frontend", "--tmp-overlay", RUNTIME / "frontend"]
    args += ["--bind", RUNTIME / "build/frontend", RUNTIME / "build/frontend"]
    return [*args, "--unshare-all", "--die-with-parent", "--"]


def run(*command, cwd=None, check=True, jail=False, env=None):
    proc = subprocess.run(
        [*sandbox(), *command] if jail else command,
        cwd=cwd or SOURCE,
        env={**CLEAN, **(env or {})},
        capture_output=True,
        text=True,
        timeout=1800,
    )
    LOG.append(f"$ {' '.join(command)}\n{proc.stdout[-3000:]}{proc.stderr[-3000:]}")
    if check and proc.returncode:
        step = next((word for word in command[1:] if not word.startswith("-") and "=" not in word), "")
        raise Failed(f"{Path(command[0]).name} {step} failed")
    return proc.stdout.strip()


def git(*args):
    return run("git", *args)


def notes():
    """Signed code requests from the app, oldest first, each read once. A valid note for another
    reader stays; unsigned and stale ones go."""
    key = hashlib.sha256(b"houseos-helper:" + os.environ["HOUSEOS_ENCRYPTION_KEY"].encode()).digest()
    found = []
    inbox = RUNTIME / "run/helper-in"
    for path in sorted(inbox.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            note = json.loads(path.read_text())
            body = note["body"]
            signed = hmac.compare_digest(
                hmac.new(key, body.encode(), hashlib.sha256).hexdigest(), note["sig"]
            )
            request = json.loads(body)
            fresh = abs(time.time() - request["ts"]) < 300
        except (OSError, ValueError, KeyError, TypeError):
            signed = fresh = False
        code = signed and fresh and request.get("action") in {"code-apply", "code-undo", "code-keep"}
        if signed and fresh and not code:
            continue
        path.unlink(missing_ok=True)
        if (
            code
            and re.fullmatch(r"[0-9a-f]{12}(:[0-9a-f]{64})?", str(request.get("arg")))
            and re.fullmatch(r"[0-9a-f-]{36}", str(request.get("id")))
        ):
            found.append(request)
    return found


def report(request, state, message="", **results):
    out = RUNTIME / "run/helper-out"  # made by the app, which reads these as "other"
    log = out / (request["id"] + ".log")
    log.write_text("\n".join(LOG)[-8000:])
    os.chmod(log, 0o664)
    data = {"id": request["id"], "action": request["action"], "state": state, "message": message}
    with tempfile.NamedTemporaryFile("w", dir=out, delete=False, suffix=".tmp") as temp:
        json.dump({**data, "results": results}, temp)
    os.chmod(temp.name, 0o664)
    os.replace(temp.name, out / (request["id"] + ".json"))


def inside(path):
    """A drafted file's place in the checkout (the app checked it; the checkout's owner checks again)."""
    full = SOURCE / path
    if not allowed(path) or full.resolve() != full:  # no link to another file either
        raise Failed(f"Refused a file Nox may not change: {path}")
    return full


def release_dir(name):
    if not re.fullmatch(r"\d{8}T\d{6}Z", name or "") or not (RUNTIME / "releases" / name).is_dir():
        raise Failed("The backup's release is missing: undo by hand (docs/CHANGING-HOUSEOS.md).")
    return RUNTIME / "releases" / name


def backup_release(tag):
    return re.search(r"release=(\S*)", git("tag", "-l", "--format=%(contents)", tag)).group(1)


def failures():
    """Test ids that fail on the SQLite suite (MariaDB-only tests fail there by design)."""
    out = run(
        PYTHON,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-rfE",
        cwd=SOURCE / "backend",
        check=False,
        jail=True,
    )
    return {line.split(" ")[1] for line in out.splitlines() if line.startswith(("FAILED ", "ERROR "))}


def checks(before):
    run(
        PYTHON,
        "-m",
        "ruff",
        "check",
        "--config",
        "backend/pyproject.toml",
        "backend/houseos",
        "backend/tests",
        "deploy",
        "--no-cache",
        jail=True,
    )
    new = failures() - before
    if new:
        raise Failed("New test failures: " + ", ".join(sorted(new)[:5]))
    run("npm", "run", "build", cwd=SOURCE / "frontend", jail=True)


def deploy():
    run("python3", "deploy/release.py")


def film_on():
    """A film on a screen now, or no answer (then wait too). The app's own Python, isolated from the
    checkout; the database address stays out of the command, so out of the log."""
    url = os.environ.get("HOUSEOS_DATABASE_URL", "").replace("mysql://", "mysql+pymysql://", 1)
    ask = "import os, sqlalchemy as s; print(s.create_engine(os.environ['URL']).connect().execute(s.text(os.environ['SQL'])).scalar())"
    try:
        return run(PYTHON, "-I", "-c", ask, cwd=RUNTIME, env={"URL": url, "SQL": FILM}) != "0"
    except (Failed, OSError, subprocess.TimeoutExpired):
        return True


def broker(action, service):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(15)
        sock.connect(BROKER)
        sock.sendall(json.dumps({"action": action, "service": service}).encode() + b"\n")
        return json.loads(sock.makefile().readline() or "{}")


def running():
    return {name for name in SERVICES if broker("status", name).get("active") == "active"}


def restart(services):
    for name in SERVICES:
        if name in services:
            if name == "worker":  # the song playing pauses and resumes at the same second
                (RUNTIME / "run/resume-music").touch()
            broker("restart", name)


def healthy(services, wait=180):
    """The API answers and every restarted service stays up, twice in a row ten seconds apart."""
    good, end = 0, time.time() + wait
    while time.time() < end and good < 2:
        time.sleep(10)
        try:
            with urllib.request.urlopen(HEALTH, timeout=5) as answer:
                ok = json.load(answer).get("status") == "ok"
        except (OSError, ValueError):
            ok = False
        good = good + 1 if ok and running() >= services else 0
    return good >= 2


def switch(release):
    temp = RUNTIME / "current.new"
    temp.unlink(missing_ok=True)
    temp.symlink_to(release)
    os.replace(temp, RUNTIME / "current")


def put_back(tag, files, new):
    """The checkout as the backup had it: only this change's files (others' edits stay)."""
    git("reset", "-q", "--keep", tag)
    for path, full in files.items():
        if path in new:
            git("rm", "-q", "--cached", "--ignore-unmatch", "--", path)
            full.unlink(missing_ok=True)
        else:
            git("checkout", tag, "--", path)
    git("tag", "-d", tag)


def apply(identity, reviewed):
    try:
        change = json.loads((RUNTIME / "run/code" / (identity + ".json")).read_text())
    except (OSError, ValueError):
        raise Failed("This change is gone: ask Nox to draft it again.")
    if digest(change) != reviewed:
        raise Failed(
            "This change was edited after it was reviewed: look at it again in Control Room → Changes."
        )
    if git("status", "--porcelain", "--untracked-files=no"):
        raise Failed("The source folder has edits nobody committed yet: commit them, then apply again.")
    if git("rev-parse", "HEAD") != change["base"]:
        raise Failed("HouseOS changed since this was drafted: ask Nox to draft it again")
    files = {path: inside(path) for path in change["files"]}
    if any(
        (full.read_bytes() if full.is_file() else b"") != change["before"].get(path, "").encode()
        for path, full in files.items()
    ):
        raise Failed("A file is not as the reviewed diff showed it: ask Nox to draft it again.")
    new = set(files) - set(git("ls-files", "--", *files).splitlines())
    if any(files[path].exists() for path in new):
        raise Failed("A new file would replace one that isn't part of HouseOS: ask Nox to draft it again.")
    before = failures()
    tag, release = "houseos-backup/" + identity, (RUNTIME / "current").resolve().name
    run("git", *IDENTITY, "tag", "-a", tag, "-m", "release=" + release)
    try:
        for path, text in change["files"].items():
            files[path].parent.mkdir(parents=True, exist_ok=True)
            files[path].write_text(text)
        git("add", "--", *files)
        summary = change.get("summary") or "a change drafted in Control Room"
        run("git", *IDENTITY, "commit", "-q", "-m", "Nox: " + summary)
        checks(before)
    except (Failed, OSError, subprocess.TimeoutExpired) as exc:
        put_back(tag, files, new)
        raise Failed(f"The change did not pass its checks, so nothing changed ({exc}).")
    if film_on():  # the checks take minutes: a film may have started since the app looked
        put_back(tag, files, new)
        raise Failed("A film is playing, so nothing changed: apply it again when it's over.")
    commit = git("rev-parse", "--short", "HEAD")
    services = running()
    deploy()
    restart(services)
    if not healthy(services):
        git("reset", "-q", "--keep", tag)
        git("tag", "-d", tag)
        switch(release_dir(release))
        restart(services)
        raise Failed("HouseOS did not come back healthy with the change, so it went back to how it was.")
    return {"commit": commit}


def undo(identity):
    tag = "houseos-backup/" + identity
    release = release_dir(backup_release(tag))
    if git("rev-parse", "HEAD^") != git("rev-parse", tag + "^{commit}"):
        raise Failed("Something was committed after this change: undo it by hand (git revert).")
    if film_on():
        raise Failed("A film is playing, so nothing changed: undo it again when it's over.")
    services = running()
    git("reset", "-q", "--keep", tag)
    switch(release)
    restart(services)
    git("tag", "-d", tag)
    if not healthy(services):
        raise Failed("Back to the backup, but HouseOS isn't healthy yet: see Control Room → Health.")
    return {}


def keep(identity):
    tag = "houseos-backup/" + identity
    release = backup_release(tag)
    git("tag", "-d", tag)
    live = {(RUNTIME / name).resolve() for name in ("current", "previous")}
    folder = RUNTIME / "releases" / release
    if re.fullmatch(r"\d{8}T\d{6}Z", release) and folder.is_dir() and folder.resolve() not in live:
        shutil.rmtree(folder)
    return {}


DONE = {
    "apply": "Changed and running. Keep it or undo it in Control Room → Changes.",
    "undo": "Back to how it was before the change.",
    "keep": "Kept; its backup is deleted.",
}


def main():
    for request in notes():
        LOG.clear()
        action = request["action"].removeprefix("code-")
        identity, _, reviewed = request["arg"].partition(":")
        report(request, "running")
        try:
            if action == "apply":
                results = apply(identity, reviewed)
            else:
                results = {"undo": undo, "keep": keep}[action](identity)
            report(request, "done", DONE[action], **results)
        except Failed as exc:
            report(request, "failed", str(exc))
        except Exception as exc:  # a report is always left behind for the page
            report(request, "failed", f"Something went wrong: {exc}")


if __name__ == "__main__":
    main()
