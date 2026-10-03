"""A Stremio add-on the admin pasted: its RD+ and torrent versions, and one private file resolver.

No add-on is built in: the only host reached is the pasted link's (its /stream and /resolve paths)."""

import re
import json
import subprocess
from pathlib import Path
import time
from functools import lru_cache
from urllib.parse import quote, unquote, urljoin, urlsplit
from cryptography.fernet import Fernet
from .config import settings
from .integrations import integration_config
from .playback import MediaError
from .cinema_adapters import public_url, RealDebrid


# Exact upstream addon/moch/static.js failure videos; never cast these as a movie.
STATIC_FAILURES = {
    "/videos/downloading_v3.mp4": (
        "SOURCE_NOT_READY",
        "The debrid service is still preparing this file. Choose another cached version.",
    ),
    "/videos/failed_infringement_v3.mp4": (
        "RD_FILE_BLOCKED",
        "The debrid service rejected this file under its infringement policy. Choose another release.",
    ),
    "/videos/failed_access_v3.mp4": (
        "RD_ACCESS_DENIED",
        "The debrid service rejected account access. Check the integration.",
    ),
    "/videos/blocked_access_v2.mp4": ("PROVIDER_ACCESS_DENIED", "The add-on blocked access to this request."),
    "/videos/limits_exceeded_v2.mp4": (
        "RD_LIMIT_EXCEEDED",
        "The debrid service reported an account limit. Try later.",
    ),
    **{
        f"/videos/{name}.mp4": (
            "SOURCE_NOT_READY",
            "The add-on could not prepare this file. Choose another cached release.",
        )
        for name in [
            "download_failed_v3",
            "failed_rar_v3",
            "failed_too_big_v2",
            "failed_opening_v3",
            "failed_unexpected_v3",
            "failed_unavailable_v1",
        ]
    },
}


def configured_base(config):
    """The pasted add-on link, whatever its host: (base, debrid key or "")."""
    url = config.get("manifest_url", "")
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 443)
        or p.query
        or p.fragment
        or not p.path.endswith("/manifest.json")
    ):
        raise MediaError(
            "PROVIDER_UNCONFIGURED",
            "Paste the add-on's https link, ending in /manifest.json, in Control Room.",
            "setup",
        )
    options = unquote(p.path.removesuffix("/manifest.json").strip("/"))
    key = next((part.split("=", 1)[1] for part in options.split("|") if part.startswith("realdebrid=")), "")
    if not key and re.search(r"(?:^|\|)(?:alldebrid|premiumize|torbox|debridlink)=", options):
        raise MediaError(
            "PROVIDER_UNCONFIGURED",
            "HouseOS doesn't support this debrid service on add-on links yet. Turn on the torrent "
            "player below, or use a link without it.",
            "setup",
        )
    if not key and config.get("torrent_player") is True:
        return url.removesuffix("/manifest.json"), ""  # no debrid: the torrent player plays it
    if not re.fullmatch(r"[A-Za-z0-9]+", key):
        raise MediaError(
            "PROVIDER_UNCONFIGURED",
            "This add-on link has no debrid service. Turn on the torrent player below, or add your "
            "debrid API token in the add-on's settings and paste the new link.",
            "setup",
        )
    return url.removesuffix("/manifest.json"), key


def addon_request(url, host, limit=4_000_000):
    parsed, address = public_url(url)
    if parsed.netloc != host:
        raise MediaError("UNSAFE_SOURCE", "Unexpected addon endpoint.", "resolve")
    try:
        result = subprocess.run(
            ["/usr/bin/node", str(Path(__file__).with_name("addon_http.cjs"))],
            input=json.dumps(
                {
                    "host": parsed.hostname,
                    "path": parsed.path + ("?" + parsed.query if parsed.query else ""),
                    "address": address,
                    "limit": limit,
                }
            ),
            capture_output=True,
            text=True,
            timeout=18,
        )
        if result.returncode or len(result.stdout) > 8_100_000:
            raise ValueError()
        response = json.loads(result.stdout)
        if response["status"] == 403:
            raise MediaError(
                "PROVIDER_ACCESS_DENIED",
                "The add-on refused the request. Try again later.",
                "discover",
                True,
            )
        return response
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        raise MediaError(
            "PROVIDER_UNAVAILABLE", "The add-on did not respond. Try again shortly.", "discover", True
        ) from None


