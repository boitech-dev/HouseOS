"""Assistant tools: typed inputs, compact result shapes, tool bundles and result cards.

Every handler calls the same permission-checked service the app's own screens use."""

import inspect
from typing import Annotated, Literal
from fastapi import HTTPException, params
from pydantic import Field, ValidationError
from pydantic_core import PydanticUndefined
from sqlalchemy import select
from .auth import Input, require_admin
from .models import Record
from .integrations import integration_config
from .cinema import StateUpdate, Control as PlaybackControl
from .cinema import Change as CinemaChangeBody, Launch
from .cinema_sleep import SleepTimer
from .cinema_tv import TVAction
from .tool_code import TOOLS as CODE_TOOLS
from .tool_setup import TOOLS as SETUP_TOOLS, Empty, card, confirmation
from .tool_api import TOOLS as API_TOOLS


def route(fn, **kwargs):
    """Call a FastAPI route function as plain Python: keywords only, and every parameter left at a
    Query/Body/Depends marker gets that marker's real default (a required one raises)."""
    for name, param in inspect.signature(fn).parameters.items():
        marker = param.default
        if name in kwargs or not isinstance(marker, (params.Param, params.Body, params.Depends)):
            continue
        if isinstance(marker, params.Depends) or marker.default in (..., PydanticUndefined):
            raise TypeError(f"{fn.__name__}() needs {name}")
        kwargs[name] = marker.default
    return fn(**kwargs)


class Search(Input):
    query: str = Field(min_length=1, max_length=200)


class MusicSearch(Search):
    limit: int = Field(default=5, ge=1, le=10)
    source: Literal["youtube", "soundcloud"] = "youtube"


class CatalogBrowse(Input):
    kind: Literal["movie", "series", "anime"] = "movie"
    catalog: Literal["top", "year", "imdbRating"] = "top"
    genre: str = Field(default="", max_length=40)
    offset: int = Field(default=0, ge=0, le=10000)


class RadioSearch(Input):
    query: str = Field(default="", max_length=120)
    genre: str = Field(default="", max_length=80)
    country: str = Field(default="", max_length=2)
    language: str = Field(default="", max_length=50)
    page: int = Field(default=0, ge=0, le=100)


class RadioQueue(Input):
    id: str
    idempotency_key: str = Field(min_length=8, max_length=100)


def browse_catalog(body, actor, db):
    from .cinema import browse

    result = route(
        browse, kind=body.kind, catalog=body.catalog, genre=body.genre, offset=body.offset, actor=actor, db=db
    )
    return {
        "items": [
            {k: v for k, v in item.items() if k in {"id", "title", "year", "kind", "genres"}}
            for item in result["items"][:10]
        ],
        "next_offset": body.offset + 10 if len(result["items"]) > 10 else result.get("next_offset"),
    }


def radio_search(body, actor, db):
    from .radio import search_radio

    result = route(
        search_radio,
        q=body.query,
        tag=body.genre,
        country=body.country,
        language=body.language,
        page=body.page,
        actor=actor,
    )
    return {**result, "items": result["items"][:5]}


def radio_queue(body, actor, db):
    from .radio import queue_radio, RadioAdd

    return queue_radio(body.id, RadioAdd(idempotency_key=body.idempotency_key), actor, db)


class MemoryId(Input):
    id: str


class PlaylistAdd(Input):
    id: str
    source_url: str = Field(max_length=2000)


class ContextSwitch(Input):
    context: Literal[
        "general",
        "music",
        "cinema",
        "household",
        "files",
        "diagnostics",
        "music_library",
        "cinema_library",
        "tv",
        "home",
        "setup",
    ]


def switch_context(body, actor, db):
    if body.context != "setup":
        return {"status": "context_changed", "context": body.context}
    # Setup mode is opened by the admin, never entered from a chat: they get its button.
    require_admin(actor)
    return {
        "status": "completed",
        "message": "Nothing switched: setup mode opens with the button on the card; tell them to tap it.",
        "card": card("House setup", None, "/assistant?mode=setup"),
    }


CONTEXT_TOOL = (
    ContextSwitch,
    "Load another toolset: general=music, house and memory; household=edit existing groceries, tasks, notes and events; cinema=find and play movies/series; cinema_library=movie queue, history, current movie controls and downloads; tv=TV power, HDMI input and volume; files=files; music_library=music history, saved songs, playlists and queue edits; home=smart-home lights, switches, blinds and heating; diagnostics=health; setup=configure the house (admins): shows a button that opens setup mode, no switch. Changes nothing else.",
    switch_context,
)


class QueueRead(Input):
    offset: int = Field(default=0, ge=0, le=10000)


class WorkflowRead(QueueRead):
    id: str


class SourcePage(WorkflowRead):
    resolution: int | None = Field(default=None, ge=0, le=4320)


def compact_workflow(result, offset=0):
    result = dict(result)
    if isinstance(result.get("workflow"), dict):
        result["workflow"] = compact_workflow(result["workflow"], offset)
    if isinstance(result.get("provisional"), list):
        sources = result["provisional"]
        result["provisional"] = [
            {**source, "release": str(source.get("release", ""))[:180]}
            for source in sources[offset : offset + 5]
        ]
        result["provisional_next_offset"] = offset + 5 if len(sources) > offset + 5 else None
    if isinstance(result.get("choice_set"), dict):
        choice = dict(result["choice_set"])
        candidates = choice.get("candidates") or []
        choice["candidates"] = [
            {**source, "release": str(source.get("release", ""))[:180]}
            for source in candidates[offset : offset + 5]
        ]
        choice["next_offset"] = offset + 5 if len(candidates) > offset + 5 else None
        result["choice_set"] = choice
    plan = result.get("plan")
    if isinstance(plan, dict):
        result["plan"] = {
            key: value
            for key, value in plan.items()
            if key
            in {
                "source_id",
                "device_id",
                "mode",
                "position",
                "audio",
                "subtitle",
                "video",
                "duration",
                "warnings",
                "interrupts",
                "preparation_strategy",
            }
        }
    return result


