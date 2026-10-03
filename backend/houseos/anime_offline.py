"""Read-only fallback when Jikan is down. Attribution in docs/THIRD-PARTY.md."""

import json
from pathlib import Path
import re
import time
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit

from .atomic import write_json
from .cinema_adapters import public_fetch
from .config import settings
from .playback import MediaError

_URL = "https://github.com/cedya77/anime-offline-database/releases/download/latest/anime-offline-database-minified.json"
_GENRE_IDS = {
    1: "Action",
    2: "Adventure",
    4: "Comedy",
    8: "Drama",
    10: "Fantasy",
    14: "Horror",
    7: "Mystery",
    22: "Romance",
    24: "Sci-Fi",
    36: "Slice of Life",
    30: "Sports",
    37: "Supernatural",
    41: "Suspense",
}
_GENRES = list(_GENRE_IDS.values())
# The dataset's thousands of tags, narrowed to themes people browse by: key → (label, its tags).
TAGS = {
    "isekai": ("Isekai", {"isekai"}),
    "mecha": ("Mecha", {"mecha"}),
    "sports": ("Sports", {"sports"}),
    "psychological": ("Psychological", {"psychological"}),
    "iyashikei": ("Iyashikei (comfy)", {"iyashikei"}),
    "zombies": ("Zombies", {"zombie", "zombies"}),
    "time-travel": ("Time travel", {"time travel", "time manipulation"}),
    "vampires": ("Vampires", {"vampire", "vampires"}),
    "magical-girl": ("Magical girls", {"magical girl"}),
    "idols": ("Idols", {"idol"}),
    "food": ("Food and cooking", {"cooking", "food", "gourmet"}),
    "romcom": ("Romantic comedy", {"romantic comedy"}),
    "detective": ("Detectives", {"detective"}),
    "war": ("War and military", {"military", "war"}),
    "space": ("Space", {"space"}),
    "cyberpunk": ("Cyberpunk", {"cyberpunk"}),
    "post-apocalyptic": ("Post-apocalyptic", {"post-apocalyptic", "dystopia"}),
    "samurai": ("Samurai and ninjas", {"samurai", "ninja"}),
    "martial-arts": ("Martial arts", {"martial arts"}),
    "super-powers": ("Super powers", {"super power", "superpowers"}),
    "demons": ("Demons", {"demons", "demon"}),
    "historical": ("Historical", {"historical"}),
    "survival": ("Survival games", {"survival", "battle royale", "death game"}),
    "reincarnation": ("Reincarnation", {"reincarnation"}),
    "virtual-worlds": ("Games and virtual worlds", {"virtual world", "video games"}),
    "music": ("Music", {"music", "band"}),
    "dragons": ("Dragons", {"dragons"}),
    "pirates": ("Pirates", {"pirates"}),
    "crime": ("Crime and yakuza", {"crime", "yakuza"}),
    "school": ("School life", {"school life", "high school"}),
}
_CORPORATE = re.compile(r"(,? (co\.,? ?ltd\.?|inc\.?|ltd\.?|llc|corporation|corp\.?)|\.)$")
# Studio names as people write them (the dataset is lower case, with company suffixes).
STUDIO_NAMES = {
    "studio ghibli": "Studio Ghibli",
    "kyoto animation": "Kyoto Animation",
    "ufotable": "ufotable",
    "mappa": "MAPPA",
    "bones": "Bones",
    "madhouse": "Madhouse",
    "wit studio": "Wit Studio",
    "production i.g": "Production I.G",
    "trigger": "Trigger",
    "sunrise": "Sunrise",
    "toei animation": "Toei Animation",
    "cloverworks": "CloverWorks",
    "a-1 pictures": "A-1 Pictures",
    "shaft": "Shaft",
    "david production": "David Production",
    "science saru": "Science SARU",
    "comix wave films": "CoMix Wave Films",
    "j.c.staff": "J.C.Staff",
    "j.c. staff": "J.C.Staff",
    "pierrot": "Pierrot",
    "studio deen": "Studio Deen",
    "tms entertainment": "TMS Entertainment",
    "olm": "OLM",
    "p.a. works": "P.A. Works",
    "lerche": "Lerche",
    "white fox": "White Fox",
    "kinema citrus": "Kinema Citrus",
    "studio chizu": "Studio Chizu",
    "shin-ei animation": "Shin-Ei Animation",
    "silver link": "Silver Link",
}


def studio(name):
    """ "toei animation co., ltd." → "Toei Animation"."""
    plain = str(name).strip().casefold()
    while (shorter := _CORPORATE.sub("", plain).strip()) != plain:
        plain = shorter
    return STUDIO_NAMES.get(plain) or plain.title()[:80]


def cached_entries():
    """The catalogue as last downloaded, whatever its age. Requests never download it (64 MB):
    the daily maintenance step does, through `refresh`."""
    path = settings.runtime_root / "cinema" / "catalog-cache" / "anime-catalog.json"
    try:
        return _read(str(path), path.stat().st_mtime)
    except (OSError, ValueError):
        raise MediaError(
            "PROVIDER_UNAVAILABLE", "The anime catalogue is not downloaded yet.", "resolve", True
        ) from None


@lru_cache(maxsize=1)
def _read(path, stamp):
    cached = json.loads(Path(path).read_text())
    if not isinstance(cached, dict) or not isinstance(cached.get("items"), list):
        raise ValueError("not a catalogue")
    return cached["items"]


_retry_at = 0.0


