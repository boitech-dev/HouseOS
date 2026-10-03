"""TV remote: pairing, the key allowlist, what each TV offers, and Nox's tool. The Android TV
Remote library, Cast and Home Assistant are fakes; no real TV is contacted."""

import json
import sys
import types

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from houseos import tv_remote, cinema_cast, cinema_tv, integrations, tool_tv
from houseos.auth import Actor, RESIDENT
from houseos.cinema_models import CinemaDevice

CODE = "A1B2C3"


class InvalidAuth(Exception):
    pass


class CannotConnect(Exception):
    pass


class FakeRemote:
    """Enough of androidtvremote2.AndroidTVRemote: pairing, connecting and key presses."""

    tv = {"paired": set(), "down": set(), "keys": [], "pairings": 0}

    def __init__(self, name, certfile, keyfile, host, **kw):
        self.name, self.certfile, self.keyfile, self.host = name, certfile, keyfile, host
        self.is_on, self.current_app = True, "com.google.android.youtube.tv"
        self.volume_info = {"level": 12, "max": 100, "muted": False}

    async def async_generate_cert_if_missing(self):
        for path, text in ((self.certfile, "CERT-PEM-SECRET"), (self.keyfile, "PRIVATE-KEY-SECRET")):
            with open(path, "w") as out:
                out.write(text)
        return True

    async def async_start_pairing(self):
        if self.host in self.tv["down"]:
            raise CannotConnect()
        self.tv["pairings"] += 1

    async def async_finish_pairing(self, code):
        if code != CODE:
            raise InvalidAuth()
        self.tv["paired"].add(self.host)

    async def async_connect(self):
        if self.host in self.tv["down"]:
            raise CannotConnect()
        if self.host not in self.tv["paired"]:
            raise InvalidAuth()

    def send_key_command(self, key):
        self.tv["keys"].append((self.host, key))

    def add_is_available_updated_callback(self, callback):
        pass

    def keep_reconnecting(self, callback=None):
        pass

    def disconnect(self):
        pass


@pytest.fixture
def house(setup, monkeypatch, tmp_path):
    db, (admin, _) = setup
    library = types.ModuleType("androidtvremote2")
    library.AndroidTVRemote, library.InvalidAuth, library.CannotConnect = (
        FakeRemote,
        InvalidAuth,
        CannotConnect,
    )
    monkeypatch.setitem(sys.modules, "androidtvremote2", library)
    monkeypatch.setattr(tv_remote.settings, "runtime_root", tmp_path)
    FakeRemote.tv = {"paired": set(), "down": set(), "keys": [], "pairings": 0}
    from houseos import home

    monkeypatch.setattr(home, "registry", lambda base, token: None)  # no Home Assistant registry
    monkeypatch.setattr(home, "_cache", {**home._cache, "entities": {}, "entities_at": 0})
    for cache in (tv_remote.REMOTES, tv_remote.UP, tv_remote.PAIRING, tv_remote.PROBES):
        cache.clear()
    # A Google TV answers on 6466; the older Chromecast and the DLNA TV do not.
    remote_port = {"192.0.2.19"}
    monkeypatch.setattr(
        tv_remote, "port_open", lambda address, port, timeout=0.8: port == 8009 or address in remote_port
    )
    monkeypatch.setattr(
        tv_remote,
        "cast_state",
        lambda address: {"app": "Backdrop", "volume": 30, "muted": False, "title": None},
    )
    cast_calls = []
    monkeypatch.setattr(cinema_cast, "cast_control", lambda *args: cast_calls.append(args))
    devices = {}
    for name, adapter, address in (
        ("Living room TV", "cast", "192.0.2.19"),
        ("Bedroom Chromecast", "cast", "192.0.2.21"),
        ("Kitchen TV", "dlna", "192.168.1.50"),
    ):
        devices[name] = CinemaDevice(name=name, adapter=adapter, address=address, capabilities={})
        db.add(devices[name])
    db.add(
        CinemaDevice(name="Nest Mini", adapter="cast", address="192.0.2.22", capabilities={"kind": "audio"})
    )
    db.commit()
    return db, admin, devices, cast_calls


