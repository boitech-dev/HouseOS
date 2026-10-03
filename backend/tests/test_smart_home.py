"""Smart home through Home Assistant: exposure policy, exact services, sensitive confirmations,
areas, Nox name resolution and permissions. Home Assistant is a mocked fixture only."""

import copy
import json
import httpx
import pytest
from fastapi import HTTPException
from houseos import assistant as a, assistant_tools as tools, home, integrations, tool_home
from houseos.auth import Actor, RESIDENT
from houseos.models import Integration, Operation
from test_providers import mock_catalog

BASE = "http://192.0.2.18:8123"
STATES = {
    "light.living_ceiling": ("off", {"friendly_name": "Ceiling", "supported_color_modes": ["brightness"]}),
    "light.living_lamp": (
        "on",
        {"friendly_name": "Lamp", "supported_color_modes": ["hs"], "brightness": 255},
    ),
    "light.kitchen": ("off", {"friendly_name": "Kitchen light", "supported_color_modes": ["onoff"]}),
    "cover.bedroom_blind": (
        "closed",
        {"friendly_name": "Blind", "supported_features": 15, "current_position": 0},
    ),
    "climate.hall": (
        "heat",
        {
            "friendly_name": "Thermostat",
            "supported_features": 1,
            "hvac_modes": ["off", "heat"],
            "temperature": 19,
            "min_temp": 7,
            "max_temp": 30,
            "current_temperature": 18.5,
        },
    ),
    "lock.front_door": ("locked", {"friendly_name": "Front door"}),
    "sensor.outside": ("12", {"friendly_name": "Outside", "unit_of_measurement": "°C"}),
    "scene.movie_night": ("2026-09-01T20:00:00", {"friendly_name": "Movie night"}),
    "media_player.salon": ("paused", {"friendly_name": "Salon speaker", "supported_features": 16389}),
}
AREAS = {
    "light.living_ceiling": "Living room",
    "light.living_lamp": "Living room",
    "light.kitchen": "Kitchen",
    "cover.bedroom_blind": "Bedroom",
    "lock.front_door": "Hall",
}
# Service -> how the fake Home Assistant changes the entity.
EFFECTS = {
    "light/turn_on": lambda s, d: ("on", {"brightness": round(d.get("brightness_pct", 100) * 255 / 100)}),
    "light/turn_off": lambda s, d: ("off", {}),
    "light/toggle": lambda s, d: ("off" if s == "on" else "on", {}),
    "cover/set_cover_position": lambda s, d: ("open", {"current_position": d["position"]}),
    "climate/set_temperature": lambda s, d: (s, {"temperature": d["temperature"]}),
    "lock/unlock": lambda s, d: ("unlocked", {}),
    "scene/turn_on": lambda s, d: ("2026-09-24T21:00:00", {}),
}


@pytest.fixture
def ha(setup, monkeypatch):
    db, (admin, _) = setup
    integrations.save_integration(
        "home_assistant",
        integrations.IntegrationInput(enabled=True, config={"base_url": BASE}, secret="ha-token"),
        admin,
        db,
    )
    monkeypatch.setattr(
        home,
        "_cache",
        {"key": None, "at": 0.0, "states": [], "areas": {}, "internal": set(), "registry_at": 0},
    )
    monkeypatch.setattr(home, "registry", lambda base, token: None)  # no websocket: template areas
    monkeypatch.setattr(home.time, "sleep", lambda seconds: None)
    states = copy.deepcopy(STATES)
    calls = []
    frozen = set()  # entities whose device ignores commands

    def state(entity_id):
        value, attributes = states[entity_id]
        return {"entity_id": entity_id, "state": value, "attributes": attributes}

    def reply(request):
        assert request.headers["authorization"] == "Bearer ha-token"
        path = request.url.path
        if path == "/api/states":
            return httpx.Response(200, json=[state(entity_id) for entity_id in states])
        if path.startswith("/api/states/"):
            return httpx.Response(200, json=state(path.rsplit("/", 1)[1]))
        if path == "/api/template":
            body = json.loads(request.content)
            assert "area_name" in body["template"]
            domains = body["variables"]["domains"]
            pairs = [[e, AREAS.get(e)] for e in states if e.split(".")[0] in domains]
            return httpx.Response(200, text=json.dumps(pairs))  # rendered template text
        assert request.method == "POST" and path.startswith("/api/services/")
        service, data = path.removeprefix("/api/services/"), json.loads(request.content)
        calls.append((service, data))
        if data["entity_id"] not in frozen and service in EFFECTS:
            value, attributes = states[data["entity_id"]]
            new_value, changes = EFFECTS[service](value, data)
            states[data["entity_id"]] = (new_value, {**attributes, **changes})
        return httpx.Response(200, json=[])

    mock_catalog(monkeypatch, reply)
    resident = Actor("resident-1", "Rita", "resident", RESIDENT)
    return db, admin, resident, calls, frozen


