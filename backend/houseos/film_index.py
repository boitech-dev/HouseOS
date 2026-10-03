"""The local film and series index behind Watch's filters and collections, built from Wikidata
(free, CC0, no account) by the maintenance service once a week. Queries go to Wikidata's own
service, then to QLever (a public mirror) when it is down; a build takes an hour or two in
the background and resumes where it stopped. HouseOS also ships a ready copy (houseos/data), so filters never wait.

Kept: notable titles with an IMDb id (Wikipedia pages in 8+ languages for films, 10+ for
series, about 45 000 titles): English and French title, year, genres, themes, directors, main
cast, a few awards, running time and how well known it is. Read by cinema_explore.py."""

import datetime
import json
import threading
import time
import urllib.parse
import urllib.request

from .atomic import write_json
from .config import settings

# Wikidata's own service first (slow but complete); QLever, a fast mirror, when it is down.
# QLever has been seen answering joins with nothing while reloading, so empty answers to the
# main queries count as failures (see sparql's at_least) and a repair pass fills gaps.
ENDPOINTS = ("https://query.wikidata.org/sparql", "https://qlever.dev/api/wikidata")
PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
AGENT = "HouseOS (https://github.com/boitech-dev/HouseOS; weekly film index)"
FILM_MIN_SITELINKS, SERIES_MIN_SITELINKS = 8, 10
BATCH, PAUSE = 200, 1.5
EVERY = 7 * 86400
FILM_CLASSES = "wd:Q11424"  # film (scanned per five years)
ANIMATED_FILM_CLASSES = "wd:Q202866 wd:Q20650540"  # animated film, anime film
SERIES_CLASSES = "wd:Q5398426 wd:Q117467246 wd:Q63952888 wd:Q1259759"  # series, animated, anime, miniseries