@lru_cache(maxsize=64)
def _listing(base, identity, kind, bucket):
    response = addon_request(f"{base}/stream/{kind}/{quote(identity, safe=':')}.json", urlsplit(base).netloc)
    try:
        if response["status"] != 200:
            raise ValueError()
        return json.loads(response["body"])
    except (ValueError, KeyError):
        raise MediaError(
            "PROVIDER_UNAVAILABLE", "The add-on could not load the source list.", "discover", True
        ) from None


def plain_stream(entry):
    """A version the debrid service doesn't hold: its torrent (hash, file, name), for the torrent player."""
    p = urlsplit(str(entry.get("url", "")))
    fields = p.path.split("/")
    hints = entry.get("behaviorHints") or {}
    info_hash = str(entry.get("infoHash") or (fields[4] if len(fields) == 8 else ""))
    index = entry.get("fileIdx", fields[6] if len(fields) == 8 else 0)
    filename = (hints.get("filename") if isinstance(hints, dict) else None) or (
        unquote(fields[7]) if len(fields) == 8 else "video"
    )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", info_hash) or not str(index).isdigit():
        return None
    return info_hash, "null", str(int(index)), str(filename)[:300]


def normalize_streams(raw, host, key, p2p=False):
    """The add-on's versions: the debrid-cached ones (its `[RD+]` marker), and, with the torrent player
    on, the others too (played from their torrent: rd_cached False, cached ones rank first)."""
    results, seen = [], set()
    entries = raw.get("streams", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        return []
    for order, entry in enumerate(entries[:2000]):
        if not isinstance(entry, dict):
            continue
        rd = "[RD+]" in str(entry.get("name", "")) and bool(key)
        if rd:
            p = urlsplit(str(entry.get("url", "")))
            fields = p.path.split("/")
            if (
                p.scheme != "https"
                or p.netloc != host
                or p.query
                or p.fragment
                or len(fields) != 8
                or fields[1:3] != ["resolve", "realdebrid"]
                or fields[3] != key
            ):
                continue
            info_hash, cached, index, filename = fields[4:]
        elif p2p and (plain := plain_stream(entry)):
            info_hash, cached, index, filename = plain
        else:
            continue
        if (
            not re.fullmatch(r"[0-9a-fA-F]{40}", info_hash)
            or not index.isdigit()
            or int(index) > 100000
            or not re.fullmatch(r"[A-Za-z0-9,._-]{1,300}", cached)
        ):
            continue
        identity = (info_hash.lower(), int(index))
        if identity in seen:
            continue
        seen.add(identity)
        description = str(entry.get("title") or entry.get("description") or "Source")[:2000]
        quality = re.search(
            r"(?<!\d)(4320|2160|1080|720|480)[pP]\b", str(entry.get("name", "")) + " " + description
        )
        seeds = re.search(r"👤\s*(\d{1,8})", description)
        if not rd and seeds and int(seeds.group(1)) == 0:
            continue  # nobody shares it: it would never start
        hints = entry.get("behaviorHints") or {}
        size = hints.get("videoSize") if isinstance(hints, dict) else None
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            claimed = re.search(r"💾\s*([0-9]+(?:\.[0-9]+)?)\s*(GB|MB)", description)
            size = int(float(claimed[1]) * (1024**3 if claimed[2] == "GB" else 1024**2)) if claimed else None
        results.append(
            {
                "provider": "stream_addon",
                "provider_order": order,
                "info_hash": identity[0],
                "file_index": identity[1],
                "_addon_cached": cached,
                "_addon_filename": unquote(filename),
                "release": description[:300],
                "size": size,
                "height_claim": int(quality.group(1)) if quality else None,
                "seeders_claim": int(seeds.group(1)) if seeds else None,
                "rd_cached": rd,
                "cache_evidence": "addon_cached" if rd else "p2p",
                "evidence": "provider_claim",
                "state": "discovered",
            }
        )
    return results[:300]


class StreamAddon:
    def __init__(self, config):
        if not config.get("enabled"):
            raise MediaError("PROVIDER_UNCONFIGURED", "Add a stream add-on in Control Room.", "setup")
        self.base, self.key = configured_base(config)
        self.p2p = bool(config.get("torrent_player") is True)

    def streams(self, canonical, kind, season=None, episode=None):
        identity = (
            canonical
            if kind == "movie" or canonical.startswith("kitsu:")
            else f"{canonical}:{season}:{episode}"
        )
        return normalize_streams(
            _listing(self.base, identity, kind, int(time.time() // 300)),
            urlsplit(self.base).netloc,
            self.key,
            self.p2p,
        )


def resolve_media(db, source, refresh=False):
    """Lease is encrypted in workflow-private data; no provider URL enters tool results."""
    if source.get("web_video"):  # Watch → Web: downloaded to the house (cinema_web)
        from .cinema_web import web_file

        path = web_file(db, source["web_video"])
        return "local:" + str(path), path.stat().st_size
    if source.get("local_record"):
        from .cinema import saved_path
        from .models import Record

        record = db.get(Record, source["local_record"])
        if not record or record.deleted_at:
            raise MediaError(
                "MEDIA_UNAVAILABLE", "This saved film was removed from the house disk.", "resolve"
            )
        path = saved_path(record.data.get("_path"))
        return "local:" + str(path), path.stat().st_size
    cipher = Fernet(settings.encryption_key.encode())
    if not refresh and source.get("_resolved_until", 0) > time.time() and source.get("_resolved_url"):
        return cipher.decrypt(source["_resolved_url"].encode()).decode(), source.get("size")
    if source.get("provider") != "stream_addon":
        rd = RealDebrid(integration_config(db, "real_debrid"))
        if (
            refresh
            and source.get("info_hash")
            and rd.info(source["torrent_id"]).get("hash", "").lower() != source["info_hash"].lower()
        ):
            raise MediaError(
                "EPISODE_MISMATCH",
                "The account source identity changed. Select the exact source again.",
                "resolve",
            )
        return rd.resolve(source["torrent_id"], source["file_id"])
    config = integration_config(db, "stream_addon")
    base, key = configured_base(config)
    p2p = bool(config.get("torrent_player") is True)
    h = source.get("info_hash", "")
    index = source.get("file_index")
    cached = source.get("_addon_cached", "null")
    filename = source.get("_addon_filename", "")
    if (
        not re.fullmatch(r"[a-f0-9]{40}", h)
        or type(index) is not int
        or not 0 <= index <= 100000
        or not re.fullmatch(r"[A-Za-z0-9,._-]{1,300}", cached)
        or not filename
        or len(filename) > 1000
    ):
        raise MediaError("SOURCE_EXPIRED", "This version needs a fresh source list.", "resolve")
    if not key or source.get("rd_cached") is False:
        if not p2p:
            raise MediaError(
                "TORRENT_PLAYER_OFF",
                "The add-on only lists torrents here: turn on the torrent player, or add a debrid service.",
                "setup",
            )
        return torrent_resolve(source, h, index)
    try:
        return rd_resolve(source, urlsplit(base).netloc, key, h, cached, index, filename, cipher)
    except MediaError as rd_error:
        if not p2p:
            raise
        try:
            return torrent_resolve(source, h, index)  # the debrid service can't: the torrent player can
        except MediaError:
            raise rd_error from None


def torrent_resolve(source, info_hash, index):
    """The torrent player serves this file while it downloads; its size, from the first byte.
    A size other than the add-on's is another file of the torrent: refused, never played."""
    from .cinema_adapters import public_stream

    url = f"torrent:{info_hash}/{index}"
    status, headers, chunks = public_stream(url, "bytes=0-0")
    try:
        next(chunks, None)  # start the generator, so closing it closes the connection
    finally:
        chunks.close()
    headers = {k.lower(): v for k, v in headers.items()}
    match = re.fullmatch(r"bytes 0-0/(\d+)", headers.get("content-range", ""))
    if status != 206 or not match:
        raise MediaError("TORRENT_NO_PEERS", "Nobody is sharing this version right now.", "resolve", True)
    size = int(match[1])
    listed = source.get("size")
    if listed and abs(size - listed) > max(listed // 100, 2 * 1024**2):
        raise MediaError("SOURCE_EXPIRED", "This version needs a fresh source list.", "resolve")
    source["size"] = size
    return url, size


def rd_resolve(source, host, key, h, cached, index, filename, cipher):
    url = f"https://{host}/resolve/realdebrid/{key}/{h}/{cached}/{index}/{quote(filename, safe='')}"
    for _ in range(5):
        p, address = public_url(url)
        # The add-on deliberately redirects provider failures to explanatory video clips.
        failure = STATIC_FAILURES.get(p.path)
        if failure:
            raise MediaError(failure[0], failure[1], "resolve", True)
        if p.netloc != host:
            # RD returns an opaque CDN URL. Validate public HTTPS via public_url,
            # rather than guessing a provider-owned hostname suffix.

            from .cinema_adapters import public_stream

            status, headers, chunks = public_stream(url, "bytes=0-0")
            try:
                next(chunks, None)  # Enter/close the response generator even for a HEAD-like result.
            finally:
                if hasattr(chunks, "close"):
                    chunks.close()
            headers = {k.lower(): v for k, v in headers.items()}
            match = re.fullmatch(r"bytes 0-0/(\d+)", headers.get("content-range", ""))
            size = (
                int(match[1])
                if status == 206 and match
                else int(headers.get("content-length", "0"))
                if status == 200 and headers.get("content-length", "").isdigit()
                else 0
            )
            if size <= 0:
                raise MediaError(
                    "SOURCE_SIZE_UNKNOWN",
                    "This source did not report its media size. Choose another version.",
                    "resolve",
                    True,
                )
            if source.get("state") == "preflight_usable" and source.get("size") and source["size"] != size:
                raise MediaError(
                    "PLAN_STALE", "The resolved file size changed. Select this version again.", "resolve"
                )
            source["size"] = size
            source["_resolved_url"] = cipher.encrypt(url.encode()).decode()
            source["_resolved_until"] = time.time() + 900
            return url, size
        response = addon_request(url, host, limit=0)
        if response["status"] in {301, 302, 303, 307, 308}:
            url = urljoin(url, response.get("location", ""))
            continue
        raise MediaError(
            "SOURCE_NOT_READY",
            "The add-on has not returned a playable debrid file. Choose another version.",
            "resolve",
            True,
        )
    raise MediaError(
        "SOURCE_NOT_READY", "The add-on's resolution exceeded its redirect limit.", "resolve", True
    )


def probe_media(url, directory):
    """Range-aware inspection; 32 MiB total across seeks and a 25-second parser budget."""
    import json
    from pathlib import Path
    import subprocess
    import tempfile
    import threading
    from .cinema_adapters import public_stream
    from .cinema_stream_input import input_broker, streaming_media_command
    from .playback import MEDIA_ENV, inspect_probe

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    used = 0
    exceeded = False
    lock = threading.Lock()

    def expired():
        return time.monotonic() - started > 25 or exceeded

    def opener(byte_range, head):
        status, headers, chunks = public_stream(url, byte_range, head=head)

        def bounded():
            nonlocal used, exceeded
            try:
                for block in chunks:
                    with lock:
                        used += len(block)
                        if used > 32 * 1024**2:
                            exceeded = True
                    if expired():
                        return
                    yield block
            finally:
                if hasattr(chunks, "close"):
                    chunks.close()

        return status, headers, bounded()

    try:
        with tempfile.TemporaryDirectory(prefix="probe-", dir=root) as temporary:
            work = Path(temporary)
            with input_broker(work, opener, cancelled=expired) as socket:
                args = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "http,tcp",
                    "-format_whitelist",
                    "mov,matroska,webm,mpegts,avi,mpeg",
                    "-probesize",
                    "16000000",
                    "-analyzeduration",
                    "10000000",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    "INPUT",
                ]
                result = subprocess.run(
                    streaming_media_command(args, socket, work),
                    capture_output=True,
                    env=MEDIA_ENV,
                    timeout=25,
                )
                if expired():
                    raise MediaError(
                        "PROBE_BUDGET_EXCEEDED",
                        "This release needs more inspection than the quick playback budget. Choose another version.",
                        "probe",
                        True,
                    )
                if result.returncode or len(result.stdout) > 2 * 1024**2:
                    raise ValueError()
                return inspect_probe(json.loads(result.stdout))
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
        raise MediaError(
            "MEDIA_PROBE_FAILED",
            "The media tracks could not be inspected. Choose another version.",
            "probe",
            True,
        ) from None