def names(overview):
    return {area["name"]: [e["id"] for e in area["entities"]] for area in overview["areas"]}


def test_default_exposure_groups_by_area(ha):
    db, admin, resident, calls, _ = ha
    result = home.overview(resident, db)
    # Default domains only: no lock (sensitive) and no sensor; areas sorted, "Other" (None) last.
    assert names(result) == {
        "Bedroom": ["cover.bedroom_blind"],
        "Kitchen": ["light.kitchen"],
        "Living room": ["light.living_ceiling", "light.living_lamp"],
        None: ["scene.movie_night", "media_player.salon", "climate.hall"],
    }
    assert list(names(result)) == ["Bedroom", "Kitchen", "Living room", None]
    entities = {e["id"]: e for area in result["areas"] for e in area["entities"]}
    assert "lock.front_door" not in entities and "sensor.outside" not in entities
    assert entities["light.living_ceiling"]["actions"] == ["toggle", "turn_on", "turn_off", "brightness_pct"]
    assert entities["light.kitchen"]["actions"] == ["toggle", "turn_on", "turn_off"]  # on/off only
    assert entities["light.living_lamp"]["attributes"]["brightness_pct"] == 100
    assert entities["cover.bedroom_blind"]["actions"] == ["open", "close", "stop", "position"]
    assert entities["media_player.salon"]["actions"] == ["play", "pause", "volume"]
    assert entities["climate.hall"]["attributes"]["current_temperature"] == 18.5
    assert "friendly_name" not in entities["climate.hall"]["attributes"] and not calls


def test_admin_policy_hides_and_enables_domains(ha):
    db, admin, resident, _, _ = ha
    row = db.get(Integration, "home_assistant")
    row.config = {**row.config, "hidden": ["light.kitchen"]}  # hidden before selections existed
    db.commit()
    assert "Kitchen" not in names(home.overview(resident, db, refresh=True))
    # Only an administrator sees hidden devices (to show them again); a resident never does.
    assert "Kitchen" not in names(home.home(True, True, resident, db))
    kitchen = home.home(True, True, admin, db)["areas"][1]
    assert kitchen["name"] == "Kitchen" and kitchen["entities"][0]["shown"] is False
    with pytest.raises(HTTPException) as denied:
        home.control(db, resident, "light.kitchen", "turn_on")
    assert denied.value.status_code == 404
    row = db.get(Integration, "home_assistant")
    row.config = {**row.config, "domains": ["lock", "light"]}
    db.commit()
    assert list(names(home.overview(resident, db, refresh=True))) == ["Hall", "Living room"]


def test_integration_accepts_only_valid_device_lists():
    integrations.check_config("home_assistant", {"domains": ["light", "lock"], "hidden": ["light.hall"]})
    for name, config in [
        ("jellyfin", {"domains": ["light"]}),
        ("home_assistant", {"domains": "light"}),
        ("home_assistant", {"hidden": ["../api"]}),
        ("home_assistant", {"device_id": ["media_player.tv"]}),
    ]:
        with pytest.raises(HTTPException):
            integrations.check_config(name, config)


