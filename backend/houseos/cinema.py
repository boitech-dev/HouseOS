"""Cinema domain: user-owned workflows, source choices, confirmations and watch state."""

from __future__ import annotations
import hashlib
import os
import re
import threading
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, UTC
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import SessionLocal, get_db, new_id, utcnow
from .cinema_models import (
    CinemaTitle,
    CinemaDevice,
    CinemaWorkflow,
    CinemaConfirmation,
    CinemaPreparation,
    CinemaSubtitle,
    CinemaPreference,
    CinemaState,
    CinemaRelay,
    Body,
    Preferences,
    Discover,
    Version,
    SourceValidation,
    DestinationChoice,
    Choice,
    Control,
    Change,
    Launch,
    StateUpdate,
    DeviceInput,
)
from .auth import Actor, require_actor, require_permission, require_admin, account_usable, delegated_user
from .config import settings
from .events import emit
from .models import Record
from .integrations import integration_config
from .cinema_suggest import NO_SUBTITLES, NOT_FOLLOWED
from .playback import (
    MediaError,
    compatibility,
    effective_request,
    exact_episode_file,
    select_candidate,
    resolution,
)
from .anime_catalog import AnimeCatalog
from .cinema_adapters import (
    exact_movie_file,
    DebridError,
    debrid_not_ready,
    Cinemeta,
    Comet,
    Jellyfin,
    RealDebrid,
    jellyfin_inspection,
    public_fetch,
)

router = APIRouter(prefix="/cinema", tags=["cinema"])
relay_router = APIRouter(prefix="/receiver", tags=["receiver"])


def allowed(actor):
    require_permission(actor, "cinema.use")


def failure(exc):
    raise HTTPException(
        status_code=409 if exc.code in {"PLAN_STALE", "CHOICE_AMBIGUOUS"} else 422, detail=exc.public()
    )


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except MediaError as exc:
        failure(exc)