def map_home_assistant(db, admin, device, monkeypatch, state="on"):
    integrations.save_integration(
        "home_assistant",
        integrations.IntegrationInput(
            enabled=True,
            config={
                "base_url": "http://192.0.2.18:8123",
                "device_id": "media_player.living_room_tv",
                "receiver_id": device.id,
            },
            secret="ha-token",
        ),
        admin,
        db,
    )
    calls = []

    def fake(base, path, *, headers=None, method="GET", payload=None, timeout=15, **kw):
        assert headers["Authorization"] == "Bearer ha-token"
        if method == "POST":
            calls.append((path, payload))
            return []
        return {
            "state": state,
            "attributes": {
                "friendly_name": "Hisense",
                "source": "HDMI 1",
                "source_list": ["HDMI 1", "HDMI 2"],
            },
        }

    monkeypatch.setattr(cinema_tv, "private_json", fake)
    return calls


def by_name(items):
    return {item["name"]: item for item in items}


def test_capabilities_cast_only_dlna_and_speakers_left_out(house):
    db, *_ = house
    items = by_name(tv_remote.describe(db, tv_remote.tvs(db)))
    assert set(items) == {"Living room TV", "Bedroom Chromecast", "Kitchen TV"}  # no speaker
    living, bedroom, kitchen = items["Living room TV"], items["Bedroom Chromecast"], items["Kitchen TV"]
    assert living["capabilities"] == {
        "dpad": False,
        "volume": True,
        "volume_level": True,
        "mute": True,
        "playback": True,
        "power": False,
        "input": False,
        "remote_pairable": True,
        "paired": False,
    }
    assert bedroom["capabilities"]["remote_pairable"] is False and bedroom["capabilities"]["dpad"] is False
    assert living["state"]["reachable"] is True and living["state"]["volume"] == 30
    # DLNA: volume and mute only.
    assert {k for k, v in kitchen["capabilities"].items() if v} == {"volume", "volume_level", "mute"}


def test_pairing_then_dpad_and_remote_state(house):
    db, admin, devices, _ = house
    living = devices["Living room TV"]
    assert tv_remote.pair(living.id, admin, db)["message"] == "Look at your TV: type the code it shows."
    with pytest.raises(HTTPException) as wrong:
        tv_remote.pair_finish(living.id, tv_remote.PairCode(code="FFFFFF"), admin, db)
    assert wrong.value.detail["code"] == "TV_PAIRING_CODE"
    with pytest.raises(HTTPException) as expired:  # a wrong code ends that attempt
        tv_remote.pair_finish(living.id, tv_remote.PairCode(code=CODE), admin, db)
    assert expired.value.detail["code"] == "TV_PAIRING_EXPIRED"
    tv_remote.pair(living.id, admin, db)
    assert tv_remote.pair_finish(living.id, tv_remote.PairCode(code=CODE.lower()), admin, db) == {
        "status": "paired"
    }
    assert FakeRemote.tv["pairings"] == 2
    folder = tv_remote.settings.runtime_root / "run" / "tv-remote"
    assert (folder.stat().st_mode & 0o777) == 0o700
    assert (folder / "client.key").stat().st_mode & 0o777 == 0o600
    item = by_name(tv_remote.list_tvs(admin, db)["items"])["Living room TV"]
    assert item["capabilities"]["dpad"] and item["capabilities"]["power"]
    assert item["state"]["volume"] == 12 and item["state"]["app"] == "com.google.android.youtube.tv"
    for key in ("DPAD_UP", "DPAD_CENTER", "BACK", "VOLUME_UP"):
        assert tv_remote.press_key(living.id, tv_remote.Press(key=key), admin, db)["via"] == "remote"
    assert FakeRemote.tv["keys"] == [
        ("192.0.2.19", k) for k in ("DPAD_UP", "DPAD_CENTER", "BACK", "VOLUME_UP")
    ]
    # Unreachable TV: a sentence, not a stack trace.
    tv_remote.forget(living.id)
    FakeRemote.tv["down"].add("192.0.2.19")
    with pytest.raises(HTTPException) as down:
        tv_remote.press_key(living.id, tv_remote.Press(key="HOME"), admin, db)
    assert down.value.detail["code"] == "TV_UNREACHABLE" and "Wi-Fi" in down.value.detail["message"]