@pytest.mark.parametrize(
    "entity_id,state,attributes,action,value,service,data",
    [
        (
            "light.a",
            "off",
            {"supported_color_modes": ["brightness"]},
            "brightness_pct",
            40,
            "turn_on",
            {"brightness_pct": 40},
        ),
        ("light.a", "on", {}, "toggle", None, "toggle", {}),
        ("switch.a", "on", {}, "turn_off", None, "turn_off", {}),
        ("fan.a", "off", {}, "turn_on", None, "turn_on", {}),
        ("input_boolean.a", "off", {}, "toggle", None, "toggle", {}),
        ("cover.a", "open", {"supported_features": 15}, "stop", None, "stop_cover", {}),
        (
            "cover.a",
            "open",
            {"supported_features": 15},
            "position",
            30,
            "set_cover_position",
            {"position": 30},
        ),
        (
            "climate.a",
            "heat",
            {"supported_features": 1},
            "set_temperature",
            21.5,
            "set_temperature",
            {"temperature": 21.5},
        ),
        (
            "climate.a",
            "heat",
            {"hvac_modes": ["off", "heat"]},
            "hvac_mode",
            "off",
            "set_hvac_mode",
            {"hvac_mode": "off"},
        ),
        ("scene.a", "x", {}, "turn_on", None, "turn_on", {}),
        ("script.a", "off", {}, "turn_on", None, "turn_on", {}),
        ("button.a", "x", {}, "press", None, "press", {}),
        (
            "media_player.a",
            "playing",
            {"supported_features": 4},
            "volume",
            30,
            "volume_set",
            {"volume_level": 0.3},
        ),
        ("media_player.a", "paused", {"supported_features": 16384}, "play", None, "media_play", {}),
        ("vacuum.a", "docked", {"supported_features": 8192}, "start", None, "start", {}),
        ("vacuum.a", "cleaning", {"supported_features": 16}, "return_to_base", None, "return_to_base", {}),
        ("lock.a", "locked", {}, "unlock", None, "unlock", {}),
        ("alarm_control_panel.a", "armed_away", {}, "disarm", None, "alarm_disarm", {}),
        ("valve.a", "open", {"supported_features": 2}, "close", None, "close_valve", {}),
    ],
)
def test_each_action_maps_to_its_exact_service(entity_id, state, attributes, action, value, service, data):
    entity = {"entity_id": entity_id, "state": state, "attributes": attributes}
    domain = entity_id.split(".")[0]
    assert home.service_call(entity, action, value) == (domain, service, {"entity_id": entity_id, **data})


@pytest.mark.parametrize(
    "entity_id,attributes,action,value",
    [
        ("light.a", {"supported_color_modes": ["onoff"]}, "brightness_pct", 50),  # not dimmable
        ("light.a", {"supported_color_modes": ["brightness"]}, "brightness_pct", 150),
        ("climate.a", {"supported_features": 1, "max_temp": 25}, "set_temperature", 28),
        ("climate.a", {"hvac_modes": ["off", "heat"]}, "hvac_mode", "cool"),
        ("cover.a", {"supported_features": 3}, "position", 50),  # open/close only
        ("switch.a", {}, "press", None),  # another domain's action
        ("sensor.a", {}, "turn_on", None),  # read-only domain
    ],
)
def test_unsupported_actions_and_values_are_refused(entity_id, attributes, action, value):
    with pytest.raises(HTTPException) as refused:
        home.service_call({"entity_id": entity_id, "state": "on", "attributes": attributes}, action, value)
    assert refused.value.status_code == 422


def test_control_reports_the_observed_state(ha):
    db, admin, resident, calls, frozen = ha
    result = home.act(
        "light.living_ceiling", home.HomeAction(action="brightness_pct", value=40), resident, db
    )
    assert calls == [("light/turn_on", {"entity_id": "light.living_ceiling", "brightness_pct": 40})]
    assert result["status"] == "completed"
    assert result["entity"]["state"] == "on" and result["entity"]["attributes"]["brightness_pct"] == 40
    # Home Assistant accepted the call but the device did not change: sent, not done.
    frozen.add("cover.bedroom_blind")
    result = home.act("cover.bedroom_blind", home.HomeAction(action="position", value=60), resident, db)
    assert result["status"] == "command_sent" and result["entity"]["state"] == "closed"


