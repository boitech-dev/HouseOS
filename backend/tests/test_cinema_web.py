"""Watch → Web (D32): a pasted link is read, downloaded once, played, and its file deleted later."""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from houseos import cinema_web, fetcher_web
from houseos.cinema import CinemaDevice, CinemaWorkflow
from houseos.db import new_id, utcnow
from houseos.models import Record
from test_core import admin


@pytest.mark.parametrize(
    "shared, link",
    [
        ("Look at this! https://youtu.be/abcdefghijk?si=xyz.", "https://youtu.be/abcdefghijk?si=xyz"),
        ("youtu.be/abcdefghijk", "https://youtu.be/abcdefghijk"),
        ("(www.example.org/video/1)", "https://www.example.org/video/1"),
        ("http://example.org/clip.mp4", "http://example.org/clip.mp4"),
    ],
)
def test_the_link_is_found_in_what_was_shared(shared, link):
    assert cinema_web.find_link(shared) == link


def test_no_link_is_refused_in_words():
    with pytest.raises(HTTPException) as refused:
        cinema_web.find_link("just some words")
    assert refused.value.detail["code"] == "WEB_VIDEO_LINK_INVALID"


def test_a_pasted_link_downloads_once_plays_and_its_file_goes_later(client, tmp_path, monkeypatch):
    c, db = client
    admin(client)
    monkeypatch.setattr(cinema_web, "DIR", tmp_path)
    monkeypatch.setattr(fetcher_web, "DIR", tmp_path)
    tv = CinemaDevice(id=new_id(), name="Living-room TV", adapter="cast", address="192.0.2.5")
    db.add(tv)
    db.commit()
    calls, launched = [], []

    def fake_fetch(action, row, **extra):
        calls.append(action)
        if action == "web_info":
            return {"status": "completed", "title": "A cat", "site": "Youtube", "duration": 61, "bytes": 5,
                    "thumbnail": "https://i.ytimg.com/x.jpg"}  # fmt: skip
        if action == "web_video":
            (tmp_path / (row.id + ".mp4")).write_bytes(b"video")
            return {"status": "completed", "file": row.id + ".mp4", "bytes": 5}
        for path in tmp_path.glob(row.id + ".*"):
            path.unlink()
        return {"status": "completed"}

    monkeypatch.setattr(cinema_web, "fetch", fake_fetch)
    monkeypatch.setattr(cinema_web, "probe_file", lambda path, timeout: {"container": "mov,mp4"})
    monkeypatch.setattr(
        cinema_web,
        "launch",
        lambda identity, body, actor, db: launched.append(body.device_id) or {"state": "command_sent"},
    )
    shared = {"text": "Look at this! youtu.be/abcdefghijk?si=xyz.", "device_id": tv.id}
    added = c.post("/api/v1/cinema/web", json=shared).json()
    assert (added["url"], added["state"]) == ("https://youtu.be/abcdefghijk?si=xyz", "queued")
    assert cinema_web.process_one_web(db) and not cinema_web.process_one_web(db)
    item = c.get("/api/v1/cinema/web").json()["items"][0]
    assert (item["state"], item["kept"], item["title"]) == ("ready", True, "A cat")
    assert item["poster"] and calls == ["web_info", "web_video"] and launched == [tv.id]
    # The same link again: the same card, played from the file already here.
    assert c.post("/api/v1/cinema/web", json=shared).json()["id"] == added["id"]
    assert cinema_web.process_one_web(db)
    assert calls == ["web_info", "web_video"] and launched == [tv.id, tv.id]
    # Still on the TV, it stays; stopped and six hours on, the file goes and the card stays.
    row = db.get(Record, added["id"])
    row.data = {**row.data, "played_at": (utcnow() - timedelta(hours=7)).isoformat()}
    flow = db.get(CinemaWorkflow, row.data["workflow_id"])
    tv.owner_workflow = flow.id  # it holds the TV
    db.commit()
    assert cinema_web.prune_web_videos(db) == 0 and cinema_web.on_screen(db, row)
    # A play that never got the TV (refused, never confirmed) is not on it: it can go.
    tv.owner_workflow = None
    db.commit()
    assert not cinema_web.on_screen(db, row)
    flow.state = "stopped"
    db.commit()
    assert cinema_web.prune_web_videos(db) == 1
    item = c.get("/api/v1/cinema/web").json()["items"][0]
    assert not item["kept"] and item["state"] == "ready" and not list(tmp_path.iterdir())


