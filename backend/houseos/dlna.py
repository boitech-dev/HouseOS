"""UPnP/DLNA media renderers: most smart TVs (Samsung, LG, Sony, Philips, Hisense…), Sonos,
many hi-fi speakers and Kodi. Found by SSDP, controlled with AVTransport/RenderingControl SOAP.

Every URL a device hands out is pinned to that device's own private address: HouseOS never
follows a description or control URL anywhere else. XML is size-capped and DTD-free."""

import hashlib
import ipaddress
import socket
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit
from xml.sax.saxutils import escape

import httpx

from .playback import MediaError

RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"
SSDP = ("239.255.255.250", 1900)
MAX_XML = 256 * 1024
# Control URLs per renderer, found once per worker run; forgotten when a call fails.
CONTROLS: dict = {}


def private_host(url, address=None):
    """The URL's host when it is an http URL on a private LAN address (and `address`, if given)."""
    try:
        parts = urlsplit(url)
        host = ipaddress.ip_address(parts.hostname or "")
    except ValueError:
        return None
    if parts.scheme != "http" or not host.is_private or host.is_loopback or host.is_link_local:
        return None
    return str(host) if address in (None, str(host)) else None


def xml(data):
    """Parse a device's XML: small, and no DOCTYPE (so no entity expansion of any kind)."""
    if len(data) > MAX_XML or b"<!DOCTYPE" in data.upper():
        raise ValueError("unsafe XML")
    return ET.fromstring(data)


def local(tag):
    return tag.rsplit("}", 1)[-1]


# ---------- discovery ----------
def table(path):
    try:
        with open(path) as rows:
            return [line.split() for line in rows.read().splitlines()[1:]]
    except OSError:
        return []


def neighbours():
    """Home network addresses this computer knows (the ARP table of its default route's
    interface, not Docker's). Asking them directly as well gets through a host firewall (ufw),
    which drops the answers to a multicast question."""
    lan = {row[0] for row in table("/proc/net/route") if len(row) > 1 and row[1] == "00000000"}
    known = [row for row in table("/proc/net/arp") if len(row) > 5 and row[2] == "0x2"]
    return [row[0] for row in known if row[5] in lan][:254]


def search(timeout=3.0, targets=(SSDP,), kinds=(RENDERER,)):
    """M-SEARCH for renderers (or other SSDP `kinds`); {sender address: description URL}.
    Multicast by default; `[(address, 1900)]` asks devices directly (works from a Docker bridge
    too)."""
    requests = [
        (
            "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
            f'MAN: "ssdp:discover"\r\nMX: 2\r\nST: {kind}\r\n\r\n'
        ).encode()
        for kind in kinds
    ]
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for target in [*targets, *targets]:  # UDP: twice, in case one is lost
            for request in requests:
                try:
                    sock.sendto(request, target)
                except OSError:
                    break  # an unreachable neighbour
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0 and len(found) < 64:
            sock.settimeout(left)
            try:
                data, (sender, _) = sock.recvfrom(4096)
            except OSError:
                break
            location = ssdp_location(data, sender, kinds)
            if location:
                found.setdefault(sender, location)
    return found


def ssdp_location(data, sender, kinds=(RENDERER,)):
    """The LOCATION of an SSDP answer of one of `kinds`, if it points back at the sender."""
    lines = data.decode("latin-1").split("\r\n")
    if not lines[0].upper().startswith("HTTP/1.1 200"):
        return None
    headers = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:])}
    location = headers.get("location", "")
    if not any(kind in headers.get("st", "") or kind in headers.get("nt", "") for kind in kinds):
        return None
    return location if len(location) <= 300 and private_host(location, sender) else None


def describe(location, address):
    """Name, maker, model and control URLs from a renderer's description XML."""
    if not private_host(location, address):
        raise ValueError("description outside the device")
    with httpx.stream("GET", location, timeout=3, follow_redirects=False) as response:
        response.raise_for_status()
        data = b""
        for chunk in response.iter_bytes():
            data += chunk
            if len(data) > MAX_XML:
                raise ValueError("description too large")
    return description(data, location, address)


