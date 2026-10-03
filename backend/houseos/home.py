"""Smart home: the house's own Home Assistant (lights, switches, blinds, heating…) behind an
admin exposure policy. Sensitive devices (locks, alarms…) always need a confirmed second step.
Every answer reports the state Home Assistant shows after the command, never just "sent"."""

import json
import re
import time
from datetime import timedelta
from typing import Annotated
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import Input, require_actor, require_admin, require_permission
from .cinema_adapters import internal_base, private_json
from .db import get_db, utcnow
from .events import emit
from .integrations import integration_config
from .cinema_models import CinemaDevice
from .models import Integration, Operation, User
from .playback import MediaError

router = APIRouter(prefix="/home", tags=["smart-home"])
PERMISSION = "home.control"
# What HouseOS may control until an administrator chooses otherwise.
DEFAULT_DOMAINS = (
    "light",
    "switch",
    "fan",
    "cover",
    "climate",
    "scene",
    "script",
    "media_player",
    "input_boolean",
    "vacuum",
    "humidifier",
    "button",
)
# Off by default, and every command on them (or any other domain) waits for a confirmation;
# so do scripts and garage/gate/door covers (see sensitive()).
SENSITIVE_DOMAINS = ("lock", "alarm_control_panel", "siren", "valve")
ENTITY = re.compile(r"^[a-z0-9_]{1,40}\.[a-z0-9_]{1,200}$")
ON_OFF = {"toggle": ("toggle", None), "turn_on": ("turn_on", None), "turn_off": ("turn_off", None)}
# domain -> action -> (Home Assistant service, service-data key for the value)
ACTIONS = {
    "light": {
        **ON_OFF,
        "brightness_pct": ("turn_on", "brightness_pct"),
        "color": ("turn_on", "rgb_color"),
        "warmth": ("turn_on", "color_temp_kelvin"),
        "effect": ("turn_on", "effect"),
    },
    "switch": ON_OFF,
    "fan": {
        **ON_OFF,
        "percentage": ("set_percentage", "percentage"),
        "preset": ("set_preset_mode", "preset_mode"),
    },
    "input_boolean": ON_OFF,
    "humidifier": ON_OFF,
    "siren": ON_OFF,
    "cover": {
        "open": ("open_cover", None),
        "close": ("close_cover", None),
        "stop": ("stop_cover", None),
        "position": ("set_cover_position", "position"),
    },
    "climate": {
        "set_temperature": ("set_temperature", "temperature"),
        "hvac_mode": ("set_hvac_mode", "hvac_mode"),
    },
    "scene": {"turn_on": ("turn_on", None)},
    "script": {"turn_on": ("turn_on", None)},
    "button": {"press": ("press", None)},
    "media_player": {
        "turn_on": ("turn_on", None),
        "turn_off": ("turn_off", None),
        "play": ("media_play", None),
        "pause": ("media_pause", None),
        "stop": ("media_stop", None),
        "previous": ("media_previous_track", None),
        "next": ("media_next_track", None),
        "volume": ("volume_set", "volume_level"),
        "volume_up": ("volume_up", None),
        "volume_down": ("volume_down", None),
        "mute": ("volume_mute", None),
        "unmute": ("volume_mute", None),
        "source": ("select_source", "source"),
        "key": (None, "key"),  # arrows, OK, back, home: through the TV's own integration (REMOTES)
    },
    "vacuum": {"start": ("start", None), "return_to_base": ("return_to_base", None)},
    "lock": {"lock": ("lock", None), "unlock": ("unlock", None)},
    "alarm_control_panel": {
        "arm_home": ("alarm_arm_home", None),
        "arm_away": ("alarm_arm_away", None),
        "disarm": ("alarm_disarm", None),
    },
    "valve": {"open": ("open_valve", None), "close": ("close_valve", None)},
}
# supported_features bits that gate an action (Home Assistant's *EntityFeature flags).
FEATURES = {
    "cover": {"open": 1, "close": 2, "position": 4, "stop": 8},
    "climate": {"set_temperature": 1},
    "media_player": {
        "pause": 1,
        "volume": 4,
        "mute": 8,
        "unmute": 8,
        "previous": 16,
        "next": 32,
        "turn_on": 128,
        "turn_off": 256,
        "volume_up": 1024,
        "volume_down": 1024,
        "source": 2048,
        "stop": 4096,
        "play": 16384,
    },
    "vacuum": {"return_to_base": 16, "start": 8192},
    "fan": {"percentage": 1, "preset": 8},
    "alarm_control_panel": {"arm_home": 1, "arm_away": 2},
    "valve": {"open": 1, "close": 2},
}
SAFE_ATTRIBUTES = (
    "color_mode",
    "current_temperature",
    "temperature",
    "target_temp_step",
    "min_temp",
    "max_temp",
    "hvac_modes",
    "current_position",
    "media_title",
    "media_artist",
    "app_name",
    "source",
    "is_volume_muted",
    "percentage",
    "humidity",
    "unit_of_measurement",
    "device_class",
    "color_temp_kelvin",
    "min_color_temp_kelvin",
    "max_color_temp_kelvin",
    "effect",
    "preset_mode",
)
COLOR_MODES = {"hs", "rgb", "rgbw", "rgbww", "xy"}
# The controls a device's panel draws, derived from what it reports (see `controls`): a value
# action -> its kind. Toggles and one-press buttons (open, play…) are drawn by the room itself.
CONTROL_KINDS = {
    "brightness_pct": "range",
    "color": "color",
    "warmth": "warmth",
    "effect": "choice",
    "percentage": "range",
    "preset": "choice",
    "position": "range",
    "set_temperature": "temperature",
    "hvac_mode": "choice",
    "volume": "range",
    "source": "choice",
}
# Lists a device offers to choose from, by action (capped: some effect lists run long).
CHOICES = {"effect": "effect_list", "preset": "preset_modes", "hvac_mode": "hvac_modes", "source": "source_list"}
# A TV's arrows, OK, back and home, by the Home Assistant integration that runs it:
# integration -> (service domain, service, data field, on its "remote" entity?, {key: name}).
# Names are each integration's own; HouseOS never sends anything else.
NAV = ("DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER", "BACK", "HOME")
REMOTES = {
    "webostv": (
        "webostv",
        "button",
        "button",
        False,
        ("UP", "DOWN", "LEFT", "RIGHT", "ENTER", "BACK", "HOME"),
    ),
    "samsungtv": (
        "remote",
        "send_command",
        "command",
        True,
        ("KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT", "KEY_ENTER", "KEY_RETURN", "KEY_HOME"),
    ),
    "braviatv": (
        "remote",
        "send_command",
        "command",
        True,
        ("Up", "Down", "Left", "Right", "Confirm", "Return", "Home"),
    ),
    "roku": (
        "remote",
        "send_command",
        "command",
        True,
        ("up", "down", "left", "right", "select", "back", "home"),
    ),
    "androidtv_remote": ("remote", "send_command", "command", True, NAV),
    "androidtv": (
        "androidtv",
        "adb_command",
        "command",
        False,
        ("UP", "DOWN", "LEFT", "RIGHT", "CENTER", "BACK", "HOME"),
    ),
    "apple_tv": (
        "remote",
        "send_command",
        "command",
        True,
        ("up", "down", "left", "right", "select", "menu", "home"),
    ),
    "philips_js": (
        "remote",
        "send_command",
        "command",
        True,
        ("CursorUp", "CursorDown", "CursorLeft", "CursorRight", "Confirm", "Back", "Home"),
    ),
}
PRESSES = {"key", "stop", "next", "previous", "volume_up", "volume_down"}
# Sound sent to a soundbar or amplifier: the TV's own level no longer changes what you hear, but
# its volume keys still reach the speakers (HDMI-CEC), so steps replace the slider.
TV_SPEAKERS = {"tv_speaker", "tv_speaker_headphone", "speaker", "internal"}


