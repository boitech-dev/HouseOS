"""The torrent player: a stream add-on without a debrid service plays from TorrServer; debrid-cached
versions come first; nothing plays from torrents until an admin turns it on."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from houseos import cinema_adapters, cinema_sources
from houseos.config import settings
from houseos.playback import MediaError

FILM = b"\x00\x00\x00\x18ftypmp42" + bytes(2000)
HASH = "dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c"


class Engine(BaseHTTPRequestHandler):
    """TorrServer's /stream, as far as HouseOS uses it: files from 1, byte ranges."""

    def do_GET(self):
        assert self.path == f"/stream?link={HASH}&index=2&play", self.path
        start, end = 0, len(FILM) - 1
        if self.headers.get("Range"):
            first, last = self.headers["Range"].removeprefix("bytes=").split("-")
            start, end = int(first), int(last or end)
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {start}-{end}/{len(FILM)}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self.wfile.write(FILM[start : end + 1])

    def log_message(self, *_):
        pass


@pytest.fixture
def engine(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Engine)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "torrent_engine", f"http://127.0.0.1:{server.server_port}")
    yield
    server.shutdown()


def listing(rd_key=""):
    rd = {
        "name": "Add-on\n[RD+] 1080p",
        "title": "Film.1080p 👤 50",
        "url": f"https://addon.example/resolve/realdebrid/{rd_key}/{'a' * 40}/null/0/film.mkv",
    }
    plain = {"name": "Add-on\n720p", "title": "Film.720p 👤 12", "infoHash": HASH, "fileIdx": 1,
             "behaviorHints": {"filename": "Big Buck Bunny.mp4"}}  # fmt: skip
    nobody = {"name": "Add-on\n480p", "title": "Film.480p 👤 0", "infoHash": "b" * 40, "fileIdx": 0}
    return {"streams": ([rd] if rd_key else []) + [plain, nobody]}


def test_plain_addon_lists_torrents_only_with_the_player_on():
    manifest = "https://addon.example/qualityfilter=4k/manifest.json"
    with pytest.raises(MediaError):
        cinema_sources.configured_base({"manifest_url": manifest})
    assert cinema_sources.configured_base({"manifest_url": manifest, "torrent_player": True})[1] == ""
    assert cinema_sources.normalize_streams(listing(), "addon.example", "", p2p=False) == []
    found = cinema_sources.normalize_streams(listing(), "addon.example", "", p2p=True)
    assert [(s["info_hash"], s["file_index"], s["rd_cached"]) for s in found] == [
        (HASH, 1, False)
    ]  # 0 seeders out
    both = cinema_sources.normalize_streams(listing("KEY"), "addon.example", "KEY", p2p=True)
    assert [s["rd_cached"] for s in both] == [True, False]


def test_a_torrent_plays_through_the_house_stream(engine):
    status, headers, chunks = cinema_adapters.public_stream(f"torrent:{HASH}/1", "bytes=4-11")
    assert status == 206 and b"".join(chunks) == b"ftypmp42"
    source = {"provider": "stream_addon"}
    assert cinema_sources.torrent_resolve(source, HASH, 1) == (f"torrent:{HASH}/1", len(FILM))
    with pytest.raises(MediaError):
        cinema_adapters.public_stream("torrent:not-a-hash/1")