def test_forgotten_pairing_is_noticed(house):
    db, admin, devices, _ = house
    living = devices["Living room TV"]
    tv_remote.set_paired(living.id, True)  # HouseOS thinks so; the TV has forgotten it
    with pytest.raises(HTTPException) as gone:
        tv_remote.press_key(living.id, tv_remote.Press(key="DPAD_LEFT"), admin, db)
    assert gone.value.detail["code"] == "TV_REMOTE_NOT_PAIRED"
    assert living.id not in tv_remote.paired_ids()


def test_key_allowlist_and_unsupported_keys(house):
    db, admin, devices, cast_calls = house
    for bad in ("KEYCODE_SETTINGS", "text:hello", "SETTINGS", "dpad_up"):
        with pytest.raises(ValidationError):
            tv_remote.Press(key=bad)
    with pytest.raises(ValidationError):
        tv_remote.PairCode(code="12345z")
    bedroom, kitchen = devices["Bedroom Chromecast"], devices["Kitchen TV"]
    # Unpaired Cast: arrows ask for pairing, volume and play/pause go over Cast.
    with pytest.raises(HTTPException) as dpad:
        tv_remote.press_key(bedroom.id, tv_remote.Press(key="DPAD_UP"), admin, db)
    assert dpad.value.detail["code"] == "TV_REMOTE_NOT_PAIRED"
    for key in ("VOLUME_DOWN", "VOLUME_MUTE", "MEDIA_PLAY_PAUSE"):
        assert tv_remote.press_key(bedroom.id, tv_remote.Press(key=key), admin, db)["via"] == "cast"
    assert cast_calls == [
        ("192.0.2.21", "volume_step", -5),
        ("192.0.2.21", "mute", 5),
        ("192.0.2.21", "toggle", 5),
    ]
    for key in ("POWER", "INPUT", "MEDIA_PLAY_PAUSE", "HOME"):
        with pytest.raises(HTTPException) as no:
            tv_remote.press_key(kitchen.id, tv_remote.Press(key=key), admin, db)
        assert no.value.detail["code"] == "TV_KEY_UNSUPPORTED"
    assert FakeRemote.tv["keys"] == []


