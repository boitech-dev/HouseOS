"""HouseOS on the home network: it finds the TVs, speakers and services there, and announces
itself as houseos.local. Multicast only works on the home network itself, so the media relay
runs both: on the host network in Docker (or with the house's own address, compose.lan.yml),
as a native service otherwise. Scan requests and results travel through one database row."""

import ipaddress
import json
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends

from .auth import require_admin
from .config import settings
from .db import SessionLocal, get_db, utcnow
from .models import Integration

router = APIRouter(tags=["discovery"])
ROW = "device_discovery"
ANNOUNCED = "mdns_announcement"  # {"origin": "https://houseos.local:8443", "address": ...}
MDNS_KINDS = {
    "_airplay._tcp.local.": "airplay",
    "_raop._tcp.local.": "airplay",
    "_home-assistant._tcp.local.": "home_assistant",
}
# One device often speaks several languages: keep the one HouseOS plays best.
PREFERENCE = {"tv": 0, "audio": 0, "group": 0, "dlna": 1, "airplay": 2, "screen": 3}
# The maker, in words the admin knows, so Control Room can say how to control each one.
BRANDS = (
    ("lg", ("lg electronics", "webos")),
    ("samsung", ("samsung",)),
    ("sony", ("sony", "bravia")),
    ("roku", ("roku",)),
    ("philips", ("philips", "tp vision")),
    ("hisense", ("hisense", "vidaa")),
    ("panasonic", ("panasonic", "viera")),
    ("tcl", ("tcl",)),
    ("sonos", ("sonos",)),
    ("apple", ("apple",)),
    ("amazon", ("amazon", "fire tv")),
    ("heos", ("denon", "marantz", "heos")),
    ("yamaha", ("yamaha", "musiccast")),
    ("bose", ("bose",)),
    ("google", ("google", "chromecast", "nvidia", "shield")),
)


def brand(item):
    text = " ".join(str(item.get(k) or "") for k in ("maker", "model", "name")).casefold()
    return next((key for key, words in BRANDS if any(word in text for word in words)), None)


def cast_devices(zc, timeout):
    """Cast receivers: Chromecasts, Google TV and Android TV (Chromecast built-in), Nest and
    Cast-enabled speakers, speaker groups."""
    from pychromecast import discovery

    found, browser = discovery.discover_chromecasts(timeout=timeout, zeroconf_instance=zc)
    discovery.stop_discovery(browser)
    return [
        {
            "kind": "group" if info.cast_type == "group" else "audio" if info.cast_type == "audio" else "tv",
            "name": info.friendly_name or info.model_name or info.host,
            "address": info.host,
            **({"port": info.port} if getattr(info, "port", 8009) not in (None, 8009) else {}),
            "model": info.model_name or "",
            "maker": info.manufacturer or "",
            "playable": True,
        }
        for info in found
        if info.host
    ]


def web_url(value):
    """An http(s) address a service advertises, shown to the admin; never fetched."""
    value = (value or "").strip()
    parts = urlsplit(value)
    return value if parts.scheme in {"http", "https"} and parts.hostname and len(value) <= 200 else None


def mdns_item(kind, info):
    """A scan item for an AirPlay receiver or Home Assistant from its mDNS record."""
    addresses = info.parsed_addresses()
    if not addresses:
        return None
    text = {
        k.decode(errors="replace").lower(): (v or b"").decode(errors="replace")
        for k, v in (info.properties or {}).items()
    }
    name = info.name.split("._", 1)[0]
    item = {"kind": kind, "name": text.get("location_name") or name, "address": addresses[0]}
    if kind == "airplay":
        # AirPlay 2 needs Apple's pairing and encryption: listed honestly, not offered.
        item.update(name=name.split("@", 1)[-1], model=text.get("model") or text.get("am") or "")
        item["playable"] = False
    else:
        url = web_url(text.get("base_url")) or web_url(text.get("internal_url"))
        item.update(url=url or f"http://{addresses[0]}:{info.port}", playable=False)
    return {"model": "", "maker": "", **item}


