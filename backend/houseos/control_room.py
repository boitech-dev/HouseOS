"""Fixed HouseOS-only service actions with stored confirmations."""

import json
from . import ipc
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .auth import Input, require_admin
from .config import settings
from .db import get_db, utcnow
from .models import Operation, Job
from .music import QueueState
from .events import emit

router = APIRouter(prefix="/admin/services", tags=["control-room"])
SERVICES = {
    name: "houseos-" + name + ".service"
    for name in (
        "api",
        "worker",
        "cinema-worker",
        "cinema-observer",
        "maintenance",
        "media",
        "upload",
        "fetch",
        "audio",
        "codex",
        "claude",
    )
}


# Docker: every HouseOS process restarts itself on request (not tusd, which is not ours).
CONTAINER_RESTARTS = {
    "api",
    "worker",
    "maintenance",
    "fetch",
    "audio",
    "media",
    "cinema-worker",
    "cinema-observer",
    "voice",
    "codex",
    "claude",
}


def broker(action, name):
    if not (
        name in SERVICES and action in {"status", "restart"} or name == "houseos" and action == "shutdown"
    ):
        return {"status": "denied"}
    return ipc.request(
        "/run/houseos-control/control.sock",
        {"action": action, "service": name},
        timeout=15,
        limit=8192,
        failure={"status": "unavailable", "code": "SERVICE_BROKER_UNAVAILABLE"},
    )


@router.get("")
def services(actor=Depends(require_admin), db=Depends(get_db)):
    if settings.storage_container:  # Docker: measured health; `docker compose` restarts
        from .house_setup import service_rows

        return service_rows(db)
    return [{"name": name, **broker("status", name)} for name in SERVICES]


class Action(Input):
    current_password: str | None = None


@router.post("/{name}/prepare-restart")
def prepare(name: str, body: Action, actor=Depends(require_admin), db=Depends(get_db)):
    if name not in SERVICES and not (settings.storage_container and name in CONTAINER_RESTARTS):
        raise HTTPException(404, "Unknown HouseOS service")
    if settings.storage_container and name not in CONTAINER_RESTARTS:
        raise HTTPException(409, "This part restarts with the whole house")
    q = db.get(QueueState, 1)
    from .cinema import CinemaWorkflow

    active = db.scalar(
        select(CinemaWorkflow.id)
        .where(CinemaWorkflow.state.in_(["playing_observed", "paused", "preparing", "command_sent"]))
        .limit(1)
    )
    if (q and q.desired == "playing") or active:
        raise HTTPException(409, "Pause/stop active media before maintenance")
    before = {} if settings.storage_container else broker("status", name)
    if not settings.storage_container and before.get("status") != "observed":
        raise HTTPException(503, "Service control is unavailable")
    op = Operation(
        actor_id=actor.id,
        kind="service.restart",
        state="needs_confirmation",
        data={"service": name, "invocation_before": before.get("invocation_id")},
        expires_at=utcnow() + timedelta(seconds=120),
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "preview": {
            "service": name,
            "effect": "Restart this HouseOS component; active requests may disconnect",
        },
    }