def test_home_assistant_mapping_gives_power_and_inputs(house, monkeypatch):
    db, admin, devices, _ = house
    bedroom = devices["Bedroom Chromecast"]
    calls = map_home_assistant(db, admin, bedroom, monkeypatch)
    items = tv_remote.list_tvs(admin, db)["items"]
    # Two remotes for that screen: the TV itself (Home Assistant) and the Chromecast alone.
    item = by_name(items)["Hisense"]
    assert item["target"] == "tv" and item["via"] == "Bedroom Chromecast"
    assert item["capabilities"]["power"] and item["capabilities"]["input"]
    assert item["inputs"] == ["HDMI 1", "HDMI 2"] and item["state"]["on"] is True
    cast = by_name(items)["Bedroom Chromecast"]
    assert cast["target"] == "device" and not cast["capabilities"]["power"] and not cast["inputs"]
    tv = lambda **kw: tv_remote.Press(target="tv", **kw)  # noqa: E731
    tv_remote.press_key(bedroom.id, tv(key="INPUT", input="HDMI 2"), admin, db)
    tv_remote.press_key(bedroom.id, tv(key="POWER"), admin, db)
    assert calls == [
        (
            "/api/services/media_player/select_source",
            {"entity_id": "media_player.living_room_tv", "source": "HDMI 2"},
        ),
        ("/api/services/media_player/turn_off", {"entity_id": "media_player.living_room_tv"}),
    ]
    with pytest.raises(HTTPException) as unknown:
        tv_remote.press_key(bedroom.id, tv(key="INPUT", input="Netflix"), admin, db)
    assert unknown.value.detail["code"] == "TV_INPUT_UNKNOWN"
    with pytest.raises(HTTPException) as chromecast:  # the Chromecast alone has no inputs
        tv_remote.press_key(bedroom.id, tv_remote.Press(key="INPUT", input="HDMI 2"), admin, db)
    assert chromecast.value.detail["code"] == "TV_KEY_UNSUPPORTED"
    # Only the mapped device gets power.
    assert not by_name(tv_remote.list_tvs(admin, db)["items"])["Living room TV"]["capabilities"]["power"]


def test_no_secret_reaches_the_browser(house, monkeypatch):
    db, admin, devices, _ = house
    map_home_assistant(db, admin, devices["Living room TV"], monkeypatch)
    tv_remote.pair(devices["Living room TV"].id, admin, db)
    tv_remote.pair_finish(devices["Living room TV"].id, tv_remote.PairCode(code=CODE), admin, db)
    text = json.dumps(tv_remote.list_tvs(admin, db), default=str)
    for secret in ("ha-token", "PRIVATE-KEY-SECRET", "CERT-PEM-SECRET", "client.key", "tv-remote"):
        assert secret not in text


def test_permissions(house):
    db, _, devices, _ = house
    guest = Actor("guest-1", "Gus", "guest", {"music.read", "music.queue"})
    for call in (
        lambda: tv_remote.list_tvs(guest, db),
        lambda: tv_remote.press_key(devices["Living room TV"].id, tv_remote.Press(key="HOME"), guest, db),
        lambda: tv_remote.pair(devices["Living room TV"].id, guest, db),
    ):
        with pytest.raises(HTTPException) as denied:
            call()
        assert denied.value.status_code == 403
    only_home = Actor("r", "Rita", "resident", {"home.control"})
    assert tv_remote.list_tvs(only_home, db)["items"]


def test_nox_tool(house, monkeypatch):
    from houseos import assistant, assistant_tools

    db, admin, devices, cast_calls = house
    resident = Actor("resident-1", "Rita", "resident", RESIDENT)
    for bundle in ("general", "home", "tv"):
        assert "tv_remote" in assistant_tools.tool_registry(bundle)
    tv_remote.set_paired(devices["Living room TV"].id, True)
    FakeRemote.tv["paired"].add("192.0.2.19")
    press = lambda **kw: tool_tv.tv_remote_press(tool_tv.TvRemote(**kw), resident, db)  # noqa: E731
    # No name: the one remote with arrows; several with volume, so Nox asks.
    assert press(key="DPAD_CENTER")["tv"] == "Living room TV"
    assert press(key="VOLUME_UP")["status"] == "needs_clarification"
    assert press(key="DPAD_CENTER", tv="living room tv")["tv"] == "Living room TV"
    assert press(key="BACK", tv="the living room")["via"] == "remote"
    assert press(key="VOLUME_UP", tv="living room", times=3)["times"] == 3
    assert FakeRemote.tv["keys"][-3:] == [("192.0.2.19", "VOLUME_UP")] * 3
    assert press(key="VOLUME_UP", tv="bedroom")["via"] == "cast" and cast_calls
    assert press(key="HOME", tv="garage")["status"] == "needs_clarification"
    with pytest.raises(ValidationError):
        tool_tv.TvRemote(key="KEYCODE_SETTINGS")
    # Turning the mapped TV off goes through Home Assistant.
    calls = map_home_assistant(db, admin, devices["Living room TV"], monkeypatch)
    card = press(key="POWER")  # like tv_control, power waits for the resident's tap
    assert card["status"] == "needs_confirmation" and card["preview"]["destination"] == "Hisense"
    assert card["preview"]["action"] == "power_off" and not calls
    assert assistant.confirm_message(card["confirmation_id"], resident, db)["via"] == "home_assistant"
    assert calls[-1][0].endswith("/turn_off")  # the TV itself, by default
    with pytest.raises(HTTPException):  # one tap, one press
        assistant.confirm_message(card["confirmation_id"], resident, db)


