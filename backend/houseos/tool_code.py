"""Nox drafts code changes; an admin reads the diff and applies it in Control Room → Changes.

The source tree (settings.source_root) is only ever read here. A draft is one JSON file under
<runtime>/run/code/<id>.json; what it may touch is code_rules.allowed. Apply freezes the draft and
sends a signed note with the digest of the diff the admin read (house_actions.send):
deploy/code_change.py natively, `houseos.sh code` in Docker. It backs up first (git tag
houseos-backup/<id>), checks, deploys, and goes back by itself if the house doesn't come back; the
backup stays until the admin presses Keep. See docs/CHANGING-HOUSEOS.md."""

import difflib
import fcntl
import json
import os
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import Field

from . import code_rules
from .atomic import write_json
from .auth import Input, require_admin
from .config import settings
from .db import get_db
from .events import emit
from .tool_setup import Empty, admin_only, card

router = APIRouter(prefix="/admin/changes", tags=["control-room"])
DOCS = "docs/CHANGING-HOUSEOS.md"
ID = re.compile(r"[0-9a-f]{12}")
# Not code: git, dependencies, builds, data, backups, other agents' worktrees.
SKIP = {".git", ".claude", "node_modules", "dist", "__pycache__", ".venv", "venv", "backups", "data",
        "runtime", "vendor", "dependencies", "evidence", ".pytest_cache", ".ruff_cache", "import"}  # fmt: skip
SECRET = re.compile(r"(^|/)(\.env[^/]*|[^/]*\.(env|key|pem|p12|sql|db|sqlite3?)|[^/]*secret[^/]*)$", re.I)
TEXT = {".py", ".ts", ".tsx", ".css", ".md", ".json", ".sh", ".yml", ".yaml", ".toml", ".cjs", ".mjs",
        ".js", ".html", ".txt", ".service", ".timer", ".path", ".ini", ".mako", ".nft", ".cfg"}  # fmt: skip
LIMIT = 400_000
# Characters that make code read differently from what it does: controls but tab and newline (a lone
# carriage return hides a line's start), other line breaks, text direction, zero-width, tags.
HIDDEN = re.compile(
    r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff\U000e0000-\U000e007f]"
)


def root():
    source = settings.source_root
    if not source or not source.is_absolute() or not source.is_dir():
        raise HTTPException(409, "Code changes aren't set up on this house: see docs/CHANGING-HOUSEOS.md")
    return source.resolve()


def target(path, write=False):
    """(relative path, file) for a source file Nox may read, or change when write=True."""
    base = root()
    rel = PurePosixPath(path.strip())
    name = rel.as_posix()
    outside = "Only files inside the HouseOS source, as a path such as backend/houseos/music.py."
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise HTTPException(422, outside)
    if SKIP & set(rel.parts):
        raise HTTPException(
            422, "That folder isn't source code (git, dependencies, builds, data or backups)."
        )
    if SECRET.search(name):
        raise HTTPException(403, "Keys and settings files are never read or changed here.")
    if rel.suffix not in TEXT and rel.name != "Dockerfile":
        raise HTTPException(422, "Only text files: pictures and other files change by hand.")
    full = (base / rel).resolve()
    if not full.is_relative_to(base):
        raise HTTPException(422, outside)
    # Only where Nox may write, and at that very path (not through a link to another file).
    if write and (full != base / rel or not code_rules.allowed(name)):
        raise HTTPException(
            403,
            "Nox drafts changes to the app's code, tests, screens, bundled themes and docs only; what "
            "builds, checks, deploys and undoes changes by hand (docs/CHANGING-HOUSEOS.md).",
        )
    if write and settings.storage_container and rel.parts[0].lower() in {"frontend", "themes"}:
        raise HTTPException(
            403,
            "In a Docker install the screens and bundled themes come prebuilt: Nox can change the "
            "server side (backend, docs), not frontend/ or themes/.",
        )
    return name, full


def original(full):
    """The file as it is in the source ("" when new); refuses anything that isn't UTF-8 text."""
    if not full.is_file():
        return ""
    data = full.read_bytes()[: LIMIT + 1]
    if len(data) > LIMIT or b"\0" in data:
        raise HTTPException(422, "That file is too big or not text.")
    try:
        return data.decode()
    except UnicodeDecodeError:
        raise HTTPException(422, "That file is too big or not text.")


def git_dir():
    return root() / ".git"


def ref(name):
    """A git ref's commit without git (the Docker app has none): loose file, then packed-refs."""
    git = git_dir()
    if (git / name).is_file():
        return (git / name).read_text().strip()
    packed = git / "packed-refs"
    for line in packed.read_text().splitlines() if packed.is_file() else ():
        sha, _, found = line.partition(" ")
        if found == name:
            return sha
    return ""


