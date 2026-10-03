"""HouseOS on the Wi-Fi: what a scan understands from SSDP, DLNA descriptions, mDNS and
Jellyfin replies. No packet leaves the machine: sockets, zeroconf and pychromecast are mocked."""

from types import SimpleNamespace

import pytest

from houseos import discovery, dlna, voice

SONOS = "192.0.2.40"
ANSWER = (
    "HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age = 1800\r\nEXT:\r\n"
    f"LOCATION: http://{SONOS}:1400/xml/device_description.xml\r\n"
    "SERVER: Linux UPnP/1.0 Sonos/85.0\r\n"
    "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
    "USN: uuid:RINCON_1::urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n"
).encode()
# Sonos: the renderer is an embedded device; control URLs are relative to the description.
DESCRIPTION = b"""<?xml version="1.0" encoding="utf-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <deviceType>urn:schemas-upnp-org:device:ZonePlayer:1</deviceType>
    <friendlyName>Living Room</friendlyName>
    <manufacturer>Sonos, Inc.</manufacturer>
    <modelName>Sonos One</modelName>
    <deviceList><device>
      <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
      <friendlyName>Living Room - Media Renderer</friendlyName>
      <serviceList>
        <service>
          <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
          <controlURL>/MediaRenderer/RenderingControl/Control</controlURL>
        </service>
        <service>
          <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
          <controlURL>/MediaRenderer/AVTransport/Control</controlURL>
        </service>
        <service>
          <serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
          <controlURL>http://8.8.8.8/elsewhere</controlURL>
        </service>
      </serviceList>
    </device></deviceList>
  </device>
</root>"""


# ---------- SSDP and DLNA descriptions ----------
def test_ssdp_answers_are_renderers_that_point_back_at_themselves():
    location = f"http://{SONOS}:1400/xml/device_description.xml"
    assert dlna.ssdp_location(ANSWER, SONOS) == location
    assert dlna.ssdp_location(ANSWER, "192.0.2.41") is None  # description on another host
    assert dlna.ssdp_location(ANSWER.replace(b"MediaRenderer", b"MediaServer"), SONOS) is None
    assert dlna.ssdp_location(ANSWER.replace(b"200 OK", b"404 Not Found"), SONOS) is None
    public = ANSWER.replace(SONOS.encode(), b"8.8.8.8")
    assert dlna.ssdp_location(public, "8.8.8.8") is None  # never outside the LAN


def test_a_description_gives_the_name_and_its_own_control_urls():
    info = dlna.description(DESCRIPTION, f"http://{SONOS}:1400/xml/device_description.xml", SONOS)
    assert info == {
        "name": "Living Room",
        "maker": "Sonos, Inc.",
        "model": "Sonos One",
        "av": f"http://{SONOS}:1400/MediaRenderer/AVTransport/Control",
        "rc": f"http://{SONOS}:1400/MediaRenderer/RenderingControl/Control",
    }
    # A control URL on another host is ignored, not followed.
    elsewhere = DESCRIPTION.replace(b"/MediaRenderer/AVTransport", b"http://192.0.2.99/AVTransport")
    assert dlna.description(elsewhere, f"http://{SONOS}:1400/d.xml", SONOS)["av"] is None


def test_hostile_xml_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><root>&a;</root>'
    for data in (bomb, b"<root>" + b" " * dlna.MAX_XML + b"</root>"):
        with pytest.raises(ValueError):
            dlna.xml(data)


def test_renderers_are_scan_items(monkeypatch):
    location = f"http://{SONOS}:1400/xml/device_description.xml"
    monkeypatch.setattr(dlna, "search", lambda timeout, targets, kinds=dlna.RENDERER: {SONOS: location})
    monkeypatch.setattr(
        dlna, "describe", lambda where, address: dlna.description(DESCRIPTION, where, address)
    )
    assert dlna.renderers() == [
        {
            "kind": "dlna",
            "name": "Living Room",
            "address": SONOS,
            "maker": "Sonos, Inc.",
            "model": "Sonos One",
            "playable": True,
            "description_url": location,
        }
    ]


