"""MyAnimeList metadata through Jikan; exact MAL→Kitsu mapping for stream add-ons.

MAL seasons are separate titles. Never reinterpret a MAL ID as an IMDb ID, or
merge seasons by title similarity. No provider credentials are needed here.
"""

from __future__ import annotations

import json
import httpx
import re
import threading
import time
from functools import lru_cache
from urllib.parse import urlencode

from .cinema_adapters import public_fetch
from .playback import MediaError

_JIKAN = "https://api.jikan.moe/v4"
_MAPPING = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-mini.json"
_lock = threading.Lock()
_next_request = 0.0
_retry_after: dict[str, float] = {}


@lru_cache(maxsize=256)
def _jikan(path: str, bucket: int):
    global _next_request
    # ponytail: one process gate; add a shared gate if multiple API replicas are deployed.
    busy = MediaError("ANIME_CATALOG_UNAVAILABLE", "The anime catalog is temporarily busy.", "identify", True)
    # Never queue behind another request (a queue of 15 s timeouts once starved every page of a
    # database connection): wait 3 s at most, and after any failure fail fast for 5 minutes.
    if time.monotonic() < _retry_after.get("*", 0) or not _lock.acquire(timeout=3):
        raise busy
    try:
        time.sleep(max(0, _next_request - time.monotonic()))
        _next_request = time.monotonic() + 2.1
        try:
            # Fixed provider origin, no redirects or user-supplied hosts. Standard
            # compressed JSON avoids the upstream's failing identity-cache variant.
            with httpx.stream(
                "GET",
                _JIKAN + path,
                timeout=8,
                trust_env=False,
                headers={"User-Agent": "HouseOS/1", "Accept": "application/json"},
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 4_000_000:
                        raise ValueError("Oversized anime metadata")
                value = json.loads(raw)
        except (MediaError, httpx.HTTPError, ValueError):
            _retry_after["*"] = time.monotonic() + 300
            raise MediaError(
                "ANIME_CATALOG_UNAVAILABLE",
                "The anime catalog is temporarily busy. Please try again shortly.",
                "identify",
                True,
            ) from None
        if not isinstance(value, dict) or not isinstance(value.get("data"), (list, dict)):
            raise MediaError(
                "ANIME_CATALOG_UNAVAILABLE",
                "The anime catalog returned an incomplete response.",
                "identify",
                True,
            )
        return value
    finally:
        _lock.release()


@lru_cache(maxsize=2)
def _mappings(bucket: int):
    raw, _ = public_fetch(_MAPPING, limit=16_000_000)
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise ValueError()
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            mal, kitsu = row.get("mal_id"), row.get("kitsu_id")
            if type(mal) is int and mal > 0 and type(kitsu) is int and kitsu > 0:
                result.setdefault(mal, set()).add(kitsu)
        return result
    except (ValueError, TypeError):
        raise MediaError(
            "ANIME_MAPPING_UNAVAILABLE", "Anime source matching is temporarily unavailable.", "identify", True
        ) from None


def resolve_stream(canonical: str, episode: int | None = None) -> str:
    """Return the exact Kitsu identity add-ons use; movie has no episode suffix."""
    if not re.fullmatch(r"mal:[1-9][0-9]*", canonical):
        raise MediaError("ANIME_ID_INVALID", "Select an anime from the catalog.", "identify")
    matches = _mappings(int(time.time() // 86400)).get(int(canonical[4:]), set())
    if len(matches) != 1:
        raise MediaError(
            "ANIME_MAPPING_MISSING",
            "This anime does not yet have a unique source-catalog match. No other title has been substituted.",
            "identify",
        )
    if episode is not None and (type(episode) is not int or episode < 1):
        raise MediaError("EPISODE_INVALID", "Choose an episode before looking for sources.", "identify")
    return f"kitsu:{next(iter(matches))}" + (f":{episode}" if episode is not None else "")


class AnimeCatalog:
    def get(self, path, ttl=3600):
        try:
            return _jikan(path, int(time.time() // ttl))
        except MediaError:
            if path.startswith("/top/anime?"):
                raise  # Never substitute mixed-provider scores for the official MAL ranking.
            from .anime_offline import catalog_response

            return catalog_response(path)

    def catalogs(self, kind="anime"):
        genres = [
            str(g["name"])[:40]
            for g in self.get("/genres/anime?filter=genres", 86400)["data"]
            if isinstance(g, dict) and g.get("name")
        ]
        return [
            {"id": key, "name": name, "genres": genres}
            for key, name in [
                ("top", "MyAnimeList Top Anime"),
                ("year", "Currently airing"),
                ("imdbRating", "Top rated"),
            ]
        ]

    def browse(self, kind="anime", catalog="top", genre="", offset=0):
        if catalog not in {"top", "year", "imdbRating"} or offset < 0 or offset > 10000:
            raise MediaError("CATALOG_FILTER_INVALID", "Choose an available anime collection.", "identify")
        if catalog == "top" and not genre:
            result = self.get("/top/anime?" + urlencode({"page": offset // 24 + 1, "limit": 24}))
            return {
                "items": self._items(result),
                "next_offset": offset + 24 if result.get("pagination", {}).get("has_next_page") else None,
            }
        params = {
            "page": offset // 24 + 1,
            "limit": 24,
            "sfw": "true",
            "order_by": "score" if catalog == "imdbRating" else "members",
            "sort": "desc",
        }
        if catalog == "year":
            params["status"] = "airing"
        if genre:
            match = next(
                (
                    g
                    for g in self.get("/genres/anime?filter=genres", 86400)["data"]
                    if str(g.get("name", "")).casefold() == genre.casefold()
                ),
                None,
            )
            if not match:
                raise MediaError("CATALOG_FILTER_INVALID", "Choose an available anime genre.", "identify")
            params["genres"] = match["mal_id"]
        result = self.get("/anime?" + urlencode(params))
        return {
            "items": self._items(result),
            "next_offset": offset + 24 if result.get("pagination", {}).get("has_next_page") else None,
        }

    def search(self, query, kind="anime"):
        query = query.strip()
        if not query or len(query) > 200:
            raise MediaError("CATALOG_FILTER_INVALID", "Enter an anime title to search.", "identify")
        return self._items(self.get("/anime?" + urlencode({"q": query, "limit": 24, "sfw": "true"})))

    def details(self, identity, kind=None):
        if not re.fullmatch(r"mal:[1-9][0-9]*", identity):
            raise MediaError("ANIME_ID_INVALID", "Select an anime from the catalog.", "identify")
        raw = self.get(f"/anime/{identity[4:]}")["data"]
        item = self.normalize(raw)
        if item["kind"] == "series":
            # Jikan's declared episode count is authoritative; labels do not invent titles.
            count = raw.get("episodes")
            if type(count) is int and 0 < count <= 3000:
                item["episodes"] = [
                    {"id": f"{identity}:{n}", "season": 1, "episode": n, "title": f"Episode {n}"}
                    for n in range(1, count + 1)
                ]
            else:
                # Airing series often have no total yet. Only list published episode evidence.
                episodes = self.get(f"/anime/{identity[4:]}/episodes")["data"]
                item["episodes"] = [
                    {
                        "id": f"{identity}:{e['mal_id']}",
                        "season": 1,
                        "episode": e["mal_id"],
                        "title": str(e.get("title") or f"Episode {e['mal_id']}")[:200],
                    }
                    for e in episodes
                    if type(e.get("mal_id")) is int and e["mal_id"] > 0
                ]
        return item

    def recommendations(self, identity):
        """What MyAnimeList's members recommend alongside this anime (most votes first); the
        caller falls back to similar themes when the service is down."""
        if not re.fullmatch(r"mal:[1-9][0-9]*", identity):
            return []
        rows = _jikan(f"/anime/{identity[4:]}/recommendations", int(time.time() // 86400))["data"]
        picks = []
        for row in sorted(rows, key=lambda r: -int(r.get("votes") or 0))[:12]:
            entry = row.get("entry") if isinstance(row, dict) else None
            if isinstance(entry, dict) and type(entry.get("mal_id")) is int:
                picks.append(f"mal:{entry['mal_id']}")
        return picks

    def _items(self, result):
        seen, items = set(), []
        for row in result["data"][:24]:
            if not isinstance(row, dict) or type(row.get("mal_id")) is not int or row["mal_id"] in seen:
                continue
            seen.add(row["mal_id"])
            items.append(self.normalize(row))
        return items

    @staticmethod
    def normalize(row):
        poster = row.get("images", {}).get("jpg", {})
        aired = row.get("aired", {}).get("prop", {}).get("from", {})
        return {
            "canonical_id": f"mal:{row['mal_id']}",
            "title": str(row.get("title_english") or row.get("title") or "Anime")[:240],
            "kind": "movie" if row.get("type") == "Movie" else "series",
            "year": str(row.get("year") or aired.get("year") or "")[:16],
            "description": str(row.get("synopsis") or "")[:2000],
            "_poster_url": str(poster.get("large_image_url") or poster.get("image_url") or "")[:2000],
            "genres": [str(g["name"])[:40] for g in row.get("genres", [])[:15] if g.get("name")],
            "rating": str(row.get("score") or "")[:5],
            "studios": [str(x["name"])[:80] for x in row.get("studios", [])[:3] if x.get("name")],
            "catalog_provider": "MyAnimeList via Jikan",
        }
