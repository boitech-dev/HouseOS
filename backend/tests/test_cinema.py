import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from houseos.db import Base, get_db, utcnow
from houseos.auth import Actor, require_actor
from houseos.cinema import (
    router,
    CinemaTitle,
    CinemaDevice,
    CinemaWorkflow,
    CinemaConfirmation,
    CinemaState,
)
from houseos.cinema_adapters import RealDebrid, public_url
from houseos.playback import MediaError
from houseos.models import User


class CinemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        self.app.dependency_overrides[require_actor] = lambda: self.actor

        def session():
            with Session(self.engine, expire_on_commit=False) as db:
                yield db

        self.app.dependency_overrides[get_db] = session
        self.client = TestClient(self.app)
        self.title_id, self.device_id = "title-one", "device-one"
        self.media = {
            "video": {"index": 0, "codec": "h264", "height": 1080, "hdr": "sdr", "dv_profile": None},
            "audio": [{"id": "1", "codec": "aac", "language": "en", "channels": 2, "default": True}],
            "subtitles": [],
            "container": "mp4",
            "duration": 100,
            "evidence": "ffprobe",
        }
        self.caps = {
            "inspected_at": utcnow().isoformat(),
            "video_codecs": ["h264"],
            "audio_codecs": ["aac"],
            "hdr_modes": ["sdr"],
            "maximum_resolution": 1080,
            "max_audio_channels": 2,
            "containers": ["mp4"],
        }
        with Session(self.engine) as db:
            db.add(
                User(
                    id="resident-one",
                    name="One",
                    username="resident-one",
                    password_hash="fixture",
                    role="resident",
                )
            )
            db.add(
                CinemaTitle(
                    id=self.title_id,
                    canonical_id="tt123",
                    title="Synthetic Film",
                    kind="movie",
                    data={"layers": ["LOCAL"]},
                )
            )
            db.add(
                CinemaDevice(
                    id=self.device_id,
                    name="Test",
                    adapter="jellyfin",
                    address="192.0.2.17",
                    session_id="session-one",
                    capabilities=self.caps,
                    observation={"state": "idle"},
                )
            )
            db.commit()

    def test_stop_cancels_failed_load_and_all_pending_work_without_erasing_history(self):
        from houseos.cinema import CinemaPreparation
        from houseos.models import Job, Operation

        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state = "recovery_required"
            row.data = {**row.data, "plan": {"expected_item": "ours"}, "checkpoint": {"position": 42}}
            device = db.get(CinemaDevice, self.device_id)
            device.adapter, device.owner_workflow = "cast", row.id
            db.add(
                Operation(
                    id="discovery-op",
                    actor_id=self.actor.id,
                    kind="cinema.discover",
                    state="running",
                    data={},
                    result={},
                )
            )
            db.add(
                Job(
                    id="discovery-job",
                    logical_key="discovery-job",
                    actor_id=self.actor.id,
                    kind="cinema.discover",
                    state="running",
                    generation=1,
                    payload={"operation_id": "discovery-op"},
                )
            )
            db.add(
                CinemaPreparation(
                    id="pending",
                    workflow_id=row.id,
                    owner_id=self.actor.id,
                    workflow_version=row.version,
                    state="queued",
                )
            )
            db.add(
                CinemaWorkflow(
                    id="other",
                    owner_id="other-user",
                    media_id=self.title_id,
                    state="preparing",
                    version=1,
                    idempotency_key="other",
                    data={},
                )
            )
            db.commit()
        with patch("houseos.cinema_cast.abort_cast", return_value="stop_sent") as abort:
            result = self.client.post("/api/v1/cinema/stop", json={})
            self.assertEqual(result.status_code, 200, result.text)
            abort.assert_called_once_with("192.0.2.17", {"ours"})
        with Session(self.engine) as db:
            self.assertEqual(db.get(CinemaWorkflow, "workflow-one").state, "cancelled")
            self.assertEqual(db.get(CinemaWorkflow, "workflow-one").data["checkpoint"]["position"], 42)
            self.assertEqual(db.get(CinemaPreparation, "pending").state, "cancelled")
            self.assertEqual(db.get(Job, "discovery-job").state, "cancelled")
            self.assertEqual(db.get(Job, "discovery-job").generation, 2)
            self.assertEqual(db.get(Operation, "discovery-op").state, "cancelled")
            self.assertIsNone(db.get(CinemaDevice, self.device_id).owner_workflow)
            self.assertEqual(db.get(CinemaWorkflow, "other").state, "preparing")
        with patch("houseos.cinema_cast.abort_cast") as abort:
            self.assertEqual(self.client.post("/api/v1/cinema/stop", json={}).status_code, 200)
            abort.assert_not_called()

    def test_orphaned_preparation_fails_immediately_and_unblocks_the_lane(self):
        from houseos.cinema import CinemaPreparation
        from houseos.cinema_prepare import process_one_preparation

        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state = "preparing"
            db.add(
                CinemaPreparation(
                    id="orphan",
                    workflow_id=row.id,
                    owner_id=self.actor.id,
                    workflow_version=row.version,
                    state="running",
                    started_at=utcnow(),
                )
            )
            db.add(
                CinemaPreparation(
                    id="next",
                    workflow_id="missing",
                    owner_id=self.actor.id,
                    workflow_version=1,
                    state="queued",
                )
            )
            db.commit()
        with Session(self.engine) as db:
            self.assertFalse(process_one_preparation(db))
        with Session(self.engine) as db:
            self.assertEqual(db.get(CinemaPreparation, "orphan").state, "failed")
            self.assertEqual(db.get(CinemaWorkflow, "workflow-one").state, "recovery_required")
            self.assertEqual(
                db.get(CinemaWorkflow, "workflow-one").data["error"]["code"], "PREPARATION_INTERRUPTED"
            )
        with Session(self.engine) as db:  # the lane now reaches the next queued job
            process_one_preparation(db)
            self.assertNotEqual(db.get(CinemaPreparation, "next").state, "queued")

    def test_stop_offline_receiver_can_be_retried(self):
        self.workflow()
        with Session(self.engine) as db:
            device = db.get(CinemaDevice, self.device_id)
            device.adapter, device.owner_workflow = "cast", "workflow-one"
            db.commit()
        with patch(
            "houseos.cinema_cast.abort_cast", side_effect=MediaError("TARGET_OFFLINE", "Offline", "control")
        ):
            result = self.client.post("/api/v1/cinema/stop", json={})
            self.assertEqual(result.json()["errors"][0]["code"], "TARGET_OFFLINE")
        with patch("houseos.cinema_cast.abort_cast", return_value="stop_sent") as abort:
            result = self.client.post("/api/v1/cinema/stop", json={})
            self.assertEqual(result.json()["errors"], [])
            abort.assert_called_once()

    def test_stop_recovers_cast_left_by_old_cancel_but_not_another_owner(self):
        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state, row.data = "cancelled", {"plan": {"expected_item": "previous"}}
            device = db.get(CinemaDevice, self.device_id)
            device.adapter, device.owner_workflow = "cast", "someone-else"
            db.commit()
        with patch("houseos.cinema_cast.abort_cast") as abort:
            self.client.post("/api/v1/cinema/stop", json={})
            abort.assert_not_called()
        with Session(self.engine) as db:
            db.get(CinemaDevice, self.device_id).owner_workflow = None
            db.commit()
        with patch("houseos.cinema_cast.abort_cast") as abort:
            self.client.post("/api/v1/cinema/stop", json={})
            abort.assert_called_once_with("192.0.2.17", {"previous"})

    def tearDown(self):
        self.engine.dispose()

    def workflow(self, owner="resident-one", expired=False):
        with Session(self.engine) as db:
            data = {
                "request": {},
                "_sources": [
                    {
                        "id": "source-one",
                        "jellyfin_item": "item-one",
                        "jellyfin_source": "release-one",
                        "release": "Edition A",
                        "layer": "LOCAL",
                        "inspection": self.media,
                    }
                ],
                "choice_set": {
                    "id": "choices-one",
                    "revision": 1,
                    "expires_at": (utcnow() + timedelta(minutes=-1 if expired else 10)).isoformat(),
                    "candidates": [{"id": "source-one", "height": 1080, "size": 100}],
                },
            }
            db.add(
                CinemaWorkflow(
                    id="workflow-one",
                    owner_id=owner,
                    media_id=self.title_id,
                    device_id=self.device_id,
                    state="awaiting_choice",
                    version=1,
                    idempotency_key="fixture-once",
                    data=data,
                )
            )
            db.commit()

    def test_resume_reuses_exact_source_tracks_and_requires_current_private_state(self):
        from houseos.cinema import resume_settings

        self.workflow()
        with Session(self.engine) as db:
            w = db.get(CinemaWorkflow, "workflow-one")
            plan = {"audio": self.media["audio"][0], "subtitle": None, "release_key": "release-one"}
            w.data = {
                **w.data,
                "_selected_source": "source-one",
                "plan": plan,
                "checkpoint": {"position": 45},
            }
            db.add(
                CinemaState(
                    owner_id=self.actor.id,
                    media_id=self.title_id,
                    last_watched_at=utcnow(),
                    version=3,
                    data={"position": 45, "release_key": "release-one", "resume": resume_settings(w, plan)},
                )
            )
            db.commit()
        offer = self.client.get("/api/v1/cinema/state/title-one/resume")
        self.assertEqual(offer.status_code, 200)
        self.assertEqual(offer.json()["release"], "Edition A")
        self.assertEqual(offer.json()["audio"], "en")
        self.assertIsNone(offer.json()["subtitles"])
        with Session(self.engine) as db:
            state = db.scalar(select(CinemaState).where(CinemaState.owner_id == self.actor.id))
            state.data = {k: v for k, v in state.data.items() if k != "resume"}
            db.commit()
        self.assertEqual(self.client.get("/api/v1/cinema/state/title-one/resume").json()["audio"], "en")
        with patch("houseos.cinema.play_selected", return_value={"state": "preparing"}) as play:
            response = self.client.post(
                "/api/v1/cinema/state/title-one/resume",
                json={"version": 3, "idempotency_key": "resume-test-one"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            with Session(self.engine) as db:
                w = db.scalar(
                    select(CinemaWorkflow).where(CinemaWorkflow.idempotency_key == "resume-test-one")
                )
                self.assertEqual(w.data["_requested_position"], 45)
                self.assertEqual([x["id"] for x in w.data["_sources"]], ["source-one"])
                self.assertEqual(w.data["request"]["audio_track"], "1")
                self.assertFalse(w.data["request"]["subtitles_on"])
            self.client.post(
                "/api/v1/cinema/state/title-one/resume",
                json={"version": 3, "idempotency_key": "resume-test-one"},
            )
            self.assertEqual(play.call_count, 1)
            stale = self.client.post(
                "/api/v1/cinema/state/title-one/resume",
                json={"version": 2, "idempotency_key": "resume-test-stale"},
            )
            self.assertEqual(stale.status_code, 409)
        self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
        self.assertEqual(self.client.get("/api/v1/cinema/state/title-one/resume").status_code, 404)

    def test_fresh_playback_preview_binds_previous_failed_owner(self):
        from houseos.cinema import prepare_plan

        self.workflow()
        with Session(self.engine, expire_on_commit=False) as db:
            old = db.get(CinemaWorkflow, "workflow-one")
            old.state = "recovery_required"
            device = db.get(CinemaDevice, self.device_id)
            device.owner_workflow = old.id
            new = CinemaWorkflow(
                id="retry-workflow",
                owner_id=self.actor.id,
                media_id=self.title_id,
                device_id=device.id,
                state="awaiting_destination",
                version=1,
                idempotency_key="retry-preview",
                data=copy.deepcopy(old.data),
            )
            db.add(new)
            db.commit()
            with patch("houseos.cinema.inspect_destination", return_value={"state": "idle"}):
                prepare_plan(db, new, new.data["_sources"][0])
            self.assertEqual(new.data.get("_replaces_workflow"), old.id)

    def test_private_workflow_and_watchlist(self):
        self.workflow()
        self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
        self.assertEqual(self.client.get("/api/v1/cinema/workflows/workflow-one").status_code, 404)
        self.assertEqual(
            self.client.put("/api/v1/cinema/state/title-one", json={"favorite": True}).status_code, 200
        )
        self.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        self.assertEqual(self.client.get("/api/v1/cinema/state").json()["items"], [])

    def test_preferences_and_history_removal_do_not_delete_favorites(self):
        self.assertEqual(
            self.client.put(
                "/api/v1/cinema/preferences", json={"audio_language": "en", "subtitles_on": True}
            ).status_code,
            200,
        )
        self.client.put("/api/v1/cinema/state/title-one", json={"favorite": True, "watchlist": True})
        result = self.client.delete("/api/v1/cinema/state/title-one/history")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["favorite"])
        self.assertTrue(result.json()["watchlist"])
        self.assertEqual(self.client.get("/api/v1/cinema/preferences").json()["audio_language"], "en")
        self.assertEqual(
            self.client.put("/api/v1/cinema/preferences", json={"audio_track": "1"}).status_code, 422
        )

    def test_stale_and_wrong_choice_sets_never_prepare(self):
        self.workflow(expired=True)
        with patch("houseos.cinema.prepare_plan") as prepare:
            result = self.client.post(
                "/api/v1/cinema/workflows/workflow-one/select",
                json={"version": 1, "choice_set_id": "choices-one", "choice": "1"},
            )
            self.assertEqual(result.status_code, 409)
            prepare.assert_not_called()

    def test_confirmation_bound_to_actor_single_use_and_version(self):
        self.workflow()
        with Session(self.engine) as db:
            w = db.get(CinemaWorkflow, "workflow-one")
            w.state = "awaiting_playback_confirmation"
            db.add(
                CinemaConfirmation(
                    id="confirm-one",
                    owner_id="resident-one",
                    workflow_id=w.id,
                    workflow_version=1,
                    action="play",
                    data={"device_version": 1},
                    expires_at=utcnow() + timedelta(minutes=1),
                )
            )
            db.commit()
        self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
        self.assertEqual(self.client.post("/api/v1/cinema/confirmations/confirm-one").status_code, 404)
        self.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        with patch("houseos.cinema.execute_play", return_value={"state": "command_sent"}) as execute:
            self.assertEqual(self.client.post("/api/v1/cinema/confirmations/confirm-one").status_code, 200)
            self.assertEqual(self.client.post("/api/v1/cinema/confirmations/confirm-one").status_code, 200)
            self.assertEqual(execute.call_count, 1)

    def test_native_synthetic_progress_without_fresh_checkin_is_not_watched(self):
        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state = "command_sent"
            row.data = {**row.data, "plan": {"expected_item": "fixture-film", "duration": 100}}
            db.get(CinemaDevice, self.device_id).owner_workflow = row.id
            db.commit()
        observation = {
            "state": "active",
            "item_id": "fixture-film",
            "position": 99,
            "check_in": (utcnow() - timedelta(minutes=2)).isoformat(),
        }
        with patch("houseos.cinema.inspect_destination", return_value=observation):
            result = self.client.post("/api/v1/cinema/workflows/workflow-one/observe", json={"version": 1})
            self.assertEqual(result.json()["state"], "recovery_required")
            self.assertEqual(result.json()["error"]["code"], "PLAYBACK_NOT_OBSERVED")
        self.assertEqual(self.client.get("/api/v1/cinema/state").json()["items"], [])

    def test_observation_racing_a_control_is_discarded(self):
        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state = "playing_observed"
            row.data = {**row.data, "plan": {"expected_item": "fixture-film", "duration": 100}}
            db.get(CinemaDevice, self.device_id).owner_workflow = row.id
            db.commit()

        def receiver_io(db, device):
            # The workflow lock is released here: a control commits a new version meanwhile.
            with Session(self.engine) as other:
                (
                    other.get(CinemaWorkflow, "workflow-one").state,
                    other.get(CinemaWorkflow, "workflow-one").version,
                ) = "paused", 2
                other.commit()
            return {"state": "idle", "item_id": None, "position": 0}

        with patch("houseos.cinema.inspect_destination", side_effect=receiver_io):
            result = self.client.post("/api/v1/cinema/workflows/workflow-one/observe", json={"version": 1})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((result.json()["state"], result.json()["version"]), ("paused", 2))

    def test_cast_status_uses_real_pychromecast_fields(self):
        from unittest.mock import MagicMock
        from pychromecast.controllers.media import MediaStatus
        from houseos.cinema_cast import cast_observe

        status = MediaStatus()
        status.update(
            {
                "status": [
                    {
                        "mediaSessionId": 7,
                        "playerState": "PLAYING",
                        "currentTime": 12,
                        "activeTrackIds": [1],
                        "media": {"contentId": "http://fixture.invalid/opaque/media.mp4", "duration": 100},
                    }
                ]
            }
        )
        cast = MagicMock()
        cast.media_controller.status = MediaStatus()  # Cached transport status is deliberately empty.
        cast.status.app_id = "CC1AD845"
        cast.media_controller.is_active = True
        cast.media_controller.send_message_nocheck.side_effect = lambda *args, **kw: kw["callback_function"](
            True,
            {
                "type": "MEDIA_STATUS",
                "status": [
                    {
                        "mediaSessionId": 7,
                        "playerState": "PLAYING",
                        "currentTime": 12,
                        "activeTrackIds": [1],
                        "media": {"contentId": "http://fixture.invalid/opaque/media.mp4", "duration": 100},
                    }
                ],
            },
        )
        with patch("houseos.cinema_cast.connect", return_value=cast):
            result = cast_observe("192.168.1.250")
        self.assertEqual(result["active_track_ids"], [1])
        self.assertEqual(result["state"], "active")
        self.assertNotIn("http", str(result))
        cast.disconnect.assert_called_once()

    def test_cowatch_requires_each_viewers_opt_in(self):
        from houseos.models import User

        with Session(self.engine) as db:
            for identity in ["resident-one", "resident-two"]:
                if db.get(User, identity):
                    continue
                db.add(
                    User(
                        id=identity,
                        name=identity,
                        username=identity,
                        password_hash="fixture",
                        role="resident",
                        permissions=["cinema.use"],
                    )
                )
            db.commit()
        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
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
            db.get(CinemaDevice, self.device_id).owner_workflow = row.id
            db.commit()
        self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
        self.assertEqual(
            self.client.post(
                "/api/v1/cinema/workflows/workflow-one/co-watch", json={"participate": True}
            ).status_code,
            200,
        )
        self.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        observation = {
            "state": "active",
            "item_id": "fixture-film",
            "position": 12,
            "check_in": utcnow().isoformat() + "Z",
            "audio_index": 1,
            "subtitle_index": -1,
        }
        with patch("houseos.cinema.inspect_destination", return_value=observation):
            result = self.client.post("/api/v1/cinema/workflows/workflow-one/observe", json={"version": 1})
            self.assertEqual(result.json()["state"], "playing_observed")
        self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
        self.assertEqual(self.client.get("/api/v1/cinema/state").json()["items"][0]["position"], 12)
        self.client.post("/api/v1/cinema/workflows/workflow-one/co-watch", json={"participate": False})
        self.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        with patch("houseos.cinema.inspect_destination", return_value={**observation, "position": 30}):
            self.client.post("/api/v1/cinema/workflows/workflow-one/observe", json={"version": 2})
        self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
        self.assertEqual(self.client.get("/api/v1/cinema/state").json()["items"][0]["position"], 12)

    def test_autoplay_never_adds_or_selects_rd_files(self):
        import houseos.cinema as cinema

        self.workflow()
        with Session(self.engine, expire_on_commit=False) as db:
            series = CinemaTitle(
                id="series-one", canonical_id="tt999", title="Synthetic Series", kind="series", data={}
            )
            db.add(series)
            db.get(CinemaTitle, self.title_id).data = {"parent_id": series.id}
            row = db.get(CinemaWorkflow, "workflow-one")
            row.data = {
                **row.data,
                "request": {"autoplay": True},
                "_autoplay_expires_at": (utcnow() + timedelta(hours=1)).isoformat(),
                "_boot_id": cinema.boot_identity(),
                "_selected_source": "source-one",
                "season": 1,
                "episode": 1,
                "_sources": [{"id": "source-one", "torrent_id": "existing-pack"}],
            }
            db.commit()
            with (
                patch("houseos.cinema.next_episode", return_value={"episode": {"season": 1, "episode": 2}}),
                patch("houseos.cinema.RealDebrid") as rd,
            ):
                rd.return_value.info.return_value = {
                    "status": "downloaded",
                    "files": [{"id": 20, "path": "Show.S01E02.mkv", "selected": 0}],
                }
                with self.assertRaisesRegex(MediaError, "AUTOPLAY_NEEDS_CONFIRMATION"):
                    cinema.prepare_autoplay(db, row, self.actor)
                rd.return_value.add.assert_not_called()
                rd.return_value.select.assert_not_called()
                row.data = {**row.data, "_boot_id": "previous-boot"}
                self.assertIsNone(cinema.prepare_autoplay(db, row, self.actor))

    def test_tv_confirmations_are_actor_bound_and_not_retried(self):
        with Session(self.engine) as db:
            device = db.get(CinemaDevice, self.device_id)
            device.capabilities = {**device.capabilities, "power_off": True}
            db.commit()
        observation = {
            "state": "playing",
            "changed_at": "fixture-time",
            "volume": 0.2,
            "input": "HDMI",
            "inputs": ["HDMI"],
        }
        config = {
            "enabled": True,
            "base_url": "http://127.0.0.1:8123",
            "token": "fixture-not-secret",
            "device_id": "media_player.fixture",
            "receiver_id": self.device_id,
        }
        with (
            patch("houseos.cinema_tv.integration_config", return_value=config),
            patch("houseos.cinema_tv.tv_observation", return_value=observation),
            patch("houseos.cinema_tv.refresh_actor", side_effect=lambda db, actor: actor),
            patch(
                "houseos.cinema_tv.private_json",
                side_effect=MediaError("PROVIDER_UNAVAILABLE", "Fixture unavailable"),
            ) as send,
        ):
            preview = self.client.post(
                "/api/v1/cinema/devices/device-one/tv-prepare", json={"version": 1, "action": "power_off"}
            )
            self.assertEqual(preview.status_code, 200)
            confirmation_id = preview.json()["confirmation_id"]
            self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
            self.assertEqual(
                self.client.post("/api/v1/cinema/device-confirmations/" + confirmation_id).status_code, 404
            )
            self.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
            first = self.client.post("/api/v1/cinema/device-confirmations/" + confirmation_id)
            second = self.client.post("/api/v1/cinema/device-confirmations/" + confirmation_id)
            self.assertEqual(first.json()["state"], "command_outcome_unknown")
            self.assertEqual(first.json(), second.json())
            self.assertEqual(send.call_count, 1)

    def test_episode_history_rediscovery_uses_parent_series(self):
        with Session(self.engine) as db:
            db.add(
                CinemaTitle(id="series-parent", canonical_id="tt999", title="Series", kind="series", data={})
            )
            db.add(
                CinemaTitle(
                    id="episode-child",
                    canonical_id="tt999:2:3",
                    title="Episode",
                    kind="episode",
                    data={"parent_id": "series-parent", "season": 2, "episode": 3},
                )
            )
            db.commit()
        with (
            patch("houseos.cinema.inspect_destination", return_value={"state": "idle"}),
            patch("houseos.cinema.Comet") as comet,
        ):
            comet.return_value.streams.return_value = []
            result = self.client.post(
                "/api/v1/cinema/discover",
                json={
                    "media_id": "episode-child",
                    "device_id": self.device_id,
                    "idempotency_key": "history-resume",
                },
            )
            self.assertEqual(result.status_code, 200, result.text)
            comet.return_value.streams.assert_called_once_with("tt999", "series", 2, 3)
            self.assertEqual(result.json()["media_id"], "episode-child")
            self.assertEqual(result.json()["episode"], 3)
            mismatch = self.client.post(
                "/api/v1/cinema/discover",
                json={
                    "media_id": "episode-child",
                    "device_id": self.device_id,
                    "season": 1,
                    "episode": 1,
                    "idempotency_key": "wrong-history",
                },
            )
            self.assertEqual(mismatch.status_code, 422)
            self.assertEqual(comet.return_value.streams.call_count, 1)

    def test_same_destination_track_change_prepares_exact_track_without_playing(self):
        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.state = "playing_observed"
            db.get(CinemaDevice, self.device_id).owner_workflow = row.id
            media = copy.deepcopy(self.media)
            media["audio"].append(
                {"id": "2", "codec": "aac", "language": "fr", "channels": 2, "url": "PRIVATE-UPSTREAM"}
            )
            source = {**row.data["_sources"][0], "inspection": media}
            row.data = {
                **row.data,
                "_selected_source": source["id"],
                "_sources": [source],
                "checkpoint": {"position": 25},
            }
            db.commit()
        with (
            patch("houseos.cinema.inspect_destination", return_value={"state": "active"}),
            patch("houseos.cinema.execute_play") as play,
        ):
            result = self.client.post(
                "/api/v1/cinema/workflows/workflow-one/change",
                json={"version": 1, "device_id": self.device_id, "preferences": {"audio_track": "2"}},
            )
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["plan"]["audio"]["id"], "2")
            self.assertEqual(result.json()["plan"]["position"], 25)
            tracks = result.json()["plan"]["available_tracks"]["audio"]
            self.assertEqual([t["id"] for t in tracks], ["1", "2"])
            self.assertNotIn("url", tracks[1])
            self.assertTrue(result.json()["confirmation_id"])
            replacement = result.json()
            self.assertNotEqual(replacement["id"], "workflow-one")
            original = self.client.get("/api/v1/cinema/workflows/workflow-one").json()
            self.assertEqual(original["state"], "playing_observed")
            self.assertEqual(original["version"], 1)
            cancelled = self.client.post(
                "/api/v1/cinema/workflows/" + replacement["id"] + "/cancel",
                json={"version": replacement["version"]},
            )
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(
                self.client.get("/api/v1/cinema/workflows/workflow-one").json()["state"], "playing_observed"
            )
            with Session(self.engine) as db:
                self.assertEqual(db.get(CinemaDevice, self.device_id).owner_workflow, "workflow-one")
            play.assert_not_called()

    def test_source_switch_clears_track_ids_and_does_not_copy_another_cut_position(self):
        self.workflow()
        with Session(self.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            other = {
                **row.data["_sources"][0],
                "id": "source-two",
                "jellyfin_source": "other-cut",
                "release": "Edition B",
            }
            row.data = {
                **row.data,
                "request": {"audio_track": "99", "subtitle_track": "88"},
                "_selected_source": "source-one",
                "_sources": row.data["_sources"] + [other],
                "choice_set": {**row.data["choice_set"], "candidates": [{"id": "source-two"}]},
                "plan": {"release_key": "release-one"},
                "checkpoint": {"position": 25},
            }
            db.commit()
        with patch("houseos.cinema.inspect_destination", return_value={"state": "idle"}):
            result = self.client.post(
                "/api/v1/cinema/workflows/workflow-one/change",
                json={"version": 1, "source_choice": "source-two"},
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["plan"]["audio"]["id"], "1")
        self.assertEqual(result.json()["plan"]["position"], 0)
        self.assertTrue(any("different release" in warning for warning in result.json()["plan"]["warnings"]))

    def test_local_browse_keeps_user_watch_state_and_paginated_catalog(self):
        self.client.put("/api/v1/cinema/state/title-one", json={"favorite": True})
        with patch("houseos.cinema.Jellyfin") as jellyfin:
            jellyfin.return_value.library.return_value = {
                "Items": [
                    {
                        "Id": "item-one",
                        "ProviderIds": {"Imdb": "tt123"},
                        "Name": "Synthetic Film",
                        "Type": "Movie",
                    }
                ],
                "TotalRecordCount": 50,
            }
            result = self.client.get("/api/v1/cinema/library?kind=movie")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["next_offset"], 30)
            self.assertTrue(result.json()["items"][0]["favorite"])
            self.actor = Actor("resident-two", "Two", "resident", frozenset({"cinema.use"}))
            self.assertNotIn("favorite", self.client.get("/api/v1/cinema/library").json()["items"][0])

    def test_explicit_cloud_selection_does_not_depend_on_discovery_or_mutate_rd(self):
        from houseos.cinema import cloud_id

        with (
            patch("houseos.cinema.inspect_destination", return_value={"state": "idle"}),
            patch("houseos.cinema.integration_config", return_value={"enabled": True}),
            patch("houseos.cinema.RealDebrid") as rd,
            patch("houseos.cinema.Comet") as comet,
        ):
            rd.return_value.inventory.return_value = [
                {
                    "id": "existing-torrent",
                    "hash": "a" * 40,
                    "filename": "Synthetic Film.mkv",
                    "bytes": 100,
                    "status": "downloaded",
                }
            ]
            result = self.client.post(
                "/api/v1/cinema/discover",
                json={
                    "media_id": self.title_id,
                    "device_id": self.device_id,
                    "cloud_id": cloud_id("existing-torrent"),
                    "idempotency_key": "cloud-direct",
                },
            )
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["provisional"][0]["layer"], "RD_CLOUD")
            comet.assert_not_called()
            rd.return_value.add.assert_not_called()
            rd.return_value.select.assert_not_called()
            rd.return_value.resolve.assert_not_called()
            preview = self.client.post(
                "/api/v1/cinema/workflows/" + result.json()["id"] + "/validate",
                json={"version": result.json()["version"]},
            )
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()["preview"]["selected_title"], "Synthetic Film")
            self.assertIn("no new torrent", preview.json()["preview"]["effects"])
            rd.return_value.resolve.assert_not_called()

    def test_guest_denied(self):
        self.actor = Actor("party", "Party", "guest", frozenset({"music.read"}))
        self.assertEqual(self.client.get("/api/v1/cinema/devices").status_code, 403)

    def test_rd_file_mapping_uses_selected_actual_ids(self):
        rd = RealDebrid({"enabled": True, "token": "fixture-not-secret", "entitlement_confirmed": True})
        manifest = {
            "status": "downloaded",
            "files": [{"id": 12, "selected": 0}, {"id": 67, "selected": 1}, {"id": 99, "selected": 1}],
            "links": ["first-link", "second-link"],
        }
        with (
            patch.object(rd, "info", return_value=manifest),
            patch.object(
                rd, "call", return_value={"download": "https://example.org/film", "filesize": 100}
            ) as api,
            patch("houseos.cinema_adapters.public_url"),
        ):
            rd.resolve("torrent", "99")
            self.assertEqual(api.call_args.kwargs["form"]["link"], "second-link")
            with self.assertRaisesRegex(MediaError, "EPISODE_MISMATCH"):
                rd.resolve("torrent", "12")

    def test_public_fetch_rejects_private_dns_and_userinfo(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaisesRegex(MediaError, "UNSAFE_SOURCE"):
                public_url("https://public-looking.example/film")
        with self.assertRaisesRegex(MediaError, "UNSAFE_SOURCE"):
            public_url("https://secret@www.example.com/film")


if __name__ == "__main__":
    unittest.main()
