"""One call plays a film or an episode, for assistants (Nox, MCP clients such as Ronda).

It does what the Watch page does, in order: find the title (a name, an IMDb id or the house's
id), check the most promising versions, pick one by what was asked (original audio, subtitles in
a language from the file or found online, a resolution, the smallest file), launch it on the
screen, and say in one line what plays. It waits up to WAIT seconds; asked again with the same
words, it carries on with the same versions instead of starting over."""

import re
import time
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from . import cinema, cinema_jobs
from .auth import Input
from .cinema_models import CinemaDevice, CinemaPreference, CinemaTitle, CinemaWorkflow, Discover, Preferences
from .cinema_suggest import language
from .db import new_id, utcnow
from .models import Operation

WAIT = 45  # seconds a call may take: under the MCP client's 60 s and Nox's round
REUSE = timedelta(minutes=20)  # a later call with the same words carries on these versions
WAITING = {"discovered", "preparing"}
# A version not checked yet says its subtitles only in its name ("VOSTFR", "MULTi SUBS").
SUBS_IN_NAME = {
    "fr": re.compile(r"vostfr|subfrench|french[ ._-]?subs?|st[ ._-]?fr\b|multi[ ._-]?subs?", re.I),
    "en": re.compile(r"eng[ ._-]?subs?|english[ ._-]?subs?|multi[ ._-]?subs?", re.I),
}


class Play(Input):
    title: str = Field(
        min_length=1,
        max_length=200,
        description="Name, IMDb id (tt…) or title id.",
    )
    year: int | None = Field(default=None, ge=1880, le=2100, description="For remakes.")
    kind: Literal["movie", "series", "anime"] | None = Field(default=None, description="Only if ambiguous.")
    season: int | None = Field(default=None, ge=0, le=100, description="For an episode.")
    episode: int | None = Field(default=None, ge=1, le=1000, description="For an episode.")
    audio: str = Field(
        default="original",
        max_length=8,
        description='"original" or a dub\'s code.',
    )
    subtitles: str | None = Field(
        default=None,
        max_length=8,
        description='"fr", "en"…, "off"; omit: usual.',
    )
    subtitles_inside: bool = Field(
        default=False,
        description="Prefer them in the file; else found online.",
    )
    resolution: Literal[2160, 1080, 720] | None = Field(default=None, description="2160 = 4K.")
    smallest: bool = Field(default=False, description="Smallest fitting file.")
    device_id: str | None = Field(
        default=None,
        max_length=36,
        description="Omit: usual screen.",
    )
    position: float | None = Field(
        default=None,
        ge=0,
        le=86400,
        description="Seconds; 0 = start; omit: resume.",
    )
    replace: bool = Field(default=False, description="Once they agreed to replace what plays.")
    skip_intros: bool | None = Field(default=None, description="Episodes: skip openings.")
    autoplay: bool | None = Field(default=None, description="Play the next episodes.")


def answer(status, message, **facts):
    return {"status": status, "message": message, **{k: v for k, v in facts.items() if v is not None}}


def find_title(db, actor, body):
    """The house's title row, or an answer asking which one."""
    text = body.title.strip()
    title = db.get(CinemaTitle, text)
    if not title and re.fullmatch(r"tt\d+", text):
        title = db.scalar(select(CinemaTitle).where(CinemaTitle.canonical_id == text))
        if not title:
            kind = "series" if body.season is not None else "movie"
            item = cinema.call(cinema.Cinemeta().details, text, kind)
            title = cinema.upsert_title(
                db, item["canonical_id"], item["title"], item["kind"], {**item, "layers": ["ON_DEMAND"]}
            )
    if title:
        return title, None
    kinds = (
        [body.kind] if body.kind else (["movie", "series"] if body.season is None else ["series", "anime"])
    )
    found = []
    for kind in kinds:
        found += cinema.search(text, kind, actor, db)["items"]
    if body.year:
        found = [i for i in found if str(i.get("year") or "")[:4] == str(body.year)] or found
    exact = [i for i in found if i["title"].casefold() == text.casefold()]
    pick = (exact or found or [None])[0]
    if not pick:
        return None, answer(
            "not_found", f"No title called “{text}” was found. Check the name or give its IMDb id."
        )
    others = [f"{i['title']} ({i.get('year') or i['kind']})" for i in (exact or found)[1:4]]
    if len(exact) > 1 and not body.year:
        return None, answer(
            "needs_answer",
            f"Several titles are called “{pick['title']}”: {', '.join([pick['title'] + ' (' + str(pick.get('year') or pick['kind']) + ')', *others])}. Call again with the year.",
        )
    return db.get(CinemaTitle, pick["id"]), None


