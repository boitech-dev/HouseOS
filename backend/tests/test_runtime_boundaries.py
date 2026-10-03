"""Failure reporting and local device controls must never infer success."""

import pytest
from houseos import audio


def test_mpv_rejection_disconnect_and_valid_null_ack(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def connect(self, *args):
            pass

        def sendall(self, *args):
            pass

        def recv(self, *args):
            return self.response

    conn = Connection()
    monkeypatch.setattr(audio.socket, "socket", lambda *args: conn)
    conn.response = b'{"request_id":1,"error":"success"}\n'
    assert audio.mpv(["pause"]) is None
    conn.response = b'{"request_id":1,"error":"invalid parameter"}\n'
    with pytest.raises(OSError):
        audio.mpv(["pause"])
    conn.response = b""
    with pytest.raises(OSError):
        audio.mpv(["pause"])


def test_audio_sink_loss_pauses_and_unverified_outputs_cannot_play(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "mpv", lambda command: calls.append(command))
    monkeypatch.setattr(audio, "policy", lambda: {"sink": "missing", "verified": True})
    monkeypatch.setattr(audio, "outputs", lambda: [])
    assert audio.execute({"command": "state"})["code"] == "SELECTED_SINK_DISAPPEARED"
    assert ["set_property", "pause", True] in calls
    monkeypatch.setattr(audio.settings, "audio_enabled", True)
    assert audio.execute({"command": "play"})["status"] == "blocked"
    assert audio.execute({"command": "load", "item_id": "anything"})["status"] == "blocked"


def test_live_fifo_requires_fresh_owned_exact_lease(tmp_path, monkeypatch):
    import os, json, time
    from types import SimpleNamespace
    from uuid import uuid4

    item = str(uuid4())
    monkeypatch.setattr(audio, "MEDIA", tmp_path)
    monkeypatch.setattr(audio.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    os.mkfifo(tmp_path / (item + ".media"))
    lease = tmp_path / (item + ".live.json")
    data = {"item_id": item, "expires_at": time.time() + 60, "state": "waiting"}
    lease.write_text(json.dumps(data))
    assert audio.live_manifest(item)["item_id"] == item
    data["expires_at"] = time.time() - 1
    lease.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        audio.live_manifest(item)
    monkeypatch.setattr(audio, "live_item", item)
    monkeypatch.setattr(audio, "policy", lambda: {})
    assert audio.execute({"command": "seek", "value": 5})["code"] == "LIVE_SEEK_UNSUPPORTED"
