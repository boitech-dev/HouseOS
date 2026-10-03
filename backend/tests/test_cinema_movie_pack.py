import pytest
from houseos import cinema_adapters as a
from houseos.playback import MediaError


def test_movie_pack_selects_actual_title_and_year_not_rd_id_or_position():
    files = [
        {"id": 561, "path": "/Other Movie (2008).mp4"},
        {"id": 900, "path": "/Vicky Cristina Barcelona (2008) 1080p (moviesbyrizzo upl).mp4"},
        {"id": 901, "path": "/Vicky Cristina Barcelona (2024).mkv"},
    ]
    assert a.exact_movie_file(files, "Vicky Cristina Barcelona", 2008)["id"] == 900
    with pytest.raises(MediaError):
        a.exact_movie_file(
            files + [{"id": 902, "path": "/Vicky.Cristina.Barcelona.2008.720p.mkv"}],
            "Vicky Cristina Barcelona",
            2008,
        )
    with pytest.raises(MediaError):
        a.exact_movie_file(files, "Barcelona", 2008)


def test_single_release_compatibility_and_pack_identity_safety():
    assert a.exact_movie_file([{"id": 1, "path": "/release.mkv"}], "Film", 2008)["id"] == 1
    files = [{"id": 1, "path": "/Film (2008) sample.mkv"}, {"id": 2, "path": "/Film (2009).mp4"}]
    with pytest.raises(MediaError):
        a.exact_movie_file(files, "Film", 2008)


def test_rd_block_identifies_failed_operation_without_guessing_reason():
    error = a.DebridError(35, 451, "unrestrict_link").public()
    assert "playable link" in error["message"]
    assert error["provider_code"] == 35 and error["operation"] == "unrestrict_link"
    assert "reason" in error["message"]


def test_cached_pack_uses_same_exact_file_mapping():
    from types import SimpleNamespace
    from houseos.cinema import exact_cached_file

    rd = SimpleNamespace(
        info=lambda _: {
            "status": "downloaded",
            "files": [
                {"id": 561, "path": "/Other (2008).mp4", "selected": 1},
                {"id": 900, "path": "/Vicky Cristina Barcelona (2008).mp4", "selected": 1},
            ],
            "links": ["other", "requested"],
        }
    )
    assert exact_cached_file(rd, "fixture", None, None, "Vicky Cristina Barcelona", 2008)
    assert not exact_cached_file(rd, "fixture", None, None, "Wrong movie", 2008)


def test_discovery_reports_the_provider_failure():
    from unittest.mock import patch

    error = MediaError("PROVIDER_UNAVAILABLE", "Unavailable", "discover", True)
    with patch.object(a.Comet, "manifest"), patch.object(a, "private_json", side_effect=error):
        with pytest.raises(MediaError):
            a.Comet({"enabled": True}).streams("tt123", "movie")
    raw = {"streams": [{"infoHash": "a" * 40, "title": "Film"}]}
    with patch.object(a.Comet, "manifest"), patch.object(a, "private_json", return_value=raw):
        assert len(a.Comet({"enabled": True}).streams("tt123", "movie")) == 1
