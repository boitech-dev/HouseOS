"""The widget door: what plays and what's on, for another assistant's widgets (Ronda's now
playing, the TV, the board), with the same bearer token as /mcp and only the groups it holds.

GET  /api/v1/agent/now?parts=music,tv,board,home   one snapshot (JSON)
GET  /api/v1/agent/stream?parts=…                   the same snapshot again whenever it changes
                                                     (Server-Sent Events, `event: now`)
POST /api/v1/agent/act {"tool": …, "arguments": {…}} one of its tools, the answer as plain JSON

Positions come with `at` (the house's clock when read): a playing song's position now is
position + (now - at). Pictures are public addresses (YouTube stills, catalogue posters), so an
<img> shows them without the token. Browsers may call it from another site (CORS); EventSource
can't send headers, so the token may also come as ?access_token= (prefer a server-side fetch)."""

import asyncio
import json
import time
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import agent_mcp
from .db import get_db, utcnow
from .models import Event

router = APIRouter(prefix="/agent", tags=["agents"])
PARTS = {"music": "music", "tv": "tv", "board": "board", "home": "home"}  # part: the group it needs
# Which events change which part (the stream rebuilds only those).
TOPICS = {"music.": "music", "cinema.": "tv", "household.": "board", "records.": "board", "home.": "home"}
REFRESH = 15  # seconds: a playing song's clock is sent again at least this often
ROUNDS = 300  # of 2 s: a stream lasts about 10 minutes, then EventSource reconnects


def agent(db, request):
    """(token record, Actor) from the Authorization header or ?access_token=, else 401."""
    header = request.headers.get("authorization") or (
        "Bearer " + request.query_params["access_token"] if request.query_params.get("access_token") else ""
    )
    found = agent_mcp.actor_for(db, header)
    if not found:
        raise HTTPException(401, "A valid agent token is required (Control Room → Agents)")
    return found


def wanted(row, parts):
    groups = set(row.data.get("groups", []))
    asked = [p.strip() for p in (parts or ",".join(PARTS)).split(",") if p.strip()]
    unknown = [p for p in asked if p not in PARTS]
    if unknown:
        raise HTTPException(422, {"code": "UNKNOWN_PART", "message": "Parts: " + ", ".join(PARTS)})
    return [p for p in asked if PARTS[p] in groups]


def utc(value):
    """A time as ISO 8601 UTC with its Z (the house keeps naive UTC)."""
    if not value:
        return None
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return text if text.endswith("Z") or "+" in text[10:] else text + "Z"


def picture(url):
    return url if isinstance(url, str) and url.startswith("https://") else None


def music_now(actor, db):
    from .music import state
    from .music_genre import youtube_thumbnail

    snap = state(actor, db)
    seen = snap.get("observation") or {}
    items = snap.get("items") or []
    current = next((i for i in items if i["id"] == snap.get("current_id")), None)

    def song(item):
        return {
            "id": item["id"],
            "title": item.get("now_title") or item["title"],
            "artist": item.get("uploader"),
            "art": picture(youtube_thumbnail(item.get("source_url") or "")),
            "duration": item.get("duration"),
            "live": item.get("is_live") or None,
            "requested_by": (item.get("requester") or {}).get("name"),
            "url": item.get("source_url"),
        }

    playing = bool(current) and snap.get("desired") == "playing" and not seen.get("paused")
    return {
        "state": "playing" if playing else "paused" if current else "stopped",
        "song": {
            **song(current),
            "position": round(seen["position"], 1)
            if seen.get("item_id") == current["id"] and seen.get("position") is not None
            else None,
        }
        if current
        else None,
        "volume": snap.get("volume"),
        "sleep_at": utc(snap.get("sleep_at")),
        "repeat": snap.get("repeat_mode"),
        "plays_on": snap.get("plays_on"),
        "next": [song(i) for i in items if i["id"] != snap.get("current_id")][:5],
        "waiting": max(0, len(items) - (1 if current else 0)),
        "version": snap.get("version"),
    }


def tv_now(actor, db):
    """Every film screen and what it shows, whoever started it (a house-wide view)."""
    from .cinema_models import CinemaDevice, CinemaTitle, CinemaWorkflow

    screens = []
    for device in db.scalars(select(CinemaDevice).order_by(CinemaDevice.name)):
        row = db.get(CinemaWorkflow, device.owner_workflow) if device.owner_workflow else None
        live = row is not None and row.state in {"playing_observed", "paused", "command_sent", "preparing"}
        shown = {"device_id": device.id, "name": device.name, "state": "idle"}
        if live:
            title = db.get(CinemaTitle, row.media_id)
            parent = (
                db.get(CinemaTitle, title.data.get("parent_id"))
                if title and title.data.get("parent_id")
                else None
            )
            plan = row.data.get("plan") or {}
            checkpoint = row.data.get("checkpoint") or {}
            state = {"playing_observed": "playing", "command_sent": "starting", "preparing": "starting"}.get(
                row.state, row.state
            )
            if (
                row.state == "command_sent"
                and (row.data.get("observation") or {}).get("shown_state") == "paused"
            ):
                state = "paused"
            shown.update(
                state=state,
                title=(parent or title).title if title else None,
                episode={
                    "season": row.data.get("season"),
                    "episode": row.data.get("episode"),
                    "title": title.title,
                }
                if parent and title
                else None,
                poster=picture(((parent or title).data or {}).get("_poster_url")) if title else None,
                position=checkpoint.get("position"),
                at=utc(checkpoint.get("at")),
                duration=plan.get("duration"),
                audio=(plan.get("audio") or {}).get("language"),
                subtitles=(plan.get("subtitle") or {}).get("language"),
                sleep_at=utc((row.data.get("sleep_timer") or {}).get("at")),
                workflow_id=row.id,
                version=row.version,
            )
        screens.append(shown)
    return {"screens": screens}