def screen(db, actor, body):
    if body.device_id:
        return db.get(CinemaDevice, body.device_id)
    saved = db.get(CinemaPreference, actor.id)
    preferred = (saved.data if saved else {}).get("preferred_device")
    devices = db.scalars(select(CinemaDevice)).all()
    return next((d for d in devices if d.id == preferred), None) or next(
        (d for d in devices if d.adapter == "cast"), devices[0] if devices else None
    )


def wait_for(db, workflow_id, deadline, ready):
    """Read the workflow again until ready(row) or the deadline; no transaction held meanwhile."""
    while True:
        db.commit()
        row = db.get(CinemaWorkflow, workflow_id, populate_existing=True)
        if not row or ready(row) or time.monotonic() >= deadline:
            return row
        time.sleep(1.5)


def inside(candidate, wanted):
    return next(
        (
            s
            for s in candidate.get("subtitles") or []
            if not s.get("external") and not s.get("forced") and language(s.get("language")) == wanted
        ),
        None,
    )


def fits(candidate, body):
    return (
        not body.resolution
        or (candidate.get("resolution") or candidate.get("height") or 0) == body.resolution
    )


def choose(row, body, wanted):
    """The checked version that best fits what was asked, or None."""
    checked = [c for c in (row.data.get("choice_set") or {}).get("candidates") or [] if fits(c, body)]
    if body.audio != "original":  # a dub asked for: only versions that have it
        dub = language(body.audio)
        checked = [
            c for c in checked if any(language(a.get("language")) == dub for a in c.get("audio") or [])
        ]
    if body.smallest:
        checked.sort(key=lambda c: c.get("size") or 0)
    if wanted and body.subtitles_inside:
        checked.sort(key=lambda c: inside(c, wanted) is None)  # stable: keeps size or rank order
    return checked[0] if checked else None


def worth_checking(row, body, wanted, chosen):
    """Cached versions not checked yet that could fit better (up to three)."""
    if row.data.get("_play_checked_more"):
        return []
    needs = not chosen or body.smallest or (wanted and body.subtitles_inside and not inside(chosen, wanted))
    if not needs:
        return []
    pool = [
        s
        for s in row.data.get("_sources", [])
        if s.get("rd_cached")
        and not s.get("inspection")
        and not s.get("error")
        and s.get("info_hash")
        and (not body.resolution or s.get("height_claim") == body.resolution)
    ]
    if wanted and body.subtitles_inside and wanted in SUBS_IN_NAME:
        pool.sort(key=lambda s: not SUBS_IN_NAME[wanted].search(str(s.get("release") or "")))
    if body.smallest:
        pool.sort(key=lambda s: s.get("size") or 0)
    better = [
        s for s in pool if not chosen or not body.smallest or (s.get("size") or 0) < (chosen.get("size") or 0)
    ]
    return [s["id"] for s in better[:3]]


def check_more(db, row, ids, actor):
    row.state, row.version, row.updated_at = "preparing", row.version + 1, utcnow()
    row.data = {
        **row.data,
        "_validation_selection": ids,
        "_suggestion": True,
        "_play_checked_more": True,
        "error": None,
    }
    cinema_jobs.enqueue_validation(db, row, ids, actor.session_hash)
    db.commit()


def tracks(candidate, body, wanted):
    """(audio id, subtitle id or "auto"/"off", language to find online or None)."""
    audio = (candidate.get("suggested_audio") or {}).get("id")
    if body.audio != "original":
        dub = next(
            (a for a in candidate.get("audio") or [] if language(a.get("language")) == language(body.audio)),
            None,
        )
        audio = dub["id"] if dub else audio
    if body.subtitles == "off":
        return audio, "off", None
    if wanted:
        track = inside(candidate, wanted)
        return audio, track["id"] if track else "auto", None if track else wanted
    suggested = candidate.get("suggested_subtitle")
    return audio, suggested["id"] if suggested else "auto", None


def describe(title, row, candidate, device, subtitle, online):
    size = f"{(candidate.get('size') or 0) / 1e9:.1f} GB" if candidate.get("size") else ""
    res = {2160: "4K", 1080: "1080p", 720: "720p"}.get(
        candidate.get("resolution") or candidate.get("height"), ""
    )
    plan = row.data.get("plan") or {}
    spoken = (plan.get("audio") or {}).get("language") or "?"
    sub = plan.get("subtitle")
    words = (
        "no subtitles"
        if not sub
        else f"{sub.get('language')} subtitles "
        + ("found online" if sub.get("external") or online else "from the file")
    )
    name = title.title + (
        f" S{row.data.get('season'):02}E{row.data.get('episode'):02}" if row.data.get("episode") else ""
    )
    return f"{name} on {device.name}: {', '.join(filter(None, [res, size]))}, {spoken} audio, {words}."


