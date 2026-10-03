import pytest
from types import SimpleNamespace
from unittest.mock import Mock
from houseos import cinema_cast


def test_transport_fetches_session_before_pause(monkeypatch):
    controller = SimpleNamespace(
        status=SimpleNamespace(media_session_id=None), update_status=Mock(), pause=Mock()
    )
    controller.is_active = True

    def status_request(message, **kwargs):
        assert message == {"type": "GET_STATUS"}
        kwargs["callback_function"](
            True, {"type": "MEDIA_STATUS", "status": [{"mediaSessionId": 12, "playerState": "PAUSED"}]}
        )

    controller.send_message_nocheck = status_request
    cast = SimpleNamespace(media_controller=controller, disconnect=Mock())
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    cinema_cast.cast_control("192.0.2.19", "pause", None)
    controller.pause.assert_called_once()
    controller.update_status.assert_not_called()
    cast.disconnect.assert_called_once()


@pytest.mark.parametrize("paused", [False, True])
def test_load_switches_receiver_and_checks_exact_media(monkeypatch, paused):
    import hashlib
    from houseos.config import settings
    from houseos.db import new_id

    controller = SimpleNamespace(
        status=SimpleNamespace(content_id=None, media_session_id=None, player_state="IDLE"),
        update_status=Mock(),
    )
    cast = SimpleNamespace(media_controller=controller, start_app=Mock(), disconnect=Mock())

    def play(url, *args, **kwargs):
        cast.start_app.assert_called_once_with("CC1AD845", timeout=10)
        assert kwargs["autoplay"] is not paused
        controller.status = SimpleNamespace(content_id=url, media_session_id=1, player_state="PLAYING")

    controller.play_media = play
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    monkeypatch.setattr(cinema_cast, "preflight_cast", lambda *a: None)
    monkeypatch.setattr(
        cinema_cast, "integration_config", lambda *a, **k: {"receiver_base_url": "http://192.0.2.17:8991"}
    )
    from houseos import cinema

    monkeypatch.setattr(cinema, "authorize_workflow", lambda *a: None)
    row = SimpleNamespace(
        id=new_id(),
        data={
            "_prepared": {"path": str(settings.runtime_root / "cinema/test.mp4")},
            "_seek_previous": {"state": "paused"} if paused else None,
        },
    )
    db = SimpleNamespace(add=Mock(), commit=Mock())
    assert cinema_cast.execute_cast(
        db,
        row,
        SimpleNamespace(address="192.0.2.19"),
        {"inspection": {"container": "mp4"}},
        {"duration": 20},
    )
    assert (
        row.data["plan"]["expected_item"] == hashlib.sha256(controller.status.content_id.encode()).hexdigest()
    )
    cast.disconnect.assert_called_once()


def test_rejected_video_is_not_reported_as_loaded_subtitle_failure(monkeypatch):
    import pytest
    from houseos.playback import MediaError
    from houseos.db import new_id
    from houseos import cinema

    controller = SimpleNamespace(status=None, update_status=Mock())

    def load(url, *a, **kw):
        controller.status = SimpleNamespace(
            content_id=url, media_session_id=1, player_state="IDLE", idle_reason="ERROR"
        )

    controller.play_media = load
    cast = SimpleNamespace(media_controller=controller, start_app=Mock(), disconnect=Mock())
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    monkeypatch.setattr(cinema_cast, "preflight_cast", lambda *a: None)
    monkeypatch.setattr(
        cinema_cast, "integration_config", lambda *a, **k: {"receiver_base_url": "http://192.0.2.17:8991"}
    )
    monkeypatch.setattr(cinema, "authorize_workflow", lambda *a: None)
    row = SimpleNamespace(id=new_id(), data={"_prepared": {"path": "/tmp/test.mp4"}})
    with pytest.raises(MediaError) as caught:
        cinema_cast.execute_cast(
            SimpleNamespace(add=Mock(), commit=Mock()),
            row,
            SimpleNamespace(address="192.0.2.19"),
            {"inspection": {"container": "mp4"}},
            {"duration": 20, "subtitle": {"language": "en"}, "subtitle_mode": "webvtt"},
        )
    assert caught.value.code == "PLAYBACK_REJECTED"
    assert "before playback started" in caught.value.message


@pytest.mark.parametrize(
    "content,app,expected,closes",
    [
        ("", "CC1AD845", set(), True),
        ("our-media", "CC1AD845", {__import__("hashlib").sha256(b"our-media").hexdigest()}, True),
        ("", "OTHERAPP", set(), False),
    ],
)
def test_abort_closes_idle_receiver_without_requiring_active_video(
    monkeypatch, content, app, expected, closes
):
    cast = SimpleNamespace(
        media_controller=SimpleNamespace(update_status=Mock(), status=SimpleNamespace(content_id=content)),
        status=SimpleNamespace(app_id=app),
        quit_app=Mock(),
        disconnect=Mock(),
    )
    monkeypatch.setattr(cinema_cast, "fresh_media_status", lambda c: c.media_controller.status)
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    cinema_cast.abort_cast("fixture", expected)
    assert cast.quit_app.called == closes
    cast.disconnect.assert_called_once()


def test_abort_preserves_another_cast_item(monkeypatch):
    from houseos.playback import MediaError

    cast = SimpleNamespace(
        media_controller=SimpleNamespace(
            update_status=Mock(), status=SimpleNamespace(content_id="another-movie")
        ),
        status=SimpleNamespace(app_id="CC1AD845"),
        quit_app=Mock(),
        disconnect=Mock(),
    )
    monkeypatch.setattr(cinema_cast, "fresh_media_status", lambda c: c.media_controller.status)
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    with pytest.raises(MediaError):
        cinema_cast.abort_cast("fixture", {"previous-hash"})
    cast.quit_app.assert_not_called()


@pytest.mark.parametrize("state,resume", [("PAUSED", "PLAYBACK_PAUSE"), ("PLAYING", "PLAYBACK_START")])
def test_native_seek_preserves_pause_and_waits_for_ack(monkeypatch, state, resume):
    controller = SimpleNamespace(
        status=SimpleNamespace(media_session_id=7, player_state=state),
        update_status=Mock(),
        block_until_active=Mock(),
    )

    def send(message, **kwargs):
        assert message == {"type": "SEEK", "mediaSessionId": 7, "currentTime": 123, "resumeState": resume}
        kwargs["callback_function"](True, {"type": "MEDIA_STATUS"})

    controller.send_message = send
    cast = SimpleNamespace(media_controller=controller, disconnect=Mock())
    monkeypatch.setattr(cinema_cast, "fresh_media_status", lambda c: c.media_controller.status)
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    cinema_cast.cast_control("fixture", "seek", 123)
    cast.disconnect.assert_called_once()


def test_observing_home_screen_never_launches_cast():
    controller = SimpleNamespace(is_active=False, update_status=Mock(), send_message_nocheck=Mock())
    status = cinema_cast.fresh_media_status(SimpleNamespace(media_controller=controller))
    assert status.media_session_id is None and status.player_state == "IDLE"
    controller.update_status.assert_not_called()
    controller.send_message_nocheck.assert_not_called()