def board_now(row, actor, db):
    """Today at home, from the board's own tools (so their permission checks run)."""
    from .household import house_today

    tools = agent_mcp.allowed_tools(row)
    today = house_today(db)
    out = {"date": today.isoformat()}
    for key, tool, args in (
        ("groceries", "household_list", {"kind": "groceries"}),
        ("tasks", "household_list", {"kind": "tasks"}),
        (
            "today",
            "calendar_agenda",
            {"start": today.isoformat(), "end": (today + timedelta(days=1)).isoformat()},
        ),
    ):
        if tool in tools:
            result, failed = agent_mcp.call_tool(tool, args, tools, actor, db)
            items = None if failed else result.get("items", result)
            # Flat for a widget: {id, label, purchased…} rather than {id, summary: {…}}.
            out[key] = (
                [
                    {**{k: v for k, v in i.items() if k != "summary"}, **(i.get("summary") or {})}
                    for i in items
                ]
                if isinstance(items, list)
                else items
            )
    return out


def home_now(row, actor, db):
    tools = agent_mcp.allowed_tools(row)
    result, failed = (
        agent_mcp.call_tool("home_list", {}, tools, actor, db) if "home_list" in tools else ({}, True)
    )
    return None if failed else {"devices": result.get("items", result)}


def snapshot(row, actor, db, parts):
    built = {"at": utcnow().isoformat() + "Z"}
    for part in parts:
        try:
            if part == "music":
                built["music"] = music_now(actor, db)
            elif part == "tv":
                built["tv"] = tv_now(actor, db)
            elif part == "board":
                built["board"] = board_now(row, actor, db)
            elif part == "home":
                built["home"] = home_now(row, actor, db)
        except HTTPException as exc:
            built[part] = {"error": exc.detail if isinstance(exc.detail, str) else exc.detail.get("message")}
        db.rollback()  # no transaction kept between parts or polls
    return built


def used(db, row):
    """Last use, written at most once a minute (a widget polls)."""
    last = row.data.get("last_used_at") or ""
    if last < (utcnow() - timedelta(minutes=1)).isoformat():
        from .models import Record

        fresh = db.get(Record, row.id, populate_existing=True)
        fresh.data = {**fresh.data, "last_used_at": utcnow().isoformat()}
        db.commit()


@router.get("/now")
def now(request: Request, parts: str = Query(default="", max_length=60), db=Depends(get_db)):
    row, actor = agent(db, request)
    used(db, row)
    return snapshot(row, actor, db, wanted(row, parts))


@router.get("/stream")
def stream(request: Request, parts: str = Query(default="", max_length=60), db=Depends(get_db)):
    """The snapshot now, then again each time it changes; a comment every few seconds keeps the
    line open. The server ends it after about 10 minutes: EventSource reconnects by itself."""
    row, actor = agent(db, request)
    chosen = wanted(row, parts)
    used(db, row)
    token_id, bind = row.id, db.get_bind()
    db.close()

    def build(cursor, last, last_sent):
        with Session(bind) as session:
            record = session.get(type(row), token_id)
            if not record or record.deleted_at:
                return None, cursor, None, last_sent
            newest = session.scalar(select(func.coalesce(func.max(Event.id), 0)))
            touched = set()
            if cursor is not None and newest > cursor:
                for (topic,) in session.execute(select(Event.topic).where(Event.id > cursor).limit(500)):
                    touched |= {part for prefix, part in TOPICS.items() if topic.startswith(prefix)}
            due = cursor is None or touched & set(chosen) or time.monotonic() - last_sent >= REFRESH
            if not due:
                return record, newest, None, last_sent
            built = snapshot(record, actor, session, chosen)
            body = json.dumps({k: v for k, v in built.items() if k != "at"}, default=str, sort_keys=True)
            if body == last:
                return record, newest, None, last_sent
            return record, newest, (json.dumps(built, default=str), body), time.monotonic()

    async def events():
        from starlette.concurrency import run_in_threadpool

        cursor, last, last_sent = None, None, 0.0
        for _ in range(ROUNDS):
            if await request.is_disconnected():
                return  # the widget left: nothing more to read for it
            record, cursor, sent, last_sent = await run_in_threadpool(build, cursor, last, last_sent)
            if record is None:
                yield "event: revoked\ndata: {}\n\n"
                return
            if sent:
                text, last = sent
                yield f"event: now\ndata: {text}\n\n"
            else:
                yield ": still here\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/act")
def act(request: Request, body: dict = Body(...), db=Depends(get_db)):
    """A widget's button: one of the agent's tools by name, the answer as JSON (ok, result)."""
    row, actor = agent(db, request)
    name, arguments = body.get("tool"), body.get("arguments") or {}
    tools = agent_mcp.allowed_tools(row)
    if name not in tools or not isinstance(arguments, dict):
        raise HTTPException(403, {"code": "NOT_ALLOWED", "message": f"This agent may not use {name}."})
    started = time.monotonic()
    result, failed = agent_mcp.call_tool(name, arguments, tools, actor, db)
    agent_mcp.note(db, row, name, arguments, started, failed, result)
    return JSONResponse({"ok": not failed, "result": result}, status_code=200)
