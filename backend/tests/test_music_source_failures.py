import sys
import pytest
from houseos.fetcher import bounded_process


def test_youtube_challenge_is_not_reported_as_missing_song():
    with pytest.raises(ValueError, match="YOUTUBE_SIGN_IN_REQUIRED"):
        bounded_process(
            [
                sys.executable,
                "-c",
                "import sys;sys.stderr.write('[youtube] Sign in to confirm you are not a bot');sys.exit(1)",
            ],
            3,
        )


def test_replay_reuses_complete_audio_without_network(tmp_path, monkeypatch):
    from houseos import fetcher
    from uuid import uuid4

    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    old, new = str(uuid4()), str(uuid4())
    source = tmp_path / (old + ".media")
    source.write_bytes(b"cached audio")
    monkeypatch.setattr(
        fetcher, "bounded_process", lambda *a, **kw: pytest.fail("cache replay must not contact YouTube")
    )
    assert (
        fetcher.execute({"action": "reuse", "cached_item_id": old, "item_id": new})["status"] == "completed"
    )
    assert (tmp_path / (new + ".media")).read_bytes() == b"cached audio"
    assert fetcher.cached_audio_bytes() == len(b"cached audio")
    source.unlink()
    source.symlink_to(tmp_path / (new + ".media"))
    assert (
        fetcher.execute({"action": "reuse", "cached_item_id": old, "item_id": str(uuid4())})["status"]
        == "miss"
    )


def test_stderr_is_drained_without_leaking_provider_text():
    assert (
        bounded_process([sys.executable, "-c", "import sys;sys.stderr.write('secret'*50000);print('ok')"], 3)
        == b"ok\n"
    )
    with pytest.raises(ValueError, match="YOUTUBE_RATE_LIMITED"):
        bounded_process(
            [
                sys.executable,
                "-c",
                "import sys;sys.stderr.write('[youtube] HTTP Error 429: Too Many Requests');sys.exit(1)",
            ],
            3,
        )


def test_worker_uses_exact_original_link_for_cache_lookup(monkeypatch):
    from houseos import worker
    from contextlib import nullcontext
    from types import SimpleNamespace

    row = SimpleNamespace(
        id="cached-id", title="Song", metadata_json={"duration": 200, "history_recorded": True}
    )
    db = SimpleNamespace(scalars=lambda query: [row], get=lambda *args: None)
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr("houseos.music_downloads.restore", lambda *args: None)
    calls = []

    def fetch(action, **kwargs):
        calls.append((action, kwargs))
        return {"status": "completed", "bytes": 123}

    monkeypatch.setattr(worker, "fetch", fetch)
    result = worker.cached_music("https://www.youtube.com/watch?v=abcdefghijk", "new-id")
    assert result["title"] == "Song"
    assert calls == [("reuse", {"item_id": "new-id", "cached_item_id": "cached-id"})]
    assert worker.cached_music("houseos-file:private", "new-id") is None


def test_other_services_links_become_search_words_and_youtube_music_albums_import():
    from houseos.music import playlist_source, song_query

    spotify = song_query(
        "https://open.spotify.com/track/x", "Iris", "The Goo Goo Dolls · Dizzy Up · Song · 1998"
    )
    assert spotify == "Iris The Goo Goo Dolls"
    assert (
        song_query("https://music.apple.com/x", "Iris by The Goo Goo Dolls on Apple Music", "")
        == "Iris The Goo Goo Dolls"
    )
    assert (
        song_query("https://www.deezer.com/track/1", "Iris - The Goo Goo Dolls", "")
        == "Iris The Goo Goo Dolls"
    )
    album = "https://music.youtube.com/browse/MPREb_Jt7FkXq4pYg"
    assert playlist_source(album) == album