def test_sensitive_devices_wait_for_confirmation(ha):
    db, admin, resident, calls, _ = ha
    row = db.get(Integration, "home_assistant")
    row.config = {**row.config, "domains": [*home.DEFAULT_DOMAINS, "lock"]}
    db.commit()
    prepared = home.act("lock.front_door", home.HomeAction(action="unlock"), resident, db)
    assert prepared["status"] == "needs_confirmation" and not calls
    assert prepared["preview"]["device"] == "Front door"
    result = home.confirm(prepared["confirmation_id"], resident, db)
    assert calls == [("lock/unlock", {"entity_id": "lock.front_door"})]
    assert result["status"] == "completed" and result["entity"]["state"] == "unlocked"
    assert db.get(Operation, prepared["confirmation_id"]).state == "completed"
    with pytest.raises(HTTPException) as again:  # one confirmation, one command
        home.confirm(prepared["confirmation_id"], resident, db)
    assert again.value.status_code == 409 and len(calls) == 1
    # Nox's card confirms through the assistant's confirmation route.
    nox = tool_home.home_control(tool_home.HomeControl(name="front door", action="lock"), resident, db)
    assert nox["confirmation_path"] == "/assistant/confirmations/" + nox["confirmation_id"]
    a.confirm_message(nox["confirmation_id"], resident, db)
    assert calls[-1] == ("lock/lock", {"entity_id": "lock.front_door"})


def test_permission_is_required(ha):
    db, admin, resident, calls, _ = ha
    guest = Actor("guest-1", "Gus", "guest", frozenset({"music.read", "music.queue"}))
    for attempt in (
        lambda: home.overview(guest, db),
        lambda: home.control(db, guest, "light.kitchen", "turn_on"),
        lambda: tool_home.home_list(tool_home.HomeList(), guest, db),
    ):
        with pytest.raises(HTTPException) as denied:
            attempt()
        assert denied.value.status_code == 403
    assert not calls and "home.control" in RESIDENT
    row = db.get(Integration, "home_assistant")
    row.enabled = False
    db.commit()
    assert home.available(db) is False
    with pytest.raises(HTTPException) as unconfigured:
        home.overview(resident, db)
    assert unconfigured.value.detail["code"] == "HOME_UNCONFIGURED"


def test_nox_resolves_names_and_asks_when_ambiguous(ha):
    db, admin, resident, calls, _ = ha
    control = lambda **kw: tool_home.home_control(tool_home.HomeControl(**kw), resident, db)  # noqa: E731
    question = control(name="the living room lights", action="turn_off")
    assert question["status"] == "needs_clarification" and not calls
    assert {m["id"] for m in question["matches"]} == {"light.living_ceiling", "light.living_lamp"}
    assert control(name="ceiling", action="turn_on")["state"] == "on"
    assert control(name="kitchen lights", action="toggle")["name"] == "Kitchen light"
    assert (
        control(name="the thermostat", action="set_temperature", value=21)["attributes"]["temperature"] == 21
    )
    assert control(name="blinds", action="position", value=50)["attributes"]["current_position"] == 50
    assert control(name="movie night", action="turn_on")["status"] == "completed"
    assert control(name="garage door", action="turn_on")["status"] == "needs_clarification"
    assert [service for service, _ in calls] == [
        "light/turn_on",
        "light/toggle",
        "climate/set_temperature",
        "cover/set_cover_position",
        "scene/turn_on",
    ]
    listed = tool_home.home_list(tool_home.HomeList(area="living room"), resident, db)
    assert {item["id"] for item in listed["items"]} == {"light.living_ceiling", "light.living_lamp"}
    assert tools.action_recap("home_control", {}, question, resident, db) is None


def test_nox_has_the_tools_everywhere_it_should():
    assert {"home_list", "home_control"} <= set(tools.tool_registry("general"))
    assert {"home_list", "home_control"} <= set(tools.tool_registry("home"))
    assert tools.ContextSwitch(context="home").context == "home"
    assert a.initial_context("Turn off the living room lights") == "home"
    assert a.initial_context("Éteins les lumières du salon") == "home"


