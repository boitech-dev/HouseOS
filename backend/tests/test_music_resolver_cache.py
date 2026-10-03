import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from houseos import fetcher
from houseos.fetcher_cache import prune


URL = "https://www.youtube.com/watch?v=abcdefghijk"


def test_metadata_download_and_concurrent_replay_extract_once(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    monkeypatch.setattr(fetcher, "COMPLETED", {})
    calls = []

    def run(args, *unused, cancelled=None):
        calls.append(args)
        if "--dump-single-json" in args:
            return json.dumps(
                {"title": "Song", "duration": 10, "url": "https://private.example/media"}
            ).encode()
        assert "--load-info-json" in args
        assert URL not in args
        from pathlib import Path

        Path(args[args.index("-o") + 1]).write_bytes(b"audio")
        return b""

    monkeypatch.setattr(fetcher, "bounded_process", run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: fetcher.execute({"action": "metadata", "source_url": URL}), range(2))
        )
    assert all(row["title"] == "Song" for row in results)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda _: fetcher.execute({"action": "download", "source_url": URL, "item_id": str(uuid4())}),
                range(2),
            )
        )
    assert len(calls) == 2  # one extraction and one actual transfer
    ticket = next((tmp_path / ".resolutions").glob("*.json"))
    assert ticket.stat().st_mode & 0o777 == 0o600
    assert not any("private.example" in str(row) for row in results)


def test_prune_protects_pinned_hardlinks_and_ignores_partial(tmp_path):
    old, current, same, partial = [str(uuid4()) for _ in range(4)]
    (tmp_path / (old + ".media")).write_bytes(b"a" * 10)
    (tmp_path / (current + ".media")).write_bytes(b"b" * 10)
    os.link(tmp_path / (current + ".media"), tmp_path / (same + ".media"))
    (tmp_path / (partial + ".media.part")).write_bytes(b"pending")
    result = prune(tmp_path, [same], maximum=10, reserve=0)
    assert result["removed_item_ids"] == [old]
    assert (tmp_path / (current + ".media")).exists()
    assert (tmp_path / (partial + ".media.part")).exists()


def test_expired_download_refreshes_once_without_retrying_challenges(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    monkeypatch.setattr(fetcher, "COMPLETED", {})
    extracts = []
    transfers = []

    def run(args, *unused, cancelled=None):
        if "--dump-single-json" in args:
            extracts.append(1)
            return b'{"duration":10}'
        transfers.append(1)
        raise ValueError("SOURCE_URL_EXPIRED")

    monkeypatch.setattr(fetcher, "bounded_process", run)
    with pytest.raises(ValueError, match="SOURCE_URL_EXPIRED"):
        fetcher.execute({"action": "download", "source_url": URL, "item_id": str(uuid4())})
    assert len(extracts) == len(transfers) == 2
    monkeypatch.setattr(fetcher, "YOUTUBE_PAUSE", {"until": float("inf"), "code": "YOUTUBE_SIGN_IN_REQUIRED"})
    # A ready resolution does not query the challenged provider again.
    assert fetcher.execute({"action": "metadata", "source_url": URL})["duration"] == 10


def test_requests_during_youtube_cooldown_do_not_extend_it(monkeypatch):
    import io
    from types import SimpleNamespace

    pause = {"until": 200.0, "code": "YOUTUBE_RATE_LIMITED"}
    monkeypatch.setattr(fetcher, "YOUTUBE_PAUSE", pause)
    monkeypatch.setattr(fetcher.time, "monotonic", lambda: 100.0)

    def fail(data):
        raise ValueError("YOUTUBE_RATE_LIMITED")

    monkeypatch.setattr(fetcher, "execute", fail)
    handler = object.__new__(fetcher.Handler)
    handler.request = SimpleNamespace(settimeout=lambda _: None)
    handler.rfile = io.BytesIO(b'{"action":"metadata"}\n')
    handler.wfile = io.BytesIO()
    handler.handle()
    assert pause["until"] == 200.0
    assert json.loads(handler.wfile.getvalue())["code"] == "YOUTUBE_RATE_LIMITED"


def test_prune_rpc_passes_the_worker_pins(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    identity = str(uuid4())
    monkeypatch.setattr(fetcher, "prune", lambda root, pins: {"status": "completed", "pins": pins})
    assert fetcher.execute({"action": "cache_prune", "pins": [identity]})["pins"] == [identity]
