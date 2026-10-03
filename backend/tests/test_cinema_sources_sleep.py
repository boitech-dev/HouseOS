import json
import time
from datetime import timedelta
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session
import test_cinema
from houseos import cinema as c, cinema_sleep as sleep
from houseos.cinema_adapters import rd_rate_limit
from houseos.playback import MediaError


def test_source_pages_reach_low_resolution_without_credential_fields():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(c.CinemaWorkflow, "workflow-one")
            row.data = {
                **row.data,
                "_sources": [
                    {
                        "id": str(i),
                        "height_claim": 2160 if i < 25 else 720,
                        "release": "Fixture",
                        "resolved_url": "secret",
                        "info_hash": "a" * 40,
                    }
                    for i in range(35)
                ],
            }
            db.commit()
        first = f.client.get("/api/v1/cinema/workflows/workflow-one/sources").json()
        assert first["total"] == 35 and len(first["items"]) == 20 and first["next_offset"] == 20
        low = f.client.get("/api/v1/cinema/workflows/workflow-one/sources?resolution=720&limit=5").json()
        assert low["total"] == 10 and low["next_offset"] == 5 and low["items"][0]["id"] == "25"
        assert "secret" not in json.dumps(low) and "info_hash" not in json.dumps(low)
        second = f.client.get("/api/v1/cinema/workflows/workflow-one/sources?offset=20").json()
        assert len(second["items"]) == 15 and second["next_offset"] is None
    finally:
        f.tearDown()


def test_limiter_separates_storage_failure_from_actual_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(c.settings, "runtime_root", tmp_path)
    rd_rate_limit()
    path = tmp_path / "cinema" / "rd-rate.json"
    path.write_text("invalid")
    with pytest.raises(MediaError) as exc:
        rd_rate_limit()
    assert exc.value.code == "DEBRID_COUNTER_UNAVAILABLE"
    path.write_text(json.dumps([time.time()] * 120))
    with pytest.raises(MediaError) as exc:
        rd_rate_limit()
    assert exc.value.code == "DEBRID_RATE_LIMIT"


def active(f):
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(c.CinemaWorkflow, "workflow-one")
        row.state = "playing_observed"
        row.data = {
            **row.data,
            "_selected_source": "source-one",
            "plan": {
                "expected_item": "fixture-film",
                "duration": 100,
                "audio": {"id": "1"},
                "subtitle": None,
            },
        }
        db.get(c.CinemaDevice, f.device_id).owner_workflow = row.id
        db.commit()


def due(db):
    row = db.get(c.CinemaWorkflow, "workflow-one")
    row.data = {
        **row.data,
        "sleep_timer": {**row.data["sleep_timer"], "at": (c.utcnow() - timedelta(seconds=1)).isoformat()},
    }
    db.commit()


def test_sleep_pause_is_exact_observed_session_single_use():
    f = test_cinema.CinemaTests()
    f.setUp()
    active(f)
    try:
        result = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/sleep", json={"version": 1, "minutes": 60}
        )
        assert result.status_code == 200, result.text
        observation = {
            "state": "active",
            "item_id": "fixture-film",
            "position": 12,
            "check_in": c.utcnow().isoformat() + "Z",
            "audio_index": 1,
            "subtitle_index": -1,
        }
        with Session(f.engine) as db:
            due(db)
            with (
                patch.object(c, "inspect_destination", return_value=observation),
                patch.object(c, "Jellyfin") as jf,
            ):
                assert sleep.process_sleep_timers(db) == 1
                assert sleep.process_sleep_timers(db) == 0
                jf.return_value.control.assert_called_once_with("session-one", "pause", None)
            timer = db.get(c.CinemaWorkflow, "workflow-one").data["sleep_timer"]
            assert timer["state"] == "completed" and timer["result"]["state"] == "pause_command_sent"
    finally:
        f.tearDown()


def test_timer_never_controls_replacement_or_unsupported_poweroff():
    f = test_cinema.CinemaTests()
    f.setUp()
    active(f)
    try:
        assert (
            f.client.post(
                "/api/v1/cinema/workflows/workflow-one/sleep",
                json={"version": 1, "minutes": 60, "power_off": True},
            ).status_code
            == 422
        )
        assert (
            f.client.post(
                "/api/v1/cinema/workflows/workflow-one/sleep", json={"version": 1, "minutes": 300}
            ).status_code
            == 200
        )
        with Session(f.engine) as db:
            due(db)
            db.get(c.CinemaDevice, f.device_id).owner_workflow = "different-workflow"
            db.commit()
            with patch.object(sleep, "control") as control:
                sleep.process_sleep_timers(db)
                control.assert_not_called()
            assert (
                db.get(c.CinemaWorkflow, "workflow-one").data["sleep_timer"]["error"]["code"]
                == "SLEEP_SESSION_CHANGED"
            )
    finally:
        f.tearDown()


def test_timer_cancel_and_revoked_permission():
    f = test_cinema.CinemaTests()
    f.setUp()
    active(f)
    try:
        result = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/sleep", json={"version": 1, "minutes": 90}
        ).json()
        cancelled = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/sleep", json={"version": result["version"], "minutes": 0}
        ).json()
        assert cancelled["sleep_timer"] is None
        f.client.post(
            "/api/v1/cinema/workflows/workflow-one/sleep",
            json={"version": cancelled["version"], "minutes": 60},
        )
        with Session(f.engine) as db:
            due(db)
            db.get(sleep.User, f.actor.id).active = False
            db.commit()
            with patch.object(sleep, "control") as control:
                sleep.process_sleep_timers(db)
                control.assert_not_called()
            assert db.get(c.CinemaWorkflow, "workflow-one").data["sleep_timer"]["state"] == "failed"
    finally:
        f.tearDown()


def test_comet_cap_preserves_lower_resolution_diversity():
    from houseos.cinema_adapters import Comet

    entries = [
        {
            "infoHash": format(i, "040x"),
            "name": "Comet " + ("2160p" if i < 130 else "720p"),
            "description": "Synthetic source",
        }
        for i in range(140)
    ]
    with (
        patch(
            "houseos.cinema_adapters.private_json",
            side_effect=[{"resources": ["stream"]}, {"streams": entries}],
        ),
    ):
        sources = Comet({"enabled": True, "base_url": "http://127.0.0.1:8767"}).streams("tt123", "movie")
    assert len(sources) == 100
    assert sum(source["height_claim"] == 720 for source in sources) == 10
