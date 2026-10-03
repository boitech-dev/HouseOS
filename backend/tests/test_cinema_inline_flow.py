import pytest
from unittest.mock import patch
from sqlalchemy.orm import Session
import test_cinema
from houseos.cinema import CinemaWorkflow


def test_device_free_discovery_and_exact_selected_validation():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with (
            patch("houseos.cinema.inspect_destination") as inspect,
            patch("houseos.cinema.Comet") as comet,
            patch("houseos.cinema.integration_config", return_value={}),
        ):
            comet.return_value.streams.return_value = [
                {
                    "info_hash": "a" * 40,
                    "release": "Exact release",
                    "state": "discovered",
                    "evidence": "provider_claim",
                }
            ]
            response = f.client.post(
                "/api/v1/cinema/discover",
                json={"media_id": f.title_id, "idempotency_key": "device-free-test"},
            )
            assert response.status_code == 200
            row = response.json()
            assert row["device_id"] is None and row["state"] == "discovered"
            assert row["provisional"][0]["evidence"] == "provider_claim"
            inspect.assert_not_called()
        with patch("houseos.cinema.RealDebrid"):
            selected = row["provisional"][0]["id"]
            prepared = f.client.post(
                "/api/v1/cinema/workflows/" + row["id"] + "/validate",
                json={"version": row["version"], "source_ids": [selected]},
            )
            assert prepared.status_code == 200
            preview = prepared.json()["preview"]
            assert [s["id"] for s in preview["sources"]] == [selected]
            assert "at most 1 torrent" in preview["effects"]
        assert (
            f.client.post(
                "/api/v1/cinema/workflows/" + row["id"] + "/observe",
                json={"version": prepared.json()["version"]},
            ).json()["detail"]["code"]
            == "DESTINATION_OWNERSHIP_LOST"
        )
    finally:
        f.tearDown()


def test_inspected_tracks_before_destination_and_play_confirmation():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.device_id = None
            row.data = {**row.data, "_destination_later": True}
            db.commit()
        chosen = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/select",
            json={"version": 1, "choice_set_id": "choices-one", "choice": "1"},
        )
        assert chosen.status_code == 200
        payload = chosen.json()
        assert payload["state"] == "awaiting_destination" and payload["device_id"] is None
        assert payload["selected_source"]["audio"][0]["id"] == "1"
        assert not payload.get("confirmation_id")
        with patch("houseos.cinema.inspect_destination", return_value={"state": "idle"}):
            reviewed = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/destination",
                json={
                    "version": payload["version"],
                    "device_id": f.device_id,
                    "preferences": {"audio_track": "1", "subtitles_on": False},
                },
            )
        assert reviewed.status_code == 200, reviewed.text
        plan = reviewed.json()
        assert plan["state"] == "awaiting_playback_confirmation"
        assert plan["confirmation_id"] and plan["plan"]["audio"]["id"] == "1"
        assert plan["plan"]["subtitle"] is None
        # Changing version revalidates state and never starts the physical receiver.
        assert (
            f.client.post(
                "/api/v1/cinema/workflows/workflow-one/destination",
                json={"version": payload["version"], "device_id": f.device_id},
            ).status_code
            == 409
        )
    finally:
        f.tearDown()


@pytest.mark.parametrize("existing", [False, True])
def test_single_explicit_version_inspection_advances_to_real_tracks(tmp_path, monkeypatch, existing):
    from houseos import cinema

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)
    try:
        with Session(f.engine, expire_on_commit=False) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            row.device_id, row.state = None, "preparing"
            row.data = {
                **row.data,
                "_destination_later": True,
                "_validation_selection": ["source-one"],
                "_sources": [
                    {
                        "id": "source-one",
                        "info_hash": "a" * 40,
                        "release": "Exact chosen version",
                        "layer": "ON_DEMAND",
                        "state": "discovered",
                    }
                ],
            }
            db.commit()
            with (
                patch.object(cinema, "RealDebrid") as rd,
                patch("houseos.cinema_sources.probe_media", return_value=f.media),
            ):
                rd.return_value.inventory.return_value = (
                    [{"id": "fixture-existing", "hash": "a" * 40, "status": "downloaded"}] if existing else []
                )
                rd.return_value.add.return_value = "fixture-remote"
                rd.return_value.info.return_value = {
                    "status": "downloaded",
                    "files": [{"id": 1, "path": "/movie.mkv", "bytes": 1000}],
                }
                rd.return_value.resolve.return_value = ("https://example.com/fixture", 1000)
                result = cinema.validate_rd(db, row, ["source-one"])
                if existing:
                    rd.return_value.add.assert_not_called()
                    rd.return_value.info.assert_called_with("fixture-existing")
            assert result["state"] == "awaiting_destination"
            assert result["selected_source"]["id"] == "source-one"
            assert result["selected_source"]["audio"][0]["id"] == f.media["audio"][0]["id"]
            assert result["device_id"] is None and result["confirmation_id"] is None
    finally:
        f.tearDown()


def test_downloaded_duplicate_wins_and_old_add_block_does_not_hide_it():
    import hashlib
    from houseos import cinema

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            old = db.get(CinemaWorkflow, "workflow-one")
            old.data = {
                **old.data,
                "_rd_account_key": hashlib.sha256(b"fixture").hexdigest()[:24],
                "_sources": [
                    {
                        "info_hash": "a" * 40,
                        "error": {"code": "SOURCE_REJECTED", "operation": "add_magnet", "provider_code": 35},
                    }
                ],
            }
            db.commit()
        config = lambda db, name: {"enabled": True, "token": "fixture"} if name == "real_debrid" else {}
        with (
            patch.object(cinema, "integration_config", side_effect=config),
            patch.object(cinema, "Comet") as comet,
            patch.object(cinema, "RealDebrid") as rd,
            patch.object(cinema, "exact_cached_file", return_value=True),
        ):
            comet.return_value.streams.return_value = [
                {"info_hash": "a" * 40, "release": "Fixture", "state": "discovered"}
            ]
            rd.return_value.inventory.return_value = [
                {"id": "ready", "hash": "a" * 40, "status": "downloaded"},
                {"id": "pending", "hash": "a" * 40, "status": "magnet_conversion"},
            ]
            result = f.client.post(
                "/api/v1/cinema/discover",
                json={"media_id": f.title_id, "idempotency_key": "fresh-account-entry"},
            )
            assert result.status_code == 200, result.text
            with Session(f.engine) as db:
                source = db.get(CinemaWorkflow, result.json()["id"]).data["_sources"][0]
                assert source["torrent_id"] == "ready" and source["rd_cached"] and not source.get("error")
            rd.return_value.add.assert_not_called()
    finally:
        f.tearDown()