def test_registry_hides_internal_entities_and_gives_areas_to_any_token(ha, monkeypatch):
    db, admin, resident, _, _ = ha
    registry = {
        "light.kitchen": {"area": "Kitchen", "internal": False},
        "media_player.salon": {"area": "Living room", "internal": False},
        "scene.movie_night": {"area": None, "internal": True},  # e.g. diagnostic or hidden in HA
    }
    monkeypatch.setattr(home, "registry", lambda base, token: registry)
    result = names(home.overview(resident, db, refresh=True))
    assert result["Living room"] == ["media_player.salon"] and "scene.movie_night" not in result[None]
    listed = tool_home.home_list(tool_home.HomeList(), resident, db)
    assert "scene.movie_night" not in {item["id"] for item in listed["items"]}


def test_nox_lists_only_working_devices_unless_asked(monkeypatch):
    items = [
        {"id": "light.a", "name": "A", "area": None, "domain": "light", "state": "on"},
        {"id": "light.b", "name": "B", "area": None, "domain": "light", "state": "unavailable"},
    ]
    for item in items:
        item.update(actions=[], attributes={})
    monkeypatch.setattr(tool_home, "entities", lambda actor, db: items)
    assert tool_home.home_list(tool_home.HomeList(), None, None)["count"] == 1
    assert tool_home.home_list(tool_home.HomeList(include_unavailable=True), None, None)["count"] == 2


def test_registry_reads_areas_and_categories_over_the_websocket(monkeypatch):
    import websockets.sync.client as client

    sent = []
    replies = [
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {"id": 3, "type": "result", "success": True, "result": [{"area_id": "k", "name": "Kitchen"}]},
        {"id": 2, "type": "result", "success": True, "result": [{"id": "d1", "area_id": "k"}]},
        {
            "id": 1,
            "type": "result",
            "success": True,
            "result": {
                "entities": [
                    {"ei": "light.a", "di": "d1"},  # the device's area
                    {"ei": "button.restart", "di": "d1", "ec": 1},  # diagnostic
                    {"ei": "switch.b", "hb": True},  # hidden in Home Assistant
                ]
            },
        },
    ]

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def recv(self, timeout):
            return json.dumps(replies.pop(0))

        def send(self, text):
            sent.append(json.loads(text))

    monkeypatch.setattr(client, "connect", lambda url, **kw: sent.append(url) or Socket())
    found = home.registry("https://ha.local:8123", "tok")
    assert sent[0] == "wss://ha.local:8123/api/websocket" and sent[1]["access_token"] == "tok"
    assert found == {
        "light.a": {"area": "Kitchen", "internal": False, "platform": None, "device": "d1"},
        "button.restart": {"area": "Kitchen", "internal": True, "platform": None, "device": "d1"},
        "switch.b": {"area": None, "internal": True, "platform": None, "device": None},
    }

    def refused(url, **kw):
        raise OSError("refused")

    monkeypatch.setattr(client, "connect", refused)
    assert home.registry("http://ha.local:8123", "tok") is None


def test_admin_choice_is_what_everyone_and_nox_see(ha):
    db, admin, resident, calls, _ = ha
    row = db.get(Integration, "home_assistant")
    row.config = {**row.config, "hidden": ["light.kitchen"]}  # hidden before selections existed
    db.commit()
    home.choose(home.Selection(shown=["light.kitchen", "climate.hall"]), admin, db)
    config = db.get(Integration, "home_assistant").config
    assert config["curated"] is True and config["hidden"] == []  # chosen again: no longer hidden
    integrations.check_config("home_assistant", config)
    result = home.overview(resident, db, refresh=True)
    assert result["curated"] and names(result) == {"Kitchen": ["light.kitchen"], None: ["climate.hall"]}
    listed = tool_home.home_list(tool_home.HomeList(), resident, db)
    assert {item["id"] for item in listed["items"]} == {"light.kitchen", "climate.hall"}
    with pytest.raises(HTTPException) as denied:
        home.control(db, resident, "light.living_ceiling", "turn_on")
    assert denied.value.status_code == 404 and not calls
    choosing = {
        e["id"]: e["shown"] for area in home.home(True, True, admin, db)["areas"] for e in area["entities"]
    }
    assert choosing["light.kitchen"] and not choosing["light.living_ceiling"]
    with pytest.raises(HTTPException):
        integrations.check_config("home_assistant", {"shown": ["not an entity"]})