def remote(entity_id):
    """(service domain, service, data, {key: name}) for this TV's arrows, or None."""
    entities = _cache.get("entities") or {}
    info = entities.get(entity_id) or {}
    spec = REMOTES.get(info.get("platform"))
    if not spec:
        return None
    domain, service, field, on_remote, names = spec
    target = entity_id
    if on_remote:
        target = next(
            (
                other
                for other, found in entities.items()
                if other.startswith("remote.")
                and info.get("device")
                and found.get("device") == info["device"]
            ),
            None,
        )
        if not target:
            return None
    return domain, service, {"entity_id": target}, field, dict(zip(NAV, names))


# One template call maps every allowed entity to its area (its own, else its device's).
AREAS = (
    "[{% for s in states if s.domain in domains %}{{ [s.entity_id, area_name(s.entity_id)] | to_json }}"
    "{% if not loop.last %},{% endif %}{% endfor %}]"
)
# Home Assistant's own registry changes rarely: read it at most once a minute.
REGISTRY_SECONDS = 60
_cache = {
    "key": None,
    "at": 0.0,
    "states": [],
    "areas": {},
    "internal": set(),
    "entities": {},  # entity -> {"platform", "device"} from HA's registry
    "registry_at": 0.0,
}


def available(db):
    """Home Assistant is connected (enabled, with a token): the Smart home room may show."""
    row = db.get(Integration, "home_assistant")
    return bool(row and row.enabled and row.encrypted_secret)


