"""Music does what was asked (2026-10-18 review)."""

from sqlalchemy.orm import Session

from houseos import audio, music
from houseos.auth import Actor


def fresh():
    from test_music_library import MusicLibraryTests

    case = MusicLibraryTests()
    case.setUp()
    return case


def test_a_seek_on_a_stopped_song_is_where_play_starts_it():
    case = fresh()
    actor = Actor("one", "One", "resident", frozenset({"music.control"}))
    with Session(case.engine, expire_on_commit=False) as db:
        item = db.get(music.QueueItem, "track")
        item.status, item.metadata_json = "ready", {"duration": 300}
        q = db.get(music.QueueState, 1)
        q.current_id, q.desired = "track", "paused"
        db.commit()
        music.control(
            music.Control(
                action="seek",
                value=150,
                item_id="track",
                expected_version=q.version,
                idempotency_key="seek-stopped",
            ),
            actor,
            db,
        )
        shown = music.item_json(db.get(music.QueueItem, "track"))
        assert shown["resume_position"] == 150


def test_switching_speakers_keeps_levelling_off(monkeypatch):
    store = {"value": {"sink": "default", "normalize": False, "volume_cap": 80}}
    monkeypatch.setattr(audio, "policy", lambda: dict(store["value"]))
    monkeypatch.setattr(audio, "save_policy", lambda v: store.update(value=v))
    monkeypatch.setattr(audio, "outputs", lambda: [{"id": "default"}, {"id": "hdmi"}])
    monkeypatch.setattr(audio, "move_to", lambda sink: None)
    assert audio.execute({"command": "select_output", "sink": "hdmi"})["status"] == "configured"
    assert store["value"]["normalize"] is False and store["value"]["sink"] == "hdmi"