def test_tv_section_owns_the_houses_tvs(ha):
    from houseos.cinema_models import CinemaDevice
    from houseos.house_settings import public_settings

    db, admin, resident, _, _ = ha
    db.add(CinemaDevice(id="tv-1", name="Living room TV", adapter="cast", address="192.0.2.21"))
    db.commit()
    assert "media_player.salon" in names(home.overview(resident, db, refresh=True))[None]
    row = db.get(Integration, "home_assistant")
    row.config = {**row.config, "device_id": "media_player.salon", "receiver_id": "tv-1"}
    db.commit()  # the TV mapped to a HouseOS screen
    assert "media_player.salon" not in names(home.overview(resident, db, refresh=True))[None]
    twin = home.tv_twins(db, row.config)  # and its own remote keys stay on its remote
    assert twin({"domain": "button", "id": "button.salon_up", "name": "Salon Up"})
    assert not twin({"domain": "button", "id": "button.salonette_up", "name": "Up"})
    db.get(CinemaDevice, "tv-1").name = "Salon speaker"
    row.config = {key: value for key, value in row.config.items() if key != "receiver_id"}
    db.commit()  # or named exactly like one
    assert "media_player.salon" not in names(home.overview(resident, db, refresh=True))[None]
    row.enabled = False
    db.commit()
    settings = public_settings(admin, db)
    assert settings["smart_home"] is True and settings["home_assistant"] is False


def test_favorites_belong_to_each_person(ha):
    db, admin, resident, _, _ = ha
    chosen = ["light.kitchen", "light.kitchen", "cover.bedroom_blind"]
    home.favorites(home.Favorites(favorites=chosen), admin, db)
    assert home.overview(admin, db)["favorites"] == ["light.kitchen", "cover.bedroom_blind"]
    assert home.overview(resident, db)["favorites"] == []


# An LG webOS TV whose sound goes to a soundbar (its real Home Assistant attributes).
LG = {
    "supported_features": 24381,
    "source_list": ["HDMI 1", "Netflix", "YouTube"],
    "source": "Netflix",
    "sound_output": "external_arc",
    "volume_level": 0.71,
    "is_volume_muted": False,
}


def test_a_tv_gets_every_control_it_reports(monkeypatch):
    monkeypatch.setitem(
        home._cache, "entities", {"media_player.oled": {"platform": "webostv", "device": "d"}}
    )
    item = home.entity_json({"entity_id": "media_player.oled", "state": "playing", "attributes": LG})
    assert set(item["actions"]) == {
        "turn_off",
        "play",
        "pause",
        "stop",
        "previous",
        "next",
        "volume",
        "volume_up",
        "volume_down",
        "mute",
        "unmute",
        "source",
        "key",
    }  # no turn_on: Home Assistant has no way to wake this TV yet
    assert item["attributes"]["external_speakers"] and item["attributes"]["source_list"][1] == "Netflix"
    state = {"entity_id": "media_player.oled", "state": "playing", "attributes": LG}
    assert home.service_call(state, "source", "YouTube") == (
        "media_player",
        "select_source",
        {"entity_id": "media_player.oled", "source": "YouTube"},
    )
    assert home.service_call(state, "mute", None)[2]["is_volume_muted"] is True
    assert home.service_call(state, "key", "DPAD_UP") == (
        "webostv",
        "button",
        {"entity_id": "media_player.oled", "button": "UP"},
    )
    for action, value in (("source", "Hulu"), ("key", "POWER")):
        with pytest.raises(HTTPException):
            home.service_call(state, action, value)


