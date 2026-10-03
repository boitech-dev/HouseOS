"""Installing your own integrations from a git repository (Control Room → Integrations).

Two steps, so an administrator sees what they install: **check** clones the repository (https only,
a branch or tag if given, with an optional access token for a private one) into a staging folder
and reads its manifest without running anything; **install** moves that exact commit into place,
turned off. Updating is the same with the saved address and token, and keeps the integration's
keys and data. The token is sent as a header, never written into the address or the copy, and
kept encrypted like the other integrations' secrets.

Sources are a field ("git" today), so other ways in (one Nox drafts, a folder) can come later
through install_folder()."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from pydantic import Field

from . import custom
from .auth import Actor, Input, require_admin
from .config import settings
from .custom import ROW, admin as router, problem
from .db import get_db, utcnow
from .events import emit
from .models import Integration

STAGING_TTL = 3600
MAX_BYTES = 20 * 1024 * 1024
CLONE_SECONDS = 90


def staging_root():
    path = custom.code_root() / ".staging"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for old in path.iterdir():  # checks nobody installed
        if time.time() - old.stat().st_mtime > STAGING_TTL:
            shutil.rmtree(old, ignore_errors=True)
    return path


def checked_url(url):
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise problem(422, "CUSTOM_URL", "Use the repository's https address.")
    if parts.username or parts.password:
        raise problem(422, "CUSTOM_URL", "Put the access token in its own field, not in the address.")
    return url.strip()


def clone(url, ref, token, into: Path):
    """A shallow copy of `ref` (or the default branch). Returns (commit, subject)."""
    command = ["git", "-c", "credential.helper=", "-c", "core.hooksPath=/dev/null"]
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        command += ["-c", f"http.extraHeader=Authorization: Basic {basic}"]
    command += ["clone", "--quiet", "--depth", "1", "--no-tags", "--single-branch"]
    if ref:
        command += ["--branch", ref]
    command += ["--", url, str(into)]
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": tempfile.gettempdir(),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ALLOW_PROTOCOL": "https" if not os.environ.get("HOUSEOS_TEST_GIT_FILE") else "https:file",
    }
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=CLONE_SECONDS, env=environment)
    except FileNotFoundError:
        raise problem(503, "CUSTOM_NO_GIT", "git isn't installed where HouseOS runs.") from None
    except subprocess.TimeoutExpired:
        raise problem(504, "CUSTOM_CLONE_SLOW", "The repository took too long to download.") from None
    if done.returncode != 0:
        said = done.stderr.lower()
        if "authentication" in said or "403" in said or "401" in said or "could not read username" in said:
            raise problem(
                403, "CUSTOM_CLONE_REFUSED", "The repository refused: check the access token and its rights."
            )
        if "not found" in said or "404" in said or "remote branch" in said:
            raise problem(404, "CUSTOM_CLONE_MISSING", "No repository (or branch) at that address.")
        raise problem(502, "CUSTOM_CLONE_FAILED", "The repository couldn't be downloaded.")
    show = subprocess.run(
        ["git", "-C", str(into), "log", "-1", "--format=%H%n%s"], capture_output=True, text=True, timeout=10
    )
    commit, _, subject = show.stdout.strip().partition("\n")
    shutil.rmtree(into / ".git", ignore_errors=True)
    size = sum(f.stat().st_size for f in into.rglob("*") if f.is_file())
    if size > MAX_BYTES:
        raise problem(413, "CUSTOM_TOO_BIG", "That repository is too big for an integration (20 MB at most).")
    return commit, subject[:200]


def seal(token):
    return Fernet(settings.encryption_key.encode()).encrypt(json.dumps({"token": token}).encode()).decode()


def unseal(row):
    if not row.encrypted_secret:
        return None
    try:
        return json.loads(Fernet(settings.encryption_key.encode()).decrypt(row.encrypted_secret.encode()))[
            "token"
        ]
    except (InvalidToken, ValueError, KeyError):
        raise problem(
            503, "CUSTOM_TOKEN_UNREADABLE", "The saved access token can't be read; add the integration again."
        )


def preview(check_id, folder, source):
    try:
        manifest = custom.read_manifest(folder)
    except ValueError as error:
        shutil.rmtree(folder.parent, ignore_errors=True)
        raise problem(422, "CUSTOM_MANIFEST", str(error)) from None
    write_meta(folder.parent, {"manifest": manifest, "source": source})
    files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())
    return {"check_id": check_id, "manifest": manifest, "source": public(source), "files": files[:50]}


def public(source):
    return {k: v for k, v in source.items() if k != "token"}


def write_meta(stage, meta):
    (stage / "meta.json").write_text(json.dumps(meta))
    os.chmod(stage / "meta.json", 0o600)


def stage(url, ref, token):
    check_id = os.urandom(9).hex()
    stage_dir = staging_root() / check_id
    stage_dir.mkdir(mode=0o700)
    try:
        commit, subject = clone(url, ref, token, stage_dir / "code")
    except HTTPException:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise
    source = {
        "kind": "git",
        "url": url,
        "ref": ref or "",
        "commit": commit,
        "subject": subject,
        "token": token,
    }
    return preview(check_id, stage_dir / "code", source)


def staged(check_id):
    stage_dir = staging_root() / check_id if check_id.isalnum() else None
    try:
        meta = json.loads((stage_dir / "meta.json").read_text())
    except (OSError, ValueError, TypeError):
        raise problem(
            410, "CUSTOM_CHECK_EXPIRED", "That check expired: check the repository again."
        ) from None
    return stage_dir, meta


def install_folder(db, folder: Path, manifest, source, actor, replace=False):
    """Put a checked copy in place, turned off (or as it was, on an update). Any source."""
    integration_id = manifest["id"]
    row = db.get(Integration, ROW + integration_id)
    if row and not replace:
        raise problem(
            409, "CUSTOM_EXISTS", "An integration with that id is already installed: update it instead."
        )
    target = custom.code_root() / integration_id
    was_on = bool(row and row.enabled)
    custom.unload(integration_id)
    shutil.rmtree(target, ignore_errors=True)
    shutil.move(str(folder), target)
    now = utcnow().isoformat()
    row = row or Integration(name=ROW + integration_id, config={}, enabled=False)
    token = source.pop("token", None)
    row.config = {
        **(row.config or {}),
        "manifest": manifest,
        "source": source,
        "installed_at": (row.config or {}).get("installed_at") or now,
        "updated_at": now,
        "by": actor.name,
    }
    if token is not None:
        row.encrypted_secret = seal(token) if token else ""
    db.add(row)
    failed = custom.load(integration_id) if was_on else None
    row.enabled = was_on and not failed
    emit(
        db,
        "audit.custom.installed" if not replace else "audit.custom.updated",
        {"id": integration_id, "commit": source.get("commit", "")[:12]},
        actor.id,
    )
    db.commit()
    return failed


class Check(Input):
    url: str = Field(min_length=10, max_length=500)
    ref: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9._/-]*$")
    token: str | None = Field(default=None, max_length=500)


class Staged(Input):
    check_id: str = Field(min_length=6, max_length=40)


@router.post("/check")
def check(body: Check, actor: Actor = Depends(require_admin)):
    """Download and read a repository's manifest, without running any of it."""
    return stage(checked_url(body.url), body.ref, (body.token or "").strip() or None)


