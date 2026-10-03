"""The house's activity, in sentences: what played, what Nox did, what broke and when.

Built from the events the house already records, so nothing new is stored per action. Each
line is a sentence template and its values (the page translates the template), a category
for its colour, and a level (info, good, problem). Private content never appears: songs and
films by title, messages and files only as "changed"."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from .auth import require_admin
from .db import SessionLocal, get_db
from .events import emit
from .models import Event, User

router = APIRouter(tags=["activity"])
FILM_STATES = {
    "preparing": ("info", "{title}: checking versions"),
    "awaiting_choice": ("good", "{title}: ready to play"),
    "recovery_required": ("problem", "{title}: no version plays on this screen"),
    "command_sent": ("info", "{title}: sent to the TV"),
    "playing_observed": ("good", "{title}: playing on the TV"),
    "paused": ("info", "{title}: paused"),
    "stopped": ("info", "{title}: stopped"),
    "completed": ("good", "{title}: finished"),
}
GAME_LINES = {
    "downloading": ("info", "Downloading {title}"),
    "ready": ("good", "{title} is ready to play"),
    "failed": ("problem", "Couldn't download {title}"),
    "added": ("good", "Added {title}"),
    "removed": ("info", "Removed {title}"),
    "hidden": ("info", "Hid {title}"),
    "scanned": ("info", "Read the games folder {title}: {count} games"),
}
HOUSE_KINDS = {"groceries": "Groceries", "task": "Tasks", "event": "Calendar", "note": "Notes"}


def note(text, level="info", **values):
    """A system line from a background process (maintenance, index builds), in its own session."""
    with SessionLocal() as db:
        emit(db, "system.note", {"text": text, "level": level, **values})
        db.commit()


def describe(event, found):
    """What one event says, or None for plumbing noise: its category, level (info, good or
    problem), the sentence and its values, who acted when it wasn't a person (auto play, the
    house), what it was trying to do, and keys tying a problem to the later success that fixed it
    (`fixes`) or marking this event as such a success (`fixed_by`)."""
    topic, p = event.topic, event.payload or {}
    status = p.get("status")
    song = found.get(p.get("item_id")) or {}

    def line(category, level, template, values=None, **more):
        return {"category": category, "level": level, "template": template, "values": values or {}, **more}

    if topic in {"music.playback", "music.metadata"}:
        title = song.get("title") or "a song"
        by = "Auto play" if song.get("auto") else None
        values = {"title": title, **({"code": p["code"]} if p.get("code") else {})}
        if topic == "music.playback" and status == "playing":
            return line(
                "music",
                "info",
                "Playing {title}",
                values,
                actor=by,
                owner=song.get("owner"),
                fixed_by=["music"],
            )
        if status != "failed":
            return None
        return line(
            "music",
            "problem",
            "Couldn't play {title}" if topic == "music.playback" else "Couldn't get {title} ready",
            values,
            actor=by,
            owner=song.get("owner"),
            tried="Playing the next song" if topic == "music.playback" else "Getting a song ready to play",
            fixes="music",
            handled=bool(by),  # auto play simply picks another song
        )
    if topic == "music.paused_itself":
        return line(
            "music",
            "problem",
            "The house paused the music by itself",
            {"code": p.get("code") or "?"},
            actor="House",
            tried="Keeping the music playing",
            fixes="music",
        )
    if topic == "audit.music_add":
        count = p.get("count") or 1
        if count > 1:
            return line("music", "info", "Added {count} songs to the queue", {"count": count})
        return line("music", "info", "Added {title} to the queue", {"title": song.get("title") or "a song"})
    if topic == "music.duplicate_kept":
        return line(
            "music", "info", "Possible duplicate kept: {title}", {"title": p.get("title") or "a song"}
        )
    if topic == "cinema.workflow" and p.get("state") in FILM_STATES:
        level, template = FILM_STATES[p["state"]]
        film = "film:" + str(p.get("workflow_id"))
        return line(
            "films",
            level,
            template,
            {"title": (found.get(p.get("workflow_id")) or {}).get("title") or "A film"},
            fixes=film if level == "problem" else None,
            fixed_by=[film] if p["state"] == "playing_observed" else [],
            tried="Playing a film on the TV" if level == "problem" else None,
        )
    if topic == "games.activity" and status in GAME_LINES:
        level, template = GAME_LINES[status]
        values = {k: v for k, v in p.items() if k != "status"}
        return line(
            "games",
            level,
            template,
            values,
            tried="Downloading a game from a link" if level == "problem" else None,
        )
    if topic == "cinema.tv_control":
        return line("films", "info", "TV: {action}", {"action": p.get("action") or "command"})
    if topic == "audit.ai_request":
        model = p.get("model") or p.get("provider") or "AI"
        keys = ["ai:" + model, "ai:" + str(p.get("provider"))]
        if status not in {"completed", None}:
            code = p.get("detail_code") or p.get("code")
            return line(
                "nox",
                "problem",
                "Nox's AI failed ({model})",
                {"model": model, **({"code": code} if code else {})},
                actor="Nox",
                tried="Answering a question",
                fixes=keys[0],
            )
        values = {"model": model, "seconds": round((p.get("latency_ms") or 0) / 1000, 1)}
        values["tools"] = p.get("tool_calls") or 0
        return line(
            "nox",
            "info",
            "Nox answered with {model} in {seconds} s · {tools} tool calls",
            values,
            fixed_by=keys,
        )
    if topic == "audit.tool_call":
        tool = p.get("tool_name") or "a tool"
        values = {"tool": tool, "status": status or "done"}
        if status in {"failed", "rejected", "error"}:
            return line(
                "nox",
                "problem",
                "Nox used {tool} · {status}",
                values,
                tried="Using a tool",
                fixes="tool:" + tool,
            )
        return line("nox", "info", "Nox used {tool} · {status}", values, fixed_by=["tool:" + tool])
    if topic == "audit.provider_failure":
        return line(
            "nox",
            "problem",
            "The AI provider failed",
            {"code": p.get("detail_code") or p.get("code") or "?"},
            actor="Nox",
            tried="Answering a question",
            fixes="ai:" + str(p.get("provider")),
        )
    if topic == "household.changed":
        kind = HOUSE_KINDS.get(p.get("kind"), "House board")
        return line("house", "info", "{what} updated", {"what": kind})
    if topic == "inbox.changed":
        return line("house", "info", "A message was sent")
    if topic == "files.changed":
        return line("house", "info", "Files changed")
    if topic == "invite.created":
        return line("house", "good", "An invite was created")
    if topic == "audit.application_error":
        return line(
            "system",
            "problem",
            "Something went wrong (ref. {ref})",
            {"ref": str(p.get("correlation_id"))[:8], **({"where": p["where"]} if p.get("where") else {})},
            tried=p.get("request") or None,
        )
    if topic == "audit.integration_test":
        name = p.get("name") or "?"
        good = status in {"reachable", "ok", "verified"}
        return line(
            "system",
            "good" if good else "problem",
            "{name} checked: {status}",
            {"name": name, "status": status},
            fixes=None if good else "integration:" + name,
            fixed_by=["integration:" + name] if good else [],
            tried=None if good else "Reaching a connected service",
        )
    if topic == "audit.service_restart_requested":
        return line("system", "info", "Restart asked for {service}", {"service": p.get("service") or "?"})
    if topic == "system.note":
        values = {k: v for k, v in p.items() if k not in {"text", "level"}}
        level = p.get("level") or "info"
        chore = "chore:" + str(p["step"]) if p.get("step") else None
        return line(
            "system",
            level,
            p.get("text") or "…",
            values,
            fixes=chore if level == "problem" else None,
            fixed_by=[chore] if chore and level == "good" else [],
            tried="A background chore" if chore and level == "problem" else None,
        )
    if topic.startswith("audit."):
        return line("system", "info", "{what}", {"what": topic.removeprefix("audit.").replace("_", " ")})
    return None


def titles_for(db, events):
    """Songs (title, who queued it, auto play's or not) and film names for the events on this
    page, in two queries."""
    from .cinema_models import CinemaTitle, CinemaWorkflow
    from .music import QueueItem

    songs = {e.payload.get("item_id") for e in events if e.topic.startswith(("music.", "audit.music"))} - {
        None
    }
    flows = {e.payload.get("workflow_id") for e in events if e.topic == "cinema.workflow"} - {None}
    found = {}
    if songs:
        for item in db.scalars(select(QueueItem).where(QueueItem.id.in_(songs))):
            found[item.id] = {
                "title": item.title,
                "owner": item.owner_id,
                "auto": bool((item.metadata_json or {}).get("auto")),
            }
    if flows:
        rows = db.execute(
            select(CinemaWorkflow.id, CinemaTitle.title)
            .join(CinemaTitle, CinemaTitle.id == CinemaWorkflow.media_id)
            .where(CinemaWorkflow.id.in_(flows))
        ).all()
        found |= {flow: {"title": title} for flow, title in rows}
    return found


GROUPED = 600  # the same line within 10 minutes of the last is one row, "×3"
QUIET = {"ref", "seconds"}  # values that differ between repeats of the same thing


@router.get("/admin/activity")
def activity(
    category: str = Query("", pattern="^(|music|films|games|nox|house|system)$"),
    problems: bool = False,
    needs: bool = False,
    search: str = Query("", max_length=80),
    before: int | None = Query(None, ge=1),
    actor=Depends(require_admin),
    db=Depends(get_db),
):
    """Newest first, 60 rows a page; `next` continues further back. Each row says who acted,
    what was being tried, whether it needs an admin (`care`: needs, handled or info) and when a
    later success fixed it; repeats of the same line are grouped (`count`, `times`)."""
    names = dict(db.execute(select(User.id, User.name)).all())
    lines, cursor, last = [], before, {}
    # ponytail: fixes are only found among newer events on this page's scan (6 × 500 events).
    fixed_at: dict[str, str] = {}
    for _ in range(6):  # at most 6 × 500 events scanned per page
        q = select(Event).order_by(Event.id.desc()).limit(500)
        if cursor:
            q = q.where(Event.id < cursor)
        events = db.scalars(q).all()
        if not events:
            cursor = None
            break
        found = titles_for(db, events)
        for event in events:
            cursor = event.id
            said = describe(event, found)
            if not said:
                continue
            at = event.created_at.isoformat() + "Z"
            for key in said.get("fixed_by") or []:
                fixed_at[key] = at  # scanning back: ends at the first success after a problem
            # A film passes through the same state several times: say it once.
            key = (event.payload.get("workflow_id"), event.payload.get("state"))
            if event.topic == "cinema.workflow" and last.get("film") == key:
                continue
            if event.topic == "cinema.workflow":
                last["film"] = key
            kind, level, template, values = said["category"], said["level"], said["template"], said["values"]
            who = names.get(event.user_id) or names.get(said.get("owner")) if not said.get("actor") else None
            resolved = fixed_at.get(said.get("fixes") or "")
            care = (
                "needs"
                if level == "problem" and not resolved and not said.get("handled")
                else ("handled" if level == "problem" else "info")
            )
            try:
                text = template.format(**{k: str(v) for k, v in values.items()})
            except (KeyError, IndexError, ValueError):
                text = template
            if (
                (category and kind != category)
                or (problems and level != "problem")
                or (needs and care != "needs")
            ):
                continue
            if search and search.casefold() not in f"{who or ''} {said.get('actor') or ''} {text}".casefold():
                continue
            same = (template, {k: v for k, v in values.items() if k not in QUIET}, who, said.get("actor"))
            previous = lines[-1] if lines else None
            if (
                previous
                and previous["_same"] == same
                and previous["_oldest"] - event.created_at.timestamp() < GROUPED
            ):
                previous["count"] += 1
                previous["_oldest"] = event.created_at.timestamp()
                if len(previous["times"]) < 20:
                    previous["times"].append(at)
                if care == "needs":  # the group needs you while any of it does
                    previous["care"], previous["resolved_at"] = "needs", None
                continue
            lines.append(
                {
                    "id": event.id,
                    "at": at,
                    "category": kind,
                    "level": level,
                    "who": who,
                    "actor": said.get("actor") or (None if who else "House"),
                    "tried": said.get("tried"),
                    "care": care,
                    "resolved_at": resolved,
                    "count": 1,
                    "times": [at],
                    "template": template,
                    "values": values,
                    "_same": same,
                    "_oldest": event.created_at.timestamp(),
                }
            )
            if len(lines) >= 60:
                return {"items": clean(lines), "next": event.id}
    return {"items": clean(lines), "next": cursor}


def clean(lines):
    for row in lines:
        row.pop("_same"), row.pop("_oldest")
    return lines