def description(data, location, address):
    root = xml(data)
    first = {}
    services = {}
    base = next((e.text for e in root if local(e.tag) == "URLBase" and e.text), location)
    for element in root.iter():
        name = local(element.tag)
        if name in {"friendlyName", "manufacturer", "modelName"} and element.text:
            first.setdefault(name, element.text.strip()[:100])
        if name == "service":
            fields = {local(child.tag): (child.text or "").strip() for child in element}
            url = urljoin(base, fields.get("controlURL", ""))
            kind = fields.get("serviceType", "").rsplit(":", 1)[0]
            if kind in (AVT[:-2], RC[:-2]) and private_host(url, address):
                services.setdefault(kind, url)
    return {
        "name": first.get("friendlyName") or address,
        "maker": first.get("manufacturer", ""),
        "model": first.get("modelName", ""),
        "av": services.get(AVT[:-2]),
        "rc": services.get(RC[:-2]),
    }


def renderer(address, location):
    """A discovery scan item for one renderer, or None when its description is unusable."""
    try:
        info = describe(location, address)
    except (httpx.HTTPError, ValueError, ET.ParseError):
        return None
    return {
        "kind": "dlna",
        "name": info["name"],
        "address": address,
        "maker": info["maker"],
        "model": info["model"],
        "playable": bool(info["av"]),  # AVTransport: it can be told what to play
        "description_url": location,
    }


# TVs that answer to their maker's own protocol even when they don't offer DLNA playback: found
# so the admin sees them and learns how to control them (Home Assistant, the TV's browser).
SCREENS = (
    "urn:lge-com:service:webos-second-screen:1",  # LG webOS
    "urn:samsung.com:device:RemoteControlReceiver:1",  # Samsung
    "urn:schemas-sony-com:service:ScalarWebAPI:1",  # Sony Bravia
    "roku:ecp",  # Roku TVs and sticks
    "urn:dial-multiscreen-org:service:dial:1",  # DIAL: most smart TVs, Fire TV, Android TV
)


def screen(address, location):
    try:
        info = describe(location, address)
    except (httpx.HTTPError, ValueError, ET.ParseError):
        info = {"name": address, "maker": "", "model": ""}
    return {
        "kind": "screen",
        "name": info["name"],
        "address": address,
        "maker": info["maker"],
        "model": info["model"],
        "playable": False,
    }


def screens(timeout=3.0):
    found = search(timeout, [SSDP, *((address, 1900) for address in neighbours())], SCREENS)
    with ThreadPoolExecutor(8) as pool:
        return list(pool.map(screen, found, found.values()))


def renderers(timeout=3.0):
    found = search(timeout, [SSDP, *((address, 1900) for address in neighbours())])
    with ThreadPoolExecutor(8) as pool:
        return [item for item in pool.map(renderer, found, found.values()) if item]


# ---------- control (the music follower, worker process) ----------
def target(device):
    """What the follower calls a renderer by: its saved description URL, else its address."""
    saved = (device.capabilities or {}).get("description_url") or ""
    return saved if private_host(saved, device.address) else device.address


def resolve(where):
    """Name and control URLs from a description URL or an address (asked directly by SSDP)."""
    address = private_host(where) or where
    locations = [where] if where != address else []
    for location in locations + [None]:
        try:
            location = location or search(3, [(address, 1900)]).get(address)
            return describe(location, address) if location else None
        except (httpx.HTTPError, ValueError, ET.ParseError):
            continue  # its port may have changed since it was added: ask the device again
    return None


def controls(where):
    """Control URLs for a renderer, looked up once and kept until a call fails."""
    if where not in CONTROLS:
        info = resolve(where)
        if not info:
            raise MediaError("TARGET_OFFLINE", "The speaker did not answer.", "destination", True)
        if not info["av"]:
            raise MediaError("TARGET_INCOMPATIBLE", "This device cannot play music.", "destination")
        CONTROLS[where] = info
    return CONTROLS[where]