def compact_media_page(result, offset=0):
    fields = {
        "id",
        "media_id",
        "queue_id",
        "title",
        "kind",
        "year",
        "parent_id",
        "season",
        "episode",
        "position",
        "duration",
        "watched",
        "favorite",
        "watchlist",
        "version",
        "last_watched_at",
    }
    return {
        "items": [
            {key: value for key, value in row.items() if key in fields} for row in result["items"][:10]
        ],
        "next_offset": offset + 10 if len(result["items"]) > 10 else result.get("next_offset"),
    }


class Recommendation(Input):
    query: str = Field(min_length=1, max_length=200, description="Exact title to look up")
    kind: Literal["movie", "series", "anime"] = "movie"
    year: str | None = Field(default=None, max_length=4)
    why: str = Field(min_length=1, max_length=200, description="One spoiler-free line on why it fits")


class Recommend(Input):
    items: list[Recommendation] = Field(min_length=1, max_length=10)


def synopsis(text):
    """First sentence or two, never the whole plot."""
    text = " ".join(str(text or "").split())
    cut = next((i + 1 for i, c in enumerate(text) if c in ".!?" and i > 60), len(text))
    return text[: min(cut, 240)].rstrip() + ("…" if min(cut, 240) < len(text) else "")


def cinema_recommend(body, actor, db):
    """Resolve Nox's picks to real catalogue titles and show them as a poster card."""
    from .cinema import search

    shown, missing = [], []
    for pick in body.items:  # ponytail: sequential catalogue lookups (~0.5 s each), fine for 10
        try:
            found = search(pick.query, pick.kind, actor, db)["items"]
        except HTTPException:
            found = []
        match = next((t for t in found if pick.year and str(t.get("year", "")).startswith(pick.year)), None)
        match = match or (found[0] if found else None)
        if not match or any(t["id"] == match["id"] for t in shown):
            missing.append(pick.query)
            continue
        shown.append(
            {
                "id": match["id"],
                "title": match["title"],
                "kind": match["kind"],
                "year": match.get("year"),
                "poster": match.get("poster"),
                "genres": match.get("genres", [])[:3],
                "runtime": match.get("runtime"),
                "cast": match.get("cast", [])[:3],
                "director": match.get("director", [])[:1],
                "rating": match.get("rating"),
                "synopsis": synopsis(match.get("description")),
                "why": pick.why,
                "href": "/watch?title=" + match["id"],
            }
        )
    return {
        "status": "shown",
        "shown": [t["title"] + (" (" + t["year"] + ")" if t.get("year") else "") for t in shown],
        "not_found": missing,
        "card": {"kind": "titles", "domain": "cinema", "status": "completed", "items": shown},
    }


class TitleRead(QueueRead):
    id: str
    season: int | None = Field(default=None, ge=0, le=100)


class CatalogFilter(QueueRead):
    kind: Literal["movie", "series", "anime"] = "movie"
    query: str = Field(default="", max_length=200)
    year_from: int | None = Field(default=None, ge=1880, le=2100)
    year_to: int | None = Field(default=None, ge=1880, le=2100)
    genre: str = Field(default="", max_length=40)
    tag: str = Field(
        default="", max_length=200, description="theme keys, comma separated: zombies, heist, isekai…"
    )
    person: str = Field(default="", max_length=120, description="director, actor, or anime studio")
    award: str = Field(default="", max_length=40, description="best-picture, palme-dor, cesar, golden-lion…")
    sort: Literal["known", "newest", "oldest", "rated"] = "known"


def catalog_filter(body, actor, db):
    from .cinema import explore

    fields = {"kind", "year_from", "year_to", "genre", "tag", "person", "award", "sort", "offset"}
    result = route(explore, q=body.query, actor=actor, db=db, **body.model_dump(include=fields))
    return {
        "total": result["total"],
        "items": [
            {k: t.get(k) for k in ("id", "title", "year", "kind", "director")} for t in result["items"][:10]
        ],
    }


def title_snapshot(body, actor, db):
    from .cinema import details

    result = details(body.id, actor, db)
    episodes = result.pop("episodes", [])
    if body.season is not None:
        episodes = [episode for episode in episodes if episode.get("season") == body.season]
    result["description"] = result.get("description", "")[:500]
    return {
        **result,
        "episodes": episodes[body.offset : body.offset + 10],
        "next_offset": body.offset + 10 if len(episodes) > body.offset + 10 else None,
    }


class QueueItemVersion(Input):
    item_id: str
    expected_version: int = Field(ge=1)


class QueueMove(QueueItemVersion):
    before_item_id: str | None = None


class MediaStateRead(QueueRead):
    scope: Literal["personal", "shared"] = "personal"
    filter: Literal["continue", "watchlist", "favorites", "history", "all"] = "all"


class WatchlistShare(Input):
    media_id: str
    shared: bool


def shared_watchlist(body, actor, db):
    from . import cinema, cinema_watchlist

    if body.scope == "personal":
        result = cinema.media_state(body.filter, actor, db, offset=body.offset)
        return compact_media_page(result, body.offset)
    if body.filter not in {"all", "watchlist"}:
        raise HTTPException(
            422, "Only explicitly shared watchlist titles are visible; histories stay private"
        )
    result = cinema_watchlist.list_shared(actor, db, body.offset)
    return {
        "items": [
            {
                "media_id": r["media"]["id"],
                "title": r["media"]["title"],
                "shared_by": r["shared_by"],
                "mine": r["mine"],
            }
            for r in result["items"][:10]
        ],
        "next_offset": body.offset + 10 if len(result["items"]) > 10 else result["next_offset"],
    }


