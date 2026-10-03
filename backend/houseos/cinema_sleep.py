"""Persisted, single-use sleep actions bound to one verified playback session."""

from datetime import timedelta
import hashlib
from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import Actor, require_actor, user_permissions
from .db import get_db, new_id, utcnow
from .models import User
from .playback import MediaError
from .cinema import (
    router,
    Version,
    CinemaWorkflow,
    CinemaDevice,
    own_workflow,
    save_workflow,
    authorize_workflow,
    observe,
    control,
    Control,
)
from .cinema_tv import tv_observation, tv_prepare, tv_confirm, TVAction, bridge


class SleepTimer(Version):
    minutes: int = Field(ge=0, le=1440)
    power_off: bool = False


def can_power_off(db, device):
    if not device or device.capabilities.get("power_off") is not True:
        return False
    try:
        current = tv_observation(db, device)
        return current.get("power_off_supported") is True and current["state"] not in {
            "unknown",
            "unavailable",
        }
    except MediaError:
        return False


def power_target(db, device):
    base, _, entity = bridge(db, device)
    return hashlib.sha256((base + "\0" + entity).encode()).hexdigest()


@router.get("/workflows/{identity}/sleep")
def timer_options(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    row = own_workflow(db, actor, identity)
    return {
        "timer": row.data.get("sleep_timer"),
        "power_off_available": can_power_off(db, db.get(CinemaDevice, row.device_id))
        if row.device_id
        else False,
    }


@router.post("/workflows/{identity}/sleep")
def set_timer(
    identity: str, body: SleepTimer, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    row = own_workflow(db, actor, identity, body.version)
    if body.minutes == 0:
        return save_workflow(db, row, row.state, {"sleep_timer": None})
    device = db.get(CinemaDevice, row.device_id) if row.device_id else None
    if row.state not in {"playing_observed", "paused"} or not device or device.owner_workflow != row.id:
        raise HTTPException(409, "Start and verify this movie before setting its sleep timer")
    authorize_workflow(db, row)
    if body.power_off and not can_power_off(db, device):
        raise HTTPException(422, "Power-off is not supported by this mapped display; use pause only")
    return save_workflow(
        db,
        row,
        row.state,
        {
            "sleep_timer": {
                "id": new_id(),
                "state": "scheduled",
                "at": (utcnow() + timedelta(minutes=body.minutes)).isoformat(),
                "power_off": body.power_off,
                "device_id": device.id,
                "device_version": device.version,
                "expected_item": row.data["plan"].get("expected_item"),
                "power_target": power_target(db, device) if body.power_off else None,
            }
        },
    )


def process_sleep_timers(db):
    now = utcnow().isoformat()
    stale = (utcnow() - timedelta(minutes=2)).isoformat()
    for abandoned in db.scalars(
        select(CinemaWorkflow)
        .where(
            CinemaWorkflow.data["sleep_timer"]["state"].as_string() == "checking",
            CinemaWorkflow.data["sleep_timer"]["claimed_at"].as_string() < stale,
        )
        .limit(20)
    ):
        prior = abandoned.data["sleep_timer"]
        save_workflow(
            db,
            abandoned,
            abandoned.state,
            {
                "sleep_timer": {
                    **prior,
                    "state": "failed",
                    "error": {
                        "code": "SLEEP_OUTCOME_UNKNOWN",
                        "message": "The timer was interrupted. Its device action will not be retried automatically.",
                    },
                }
            },
        )
    ids = list(
        db.scalars(
            select(CinemaWorkflow.id)
            .where(
                CinemaWorkflow.data["sleep_timer"]["state"].as_string() == "scheduled",
                CinemaWorkflow.data["sleep_timer"]["at"].as_string() <= now,
            )
            .limit(20)
        )
    )
    for identity in ids:
        row = db.scalar(select(CinemaWorkflow).where(CinemaWorkflow.id == identity).with_for_update())
        timer = (row.data.get("sleep_timer") or {}) if row else {}
        if timer.get("state") != "scheduled" or timer.get("at", "") > now:
            db.rollback()
            continue
        # Claim before any device traffic. Unknown outcomes are never blindly retried.
        timer = {**timer, "state": "checking", "claimed_at": now}
        row.data = {**row.data, "sleep_timer": timer}
        db.commit()
        try:
            authorize_workflow(db, row)
            device = db.get(CinemaDevice, timer["device_id"])
            if (
                row.state not in {"playing_observed", "paused", "command_sent"}
                or not device
                or device.owner_workflow != row.id
                or device.version != timer["device_version"]
                or (row.data.get("plan") or {}).get("expected_item") != timer["expected_item"]
            ):
                raise MediaError(
                    "SLEEP_SESSION_CHANGED",
                    "The original playback session changed; no sleep action was sent.",
                    "control",
                )
            user = db.get(User, row.owner_id)
            actor = Actor(user.id, user.name, user.role, user_permissions(user))
            result = observe(row.id, Version(version=row.version), actor, db)
            if result["state"] not in {"playing_observed", "paused"}:
                raise MediaError(
                    "SLEEP_SESSION_UNVERIFIED",
                    "The original movie could not be verified; no sleep action was sent.",
                    "control",
                )
            db.refresh(row)
            current_timer = row.data.get("sleep_timer") or {}
            if current_timer.get("id") != timer["id"] or current_timer.get("state") != "checking":
                continue
            if (row.data.get("plan") or {}).get("expected_item") != timer["expected_item"]:
                raise MediaError(
                    "SLEEP_SESSION_CHANGED",
                    "The original playback session changed; no sleep action was sent.",
                    "control",
                )
            authorize_workflow(db, row)
            paused = control(row.id, Control(version=row.version, action="pause"), actor, db)
            if paused["state"] == "recovery_required":
                raise MediaError(
                    "SLEEP_PAUSE_UNVERIFIED",
                    "The pause command failed; the display was not powered off.",
                    "control",
                )
            result = {"state": "pause_command_sent", "physical_verification": "unverified"}
            if timer["power_off"]:
                db.refresh(device)
                db.refresh(row)
                latest = row.data.get("sleep_timer") or {}
                if (
                    device.owner_workflow != row.id
                    or latest.get("id") != timer["id"]
                    or latest.get("state") != "checking"
                ):
                    raise MediaError(
                        "SLEEP_SESSION_CHANGED",
                        "Pause was sent; the display session then changed, so no power-off was sent.",
                        "control",
                    )
                authorize_workflow(db, row)
                if not can_power_off(db, device) or power_target(db, device) != timer.get("power_target"):
                    raise MediaError(
                        "SLEEP_POWER_UNAVAILABLE",
                        "Pause was sent, but display power-off is no longer available.",
                        "control",
                    )
                prepared = tv_prepare(
                    device.id, TVAction(version=device.version, action="power_off"), actor, db
                )
                result = tv_confirm(prepared["confirmation_id"], actor, db)
            db.refresh(row)
            if (row.data.get("sleep_timer") or {}).get("id") == timer["id"]:
                save_workflow(
                    db, row, row.state, {"sleep_timer": {**timer, "state": "completed", "result": result}}
                )
        except (MediaError, HTTPException) as exc:
            db.rollback()
            row = db.get(CinemaWorkflow, identity)
            if row and (row.data.get("sleep_timer") or {}).get("id") == timer["id"]:
                detail = (
                    exc.public()
                    if isinstance(exc, MediaError)
                    else {
                        "code": "SLEEP_ACTION_FAILED",
                        "message": "The scheduled action could not be confirmed.",
                    }
                )
                save_workflow(
                    db, row, row.state, {"sleep_timer": {**timer, "state": "failed", "error": detail}}
                )
    return len(ids)