def connection(db):
    config = integration_config(db, "home_assistant")
    token = config.get("token") or config.get("api_key")
    if not config.get("enabled") or not token:
        raise HTTPException(
            409,
            {
                "code": "HOME_UNCONFIGURED",
                "message": "Home Assistant isn't connected. An administrator can connect it in Control Room → Integrations.",
            },
        )
    try:
        base = internal_base(config, "http://127.0.0.1:8123")
    except MediaError as exc:
        raise HTTPException(503, {"code": exc.code, "message": exc.message}) from None
    return base, {"Authorization": "Bearer " + token}, config


def ha(base, headers, path, **kwargs):
    """One short request; failures become plain sentences without addresses or tokens."""
    try:
        return private_json(base, path, headers=headers, timeout=kwargs.pop("timeout", 5), **kwargs)
    except MediaError as exc:
        refused = exc.code == "INTEGRATION_AUTH_EXPIRED"
        raise HTTPException(
            503,
            {
                "code": "HOME_TOKEN_REFUSED" if refused else "HOME_UNREACHABLE",
                "message": "Home Assistant refused HouseOS's token. An administrator needs to create a new one."
                if refused
                else "Home Assistant didn't answer or refused the request. Try again in a moment.",
            },
        ) from None


def policy(config):
    domains = config.get("domains")
    return (
        set(domains) if isinstance(domains, list) else set(DEFAULT_DOMAINS),
        set(config.get("hidden") or []),
    )


def panel(config, entity_id):
    """The controls an admin took off this device's panel (everything it can do shows otherwise)."""
    prefix = entity_id + ":"
    return {item[len(prefix) :] for item in config.get("panel_hidden") or [] if item.startswith(prefix)}


def sensitive(domain, attributes=None):
    """Locks and the like; also scripts (they can do anything) and garage doors, gates and doors."""
    return (
        domain in SENSITIVE_DOMAINS
        or domain not in DEFAULT_DOMAINS
        or domain == "script"
        or (domain == "cover" and (attributes or {}).get("device_class") in {"garage", "gate", "door"})
    )


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def actions(domain, attributes, entity_id=""):
    features = int(number(attributes.get("supported_features")) or 0)
    names = list(ACTIONS.get(domain, {}))
    if domain == "media_player":
        if not attributes.get("source_list"):
            names.remove("source")
        if not remote(entity_id):
            names.remove("key")
    if domain == "light" and not (
        any(mode != "onoff" for mode in attributes.get("supported_color_modes") or []) or features & 1
    ):
        names.remove("brightness_pct")
    if domain == "climate" and not attributes.get("hvac_modes"):
        names.remove("hvac_mode")
    if domain == "light":
        modes = set(attributes.get("supported_color_modes") or [])
        if not modes & COLOR_MODES:
            names.remove("color")
        if "color_temp" not in modes:
            names.remove("warmth")
        if not attributes.get("effect_list"):
            names.remove("effect")
    if domain == "fan" and not attributes.get("preset_modes"):
        names.remove("preset")
    gates = FEATURES.get(domain, {})
    return [name for name in names if name not in gates or features & gates[name]]


def kelvin_range(attributes):
    low = number(attributes.get("min_color_temp_kelvin")) or 2000
    high = number(attributes.get("max_color_temp_kelvin")) or 6500
    return int(low), int(high)


def hex_color(rgb):
    if isinstance(rgb, (list, tuple)) and len(rgb) >= 3 and all(number(c) is not None for c in rgb[:3]):
        return "#" + "".join(f"{max(0, min(255, int(c))):02x}" for c in rgb[:3])
    return None


