import sys
import threading
from uuid import uuid4
import pytest
from houseos import fetcher


def test_cancel_kills_transfer_and_cleans_only_its_files(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    identity, other = str(uuid4()), str(uuid4())
    for name in [identity + ".media.part", identity + ".media.ytdl", other + ".media"]:
        (tmp_path / name).write_bytes(b"audio")
    errors = []

    def transfer():
        try:
            fetcher.bounded_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                40,
                cancelled=lambda: (tmp_path / (identity + ".cancelled")).exists(),
            )
        except ValueError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=transfer)
    thread.start()
    assert fetcher.execute({"action": "cancel_download", "item_id": identity})["status"] == "completed"
    thread.join(2)
    assert not thread.is_alive() and errors == ["DOWNLOAD_CANCELLED"]
    assert not list(tmp_path.glob(identity + ".media*"))
    assert (tmp_path / (other + ".media")).read_bytes() == b"audio"
    with pytest.raises(ValueError):
        fetcher.execute({"action": "cancel_download", "item_id": "../unsafe"})


def test_failed_download_removes_partial_output(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    monkeypatch.setattr(fetcher, "COMPLETED", {})
    monkeypatch.setattr(fetcher, "resolve_info", lambda *a, **k: (tmp_path / "ticket.json", {}))
    identity = str(uuid4())

    def fail(*args, **kwargs):
        (tmp_path / (identity + ".media.part")).write_bytes(b"incomplete")
        raise ValueError("SOURCE_UNAVAILABLE")

    monkeypatch.setattr(fetcher, "bounded_process", fail)
    with pytest.raises(ValueError, match="SOURCE_UNAVAILABLE"):
        fetcher.execute(
            {
                "action": "download",
                "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
                "item_id": identity,
            }
        )
    assert not list(tmp_path.glob(identity + ".*"))
