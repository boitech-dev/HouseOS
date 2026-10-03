from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
import test_cinema
from houseos import cinema
from houseos.models import Record
from houseos.auth import Actor


def test_cache_means_exact_selected_episode_and_link():
    rd = Mock()
    rd.info.return_value = {
        "status": "downloaded",
        "files": [
            {"id": 1, "path": "Show.S01E01.mkv", "selected": 1},
            {"id": 2, "path": "Show.S01E02.mkv", "selected": 0},
        ],
        "links": ["ready"],
    }
    assert cinema.exact_cached_file(rd, "one", 1, 1)
    assert not cinema.exact_cached_file(rd, "one", 1, 2)
    rd.info.return_value["links"] = [""]
    assert not cinema.exact_cached_file(rd, "one", 1, 1)
    sources = [
        {"id": "a", "height_claim": 2160, "seeders_claim": 50},
        {"id": "b", "height_claim": 1080, "rd_cached": True},
        {"id": "c", "height_claim": 2160, "seeders_claim": 100},
    ]
    assert [s["id"] for s in sorted(sources, key=cinema.source_order)] == ["b", "c", "a"]


def test_queue_private_idempotency_tombstone_and_movie_identity():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        body = {"media_id": f.title_id, "idempotency_key": "same-queue-request"}
        one = f.client.post("/api/v1/cinema/queue", json=body).json()
        assert one["status"] == "queued"
        assert f.client.post("/api/v1/cinema/queue", json={**body, "episode": 2}).status_code == 422
        f.actor = Actor("other", "Other", "resident", frozenset({"cinema.use"}))
        assert f.client.get("/api/v1/cinema/queue").json()["items"] == []
        assert f.client.delete("/api/v1/cinema/queue/" + one["queue_id"]).status_code == 404
        f.actor = Actor("resident-one", "One", "resident", frozenset({"cinema.use"}))
        assert f.client.delete("/api/v1/cinema/queue/" + one["queue_id"]).status_code == 200
        assert f.client.post("/api/v1/cinema/queue", json=body).json()["status"] == "removed"
        assert not f.client.get("/api/v1/cinema/queue").json()["items"]
        with Session(f.engine) as db:
            assert db.get(Record, one["queue_id"]).deleted_at
    finally:
        f.tearDown()


def test_single_play_retains_material_preparation_preview():
    with (
        patch.object(
            cinema,
            "choose_destination",
            return_value={"plan": {"mode": "direct"}, "confirmation_id": "exact"},
        ) as choose,
        patch.object(cinema, "confirm", return_value={"state": "command_sent"}) as confirm,
    ):
        assert (
            cinema.play_selected("one", cinema.DestinationChoice(version=1, device_id="screen"), None, None)[
                "state"
            ]
            == "command_sent"
        )
        confirm.assert_called_once_with("exact", None, None)
        for strategy in ("progressive_hls", "external_sidecar"):
            confirm.reset_mock()
            choose.return_value = {
                "plan": {"mode": "audio_convert", "preparation_strategy": strategy},
                "confirmation_id": "routine",
            }
            assert (
                cinema.play_selected(
                    "one", cinema.DestinationChoice(version=1, device_id="screen"), None, None
                )["state"]
                == "command_sent"
            )
            confirm.assert_called_once_with("routine", None, None)
        confirm.reset_mock()
        choose.return_value = {"plan": {"mode": "direct", "interrupts": True}, "confirmation_id": "interrupt"}
        assert (
            cinema.play_selected("one", cinema.DestinationChoice(version=1, device_id="screen"), None, None)[
                "confirmation_id"
            ]
            == "interrupt"
        )
        confirm.assert_not_called()
        confirm.reset_mock()
        choose.return_value = {
            "plan": {"mode": "remux", "preparation_strategy": "full_spool"},
            "confirmation_id": "costly",
        }
        assert (
            cinema.play_selected("one", cinema.DestinationChoice(version=1, device_id="screen"), None, None)[
                "confirmation_id"
            ]
            == "costly"
        )
        confirm.assert_not_called()


def test_real_srt_normalization_and_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    normalized = cinema.normalize_uploaded_subtitle("1\n00:00:01,000 --> 00:00:02,000\nBonjour\n")
    assert normalized.startswith("WEBVTT") and "Bonjour" in normalized
    with pytest.raises(HTTPException):
        cinema.normalize_uploaded_subtitle("not subtitle data")


