"""Nox's smart-home tools: list and control what the admin exposed from Home Assistant.
Names such as "the living room lights" resolve by fuzzy match on name and area; several
equally good matches are returned for the resident to choose, never guessed."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Literal

from pydantic import Field

from . import home
from .auth import Input

ACTION_NAMES = tuple(sorted({action for actions in home.ACTIONS.values() for action in actions}))
STOP_WORDS = set(
    "the a an my our all in on of at to please le la les l un une des du de d mon ma mes nos dans au aux sur".split()
)
# Everyday words for each kind of device, English and French.
KIND_WORDS = {
    "light": "light lights lamp lamps lampe lampes lumiere lumieres eclairage",
    "switch": "switch plug socket prise interrupteur",
    "fan": "fan ventilateur",
    "cover": "blind blinds shutter shutters curtain curtains volet volets store stores rideau rideaux",
    "climate": "thermostat heating heater radiator aircon chauffage radiateur clim climatisation",
    "media_player": "tv television speaker player tele enceinte",
    "vacuum": "vacuum robot aspirateur",
    "humidifier": "humidifier humidificateur",
    "lock": "lock door serrure porte",
    "alarm_control_panel": "alarm alarme",
    "scene": "scene ambiance",
    "script": "script routine",
    "valve": "valve vanne",
}


def words(text):
    text = unicodedata.normalize("NFKD", str(text or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return [word for word in re.findall(r"[a-z0-9]+", text) if word not in STOP_WORDS]


def score(query, text):
    """Share of the query's words found in the text (small typos and plurals allowed)."""
    known = set(words(text))
    found = sum(
        1 for word in query if any(word == k or SequenceMatcher(None, word, k).ratio() >= 0.8 for k in known)
    )
    return found / len(query) if query else 0


def described(entity):
    """Everything a resident may call a device: its name, area, id and kind."""
    return " ".join(
        [
            entity["name"],
            entity["area"] or "",
            entity["id"].split(".", 1)[1].replace("_", " "),
            KIND_WORDS.get(entity["domain"], entity["domain"]),
        ]
    )


def entities(actor, db):
    return [item for area in home.overview(actor, db)["areas"] for item in area["entities"]]


def compact(item):
    return {key: item[key] for key in ("id", "name", "area", "domain", "state", "actions")} | {
        key: value
        for key, value in item["attributes"].items()
        if key
        in {
            "brightness_pct",
            "current_temperature",
            "temperature",
            "current_position",
            "media_title",
            "source",
            "source_list",
            "volume_pct",
            "external_speakers",
            "color",
            "color_temp_kelvin",
            "effect",
            "percentage",
            "preset_mode",
        }
    } | {"choices": {c["id"]: c["options"] for c in item.get("controls", []) if c.get("options")}}


class HomeList(Input):
    area: str | None = Field(default=None, max_length=80)
    domain: str | None = Field(default=None, max_length=40, description="e.g. light, cover, climate")
    search: str | None = Field(default=None, max_length=120, description="words from a device's name")
    include_unavailable: bool = Field(default=False, description="also list devices reported offline")


def home_list(body, actor, db):
    items = entities(actor, db)
    if not body.include_unavailable:
        # Buttons, scenes and scripts have no state until used: "unknown" is normal for them.
        items = [
            item
            for item in items
            if item["state"] != "unavailable"
            and (item["state"] != "unknown" or item["domain"] in {"button", "scene", "script"})
        ]
    if body.domain:
        items = [item for item in items if item["domain"] == body.domain]
    if body.area:
        items = [item for item in items if score(words(body.area), item["area"] or "Other") >= 0.5]
    if body.search:
        query = words(body.search)
        items = [item for item in items if score(query, described(item)) >= 0.5]
    return {
        "items": [compact(item) for item in items[:25]],
        "count": len(items),
        "areas": sorted({item["area"] or "Other" for item in items}),
    }


class HomeControl(Input):
    entity: str | None = Field(default=None, max_length=240, description="exact id from home_list, if known")
    name: str | None = Field(
        default=None, max_length=120, description="what the resident called it, e.g. 'living room lights'"
    )
    action: Literal[ACTION_NAMES]
    value: home.Value = Field(
        default=None,
        description=(
            "brightness_pct/position/volume/percentage 0-100, set_temperature degrees, an hvac_mode, "
            "color as #rrggbb, warmth in kelvin (2000 warm to 6500 cool), an effect or preset from "
            "the device's choices, a TV's source (one of its source_list), or for key: "
            "DPAD_UP/DOWN/LEFT/RIGHT/CENTER, BACK, HOME"
        ),
    )


def resolve(body, items):
    """One entity, or the reason to ask the resident."""
    if body.entity:
        match = [item for item in items if item["id"] == body.entity]
        if match:
            return match[0], None
    query = words(body.name or body.entity)
    able = [item for item in items if body.action in item["actions"]] or items
    exact = [item for item in able if words(item["name"]) == query]
    if len(exact) == 1:
        return exact[0], None
    ranked = sorted(((score(query, described(item)), item) for item in able), key=lambda pair: -pair[0])
    best = ranked[0][0] if ranked else 0
    top = [item for value, item in ranked if value == best] if best >= 0.5 else []
    if len(top) == 1:
        return top[0], None
    return None, {
        "status": "needs_clarification",
        "message": "Several devices match: ask the resident which one (or act on each, one call per device)."
        if top
        else "No exposed device matches that name. Ask the resident, or use home_list.",
        "matches": [
            {"id": item["id"], "name": item["name"], "area": item["area"]} for item in (top or able)[:8]
        ],
    }


def home_control(body, actor, db):
    item, question = resolve(body, entities(actor, db))
    if question:
        return question
    result = home.control(db, actor, item["id"], body.action, body.value)
    if result.get("confirmation_id"):
        result["confirmation_path"] = "/assistant/confirmations/" + result["confirmation_id"]
        return result
    observed = result["entity"]
    return {
        "status": result["status"],
        "name": observed["name"],
        "area": observed["area"],
        "state": observed["state"],
        "attributes": observed["attributes"],
    }


TOOLS = {
    "home_list": (
        HomeList,
        "Smart-home devices HouseOS may control (lights, switches, blinds, heating…) with state, area and actions.",
        home_list,
    ),
    "home_control": (
        HomeControl,
        "Control one smart-home device by id or by the resident's words; returns the state observed afterwards. "
        "For several devices call once per device. Locks, alarms and similar return a confirmation card.",
        home_control,
    ),
}