def test_a_saved_description_url_is_used_only_on_its_own_device():
    saved = {"description_url": f"http://{SONOS}:1400/xml/device_description.xml"}
    assert dlna.target(SimpleNamespace(address=SONOS, capabilities=saved)) == saved["description_url"]
    assert dlna.target(SimpleNamespace(address="192.0.2.41", capabilities=saved)) == "192.0.2.41"


def test_clock_values():
    assert dlna.clock(3725.6) == "1:02:05" and dlna.clock(-3) == "0:00:00"
    assert dlna.seconds("0:01:30.500") == 90.5 and dlna.seconds("NOT_IMPLEMENTED") is None


# ---------- mDNS, Cast and Jellyfin ----------
def record(name, addresses, port=0, properties=None):
    return SimpleNamespace(
        name=name, port=port, properties=properties or {}, parsed_addresses=lambda: addresses
    )


def test_mdns_records_become_honest_scan_items():
    airplay = record(
        "A8B1C2D3E4F5@Kitchen HomePod._raop._tcp.local.",
        ["192.0.2.50"],
        7000,
        {b"am": b"AudioAccessory5,1"},
    )
    assert discovery.mdns_item("airplay", airplay) == {
        "kind": "airplay",
        "name": "Kitchen HomePod",
        "address": "192.0.2.50",
        "model": "AudioAccessory5,1",
        "maker": "",
        "playable": False,
    }
    ha = record(
        "Home._home-assistant._tcp.local.",
        ["192.0.2.10"],
        8123,
        {
            b"location_name": b"Our Home",
            b"base_url": b"",
            b"internal_url": b"http://homeassistant.local:8123",
        },
    )
    assert discovery.mdns_item("home_assistant", ha) == {
        "kind": "home_assistant",
        "name": "Our Home",
        "address": "192.0.2.10",
        "url": "http://homeassistant.local:8123",
        "model": "",
        "maker": "",
        "playable": False,
    }
    bare = record("Home._home-assistant._tcp.local.", ["192.0.2.10"], 8123, {b"base_url": b"javascript:x"})
    assert discovery.mdns_item("home_assistant", bare)["url"] == "http://192.0.2.10:8123"
    assert discovery.mdns_item("airplay", record("Nowhere._airplay._tcp.local.", [])) is None


def test_cast_receivers_keep_their_kinds(monkeypatch):
    from pychromecast import discovery as cast_discovery

    info = SimpleNamespace(
        friendly_name="Living room TV", model_name="Chromecast with Google TV", manufacturer="Google"
    )
    found = [
        SimpleNamespace(**vars(info), host="192.0.2.30", cast_type="cast"),
        SimpleNamespace(
            friendly_name="Everywhere", model_name="", manufacturer="", host="192.0.2.31", cast_type="group"
        ),
        SimpleNamespace(friendly_name="", model_name="", manufacturer="", host=None, cast_type="audio"),
    ]
    monkeypatch.setattr(cast_discovery, "discover_chromecasts", lambda **kw: (found, None))
    monkeypatch.setattr(cast_discovery, "stop_discovery", lambda browser: None)
    items = discovery.cast_devices(None, 1)
    assert [(i["kind"], i["name"], i["playable"]) for i in items] == [
        ("tv", "Living room TV", True),
        ("group", "Everywhere", True),
    ]


def test_jellyfin_replies():
    reply = b'{"Address":"http://192.0.2.20:8096","Id":"abc","Name":"Attic","EndpointAddress":null}'
    assert discovery.jellyfin_reply(reply, "192.0.2.20") == {
        "kind": "jellyfin",
        "name": "Attic",
        "address": "192.0.2.20",
        "url": "http://192.0.2.20:8096",
        "model": "",
        "maker": "",
    }
    for bad in (b"not json", b"[]", b'{"Address":"file:///etc/passwd"}'):
        assert discovery.jellyfin_reply(bad, "192.0.2.20") is None


def test_one_device_appears_once_as_what_plays_best_and_services_stay():
    tv = {"kind": "tv", "name": "TV", "address": "192.0.2.30"}
    group = {"kind": "group", "name": "All", "address": "192.0.2.30"}  # hosted by the TV
    same_tv = [
        {"kind": "dlna", "name": "TV", "address": "192.0.2.30"},
        {"kind": "airplay", "name": "TV", "address": "192.0.2.30"},
    ]
    sonos = {"kind": "airplay", "name": "Sonos", "address": SONOS}
    sonos_dlna = {"kind": "dlna", "name": "Sonos", "address": SONOS}
    ha = {"kind": "home_assistant", "name": "Home", "address": "192.0.2.30"}
    kept = discovery.best_per_address([tv, group, *same_tv, sonos, sonos_dlna, ha])
    assert kept == [group, ha, sonos_dlna, tv]


