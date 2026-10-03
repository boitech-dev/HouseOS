"""Community radio directory; station UUIDs cross the app/parser boundary, never URLs."""

from functools import lru_cache
from typing import Literal
import re
import time
from urllib.parse import urlparse
from uuid import UUID
import httpx
from fastapi import Depends, HTTPException, Query
from .music import router, enqueue, Add
from .auth import Input, require_actor, require_permission
from pydantic import Field
from .db import get_db
from .models import Record
from sqlalchemy import select

SERVERS = ("de1.api.radio-browser.info", "de2.api.radio-browser.info", "nl1.api.radio-browser.info")


def station_id(value):
    return str(UUID(value))


def directory(path, params=None):
    for server in SERVERS:
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET",
                    "https://" + server + "/json/" + path,
                    params=params,
                    headers={"User-Agent": "HouseOS/1.0 (private household radio)"},
                ) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 2_000_000:
                            raise ValueError("RADIO_RESPONSE_TOO_LARGE")
                    import json

                    result = json.loads(content)
                    if isinstance(result, list):
                        return result
        except (httpx.HTTPError, ValueError):
            continue
    raise ValueError("RADIO_DIRECTORY_UNAVAILABLE")


def normalize(row, include_url=False):
    if not isinstance(row, dict):
        raise ValueError("RADIO_STATION_INVALID")
    url = str(row.get("url_resolved") or row.get("url") or "")
    parsed = urlparse(url)
    # The fetch sandbox allows public HTTP(S); reject credentials and other protocols.
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        # web ports, or the high ports most Icecast/Shoutcast streams use (never other services)
        or not (parsed.port in (None, 80, 443) or 1024 <= parsed.port <= 65535)
        or len(url) > 2048
    ):
        raise ValueError("RADIO_STREAM_UNSUPPORTED")
    result = {
        "id": station_id(row["stationuuid"]),
        "name": str(row.get("name") or "Radio")[:160],
        "country": str(row.get("country") or "")[:80],
        "language": str(row.get("language") or "")[:80],
        "tags": str(row.get("tags") or "")[:160],
        "codec": str(row.get("codec") or "")[:16],
        "bitrate": max(0, min(int(row.get("bitrate") or 0), 10000)),
        "checked_at": str(row.get("lastchecktime_iso8601") or "")[:40],
        "live": True,
        "https": url.startswith("https://"),  # plays on phones too (Speaker mode)
    }
    favicon = str(row.get("favicon") or "")
    result["favicon"] = favicon if favicon.startswith("https://") and len(favicon) <= 1000 else None
    if include_url:
        result["url"] = url
    return result


# How to rank the directory: most listened, rising, most liked, newly added, or a surprise.
ORDERS = {
    "popular": "clickcount",
    "trending": "clicktrend",
    "liked": "votes",
    "new": "changetimestamp",
    "random": "random",
}
# Genres people look for; the directory's own tag list is dominated by a few broadcasters'
# labels, so it is filtered through this vocabulary and ranked by how many stations it has.
GENRES = {
    "pop",
    "rock",
    "jazz",
    "classical",
    "electronic",
    "dance",
    "house",
    "techno",
    "trance",
    "ambient",
    "chillout",
    "lounge",
    "lofi",
    "hip hop",
    "rap",
    "rnb",
    "soul",
    "funk",
    "disco",
    "blues",
    "country",
    "folk",
    "reggae",
    "latin",
    "salsa",
    "reggaeton",
    "metal",
    "hard rock",
    "punk",
    "indie",
    "alternative",
    "oldies",
    "60s",
    "70s",
    "80s",
    "90s",
    "2000s",
    "soundtrack",
    "world",
    "african",
    "afrobeats",
    "k-pop",
    "j-pop",
    "anime",
    "chanson",
    "french",
    "drum and bass",
    "dubstep",
    "psytrance",
    "synthwave",
    "eurodance",
    "italo disco",
    "schlager",
    "flamenco",
    "bossa nova",
    "tango",
    "gospel",
    "christian",
    "piano",
    "instrumental",
    "meditation",
    "kids",
    "news",
    "talk",
    "sports",
    "comedy",
    "top 40",
    "classic rock",
    "easy listening",
    "smooth jazz",
    "deep house",
    "lo-fi",
    "hits",
}