def share_watchlist(body, actor, db):
    from . import cinema_watchlist

    return (cinema_watchlist.share if body.shared else cinema_watchlist.unshare)(body.media_id, actor, db)


class MediaStateWrite(StateUpdate):
    media_id: str


class CinemaSleep(SleepTimer):
    workflow_id: str


class CinemaTransport(PlaybackControl):
    workflow_id: str


class EpisodeIdentity(Input):
    media_id: str
    season: int = Field(ge=0, le=100)
    episode: int = Field(ge=1, le=1000)


class TVControl(TVAction):
    device_id: str


def page_items(items, offset):
    return {
        "items": items[offset : offset + 10],
        "next_offset": offset + 10 if len(items) > offset + 10 else None,
    }


def music_snapshot(body, actor, db):
    from .music import state

    result = state(actor, db)
    items = result.pop("items")
    result["current_item"] = next((item for item in items if item["id"] == result.get("current_id")), None)
    return {**result, **page_items(items, body.offset)}


def playlist_card(result):
    if result.get("confirmation_id"):
        result["confirmation_path"] = "/music/playlists/" + result["confirmation_id"] + "/confirm"
    return result


def tv_card(result):
    result["status"] = "needs_confirmation"
    result["confirmation_path"] = "/cinema/device-confirmations/" + result["confirmation_id"]
    return result


def space_summary(result):
    return {
        "configured": result.get("configured"),
        "day": result.get("day"),
        "sections": [
            {
                "kind": section["kind"],
                "sources": section.get("sources", []),
                "items": [
                    {key: item[key] for key in ("id", "title", "provider") if key in item}
                    for item in section.get("items", [])[:5]
                ],
            }
            for section in result.get("sections", [])
        ],
    }


def assistant_devices(actor, db, tv=False):
    from .cinema import devices

    result = devices(actor, db)
    config = integration_config(db, "home_assistant")
    mapped = (
        config.get("receiver_id")
        if config.get("enabled") and (config.get("token") or config.get("api_key"))
        else None
    )
    items = []
    for row in result["items"][:10]:
        item = {key: row[key] for key in ("id", "name", "adapter", "version", "state") if key in row}
        item.update(
            maximum_resolution=row.get("capabilities", {}).get("maximum_resolution"), reboot_supported=False
        )
        if row["id"] == mapped:
            hisense = (
                "vidaa" in config.get("device_id", "").casefold()
                or "hisense" in config.get("device_id", "").casefold()
            )
            target = {
                "name": "Hisense TV" if hisense else "Linked TV",
                "aliases": [
                    "TV",
                    "television",
                    "télévision",
                    "télé",
                    *(["Hisense", "VIDAA"] if hisense else []),
                ],
                "controls": [
                    action
                    for action, cap in (
                        ("power_on", "power_on"),
                        ("power_off", "power_off"),
                        ("volume", "volume_absolute"),
                        ("input", "set_input"),
                    )
                    if row.get("capabilities", {}).get(cap) is True
                ],
            }
            item["tv_control_target"] = target
            if tv:
                item.update(target, adapter="home_assistant", linked_playback_name=row["name"])
                item.pop("tv_control_target")
                item.pop("maximum_resolution")
                try:
                    state = assistant_tv_state(MemoryId(id=row["id"]), actor, db)
                    item.update({key: value for key, value in state.items() if key != "display_name"})
                except HTTPException as exc:
                    item.update(state="unavailable", error=exc.detail)
        if not tv or row["id"] == mapped:
            items.append(item)
    return {"items": items} if tv else {"items": items, "setup_required": result.get("setup_required", [])}


def assistant_tv_state(body, actor, db):
    from .cinema_tv import tv_state

    result = tv_state(body.id, actor, db)
    return {
        key: result[key]
        for key in (
            "state",
            "display_name",
            "changed_at",
            "observed_at",
            "volume",
            "input",
            "reboot_supported",
            "power_off_supported",
        )
        if key in result
    } | {"inputs": [name for name in result.get("inputs", []) if str(name).upper().startswith("HDMI")][:10]}


class AutoNext(Input):
    shuffle: bool = False


def auto_next(body, actor, db):
    from . import music_auto

    plan = music_auto.upcoming(actor, db)
    if body.shuffle and plan["items"]:
        plan = music_auto.change_upcoming(music_auto.Plan(version=plan["version"], shuffle=True), actor, db)
    return {
        "mode": plan["mode"],
        "next": [
            f"{i['title']}" + (f" ({i['genre']})" if i.get("genre") else "") for i in plan["items"][:10]
        ],
        "total": len(plan["items"]),
    }


class MusicControl(Input):
    """Assistant music control. The queue version only guards a stale screen; a spoken
    request acts on the queue as it is now."""

    action: Literal["play", "pause", "seek", "volume", "mute", "skip", "previous", "clear", "sleep", "repeat"]
    value: Annotated[float, Field(ge=0, le=86400)] | Literal["off", "one", "queue"] | None = Field(
        default=None,
        description="volume 0-100; seek position in seconds; sleep minutes; mute 1/0; repeat off/one/queue",
    )
    idempotency_key: str = Field(min_length=8, max_length=100)


def music_control(body, actor, db):
    from . import music

    # locked, so control sees the same row
    return music.control(
        music.Control(**body.model_dump(), expected_version=music.queue(db).version), actor, db
    )