def mdns_services(zc, timeout):
    from zeroconf import ServiceBrowser, ServiceInfo

    names = set()
    browser = ServiceBrowser(
        zc,
        list(MDNS_KINDS),
        handlers=[lambda zeroconf, service_type, name, state_change: names.add((service_type, name))],
    )
    time.sleep(timeout)
    browser.cancel()
    items = {}
    for service_type, name in sorted(names)[:64]:
        info = ServiceInfo(service_type, name)
        if info.load_from_cache(zc) or info.request(zc, 1500):
            item = mdns_item(MDNS_KINDS[service_type], info)
            if item:  # an AirPlay speaker announces itself twice (AirPlay and RAOP)
                items.setdefault((item["kind"], item["address"]), item)
    return list(items.values())


def jellyfin_reply(data, sender):
    """A Jellyfin server's answer to "who is JellyfinServer?"."""
    try:
        reply = json.loads(data.decode())
        url = web_url(reply.get("Address"))
    except (ValueError, AttributeError):
        return None
    if not url:
        return None
    name = str(reply.get("Name") or "Jellyfin")[:100]
    return {"kind": "jellyfin", "name": name, "address": sender, "url": url, "model": "", "maker": ""}


def jellyfin_servers(timeout):
    from .dlna import neighbours

    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for address in ["255.255.255.255", *neighbours()]:  # direct questions pass firewalls
            try:
                sock.sendto(b"who is JellyfinServer?", (address, 7359))
            except OSError:
                continue
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0 and len(found) < 16:
            sock.settimeout(left)
            try:
                data, (sender, _) = sock.recvfrom(2048)
            except OSError:
                break
            item = jellyfin_reply(data, sender)
            if item:
                found.setdefault(sender, {**item, "playable": False})
    return list(found.values())


def best_per_address(items):
    """Services are all kept; a speaker or TV appears only as the kind HouseOS plays best."""
    best = {}
    for item in items:
        rank = PREFERENCE.get(item["kind"], 9)
        best[item["address"]] = min(best.get(item["address"], 9), rank)
    return sorted(
        (item for item in items if PREFERENCE.get(item["kind"], -1) <= best[item["address"]]),
        key=lambda item: item["name"].casefold(),
    )


def scan(timeout=6):
    """Every source at once (about `timeout` seconds). One failing source leaves the others."""
    from zeroconf import IPVersion, Zeroconf

    from . import dlna

    zc = Zeroconf(ip_version=IPVersion.V4Only)
    try:
        with ThreadPoolExecutor(5) as pool:
            jobs = [
                pool.submit(dlna.screens, timeout - 3),
                pool.submit(cast_devices, zc, timeout),
                pool.submit(mdns_services, zc, timeout - 2),
                pool.submit(dlna.renderers, timeout - 3),
                pool.submit(jellyfin_servers, timeout - 3),
            ]
            items = []
            for job in jobs:
                try:
                    items += job.result()
                except Exception as exc:
                    print("device_discovery_source_failed", type(exc).__name__, flush=True)
    finally:
        zc.close()
    return [{**item, "brand": brand(item)} for item in best_per_address(items)]


def answer_request():
    """Run the scan Control Room asked for, once; nothing to do otherwise."""
    with SessionLocal() as db:
        row = db.get(Integration, ROW)
        config = dict(row.config or {}) if row else {}
    asked = config.get("requested_at")
    if not asked or config.get("scanned_for") == asked:
        return
    try:
        devices, problem = scan(), None
    except Exception as exc:
        devices, problem = [], type(exc).__name__
    with SessionLocal() as db:
        row = db.get(Integration, ROW)
        row.config = {
            **(row.config or {}),
            "scanned_for": asked,
            "scanned_at": utcnow().isoformat() + "Z",
            "devices": devices,
            "problem": problem,
        }
        db.commit()


def discovery_loop():
    """Relay thread: look for scan requests every 2 s."""
    while True:
        time.sleep(2)
        try:
            answer_request()
        except Exception as exc:  # database blip: try again at the next tick
            print("device_discovery_failed", type(exc).__name__, flush=True)


# ---------- HouseOS on the Wi-Fi ----------
def door(address):
    """(port, origin) phones should open: the built-in HTTPS door when it answers (its
    certificate is made for any name, houseos.local included), else the configured LAN URL."""
    name = settings.mdns_name + ".local"
    try:
        socket.create_connection((address, settings.https_port), timeout=1).close()
        return settings.https_port, f"https://{name}:{settings.https_port}"
    except OSError:
        parts = urlsplit(settings.lan_url)
        if parts.scheme == "https" and parts.hostname:
            return parts.port or 443, settings.lan_url.rstrip("/")
    return None, None


