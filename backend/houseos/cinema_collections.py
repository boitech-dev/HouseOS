"""The Watch home's collections: saved filters over the local catalogue indexes
(cinema_explore.py). A new collection is one line of data. The home shows the seasonal ones
for this month, the ones pinned for their kind, and six more that change every week (the same
six for everyone that week). A collection with too few titles is simply left out."""

from datetime import date
from functools import lru_cache

from . import cinema_explore

WEEKLY = 6

# key, title, kinds, filters, and optionally sort, months (seasonal) or pinned (always shown).
COLLECTIONS = [
    # Seasonal
    dict(key="halloween", title="Horror nights", kinds=("movie",), filters={"genre": "Horror"}, months=(10,)),
    dict(
        key="christmas", title="Christmas films", kinds=("movie",), filters={"tag": "christmas"}, months=(12,)
    ),
    dict(
        key="summer",
        title="Summer blockbusters",
        kinds=("movie",),
        filters={"genre": "Action", "year_from": 1990},
        months=(7, 8),
    ),
    dict(
        key="anime-spooky", title="Spooky anime", kinds=("anime",), filters={"genre": "Horror"}, months=(10,)
    ),
    # Always there
    dict(
        key="new",
        title="New this year",
        kinds=("movie", "series"),
        filters={"year_from": "this_year"},
        pinned=True,
    ),
    dict(
        key="season",
        title="This season",
        kinds=("anime",),
        filters={"airing": True, "season": "this_season"},
        pinned=True,
    ),
    # Awards
    dict(
        key="best-picture", title="Best Picture Oscars", kinds=("movie",), filters={"award": "best-picture"}
    ),
    dict(key="palme", title="Palme d'Or winners", kinds=("movie",), filters={"award": "palme-dor"}),
    dict(key="cesar", title="César for Best Film", kinds=("movie",), filters={"award": "cesar"}),
    dict(key="venice", title="Golden Lions of Venice", kinds=("movie",), filters={"award": "golden-lion"}),
    dict(key="berlin", title="Golden Bears of Berlin", kinds=("movie",), filters={"award": "golden-bear"}),
    dict(
        key="animated-oscar",
        title="Oscar-winning animation",
        kinds=("movie",),
        filters={"award": "animated-oscar"},
    ),
    dict(
        key="international",
        title="Best International Feature",
        kinds=("movie",),
        filters={"award": "international-oscar"},
    ),
    # Themes (films and series)
    dict(key="zombies", title="Zombie night", kinds=("movie", "series"), filters={"tag": "zombies"}),
    dict(key="heists", title="Heists", kinds=("movie",), filters={"tag": "heist"}),
    dict(
        key="time-loops",
        title="Time travel and loops",
        kinds=("movie", "series"),
        filters={"tag": "time-travel"},
    ),
    dict(key="true-stories", title="True stories", kinds=("movie",), filters={"tag": "true-story"}),
    dict(key="space", title="Lost in space", kinds=("movie", "series"), filters={"tag": "space"}),
    dict(
        key="apocalypse",
        title="After the end of the world",
        kinds=("movie", "series"),
        filters={"tag": "post-apocalyptic"},
    ),
    dict(key="dystopia", title="Dystopias", kinds=("movie", "series"), filters={"tag": "dystopia"}),
    dict(key="vampires", title="Vampires", kinds=("movie", "series"), filters={"tag": "vampires"}),
    dict(key="spies", title="Spies", kinds=("movie", "series"), filters={"tag": "spy"}),
    dict(
        key="gangsters", title="Gangsters and the mob", kinds=("movie", "series"), filters={"tag": "gangster"}
    ),
    dict(key="westerns", title="Westerns", kinds=("movie",), filters={"tag": "western"}),
    dict(key="coming-of-age", title="Coming of age", kinds=("movie",), filters={"tag": "coming-of-age"}),
    dict(key="cyberpunk", title="Cyberpunk", kinds=("movie", "series"), filters={"tag": "cyberpunk"}),
    dict(key="disasters", title="Disaster films", kinds=("movie",), filters={"tag": "disaster"}),
    dict(key="monsters", title="Monsters and kaiju", kinds=("movie",), filters={"tag": "monster"}),
    dict(key="found-footage", title="Found footage", kinds=("movie",), filters={"tag": "found-footage"}),
    dict(key="martial-arts-films", title="Martial arts", kinds=("movie",), filters={"tag": "martial-arts"}),
    dict(key="superheroes", title="Superheroes", kinds=("movie", "series"), filters={"tag": "superhero"}),
    dict(key="courtroom", title="Courtroom dramas", kinds=("movie", "series"), filters={"tag": "courtroom"}),
    dict(key="road-movies", title="Road movies", kinds=("movie",), filters={"tag": "road-movie"}),
    dict(key="short", title="Under 90 minutes", kinds=("movie",), filters={"max_minutes": 90}),
    dict(key="80s", title="The 80s", kinds=("movie", "series"), filters={"year_from": 1980, "year_to": 1989}),
    dict(
        key="90s",
        title="The 90s",
        kinds=("movie", "series", "anime"),
        filters={"year_from": 1990, "year_to": 1999},
    ),
    dict(key="classics", title="Classics before 1970", kinds=("movie",), filters={"year_to": 1969}),
    # Anime
    dict(key="isekai", title="Another world (isekai)", kinds=("anime",), filters={"tag": "isekai"}),
    dict(key="mecha", title="Giant robots", kinds=("anime",), filters={"tag": "mecha"}),
    dict(key="anime-sports", title="Sports anime", kinds=("anime",), filters={"tag": "sports"}),
    dict(key="mind-games", title="Mind games", kinds=("anime",), filters={"tag": "psychological"}),
    dict(key="iyashikei", title="Comfy and calm", kinds=("anime",), filters={"tag": "iyashikei"}),
    dict(key="anime-zombies", title="Zombie anime", kinds=("anime",), filters={"tag": "zombies"}),
    dict(key="anime-time", title="Time travel anime", kinds=("anime",), filters={"tag": "time-travel"}),
    dict(key="anime-food", title="Food anime", kinds=("anime",), filters={"tag": "food"}),
    dict(key="anime-survival", title="Survival games", kinds=("anime",), filters={"tag": "survival"}),
    dict(key="anime-cyberpunk", title="Cyberpunk anime", kinds=("anime",), filters={"tag": "cyberpunk"}),
    dict(
        key="anime-short",
        title="Short series (13 episodes or less)",
        kinds=("anime",),
        filters={"max_episodes": 13},
    ),
    dict(key="anime-rated", title="Best rated anime", kinds=("anime",), filters={}, sort="rated"),
    dict(key="ghibli", title="Studio Ghibli", kinds=("anime",), filters={"person": "Studio Ghibli"}),
    dict(key="kyoani", title="Kyoto Animation", kinds=("anime",), filters={"person": "Kyoto Animation"}),
    dict(key="ufotable", title="ufotable", kinds=("anime",), filters={"person": "ufotable"}),
    dict(key="mappa", title="MAPPA", kinds=("anime",), filters={"person": "MAPPA"}),
    # One director each week (films)
    dict(key="spotlight", title="Spotlight: {name}", kinds=("movie",), filters={"person": "spotlight"}),
]
# Classic rows, always shown in this order, before the niche ones.
CLASSICS = {
    "movie": ["Action", "Comedy", "Drama", "Horror", "Sci-Fi", "Thriller", "Romance", "Animation"],
    "series": ["Drama", "Comedy", "Crime", "Sci-Fi", "Animation", "Mystery", "Documentary"],
    "anime": ["Action", "Comedy", "Romance", "Fantasy", "Slice of Life", "Sports", "Mystery", "Horror"],
}
SPOTLIGHT = [
    "Denis Villeneuve", "Christopher Nolan", "Bong Joon-ho", "Agnès Varda", "Akira Kurosawa",
    "Wong Kar-wai", "Céline Sciamma", "Stanley Kubrick", "Alfred Hitchcock", "Jacques Audiard",
    "Park Chan-wook", "Guillermo del Toro", "Greta Gerwig", "Quentin Tarantino", "Martin Scorsese",
    "Sofia Coppola", "Jean-Pierre Jeunet", "David Fincher", "Hayao Miyazaki", "François Truffaut",
    "Jean-Luc Godard", "Spike Lee", "Kathryn Bigelow", "Ridley Scott", "Wes Anderson",
    "Hirokazu Kore-eda", "Pedro Almodóvar", "Luc Besson", "Joel Coen", "Jordan Peele",
]  # fmt: skip
SEASONS = ["WINTER", "WINTER", "WINTER", "SPRING", "SPRING", "SPRING",
           "SUMMER", "SUMMER", "SUMMER", "FALL", "FALL", "FALL"]  # fmt: skip


