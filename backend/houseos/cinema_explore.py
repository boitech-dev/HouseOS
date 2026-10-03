"""Filters, tags, people and awards over local indexes: films and series from Wikidata
(`film_index.py`, rebuilt weekly in the background), anime from the offline anime database
(`anime_offline.py`, daily). Everything here is a quick in-memory filter; nothing waits on a
remote service, so it keeps working when those are down."""

import threading
import time
from functools import lru_cache
from pathlib import Path

from .config import settings

PAGE = 24
SORTS = {"known", "newest", "oldest", "rated"}


def film_path():
    return settings.runtime_root / "cinema" / "catalog-cache" / "film-index.json"


# A ready index ships with HouseOS (CC0 data), so filters work from the first start; the weekly
# build in maintenance (film_index.py) replaces it with a fresher one on this server.
BUNDLED = Path(__file__).parent / "data" / "film-index.json.gz"


def film_source():
    return film_path() if film_path().exists() else BUNDLED


@lru_cache(maxsize=2)
def _films(source, stamp):
    import gzip
    import json

    from .film_index import GENRES, TAGS

    try:
        opener = gzip.open if str(source).endswith(".gz") else open
        with opener(source, "rt") as stream:
            raw = json.load(stream)
    except (OSError, ValueError):
        return []
    genre_name = {key: label for key, label, _ in GENRES}
    tag_keys = {key for key, _, _ in TAGS}
    return [
        {
            "canonical_id": row["id"],
            "title": row["t"],
            "title_fr": row.get("f") or "",
            "kind": row.get("k", "movie"),
            "year": row.get("y"),
            "genres": [genre_name[g] for g in row.get("g", []) if g in genre_name],
            "tags": [t for t in row.get("s", []) if t in tag_keys],
            "people": row.get("d", []) + row.get("c", []),
            "director": row.get("d", []),
            "cast": row.get("c", []),
            "awards": row.get("a", []),
            "minutes": row.get("r"),
            "score": None,
            "known": row.get("n", 0),
            "poster": f"https://images.metahub.space/poster/medium/{row['id']}/img",
        }
        for row in raw.get("items", [])
        if isinstance(row, dict) and str(row.get("id", "")).startswith("tt") and row.get("t")
    ]


def films():
    source = film_source()
    try:
        return _films(str(source), source.stat().st_mtime)
    except OSError:
        return []


def _anime():
    from .anime_offline import cached_entries

    rows = []
    for row in cached_entries():
        year = row.get("year")
        rows.append(
            {
                "canonical_id": f"mal:{row['mal_id']}",
                "title": row["title"],
                "title_fr": "",
                "kind": "movie" if row.get("type") == "Movie" else "series",
                "year": year if isinstance(year, int) else None,
                "genres": [g["name"] for g in row.get("genres", [])],
                "tags": row.get("_tags", []),
                "people": row.get("_studios", []),
                "studios": row.get("_studios", []),
                "awards": [],
                "minutes": row.get("_minutes"),
                "episodes": row.get("episodes"),
                "score": row.get("_score") or None,
                "known": row.get("_known", 0),
                "airing": row.get("_airing", False),
                "season": row.get("_season", ""),
                "synonyms": row.get("synonyms", []),
                "related": [f"mal:{n}" for n in row.get("_related", [])],
                "poster": ((row.get("images") or {}).get("jpg") or {}).get("image_url") or "",
            }
        )
    return rows


# Watch asks for many rows at once: the first to find an index missing loads it, the others
# wait for that one load instead of each reading 20 MB of JSON (17 loads at once took 9 s).
LOADING = threading.Lock()
_loaded: dict = {}


def stamp(kind):
    """What an index is built from: it is rebuilt only when that file changes."""
    if kind == "anime":
        path = settings.runtime_root / "cinema" / "catalog-cache" / "anime-catalog.json"
    else:
        path = film_source()
    try:
        return str(path), path.stat().st_mtime
    except OSError:
        return str(path), 0