def test_uploaded_subtitle_real_track_before_destination(tmp_path, monkeypatch):
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    try:
        with Session(f.engine) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            row.device_id = None
            row.data = {**row.data, "_destination_later": True}
            db.commit()
        selected = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/select",
            json={"version": 1, "choice_set_id": "choices-one", "choice": "1"},
        ).json()
        result = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/subtitles/upload",
            json={
                "version": selected["version"],
                "text": "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n",
                "language": "fr",
                "name": "French.srt",
            },
        )
        assert result.status_code == 200, result.text
        track = result.json()["selected_source"]["subtitles"][0]
        assert (
            track["codec"] == "webvtt"
            and track["language"] == "fr"
            and track["external"]
            and track["uploaded"]
        )
        assert result.json()["state"] == "awaiting_destination"
    finally:
        f.tearDown()


def test_queue_consumed_only_exact_entry_after_verified_observation():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        ids = [
            f.client.post(
                "/api/v1/cinema/queue", json={"media_id": f.title_id, "idempotency_key": key}
            ).json()["queue_id"]
            for key in ["queue-first", "queue-second"]
        ]
        with Session(f.engine) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            row.state = "command_sent"
            row.data = {
                **row.data,
                "_queue_id": ids[0],
                "_selected_source": "source-one",
                "plan": {
                    "expected_item": "fixture-film",
                    "duration": 100,
                    "audio": {"id": "1"},
                    "subtitle": None,
                },
            }
            db.get(cinema.CinemaDevice, f.device_id).owner_workflow = row.id
            db.commit()
        assert len(f.client.get("/api/v1/cinema/queue").json()["items"]) == 2
        observation = {
            "state": "active",
            "item_id": "fixture-film",
            "position": 12,
            "check_in": cinema.utcnow().isoformat() + "Z",
            "audio_index": 1,
            "subtitle_index": -1,
        }
        with patch.object(cinema, "inspect_destination", return_value=observation):
            observed = f.client.post("/api/v1/cinema/workflows/workflow-one/observe", json={"version": 1})
        assert observed.json()["state"] == "playing_observed", observed.text
        assert [i["queue_id"] for i in f.client.get("/api/v1/cinema/queue").json()["items"]] == [ids[1]]
    finally:
        f.tearDown()


def test_null_prior_plan_preflights_after_device_free_inspection():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            row.device_id = None
            row.state = "awaiting_destination"
            row.data = {**row.data, "plan": None, "_selected_source": "source-one"}
            db.commit()
        with patch.object(cinema, "inspect_destination", return_value={"state": "idle"}):
            result = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/destination",
                json={"version": 1, "device_id": f.device_id},
            )
        assert result.status_code == 200, result.text
        assert result.json()["selected_source"]["audio"][0]["id"] == "1"
    finally:
        f.tearDown()


def test_episode_history_keeps_positions_and_uses_series_poster():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with Session(f.engine) as db:
            parent = db.get(cinema.CinemaTitle, f.title_id)
            parent.kind = "series"
            parent.data = {"_poster_url": "https://example.invalid/poster.jpg"}
            for episode, position in [(1, 900), (2, 125)]:
                title = cinema.CinemaTitle(
                    id=f"episode-{episode}",
                    canonical_id=f"tt123:1:{episode}",
                    title=f"Fixture · S01E{episode:02}",
                    kind="episode",
                    data={"parent_id": parent.id, "season": 1, "episode": episode},
                )
                db.add(title)
                db.flush()
                db.add(
                    cinema.CinemaState(
                        owner_id=f.actor.id,
                        media_id=title.id,
                        data={"position": position, "duration": 1200, "watched": False},
                        last_watched_at=cinema.utcnow(),
                    )
                )
            db.commit()
        rows = f.client.get("/api/v1/cinema/state?filter=history").json()["items"]
        assert len(rows) == 2
        assert {r["position"] for r in rows} == {900, 125}
        assert all(
            r["poster"] == f"/api/v1/cinema/titles/{f.title_id}/poster"
            and r["series_title"] == "Synthetic Film"
            for r in rows
        )
    finally:
        f.tearDown()
