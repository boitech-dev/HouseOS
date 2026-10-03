"""Catalog fixtures prove filtering/cache/pagination; live network evidence is documented separately."""

from unittest.mock import patch
import pytest
from houseos.cinema_adapters import Cinemeta, cinemeta_json
from houseos.playback import MediaError
import test_cinema


@pytest.fixture
def cinema_client():
    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    yield fixture.client
    fixture.tearDown()


def test_catalog_cache_filter_and_bounded_page():
    cinemeta_json.cache_clear()
    manifest = {"catalogs": [{"id": "top", "type": "movie", "name": "Popular", "genres": ["Animation"]}]}
    raw = {
        "metas": [
            {
                "id": f"tt{i:07d}",
                "type": "movie",
                "name": f"Movie {i}",
                "genres": ["Animation"],
                "poster": "https://example.com/poster.jpg",
            }
            for i in range(50)
        ]
    }
    with patch("houseos.cinema_adapters.public_json", side_effect=[manifest, raw]) as fetch:
        first = Cinemeta().browse("movie", "top", "Animation", 24)
        assert len(first["items"]) == 24 and first["next_offset"] == 48
        assert Cinemeta().browse("movie", "top", "Animation", 24) == first
        assert fetch.call_count == 2
        assert fetch.call_args.args[0].endswith("/genre=Animation&skip=24.json")
        with pytest.raises(MediaError, match="CATALOG_FILTER_INVALID"):
            Cinemeta().browse("movie", "top", "unlisted", 0)
    cinemeta_json.cache_clear()


def test_browse_normalizes_ids_without_exposing_source_urls(cinema_client):
    data = {
        "items": [
            {
                "canonical_id": "tt7654321",
                "title": "Fixture title",
                "kind": "movie",
                "year": "2026",
                "genres": ["Drama"],
                "_poster_url": "https://example.com/poster.jpg",
            }
        ],
        "next_offset": 24,
    }
    with patch("houseos.cinema.Cinemeta.browse", return_value=data):
        result = cinema_client.get("/api/v1/cinema/browse?genre=Drama")
        assert result.status_code == 200
        row = result.json()["items"][0]
        assert row["id"] and row["poster"].startswith("/api/v1/cinema/titles/")
        assert "_poster_url" not in row and row["genres"] == ["Drama"]
        assert result.json()["availability"] == "sources_require_validation"
        assert cinema_client.get("/api/v1/cinema/browse?offset=-1").status_code == 422
        assert cinema_client.get("/api/v1/cinema/browse?catalog=arbitrary").status_code == 422


def test_public_images_are_kept_on_disk_and_a_failure_is_not_retried_at_once(tmp_path, monkeypatch):
    from houseos import cinema
    from houseos.playback import MediaError

    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    with (
        patch("houseos.cinema.public_fetch", return_value=(b"fixture-image", {})) as fetch,
        patch("houseos.cinema.poster_jpeg", return_value=b"safe-jpeg"),
    ):
        assert cinema.cached_public_poster("https://example.com/poster.jpg") == b"safe-jpeg"
        assert cinema.cached_public_poster("https://example.com/poster.jpg") == b"safe-jpeg"
        assert fetch.call_count == 1 and cinema.image_on_disk("https://example.com/poster.jpg")
    failing = MediaError("PROVIDER_UNAVAILABLE", "down", "resolve", True)
    with patch("houseos.cinema.public_fetch", side_effect=failing) as fetch:
        for _ in range(2):
            with pytest.raises(MediaError):
                cinema.cached_public_poster("https://example.com/gone.jpg")
        assert fetch.call_count == 1  # remembered as missing for a while


def test_public_addresses_prefer_ipv4(monkeypatch):
    from houseos import cinema_adapters

    answers = [(0, 0, 0, "", ("2a03:90c0::1", 443)), (0, 0, 0, "", ("92.223.84.84", 443))]
    monkeypatch.setattr(cinema_adapters.socket, "getaddrinfo", lambda *a, **k: answers)
    assert cinema_adapters.public_url("https://images.example/x")[1] == "92.223.84.84"


def test_human_genre_normalization():
    metadata = {"metas": []}
    with (
        patch.object(Cinemeta, "catalogs", return_value=[{"id": "top", "genres": ["Sci-Fi", "Animation"]}]),
        patch.object(Cinemeta, "get", return_value=metadata) as fetch,
    ):
        Cinemeta().browse("movie", "top", "science fiction", 0)
        assert "genre=Sci-Fi" in fetch.call_args.args[0]
        Cinemeta().browse("movie", "top", "SCI-FI", 0)
        assert "genre=Sci-Fi" in fetch.call_args.args[0]


def test_an_unwritable_image_cache_still_serves_the_image(tmp_path, monkeypatch):
    from houseos import cinema

    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)  # like Docker's /state: the service cannot create folders there
    monkeypatch.setattr(cinema.settings, "runtime_root", locked)
    with (
        patch("houseos.cinema.public_fetch", return_value=(b"fixture-image", {})),
        patch("houseos.cinema.poster_jpeg", return_value=b"safe-jpeg"),
    ):
        assert cinema.cached_public_poster("https://example.com/p.jpg") == b"safe-jpeg"
