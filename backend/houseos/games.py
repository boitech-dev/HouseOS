"""Games: the house's own games (uploaded, pasted as a link, or read from a folder the admin
points at), named and pictured from the open libretro database, played in the browser (EmulatorJS,
downloaded when a game first needs it) or on the TV (games_tv). HouseOS never downloads a game
by itself. Saves belong to each person: nobody else, not even an admin, can read them."""

import errno
import json
import os
import re
import shutil
import threading
import time
from datetime import timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import games_catalog as catalog
from . import ipc
from .auth import Actor, require_actor, require_permission
from .config import settings
from .db import SessionLocal, get_db, utcnow
from .events import emit, failure_site
from .fetcher_games import DIR as CACHE
from .fetcher_games import EJS_FILE, EMULATORJS
from .games_systems import AMBIGUOUS, BY_EXT, DISC_ENTRY, SYSTEMS, system_for
from .models import Record, User

router = APIRouter(prefix="/games", tags=["games"])
files = APIRouter()  # the emulator's own files, outside /api so browsers keep them
SURFACES = ("browser", "tv")
KEEP_STATES = 12  # per person, game and surface; older ones go
MAX_STATE = 64 * 1024**2
MAX_SAVE = 16 * 1024**2
MAX_PATCHED = 128 * 1024**2
PREFERRED = {"fr": ("France", "Europe", "World", "USA", "Japan"), "en": ("USA", "World", "Europe", "Japan")}


def library():
    return Path(settings.data_root) / "media" / "games"


def bios_dir():
    return library() / "_bios"


def saves(user_id, game_id):
    return Path(settings.data_root) / "game-saves" / user_id / game_id


def allowed(actor):
    require_permission(actor, "games.play")


def fetch(action, timeout=90, **extra):
    return ipc.fetcher(action, timeout=timeout, **extra)


def games(db, *, visible=True, state=None):
    query = select(Record).where(Record.kind == "game.rom", Record.deleted_at.is_(None))
    if state:
        query = query.where(Record.data["state"].as_string() == state)
    rows = db.scalars(query).all()
    return [r for r in rows if not visible or not (r.data.get("hidden") or r.data.get("duplicate_of"))]


def game_row(db, game_id):
    row = db.get(Record, game_id)
    if not row or row.kind != "game.rom" or row.deleted_at or row.data.get("hidden"):
        raise HTTPException(404, "Game not found")
    return row


def game_path(db, row):
    """The file itself, only where the house keeps games or in a games folder still configured."""
    path = Path(row.data.get("_path") or "/nonexistent")
    roots = [library()]
    if row.data.get("source") == "folder":
        folder = db.get(Record, row.data.get("folder_id") or "")
        roots = [Path(folder.data["path"])] if folder and not folder.deleted_at else []
    if (
        ".." in path.parts
        or not any(path.is_relative_to(root) for root in roots)
        or path.is_symlink()
        or not path.is_file()
    ):
        raise HTTPException(404, {"code": "GAME_FILE_MISSING", "message": "This game's file is gone."})
    return path


# --- Who played what -------------------------------------------------------------------------


def play_id(user_id, game_id):
    return str(uuid5(NAMESPACE_URL, f"houseos:game-play:{user_id}:{game_id}"))


def plays(db, user_id=None):
    query = select(Record).where(Record.kind == "game.play")
    if user_id:
        query = query.where(Record.owner_id == user_id)
    return db.scalars(query).all()


def play_row(db, actor, game_id):
    row = db.get(Record, play_id(actor.id, game_id))
    if not row:
        row = Record(
            id=play_id(actor.id, game_id), kind="game.play", owner_id=actor.id, visibility="private",
            data={"game_id": game_id, "plays": 0, "seconds": 0}, version=1,
        )  # fmt: skip
        db.add(row)
    return row


# --- Identify: name, facts, pictures, duplicates ---------------------------------------------


def identify(game_id):
    """Look a game up and fetch its pictures; safe to repeat (the maintenance sweep retries)."""
    with SessionLocal() as db:
        row = db.get(Record, game_id)
        if not row or row.deleted_at or row.data.get("identified"):
            return
        data = dict(row.data)
        system = data.get("system")
        try:
            path = game_path(db, row)
        except HTTPException:
            return
        if not system and path.suffix.lower() == ".zip":
            system = zip_system(path)
            data["system"] = system
        if not system:
            row.data = {**data, "identified": True}
            db.commit()
            return
        if not catalog.ensure(system, fetch):
            return  # the fetcher is away: try again on the next sweep
        crcs, size, inner = catalog.fingerprint(path, system)
        facts = catalog.describe(system, crcs, inner if path.suffix.lower() == ".zip" else path.name)
        key = facts["crc"] or row.id
        art = {}
        # The DAT's name first; libretro's pictures of homebrew keep the file's full name
        # ("… (Aftermarket) (Unl)"), which the DAT's name drops.
        stem = Path(inner if path.suffix.lower() == ".zip" else path.name).stem
        names = list(dict.fromkeys(n for n in (facts["art_name"], stem) if n))
        for kind in ("box", "title", "snap"):
            cached = CACHE / "art" / f"{key}-{kind}.png"
            for name in names:
                if cached.is_file() and cached.stat().st_size > 0:
                    break
                fetch("games_art", system=system, key=key, kind=kind, name=name, timeout=30)
            art[kind] = cached.is_file() and cached.stat().st_size > 0
        twin = twin_of(db, crcs, before=row)
        facts = {k: v for k, v in facts.items() if k not in {"crc", "art_name"}}
        base = db.get(Record, data.get("base_id") or "")
        if data.get("title_fixed"):
            facts.pop("title")
        if base:  # a patched game: the original's pictures and facts, and it stays a hack
            facts.update(
                {
                    k: base.data.get(k)
                    for k in ("genre", "developer", "publisher", "year", "players", "franchise")
                }
            )
            facts.update(hack=True, base=base.data.get("title"))
            key, art = base.data.get("art_key") or key, base.data.get("art") or art
        row.data = {
            **data,
            **facts,
            "crcs": crcs,
            "art_key": key,
            "art": art,
            "duplicate_of": twin.id if twin else None,
            "identified": True,
        }
        row.version += 1
        emit(db, "games.changed", {"id": row.id})
        db.commit()


