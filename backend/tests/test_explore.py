import time

"""Watch discovery: filters over the local indexes, facets that only offer what exists,
collections that rotate by week and season, and anime tags/studios from the offline data."""

import json
from datetime import date

import pytest

from houseos import anime_offline, cinema_collections, cinema_explore
import test_cinema


def film(n, **extra):
    return {
        "canonical_id": f"tt{n:07d}",
        "title": f"Film {n}",
        "title_fr": f"Film FR {n}",
        "kind": "movie",
        "year": 1980 + n % 40,
        "genres": ["Horror"] if n % 2 else ["Comedy"],
        "tags": ["zombies"] if n % 3 == 0 else [],
        "people": ["Ada Director", "Bo Actor"] if n < 10 else ["Cy Director"],
        "director": ["Ada Director"] if n < 10 else ["Cy Director"],
        "cast": ["Bo Actor"],
        "awards": ["palme-dor"] if n < 8 else [],
        "minutes": 80 + n,
        "score": None,
        "known": 100 - n,
        "poster": f"https://images.metahub.space/poster/medium/tt{n:07d}/img",
        **extra,
    }


@pytest.fixture
def catalogue(monkeypatch):
    rows = [film(n) for n in range(60)]
    anime = [
        {
            **film(1000 + n),
            "canonical_id": f"mal:{n + 1}",
            "kind": "series",
            "tags": ["isekai"] if n < 20 else [],
            "people": ["Studio Ghibli"] if n < 7 else ["MAPPA"],
            "studios": ["Studio Ghibli"] if n < 7 else ["MAPPA"],
            "episodes": 12 if n % 2 else 24,
            "airing": n < 9,
            "season": "FALL",
            "year": 2026 if n < 9 else 2001,
            "score": 9 - n / 10,
        }
        for n in range(40)
    ]
    monkeypatch.setattr(cinema_explore, "index", lambda kind: anime if kind == "anime" else rows)
    return rows, anime


def test_filters_combine_and_page(catalogue):
    rows, _ = catalogue
    page = cinema_explore.discover("movie", tag="zombies", genre="horror", year_from=1985)
    expected = [r for r in rows if "zombies" in r["tags"] and "Horror" in r["genres"] and r["year"] >= 1985]
    assert page["total"] == len(expected) > 0
    assert all(int(item["year"]) >= 1985 and item["genres"] == ["Horror"] for item in page["items"])
    assert cinema_explore.discover("movie", person="ada")["total"] == 10  # any part of a name
    # Several people, several genres: each narrows the list further.
    assert cinema_explore.discover("movie", person="ada|bo actor")["total"] == 10
    assert cinema_explore.discover("movie", person="ada|cy director")["total"] == 0
    assert cinema_explore.discover("movie", genre="horror,comedy")["total"] == 0
    assert cinema_explore.discover("movie", q="film fr 12")["total"] == 1  # French titles match
    assert cinema_explore.discover("movie", award="palme-dor")["total"] == 8
    assert cinema_explore.discover("movie", max_minutes=90)["total"] == 11
    first = cinema_explore.discover("movie")
    assert first["next_offset"] == 24 and first["items"][0]["canonical_id"] == "tt0000000"  # best known
    newest = cinema_explore.discover("movie", sort="newest")["items"][0]
    assert newest["year"] == "2019" and newest["director"] and newest["_poster_url"].startswith("https://")
    rated = cinema_explore.discover("anime", sort="rated", max_episodes=13)["items"]
    assert rated[0]["rating"] and all(r["kind"] == "series" for r in rated)


def test_facets_offer_only_what_has_titles_and_people_suggest_names(catalogue):
    cinema_explore._facets.cache_clear()
    facets = cinema_explore.facets("movie")
    assert facets["ready"] and facets["years"] == [1980, 2019]
    assert {t["key"] for t in facets["tags"]} == {"zombies"}  # 20 titles; rarer tags are hidden
    assert facets["awards"][0]["key"] == "palme-dor" and facets["awards"][0]["label"]
    cinema_explore._people.cache_clear()
    assert cinema_explore.people("movie", "di") == ["Cy Director", "Ada Director"]  # best known first
    assert cinema_explore.people("anime", "ghi") == ["Studio Ghibli"]
    assert cinema_explore.people("movie", "a") == []  # two letters at least


