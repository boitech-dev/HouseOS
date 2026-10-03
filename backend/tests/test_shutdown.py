from houseos import control_room
from houseos.auth import require_admin
from houseos.models import Operation
from sqlalchemy.orm import Session


def test_shutdown_is_exact_actor_confirmation_and_checkpoints_music(monkeypatch, tmp_path):
    from test_music_library import MusicLibraryTests
    from houseos import cinema  # register Cinema tables before the isolated schema

    assert cinema.CinemaWorkflow is not None
    case = MusicLibraryTests()
    case.setUp()
    case.app.include_router(control_room.router)
    case.app.dependency_overrides[require_admin] = lambda: case.actor
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(control_room.settings, "runtime_root", tmp_path)
    requests = []
    monkeypatch.setattr(
        control_room, "broker", lambda action, name: requests.append((action, name)) or {"status": "accepted"}
    )
    monkeypatch.setattr("houseos.music.bridge", lambda action: {"status": "observed", "position": 31})
    from houseos.music import QueueState, QueueItem

    with Session(case.engine) as db:
        q = db.get(QueueState, 1)
        q.current_id, q.desired = "track", "playing"
        db.commit()
    prepared = case.client.post("/admin/services/shutdown/prepare").json()
    identity = prepared["confirmation_id"]
    result = case.client.post("/admin/services/shutdown/confirm/" + identity)
    assert result.status_code == 200 and result.json()["status"] == "accepted"
    assert requests == [("shutdown", "houseos")]
    assert (tmp_path / "run/shutdown.json").is_file()
    with Session(case.engine) as db:
        assert db.get(QueueState, 1).desired == "paused"
        assert db.get(QueueItem, "track").metadata_json["last_position"] == 31
        assert db.get(Operation, identity).state == "accepted"
    assert case.client.post("/admin/services/shutdown/confirm/" + identity).status_code == 409
    assert control_room.broker is not None


def test_shutdown_marker_blocks_late_player_and_worker_actions(monkeypatch, tmp_path):
    from houseos import audio, worker

    (tmp_path / "run").mkdir()
    (tmp_path / "run/shutdown.json").write_text("{}")
    monkeypatch.setattr(audio.settings, "runtime_root", tmp_path)
    assert audio.execute({"command": "play"})["code"] == "HOUSEOS_SHUTTING_DOWN"
    assert audio.execute({"command": "load"})["code"] == "HOUSEOS_SHUTTING_DOWN"
    assert worker.claim("test") is None
    assert worker.advance() is None


def test_restart_restores_exact_track_position_but_remains_paused(monkeypatch):
    from test_music_library import MusicLibraryTests
    from houseos import worker
    from houseos.music import QueueState, QueueItem

    case = MusicLibraryTests()
    case.setUp()
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(case.engine, expire_on_commit=False))
    with Session(case.engine) as db:
        q = db.get(QueueState, 1)
        q.current_id, q.desired = "track", "playing"
        db.get(QueueItem, "track").metadata_json = {"last_position": 45.5}
        db.commit()
    worker.reconcile_player_restart({"status": "observed", "idle": True})
    with Session(case.engine) as db:
        q, track = db.get(QueueState, 1), db.get(QueueItem, "track")
        assert q.desired == "paused" and q.current_id is None
        assert track.status == "ready" and track.metadata_json["resume_position"] == 45.5
        q.current_id, track.status = "track", "playing"
        db.commit()
    worker.reconcile_player_restart({"status": "observed", "idle": False, "item_id": "track"})
    with Session(case.engine) as db:
        assert db.get(QueueState, 1).current_id == "track"
        assert db.get(QueueItem, "track").status == "paused"


def test_restart_keeps_a_just_requested_song_that_has_not_started(monkeypatch):
    from datetime import timedelta
    from test_music_library import MusicLibraryTests
    from houseos import worker
    from houseos.db import utcnow
    from houseos.music import QueueState, QueueItem

    case = MusicLibraryTests()
    case.setUp()
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(case.engine, expire_on_commit=False))
    for age, desired in ((10, "playing"), (600, "paused")):
        with Session(case.engine) as db:
            q, track = db.get(QueueState, 1), db.get(QueueItem, "track")
            q.current_id, q.desired = "track", "playing"
            track.status, track.created_at = "ready", utcnow() - timedelta(seconds=age)
            db.commit()
        worker.reconcile_player_restart({"status": "observed", "idle": True})
        with Session(case.engine) as db:
            assert db.get(QueueState, 1).desired == desired