def controls(domain, attributes, entity_id="", hidden=()):
    """What the device's panel can draw, from what the device itself reports: each value control
    with its kind, range or choices, and whether the admin keeps it on the panel."""
    found = []
    for action in actions(domain, attributes, entity_id):
        kind = CONTROL_KINDS.get(action)
        if not kind:
            continue
        item = {"id": action, "kind": kind, "shown": action not in hidden}
        if kind == "warmth":
            item["min"], item["max"] = kelvin_range(attributes)
        elif kind == "temperature":
            item["min"] = number(attributes.get("min_temp")) or 5
            item["max"] = number(attributes.get("max_temp")) or 35
            item["step"] = number(attributes.get("target_temp_step")) or 0.5
        elif kind == "choice":
            item["options"] = [str(o)[:40] for o in (attributes.get(CHOICES[action]) or [])[:60]]
        found.append(item)
    return found


def entity_json(state, area=None, hidden_controls=()):
    entity_id = state["entity_id"]
    domain = entity_id.split(".")[0]
    attributes = state.get("attributes") or {}
    safe = {key: attributes[key] for key in SAFE_ATTRIBUTES if attributes.get(key) is not None}
    if isinstance(safe.get("hvac_modes"), list):
        safe["hvac_modes"] = [str(mode) for mode in safe["hvac_modes"][:10]]
    if number(attributes.get("brightness")) is not None:
        safe["brightness_pct"] = round(attributes["brightness"] * 100 / 255)
    if number(attributes.get("volume_level")) is not None:
        safe["volume_pct"] = round(attributes["volume_level"] * 100)
    if isinstance(attributes.get("source_list"), list):
        safe["source_list"] = [str(source)[:40] for source in attributes["source_list"][:60]]
    if hex_color(attributes.get("rgb_color")):
        safe["color"] = hex_color(attributes.get("rgb_color"))
    output = attributes.get("sound_output")
    if isinstance(output, str) and output.casefold() not in TV_SPEAKERS:
        safe["external_speakers"] = True  # volume steps, not the slider
    return {
        "id": entity_id,
        "name": str(attributes.get("friendly_name") or entity_id.split(".", 1)[1].replace("_", " "))[:120],
        "domain": domain,
        "area": area,
        "state": str(state.get("state", "unknown"))[:60],
        "attributes": safe,
        "actions": actions(domain, attributes, entity_id),
        "controls": controls(domain, attributes, entity_id, hidden_controls),
        "sensitive": sensitive(domain, attributes),
        "last_changed": str(state.get("last_changed") or "")[:40] or None,
    }


def registry(base, token):
    """Each entity's area and whether Home Assistant marks it internal (a config or diagnostic
    entity, or hidden), read from its registry over the websocket API. Unlike templates this
    works with any user's token. None when it can't be read."""
    kinds = (
        "config/entity_registry/list_for_display",
        "config/device_registry/list",
        "config/area_registry/list",
    )
    try:
        from websockets.sync.client import connect  # installed with uvicorn[standard]

        url = "ws" + base.removeprefix("http") + "/api/websocket"
        with connect(url, open_timeout=5, close_timeout=1, max_size=2**24, proxy=None) as ws:
            ws.recv(timeout=5)  # auth_required
            ws.send(json.dumps({"type": "auth", "access_token": token}))
            if json.loads(ws.recv(timeout=5)).get("type") != "auth_ok":
                return None
            for index, kind in enumerate(kinds, 1):
                ws.send(json.dumps({"id": index, "type": kind}))
            results = {}
            while len(results) < len(kinds):
                message = json.loads(ws.recv(timeout=5))
                if message.get("type") == "result":
                    results[message.get("id")] = message.get("result") if message.get("success") else None
    except Exception:  # best effort: missing module, refused, timeout, odd replies
        return None
    display = results.get(1)
    if not isinstance(display, dict):
        return None
    areas = {a.get("area_id"): a.get("name") for a in results.get(3) or [] if isinstance(a, dict)}
    devices = {d.get("id"): d.get("area_id") for d in results.get(2) or [] if isinstance(d, dict)}
    found = {}
    for entry in display.get("entities") or []:
        if isinstance(entry, dict) and isinstance(entry.get("ei"), str):
            area = areas.get(entry.get("ai") or devices.get(entry.get("di")))
            found[entry["ei"]] = {
                "area": str(area)[:80] if area else None,
                "internal": entry.get("ec") is not None or bool(entry.get("hb")),
                "platform": entry.get("pl"),
                "device": entry.get("di"),
            }
    return found