def test_a_failing_source_leaves_the_others(monkeypatch):
    import zeroconf

    class Quiet:
        def __init__(self, **kwargs):
            pass

        def close(self):
            pass

    def broken(*args):
        raise OSError("no multicast here")

    monkeypatch.setattr(zeroconf, "Zeroconf", Quiet)
    monkeypatch.setattr(discovery, "cast_devices", broken)
    monkeypatch.setattr(discovery, "mdns_services", lambda zc, timeout: [])
    monkeypatch.setattr(dlna, "renderers", lambda timeout: [{"kind": "dlna", "name": "TV", "address": SONOS}])
    monkeypatch.setattr(discovery, "jellyfin_servers", broken)
    monkeypatch.setattr(dlna, "screens", broken)
    assert discovery.scan() == [{"kind": "dlna", "name": "TV", "address": SONOS, "brand": None}]


def test_brand_tvs_are_found_by_their_own_protocol_and_named(monkeypatch):
    lg = "192.0.2.50"
    answer = (
        b"HTTP/1.1 200 OK\r\nST: urn:lge-com:service:webos-second-screen:1\r\n"
        b"LOCATION: http://192.0.2.50:1754/\r\n\r\n"
    )
    assert dlna.ssdp_location(answer, lg, dlna.SCREENS) == "http://192.0.2.50:1754/"
    assert dlna.ssdp_location(answer, lg) is None  # not a DLNA renderer
    item = {"kind": "screen", "name": "OLED TV", "address": lg, "maker": "LG Electronics", "model": ""}
    assert discovery.brand(item) == "lg"
    assert discovery.brand({"name": "Salon", "maker": "Sonos, Inc."}) == "sonos"
    assert discovery.brand({"name": "Kitchen", "maker": "Unknown"}) is None
    # The same TV found as a DLNA renderer too: it shows once, as what HouseOS plays on.
    dlna_tv = {**item, "kind": "dlna", "playable": True}
    assert discovery.best_per_address([item, dlna_tv]) == [dlna_tv]