def test_collections_rotate_weekly_follow_the_season_and_skip_thin_ones(catalogue):
    october = cinema_collections.chosen("movie", date(2026, 10, 5))
    assert october[0]["key"] == "halloween"
    march = [c["key"] for c in cinema_collections.chosen("movie", date(2026, 3, 2))]
    later = [c["key"] for c in cinema_collections.chosen("movie", date(2026, 3, 9))]
    assert "halloween" not in march and march[0] == "new" and march != later  # a new week, new rows
    assert len(march) == 1 + cinema_collections.WEEKLY
    rows = cinema_collections.this_week("anime", date(2026, 10, 5))
    keys = [row["key"] for row in rows]
    assert "season" in keys  # nine titles airing this autumn
    assert all(row["total"] >= 6 for row in rows)  # thin collections are left out
    assert [row["group"] for row in rows][:2] == ["classic", "classic"]  # genres first, then niche
    season = next(row for row in rows if row["key"] == "season")
    assert season["filters"] == {"year_from": 2026, "year_to": 2026}
    filters, name = cinema_collections.resolved(
        next(c for c in cinema_collections.COLLECTIONS if c["key"] == "spotlight"), date(2026, 1, 5)
    )
    assert filters["person"] == name and name in cinema_collections.SPOTLIGHT
    assert cinema_collections.for_the_page({"tag": "zombies", "max_minutes": 90}, "rated") == {
        "tag": ["zombies"],
        "short": True,
        "sort": "rated",
    }


def test_anime_tags_and_studio_names():
    assert anime_offline.studio("toei animation co., ltd.") == "Toei Animation"
    assert anime_offline.studio("Kyoto Animation Co., Ltd.") == "Kyoto Animation"
    assert anime_offline.studio("some new studio inc.") == "Some New Studio"
    tags = {"isekai", "time manipulation", "cooking"}
    assert [k for k, (_, words) in anime_offline.TAGS.items() if words & tags] == [
        "isekai",
        "time-travel",
        "food",
    ]


def test_explore_endpoints_store_openable_titles(catalogue, monkeypatch):
    zombies = [c for c in cinema_collections.COLLECTIONS if c["key"] == "zombies"]
    monkeypatch.setattr(cinema_collections, "chosen", lambda kind, today: zombies)
    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    try:
        response = fixture.client.get("/api/v1/cinema/explore?kind=movie&tag=zombies")
        assert response.status_code == 200
        row = response.json()["items"][0]
        assert row["id"] and row["poster"].startswith("/api/v1/cinema/titles/") and row["director"]
        assert "_poster_url" not in row
        assert fixture.client.get("/api/v1/cinema/explore?year_from=1700").status_code == 422
        facets = fixture.client.get("/api/v1/cinema/explore/facets?kind=anime").json()
        assert facets["people_label"] == "Studio"
        rows = fixture.client.get("/api/v1/cinema/collections?kind=movie").json()["items"]
        zombies = rows[-1]
        assert [r["key"] for r in rows] == ["genre-Comedy", "genre-Horror", "zombies"]
        assert zombies["total"] == 20 and zombies["filters"] == {"tag": ["zombies"]}
        # Each row loads itself, sideways and endless, through explore with its own query.
        page = fixture.client.get(
            "/api/v1/cinema/explore", params={"kind": "movie", **zombies["query"]}
        ).json()
        assert page["total"] == 20 and page["items"][0]["id"]
        # No local series yet: the popular list comes from Cinemeta instead of an empty tab.
        from houseos.cinema_adapters import Cinemeta

        monkeypatch.setattr(cinema_explore, "index", lambda kind: [])
        asked = []
        show = {"canonical_id": "tt0903747", "title": "Breaking Bad", "kind": "series", "year": "2008"}
        monkeypatch.setattr(
            Cinemeta, "browse", lambda self, *a: asked.append(a) or {"items": [show], "next_offset": 24}
        )
        series = fixture.client.get("/api/v1/cinema/explore?kind=series&genre=Drama").json()
        assert asked == [("series", "top", "Drama", 0)] and series["items"][0]["title"] == "Breaking Bad"
        assert fixture.client.get("/api/v1/cinema/explore?kind=series&tag=heist").json()["items"] == []
    finally:
        fixture.tearDown()


