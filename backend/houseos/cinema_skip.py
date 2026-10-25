"""Skip openings and endings, when the person chose it on the launch card (it follows the
episodes autoplay starts after it).

Each episode's own times, never a guess: the file's chapters ("OP", "Opening", "ED", "Credits"),
else AniSkip's community times for that anime episode, only when the episode they were measured
on is as long as this file (another cut would skip the wrong minute). Nothing found: no skip."""

import json
import re

from fastapi import HTTPException

from .cinema_adapters import public_fetch
from .db import utcnow
from .playback import MediaError

ANISKIP = "https://api.aniskip.com/v2/skip-times/{mal}/{episode}?types=op&types=ed&episodeLength=0"
OPENING = re.compile(r"(op|opening|intro)( ?\d+)?( song| theme)?", re.I)
ENDING = re.compile(r"(ed|ending|credits|end credits|outro)( ?\d+)?( song| theme)?", re.I)


def plausible(start, end):
    return 20 <= end - start <= 240  # a song, not half the episode under a wrong label


def from_chapters(chapters):
    found = []
    for chapter in chapters or []:
        title = str(chapter.get("title") or "").strip()
        kind = "op" if OPENING.fullmatch(title) else "ed" if ENDING.fullmatch(title) else None
        start, end = float(chapter.get("start") or 0), float(chapter.get("end") or 0)
        if kind and plausible(start, end):
            found.append({"kind": kind, "start": start, "end": end})
    return found


def from_aniskip(canonical, episode, duration):
    if not canonical.startswith("mal:") or not episode or not duration:
        return []
    try:
        content, _ = public_fetch(ANISKIP.format(mal=canonical.removeprefix("mal:"), episode=episode))
        results = json.loads(content).get("results") or []
    except (MediaError, ValueError):
        return []  # not listed (AniSkip answers 404) or unreachable: nothing is skipped
    found = []
    for item in results:
        interval = item.get("interval") or {}
        start, end = float(interval.get("startTime") or 0), float(interval.get("endTime") or 0)
        if (
            item.get("skipType") in {"op", "ed"}
            and abs(float(item.get("episodeLength") or 0) - duration) <= 5
            and plausible(start, end)
        ):
            found.append({"kind": item["skipType"], "start": start, "end": end})
    return found


def marks(db, row):
    """Worked out once per episode, kept on it."""
    if row.data.get("_skips") is not None:
        return row.data["_skips"]
    from .cinema import CinemaTitle

    source = next(
        (s for s in row.data.get("_sources", []) if s["id"] == row.data.get("_selected_source")), {}
    )
    found = from_chapters((source.get("inspection") or {}).get("chapters"))
    if not found:
        title = db.get(CinemaTitle, row.media_id)
        parent = db.get(CinemaTitle, (title.data or {}).get("parent_id")) if title else None
        duration = float((row.data.get("plan") or {}).get("duration") or 0)
        found = from_aniskip(parent.canonical_id if parent else "", row.data.get("episode"), duration)
    row.data = {**row.data, "_skips": found}
    return found


def skip_now(db, row, actor):
    """Inside an opening or an ending: jump past it, once (seek back to watch it: it stays)."""
    if (
        row.state != "playing_observed"
        or not (row.data.get("request") or {}).get("skip_intros")
        or row.data.get("_seek_previous")
        or (row.data.get("observation") or {}).get("state") != "active"
    ):
        return
    from .cinema import Control, control

    position = float((row.data.get("checkpoint") or {}).get("position") or 0)
    duration = float((row.data.get("plan") or {}).get("duration") or 0)
    done = row.data.get("_skipped") or []
    for mark in marks(db, row):
        key = f"{mark['kind']}:{mark['start']}"
        if key in done or not mark["start"] - 1 <= position < mark["end"] - 3:
            continue
        # An ending that runs to the end lands a few seconds short of it: the episode then ends as
        # usual (and the next one starts), without loading the stream again at its very end.
        target = min(mark["end"], duration - 6) if duration else mark["end"]
        row.data = {
            **row.data,
            "_skipped": [*done, key],
            "_skip_note": {"kind": mark["kind"], "from": position, "at": utcnow().isoformat()},
        }
        db.commit()
        try:
            control(row.id, Control(version=row.version, action="seek", position=target), actor, db)
        except (HTTPException, MediaError):
            db.rollback()
        return
    db.commit()
