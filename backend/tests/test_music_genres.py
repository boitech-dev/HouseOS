"""Song genres without a model: keywords, the house's own genres, Deezer's catalogue (faked),
the maintenance catch-up with artwork, and stats by time listened (radio included)."""

import httpx
import pytest

from houseos import music as m, music_catalog, music_genre, radio, stats
from houseos.models import Integration, Record
from houseos.music_genre import artist_and_track, deezer, genre_of, same
from test_house_features import played, song


def test_families_house_genres_and_names():
    assert genre_of({"title": "Jujutsu Kaisen - Opening 2 | Full"}) == "anime"
    assert genre_of({"genres": ["Rap/Hip Hop", "French Rap"]}) == "rap / hip-hop"
    assert genre_of({"genres": ["Films/Games"]}) == "soundtrack"
    assert genre_of({"genres": ["Dance"]}) == "electro"
    assert genre_of({"tags": ["jazz", "lounge"]}) == "jazz"
    house = [{"name": "Anime songs", "words": ["aimer", "lisa"]}]
    assert genre_of({"title": "Aimer - Zankyosanka"}, house) == "Anime songs"
    assert genre_of({"title": "Aimer - Zankyosanka"}) == "other"
    assert artist_and_track("La Femme - Pasadena (Official Audio)") == ("La Femme", "Pasadena")
    assert artist_and_track("Séquelles", "So La Lune - Topic") == ("So La Lune", "Séquelles")
    assert artist_and_track("Maladresse [Clip Officiel] ft. X", "", "Laylow") == ("Laylow", "Maladresse")
    assert same("LAYLOW", "Laylow") and not same("Pacifique", "So La Lune")


def fake_deezer(tracks, calls=None):
    def handle(request):
        (calls if calls is not None else []).append(str(request.url))
        if request.url.path == "/search":
            return httpx.Response(200, json={"data": tracks})
        return httpx.Response(
            200, json={"genres": {"data": [{"name": "Rap/Hip Hop"}, {"name": "French Rap"}]}}
        )

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_deezer_only_trusts_the_same_artist_and_track():
    hit = {
        "title": "Séquelles",
        "artist": {"name": "So La Lune"},
        "album": {"id": 7, "cover_medium": "https://e-cdns-images.dzcdn.net/images/cover/1/250x250.jpg"},
    }
    calls = []
    found = deezer("Séquelles", "So La Lune - Topic", client=fake_deezer([hit], calls))
    assert found["genres"] == ["Rap/Hip Hop", "French Rap"] and found["cover"].endswith("250x250.jpg")
    assert 'artist:"So La Lune"' in httpx.URL(calls[0]).params["q"]
    wrong = {**hit, "artist": {"name": "MC Solaar"}}
    assert deezer("Séquelles", "So La Lune - Topic", client=fake_deezer([wrong])) == {}
    # "Title - Artist" exists too; the channel's artist counts when the title names none.
    reversed_ = {**hit, "title": "KUN FU", "artist": {"name": "Nathy Peluso"}}
    assert deezer("KUN FU - Nathy Peluso (Prod. X)", "NATHY PELUSO", client=fake_deezer([reversed_]))
    eminem = {**hit, "title": "Superman", "artist": {"name": "Eminem"}}
    assert deezer("Superman", "EminemMusic", client=fake_deezer([eminem]))


@pytest.fixture
def catalog(music_domain, monkeypatch):
    monkeypatch.setitem(music_catalog.state, "idle_until", 0.0)
    monkeypatch.setattr(radio, "resolve", lambda identity: {"tags": "jazz,lounge"})
    return music_domain


def test_catch_up_finds_genres_artwork_and_keeps_the_guess_on_errors(catalog, monkeypatch):
    db, (alice, _, _), _ = catalog
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    item = played(db, alice, url, genre="other")
    item.title = "LAYLOW - MALADRESSE (Clip officiel)"
    db.commit()
    key = m.history_key(url)
    monkeypatch.setattr(music_catalog, "deezer", lambda *a: (_ for _ in ()).throw(httpx.ConnectError("down")))
    music_catalog.enrich(db, limit=10000)
    row = db.get(Record, key)
    db.refresh(row)
    assert row.data["genre"] == "other" and row.data["evidence"]["retry_at"]  # tried again later
    row.data = {**row.data, "evidence": {}}
    db.commit()
    monkeypatch.setitem(music_catalog.state, "idle_until", 0.0)
    monkeypatch.setattr(music_catalog, "deezer", lambda *a: {"genres": ["Rap/Hip Hop"], "cover": None})
    music_catalog.enrich(db, limit=10000)
    db.refresh(row)
    assert row.data["genre"] == "rap / hip-hop" and row.data["evidence"]["checked_at"]
    db.refresh(item)
    assert item.metadata_json["thumbnail"] == "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
    # Played again: the genre worked out stays.
    item.metadata_json = {**item.metadata_json, "history_recorded": False}
    m.record_played(db, item, {"status": "observed", "item_id": item.id, "idle": False, "paused": False})
    db.commit()
    db.refresh(row)
    assert row.data["genre"] == "rap / hip-hop" and row.data["evidence"]["genres"] == ["Rap/Hip Hop"]


