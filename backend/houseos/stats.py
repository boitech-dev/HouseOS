"""The house in numbers, for the Home board. Pure aggregation over what HouseOS already
records: one row per song played (`music.play`) and each resident's own film progress.
Films are only ever counted for the house as a whole; nobody's viewing is singled out."""

import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .auth import require_actor, require_permission
from .db import get_db, utcnow
from .models import Record, User

router = APIRouter(prefix="/stats", tags=["stats"])
CACHE = {"at": 0.0, "data": None}
WINDOW = 20000  # ponytail: newest plays only; a SQL rollup if a house ever plays more


def person(users, identity):
    user = users.get(identity)
    return {
        "id": identity,
        "name": user.name if user else "?",
        "avatar": ((user.preferences or {}).get("avatar", "crest")) if user else "crest",
    }


def heard_seconds(db, plays):
    """{queue item: seconds heard} for the plays that name their item: the player's last
    position, which is how long a station was listened to."""
    from .music import QueueItem

    ids = list({data["item"] for _, _, data in plays if data.get("item")})
    heard = {}
    for start in range(0, len(ids), 500):
        for identity, meta in db.execute(
            select(QueueItem.id, QueueItem.metadata_json).where(QueueItem.id.in_(ids[start : start + 500]))
        ):
            position = (meta or {}).get("last_position")
            if isinstance(position, (int, float)) and position > 0:
                heard[identity] = position
    return heard


def listened(data, heard):
    """Seconds one play was listened to: as far as the player got (never more than the song),
    else the song's length. A station counts its time on air, 12 h at most."""
    duration = data.get("duration") or 0
    position = heard.get(data.get("item"))
    if position is None:
        return duration
    return min(position, duration) if duration else min(position, 12 * 3600)


def compute(db):
    from .house_settings import get_house_settings
    from .music import source_metadata
    from .music_catalog import family

    house_settings = get_house_settings(db)
    zone = ZoneInfo(house_settings["timezone"])
    users = {user.id: user for user in db.scalars(select(User))}
    # Each song's genre as known now (music_catalog), with the house's own genres applied.
    songs = db.execute(select(Record.id, Record.data).where(Record.kind == "music.history")).all()
    genres_now = {identity: family(data, house_settings["music_genres"]) for identity, data in songs}
    stations = frozenset(i for i, data in songs if str(data.get("source_url") or "").startswith("radio:"))
    plays = list(
        db.execute(
            select(Record.owner_id, Record.created_at, Record.data)
            .where(Record.kind == "music.play")
            .order_by(Record.created_at.desc())
            .limit(WINDOW)
        )
    )
    heard = heard_seconds(db, plays)
    plays = [
        (owner, created, {**data, "genre": genres_now.get(data.get("key")) or data.get("genre") or "other"})
        for owner, created, data in plays
    ]
    now = utcnow()
    by_genre, genre_plays, by_key, hours = Counter(), Counter(), Counter(), [0] * 24
    seconds, week, last_week = 0, 0, 0
    for owner, created, data in plays:
        spent = listened(data, heard)
        by_genre[data["genre"]] += spent
        genre_plays[data["genre"]] += 1
        by_key[data.get("key")] += 1
        hours[created.replace(tzinfo=UTC).astimezone(zone).hour] += 1
        seconds += spent
        age = now - created
        week += age < timedelta(days=7)
        last_week += timedelta(days=7) <= age < timedelta(days=14)
    since = now - timedelta(days=7)
    games = game_numbers(db)
    house = house_records(db)
    ever = boards_for(plays, zone, {**house_counters(db, rows=house), **games.pop("_boards")}, stations)
    fresh = boards_for([p for p in plays if p[1] >= since], zone, house_counters(db, since, house), stations)
    keys = [key for key, _ in by_key.most_common(5)] + ever["songs"] + fresh["songs"]
    history = {row.id: row for row in db.scalars(select(Record).where(Record.id.in_(keys)))}
    meta = source_metadata(db, [row.data["source_url"] for row in history.values()])

    def song(key):
        row = history.get(key)
        info = meta.get(row.data["source_url"], {}) if row else {}
        return {"title": info.get("title") or "?", "artist": info.get("uploader"), "art": info.get("art")}

    by_person = ever["boards"]["dj"]
    return {
        "music": {
            "plays": len(plays),
            "hours": round(seconds / 3600, 1),
            "songs": len(by_key),
            "week": week,
            "last_week": last_week,
            "top_songs": [{**song(key), "plays": count} for key, count in by_key.most_common(5)],
            "djs": [{**person(users, owner), "plays": count} for owner, count in by_person.most_common(6)],
            # By time listened (a station's hours count as much as songs'), the 7 biggest.
            "genres": [
                {"name": name, "seconds": round(spent), "plays": genre_plays[name]}
                for name, spent in by_genre.most_common(7)
                if spent > 0
            ],
            "hours_of_day": hours,
        },
        "titles": award(ever, users, song, stars=True),
        "week": award(fresh, users, song, stars=False),
        "movies": movies(db, zone),
        "games": games,
        "_boards": ever["boards"],  # per-person scores for the viewer's own nudge; never sent as is
    }