# key, label, Wikidata items (verified 2026-09-24 by label and title counts).
GENRES = [
    ("action", "Action", "Q188473 Q2678111 Q3990883 Q20656232 Q1033891"),
    ("comedy", "Comedy", "Q157443 Q859369 Q860626 Q118612349 Q622548 Q224700 Q108466999 Q2678111 Q761469 Q5778924 Q16950433"),
    ("drama", "Drama", "Q130232 Q859369 Q113485322 Q63214877 Q7168625 Q1919632"),
    ("horror", "Horror", "Q200092 Q853630 Q3072049 Q2137852 Q102260466 Q224700 Q108466999 Q43911809 Q909586 Q10663882"),
    ("thriller", "Thriller", "Q2484376 Q182015 Q590103 Q109733304 Q3990883 Q19367312 Q109733333 Q2439025 Q16950433 Q11304653"),
    ("scifi", "Sci-Fi", "Q471839 Q24925 Q20656232 Q174526 Q761469 Q10663882 Q20443008 Q104765957"),
    ("fantasy", "Fantasy", "Q157394 Q132311"),
    ("animation", "Animation", "Q202866 Q29168811 Q20650540 Q581714 Q117467246 Q63952888"),
    ("documentary", "Documentary", "Q93204"),
    ("romance", "Romance", "Q1054574 Q860626 Q118612349"),
    ("crime", "Crime", "Q959790 Q7444356 Q496523 Q19367312 Q113485322 Q2101714 Q2421031 Q185867"),
    ("adventure", "Adventure", "Q319221"),
    ("mystery", "Mystery", "Q1200678"),
    ("family", "Family", "Q1361932 Q2143665"),
]  # fmt: skip
# Themes: matched on genre (P136), main subject (P921), setting (P840) or characteristic (P1552).
TAGS = [
    ("zombies", "Zombies", "Q3072049 Q9406"),
    ("heist", "Heists", "Q496523"),
    ("time-travel", "Time travel and loops", "Q104765957 Q182154 Q186610"),
    ("vampires", "Vampires", "Q2137852 Q46721"),
    ("dystopia", "Dystopias", "Q20443008"),
    ("space", "Space", "Q468478 Q4235011 Q135246202 Q4169 Q5916 Q180046 Q11631 Q111 Q405"),
    ("true-story", "True stories", "Q645928 Q28146524"),
    ("post-apocalyptic", "Post-apocalyptic", "Q1341051"),
    ("coming-of-age", "Coming of age", "Q102429885 Q681737 Q2975633"),
    ("samurai", "Samurai and ninjas", "Q169672"),
    ("mockumentary", "Mockumentary", "Q459435"),
    ("found-footage", "Found footage", "Q3272147"),
    ("cyberpunk", "Cyberpunk", "Q174526"),
    ("slasher", "Slashers", "Q853630"),
    ("disaster", "Disasters", "Q846544"),
    ("sports", "Sports", "Q1339864"),
    ("musical", "Musicals", "Q842256"),
    ("war", "War and military", "Q369747"),
    ("western", "Westerns", "Q172980"),
    ("noir", "Film noir", "Q185867"),
    ("road-movie", "Road movies", "Q628165"),
    ("courtroom", "Courtroom", "Q3072039 Q643873"),
    ("martial-arts", "Martial arts", "Q1033891"),
    ("superhero", "Superheroes", "Q1535153"),
    ("christmas", "Christmas", "Q28026639"),
    ("monster", "Monsters and kaiju", "Q1342372 Q1065444"),
    ("psychological", "Psychological", "Q590103 Q109733304"),
    ("survival", "Survival", "Q15898171"),
    ("spy", "Spies", "Q2297927"),
    ("gangster", "Gangsters and the mob", "Q7444356 Q33130924 Q46952 Q731194"),
    ("romcom", "Romantic comedy", "Q860626 Q118612349"),
    ("body-horror", "Body horror", "Q102260466 Q3641550"),
    ("alien-invasion", "Alien invasions", "Q2447078"),
    ("robots", "Robots and AI", "Q11660 Q11012 Q181787"),
    ("serial-killer", "Serial killers", "Q484188"),
    ("teen", "Teen films", "Q1146335"),
    ("parody", "Parodies", "Q622548"),
    ("historical", "Historical", "Q17013749"),
]
AWARDS = [
    ("best-picture", "Best Picture Oscar", "Q102427"),
    ("palme-dor", "Palme d'Or", "Q179808"),
    ("cesar", "César for Best Film", "Q645595"),
    ("golden-lion", "Golden Lion (Venice)", "Q209459"),
    ("golden-bear", "Golden Bear (Berlin)", "Q154590"),
    ("bafta", "BAFTA Best Film", "Q139184"),
    ("golden-globe-drama", "Golden Globe, Best Drama", "Q1011509"),
    ("animated-oscar", "Best Animated Feature Oscar", "Q106800"),
    ("international-oscar", "Best International Feature Oscar", "Q105304"),
]


def _by_item(table):
    found = {}
    for key, _, items in table:
        for item in items.split():
            found.setdefault(item, []).append(key)
    return found


GENRE_OF, TAG_OF, AWARD_OF = _by_item(GENRES), _by_item(TAGS), _by_item(AWARDS)
state = {"thread": None, "error": ""}


def paths():
    folder = settings.runtime_root / "cinema" / "catalog-cache"
    return folder / "film-index.json", folder / "film-index.partial.json"


