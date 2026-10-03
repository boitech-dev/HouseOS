"""Exact Home Assistant display controls, separate from media playback transport."""

from datetime import timedelta
from typing import Literal
from urllib.parse import quote
from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import Actor, require_actor, refresh_actor
from .db import get_db, new_id, utcnow
from .events import emit
from .integrations import integration_config
from .models import Record
from .cinema import router, Body, CinemaDevice, allowed, call, failure
from .cinema_adapters import internal_base, private_json
from .playback import MediaError


class TVAction(Body):
    version: int = Field(ge=1)
    action: Literal["power_on", "power_off", "volume", "input", "reboot"]
    value: float | str | None = None


def bridge(db, device):
    config = integration_config(db, "home_assistant")
    entity = config.get("device_id", "")
    token = config.get("token") or config.get("api_key")
    if (
        not config.get("enabled")
        or not token
        or not entity.startswith("media_player.")
        or config.get("receiver_id") != device.id
    ):
        raise MediaError(
            "TV_CONTROL_UNCONFIGURED",
            "Map this exact destination to an authorized Home Assistant media-player entity first.",
            "setup",
        )
    return internal_base(config, "http://127.0.0.1:8123"), {"Authorization": "Bearer " + token}, entity


def tv_observation(db, device):
    from .home import TV_SPEAKERS

    base, headers, entity = bridge(db, device)
    state = private_json(base, "/api/states/" + quote(entity, safe=""), headers=headers, timeout=4)
    attributes = state.get("attributes", {})
    display = attributes.get("friendly_name") or entity
    if display.casefold() == "vidaa tv":
        display = "Hisense TV"
    return {
        "display_name": display,
        "reboot_supported": False,
        "power_off_supported": bool(int(attributes.get("supported_features") or 0) & 256),
        "state": state.get("state", "unknown"),
        "changed_at": state.get("last_changed"),
        "observed_at": utcnow().isoformat(),
        "volume": attributes.get("volume_level"),
        "muted": attributes.get("is_volume_muted"),
        "features": int(attributes.get("supported_features") or 0),
        "input": attributes.get("source"),
        "inputs": attributes.get("source_list", [])[:30],
        # Sound on a soundbar or amplifier (LG's sound_output): the TV's level changes nothing heard.
        "external_speakers": isinstance(attributes.get("sound_output"), str)
        and attributes["sound_output"].casefold() not in TV_SPEAKERS,
    }