def test_radio_hours_count_under_the_stations_genre_and_house_genres_apply_later(catalog):
    db, (alice, _, _), _ = catalog
    station = "radio:" + "5a3e2a4b-0000-4000-8000-00000000abcd"
    item = m.QueueItem(
        owner_id=alice.id,
        source_url=station,
        title="FIP Jazz",
        position=0,
        status="playing",
        metadata_json={"is_live": True, "genre": "other"},
    )
    db.add(item)
    db.flush()
    m.record_played(db, item, {"status": "observed", "item_id": item.id, "idle": False, "paused": False})
    item.metadata_json = {**item.metadata_json, "last_position": 5400}  # 1 h 30 on air
    tune = played(db, alice, song(), genre="other")
    tune.title = "Frieren - Opening"
    db.commit()
    music_catalog.enrich(db, limit=10000)
    stats.CACHE["data"] = None
    genres = {g["name"]: g for g in stats.compute(db)["music"]["genres"]}
    assert genres["jazz"]["seconds"] >= 5400  # the station's time, under its tags' genre
    row = db.get(Integration, "house_settings") or Integration(name="house_settings", config={})
    before = dict(row.config or {})
    row.config = {**before, "music_genres": [{"name": "Lounge nights", "words": ["lounge"]}]}
    db.merge(row)
    db.commit()
    try:
        genres = {g["name"] for g in stats.compute(db)["music"]["genres"]}
        assert "Lounge nights" in genres and "anime" in genres  # no new lookup needed
    finally:
        row = db.get(Integration, "house_settings")
        row.config = before
        db.commit()


def test_film_stats_split_films_series_and_anime(music_domain):
    from zoneinfo import ZoneInfo

    from houseos.cinema_models import CinemaState, CinemaTitle
    from houseos.db import new_id, utcnow

    db, (alice, _, _), _ = music_domain
    for canonical, kind, genres in (
        ("tt" + new_id()[:7], "movie", ["Drama"]),
        ("mal:" + new_id()[:6], "series", ["Action"]),
    ):
        title = CinemaTitle(canonical_id=canonical, title=canonical, kind=kind, data={"genres": genres})
        db.add(title)
        db.flush()
        db.add(
            CinemaState(
                owner_id=alice.id,
                media_id=title.id,
                data={"watched": True, "duration": 3600},
                last_watched_at=utcnow(),
            )
        )
    db.flush()
    try:
        films = stats.movies(db, ZoneInfo("UTC"))
        assert set(films) == {"month", "ever"}
        month = films["month"]
        assert month["kinds"]["film"] >= 1 and month["kinds"]["anime"] >= 1 and month["finished"] >= 1
        assert {g["name"] for g in month["genres"]} >= {"Drama", "Action"}
    finally:
        db.rollback()


def test_the_music_genre_module_checks_itself():
    import runpy

    runpy.run_module(music_genre.__name__, run_name="__main__")


def test_kept_songs_never_played_get_a_genre_and_the_button_looks_again(catalog, monkeypatch):
    from houseos import music_auto

    db, (alice, _, _), _ = catalog
    url = "https://www.youtube.com/watch?v=keptneverpl"
    db.add(Record(kind="music.download", owner_id=alice.id,
                  data={"state": "ready", "source_url": url, "title": "Sous le vent", "uploader": "Garou - Topic"}))  # fmt: skip
    db.commit()
    monkeypatch.setattr(music_catalog, "deezer", lambda *a: {})  # Deezer knows nothing yet
    music_catalog.enrich(db, limit=10000)
    assert dict((u, g) for u, _, g in music_auto.kept_songs(db))[url] == "other"
    # The button: every "other" song is looked at once more, even while the routine naps.
    assert music_catalog.sort_again(db) >= 1
    db.commit()
    assert music_catalog.sort_requested(db)
    monkeypatch.setitem(music_catalog.state, "idle_until", float("inf"))
    monkeypatch.setattr(
        music_catalog, "deezer", lambda *a: {"genres": ["Chanson française"], "by_artist": True}
    )
    music_catalog.enrich(db, limit=10000)
    assert dict((u, g) for u, _, g in music_auto.kept_songs(db))[url] == "chanson"
    music_catalog.enrich(db, limit=10000)  # nothing left: the request is done
    assert not music_catalog.sort_requested(db)


def test_deezer_falls_back_to_the_artists_genre():
    hit = {"title": "Another song", "artist": {"name": "Garou"}, "album": {"id": 9}}
    found = deezer("Sous le vent (Live)", "Garou - Topic", client=fake_deezer([hit]))
    assert found["by_artist"] and found["genres"] == ["Rap/Hip Hop", "French Rap"] and found["cover"] is None


def test_deezer_decides_over_a_title_or_tag_guess_and_old_guesses_are_checked_again(catalog, monkeypatch):
    from houseos import music_auto

    db, (alice, _, _), _ = catalog
    swing = "https://www.youtube.com/watch?v=sultansswin"
    label = "https://www.youtube.com/watch?v=rosaliaplat"
    db.add(Record(kind="music.download", owner_id=alice.id,
                  data={"state": "ready", "source_url": swing, "title": "Mark Knopfler - Sultans Of Swing", "uploader": "Mark Knopfler"}))  # fmt: skip
    # Filed jazz by the old matcher from a record label's tag, Deezer never asked.
    db.add(Record(kind="music.download", owner_id=alice.id,
                  data={"state": "ready", "source_url": label, "title": "ROSALÍA - De Plata", "uploader": "ROSALÍA", "genre": "jazz",
                        "evidence": {"tags": ["Universal", "Classics", "Jazz"], "title": "ROSALÍA - De Plata", "checked_at": "2026-09-28T00:00:00Z", "matcher": 3}}))  # fmt: skip
    db.commit()
    asked = []
    monkeypatch.setattr(music_catalog, "deezer", lambda title, *a: asked.append(title) or {"genres": ["Pop"]})
    music_catalog.enrich(db, limit=10000)
    genres = dict((u, g) for u, _, g in music_auto.kept_songs(db))
    assert genres[swing] == "pop" and genres[label] == "pop"
    assert set(asked) >= {"Mark Knopfler - Sultans Of Swing", "ROSALÍA - De Plata"}