def test_a_link_that_cannot_play_says_why(client, tmp_path, monkeypatch):
    c, db = client
    admin(client)
    monkeypatch.setattr(cinema_web, "DIR", tmp_path)
    tv = CinemaDevice(id=new_id(), name="Living-room TV", adapter="cast", address="192.0.2.5")
    db.add(tv)
    db.commit()
    monkeypatch.setattr(
        cinema_web, "fetch", lambda action, row, **extra: {"status": "failed", "code": "WEB_VIDEO_LIVE"}
    )
    c.post("/api/v1/cinema/web", json={"text": "https://www.twitch.tv/someone", "device_id": tv.id})
    assert cinema_web.process_one_web(db)
    item = c.get("/api/v1/cinema/web").json()["items"][0]
    assert (item["state"], item["error"]) == ("failed", "WEB_VIDEO_LIVE")


def test_the_fetcher_names_web_video_failures():
    from houseos.fetcher import failure_code

    assert failure_code("ERROR: [generic] Unsupported URL: https://x") == "WEB_VIDEO_UNSUPPORTED"
    assert failure_code("ERROR: This video is DRM protected") == "WEB_VIDEO_DRM"
    assert failure_code("ERROR: [instagram] x: Requested content is not available, login required") == (
        "WEB_VIDEO_SIGN_IN"
    )


def test_a_streamable_link_plays_from_its_first_pieces(client, tmp_path, monkeypatch):
    c, db = client
    admin(client)
    monkeypatch.setattr(cinema_web, "DIR", tmp_path)
    monkeypatch.setattr(fetcher_web, "DIR", tmp_path)
    tv = CinemaDevice(id=new_id(), name="Living-room TV", adapter="cast", address="192.0.2.5")
    db.add(tv)
    db.commit()
    prepared = []

    def fake_fetch(action, row, **extra):
        if action == "web_info":
            return {"status": "completed", "title": "Bunny", "duration": 635, "bytes": 9, "streamable": True}
        folder = tmp_path / row.id  # what fetcher_web.stream leaves: HLS pieces, finished
        folder.mkdir()
        (folder / "init.mp4").write_bytes(b"i")
        (folder / "video0.m4s").write_bytes(b"v")
        (folder / "av_master.m3u8").write_text(
            '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,CODECS="avc1.64002a,mp4a.40.2"\nvideo.m3u8\n'
        )
        (folder / "video.m3u8").write_text(
            '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4,\nvideo0.m4s\n#EXT-X-ENDLIST\n'
        )
        return {"status": "completed", "stream": row.id, "bytes": 2}

    monkeypatch.setattr(cinema_web, "fetch", fake_fetch)
    monkeypatch.setattr(
        cinema_web, "probe_file", lambda path, timeout: {"container": "mov,mp4", "duration": 4}
    )

    def fake_launch(identity, body, actor, db):
        prepared.append(db.get(CinemaWorkflow, identity).data["_prepared"])
        return {"state": "command_sent"}

    monkeypatch.setattr(cinema_web, "launch", fake_launch)
    c.post("/api/v1/cinema/web", json={"text": "https://youtu.be/abcdefghijk", "device_id": tv.id})
    assert cinema_web.process_one_web(db)
    assert prepared[0]["streaming"] and prepared[0]["web"] and prepared[0]["path"].endswith("master.m3u8")
    item = c.get("/api/v1/cinema/web").json()["items"][0]
    assert (item["state"], item["kept"]) == ("ready", True) and item["delete_at"]
    row = db.get(Record, item["id"])
    assert row.data["inspection"]["duration"] == 635  # the whole length, not the first piece's
