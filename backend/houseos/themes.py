"""Installed themes: made in Nox's theme studio or imported as `.houseos-theme` packs.

Anyone who lives here designs (drafts are their own); an administrator shares a theme with the
house. A theme is a folder of data under `<runtime_root>/themes/<id>/`, checked by the same theme
kit as the bundled ones; its CSS is generated here, never taken from a pack. `house.json` beside the
data records the owner and whether it is a draft, asked to be shared, or shared.

The compiled CSS, fonts and art are served outside `/api` (`/themes/<id>.css?v=<hash>`, `/themes/<id>/
fonts|art/<file>`) to people allowed to see the theme: its owner, and everyone once it is shared."""

import hashlib
import re
import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import Field

from .atomic import write_json
from .auth import Actor, Input, require_actor
from .config import settings
from .db import get_db, utcnow
from .events import emit
from .theme_kit import build, pack as kit_pack, tokens as t

router = APIRouter(tags=["themes"])
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DRAFTS_PER_PERSON = 12
lock = threading.RLock()  # root() may take it inside a locked write


_ready: set[Path] = set()


def root() -> Path:
    """The installed themes' folder, with a copy of this release's Base (every check merges over
    it), refreshed once per process (a release restarts the API)."""
    folder = settings.runtime_root / "themes"
    if folder not in _ready:
        with lock:
            folder.mkdir(parents=True, exist_ok=True)
            t.copy_tree(t.ROOT / "base", folder / "base")
            (folder / "_schema").mkdir(exist_ok=True)
            shutil.copyfile(t.ROOT / "_schema/slots.json", folder / "_schema/slots.json")
            _ready.add(folder)
    return folder


def bundled_ids() -> set[str]:
    return {p.name for p in t.ROOT.iterdir() if p.is_dir() and not p.name.startswith("_")}


def meta(theme_id: str) -> dict:
    return t.read(root() / theme_id / "house.json")


def installed() -> list[str]:
    folder = root()
    return sorted(
        p.name for p in folder.iterdir() if p.name not in {"base", "_schema"} and (p / "house.json").is_file()
    )


def visible(actor: Actor, theme_id: str) -> bool:
    m = meta(theme_id)
    return bool(m) and (m["status"] == "shared" or m["owner"] == actor.id or actor.role == "admin")


def compile_theme(theme_id: str) -> None:
    """The theme's CSS (its tokens in the theme layer, then its fonts), stored with a hash for the URL."""
    folder = root()
    theme, base = t.load(theme_id, folder), t.load("base", folder)
    css = "@layer theme {\n" + build.indent(build.theme_css(theme, base, f"/themes/{theme_id}/")) + "}\n"
    css += build.font_faces(theme, f"/themes/{theme_id}/fonts/")
    (theme.folder / "theme.css").write_text(css)


def public(actor: Actor, theme_id: str) -> dict:
    folder = root()
    theme, m = t.load(theme_id, folder), meta(theme_id)
    info = build.served(build.entry(theme, t.load("base", folder)), f"/themes/{theme_id}/", theme.folder)
    css = (theme.folder / "theme.css").read_bytes()
    return info | {
        "css": f"/themes/{theme_id}.css?v={hashlib.sha256(css).hexdigest()[:12]}",
        "status": m["status"],
        "owner": {"id": m["owner"], "name": m["owner_name"]},
        "mine": m["owner"] == actor.id,
        "version": theme.manifest.get("version", 1),
    }


def keep(actor: Actor, theme_id: str, results, previous: dict | None = None) -> None:
    """After a pack or the studio wrote a checked theme: record its owner and build its CSS.
    A shared theme its owner changes goes back to an administrator (asked again), so nothing
    reaches the house unreviewed; an administrator's own change stays shared."""
    if results.failed:
        raise HTTPException(422, {"message": "The theme didn't pass its checks", "failures": [
            f"{name}: {detail}" for name, _, detail in results.failed
        ]})  # fmt: skip
    previous = meta(theme_id) if previous is None else previous
    status = previous.get("status", "draft") if previous.get("owner", actor.id) == actor.id else "draft"
    if status == "shared" and actor.role != "admin":
        status = "requested"
    write_json(
        root() / theme_id / "house.json",
        {"owner": actor.id, "owner_name": actor.name, "status": status, "updated": utcnow().isoformat()},
        0o660,
    )
    compile_theme(theme_id)


def claim(actor: Actor, theme_id: str) -> None:
    """A theme id this person may write: new, or already theirs; never a bundled one."""
    if actor.role == "guest":
        raise HTTPException(403, "Guests can use the house's themes but not make their own")
    if not ID.fullmatch(theme_id) or theme_id in bundled_ids():
        raise HTTPException(422, f"{theme_id!r} can't be used: choose another theme id")
    m = meta(theme_id)
    if m and m["owner"] != actor.id:
        raise HTTPException(409, "Another person's theme already has this id: choose another")
    if not m and sum(1 for i in installed() if meta(i)["owner"] == actor.id) >= DRAFTS_PER_PERSON:
        raise HTTPException(409, f"You have {DRAFTS_PER_PERSON} themes: remove one first")