def test_brand_remotes_use_the_tvs_own_remote_entity(monkeypatch):
    monkeypatch.setitem(
        home._cache,
        "entities",
        {
            "media_player.samsung": {"platform": "samsungtv", "device": "s"},
            "remote.samsung": {"platform": "samsungtv", "device": "s"},
            "media_player.sony": {"platform": "braviatv", "device": "b"},  # its remote is off
        },
    )
    tv = {"entity_id": "media_player.samsung", "state": "on", "attributes": {"supported_features": 1}}
    assert home.service_call(tv, "key", "BACK") == (
        "remote",
        "send_command",
        {"entity_id": "remote.samsung", "command": "KEY_RETURN"},
    )
    sony = home.entity_json({"entity_id": "media_player.sony", "state": "on", "attributes": {}})
    assert "key" not in sony["actions"] and "external_speakers" not in sony["attributes"]


BULB = {
    "supported_color_modes": ["color_temp", "hs"],
    "min_color_temp_kelvin": 2200,
    "max_color_temp_kelvin": 6500,
    "effect_list": ["colorloop", "candle"],
}


@pytest.mark.parametrize(
    "entity_id,attributes,action,value,service,data",
    [
        ("light.a", BULB, "color", "#ff8000", "turn_on", {"rgb_color": [255, 128, 0]}),
        ("light.a", BULB, "warmth", 2700, "turn_on", {"color_temp_kelvin": 2700}),
        ("light.a", BULB, "effect", "candle", "turn_on", {"effect": "candle"}),
        ("fan.a", {"supported_features": 1}, "percentage", 40, "set_percentage", {"percentage": 40}),
        (
            "fan.a",
            {"supported_features": 8, "preset_modes": ["sleep", "auto"]},
            "preset",
            "sleep",
            "set_preset_mode",
            {"preset_mode": "sleep"},
        ),
    ],
)
def test_what_a_device_reports_becomes_a_control(entity_id, attributes, action, value, service, data):
    entity = {"entity_id": entity_id, "state": "on", "attributes": attributes}
    assert home.service_call(entity, action, value) == (entity_id.split(".")[0], service, {"entity_id": entity_id, **data})


@pytest.mark.parametrize(
    "attributes,action,value",
    [
        ({"supported_color_modes": ["brightness"]}, "color", "#ff0000"),  # white-only bulb
        ({"supported_color_modes": ["hs"]}, "warmth", 3000),  # no colour temperature
        (BULB, "warmth", 9000),  # outside its range
        (BULB, "color", "red"),
        (BULB, "effect", "disco"),  # not one it offers
    ],
)
def test_controls_a_device_lacks_are_refused(attributes, action, value):
    with pytest.raises(HTTPException) as refused:
        home.service_call({"entity_id": "light.a", "state": "on", "attributes": attributes}, action, value)
    assert refused.value.status_code == 422


def test_panel_controls_follow_the_device_and_the_admins_choice():
    found = {c["id"]: c for c in home.controls("light", BULB, "light.a", {"effect"})}
    assert set(found) == {"brightness_pct", "color", "warmth", "effect"}
    assert found["warmth"]["min"] == 2200 and found["warmth"]["max"] == 6500
    assert found["effect"]["options"] == ["colorloop", "candle"] and found["effect"]["shown"] is False
    assert [c["id"] for c in home.controls("light", {"supported_color_modes": ["onoff"]})] == []


def test_admins_look_closer_and_choose_a_panels_controls(ha):
    db, admin, resident, calls, frozen = ha
    seen = home.inspect("light.living_lamp", admin, db)
    assert {c["id"] for c in seen["controls"]} == {"brightness_pct", "color"}
    assert seen["reported"]["supported_color_modes"] == str(["hs"])
    home.choose_controls("light.living_lamp", home.PanelControls(hidden=["color"]), admin, db)
    lamp = next(
        e for area in home.overview(admin, db, refresh=True)["areas"] for e in area["entities"] if e["id"] == "light.living_lamp"
    )
    assert {c["id"]: c["shown"] for c in lamp["controls"]} == {"brightness_pct": True, "color": False}
    home.choose_controls("light.living_lamp", home.PanelControls(hidden=[]), admin, db)
    assert not db.get(Integration, "home_assistant").config["panel_hidden"]
