from unittest.mock import patch
from sqlalchemy.orm import Session
import test_cinema
from houseos.cinema import CinemaDevice
import houseos.cinema_tv  # noqa: F401 (registers the TV endpoints)


def test_reboot_is_not_tv_standby_and_mapped_display_confirmation_is_compact():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with (
            patch("houseos.cinema_tv.tv_observation") as observe,
            patch("houseos.cinema_tv.private_json") as send,
        ):
            result = f.client.post(
                "/api/v1/cinema/devices/device-one/tv-prepare", json={"version": 1, "action": "reboot"}
            )
            assert result.json()["detail"]["code"] == "CONTROL_UNSUPPORTED"
            observe.assert_not_called()
            send.assert_not_called()
        with Session(f.engine) as db:
            device = db.get(CinemaDevice, f.device_id)
            device.name = "Chromecast"
            device.capabilities = {**device.capabilities, "power_off": True}
            db.commit()
        config = {
            "enabled": True,
            "base_url": "http://127.0.0.1:8123",
            "token": "fixture",
            "device_id": "media_player.hisense",
            "receiver_id": f.device_id,
        }
        observation = {
            "display_name": "Hisense TV",
            "state": "playing",
            "changed_at": "fixture",
            "volume": 0.2,
            "input": "HDMI 2",
            "inputs": ["HDMI 2", *["Application"] * 30],
        }
        with (
            patch("houseos.cinema_tv.integration_config", return_value=config),
            patch("houseos.cinema_tv.tv_observation", return_value=observation),
            patch("houseos.cinema_tv.private_json") as send,
        ):
            result = f.client.post(
                "/api/v1/cinema/devices/device-one/tv-prepare", json={"version": 1, "action": "power_off"}
            )
            assert result.status_code == 200, result.text
            preview = result.json()["preview"]
            assert preview["destination"] == "Hisense TV"
            assert "does not reboot" in preview["summary"]
            assert "current_state" not in preview and "inputs" not in preview
            config["device_id"] = "media_player.another_display"
            confirmed = f.client.post(
                "/api/v1/cinema/device-confirmations/" + result.json()["confirmation_id"]
            )
            assert confirmed.json()["detail"]["code"] == "PLAN_STALE"
            send.assert_not_called()
    finally:
        f.tearDown()
