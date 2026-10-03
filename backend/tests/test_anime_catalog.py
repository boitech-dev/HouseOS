import unittest
from unittest.mock import patch

from houseos.anime_catalog import AnimeCatalog, resolve_stream, _mappings, _jikan
from houseos.playback import MediaError


class AnimeCatalogTests(unittest.TestCase):
    def test_identity_poster_pagination_and_separate_season(self):
        raw = {
            "mal_id": 5114,
            "title": "Fullmetal Alchemist: Brotherhood",
            "type": "TV",
            "episodes": 64,
            "score": 9.1,
            "images": {"jpg": {"image_url": "https://cdn.myanimelist.net/anime/test.jpg"}},
            "genres": [{"name": "Adventure"}],
        }
        with patch.object(
            AnimeCatalog, "get", return_value={"data": [raw, raw], "pagination": {"has_next_page": True}}
        ) as get:
            result = AnimeCatalog().browse(offset=24)
            self.assertEqual(result["next_offset"], 48)
            self.assertEqual(len(result["items"]), 1)
            self.assertIn("page=2", get.call_args.args[0])
            self.assertEqual(result["items"][0]["canonical_id"], "mal:5114")
            self.assertIn("myanimelist", result["items"][0]["_poster_url"])
        with patch.object(AnimeCatalog, "get", return_value={"data": raw}):
            detail = AnimeCatalog().details("mal:5114")
            self.assertEqual(len(detail["episodes"]), 64)
            self.assertEqual(detail["episodes"][-1]["episode"], 64)
            self.assertEqual(detail["episodes"][-1]["season"], 1)
        with patch("houseos.anime_catalog._mappings", return_value={5114: {3936}}):
            self.assertEqual(resolve_stream("mal:5114", 4), "kitsu:3936:4")
            self.assertEqual(resolve_stream("mal:5114"), "kitsu:3936")
            with self.assertRaises(MediaError):
                resolve_stream("mal:5114", 0)
        with patch("houseos.anime_catalog._mappings", return_value={5114: {1, 2}}):
            with self.assertRaisesRegex(MediaError, "ANIME_MAPPING_MISSING"):
                resolve_stream("mal:5114", 4)

    def test_airing_episode_evidence_and_provider_failure(self):
        raw = {"mal_id": 1, "title": "Show", "type": "TV", "episodes": None}
        with patch.object(
            AnimeCatalog, "get", side_effect=[{"data": raw}, {"data": [{"mal_id": 1, "title": "Pilot"}]}]
        ):
            self.assertEqual(
                AnimeCatalog().details("mal:1")["episodes"],
                [{"id": "mal:1:1", "season": 1, "episode": 1, "title": "Pilot"}],
            )
        _jikan.cache_clear()
        with (
            patch("houseos.anime_catalog.httpx.stream", side_effect=MediaError("SOURCE_NOT_READY", "No")),
            patch("houseos.anime_catalog.time.sleep"),
        ):
            with self.assertRaisesRegex(MediaError, "ANIME_CATALOG_UNAVAILABLE"):
                _jikan("/anime", 1)
        _mappings.cache_clear()
        with patch("houseos.anime_catalog.public_fetch", return_value=(b"{}", {})):
            with self.assertRaisesRegex(MediaError, "ANIME_MAPPING_UNAVAILABLE"):
                _mappings(1)

    def test_backup_dataset_local_search_genre_and_cache(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from houseos import anime_offline

        data = {
            "data": [
                {
                    "sources": ["https://myanimelist.net/anime/1"],
                    "title": "Cowboy Bebop",
                    "type": "TV",
                    "episodes": 26,
                    "picture": "https://cdn.myanimelist.net/test.jpg",
                    "animeSeason": {"year": 1998},
                    "synonyms": ["Bebop"],
                    "tags": ["action"],
                    "status": "FINISHED",
                    "score": {"arithmeticMean": 8.9},
                }
            ]
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(anime_offline, "settings", SimpleNamespace(runtime_root=Path(directory))),
            patch.object(
                anime_offline, "public_fetch", return_value=(json.dumps(data).encode(), {})
            ) as fetch,
        ):
            anime_offline._retry_at = 0.0
            # A request never downloads: before the maintenance step has, it says so.
            with self.assertRaises(anime_offline.MediaError):
                anime_offline.catalog_response("/anime?q=Bebop")
            anime_offline.refresh()  # the daily maintenance step
            anime_offline.refresh()  # fresh file: no second download, nothing parsed
            result = anime_offline.catalog_response("/anime?q=Bebop&genres=1")
            self.assertEqual(result["data"][0]["mal_id"], 1)
            self.assertEqual(anime_offline.catalog_response("/anime/1")["data"]["episodes"], 26)
            self.assertEqual(len(anime_offline.catalog_response("/anime")["data"]), 1)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(list(Path(directory).rglob("*.tmp")), [])


def test_default_is_official_mal_order_and_outage_never_changes_ranking():
    raw = [
        {"mal_id": 52991, "title": "Frieren", "rank": 1},
        {"mal_id": 5114, "title": "Brotherhood", "rank": 2},
    ]
    with patch.object(AnimeCatalog, "get", return_value={"data": raw}) as get:
        rows = AnimeCatalog().browse()["items"]
        assert get.call_args.args[0].startswith("/top/anime?")
        assert [r["canonical_id"] for r in rows] == ["mal:52991", "mal:5114"]
    with (
        patch("houseos.anime_catalog._jikan", side_effect=MediaError("UNAVAILABLE", "Busy", "identify")),
        patch("houseos.anime_offline.catalog_response") as backup,
    ):
        try:
            AnimeCatalog().browse()
            assert False, "Must not mislabel backup scores as the MAL ranking"
        except MediaError:
            pass
        backup.assert_not_called()


def test_an_outage_fails_fast_for_every_request_instead_of_queueing(monkeypatch):
    import time

    import httpx
    import pytest

    from houseos import anime_catalog
    from houseos.playback import MediaError

    calls = []

    def down(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectTimeout("down")

    monkeypatch.setattr(anime_catalog.httpx, "stream", down)
    monkeypatch.setattr(anime_catalog, "_retry_after", {})
    monkeypatch.setattr(anime_catalog, "_next_request", 0.0)
    anime_catalog._jikan.cache_clear()
    for path in ("/anime/1", "/anime/2/recommendations", "/top/anime?page=1"):
        started = time.monotonic()
        with pytest.raises(MediaError):
            anime_catalog._jikan(path, 1)
        assert time.monotonic() - started < 1
    assert len(calls) == 1  # one real attempt; everything after fails at once for 5 minutes
    anime_catalog._jikan.cache_clear()
