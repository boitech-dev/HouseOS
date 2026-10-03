"""Admin-only physical speaker setup through the fixed local audio bridge."""

from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import Input, require_admin
from .db import get_db, utcnow
from .models import Operation
from .music import bridge, QueueState
from .events import emit

router = APIRouter(prefix="/admin/audio", tags=["audio-setup"])


def idle(db):
    from .cinema import CinemaWorkflow

    q = db.get(QueueState, 1)
    if (
        q
        and q.desired == "playing"
        or db.scalar(
            select(CinemaWorkflow.id)
            .where(CinemaWorkflow.state.in_(["playing_observed", "command_sent", "preparing"]))
            .limit(1)
        )
    ):
        raise HTTPException(409, "Stop active media before speaker setup")


@router.get("")
def status(actor=Depends(require_admin), db=Depends(get_db)):
    """Where the music plays: this computer's outputs, and the enrolled Wi-Fi speakers and TVs."""
    from .cinema_models import CinemaDevice
    from .music_outputs import NETWORK_ADAPTERS, output_choice, relay_base_url

    devices = db.scalars(select(CinemaDevice).where(CinemaDevice.adapter.in_(NETWORK_ADAPTERS)).limit(50))
    return {
        **bridge("outputs"),
        "devices": [{"id": d.id, "name": d.name, "adapter": d.adapter} for d in devices],
        "device_id": output_choice(db).get("device_id"),
        "relay_ready": bool(relay_base_url(db)),
    }


class DeviceChoice(Input):
    device_id: str | None = Field(default=None, max_length=36)


@router.put("/device")
@router.put("/cast")  # its name before DLNA speakers could be chosen too
def choose_device(body: DeviceChoice, actor=Depends(require_admin), db=Depends(get_db)):
    """Music plays on this Cast or DLNA device (this computer goes quiet), or on none."""
    from .cinema_models import CinemaDevice
    from .music_outputs import NETWORK_ADAPTERS, save_output_choice

    if body.device_id:  # the follower picks the song up at the house clock's position
        device = db.get(CinemaDevice, body.device_id)
        if not device or device.adapter not in NETWORK_ADAPTERS:
            raise HTTPException(404, "Choose a speaker or TV enrolled in Devices")
        if bridge("select_output", sink="none").get("status") != "configured":
            raise HTTPException(409, "This computer's player did not answer; try again")
    save_output_choice(db, device_id=body.device_id, grant=None, problem=None)
    emit(db, "audit.audio_setup", {"device_id": body.device_id, "status": "configured"}, actor.id)
    db.commit()
    return {"status": "configured", "device_id": body.device_id}


class Prepare(Input):
    action: Literal["select", "test"]
    sink: str = Field(min_length=1, max_length=256)
    current_password: str | None = Field(default=None, max_length=256)


@router.post("/prepare")
def prepare(body: Prepare, actor=Depends(require_admin), db=Depends(get_db)):
    if body.action == "test":  # switching speakers works mid-song; a test tone needs silence
        idle(db)
    outputs = bridge("outputs")
    if body.sink not in {s["id"] for s in outputs.get("items", [])}:
        raise HTTPException(409, "Selected speaker is unavailable")
    if body.action == "test" and outputs.get("selected") != body.sink:
        raise HTTPException(409, "Select this output first")
    op = Operation(
        actor_id=actor.id,
        kind="audio.setup",
        state="needs_confirmation",
        data={"action": body.action, "sink": body.sink, "previous": outputs.get("selected")},
        expires_at=utcnow() + timedelta(seconds=120),
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "preview": {
            "action": body.action,
            "sink": body.sink,
            "effect": "Play one quiet one-second test sound"
            if body.action == "test"
            else "Music plays here from the next song you start",
        },
    }


@router.post("/confirm/{identity}")
def confirm(identity: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "audio.setup"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Confirmation expired or consumed")
    data = dict(row.data)
    if data["action"] == "test":
        idle(db)
    row.state = "executing"
    db.commit()
    current = bridge("outputs")
    if current.get("selected") != data["previous"]:
        result = {"status": "failed", "code": "OUTPUT_CHANGED"}
    else:
        result = bridge("select_output" if data["action"] == "select" else "test_output", sink=data["sink"])
    if data["action"] == "select" and result.get("status") == "configured":
        from .music_outputs import save_output_choice

        save_output_choice(db, device_id=None, grant=None)
    row = db.get(Operation, identity)
    row.state = "unverified" if result.get("status") == "command_sent" else result.get("status", "failed")
    row.result = result
    emit(db, "audit.audio_setup", {"operation_id": row.id, "status": row.state}, actor.id)
    db.commit()
    return result


class Heard(Input):
    sink: str = Field(min_length=1, max_length=256)
    heard: bool


@router.post("/verify")
def verify(body: Heard, actor=Depends(require_admin), db=Depends(get_db)):
    result = bridge("verify_output", sink=body.sink, heard=body.heard)
    emit(
        db,
        "audit.audio_verification",
        {"status": result.get("status"), "outcome": "confirmed" if body.heard else "not_heard"},
        actor.id,
    )
    db.commit()
    return result
