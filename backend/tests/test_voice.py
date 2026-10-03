"""Voice: recordings go to the local transcriber over a private socket and never stay."""

import json
import socketserver
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from houseos import assistant
from houseos.auth import Actor, require_actor
from houseos.config import settings


@pytest.fixture
def voice(tmp_path, monkeypatch):
    (tmp_path / "run" / "voice").mkdir(parents=True)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    seen = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline())
            path = tmp_path / "run" / "voice" / request["name"]
            seen.append((request, path.read_bytes()))
            path.unlink()
            reply = {"status": "completed", "text": "Mets de la musique", "language": "fr", "duration": 2.1}
            self.wfile.write(json.dumps(reply).encode() + b"\n")

    server = socketserver.ThreadingUnixStreamServer(str(tmp_path / "run" / "voice.sock"), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app = FastAPI()
    app.include_router(assistant.router, prefix="/api/v1")
    actor = {"value": Actor("resident", "Resident", "resident", frozenset({"assistant.use"}))}
    app.dependency_overrides[require_actor] = lambda: actor["value"]
    assistant.voice_calls.clear()
    yield TestClient(app), seen, tmp_path, actor
    server.shutdown()
    server.server_close()


def post(client, body, kind="audio/webm;codecs=opus", language="fr"):
    return client.post(
        "/api/v1/assistant/voice?language=" + language, content=body, headers={"Content-Type": kind}
    )


def test_transcribes_locally_and_keeps_nothing(voice):
    client, seen, root, _ = voice
    reply = post(client, b"\x1a\x45\xdf\xa3" + b"0" * 4000)
    assert reply.status_code == 200, reply.text
    assert reply.json() == {
        "text": "Mets de la musique",
        "language": "fr",
        "duration": 2.1,
        "confident": False,
    }
    request, audio = seen[0]
    assert request["language"] == "fr" and audio.startswith(b"\x1a\x45\xdf\xa3")
    assert not any((root / "run" / "voice").iterdir())


def test_limits_permission_and_rate(voice):
    client, seen, _, actor = voice
    assert post(client, b"0" * 4000, kind="text/plain").status_code == 415
    assert post(client, b"0" * 100).status_code == 422
    assert post(client, b"0" * (assistant.VOICE_LIMIT_BYTES + 1)).status_code == 413
    actor["value"] = Actor("guest", "Guest", "guest", frozenset({"music.read"}))
    assert post(client, b"0" * 4000).status_code == 403
    actor["value"] = Actor("resident", "Resident", "resident", frozenset({"assistant.use"}))
    assistant.voice_calls.clear()
    codes = [post(client, b"0" * 4000).status_code for _ in range(13)]
    assert codes[:12] == [200] * 12 and codes[12] == 429
    assert len(seen) == 12


def test_service_down_says_type_instead(voice, tmp_path):
    client, _, root, _ = voice
    (root / "run" / "voice.sock").unlink()
    reply = post(client, b"0" * 4000)
    assert reply.status_code == 503 and "type instead" in reply.text
    assert not any((root / "run" / "voice").iterdir())


def test_the_page_may_use_the_microphone():
    from houseos.main import app

    headers = TestClient(app).get("/api/v1/health").headers
    assert "microphone=(self)" in headers["permissions-policy"]


def test_a_failing_graphics_card_falls_back_to_the_cpu_once(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from houseos import voice as service

    monkeypatch.setattr(service, "INBOX", tmp_path)
    monkeypatch.setattr(service, "state", {"model": None, "name": None, "used": 0.0, "gpu_failed": False})
    loads = []

    class Model:
        def __init__(self, name):
            self.name = name

        def transcribe(self, *args, **kwargs):
            if self.name.endswith("@cuda"):
                raise RuntimeError("libcublas.so.12 not found")
            segment = SimpleNamespace(text=" Bonsoir Nox", avg_logprob=-0.2, no_speech_prob=0.1)
            return iter([segment]), SimpleNamespace(language="fr", duration=1.0, language_probability=0.9)

    def load():
        if service.state["model"] is None:
            name = "small@cpu" if service.state["gpu_failed"] else "large-v3-turbo@cuda"
            service.state.update(model=Model(name), name=name)
            loads.append(name)
        return service.state["model"]

    monkeypatch.setattr(service, "load", load)
    for attempt in range(2):
        (tmp_path / "clip").write_bytes(b"0" * 600)
        assert service.transcribe("clip", "fr")["text"] == "Bonsoir Nox"
    assert loads == ["large-v3-turbo@cuda", "small@cpu"]
    assert service.device() == "cpu"


def test_a_failed_model_download_tries_again_without_a_restart(monkeypatch):
    import sys
    from types import SimpleNamespace

    from houseos import voice as service

    attempts, sleeps = [], []

    def download_model(name, cache_dir):
        attempts.append(name)
        if len(attempts) < 3:
            raise OSError("no internet yet")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(download_model=download_model))
    monkeypatch.setattr(service.time, "sleep", sleeps.append)
    monkeypatch.setattr(service, "state", {"model": None, "name": None, "used": 0.0, "gpu_failed": False})
    monkeypatch.setenv("HOUSEOS_VOICE_MODEL", "base")
    monkeypatch.delenv("HOUSEOS_VOICE_GPU", raising=False)
    service.prefetch()
    assert attempts == ["base"] * 3 and sleeps == [600, 600] and not service.state["preparing"]
    attempts.clear()
    sleeps.clear()
    service.prefetch(tries=1)
    assert attempts == ["base"]  # bounded: gives up after its tries