def resolved(collection, today):
    """The collection's filters for today (this year, this season, this week's director)."""
    filters, name = dict(collection["filters"]), None
    if filters.get("year_from") == "this_year":
        filters["year_from"] = today.year
    if filters.get("season") == "this_season":
        filters["season"] = SEASONS[today.month - 1]
        filters["year_from"] = filters["year_to"] = today.year
    if filters.get("person") == "spotlight":
        name = SPOTLIGHT[today.isocalendar().week % len(SPOTLIGHT)]
        filters["person"] = name
    return filters, name


def chosen(kind, today):
    """Which collections show this week, in order: seasonal, pinned, then six rotating."""
    mine = [c for c in COLLECTIONS if kind in c["kinds"]]
    seasonal = [c for c in mine if today.month in c.get("months", ())]
    pinned = [c for c in mine if c.get("pinned")]
    rotating = [c for c in mine if not c.get("months") and not c.get("pinned")]
    if not rotating:
        return seasonal + pinned
    start = today.isocalendar().week * WEEKLY % len(rotating)
    week = (rotating[start:] + rotating[:start])[:WEEKLY]
    return seasonal + pinned + week


def for_the_page(filters, sort=None):
    """The same filters in the Watch page's own terms, for "See all"."""
    page = {k: v for k, v in filters.items() if k in {"year_from", "year_to", "genre", "person", "award"}}
    if filters.get("tag"):
        page["tag"] = [filters["tag"]]
    if filters.get("max_minutes") or filters.get("max_episodes"):
        page["short"] = True
    if sort:
        page["sort"] = sort
    return page


