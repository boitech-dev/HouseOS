import pytest
from houseos.music import canonical_source
from houseos import radio
from houseos.fetcher import execute

IDENTITY = "d1234567-1234-1234-1234-123456789abc"


def test_station_ids_and_normalized_contract(monkeypatch):
    row = {
        "stationuuid": IDENTITY,
        "name": "Test station",
        "url_resolved": "https://example.org/radio",
        "lastcheckok": 1,
        "bitrate": 192,
    }
    monkeypatch.setattr(radio, "directory", lambda *args, **kw: [row])
    assert canonical_source("radio:" + IDENTITY) == "radio:" + IDENTITY
    result = radio.cached_search("", "", "", "", 0, 123)
    assert result[0]["id"] == IDENTITY and "url" not in result[0]
    assert radio.resolve(IDENTITY)["url"] == row["url_resolved"]
    for source in [
        "file:///etc/passwd",
        "https://user:secret@example.org/radio",
        "http://example.org:25/radio",  # never another service's port
    ]:
        with pytest.raises(ValueError):
            radio.normalize({**row, "url_resolved": source})
    # Icecast/Shoutcast streams live on high ports: most of the directory.
    assert radio.normalize({**row, "url_resolved": "https://example.org:8443/jazz"})["https"]
    metadata = execute({"action": "metadata", "source_url": "radio:" + IDENTITY})
    assert metadata["is_live"] and metadata["status"] == "needs_confirmation"
    with pytest.raises(ValueError):
        execute({"action": "download", "source_url": "radio:" + IDENTITY})


def test_configured_output_does_not_fabricate_heard_evidence(monkeypatch):
    from houseos import audio

    monkeypatch.setattr(audio, "policy", lambda: {"sink": "speakers", "verified": False})
    monkeypatch.setattr(audio, "outputs", lambda: [{"id": "speakers"}])
    monkeypatch.setattr(audio.settings, "audio_enabled", True)
    commands = []
    monkeypatch.setattr(audio, "mpv", lambda command: commands.append(command))
    assert audio.execute({"command": "play"})["status"] == "command_sent"
    assert audio.execute({"command": "outputs"})["physical_verified"] is False
    monkeypatch.setattr(audio, "outputs", lambda: [])
    assert audio.execute({"command": "play"})["status"] == "blocked"
    monkeypatch.setattr(audio.settings, "audio_enabled", False)
    assert audio.execute({"command": "play"})["status"] == "blocked"


def test_radio_queue_is_idempotent_and_favorites_private(monkeypatch):
    from test_music_library import MusicLibraryTests

    case = MusicLibraryTests()
    case.setUp()
    monkeypatch.setattr(
        radio,
        "resolve",
        lambda identity: {"id": IDENTITY, "name": "Station", "url": "https://example.org/radio"},
    )
    assert case.client.post("/music/radio/" + IDENTITY + "/favorite").status_code == 200
    assert case.client.get("/music/radio/favorites").json()["items"][0]["name"] == "Station"
    body = {"idempotency_key": "radio-queue-test"}
    first = case.client.post("/music/radio/" + IDENTITY + "/queue", json=body)
    second = case.client.post("/music/radio/" + IDENTITY + "/queue", json=body)
    assert first.status_code == 200 and first.json()["item_id"] == second.json()["item_id"]
    from houseos.auth import Actor

    case.actor = Actor("two", "Two", "resident", case.actor.permissions)
    assert case.client.get("/music/radio/favorites").json()["items"] == []
    case.actor = Actor("two", "Two", "guest", frozenset({"music.read"}))
    assert case.client.post("/music/radio/" + IDENTITY + "/queue", json=body).status_code == 403
