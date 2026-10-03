"""House defaults use live deterministic domains; audio calls are safely stubbed."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete

from houseos import house_settings as h, household, audio, music
from houseos.auth import Actor, require_actor
from houseos.db import get_db
from houseos.models import Integration, User


def test_house_defaults_authorization_preservation_and_domain_timezone(domain, monkeypatch):
    db, (alice, _, _) = domain
    app = FastAPI()
    app.include_router(h.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_actor] = lambda: alice
    calls = []
    monkeypatch.setattr(
        music, "bridge", lambda command, **kwargs: calls.append((command, kwargs)) or {"status": "configured"}
    )
    original = db.get(Integration, "house_settings")
    snapshot = dict(original.config) if original else None
    try:
        with TestClient(app) as client:
            assert client.get("/house-settings").status_code == 200
            assert client.put("/admin/house-settings", json={"name": "House"}).status_code == 403
            db.get(User, alice.id).role = "admin"
            db.commit()
            admin = Actor(alice.id, alice.name, "admin", alice.permissions)
            app.dependency_overrides[require_actor] = lambda: admin
            body = h.HouseSettings(
                name="Night House",
                timezone="UTC",
                language="fr",
                motion="still",
                music_volume_cap=20,
                music_normalize=False,
            ).model_dump()
            assert client.put("/admin/house-settings", json=body).status_code == 200
            assert calls == [("volume_cap", {"value": 20}), ("normalize", {"value": False})]
            db.get(User, alice.id).preferences = {"timezone": "Europe/Paris"}
            db.commit()
            result = client.get("/house-settings").json()
            assert result["name"] == "Night House" and result["preferences"]["timezone"] == "Europe/Paris"
            assert (
                result["preferences"]["language"] == "en"
            )  # Admin default stays English, independent of the house setting.
            db.get(User, alice.id).preferences = {"language": "fr"}
            db.commit()
            assert client.get("/house-settings").json()["preferences"]["language"] == "fr"
            event = household.normalize_data(
                db,
                alice,
                "calendar",
                {"title": "Tea", "start": "2026-10-01T10:00:00", "end": "2026-10-01T11:00:00"},
            )
            assert event["timezone"] == "UTC"
            assert h.notification_defaults(db)["timezone"] == "UTC"
    finally:
        db.rollback()
        if snapshot is None:
            db.execute(delete(Integration).where(Integration.name == "house_settings"))
        else:
            db.get(Integration, "house_settings").config = snapshot
        db.commit()


def test_house_validation_and_audio_enforces_persisted_cap(tmp_path, monkeypatch):
    for values in (
        {"timezone": "Not/AZone"},
        {"quiet_start": "25:30"},
        {"max_upload_bytes": 5 * 1024**3, "file_quota_bytes": 1024**3},
        {"music_volume_cap": 101},
    ):
        with pytest.raises(ValidationError):
            h.HouseSettings(**values)
    monkeypatch.setattr(audio, "POLICY", tmp_path / "audio-policy.json")
    from unittest.mock import Mock

    ramp = Mock()
    monkeypatch.setattr(audio, "volume_ramp", ramp)
    calls = []

    def mpv(command):
        calls.append(command)
        return 50 if command == ["get_property", "volume"] else None

    monkeypatch.setattr(audio, "mpv", mpv)
    assert audio.execute({"command": "volume_cap", "value": 15})["status"] == "configured"
    assert ["set_property", "volume", 15] in calls
    calls.clear()
    audio.execute({"command": "volume", "value": 70})
    ramp.request.assert_called_once_with(15)
    assert calls == []
    assert h.HouseSettings(music_volume_cap=100).music_volume_cap == 100
    assert audio.execute({"command": "volume_cap", "value": 100})["volume_cap"] == 100
    assert ramp.cancel.call_count == 2


def test_language_defaults_are_role_based_and_profile_choice_wins(domain):
    from houseos import core, account

    db, (resident, _, _) = domain
    db.get(User, resident.id).preferences = {}
    from houseos.models import Integration

    db.merge(Integration(name="house_settings", config={"language": "fr"}, enabled=True))  # house in French
    db.commit()
    assert core.preferences(resident, db)["language"] == "fr"
    assert account.profile(resident, db)["language"] == "fr"
    assert h.public_settings(resident, db)["preferences"]["language"] == "fr"
    core.save_preferences(core.Preferences(language="en"), resident, db)
    assert core.preferences(resident, db)["language"] == "en"
    account.edit_profile(account.Profile(language="fr"), resident, db)
    assert core.preferences(resident, db)["language"] == "fr"
    admin = Actor(resident.id, resident.name, "admin", resident.permissions)
    db.get(User, resident.id).preferences = {}
    db.commit()
    assert core.preferences(admin, db)["language"] == "en"


def test_audio_default_follows_computer_and_never_silently_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "POLICY", tmp_path / "audio-policy.json")
    monkeypatch.setattr(audio, "default_sink", lambda: "jack")
    monkeypatch.setattr(audio, "outputs", lambda: [{"id": "default"}, {"id": "jack"}])
    calls = []
    values = {
        "audio-device": "pulse/hdmi",
        "idle-active": False,
        "pause": False,
        "time-pos": 2,
        "volume": 25,
        "mute": False,
        "current-ao": "pulse",
    }

    def mpv(command):
        calls.append(command)
        return values.get(command[1]) if command[0] == "get_property" else None

    monkeypatch.setattr(audio, "mpv", mpv)
    state = audio.execute({"command": "state"})
    assert ["set_property", "audio-device", "pulse/jack"] in calls
    assert state["resolved_output"] == "jack" and state["audio_backend"] == "pulse"
    monkeypatch.setattr(audio, "default_sink", lambda: "missing")
    assert audio.execute({"command": "play"})["code"] == "DEFAULT_SINK_UNAVAILABLE"
    assert calls[-1] == ["set_property", "pause", True]


def test_state_polls_reuse_one_output_snapshot(monkeypatch):
    from houseos import audio

    calls = []
    monkeypatch.setattr(audio, "default_sink", lambda: calls.append("default") or "jack")
    monkeypatch.setattr(
        audio, "outputs", lambda: calls.append("outputs") or [{"id": "default"}, {"id": "jack"}]
    )
    assert audio.output_snapshot(False) == audio.output_snapshot(False) == ("jack", {"default", "jack"})
    assert calls == ["default", "outputs"]
    audio.output_snapshot(True)  # load/play always re-check the live outputs
    assert len(calls) == 4


def test_song_levels_one_fixed_gain_per_song_never_mid_song(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr(audio, "POLICY", tmp_path / "audio-policy.json")
    calls = []
    monkeypatch.setattr(audio, "mpv", lambda command: calls.append(command))
    assert h.HouseSettings().music_normalize is True  # on unless the house turns it off
    assert audio.song_filter(-18, -9) == f"lavfi=[volume={audio.BOOST}dB]"  # quiet upload: +20 %
    assert "alimiter" in audio.song_filter(-14, -0.5)  # its few peaks that would clip are guarded
    assert audio.song_filter(-10, -0.1) == ""  # a normal loud master plays as released
    assert audio.song_filter(-5, 0.0) == f"lavfi=[volume={audio.CUT}dB]"  # ear-splitting: -15 %
    quiet = tmp_path / "quiet.media"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:d=3",
            "-af",
            "volume=-24dB",
            "-f",
            "wav",
            str(quiet),
        ],
        check=True,
    )
    assert audio.level_filter(quiet) == f"lavfi=[volume={audio.BOOST}dB]"
    assert audio.execute({"command": "normalize", "value": False})["normalize"] is False
    assert calls == []  # nothing changes under the song playing now
    assert audio.level_filter(quiet) == ""
    with pytest.raises(ValueError):
        audio.execute({"command": "normalize", "value": "yes"})


def test_timezone_defaults_follow_the_house_setting(domain):
    """Code defaults are UTC; a house that saved its own zone keeps it everywhere."""
    from houseos import core, notifications

    db, (resident, _, _) = domain
    original = db.get(Integration, "house_settings")
    snapshot = dict(original.config) if original else None
    try:
        for zone in ("UTC", "Europe/Paris"):
            db.merge(Integration(name="house_settings", config={"timezone": zone}, enabled=True))
            db.get(User, resident.id).preferences = {}
            db.commit()
            assert core.preferences(resident, db)["timezone"] == zone
            assert notifications.push_status(resident, db)["preferences"]["timezone"] == zone
            task = household.normalize_data(db, resident, "tasks", {"title": "Bins"})
            assert task["timezone"] == zone
            saved = notifications.preferences(
                notifications.NotificationPreferences(quiet_start="22:00"), resident, db
            )
            assert (
                saved["timezone"]
                == zone
                == db.get(User, resident.id).preferences["notification_settings"]["timezone"]
            )
    finally:
        db.rollback()
        if snapshot is None:
            db.execute(delete(Integration).where(Integration.name == "house_settings"))
        else:
            db.get(Integration, "house_settings").config = snapshot
        db.commit()
