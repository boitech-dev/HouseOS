"""Small persisted household defaults; explicit resident settings keep precedence."""

import re
from datetime import time
from typing import Literal
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select

from .auth import Input, require_actor, require_admin, refresh_actor
from .config import settings
from .db import get_db
from .events import emit
from .models import Integration, User

router = APIRouter(tags=["house-settings"])
# ponytail: one API process; use a host-wide lock before enabling multiple API workers.
_policy_write = Lock()


class CustomGenre(Input):
    """A genre the house adds (e.g. "anime songs"): its name and the words that mean it."""

    name: str = Field(min_length=1, max_length=40)
    words: list[str] = Field(min_length=1, max_length=20)

    @field_validator("words")
    @classmethod
    def short_words(cls, value):
        value = [word.strip()[:40] for word in value if word.strip()]
        if not value:
            raise ValueError("Give at least one word")
        return value


class HouseSettings(Input):
    name: str = Field(default="MIDNIGHT HOUSE", min_length=1, max_length=80)
    timezone: str = "UTC"
    language: str = Field(default="en", pattern="^[a-z]{2,3}$")
    motion: Literal["still", "subtle", "full"] = "subtle"
    # The house's look (Me → Appearance lets each person choose another; unknown ids fall back).
    theme: str = Field(default="zabiwa", pattern="^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)
    scheme: Literal["", "dark", "light", "device"] = ""
    quiet_start: str = "23:00"
    quiet_end: str = "08:00"
    music_round_robin: bool = True
    music_sleep_minutes: int = Field(default=300, ge=0, le=1440)
    music_volume_cap: int = Field(default=100, ge=0, le=100)
    music_normalize: bool = True  # one fixed gain per song: quiet uploads +20 %, very loud -15 % (audio.py)
    music_genre_lookup: bool = True  # ask Deezer's public catalogue for genres (music_catalog)
    music_preload: int = Field(default=0, ge=0, le=10)  # songs downloaded ahead; 0: the whole queue
    # Off: songs are downloaded to play, then deleted (at most 3 ahead); none join the library.
    music_keep_downloads: bool = True
    backup_keep: int = Field(default=0, ge=0, le=90)  # backups kept, newest first; 0 keeps all
    # Games → Catalogue → "Search online": opened in a new tab with the game's details filled in
    # ({title} {console} {system} {region} {filename} {crc32}); the house admin's to change or
    # empty. A web search by default: HouseOS itself never downloads a game (D34).
    games_find_url: str = Field(
        default="https://www.google.com/search?q={title}+{console}+rom", max_length=500
    )
    music_genres: list[CustomGenre] = Field(default_factory=list, max_length=20)
    file_quota_bytes: int = Field(default_factory=lambda: settings.file_quota_bytes, ge=1024**3, le=1024**4)
    max_upload_bytes: int = Field(
        default_factory=lambda: settings.max_upload_bytes, ge=1024**2, le=80 * 1024**3
    )

    @field_validator("name")
    @classmethod
    def visible_name(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Use a visible house name")
        return value.strip()

    @field_validator("games_find_url")
    @classmethod
    def find_link(cls, value):
        value = value.strip()
        if value and not re.match(r"https?://[^\s/]+", value, re.I):
            raise ValueError("Use a web address that starts with https://")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a valid IANA timezone") from None
        return value

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def valid_time(cls, value):
        parsed = time.fromisoformat(value)
        if parsed.tzinfo or len(value) != 5:
            raise ValueError("Use HH:MM")
        return value

    @model_validator(mode="after")
    def upload_fits(self):
        if self.max_upload_bytes > self.file_quota_bytes:
            raise ValueError("Maximum upload cannot exceed the personal quota")
        return self


def get_house_settings(db):
    row = db.get(Integration, "house_settings")
    # A stored `ui` key (no longer a setting) is ignored until migration 0008 drops it.
    config = {k: v for k, v in (row.config or {}).items() if k != "ui"} if row else {}
    return HouseSettings.model_validate(config).model_dump()


def resident_defaults(db, role="resident"):
    values = get_house_settings(db)
    return {
        **{key: values[key] for key in ("timezone", "motion")},
        # Residents see the house's language; the administrator starts in English (COPY.md).
        "language": "en" if role == "admin" else values["language"],
    }


def notification_defaults(db):
    values = get_house_settings(db)
    return {key: values[key] for key in ("timezone", "quiet_start", "quiet_end")}


@router.get("/house-settings")
def public_settings(actor=Depends(require_actor), db=Depends(get_db)):
    from .cinema_models import CinemaDevice
    from .home import available

    values = get_house_settings(db)
    own = db.get(User, actor.id).preferences or {}
    home_assistant = available(db)
    return {
        **values,
        # The Smart home room also holds the TV remotes, so a TV alone is enough to show it.
        "smart_home": home_assistant or db.scalar(select(CinemaDevice.id).limit(1)) is not None,
        "home_assistant": home_assistant,
        "preferences": {**resident_defaults(db, actor.role), **own},
    }


@router.get("/admin/house-settings")
def admin_settings(actor=Depends(require_admin), db=Depends(get_db)):
    return get_house_settings(db)


@router.put("/admin/house-settings")
def save_settings(body: HouseSettings, actor=Depends(require_admin), db=Depends(get_db)):
    with _policy_write:
        db.rollback()
        db.expire_all()
        return _save_settings(body, require_admin(refresh_actor(db, actor)), db)


def _save_settings(body, actor, db):
    current = get_house_settings(db)
    # Only what this form sent: a form that shows some settings must not reset the others.
    body = HouseSettings.model_validate({**current, **body.model_dump(exclude_unset=True)})
    if body.language != current["language"]:
        from .languages import ensure_ready

        ensure_ready(db, body.language)
    if body.music_volume_cap != current["music_volume_cap"]:
        from .music import bridge

        applied = bridge("volume_cap", value=body.music_volume_cap)
        if applied.get("status") != "configured":
            raise HTTPException(503, "Audio bridge could not apply the volume cap; settings were not saved")
    if body.music_normalize != current["music_normalize"]:
        from .music import bridge

        applied = bridge("normalize", value=body.music_normalize)
        if applied.get("status") != "configured":
            raise HTTPException(503, "The music player could not apply this; settings were not saved")
    row = db.scalar(select(Integration).where(Integration.name == "house_settings").with_for_update())
    if row is None:
        row = Integration(name="house_settings", enabled=True)
        db.add(row)
    if body.music_volume_cap < current["music_volume_cap"]:
        from .music import QueueState

        queue = db.get(QueueState, 1)
        if queue and queue.volume > body.music_volume_cap:
            queue.volume = body.music_volume_cap
            queue.version += 1
            emit(db, "music.queue_changed", {"version": queue.version})
    if body.music_round_robin != current["music_round_robin"]:
        from .music import queue

        music_queue = queue(db)
        music_queue.version += 1
        emit(db, "music.queue_changed", {"version": music_queue.version})
    row.config = body.model_dump()
    emit(db, "house.settings", {"updated": True})
    emit(db, "audit.house_settings", {"status": "updated"}, actor.id)
    db.commit()
    return row.config