def test_more_like_this_shares_people_and_themes_and_anime_keep_their_franchise(catalogue, monkeypatch):
    rows, anime = catalogue
    anime[0]["related"] = ["mal:2", "mal:3"]
    like = cinema_explore.similar("movie", "tt0000003")
    assert like and "tt0000003" not in [x["canonical_id"] for x in like]
    assert like[0]["director"] == ["Ada Director"]  # same director counts most
    assert [x["canonical_id"] for x in cinema_explore.franchise("mal:1")] == ["mal:2", "mal:3"]
    assert {"mal:2", "mal:3"}.isdisjoint(x["canonical_id"] for x in cinema_explore.similar("anime", "mal:1"))
    assert cinema_explore.similar("movie", "tt9999999") == []  # not in the index: nothing invented

    from houseos import anime_catalog
    from houseos.playback import MediaError

    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    try:
        opened = fixture.client.get("/api/v1/cinema/explore?kind=anime&q=Film 1000").json()["items"][0]
        monkeypatch.setattr(
            anime_catalog.AnimeCatalog, "recommendations", lambda self, i: ["mal:30", "mal:31"]
        )
        answer = fixture.client.get(f"/api/v1/cinema/titles/{opened['id']}/similar").json()
        assert answer["source"] == "myanimelist"
        assert [x["canonical_id"] for x in answer["items"][:2]] == [
            "mal:30",
            "mal:31",
        ]  # members' picks first
        assert [x["canonical_id"] for x in answer["franchise"]] == ["mal:2", "mal:3"]

        def down(self, identity):
            raise MediaError("ANIME_CATALOG_UNAVAILABLE", "down", "identify", True)

        monkeypatch.setattr(anime_catalog.AnimeCatalog, "recommendations", down)
        answer = fixture.client.get(f"/api/v1/cinema/titles/{opened['id']}/similar").json()
        assert answer["source"] == "themes" and answer["items"]  # MyAnimeList down: similar themes
    finally:
        fixture.tearDown()


def test_film_index_builds_from_wikidata_answers_and_resumes(monkeypatch, tmp_path):
    from houseos import film_index

    monkeypatch.setattr(film_index.settings, "runtime_root", tmp_path)
    monkeypatch.setattr(film_index, "steps", lambda year: [("films-2000", "CORE", "movie", ())])
    answers = {
        "CORE": [{"f": "Q1", "imdb": "tt0000001", "s": "40", "date": "2003-05-01T00:00:00Z"},
                 {"f": "Q2", "imdb": "nm0000002", "s": "30", "date": "2004-01-01T00:00:00Z"}],
        "?en": [{"f": "Q1", "en": "Night of the Fixture", "fr": "La Nuit du test", "dur": "5400"}],
        "?p ?v WHERE": [{"f": "Q1", "p": "P136", "v": "Q3072049"}, {"f": "Q1", "p": "P166", "v": "Q179808"},
                        {"f": "Q1", "p": "P166", "v": "Q999"}],
        "?s WHERE": [{"f": "Q1", "p": "P57", "v": "Q10", "s": "50"},
                     {"f": "Q1", "p": "P161", "v": "Q11", "s": "5"}],
        # English wins; a name kept only in Wikidata's multilingual label ("mul") still counts.
        "?name": [{"v": "Q10", "name": "Ada (mul)", "lang": "mul"}, {"v": "Q10", "name": "Ada Director", "lang": "en"},
                  {"v": "Q11", "name": "Bo Actor", "lang": "mul"}],
    }  # fmt: skip
    asked = []

    def fake(query, at_least=0):
        asked.append(query)
        return next(rows for key, rows in answers.items() if key in query)

    monkeypatch.setattr(film_index, "sparql", fake)
    monkeypatch.setattr(film_index, "previous_size", lambda: 0)  # no index in use yet
    assert film_index.build() == 1
    final, partial = film_index.paths()
    entry = json.loads(final.read_text())["items"][0]
    assert entry == {
        "id": "tt0000001", "t": "Night of the Fixture", "f": "La Nuit du test", "k": "movie", "y": 2003,
        "n": 40, "g": ["horror"], "s": ["zombies"], "d": ["Ada Director"], "c": ["Bo Actor"],
        "a": ["palme-dor"], "r": 90,
    }  # fmt: skip
    assert not partial.exists()
    # Read back by the explorer: genres by name, the poster by IMDb id.
    cinema_explore._films.cache_clear()
    row = cinema_explore.films()[0]
    assert (
        row["genres"] == ["Horror"]
        and row["tags"] == ["zombies"]
        and row["poster"].endswith("/tt0000001/img")
    )
    # A fresh index is left alone; a missing one starts one background build.
    assert film_index.refresh() == 0
    # A recent index with a build still unfinished (partial file) carries on building.
    partial.write_text(json.dumps({"started": time.time(), "done": [], "index": {}, "names": {}}))
    monkeypatch.setattr(
        film_index.threading,
        "Thread",
        lambda **kw: type("T", (), {"start": lambda self: None, "is_alive": lambda self: False})(),
    )
    film_index.state.update(thread=None, retry_at=0)
    assert film_index.refresh() == 1
    partial.unlink()
    # A build that got fewer answers never replaces a bigger index in use.
    final.unlink()
    monkeypatch.setattr(film_index, "previous_size", lambda: 1000)
    assert film_index.build() == 1 and not final.exists()