def play(body: Play, actor, db):
    deadline = time.monotonic() + WAIT
    cinema.allowed(actor)
    title, question = find_title(db, actor, body)
    if question:
        return question
    device = screen(db, actor, body)
    if not device:
        return answer("failed", "No screen is set up for films (Control Room → Devices).")
    episode = body.episode if title.kind != "movie" else None
    if title.kind != "movie" and episode is None:
        return answer(
            "needs_answer", f"{title.title} is a series: which season and episode?", title_id=title.id
        )
    wanted = language(body.subtitles) if body.subtitles and body.subtitles != "off" else None
    key = [
        title.id,
        body.season,
        episode,
        body.audio,
        body.subtitles,
        body.subtitles_inside,
        body.resolution,
        body.smallest,
        device.id,
    ]
    # The same words a moment ago: carry on with the versions already checked.
    rows = db.scalars(
        select(CinemaWorkflow)
        .where(CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.updated_at >= utcnow() - REUSE)
        .order_by(CinemaWorkflow.updated_at.desc())
        .limit(20)
    ).all()
    row = next(
        (r for r in rows if r.data.get("_play_key") == key and r.state in WAITING | {"awaiting_choice"}), None
    )
    if not row:
        preferences = Preferences(
            **({"subtitle_language": wanted, "always_subtitles": True} if wanted else {}),
            **({"subtitles_on": False} if body.subtitles == "off" else {}),
            **({"autoplay": body.autoplay} if body.autoplay is not None else {}),
        )
        started = cinema_jobs.enqueue_discovery(
            Discover(
                media_id=title.id,
                season=body.season if episode else None,
                episode=episode,
                position=body.position,
                device_id=device.id,
                preferences=preferences,
                idempotency_key="play:" + new_id(),
                suggest=True,
            ),
            actor,
            db,
        )
        operation = started["operation_id"]
        while time.monotonic() < deadline:
            db.commit()
            op = db.get(Operation, operation, populate_existing=True)
            workflow_id = (op.result or {}).get("workflow_id")
            if workflow_id or op.state in {"failed", "unverified"}:
                break
            time.sleep(1)
        if not workflow_id:
            error = (op.result or {}).get("error") or {}
            if error:
                return answer(
                    "failed",
                    error.get("message") or "The search for versions failed.",
                    code=error.get("code"),
                )
            return answer(
                "working", "Still looking for versions: call again with the same words in a few seconds."
            )
        row = db.get(CinemaWorkflow, workflow_id)
        row.data = {**row.data, "_play_key": key}
        db.commit()
    # Discovered with nothing to check: no version anywhere (yet). Said at once, and the next call
    # searches again (a source service may need a first request to find any).
    row = wait_for(db, row.id, deadline, lambda r: r.state not in WAITING or not r.data.get("_sources"))
    if row.state == "discovered" and not row.data.get("_sources"):
        row.data = {**row.data, "_play_key": None}
        db.commit()
        return answer(
            "not_found",
            f"No version of {title.title} was found right now. The sources can need a minute the first "
            "time: asking again shortly may find some.",
        )
    chosen = choose(row, body, wanted)
    more = worth_checking(row, body, wanted, chosen) if row.state == "awaiting_choice" else []
    if more:
        check_more(db, row, more, actor)
        row = wait_for(db, row.id, deadline, lambda r: r.state not in WAITING)
        chosen = choose(row, body, wanted)
    if row.state in WAITING:
        return answer(
            "working",
            "Still checking versions: call again with the same words in a few seconds.",
            workflow_id=row.id,
        )
    if not chosen:
        error = row.data.get("error") or {}
        res = (
            f" in {'4K' if body.resolution == 2160 else str(body.resolution) + 'p'}"
            if body.resolution
            else ""
        )
        return answer(
            "not_found",
            error.get("message") or f"No playable version{res} was found for {title.title}.",
            workflow_id=row.id,
        )
    audio, subtitle, online = tracks(chosen, body, wanted)
    try:
        result = cinema.launch(
            row.id,
            cinema.Launch(
                version=row.version,
                source_id=chosen["id"],
                device_id=device.id,
                audio_track=audio,
                subtitle_track=subtitle,
                position=body.position,
                replace=body.replace,
                skip_intros=body.skip_intros,
                subtitle_language=wanted,
            ),
            actor,
            db,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return answer(
            "failed", detail.get("message", "Launching failed."), code=detail.get("code"), workflow_id=row.id
        )
    if result.get("state") == "awaiting_playback_confirmation":
        return answer(
            "needs_answer",
            f"Something else plays on {device.name}. Ask the person; if they agree, call again with replace=true.",
            workflow_id=row.id,
        )
    row = wait_for(
        db, row.id, deadline, lambda r: r.state in {"playing_observed", "recovery_required", "failed"}
    )
    line = describe(title, row, chosen, device, subtitle, online)
    if row.state == "playing_observed":
        return answer("playing", "Playing " + line, workflow_id=row.id, version=row.version)
    error = row.data.get("error") or {}
    if row.state in {"recovery_required", "failed"}:
        return answer(
            "failed",
            error.get("message") or "The screen did not start it.",
            code=error.get("code"),
            workflow_id=row.id,
        )
    return answer(
        "starting",
        "Sending " + line + " It may take a few more seconds to show.",
        workflow_id=row.id,
        version=row.version,
    )


class Versions(Input):
    workflow_id: str = Field(max_length=36, description="From cinema_play or cinema_discover.")
    resolution: Literal[2160, 1080, 720] | None = Field(default=None, description="Only this resolution.")
    subtitles_inside: str | None = Field(
        default=None,
        max_length=8,
        description="Only versions with these subtitles in the file (a language code).",
    )
    order: Literal["best", "smallest", "largest"] = "best"
    check: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Version ids to check now (unchecked ones); then call again.",
    )
    offset: int = Field(default=0, ge=0, le=500)