# ---------- HouseOS on the Wi-Fi ----------
def test_the_announcement_names_the_https_door(monkeypatch):
    class Door:
        def close(self):
            pass

    monkeypatch.setattr(discovery.socket, "create_connection", lambda *args, **kwargs: Door())
    assert discovery.door("192.0.2.5") == (8443, "https://houseos.local:8443")
    infos = discovery.announcements("192.0.2.5", 8443, "https://houseos.local:8443")
    assert {info.type for info in infos} == {"_https._tcp.local.", "_houseos._tcp.local."}
    assert all(info.server == "houseos.local." and info.parsed_addresses() == ["192.0.2.5"] for info in infos)

    def closed(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(discovery.socket, "create_connection", closed)
    assert discovery.door("192.0.2.5") == (None, None)
    monkeypatch.setattr(discovery.settings, "lan_url", "https://house.lan:9443/")
    assert discovery.door("192.0.2.5") == (9443, "https://house.lan:9443")


# ---------- voice on small computers ----------
def test_voice_uses_the_base_model_on_arm_and_small_memory(monkeypatch):
    monkeypatch.delenv("HOUSEOS_VOICE_MODEL", raising=False)
    monkeypatch.setattr(voice.os, "sysconf", lambda name: 4096 if name == "SC_PAGE_SIZE" else 4 * 1024**2)
    monkeypatch.setattr(voice.os, "uname", lambda: SimpleNamespace(machine="x86_64"))
    assert voice.cpu_model() == "small"  # 16 GB
    monkeypatch.setattr(voice.os, "uname", lambda: SimpleNamespace(machine="aarch64"))
    assert voice.cpu_model() == "base"
    monkeypatch.setenv("HOUSEOS_VOICE_MODEL", "tiny")
    assert voice.cpu_model() == "tiny"


def test_neighbours_are_the_home_network_only(monkeypatch):
    tables = {
        "/proc/net/route": [["wlan0", "00000000"], ["docker0", "000011AC"]],
        "/proc/net/arp": [
            ["192.0.2.40", "0x1", "0x2", "aa", "*", "wlan0"],
            ["192.0.2.41", "0x1", "0x0", "00", "*", "wlan0"],  # incomplete: gone
            ["172.17.0.2", "0x1", "0x2", "bb", "*", "docker0"],
        ],
    }
    monkeypatch.setattr(dlna, "table", tables.get)
    assert dlna.neighbours() == ["192.0.2.40"]


def test_lan_suggest_reads_the_card_subnet_router_and_a_free_address(monkeypatch):
    from houseos import music_outputs

    routes = [  # /proc/net/route: little-endian hex; the router is 192.0.2.254
        ["wlan0", "00000000", "FE0200C0", "0003", "0", "0", "600", "00000000"],
        ["wlan0", "000200C0", "00000000", "0001", "0", "0", "600", "00FFFFFF"],
        ["docker0", "000011AC", "00000000", "0001", "0", "0", "0", "0000FFFF"],
    ]
    monkeypatch.setattr(dlna, "table", lambda path: routes)
    monkeypatch.setattr(dlna, "neighbours", lambda: ["192.0.2.253"])
    monkeypatch.setattr(music_outputs, "lan_address", lambda: "192.0.2.20")
    assert discovery.lan_settings() == {
        "HOUSEOS_LAN_PARENT": "wlan0",
        "HOUSEOS_LAN_SUBNET": "192.0.2.0/24",
        "HOUSEOS_LAN_GATEWAY": "192.0.2.254",
        "HOUSEOS_LAN_IP": "192.0.2.252",  # .254 is the router, .253 answers
    }


def test_find_devices_add_is_accepted_as_the_ui_sends_it():
    """Control Room's Add sends the scan item's kind (and a group's port, a renderer's
    description): the device check must accept exactly that, and refuse anything else."""
    from pydantic import ValidationError
    from houseos.cinema_models import DeviceInput

    for capabilities in (
        {"kind": "tv"},
        {"kind": "group", "port": 32187},
        {"kind": "dlna", "description_url": f"http://{SONOS}:1400/xml/device_description.xml"},
        {"kind": "tv", "tv_input": "HDMI 2", "inspected_at": "2026-09-25T20:00:00", "confidence": "x"},
    ):
        DeviceInput(name="Living room", adapter="cast", address="192.0.2.30", capabilities=capabilities)
    for capabilities in ({"kind": "toaster"}, {"kind": "group", "port": 0}, {"kind": "tv", "shell": "x"}):
        with pytest.raises(ValidationError):
            DeviceInput(name="Living room", adapter="cast", address="192.0.2.30", capabilities=capabilities)


def test_a_cast_group_is_reached_on_its_own_port(monkeypatch):
    import pychromecast
    from houseos import cinema_cast

    seen = []

    class Cast:
        def wait(self, timeout):
            pass

    monkeypatch.setattr(
        pychromecast, "get_chromecast_from_host", lambda host, **kw: seen.append(host[:2]) or Cast()
    )
    cinema_cast.connect("192.0.2.30:32187")
    cinema_cast.connect("192.0.2.30")
    assert seen == [("192.0.2.30", 32187), ("192.0.2.30", 8009)]


def test_a_device_can_be_forgotten_and_music_goes_back_to_the_computer(setup):
    from fastapi import HTTPException
    from houseos import cinema
    from houseos.cinema_models import CinemaDevice
    from houseos.music_outputs import output_choice, save_output_choice

    db, (admin, _) = setup
    db.add(CinemaDevice(id="old-tv", name="Old TV", adapter="cast", address="192.0.2.30"))
    save_output_choice(db, device_id="old-tv", problem="TARGET_OFFLINE")
    db.commit()
    assert cinema.delete_device("old-tv", admin, db)["status"] == "deleted"
    assert db.get(CinemaDevice, "old-tv") is None
    assert output_choice(db)["device_id"] is None and output_choice(db)["problem"] is None
    with pytest.raises(HTTPException):
        cinema.delete_device("old-tv", admin, db)