def refresh(db=None):
    """Maintenance step: download the catalogue when a day old, at most one try an hour.
    Nothing parsed is kept: this process only refreshes the file that requests read."""
    global _retry_at
    path = settings.runtime_root / "cinema" / "catalog-cache" / "anime-catalog.json"
    try:
        if time.time() - path.stat().st_mtime < 86400:
            return
    except OSError:
        pass
    if time.monotonic() < _retry_at:
        return
    _retry_at = time.monotonic() + 3600  # a failed or offline download is not retried every minute
    _entries()


def _entries():
    path = settings.runtime_root / "cinema" / "catalog-cache" / "anime-catalog.json"
    cached = None
    try:
        if path.stat().st_size <= 40_000_000:
            cached = json.loads(path.read_text())
            if not isinstance(cached, dict) or not isinstance(cached.get("items"), list):
                cached = None
            elif cached.get("version") != 2:  # older cache without tags or studios: refresh
                cached["stale"] = True
            elif time.time() - path.stat().st_mtime < 86400 and not cached.get("stale"):
                return cached["items"]
    except (OSError, ValueError):
        pass
    try:
        content, _ = public_fetch(_URL, limit=64_000_000)
        rows = json.loads(content)["data"]
        if not isinstance(rows, list):
            raise ValueError()
        items = []
        seen = set()
        for row in rows[:60000]:
            matches = [
                re.fullmatch(r"https://myanimelist\.net/anime/([1-9][0-9]*)", str(v))
                for v in row.get("sources", [])
            ]
            ids = {int(m[1]) for m in matches if m}
            tags = [str(t).lower() for t in row.get("tags", [])]
            if len(ids) != 1 or set(tags) & {"hentai", "erotica"}:
                continue
            identity = next(iter(ids))
            if identity in seen:
                continue
            seen.add(identity)
            items.append(
                {
                    "mal_id": identity,
                    "title": str(row.get("title", "Anime"))[:240],
                    "type": "Movie" if row.get("type") == "MOVIE" else "TV",
                    "episodes": row.get("episodes"),
                    "year": row.get("animeSeason", {}).get("year"),
                    "images": {"jpg": {"image_url": row.get("picture")}},
                    "genres": [{"name": g} for g in _GENRES if g.lower() in tags],
                    "synonyms": row.get("synonyms", [])[:25],
                    "_airing": row.get("status") == "ONGOING",
                    "_score": row.get("score", {}).get("arithmeticMean") or 0,
                    "_tags": [key for key, (_, words) in TAGS.items() if words & set(tags)],
                    "_studios": sorted({studio(name) for name in row.get("studios", [])[:6]}),
                    "_season": str((row.get("animeSeason") or {}).get("season") or "")[:10],
                    "_known": len(row.get("sources", [])),  # sites listing it: how well known
                    "_minutes": round((row.get("duration") or {}).get("value", 0) / 60) or None,
                    "_format": str(row.get("type") or "")[:10],
                    # Sequels, prequels, side stories: the same franchise on MyAnimeList.
                    "_related": [
                        int(m[1])
                        for m in (
                            re.fullmatch(r"https://myanimelist\.net/anime/([1-9][0-9]*)", str(v))
                            for v in row.get("relatedAnime", [])
                        )
                        if m
                    ][:20],
                }
            )
        # Do not mislabel combined-provider scores as MAL scores/popularity.
        items.sort(key=lambda row: (-float(row["_score"]), row["title"]))
        write_json(path, {"version": 2, "items": items})
        return items
    except (MediaError, OSError, ValueError, KeyError, TypeError):
        if cached:
            return cached["items"]
        raise MediaError(
            "ANIME_CATALOG_UNAVAILABLE",
            "Anime metadata is temporarily unavailable. Try again shortly.",
            "identify",
            True,
        ) from None


def catalog_response(path):
    parsed = urlsplit(path)
    if parsed.path == "/genres/anime":
        return {
            "data": [{"mal_id": i, "name": g} for i, g in _GENRE_IDS.items()],
            "metadata_source": "anime-offline-database",
        }
    rows = cached_entries()
    identity = re.fullmatch(r"/anime/([1-9][0-9]*)(/episodes)?", parsed.path)
    if identity:
        row = next((r for r in rows if r["mal_id"] == int(identity[1])), None)
        if row is None:
            raise MediaError(
                "METADATA_NOT_FOUND", "This anime is not in the backup catalog yet.", "identify", True
            )
        # No invented episode evidence for unknown/airing totals.
        return {"data": [] if identity[2] else row, "metadata_source": "anime-offline-database"}
    if parsed.path != "/anime":
        raise MediaError("CATALOG_FILTER_INVALID", "Choose an available anime collection.", "identify")
    query = parse_qs(parsed.query)
    needle = query.get("q", [""])[0].casefold()
    if needle:
        rows = [r for r in rows if any(needle in str(t).casefold() for t in [r["title"], *r["synonyms"]])]
    if query.get("status") == ["airing"]:
        rows = [r for r in rows if r["_airing"]]
    if "genres" in query:
        # Preserve Jikan's IDs even when its genre list was cached before an outage.
        genre = _GENRE_IDS.get(int(query["genres"][0])) if query["genres"][0].isdigit() else None
        rows = [r for r in rows if genre in [g["name"] for g in r["genres"]]]
    start = (int(query.get("page", ["1"])[0]) - 1) * 24
    return {
        "data": rows[start : start + 24],
        "pagination": {"has_next_page": len(rows) > start + 24},
        "metadata_source": "anime-offline-database",
    }