def boards_for(plays, zone, house, stations=frozenset()):
    """Per-person scores for every title over one set of plays and house records.
    `stations`: history keys of radio stations (plays recorded before the `radio` flag)."""
    by_person, night, dawn, weekend, repeat = Counter(), Counter(), Counter(), Counter(), Counter()
    radio = Counter()
    distinct, genres_of, genres, longest = defaultdict(set), defaultdict(Counter), Counter(), {}
    for owner, created, data in plays:
        local = created.replace(tzinfo=UTC).astimezone(zone)
        genre = data.get("genre") or "other"
        by_person[owner] += 1
        radio[owner] += bool(data.get("radio") or data.get("key") in stations)
        night[owner] += local.hour < 5
        dawn[owner] += 5 <= local.hour < 9
        weekend[owner] += local.weekday() >= 5
        repeat[(owner, data.get("key"))] += 1
        distinct[owner].add(data.get("key"))
        genres_of[genre][owner] += 1
        genres[genre] += 1
        duration = data.get("duration") or 0
        if duration > longest.get("duration", 0):
            longest = {"owner": owner, "duration": duration, "key": data.get("key")}
    favourite = next((g for g, _ in genres.most_common() if g != "other"), None)
    top_repeat = repeat.most_common(1)
    return {
        "boards": {
            "dj": by_person,
            "night_owl": night,
            "early_bird": dawn,
            "weekend": weekend,
            "explorer": Counter({owner: len(keys) for owner, keys in distinct.items()}),
            "broken_record": Counter({top_repeat[0][0][0]: top_repeat[0][1]}) if top_repeat else Counter(),
            "marathon": Counter({longest["owner"]: round(longest["duration"] / 60)})
            if longest
            else Counter(),
            "genre_guardian": genres_of[favourite] if favourite else Counter(),
            "radio_host": Counter({owner: n for owner, n in radio.items() if n}),
            **house,
        },
        "extra": {
            "broken_record": {"song_key": top_repeat[0][0][1]} if top_repeat else {},
            "marathon": {"song_key": longest["key"]} if longest else {},
            "genre_guardian": {"genre": favourite},
        },
        "songs": ([top_repeat[0][0][1]] if top_repeat else []) + ([longest["key"]] if longest else []),
    }


def award(scores, users, song, stars):
    """Titles for one period: each goes to whoever leads it, however many that makes theirs (a
    title handed to a runner-up would name the wrong person). `stars`: all time counts them."""
    titles = []
    for key, family, tiers in TITLES:
        board = scores["boards"].get(key) or Counter()
        ranked = [(o, v) for o, v in board.most_common() if v >= (2 if key == "broken_record" else 1)]
        if not ranked:
            continue
        owner, value = ranked[0]
        extra = dict(scores["extra"].get(key, {}))
        if "song_key" in extra:
            extra["song"] = song(extra.pop("song_key"))["title"]
        titles.append(
            {
                "key": key,
                "family": family,
                "person": person(users, owner),
                "value": value,
                "stars": sum(value >= tier for tier in tiers) if stars else 0,
                **extra,
            }
        )
    return titles


# key, family, star thresholds (one star each). The holder is whoever leads; stars say how
# far they have gone. Films are private per person, so they never make a title.
TITLES = [
    ("dj", "music", (25, 100, 500)),
    ("explorer", "music", (20, 100, 400)),
    ("night_owl", "music", (5, 25, 100)),
    ("early_bird", "music", (5, 25, 100)),
    ("weekend", "music", (10, 50, 200)),
    ("genre_guardian", "music", (5, 25, 100)),
    ("broken_record", "music", (3, 10, 30)),
    ("marathon", "music", (20, 60, 120)),
    ("radio_host", "music", (5, 25, 100)),
    ("task_hero", "house", (3, 15, 50)),
    ("grocery_runner", "house", (5, 25, 100)),
    ("planner", "house", (3, 10, 30)),
    ("wall_poet", "house", (3, 10, 30)),
    ("courier", "house", (5, 25, 100)),
    ("curator", "music", (5, 25, 100)),
    ("high_scorer", "games", (1, 10, 50)),
    ("collector", "games", (5, 25, 100)),
    ("game_hopper", "games", (3, 10, 30)),
    ("console_hopper", "games", (2, 4, 8)),
    ("romhacker", "games", (1, 5, 20)),
]  # 20: tests/test_house_features.py keeps the total a multiple of five
NUDGE = {
    "dj",
    "explorer",
    "night_owl",
    "early_bird",
    "weekend",
    "radio_host",
    "task_hero",
    "grocery_runner",
    "planner",
}