def test_installed_mpv_accepts_resume_start_without_physical_output(tmp_path, monkeypatch):
    import subprocess
    import time
    import wave
    from houseos import audio

    source, ipc = tmp_path / "sample.wav", tmp_path / "mpv.sock"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 32000)
    process = subprocess.Popen(
        [
            "mpv",
            "--no-config",
            "--load-scripts=no",
            "--ytdl=no",
            "--no-video",
            "--ao=null",
            "--idle=yes",
            "--pause=yes",
            "--terminal=no",
            "--input-ipc-server=" + str(ipc),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            if ipc.exists():
                break
            time.sleep(0.05)
        monkeypatch.setattr(audio, "SOCKET", ipc)
        audio.mpv(["set_property", "start", "2"])  # the form mpv 0.35 (Docker) accepts too
        audio.mpv(["loadfile", str(source), "replace"])
        position = None
        for _ in range(40):
            position = audio.mpv(["get_property", "time-pos"])
            if position is not None:
                break
            time.sleep(0.05)
        assert position is not None and 1.9 <= position <= 2.1
        assert audio.mpv(["get_property", "pause"]) is True
    finally:
        process.terminate()
        process.wait(timeout=3)


def test_maintenance_step_failure_does_not_skip_later_steps(monkeypatch, capsys):
    from houseos import maintenance

    ran = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def commit(self):
            ran.append("commit")

    def broken(db):
        raise RuntimeError("https://secret.example/token")

    monkeypatch.setattr(maintenance, "SessionLocal", Session)
    monkeypatch.setattr(maintenance, "STEPS", (broken, lambda db: ran.append("later")))
    maintenance.run_steps()
    assert ran == ["later", "commit"]
    logged = capsys.readouterr().out
    assert "RuntimeError" in logged and "secret.example" not in logged


def test_prune_history_keeps_live_and_recent_rows(monkeypatch):
    from datetime import timedelta
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from houseos import maintenance
    from houseos.db import Base, utcnow
    from houseos.models import Event, Job, Operation, SessionToken, User
    from houseos.auth import LoginAttempt

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    old, recent = utcnow() - timedelta(days=200), utcnow() - timedelta(days=2)
    with Session(engine) as db:
        db.add(User(id="u", name="U", username="u", password_hash="x"))
        db.add_all(
            [
                Event(topic="music.playback", created_at=old),
                Event(topic="music.playback", created_at=recent),
                Event(topic="audit.login", created_at=old),
                Event(topic="audit.login", created_at=recent),
                Job(logical_key="done", kind="k", state="done", next_run=old),
                Job(logical_key="pending", kind="k", state="pending", next_run=old),
                Operation(id="fin", actor_id="u", kind="k", state="completed", updated_at=old),
                Operation(id="live", actor_id="u", kind="k", state="needs_confirmation", updated_at=old),
                SessionToken(token_hash="gone", user_id="u", csrf_token="c", expires_at=old),
                SessionToken(
                    token_hash="kept", user_id="u", csrf_token="c", expires_at=utcnow() + timedelta(days=1)
                ),
                LoginAttempt(key="stale", window_at=old),
            ]
        )
        db.commit()
        monkeypatch.setattr(maintenance, "last_prune", 0.0)
        monkeypatch.setattr(maintenance.time, "monotonic", lambda: 10_000.0)
        maintenance.prune_history(db)
        db.commit()
        assert sorted(e.topic for e in db.scalars(select(Event))) == ["audit.login", "music.playback"]
        assert [j.logical_key for j in db.scalars(select(Job))] == ["pending"]
        assert [o.id for o in db.scalars(select(Operation))] == ["live"]
        assert [s.token_hash for s in db.scalars(select(SessionToken))] == ["kept"]
        assert not db.scalars(select(LoginAttempt)).all()
        maintenance.prune_history(db)  # the hourly gate makes a second call a no-op
