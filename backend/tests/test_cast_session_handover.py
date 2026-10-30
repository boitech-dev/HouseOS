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
def test_load_switches_receiver_and_checks_exact_media(monkeypatch, paused, tmp_path):
    import hashlib
    from houseos.config import settings
    from houseos.db import new_id

    controller = SimpleNamespace(
        status=SimpleNamespace(content_id=None, media_session_id=None, player_state="IDLE", current_time=0)
    )
    # Its clock moves while it plays (the load is checked to really play).
    controller.update_status = lambda: setattr(
        controller.status, "current_time", controller.status.current_time + 1
    )
    cast = SimpleNamespace(media_controller=controller, start_app=Mock(), disconnect=Mock())

    def play(url, *args, **kwargs):
        cast.start_app.assert_called_once_with("CC1AD845", timeout=10)
        assert kwargs["autoplay"] is not paused
        controller.status = SimpleNamespace(
            content_id=url, media_session_id=1, player_state="PLAYING", current_time=0
        )

    controller.play_media = play
    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    monkeypatch.setattr(cinema_cast, "preflight_cast", lambda *a: None)
    monkeypatch.setattr(
        cinema_cast, "integration_config", lambda *a, **k: {"receiver_base_url": "http://192.0.2.17:8991"}
    )
    from houseos import cinema

    monkeypatch.setattr(cinema, "authorize_workflow", lambda *a: None)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    film = tmp_path / "cinema/test.mp4"  # the prepared copy is on disk
    film.parent.mkdir()
    film.touch()
    row = SimpleNamespace(
        id=new_id(),
        data={
            "_prepared": {"path": str(film)},
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


def test_rejected_video_is_not_reported_as_loaded_subtitle_failure(monkeypatch, tmp_path):
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
    (tmp_path / "test.mp4").touch()
    row = SimpleNamespace(id=new_id(), data={"_prepared": {"path": str(tmp_path / "test.mp4")}})
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


def test_a_prepared_copy_that_was_cleaned_up_is_prepared_again(monkeypatch):
    from unittest.mock import Mock

    from houseos.db import new_id

    monkeypatch.setattr(cinema_cast, "preflight_cast", lambda *a: None)
    monkeypatch.setattr(cinema_cast, "cast_config", lambda db: {})
    row = SimpleNamespace(
        id=new_id(), owner_id="u", version=3, data={"_prepared": {"path": "/nowhere/gone.m3u8"}}
    )
    db = SimpleNamespace(add=Mock(), commit=Mock())
    plan = {"preparation_strategy": "progressive"}
    assert cinema_cast.execute_cast(db, row, SimpleNamespace(), {}, plan) is False  # queued again
    assert row.data["_prepared"] is None and db.add.call_args[0][0].state == "queued"


def test_a_big_streamed_version_needs_only_room_on_the_disk(monkeypatch, tmp_path):
    import shutil
    from collections import namedtuple

    import pytest

    from houseos.config import settings

    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "encryption_key", "fixture-key")
    gb = 1024**3
    space = namedtuple("usage", "total used free")
    plan = {
        "mode": "audio_convert",
        "audio": {"default": True},
        "subtitle_mode": "off",
        "video_copied": True,
        "video": {"codec": "hevc"},
        "warnings": [],
    }
    source = {"size": int(82.1 * gb)}  # 4K Dolby Vision, over the old 80 GiB cap
    config = {"enabled": True, "receiver_base_url": "http://192.0.2.17:8991"}
    monkeypatch.setattr(shutil, "disk_usage", lambda path: space(0, 0, 117 * gb))
    cinema_cast.preflight_cast(config, source, dict(plan))  # streamed: fits in 117 GB free
    monkeypatch.setattr(shutil, "disk_usage", lambda path: space(0, 0, 60 * gb))
    with pytest.raises(cinema_cast.MediaError) as full:
        cinema_cast.preflight_cast(config, source, dict(plan))
    assert "GB are free" in full.value.message


def test_a_stream_the_chromecast_starts_at_its_newest_point_goes_back_to_where_it_was_asked():
    from unittest.mock import Mock

    controller = Mock()
    controller.status = SimpleNamespace(current_time=443.7)  # asked for 0:00, it started at 7:23
    cast = SimpleNamespace(media_controller=controller)
    assert cinema_cast.back_to_start(cast, 0, settle=0.5)
    controller.seek.assert_called_once_with(0)
    controller.seek.reset_mock()
    controller.status = SimpleNamespace(current_time=2.0)  # where it was asked: left alone
    assert not cinema_cast.back_to_start(cast, 0, settle=0.3)
    controller.seek.assert_not_called()


def test_a_new_film_closes_the_receiver_app_before_loading(monkeypatch):
    closed = []
    cast = SimpleNamespace(
        media_controller=SimpleNamespace(stop=Mock()),
        status=SimpleNamespace(app_id="CC1AD845"),
    )

    def quit_app(timeout):
        closed.append(timeout)
        cast.status.app_id = None  # the app is gone

    cast.quit_app = quit_app
    monkeypatch.setattr(
        cinema_cast,
        "fresh_media_status",
        lambda c: SimpleNamespace(player_state="PLAYING", media_session_id=7),
    )
    cinema_cast.stop_current(cast, wait=1)
    assert closed == [1] and not cast.media_controller.stop.called  # closed, as Stop does: not paused
    # An idle screen (an episode that ended) has nothing to close; a receiver that will not
    # answer does not block the load.
    monkeypatch.setattr(
        cinema_cast,
        "fresh_media_status",
        lambda c: SimpleNamespace(player_state="IDLE", media_session_id=None),
    )
    cinema_cast.stop_current(cast)
    monkeypatch.setattr(cinema_cast, "fresh_media_status", Mock(side_effect=RuntimeError))
    cinema_cast.stop_current(cast)
    assert closed == [1]


def fake_receiver(behaviour):
    """A Chromecast whose loads behave as `behaviour(n)` says: "playing", "paused" or "ended"."""
    loads, quits = [], []
    controller = SimpleNamespace(status=None)
    cast = SimpleNamespace(media_controller=controller, start_app=Mock(), disconnect=Mock())

    def load(url, *a, **kw):
        loads.append(url)
        state = behaviour(len(loads))
        controller.status = SimpleNamespace(
            content_id=url, media_session_id=1, current_time=0.0,
            player_state={"playing": "PLAYING", "paused": "PAUSED", "ended": "BUFFERING"}[state],
        )  # fmt: skip
        controller.state = state

    def update_status():
        status = controller.status
        if controller.state == "playing":
            status.current_time += 1
        elif controller.state == "ended" and status.player_state == "BUFFERING":
            status.player_state, status.content_id = "IDLE", None  # reported, then gone at once

    controller.play_media, controller.update_status = load, update_status
    controller.play = lambda: setattr(controller, "state", controller.state)  # ignored, as it was
    cast.quit_app = lambda timeout: quits.append(timeout)
    return cast, loads, quits


def cast_setup(monkeypatch, tmp_path, cast):
    from houseos import cinema

    monkeypatch.setattr(cinema_cast, "connect", lambda _: cast)
    monkeypatch.setattr(cinema_cast, "stop_current", lambda c: None)
    monkeypatch.setattr(cinema_cast, "preflight_cast", lambda *a: None)
    monkeypatch.setattr(cinema_cast, "SETTLE", 0)
    monkeypatch.setattr(cinema_cast.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        cinema_cast, "integration_config", lambda *a, **k: {"receiver_base_url": "http://192.0.2.17:8991"}
    )
    monkeypatch.setattr(cinema, "authorize_workflow", lambda *a: None)
    (tmp_path / "film.mp4").touch()


def send(tmp_path, seek_previous=None):
    from houseos.db import new_id

    row = SimpleNamespace(
        id=new_id(), data={"_prepared": {"path": str(tmp_path / "film.mp4")}, "_seek_previous": seek_previous}
    )
    return cinema_cast.execute_cast(
        SimpleNamespace(add=Mock(), commit=Mock()),
        row,
        SimpleNamespace(address="192.0.2.19"),
        {"inspection": {"container": "mp4"}},
        {"duration": 20},
    )


def test_a_load_that_does_not_really_play_is_loaded_once_more(monkeypatch, tmp_path):
    import pytest

    from houseos.playback import MediaError

    # Paused at the start, then playing on the second load (the Stop then Play that works by hand).
    cast, loads, quits = fake_receiver(lambda n: "paused" if n == 1 else "playing")
    cast_setup(monkeypatch, tmp_path, cast)
    assert send(tmp_path) and len(loads) == 2 and len(quits) == 1
    # Playing at once: one load, nothing closed.
    cast, loads, quits = fake_receiver(lambda n: "playing")
    cast_setup(monkeypatch, tmp_path, cast)
    assert send(tmp_path) and len(loads) == 1 and not quits
    # A film paused before a seek's reload stays paused: no second load.
    cast, loads, quits = fake_receiver(lambda n: "paused")
    cast_setup(monkeypatch, tmp_path, cast)
    assert send(tmp_path, {"state": "paused"}) and len(loads) == 1
    # Never playing, twice: said so, not reported as playing.
    cast, loads, quits = fake_receiver(lambda n: "paused")
    cast_setup(monkeypatch, tmp_path, cast)
    with pytest.raises(MediaError):
        send(tmp_path)
    assert len(loads) == 2


def test_a_slow_file_is_sent_once_complete_a_fast_one_at_once(monkeypatch, tmp_path):
    from houseos import cinema_progressive as p

    playlist = tmp_path / "video.m3u8"

    def grows(by):
        def sleep(seconds):
            playlist.write_text(playlist.read_text() + "#EXTINF:%.1f,\nseg.m4s\n" % (by * seconds))

        return sleep

    playlist.write_text("#EXTM3U\n#EXTINF:4.0,\nseg0.m4s\n")
    monkeypatch.setattr(p.time, "sleep", grows(2))  # 2 s of film per second: slower than it plays well
    assert p.slow(tmp_path) and p.prepared_seconds(tmp_path) == 10
    monkeypatch.setattr(p.time, "sleep", grows(30))
    assert not p.slow(tmp_path)
    playlist.write_text(playlist.read_text() + "#EXT-X-ENDLIST\n")
    assert p.complete(tmp_path) and not p.slow(tmp_path)


def test_a_slow_start_still_buffering_is_not_loaded_again():
    status = SimpleNamespace(content_id="u", player_state="BUFFERING", current_time=0)
    cast = SimpleNamespace(media_controller=SimpleNamespace(status=status, update_status=lambda: None))
    assert cinema_cast.playing(cast, "u", seconds=0.6)  # buffering the whole time: left to play
    status.player_state = "IDLE"
    assert not cinema_cast.playing(cast, "u", seconds=0.6)  # gone: loaded again


def test_only_a_slow_file_waits_to_be_all_prepared(tmp_path):
    from houseos import cinema_progressive as p

    (tmp_path / "video.m3u8").write_text("#EXTM3U\n#EXTINF:4.0,\nseg0.m4s\n")
    assert p.keep_waiting(tmp_path, True)  # slow, unfinished: waited for
    assert not p.keep_waiting(tmp_path, False)  # fast: at once
    (tmp_path / "video.m3u8").write_text("#EXTM3U\n#EXTINF:4.0,\nseg0.m4s\n#EXT-X-ENDLIST\n")
    assert not p.keep_waiting(tmp_path, True)  # all prepared: sent


def test_the_place_kept_never_runs_ahead_of_time_while_the_stream_is_live():
    from datetime import timedelta

    from houseos import cinema
    from houseos.db import utcnow

    ten_seconds_ago = (utcnow() - timedelta(seconds=10)).isoformat()
    row = SimpleNamespace(
        data={"checkpoint": {"position": 1020, "at": ten_seconds_ago}, "observation": {"state": "active"}}
    )
    live = {"duration": -1}
    assert 1031 <= cinema.kept_place(row, live, 1350) <= 1033  # the live clock jumped: 17:00 + 10 s
    assert cinema.kept_place(row, live, 1025) == 1025  # a normal step: as reported
    assert cinema.kept_place(row, {"duration": 5400}, 1350) == 1350  # a normal film: trusted
    row.data["observation"] = {"state": "paused"}
    assert cinema.kept_place(row, live, 1350) == 1022  # paused meanwhile: no time passed
    row.data["_seek_previous"] = {"state": "active"}
    assert cinema.kept_place(row, live, 1350) == 1350  # a seek sets the place itself