def house_records(db):
    return db.execute(
        select(Record.kind, Record.owner_id, Record.visibility, Record.data, Record.created_at).where(
            Record.kind.in_(
                [
                    "household.tasks",
                    "household.groceries",
                    "household.calendar",
                    "household.board",
                    "household.messages",
                    "saved_track",
                ]
            ),
            Record.deleted_at.is_(None),
        )
    ).all()


def house_counters(db, since=None, rows=None):
    """Who keeps the house running: tasks finished, groceries bought, events planned, notes
    and messages sent (since `since` if given). Only house-visible records count; private
    ones stay out of it. `rows`: house_records, already read."""
    counters = {
        key: Counter()
        for key in ("task_hero", "grocery_runner", "planner", "wall_poet", "courier", "curator")
    }
    after = since.isoformat() if since else ""
    for kind, owner, visibility, data, created in house_records(db) if rows is None else rows:
        new = not since or created >= since
        if kind == "household.messages":
            counters["courier"][owner] += new
        elif kind == "saved_track":  # songs kept as favourites: only how many, never which
            counters["curator"][owner] += new
        elif visibility != "house":
            continue
        elif kind == "household.tasks" and data.get("status") == "done":
            who = data.get("completed_by") or data.get("assignee_id") or owner
            counters["task_hero"][who] += (data.get("completed_at") or "") >= after
        elif kind == "household.groceries" and data.get("purchased_by"):
            counters["grocery_runner"][data["purchased_by"]] += (data.get("purchased_at") or "") >= after
        elif kind == "household.calendar":
            counters["planner"][owner] += new
        elif kind == "household.board":
            counters["wall_poet"][owner] += new
    return {key: Counter({o: v for o, v in board.items() if v}) for key, board in counters.items()}