@router.get("/themes")
def list_themes(actor: Actor = Depends(require_actor)):
    with lock:
        return {"items": [public(actor, i) for i in installed() if visible(actor, i)]}


@router.post("/themes/import")
def import_pack(file: UploadFile = File(...), actor: Actor = Depends(require_actor), db=Depends(get_db)):
    data = file.file.read(kit_pack.MAX_PACK + 1)  # a worker thread: the lock never blocks the event loop
    try:
        manifest = kit_pack.manifest_of(data)
    except t.ThemeError as error:
        raise HTTPException(422, str(error)) from None
    theme_id = str(manifest.get("id", ""))
    with lock:
        claim(actor, theme_id)
        previous = meta(theme_id)
        was = t.read(root() / theme_id / "theme.json").get("version") if previous else None
        try:
            theme_id, results = kit_pack.unpack(data, root(), theme_id)
        except (t.ThemeError, KeyError, ValueError, TypeError, AttributeError) as error:
            raise HTTPException(422, f"Not a usable theme pack: {error}"[:300]) from None
        keep(actor, theme_id, results, previous)
        emit(db, "themes.changed", {"id": theme_id}, user_id=actor.id)
        db.commit()
        # Importing an id you already have replaces it: say which version it was.
        return public(actor, theme_id) | {"replaced": was}


@router.get("/themes/{theme_id}/pack")
def export_pack(theme_id: str, actor: Actor = Depends(require_actor)):
    with lock:
        if not ID.fullmatch(theme_id) or not visible(actor, theme_id):
            raise HTTPException(404, "No such theme")
        target = kit_pack.pack(theme_id, root(), root() / f".{theme_id}.houseos-theme")
    data = target.read_bytes()
    target.unlink(missing_ok=True)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{theme_id}.houseos-theme"'},
    )


class StatusChange(Input):
    status: str = Field(pattern="^(draft|requested|shared)$")


@router.put("/themes/{theme_id}/status")
def change_status(
    theme_id: str, body: StatusChange, actor: Actor = Depends(require_actor), db=Depends(get_db)
):
    """The owner asks to share (or takes the request back); an administrator shares or unshares."""
    with lock:
        m = meta(theme_id) if ID.fullmatch(theme_id) else {}
        if not m or not visible(actor, theme_id):
            raise HTTPException(404, "No such theme")
        admin, owner = actor.role == "admin", m["owner"] == actor.id
        allowed = (admin and body.status in ("draft", "shared")) or (
            owner and body.status in ("draft", "requested") and m["status"] != "shared"
        )
        if not allowed:
            raise HTTPException(403, "Only an administrator shares a theme with the house")
        m["status"] = body.status
        write_json(root() / theme_id / "house.json", m, 0o660)
        emit(db, "themes.changed", {"id": theme_id, "status": body.status})
        db.commit()
        return public(actor, theme_id)


@router.delete("/themes/{theme_id}")
def remove(theme_id: str, actor: Actor = Depends(require_actor), db=Depends(get_db)):
    with lock:
        m = meta(theme_id) if ID.fullmatch(theme_id) else {}
        if not m or not (m["owner"] == actor.id or actor.role == "admin"):
            raise HTTPException(404, "No such theme")
        shutil.rmtree(root() / theme_id)
        emit(db, "themes.changed", {"id": theme_id, "removed": True})
        db.commit()
        return {"removed": theme_id}


# Served outside /api (main.py mounts this router at the root): CSS, fonts and art.
files = APIRouter()


@files.get("/themes/{name}.css", include_in_schema=False)
def theme_css(name: str, actor: Actor = Depends(require_actor)):
    if not ID.fullmatch(name) or not visible(actor, name):
        raise HTTPException(404, "No such theme")
    return FileResponse(
        root() / name / "theme.css",
        media_type="text/css",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@files.get("/themes/bundled/{theme_id}/{kind}/{name}", include_in_schema=False)
def bundled_file(theme_id: str, kind: str, name: str):
    """A bundled theme's pictures and fonts: part of HouseOS itself (public in its repository), so
    the sign-in page may show them too (its crest)."""
    if (
        kind not in ("fonts", "art")
        or theme_id not in bundled_ids()
        or not kit_pack.DATA.fullmatch(f"{kind}/{name}")
    ):
        raise HTTPException(404, "Not found")
    path = t.ROOT / theme_id / kind / name
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@files.get("/themes/{theme_id}/{kind}/{name}", include_in_schema=False)
def theme_file(theme_id: str, kind: str, name: str, actor: Actor = Depends(require_actor)):
    if (
        kind not in ("fonts", "art")
        or not ID.fullmatch(theme_id)
        or not kit_pack.DATA.fullmatch(f"{kind}/{name}")
        or not visible(actor, theme_id)
    ):
        raise HTTPException(404, "Not found")
    path = root() / theme_id / kind / name
    if not path.is_file():
        raise HTTPException(404, "Not found")
    # Art is checked (no scripts in SVG); opened on its own, it still may not run or fetch anything.
    return FileResponse(
        path,
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
