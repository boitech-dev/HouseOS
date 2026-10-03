from datetime import timedelta
from unittest.mock import patch
from sqlalchemy.orm import Session
import test_cinema
from houseos import cinema as c
from houseos.auth import Actor
from houseos.playback import MediaError


def setup_active(f):
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
                "release_key": "release-one",
                "audio": {"id": "1"},
                "subtitle": None,
            },
            "checkpoint": {"position": 42, "at": c.utcnow().isoformat()},
            "observation": {"identity": "matched", "state": "active"},
            "sleep_timer": {"state": "scheduled"},
        }
        d = db.get(c.CinemaDevice, f.device_id)
        d.owner_workflow = row.id
        d.observed_at = c.utcnow()
        db.commit()


def test_current_requires_fresh_owned_matching_observation():
    f = test_cinema.CinemaTests()
    f.setUp()
    setup_active(f)
    try:
        assert f.client.get("/api/v1/cinema/current").json()["current"]["checkpoint"]["position"] == 42
        f.actor = Actor("other", "Other", "resident", frozenset({"cinema.use"}))
        assert f.client.get("/api/v1/cinema/current").json()["current"] is None
        f.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        with Session(f.engine) as db:
            row = db.get(c.CinemaWorkflow, "workflow-one")
            row.data = {
                **row.data,
                "checkpoint": {"position": 42, "at": (c.utcnow() - timedelta(seconds=31)).isoformat()},
            }
            db.commit()
        assert f.client.get("/api/v1/cinema/current").json()["current"] is None
    finally:
        f.tearDown()


def test_stop_preserves_fresh_private_resume_and_cancels_timer():
    f = test_cinema.CinemaTests()
    f.setUp()
    setup_active(f)
    try:
        observed = {
            "state": "active",
            "item_id": "fixture-film",
            "position": 47,
            "check_in": c.utcnow().isoformat() + "Z",
            "audio_index": 1,
            "subtitle_index": -1,
        }
        with patch.object(c, "inspect_destination", return_value=observed), patch.object(c, "Jellyfin") as jf:
            result = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control", json={"version": 1, "action": "stop"}
            )
            assert result.status_code == 200, result.text
            jf.return_value.control.assert_called_once_with("session-one", "stop", None)
        assert result.json()["state"] == "stopped" and result.json()["sleep_timer"] is None
        assert result.json()["observation"]["state"] == "stop_command_sent"
        assert f.client.get("/api/v1/cinema/current").json()["current"] is None
        assert f.client.get("/api/v1/cinema/titles/title-one").json()["progress"]["position"] == 47
        with Session(f.engine) as db:
            source = db.get(c.CinemaWorkflow, "workflow-one").data["_sources"][0]
            reopened = c.CinemaWorkflow(
                id="reopened",
                owner_id=f.actor.id,
                media_id=f.title_id,
                device_id=f.device_id,
                state="awaiting_choice",
                version=1,
                idempotency_key="reopen-exact",
                data={"request": {}, "_sources": [source]},
            )
            db.add(reopened)
            db.flush()
            with patch.object(c, "inspect_destination", return_value={"state": "idle"}):
                assert c.prepare_plan(db, reopened, source)["plan"]["position"] == 47
        f.actor = Actor("other", "Other", "resident", frozenset({"cinema.use"}))
        assert f.client.get("/api/v1/cinema/titles/title-one").json()["progress"] == {}
    finally:
        f.tearDown()


def test_unverified_stop_releases_application_without_stopping_other_media():
    f = test_cinema.CinemaTests()
    f.setUp()
    setup_active(f)
    try:
        with (
            patch.object(c, "inspect_destination", side_effect=MediaError("TARGET_OFFLINE", "Unavailable")),
            patch.object(c, "Jellyfin") as jf,
        ):
            result = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control", json={"version": 1, "action": "stop"}
            ).json()
            jf.assert_not_called()
        assert result["state"] == "stopped" and result["observation"]["state"] == "command_outcome_unknown"
        assert result["checkpoint"]["position"] == 42 and result["sleep_timer"] is None
    finally:
        f.tearDown()


def test_cast_stop_saves_place_closes_receiver_and_releases_everything():
    f = test_cinema.CinemaTests()
    f.setUp()
    setup_active(f)
    try:
        with Session(f.engine) as db:
            db.get(c.CinemaDevice, f.device_id).adapter = "cast"
            db.add(
                c.CinemaRelay(
                    token_hash="b" * 64,
                    workflow_id="workflow-one",
                    device_address="192.0.2.17",
                    path="/nowhere",
                    mime="video/mp4",
                    expires_at=c.utcnow() + timedelta(hours=1),
                )
            )
            db.commit()
        observed = {"state": "active", "item_id": "fixture-film", "position": 63}
        with (
            patch.object(c, "inspect_destination", return_value=observed),
            patch("houseos.cinema_cast.abort_cast") as abort,
            patch("houseos.cinema_cast.cast_control") as cast_control,
        ):
            result = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control", json={"version": 1, "action": "stop"}
            )
            assert result.status_code == 200, result.text
            abort.assert_called_once_with("192.0.2.17", {"fixture-film"})
            cast_control.assert_not_called()
        assert result.json()["state"] == "stopped" and result.json()["error"] is None
        assert f.client.get("/api/v1/cinema/titles/title-one").json()["progress"]["position"] == 63
        with Session(f.engine) as db:
            assert db.get(c.CinemaDevice, f.device_id).owner_workflow is None
            assert db.get(c.CinemaWorkflow, "workflow-one").data["_cast_closed"] is True
            assert not db.scalars(c.select(c.CinemaRelay)).all()
    finally:
        f.tearDown()


def test_clear_queue_snapshot_and_retry_never_remove_later_items():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:

        def add(key):
            return f.client.post(
                "/api/v1/cinema/queue", json={"media_id": f.title_id, "idempotency_key": key}
            )

        add("queue-one")
        snapshot = f.client.get("/api/v1/cinema/queue").json()
        add("queue-two")
        assert (
            f.client.post(
                "/api/v1/cinema/queue/clear",
                json={"revision": snapshot["revision"], "idempotency_key": "clear-first"},
            ).status_code
            == 409
        )
        snapshot = f.client.get("/api/v1/cinema/queue").json()
        body = {"revision": snapshot["revision"], "idempotency_key": "clear-second"}
        assert f.client.post("/api/v1/cinema/queue/clear", json=body).json()["removed"] == 2
        add("queue-three")
        assert f.client.post("/api/v1/cinema/queue/clear", json=body).json()["removed"] == 2
        assert f.client.get("/api/v1/cinema/queue").json()["total"] == 1
    finally:
        f.tearDown()


def test_actual_volume_adapter_commands_and_supported_range():
    from houseos.cinema_adapters import Jellyfin
    from houseos.cinema_cast import cast_control

    with patch("houseos.cinema_cast.connect") as connect:
        cast_control("fixture", "volume", 35)
        connect.return_value.set_volume.assert_called_once_with(0.35)
    with patch.object(Jellyfin, "call") as request:
        Jellyfin({"enabled": True, "api_key": "fixture", "user_id": "fixture-user"}).control(
            "session", "volume", 35
        )
        assert request.call_args.kwargs["payload"] == {"Name": "SetVolume", "Arguments": {"Volume": "35"}}
    f = test_cinema.CinemaTests()
    f.setUp()
    setup_active(f)
    try:
        assert (
            f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control",
                json={"version": 1, "action": "volume", "position": 30},
            ).status_code
            == 422
        )
    finally:
        f.tearDown()