# Tool bundles. "general" is the default and covers everyday music, house and memory
# requests in one round; specialised bundles load through routing or switch_context.
BUNDLES = {
    "general": (
        "users_lookup",
        "memory_list",
        "memory_save",
        "memory_delete",
        "music_get_state",
        "music_search",
        "music_add",
        "music_add_candidates",
        "music_control",
        "radio_search",
        "radio_queue",
        "household_list",
        "household_create",
        "task_action",
        "groceries_purchase",
        "groceries_undo",
        "calendar_agenda",
        "calendar_digest",
        "music_queue_favorites",
        "messages_send",
        "inbox_list",
        "home_list",
        "home_control",
        "tv_remote",
        "tv_show_video",
    ),
    "music": (
        "users_lookup",
        "household_list",
        "memory_list",
        "music_get_state",
        "music_search",
        "radio_search",
        "radio_queue",
        "music_add",
        "music_control",
        "music_add_candidates",
        "music_auto",
        "music_auto_next",
    ),
    "music_library": (
        "music_get_state",
        "music_remove",
        "music_reorder",
        "music_veto",
        "music_history",
        "music_saved",
        "music_save",
        "music_playlists",
        "music_playlist_save",
        "music_playlist_prepare",
        "music_playlist_url_prepare",
        "music_playlist_add",
        "music_playlists_prepare",
    ),
    "household": (
        "users_lookup",
        "household_list",
        "household_create",
        "household_update",
        "task_action",
        "groceries_purchase",
        "groceries_undo",
        "calendar_agenda",
        "messages_send",
        "inbox_list",
    ),
    "files": (
        "files_search",
        "files_folder",
        "files_move",
        "files_prepare",
        "files_roots",
        "files_read_excerpt",
        "files_quota",
        "users_lookup",
    ),
    "cinema": (
        "cinema_browse",
        "cinema_search",
        "cinema_filter",
        "cinema_similar",
        "cinema_details",
        "cinema_recommend",
        "cinema_cloud_inventory",
        "devices_list",
        "cinema_discover",
        "cinema_operation",
        "cinema_sources",
        "cinema_workflow",
        "cinema_launch",
        "cinema_change",
        "tv_get_state",
        "tv_control",
    ),
    "cinema_library": (
        "cinema_queue",
        "cinema_queue_add",
        "cinema_queue_clear_prepare",
        "cinema_queue_remove",
        "cinema_state",
        "cinema_watchlist_share",
        "cinema_state_update",
        "cinema_history_remove",
        "cinema_sources",
        "cinema_sleep",
        "cinema_workflow",
        "cinema_save_locally",
        "cinema_control",
        "cinema_next_episode",
    ),
    "tv": (
        "tv_devices",
        "tv_get_state",
        "tv_control",
        "tv_remote",
        "tv_film_input",
        "tv_show_video",
        "cinema_search",
        "cinema_discover",
    ),
    "diagnostics": (
        "music_get_state",
        "diagnostics_get_health",
        "diagnostics_get_operation",
        "devices_list",
        "house_update",  # "is there an update?" / "update HouseOS" (admins; a confirmation card)
    ),
    "setup": (*SETUP_TOOLS, *API_TOOLS, *CODE_TOOLS, "diagnostics_get_health"),  # admin-only house-setup mode
    "home": ("home_list", "home_control", "tv_remote", "memory_list"),
}