def entities(base, token):
    """Each entity's integration and device from Home Assistant's registry, read at most once
    a minute (the TV remote needs it without opening the Smart home room)."""
    now = time.monotonic()
    if now - _cache.get("entities_at", 0) > REGISTRY_SECONDS:
        _cache["entities_at"] = now
        found = registry(base, token)
        if found is not None:
            _cache["entities"] = {
                entity: {"platform": info.get("platform"), "device": info.get("device")}
                for entity, info in found.items()
            }
    return _cache.get("entities") or {}


def snapshot(base, headers, domains, refresh=False):
    """Allowed states, their areas and HA's internal entities, shared for about 3 s between
    residents and Nox (the registry for a minute)."""
    key = (base, tuple(sorted(domains)))
    now = time.monotonic()
    # Home Assistant down: say so at once for 20 s rather than wait out its timeout per request.
    if not refresh and _cache.get("failure") and now - _cache.get("failed_at", 0) < 20:
        raise _cache["failure"]
    try:
        return fresh_snapshot(base, headers, domains, refresh, key, now)
    except HTTPException as failure:
        _cache.update(failure=failure, failed_at=now)
        raise


def fresh_snapshot(base, headers, domains, refresh, key, now):
    if refresh or _cache["key"] != key or now - _cache["at"] > 3:
        states = [
            state
            for state in ha(base, headers, "/api/states")
            if isinstance(state, dict) and str(state.get("entity_id", "")).split(".")[0] in domains
        ][:500]
        if refresh or _cache["key"] != key or now - _cache["registry_at"] > REGISTRY_SECONDS:
            found = registry(base, headers["Authorization"].removeprefix("Bearer "))
            if found is not None:
                areas = {entity: info["area"] for entity, info in found.items() if info["area"]}
                internal = {entity for entity, info in found.items() if info["internal"]}
                _cache["entities"] = {
                    entity: {"platform": info.get("platform"), "device": info.get("device")}
                    for entity, info in found.items()
                }
            else:
                internal = set()
                try:
                    pairs = ha(
                        base,
                        headers,
                        "/api/template",
                        method="POST",
                        payload={"template": AREAS, "variables": {"domains": sorted(domains)}},
                    )
                    areas = {
                        pair[0]: pair[1]
                        for pair in pairs
                        if isinstance(pair, list) and len(pair) == 2 and pair[1]
                    }
                except (HTTPException, TypeError):  # templates need an admin token: all "Other"
                    areas = {}
            _cache.update(areas=areas, internal=internal, registry_at=now)
        _cache.update(key=key, at=now, states=states, failure=None)
    return _cache["states"], _cache["areas"], _cache["internal"]


def curated(config):
    """The entities an administrator chose to show, or None while nobody has chosen."""
    return set(config.get("shown") or []) if config.get("curated") else None


def tv_twins(db, config):
    """Media players the TV section already shows: the one mapped to a HouseOS screen, and
    any named exactly like a HouseOS screen."""
    mapped = config.get("device_id") if config.get("receiver_id") else None
    names = {str(name).casefold() for name in db.scalars(select(CinemaDevice.name))}
    # The mapped TV's own controls (button.vidaa_tv_up, switch.vidaa_tv_mute…) live on its remote.
    # ponytail: matched by entity-name prefix; HA's device registry would be exact.
    own = mapped.split(".", 1)[1] + "_" if mapped and "." in mapped else None
    return lambda item: (
        (item["domain"] == "media_player" and (item["id"] == mapped or item["name"].casefold() in names))
        or bool(own and item["id"].split(".", 1)[-1].startswith(own))
    )