@router.post("/install")
def install(body: Staged, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    stage_dir, meta = staged(body.check_id)
    install_folder(db, stage_dir / "code", meta["manifest"], meta["source"], actor)
    shutil.rmtree(stage_dir, ignore_errors=True)
    return custom.describe(
        meta["manifest"]["id"], db.get(Integration, ROW + meta["manifest"]["id"]), actor, db
    )


@router.post("/{integration_id}/check-update")
def check_update(integration_id: str, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    row = custom.row_or_404(db, integration_id)
    source = (row.config or {}).get("source") or {}
    if source.get("kind") != "git":
        raise problem(409, "CUSTOM_NO_SOURCE", "This integration wasn't installed from a repository.")
    found = stage(source["url"], source.get("ref"), unseal(row))
    found["current"] = source.get("commit")
    if found["manifest"]["id"] != integration_id:
        shutil.rmtree(staging_root() / found["check_id"], ignore_errors=True)
        raise problem(409, "CUSTOM_ID_CHANGED", "The repository now holds another integration.")
    return found


@router.post("/{integration_id}/update")
def update(integration_id: str, body: Staged, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    custom.row_or_404(db, integration_id)
    stage_dir, meta = staged(body.check_id)
    if meta["manifest"]["id"] != integration_id:
        raise problem(409, "CUSTOM_ID_CHANGED", "That check is for another integration.")
    meta["source"].pop("token", None)  # keep the saved token
    failed = install_folder(db, stage_dir / "code", meta["manifest"], meta["source"], actor, replace=True)
    shutil.rmtree(stage_dir, ignore_errors=True)
    reply = custom.describe(integration_id, db.get(Integration, ROW + integration_id), actor, db)
    if failed:
        reply["problem"] = failed
    return reply


@router.delete("/{integration_id}")
def remove(integration_id: str, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    """Its code, keys and data go; what it recorded in the activity diary stays."""
    row = custom.row_or_404(db, integration_id)
    custom.remove_files(integration_id)
    db.delete(row)
    emit(db, "audit.custom.removed", {"id": integration_id}, actor.id)
    db.commit()
    return {"removed": integration_id}
