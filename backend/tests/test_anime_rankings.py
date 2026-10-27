"""Anime rankings: Kitsu's order, as MyAnimeList ids, shown in that order over the local list."""

from datetime import date

from houseos import anime_rankings, cinema_explore


def test_kitsu_answers_become_mal_ids_in_kitsu_order():
    answer = {
        "data": [
            {"id": "2", "relationships": {"mappings": {"data": [{"id": "m3"}, {"id": "m2"}]}}},
            {"id": "1", "relationships": {"mappings": {"data": [{"id": "m1"}]}}},
            {"id": "9", "relationships": {"mappings": {"data": [{"id": "m9"}]}}},  # no MAL id: left out
        ],
        "included": [
            {"type": "mappings", "id": "m3", "attributes": {"externalSite": "anidb", "externalId": "5"}},
            {"type": "mappings", "id": "m2", "attributes": {"externalSite": "myanimelist/anime", "externalId": "20"}},
            {"type": "mappings", "id": "m1", "attributes": {"externalSite": "myanimelist/anime", "externalId": "10"}},
            {"type": "mappings", "id": "m9", "attributes": {"externalSite": "thetvdb", "externalId": "7"}},
        ],
    }  # fmt: skip
    assert anime_rankings.mal_ids(answer) == [20, 10]
    assert anime_rankings.season_filter(date(2026, 10, 27)) == {
        "filter[season]": "fall",
        "filter[seasonYear]": 2026,
    }


def test_a_ranking_keeps_its_order_and_combines_with_other_filters(monkeypatch):
    rows = [
        {"canonical_id": f"mal:{n}", "title": str(n), "year": 2020, "genres": [], "tags": tags, "known": known}
        for n, tags, known in ((1, ["shounen"], 99), (2, [], 50), (3, ["shounen"], 10))
    ]  # fmt: skip
    monkeypatch.setattr(cinema_explore, "index", lambda kind: rows)
    monkeypatch.setattr(anime_rankings, "saved", lambda: {"popular": [3, 2, 7]})
    found = cinema_explore.matching("anime", ranking="popular")
    assert [r["canonical_id"] for r in found] == ["mal:3", "mal:2"]  # Kitsu's order, not "known"
    assert [
        r["canonical_id"] for r in cinema_explore.matching("anime", ranking="popular", tag="shounen")
    ] == ["mal:3"]
    assert cinema_explore.discover("anime", ranking="rated")["items"] == []  # not downloaded yet: empty


def test_the_anime_id_map_is_kept_and_used_when_its_download_fails(monkeypatch, tmp_path):
    import json

    import pytest

    from houseos import anime_catalog
    from houseos.config import settings
    from houseos.playback import MediaError

    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    answer = json.dumps([{"mal_id": 1, "kitsu_id": 2}, {"mal_id": 3}]).encode()
    monkeypatch.setattr(anime_catalog, "public_fetch", lambda url, limit: (answer, {}))
    assert anime_catalog._mappings.__wrapped__(1) == {1: {2}}

    def down(url, limit):
        raise MediaError("PROVIDER_UNAVAILABLE", "down", "resolve")

    monkeypatch.setattr(anime_catalog, "public_fetch", down)
    assert anime_catalog._mappings.__wrapped__(2) == {1: {2}}  # yesterday's copy
    (tmp_path / "cinema/catalog-cache/anime-kitsu-map.json").unlink()
    with pytest.raises(MediaError):
        anime_catalog._mappings.__wrapped__(3)