def overview(actor, db, refresh=False, choosing=False):
    """What the room shows: the admin's choice, else everything except Home Assistant's
    internal entities; never hidden devices nor TVs the TV section already shows.
    `choosing` (admins) lists every allowed device, each flagged with whether it shows."""
    require_permission(actor, PERMISSION)
    base, headers, config = connection(db)
    domains, hidden = policy(config)
    chosen = curated(config)
    db.commit()  # the connection goes back to the pool while Home Assistant answers
    states, areas, internal = snapshot(base, headers, domains, refresh)
    twin = tv_twins(db, config)
    groups = {}
    for state in states:
        entity_id = state["entity_id"]
        item = entity_json(state, areas.get(entity_id), panel(config, entity_id))
        shows = entity_id not in hidden and (
            entity_id in chosen if chosen is not None else entity_id not in internal
        )
        if twin(item) or not (shows or choosing):
            continue
        if choosing:
            item.update(shown=shows, internal=entity_id in internal)
        groups.setdefault(item["area"], []).append(item)
    user = db.get(User, actor.id)
    return {
        "areas": [
            {"name": area, "entities": sorted(groups[area], key=lambda item: item["name"].casefold())}
            for area in sorted(groups, key=lambda area: (area is None, str(area).casefold()))
        ],
        "curated": chosen is not None,
        "favorites": ((user.preferences or {}).get("home_favorites") or []) if user else [],
        "observed_at": utcnow().isoformat() + "Z",
    }


@router.get("")
def home(refresh: bool = False, choose: bool = False, actor=Depends(require_actor), db=Depends(get_db)):
    return overview(actor, db, refresh, choose and actor.role == "admin")


# A number (percent, degrees) or a short word (a thermostat mode).
Value = float | Annotated[str, Field(max_length=40)] | None


class HomeAction(Input):
    action: str = Field(pattern=r"^[a-z_]{2,40}$")
    value: Value = None


def exposed_domain(config, entity_id):
    domains, hidden = policy(config)
    chosen = curated(config)
    domain = entity_id.split(".")[0]
    if (
        not ENTITY.match(entity_id)
        or domain not in domains
        or entity_id in hidden
        or (chosen is not None and entity_id not in chosen)
    ):
        raise HTTPException(
            404, {"code": "HOME_NOT_EXPOSED", "message": "HouseOS isn't allowed to control this device."}
        )
    return domain


def service_call(state, action, value):
    """The exact Home Assistant service and data for one action, after checking the value."""
    entity_id = state["entity_id"]
    domain = entity_id.split(".")[0]
    attributes = state.get("attributes") or {}
    if state.get("state") == "unavailable":
        raise HTTPException(
            409, {"code": "HOME_UNAVAILABLE", "message": "Home Assistant reports this device unavailable."}
        )
    if action not in actions(domain, attributes, entity_id):
        raise HTTPException(422, {"code": "HOME_ACTION_UNSUPPORTED", "message": "This device can't do that."})
    service, key = ACTIONS[domain][action]
    data = {"entity_id": entity_id}
    if action == "key":
        target_domain, target_service, target, field, keys = remote(entity_id)
        if value not in keys:
            raise HTTPException(422, "Choose an arrow, OK, back or home")
        return target_domain, target_service, {**target, field: keys[value]}
    if action in {"mute", "unmute"}:
        return domain, service, {**data, "is_volume_muted": action == "mute"}
    if key == "source":
        if value not in (attributes.get("source_list") or []):
            raise HTTPException(422, "Choose a source this device offers")
        return domain, service, {**data, key: value}
    if action in CHOICES and action not in {"hvac_mode", "source"}:
        if value not in (attributes.get(CHOICES[action]) or []):
            raise HTTPException(422, "Choose one this device offers")
        return domain, service, {**data, key: value}
    if action == "color":
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise HTTPException(422, "Choose a colour")
        return domain, service, {**data, key: [int(value[i : i + 2], 16) for i in (1, 3, 5)]}
    if action == "warmth":
        low, high = kelvin_range(attributes)
        if number(value) is None or not low <= value <= high:
            raise HTTPException(422, f"Choose a warmth between {low} K and {high} K")
        return domain, service, {**data, key: round(value)}
    if key == "hvac_mode":
        if value not in (attributes.get("hvac_modes") or []):
            raise HTTPException(422, "Choose a mode this thermostat offers")
        data[key] = value
    elif key == "temperature":
        low, high = number(attributes.get("min_temp")), number(attributes.get("max_temp"))
        low, high = 5 if low is None else low, 35 if high is None else high
        if number(value) is None or not low <= value <= high:
            raise HTTPException(422, f"Choose a temperature between {low:g} and {high:g}")
        data[key] = value
    elif key:
        if number(value) is None or not 0 <= value <= 100:
            raise HTTPException(422, "Choose a value between 0 and 100")
        data[key] = value / 100 if key == "volume_level" else round(value)
    return domain, service, data