@router.get("/devices/{identity}/tv")
def tv_state(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    device = db.get(CinemaDevice, identity)
    if not device:
        raise HTTPException(404, "Destination not found")
    return call(tv_observation, db, device)


@router.post("/devices/{identity}/tv-prepare")
def tv_prepare(
    identity: str, body: TVAction, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    allowed(actor)
    device = db.get(CinemaDevice, identity)
    if not device:
        raise HTTPException(404, "Destination not found")
    if body.version != device.version:
        failure(MediaError("PLAN_STALE", "The destination configuration changed. Refresh first.", "control"))
    if body.action == "reboot":
        failure(
            MediaError(
                "CONTROL_UNSUPPORTED",
                "Chromecast reboot is not supported by the configured adapter. TV power-off only puts the mapped display in standby; it cannot reboot the Chromecast. No device command was sent.",
                "control",
            )
        )
    base, _, entity = call(bridge, db, device)
    capability = {"volume": "volume_absolute", "input": "set_input"}.get(body.action, body.action)
    if device.capabilities.get(capability) is not True:
        failure(
            MediaError(
                "CONTROL_UNSUPPORTED",
                "This display control has not been enabled for the actual device.",
                "control",
            )
        )
    current = call(tv_observation, db, device)
    if current["state"] in {"unavailable", "unknown"}:
        failure(
            MediaError(
                "TARGET_OFFLINE",
                "The display integration currently reports this device unavailable.",
                "control",
                True,
            )
        )
    if body.action == "volume" and (
        not isinstance(body.value, (int, float)) or isinstance(body.value, bool) or not 0 <= body.value <= 75
    ):
        raise HTTPException(422, "Volume must be 0–75 percent")
    if body.action == "input" and body.value not in current["inputs"]:
        raise HTTPException(422, "Choose an input actually reported by this display")
    record = Record(
        id=new_id(),
        kind="cinema.tv_confirmation",
        owner_id=actor.id,
        visibility="private",
        data={
            "device_id": device.id,
            "version": device.version,
            "control_entity": entity,
            "control_base": base,
            "action": body.action,
            "value": body.value,
            "observation": current,
            "expires_at": (utcnow() + timedelta(seconds=120)).isoformat(),
            "consumed": False,
        },
        version=1,
    )
    db.add(record)
    db.commit()
    display = current.get("display_name") or entity
    description = {
        "power_on": f"Turn on {display}.",
        "power_off": f"Put {display} in standby. This does not reboot the Chromecast.",
        "volume": f"Set {display} volume to {body.value}%.",
        "input": f"Switch {display} to {body.value}.",
    }[body.action]
    return {
        "confirmation_id": record.id,
        "preview": {
            "destination": display,
            "action": body.action,
            "summary": description,
            "value": body.value,
            "may_interrupt": body.action in {"power_off", "input"},
            "expires_at": record.data["expires_at"],
        },
    }


@router.post("/device-confirmations/{identity}")
def tv_confirm(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    record = db.scalar(
        select(Record)
        .where(
            Record.id == identity,
            Record.kind == "cinema.tv_confirmation",
            Record.owner_id == actor.id,
            Record.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not record:
        raise HTTPException(404, "Confirmation not found")
    data = record.data
    if data["consumed"]:
        return data.get("result", {"state": "command_outcome_unknown"})
    device = db.get(CinemaDevice, data["device_id"])
    if not device or device.version != data["version"] or data["expires_at"] <= utcnow().isoformat():
        failure(MediaError("PLAN_STALE", "This display-control confirmation expired or changed.", "control"))
    base, headers, entity = call(bridge, db, device)
    if data.get("control_entity") != entity or data.get("control_base") != base:
        failure(
            MediaError(
                "PLAN_STALE", "The display-control mapping changed. Prepare the action again.", "control"
            )
        )
    current = call(tv_observation, db, device)
    if any(current.get(k) != data["observation"].get(k) for k in ["state", "changed_at", "volume", "input"]):
        failure(
            MediaError(
                "PLAN_STALE", "The display changed after preview. Prepare the action again.", "control"
            )
        )
    record.data = {**data, "consumed": True}
    db.commit()
    service = {
        "power_on": "turn_on",
        "power_off": "turn_off",
        "volume": "volume_set",
        "input": "select_source",
    }[data["action"]]
    payload = {"entity_id": entity}
    if data["action"] == "volume":
        payload["volume_level"] = data["value"] / 100
    elif data["action"] == "input":
        payload["source"] = data["value"]
    try:
        actor = refresh_actor(db, actor)
        allowed(actor)
        private_json(
            base,
            "/api/services/media_player/" + service,
            headers=headers,
            method="POST",
            payload=payload,
            timeout=5,
        )
        observed = tv_observation(db, device)
        verified = (
            observed["state"] == "off"
            if data["action"] == "power_off"
            else observed["state"] not in {"off", "unavailable", "unknown"}
            if data["action"] == "power_on"
            else abs((observed.get("volume") or 0) - data["value"] / 100) < 0.02
            if data["action"] == "volume"
            else observed.get("input") == data["value"]
        )
        result = {
            "state": "observed" if verified else "command_sent",
            "action": data["action"],
            "destination": observed.get("display_name") or entity,
            "value": data["value"],
            "observation": {k: observed.get(k) for k in ("state", "volume", "input", "observed_at")},
            "physical_verification": "unverified",
        }
    except MediaError as exc:
        result = {
            "state": "command_outcome_unknown",
            "error": exc.public(),
            "retry_requires_observation": True,
        }
    record.data = {**record.data, "result": result}
    emit(
        db,
        "cinema.tv_control",
        {"device_id": device.id, "action": data["action"], "state": result["state"]},
        user_id=actor.id,
    )
    db.commit()
    return result