def this_week(kind, today=None):
    """Classic genre rows, then this week's niche collections. Each row loads its own titles
    (endless, sideways) through /cinema/explore with its filters; empty or thin ones are left out.
    The same week, kind and index give the same rows, so they are worked out once."""
    today = today or date.today()
    local = cinema_explore.index(kind)
    if not local and kind != "anime":
        # No local index for this kind yet: genre rows only, which explore serves from Cinemeta.
        return [
            {"key": "genre-" + g, "title": g, "name": None, "group": "classic", "total": None,
             "sort": "known", "filters": for_the_page({"genre": g}, None), "query": {"genre": g}}
            for g in CLASSICS.get(kind, [])
        ]  # fmt: skip
    return _this_week(kind, today, len(local))


@lru_cache(maxsize=12)
def _this_week(kind, today, size):
    rows = [
        dict(key="genre-" + genre, title=genre, group="classic", filters={"genre": genre})
        for genre in CLASSICS.get(kind, [])
    ]
    for collection in chosen(kind, today):
        filters, name = resolved(collection, today)
        rows.append(dict(collection, filters=filters, name=name, group="niche"))
    shown = []
    for row in rows:
        total = len(cinema_explore.matching(kind, **row["filters"]))
        if total < 6:
            continue
        shown.append(
            {
                "key": row["key"],
                "title": row["title"],
                "name": row.get("name"),
                "group": row["group"],
                "total": total,
                "sort": row.get("sort", "known"),
                # The same filters in the page's own terms, for the row and for "See all".
                "filters": for_the_page(row["filters"], row.get("sort")),
                "query": {k: v for k, v in row["filters"].items()},
            }
        )
    return shown