def sparql(query, at_least=0):
    """One query, to QLever then to Wikidata's own service (both ask for a named client). An
    answer with fewer than `at_least` rows counts as a failure: a mirror mid-reload answers
    quickly with nothing, and an empty year must not look like a finished one."""
    body = urllib.parse.urlencode({"query": PREFIXES + query}).encode()
    failures = []
    for endpoint in ENDPOINTS:
        for attempt in (0, 1):
            request = urllib.request.Request(
                endpoint,
                data=body,
                headers={"User-Agent": AGENT, "Accept": "application/sparql-results+json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    rows = json.load(response)["results"]["bindings"]
                time.sleep(PAUSE)
                if len(rows) < at_least:
                    raise ValueError(f"only {len(rows)} rows from {endpoint}")
                return [
                    {
                        k: v["value"].rsplit("/", 1)[-1] if v["type"] == "uri" else v["value"]
                        for k, v in row.items()
                    }
                    for row in rows
                ]
            except (OSError, ValueError, KeyError) as error:
                host = urllib.parse.urlsplit(endpoint).hostname
                failures.append(f"{host}: {getattr(error, 'code', '') or type(error).__name__}")
                time.sleep(5 * (attempt + 1))
    # Each service's own answer (a status code or an error name), not only the last one.
    raise ConnectionError("no usable answer (" + "; ".join(failures) + ")")


def core_query(classes, sitelinks, years=None, date="wdt:P577"):
    """Notable titles of these classes (optionally released in [from, to)): id, IMDb id, fame, date."""
    span = (
        f'?f {date} ?d . FILTER(?d >= "{years[0]}-01-01T00:00:00Z"^^xsd:dateTime'
        f' && ?d < "{years[1]}-01-01T00:00:00Z"^^xsd:dateTime)'
        if years
        else f"OPTIONAL {{ ?f {date} ?d }}"
    )
    return f"""SELECT ?f ?imdb ?s (MIN(?d) AS ?date) WHERE {{
  VALUES ?cls {{ {classes} }}
  ?f wdt:P31 ?cls ; wikibase:sitelinks ?s ; wdt:P345 ?imdb .
  FILTER(?s >= {sitelinks}) {span}
}} GROUP BY ?f ?imdb ?s"""


def take(rows, index, kind, genres=()):
    """New titles from a core query (earliest year wins); returns the ones to describe."""
    fresh = []
    for row in rows:
        year = int(row["date"][:4]) if row.get("date", "")[:4].isdigit() else None
        entry = index.get(row["f"])
        if entry:
            if year and (entry["y"] is None or year < entry["y"]):
                entry["y"] = year
            continue
        if not row["imdb"].startswith("tt"):
            continue
        index[row["f"]] = {
            "id": row["imdb"], "t": None, "f": None, "k": kind, "y": year, "n": int(row["s"]),
            "g": list(genres), "s": [], "d": [], "c": [], "a": [], "r": None,
        }  # fmt: skip
        fresh.append(row["f"])
    return fresh


def learn_names(ids, names):
    """English names for these people, else Wikidata's multilingual one ("mul"): since 2024 many
    well-known people (Angelina Jolie) keep their name there only, and an English-only lookup
    dropped them from every cast."""
    ids = sorted(set(ids) - names.keys())
    for start in range(0, len(ids), 2000):
        chunk = " ".join("wd:" + v for v in ids[start : start + 2000])
        found = {}
        for row in sparql(
            f"""SELECT ?v ?name (LANG(?name) AS ?lang) WHERE {{ VALUES ?v {{ {chunk} }}
  ?v rdfs:label ?name FILTER(LANG(?name) IN ("en", "mul")) }}"""
        ):
            if row.get("lang") == "en" or row["v"] not in found:
                found[row["v"]] = row["name"]
        names.update(found)


def describe(items, index, names):
    """Titles, running time, genres, themes, awards and people for up to BATCH titles."""
    values = " ".join("wd:" + item for item in items)
    for row in sparql(f"""SELECT ?f ?en ?mul ?fr ?dur WHERE {{ VALUES ?f {{ {values} }}
  OPTIONAL {{ ?f rdfs:label ?en FILTER(LANG(?en) = "en") }}
  OPTIONAL {{ ?f rdfs:label ?mul FILTER(LANG(?mul) = "mul") }}
  OPTIONAL {{ ?f rdfs:label ?fr FILTER(LANG(?fr) = "fr") }}
  OPTIONAL {{ ?f p:P2047/psn:P2047/wikibase:quantityAmount ?dur }} }}"""):
        entry = index[row["f"]]
        entry["t"] = entry["t"] or row.get("en") or row.get("mul")
        entry["f"] = entry["f"] or row.get("fr")
        if row.get("dur") and not entry["r"]:
            entry["r"] = round(float(row["dur"]) / 60) or None  # normalised to seconds
    for row in sparql(f"""SELECT ?f ?p ?v WHERE {{ VALUES ?f {{ {values} }}
  VALUES ?p {{ wdt:P31 wdt:P136 wdt:P921 wdt:P840 wdt:P1552 wdt:P166 }} ?f ?p ?v . }}"""):
        entry, value, prop = index[row["f"]], row["v"], row["p"]
        adds = {
            "a": AWARD_OF.get(value, []) if prop == "P166" else [],
            "g": GENRE_OF.get(value, []) if prop in {"P31", "P136"} else [],
            "s": TAG_OF.get(value, []) if prop in {"P136", "P921", "P840", "P1552"} else [],
        }
        for key, found in adds.items():
            entry[key] += [x for x in found if x not in entry[key]]
    # People: ids and fame first (fast), names only for the ones kept (labels are the slow part).
    people = {}
    for row in sparql(f"""SELECT ?f ?p ?v ?s WHERE {{ VALUES ?f {{ {values} }}
  VALUES ?p {{ wdt:P57 wdt:P161 }} ?f ?p ?v . OPTIONAL {{ ?v wikibase:sitelinks ?s }} }}"""):
        people.setdefault((row["f"], row["p"]), {})[row["v"]] = int(row.get("s", 0))
    # ponytail: cast has no billing order on Wikidata; the best-known six stand in for it.
    kept = {
        key: sorted(v, key=v.get, reverse=True)[: 6 if key[1] == "P161" else 3] for key, v in people.items()
    }
    learn_names([v for vs in kept.values() for v in vs], names)
    for (item, prop), who in kept.items():
        index[item]["d" if prop == "P57" else "c"] = [names[v] for v in who if v in names]


def steps(this_year):
    """The build in resumable pieces: films five years at a time until 2005, then one year at a
    time (a five-year query of the 2010s is too big for Wikidata's 60 s limit), animated films,
    then series."""
    for start in range(1890, 2005, 5):
        yield f"films-{start}", core_query(FILM_CLASSES, FILM_MIN_SITELINKS, (start, start + 5)), "movie", ()
    for year in range(2005, this_year):
        yield f"films-{year}", core_query(FILM_CLASSES, FILM_MIN_SITELINKS, (year, year + 1)), "movie", ()
    yield "animated-films", core_query(ANIMATED_FILM_CLASSES, FILM_MIN_SITELINKS), "movie", ("animation",)
    yield "series", core_query(SERIES_CLASSES, SERIES_MIN_SITELINKS, date="wdt:P580|wdt:P577"), "series", ()


def backfill(work):
    """Asks again for directors and cast that a failing service left empty (best effort)."""
    names = work["names"]
    missing = [
        item for item, entry in work["index"].items() if entry["t"] and not (entry["d"] and entry["c"])
    ]
    for start in range(0, len(missing), BATCH):
        batch = missing[start : start + BATCH]
        values = " ".join("wd:" + item for item in batch)
        people = {}
        for row in sparql(f"""SELECT ?f ?p ?v ?s WHERE {{ VALUES ?f {{ {values} }}
  VALUES ?p {{ wdt:P57 wdt:P161 }} ?f ?p ?v . OPTIONAL {{ ?v wikibase:sitelinks ?s }} }}"""):
            people.setdefault((row["f"], row["p"]), {})[row["v"]] = int(row.get("s", 0))
        kept = {
            key: sorted(v, key=v.get, reverse=True)[: 6 if key[1] == "P161" else 3]
            for key, v in people.items()
        }
        learn_names([v for vs in kept.values() for v in vs], names)
        for (item, prop), who in kept.items():
            found = [names[v] for v in who if v in names]
            if found:
                work["index"][item]["d" if prop == "P57" else "c"] = found


def publish(work, final):
    """Writes the index when it has more titles than the one in use: filters get new titles
    while a build is still running, and a half-answered build never replaces a better one."""
    items = [entry for entry in work["index"].values() if entry["t"]]
    if len(items) <= previous_size():
        return 0
    stamp = datetime.datetime.now(datetime.UTC).isoformat()
    write_json(final, {"version": 1, "built_at": stamp, "complete": False, "items": items})
    return len(items)


def build():
    """Runs every step not done yet, saving and publishing after each; a failed step raises
    (maintenance tries again later, from where it stopped)."""
    final, partial = paths()
    try:
        work = json.loads(partial.read_text())
        if time.time() - work.get("started", 0) > EVERY:
            raise ValueError("stale")
    except (OSError, ValueError):
        work = {"started": time.time(), "done": [], "index": {}, "names": {}}
    for key, query, kind, genres in steps(datetime.date.today().year):
        if key in work["done"]:
            continue
        fresh = take(sparql(query, at_least=1 if key >= "films-1920" else 0), work["index"], kind, genres)
        for start in range(0, len(fresh), BATCH):
            describe(fresh[start : start + BATCH], work["index"], work["names"])
        work["done"].append(key)
        write_json(partial, work)
        publish(work, final)
        print("film_index_step", key, len(fresh), "new", flush=True)
    if "people" not in work["done"]:
        backfill(work)
        work["done"].append("people")
        write_json(partial, work)
    items = [entry for entry in work["index"].values() if entry["t"]]
    if len(items) >= 0.9 * previous_size():  # a complete build replaces even a bigger old one
        stamp = datetime.datetime.now(datetime.UTC).isoformat()
        write_json(final, {"version": 1, "built_at": stamp, "complete": True, "items": items})
    partial.unlink(missing_ok=True)
    return len(items)


def previous_size():
    """How many titles the index in use has (this server's, else the one HouseOS ships)."""
    import gzip

    from .cinema_explore import BUNDLED

    final, _ = paths()
    for path, opener in ((final, open), (BUNDLED, gzip.open)):
        try:
            with opener(path, "rt") as stream:
                return len(json.load(stream).get("items", []))
        except (OSError, ValueError):
            continue
    return 0


def refresh(db=None):
    """Maintenance step: starts a background build when the index is missing or a week old."""
    final, partial = paths()
    try:
        # Steps publish as they finish, so a recent file is not a finished one: while the
        # partial build exists, the index is still growing and the build must carry on.
        fresh = time.time() - final.stat().st_mtime < EVERY and not partial.exists()
    except OSError:
        fresh = False
    running = state["thread"] and state["thread"].is_alive()
    if fresh or running or time.time() < state.get("retry_at", 0):
        return 0

    def run():
        from .events import failure_site

        try:
            count = build()
            print("film_index_build_done", count, "titles", flush=True)
            state["error"] = ""
            from .activity import note

            note("Film index rebuilt: {count} titles", "good", count=count)
        except Exception as error:  # noqa: BLE001 - the build retries in an hour, keeping its progress
            state["error"], state["retry_at"] = type(error).__name__, time.time() + 3600
            # Said in the journal: a build that keeps failing must not be invisible.
            said = str(error) if isinstance(error, ConnectionError) else ""
            print("film_index_build_failed", failure_site(error), said, "retry in 1 h", flush=True)
            try:
                from .activity import note

                note(
                    "Film index build failed, retrying in an hour ({error})",
                    "problem",
                    error=type(error).__name__,
                )
            except Exception:  # noqa: BLE001 - the journal line above is enough
                pass

    state["thread"] = threading.Thread(target=run, name="film-index", daemon=True)
    state["thread"].start()
    return 1