def tool_catalogue():
    """Every assistant tool once: name -> (input model, description, handler)."""
    from . import (
        music,
        household,
        cinema,
        core,
        cinema_jobs,
        cinema_tv,
        cinema_queue,
        cinema_sleep,
        music_library,
        music_auto,
        assistant_cinema_contract as contract,
    )
    from .assistant import Memory, enabled_memories, delete_memory, prepare_cinema_queue_clear
    from .tool_household import build_tools
    from .tool_home import TOOLS as home_tools
    from .tool_tv import TOOLS as tv_tools

    tv_prepare = lambda b, a, d: tv_card(
        cinema_tv.tv_prepare(b.device_id, cinema_tv.TVAction(**b.model_dump(exclude={"device_id"})), a, d)
    )  # noqa: E731
    return {
        **build_tools("household"),
        **build_tools("files"),
        **SETUP_TOOLS,
        **API_TOOLS,
        **CODE_TOOLS,
        **home_tools,
        **tv_tools,
        "memory_list": (Empty, "Read your own saved memories.", lambda b, a, d: enabled_memories(a, d)[:5]),
        "memory_save": (
            Memory,
            "Remember something for this person when they ask; returns a card they confirm to keep it.",
            lambda b, a, d: confirmation(
                a,
                d,
                "assistant.memory_save",
                b.model_dump(mode="json"),
                "Remember this",
                {"name": b.text, "effect": "Nox keeps this; you can see and forget it in Settings"},
            ),
        ),
        "memory_delete": (
            MemoryId,
            "Forget the selected personal memory when explicitly requested.",
            lambda b, a, d: delete_memory(b.id, a, d),
        ),
        # Music
        "music_get_state": (
            QueueRead,
            "What is playing, volume and ten queue entries; paginate by offset.",
            music_snapshot,
        ),
        "music_search": (
            MusicSearch,
            "Search 1-10 YouTube or SoundCloud songs; set limit to the number wanted. Returns candidate IDs.",
            lambda b, a, d: music.search(b.query, b.source, a, d, limit=b.limit),
        ),
        "music_add": (
            music.Add,
            "Queue one explicit YouTube/SoundCloud URL. Starts at once when the jukebox is idle or paused.",
            lambda b, a, d: music.enqueue(b, a, d),
        ),
        "music_add_candidates": (
            music.CandidateBatch,
            "Queue 1-10 searched songs in ONE ordered call using their exact candidate IDs. Starts the first when idle or paused. avoid_duplicates skips songs already queued.",
            lambda b, a, d: music.add_candidates(b, a, d),
        ),
        "music_control": (
            MusicControl,
            "play, pause, volume, mute, skip, previous, seek, sleep timer, repeat, clear (clear asks for confirmation).",
            music_control,
        ),
        "radio_search": (
            RadioSearch,
            "Find up to five real internet radio stations by name, genre, country code or language.",
            radio_search,
        ),
        "radio_queue": (
            RadioQueue,
            "Play or queue a found radio station by its UUID (starts like a song when the jukebox is idle).",
            radio_queue,
        ),
        "music_remove": (
            QueueItemVersion,
            "Remove your pending queue entry at the current queue version.",
            lambda b, a, d: music.remove(b.item_id, b.expected_version, a, d),
        ),
        "music_reorder": (
            QueueMove,
            "Move any waiting queue entry, anyone's; null before_item_id moves it to the end.",
            lambda b, a, d: music.reorder(
                b.item_id, music.Reorder(**b.model_dump(exclude={"item_id"})), a, d
            ),
        ),
        "music_veto": (
            QueueItemVersion,
            "Spend the user's one veto (back 3 h after use) on someone else's song: skips it if "
            "playing, removes it if waiting. Only when the user asks to veto.",
            lambda b, a, d: music.veto(
                b.item_id, music.QueueVersion(expected_version=b.expected_version), a, d
            ),
        ),
        "music_history": (
            QueueRead,
            "Five recently played songs with who requested them; paginate by offset.",
            lambda b, a, d: route(music.history, offset=b.offset, limit=5, actor=a, db=d),
        ),
        "music_saved": (
            QueueRead,
            "Ten of your saved tracks.",
            lambda b, a, d: page_items(music.saved(a, d), b.offset),
        ),
        "music_save": (
            music.Add,
            "Save a track URL to your library.",
            lambda b, a, d: music.save_track(b, a, d),
        ),
        "music_playlists": (
            QueueRead,
            "Your playlists by ID, name and size.",
            lambda b, a, d: page_items(
                [
                    {"id": r["id"], "name": r.get("name"), "count": len(r.get("items", []))}
                    for r in music_library.playlists(a, d)["items"]
                ],
                b.offset,
            ),
        ),
        "music_playlist_save": (
            music_library.NamedPlaylist,
            "Save a named playlist: empty, from exact queue entries (item_ids) or song URLs (source_urls).",
            lambda b, a, d: music_library.save_playlist(b, a, d),
        ),
        "music_playlist_prepare": (
            MemoryId,
            "Preview queueing a saved playlist; returns a confirmation.",
            lambda b, a, d: playlist_card(music_library.playlist_preview(b.id, a, d)),
        ),
        "music_playlist_url_prepare": (
            music.Add,
            "Preview queueing a playlist URL; returns a confirmation.",
            lambda b, a, d: playlist_card(music.preview_playlist(b, a, d)),
        ),
        "music_playlist_add": (
            PlaylistAdd,
            "Add one song URL to the end of your playlist (by ID).",
            lambda b, a, d: music_library.add_to_playlist(b.id, b, a, d),
        ),
        "music_playlists_prepare": (
            music_library.PlaylistQueue,
            "Preview queueing several of your playlists together (ids), optionally shuffled; returns a confirmation.",
            lambda b, a, d: playlist_card(music_library.queue_playlists(b, a, d)),
        ),
        # Cinema
        "cinema_browse": (
            CatalogBrowse,
            "Browse titles: catalog top=popular, imdbRating=featured, year=release year (genre=e.g. 2026). Genres: Action, Animation, Comedy, Drama, Sci-Fi, Thriller. Returns title IDs.",
            browse_catalog,
        ),
        "cinema_search": (
            CinemaSearch,
            "Find exact movie, series or anime titles and their IDs.",
            lambda b, a, d: cinema.search(b.query, b.kind, a, d),
        ),
        "cinema_filter": (
            CatalogFilter,
            "Find titles by year range, genre, theme tag, director/actor/studio or award (all at "
            "once, instant). Returns the total and ten title IDs.",
            catalog_filter,
        ),
        "cinema_similar": (
            TitleRead,
            "Titles like this one (MyAnimeList members' picks for anime; same director, cast and "
            "themes for films) and, for anime, the same franchise.",
            lambda b, a, d: {
                key: [{k: t.get(k) for k in ("id", "title", "year", "kind")} for t in value][:10]
                if isinstance(value, list)
                else value
                for key, value in cinema.similar_titles(b.id, a, d).items()
            },
        ),
        "cinema_recommend": (
            Recommend,
            "Show up to 10 recommended titles as a poster card the resident can tap to open in Watch.",
            cinema_recommend,
        ),
        "music_auto": (
            music_auto.Auto,
            "Auto play when the queue runs dry: mode library (songs the house keeps, optionally only "
            "these genres, only songs these people (user ids) kept or played, only within the last "
            "7/30/90/365 days), radio (station ids in rotation, each for some songs or minutes), or off. "
            "Requests always go first. Turning it on while nothing plays starts the music.",
            lambda b, a, d: music_auto.set_auto(b, a, d),
        ),
        "music_auto_next": (
            AutoNext,
            "The next songs auto play will pick (library mode), in order; shuffle=true draws a new list.",
            auto_next,
        ),
        "music_queue_favorites": (
            Empty,
            "Queue 10 random songs from the house's 100 most played. No search needed.",
            lambda b, a, d: music.queue_favorites(d, a),
        ),
        "calendar_digest": (
            Empty,
            "The week ahead in one call: this week's events by day, notable later ones and tasks due soon. Use it for 'this week' or 'what's coming up'; calendar_agenda is for other date ranges.",
            lambda b, a, d: household.calendar_digest(d, a),
        ),
        "cinema_details": (
            TitleRead,
            "Title details and ten episodes; filter by season, paginate by offset.",
            title_snapshot,
        ),
        "cinema_cloud_inventory": (
            QueueRead,
            "Ten items already in the debrid cloud; pass cloud_id to discovery for an exact match.",
            lambda b, a, d: page_items(cinema.cloud_inventory(a, d)["items"], b.offset),
        ),
        "devices_list": (
            Empty,
            "Playback screens and their capabilities.",
            lambda b, a, d: assistant_devices(a, d),
        ),
        "cinema_discover": (
            contract.AgentDiscover,
            "Find and check versions of an exact title ID (movies: null season/episode) with an optional start position in seconds. Runs in the background; the first candidate is the house suggestion.",
            contract.discover,
        ),
        "cinema_operation": (
            WorkflowRead,
            "Progress of a discovery operation and five source summaries; paginate by offset.",
            lambda b, a, d: compact_workflow(cinema_jobs.get_operation(b.id, a, d), b.offset),
        ),
        "cinema_sources": (
            SourcePage,
            "Five frozen sources at a resolution (0=unknown) with totals; paginate with next_offset.",
            lambda b, a, d: cinema.source_page(
                b.id, offset=b.offset, resolution=b.resolution, limit=5, actor=a, db=d
            ),
        ),
        "cinema_workflow": (
            WorkflowRead,
            "A playback workflow's state and five source summaries; paginate by offset.",
            lambda b, a, d: compact_workflow(cinema.workflow(b.id, a, d), b.offset),
        ),
        "cinema_launch": (
            CinemaLaunch,
            "Play a checked version on a screen with the exact audio/subtitle ids and start position; asks before replacing something already playing.",
            lambda b, a, d: compact_workflow(
                cinema.launch(b.workflow_id, cinema.Launch(**b.model_dump(exclude={"workflow_id"})), a, d)
            ),
        ),
        "cinema_change": (
            CinemaChange,
            "Prepare a track, source or screen change; returns an approval.",
            lambda b, a, d: cinema.change(
                b.workflow_id, cinema.Change(**b.model_dump(exclude={"workflow_id"})), a, d
            ),
        ),
        "cinema_queue": (
            QueueRead,
            "Ten titles or episodes in your movie queue.",
            lambda b, a, d: compact_media_page(cinema_queue.list_queue(a, d, offset=b.offset), b.offset),
        ),
        "cinema_queue_add": (
            cinema_queue.QueueAdd,
            "Add an exact title or episode to your movie queue (doesn't play).",
            lambda b, a, d: cinema_queue.enqueue_title(b, a, d),
        ),
        "cinema_queue_clear_prepare": (
            Empty,
            "Preview clearing your movie queue; returns a confirmation.",
            prepare_cinema_queue_clear,
        ),
        "cinema_queue_remove": (
            MemoryId,
            "Remove an entry from your movie queue.",
            lambda b, a, d: cinema_queue.remove_queued(b.id, a, d),
        ),
        "cinema_state": (
            MediaStateRead,
            "Your continue-watching, watchlist, favorites or history; or titles shared to the house watchlist.",
            shared_watchlist,
        ),
        "cinema_watchlist_share": (
            WatchlistShare,
            "Share or unshare one title on the house watchlist when asked.",
            share_watchlist,
        ),
        "cinema_state_update": (
            MediaStateWrite,
            "Set watched/favorite/watchlist using the title's current revision.",
            lambda b, a, d: cinema.update_media_state(
                b.media_id, cinema.StateUpdate(**b.model_dump(exclude={"media_id"}, exclude_unset=True)), a, d
            ),
        ),
        "cinema_history_remove": (
            MemoryId,
            "Remove a title from your playback history when asked.",
            lambda b, a, d: cinema.remove_history(b.id, a, d),
        ),
        "cinema_sleep": (
            CinemaSleep,
            "Sleep timer for your current movie; minutes=0 cancels. TV power off only when asked.",
            lambda b, a, d: cinema_sleep.set_timer(
                b.workflow_id, SleepTimer(**b.model_dump(exclude={"workflow_id"})), a, d
            ),
        ),
        "cinema_save_locally": (
            WorkflowVersion,
            "Prepare saving the validated release to the house library (quota checked); returns an approval.",
            lambda b, a, d: cinema.prepare_save_local(b.workflow_id, cinema.Version(version=b.version), a, d),
        ),
        "cinema_control": (
            CinemaTransport,
            "Pause, resume, seek, volume or stop your current movie.",
            lambda b, a, d: cinema.control(
                b.workflow_id, cinema.Control(**b.model_dump(exclude={"workflow_id"})), a, d
            ),
        ),
        "cinema_next_episode": (
            EpisodeIdentity,
            "The exact next episode of a series (doesn't play).",
            lambda b, a, d: cinema.next_episode(b.media_id, b.season, b.episode, a, d),
        ),
        # TV and diagnostics
        "tv_devices": (
            Empty,
            "TV displays with current state and HDMI inputs (separate from movie screens).",
            lambda b, a, d: assistant_devices(a, d, tv=True),
        ),
        "tv_get_state": (MemoryId, "Current state, input and volume of a TV display.", assistant_tv_state),
        "tv_control": (
            TVControl,
            "TV power on/off, HDMI input (exact label) or volume percent; returns a confirmation. Not a reboot.",
            tv_prepare,
        ),
        "diagnostics_get_health": (
            Empty,
            "Integration health and evidence freshness.",
            lambda b, a, d: cinema.health(a, d),
        ),
        "diagnostics_get_operation": (
            MemoryId,
            "Outcome and evidence of one of your operations.",
            lambda b, a, d: core.get_operation(b.id, a, d),
        ),
    }


