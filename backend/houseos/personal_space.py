"""Preconfigured public discoveries and private bookmarks; no model or account required."""

import hashlib
import time
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Actor, require_actor
from .cinema import cached_public_poster
from .cinema_adapters import public_fetch, public_json
from .db import get_db
from .models import Record, User
from .playback import MediaError

router = APIRouter(prefix="/personal-space", tags=["personal-space"])
FEEDS = {
    "technology": ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    "science": ("BBC Science & Environment", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
}


def resident(actor):
    if actor.role not in {"admin", "resident"}:
        raise HTTPException(403, "Personal space is available to residents.")


def safe_call(fn, *args):
    try:
        return fn(*args)
    except MediaError as exc:
        raise HTTPException(
            503,
            {
                "code": "PUBLIC_SOURCE_UNAVAILABLE",
                "message": "This public source is temporarily unavailable. Try again later.",
                "cause": exc.code,
            },
        ) from None


@lru_cache(maxsize=64)
def anime_data(query, offset, bucket):
    params = {"sort": "-userCount", "page[limit]": 12, "page[offset]": offset, "filter[ageRating]": "G,PG"}
    if query:
        params["filter[text]"] = query
    raw = public_json("https://kitsu.io/api/edge/anime?" + urlencode(params))
    return [
        anime_summary(item)
        for item in raw.get("data", [])[:12]
        if item.get("attributes", {}).get("ageRating") in {"G", "PG"}
    ]


def anime_summary(item):
    a = item["attributes"]
    identity = str(item["id"])
    if not identity.isdigit():
        raise MediaError("PROVIDER_UNAVAILABLE", "Invalid anime identity.", "identify")
    return {
        "id": identity,
        "title": str(a.get("canonicalTitle") or "Untitled")[:240],
        "description": str(a.get("synopsis") or "")[:500],
        "rating": str(a.get("averageRating") or "")[:6],
        "poster": "/api/v1/personal-space/anime/" + identity + "/poster",
        "url": "https://kitsu.app/anime/" + identity,
        "provider": "Kitsu",
    }


@lru_cache(maxsize=64)
def anime_detail(identity, bucket):
    raw = public_json("https://kitsu.io/api/edge/anime/" + str(identity)).get("data", {})
    if raw.get("attributes", {}).get("ageRating") not in {"G", "PG"}:
        raise HTTPException(404, "This title is outside the family-friendly catalog.")
    return anime_summary(raw)


@lru_cache(maxsize=8)
def feed_items(feed, bucket):
    content, _ = public_fetch(FEEDS[feed][1], limit=500000)
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise MediaError("PROVIDER_UNAVAILABLE", "Unsupported feed format.", "identify")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise MediaError("PROVIDER_UNAVAILABLE", "Invalid feed.", "identify") from None
    result = []
    for item in root.findall("./channel/item")[:20]:
        url = item.findtext("link", "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "www.bbc.com",
            "www.bbc.co.uk",
            "bbc.com",
            "bbc.co.uk",
            "www.lemonde.fr",
            "lemonde.fr",
        }:
            continue
        result.append(
            {
                "id": hashlib.sha256(url.encode()).hexdigest()[:24],
                "title": item.findtext("title", "")[:240],
                "date": item.findtext("pubDate", "")[:80],
                "url": url,
                "provider": FEEDS[feed][0],
            }
        )
    return result


@router.get("/anime")
def anime(
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=1000),
    actor: Actor = Depends(require_actor),
):
    resident(actor)
    rows = safe_call(anime_data, q.strip(), offset, int(time.time() // 1800))
    return {
        "items": rows,
        "next_offset": offset + 12 if len(rows) == 12 else None,
        "provider": "Kitsu",
        "filter": "G/PG only",
    }


@router.get("/news")
def news(feed: Literal["technology", "science"] = "technology", actor: Actor = Depends(require_actor)):
    resident(actor)
    return {"items": safe_call(feed_items, feed, int(time.time() // 900)), "provider": FEEDS[feed][0]}


@router.get("/anime/{identity}/poster")
def poster(identity: int, actor: Actor = Depends(require_actor)):
    resident(actor)
    if not 1 <= identity <= 10000000:
        raise HTTPException(404)
    # Fixed CDN/path, never a caller-controlled URL or arbitrary image proxy.
    content = safe_call(
        cached_public_poster,
        f"https://media.kitsu.app/anime/poster_images/{identity}/small.jpg",
        int(time.time() // 3600),
    )
    return Response(
        content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/favorites")
def favorites(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    rows = db.scalars(
        select(Record)
        .where(Record.kind == "space.favorite", Record.owner_id == actor.id, Record.deleted_at.is_(None))
        .order_by(Record.created_at.desc())
        .limit(100)
    )
    return {"items": [row.data for row in rows]}


@router.put("/favorites/{identity}")
def save_favorite(identity: int, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    if not 1 <= identity <= 10000000:
        raise HTTPException(422, "Invalid anime identity")
    data = safe_call(anime_detail, identity, int(time.time() // 1800))
    key = hashlib.sha256(f"{actor.id}:kitsu:{identity}".encode()).hexdigest()[:36]
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    row = db.get(Record, key)
    if row is None:
        count = len(
            db.scalars(
                select(Record.id).where(Record.owner_id == actor.id, Record.kind == "space.favorite")
            ).all()
        )
        if count >= 100:
            raise HTTPException(409, "Your personal space holds up to 100 saved titles.")
        row = Record(id=key, owner_id=actor.id, kind="space.favorite", visibility="private", data=data)
        db.add(row)
    else:
        row.data = data
    db.commit()
    return data


@router.delete("/favorites/{identity}")
def remove_favorite(identity: int, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    key = hashlib.sha256(f"{actor.id}:kitsu:{identity}".encode()).hexdigest()[:36]
    row = db.scalar(
        select(Record).where(Record.id == key, Record.owner_id == actor.id, Record.kind == "space.favorite")
    )
    if row:
        db.delete(row)
        db.commit()
    return {"removed": True}


# Daily modules are opt-in. Nothing fetches public feeds before a resident configures them.
from datetime import UTC
from zoneinfo import ZoneInfo
import re
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

PUBLIC_FETCH_SLOTS = BoundedSemaphore(3)
from pydantic import Field, field_validator
from .auth import Input
from .db import utcnow

FEEDS.update(
    {
        "world": ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        "culture": ("BBC Culture", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"),
        "business": ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        "sports": ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
    }
)
NEWS_INTERESTS = ["technology", "science", "world", "culture", "business", "sports"]
for interest, path in zip(
    NEWS_INTERESTS, ["pixels", "sciences", "international", "culture", "economie", "sport"]
):
    FEEDS["fr_" + interest] = ("Le Monde · " + path, "https://www.lemonde.fr/" + path + "/rss_full.xml")

ART_PRESETS = ["scenery", "landscape", "cityscape", "cat", "space", "fantasy", "flowers"]
SPACE_DEFAULTS = {
    "news_language": "fr",
    "news_interests": [],
    "subreddits": [],
    "art_tags": [],
    "daily_count": 5,
}


class SpaceConfig(Input):
    news_language: Literal["fr", "en"] | None = None
    news_interests: (
        list[Literal["technology", "science", "world", "culture", "business", "sports"]] | None
    ) = Field(default=None, max_length=3)
    subreddits: list[str] | None = Field(default=None, max_length=5)
    art_tags: list[str] | None = Field(default=None, max_length=3)
    daily_count: int | None = Field(default=None, ge=5, le=20)
    expected_version: int = Field(default=0, ge=0)

    @field_validator("subreddits")
    @classmethod
    def subreddit_names(cls, values):
        if values is None:
            return None
        normalized = list(dict.fromkeys(value.strip().removeprefix("r/").lower() for value in values))
        if any(not re.fullmatch(r"[a-z0-9_]{2,21}", value) for value in normalized):
            raise ValueError("Choose subreddit names, not URLs (2-21 letters, digits or underscores).")
        return normalized

    @field_validator("art_tags")
    @classmethod
    def illustration_tags(cls, values):
        if values is None:
            return None
        normalized = list(dict.fromkeys(value.strip().lower().replace(" ", "_") for value in values))
        if any(not re.fullmatch(r"[a-z0-9_.()\-]{1,60}", value) for value in normalized):
            raise ValueError("Use simple illustration tags; operators and rating overrides are not accepted.")
        return normalized


def private_space(db, actor, kind):
    return db.scalar(
        select(Record).where(Record.owner_id == actor.id, Record.kind == kind, Record.deleted_at.is_(None))
    )


def set_setup_conversation(db, actor, conversation_id):
    # Serialize pointer creation; SQL timestamps may tie within a second.
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    pointer = private_space(db, actor, "space.session")
    if pointer:
        pointer.data = {"conversation_id": conversation_id}
    else:
        db.add(
            Record(
                owner_id=actor.id,
                kind="space.session",
                visibility="private",
                data={"conversation_id": conversation_id},
            )
        )


def setup_conversation(db, actor):
    query = select(Record).where(
        Record.owner_id == actor.id,
        Record.kind == "conversation",
        Record.deleted_at.is_(None),
        Record.data["purpose"].as_string() == "personal_space",
    )
    pointer = private_space(db, actor, "space.session")
    if pointer:
        return db.scalar(query.where(Record.id == pointer.data.get("conversation_id")))
    # Existing pre-pointer conversations remain recoverable on first upgrade.
    return db.scalar(query.order_by(Record.updated_at.desc(), Record.id.desc()).limit(1))


@router.get("/config")
def configuration(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    row = private_space(db, actor, "space.config")
    conversation = setup_conversation(db, actor)
    completed = bool(conversation and conversation.data.get("space_setup_complete"))
    return {
        "configured": row is not None,
        "version": row.version if row else 0,
        "config": row.data if row else None,
        "setup_complete": completed,
        "conversation_id": conversation.id if conversation and not completed else None,
    }


def finish_setup(actor, db, conversation_id=None, message=""):
    resident(actor)
    # Only the actual latest resident message can authorize closing setup, never a tool argument.
    normalized = message.strip().lower().replace("’", "'").rstrip(".! ✅👍")
    if not re.fullmatch(
        r"(?:yes[, ]+)?(?:looks good|all good|it(?:'s| is) good|perfect|that(?:'s| is) good|done|finish setup|i confirm|yes|oui|parfait|c'est bon|tout est bon|je confirme|ça me va|ca me va)(?:[, ]+(?:thanks|thank you|merci))?",
        normalized,
    ):
        raise HTTPException(
            409, "Ask the resident to confirm the saved space looks good before closing setup."
        )
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    current = setup_conversation(db, actor)
    if not current or current.id != conversation_id:
        raise HTTPException(409, "This setup conversation was replaced. Continue the current setup chat.")
    row = db.scalar(
        select(Record)
        .where(
            Record.id == conversation_id,
            Record.owner_id == actor.id,
            Record.kind == "conversation",
            Record.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not row or row.data.get("purpose") != "personal_space":
        raise HTTPException(404, "Personal setup conversation not found.")
    if not private_space(db, actor, "space.config"):
        raise HTTPException(409, "Save the requested space settings before finishing setup.")
    row.data = {**row.data, "space_setup_complete": True}
    db.commit()
    return {
        "status": "completed",
        "message": "Your space is ready. Setup chat is tucked away; saved conversation history is retained.",
    }


@router.get("/options")
def options(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    return {
        **configuration(actor, db),
        "news_interests": NEWS_INTERESTS,
        "news_languages": {"fr": "Le Monde public RSS (French)", "en": "BBC public RSS (English)"},
        "presets_are_examples": True,
        "subreddit_presets": ["technology", "science", "anime", "CozyPlaces"],
        "maximum_subreddits": 5,
        "art_tag_presets": ART_PRESETS,
        "art_source": "Safebooru / Danbooru general-rated illustrations",
        "daily_count": {"min": 5, "max": 20, "applies_to": ["news", "reddit", "art"]},
        "maximum_news_interests": 3,
        "maximum_art_tags": 3,
        "behavior": "Choose only requested modules. Empty lists disable a module. Daily selections use code, no model calls. Reddit is public RSS: unavailable feeds show an error, never a fabricated replacement. Provide only changed fields with expected_version. Omitted or null fields preserve current settings; empty arrays explicitly disable modules.",
    }


class ArtTagSearch(Input):
    query: str = Field(min_length=1, max_length=60)


@lru_cache(maxsize=128)
def lookup_art_tags(query):
    raw = public_json(
        "https://safebooru.donmai.us/tags.json?"
        + urlencode({"search[name_matches]": query + "*", "search[order]": "count", "limit": 20})
    )
    if not isinstance(raw, list):
        raise MediaError("PUBLIC_FEED_INVALID", "Invalid tag lookup response.", "discover")
    return [
        {
            "tag": item["name"],
            "post_count": item.get("post_count", 0),
            "category": {0: "theme", 3: "series", 4: "character"}[item["category"]],
        }
        for item in raw
        if isinstance(item, dict)
        and item.get("category") in {0, 3, 4}
        and re.fullmatch(r"[a-z0-9_.()\-]{1,60}", str(item.get("name", "")))
    ][:5]


@router.get("/art-tags")
def art_tags(query: str = Query(min_length=1, max_length=60), actor: Actor = Depends(require_actor)):
    resident(actor)
    normalized = query.strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9_.()\-]{1,60}", normalized):
        raise HTTPException(422, "Use a character, series or simple theme name.")
    try:
        with PUBLIC_FETCH_SLOTS:
            rows = lookup_art_tags(normalized)
            if not rows and "_(" in normalized:
                rows = lookup_art_tags(normalized.split("_(", 1)[0])
        return {
            "status": "completed",
            "items": rows,
            "count_scope": "Provider tag counts include all ratings; the daily image feed always filters general-rated posts.",
            "guidance": "Use a matching canonical tag. Ask which character when ambiguous; never silently substitute an unrelated result.",
        }
    except (MediaError, ValueError, KeyError, TypeError) as exc:
        return {
            "status": "unavailable",
            "code": getattr(exc, "code", "PUBLIC_SOURCE_UNAVAILABLE"),
            "items": [],
        }


@router.put("/config")
def configure(body: SpaceConfig, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    db.scalar(select(User).where(User.id == actor.id).with_for_update())
    row = private_space(db, actor, "space.config")
    if body.expected_version != (row.version if row else 0):
        raise HTTPException(409, "Your space changed. Read its current options before updating it.")
    data = {
        **SPACE_DEFAULTS,
        **(row.data if row else {}),
        **body.model_dump(exclude={"expected_version"}, exclude_none=True),
    }
    data["news_interests"] = list(dict.fromkeys(data["news_interests"]))
    if row:
        row.data, row.version = data, row.version + 1
    else:
        row = Record(owner_id=actor.id, kind="space.config", visibility="private", data=data)
        db.add(row)
    db.commit()
    return {
        "status": "configured",
        "version": row.version,
        "news_interests": data["news_interests"],
        "subreddits": data["subreddits"],
        "art_tags": data["art_tags"],
        "daily_count": data["daily_count"],
        "news_language": data["news_language"],
        "message": "Personal daily selections saved. Refresh your space to view them; no content has been claimed available yet.",
    }


def parse_atom(content, subreddit):
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise MediaError("PUBLIC_FEED_INVALID", "Unsupported public feed.", "discover")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise MediaError("PUBLIC_FEED_INVALID", "Invalid public feed.", "discover") from None
    namespace = {"a": "http://www.w3.org/2005/Atom"}
    rows = []
    for entry in root.findall("a:entry", namespace)[:5]:
        link = entry.find("a:link", namespace)
        url = link.get("href", "") if link is not None else ""
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.reddit.com"
            or not parsed.path.lower().startswith("/r/" + subreddit.lower() + "/")
        ):
            continue
        rows.append(
            {
                "id": hashlib.sha256(url.encode()).hexdigest()[:24],
                "title": (entry.findtext("a:title", "", namespace))[:240],
                "url": url,
                "date": entry.findtext("a:updated", "", namespace)[:40],
                "provider": "Reddit · r/" + subreddit,
            }
        )
    return rows


@lru_cache(maxsize=128)
def reddit_daily(subreddit, day):
    content, _ = public_fetch(
        "https://www.reddit.com/r/" + subreddit + "/top/.rss?t=day&limit=20", limit=500000
    )
    return parse_atom(content, subreddit)


@lru_cache(maxsize=128)
def art_daily(tag, hour):
    """A fresh random set of general-rated illustrations for each hour."""
    raw = public_json(
        "https://safebooru.donmai.us/posts.json?"
        + urlencode({"tags": "rating:g " + tag, "limit": 20, "random": "true"})
    )
    result = []
    if not isinstance(raw, list):
        raise MediaError("PUBLIC_FEED_INVALID", "Invalid illustration response.", "discover")
    for item in raw[:20]:
        if (
            not isinstance(item, dict)
            or item.get("rating") != "g"
            or item.get("is_deleted")
            or item.get("is_banned")
        ):
            continue
        identity = str(item.get("id", ""))
        image_url = str(item.get("large_file_url") or item.get("preview_file_url") or "")
        parsed = urlsplit(image_url)
        if (
            not identity.isdigit()
            or parsed.scheme != "https"
            or parsed.hostname != "cdn.donmai.us"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+\.(jpg|png|webp)", parsed.path)
            or parsed.query
        ):
            continue
        result.append(
            {
                "id": identity,
                "title": (item.get("tag_string_copyright") or tag).replace("_", " ")[:120],
                "artist": str(item.get("tag_string_artist") or "Artist not identified")[:160],
                "tag": tag,
                "provider": "Safebooru / Danbooru",
                "url": "https://safebooru.donmai.us/posts/" + identity,
                "poster": "/api/v1/personal-space/illustrations/" + identity + "/image",
                "_image_url": image_url,
            }
        )
    return result


def daily_source(kind, key, day):
    try:
        with PUBLIC_FETCH_SLOTS:
            rows = (
                feed_items(key, day)
                if kind == "news"
                else reddit_daily(key, day)
                if kind == "reddit"
                else art_daily(key, day)
            )
        return {"kind": kind, "key": key, "items": rows, "status": "ready" if rows else "empty"}
    except (MediaError, ValueError, KeyError, TypeError) as exc:
        return {
            "kind": kind,
            "key": key,
            "items": [],
            "status": "unavailable",
            "code": getattr(exc, "code", "PUBLIC_SOURCE_UNAVAILABLE"),
        }


def public_daily(data):
    return {
        **data,
        "sections": [
            {
                **section,
                "items": [
                    {k: v for k, v in item.items() if not k.startswith("_")} for item in section["items"]
                ],
            }
            for section in data.get("sections", [])
        ],
    }


@router.get("/today")
def today(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    config_row = private_space(db, actor, "space.config")
    if not config_row:
        return {"configured": False, "sections": []}
    config = SpaceConfig(**{**SPACE_DEFAULTS, **config_row.data})
    from .house_settings import resident_defaults

    user = db.get(User, actor.id)
    zone = (user.preferences or {}).get("timezone") or resident_defaults(db)["timezone"]
    try:
        day = utcnow().replace(tzinfo=UTC).astimezone(ZoneInfo(zone)).date().isoformat()
    except (ValueError, KeyError):
        day = utcnow().date().isoformat()
    # Illustrations change every hour (a new random set); news and Reddit every 12 hours.
    bucket = int(time.time() // (3600 if config.art_tags else 43200))
    half_day = int(time.time() // 43200)
    version = config_row.version
    cache = private_space(db, actor, "space.daily")
    if (
        cache
        and cache.data.get("refresh_bucket") == bucket
        and cache.data.get("config_version") == version
        and (not cache.data.get("retry_after") or cache.data["retry_after"] > time.time())
    ):
        return public_daily(cache.data)
    db.rollback()  # Do not keep a transaction open while fetching public data.
    work = (
        [
            ("news", ("fr_" if config.news_language == "fr" else "") + key, half_day)
            for key in config.news_interests
        ]
        + [("reddit", key, half_day) for key in config.subreddits]
        + [("art", key, int(time.time() // 3600)) for key in config.art_tags]
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = list(pool.map(lambda args: daily_source(*args), work))
    sections = []
    for kind in ("news", "reddit", "art"):
        selected = [source for source in sources if source["kind"] == kind]
        if not selected:
            continue
        # Interleave each chosen source instead of letting one interest fill every slot.
        combined, seen = [], set()
        for index in range(20):
            for source in selected:
                if len(source["items"]) > index:
                    item = source["items"][index]
                    if item["id"] not in seen:
                        combined.append(item)
                        seen.add(item["id"])
        sections.append(
            {
                "kind": kind,
                "items": combined[: config.daily_count],
                "sources": [
                    {key: source[key] for key in ("key", "status")}
                    | ({"code": source["code"]} if "code" in source else {})
                    for source in selected
                ],
            }
        )
    result = {
        "configured": True,
        "day": day,
        "refresh_bucket": bucket,
        "config_version": version,
        "selected_at": utcnow().isoformat() + "Z",
        "sections": sections,
        "news_language": config.news_language,
        "selection": "News and Reddit every 12 hours, new random illustrations every hour; fewer items are shown when sources return fewer results.",
        "retry_after": time.time() + 1800
        if any(source["status"] == "unavailable" for source in sources)
        else None,
    }
    active_user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if not active_user or not active_user.active or active_user.role not in {"resident", "admin"}:
        raise HTTPException(403, "Resident access changed during refresh.")
    current = private_space(db, actor, "space.config")
    if not current or current.version != version:
        raise HTTPException(409, "Your space changed during refresh. Reload the current selection.")
    cache = private_space(db, actor, "space.daily")
    if (
        cache
        and cache.data.get("refresh_bucket") == bucket
        and cache.data.get("config_version") == version
        and (not cache.data.get("retry_after") or cache.data["retry_after"] > time.time())
    ):
        return public_daily(cache.data)
    if cache:
        cache.data = result
    else:
        db.add(Record(owner_id=actor.id, kind="space.daily", visibility="private", data=result))
    db.commit()
    return public_daily(result)


@router.get("/illustrations/{identity}/image")
def illustration_image(identity: int, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    resident(actor)
    cache = private_space(db, actor, "space.daily")
    item = next(
        (
            item
            for section in (cache.data.get("sections", []) if cache else [])
            if section["kind"] == "art"
            for item in section["items"]
            if item["id"] == str(identity)
        ),
        None,
    )
    if not item:
        raise HTTPException(404, "Illustration is not in your daily selection.")
    content = safe_call(cached_public_poster, item["_image_url"], int(time.time() // 86400))
    return Response(
        content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


def refresh_configured_spaces(db):
    """Maintenance and HTTP share the same private, cached refresh path; no AI."""
    users = db.scalars(
        select(User).where(
            User.active.is_(True),
            User.role.in_(["admin", "resident"]),
            User.id.in_(
                select(Record.owner_id).where(Record.kind == "space.config", Record.deleted_at.is_(None))
            ),
        )
    ).all()
    for user in users:
        try:
            today(Actor(user.id, user.name, user.role, frozenset()), db)
        except Exception:
            db.rollback()
            print("personal_space_refresh_failed", flush=True)