@lru_cache(maxsize=128)
def cached_search(name, tag, country, language, page, bucket, order="popular", https=False):
    rows = directory(
        "stations/search",
        {
            "name": name,
            "tag": tag,
            "countrycode": country,
            "language": language,
            "hidebroken": "true",
            "order": ORDERS[order],
            "reverse": "false" if order == "random" else "true",
            "limit": 24,
            "offset": 0 if order == "random" else page * 24,
            **({"is_https": "true"} if https else {}),
        },
    )
    result = []
    for row in rows[:24]:
        try:
            if isinstance(row, dict) and row.get("lastcheckok") == 1:
                result.append(normalize(row))
        except (ValueError, TypeError, KeyError):
            continue
    return result


def require_public(url):
    """Stations come from a public directory: never let one point at this house's network."""
    import ipaddress
    import socket

    host = urlparse(url).hostname or ""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)}
    except OSError:
        raise ValueError("RADIO_STATION_UNAVAILABLE")
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        raise ValueError("RADIO_STATION_UNAVAILABLE")
    return url


def resolve(identity):
    rows = directory("stations/byuuid/" + station_id(identity))
    if not rows or rows[0].get("lastcheckok") != 1:
        raise ValueError("RADIO_STATION_UNAVAILABLE")
    return normalize(rows[0], include_url=True)


def icy_title(url, name="", deadline=8.0, limit=64 * 1024):
    """The song a station says it is playing (its ICY "StreamTitle"), or None. One short
    read: the stream's first metadata block, then the connection closes."""
    started = time.monotonic()
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"Icy-MetaData": "1", "User-Agent": "HouseOS/1.0"},
            timeout=deadline,
            follow_redirects=True,
        ) as response:
            every = int(response.headers.get("icy-metaint") or 0)
            if not 0 < every <= limit:
                return None
            data = b""
            for chunk in response.iter_raw():
                data += chunk
                if len(data) > every and len(data) >= every + 1 + data[every] * 16:
                    break
                if len(data) > limit + 4081 or time.monotonic() - started > deadline:
                    return None
            title = parse_icy(data[every:])
            # Some stations only repeat their own name or an internal id: not a song.
            if not title or title.casefold() == name.casefold() or not re.search(r"[^\W\d_]{3}", title):
                return None
            return title
    except (httpx.HTTPError, ValueError, IndexError):
        return None


def parse_icy(block):
    """`block` starts at the metadata length byte: StreamTitle='Artist - Title';"""
    if not block:
        return None
    text = block[1 : 1 + block[0] * 16].rstrip(b"\0").decode("utf-8", "replace")
    start = text.find("StreamTitle='")
    if start < 0:
        return None
    title = text[start + 13 :].split("';", 1)[0].strip()
    return title[:200] or None


@lru_cache(maxsize=256)
def cached_station(identity, bucket):
    return resolve(identity)


