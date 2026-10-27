"""Anime rankings, as Stremio's Kitsu add-on lists them: most popular, popular this season,
top rated and top films. Kitsu is asked once a day by maintenance and the lists are kept on disk
as MyAnimeList ids; Watch only reads the file, so it never waits on Kitsu (a day's old lists
stay when Kitsu is down)."""

import json
import time
from datetime import date
from functools import lru_cache
from urllib.parse import urlencode

from .atomic import write_json
from .cinema_adapters import public_fetch
from .config import settings
from .playback import MediaError

KITSU = "https://kitsu.io/api/edge/anime"
LISTS = {
    "popular": {"sort": "popularityRank"},
    # This season's shows, started or done (Kitsu's "airing" list is decades-long runners).
    "airing": {"filter[status]": "current,finished", "sort": "popularityRank", "season": True},
    "rated": {"sort": "ratingRank"},
    "movies": {"filter[subtype]": "movie", "sort": "ratingRank"},
}
PAGES = 5  # Kitsu gives 20 a page: the first hundred of each list


def path():
    return settings.runtime_root / "cinema" / "catalog-cache" / "anime-rankings.json"


def mal_ids(answer):
    """The page's anime in Kitsu's order, as MyAnimeList ids (one without a MAL id is left out)."""
    mal = {
        item["id"]: int(item["attributes"]["externalId"])
        for item in answer.get("included", [])
        if item.get("type") == "mappings"
        and (item.get("attributes") or {}).get("externalSite") == "myanimelist/anime"
        and str((item.get("attributes") or {}).get("externalId") or "").isdigit()
    }
    ids = []
    for anime in answer.get("data", []):
        links = ((anime.get("relationships") or {}).get("mappings") or {}).get("data") or []
        found = next((mal[link["id"]] for link in links if link.get("id") in mal), None)
        if found and found not in ids:
            ids.append(found)
    return ids


def season_filter(today=None):
    today = today or date.today()
    name = ("winter", "spring", "summer", "fall")[(today.month - 1) // 3]
    return {"filter[season]": name, "filter[seasonYear]": today.year}


def ranking(params):
    params = {k: v for k, v in params.items() if k != "season"} | (
        season_filter() if params.get("season") else {}
    )
    ids = []
    for page in range(PAGES):
        query = {
            **params,
            "page[limit]": 20,
            "page[offset]": page * 20,
            "include": "mappings",
            "fields[anime]": "mappings",
            "fields[mappings]": "externalSite,externalId",
        }
        content, _ = public_fetch(KITSU + "?" + urlencode(query), limit=2_000_000)
        ids += [n for n in mal_ids(json.loads(content)) if n not in ids]
    return ids


_retry_at = 0.0


def refresh(db=None):
    """Maintenance step: the lists again once a day; a list Kitsu fails keeps its last one."""
    global _retry_at
    try:
        if time.time() - path().stat().st_mtime < 86400:
            return
    except OSError:
        pass
    if time.monotonic() < _retry_at:
        return
    _retry_at = time.monotonic() + 3600
    lists = dict(saved())
    for key, params in LISTS.items():
        try:
            lists[key] = ranking(params)
        except (MediaError, OSError, ValueError, KeyError, TypeError):
            continue
    if lists:
        write_json(path(), {"version": 1, "lists": lists})


def saved():
    try:
        return _read(str(path()), path().stat().st_mtime)
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def _read(name, stamp):
    lists = json.loads(open(name).read()).get("lists")
    return {k: v for k, v in lists.items() if k in LISTS and isinstance(v, list)}


def order(key):
    """canonical id → its place in that list ({} when the list isn't downloaded yet)."""
    return {f"mal:{n}": place for place, n in enumerate(saved().get(key, []))}