def zip_system(path):
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            names = [m.filename for m in archive.infolist() if not m.is_dir()]
    except (OSError, zipfile.BadZipFile):
        return None
    found = {BY_EXT[e] for e in (os.path.splitext(n)[1].lower() for n in names) if e in BY_EXT}
    return found.pop() if len(found) == 1 else None


def sweep(db, budget=40):
    """Maintenance: identify what isn't yet (new folder games, a fetcher that was away), and
    rescan the games folders once a day or when asked."""
    started = time.monotonic()
    recover(db)
    for folder in db.scalars(
        select(Record).where(Record.kind == "games.folder", Record.deleted_at.is_(None))
    ):
        last = folder.data.get("scanned_at") or 0
        if folder.data.get("scan_requested") or time.time() - last > 86400:
            try:
                scan(db, folder)
                db.commit()
            except Exception as error:  # an unplugged drive: the others and the naming go on
                db.rollback()
                print("games folder unavailable:", folder.id, type(error).__name__, flush=True)
    for row in games(db, visible=False, state="ready"):
        if time.monotonic() - started > budget:
            break
        if not row.data.get("identified"):
            identify(row.id)


def scan(db, folder):
    """Index a games folder (read only: nothing is copied, moved or changed there)."""
    from .files import readonly_fd

    root = Path(folder.data["path"])
    with readonly_fd(str(root)):
        pass  # still where the admin said, on the approved disk, no symlinked parents
    # Every game this folder ever had, gone ones too: a file that comes back revives its row.
    known = {
        r.data.get("rel"): r
        for r in db.scalars(select(Record).where(Record.kind == "game.rom"))
        if r.data.get("folder_id") == folder.id
    }
    seen, skipped = set(), 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")))
        parts = Path(base).relative_to(root).parts
        for name in sorted(names):
            path = Path(base) / name
            if name.startswith(".") or not catalog.is_entry(name, names) or path.is_symlink():
                continue
            system = system_for(name, parts)
            if not system and os.path.splitext(name)[1].lower() == ".zip":
                system = zip_system(path)
            if not system:
                skipped += 1
                continue
            rel = str(path.relative_to(root))
            seen.add(rel)
            if rel in known:
                known[rel].deleted_at = None
                continue
            db.add(
                Record(
                    id=str(uuid5(NAMESPACE_URL, f"houseos:game-folder:{folder.id}:{rel}")),
                    kind="game.rom",
                    owner_id=folder.owner_id,
                    visibility="house",
                    data={
                        "state": "ready", "source": "folder", "folder_id": folder.id, "rel": rel,
                        "_path": str(path), "file": name, "system": system,
                        "title": catalog.clean(name), "size": path.stat().st_size,
                    },
                    version=1,
                )
            )  # fmt: skip
    for rel, row in known.items():
        # Gone from the folder: gone from the library (saves stay). An empty walk is a drive that
        # isn't there right now, not a folder emptied: nothing leaves then.
        if rel not in seen and seen and not row.deleted_at:
            row.deleted_at = utcnow()
    folder.data = {
        **folder.data,
        "scan_requested": False,
        "scanned_at": time.time(),
        "count": len(seen),
        "skipped": skipped,
    }
    emit(db, "games.changed", {"folder": folder.id})
    log(db, "scanned", os.path.basename(folder.data["path"]), count=len(seen), skipped=skipped)


# --- The library -------------------------------------------------------------------------------


def house_language(db):
    from .house_settings import get_house_settings

    return (get_house_settings(db).get("language") or "en")[:2]


def bios_present():
    return {name for s in SYSTEMS.values() for name in s.get("bios", []) if (bios_dir() / name).is_file()}


def card(rows, mine, counts, names, region_order, present, tv_ready):
    """One card per game: its versions (regions, revisions, translations) grouped."""
    ordered = sorted(
        rows,
        key=lambda r: (
            -(mine.get(r.id, {}).get("last_played") or 0),
            bool(r.data.get("hack")),
            region_order.index(r.data["region"]) if r.data.get("region") in region_order else 99,
            r.data.get("title", ""),
        ),
    )
    first = ordered[0]
    d = first.data
    system = SYSTEMS.get(d.get("system") or "", {})
    art = d.get("art") or {}
    key = d.get("art_key")
    own = [mine.get(r.id, {}) for r in rows]
    needs = bool(system.get("needs_bios")) and not set(system.get("bios", [])) & present
    # A disc in several files (.cue + tracks) only opens on the TV; one file (.chd, .pbp, .iso,
    # a zip) plays in the browser too.
    several = os.path.splitext(d.get("file") or "")[1].lower() in {".cue", ".gdi", ".m3u"}
    return {
        "id": first.id,
        "title": d.get("title") or d.get("file") or "Game",
        "system": d.get("system"),
        "system_name": system.get("name"),
        "year": d.get("year"),
        "genre": d.get("genre"),
        "players": d.get("players"),
        "developer": d.get("developer"),
        "publisher": d.get("publisher"),
        "franchise": d.get("franchise"),
        "hack": all(r.data.get("hack") for r in rows),
        "base": d.get("base"),
        "region": d.get("region"),
        "versions": len(rows),
        "art": {k: f"/api/v1/games/art/{key}/{k}" for k in ("box", "title", "snap") if art.get(k)},
        "here": bool(system.get("browser")) and not needs and not several,
        "tv": bool(system.get("tv")) and tv_ready and not needs,
        "needs_bios": needs,
        "identifying": not d.get("identified"),
        "state": d.get("state", "ready"),
        "progress": progress(first.id) if d.get("state") == "downloading" else None,
        "favourite": any(o.get("favourite") for o in own),
        "last_played": max((o.get("last_played") or 0 for o in own), default=0) or None,
        "seconds": sum(o.get("seconds") or 0 for o in own),
        "plays": sum(counts.get(r.id, 0) for r in rows),
        "added_at": min(r.created_at for r in rows),
        "added_by": names.get(first.owner_id),
    }


def cards(db, actor):
    from .games_tv import host_ready

    rows = games(db)
    mine = {p.data["game_id"]: p.data for p in plays(db, actor.id)}
    counts = {}
    for p in plays(db):
        counts[p.data["game_id"]] = counts.get(p.data["game_id"], 0) + (p.data.get("plays") or 0)
    names = dict(db.execute(select(User.id, User.name)).all())
    groups = {}
    for row in rows:
        key = (row.data.get("system"), catalog.fold(row.data.get("title") or row.id))
        groups.setdefault(key, []).append(row)
    order = PREFERRED.get(house_language(db), PREFERRED["en"])
    present, ready = bios_present(), host_ready()
    return [card(g, mine, counts, names, order, present, ready) for g in groups.values()]