def index(kind):
    key = stamp(kind)
    found = _loaded.get(kind)
    if found and found[0] == key:
        return found[1]
    with LOADING:
        found = _loaded.get(kind)
        if found and found[0] == key:
            return found[1]
        if kind == "anime":
            from .playback import MediaError

            try:
                rows = _anime()
            except MediaError:  # not downloaded yet: empty rows, retried when the file appears
                rows = []
        else:
            rows = [row for row in films() if row["kind"] == kind]
        _loaded[kind] = (key, rows)
        return rows


def warm():
    """Load every index once, in the background, so the first visitor after a start waits less."""
    for kind in ("movie", "series", "anime"):
        index(kind)


def ready(kind):
    return bool(index(kind))


def _has(values, wanted):
    wanted = wanted.casefold()
    return any(wanted in str(value).casefold() for value in values)


def matching(kind, q="", year_from=None, year_to=None, genre="", tag="", person="", award="",
             max_minutes=None, max_episodes=None, airing=None, season=""):  # fmt: skip
    rows = index(kind)
    if q:
        rows = [r for r in rows if _has([r["title"], r["title_fr"], *r.get("synonyms", [])], q)]
    if year_from:
        rows = [r for r in rows if r["year"] and r["year"] >= year_from]
    if year_to:
        rows = [r for r in rows if r["year"] and r["year"] <= year_to]
    # Several genres, themes or people: each one narrows the list (all must match).
    for name in [g.strip().casefold() for g in genre.split(",") if g.strip()][:3]:
        rows = [r for r in rows if name in (g.casefold() for g in r["genres"])]
    for key in [t for t in tag.split(",") if t][:4]:
        rows = [r for r in rows if key in r["tags"]]
    for name in [p.strip() for p in person.split("|") if p.strip()][:4]:
        rows = [r for r in rows if _has(r["people"], name)]
    if award:
        rows = [r for r in rows if award in r["awards"]]
    if max_minutes:
        rows = [r for r in rows if r["minutes"] and r["minutes"] <= max_minutes]
    if max_episodes:
        rows = [r for r in rows if r.get("episodes") and r["episodes"] <= max_episodes]
    if airing is not None:
        rows = [r for r in rows if r.get("airing") == airing]
    if season:
        rows = [r for r in rows if r.get("season") == season]
    return rows


def ordered(rows, sort):
    if sort == "newest":
        return sorted(rows, key=lambda r: (-(r["year"] or 0), -r["known"]))
    if sort == "oldest":
        return sorted(rows, key=lambda r: (r["year"] or 9999, -r["known"]))
    if sort == "rated":
        return sorted(rows, key=lambda r: (-(r["score"] or 0), -r["known"]))
    return sorted(rows, key=lambda r: (-r["known"], -(r["score"] or 0)))


def discover(kind, sort="known", offset=0, **filters):
    rows = ordered(matching(kind, **filters), sort if sort in SORTS else "known")
    page = rows[offset : offset + PAGE]
    return {
        "items": [catalog_item(row) for row in page],
        "total": len(rows),
        "next_offset": offset + PAGE if len(rows) > offset + PAGE else None,
    }


def catalog_item(row):
    """What the catalog tables store for a title (only fields the index knows)."""
    item = {
        "canonical_id": row["canonical_id"],
        "title": row["title"],
        "kind": row["kind"],
        "genres": row["genres"][:15],
        "_poster_url": row["poster"],
    }
    if row["year"]:
        item["year"] = str(row["year"])
    if row.get("director"):
        item["director"] = row["director"][:2]
    if row.get("cast"):
        item["cast"] = row["cast"][:5]
    if row.get("studios"):
        item["studios"] = row["studios"][:3]
    if row.get("score"):
        item["rating"] = f"{row['score']:.1f}"
    if row.get("minutes") and row["kind"] == "movie":
        item["runtime"] = f"{row['minutes']} min"
    return item


def labels():
    from .anime_offline import TAGS as ANIME_TAGS
    from .film_index import AWARDS, TAGS

    return {
        **{key: label for key, (label, _) in ANIME_TAGS.items()},
        **{key: label for key, label, _ in TAGS},
        **{key: label for key, label, _ in AWARDS},
    }