def game_numbers(db):
    """Games: house totals, the games and consoles played most, who plays, and the boards of the
    games titles (hours played, games brought, different games and consoles, romhacks added)."""
    from .games_catalog import fold
    from .games_systems import SYSTEMS

    roms = {
        r.id: r
        for r in db.scalars(select(Record).where(Record.kind == "game.rom", Record.deleted_at.is_(None)))
    }
    plays = [
        (owner, data)
        for owner, data in db.execute(select(Record.owner_id, Record.data).where(Record.kind == "game.play"))
        if data.get("game_id") in roms and (data.get("seconds") or data.get("plays"))
    ]
    users = {user.id: user for user in db.scalars(select(User))}
    seconds, by_game, by_console, by_person = 0, Counter(), Counter(), Counter()
    games_of, consoles_of = defaultdict(set), defaultdict(set)
    for owner, data in plays:
        rom = roms[data["game_id"]].data
        spent = data.get("seconds") or 0
        seconds += spent
        by_game[data["game_id"]] += spent
        by_console[rom.get("system")] += spent
        by_person[owner] += spent
        games_of[owner].add((rom.get("system"), rom.get("title")))
        consoles_of[owner].add(rom.get("system"))
    brought, hacks = Counter(), Counter()
    for row in roms.values():
        if row.data.get("source") != "folder":
            brought[row.owner_id] += 1
            hacks[row.owner_id] += bool(row.data.get("hack"))

    def game(identity, spent):
        rom = roms[identity].data
        art = rom.get("art") or {}
        return {
            "id": identity,
            "title": rom.get("title"),
            "system": SYSTEMS.get(rom.get("system") or "", {}).get("name"),
            "art": f"/api/v1/games/art/{rom.get('art_key')}/box" if art.get("box") else None,
            "hours": round(spent / 3600, 1),
        }

    return {
        "hours": round(seconds / 3600, 1),
        "played": len({(r.data.get("system"), r.data.get("title")) for i, r in roms.items() if by_game[i]}),
        "sessions": sum(data.get("plays") or 0 for _, data in plays),
        # Counted as the room counts them: one per game (versions together), duplicates and hidden out.
        "library": len(
            {
                (r.data.get("system"), fold(r.data.get("title") or ""))
                for r in roms.values()
                if not (r.data.get("hidden") or r.data.get("duplicate_of"))  # games.games(visible=True)
            }
        ),
        "top": [game(identity, spent) for identity, spent in by_game.most_common(5) if spent],
        "consoles": [
            {"name": SYSTEMS.get(key or "", {}).get("name", "?"), "seconds": spent}
            for key, spent in by_console.most_common(7)
            if spent
        ],
        "players": [
            {**person(users, owner), "hours": round(spent / 3600, 1)}
            for owner, spent in by_person.most_common(6)
            if spent
        ],
        "_boards": {
            "high_scorer": Counter({o: int(s // 3600) for o, s in by_person.items() if s >= 3600}),
            "collector": Counter({o: n for o, n in brought.items() if n}),
            "game_hopper": Counter({o: len(g) for o, g in games_of.items()}),
            "console_hopper": Counter({o: len(c) for o, c in consoles_of.items()}),
            "romhacker": Counter({o: n for o, n in hacks.items() if n}),
        },
    }


def nudge(boards, me):
    """The title the viewer is closest to taking: a gentle "3 more songs" from Nox."""
    best = None
    for key in NUDGE:
        board = boards.get(key) or Counter()
        if not board:
            continue
        holder, lead = board.most_common(1)[0]
        if holder == me:
            continue
        gap = lead - board.get(me, 0) + 1
        if gap <= 25 and (best is None or gap < best["n"]):
            best = {"key": key, "n": gap}
    return best


def movies(db, zone):
    """House totals, this month and all time; no per-person breakdown, by design. Time is split
    into films, series and anime (titles from the anime catalogue), and by each title's first
    genre."""
    from .cinema_models import CinemaState, CinemaTitle

    start = datetime.now(zone).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = start.astimezone(UTC).replace(tzinfo=None)
    rows = list(
        db.execute(
            select(
                CinemaState.data,
                CinemaState.last_watched_at,
                CinemaTitle.kind,
                CinemaTitle.canonical_id,
                CinemaTitle.data,
            ).join(CinemaTitle, CinemaTitle.id == CinemaState.media_id)
        )
    )
    parents = {
        identity: (canonical, data)
        for identity, canonical, data in db.execute(
            select(CinemaTitle.id, CinemaTitle.canonical_id, CinemaTitle.data).where(
                CinemaTitle.id.in_({title.get("parent_id") for *_, title in rows if title.get("parent_id")})
            )
        )
    }

    def block(chosen):
        kinds, genres, finished, episodes, total = Counter(), Counter(), 0, 0, 0
        for state, _, kind, canonical, title in chosen:
            if kind == "web":  # a web video (Watch → Web) is not a film night
                continue
            episode = kind == "episode" or bool(title.get("parent_id"))
            canonical, title = (
                parents.get(title.get("parent_id"), (canonical, title)) if episode else (canonical, title)
            )
            spent = (state.get("duration") or 0) if state.get("watched") else (state.get("position") or 0)
            total += spent
            family = (
                "anime"
                if canonical.startswith("mal:")
                else "series"
                if episode or kind == "series"
                else "film"
            )
            kinds[family] += spent
            first = (title.get("genres") or ["other"])[0]
            genres[first] += spent
            if state.get("watched"):
                finished += not episode
                episodes += episode
        return {
            "finished": finished,
            "episodes": episodes,
            "hours": round(total / 3600, 1),
            "kinds": {name: round(kinds[name] / 3600, 1) for name in ("film", "series", "anime")},
            "genres": [
                {"name": name, "seconds": round(spent)} for name, spent in genres.most_common(7) if spent > 0
            ],
        }

    return {
        "month": block([row for row in rows if row[1] and row[1] >= start]),
        "ever": block(rows),
    }


@router.get("/house")
def house(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "music.read")
    if actor.role == "guest":
        raise HTTPException(403, "House stats are for residents")
    if CACHE["data"] is None or time.monotonic() - CACHE["at"] > 60:
        CACHE["data"], CACHE["at"] = compute(db), time.monotonic()
    data = CACHE["data"]
    return {
        **{key: value for key, value in data.items() if key != "_boards"},
        "you": {
            "holds": [title["key"] for title in data["titles"] if title["person"]["id"] == actor.id],
            "next": nudge(data["_boards"], actor.id),
        },
    }