def tool_registry(context):
    if context == "personal_space":
        from . import personal_space as space

        return {
            "personal_space_options": (
                Empty,
                "Read presets, current settings and version again (the context note has them); use after a version conflict.",
                lambda b, a, d: space.options(a, d),
            ),
            "personal_space_art_tags": (
                space.ArtTagSearch,
                "Look up up to five real canonical illustration tags for a character/theme, with provider counts. Resolve ambiguity before configuring.",
                lambda b, a, d: space.art_tags(b.query, a),
            ),
            "personal_space_configure": (
                space.SpaceConfig,
                "Save the user's expressed daily-feed choices; preserve unrelated settings and send the current version.",
                lambda b, a, d: space.configure(b, a, d),
            ),
            "personal_space_finish": (
                Empty,
                "Close setup only after the resident explicitly confirms the saved space is good in their current message.",
                lambda b, a, d: space.finish_setup(a, d),
            ),
            "personal_space_today": (
                Empty,
                "Read compact current daily feed results and real source errors; never run a model for daily selection.",
                lambda b, a, d: space_summary(space.today(a, d)),
            ),
        }
    if context == "themes":  # the studio's own tools only; no switching to the house's
        from .tool_themes import TOOLS

        return dict(TOOLS)
    catalogue = tool_catalogue()
    tools = {name: catalogue[name] for name in BUNDLES.get(context, BUNDLES["general"])}
    if "tv_devices" in tools:  # The TV bundle's device list is TV controls, under its usual name.
        tools = {("devices_list" if name == "tv_devices" else name): tool for name, tool in tools.items()}
    if context != "setup":  # setup mode keeps its own tools
        tools["switch_context"] = CONTEXT_TOOL
    return tools


