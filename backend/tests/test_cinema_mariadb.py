"""MariaDB contention and revocation proofs; never calls a physical device/provider."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Lock
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from houseos import cinema as c
from houseos.db import new_id, utcnow
from houseos.models import SessionToken
from houseos.playback import MediaError, compatibility

pytestmark = pytest.mark.skipif(
    os.environ.get("HOUSEOS_TEST_MARIADB") != "1", reason="Isolated MariaDB integration check"
)


@pytest.fixture
def media(domain):
    db, actors = domain
    title = c.CinemaTitle(
        id=new_id(), canonical_id="test-" + new_id(), title="Synthetic test", kind="movie", data={}
    )
    device = c.CinemaDevice(
        id=new_id(),
        name="Unconnected fixture",
        adapter="jellyfin",
        address="192.168.1.250",
        session_id="fixture-session",
        capabilities={
            "inspected_at": utcnow().isoformat(),
            "video_codecs": ["h264"],
            "audio_codecs": ["aac"],
            "hdr_modes": ["sdr"],
            "maximum_resolution": 1080,
            "max_audio_channels": 2,
            "containers": ["mp4"],
        },
        observation={"state": "idle"},
    )
    db.add_all([title, device])
    db.commit()
    try:
        yield db, actors, title, device
    finally:
        db.rollback()
        workflows = list(db.scalars(select(c.CinemaWorkflow.id).where(c.CinemaWorkflow.media_id == title.id)))
        db.execute(delete(c.CinemaConfirmation).where(c.CinemaConfirmation.workflow_id.in_(workflows)))
        db.execute(delete(c.CinemaWorkflow).where(c.CinemaWorkflow.id.in_(workflows)))
        db.execute(delete(c.CinemaState).where(c.CinemaState.media_id == title.id))
        db.execute(delete(c.CinemaDevice).where(c.CinemaDevice.id == device.id))
        db.execute(delete(c.CinemaTitle).where(c.CinemaTitle.id == title.id))
        db.commit()


def request(db, actor, title, device):
    workflow = c.CinemaWorkflow(
        id=new_id(),
        owner_id=actor.id,
        media_id=title.id,
        device_id=device.id,
        state="awaiting_playback_confirmation",
        version=1,
        idempotency_key=new_id(),
        data={},
    )
    db.add(workflow)
    db.flush()
    confirmation = c.CinemaConfirmation(
        id=new_id(),
        owner_id=actor.id,
        workflow_id=workflow.id,
        workflow_version=1,
        action="play",
        data={"device_version": device.version},
        expires_at=utcnow() + timedelta(minutes=1),
    )
    db.add(confirmation)
    db.commit()
    return workflow, confirmation


def test_two_users_cannot_both_claim_same_destination(media, monkeypatch):
    db, actors, title, device = media
    requests = [request(db, actor, title, device) for actor in actors[:2]]
    barrier, lock, calls = Barrier(2), Lock(), []

    def execute(session, row):
        with lock:
            calls.append(row.id)
        return {"state": "command_sent"}

    monkeypatch.setattr(c, "execute_play", execute)

    def send(pair):
        actor, (_, confirmation) = pair
        with Session(db.get_bind(), expire_on_commit=False) as session:
            session.scalar(select(func.count()).select_from(c.CinemaWorkflow))  # establish old RR snapshot
            barrier.wait()
            try:
                return c.confirm(confirmation.id, actor, session)["state"]
            except HTTPException as exc:
                session.rollback()
                return exc.detail["code"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, zip(actors[:2], requests)))
    assert sorted(results) == ["DESTINATION_BUSY", "command_sent"]
    assert len(calls) == 1


def test_a_stuck_session_frees_an_idle_tv_but_not_a_playing_one(media, monkeypatch):
    db, actors, title, device = media
    monkeypatch.setattr(c, "execute_play", lambda db, row: {"state": "command_sent"})
    # Someone else's play the TV refused: stuck, still holding the TV.
    stuck, _ = request(db, actors[1], title, device)
    stuck.state = "recovery_required"
    device.owner_workflow = stuck.id
    db.commit()
    for tv_shows_something, expected in ((True, "DESTINATION_BUSY"), (False, "command_sent")):
        workflow, confirmation = request(db, actors[0], title, device)
        workflow.data = {"plan": {"interrupts": tv_shows_something}}
        db.commit()
        try:
            result = c.confirm(confirmation.id, actors[0], db)["state"]
        except HTTPException as exc:
            db.rollback()
            result = exc.detail["code"]
        assert result == expected
    assert db.get(c.CinemaDevice, device.id).owner_workflow == workflow.id


def test_same_confirmation_race_dispatches_once(media, monkeypatch):
    db, actors, title, device = media
    workflow, confirmation = request(db, actors[0], title, device)
    barrier, calls = Barrier(2), []
    monkeypatch.setattr(c, "execute_play", lambda db, row: calls.append(row.id) or {"state": "command_sent"})

    def send(_):
        with Session(db.get_bind(), expire_on_commit=False) as session:
            barrier.wait()
            return c.confirm(confirmation.id, actors[0], session)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(send, range(2)))
    assert calls == [workflow.id]


def test_revocation_during_preflight_prevents_native_command(media, monkeypatch):
    db, actors, title, device = media
    actor = actors[0]
    token_hash = new_id().replace("-", "") * 2
    db.add(
        SessionToken(
            token_hash=token_hash,
            user_id=actor.id,
            csrf_token="test",
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    workflow, _ = request(db, actor, title, device)
    inspection = {
        "video": {"index": 0, "codec": "h264", "height": 1080, "hdr": "sdr"},
        "audio": [{"id": "1", "codec": "aac", "language": "en", "channels": 2, "default": True}],
        "subtitles": [],
        "duration": 100,
        "container": "mp4",
    }
    plan = compatibility(inspection, device.capabilities, {})
    workflow.data = {
        "_authorization_session": token_hash,
        "_selected_source": "fixture-source",
        "_sources": [
            {"id": "fixture-source", "jellyfin_item": "fixture-item", "jellyfin_source": "fixture-release"}
        ],
        "request": {},
        "plan": {**plan, "position": 0},
        "_destination_observation": {"state": "idle", "item_id": None, "session_id": "fixture-session"},
    }
    db.commit()

    def revoke(item):
        with Session(db.get_bind()) as other:
            other.execute(delete(SessionToken).where(SessionToken.token_hash == token_hash))
            other.commit()
        return {"MediaSources": [{"Id": "fixture-release"}]}

    with patch("houseos.cinema.Jellyfin") as adapter:
        adapter.return_value.playback_info.side_effect = revoke
        monkeypatch.setattr(c, "integration_config", lambda db, name: {})
        monkeypatch.setattr(
            c,
            "inspect_destination",
            lambda db, device: {"state": "idle", "item_id": None, "session_id": "fixture-session"},
        )
        monkeypatch.setattr(c, "jellyfin_inspection", lambda source: inspection)
        with pytest.raises(MediaError, match="PERMISSION_REVOKED"):
            c.execute_play(db, workflow)
        adapter.return_value.play.assert_not_called()


def test_private_history_json_filters_on_mariadb(media):
    db, actors, title, device = media
    state = c.CinemaState(
        id=new_id(),
        owner_id=actors[0].id,
        media_id=title.id,
        last_watched_at=utcnow(),
        data={"position": 12, "watched": False, "favorite": True, "watchlist": False},
    )
    db.add(state)
    db.commit()
    assert c.media_state("continue", actors[0], db)["items"][0]["media_id"] == title.id
    assert c.media_state("favorites", actors[0], db)["items"][0]["media_id"] == title.id
    assert c.media_state("watchlist", actors[0], db)["items"] == []
    assert c.media_state("history", actors[1], db)["items"] == []
    state.data = {**state.data, "watched": True}
    db.commit()
    assert c.media_state("continue", actors[0], db)["items"] == []


def test_sleep_timer_nested_json_due_selection_and_single_claim(media, monkeypatch):
    from houseos import cinema_sleep as sleep

    db, actors, title, device = media
    row = c.CinemaWorkflow(
        id=new_id(),
        owner_id=actors[0].id,
        media_id=title.id,
        device_id=device.id,
        state="playing_observed",
        version=1,
        idempotency_key=new_id(),
        data={
            "plan": {"expected_item": "fixture"},
            "sleep_timer": {
                "id": new_id(),
                "state": "scheduled",
                "at": (utcnow() - timedelta(seconds=1)).isoformat(),
                "power_off": False,
                "device_id": device.id,
                "device_version": device.version,
                "expected_item": "fixture",
            },
        },
    )
    db.add(row)
    device.owner_workflow = row.id
    db.commit()
    monkeypatch.setattr(sleep, "observe", lambda *args, **kwargs: {"state": "playing_observed"})
    calls = []
    monkeypatch.setattr(
        sleep, "control", lambda *args, **kwargs: calls.append("pause") or {"state": "command_sent"}
    )
    assert sleep.process_sleep_timers(db) == 1
    assert sleep.process_sleep_timers(db) == 0
    assert calls == ["pause"] and row.data["sleep_timer"]["state"] == "completed"