def test_recommended_for_you_follows_the_last_titles_watched(catalogue):
    picks = cinema_explore.for_you("movie", ["tt0000003", "tt0000012"])
    ids = [item["canonical_id"] for item in picks]
    assert ids and "tt0000003" not in ids and "tt0000012" not in ids
    assert picks[0]["director"] == ["Ada Director"]  # most like the latest one first
    assert cinema_explore.for_you("movie", []) == []


def test_a_saved_film_plays_in_the_browser_only_when_its_formats_do(domain, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from houseos import files, playback
    from houseos.models import Record

    db, (alice, _, _) = domain
    film = tmp_path / "film.mkv"
    film.write_bytes(b"\x1aE\xdf\xa3" + b"0" * 4096)
    row = Record(kind="cinema.local_media", owner_id=alice.id, visibility="house",
                 data={"state": "ready", "title": "Fixture", "_path": str(film)})  # fmt: skip
    db.add(row)
    db.flush()
    probes = []

    def probe(path, timeout=20):
        probes.append(path)
        return {"video": {"codec": "hevc"}, "audio": [{"codec": "ac3"}]}

    monkeypatch.setattr(playback, "probe_file", probe)
    try:
        answer = files.film_in_browser(row.id, alice, db)
        assert not answer["playable"] and answer["reason"] and answer["stream"] is None
        files.film_in_browser(row.id, alice, db)
        assert len(probes) == 1  # checked once, then remembered
        row.data = {**row.data, "_browser": None}
        db.flush()
        monkeypatch.setattr(
            playback,
            "probe_file",
            lambda p, timeout=20: {"video": {"codec": "h264"}, "audio": [{"codec": "aac"}]},
        )
        row.data = {k: v for k, v in row.data.items() if k != "_browser"}
        db.flush()
        assert files.film_in_browser(row.id, alice, db)["playable"]
        request = SimpleNamespace(headers={"range": "bytes=0-99"}, method="GET")
        response = files.film_stream(row.id, request, alice, db)
        assert response.status_code == 206 and response.media_type == "video/x-matroska"
    finally:
        db.rollback()


def test_a_fresh_install_filters_from_the_bundled_index_at_once(monkeypatch, tmp_path):
    monkeypatch.setattr(cinema_explore.settings, "runtime_root", tmp_path)  # nothing built yet
    cinema_explore._films.cache_clear()
    assert cinema_explore.film_source() == cinema_explore.BUNDLED
    films = cinema_explore.films()
    assert len(films) > 20000 and any("zombies" in f["tags"] for f in films)
    cinema_explore._films.cache_clear()


def test_backfill_asks_again_for_people_a_failing_service_left_out(monkeypatch):
    from houseos import film_index

    work = {"index": {"Q1": {"t": "Memento", "d": [], "c": ["Guy Pearce"]}}, "names": {}}
    answers = {
        "?s WHERE": [
            {"f": "Q1", "p": "P57", "v": "Q9", "s": "90"},
            {"f": "Q1", "p": "P161", "v": "Q8", "s": "5"},
        ],
        "?name": [{"v": "Q9", "name": "Christopher Nolan"}, {"v": "Q8", "name": "Guy Pearce"}],
    }
    monkeypatch.setattr(
        film_index, "sparql", lambda q, at_least=0: next(r for k, r in answers.items() if k in q)
    )
    film_index.backfill(work)
    assert work["index"]["Q1"]["d"] == ["Christopher Nolan"] and work["index"]["Q1"]["c"] == ["Guy Pearce"]


def test_a_failed_query_names_each_service_and_its_answer(monkeypatch):
    import urllib.error

    from houseos import film_index

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(film_index.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(film_index.time, "sleep", lambda s: None)
    with pytest.raises(ConnectionError) as failed:
        film_index.sparql("SELECT * WHERE {}")
    assert "query.wikidata.org: 429" in str(failed.value) and "qlever.dev: 429" in str(failed.value)