class CinemaSearch(Search):
    kind: Literal["movie", "series", "anime"] = "movie"


class WorkflowVersion(Input):
    workflow_id: str
    version: int = Field(ge=1)


class CinemaLaunch(Launch):
    workflow_id: str


class CinemaChange(CinemaChangeBody):
    workflow_id: str


def omit_default_nulls(value, schema):
    """Undo strict-provider null placeholders, including nested union/list models."""
    from typing import get_args, get_origin, Union
    from types import UnionType
    from pydantic import BaseModel, TypeAdapter

    origin = get_origin(schema)
    if origin in (Union, UnionType):
        candidates = get_args(schema)
        # Discriminated domain records must use their own defaults, never the first variant.
        if isinstance(value, dict):
            tagged = [
                candidate
                for candidate in candidates
                if isinstance(candidate, type)
                and issubclass(candidate, BaseModel)
                and any(
                    get_origin(field.annotation) is Literal
                    and key in value
                    and value[key] in get_args(field.annotation)
                    for key, field in candidate.model_fields.items()
                )
            ]
            if tagged:
                candidates = tagged
        for candidate in candidates:
            normalized = omit_default_nulls(value, candidate)
            try:
                TypeAdapter(candidate).validate_python(normalized)
                return normalized
            except ValidationError:
                pass
        return value  # Keep invalid/extra fields for the caller's validation error.
    if origin is list and isinstance(value, list):
        return [omit_default_nulls(item, get_args(schema)[0]) for item in value]
    if not isinstance(value, dict) or not isinstance(schema, type) or not issubclass(schema, BaseModel):
        return value
    result = {}
    for key, item in value.items():
        field = schema.model_fields.get(key)
        if (
            field
            and item is None
            and not field.is_required()
            and (field.default is not None or field.default_factory is not None)
        ):
            continue
        result[key] = omit_default_nulls(item, field.annotation) if field else item
    return result


def tool_schemas(registry):
    """What a provider sees of each tool. idempotency_key is left out: execute_tool always
    sets a fresh one, so the model would only write throwaway output."""
    schemas = []
    for name, (model, desc, _) in registry.items():
        parameters = compact_schema(model.model_json_schema())
        if parameters.get("properties", {}).pop("idempotency_key", None):
            parameters["required"] = [n for n in parameters.get("required", []) if n != "idempotency_key"]
        schemas.append({"name": name, "description": desc, "parameters": parameters})
    return schemas