def own_workflow(db, actor, identity, version=None):
    allowed(actor)
    row = db.scalar(
        select(CinemaWorkflow)
        .where(CinemaWorkflow.id == identity, CinemaWorkflow.owner_id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        raise HTTPException(404, "Workflow not found")
    if version is not None and row.version != version:
        failure(MediaError("PLAN_STALE", "This workflow changed. Refresh before continuing."))
    return row


def public_title(title):
    return {
        "id": title.id,
        "poster": "/api/v1/cinema/titles/" + title.id + "/poster"
        if title.data.get("_poster_url") or title.data.get("jellyfin_id")
        else None,
        "canonical_id": title.canonical_id,
        "title": title.title,
        "kind": title.kind,
        **{
            k: v
            for k, v in title.data.items()
            if k
            in {
                "year",
                "description",
                "episodes",
                "layers",
                "parent_id",
                "season",
                "episode",
                "genres",
                "rating",
                "cast",
                "director",
                "studios",
                "runtime",
            }
        },
    }


def public_device(row, admin=True):
    return {
        "id": row.id,
        "name": row.name,
        "adapter": row.adapter,
        **({"address": row.address, "session_id": row.session_id} if admin else {}),
        "capabilities": row.capabilities,
        "state": row.observation.get("state", "unknown"),
        "observed_at": row.observed_at,
        "version": row.version,
    }


def public_workflow(row):
    fields = {
        "download",
        "validation_summary",
        "operation_id",
        "choice_set",
        "provisional",
        "error",
        "confirmation_id",
        "preview",
        "plan",
        "observation",
        "checkpoint",
        "recovery_actions",
        "season",
        "episode",
        "selected_source",
    }
    payload = {
        "id": row.id,
        "kind": row.data.get("_kind", "playback"),
        "state": row.state,
        "version": row.version,
        "media_id": row.media_id,
        "device_id": row.device_id,
        **{k: v for k, v in row.data.items() if k in fields},
    }
    payload["provisional"] = payload.get("provisional", [])[:20]
    if row.data.get("_suggestion"):
        chosen = set(row.data.get("_validation_selection", []))
        checked = [s for s in row.data.get("_sources", []) if s["id"] in chosen]
        payload["suggestion_progress"] = {
            "checked": sum(bool(s.get("inspection") or s.get("error")) for s in checked),
            "total": len(chosen),
            "round": row.data.get("_rounds", 1),
            # Why earlier versions were set aside, so the wait can be explained in words.
            "setbacks": sorted(
                {(s.get("rejection") or s.get("error") or {}).get("code") for s in checked} - {None}
            ),
        }
    payload["requested_position"] = row.data.get("_requested_position")
    payload["source_total"] = len(row.data.get("_sources", []))
    payload["sleep_timer"] = row.data.get("sleep_timer")
    payload["seek_target"] = (
        row.data.get("plan", {}).get("position") if row.data.get("_seek_previous") else None
    )
    return payload


def save_workflow(db, row, state, data=None):
    row.state, row.version, row.updated_at = state, row.version + 1, utcnow()
    row.data = {**row.data, **(data or {})}
    emit(
        db,
        "cinema.workflow",
        {"workflow_id": row.id, "state": state, "version": row.version},
        user_id=row.owner_id,
    )
    db.commit()
    return public_workflow(row)


def upsert_title(db, canonical, title, kind, data):
    row = db.scalar(select(CinemaTitle).where(CinemaTitle.canonical_id == canonical))
    if row is None:
        row = CinemaTitle(id=new_id(), canonical_id=canonical, title=title[:240], kind=kind, data=data)
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.scalar(select(CinemaTitle).where(CinemaTitle.canonical_id == canonical))
            if row is None:
                raise
    else:
        old_layers = row.data.get("layers", [])
        row.data = {**row.data, **data, "layers": list(dict.fromkeys(old_layers + data.get("layers", [])))}
        row.updated_at = utcnow()
    db.flush()
    return row


def local_title(db, item):
    canonical = item.get("ProviderIds", {}).get("Imdb") or "jellyfin:" + item["Id"]
    return upsert_title(
        db,
        canonical,
        item.get("Name", "Untitled"),
        "series" if item.get("Type") == "Series" else "movie",
        {
            "year": item.get("ProductionYear"),
            "description": str(item.get("Overview", ""))[:2000],
            "jellyfin_id": item["Id"],
            "layers": ["LOCAL"],
        },
    )


def saved_sources(db, title):
    """Copies saved on the house disk (Files → Films) play like any other version, first."""
    from .playback import probe_file

    sources = []
    records = db.scalars(
        select(Record).where(
            Record.kind == "cinema.local_media",
            Record.deleted_at.is_(None),
            Record.data["media_id"].as_string() == title.id,
            Record.data["state"].as_string() == "ready",
        )
    )
    for record in records:
        try:
            path = saved_path(record.data.get("_path"))
            inspection = record.data.get("_inspection") or probe_file(path, timeout=20)
        except MediaError:
            continue
        if not record.data.get("_inspection"):
            record.data = {**record.data, "_inspection": inspection}
        sources.append(
            {
                "id": new_id(),
                "release": path.name[:300],
                "layer": "LOCAL",
                "local_record": record.id,
                "inspection": inspection,
                "size": path.stat().st_size,
                "state": "preflight_usable",
            }
        )
    return sources


def saved_path(value):
    """A saved film's file (or a web video's), only inside the house media folder (or the web
    videos' one) and never through a link."""
    from .fetcher_web import DIR

    path = Path(value or "")
    roots = ((Path(settings.data_root) / "media").resolve(), DIR.resolve())
    if not path.is_file() or path.is_symlink() or not any(path.resolve().is_relative_to(r) for r in roots):
        raise MediaError("MEDIA_UNAVAILABLE", "This saved film is no longer on the house disk.", "discover")
    return path


@router.get("/library")
def local_library(
    kind: Literal["movie", "series"] = "movie",
    offset: int = Query(0, ge=0, le=100000),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    allowed(actor)
    try:
        jf = Jellyfin(integration_config(db, "jellyfin"))
    except MediaError as exc:
        if exc.code == "JELLYFIN_UNCONFIGURED":  # no local library: an empty shelf, not an error
            return {"items": [], "next_offset": None}
        failure(exc)
    db.commit()  # no connection held while Jellyfin answers
    result = call(jf.library, kind, offset, 30)
    from .cinema_library import reconcile_index

    rows = [public_title(local_title(db, item)) for item in result.get("Items", [])[:30]]
    reconcile_index(db, result.get("Items", []))
    states = {
        state.media_id: state
        for state in db.scalars(
            select(CinemaState).where(
                CinemaState.owner_id == actor.id, CinemaState.media_id.in_([row["id"] for row in rows])
            )
        )
    }
    rows = [
        {
            **row,
            **(states[row["id"]].data if row["id"] in states else {}),
            "version": states[row["id"]].version if row["id"] in states else None,
        }
        for row in rows
    ]
    db.commit()
    return {
        "items": rows,
        "next_offset": offset + 30 if result.get("TotalRecordCount", 0) > offset + 30 else None,
    }


@router.get("/catalogs")
def catalogs(kind: Literal["movie", "series", "anime"] = "movie", actor: Actor = Depends(require_actor)):
    allowed(actor)
    return {"items": call((AnimeCatalog() if kind == "anime" else Cinemeta()).catalogs, kind)}


@router.get("/browse")
def browse(
    kind: Literal["movie", "series", "anime"] = "movie",
    catalog: Literal["top", "year", "imdbRating"] = "top",
    genre: str = Query("", max_length=40),
    offset: int = Query(0, ge=0, le=10000),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    allowed(actor)
    result = call((AnimeCatalog() if kind == "anime" else Cinemeta()).browse, kind, catalog, genre, offset)
    rows = [
        public_title(
            upsert_title(
                db,
                item["canonical_id"],
                item["title"],
                item.get("kind", kind),
                {**item, "layers": ["ON_DEMAND"]},
            )
        )
        for item in result["items"]
    ]
    db.commit()
    return {
        "items": rows,
        "next_offset": result["next_offset"],
        "provider": "MyAnimeList" if kind == "anime" else "Cinemeta",
        "availability": "sources_require_validation",
    }


def stored(db, rows):
    """Catalogue entries become titles (openable, with posters). One query for the page; only
    new titles, or known ones missing a field, are written, and committed here. Watch loads its
    rows side by side, so two may save the same new title at once: the loser (duplicate or
    deadlock) starts again and finds it saved."""
    from sqlalchemy.exc import OperationalError

    for attempt in range(3):
        try:
            titles = stored_once(db, rows)
            db.commit()
            return titles
        except (IntegrityError, OperationalError):
            db.rollback()
            if attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))


def stored_once(db, rows):
    known = {
        row.canonical_id: row
        for row in db.scalars(
            select(CinemaTitle).where(CinemaTitle.canonical_id.in_([item["canonical_id"] for item in rows]))
        )
    }
    titles = []
    for item in rows:
        row = known.get(item["canonical_id"])
        data = {**item, "layers": ["ON_DEMAND"]}
        if row is None or any(key not in row.data for key in item):
            row = upsert_title(db, item["canonical_id"], item["title"], item["kind"], data)
            known[item["canonical_id"]] = row
        titles.append(public_title(row))
    return titles


@router.get("/explore")
def explore(
    kind: Literal["movie", "series", "anime"] = "movie",
    q: str = Query("", max_length=200),
    year_from: int | None = Query(None, ge=1880, le=2100),
    year_to: int | None = Query(None, ge=1880, le=2100),
    genre: str = Query("", max_length=130),
    tag: str = Query("", max_length=200),
    person: str = Query("", max_length=490),  # up to four names, "|" between them
    award: str = Query("", max_length=40),
    max_minutes: int | None = Query(None, ge=1, le=600),
    max_episodes: int | None = Query(None, ge=1, le=3000),
    airing: bool | None = None,
    season: Literal["", "WINTER", "SPRING", "SUMMER", "FALL"] = "",
    sort: str = Query("known", max_length=10),
    offset: int = Query(0, ge=0, le=100000),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """Every filter at once over the local catalogue indexes (cinema_explore.py)."""
    from . import cinema_explore

    allowed(actor)
    result = cinema_explore.discover(
        kind,
        sort=sort,
        offset=offset,
        q=q.strip(),
        year_from=year_from,
        year_to=year_to,
        genre=genre,
        tag=tag,
        person=person.strip(),
        award=award,
        max_minutes=max_minutes,
        max_episodes=max_episodes,
        airing=airing if isinstance(airing, bool) else None,
        season=season if isinstance(season, str) else "",
    )
    local = bool(cinema_explore.index(kind)) or kind == "anime"
    if not local and not (q.strip() or year_from or year_to or tag or person or award or max_minutes):
        # No local index for this kind yet (a new house before its first build, or series
        # while Wikidata is down): the popular list from Cinemeta, cached 15 min.
        try:
            result = {**Cinemeta().browse(kind, "top", genre.split(",")[0], offset), "total": None}
        except MediaError:
            result = {"items": [], "next_offset": None, "total": 0}
    items = stored(db, result["items"])
    return {**result, "items": items}


@router.get("/titles/{identity}/similar")
def similar_titles(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """ "More like this" for a title: for anime, what MyAnimeList members recommend (else
    similar themes and studio) plus the same franchise; for films and series, the same
    director, cast and themes from the local film index. Nothing is generated by a model."""
    from . import cinema_explore

    allowed(actor)
    title = db.get(CinemaTitle, identity)
    if not title:
        raise HTTPException(404, "Title not found")
    canonical, source, related = title.canonical_id, "themes", []
    db.commit()  # give the connection back before asking an outside service
    if canonical.startswith("mal:"):
        items = []
        try:
            for pick in AnimeCatalog().recommendations(canonical):
                if row := cinema_explore.find("anime", pick):
                    items.append(cinema_explore.catalog_item(row))
            source = "myanimelist" if items else source
        except MediaError:
            pass  # MyAnimeList unreachable: similar themes below
        known = {item["canonical_id"] for item in items}
        items += [x for x in cinema_explore.similar("anime", canonical) if x["canonical_id"] not in known]
        related = cinema_explore.franchise(canonical)
    else:
        items = cinema_explore.similar("series" if title.kind == "series" else "movie", canonical)
    result = {"items": stored(db, items[:12]), "franchise": stored(db, related), "source": source}
    db.commit()
    return result


@router.get("/for-you")
def for_you(
    kind: Literal["movie", "series", "anime"] = "movie",
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """Titles like the last five this person watched in this tab (films, series or anime)."""
    from . import cinema_explore

    allowed(actor)
    watched = db.execute(
        select(CinemaTitle)
        .join(CinemaState, CinemaState.media_id == CinemaTitle.id)
        .where(CinemaState.owner_id == actor.id, CinemaState.last_watched_at.is_not(None))
        .order_by(CinemaState.last_watched_at.desc())
        .limit(60)
    ).scalars()
    seen = []
    for title in watched:
        if title.data.get("parent_id"):  # an episode counts as its series
            title = db.get(CinemaTitle, title.data["parent_id"]) or title
        anime = title.canonical_id.startswith("mal:")
        mine = anime if kind == "anime" else not anime and title.kind == kind
        if mine and title.canonical_id not in seen:
            seen.append(title.canonical_id)
    items = stored(db, cinema_explore.for_you(kind, seen)) if seen else []
    db.commit()
    return {"items": items, "based_on": len(seen[:5])}


@router.get("/explore/facets")
def explore_facets(
    kind: Literal["movie", "series", "anime"] = "movie", actor: Actor = Depends(require_actor)
):
    from . import cinema_explore

    allowed(actor)
    return cinema_explore.facets(kind)


@router.get("/explore/people")
def explore_people(
    kind: Literal["movie", "series", "anime"] = "movie",
    q: str = Query("", max_length=120),
    actor: Actor = Depends(require_actor),
):
    from . import cinema_explore

    allowed(actor)
    return {"items": cinema_explore.people(kind, q)}


@router.get("/collections")
def collections(
    kind: Literal["movie", "series", "anime"] = "movie",
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """This week's collections for the Watch home (cinema_collections.py)."""
    from . import cinema_collections

    allowed(actor)
    return {"items": cinema_collections.this_week(kind)}


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    kind: Literal["movie", "series", "anime"] = "movie",
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    allowed(actor)
    items, errors = {}, []
    db.commit()  # no connection held while the catalogues answer
    try:
        for item in (AnimeCatalog() if kind == "anime" else Cinemeta()).search(q, kind):
            row = upsert_title(
                db, item["canonical_id"], item["title"], item["kind"], {**item, "layers": ["ON_DEMAND"]}
            )
            items[row.id] = public_title(row)
    except MediaError as exc:
        errors.append(exc.public())
    try:
        for item in [] if kind == "anime" else Jellyfin(integration_config(db, "jellyfin")).search(q):
            if ("series" if item.get("Type") == "Series" else "movie") != kind:
                continue
            row = local_title(db, item)
            items[row.id] = public_title(row)
    except MediaError as exc:
        errors.append(exc.public())
    db.commit()
    return {"items": list(items.values())[:30], "errors": errors}


@router.get("/titles/{identity}")
def details(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    title = db.get(CinemaTitle, identity)
    if not title:
        raise HTTPException(404, "Title not found")
    if title.kind == "series":
        db.commit()  # no connection held while the catalogue answers
        if title.canonical_id.startswith("tt"):
            data = call(Cinemeta().details, title.canonical_id, title.kind)
            title.data = {**title.data, "episodes": data.get("episodes", [])}
        elif title.canonical_id.startswith("mal:"):
            data = call(AnimeCatalog().details, title.canonical_id, title.kind)
            title.data = {**title.data, **data}
        elif title.data.get("jellyfin_id"):
            jf = call(Jellyfin, integration_config(db, "jellyfin"))
            entries = call(jf.episodes, title.data["jellyfin_id"])
            title.data = {
                **title.data,
                "episodes": [
                    {
                        "id": e["Id"],
                        "title": e.get("Name"),
                        "season": e.get("ParentIndexNumber"),
                        "episode": e.get("IndexNumber"),
                    }
                    for e in entries
                ],
            }
        db.commit()
    result = public_title(title)
    personal = db.scalar(
        select(CinemaState).where(CinemaState.owner_id == actor.id, CinemaState.media_id == title.id)
    )
    result["progress"] = personal.data if personal else {}
    if title.kind == "series":
        states = {
            (episode.data.get("season"), episode.data.get("episode")): state.data
            for state, episode in db.execute(
                select(CinemaState, CinemaTitle)
                .join(CinemaTitle, CinemaTitle.id == CinemaState.media_id)
                .where(
                    CinemaState.owner_id == actor.id,
                    CinemaTitle.kind == "episode",
                    CinemaTitle.data["parent_id"].as_string() == title.id,
                )
            )
        }
        result["episodes"] = [
            {**episode, "progress": states.get((episode.get("season"), episode.get("episode")), {})}
            for episode in result.get("episodes", [])
        ]
    return result


@router.get("/preferences")
def preferences(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    row = db.get(CinemaPreference, actor.id)
    return effective_request(row.data if row else {}, {})


@router.put("/preferences")
def set_preferences(body: Preferences, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    values = body.model_dump(exclude_unset=True)
    if "audio_track" in values or "subtitle_track" in values or "allow_video_transcode" in values:
        raise HTTPException(422, "Track IDs belong to one source, not permanent preferences")
    row = db.get(CinemaPreference, actor.id)
    if not row:
        row = CinemaPreference(owner_id=actor.id, data={})
        db.add(row)
    row.data = {**row.data, **values}
    emit(db, "cinema.preferences", {}, user_id=actor.id)
    db.commit()
    return effective_request(row.data, {})


@router.get("/devices")
def devices(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    config = integration_config(db, "home_assistant")
    setup = (
        [
            {
                "name": "Hisense TV",
                "reason": "Native TV playback is not configured; use the Chromecast or finish TV setup.",
            }
        ]
        if config.get("enabled") and "vidaa" in config.get("device_id", "")
        else []
    )
    return {
        "items": [
            public_device(d, actor.role == "admin") for d in db.scalars(select(CinemaDevice).limit(50))
        ],
        "setup_required": setup,
    }


@router.post("/devices")
def create_device(body: DeviceInput, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    row = CinemaDevice(
        id=new_id(),
        name=body.name,
        adapter=body.adapter,
        address=body.address,
        session_id=body.session_id,
        capabilities=body.capabilities,
        observation={"state": "unverified"},
    )
    db.add(row)
    db.commit()
    return public_device(row)


@router.put("/devices/{identity}")
def update_device(
    identity: str, body: DeviceInput, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)
):
    row = db.scalar(select(CinemaDevice).where(CinemaDevice.id == identity).with_for_update())
    if not row:
        raise HTTPException(404, "Device not found")
    if row.owner_workflow:
        raise HTTPException(409, "Stop current playback before changing this device configuration")
    if body.version != row.version:
        raise HTTPException(409, "Device changed")
    row.name, row.adapter, row.address, row.session_id = (
        body.name,
        body.adapter,
        body.address,
        body.session_id,
    )
    row.capabilities, row.observation, row.observed_at = body.capabilities, {"state": "unverified"}, None
    row.version += 1
    db.commit()
    return public_device(row)


@router.delete("/devices/{identity}")
def delete_device(identity: str, actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    """Forget a device (a TV replaced, a speaker given away). Past films keep their history."""
    from sqlalchemy import update

    from .music_outputs import output_choice, save_output_choice

    row = db.scalar(select(CinemaDevice).where(CinemaDevice.id == identity).with_for_update())
    if not row:
        raise HTTPException(404, "Device not found")
    if row.owner_workflow:
        raise HTTPException(409, "Stop what's playing on it first")
    db.execute(update(CinemaWorkflow).where(CinemaWorkflow.device_id == identity).values(device_id=None))
    if output_choice(db).get("device_id") == identity:  # music was playing there: back to this computer
        save_output_choice(db, device_id=None, grant=None, problem=None)
    db.delete(row)
    db.commit()
    try:
        from .tv_remote import set_paired

        set_paired(identity, False)
    except Exception:
        pass
    return {"status": "deleted", "id": identity}


def inspect_destination(db, device):
    if device.adapter == "jellyfin":
        jf = Jellyfin(integration_config(db, "jellyfin"))
        sessions = jf.sessions()
        session = next((s for s in sessions if s.get("Id") == device.session_id), None)
        if not session:
            raise MediaError(
                "TARGET_OFFLINE",
                "The configured Jellyfin player session is unavailable.",
                "destination",
                True,
            )
        player = session.get("PlayState", {})
        observation = {
            "state": "paused"
            if player.get("IsPaused")
            else "active"
            if session.get("NowPlayingItem")
            else "idle",
            "item_id": (session.get("NowPlayingItem") or {}).get("Id"),
            "position": (player.get("PositionTicks") or 0) / 10_000_000,
            "audio_index": player.get("AudioStreamIndex"),
            "subtitle_index": player.get("SubtitleStreamIndex"),
            "check_in": session.get("LastPlaybackCheckIn"),
            "session_id": session.get("Id"),
            "volume": player.get("VolumeLevel"),
            "volume_supported": "SetVolume" in session.get("SupportedCommands", []),
        }
    elif device.adapter == "dlna":
        raise MediaError(
            "TARGET_INCOMPATIBLE",
            "This speaker or TV plays music only; choose a Cast or Jellyfin screen for films.",
            "destination",
        )
    else:
        from .cinema_cast import cast_observe

        observation = cast_observe(device.address)
    device.observed_at = utcnow()
    device.observation = observation
    device.capabilities = {
        **device.capabilities,
        "inspected_at": device.observed_at.isoformat(),
        "confidence": "configured_profile_live_transport",
    }
    db.flush()
    return observation


@router.post("/devices/{identity}/inspect")
def inspect_device(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    device = db.get(CinemaDevice, identity)
    if not device:
        raise HTTPException(404, "Device not found")
    try:
        inspect_destination(db, device)
        db.commit()
    except MediaError as exc:
        device.observed_at, device.observation = utcnow(), {"state": "unavailable", "error": exc.public()}
        db.commit()
        return {**public_device(device), "error": exc.public()}
    return public_device(device)


def source_summary(source, plan):
    media = source["inspection"]
    return {
        "id": source["id"],
        "release": source["release"],
        "layer": source["layer"],
        "size": source.get("size"),
        "duration": media.get("duration"),
        "height": media["video"]["height"],
        "resolution": resolution(media["video"]),  # 1080 for a 1920×800 crop: what the label says
        "hdr": media["video"]["hdr"],
        "video_codec": media["video"]["codec"],
        "audio": media["audio"],
        "subtitles": media["subtitles"],
        "mode": plan["mode"],
        "warnings": plan["warnings"],
        "evidence": media["evidence"],
        "rd_cached": bool(source.get("rd_cached")),
        "cache_evidence": source.get("cache_evidence", "unknown"),
        "seeders_claim": source.get("seeders_claim"),
        "provider": source.get("provider"),
        "provider_order": source.get("provider_order"),
    }


def freeze_choices(row, device):
    from .cinema_suggest import rank_inspected

    candidates = []
    sources = row.data.get("_sources", [])
    if device:
        # Ranked by the household's defaults; taste never rejects, only hard limits do.
        for source, plan, score, reasons in rank_inspected(sources, device.capabilities, row.data["request"]):
            candidates.append(
                {
                    **source_summary(source, plan),
                    "score": round(score, 2),
                    "why": reasons,
                    "suggested_audio": plan["audio"],
                    "suggested_subtitle": plan["subtitle"],
                    "subtitle_mode": plan["subtitle_mode"],
                }
            )
    else:
        plan = {
            "mode": "destination_not_selected",
            "warnings": ["Media inspected; destination compatibility has not been checked."],
        }
        candidates = [
            source_summary(source, plan)
            for source in sorted(sources, key=source_order)
            if source.get("inspection") and not source.get("error")
        ]
    chosen = row.data.get("_validation_selection", [])
    if len(chosen) == 1:  # a release the resident picked by hand leads
        candidates.sort(key=lambda c: c["id"] != chosen[0])
    return {
        "id": new_id(),
        "revision": row.version + 1,
        "expires_at": (utcnow() + timedelta(minutes=10)).isoformat(),
        "candidates": [{**c, "rank": index + 1} for index, c in enumerate(candidates[:5])],
    }


def source_order(source):
    height = (
        source.get("inspection", {}).get("video", {}).get("height")
        or source.get("height")
        or source.get("height_claim")
        or 0
    )
    if source.get("provider") == "stream_addon":
        return (
            bool(source.get("error") and not source["error"].get("retryable", False)),
            source.get("rd_cached") is False,  # debrid-cached versions first, then torrents
            source.get("provider_order", 0),
            0,
            0,
            source["id"],
        )
    return (
        bool(source.get("error") and not source["error"].get("retryable", False)),
        not (source.get("rd_cached") or source.get("layer") == "LOCAL"),
        -height,
        -(source.get("seeders_claim") or 0),
        source.get("size") or 2**64,
        source["id"],
    )


def exact_cached_file(rd, torrent_id, season, episode, title="", year=None):
    info = rd.info(torrent_id)
    if info.get("status") != "downloaded":
        return False
    files = info.get("files", [])
    if episode is not None:
        selected = exact_episode_file(files, season, episode)
    else:
        try:
            selected = exact_movie_file(files, title, year)
        except MediaError:
            return False
    ready = [f for f in files if f.get("selected")]
    return bool(
        selected.get("selected")
        and len(ready) == len(info.get("links", []))
        and any(
            str(f["id"]) == str(selected["id"]) and bool(info["links"][index])
            for index, f in enumerate(ready)
        )
    )


def provisional_source(source):
    return {
        key: source.get(key)
        for key in (
            "id",
            "release",
            "layer",
            "state",
            "size",
            "height_claim",
            "seeders_claim",
            "rd_cached",
            "cache_evidence",
            "evidence",
            "error",
            "rd_status",
            "rd_progress",
            "provider",
            "provider_order",
        )
    }


@router.post("/discover")
def discover(body: Discover, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    existing = db.scalar(
        select(CinemaWorkflow).where(
            CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.idempotency_key == body.idempotency_key
        )
    )
    if existing:
        return public_workflow(existing)
    title, device = (
        db.get(CinemaTitle, body.media_id),
        db.get(CinemaDevice, body.device_id) if body.device_id else None,
    )
    if not title or (body.device_id and not device):
        raise HTTPException(404, "Title or destination not found")
    if title.kind == "episode":
        season, episode = title.data.get("season"), title.data.get("episode")
        if (body.season is not None and body.season != season) or (
            body.episode is not None and body.episode != episode
        ):
            failure(
                MediaError("EPISODE_MISMATCH", "The selected episode does not match this title.", "identify")
            )
        title = db.get(CinemaTitle, title.data.get("parent_id"))
        if not title or title.kind != "series":
            failure(
                MediaError(
                    "EPISODE_AMBIGUOUS",
                    "The parent series is unavailable. Select the exact series again.",
                    "identify",
                )
            )
        body = body.model_copy(update={"season": season, "episode": episode})
    if title.kind == "series" and (body.season is None or body.episode is None):
        failure(MediaError("EPISODE_AMBIGUOUS", "Choose the exact season and episode first.", "identify"))
    if device:
        call(inspect_destination, db, device)
    if body.queue_id:
        from .models import Record

        queued = db.get(Record, body.queue_id)
        queued_title = (
            db.get(CinemaTitle, queued.data["media_id"])
            if queued
            and queued.owner_id == actor.id
            and queued.kind == "cinema.queue"
            and not queued.deleted_at
            else None
        )
        if (
            not queued_title
            or (
                (queued_title.data.get("parent_id") if queued_title.kind == "episode" else queued_title.id)
                != title.id
            )
            or queued.data.get("season") != body.season
            or queued.data.get("episode") != body.episode
        ):
            raise HTTPException(409, "This queue entry does not match the requested title and episode")
    pref = db.get(CinemaPreference, actor.id)
    request = effective_request(pref.data if pref else {}, body.preferences.model_dump(exclude_unset=True))
    if not request.get("languages"):
        from .cinema_suggest import understood
        from .house_settings import get_house_settings

        house = get_house_settings(db)["language"]
        request["languages"] = understood(
            {"languages": [request.get("subtitle_language"), request.get("audio_language"), house, "en"]}
        )
    watch_title = title
    if title.kind == "series":
        watch_title = upsert_title(
            db,
            f"{title.canonical_id}:{body.season}:{body.episode}",
            f"{title.title} · S{body.season:02}E{body.episode:02}",
            "episode",
            {
                "parent_id": title.id,
                "season": body.season,
                "episode": body.episode,
                "layers": title.data.get("layers", []),
            },
        )
    row = CinemaWorkflow(
        id=new_id(),
        owner_id=actor.id,
        media_id=watch_title.id,
        device_id=device.id if device else None,
        idempotency_key=body.idempotency_key,
        data={
            "_requested_position": body.position,
            "_queue_id": body.queue_id,
            "request": request,
            "_initial_request": request,
            "_destination_later": not bool(device),
            "_authorization_session": actor.session_hash,
            "season": body.season,
            "episode": body.episode,
            "_boot_id": boot_identity(),
            "_autoplay_expires_at": (utcnow() + timedelta(hours=2)).isoformat(),
            "_autoplay_depth": 0,
        },
    )
    saved_state = db.scalar(
        select(CinemaState).where(CinemaState.owner_id == actor.id, CinemaState.media_id == watch_title.id)
    )
    if saved_state and saved_state.data.get("preferred_release"):
        row.data = {**row.data, "preferred_release": saved_state.data["preferred_release"]}
    sources, errors = ([] if body.cloud_id else saved_sources(db, watch_title)), []
    if title.data.get("jellyfin_id") and not body.cloud_id:
        try:
            jf = Jellyfin(integration_config(db, "jellyfin"))
            item_id = title.data["jellyfin_id"]
            if title.kind == "series":
                matches = [
                    e
                    for e in jf.episodes(item_id)
                    if e.get("ParentIndexNumber") == body.season and e.get("IndexNumber") == body.episode
                ]
                if len(matches) != 1:
                    raise MediaError(
                        "EPISODE_AMBIGUOUS", "The Jellyfin episode mapping is not unique.", "identify"
                    )
                item_id = matches[0]["Id"]
            for source in jf.playback_info(item_id).get("MediaSources", [])[:10]:
                sources.append(
                    {
                        "id": new_id(),
                        "release": source.get("Name", title.title)[:300],
                        "layer": "LOCAL",
                        "jellyfin_item": item_id,
                        "jellyfin_source": source["Id"],
                        "inspection": jellyfin_inspection(source),
                        "size": source.get("Size"),
                        "state": "preflight_usable",
                    }
                )
        except MediaError as exc:
            errors.append(exc.public())
    if title.canonical_id.startswith(("tt", "mal:")) and not body.cloud_id:
        try:
            from .cinema_sources import StreamAddon

            canonical = title.canonical_id
            if canonical.startswith("mal:"):
                from .anime_catalog import resolve_stream

                canonical = resolve_stream(canonical, body.episode)
            provider = (
                StreamAddon(integration_config(db, "stream_addon"))
                if integration_config(db, "stream_addon").get("enabled")
                else Comet(integration_config(db, "comet"))
            )
            for source in provider.streams(canonical, title.kind, body.season, body.episode)[:300]:
                if (source["info_hash"], source.get("file_index")) not in {
                    (s.get("info_hash"), s.get("file_index")) for s in sources
                }:
                    sources.append({**source, "id": new_id(), "layer": "ON_DEMAND"})
        except MediaError as exc:
            errors.append(exc.public())
    rd_config = {}
    try:
        rd_config = integration_config(db, "real_debrid")
        if rd_config.get("enabled") and (
            body.cloud_id or not integration_config(db, "stream_addon").get("enabled")
        ):
            rd = RealDebrid(rd_config)
            inventory = rd.inventory()
            existing_torrents = {
                t.get("hash", "").lower(): t
                for t in sorted(inventory, key=lambda item: item.get("status") == "downloaded")
            }
            if body.cloud_id:
                selected = next((t for t in inventory if cloud_id(t["id"]) == body.cloud_id), None)
                if not selected or not selected.get("hash"):
                    raise MediaError(
                        "SOURCE_EXPIRED",
                        "This cloud entry is unavailable. Refresh cloud inventory and choose again.",
                        "discover",
                    )
                sources.append(
                    {
                        "id": new_id(),
                        "release": str(selected.get("filename", "Cloud media"))[:300],
                        "layer": "RD_CLOUD",
                        "info_hash": selected["hash"].lower(),
                        "torrent_id": selected["id"],
                        "account_owned": False,
                        "state": "discovered",
                        "size": selected.get("bytes"),
                    }
                )
                row.data = {**row.data, "_explicit_cloud_mapping": True}
            to_check = []
            for source in sources:
                existing_torrent = existing_torrents.get(source.get("info_hash"))
                if existing_torrent:
                    source.update(torrent_id=existing_torrent["id"], layer="RD_CLOUD", account_owned=False)
                    if existing_torrent.get("status") == "downloaded" and len(to_check) < 5:
                        to_check.append(source)

            def cached_file(source):
                try:
                    return exact_cached_file(
                        rd,
                        source["torrent_id"],
                        body.season,
                        body.episode,
                        title.title,
                        title.data.get("year"),
                    )
                except MediaError:
                    return None

            with ThreadPoolExecutor(max_workers=5) as pool:  # independent account lookups
                for source, found in zip(to_check, pool.map(cached_file, to_check)):
                    if found is not None:
                        source["rd_cached"] = found
                    source["cache_evidence"] = "account_selected_file" if found else "unknown"
    except MediaError as exc:
        errors.append(exc.public())
    if rd_config.get("enabled"):
        fingerprint = hashlib.sha256(
            (rd_config.get("token") or rd_config.get("api_key") or "").encode()
        ).hexdigest()[:24]
        known = {}
        prior = db.scalars(
            select(CinemaWorkflow)
            .where(
                CinemaWorkflow.owner_id == actor.id,
                CinemaWorkflow.media_id == watch_title.id,
                CinemaWorkflow.updated_at > utcnow() - timedelta(minutes=15),
            )
            .order_by(CinemaWorkflow.updated_at.desc())
            .limit(30)
        )
        for previous in prior:
            if previous.data.get("_rd_account_key") != fingerprint:
                continue
            for old in previous.data.get("_sources", []):
                if old.get("error", {}).get("code") == "SOURCE_REJECTED" and old.get("info_hash"):
                    known.setdefault(old["info_hash"], old["error"])
        for source in sources:
            if source.get("provider") == "stream_addon":
                continue
            rejection = known.get(source.get("info_hash"))
            # A fresh account entry supersedes a previous failed add, not a failed unrestrict.
            if rejection and not (source.get("torrent_id") and rejection.get("operation") == "add_magnet"):
                source.update(
                    error=rejection, state="rejected", rd_cached=False, cache_evidence="provider_rejected"
                )
    sources = sorted(sources, key=source_order)[:300]
    row.data = {
        **row.data,
        "_sources": sources,
        "provisional": [provisional_source(s) for s in sources if not s.get("inspection")],
        "error": errors[0] if errors else None,
    }
    db.add(row)
    db.flush()
    choices = freeze_choices(row, device)
    return save_workflow(
        db, row, "awaiting_choice" if choices["candidates"] else "discovered", {"choice_set": choices}
    )


@router.get("/current")
def current_playback(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    rows = db.execute(
        select(CinemaWorkflow, CinemaDevice)
        .join(CinemaDevice, CinemaDevice.id == CinemaWorkflow.device_id)
        .where(
            CinemaWorkflow.owner_id == actor.id,
            # A control command keeps the film on screen until the receiver confirms it.
            CinemaWorkflow.state.in_(["playing_observed", "paused", "command_sent"]),
            CinemaDevice.owner_workflow == CinemaWorkflow.id,
        )
        .order_by(CinemaWorkflow.updated_at.desc())
        .limit(10)
    )
    for row, device in rows:
        checkpoint = row.data.get("checkpoint") or {}
        if (
            checkpoint.get("at", "") < (utcnow() - timedelta(seconds=30)).isoformat()
            or row.data.get("observation", {}).get("identity") != "matched"
        ):
            continue
        if not device.observed_at or device.observed_at < utcnow() - timedelta(seconds=30):
            continue
        title = db.get(CinemaTitle, row.media_id)
        if not title:
            continue
        return {
            "current": {
                "id": row.id,
                "title": title.title,
                "media_id": row.media_id,
                "device_id": row.device_id,
                "device": device.name,
                "version": row.version,
                "state": row.state
                if row.state != "command_sent"
                else row.data["observation"].get("shown_state", "playing_observed"),
                "checkpoint": checkpoint,
                "observation": {
                    k: v
                    for k, v in row.data["observation"].items()
                    if k in {"state", "identity", "volume", "volume_supported"}
                },
                "duration": (row.data.get("plan") or {}).get("duration"),
                "can_seek": bool(
                    device.capabilities.get("seek", False) and (row.data.get("plan") or {}).get("duration")
                ),
                "volume_supported": device.observation.get("volume_supported", False),
                "volume": device.observation.get("volume"),
            }
        }
    # Not playing yet: a title on its way to a screen still belongs in the Player.
    starting = db.execute(
        select(CinemaWorkflow, CinemaDevice)
        .join(CinemaDevice, CinemaDevice.id == CinemaWorkflow.device_id)
        .where(
            CinemaWorkflow.owner_id == actor.id,
            CinemaWorkflow.state.in_(["preparing", "command_sent"]),
            CinemaDevice.owner_workflow == CinemaWorkflow.id,
            CinemaWorkflow.updated_at > utcnow() - timedelta(minutes=30),
        )
        .order_by(CinemaWorkflow.updated_at.desc())
        .limit(1)
    ).first()
    if starting:
        row, device = starting
        title = db.get(CinemaTitle, row.media_id)
        download = row.data.get("download") or {}
        return {
            "current": {
                "id": row.id,
                "title": title.title if title else None,
                "media_id": row.media_id,
                "device_id": row.device_id,
                "device": device.name,
                "version": row.version,
                "state": row.state,
                "phase": "sending" if row.state == "command_sent" else "preparing",
                "progress": download.get("bytes") / download["total"]
                if download.get("total") and download.get("bytes")
                else None,
                "checkpoint": {},
                "observation": {},
                "duration": (row.data.get("plan") or {}).get("duration"),
                "can_seek": False,
                "volume_supported": False,
                "volume": None,
            }
        }
    return {"current": None}


def watched_through(data):
    duration, position = data.get("duration") or 0, data.get("position") or 0
    return bool(data.get("watched")) or (duration > 0 and position >= duration * 0.92)


@router.get("/shelves")
def shelves(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Continue watching (one card per series: resume the episode or start the next one),
    the watchlist and recently watched, for the Watch page's shelves."""
    from .files import film_kind

    allowed(actor)
    rows = list(
        db.execute(
            select(CinemaState, CinemaTitle)
            .join(CinemaTitle, CinemaTitle.id == CinemaState.media_id)
            .where(CinemaState.owner_id == actor.id)
            .order_by(CinemaState.last_watched_at.desc(), CinemaState.id)
            .limit(200)
        )
    )
    parents = {}
    continuing, seen, watchlist, recent = [], set(), [], []
    for state, title in rows:
        data = state.data or {}
        parent_id = title.data.get("parent_id")
        if parent_id and parent_id not in parents:
            parents[parent_id] = db.get(CinemaTitle, parent_id)
        parent = parents.get(parent_id)
        card = {
            **public_title(title),
            "media_id": title.id,
            "tab": tab_of(film_kind(title, parent)),  # Watch's Films / Series / Anime
            "version": state.version,
            "position": data.get("position") or 0,
            "duration": data.get("duration"),
            "last_watched_at": state.last_watched_at,
        }
        if parent:
            card.update(
                series_id=parent.id,
                series_title=parent.title,
                poster=card.get("poster") or public_title(parent).get("poster"),
            )
        if data.get("watchlist"):
            watchlist.append(card)
        if not state.last_watched_at:
            continue
        if len(recent) < 20:
            recent.append(card)
        key = parent.id if parent else title.id
        if key in seen:
            continue
        seen.add(key)
        if not watched_through(data) and card["position"] > 30:
            continuing.append({**card, "action": "resume"})
        elif parent and isinstance(title.data.get("season"), int):
            episodes = sorted(
                (e for e in parent.data.get("episodes", []) if isinstance(e.get("episode"), int)),
                key=lambda e: (e.get("season") or 0, e["episode"]),
            )
            current = (title.data["season"], title.data.get("episode") or 0)
            upcoming = [
                e for e in episodes if (e.get("season") or 0) > 0 and (e["season"], e["episode"]) > current
            ]
            if upcoming:
                continuing.append(
                    {
                        **card,
                        "action": "next",
                        "media_id": parent.id,
                        "season": upcoming[0]["season"],
                        "episode": upcoming[0]["episode"],
                        "episode_title": upcoming[0].get("title"),
                        "position": 0,
                    }
                )
    return {
        "continue": continuing[:20],
        "watchlist": watchlist[:40],
        "recent": recent,
        "saved": saved_on_disk(db),
        "sources": connected_sources(db),
    }


def saved_on_disk(db):
    """Films and episodes saved on the house disk, one card per title (Files → Films)."""
    from .files import library_films

    cards, seen = [], set()
    for film in sorted(library_films(db), key=lambda f: str(f["created_at"]), reverse=True):
        if film.get("media_id") and film["media_id"] not in seen:
            seen.add(film["media_id"])
            cards.append(
                {
                    "id": film["media_id"],
                    "media_id": film["media_id"],
                    "title": film["title"],
                    "poster": film["poster"],
                    "year": film["year"],
                    "tab": tab_of(film["type"]),
                }
            )
    return cards[:20]


def tab_of(kind):
    """files.film_kind's film / series / anime as Watch's tabs (movie / series / anime)."""
    return "movie" if kind == "film" else kind


def connected_sources(db):
    """Where films can come from here, so Watch can show them (no secrets, only on/off)."""
    from .models import Integration

    def on(name):
        row = db.get(Integration, name)
        return bool(row and row.enabled)

    return {
        "jellyfin": on("jellyfin"),
        "real_debrid": on("real_debrid"),
        "streams": on("stream_addon") or on("comet"),
    }


@router.get("/workflows")
def workflows(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    rows = db.scalars(
        select(CinemaWorkflow)
        .where(CinemaWorkflow.owner_id == actor.id)
        .order_by(CinemaWorkflow.updated_at.desc())
        .limit(20)
    )
    return {
        "items": [
            {
                **public_workflow(row),
                "title": (
                    db.get(CinemaTitle, row.media_id).title if db.get(CinemaTitle, row.media_id) else None
                ),
            }
            for row in rows
        ]
    }


@router.get("/downloads")
def downloads(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    rows = db.scalars(
        select(CinemaWorkflow)
        .where(CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.data["_kind"].as_string() == "save_local")
        .order_by(CinemaWorkflow.updated_at.desc())
        .limit(50)
    )
    return {
        "items": [
            {
                **public_workflow(row),
                "title": getattr(db.get(CinemaTitle, row.media_id), "title", None) or "Film",
            }
            for row in rows
        ]
    }


@router.get("/workflows/{identity}/sources")
def source_page(
    identity: str,
    offset: int = Query(0, ge=0, le=100),
    resolution: int | None = Query(default=None, ge=0, le=4320),
    limit: int = Query(20, ge=1, le=20),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    row = own_workflow(db, actor, identity)
    offset = offset if isinstance(offset, int) else 0
    limit = limit if isinstance(limit, int) else 20
    resolution = resolution if isinstance(resolution, int) else None
    sources = row.data.get("_sources", [])

    def height(source):
        return source.get("inspection", {}).get("video", {}).get("height") or source.get("height_claim") or 0

    available = sorted({height(source) for source in sources}, reverse=True)
    filtered = [source for source in sources if resolution is None or height(source) == resolution]
    return {
        "items": [
            {**provisional_source(source), "height": height(source)}
            for source in filtered[offset : offset + limit]
        ],
        "total": len(filtered),
        "available_resolutions": available,
        "next_offset": offset + limit if len(filtered) > offset + limit else None,
    }


@router.get("/workflows/{identity}")
def workflow(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    return public_workflow(own_workflow(db, actor, identity))


def confirmation(db, row, action, preview, private=None):
    confirm = CinemaConfirmation(
        id=new_id(),
        owner_id=row.owner_id,
        workflow_id=row.id,
        workflow_version=row.version + 1,
        action=action,
        data=private or {},
        expires_at=utcnow() + timedelta(seconds=120),
    )
    db.add(confirm)
    return save_workflow(
        db,
        row,
        "awaiting_preparation_confirmation" if action == "validate_rd" else "awaiting_playback_confirmation",
        {
            "confirmation_id": confirm.id,
            "preview": {**preview, "expires_at": confirm.expires_at.isoformat()},
            "error": None,
        },
    )


@router.post("/workflows/{identity}/validate")
def validate_sources(
    identity: str,
    body: SourceValidation,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    row = own_workflow(db, actor, identity, body.version)
    if row.state not in {
        "discovered",
        "awaiting_choice",
        "recovery_required",
        "awaiting_destination",
        "awaiting_playback_confirmation",
    }:
        raise HTTPException(409, "This workflow cannot validate sources in its current state")
    requested = getattr(body, "source_ids", None)
    candidates = [
        s
        for s in row.data.get("_sources", [])
        if s.get("info_hash")
        and (not s.get("inspection") or s.get("error"))
        and (requested is None or s["id"] in requested)
    ][:5]
    if requested and set(requested) != {s["id"] for s in candidates}:
        raise HTTPException(409, "The selected release changed or is already inspected. Refresh sources.")
    if not candidates:
        failure(MediaError("NO_SOURCES", "There are no provisional debrid sources to validate.", "discover"))
    call(RealDebrid, integration_config(db, "real_debrid"))
    if row.data.get("_destination_later"):
        row.device_id = None
        row.data = {**row.data, "plan": None, "selected_source": None, "_selected_source": None}
    row.data = {**row.data, "_validation_selection": requested or []}
    return confirmation(
        db,
        row,
        "validate_rd",
        {
            "action": "Validate sources through the debrid service",
            "selected_title": db.get(CinemaTitle, row.media_id).title,
            "identity_basis": "Your explicit cloud item and title association; exact episode/file mapping is still required"
            if row.data.get("_explicit_cloud_mapping")
            else "Canonical title discovery",
            "sources": [{"id": s["id"], "release": s["release"]} for s in candidates],
            "effects": (
                "Uses the selected existing cloud entry; no new torrent is added. Selects an exact file only if the debrid service requires it. "
                if row.data.get("_explicit_cloud_mapping")
                else f"Adds at most {len(candidates)} torrent(s) and selects their exact movie/episode files. "
            )
            + "Probes at most 16 MB each. Does not play or download full movies.",
        },
        {"source_ids": [s["id"] for s in candidates]},
    )


def inspection_key(source):
    """The exact file: same torrent, same file inside it. None when that is not known."""
    if not source.get("info_hash"):
        return None
    part = str(source.get("file_id") or source.get("file_idx") or source.get("release") or "")
    return hashlib.sha256(("cinema.inspection:" + source["info_hash"] + ":" + part).encode()).hexdigest()[:36]


def cached_inspection(db, source):
    key = inspection_key(source)
    row = db.get(Record, key) if key else None
    if row and row.kind == "cinema.inspection" and row.updated_at > utcnow() - timedelta(days=7):
        return copy.deepcopy(row.data["inspection"])
    return None


def remember_inspection(db, owner_id, source):
    key = inspection_key(source)
    if not key:
        return
    row = db.get(Record, key)
    if row:
        row.data, row.updated_at = {"inspection": source["inspection"]}, utcnow()
    else:
        db.add(
            Record(
                id=key,
                kind="cinema.inspection",
                owner_id=owner_id,
                visibility="house",
                data={"inspection": source["inspection"]},
            )
        )


def validate_rd(db, row, source_ids):
    rd_config = integration_config(db, "real_debrid")
    rd = RealDebrid(rd_config)
    row.data = {
        **row.data,
        "_rd_account_key": hashlib.sha256(
            (rd_config.get("token") or rd_config.get("api_key") or "").encode()
        ).hexdigest()[:24],
    }
    sources = copy.deepcopy(row.data["_sources"])
    approved_version = row.version
    inventory = None

    def still_authorized():
        authorize_workflow(db, row)
        with Session(db.get_bind()) as fresh:
            current = fresh.get(CinemaWorkflow, row.id)
            if not current or current.state != "preparing" or current.version != approved_version:
                raise MediaError(
                    "PREPARATION_CANCELLED", "Source validation was cancelled or superseded.", "validation"
                )

    def reject(source, exc):
        if exc.code in {"PERMISSION_REVOKED", "PREPARATION_CANCELLED"}:
            db.rollback()
            raise exc
        if (
            isinstance(exc, DebridError)
            and exc.operation == "add_magnet"
            and type(exc.provider_code) is int
            and exc.provider_code in set(range(1, 38)) - {31, 33}
        ):
            source["add_uncertain"] = False
        if hasattr(exc, "rd_status"):
            source.update(rd_status=exc.rd_status, rd_progress=exc.rd_progress)
        source["error"], source["state"] = exc.public(), "not_ready"
        if exc.code == "SOURCE_REJECTED":
            source.update(rd_cached=False, cache_evidence="provider_rejected")

    probes = []
    for source in sources:
        if source["id"] not in source_ids:
            continue
        try:
            still_authorized()
            if source.get("provider") == "stream_addon":
                from .cinema_sources import resolve_media

                url, size = resolve_media(db, source)
                file = {"bytes": size}
            else:
                # Persist remote identity immediately; never repeat an uncertain add automatically.
                if not source.get("torrent_id"):
                    # Discovery may predate a user's Stremio/account addition. Reuse that
                    # exact hash before issuing a fresh add; never infer cache from a label.
                    if inventory is None:
                        inventory = rd.inventory()
                    matching = [
                        item for item in inventory if item.get("hash", "").lower() == source["info_hash"]
                    ]
                    if (
                        not source.get("add_uncertain")
                        and source.get("state") != "add_requested"
                        and matching
                    ):
                        existing = next(
                            (item for item in matching if item.get("status") == "downloaded"), matching[0]
                        )
                        source["torrent_id"] = existing["id"]
                        row.data = {**row.data, "_sources": copy.deepcopy(sources)}
                        db.commit()
                    if source.get("state") == "add_requested" or source.get("add_uncertain"):
                        if len(matching) == 1:
                            source["torrent_id"] = matching[0]["id"]
                            source["add_uncertain"] = False
                        else:
                            raise MediaError(
                                "ACCOUNT_ACTION_UNCERTAIN",
                                "The previous add has an unknown outcome and no unique inventory match was found. No duplicate was added.",
                                "resolve",
                            )
                    if not source.get("torrent_id"):
                        source["state"] = "add_requested"
                        source["add_uncertain"] = True
                        row.data = {**row.data, "_sources": copy.deepcopy(sources)}
                        db.commit()
                        source["torrent_id"] = rd.add(source["info_hash"], check=still_authorized)
                        source["add_uncertain"] = False
                        row.data = {**row.data, "_sources": copy.deepcopy(sources)}
                        db.commit()
                info = rd.info(source["torrent_id"])
                deadline = time.monotonic() + 6
                while (
                    info.get("status") == "magnet_conversion"
                    and not info.get("files")
                    and time.monotonic() < deadline
                ):
                    still_authorized()
                    time.sleep(0.5)
                    info = rd.info(source["torrent_id"])
                source["rd_status"] = info.get("status", "unknown")
                source["rd_progress"] = info.get("progress")
                files = info.get("files", [])
                if not files:
                    raise debrid_not_ready(info)
                if row.data.get("episode") is not None:
                    file = exact_episode_file(files, row.data["season"], row.data["episode"])
                else:
                    title = db.get(CinemaTitle, row.media_id)
                    file = exact_movie_file(files, title.title, title.data.get("year"))
                    if len(files) > 1:
                        source["release"] = Path(file["path"]).name[:300]
                source["file_id"] = str(file["id"])
                if info.get("status") == "waiting_files_selection":
                    still_authorized()
                    rd.select(source["torrent_id"], source["file_id"])
                url, size = rd.resolve(
                    source["torrent_id"],
                    source["file_id"],
                    wait_seconds=6,
                    check=still_authorized,
                    selection_pending=info.get("status") == "waiting_files_selection",
                )
            probes.append((source, url, size or file.get("bytes")))
        except MediaError as exc:
            reject(source, exc)
        row.data = {**row.data, "_sources": copy.deepcopy(sources)}
        db.commit()
    # The slow part (ffprobe over the network, up to 25 s each) runs side by side, and a
    # file already inspected this week is not inspected again.
    from .cinema_sources import probe_media

    known = {source["id"]: cached_inspection(db, source) for source, _, _ in probes}

    def probe(entry):
        source, url, _ = entry
        if known[source["id"]]:
            return known[source["id"]]
        directory = Path(settings.runtime_root) / "cinema" / row.id / source["id"]
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return probe_media(url, directory)

    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = [(entry, pool.submit(probe, entry)) for entry in probes]
    still_authorized()
    for (source, _, size), outcome in outcomes:
        try:
            source["inspection"] = outcome.result()
        except MediaError as exc:
            reject(source, exc)
            continue
        if not known[source["id"]]:
            remember_inspection(db, row.owner_id, source)
        source.pop("error", None)
        source["size"], source["state"] = size, "preflight_usable"
        if source.get("cache_evidence") != "p2p":  # a torrent stays a torrent (the player's)
            source["rd_status"] = "downloaded"
            source["rd_progress"] = 100
            source["rd_cached"], source["cache_evidence"] = True, "rd_resolved_probed"
    row.data = {**row.data, "_sources": copy.deepcopy(sources)}
    db.commit()
    still_authorized()  # a Stop or cancel during the last probe wins; never resurrect it
    device = db.get(CinemaDevice, row.device_id) if row.device_id else None
    choices = freeze_choices(row, device)
    checked = [s for s in sources if s["id"] in source_ids]
    failures = [s["error"] for s in checked if s.get("error")]
    summary = {
        "checked": len(checked),
        "usable": sum(bool(s.get("inspection") and not s.get("error")) for s in checked),
        "errors": {
            code: sum(e["code"] == code for e in failures) for code in sorted({e["code"] for e in failures})
        },
    }
    # Tonight's suggestion keeps looking while nothing fits the screen or nobody would follow
    # it: the next most promising versions, up to four rounds of three, without asking again.
    rounds = row.data.get("_rounds", 1)
    top = choices["candidates"][0] if choices["candidates"] else None
    # Missing subtitles alone (always-subtitles on) earns one extra round, not three: many films
    # simply have none in any release.
    why = set(top.get("why", [])) if top else set()
    if row.data.get("_suggestion") and (
        (rounds < 4 and (not top or NOT_FOLLOWED in why)) or (rounds < 2 and NO_SUBTITLES in why)
    ):
        from .cinema_suggest import rank_provisional

        more = [
            s["id"] for s in rank_provisional(sources, row.data["request"].get("maximum_resolution") or 2160)
        ]
        if more:
            row.data = {
                **row.data,
                "_rounds": rounds + 1,
                "_validation_selection": [*row.data.get("_validation_selection", []), *more],
                "validation_summary": summary,
            }
            emit(
                db,
                "cinema.workflow",
                {"workflow_id": row.id, "state": row.state, "version": row.version},
                user_id=row.owner_id,
            )
            db.commit()
            return validate_rd(db, row, more)
    batch_error = (
        failures[-1]
        if failures
        else MediaError(
            "NO_USABLE_SOURCES", "No checked source passed destination preflight.", "probe"
        ).public()
    )
    update = {
        "validation_summary": summary,
        "choice_set": choices,
        "provisional": [provisional_source(s) for s in sources if not s.get("inspection")],
        "confirmation_id": None,
        "preview": None,
        "error": None if choices["candidates"] else batch_error,
    }
    # A resident explicitly chose this one version before approving its inspection.
    selected_ids = row.data.get("_validation_selection", [])
    selected = next(
        (
            source
            for source in sources
            if len(selected_ids) == 1
            and source["id"] == selected_ids[0]
            and source.get("inspection")
            and not source.get("error")
        ),
        None,
    )
    if not device and selected:
        update.update(
            _selected_source=selected["id"],
            selected_source=source_summary(selected, {"mode": "destination_not_selected", "warnings": []}),
        )
        return save_workflow(db, row, "awaiting_destination", update)
    return save_workflow(db, row, "awaiting_choice" if choices["candidates"] else "recovery_required", update)


def prepare_plan(db, row, source):
    if not row.device_id:
        raise MediaError(
            "DESTINATION_REQUIRED", "Choose a playback destination before reviewing playback.", "preflight"
        )
    device = db.get(CinemaDevice, row.device_id)
    observation = inspect_destination(db, device)
    plan = compatibility(source["inspection"], device.capabilities, row.data["request"])
    # Native Jellyfin path may use its media-source transcoding; track indexes are actual server data.
    if device.adapter == "jellyfin" and (plan.get("subtitle") or {}).get("external"):
        raise MediaError(
            "TARGET_INCOMPATIBLE",
            "External subtitle attachment is supported through the HouseOS Cast route; this native Jellyfin session needs its own subtitle file.",
        )
    if device.adapter == "jellyfin" and not source.get("jellyfin_item"):
        raise MediaError(
            "TARGET_INCOMPATIBLE",
            "This native Jellyfin session requires a Jellyfin library item. Choose a Cast destination for on-demand media.",
        )
    if device.adapter == "cast":
        from .cinema_cast import cast_config, preflight_cast

        preflight_cast(cast_config(db), source, plan)
    state = db.scalar(
        select(CinemaState).where(CinemaState.owner_id == row.owner_id, CinemaState.media_id == row.media_id)
    )
    checkpoint = row.data.get("checkpoint", {})
    release_key = source.get("jellyfin_source") or (
        str(source.get("info_hash"))
        + ":"
        + str(
            source.get("file_index") + 1
            if source.get("provider") == "stream_addon"
            else source.get("file_id")
        )
    )
    previous_release = (row.data.get("plan") or {}).get("release_key")
    resume = checkpoint.get("position", 0) if previous_release in {None, release_key} else 0
    if checkpoint.get("position") and previous_release and previous_release != release_key:
        plan["warnings"].append(
            "This is a different release. Playback starts at the beginning; seek after verifying that its timeline matches."
        )
    if not resume and state and state.data.get("release_key") == release_key:
        resume = state.data.get("position", 0)
    if not checkpoint and row.data.get("_requested_position") is not None:
        resume = row.data["_requested_position"]
        if resume and plan.get("duration") and resume >= plan["duration"]:
            raise MediaError(
                "INVALID_POSITION",
                "The requested start position is outside this movie duration.",
                "preflight",
            )
    plan = {
        **plan,
        "source_id": source["id"],
        "device_id": device.id,
        "device_version": device.version,
        "position": resume,
        "current_destination_state": observation["state"],
        # Only something actually playing is "replaced": an idle Chromecast often reports its
        # media state as unknown, and that asked residents to replace nothing.
        "interrupts": observation["state"] not in {"idle", "stopped", "unknown", "unverified", "unavailable"},
        "expected_item": source.get("jellyfin_item"),
        "issued_at": utcnow().isoformat(),
        "release_key": release_key,
        "available_tracks": {
            kind: [
                {
                    k: v
                    for k, v in track.items()
                    if k in {"id", "language", "codec", "channels", "forced", "sdh", "default", "title"}
                }
                for track in source["inspection"].get(kind, [])
            ]
            for kind in ("audio", "subtitles")
        },
    }
    previous = (
        db.get(CinemaWorkflow, device.owner_workflow)
        if device.owner_workflow and device.owner_workflow != row.id
        else None
    )
    if (
        plan["interrupts"]
        and previous
        and previous.owner_id == row.owner_id  # someone else's film stays theirs
        and (playing := db.get(CinemaTitle, previous.media_id))
    ):
        plan["playing_title"] = playing.title  # "Titanic is still on the TV", not "something"
    row.data = {
        **row.data,
        "_replaces_workflow": previous.id if previous and previous.owner_id == row.owner_id else None,
        "plan": plan,
        "selected_source": source_summary(source, plan),
        "_selected_source": source["id"],
        "_destination_observation": observation,
    }
    return confirmation(
        db,
        row,
        "play",
        {
            "action": "Replace current playback" if plan["interrupts"] else "Play movie/episode",
            "destination": device.name,
            "release": source["release"],
            "plan": plan,
        },
        {"device_version": device.version},
    )


@router.post("/workflows/{identity}/select")
def select_source(
    identity: str, body: Choice, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    if row.state not in {
        "awaiting_choice",
        "recovery_required",
        "discovered",
        "awaiting_destination",
        "awaiting_playback_confirmation",
    }:
        raise HTTPException(409, "This workflow is not awaiting a source choice")
    choices = row.data.get("choice_set", {})
    if body.choice_set_id != choices.get("id") or choices.get("expires_at", "") < utcnow().isoformat():
        failure(MediaError("PLAN_STALE", "This source choice set expired. Discover sources again.", "select"))
    selected = call(select_candidate, choices.get("candidates", []), body.choice)
    source = next(s for s in row.data["_sources"] if s["id"] == selected["id"])
    if not row.device_id or row.data.get("_destination_later"):
        row.device_id = None
        summary = source_summary(source, {"mode": "destination_not_selected", "warnings": []})
        return save_workflow(
            db,
            row,
            "awaiting_destination",
            {
                "_selected_source": source["id"],
                "selected_source": summary,
                "confirmation_id": None,
                "preview": None,
            },
        )
    return call(prepare_plan, db, row, source)


@router.post("/workflows/{identity}/destination")
def choose_destination(
    identity: str,
    body: DestinationChoice,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    row = own_workflow(db, actor, identity, body.version)
    if row.state not in {"awaiting_destination", "awaiting_playback_confirmation"}:
        raise HTTPException(409, "Choose an inspected source first.")
    device = db.get(CinemaDevice, body.device_id)
    if not device:
        raise HTTPException(404, "Destination not found")
    source = next(
        (
            s
            for s in row.data.get("_sources", [])
            if s["id"] == row.data.get("_selected_source") and s.get("inspection")
        ),
        None,
    )
    if not source:
        raise HTTPException(409, "The selected source must be inspected first.")
    row.device_id = device.id
    row.data = {
        **row.data,
        "request": effective_request(
            row.data.get(
                "_initial_request",
                {k: v for k, v in row.data["request"].items() if k not in {"audio_track", "subtitle_track"}},
            ),
            body.preferences.model_dump(exclude_unset=True),
        ),
    }
    return call(prepare_plan, db, row, source)


class ConfigureSource(Version):
    source_id: str = Field(min_length=1, max_length=36)


@router.post("/workflows/{identity}/configure")
def configure_source(
    identity: str, body: ConfigureSource, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    source = next((s for s in row.data.get("_sources", []) if s["id"] == body.source_id), None)
    if not source:
        raise HTTPException(404, "Release not found")
    if source.get("inspection") and not source.get("error"):
        if source["id"] not in {s["id"] for s in row.data.get("choice_set", {}).get("candidates", [])}:
            row.data = {**row.data, "_validation_selection": [source["id"]]}
            row.data = {
                **row.data,
                "choice_set": freeze_choices(
                    row, db.get(CinemaDevice, row.device_id) if row.device_id else None
                ),
            }
        return select_source(
            identity,
            Choice(version=body.version, choice_set_id=row.data["choice_set"]["id"], choice=body.source_id),
            actor,
            db,
        )
    prepared = validate_sources(
        identity, SourceValidation(version=body.version, source_ids=[body.source_id]), actor, db
    )
    return confirm(prepared["confirmation_id"], actor, db)


@router.post("/workflows/{identity}/play")
def play_selected(
    identity: str,
    body: DestinationChoice,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    prepared = choose_destination(identity, body, actor, db)
    plan = prepared.get("plan", {})
    if (
        plan.get("interrupts")
        or plan.get("preparation_strategy") in {"full_spool", "bounded_complete_spool"}
        or plan.get("mode") in {"video_transcode", "video_convert"}
        or plan.get("subtitle_mode") == "burn"
    ):
        return prepared  # A consequential interruption/conversion still needs its exact preview.
    return confirm(prepared["confirmation_id"], actor, db)


@router.post("/workflows/{identity}/launch")
def launch(identity: str, body: Launch, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Play the reviewed suggestion (release, tracks, screen, start time) in one tap."""
    row = own_workflow(db, actor, identity, body.version)
    if row.state not in {
        "discovered",
        "awaiting_choice",
        "recovery_required",
        "awaiting_destination",
        "awaiting_playback_confirmation",
    }:
        raise HTTPException(409, "This title is not ready to play yet")
    source = next(
        (
            s
            for s in row.data.get("_sources", [])
            if s["id"] == body.source_id and s.get("inspection") and not s.get("error")
        ),
        None,
    )
    device = db.get(CinemaDevice, body.device_id)
    if not source or not device:
        raise HTTPException(404, "Release or screen not found")
    tracks = {
        "audio_track": body.audio_track,
        "subtitle_track": None if body.subtitle_track == "off" else body.subtitle_track,
        "subtitles_on": bool(body.subtitle_track and body.subtitle_track != "off"),
        # The card already shows the resolution; a minimum must not refuse it now.
        "quality": None,
    }
    initial = row.data.get("_initial_request", row.data["request"])
    row.device_id = device.id
    row.data = {
        **row.data,
        "_destination_later": False,
        "request": {**effective_request(initial, {}), **tracks},
    }
    if body.position is not None:
        row.data = {**row.data, "_requested_position": body.position, "checkpoint": {}}
    prepared = call(prepare_plan, db, row, source)
    if (prepared.get("plan") or {}).get("interrupts") and not body.replace:
        return prepared  # the card asks "replace what is playing?" and launches again
    return confirm(prepared["confirmation_id"], actor, db)


@router.post("/confirmations/{identity}")
def confirm(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    confirmation_row = db.scalar(
        select(CinemaConfirmation)
        .where(CinemaConfirmation.id == identity, CinemaConfirmation.owner_id == actor.id)
        .with_for_update()
    )
    if not confirmation_row:
        raise HTTPException(404, "Confirmation not found")
    row = own_workflow(db, actor, confirmation_row.workflow_id)
    if confirmation_row.consumed_at:
        return public_workflow(row)
    if confirmation_row.expires_at <= utcnow() or confirmation_row.workflow_version != row.version:
        failure(MediaError("PLAN_STALE", "This confirmation expired or its plan changed. Prepare again."))
    if confirmation_row.action == "play":
        device = db.scalar(select(CinemaDevice).where(CinemaDevice.id == row.device_id).with_for_update())
        if device.version != confirmation_row.data["device_version"]:
            failure(MediaError("PLAN_STALE", "The destination configuration changed. Prepare again."))
        if device.owner_workflow not in (None, row.id):
            previous = db.get(CinemaWorkflow, device.owner_workflow)
            # A session that ended, or got stuck after the TV refused or lost it, keeps the TV only
            # while the TV still shows something; an idle TV is free again (or it stays busy forever).
            stale = previous and previous.state in {
                "completed",
                "cancelled",
                "superseded",
                "recovery_required",
            }
            if stale and not (row.data.get("plan") or {}).get("interrupts"):
                for grant in db.scalars(select(CinemaRelay).where(CinemaRelay.workflow_id == previous.id)):
                    db.delete(grant)
            elif previous and previous.state not in {"stopped", "failed"}:
                if previous.id != row.data.get("_replaces_workflow") or previous.owner_id != actor.id:
                    failure(
                        MediaError(
                            "DESTINATION_BUSY",
                            "Another HouseOS session now owns this destination. Prepare a new interruption preview.",
                        )
                    )
                # The confirmed preview names this exact session, not any later owner.
                previous.state, previous.version = "superseded", previous.version + 1
                for grant in db.scalars(select(CinemaRelay).where(CinemaRelay.workflow_id == previous.id)):
                    db.delete(grant)
        # This claim is committed before external work. An unknown outcome never repeats automatically.
        device.owner_workflow = row.id
    row.data = {**row.data, "_authorization_session": actor.session_hash}
    confirmation_row.consumed_at = utcnow()
    if confirmation_row.action == "validate_rd":
        from .cinema_jobs import enqueue_validation

        row.state, row.version, row.updated_at = "preparing", row.version + 1, utcnow()
        row.data = {**row.data, "confirmation_id": None}
        return enqueue_validation(db, row, confirmation_row.data["source_ids"], actor.session_hash)
    save_workflow(db, row, "preparing", {"confirmation_id": None})
    try:
        if confirmation_row.action == "save_local":
            row.data = {**row.data, "download": {**row.data.get("download", {}), "phase": "queued"}}
            db.add(
                CinemaPreparation(
                    id=new_id(),
                    workflow_id=row.id,
                    owner_id=row.owner_id,
                    workflow_version=row.version,
                    state="queued",
                )
            )
            db.commit()
            return public_workflow(row)
        return execute_play(db, row)
    except Exception as exc:
        error = (
            exc.public()
            if isinstance(exc, MediaError)
            else {"code": "PLAYBACK_START_FAILED", "message": "The screen did not accept the film."}
        )
        db.rollback()
        row = db.get(CinemaWorkflow, row.id)
        device = db.get(CinemaDevice, row.device_id) if row.device_id else None
        if device and device.owner_workflow == row.id and not isinstance(exc, MediaError):
            device.owner_workflow = None
        return save_workflow(
            db,
            row,
            "recovery_required",
            {"error": error, "recovery_actions": ["inspect_destination", "choose_source", "cancel"]},
        )


def execute_play(db, row):
    authorize_workflow(db, row)
    device = db.get(CinemaDevice, row.device_id)
    source = next(s for s in row.data["_sources"] if s["id"] == row.data["_selected_source"])
    plan = row.data["plan"]
    fresh = inspect_destination(db, device)
    old = row.data["_destination_observation"]
    if fresh.get("item_id") != old.get("item_id") or fresh.get("session_id") != old.get("session_id"):
        raise MediaError(
            "PLAN_STALE",
            "Playback on the destination changed after the preview. A new confirmation is required.",
        )
    if device.adapter == "jellyfin":
        jf = Jellyfin(integration_config(db, "jellyfin"))
        info = jf.playback_info(source["jellyfin_item"])
        live_source = next(
            (s for s in info.get("MediaSources", []) if s["Id"] == source["jellyfin_source"]), None
        )
        if not live_source:
            raise MediaError(
                "SOURCE_EXPIRED", "The selected Jellyfin release is no longer available.", "prepare"
            )
        current = compatibility(jellyfin_inspection(live_source), device.capabilities, row.data["request"])
        if any(current[k] != plan[k] for k in ["video", "audio", "subtitle", "mode"]):
            raise MediaError("PLAN_STALE", "Media tracks changed after preview. Prepare a new plan.")
        authorize_workflow(db, row)
        jf.play(
            device.session_id,
            source["jellyfin_item"],
            plan["position"],
            plan["audio"]["id"],
            int(plan["subtitle"]["id"]) if plan["subtitle"] else -1,
            source["jellyfin_source"],
        )
    else:
        from .cinema_cast import execute_cast

        if not execute_cast(db, row, device, source, plan):
            return public_workflow(row)
    return save_workflow(
        db,
        row,
        "command_sent",
        {
            "error": None,
            "observation": {
                "state": "command_sent",
                "physical_verification": "unverified",
                "observed_at": utcnow().isoformat(),
            },
            "_observation_deadline": (utcnow() + timedelta(seconds=45)).isoformat(),
        },
    )


def own_state(db, actor_id, media_id):
    row = db.scalar(
        select(CinemaState)
        .where(CinemaState.owner_id == actor_id, CinemaState.media_id == media_id)
        .with_for_update()
    )
    if not row:
        row = CinemaState(
            id=new_id(),
            owner_id=actor_id,
            media_id=media_id,
            data={"position": 0, "watched": False, "favorite": False, "watchlist": False},
        )
        db.add(row)
    return row


@router.post("/workflows/{identity}/observe")
def observe(
    identity: str, body: Version, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    device = db.get(CinemaDevice, row.device_id) if row.device_id else None
    if not device or device.owner_workflow != row.id:
        failure(
            MediaError(
                "DESTINATION_OWNERSHIP_LOST", "This workflow no longer controls that destination.", "observe"
            )
        )
    if row.state not in {"command_sent", "playing_observed", "paused"}:
        return public_workflow(row)
    # Release the workflow lock during receiver I/O so controls never queue behind a
    # slow Cast connection; discard the observation if the workflow moved on meanwhile.
    observed_version = row.version
    db.commit()
    try:
        observation = inspect_destination(db, device)
        db.commit()  # Device evidence commits alone; never lock device before workflow.
    except MediaError as exc:
        db.rollback()
        observation = exc
    row = own_workflow(db, actor, identity)
    if row.version != observed_version:
        return public_workflow(row)
    device = db.get(CinemaDevice, row.device_id) if row.device_id else None
    if not device or device.owner_workflow != row.id:
        failure(
            MediaError(
                "DESTINATION_OWNERSHIP_LOST", "This workflow no longer controls that destination.", "observe"
            )
        )
    try:
        if isinstance(observation, MediaError):
            raise observation
        authorize_workflow(db, row)
        plan = row.data["plan"]
        expected = plan.get("expected_item")
        if (
            device.adapter == "cast"
            and observation.get("item_id") == expected
            and observation.get("state") == "idle"
            and observation.get("idle_reason") == "FINISHED"
        ):
            if (row.data.get("_prepared") or {}).get("streaming") and "#EXT-X-ENDLIST" not in Path(
                row.data["_prepared"]["path"]
            ).with_name("video.m3u8").read_text():
                raise MediaError(
                    "STREAM_INTERRUPTED",
                    "The receiver ended before the source finished preparing.",
                    "verify",
                    True,
                )
            state = own_state(db, actor.id, row.media_id)
            state.data = {
                **state.data,
                "position": plan["duration"],
                "duration": plan["duration"],
                "watched": True,
                "release_key": plan.get("release_key"),
            }
            state.last_watched_at, state.version = utcnow(), (state.version or 0) + 1
            checkpoint_participants(db, row, plan["duration"], plan["duration"], plan)
            next_id, continuation_error = None, None
            try:
                next_id = prepare_autoplay(db, row, actor)
            except MediaError as exc:
                continuation_error = exc.public()
            if not next_id and device.owner_workflow == row.id:
                device.owner_workflow = None
            for grant in db.scalars(select(CinemaRelay).where(CinemaRelay.workflow_id == row.id)):
                db.delete(grant)
            return save_workflow(
                db,
                row,
                "completed",
                {
                    "checkpoint": {
                        "position": plan["duration"],
                        "duration": plan["duration"],
                        "at": utcnow().isoformat(),
                    },
                    "observation": {**observation, "physical_verification": "unverified"},
                    "preview": {"next_workflow_id": next_id},
                    "error": continuation_error,
                },
            )
        if device.adapter == "jellyfin":
            if observation.get("item_id") != expected:
                raise MediaError(
                    "PLAYBACK_NOT_OBSERVED",
                    "The selected media is not observed on the player.",
                    "verify",
                    True,
                )
            # Jellyfin can synthetically advance PositionTicks; require fresh actual playback check-in.
            from datetime import datetime

            check_in = observation.get("check_in")
            try:
                observed_time = (
                    datetime.fromisoformat(check_in.replace("Z", "+00:00"))
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                )
            except (TypeError, ValueError, AttributeError):
                raise MediaError(
                    "PLAYBACK_NOT_OBSERVED",
                    "The player did not supply a fresh playback check-in.",
                    "verify",
                    True,
                )
            if (utcnow() - observed_time).total_seconds() > 30:
                raise MediaError(
                    "PLAYBACK_NOT_OBSERVED", "The player playback check-in is stale.", "verify", True
                )
        elif (
            (row.data.get("_prepared") or {}).get("streaming")
            and observation.get("item_id") == expected
            and observation.get("state") == "buffering"
            and row.data.get("_observation_deadline", "") > utcnow().isoformat()
        ):
            return save_workflow(
                db,
                row,
                "command_sent",
                {"observation": {**observation, "physical_verification": "unverified"}, "error": None},
            )
        elif observation.get("item_id") != expected or observation.get("state") not in {"active", "paused"}:
            raise MediaError(
                "PLAYBACK_NOT_OBSERVED", "The receiver has not confirmed active playback.", "verify", True
            )
        track_evidence = {"audio_track": "unverified", "subtitle_track": "unverified"}
        if device.adapter == "jellyfin":
            audio_index = observation.get("audio_index")
            subtitle_index = observation.get("subtitle_index")
            expected_subtitle = int(plan["subtitle"]["id"]) if plan.get("subtitle") else -1
            if audio_index is not None:
                if str(audio_index) != plan["audio"]["id"]:
                    raise MediaError(
                        "AUDIO_TRACK_NOT_OBSERVED",
                        "The player reports a different audio track than requested.",
                        "verify",
                    )
                track_evidence["audio_track"] = "matched"
            if subtitle_index is not None:
                if int(subtitle_index) != expected_subtitle:
                    raise MediaError(
                        "SUBTITLE_NOT_OBSERVED",
                        "The player reports a different subtitle selection than requested.",
                        "verify",
                    )
                track_evidence["subtitle_track"] = "matched"
        elif (row.data.get("_prepared") or {}).get("streaming"):
            tracks = observation.get("subtitle_tracks") or []
            active_ids = observation.get("active_track_ids") or []
            matches = [
                t
                for t in tracks
                if t.get("id") in active_ids
                and t.get("language") == ((plan.get("subtitle") or {}).get("language") or "und")
            ]
            if plan.get("subtitle") and matches:
                track_evidence["subtitle_track"] = "matched"
            elif not plan.get("subtitle") and not active_ids:
                track_evidence["subtitle_track"] = "matched"
            else:
                raise MediaError(
                    "SUBTITLE_NOT_OBSERVED",
                    "The receiver has not confirmed the requested subtitle selection.",
                    "verify",
                    True,
                )
        elif observation.get("active_track_ids") is not None:
            active_tracks = observation["active_track_ids"]
            expected_on = bool(plan.get("subtitle")) and plan.get("subtitle_mode") != "burn"
            if expected_on and 1 not in active_tracks or not expected_on and active_tracks:
                raise MediaError(
                    "SUBTITLE_NOT_OBSERVED",
                    "The Cast receiver did not activate the requested subtitle selection.",
                    "verify",
                )
            track_evidence["subtitle_track"] = "matched"
        observation = {**observation, "identity": "matched", **track_evidence}
        if (row.data.get("_prepared") or {}).get("streaming"):
            observation = {
                **observation,
                "position": float(observation.get("position") or 0)
                + float(row.data["_prepared"].get("position_offset", 0)),
            }
        position = max(0, min(float(observation.get("position") or 0), float(plan.get("duration") or 86400)))
        duration = float(plan.get("duration") or 0)
        last = row.data.get("checkpoint", {})
        progress_at = row.data.get("_progress_at", utcnow().isoformat())
        if abs(position - float(last.get("position") or 0)) > 0.5 or observation["state"] == "paused":
            progress_at = utcnow().isoformat()
        elif progress_at < (utcnow() - timedelta(seconds=60)).isoformat():
            raise MediaError(
                "BUFFERING_TIMEOUT",
                "The receiver reports playing but content position has not advanced for a minute.",
                "verify",
                True,
            )
        row.data = {
            **row.data,
            "_progress_at": progress_at,
            "_observation_deadline": (utcnow() + timedelta(seconds=45)).isoformat(),
        }
        state = own_state(db, actor.id, row.media_id)
        state.data = {
            **state.data,
            "resume": resume_settings(row, plan),
            "position": position,
            "duration": duration,
            "release": row.data["_selected_source"],
            "release_key": plan.get("release_key"),
            "watched": state.data.get("watched", False) or (duration > 0 and position / duration >= 0.95),
            "season": row.data.get("season"),
            "episode": row.data.get("episode"),
        }
        state.last_watched_at, state.version = utcnow(), (state.version or 0) + 1
        checkpoint_participants(db, row, position, duration, plan)
        if row.data.get("_queue_id"):
            from .models import Record

            queued = db.get(Record, row.data["_queue_id"])
            if (
                queued
                and queued.owner_id == actor.id
                and queued.kind == "cinema.queue"
                and not queued.deleted_at
            ):
                queued.deleted_at = utcnow()
                emit(db, "cinema.queue", {"queue_id": queued.id}, user_id=actor.id)
        return save_workflow(
            db,
            row,
            "paused" if observation["state"] == "paused" else "playing_observed",
            {
                "checkpoint": {"position": position, "duration": duration, "at": utcnow().isoformat()},
                "observation": {
                    **observation,
                    "physical_video": "unverified",
                    "physical_audio": "unverified",
                    "physical_subtitles": "unverified",
                },
                "error": None,
            },
        )
    except MediaError as exc:
        if (
            exc.code == "PLAYBACK_NOT_OBSERVED"
            and row.state == "command_sent"
            and row.data.get("_observation_deadline", "") > utcnow().isoformat()
        ):
            return save_workflow(
                db,
                row,
                "command_sent",
                {
                    "observation": {"state": "awaiting_observation", "physical_verification": "unverified"},
                    "error": None,
                },
            )
        return save_workflow(
            db,
            row,
            "recovery_required",
            {
                "error": exc.public(),
                "recovery_actions": ["inspect_destination", "change_destination", "choose_source"],
            },
        )


@router.post("/stop")
def stop_cinema(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    """Invalidate work first; then close owned receivers, including failed loads."""
    allowed(actor)
    from .models import Job, Operation

    for job in db.scalars(
        select(Job).where(
            Job.actor_id == actor.id,
            Job.kind.in_(["cinema.discover", "cinema.validate"]),
            Job.state.in_(["pending", "running"]),
        )
    ):
        job.state, job.generation = "cancelled", job.generation + 1
        operation = db.get(Operation, job.payload.get("operation_id"))
        if operation:
            operation.state = "cancelled"
            operation.result = {"error": {"code": "CANCELLED", "message": "Stopped by you."}}
            emit(
                db,
                "cinema.operation",
                {"operation_id": operation.id, "status": "cancelled"},
                user_id=actor.id,
            )
    rows = list(
        db.scalars(
            select(CinemaWorkflow)
            .where(CinemaWorkflow.owner_id == actor.id)
            .order_by(CinemaWorkflow.updated_at.desc())
        )
    )
    targets = []
    targeted = set()
    stopped = 0
    for row in rows:
        device = db.get(CinemaDevice, row.device_id) if row.device_id else None
        owned = device and device.owner_workflow == row.id
        # Older Cancel releases ownership before closing Cast. Recover that orphan
        # only on a previously used device; abort_cast still checks the actual item.
        orphan = (
            device
            and device.adapter == "cast"
            and device.owner_workflow is None
            and row.data.get("plan", {}).get("expected_item")
            and not row.data.get("_cast_closed")
            and device.id not in targeted
        )
        if owned or orphan:
            expected = {
                row.data.get("plan", {}).get("expected_item"),
                (row.data.get("_seek_previous") or {}).get("plan", {}).get("expected_item"),
            }
            targets.append((device.id, device.owner_workflow, row.id, expected - {None}))
            targeted.add(device.id)
        if row.state in {"cancelled", "stopped", "completed", "superseded"} and not owned:
            continue
        for job in db.scalars(
            select(CinemaPreparation).where(
                CinemaPreparation.workflow_id == row.id, CinemaPreparation.state == "queued"
            )
        ):
            job.state, job.finished_at = "cancelled", utcnow()
        for relay in db.scalars(select(CinemaRelay).where(CinemaRelay.workflow_id == row.id)):
            db.delete(relay)
        # State/version invalidates running workers and their bounded subprocesses.
        row.state, row.version, row.updated_at = "cancelled", row.version + 1, utcnow()
        row.data = {
            **row.data,
            "confirmation_id": None,
            "sleep_timer": None,
            "_stream_job_id": None,
            "_seek_previous": None,
            "_autoplay_expires_at": utcnow().isoformat(),
            "error": None,
        }
        emit(
            db,
            "cinema.workflow",
            {"workflow_id": row.id, "state": row.state, "version": row.version},
            user_id=actor.id,
        )
        stopped += 1
    db.commit()
    errors = []
    for device_id, workflow_id, row_id, expected in targets:
        db.expire_all()
        device = db.get(CinemaDevice, device_id)
        if device.owner_workflow != workflow_id:
            continue
        adapter, address, session_id = device.adapter, device.address, device.session_id
        db.commit()  # Never hold database locks during receiver calls.
        try:
            if adapter == "jellyfin":
                Jellyfin(integration_config(db, "jellyfin")).control(session_id, "stop")
            else:
                from .cinema_cast import abort_cast

                abort_cast(address, expected)
        except MediaError as exc:
            errors.append({"destination": device.name, **exc.public()})
            continue  # Keep ownership so the user can retry an unreachable receiver.
        db.expire_all()
        device = db.get(CinemaDevice, device_id)
        if device.owner_workflow == workflow_id:
            device.owner_workflow = None
            row = db.get(CinemaWorkflow, row_id)
            row.data = {**row.data, "_cast_closed": True}
            db.commit()
    return {"cancelled": stopped, "errors": errors}


@router.post("/workflows/{identity}/cancel")
def cancel_workflow(
    identity: str, body: Version, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    if row.state in {"playing_observed", "paused", "command_sent"}:
        raise HTTPException(409, "Use Stop to cancel an active player session")
    for job in db.scalars(
        select(CinemaPreparation).where(
            CinemaPreparation.workflow_id == row.id, CinemaPreparation.state == "queued"
        )
    ):
        job.state, job.finished_at = "cancelled", utcnow()
    for grant in db.scalars(select(CinemaRelay).where(CinemaRelay.workflow_id == row.id)):
        db.delete(grant)
    device = db.get(CinemaDevice, row.device_id) if row.device_id else None
    if device and device.owner_workflow == row.id:
        device.owner_workflow = None
    elif device and device.owner_workflow == row.data.get("_autoplay_parent"):
        parent = db.get(CinemaWorkflow, device.owner_workflow)
        if parent and parent.state == "completed":
            device.owner_workflow = None
    return save_workflow(db, row, "cancelled", {"confirmation_id": None})


@router.post("/workflows/{identity}/control")
def control(
    identity: str, body: Control, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity)
    device = db.get(CinemaDevice, row.device_id) if row.device_id else None
    if not device or device.owner_workflow != row.id:
        failure(
            MediaError(
                "DESTINATION_OWNERSHIP_LOST", "This workflow no longer controls that destination.", "control"
            )
        )
    if body.action == "seek" and (
        body.position is None or body.position > row.data.get("plan", {}).get("duration", 0)
    ):
        raise HTTPException(422, "Choose a seek position within this media duration")
    authorize_workflow(db, row)
    if body.action == "volume" and (
        body.position is None
        or body.position > 75
        or not device.observation.get("volume_supported")
        or not device.observed_at
        or device.observed_at < utcnow() - timedelta(seconds=30)
    ):
        raise HTTPException(
            422, "This receiver has no fresh supported volume control, or volume is outside 0–75%"
        )
    if body.action == "seek" and row.data.get("_seek_previous"):
        raise HTTPException(
            409, "The requested position is buffering. Wait for this seek to finish before seeking again."
        )
    if body.action == "seek" and (row.data.get("_prepared") or {}).get("streaming"):
        prepared = row.data["_prepared"]
        offset = float(prepared.get("position_offset", 0))
        playlist = Path(prepared["path"]).with_name("video.m3u8")
        buffered = (
            sum(float(x) for x in re.findall(r"#EXTINF:([0-9.]+)", playlist.read_text()))
            if playlist.is_file()
            else 0
        )
        if prepared.get("timeline_version") == 2 and offset <= body.position < offset + max(0, buffered - 4):
            body = body.model_copy(update={"position": body.position - offset})
        elif prepared.get("web"):  # a web video still downloading: nothing to prepare it from
            raise HTTPException(409, "That part isn't downloaded yet. Try again in a moment.")
        else:
            fresh = call(inspect_destination, db, device)
            if fresh.get("item_id") != row.data["plan"].get("expected_item"):
                failure(
                    MediaError(
                        "PLAN_STALE", "The screen is playing something else; no seek was sent.", "control"
                    )
                )
            previous_state = "paused" if fresh.get("state") == "paused" else "playing_observed"
            # Freeze the old buffer before stopping its producer; otherwise Cast
            # can run off its end while the new seek position is being prepared.
            if device.adapter == "cast" and previous_state != "paused":
                from .cinema_cast import cast_control

                call(cast_control, device.address, "pause", None)
            save_workflow(
                db,
                row,
                "preparing",
                {
                    "_seek_previous": {
                        "prepared": prepared,
                        "plan": row.data["plan"],
                        "state": previous_state,
                        "job_id": row.data.get("_stream_job_id"),
                    },
                    "plan": {**row.data["plan"], "position": body.position},
                    "_prepared": None,
                    "_stream_job_id": None,
                    "_destination_observation": fresh,
                    "error": None,
                },
            )
            db.add(
                CinemaPreparation(
                    id=new_id(),
                    workflow_id=row.id,
                    owner_id=row.owner_id,
                    workflow_version=row.version,
                    state="queued",
                )
            )
            db.commit()
            return public_workflow(row)
    error = None
    try:
        if body.action == "stop":
            # Save a last fresh matching checkpoint first (Pick up resumes there); the
            # last periodic one stays when the receiver cannot be read.
            try:
                fresh = observe(identity, Version(version=row.version), actor, db)["state"]
            except HTTPException:
                fresh = None
            ours = {
                row.data.get("plan", {}).get("expected_item"),
                (row.data.get("_seek_previous") or {}).get("plan", {}).get("expected_item"),
            } - {None}
            if device.adapter == "cast":
                # Close our receiver app, not only its media session (also mid-seek or
                # buffering); abort_cast leaves a screen showing something else alone.
                # Nothing expected yet: still preparing, nothing of ours on the screen.
                if ours:
                    from .cinema_cast import abort_cast

                    abort_cast(device.address, ours)
                    row.data = {**row.data, "_cast_closed": True}
            elif fresh not in {"playing_observed", "paused"}:
                # Jellyfin's stop has no identity check: never stop an unverified player.
                raise MediaError(
                    "STOP_SESSION_UNVERIFIED",
                    "HouseOS released this session, but did not stop an unverified receiver.",
                    "control",
                )
            else:
                Jellyfin(integration_config(db, "jellyfin")).control(device.session_id, "stop", None)
        elif device.adapter == "jellyfin":
            Jellyfin(integration_config(db, "jellyfin")).control(
                device.session_id, body.action, body.position
            )
        else:
            from .cinema_cast import cast_control

            cast_control(device.address, body.action, body.position)
    except MediaError as exc:
        error = exc.public()
    if body.action == "stop":
        for relay in db.scalars(select(CinemaRelay).where(CinemaRelay.workflow_id == row.id)):
            db.delete(relay)
        if device.owner_workflow == row.id:
            device.owner_workflow = None
        return save_workflow(
            db,
            row,
            "stopped",
            {
                "sleep_timer": None,
                "_autoplay_expires_at": utcnow().isoformat(),
                "confirmation_id": None,
                "error": error,
                "observation": {
                    "state": "command_outcome_unknown" if error else "stop_command_sent",
                    "action": "stop",
                    "physical_verification": "unverified",
                },
            },
        )
    if error:
        return save_workflow(db, row, "recovery_required", {"error": error})
    return save_workflow(
        db,
        row,
        "command_sent",
        {
            "_observation_deadline": (utcnow() + timedelta(seconds=45)).isoformat(),
            "error": None,
            # The receiver's last matched observation stays until the next one arrives.
            "observation": {
                **(row.data.get("observation") or {}),
                "state": "command_sent",
                "action": body.action,
                "shown_state": "paused"
                if body.action == "pause"
                else "playing_observed"
                if body.action == "resume"
                else row.data.get("observation", {}).get("shown_state") or row.state,
                "physical_verification": "unverified",
            }
            if row.state in {"playing_observed", "paused", "command_sent"}
            else {"state": "command_sent", "action": body.action, "physical_verification": "unverified"},
        },
    )


def replacement_preview(db, row):
    """Keep the observed player and its delivery grant alive until replacement is approved."""
    if row.state not in {"playing_observed", "paused", "command_sent"}:
        return row
    clone = CinemaWorkflow(
        id=new_id(),
        owner_id=row.owner_id,
        media_id=row.media_id,
        device_id=row.device_id,
        idempotency_key="change-" + row.id + "-" + str(row.version),
        state="awaiting_choice",
        version=1,
        data={
            **copy.deepcopy(row.data),
            "_replaces_workflow": row.id,
            "_relay_refresh_attempts": 0,
            "confirmation_id": None,
        },
    )
    existing = db.scalar(
        select(CinemaWorkflow).where(
            CinemaWorkflow.owner_id == row.owner_id, CinemaWorkflow.idempotency_key == clone.idempotency_key
        )
    )
    if existing:
        failure(
            MediaError(
                "PLAN_STALE",
                "A replacement preview already exists. Open that workflow or refresh playback before preparing another.",
            )
        )
    db.add(clone)
    db.flush()
    return clone


@router.post("/workflows/{identity}/change")
def change(identity: str, body: Change, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    row = own_workflow(db, actor, identity, body.version)
    if body.device_id and body.device_id != row.device_id:
        if not db.get(CinemaDevice, body.device_id):
            raise HTTPException(404, "Destination not found")
        if row.state in {"playing_observed", "paused", "command_sent"}:
            failure(
                MediaError(
                    "STOP_REQUIRED",
                    "Stop the current destination first; its checkpoint is retained. Then select the new destination.",
                    "prepare",
                )
            )
        row.device_id = body.device_id
    row = replacement_preview(db, row)
    previous_request = row.data["request"]
    if body.source_choice:
        candidate = call(
            select_candidate, row.data.get("choice_set", {}).get("candidates", []), body.source_choice
        )
        source_id = candidate["id"]
    else:
        source_id = row.data.get("_selected_source")
    source = next((s for s in row.data["_sources"] if s["id"] == source_id), None)
    if not source:
        failure(MediaError("NO_SOURCES", "Choose a source before changing playback.", "prepare"))
    if source_id != row.data.get("_selected_source"):
        previous_request = {
            k: v for k, v in previous_request.items() if k not in {"audio_track", "subtitle_track"}
        }
    row.data = {
        **row.data,
        "request": effective_request(previous_request, body.preferences.model_dump(exclude_unset=True)),
    }
    return call(prepare_plan, db, row, source)


def resume_settings(workflow, plan):
    return {
        "workflow_id": workflow.id,
        "source_id": workflow.data.get("_selected_source"),
        "device_id": workflow.device_id,
        "request": {
            **workflow.data.get("request", {}),
            "audio_track": (plan.get("audio") or {}).get("id"),
            "subtitle_track": (plan.get("subtitle") or {}).get("id"),
            "subtitles_on": bool(plan.get("subtitle")),
        },
    }


def last_resume(db, actor, identity):
    allowed(actor)
    state = db.scalar(
        select(CinemaState).where(CinemaState.owner_id == actor.id, CinemaState.media_id == identity)
    )
    if not state or not state.last_watched_at or not state.data.get("position"):
        raise HTTPException(404, "No saved playback for this title")
    saved = state.data.get("resume")
    previous = db.get(CinemaWorkflow, saved["workflow_id"]) if saved else None
    if not saved:
        # Existing history predates saved settings: reuse only an observed matching release.
        previous = next(
            (
                w
                for w in db.scalars(
                    select(CinemaWorkflow)
                    .where(CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.media_id == identity)
                    .order_by(CinemaWorkflow.updated_at.desc())
                    .limit(50)
                )
                if w.data.get("checkpoint")
                and w.data.get("plan", {}).get("release_key") == state.data.get("release_key")
            ),
            None,
        )
        if previous:
            saved = resume_settings(previous, previous.data["plan"])
    if not previous or previous.media_id != identity or previous.owner_id != actor.id:
        raise HTTPException(409, "The previous source is unavailable. Choose a version to continue.")
    source = next(
        (
            x
            for x in previous.data.get("_sources", [])
            if x["id"] == saved["source_id"] and x.get("inspection")
        ),
        None,
    )
    device = db.get(CinemaDevice, saved["device_id"])
    if not source or not device:
        raise HTTPException(
            409, "The previous source or destination is unavailable. Choose your settings again."
        )
    return state, previous, saved, source, device


@router.get("/state/{identity}/resume")
def resume_offer(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    state, previous, saved, source, device = last_resume(db, actor, identity)
    request = saved["request"]

    def track(kind, key):
        return next(
            (
                t.get("language") or t.get("title") or t["id"]
                for t in source["inspection"].get(kind, [])
                if t["id"] == request.get(key)
            ),
            None,
        )

    return {
        "media_id": identity,
        "version": state.version,
        "position": state.data["position"],
        "release": source["release"],
        "destination": device.name,
        "audio": track("audio", "audio_track"),
        "subtitles": track("subtitles", "subtitle_track") if request.get("subtitles_on") else None,
    }


class ResumePlayback(Version):
    idempotency_key: str = Field(min_length=8, max_length=80)


@router.post("/state/{identity}/resume")
def resume_playback(
    identity: str, body: ResumePlayback, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    allowed(actor)
    existing = db.scalar(
        select(CinemaWorkflow).where(
            CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.idempotency_key == body.idempotency_key
        )
    )
    if existing:
        if existing.media_id != identity:
            raise HTTPException(409, "This request belongs to another title")
        return public_workflow(existing)
    state, previous, saved, source, device = last_resume(db, actor, identity)
    if state.version != body.version:
        raise HTTPException(
            409, "Playback progress changed. Reopen Continue Watching for the latest position."
        )
    subtitle_id = saved["request"].get("subtitle_track")
    selected_sub = next((t for t in source["inspection"].get("subtitles", []) if t["id"] == subtitle_id), {})
    if selected_sub.get("external"):
        subtitle = db.get(CinemaSubtitle, subtitle_id)
        if subtitle and (subtitle.owner_id != actor.id or subtitle.expires_at <= utcnow()):
            raise HTTPException(
                409, "The external subtitle has expired. Choose subtitles again; your position is saved."
            )
    source = copy.deepcopy(source)
    source.pop("error", None)
    request = saved["request"]
    row = CinemaWorkflow(
        id=new_id(),
        owner_id=actor.id,
        media_id=identity,
        device_id=device.id,
        idempotency_key=body.idempotency_key,
        state="awaiting_destination",
        version=1,
        data={
            "request": request,
            "_initial_request": request,
            "_sources": [source],
            "_selected_source": source["id"],
            "_requested_position": state.data["position"],
            "season": previous.data.get("season"),
            "episode": previous.data.get("episode"),
            "_authorization_session": actor.session_hash,
            "_boot_id": boot_identity(),
            "_autoplay_expires_at": (utcnow() + timedelta(hours=2)).isoformat(),
            "_autoplay_depth": 0,
        },
    )
    db.add(row)
    db.commit()
    # Existing playback path refreshes destination compatibility and expiring media URLs.
    # Immutable exact-release probing is reused; never rediscover or choose another torrent.
    return play_selected(
        row.id,
        DestinationChoice(version=row.version, device_id=device.id, preferences=Preferences(**request)),
        actor,
        db,
    )


@router.get("/state")
def media_state(
    filter: Literal["continue", "watchlist", "favorites", "history", "all"] = "all",
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
    offset: int = 0,
):
    allowed(actor)
    if not 0 <= offset <= 100000:
        raise HTTPException(422, "Invalid history page")
    query = (
        select(CinemaState, CinemaTitle)
        .join(CinemaTitle, CinemaTitle.id == CinemaState.media_id)
        .where(CinemaState.owner_id == actor.id)
    )
    if filter == "history":
        query = query.where(CinemaState.last_watched_at.is_not(None))
    elif filter in {"watchlist", "favorites"}:
        query = query.where(
            CinemaState.data["favorite" if filter == "favorites" else "watchlist"].as_boolean().is_(True)
        )
    elif filter == "continue":
        query = query.where(
            CinemaState.data["position"].as_float() > 0, CinemaState.data["watched"].as_boolean().is_not(True)
        )
    rows = list(
        db.execute(
            query.order_by(CinemaState.last_watched_at.desc(), CinemaState.id).offset(offset).limit(51)
        )
    )
    parent_ids = {title.data["parent_id"] for _, title in rows[:50] if title.data.get("parent_id")}
    parents = (
        {
            parent.id: parent
            for parent in db.scalars(select(CinemaTitle).where(CinemaTitle.id.in_(parent_ids)))
        }
        if parent_ids
        else {}
    )
    items = []
    for state, title in rows[:50]:
        item = {
            "media_id": state.media_id,
            **public_title(title),
            **state.data,
            "version": state.version,
            "last_watched_at": state.last_watched_at,
        }
        parent = parents.get(title.data.get("parent_id"))
        if parent:
            item["poster"] = item.get("poster") or public_title(parent).get("poster")
            item["series_title"] = parent.title
        items.append(item)
    return {"items": items, "next_offset": offset + 50 if len(rows) > 50 else None}


@router.put("/state/{identity}")
def update_media_state(
    identity: str, body: StateUpdate, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    allowed(actor)
    if not db.get(CinemaTitle, identity):
        raise HTTPException(404, "Title not found")
    row = own_state(db, actor.id, identity)
    if body.version is not None and body.version != row.version:
        raise HTTPException(409, "Media state changed")
    row.data = {**row.data, **body.model_dump(exclude_unset=True, exclude={"version"})}
    row.version = (row.version or 0) + 1
    emit(db, "cinema.state", {"media_id": identity}, user_id=actor.id)
    db.commit()
    return {"media_id": identity, **row.data, "version": row.version}


@router.delete("/state/{identity}/history")
def remove_history(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    row = db.scalar(
        select(CinemaState)
        .where(CinemaState.owner_id == actor.id, CinemaState.media_id == identity)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "History entry not found")
    row.data = {k: v for k, v in row.data.items() if k in {"favorite", "watchlist", "preferred_release"}}
    row.last_watched_at = None
    row.version += 1
    # Clear private historical workflows too; active sessions must first stop.
    workflows = list(
        db.scalars(
            select(CinemaWorkflow).where(
                CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.media_id == identity
            )
        )
    )
    if any(w.state in {"playing_observed", "paused", "preparing", "command_sent"} for w in workflows):
        raise HTTPException(409, "Stop active playback before removing its history")
    for w in workflows:
        for confirmation_row in db.scalars(
            select(CinemaConfirmation).where(CinemaConfirmation.workflow_id == w.id)
        ):
            db.delete(confirmation_row)
        db.delete(w)
    emit(db, "cinema.history_removed", {}, user_id=actor.id)
    db.commit()
    return {
        "removed": True,
        "favorite": row.data.get("favorite", False),
        "watchlist": row.data.get("watchlist", False),
    }


@router.get("/health")
def health(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    from .models import Record
    from .cinema_adapters import private_json, internal_base
    from urllib.parse import quote

    allowed(actor)
    cache = db.scalar(
        select(Record)
        .where(Record.kind == "cinema.diagnostics", Record.visibility == "house", Record.deleted_at.is_(None))
        .order_by(Record.updated_at.desc())
        .limit(1)
    )
    if cache and (utcnow() - cache.updated_at).total_seconds() < 30:
        return {**cache.data, "cache_age_seconds": (utcnow() - cache.updated_at).total_seconds()}
    items = []
    for name in ["jellyfin", "real_debrid", "comet", "opensubtitles", "cast", "home_assistant"]:
        config = integration_config(db, name)
        item = {
            "component": name,
            "status": "unconfigured",
            "stage": "setup",
            "evidence": "configuration_absent",
            "checked_at": utcnow().isoformat(),
            "expires_after_seconds": 30,
        }
        try:
            if config.get("enabled"):
                if name == "jellyfin":
                    jf = Jellyfin(config)
                    sessions = private_json(
                        jf.base,
                        "/Sessions",
                        headers=jf.headers,
                        params={"ControllableByUserId": jf.user},
                        timeout=3,
                    )
                    private_json(
                        jf.base,
                        "/Users/" + quote(jf.user, safe="") + "/Items",
                        headers=jf.headers,
                        params={"Limit": 1},
                        timeout=3,
                    )
                    item.update(
                        status="healthy",
                        stage="read",
                        evidence="restricted_library_and_session_queries_succeeded",
                        session_count=len(sessions),
                    )
                elif name == "comet":
                    comet = Comet(config)
                    manifest = private_json(comet.base, "/manifest.json", timeout=3)
                    resources = [
                        r if isinstance(r, str) else r.get("name") for r in manifest.get("resources", [])
                    ]
                    item.update(
                        status="healthy" if "stream" in resources else "degraded",
                        stage="read",
                        evidence="manifest_resource_capabilities",
                        resources=resources,
                    )
                elif name == "real_debrid":
                    rd = RealDebrid(config)
                    account = private_json(
                        rd.base, "/user", headers={"Authorization": "Bearer " + rd.token}, timeout=3
                    )
                    item.update(
                        status="healthy" if account.get("type") == "premium" else "degraded",
                        stage="read",
                        evidence="authenticated_account_query",
                        account_type=account.get("type"),
                    )
                elif (
                    name == "home_assistant"
                    and config.get("device_id")
                    and (config.get("token") or config.get("api_key"))
                ):
                    entity = config["device_id"]
                    if not entity.startswith("media_player.") or len(entity) > 120:
                        raise MediaError(
                            "INTEGRATION_CONFIG_INVALID",
                            "Configure the exact permitted media-player entity.",
                            "setup",
                        )
                    state = private_json(
                        internal_base(config, "http://127.0.0.1:8123"),
                        "/api/states/" + quote(entity, safe=""),
                        headers={"Authorization": "Bearer " + (config.get("token") or config["api_key"])},
                        timeout=3,
                    )
                    item.update(
                        status="unavailable"
                        if state.get("state") in {"unknown", "unavailable"}
                        else "healthy",
                        stage="read",
                        evidence="home_assistant_entity_state",
                        device_state=state.get("state"),
                        last_changed=state.get("last_changed"),
                    )
                else:
                    item.update(
                        status="unknown",
                        stage="verification",
                        evidence="configured_no_fresh_device_or_provider_observation",
                    )
        except MediaError as exc:
            item.update(status="unavailable", stage=exc.stage, evidence=exc.code, error=exc.public())
        items.append(item)
    for device in db.scalars(select(CinemaDevice).limit(50)):
        age = (utcnow() - device.observed_at).total_seconds() if device.observed_at else None
        items.append(
            {
                "component": "device:" + device.id,
                "name": device.name,
                "status": "unknown"
                if age is None or age > 30
                else "unavailable"
                if device.observation.get("state") == "unavailable"
                else "healthy",
                "state": device.observation.get("state", "unknown"),
                "checked_at": device.observed_at.isoformat() if device.observed_at else None,
                "age_seconds": age,
                "stale": age is None or age > 30,
                "evidence": "stored_adapter_observation",
                "next_action": "inspect_destination",
            }
        )
    data = {"items": items, "physical_playback": "unverified"}
    if not cache:
        cache = Record(
            id=new_id(),
            kind="cinema.diagnostics",
            owner_id=actor.id,
            visibility="house",
            data=data,
            version=1,
        )
        db.add(cache)
    else:
        cache.data, cache.updated_at, cache.version = data, utcnow(), cache.version + 1
    db.commit()
    return {**data, "cache_age_seconds": 0}


@relay_router.api_route("/{token}/{name}", methods=["GET", "HEAD"])
def receiver_media(token: str, name: str, request: Request, db: Session = Depends(get_db)):
    # Dedicated LAN listener only. No cookies, no query URL, exact receiver IP, revocable grant.
    row = db.get(CinemaRelay, hashlib.sha256(token.encode()).hexdigest())
    if (
        not row
        or row.expires_at <= utcnow()
        or not request.client
        or request.client.host != row.device_address
        or not re.fullmatch(
            r"(?:media\.mp4|subtitle\.vtt|master\.m3u8|video(?:_vtt)?\.m3u8|init\.mp4|video[0-9]+\.(?:m4s|vtt))",
            name,
        )
    ):
        raise HTTPException(404, "Media unavailable")
    from .cinema_delivery import grant_authorized, revocable_chunks, local_stream

    if not grant_authorized(db.get_bind(), row.token_hash):
        raise HTTPException(404, "Media unavailable")
    if row.encrypted_url and name == "media.mp4":
        from cryptography.fernet import Fernet
        from .cinema_adapters import public_stream

        resource = Fernet(settings.encryption_key.encode()).decrypt(row.encrypted_url.encode()).decode()
        if resource.startswith("jellyfin:"):
            descriptor = json.loads(resource.removeprefix("jellyfin:"))
            jf = call(Jellyfin, integration_config(db, "jellyfin"))
            status, headers, chunks = call(
                jf.stream,
                descriptor["item_id"],
                descriptor["source_id"],
                request.headers.get("range"),
                head=request.method == "HEAD",
            )
        else:
            try:
                status, headers, chunks = public_stream(
                    resource, request.headers.get("range"), head=request.method == "HEAD"
                )
            except MediaError as exc:
                if exc.code != "SOURCE_EXPIRED":
                    failure(exc)
                from .cinema_delivery import refresh_rd_relay

                refreshed = call(refresh_rd_relay, db.get_bind(), row.token_hash)
                status, headers, chunks = call(
                    public_stream, refreshed, request.headers.get("range"), head=request.method == "HEAD"
                )
    else:
        path = Path(row.path)
        if row.mime == "application/vnd.apple.mpegurl":
            path = path.with_name(name)
        elif name == "subtitle.vtt":
            if row.path:
                path = path.with_name("subtitle.vtt")
            else:
                workflow = db.get(CinemaWorkflow, row.workflow_id)
                prepared = workflow.data.get("_prepared", {}) if workflow else {}
                if not prepared.get("sidecar_only") or not prepared.get("subtitle_path"):
                    raise HTTPException(404, "Media unavailable")
                path = Path(prepared["subtitle_path"])
        elif name != "media.mp4":
            raise HTTPException(404, "Media unavailable")
        from .fetcher_web import DIR as web_videos  # Watch → Web's streamed pieces (D32)

        expected = (Path(settings.runtime_root).resolve() / "cinema", web_videos.resolve())
        if (
            not path.is_file()
            or path.is_symlink()
            or not any(path.resolve().is_relative_to(root) for root in expected)
        ):
            raise HTTPException(404, "Media unavailable")
        status, headers, chunks = call(
            local_stream, path, request.headers.get("range"), head=request.method == "HEAD"
        )
    guarded = revocable_chunks(chunks, db.get_bind(), row.token_hash)
    return StreamingResponse(
        guarded,
        status_code=status,
        media_type="text/vtt; charset=utf-8"
        if name.endswith(".vtt")
        else "application/vnd.apple.mpegurl"
        if name.endswith(".m3u8")
        else "video/mp4"
        if row.mime == "application/vnd.apple.mpegurl" and name.endswith((".m4s", ".mp4"))
        else row.mime,
        headers={
            **headers,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range,Accept-Ranges,Content-Length",
            "Cache-Control": "private, no-store",
        },
    )


def cloud_id(torrent_id):
    return hashlib.sha256(("rd:" + str(torrent_id)).encode()).hexdigest()[:32]


@router.get("/cloud")
def cloud_inventory(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    rd = call(RealDebrid, integration_config(db, "real_debrid"))
    items = call(rd.inventory)
    # Account inventory is not local download proof; no generated links or upstream IDs escape.
    return {
        "items": [
            {
                "id": cloud_id(i["id"]),
                "title": str(i.get("filename", "Untitled"))[:240],
                "size": i.get("bytes"),
                "state": i.get("status"),
                "progress": i.get("progress"),
                "layer": "RD_CLOUD",
                "local": False,
            }
            for i in items[:100]
        ]
    }


@router.get("/titles/{identity}/subtitles")
def subtitle_search(
    identity: str,
    language: str = Query(min_length=2, max_length=3, pattern="^[a-z]{2,3}$"),
    season: int | None = Query(default=None, ge=0, le=100),
    episode: int | None = Query(default=None, ge=1, le=1000),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    from .cinema_adapters import OpenSubtitles

    allowed(actor)
    title = db.get(CinemaTitle, identity)
    if not title or not title.canonical_id.startswith("tt"):
        raise HTTPException(404, "Canonical title not found")
    adapter = call(OpenSubtitles, integration_config(db, "opensubtitles"))
    items = call(adapter.search, title.canonical_id, language, season, episode)
    # Only exact metadata matches; release/timing still require a user choice before consumption.
    output = []
    for item in items:
        row = CinemaSubtitle(
            id=new_id(),
            owner_id=actor.id,
            media_id=identity,
            data={**item, "season": season, "episode": episode},
            expires_at=utcnow() + timedelta(minutes=30),
        )
        db.add(row)
        output.append({"id": row.id, **{k: v for k, v in item.items() if k != "file_id"}})
    db.commit()
    return {"items": output, "timing": "unverified", "download_requires_confirmation": True}


@router.get("/titles/{identity}/next")
def next_episode(
    identity: str,
    season: int = Query(ge=0, le=100),
    episode: int = Query(ge=1, le=1000),
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    allowed(actor)
    title = db.get(CinemaTitle, identity)
    if not title or title.kind != "series":
        raise HTTPException(404, "Series not found")
    detailed = details(identity, actor, db)
    episodes = [
        e
        for e in detailed.get("episodes", [])
        if isinstance(e.get("season"), int) and isinstance(e.get("episode"), int)
    ]
    current = [e for e in episodes if (e["season"], e["episode"]) == (season, episode)]
    if len(current) != 1:
        failure(
            MediaError(
                "EPISODE_AMBIGUOUS",
                "Current episode is not unique in the canonical series metadata.",
                "identify",
            )
        )
    subsequent = sorted(
        (e for e in episodes if e["season"] > 0 and (e["season"], e["episode"]) > (season, episode)),
        key=lambda e: (e["season"], e["episode"]),
    )
    if not subsequent:
        return {"episode": None, "state": "end_of_series"}
    chosen = subsequent[0]
    if sum((e["season"], e["episode"]) == (chosen["season"], chosen["episode"]) for e in subsequent) != 1:
        failure(
            MediaError("EPISODE_AMBIGUOUS", "The next episode has multiple canonical entries.", "identify")
        )
    return {
        "episode": chosen,
        "state": "needs_sources",
        "autoplay": preferences(actor, db).get("autoplay", False),
    }


def reconcile_playback(db):
    """Periodic read-only receiver observations/checkpoints; revocation stops new controls."""
    from .models import User
    from .auth import user_permissions
    from .cinema_sleep import process_sleep_timers

    process_sleep_timers(db)
    process_autoplay(db)
    rows = list(
        db.scalars(
            select(CinemaWorkflow)
            .where(CinemaWorkflow.state.in_(["command_sent", "playing_observed", "paused"]))
            .limit(10)
        )
    )
    for row in rows:
        user = db.get(User, row.owner_id)
        if not account_usable(user):
            save_workflow(
                db,
                row,
                "recovery_required",
                {
                    "error": MediaError(
                        "PERMISSION_REVOKED",
                        "Playback authorization expired; no further controls will be sent.",
                        "observe",
                    ).public()
                },
            )
            continue
        actor = Actor(user.id, user.name, user.role, user_permissions(user))
        try:
            observe(row.id, Version(version=row.version), actor, db)
        except HTTPException:
            db.rollback()
    return len(rows)


class AttachSubtitle(Version):
    subtitle_id: str = Field(max_length=36)
    source_id: str | None = Field(default=None, max_length=36)  # the release shown on the card


def pick_source(row, source_id):
    """Subtitles attach to the release the resident is looking at."""
    if source_id and any(s["id"] == source_id and s.get("inspection") for s in row.data.get("_sources", [])):
        row.data = {**row.data, "_selected_source": source_id}


@router.post("/workflows/{identity}/subtitle")
def attach_subtitle(
    identity: str, body: AttachSubtitle, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    if row.state == "preparing":
        raise HTTPException(409, "Versions are still being checked; add subtitles in a moment")
    pick_source(row, body.source_id)
    subtitle = db.scalar(
        select(CinemaSubtitle).where(
            CinemaSubtitle.id == body.subtitle_id, CinemaSubtitle.owner_id == actor.id
        )
    )
    title = db.get(CinemaTitle, row.media_id)
    if (
        not subtitle
        or subtitle.expires_at <= utcnow()
        or subtitle.media_id not in {row.media_id, title.data.get("parent_id")}
        or subtitle.data.get("season") != row.data.get("season")
        or subtitle.data.get("episode") != row.data.get("episode")
    ):
        raise HTTPException(404, "Matching subtitle not found")
    row = replacement_preview(db, row)
    source_id = row.data.get("_selected_source")
    sources = copy.deepcopy(row.data.get("_sources", []))
    source = next((s for s in sources if s["id"] == source_id), None)
    if not source:
        failure(MediaError("NO_SOURCES", "Select a media source before attaching subtitles.", "prepare"))
    source["inspection"]["subtitles"].append(
        {
            "id": subtitle.id,
            "codec": "webvtt" if subtitle.data.get("uploaded_vtt") else "subrip",
            "language": subtitle.data["language"],
            "title": subtitle.data["release"],
            "external": True,
            "uploaded": bool(subtitle.data.get("uploaded_vtt")),
            "sdh": subtitle.data["sdh"],
            "forced": subtitle.data["foreign_parts_only"],
            "timing": "unverified",
        }
    )
    row.data = {
        **row.data,
        "_sources": sources,
        "request": {**row.data["request"], "subtitles_on": True, "subtitle_track": subtitle.id},
    }
    if not row.device_id:
        return save_workflow(
            db,
            row,
            "awaiting_destination",
            {"selected_source": source_summary(source, {"mode": "destination_not_selected", "warnings": []})},
        )
    return call(prepare_plan, db, row, source)


class SubtitleUpload(Version):
    source_id: str | None = Field(default=None, max_length=36)
    text: str = Field(min_length=10, max_length=512000)
    language: str = Field(default="fr", pattern="^[a-z]{2,3}$")
    name: str = Field(default="Uploaded subtitles", min_length=1, max_length=100)


def normalize_uploaded_subtitle(text):
    import subprocess
    import tempfile
    from .playback import media_command, MEDIA_ENV

    if len(text.encode("utf-8")) > 512000 or "\x00" in text:
        raise HTTPException(422, "Use a UTF-8 SRT or WebVTT file under 500 KB")
    root = Path(settings.runtime_root) / "cinema"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="subtitle-", dir=root) as directory:
        source = Path(directory) / "input.srt"
        target = Path(directory) / "output.vtt"
        source.write_text(text, encoding="utf-8")
        try:
            subprocess.run(
                media_command(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-n",
                        "-protocol_whitelist",
                        "file",
                        "-format_whitelist",
                        "srt,webvtt",
                        "-i",
                        str(source),
                        "-c:s",
                        "webvtt",
                        str(target),
                    ],
                    source,
                    Path(directory),
                ),
                capture_output=True,
                check=True,
                timeout=15,
                env=MEDIA_ENV,
            )
            result = target.read_text(encoding="utf-8")
            if len(result.encode()) > 512000 or "-->" not in result:
                raise ValueError("No subtitle cues")
            return result
        except (subprocess.SubprocessError, OSError, ValueError):
            raise HTTPException(422, "The file is not valid SRT/WebVTT or could not be normalized") from None


@router.post("/workflows/{identity}/subtitles/upload")
def upload_subtitle(
    identity: str, body: SubtitleUpload, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    pick_source(row, body.source_id)
    if row.state not in {
        "awaiting_choice",
        "awaiting_destination",
        "awaiting_playback_confirmation",
    } or not row.data.get("_selected_source"):
        raise HTTPException(409, "Choose an inspected movie version before uploading subtitles")
    if (
        len(
            db.scalars(
                select(CinemaSubtitle.id).where(
                    CinemaSubtitle.owner_id == actor.id, CinemaSubtitle.expires_at > utcnow()
                )
            ).all()
        )
        >= 30
    ):
        raise HTTPException(429, "Too many active subtitle selections; try again after they expire")
    data = normalize_uploaded_subtitle(body.text)
    subtitle = CinemaSubtitle(
        id=new_id(),
        owner_id=actor.id,
        media_id=row.media_id,
        expires_at=utcnow() + timedelta(hours=6),
        data={
            "language": body.language,
            "release": body.name,
            "uploaded_vtt": data,
            "sdh": False,
            "foreign_parts_only": False,
            "season": row.data.get("season"),
            "episode": row.data.get("episode"),
        },
    )
    db.add(subtitle)
    db.flush()
    return attach_subtitle(identity, AttachSubtitle(version=body.version, subtitle_id=subtitle.id), actor, db)


@router.get("/devices/{identity}/current")
def current_destination(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    device = db.get(CinemaDevice, identity)
    if not device:
        raise HTTPException(404, "Destination not found")
    row = db.get(CinemaWorkflow, device.owner_workflow) if device.owner_workflow else None
    if not row or row.state in {"failed", "stopped", "cancelled"}:
        return {"workflow_id": None, "state": device.observation.get("state", "unknown")}
    title = db.get(CinemaTitle, row.media_id)
    return {
        "workflow_id": row.id,
        "title": title.title if title else None,
        "state": row.state,
        "observation_at": device.observed_at,
    }


class CoWatch(Body):
    participate: bool


@router.post("/workflows/{identity}/co-watch")
def co_watch(
    identity: str, body: CoWatch, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    from .models import Record

    allowed(actor)
    workflow = db.get(CinemaWorkflow, identity)
    device = db.get(CinemaDevice, workflow.device_id) if workflow else None
    if not workflow or not device or device.owner_workflow != workflow.id:
        raise HTTPException(404, "Active shared playback not found")
    # Only the joining user can opt themselves in. Initiators cannot assign others' history.
    records = list(
        db.scalars(
            select(Record).where(
                Record.kind == "cinema.cowatch", Record.owner_id == actor.id, Record.deleted_at.is_(None)
            )
        )
    )
    participation = next((r for r in records if r.data.get("workflow_id") == identity), None)
    if body.participate and not participation:
        db.add(
            Record(
                id=new_id(),
                kind="cinema.cowatch",
                owner_id=actor.id,
                visibility="private",
                data={"workflow_id": identity},
                version=1,
            )
        )
    elif not body.participate and participation:
        participation.deleted_at = utcnow()
    emit(db, "cinema.cowatch", {"workflow_id": identity, "participate": body.participate}, user_id=actor.id)
    db.commit()
    return {"participate": body.participate, "workflow_id": identity}


def checkpoint_participants(db, workflow, position, duration, plan):
    from .models import Record, User

    entries = db.execute(
        select(Record, User)
        .join(User, User.id == Record.owner_id)
        .where(
            Record.kind == "cinema.cowatch",
            Record.deleted_at.is_(None),
            Record.data["workflow_id"].as_string() == workflow.id,
            User.active.is_(True),
        )
    ).all()
    for record, user in entries:
        if (
            record.data.get("workflow_id") != workflow.id
            or user.id == workflow.owner_id
            or user.expires_at
            and user.expires_at <= utcnow()
        ):
            continue
        if user.role not in {"resident", "admin"} and "cinema.use" not in user.permissions:
            continue
        state = own_state(db, user.id, workflow.media_id)
        state.data = {
            **state.data,
            "position": position,
            "duration": duration,
            "release": workflow.data["_selected_source"],
            "release_key": plan.get("release_key"),
            "watched": state.data.get("watched", False) or (duration > 0 and position / duration >= 0.95),
            "season": workflow.data.get("season"),
            "episode": workflow.data.get("episode"),
        }
        state.last_watched_at, state.version = utcnow(), (state.version or 0) + 1
        emit(db, "cinema.state", {"media_id": workflow.media_id}, user_id=user.id)


def poster_jpeg(content, size=(360, 540)):
    import io
    from PIL import Image

    image = Image.open(io.BytesIO(content))
    if image.format not in {"JPEG", "PNG", "WEBP", "GIF"} or image.width * image.height > 40_000_000:
        raise ValueError("Unsupported image")
    image.thumbnail(size)
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=85)
    return output.getvalue()


# Posters, song art, station logos: sanitised small JPEGs kept on disk for a month. A page
# asks for a hundred at once, so misses go to their own few threads (never the request
# threads), the same image is fetched once, and one that fails is not asked again for 6 h.
IMAGE_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="images")
IMAGE_LOCKS = [threading.Lock() for _ in range(64)]
IMAGE_KEEP, IMAGE_MISS = 30 * 86400, 6 * 3600


def image_path(url):
    # Under cinema/: the folder the service may write in every install (Docker's /state is not).
    return settings.runtime_root / "cinema/images" / (hashlib.sha256(url.encode()).hexdigest()[:40] + ".jpg")


def image_on_disk(url):
    path = image_path(url)
    try:
        if time.time() - path.stat().st_mtime < IMAGE_KEEP:
            return path.read_bytes()
    except OSError:
        pass
    return None


def cached_public_poster(url, freshness_bucket=None):
    """A public image as a sanitised JPEG, from disk or fetched once (`freshness_bucket` is
    unused, kept for callers)."""
    jpeg = image_on_disk(url)
    if jpeg is not None:
        return jpeg
    path = image_path(url)
    miss = path.with_suffix(".miss")
    with IMAGE_LOCKS[int(path.stem[:8], 16) % len(IMAGE_LOCKS)]:
        jpeg = image_on_disk(url)  # fetched while we waited
        if jpeg is not None:
            return jpeg
        try:
            if time.time() - miss.stat().st_mtime < IMAGE_MISS:
                raise MediaError("SOURCE_NOT_READY", "This image is unavailable for now.", "resolve", True)
        except OSError:
            pass
        try:
            jpeg = poster_jpeg(public_fetch(url, limit=6_000_000)[0])
        except (MediaError, OSError, ValueError):
            keep(miss, b"")
            raise
        keep(path, jpeg)
        miss.unlink(missing_ok=True)
        return jpeg


def keep(path, content):
    """Best effort: a cache that cannot be written only costs a fetch next time."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp" + str(threading.get_ident()))
        temporary.write_bytes(content)
        os.replace(temporary, path)
    except OSError:
        pass


async def image_response(url, max_age=7 * 86400):
    """Serve a public image: a disk hit at once, a miss fetched on the image threads."""
    import asyncio

    jpeg = image_on_disk(url)
    if jpeg is None:
        try:
            jpeg = await asyncio.get_running_loop().run_in_executor(IMAGE_POOL, cached_public_poster, url)
        except (MediaError, OSError, ValueError):
            raise HTTPException(404, "Image unavailable") from None
    return Response(
        jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": f"private, max-age={max_age}", "X-Content-Type-Options": "nosniff"},
    )


def poster_source(identity):
    """Where a title's poster comes from: (public URL, Jellyfin item id), or None."""
    with SessionLocal() as db:
        title = db.get(CinemaTitle, identity)
        if not title:
            return None
        return (
            title.data.get("_poster_url"),
            title.data.get("jellyfin_id"),
            integration_config(db, "jellyfin"),
        )


def jellyfin_poster(config, item):
    import httpx

    jf = Jellyfin(config)
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
        with client.stream(
            "GET",
            jf.base + "/Items/" + item + "/Images/Primary",
            headers=jf.headers,
            params={"maxWidth": 360, "quality": 85},
        ) as response:
            if response.status_code != 200:
                raise ValueError("no poster")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 6_000_000:
                    raise ValueError("poster too large")
    return poster_jpeg(content)


@router.get("/titles/{identity}/poster")
async def poster(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    import asyncio
    import httpx
    from starlette.concurrency import run_in_threadpool

    allowed(actor)
    db.close()  # the sign-in check's connection; a cold Watch page must not drain the pool on fetches
    found = await run_in_threadpool(poster_source, identity)
    if not found or not (found[0] or found[1]):
        raise HTTPException(404, "Poster not found")
    url, jellyfin_id, config = found
    if url:
        return await image_response(url)
    try:  # a private library's artwork is not kept on disk
        jpeg = await asyncio.get_running_loop().run_in_executor(
            IMAGE_POOL, jellyfin_poster, config, jellyfin_id
        )
    except (MediaError, OSError, ValueError, httpx.HTTPError):
        raise HTTPException(404, "Poster unavailable") from None
    return Response(
        jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


class SaveLocal(Version):
    source_id: str | None = Field(default=None, max_length=36)  # the release shown on the card


@router.post("/workflows/{identity}/save-local")
def prepare_save_local(
    identity: str, body: SaveLocal, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    from .files import storage_check, lock_quota, media_usage
    from .models import Record
    import shutil

    row = own_workflow(db, actor, identity, body.version)
    require_permission(actor, "files.shared.write")
    if body.source_id:
        if not any(s["id"] == body.source_id and s.get("inspection") for s in row.data.get("_sources", [])):
            raise HTTPException(409, "That version is not checked yet")
        row.data = {**row.data, "_selected_source": body.source_id}
    source = next(
        (s for s in row.data.get("_sources", []) if s["id"] == row.data.get("_selected_source")), None
    )
    if source and source.get("local_record"):
        raise HTTPException(409, "This version is already saved on the house disk.")
    if (
        not source
        or source.get("state") != "preflight_usable"
        or (
            source.get("provider") != "stream_addon"
            and (not source.get("torrent_id") or not source.get("file_id"))
        )
    ):
        failure(
            MediaError(
                "NO_SOURCES", "Choose and validate a debrid source before saving it locally.", "prepare"
            )
        )
    size = source.get("size")
    if not size or not 0 < size <= 80 * 1024**3:
        failure(
            MediaError(
                "RESOURCE_LIMIT", "The source needs a verified size no greater than 80 GiB.", "prepare"
            )
        )
    storage_check()
    lock_quota(db)
    used, reserved = media_usage(db, locked=True)
    if (
        used + reserved + size > settings.media_quota_bytes
        or shutil.disk_usage(settings.data_root).free < size + 20 * 1024**3
    ):
        failure(
            MediaError(
                "RESOURCE_LIMIT",
                "The shared media quota or storage safety headroom would be exceeded.",
                "prepare",
            )
        )
    clone = CinemaWorkflow(
        id=new_id(),
        owner_id=actor.id,
        media_id=row.media_id,
        device_id=row.device_id,
        state="discovered",
        version=1,
        idempotency_key="save-" + new_id(),
        data={
            **copy.deepcopy(row.data),
            "_kind": "save_local",
            "download": {"bytes": 0, "total": size, "phase": "awaiting_confirmation"},
            "confirmation_id": None,
            "_prepared": None,
        },
    )
    record = Record(
        id=new_id(),
        kind="cinema.local_media",
        owner_id=actor.id,
        visibility="house",
        data={
            "workflow_id": clone.id,
            "media_id": row.media_id,
            "size": size,
            "state": "reserved",
            "expires_at": (utcnow() + timedelta(minutes=3)).isoformat(),
        },
        version=1,
    )
    clone.data = {**clone.data, "_local_record_id": record.id}
    db.add_all([clone, record])
    db.flush()
    return confirmation(
        db,
        clone,
        "save_local",
        {
            "action": "Save this exact release in the shared Cinema library",
            "release": source["release"],
            "bytes": size,
            "effects": "Downloads the complete file to the approved storage drive. Verifies media and atomically publishes only a complete file. Does not start playback.",
        },
    )


# Register the display-control routes on this domain router without another app module.
from . import cinema_tv as _cinema_tv  # noqa: F401 (registers TV routes)


def boot_identity():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def prepare_autoplay(db, row, actor):
    """Continue only an already selected debrid pack, same source/policy/target, max3 episodes."""
    from .cinema_cast import cast_config, preflight_cast

    request = row.data.get("request", {})
    if (
        not request.get("autoplay")
        or row.data.get("_autoplay_depth", 0) >= 3
        or row.data.get("_autoplay_expires_at", "") <= utcnow().isoformat()
        or row.data.get("_boot_id") != boot_identity()
    ):
        return None
    current_title = db.get(CinemaTitle, row.media_id)
    parent_id = current_title.data.get("parent_id") if current_title else None
    if not parent_id:
        return None
    source = next(s for s in row.data["_sources"] if s["id"] == row.data["_selected_source"])
    parent = db.get(CinemaTitle, parent_id)
    following = next_episode(parent_id, row.data["season"], row.data["episode"], actor, db)["episode"]
    if not following:
        return None
    authorize_workflow(db, row)
    if source.get("provider") == "stream_addon":
        from .cinema_sources import StreamAddon, resolve_media

        canonical = parent.canonical_id
        if canonical.startswith("mal:"):
            from .anime_catalog import resolve_stream

            canonical = resolve_stream(canonical, following["episode"])
        candidates = StreamAddon(integration_config(db, "stream_addon")).streams(
            canonical, parent.kind, following["season"], following["episode"]
        )
        matches = [
            candidate
            for candidate in candidates
            if candidate.get("info_hash") == source.get("info_hash")
            and candidate.get("rd_cached") == source.get("rd_cached")
            and candidate.get("file_index") != source.get("file_index")
        ]
        if len(matches) != 1:
            raise MediaError(
                "AUTOPLAY_NEEDS_SELECTION",
                "The next episode has no unique ready file in this same release. Choose a version explicitly.",
                "autoplay",
            )
        next_source = {**matches[0], "id": new_id(), "layer": source.get("layer", "ON_DEMAND")}
        url, size = resolve_media(db, next_source)
        next_source["size"] = size or next_source.get("size")
    else:
        if not source.get("torrent_id"):
            raise MediaError(
                "AUTOPLAY_NEEDS_SELECTION",
                "Choose the next episode; this destination did not provide a safe ready-source continuation.",
                "autoplay",
            )
        rd = RealDebrid(integration_config(db, "real_debrid"))
        manifest = rd.info(source["torrent_id"])
        file = exact_episode_file(manifest.get("files", []), following["season"], following["episode"])
        if not file.get("selected") or manifest.get("status") != "downloaded":
            raise MediaError(
                "AUTOPLAY_NEEDS_CONFIRMATION",
                "The next episode needs a new debrid file-selection action. Choose it explicitly.",
                "autoplay",
            )
        url, size = rd.resolve(source["torrent_id"], str(file["id"]))
        next_source = {
            **source,
            "id": new_id(),
            "file_id": str(file["id"]),
            "size": size or file.get("bytes"),
        }
    authorize_workflow(db, row)
    import tempfile
    from .cinema_sources import probe_media

    with tempfile.TemporaryDirectory(
        prefix="autoplay-", dir=Path(settings.runtime_root) / "cinema"
    ) as temporary:
        inspection = probe_media(url, Path(temporary))
    next_source.update(inspection=inspection, state="preflight_usable")
    authorize_workflow(db, row)
    device = db.get(CinemaDevice, row.device_id)
    next_request = {k: v for k, v in request.items() if k not in {"audio_track", "subtitle_track"}}
    prior_plan = row.data["plan"]
    next_request["audio_language"] = prior_plan["audio"].get("language")
    next_request["subtitles_on"] = prior_plan.get("subtitle") is not None
    next_request["subtitle_language"] = (prior_plan.get("subtitle") or {}).get("language")
    plan = compatibility(inspection, device.capabilities, next_request)
    request = next_request
    preflight_cast(cast_config(db), next_source, plan)
    previous = row.data["plan"]
    if (
        plan.get("preparation_strategy")
        or plan["mode"] != previous["mode"]
        or plan["video"]["height"] != previous["video"]["height"]
        or plan["video"]["hdr"] != previous["video"]["hdr"]
    ):
        raise MediaError(
            "AUTOPLAY_NEEDS_CONFIRMATION",
            "The next episode needs a materially different playback plan. Review it before playing.",
            "autoplay",
        )
    parent = db.get(CinemaTitle, parent_id)
    title = upsert_title(
        db,
        f"{parent.canonical_id}:{following['season']}:{following['episode']}",
        f"{parent.title} · S{following['season']:02}E{following['episode']:02}",
        "episode",
        {
            "parent_id": parent_id,
            "season": following["season"],
            "episode": following["episode"],
            "layers": ["RD_CLOUD"],
        },
    )
    child = CinemaWorkflow(
        id=new_id(),
        owner_id=row.owner_id,
        media_id=title.id,
        device_id=row.device_id,
        idempotency_key="autoplay-" + row.id,
        state="autoplay_countdown",
        version=1,
        data={
            "request": request,
            "_authorization_session": row.data.get("_authorization_session"),
            "season": following["season"],
            "episode": following["episode"],
            "_sources": [next_source],
            "_selected_source": next_source["id"],
            "_boot_id": row.data["_boot_id"],
            "_autoplay_expires_at": row.data["_autoplay_expires_at"],
            "_autoplay_depth": row.data.get("_autoplay_depth", 0) + 1,
            "_autoplay_parent": row.id,
            "preview": {
                "action": "Autoplay next episode",
                "title": title.title,
                "countdown_until": (utcnow() + timedelta(seconds=15)).isoformat(),
                "cancel_action": "cancel",
            },
            "plan": {
                **plan,
                "source_id": next_source["id"],
                "device_id": device.id,
                "device_version": device.version,
                "position": 0,
                "release_key": str(next_source.get("info_hash"))
                + ":"
                + str(
                    next_source["file_index"] + 1
                    if next_source.get("provider") == "stream_addon"
                    else next_source.get("file_id")
                ),
            },
        },
    )
    db.add(child)
    db.flush()
    emit(
        db,
        "cinema.autoplay_countdown",
        {"workflow_id": child.id, "countdown_until": child.data["preview"]["countdown_until"]},
        user_id=actor.id,
    )
    return child.id


def process_autoplay(db):
    from .models import User
    from .auth import user_permissions
    from .cinema_cast import execute_cast

    rows = list(
        db.scalars(select(CinemaWorkflow).where(CinemaWorkflow.state == "autoplay_countdown").limit(10))
    )
    for row in rows:
        if row.data["preview"]["countdown_until"] > utcnow().isoformat():
            continue
        try:
            row = db.scalar(select(CinemaWorkflow).where(CinemaWorkflow.id == row.id).with_for_update())
            user, device = db.get(User, row.owner_id), db.get(CinemaDevice, row.device_id)
            if row.state != "autoplay_countdown":
                continue
            if (
                not account_usable(user)
                or "cinema.use" not in user_permissions(user)
                or row.data.get("_boot_id") != boot_identity()
                or row.data["_autoplay_expires_at"] <= utcnow().isoformat()
            ):
                raise MediaError(
                    "AUTOPLAY_EXPIRED", "The bounded autoplay authorization expired.", "autoplay"
                )
            if (
                device.owner_workflow != row.data["_autoplay_parent"]
                or device.version != row.data["plan"]["device_version"]
            ):
                raise MediaError(
                    "DESTINATION_OWNERSHIP_LOST",
                    "Another session changed the destination; autoplay stopped.",
                    "autoplay",
                )
            authorize_workflow(db, row)
            fresh = inspect_destination(db, device)
            parent = db.get(CinemaWorkflow, row.data["_autoplay_parent"])
            if not parent or fresh.get("item_id") != parent.data.get("plan", {}).get("expected_item"):
                raise MediaError(
                    "DESTINATION_BUSY",
                    "The destination changed after the completed episode; autoplay stopped.",
                    "autoplay",
                )
            if fresh["state"] != "idle" or fresh.get("idle_reason") != "FINISHED":
                raise MediaError(
                    "DESTINATION_BUSY",
                    "The destination no longer reports the previous episode finished; autoplay stopped.",
                    "autoplay",
                )
            device.owner_workflow = row.id
            save_workflow(db, row, "preparing", {"_destination_observation": fresh})
            source = row.data["_sources"][0]
            if execute_cast(db, row, device, source, row.data["plan"]) is False:
                continue
            save_workflow(
                db,
                row,
                "command_sent",
                {
                    "_observation_deadline": (utcnow() + timedelta(seconds=45)).isoformat(),
                    "observation": {"state": "command_sent", "physical_verification": "unverified"},
                },
            )
        except MediaError as exc:
            save_workflow(db, row, "recovery_required", {"error": exc.public()})


def authorize_workflow(db, workflow):
    """Independent fresh DB transaction before external side effects/after slow work."""
    if workflow is None:
        raise MediaError("PERMISSION_REVOKED", "This workflow is no longer available.", "authorization")
    with Session(db.get_bind()) as fresh:
        if not delegated_user(
            fresh, workflow.owner_id, workflow.data.get("_authorization_session"), "cinema.use"
        ):
            raise MediaError(
                "PERMISSION_REVOKED",
                "Playback permission or its authorizing session was revoked or expired.",
                "authorization",
            )


from . import cinema_jobs, cinema_queue, cinema_sleep, cinema_library, cinema_web  # noqa: F401 (register routes after domain definitions)


# ---- A film in VLC (or any player): the chosen version streamed as it is, nothing kept ----

PLAYER_LINK_SECONDS = 12 * 3600
PLAYER_EXTENSIONS = {"matroska": "mkv", "webm": "webm", "mpegts": "ts", "avi": "avi"}
# The resolved stream per link, a few minutes: a player asks again at every jump.
# ponytail: per-process memory; the API runs in one process.
_resolved: dict[tuple[str, str], tuple[float, str]] = {}


class PlayerLink(Body):
    source_id: str = Field(min_length=1, max_length=36)


@router.post("/workflows/{identity}/player-link")
def player_link(
    identity: str, body: PlayerLink, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    """VLC and other players send no sign-in cookie, so the link carries its own permission:
    encrypted, for this person and this sign-in, and it stops after 12 hours or at sign-out."""
    from cryptography.fernet import Fernet
    from urllib.parse import quote

    row = own_workflow(db, actor, identity)
    source = next(
        (
            s
            for s in row.data.get("_sources", [])
            if s["id"] == body.source_id and s.get("inspection") and not s.get("error")
        ),
        None,
    )
    if not source:
        raise HTTPException(409, "That version is not checked yet")
    grant = {"workflow": row.id, "source": source["id"], "user": actor.id, "session": actor.session_hash}
    token = Fernet(settings.encryption_key.encode()).encrypt(json.dumps(grant).encode()).decode()
    title = db.get(CinemaTitle, row.media_id)
    container = str(source["inspection"].get("container") or "")
    extension = next((ext for key, ext in PLAYER_EXTENSIONS.items() if key in container), "mp4")
    name = re.sub(r'[\\/:*?"<>|\r\n]', "", title.title if title else "Film")[:120] or "Film"
    db.commit()  # own_workflow locked the row
    return {
        "url": f"/api/v1/cinema/player/{token}/{quote(name + '.' + extension)}",
        "title": name,
        "expires_in": PLAYER_LINK_SECONDS,
    }


@router.api_route("/player/{token}/{name}", methods=["GET", "HEAD"])
def player_stream(token: str, name: str, request: Request, db: Session = Depends(get_db)):
    from cryptography.fernet import Fernet, InvalidToken
    from .cinema_adapters import public_stream
    from .cinema_sources import resolve_media

    gone = HTTPException(404, "This link has expired: open the film again for a new one")
    try:
        grant = json.loads(
            Fernet(settings.encryption_key.encode()).decrypt(token.encode(), ttl=PLAYER_LINK_SECONDS)
        )
    except (InvalidToken, ValueError):
        raise gone from None
    user = delegated_user(db, grant.get("user"), grant.get("session"), "cinema.use")
    row = db.get(CinemaWorkflow, grant.get("workflow") or "")
    if not user or user.role == "guest" or not row or row.owner_id != user.id:
        raise gone
    source = next((s for s in row.data.get("_sources", []) if s["id"] == grant.get("source")), None)
    if not source:
        raise gone
    byte_range, head = request.headers.get("range"), request.method == "HEAD"
    if source.get("jellyfin_item"):
        jellyfin = call(Jellyfin, integration_config(db, "jellyfin"))
        db.close()
        status, headers, chunks = call(
            jellyfin.stream, source["jellyfin_item"], source["jellyfin_source"], byte_range, head=head
        )
    else:
        key = (row.id, source["id"])
        for attempt in range(2):
            cached = _resolved.get(key)
            if not cached or cached[0] < time.time():
                url, _ = call(resolve_media, db, source, refresh=attempt > 0)
                _resolved[key] = cached = (time.time() + 600, url)
            try:
                status, headers, chunks = public_stream(cached[1], byte_range, head=head)
                break
            except MediaError as exc:
                _resolved.pop(key, None)
                if exc.code != "SOURCE_EXPIRED" or attempt:
                    failure(exc)
        db.close()  # a film streams for hours: give the connection back first
    return StreamingResponse(
        chunks,
        status_code=status,
        media_type="video/x-matroska" if name.endswith(".mkv") else "video/mp4",
        headers={**headers, "Accept-Ranges": "bytes", "Cache-Control": "private, no-store"},
    )