def announcements(address, port, origin):
    from zeroconf import ServiceInfo

    host = settings.mdns_name + ".local."
    return [
        ServiceInfo(
            kind,
            "HouseOS." + kind,
            addresses=[socket.inet_aton(address)],
            port=port,
            properties={"path": "/", "url": origin},
            server=host,  # zeroconf then answers for houseos.local itself, with this address
        )
        for kind in ("_https._tcp.local.", "_houseos._tcp.local.")
    ]


def announce_loop():
    """Relay thread: be `houseos.local` on the home network, and follow its address changes."""
    from zeroconf import IPVersion, Zeroconf

    from .music_outputs import lan_address

    zc, shown = None, None
    while True:
        try:
            address = lan_address()
            port, origin = door(address) if settings.mdns_name else (None, None)
            if (address, origin) != shown:
                if zc:
                    zc.close()  # says goodbye for the old address
                    zc = None
                if origin:
                    zc = Zeroconf(interfaces=[address], ip_version=IPVersion.V4Only)
                    for info in announcements(address, port, origin):
                        zc.register_service(info, allow_name_change=True)
                with SessionLocal() as db:
                    row = db.get(Integration, ANNOUNCED) or Integration(name=ANNOUNCED, enabled=True)
                    row.config = {"origin": origin, "address": address}
                    db.merge(row)
                    db.commit()
                shown = address, origin
        except Exception as exc:  # no network yet, or a database blip: try again soon
            print("mdns_announce_failed", type(exc).__name__, flush=True)
        time.sleep(60)


def lan_settings():
    """compose.lan.yml's .env lines, read from this computer's network (run on the host
    network): the card with the default route, its subnet and router, and a free address."""
    from .dlna import neighbours, table
    from .music_outputs import lan_address

    def dotted(value):
        return socket.inet_ntoa(struct.pack("<I", int(value, 16)))

    routes = table("/proc/net/route")
    parent, _, gateway = next(row[:3] for row in routes if row[1] == "00000000" and row[7] == "00000000")
    link = next(row for row in routes if row[0] == parent and row[2] == "00000000" and row[7] != "00000000")
    subnet = ipaddress.ip_network(f"{dotted(link[1])}/{dotted(link[7])}")
    taken = {lan_address(), dotted(gateway), *neighbours()}
    # ponytail: "free" means not seen in the ARP table; the admin checks it against the router.
    free = next(str(host) for host in reversed(list(subnet.hosts())) if str(host) not in taken)
    return {
        "HOUSEOS_LAN_PARENT": parent,
        "HOUSEOS_LAN_SUBNET": str(subnet),
        "HOUSEOS_LAN_GATEWAY": dotted(gateway),
        "HOUSEOS_LAN_IP": free,
    }


def suggest_lan():
    print("# HouseOS as its own device: add to .env, then `docker compose up -d`.")
    print("# Check the address is free and outside your router's automatic (DHCP) range.")
    print("COMPOSE_FILE=docker-compose.yml:compose.lan.yml")
    for key, value in lan_settings().items():
        print(f"{key}={value}")


@router.post("/admin/devices/discover")
def request_scan(actor=Depends(require_admin), db=Depends(get_db)):
    row = db.get(Integration, ROW) or Integration(name=ROW, config={}, enabled=True)
    row.config = {**(row.config or {}), "requested_at": utcnow().isoformat() + "Z"}
    db.merge(row)
    db.commit()
    return {"status": "scanning"}


@router.get("/admin/devices/discover")
def scan_result(actor=Depends(require_admin), db=Depends(get_db)):
    from .music_outputs import relay_base_url

    config = (db.get(Integration, ROW) or Integration(config={})).config or {}
    announced = (db.get(Integration, ANNOUNCED) or Integration(config={})).config or {}
    return {
        "scanning": bool(config.get("requested_at"))
        and config.get("scanned_for") != config.get("requested_at"),
        "scanned_at": config.get("scanned_at"),
        "devices": config.get("devices", []),
        "problem": config.get("problem"),
        "scanner_running": bool(relay_base_url(db)),
        "announced": announced.get("origin"),
    }