def compact_schema(schema):
    """Pydantic's schema without titles, defaults or additionalProperties (the models forbid
    extras themselves); an optional `X | None = None` is plain X, left out of required.
    OpenAI's strict mode gets strict_schema() of this."""
    if isinstance(schema, list):
        return [compact_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    options = schema.get("anyOf", [])
    if schema.get("default", 0) is None and len(options) == 2 and {"type": "null"} in options:
        schema = {key: value for key, value in schema.items() if key != "anyOf"} | next(
            x for x in options if x != {"type": "null"}
        )
    # Property/definition names are data: a field named "title" is not an annotation.
    return {
        key: {name: compact_schema(child) for name, child in value.items()}
        if key in {"properties", "$defs"}
        else compact_schema(value)
        for key, value in schema.items()
        if key not in {"title", "default"} and (key, value) != ("additionalProperties", False)
    }


def strict_schema(schema):
    if isinstance(schema, dict):
        # Property/definition names are data: a field named "title" is not an annotation.
        result = {}
        for key, value in schema.items():
            if key in {"default", "title"}:
                continue
            result[key] = (
                {name: strict_schema(child) for name, child in value.items()}
                if key in {"properties", "$defs", "definitions"}
                else strict_schema(value)
            )
        schema = result
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            props = schema.get("properties", {})
            required = schema.get("required", [])
            for name in props:
                if name not in required and not any(
                    item.get("type") == "null" for item in props[name].get("anyOf", [])
                ):
                    props[name] = {"anyOf": [props[name], {"type": "null"}]}
            schema["required"] = list(props)
    elif isinstance(schema, list):
        schema = [strict_schema(x) for x in schema]
    return schema


# Result cards are deterministic summaries of authorized service results, never model claims.
ACTION_LABELS = {
    "music_add": "Added to music queue",
    "music_add_candidate": "Added to music queue",
    "music_add_candidates": "Added to music queue",
    "music_control": "Music control",
    "music_remove": "Removed from music queue",
    "music_reorder": "Music queue reordered",
    "music_veto": "Veto used",
    "music_auto": "Auto play",
    "music_auto_next": "Auto play list",
    "music_save": "Track saved",
    "music_playlist_save": "Playlist saved",
    "music_playlist_prepare": "Playlist preview",
    "music_playlist_url_prepare": "Playlist preview",
    "music_playlist_add": "Added to playlist",
    "music_playlists_prepare": "Playlist preview",
    "radio_queue": "Radio queue",
    "household_create": "House record created",
    "household_update": "House record updated",
    "task_action": "Task updated",
    "groceries_purchase": "Groceries updated",
    "groceries_undo": "Grocery changes undone",
    "messages_send": "Message",
    "files_folder": "Folder created",
    "files_move": "File updated",
    "files_prepare": "File action",
    "files_read_excerpt": "File excerpt",
    "memory_delete": "Memory removed",
    "personal_space_configure": "Personal space updated",
    "cinema_discover": "Finding movie sources",
    "cinema_change": "Playback change",
    "cinema_queue_add": "Added to Cinema queue",
    "cinema_queue_remove": "Removed from Cinema queue",
    "cinema_queue_clear_prepare": "Clear movie queue",
    "cinema_state_update": "Cinema preferences updated",
    "cinema_watchlist_share": "Watchlist sharing",
    "cinema_history_remove": "History updated",
    "cinema_sleep": "Movie sleep timer",
    "cinema_save_locally": "Local movie save",
    "cinema_control": "Movie control",
    "tv_control": "TV control",
    "home_control": "Smart home",
    "tv_remote": "TV remote",
    "tv_film_input": "Film TV input",
    "tv_show_video": "Show on the TV",
}


def action_recap(name, args, result, actor, db):
    if (
        name not in ACTION_LABELS
        or not isinstance(result, dict)
        or result.get("status") == "needs_clarification"  # a question for the resident, not an action
    ):
        return None
    domain = (
        "music"
        if name.startswith(("music_", "radio_"))
        else "cinema"
        if name.startswith(("cinema_", "tv_"))
        else "files"
        if name.startswith("files_")
        else "space"
        if name.startswith("personal_space_")
        else "settings"
        if name.startswith("memory_")
        else "house"
    )
    status = result.get("status", result.get("state", "completed"))
    label = ACTION_LABELS[name]
    # A failure or preview never receives a completed-action heading.
    if status in {
        "failed",
        "denied",
        "conflict",
        "unavailable",
        "unverified",
        "needs_confirmation",
        "needs_choice",
    } or result.get("confirmation_id"):
        label = (
            "TV control"
            if name in {"tv_control", "tv_remote"}
            else "Clear movie queue"
            if name == "cinema_queue_clear_prepare"
            else {
                "music": "Music action",
                "cinema": "Movie action",
                "files": "File action",
                "house": "House action",
                "space": "Personal space",
                "settings": "Memory action",
            }[domain]
        )
    fields = result.get("summary") or result.get("data") or result.get("preview") or result
    rows = result.get("items")
    summaries = []
    for row in (rows if isinstance(rows, list) else [fields])[:10]:
        if not isinstance(row, dict):
            continue
        title = row.get("title") or row.get("label") or row.get("name")
        if not title and row.get("id") and name == "groceries_purchase":
            record = db.get(Record, row["id"])
            if record and record.kind == "household.groceries":
                title = record.data.get("label")
        if title:
            summaries.append(
                {
                    "title": str(title)[:200],
                    "detail": " · ".join(
                        str(row[key])[:100]
                        for key in ("quantity", "unit", "start", "due_date", "status")
                        if row.get(key) is not None
                    ),
                }
            )
    if not summaries and name in {"music_add", "music_add_candidate"}:
        from .music import QueueItem

        item = db.get(QueueItem, result.get("item_id")) if result.get("item_id") else None
        candidate = (
            db.scalar(
                select(Record).where(
                    Record.id == args.get("candidate_id"),
                    Record.owner_id == actor.id,
                    Record.kind == "music_candidate",
                )
            )
            if args.get("candidate_id")
            else None
        )
        title = (candidate.data.get("title") if candidate else None) or (item.title if item else None)
        if title:
            summaries.append({"title": str(title)[:200]})
    if name == "personal_space_configure":
        summaries = [
            {"title": key.replace("_", " "), "detail": ", ".join(map(str, result[key]))}
            for key in ("news_interests", "subreddits", "art_tags")
            if result.get(key)
        ]
    detail = None
    if args.get("action"):
        detail = str(args["action"]) + (": " + str(args["value"]) if args.get("value") is not None else "")
    if name == "music_add_candidates" and result.get("duplicates_skipped"):
        detail = str(result["duplicates_skipped"]) + " duplicate queue entries skipped"
    if name == "cinema_sleep":
        detail = str(args.get("minutes", 0)) + " min"
    return {
        "kind": "result",
        "label": label,
        "domain": domain,
        "status": status,
        "items": summaries,
        "count": result.get("count", len(rows) if isinstance(rows, list) else None),
        "detail": detail,
        "href": {
            "music": "/music",
            "cinema": "/cinema",
            "files": "/files",
            "space": "/space",
            "settings": "/settings",
            "house": "/house",
        }[domain],
        "operation_id": result.get("operation_id"),
        "workflow_id": result.get("workflow_id"),
    }