def reached(domain, action, value, before, after):
    """Whether the state Home Assistant now shows is the one the action asked for."""
    state, attributes = after.get("state"), after.get("attributes") or {}
    if domain in {"scene", "button"}:  # their state is the time they last ran
        return state != before.get("state")
    if domain == "script":
        return attributes.get("last_triggered") != (before.get("attributes") or {}).get("last_triggered")
    if action == "brightness_pct":
        brightness = number(attributes.get("brightness"))
        return (
            state == "off"
            if value == 0
            else state == "on" and brightness is not None and abs(brightness * 100 / 255 - value) <= 2
        )
    if action == "position":
        return attributes.get("current_position") == round(value) or state in {"opening", "closing"}
    if action == "color":
        seen = attributes.get("rgb_color") or []
        want = [int(value[i : i + 2], 16) for i in (1, 3, 5)]
        return state == "on" and len(seen) >= 3 and all(abs(a - b) <= 12 for a, b in zip(seen, want))
    if action == "warmth":
        seen = number(attributes.get("color_temp_kelvin"))
        return state == "on" and seen is not None and abs(seen - value) <= 60
    if action == "effect":
        return attributes.get("effect") == value
    if action == "percentage":
        seen = number(attributes.get("percentage"))
        return seen is not None and abs(seen - value) <= 2
    if action == "preset":
        return attributes.get("preset_mode") == value
    if action == "set_temperature":
        return attributes.get("temperature") == value
    if action == "hvac_mode":
        return state == value
    if action == "volume":
        level = number(attributes.get("volume_level"))
        return level is not None and abs(level - value / 100) < 0.02
    if action in {"mute", "unmute"}:
        return attributes.get("is_volume_muted") is (action == "mute")
    if action == "source":
        return attributes.get("source") == value
    if domain == "media_player" and action == "turn_on":
        return state not in {"off", "standby", "unavailable"}
    if action == "toggle":
        return state in {"on", "off"} and state != before.get("state")
    return state in {
        "turn_on": {"on"},
        "turn_off": {"off"},
        "open": {"open", "opening"},
        "close": {"closed", "closing"},
        "stop": {"open", "closed", "stopped"},
        "play": {"playing"},
        "pause": {"paused"},
        "start": {"cleaning"},
        "return_to_base": {"returning", "docked"},
        "lock": {"locked", "locking"},
        "unlock": {"unlocked", "unlocking"},
        "arm_home": {"armed_home", "arming"},
        "arm_away": {"armed_away", "arming"},
        "disarm": {"disarmed"},
    }.get(action, set())


def read_state(base, headers, entity_id):
    return ha(base, headers, "/api/states/" + quote(entity_id, safe=""))


def control(db, actor, entity_id, action, value=None, confirmed=False):
    """Check policy and value, then either ask for a confirmation (sensitive devices) or act."""
    require_permission(actor, PERMISSION)
    base, headers, config = connection(db)
    domain = exposed_domain(config, entity_id)
    before = read_state(base, headers, entity_id)
    service_domain, service, data = service_call(before, action, value)
    item = entity_json(before, _cache["areas"].get(entity_id), panel(config, entity_id))
    if sensitive(domain, before.get("attributes")) and not confirmed:
        op = Operation(
            actor_id=actor.id,
            kind="home.control",
            state="needs_confirmation",
            data={"entity_id": entity_id, "action": action, "value": value},
            expires_at=utcnow() + timedelta(seconds=120),
        )
        db.add(op)
        db.commit()
        return {
            "status": "needs_confirmation",
            "confirmation_id": op.id,
            "name": item["name"],
            "preview": {
                "device": item["name"],
                "area": item["area"],
                "action": action.replace("_", " "),
                "value": value,
                "impact": "A sensitive device: nothing is sent until you confirm.",
                "expires_at": op.expires_at.isoformat() + "Z",
            },
        }
    ha(base, headers, f"/api/services/{service_domain}/{service}", method="POST", payload=data, timeout=10)
    # Accepted is not done: look again (briefly) until Home Assistant shows the result. A key
    # press or a track skip has no state to wait for.
    for attempt in range(1 if action in PRESSES else 4):
        if attempt:
            time.sleep(0.5)
        after = read_state(base, headers, entity_id)
        if reached(domain, action, value, before, after):
            break
    status = "completed" if reached(domain, action, value, before, after) else "command_sent"
    emit(db, "audit.home_control", {"entity_id": entity_id, "action": action, "status": status}, actor.id)
    db.commit()
    _cache["at"] = 0.0
    return {
        "status": status,
        "name": item["name"],
        "action": action,
        "value": value,
        "entity": entity_json(after, item["area"], panel(config, entity_id)),
    }