def test_home_assistant_remote_buttons_give_arrows_before_pairing(house, monkeypatch):
    db, admin, devices, _ = house
    bedroom = devices["Bedroom Chromecast"]
    calls = map_home_assistant(db, admin, bedroom, monkeypatch)
    observed = cinema_tv.private_json

    def with_buttons(base, path, **kw):
        if path == "/api/states":
            names = ("up", "down", "left", "right", "ok", "back", "home", "power")
            return [{"entity_id": "button.living_room_tv_" + n, "state": "unknown"} for n in names] + [
                {"entity_id": "button.other_up", "state": "unknown"}
            ]
        return observed(base, path, **kw)

    monkeypatch.setattr(cinema_tv, "private_json", with_buttons)
    items = by_name(tv_remote.list_tvs(admin, db)["items"])
    assert items["Hisense"]["capabilities"]["dpad"]  # the TV's own arrows
    assert not items["Bedroom Chromecast"]["capabilities"]["dpad"]  # the Chromecast's need pairing
    tv_remote.press_key(bedroom.id, tv_remote.Press(key="DPAD_CENTER", target="tv"), admin, db)
    assert calls == [("/api/services/button/press", {"entity_id": "button.living_room_tv_ok"})]


def test_an_lg_tv_gets_arrows_through_its_home_assistant_integration(house, monkeypatch):
    from houseos import home

    db, admin, devices, _ = house
    bedroom = devices["Bedroom Chromecast"]
    calls = map_home_assistant(db, admin, bedroom, monkeypatch)
    monkeypatch.setattr(
        home,
        "registry",
        lambda base, token: {"media_player.living_room_tv": {"platform": "webostv", "device": "lg"}},
    )
    items = by_name(tv_remote.list_tvs(admin, db)["items"])
    assert items["Hisense"]["capabilities"]["dpad"]
    tv_remote.press_key(bedroom.id, tv_remote.Press(key="BACK", target="tv"), admin, db)
    assert calls[-1] == (
        "/api/services/webostv/button",
        {"entity_id": "media_player.living_room_tv", "button": "BACK"},
    )


def test_tv_volume_and_mute_through_home_assistant(house, monkeypatch):
    db, admin, devices, cast_calls = house
    bedroom = devices["Bedroom Chromecast"]
    calls = map_home_assistant(db, admin, bedroom, monkeypatch)
    observed = cinema_tv.private_json

    def with_volume(base, path, **kw):
        answer = observed(base, path, **kw)
        if isinstance(answer, dict) and "attributes" in answer:
            answer["attributes"].update(supported_features=1024 | 8, volume_level=0.2, is_volume_muted=False)
        return answer

    monkeypatch.setattr(cinema_tv, "private_json", with_volume)
    tv = by_name(tv_remote.list_tvs(admin, db)["items"])["Hisense"]
    assert tv["capabilities"]["volume"] and tv["capabilities"]["mute"] and tv["state"]["volume"] == 20
    for key in ("VOLUME_UP", "VOLUME_MUTE"):
        tv_remote.press_key(bedroom.id, tv_remote.Press(key=key, target="tv"), admin, db)
    assert calls == [
        ("/api/services/media_player/volume_up", {"entity_id": "media_player.living_room_tv"}),
        (
            "/api/services/media_player/volume_mute",
            {"entity_id": "media_player.living_room_tv", "is_volume_muted": True},
        ),
    ]
    assert not cast_calls  # the Chromecast's own volume was left alone