@router.get("/radio/{identity}/art")
async def station_art(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    """A station's logo through the sanitising image cache (small JPEG)."""
    from starlette.concurrency import run_in_threadpool
    from .cinema import image_response
    from .playback import MediaError

    require_permission(actor, "music.read")
    db.close()  # never hold a connection while an image is fetched
    try:
        station = await run_in_threadpool(cached_station, station_id(identity), int(time.time() // 86400))
    except (MediaError, OSError, ValueError, httpx.HTTPError):
        raise HTTPException(404, "Artwork unavailable") from None
    if not station.get("favicon"):
        raise HTTPException(404, "No artwork")
    return await image_response(station["favicon"], 86400)


@router.get("/radio")
def search_radio(
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=80),
    country: str = Query(default="", max_length=2),
    language: str = Query(default="", max_length=50),
    page: int = Query(default=0, ge=0, le=100),
    order: Literal["popular", "trending", "liked", "new", "random"] = "popular",
    https: bool = False,
    actor=Depends(require_actor),
):
    require_permission(actor, "music.read")
    # A surprise is new on every ask; the rest is cached for ten minutes.
    bucket = time.time() if order == "random" else int(time.time() // 600)
    try:
        return {
            "items": cached_search(q, tag, country.upper(), language, page, bucket, order, https),
            "page": page,
            "directory": "Radio Browser",
            "cache_seconds": 600,
            "station_checks_are_not_playback_verification": True,
        }
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None


@lru_cache(maxsize=4)
def cached_facets(day):
    """The directory's own genres, countries and languages, biggest first (once a day)."""
    tags = directory(
        "tags", {"order": "stationcount", "reverse": "true", "hidebroken": "true", "limit": 3000}
    )
    countries = directory("countries", {"order": "stationcount", "reverse": "true", "hidebroken": "true"})
    languages = directory(
        "languages", {"order": "stationcount", "reverse": "true", "hidebroken": "true", "limit": 60}
    )

    def clean(rows, least):
        return [
            r
            for r in rows
            if isinstance(r, dict)
            and 2 <= len(str(r.get("name", ""))) <= 30
            and (r.get("stationcount") or 0) >= least
        ]

    return {
        "genres": [r["name"] for r in clean(tags, 10) if r["name"].lower() in GENRES],
        "countries": [
            {"code": r["iso_3166_1"], "name": r["name"], "stations": r["stationcount"]}
            for r in clean(countries, 20)
            if re.fullmatch(r"[A-Z]{2}", str(r.get("iso_3166_1", "")))
        ],
        "languages": [r["name"] for r in clean(languages, 30)],
    }


@router.get("/radio/facets")
def radio_facets(actor=Depends(require_actor)):
    require_permission(actor, "music.read")
    try:
        return cached_facets(int(time.time() // 86400))
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None


class RadioAdd(Input):
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/radio/{identity}/queue")
def queue_radio(identity: str, body: RadioAdd, actor=Depends(require_actor), db=Depends(get_db)):
    try:
        source = "radio:" + station_id(identity)
    except ValueError:
        raise HTTPException(422, "Invalid station ID") from None
    return enqueue(Add(source_url=source, idempotency_key=body.idempotency_key), actor, db)


@router.get("/radio/favorites")
def favorites(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    return {
        "items": [
            {"favorite_id": row.id, **row.data}
            for row in db.scalars(
                select(Record)
                .where(
                    Record.kind == "radio.favorite", Record.owner_id == actor.id, Record.deleted_at.is_(None)
                )
                .limit(100)
            )
        ]
    }


@router.post("/radio/{identity}/favorite")
def favorite(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    try:
        station = resolve(identity)
        station.pop("url", None)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "Station unavailable") from None
    rows = db.scalars(
        select(Record).where(
            Record.kind == "radio.favorite", Record.owner_id == actor.id, Record.deleted_at.is_(None)
        )
    ).all()
    if any(row.data.get("id") == station["id"] for row in rows):
        return {"status": "completed"}
    if len(rows) >= 100:
        raise HTTPException(409, "Favorite station limit reached")
    db.add(Record(kind="radio.favorite", owner_id=actor.id, data=station))
    db.commit()
    return {"status": "completed"}


@router.delete("/radio/favorites/{identity}")
def remove_favorite(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.queue")
    row = db.scalar(
        select(Record).where(
            Record.id == identity, Record.owner_id == actor.id, Record.kind == "radio.favorite"
        )
    )
    if not row:
        raise HTTPException(404, "Favorite not found")
    db.delete(row)
    db.commit()
    return {"status": "completed"}