def versions(body: Versions, actor, db):
    """Every version of a film or episode, checked or not, filtered and sorted, ten at a time."""
    row = cinema.own_workflow(db, actor, body.workflow_id)
    if body.check:
        unchecked = {
            s["id"] for s in row.data.get("_sources", []) if not s.get("inspection") and s.get("info_hash")
        }
        ids = [i for i in body.check if i in unchecked]
        if not ids:
            return answer("failed", "Those versions are checked already or unknown: read the list again.")
        if row.state in WAITING:
            return answer("working", "Versions are being checked: call again in a few seconds.")
        check_more(db, row, ids, actor)
        return answer("working", f"Checking {len(ids)} version(s): call again in a few seconds.")
    wanted = language(body.subtitles_inside) if body.subtitles_inside else None
    checked = {c["id"]: c for c in (row.data.get("choice_set") or {}).get("candidates") or []}
    items = []
    for rank, source in enumerate(row.data.get("_sources", [])):
        c = checked.get(source["id"])
        height = (c.get("resolution") or c.get("height")) if c else source.get("height_claim")
        if body.resolution and height != body.resolution:
            continue
        if c:
            subs = sorted(
                {
                    language(s.get("language"))
                    for s in c.get("subtitles") or []
                    if not s.get("external") and not s.get("forced")
                }
                - {None}
            )
        else:
            subs = [
                code for code, words in SUBS_IN_NAME.items() if words.search(str(source.get("release") or ""))
            ]
        if wanted and wanted not in subs:
            continue
        items.append(
            {
                "id": source["id"],
                "checked": bool(c),
                "rank": c["rank"] if c else None,
                "resolution": height,
                "size_gb": round((source.get("size") or 0) / 1e9, 1) or None,
                "cached": bool(source.get("rd_cached")),
                "subtitles_inside": subs,
                "audio": sorted({language(a.get("language")) for a in (c or {}).get("audio") or []} - {None})
                or None,
                "release": str(source.get("release") or "").split("\n")[0][:90],
                "_order": (c["rank"] if c else 100 + rank),
            }
        )
    if body.order == "best":
        items.sort(key=lambda i: i["_order"])
    else:
        items.sort(key=lambda i: i["size_gb"] or 0, reverse=body.order == "largest")
    page = [
        {k: v for k, v in i.items() if k != "_order" and v is not None}
        for i in items[body.offset : body.offset + 10]
    ]
    return {
        "status": "completed",
        "state": row.state,
        "version": row.version,
        "total": len(items),
        "items": page,
        "next_offset": body.offset + 10 if len(items) > body.offset + 10 else None,
        "note": "Unchecked versions show their subtitles only from their name; check them to play them.",
    }
