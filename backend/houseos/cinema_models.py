"""Cinema tables and request bodies."""

from __future__ import annotations
import ipaddress
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, new_id, utcnow


class CinemaTitle(Base):
    __tablename__ = "cinema_titles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    canonical_id: Mapped[str] = mapped_column(String(180), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class CinemaDevice(Base):
    __tablename__ = "cinema_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    adapter: Mapped[str] = mapped_column(String(30))
    address: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    observation: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner_workflow: Mapped[str | None] = mapped_column(String(36), nullable=True)


class CinemaWorkflow(Base):
    __tablename__ = "cinema_workflows"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("cinema_titles.id"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("cinema_devices.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(48), default="discovered")
    version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class CinemaConfirmation(Base):
    __tablename__ = "cinema_confirmations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("cinema_workflows.id", ondelete="CASCADE"))
    workflow_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[object] = mapped_column(DateTime)
    consumed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


class CinemaPreparation(Base):
    __tablename__ = "cinema_preparations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("cinema_workflows.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workflow_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


class CinemaSubtitle(Base):
    __tablename__ = "cinema_subtitles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("cinema_titles.id"))
    data: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[object] = mapped_column(DateTime)


class CinemaPreference(Base):
    __tablename__ = "cinema_preferences"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class CinemaState(Base):
    __tablename__ = "cinema_user_state"
    __table_args__ = (UniqueConstraint("owner_id", "media_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    media_id: Mapped[str] = mapped_column(ForeignKey("cinema_titles.id"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_watched_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


class CinemaRelay(Base):
    __tablename__ = "cinema_relays"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("cinema_workflows.id", ondelete="CASCADE"), index=True
    )
    device_address: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(1000))
    encrypted_url: Mapped[str | None] = mapped_column(String(8000), nullable=True)
    mime: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[object] = mapped_column(DateTime)


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preferences(Body):
    # Languages the viewer follows, most comfortable first: a version in none of them ranks last.
    languages: list[str] | None = Field(default=None, max_length=6)
    audio_language: str | None = Field(default=None, min_length=2, max_length=3)
    subtitle_language: str | None = Field(default=None, min_length=2, max_length=3)
    subtitles_on: bool | None = None
    # Subtitles in one of `languages` every time, even when the sound is in the first one.
    always_subtitles: bool | None = None
    allow_video_transcode: bool | None = None
    quality: Literal["auto", "4k", "2160p", "1080p", "720p"] | None = None
    maximum_resolution: Literal[720, 1080, 2160, 4320] | None = None
    hdr: Literal["prefer", "require", "avoid", "auto"] | None = None
    autoplay: bool | None = None
    preferred_device: str | None = Field(default=None, max_length=36)
    source_selection: Literal["ask", "best_compatible"] | None = None
    audio_track: str | None = Field(default=None, max_length=80)
    subtitle_track: str | None = Field(default=None, max_length=80)

    @field_validator("languages")
    @classmethod
    def language_codes(cls, value):
        if value is not None and not all(re.fullmatch("[a-z]{2,3}", code) for code in value):
            raise ValueError("Use two- or three-letter language codes")
        return list(dict.fromkeys(value)) if value else None


class Discover(Body):
    position: float | None = Field(default=None, ge=0, le=86400)
    queue_id: str | None = Field(default=None, max_length=36)
    cloud_id: str | None = Field(default=None, pattern="^[0-9a-f]{32}$")
    media_id: str = Field(max_length=36)
    device_id: str | None = Field(default=None, max_length=36)
    season: int | None = Field(default=None, ge=0, le=100)
    episode: int | None = Field(default=None, ge=1, le=1000)
    preferences: Preferences = Field(default_factory=Preferences)
    idempotency_key: str = Field(min_length=8, max_length=80)
    # Check the most promising releases right away to offer one ready suggestion.
    suggest: bool = False


class Version(Body):
    version: int = Field(ge=1)


class SourceValidation(Version):
    source_ids: list[str] | None = Field(default=None, min_length=1, max_length=5)


class DestinationChoice(Version):
    device_id: str = Field(min_length=1, max_length=36)
    preferences: Preferences = Field(default_factory=Preferences)


class Choice(Version):
    choice_set_id: str = Field(max_length=36)
    choice: str = Field(min_length=1, max_length=120)


class Control(Version):
    action: Literal["pause", "resume", "stop", "seek", "volume"]
    position: float | None = Field(default=None, ge=0, le=86400)


class Launch(Version):
    """The resident's one tap on the suggestion card is the confirmation."""

    source_id: str = Field(min_length=1, max_length=36)
    device_id: str = Field(min_length=1, max_length=36)
    audio_track: str | None = Field(default=None, max_length=80)
    subtitle_track: str | None = Field(default=None, max_length=80)  # "off" = no subtitles
    position: float | None = Field(default=None, ge=0, le=86400)
    # Something else is on that screen: play only once the resident agreed to replace it.
    replace: bool = False


class Change(Version):
    device_id: str | None = Field(default=None, max_length=36)
    preferences: Preferences = Field(default_factory=Preferences)
    source_choice: str | None = Field(default=None, max_length=120)


class StateUpdate(Body):
    watched: bool | None = None
    favorite: bool | None = None
    watchlist: bool | None = None
    preferred_release: str | None = Field(default=None, max_length=300)
    version: int | None = Field(default=None, ge=1)


class DeviceInput(Body):
    name: str = Field(min_length=1, max_length=100)
    adapter: Literal["jellyfin", "cast", "dlna"]  # dlna: a music-only speaker or TV
    address: str = Field(max_length=64)
    session_id: str | None = Field(default=None, max_length=100)
    capabilities: dict = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)

    @field_validator("address")
    @classmethod
    def private_literal(cls, value):
        address = ipaddress.ip_address(value)
        if (
            not address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
        ):
            raise ValueError("Use the exact LAN receiver IP address.")
        return str(address)

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, value):
        allowed = {
            "video_codecs",
            "video_profiles",
            "audio_codecs",
            "containers",
            "hdr_modes",
            "dv_profiles",
            "maximum_resolution",
            "max_audio_channels",
            "embedded_subtitle_codecs",
            "external_webvtt",
            "seek",
            "pause",
            "observe_playback",
            "set_audio",
            "set_subtitles",
            "power_on",
            "power_off",
            "volume_absolute",
            "set_input",
            "description_url",  # a DLNA renderer's, from Find devices
            "kind",  # tv, audio, group or dlna, from Find devices (TV remotes leave out speakers)
            "port",  # a Cast speaker group answers on its own port, not 8009
            "tv_input",  # where films switch the TV (the TV remote)
            "inspected_at",  # the last Inspect: kept so Edit → Save still works
            "confidence",
        }
        if set(value) - allowed or len(str(value)) > 6000:
            raise ValueError("Unsupported capability profile.")
        if value.get("kind") not in (None, "tv", "audio", "group", "dlna"):
            raise ValueError("Unsupported device kind.")
        port = value.get("port")
        if port is not None and (
            not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535
        ):
            raise ValueError("Invalid device port.")
        url = value.get("description_url")
        if url is not None and (not isinstance(url, str) or not url.startswith("http://") or len(url) > 300):
            raise ValueError("Invalid description address.")
        for key in {
            "video_codecs",
            "audio_codecs",
            "containers",
            "hdr_modes",
            "embedded_subtitle_codecs",
        } & value.keys():
            if (
                not isinstance(value[key], list)
                or len(value[key]) > 32
                or any(not isinstance(v, str) or len(v) > 80 for v in value[key])
            ):
                raise ValueError("Capability lists must contain bounded strings.")
        if "dv_profiles" in value and (
            not isinstance(value["dv_profiles"], list)
            or any(type(v) is not int or v not in range(1, 11) for v in value["dv_profiles"])
        ):
            raise ValueError("Invalid Dolby Vision profile list.")
        for key, maximum in [("maximum_resolution", 4320), ("max_audio_channels", 16)]:
            if key in value and (type(value[key]) is not int or not 1 <= value[key] <= maximum):
                raise ValueError("Invalid destination resource limit.")
        for key in {
            "external_webvtt",
            "seek",
            "pause",
            "observe_playback",
            "set_audio",
            "set_subtitles",
            "power_on",
            "power_off",
            "volume_absolute",
            "set_input",
        } & value.keys():
            if type(value[key]) is not bool:
                raise ValueError("Capability switches must be booleans.")
        if "video_profiles" in value:
            if not isinstance(value["video_profiles"], dict):
                raise ValueError("Invalid codec profiles.")
            for profile in value["video_profiles"].values():
                if not isinstance(profile, dict) or set(profile) - {
                    "profiles",
                    "maximum_level",
                    "maximum_frame_rate",
                    "pixel_formats",
                }:
                    raise ValueError("Invalid codec profile limits.")
                if "maximum_level" in profile and (
                    type(profile["maximum_level"]) is not int or not 1 <= profile["maximum_level"] <= 1000
                ):
                    raise ValueError("Invalid codec level.")
                if "maximum_frame_rate" in profile and (
                    type(profile["maximum_frame_rate"]) not in {int, float}
                    or not 1 <= profile["maximum_frame_rate"] <= 240
                ):
                    raise ValueError("Invalid codec frame-rate limit.")
                if "pixel_formats" in profile and (
                    not isinstance(profile["pixel_formats"], list)
                    or len(profile["pixel_formats"]) > 32
                    or any(not isinstance(v, str) or len(v) > 40 for v in profile["pixel_formats"])
                ):
                    raise ValueError("Invalid codec bit-depth/chroma formats.")
                if "profiles" in profile and (
                    not isinstance(profile["profiles"], list)
                    or any(not isinstance(v, str) for v in profile["profiles"])
                ):
                    raise ValueError("Invalid codec profiles.")
        return value
