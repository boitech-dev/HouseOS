"""Games: what a game file is. Its fingerprint (CRC32) or its name is looked up in the open
libretro database (No-Intro, Redump, FBNeo, plus genre, year, players, developer, publisher,
series and known romhacks), downloaded once per console. No account, no API key."""

import json
import os
import re
import zipfile
import zlib
from functools import lru_cache
from pathlib import Path

from .atomic import write_json
from .fetcher_games import DATS, DIR
from .games_systems import BY_EXT, DISC_ENTRY, SYSTEMS

TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|(\()|(\))|([^\s()"]+)')
REGIONS = ("World", "USA", "Europe", "France", "Germany", "Spain", "Italy", "Japan", "Korea", "Brazil")
FIELDS = ("region", "genre", "developer", "publisher", "releaseyear", "users", "franchise", "serial")
HACK = re.compile(r"\[(?:h\d*|t[+-]|hack)|\((?:hack|translated)|\bhack\b", re.I)
CRC_LIMIT = 256 * 1024**2  # bigger files (discs) are named, not fingerprinted


def parse_dat(text):
    """Every `game ( … )` block of a clrmamepro file, flat, with its first `rom ( … )` as `rom`."""
    games, current, rom, key, depth = [], None, None, None, 0
    for match in TOKEN.finditer(text):
        quoted, opened, closed, word = match.groups()
        if opened:
            depth += 1
            if depth == 1:
                current = {} if key == "game" else None
            elif depth == 2 and current is not None and key == "rom":
                rom = {}
            key = None
        elif closed:
            if depth == 2 and rom is not None:
                current.setdefault("rom", rom)
                rom = None
            elif depth == 1 and current is not None:
                games.append(current)
                current = None
            depth = max(0, depth - 1)
        elif key is None:
            key = word if word is not None else quoted
        else:
            target = rom if depth == 2 and rom is not None else current
            if target is not None:
                target.setdefault(key, quoted if quoted is not None else word)
            key = None
    return games


def fold(name):
    return re.sub(r"[^0-9a-z]+", "", name.casefold())


def clean(name):
    """'Legend of Zelda, The - A Link to the Past (USA) [!]' → 'The Legend of Zelda - A Link to the Past'."""
    stem, ext = os.path.splitext(name)
    known = ext.lower() in BY_EXT or ext.lower() in DISC_ENTRY or ext.lower() in {".zip", ".7z", ".bin"}
    title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", stem if known else name)
    title = re.sub(r"^(.+?), (The|A|An|Le|La|Les|Die|Der|Das)( - .*)?$", r"\2 \1\3", title.strip())
    return " ".join(title.replace("_", " ").split()) or name


def tags(name):
    return re.findall(r"[\(\[]([^\)\]]+)[\)\]]", name)


def region_of(name):
    for tag in tags(name):
        for region in REGIONS:
            if region in tag:
                return region
    return None


def build(files):
    """{file: text} → {"crc": {crc: facts}, "names": {folded name: crc}} for one console."""
    entries = {}
    for file, text in files.items():
        for game in parse_dat(text):
            crc = str(game.get("rom", {}).get("crc", "")).lower()
            name = game.get("name") or game.get("comment")
            if not re.fullmatch(r"[0-9a-f]{8}", crc) or not name:
                continue
            entry = entries.setdefault(crc, {})
            if file == "metadat/hacks":
                base = game["rom"].get("name", "")
                entry.update(name=name, hack=True, base=os.path.splitext(base)[0])
                entry.setdefault("homepage", game.get("homepage"))
                continue
            if file in {"metadat/no-intro", "metadat/redump", "metadat/fbneo-split"}:
                entry["name"] = name
                entry["file"] = game["rom"].get("name")
            else:
                entry.setdefault("name", name)
            for field in FIELDS:
                if game.get(field):
                    entry.setdefault(field, game[field])
    names = {}
    for crc, entry in entries.items():
        for label in (entry["name"], os.path.splitext(entry.get("file") or "")[0]):
            if label and not entry.get("hack"):
                names.setdefault(fold(label), crc)
    return {"crc": entries, "names": names}


def db_path(system):
    return DIR / "db" / (system + ".json")


def ensure(system, fetch):
    """Download this console's lists once (through the fetcher) and index them."""
    target = db_path(system)
    if target.is_file():
        return True
    raw = DIR / "db" / "raw" / system
    for file in DATS:
        if not (raw / (file.replace("/", "-") + ".dat")).is_file():
            if fetch("games_dat", system=system, file=file).get("status") != "completed":
                return False
    files = {file: (raw / (file.replace("/", "-") + ".dat")).read_text(errors="replace") for file in DATS}
    write_json(target, build(files), 0o660)
    return True


@lru_cache(maxsize=8)
def _load(path, mtime):
    return json.loads(Path(path).read_text())


def catalogue(system):
    path = db_path(system)
    try:
        return _load(str(path), path.stat().st_mtime)
    except (OSError, ValueError):
        return {"crc": {}, "names": {}}


def fingerprint(path, system):
    """(crcs, size, inner name): a zip member's CRC is read from the zip, a cartridge's is
    computed with and without a copier header; a disc (or anything huge) is known by name only."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            known = [m for m in members if os.path.splitext(m.filename)[1].lower() in BY_EXT]
            if not members:
                return [], 0, path.name
            game = max(known or members, key=lambda m: m.file_size)
            return [f"{game.CRC:08x}"], game.file_size, os.path.basename(game.filename)
    size = path.stat().st_size
    spec = SYSTEMS.get(system, {})
    if spec.get("disc") or system == "arcade" or size > CRC_LIMIT:
        return [], size, path.name
    whole = skipped = 0
    skip = 0
    with open(path, "rb") as file:
        head = file.read(16)
        if spec.get("header") == 512 and size % 1024 == 512:
            skip = 512
        elif spec.get("header") == 16 and head.startswith(b"NES\x1a"):
            skip = 16
        file.seek(0)
        seen = 0
        while chunk := file.read(1024 * 1024):
            whole = zlib.crc32(chunk, whole)
            if skip:
                part = chunk[max(0, skip - seen) :]
                skipped = zlib.crc32(part, skipped) if part else skipped
            seen += len(chunk)
    crcs = [f"{skipped:08x}", f"{whole:08x}"] if skip else [f"{whole:08x}"]
    return crcs, size, path.name


def describe(system, crcs, filename):
    """What the house shows for a file: its name, facts and the name its pictures go by."""
    book = catalogue(system)
    crc = next((c for c in crcs if c in book["crc"]), None)
    stem = os.path.splitext(filename)[0]
    if crc is None:  # renamed, a disc, an arcade set, or a hack we don't know: try its name
        crc = book["names"].get(fold(stem))
    entry = book["crc"].get(crc, {}) if crc else {}
    name = entry.get("name") or stem
    hack = bool(entry.get("hack") or HACK.search(filename))
    base = entry.get("base")
    if hack and not base:  # a hack named like its game: borrow the game's pictures and facts
        wanted = region_of(filename)
        candidates = sorted(
            (c for c, e in book["crc"].items() if not e.get("hack") and clean(e["name"]) == clean(stem)),
            key=lambda c: (region_of(book["crc"][c]["name"]) != wanted, book["crc"][c]["name"]),
        )
        base_crc = candidates[0] if candidates else None
        base = book["crc"][base_crc]["name"] if base_crc else None
    facts = dict(entry)
    if hack and base:
        base_entry = book["crc"].get(book["names"].get(fold(base), ""), {})
        for field in ("genre", "developer", "publisher", "releaseyear", "users", "franchise"):
            facts.setdefault(field, base_entry.get(field))
    year = str(facts.get("releaseyear") or "")[:4]
    return {
        "matched": bool(entry),
        "crc": crc or (crcs[0] if crcs else None),
        "name": name,
        "title": clean(name),
        "region": entry.get("region") or region_of(name) or region_of(filename),
        "tags": tags(filename),
        "hack": hack,
        "base": clean(base) if base else None,
        "art_name": base if hack and base else (name if entry else None),
        "genre": facts.get("genre"),
        "developer": facts.get("developer"),
        "publisher": facts.get("publisher"),
        "year": int(year) if year.isdigit() else None,
        "players": int(facts["users"]) if str(facts.get("users") or "").isdigit() else None,
        "franchise": facts.get("franchise"),
        "homepage": entry.get("homepage"),
    }


def is_entry(name, siblings=()):
    """Whether a file is a game to list: not a disc's track (a .bin next to its .cue)."""
    ext = os.path.splitext(name)[1].lower()
    if ext == ".bin":
        stem = os.path.splitext(name)[0]
        return not any(
            s.lower().endswith(".cue") and (s[:-4] == stem or stem.startswith(s[:-4])) for s in siblings
        )
    return ext in BY_EXT or ext in DISC_ENTRY or ext in {".zip", ".7z", ".bin"}