@router.post("/confirmations/{identity}")
def confirm(identity: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "service.restart"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Confirmation expired or consumed")
    q = db.get(QueueState, 1)
    from .cinema import CinemaWorkflow

    if (q and q.desired == "playing") or db.scalar(
        select(CinemaWorkflow.id)
        .where(CinemaWorkflow.state.in_(["playing_observed", "paused", "preparing", "command_sent"]))
        .limit(1)
    ):
        raise HTTPException(409, "Media activity changed; prepare a new maintenance action")
    if settings.storage_container:  # the service reads this note and restarts itself
        notes = settings.runtime_root / "run" / "restart"
        notes.mkdir(mode=0o2770, parents=True, exist_ok=True)
        (notes / row.data["service"]).touch()
        row.state, row.result = "unverified", {"service": row.data["service"], "status": "requested"}
        emit(
            db,
            "audit.service_restart_requested",
            {"service": row.data["service"], "operation_id": row.id},
            actor.id,
        )
        db.commit()
        return {"status": "accepted", "operation_id": row.id}
    row.state = "accepted"
    db.add(
        Job(
            kind="service.restart",
            logical_key="restart:" + row.id,
            actor_id=actor.id,
            payload={
                "service": row.data["service"],
                "operation_id": row.id,
                "session_hash": actor.session_hash,
            },
        )
    )
    emit(
        db,
        "audit.service_restart_requested",
        {"service": row.data["service"], "operation_id": row.id},
        actor.id,
    )
    db.commit()
    return {"status": "accepted", "operation_id": row.id}


def reconcile_restarts(db):
    if settings.storage_container:  # nothing to ask systemd; Services shows the service answering
        return
    rows = db.scalars(
        select(Operation).where(
            Operation.kind == "service.restart", Operation.state.in_(["executing", "unverified"])
        )
    ).all()
    for row in rows:
        observation = broker("status", row.data["service"])
        changed = observation.get("invocation_id") and observation.get("invocation_id") != row.data.get(
            "invocation_before"
        )
        if changed and observation.get("active") == "active":
            row.state = "completed"
            row.result = {
                "service": row.data["service"],
                "observation": observation,
                "verified_at": utcnow().isoformat() + "Z",
            }
            emit(
                db,
                "audit.service_restart_verified",
                {"operation_id": row.id, "service": row.data["service"], "status": "completed"},
                row.actor_id,
            )
        elif observation.get("active") == "failed":
            row.state = "failed"
            row.result = {"service": row.data["service"], "observation": observation}
    db.commit()


@router.post("/shutdown/prepare")
def prepare_shutdown(actor=Depends(require_admin), db=Depends(get_db)):
    if settings.storage_container:
        raise HTTPException(409, "Stop HouseOS from the server: docker compose stop")
    op = Operation(
        actor_id=actor.id,
        kind="houseos.shutdown",
        state="needs_confirmation",
        data={},
        expires_at=utcnow() + timedelta(minutes=2),
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "preview": {
            "effect": "Stop HouseOS, its music player, native assistants, uploads, workers, backup timer, Comet and Jellyfin. Other applications stay running. Open the HouseOS desktop launcher to restart.",
            "active_tv": "Stop active Cinema playback first; shutdown preserves its last checkpoint.",
        },
    }


@router.post("/shutdown/confirm/{identity}")
def confirm_shutdown(identity: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "houseos.shutdown"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Shutdown confirmation expired or consumed")
    from .cinema import CinemaWorkflow

    if db.scalar(
        select(CinemaWorkflow.id)
        .where(CinemaWorkflow.state.in_(["playing_observed", "paused", "preparing", "command_sent"]))
        .limit(1)
    ):
        raise HTTPException(409, "Stop active Cinema playback before shutting down HouseOS")
    from .music import bridge, QueueItem

    q = db.get(QueueState, 1)
    if q:
        q.desired = "paused"
    row.state = "accepted"
    emit(db, "audit.houseos_shutdown_requested", {"operation_id": row.id}, actor.id)
    db.commit()
    # Freeze new mutations before taking the final player checkpoint. Restart removes this file.
    marker = settings.runtime_root / "run/shutdown.json"
    marker.write_text(json.dumps({"operation_id": identity, "at": utcnow().isoformat()}))
    observation = bridge("state")
    paused = bridge("pause")
    q = db.get(QueueState, 1)
    if q and q.current_id:
        item = db.get(QueueItem, q.current_id)
        if item and observation.get("position") is not None:
            item.metadata_json = {**item.metadata_json, "last_position": observation["position"]}
            item.status = "paused"
    row = db.get(Operation, identity)
    row.result = {
        "music_pause": paused.get("status"),
        "last_checkpoint_saved": observation.get("position") is not None,
    }
    db.commit()
    result = broker("shutdown", "houseos")
    if result.get("status") != "accepted":
        marker.unlink(missing_ok=True)
        row.state, row.result = "failed", result
        db.commit()
        raise HTTPException(503, "HouseOS shutdown could not be scheduled")
    return {
        "status": "accepted",
        "operation_id": identity,
        "message": "Shutdown scheduled. This page will disconnect; reopen the desktop launcher to restart.",
    }