@router.post("/{entity_id}/action")
def act(entity_id: str, body: HomeAction, actor=Depends(require_actor), db=Depends(get_db)):
    return control(db, actor, entity_id, body.action, body.value)


@router.post("/confirmations/{identity}")
def confirm(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, PERMISSION)
    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "home.control"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Confirmation expired or consumed")
    row.state = "accepted"  # one confirmation sends at most one command
    db.commit()
    result = control(db, actor, row.data["entity_id"], row.data["action"], row.data["value"], confirmed=True)
    row.state, row.result = result["status"], {"status": result["status"]}
    db.commit()
    return result


EntityId = Annotated[str, Field(pattern=ENTITY.pattern)]


class Selection(Input):
    shown: list[EntityId] = Field(max_length=500)


@router.put("/selection")
def choose(body: Selection, actor=Depends(require_admin), db=Depends(get_db)):
    """Administrators choose exactly what the room (and Nox) shows; new devices stay out until chosen."""
    row = db.get(Integration, "home_assistant")
    if not row:
        raise HTTPException(404, "Home Assistant isn't connected")
    shown = sorted(set(body.shown))
    row.config = {
        **row.config,
        "shown": shown,
        "curated": True,
        "hidden": sorted(set(row.config.get("hidden") or []) - set(shown)),
    }
    emit(db, "audit.home_policy_updated", {"shown": len(shown)}, actor.id)
    db.commit()
    _cache["at"] = 0.0
    return {"status": "completed", "shown": len(shown)}


@router.get("/{entity_id}/inspect")
def inspect(entity_id: str, actor=Depends(require_admin), db=Depends(get_db)):
    """Look closer at one device (admins): everything it reports, and every control HouseOS can
    draw from that, each marked shown or not on its panel."""
    base, headers, config = connection(db)
    domain = exposed_domain(config, entity_id)
    db.commit()
    state = read_state(base, headers, entity_id)
    attributes = state.get("attributes") or {}
    # Plain facts only: no pictures or links (a media player's carries an access token).
    reported = {
        str(key)[:60]: (value if isinstance(value, (int, float, bool)) else str(value)[:120])
        for key, value in list(attributes.items())[:60]
        if not re.search(r"token|picture|url|image", str(key), re.I)
    }
    return {
        "id": entity_id,
        "domain": domain,
        "state": str(state.get("state", "unknown"))[:60],
        "name": entity_json(state)["name"],
        "controls": controls(domain, attributes, entity_id, panel(config, entity_id)),
        "reported": reported,
    }


class PanelControls(Input):
    hidden: list[Annotated[str, Field(pattern=r"^[a-z_]{2,40}$")]] = Field(max_length=40)


@router.put("/{entity_id}/controls")
def choose_controls(entity_id: str, body: PanelControls, actor=Depends(require_admin), db=Depends(get_db)):
    """Administrators choose which of a device's controls its panel shows."""
    row = db.get(Integration, "home_assistant")
    if not row or not ENTITY.match(entity_id):
        raise HTTPException(404, "Home Assistant isn't connected")
    others = [item for item in row.config.get("panel_hidden") or [] if not item.startswith(entity_id + ":")]
    row.config = {**row.config, "panel_hidden": others + [entity_id + ":" + x for x in sorted(set(body.hidden))]}
    emit(db, "audit.home_policy_updated", {"entity_id": entity_id, "hidden_controls": len(body.hidden)}, actor.id)
    db.commit()
    _cache["at"] = 0.0
    return {"status": "completed", "hidden": sorted(set(body.hidden))}


class Favorites(Input):
    favorites: list[EntityId] = Field(max_length=100)


@router.put("/favorites")
def favorites(body: Favorites, actor=Depends(require_actor), db=Depends(get_db)):
    """Each resident's own devices pinned at the top of the room."""
    require_permission(actor, PERMISSION)
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    chosen = list(dict.fromkeys(body.favorites))
    user.preferences = {**(user.preferences or {}), "home_favorites": chosen}
    db.commit()
    return {"favorites": chosen}
