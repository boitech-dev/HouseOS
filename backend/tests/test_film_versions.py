"""Tonight's suggestion keeps looking past versions the TV cannot play, and a film saved on the
house disk is a version like any other (played through the relay, never re-downloaded)."""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

import test_cinema
from houseos import cinema
from houseos.cinema_models import CinemaWorkflow
from houseos.models import Record
from houseos.playback import MediaError


def release(identity, name, height):
    return {
        "id": identity,
        "info_hash": identity * 40,
        "release": name,
        "height_claim": height,
        "rd_cached": True,
        "layer": "ON_DEMAND",
        "state": "discovered",
    }


def test_a_round_the_tv_cannot_play_leads_to_the_next_versions(tmp_path, monkeypatch):
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    hdr = {**f.media, "video": {**f.media["video"], "hdr": "hdr10"}}  # the fixture screen is SDR only
    try:
        with Session(f.engine, expire_on_commit=False) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state = "preparing"
            row.data = {
                **row.data,
                "choice_set": {},
                "_suggestion": True,
                "_validation_selection": ["a", "b", "c"],
                "_sources": [release(x, "Film.2160p.HDR", 2160) for x in "abc"]
                + [release(x, "Film.1080p", 1080) for x in "def"],
            }
            db.commit()
            with (
                patch.object(cinema, "RealDebrid") as rd,
                patch(
                    "houseos.cinema_sources.probe_media",
                    side_effect=lambda url, _: hdr if url[-1] in "abc" else f.media,
                ),
            ):
                rd.return_value.inventory.return_value = []
                rd.return_value.add.side_effect = lambda info_hash, check=None: info_hash[0]
                rd.return_value.info.return_value = {
                    "status": "downloaded",
                    "files": [{"id": 1, "path": "/Film.mkv", "bytes": 1000}],
                }
                rd.return_value.resolve.side_effect = lambda torrent, *_, **__: (
                    "https://example.com/" + torrent,
                    1000,
                )
                result = cinema.validate_rd(db, row, ["a", "b", "c"])
            assert result["state"] == "awaiting_choice"
            assert result["choice_set"]["candidates"][0]["id"] in {"d", "e", "f"}
            assert result["suggestion_progress"]["round"] == 2
            assert result["suggestion_progress"]["total"] == 6
            assert result["suggestion_progress"]["setbacks"] == ["VIDEO_MODE_UNSUPPORTED"]
    finally:
        f.tearDown()


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(cinema.settings, "data_root", tmp_path)
    movies = tmp_path / "media" / "movies"
    movies.mkdir(parents=True)
    film = movies / "Film.mkv"
    film.write_bytes(b"0123456789")
    return film


def test_a_film_saved_on_the_house_disk_is_offered_and_streamed(saved, tmp_path):
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with Session(f.engine, expire_on_commit=False) as db:
            db.add(
                Record(
                    id="saved-one",
                    kind="cinema.local_media",
                    owner_id="resident-one",
                    visibility="house",
                    data={"state": "ready", "media_id": f.title_id, "_path": str(saved)},
                )
            )
            db.commit()
            title = db.get(cinema.CinemaTitle, f.title_id)
            with patch("houseos.playback.probe_file", return_value=f.media):
                (source,) = cinema.saved_sources(db, title)
            assert source["layer"] == "LOCAL" and source["size"] == 10
            from houseos.cinema_adapters import public_stream
            from houseos.cinema_sources import resolve_media

            url, size = resolve_media(db, source)
            assert url.startswith("local:") and size == 10
            status, headers, chunks = public_stream(url, "bytes=2-4")
            assert status == 206 and b"".join(chunks) == b"234"
            assert [c["media_id"] for c in f.client.get("/api/v1/cinema/shelves").json()["saved"]] == [
                f.title_id
            ]
            outside = tmp_path / "elsewhere.mkv"
            outside.write_bytes(b"x")
            with pytest.raises(MediaError):
                public_stream("local:" + str(outside))
    finally:
        f.tearDown()
