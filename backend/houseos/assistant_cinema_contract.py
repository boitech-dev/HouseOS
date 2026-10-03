"""Canonical-title validation at the assistant's Cinema discovery boundary."""

from fastapi import HTTPException
from pydantic import Field, model_validator

from . import cinema, cinema_jobs


class AgentDiscover(cinema.Discover):
    media_id: str = Field(
        max_length=36,
        description="Exact canonical title ID returned by cinema_search or cinema_details; never invent an ID.",
    )
    season: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Null for a movie. For a series, use the exact season; season 0 means specials.",
    )
    episode: int | None = Field(
        default=None,
        ge=0,
        le=1000,
        description="Null for a movie. For a series, use the exact episode number, at least 1; never guess.",
    )
    position: float | None = Field(
        default=None,
        ge=0,
        le=86400,
        description="Explicit requested starting position in seconds (14 minutes = 840). Null uses watch history; 0 explicitly starts from the beginning.",
    )

    @model_validator(mode="before")
    @classmethod
    def disabled_subtitles(cls, value):
        if (
            isinstance(value, dict)
            and isinstance(value.get("preferences"), dict)
            and value["preferences"].get("subtitles_on") is False
        ):
            # Off overrides irrelevant track/language placeholders from strict tool callers.
            value = {
                **value,
                "preferences": {
                    k: v
                    for k, v in value["preferences"].items()
                    if k not in {"subtitle_language", "subtitle_track"}
                },
            }
        return value


def discover(body: AgentDiscover, actor, db):
    cinema.allowed(actor)
    title = db.get(cinema.CinemaTitle, body.media_id)
    if not title:
        raise HTTPException(404, "Title not found. Search for the exact movie or series first.")
    payload = body.model_dump(exclude_unset=True)
    payload["suggest"] = True  # check the three best versions right away, like the Watch page
    if title.kind == "movie":
        if body.season not in (None, 0) or body.episode not in (None, 0):
            raise HTTPException(422, "This title is a movie. Use null for season and episode.")
        # Some tool callers send zero for an inapplicable numeric field. Only a
        # canonical movie can make that correction safe; series remain strict.
        payload.update(season=None, episode=None)
    elif title.kind == "series":
        if body.season is None or body.episode is None or body.episode < 1:
            raise HTTPException(422, "Choose the exact season and episode first; episode must be at least 1.")
    elif title.kind == "episode":
        season, episode = title.data.get("season"), title.data.get("episode")
        parent = (
            db.get(cinema.CinemaTitle, title.data.get("parent_id")) if title.data.get("parent_id") else None
        )
        if not parent or parent.kind != "series":
            raise HTTPException(422, "The parent series is unavailable. Search for the exact series again.")
        if season is None or not isinstance(episode, int) or episode < 1:
            raise HTTPException(
                422, "This episode has no valid season/episode mapping. Choose the exact episode again."
            )
        if body.season not in (None, season) or body.episode not in (None, episode):
            raise HTTPException(422, "The requested season or episode does not match the selected title.")
        payload.update(media_id=parent.id, season=season, episode=episode)
    else:
        raise HTTPException(422, "Select a movie or an exact series episode.")
    return cinema_jobs.enqueue_discovery(cinema.Discover(**payload), actor, db)