SORTS = {
    "title": (lambda c: c["title"].casefold().removeprefix("the "), False),
    "added": (lambda c: str(c["added_at"]), True),
    "played": (lambda c: c["last_played"] or 0, True),
    "plays": (lambda c: c["plays"], True),
    "year": (lambda c: c["year"] or 0, True),
}


def matches(c, q, system, genre, players, decade, hacks, here, favourites, played=False):
    text = " ".join(
        str(c.get(k) or "") for k in ("title", "franchise", "developer", "publisher", "genre", "base")
    )
    return (
        (not q or all(word in text.casefold() for word in q.casefold().split()))
        and (not system or c["system"] == system)
        and (not genre or genre.casefold() in str(c["genre"] or "").casefold())
        and (not players or (c["players"] or 1) >= players)
        and (not decade or (c["year"] or 0) // 10 * 10 == decade)
        and (not hacks or c["hack"])
        and (not here or c["here"])
        and (not favourites or c["favourite"])
        and (not played or c["last_played"])
    )  # fmt: skip


@router.get("")
def list_games(
    q: Annotated[str, Query(max_length=100)] = "",
    system: Annotated[str, Query(max_length=20)] = "",
    genre: Annotated[str, Query(max_length=80)] = "",
    players: Annotated[int, Query(ge=0, le=8)] = 0,
    decade: Annotated[int, Query(ge=0, le=2100)] = 0,
    hacks: bool = False,
    here: bool = False,
    favourites: bool = False,
    played: bool = False,
    sort: Literal["title", "added", "played", "plays", "year"] = "title",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=120)] = 60,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """The library as cards, filtered and sorted; `facets` count over the whole library.
    ponytail: built in memory, instant for a few thousand games; index in SQL beyond that."""
    allowed(actor)
    everything = cards(db, actor)
    found = [
        c
        for c in everything
        if matches(c, q, system, genre, players, decade, hacks, here, favourites, played)
    ]
    key, reverse = SORTS[sort]
    found.sort(key=lambda c: c["title"].casefold())
    found.sort(key=key, reverse=reverse)
    facets = {"systems": {}, "genres": {}, "decades": {}, "players": {}}
    for c in everything:
        facets["systems"][c["system"] or ""] = facets["systems"].get(c["system"] or "", 0) + 1
        for g in re.split(r"\s*[/,]\s*", c["genre"] or ""):
            if g:
                facets["genres"][g] = facets["genres"].get(g, 0) + 1
        if c["year"]:
            decade_key = str(c["year"] // 10 * 10)
            facets["decades"][decade_key] = facets["decades"].get(decade_key, 0) + 1
        if (c["players"] or 1) > 1:
            facets["players"]["2"] = facets["players"].get("2", 0) + 1
    facets["hacks"] = sum(1 for c in everything if c["hack"])
    facets["systems"] = {
        k: {"count": v, "name": SYSTEMS.get(k, {}).get("name", "")} for k, v in facets["systems"].items()
    }
    return {
        "items": found[offset : offset + limit],
        "total": len(found),
        "next_offset": offset + limit if offset + limit < len(found) else None,
        "facets": facets,
    }


@router.get("/shelves")
def shelves(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Rows for the room's front page: yours first, then what's new, together, hacks, by console."""
    allowed(actor)
    everything = cards(db, actor)
    by_title = sorted(everything, key=SORTS["title"][0])

    def by(items, key=None):
        return sorted(items, key=key, reverse=True) if key else items

    systems = {}
    for c in by_title:
        systems.setdefault(c["system"] or "", []).append(c)
    rows = [
        ("continue", by([c for c in everything if c["last_played"]], SORTS["played"][0])),
        ("favourites", [c for c in by_title if c["favourite"]]),
        ("recent", by(everything, SORTS["added"][0])),
        ("together", [c for c in by_title if (c["players"] or 1) > 1]),
        ("hacks", [c for c in by_title if c["hack"]]),
    ] + [
        ("system:" + key, items) for key, items in sorted(systems.items(), key=lambda kv: -len(kv[1])) if key
    ]
    return {
        "total": len(everything),
        # 16 per row; `count` says how many in all (the page offers "See all" only when there are more)
        "rows": [{"id": key, "items": items[:16], "count": len(items)} for key, items in rows if items],
        "systems": {k: {"name": s["name"], "here": bool(s["browser"])} for k, s in SYSTEMS.items()},
        "unsorted": sum(1 for c in everything if not c["system"]),
    }


def saves_of(user_id, game_id):
    folder = saves(user_id, game_id)
    sram = folder / "save.srm"
    states = sorted((folder / "states").glob("*.state"), reverse=True) if folder.is_dir() else []
    return {
        "sram": {"at": sram.stat().st_mtime, "size": sram.stat().st_size} if sram.is_file() else None,
        "states": [
            {
                "name": s.stem,
                "at": s.stat().st_mtime,
                "surface": s.stem.rsplit("-", 1)[-1],
                "shot": f"/api/v1/games/{game_id}/states/{s.stem}/shot"
                if s.with_suffix(".shot").is_file()
                else None,
            }
            for s in states
        ],
    }


# --- Adding games ------------------------------------------------------------------------------


class Import(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=36, max_length=36)
    version: int = Field(ge=1)
    system: str | None = Field(default=None, max_length=20)


def safe_name(title, identity, ext):
    stem = re.sub(r"[^\w .()\[\]!+,'&-]", "_", title, flags=re.UNICODE)[:120].strip(". ") or "Game"
    return f"{stem}-{identity[:8]}{ext}"


def twin_of(db, crcs, before=None):
    """A game already in the house with one of these fingerprints; for identify(`before`), a
    visible one added before that row."""
    if not crcs:
        return None
    return next(
        (
            r
            for r in games(db, visible=before is not None)
            if set(r.data.get("crcs") or []) & set(crcs)
            and (before is None or (r.id != before.id and r.created_at <= before.created_at))
        ),
        None,
    )


def new_game(db, actor, identity, path, name, source, system, **extra):
    row = Record(
        id=identity,
        kind="game.rom",
        owner_id=actor.id,
        visibility="house",
        data={
            "state": "ready", "source": source, "_path": str(path), "file": name, "system": system,
            "title": catalog.clean(name), "size": path.stat().st_size, **extra,
        },
        version=1,
    )  # fmt: skip
    db.add(row)
    emit(db, "games.changed", {"id": identity}, user_id=actor.id)
    return row


@router.post("/import")
def import_game(
    body: Import,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """A finished upload (shared media) becomes a game; the same game twice is refused."""
    from .files import accessible_entry, file_changed, storage_check, upload_lock

    allowed(actor)
    require_permission(actor, "files.shared.write")
    if body.system and body.system not in SYSTEMS:
        raise HTTPException(422, "Unknown console")
    with upload_lock(body.file_id):
        entry = accessible_entry(db, actor, body.file_id, write=True)
        if entry.version != body.version or entry.scope != "media" or entry.is_folder:
            raise HTTPException(409, "The upload changed. Refresh and try again.")
        storage_check()
        blob = Path(settings.data_root) / "blobs" / entry.id
        ext = os.path.splitext(entry.name)[1].lower()
        system = body.system or system_for(entry.name) or (zip_system(blob) if ext == ".zip" else None)
        if ext not in BY_EXT and ext not in AMBIGUOUS | DISC_ENTRY:
            raise HTTPException(422, {"code": "GAME_FILE_UNSUPPORTED", "message": "This isn't a game file."})
        crcs, _, _ = catalog.fingerprint(blob, system or "")
        twin = twin_of(db, crcs)
        identity = str(uuid5(NAMESPACE_URL, "houseos:game-upload:" + entry.id))
        folder = library() / (system or "_unsorted")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe_name(catalog.clean(entry.name), identity, ext)
        if not twin:
            os.rename(blob, target)
        else:
            blob.unlink(missing_ok=True)  # already in the house: the copy isn't kept
        entry.deleted_at = entry.storage_removed_at = utcnow()
        entry.version += 1
        file_changed(db, entry)
        if twin:
            db.commit()
            raise HTTPException(
                409,
                {"code": "GAME_DUPLICATE", "message": "Already in the house.", "id": twin.id,
                 "title": twin.data.get("title")},
            )  # fmt: skip
        row = new_game(db, actor, identity, target, entry.name, "upload", system, crcs=crcs)
        log(db, "added", row.data["title"], actor.id)
        db.commit()
    background(identify, row.id)
    return {"id": row.id, "system": system, "title": row.data["title"]}


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=2000)
    system: str | None = Field(default=None, max_length=20)


@router.post("/link")
def add_link(body: Link, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """A link to a game file you're allowed to have (your own backup, homebrew): downloaded as it
    is, then treated like an upload."""
    identity = start_link(db, actor, body.url, body.system)
    background(download, identity)
    return {"id": identity, "state": "downloading"}


def start_link(db, actor, url, system=None):
    """The download's row, before the file comes (the caller runs background(download, identity))."""
    allowed(actor)
    require_permission(actor, "files.shared.write")
    if not re.match(r"https://[^\s/@]+/\S*$", url):
        raise HTTPException(422, {"code": "GAME_LINK_INVALID", "message": "Paste a full https:// link."})
    identity = str(uuid4())
    db.add(
        Record(
            id=identity, kind="game.rom", owner_id=actor.id, visibility="house",
            data={"state": "downloading", "source": "link", "title": link_name(url),
                  "system": system if system in SYSTEMS else None, "_url": url},
            version=1,
        )
    )  # fmt: skip
    emit(db, "games.changed", {"id": identity}, user_id=actor.id)
    log(db, "downloading", link_name(url), actor.id)
    db.commit()
    return identity


def link_name(url):
    """What a pasted link is called until it's identified: its file's name, else its site."""
    path = urlsplit(url).path
    return (unquote(path.rsplit("/", 1)[-1]) or urlsplit(url).hostname or "Game")[:200]


def log(db, status, title, user_id=None, **values):
    """A line in the house's activity log (Control Room → Logs, category games)."""
    emit(db, "games.activity", {"status": status, "title": title or "a game",
                                **{k: v for k, v in values.items() if v is not None}}, user_id=user_id)  # fmt: skip


# A link's failure in words about the link (the fetcher's codes are shared with music and video).
LINK_ERRORS = {
    "SOURCE_UNAVAILABLE": "GAME_LINK_UNAVAILABLE",
    "UNSAFE_SOURCE": "GAME_LINK_UNSAFE",
    "SOURCE_RESPONSE_TOO_LARGE": "GAME_LINK_TOO_BIG",
    "SOURCE_TIMEOUT": "GAME_LINK_TIMEOUT",
}


def progress(identity):
    """How far a link's download is: bytes so far and, when the site said, the total."""
    incoming = CACHE / "incoming" / identity
    try:
        total = json.loads(incoming.with_name(identity + ".json").read_text()).get("total") or None
    except (OSError, ValueError):
        total = None
    try:
        done = incoming.stat().st_size
    except OSError:
        done = 0
    return {"bytes": done, "total": total}


STALLED = 180  # seconds without a byte: the fetcher (or the API waiting on it) restarted
FINISHING = 3600  # a claim older than this was left by a restart mid-copy


def recover(db):
    """Maintenance: a link whose waiter went away with an API restart is finished from the
    fetcher's note, or marked interrupted once its file stops growing."""
    for row in games(db, visible=False, state="downloading"):
        if row.data.get("source") != "link":
            continue
        incoming = CACHE / "incoming" / row.id
        try:
            note = json.loads(incoming.with_name(row.id + ".json").read_text())
        except (OSError, ValueError):
            note = {}
        if note.get("status") in {"completed", "failed"}:
            finish(row.id, note)
            continue
        try:
            last = incoming.stat().st_mtime
        except OSError:
            last = row.updated_at.replace(tzinfo=timezone.utc).timestamp() if row.updated_at else 0
        if time.time() - last > STALLED:
            finish(row.id, {"status": "failed", "code": "GAME_LINK_INTERRUPTED"})


def background(job, *args):
    """A job on its own thread, not a request's: a link's download waits up to 6 h."""

    def run():
        try:
            job(*args)
        except Exception as error:
            print("games_job_failed", job.__name__, failure_site(error), flush=True)

    threading.Thread(target=run, daemon=True).start()


def download(identity):
    with SessionLocal() as db:
        row = db.get(Record, identity)
        url = row.data.get("_url") if row else None
    result = fetch("games_link", item_id=identity, source_url=url, timeout=6 * 3600) if url else {}
    finish(identity, result)


def finish(identity, result):
    """A link's download ended (the fetcher's answer or its note): the game joins the library, or
    the row says why not. Once: the CRC and the copy run unlocked, then the row is locked and must
    still be downloading, else the copy goes."""
    incoming = CACHE / "incoming" / identity
    note = incoming.with_name(identity + ".json")
    with SessionLocal() as db:
        row = db.get(Record, identity, with_for_update=True)
        if not row or row.deleted_at or row.data.get("state") != "downloading":
            if not row or row.deleted_at:
                incoming.unlink(missing_ok=True)
                note.unlink(missing_ok=True)
            return
        claim = row.data.get("_finishing") or {}
        if time.time() - claim.get("at", 0) < FINISHING:
            return  # the API or maintenance is already finishing it
        data = {k: v for k, v in row.data.items() if k not in {"_url", "_finishing"}}
        mine = {"token": uuid4().hex, "at": time.time()}
        row.data = {**row.data, "_finishing": mine}
        db.commit()  # claimed: no transaction open through a disc's CRC and copy
        part = target = None
        try:
            if result.get("status") != "completed" or not incoming.is_file():
                raise ValueError(result.get("code") or "SOURCE_UNAVAILABLE")
            name = os.path.basename(result.get("name") or "game")
            ext = os.path.splitext(name)[1].lower()
            system = (
                data.get("system") or system_for(name) or (zip_system(incoming) if ext == ".zip" else None)
            )
            if ext not in BY_EXT and ext not in AMBIGUOUS | DISC_ENTRY:
                raise ValueError("GAME_FILE_UNSUPPORTED")
            if shutil.disk_usage(settings.data_root).free < incoming.stat().st_size + 10 * 1024**3:
                raise ValueError("GAME_NO_SPACE")
            crcs, _, _ = catalog.fingerprint(incoming, system or "")
            twin = twin_of(db, crcs)
            db.rollback()
            if twin:
                data.update(state="failed", error="GAME_DUPLICATE", twin=twin.id)
            else:
                folder = library() / (system or "_unsorted")
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / safe_name(catalog.clean(name), identity, ext)
                part = folder / f".{uuid4()}.part"  # its own name: a second finish can't touch it
                shutil.copyfile(incoming, part)  # another disk: copy, then let go of the download
                data.update(
                    state="ready", _path=str(target), file=name, system=system, crcs=crcs,
                    title=catalog.clean(name), size=part.stat().st_size,
                )  # fmt: skip
        except ValueError as error:
            data.update(state="failed", error=LINK_ERRORS.get(str(error), str(error)))
        except Exception as error:  # the disk filled, the download went, or it isn't a real archive
            if part:
                part.unlink(missing_ok=True)
            no_space = isinstance(error, OSError) and error.errno in {errno.ENOSPC, errno.EDQUOT}
            data.update(state="failed", error="GAME_NO_SPACE" if no_space else "GAME_LINK_UNAVAILABLE")
        row = db.get(Record, identity, with_for_update=True, populate_existing=True)
        if (
            not row
            or row.deleted_at
            or row.data.get("state") != "downloading"
            or row.data.get("_finishing", {}).get("token") != mine["token"]
        ):
            if part:
                part.unlink(missing_ok=True)
            if not row or row.deleted_at:
                incoming.unlink(missing_ok=True)
                note.unlink(missing_ok=True)
            return
        if data["state"] == "ready":
            os.replace(part, target)
        row.data = data
        row.version += 1
        emit(db, "games.changed", {"id": identity})
        log(db, data["state"], data.get("title"), row.owner_id, code=data.get("error"))
        db.commit()
    incoming.unlink(missing_ok=True)
    note.unlink(missing_ok=True)
    if data["state"] == "ready":
        identify(identity)


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str | None = Field(default=None, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=200)


@router.patch("/{game_id}")
def change(
    game_id: str,
    body: Change,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """Fix a game's console (then it's looked up again) or its title."""
    allowed(actor)
    row = game_row(db, game_id)
    if actor.role != "admin" and row.owner_id != actor.id:
        raise HTTPException(403, "Only who added it or an admin can change it")
    data = dict(row.data)
    if body.system:
        if body.system not in SYSTEMS:
            raise HTTPException(422, "Unknown console")
        data.update(system=body.system, identified=False)
    if body.title:
        data.update(title=body.title.strip(), title_fixed=True)
    row.data = data
    row.version += 1
    emit(db, "games.changed", {"id": row.id}, user_id=actor.id)
    db.commit()
    if body.system:
        background(identify, row.id)
    return {"id": row.id, "version": row.version}


@router.delete("/{game_id}")
def remove(
    game_id: str,
    version: Annotated[int, Query(ge=1)],
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """Delete an uploaded or linked game (its file too); a folder's game is only hidden, since
    the folder isn't HouseOS's to change. Everyone's saves stay, in case it comes back."""
    allowed(actor)
    row = game_row(db, game_id)
    folder = row.data.get("source") == "folder"
    if actor.role != "admin" and (folder or row.owner_id != actor.id):
        raise HTTPException(403, "Only who added it or an admin can remove it")
    if row.version != version:
        raise HTTPException(409, "This game changed. Refresh and try again.")
    if folder:
        row.data = {**row.data, "hidden": True}
    else:
        path = Path(row.data.get("_path") or "")
        if path.is_relative_to(library()) and path.is_file() and not path.is_symlink():
            path.unlink()
        row.deleted_at = utcnow()
    row.version += 1
    emit(db, "games.changed", {"id": row.id}, user_id=actor.id)
    log(db, "hidden" if folder else "removed", row.data.get("title"), actor.id)
    db.commit()
    return {"removed": row.id, "hidden": folder}


class Patch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=36, max_length=36)
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)


@router.post("/{game_id}/patch")
def add_patch(
    game_id: str,
    body: Patch,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """A romhack: an uploaded .ips/.bps patch applied to this game, saved as a new game."""
    import zipfile

    from .files import accessible_entry, file_changed, storage_check, upload_lock
    from .games_patch import apply

    allowed(actor)
    require_permission(actor, "files.shared.write")
    base = game_row(db, game_id)
    source_path = game_path(db, base)
    with upload_lock(body.file_id):
        entry = accessible_entry(db, actor, body.file_id, write=True)
        if entry.version != body.version or entry.scope != "media" or entry.size > 32 * 1024**2:
            raise HTTPException(409, "The upload changed. Refresh and try again.")
        storage_check()
        blob = Path(settings.data_root) / "blobs" / entry.id
        patch = blob.read_bytes()
        if source_path.stat().st_size > MAX_PATCHED:
            raise HTTPException(
                422, {"code": "GAME_PATCH_TOO_BIG", "message": "Patches work on cartridge games."}
            )
        if source_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(source_path) as archive:
                member = max(archive.infolist(), key=lambda m: m.file_size)
                if member.file_size > MAX_PATCHED:
                    raise HTTPException(
                        422, {"code": "GAME_PATCH_TOO_BIG", "message": "Patches work on cartridge games."}
                    )
                source, ext = archive.read(member), os.path.splitext(member.filename)[1].lower()
        else:
            source, ext = source_path.read_bytes(), source_path.suffix.lower()
        try:
            patched = apply(source, patch, limit=MAX_PATCHED)
        except (ValueError, IndexError) as error:
            code = str(error) if str(error).startswith("GAME_PATCH") else "GAME_PATCH_INVALID"
            raise HTTPException(422, {"code": code, "message": code}) from None
        title = (body.title or catalog.clean(entry.name)).strip()
        identity = str(uuid5(NAMESPACE_URL, "houseos:game-patch:" + entry.id))
        folder = library() / base.data["system"]
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe_name(title, identity, ext)
        target.write_bytes(patched)
        blob.unlink(missing_ok=True)
        entry.deleted_at = entry.storage_removed_at = utcnow()
        entry.version += 1
        file_changed(db, entry)
        import zlib

        row = new_game(
            db, actor, identity, target, title + ext, "patch", base.data["system"],
            hack=True, base=base.data.get("title"), base_id=base.id, title_fixed=True,
            crcs=[f"{zlib.crc32(patched):08x}"],
        )  # fmt: skip
        row.data = {**row.data, "title": title}
        db.commit()
    background(identify, row.id)
    return {"id": row.id, "title": title}


# --- Files: the game, its pictures, BIOS, the emulator -----------------------------------------


@router.api_route("/{game_id}/file/{name}", methods=["GET", "HEAD"])
def game_file(
    game_id: str,
    name: str,
    request: Request,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """The game file (named, since some emulators tell consoles apart by the extension); also
    the Download button."""
    from .files import stream_fd

    allowed(actor)
    path = game_path(db, game_row(db, game_id))
    db.close()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    return stream_fd(fd, os.fstat(fd).st_size, path.name, "application/octet-stream", request, inline=False)


@router.get("/art/{key}/{kind}")
def art(key: str, kind: Literal["box", "title", "snap"], actor: Actor = Depends(require_actor)):
    allowed(actor)
    path = CACHE / "art" / f"{key}-{kind}.png"
    if not re.fullmatch(r"[0-9a-f]{8}|[0-9a-f-]{36}", key) or not path.is_file() or not path.stat().st_size:
        raise HTTPException(404, "No picture")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=604800"})


# --- The catalogue: every game known for a console (names, facts, covers; never the games) ------


@lru_cache(maxsize=4)
def known(system, mtime, hacks):
    """One entry per game (its regions grouped), or the known romhacks, sorted by title."""
    order = PREFERRED["en"]
    groups = {}
    for crc, entry in catalog.catalogue(system)["crc"].items():
        if bool(entry.get("hack")) != hacks or not entry.get("name"):
            continue
        title = catalog.clean(entry["name"])
        region = entry.get("region") or catalog.region_of(entry["name"])
        rank = order.index(region) if region in order else 9
        best = groups.get(catalog.fold(title))
        if best is None or rank < best["_rank"]:
            year = str(entry.get("releaseyear") or "")[:4]
            groups[catalog.fold(title)] = {
                "key": crc, "title": title, "name": entry["name"], "region": region, "_rank": rank,
                "year": int(year) if year.isdigit() else None, "genre": entry.get("genre"),
                "players": int(entry["users"]) if str(entry.get("users") or "").isdigit() else None,
                "publisher": entry.get("publisher"), "developer": entry.get("developer"),
                "base": catalog.clean(entry["base"]) if entry.get("base") else None,
                "file": entry.get("file"),
                "art_name": entry.get("base") if hacks else entry["name"], "homepage": entry.get("homepage"),
            }  # fmt: skip
    return sorted(groups.values(), key=lambda g: g["title"].casefold().removeprefix("the "))


PREPARING = set()  # consoles whose lists are downloading now (once per house, in the background)


def prepare(system):
    try:
        catalog.ensure(system, fetch)
    finally:
        PREPARING.discard(system)


@router.get("/catalogue")
def catalogue_list(
    tasks: BackgroundTasks,
    system: Annotated[str, Query(max_length=20)],
    q: Annotated[str, Query(max_length=100)] = "",
    hacks: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """Browse what exists for a console, from the open libretro database: what the house has is
    marked; the rest says to bring your own copy. Romhacks link to their page (the patch)."""
    allowed(actor)
    if system not in SYSTEMS:
        raise HTTPException(404, "Unknown console")
    if not catalog.db_path(system).is_file():
        # The first look at a console: its lists download behind (a minute or two), the page waits.
        if not settings.external_fetch_enabled:
            raise HTTPException(503, {"code": "GAMES_LIST_OFF", "message": "Downloads are off here."})
        if system not in PREPARING:
            PREPARING.add(system)
            tasks.add_task(prepare, system)
        return {"items": [], "total": 0, "next_offset": None, "preparing": True}
    everything = known(system, catalog.db_path(system).stat().st_mtime, hacks)
    words = q.casefold().split()
    found = [
        g for g in everything
        if all(w in " ".join(str(g.get(k) or "") for k in ("title", "publisher", "genre", "base")).casefold() for w in words)
    ]  # fmt: skip
    have = {(r.data.get("system"), catalog.fold(r.data.get("title") or "")): r.id for r in games(db)}
    page = found[offset : offset + 60]
    return {
        "items": [
            {
                **{k: v for k, v in g.items() if not k.startswith("_") and k != "art_name"},
                "id": g["key"],
                "have": have.get((system, catalog.fold(g["title"]))),
                "base_have": have.get((system, catalog.fold(g["base"] or ""))) if g["base"] else None,
                "art": {
                    "box": f"/api/v1/games/catalogue/{system}/{g['key']}/box" + ("?hack=1" if hacks else "")
                },
            }
            for g in page
        ],
        "total": len(found),
        "next_offset": offset + 60 if offset + 60 < len(found) else None,
    }


@router.get("/catalogue/{system}/{key}/{kind}")
def catalogue_art(
    system: str,
    key: str,
    kind: Literal["box", "title", "snap"],
    hack: bool = False,
    actor: Actor = Depends(require_actor),
):
    """A catalogue game's picture, fetched the first time someone scrolls past it."""
    allowed(actor)
    if system not in SYSTEMS or not re.fullmatch(r"[0-9a-f]{8}", key):
        raise HTTPException(404, "No picture")
    path = CACHE / "art" / f"{key}-{kind}.png"
    if not path.exists():
        entry = next(
            (g for g in known(system, catalog.db_path(system).stat().st_mtime, hack) if g["key"] == key), None
        )
        if entry and entry["art_name"]:
            fetch("games_art", system=system, key=key, kind=kind, name=entry["art_name"], timeout=20)
    if not path.is_file() or not path.stat().st_size:
        raise HTTPException(404, "No picture")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=604800"})


@router.get("/bios")
def bios_list(actor: Actor = Depends(require_actor)):
    allowed(actor)
    present = bios_present()
    return {
        "items": [
            {"system": key, "name": s["name"], "needed": bool(s.get("needs_bios")),
             "files": [{"name": n, "present": n in present} for n in s["bios"]]}
            for key, s in SYSTEMS.items()
            if s.get("bios")
        ]
    }  # fmt: skip


def bios_name(name):
    names = {n for s in SYSTEMS.values() for n in s.get("bios", [])}
    if name not in names:
        raise HTTPException(404, "Not a BIOS file HouseOS knows")
    return bios_dir() / name


@router.get("/bios/{name:path}")
def bios_file(name: str, actor: Actor = Depends(require_actor)):
    allowed(actor)
    path = bios_name(name)
    if not path.is_file():
        raise HTTPException(404, "Not here yet")
    return FileResponse(path, media_type="application/octet-stream")


@router.put("/bios/{name:path}")
async def bios_upload(name: str, request: Request, actor: Actor = Depends(require_actor)):
    """An admin brings a console's BIOS (a file from their own console; never downloaded)."""
    from .files import storage_check

    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    path = bios_name(name)
    body = await request.body()
    if not 0 < len(body) <= 64 * 1024**2:
        raise HTTPException(413, "That file is too big for a BIOS")
    storage_check()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".part").write_bytes(body)
    os.replace(path.with_suffix(".part"), path)
    return {"name": name, "present": True}


@files.get("/emulator/{version}/{path:path}", include_in_schema=False)
def emulator(version: str, path: str, actor: Actor = Depends(require_actor)):
    """EmulatorJS, one file at a time: downloaded the first time a game needs it, then kept."""
    allowed(actor)
    if version != EMULATORJS or not EJS_FILE.fullmatch(path):
        raise HTTPException(404, "Not found")
    target = CACHE / "emulatorjs" / EMULATORJS / path
    if not target.is_file():
        result = fetch("games_ejs", path=path, timeout=180)
        if result.get("status") != "completed" or not target.is_file():
            raise HTTPException(404 if result.get("code") == "SOURCE_UNAVAILABLE" else 503, "Not available")
    types = {
        ".js": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".wasm": "application/wasm",
    }
    return FileResponse(
        target,
        media_type=types.get(target.suffix, "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- Your saves --------------------------------------------------------------------------------


def own_game(db, actor, game_id):
    allowed(actor)
    game_row(db, game_id)
    from .files import storage_check

    storage_check()
    return saves(actor.id, game_id)


@router.get("/{game_id}/save")
def get_save(game_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Your in-game save (the game's own memory card), the same on every screen."""
    path = own_game(db, actor, game_id) / "save.srm"
    if not path.is_file():
        return Response(status_code=204)
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@router.put("/{game_id}/save")
async def put_save(
    game_id: str, request: Request, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    folder = own_game(db, actor, game_id)
    db.close()
    body = await request.body()
    if not 0 < len(body) <= MAX_SAVE:
        raise HTTPException(413, "Not a save")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "save.part").write_bytes(body)
    if (folder / "save.srm").exists():  # one step back, if a stale screen ever writes over it
        os.replace(folder / "save.srm", folder / "save.srm.1")
    os.replace(folder / "save.part", folder / "save.srm")
    return {"at": time.time(), "size": len(body)}


@router.get("/{game_id}/states")
def list_states(game_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    own_game(db, actor, game_id)
    return saves_of(actor.id, game_id)


def state_path(folder, name):
    if not re.fullmatch(r"\d{10,14}-(browser|tv)", name):
        raise HTTPException(404, "No such save")
    return folder / "states" / (name + ".state")


@router.post("/{game_id}/states")
async def post_state(
    game_id: str,
    request: Request,
    surface: Literal["browser", "tv"] = "browser",
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """A snapshot of the game this very moment (it only loads where it was made: browser or TV)."""
    folder = own_game(db, actor, game_id)
    db.close()
    body = await request.body()
    if not 0 < len(body) <= MAX_STATE:
        raise HTTPException(413, "Not a save state")
    name = f"{int(time.time() * 1000)}-{surface}"
    path = state_path(folder, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    for old in sorted(path.parent.glob(f"*-{surface}.state"), reverse=True)[KEEP_STATES:]:
        old.unlink(missing_ok=True)
        old.with_suffix(".shot").unlink(missing_ok=True)
    return {"name": name}


@router.put("/{game_id}/states/{name}/shot")
async def put_shot(
    game_id: str,
    name: str,
    request: Request,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    path = state_path(own_game(db, actor, game_id), name)
    db.close()
    body = await request.body()
    if not path.is_file() or not 0 < len(body) <= 4 * 1024**2:
        raise HTTPException(404, "No such save")
    path.with_suffix(".shot").write_bytes(body)
    return {"name": name}


@router.get("/{game_id}/states/{name}")
def get_state(game_id: str, name: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    path = state_path(own_game(db, actor, game_id), name)
    if not path.is_file():
        raise HTTPException(404, "No such save")
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@router.get("/{game_id}/states/{name}/shot")
def get_shot(game_id: str, name: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    path = state_path(own_game(db, actor, game_id), name).with_suffix(".shot")
    if not path.is_file():
        raise HTTPException(404, "No picture")
    head = path.read_bytes()[:4]
    kind = (
        "image/png"
        if head.startswith(b"\x89PNG")
        else "image/jpeg"
        if head.startswith(b"\xff\xd8")
        else "image/webp"
    )
    return FileResponse(path, media_type=kind, headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/{game_id}/states/{name}")
def delete_state(
    game_id: str, name: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    path = state_path(own_game(db, actor, game_id), name)
    path.unlink(missing_ok=True)
    path.with_suffix(".shot").unlink(missing_ok=True)
    return {"removed": name}


class Played(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seconds: int = Field(ge=0, le=3600)
    started: bool = False


@router.post("/{game_id}/played")
def played(game_id: str, body: Played, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """The player reports time played (every minute and on leaving), for Continue and Most played."""
    allowed(actor)
    game_row(db, game_id)
    row = play_row(db, actor, game_id)
    row.data = {
        **row.data,
        "plays": (row.data.get("plays") or 0) + (1 if body.started else 0),
        "seconds": (row.data.get("seconds") or 0) + body.seconds,
        "last_played": time.time(),
    }
    db.commit()
    return {"ok": True}


class Favourite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: bool


@router.put("/{game_id}/favourite")
def favourite(
    game_id: str, body: Favourite, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    allowed(actor)
    game_row(db, game_id)
    row = play_row(db, actor, game_id)
    row.data = {**row.data, "favourite": body.on}
    emit(db, "games.changed", {"id": game_id}, user_id=actor.id)
    db.commit()
    return {"favourite": body.on}


# --- Games folders (admin) ---------------------------------------------------------------------


class Folder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=2, max_length=500)


def admin(actor):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")


@router.get("/setup/folders")
def folders(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    admin(actor)
    rows = db.scalars(select(Record).where(Record.kind == "games.folder", Record.deleted_at.is_(None)))
    return {
        "items": [
            {"id": r.id, "path": r.data["path"], "count": r.data.get("count"), "skipped": r.data.get("skipped"),
             "scanned_at": r.data.get("scanned_at"), "scanning": bool(r.data.get("scan_requested"))}
            for r in rows
        ],
        "import_root": str(settings.import_root),
        "hidden": sum(1 for r in games(db, visible=False) if r.data.get("hidden")),
    }  # fmt: skip


@router.post("/setup/folders")
def add_folder(body: Folder, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Point the house at your games folder: read in place, never copied or changed."""
    from .files import readonly_fd

    admin(actor)
    path = os.path.normpath(body.path.strip())
    with readonly_fd(path):
        pass
    identity = str(uuid5(NAMESPACE_URL, "houseos:games-folder:" + path))
    row = db.get(Record, identity)
    if row and not row.deleted_at:
        raise HTTPException(409, "This folder is already a games folder")
    if row:
        row.deleted_at, row.data = None, {"path": path, "scan_requested": True}
    else:
        db.add(
            Record(id=identity, kind="games.folder", owner_id=actor.id, visibility="house",
                   data={"path": path, "scan_requested": True}, version=1)
        )  # fmt: skip
    emit(db, "games.changed", {"folder": identity}, user_id=actor.id)
    db.commit()
    return {"id": identity, "scanning": True}


@router.post("/setup/unhide")
def unhide(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Bring back the folder games someone hid."""
    admin(actor)
    for row in games(db, visible=False):
        if row.data.get("hidden"):
            row.data = {**row.data, "hidden": False}
    emit(db, "games.changed", {}, user_id=actor.id)
    db.commit()
    return {"ok": True}


@router.post("/setup/folders/{folder_id}/scan")
def rescan(folder_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    admin(actor)
    row = db.get(Record, folder_id)
    if not row or row.kind != "games.folder" or row.deleted_at:
        raise HTTPException(404, "No such folder")
    row.data = {**row.data, "scan_requested": True}
    db.commit()
    return {"scanning": True}


@router.delete("/setup/folders/{folder_id}")
def remove_folder(folder_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Forget a games folder: its games leave the library; the files stay where they are."""
    admin(actor)
    row = db.get(Record, folder_id)
    if not row or row.kind != "games.folder" or row.deleted_at:
        raise HTTPException(404, "No such folder")
    row.deleted_at = utcnow()
    for game_row_ in games(db, visible=False):
        if game_row_.data.get("folder_id") == folder_id:
            game_row_.deleted_at = utcnow()
    emit(db, "games.changed", {"folder": folder_id}, user_id=actor.id)
    db.commit()
    return {"removed": folder_id}


from . import games_tv  # noqa: E402,F401  (its routes join this router, before /{game_id})


@router.get("/{game_id}")
def game(game_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """One game: its card, every version, your saves and how to play it."""
    allowed(actor)
    row = game_row(db, game_id)
    group = [
        r
        for r in games(db)
        if r.data.get("system") == row.data.get("system")
        and catalog.fold(r.data.get("title") or r.id) == catalog.fold(row.data.get("title") or row.id)
    ] or [row]
    everything = {c["id"]: c for c in cards(db, actor)}
    head = next((everything[r.id] for r in group if r.id in everything), None) or {}
    d = row.data
    system = SYSTEMS.get(d.get("system") or "", {})
    present = bios_present()
    bios = next((name for name in system.get("bios", []) if name in present), None)
    try:
        name = game_path(db, row).name
    except HTTPException:
        name = None
    return {
        **head,
        "id": row.id,
        "version": row.version,
        "file": d.get("file"),
        "size": d.get("size"),
        "source": d.get("source"),
        "tags": d.get("tags") or [],
        "homepage": d.get("homepage"),
        "missing": name is None and d.get("state", "ready") == "ready",
        "error": d.get("error"),
        "versions": [
            {
                "id": r.id,
                "region": r.data.get("region"),
                "tags": r.data.get("tags") or [],
                "hack": bool(r.data.get("hack")),
                "file": r.data.get("file"),
                "size": r.data.get("size"),
            }
            for r in group
        ],
        "saves": saves_of(actor.id, row.id),
        "can_change": actor.role == "admin" or (row.owner_id == actor.id and d.get("source") != "folder"),
        "player": {
            "core": system.get("browser"),
            "file": f"/api/v1/games/{row.id}/file/{name}" if name else None,
            "bios": f"/api/v1/games/bios/{bios}" if bios else None,
        },
        "bios_names": system.get("bios", []),
    }