def soap(where, service, action, **arguments):
    """One SOAP action; the response's output arguments."""
    url = controls(where)["av" if service == AVT else "rc"]
    if not url:
        raise MediaError("TARGET_INCOMPATIBLE", "This device has no volume control.", "control")
    body = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in arguments.items())
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?><s:Envelope '
        'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>'
    )
    try:
        response = httpx.post(
            url,
            content=envelope.encode(),
            headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{service}#{action}"'},
            timeout=5,
            follow_redirects=False,
        )
        if response.status_code == 500 and b"<errorCode>" in response.content[:4096]:
            # A UPnP refusal, not a lost packet: a grouped Sonos that isn't the group's main
            # speaker answers 800, for example. Retrying won't help; say so.
            raise MediaError("SPEAKER_REFUSED", "The speaker refused the song.", "control", False)
        response.raise_for_status()
        reply = next(e for e in xml(response.content).iter() if local(e.tag) == action + "Response")
    except (httpx.HTTPError, ValueError, ET.ParseError, StopIteration):
        CONTROLS.pop(where, None)  # its port may have changed: look it up again next time
        raise MediaError(
            "PLAYBACK_NOT_OBSERVED", "The speaker did not confirm the command.", "control", True
        ) from None
    return {local(child.tag): child.text or "" for child in reply}


def clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def seconds(value):
    try:
        h, m, s = (value or "").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return None  # NOT_IMPLEMENTED and friends


def didl(url, mime, title):
    """Minimal DIDL-Lite: renderers such as Sonos and Samsung refuse a URI without it."""
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        f'<item id="0" parentID="-1" restricted="1"><dc:title>{escape(title or "HouseOS")}</dc:title>'
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        f'<res protocolInfo="http-get:*:{escape(mime)}:*">{escape(url)}</res></item></DIDL-Lite>'
    )


def dlna_music(where, url, mime, position, paused, live, title):
    """Load one song, same contract as cinema_cast.cast_music."""
    soap(
        where,
        AVT,
        "SetAVTransportURI",
        InstanceID=0,
        CurrentURI=url,
        CurrentURIMetaData=didl(url, mime, title),
    )
    if not paused:
        soap(where, AVT, "Play", InstanceID=0, Speed=1)
        for _ in range(10):  # most renderers refuse Seek until they are actually playing
            if soap(where, AVT, "GetTransportInfo", InstanceID=0).get("CurrentTransportState") == "PLAYING":
                break
            time.sleep(0.5)
    if position >= 1 and not live:
        try:
            soap(where, AVT, "Seek", InstanceID=0, Unit="REL_TIME", Target=clock(position))
        except MediaError:
            pass  # stopped renderers may refuse; the follower's next check puts it right


def dlna_control(where, action, value):
    """pause, resume, stop, seek (seconds) or volume (0–100), like cinema_cast.cast_control."""
    if action == "volume":
        soap(where, RC, "SetVolume", InstanceID=0, Channel="Master", DesiredVolume=int(value))
    elif action == "seek":
        soap(where, AVT, "Seek", InstanceID=0, Unit="REL_TIME", Target=clock(value))
    elif action == "resume":
        soap(where, AVT, "Play", InstanceID=0, Speed=1)
    else:
        soap(where, AVT, {"pause": "Pause", "stop": "Stop"}[action], InstanceID=0)


def dlna_observe(where):
    """What the renderer plays and where it is, like cinema_cast.cast_observe."""
    info = soap(where, AVT, "GetPositionInfo", InstanceID=0)
    uri = info.get("TrackURI") or ""
    return {
        "item_id": hashlib.sha256(uri.encode()).hexdigest() if uri else None,
        "position": seconds(info.get("RelTime")),
    }


def dlna_volume(where):
    """The renderer's own volume (0–100), or None when it won't say."""
    try:
        return int(soap(where, RC, "GetVolume", InstanceID=0, Channel="Master").get("CurrentVolume"))
    except (MediaError, TypeError, ValueError):
        return None