def head():
    try:
        text = (git_dir() / "HEAD").read_text().strip()
    except OSError:
        raise HTTPException(409, "The HouseOS source isn't a git checkout: see docs/CHANGING-HOUSEOS.md")
    return ref(text[5:]) if text.startswith("ref: ") else text


def backups():
    """Change ids with a backup waiting for Keep or Undo (tags houseos-backup/<id>)."""
    git, prefix = git_dir(), "refs/tags/houseos-backup/"
    names = {p.name for p in (git / prefix).glob("*")}
    packed = git / "packed-refs"
    for line in packed.read_text().splitlines() if packed.is_file() else ():
        if line.partition(" ")[2].startswith(prefix):
            names.add(line.partition(" ")[2][len(prefix) :])
    return sorted(n for n in names if ID.fullmatch(n))


def folder():
    return settings.runtime_root / "run" / "code"


def load(identity):
    if not ID.fullmatch(identity or ""):
        return None
    try:
        return json.loads((folder() / (identity + ".json")).read_text())
    except (OSError, ValueError):
        return None


@contextmanager
def locked():
    """One at a time: Nox's tools and the Changes page each read, change and save a draft."""
    folder().mkdir(mode=0o2770, parents=True, exist_ok=True)
    fd = os.open(folder() / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def save(change):
    folder().mkdir(mode=0o2770, parents=True, exist_ok=True)
    # Group-readable: the house computer's side reads it (the Docker helper's task, natively the
    # checkout's owner).
    write_json(folder() / (change["id"] + ".json"), change, mode=0o660)


def changes():
    found = [load(p.stem) for p in folder().glob("*.json")] if folder().is_dir() else []
    return sorted((c for c in found if c), key=lambda c: c["created"], reverse=True)


def draft(actor, create=False, summary=None):
    """The admin's change being drafted (not yet sent to the house computer)."""
    change = next((c for c in changes() if c["by_id"] == actor.id and not c["requests"]), None)
    if change is None and create:
        change = {"id": secrets.token_hex(6), "base": head(), "summary": "", "author": "Nox",
                  "by": actor.name, "by_id": actor.id, "created": time.time(), "files": {},
                  "before": {}, "requests": []}  # fmt: skip
    if change is not None and summary:
        change["summary"] = summary.strip()[:120]
    return change


def diff(change):
    """File by file, the source as Nox read it against the drafted text."""
    out = []
    for path, text in sorted(change["files"].items()):
        before = change["before"].get(path, "")
        lines = difflib.unified_diff(
            before.splitlines(keepends=True), text.splitlines(keepends=True), "a/" + path, "b/" + path
        )
        out.append({"path": path, "new": not before, "diff": "".join(lines)})
    return out


def result(request):
    """The house computer's report on one request (helper-out/<id>.json), or None while waiting."""
    out = settings.runtime_root / "run" / "helper-out"
    try:
        found = json.loads((out / (request["id"] + ".json")).read_text())
    except (OSError, ValueError):
        return None
    log = out / (request["id"] + ".log")
    found["log"] = log.read_text()[-4000:] if log.is_file() else ""
    return found


def state(change, backed_up):
    """draft · working · applied · failed · undone · kept, from the last request's result."""
    if not change["requests"]:
        return {"state": "draft"}
    last = change["requests"][-1]
    done = result(last)
    if not done or done.get("state") == "running":
        return {
            "state": "working",
            "action": last["action"],
            "stuck": time.time() - last["at"] > 90 and not done,
        }
    report = {"action": last["action"], "message": done.get("message", ""), "log": done.get("log", "")}
    if done.get("state") != "done":
        return {"state": "applied" if backed_up else "failed", "failed": True, **report}
    return {"state": {"apply": "applied", "undo": "undone", "keep": "kept"}[last["action"]], **report}


def summary_row(change, marks):
    return {
        "id": change["id"],
        "summary": change["summary"] or "Changes drafted by Nox",
        "author": change["author"],
        "by": change.get("by"),
        "created": change["created"],
        "files": sorted(change["files"]),
        "backed": change["id"] in marks,
        **state(change, change["id"] in marks),
    }


# ---------------------------------------------------------------------------------------------
# Nox's tools (setup mode, admins)

NEXT = "The admin reads the full diff and applies it in Control Room → Changes; nothing changes before."


class Search(Input):
    query: str = Field(min_length=2, max_length=200, description="Text to find (not case-sensitive).")
    path: str = Field(default="", max_length=200, description="Only under this folder, e.g. backend/houseos.")


class Read(Input):
    path: str = Field(min_length=1, max_length=300)
    start: int = Field(default=1, ge=1, description="First line.")
    lines: int = Field(default=200, ge=1, le=400)


class Edit(Input):
    path: str = Field(min_length=1, max_length=300)
    old: str = Field(min_length=1, max_length=20000, description="Exact text now in the file, found once.")
    new: str = Field(max_length=20000)
    summary: str | None = Field(default=None, max_length=120, description="What the whole change does.")


class Write(Input):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=LIMIT, description="The whole file.")
    summary: str | None = Field(default=None, max_length=120, description="What the whole change does.")


