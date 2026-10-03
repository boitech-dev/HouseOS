from unittest.mock import patch
from houseos.audio_volume import VolumeRamp


def test_fade_retargets_from_actual_volume_and_cancel_prevents_late_writes():
    now = [0.0]
    actual = [20.0]
    writes = []

    def write(value):
        actual[0] = value
        writes.append(value)

    ramp = VolumeRamp(lambda: actual[0], write, lambda: now[0])
    with patch("houseos.audio_volume.threading.Thread"):
        ramp.request(80.0)
        now[0] = 0.175
        ramp.step()
        assert actual[0] == 50.0
        ramp.request(10.0)
        ramp.step()
        assert actual[0] == 50.0
        now[0] = 0.35
        ramp.step()
        assert actual[0] == 30.0
        now[0] = 0.525
        ramp.step()
        assert actual[0] == 10.0 and ramp.target is None
        ramp.request(100.0)
        now[0] = 0.6
        ramp.step()
        ramp.cancel()
        before = list(writes)
        now[0] = 1.0
        ramp.step()
        assert writes == before


def test_latest_request_wins_without_queuing_previous_fades():
    now = [0.0]
    actual = [50.0]
    ramp = VolumeRamp(lambda: actual[0], lambda v: actual.__setitem__(0, v), lambda: now[0])
    with patch("houseos.audio_volume.threading.Thread") as thread:
        for target in [90, 10, 70, 0, 35]:
            ramp.request(target)
        assert thread.call_count == 1
        now[0] = 0.35
        ramp.step()
        assert actual[0] == 35 and ramp.state()["volume_target"] is None


def test_worker_skips_superseded_volume_commands(tmp_path):
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from test_music_library import MusicLibraryTests
    from houseos import music, worker
    from houseos.auth import Actor
    from houseos.models import Operation

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.control"}))
    operations = []
    with Session(fixture.engine) as db:
        for value in (80, 20, 45):
            result = music.control(
                music.Control(
                    action="volume", value=value, expected_version=1, idempotency_key="volume-" + str(value)
                ),
                actor,
                db,
            )
            operations.append(result["operation_id"])
    with (
        patch.object(worker, "SessionLocal", lambda: Session(fixture.engine)),
        patch.object(worker, "settings", SimpleNamespace(runtime_root=tmp_path)),
        patch.object(worker, "bridge", return_value={"status": "command_sent"}) as player,
    ):
        for _ in operations:
            job = worker.claim("volume-test", ("music.control",))
            assert job is not None
            worker.run_job(job)
        player.assert_called_once_with("volume", value=45)
    with Session(fixture.engine) as db:
        assert [db.get(Operation, op).state for op in operations] == ["cancelled", "cancelled", "unverified"]