def facets(kind):
    """What can be filtered on right now: only choices that have titles behind them."""
    rows = index(kind)
    return _facets(kind, id(rows), len(rows))  # the index lists are cached: counted once each


@lru_cache(maxsize=6)
def _facets(kind, identity, size):
    from collections import Counter

    rows = index(kind)
    count = lambda key: Counter(value for row in rows for value in row[key])  # noqa: E731
    years = [row["year"] for row in rows if row["year"]]
    names = labels()
    return {
        "ready": bool(rows),
        "genres": [name for name, n in count("genres").most_common() if n >= 5],
        "tags": [
            {"key": key, "label": names.get(key, key)} for key, n in count("tags").most_common() if n >= 15
        ],
        "awards": [
            {"key": key, "label": names.get(key, key)} for key, n in count("awards").most_common() if n >= 5
        ],
        "years": [min(years), max(years)] if years else None,
        "people_label": "Studio" if kind == "anime" else "Director or actor",
    }


@lru_cache(maxsize=8)
def _people(kind, stamp):
    from collections import Counter

    return Counter(person for row in index(kind) for person in row["people"]).most_common()


def people(kind, q, limit=8):
    """Names for the person field, best known first."""
    q = q.casefold().strip()
    if len(q) < 2:
        return []
    stamp = int(time.time() // 3600)
    starts, contains = [], []
    for name, _ in _people(kind, stamp):
        folded = name.casefold()
        if folded.startswith(q) or f" {q}" in folded:
            starts.append(name)
        elif q in folded:
            contains.append(name)
        if len(starts) >= limit:
            break
    return (starts + contains)[:limit]


def find(kind, canonical_id):
    return next((row for row in index(kind) if row["canonical_id"] == canonical_id), None)


def similar(kind, canonical_id, limit=12):
    """ "More like this" from what the indexes know, no model and no network: the same
    director, cast or studio, shared themes and genres, a similar time, and well-known titles
    first among equals. Anime of the same franchise are listed apart (`franchise`)."""
    import math

    base = find(kind, canonical_id)
    if not base:
        return []
    related = set(base.get("related", []))
    mine = {key: set(base.get(key) or []) for key in ("director", "cast", "studios", "tags", "genres")}
    scored = []
    for row in index(kind):
        if row["canonical_id"] == canonical_id or row["canonical_id"] in related:
            continue
        score = (
            4 * len(mine["director"] & set(row.get("director") or []))
            + 1.5 * len(mine["cast"] & set(row.get("cast") or []))
            + 2 * len(mine["studios"] & set(row.get("studios") or []))
            + 3 * len(mine["tags"] & set(row["tags"]))
            + len(mine["genres"] & set(row["genres"]))
        )
        if score < 3:
            continue
        if base["year"] and row["year"] and abs(base["year"] - row["year"]) <= 10:
            score += 1
        scored.append((score + math.log1p(max(0, row["known"])) / 5, row))
    scored.sort(key=lambda pair: -pair[0])
    return [catalog_item(row) for _, row in scored[:limit]]


def franchise(canonical_id, limit=12):
    """The anime's sequels, prequels and side stories that the offline list knows."""
    base = find("anime", canonical_id)
    if not base:
        return []
    wanted = set(base.get("related", []))
    rows = [row for row in index("anime") if row["canonical_id"] in wanted]
    return [catalog_item(row) for row in sorted(rows, key=lambda r: r["year"] or 9999)[:limit]]


def for_you(kind, seen, limit=24):
    """ "Recommended for you": what is most like the last titles watched (most recent first,
    each counting a little less), without what was already seen."""
    scores, rows = {}, {}
    for rank, canonical in enumerate(seen[:5]):
        for position, item in enumerate(similar(kind, canonical, limit=30)):
            if item["canonical_id"] in seen:
                continue
            weight = (1 / (1 + rank)) * (1 / (1 + position / 10))
            scores[item["canonical_id"]] = scores.get(item["canonical_id"], 0) + weight
            rows[item["canonical_id"]] = item
    return [rows[key] for key in sorted(scores, key=lambda key: -scores[key])[:limit]]