class Discard(Input):
    path: str | None = Field(
        default=None, max_length=300, description="One file; empty drops the whole draft."
    )


def code_search(body, actor, db):
    base, needle, found = root(), body.query.casefold(), []
    start = (base / body.path.strip().strip("/")).resolve()
    if not start.is_relative_to(base):
        raise HTTPException(422, "Only folders inside the HouseOS source.")
    for folder_path, folders, files in os.walk(start):
        folders[:] = sorted(f for f in folders if f not in SKIP)
        for file in sorted(files):
            rel = (Path(folder_path) / file).relative_to(base).as_posix()
            try:
                full = target(rel)[1]
                if not full.is_file() or full.stat().st_size > LIMIT:
                    continue
                text = original(full)
            except (HTTPException, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if needle in line.casefold():
                    found.append({"path": rel, "line": number, "text": line.strip()[:200]})
                    if len(found) > 40:
                        return {"status": "completed", "matches": found[:40], "more": True}
    return {"status": "completed", "matches": found, "more": False}


def code_read(body, actor, db):
    name, full = target(body.path)
    change = draft(actor)
    staged = change and name in change["files"]
    text = change["files"][name] if staged else original(full)
    if not staged and not full.is_file():
        raise HTTPException(404, "No such file: search with code_search.")
    lines = text.splitlines()
    shown = lines[body.start - 1 : body.start - 1 + body.lines]
    return {
        "status": "completed",
        "path": name,
        "drafted": bool(staged),
        "total_lines": len(lines),
        "text": "\n".join(f"{body.start + i}: {line}" for i, line in enumerate(shown)),
    }


def stage(actor, name, text, summary):
    if HIDDEN.search(text + (summary or "")):
        raise HTTPException(
            422,
            "Invisible characters (controls, line separators, text direction, zero-width) are "
            "refused: write them as escapes.",
        )
    with locked():
        change = draft(actor, create=True, summary=summary)
        before = change["before"].setdefault(name, original(target(name)[1]))
        if text == before:
            change["files"].pop(name, None)
            change["before"].pop(name)
        else:
            change["files"][name] = text
        save(change)
    return {
        "status": "completed",
        "change": change["id"],
        "files": sorted(change["files"]),
        "next": NEXT,
        "card": card("Change drafted", change["summary"] or name, "/control?tab=changes"),
    }


def code_edit(body, actor, db):
    name, full = target(body.path, write=True)
    change = draft(actor)
    text = change["files"][name] if change and name in change["files"] else original(full)
    count = text.count(body.old)
    if count != 1:
        raise HTTPException(
            422,
            "The old text isn't in the file: read it again (code_read)."
            if not count
            else f"The old text is in the file {count} times: include more lines around it.",
        )
    return stage(actor, name, text.replace(body.old, body.new), body.summary)


def code_write(body, actor, db):
    name, _ = target(body.path, write=True)
    return stage(actor, name, body.content, body.summary)


def code_diff(body, actor, db):
    change = draft(actor)
    if not change or not change["files"]:
        return {"status": "completed", "change": None, "diff": "", "note": "Nothing drafted yet."}
    text = "\n".join(f["diff"] for f in diff(change))
    return {
        "status": "completed",
        "change": change["id"],
        "summary": change["summary"],
        "files": sorted(change["files"]),
        "diff": text[:12000] + ("\n… (the rest is on the Changes page)" if len(text) > 12000 else ""),
        "next": NEXT,
    }


def code_discard(body, actor, db):
    with locked():
        return discard(body, actor)


def discard(body, actor):
    change = draft(actor)
    if not change:
        return {"status": "completed", "note": "Nothing drafted."}
    if body.path:
        change["files"].pop(target(body.path)[0], None)
        change["before"].pop(target(body.path)[0], None)
    if body.path and change["files"]:
        save(change)
        return {"status": "completed", "change": change["id"], "files": sorted(change["files"])}
    (folder() / (change["id"] + ".json")).unlink(missing_ok=True)
    return {"status": "completed", "discarded": change["id"]}


def code_list(body, actor, db):
    marks = backups()
    rows = [summary_row(c, marks) for c in changes()]
    for row in rows:  # what the house computer printed (test output) is for the admin's page only
        row.pop("log", None)
        row.pop("message", None)
    return {"status": "completed", "changes": rows[:10], "page": "/control?tab=changes"}


TOOLS = {
    name: (model, description, admin_only(handler))
    for name, model, description, handler in (
        ("code_search", Search, "Find text in HouseOS's own source code (paths and lines).", code_search),
        ("code_read", Read, f"Read a source file with line numbers ({DOCS} explains the code).", code_read),
        (
            "code_edit",
            Edit,
            "Draft a change to a source file: replace one exact piece of text (found once). Drafts "
            "only: the admin reviews and applies them in Control Room → Changes.",
            code_edit,
        ),
        ("code_write", Write, "Draft a new source file, or a whole file's new text.", code_write),
        ("code_diff", Empty, "The drafted change as a diff, to show the admin.", code_diff),
        ("code_discard", Discard, "Drop one drafted file, or the whole draft.", code_discard),
        ("code_list", Empty, "Drafted and applied changes, and backups waiting for Keep or Undo.", code_list),
    )
}


# ---------------------------------------------------------------------------------------------
# Control Room → Changes


@router.get("")
def listing(actor=Depends(require_admin)):
    from .house_actions import helper_alive

    try:
        base = head()
    except HTTPException as exc:
        return {"ready": False, "problem": exc.detail, "changes": []}
    marks = backups()
    rows = []
    for change in changes():
        row = summary_row(change, marks)
        row["stale"] = row["state"] in {"draft", "undone", "failed"} and change["base"] != base
        row["diff"], row["digest"] = diff(change), code_rules.digest(change)
        rows.append(row)
    return {
        "ready": True,
        "docker": settings.storage_container,
        "helper": helper_alive() if settings.storage_container else None,
        "changes": rows,
    }


@router.post("/{identity}/{action}")
def act(
    identity: str,
    action: str,
    digest: str = Body("", embed=True, description="Apply: the digest of the diff on the admin's screen."),
    actor=Depends(require_admin),
    db=Depends(get_db),
):
    with locked():  # read to saved at once: a draft saved meanwhile can't drop this request
        return request_action(identity, action, digest, actor, db)


def request_action(identity, action, digest, actor, db):
    from .house_actions import helper_alive, house_busy, send

    change = load(identity)
    if action not in {"apply", "undo", "keep", "discard"} or not change:
        raise HTTPException(404, "Unknown change")
    base = head()
    row = summary_row(change, backups())
    if row["state"] == "working":
        raise HTTPException(409, "The house computer is still working on this change")
    if action == "discard":
        if row["backed"]:
            raise HTTPException(409, "Keep or undo this change first")
        (folder() / (identity + ".json")).unlink(missing_ok=True)
        return {"status": "discarded"}
    if action == "apply":
        if not change["files"] or row["state"] not in {"draft", "undone", "failed"}:
            raise HTTPException(409, "This change can't be applied now")
        if change["base"] != base:
            raise HTTPException(409, "HouseOS changed since this was drafted: ask Nox to draft it again")
        if digest != code_rules.digest(change):
            raise HTTPException(409, "This change is no longer the one on your screen: look at it again")
    elif not row["backed"]:
        raise HTTPException(409, "There is no backup for this change")
    if action != "keep" and house_busy(db, music=False):  # songs resume after the restart
        raise HTTPException(409, "A film is playing: try again when it's over")
    if settings.storage_container and not helper_alive():
        raise HTTPException(
            409, "The HouseOS helper is not running: on the server, run ./houseos.sh buttons on"
        )
    if not settings.storage_container:  # houseos-code.service, as the checkout's owner, works in both
        for name in ("helper-in", "helper-out"):
            (settings.runtime_root / "run" / name).mkdir(mode=0o2770, parents=True, exist_ok=True)
    # Saved before the note: a change with a request is frozen (Nox's tools start a new draft), and
    # the house computer refuses one whose diff no longer has the digest the admin approved.
    request = str(uuid.uuid4())
    change["requests"].append({"action": action, "id": request, "at": time.time(), "by": actor.name})
    save(change)
    send("code-" + action, identity + (":" + digest if action == "apply" else ""), request)
    emit(
        db,
        "audit.code_change",
        {"action": action, "change": identity, "files": sorted(change["files"])},
        actor.id,
    )
    db.commit()
    return {"status": "accepted", "request": request}