def test_the_volume_slider_sets_an_exact_level_and_only_where_it_is_heard(house, monkeypatch):
    db, admin, devices, cast_calls = house
    bedroom = devices["Bedroom Chromecast"]
    calls = map_home_assistant(db, admin, bedroom, monkeypatch)
    observed = cinema_tv.private_json
    output = {"sound_output": "tv_speaker"}

    def with_volume(base, path, **kw):
        answer = observed(base, path, **kw)
        if isinstance(answer, dict) and "attributes" in answer:
            answer["attributes"].update(supported_features=4 | 1024 | 8, volume_level=0.2, **output)
        return answer

    monkeypatch.setattr(cinema_tv, "private_json", with_volume)
    items = by_name(tv_remote.list_tvs(admin, db)["items"])
    assert items["Hisense"]["capabilities"]["volume_level"]
    assert items["Bedroom Chromecast"]["capabilities"]["volume_level"]  # Cast: exact too
    tv_remote.press_key(bedroom.id, tv_remote.Press(key="VOLUME_SET", level=35, target="tv"), admin, db)
    assert calls[-1] == (
        "/api/services/media_player/volume_set",
        {"entity_id": "media_player.living_room_tv", "volume_level": 0.35},
    )
    tv_remote.press_key(bedroom.id, tv_remote.Press(key="VOLUME_SET", level=12), admin, db)
    assert cast_calls[-1] == ("192.0.2.21", "volume", 12)
    with pytest.raises(ValidationError):
        tv_remote.Press(key="VOLUME_SET", level=140)
    # Sound on a soundbar: the TV's own level changes nothing heard, so steps only.
    output["sound_output"] = "external_arc"
    items = by_name(tv_remote.list_tvs(admin, db)["items"])
    assert not items["Hisense"]["capabilities"]["volume_level"] and items["Hisense"]["capabilities"]["volume"]


def test_a_film_turns_the_tv_on_and_goes_to_the_chromecast_input(house, monkeypatch):
    db, admin, devices, _ = house
    bedroom = devices["Bedroom Chromecast"]
    calls = map_home_assistant(db, admin, bedroom, monkeypatch, state="off")
    clock = [0.0]  # the TV never comes up here: 8 s of fake waiting, then on anyway

    def sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr(tv_remote.time, "sleep", sleep)
    monkeypatch.setattr(tv_remote.time, "monotonic", lambda: clock[0])
    # Nothing chosen and no input named after the Chromecast: the TV is only turned on.
    assert tv_remote.wake_for_film(db, bedroom) == ["turned on"]
    assert calls[-1][0] == "/api/services/media_player/turn_on"
    calls.clear()
    tv_remote.set_film_input(bedroom.id, tv_remote.FilmInput(input="HDMI 2"), admin, db)
    tv = by_name(tv_remote.list_tvs(admin, db)["items"])["Hisense"]
    assert tv["film_input"] == tv["film_input_now"] == "HDMI 2"
    assert tv_remote.wake_for_film(db, bedroom) == ["turned on", "switched to HDMI 2"]
    assert calls[-1] == (
        "/api/services/media_player/select_source",
        {"entity_id": "media_player.living_room_tv", "source": "HDMI 2"},
    )
    tv_remote.set_film_input(bedroom.id, tv_remote.FilmInput(input=""), admin, db)  # never switch
    assert tv_remote.film_input(bedroom, {"inputs": ["HDMI 1", "Chromecast"]}) is None
    bedroom.capabilities = {}
    assert tv_remote.film_input(bedroom, {"inputs": ["HDMI 1", "Chromecast"]}) == "Chromecast"
