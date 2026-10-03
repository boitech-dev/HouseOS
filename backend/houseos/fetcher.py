"""No-secret parser process. Deploy only with the accompanying egress sandbox."""

import json
from html.parser import HTMLParser
import re
import os
import selectors
import socketserver
import subprocess
import time
import threading
from uuid import UUID
from .music import canonical_source
from .config import settings
from .fetcher_cache import resolve as cached_resolve, source_lock, prune

ROOT = settings.runtime_root / "audio"
SOCKET = settings.runtime_root / "run/fetch.sock"
SLOW_REQUESTS = threading.BoundedSemaphore(2)
WEB_VIDEO = threading.BoundedSemaphore(1)  # a video download never takes a song's place
GAMES = threading.BoundedSemaphore(3)  # a game's files load a few at once; songs keep their own
GAME_LINKS = threading.BoundedSemaphore(1)  # a pasted game (up to 16 GB) never holds the others up
COMPLETED = {}
YOUTUBE_PAUSE = {"until": 0, "code": "YOUTUBE_RATE_LIMITED"}
# YouTube's bot check marks one address, not the house: IPv6 can be refused while IPv4 still works
# after many downloads in a short time. On a bot check the request is tried once on the other
# network and YouTube stays there 12 h (run()).
ROUTE = {"flag": None, "until": 0.0}


def youtube_request(data):
    if data.get("action") == "search":
        return data.get("source") != "soundcloud"
    url = str(data.get("source_url", ""))
    return "youtube.com/" in url or "youtu.be/" in url


def run(data):
    """execute(), and on a YouTube bot check the same request once more on the other network."""
    try:
        return execute(data)
    except ValueError as error:
        if (
            str(error) != "YOUTUBE_SIGN_IN_REQUIRED"
            or not youtube_request(data)
            or time.monotonic() < ROUTE["until"]
        ):
            raise
        ROUTE.update(
            flag="--force-ipv6" if ROUTE["flag"] == "--force-ipv4" else "--force-ipv4",
            until=time.monotonic() + 12 * 3600,
        )
        print("youtube bot check: trying", ROUTE["flag"], "for 12 h", flush=True)
        return execute(data)


def failure_code(stderr):
    """The resident-facing reason for a failed yt-dlp run; the cause goes to the journal."""
    message = stderr.lower()
    tail = re.sub(r"https?://\S+", "<url>", stderr.strip()[-600:])
    print("fetch failed:", tail.replace("\n", " | "), flush=True)
    if "confirm your age" in message or "age-restricted" in message:
        return "YOUTUBE_AGE_RESTRICTED"
    if "in your country" in message:
        return "SOURCE_REGION_BLOCKED"
    if "[youtube]" in message:
        if "not a bot" in message:
            return "YOUTUBE_SIGN_IN_REQUIRED"
        if "429" in message or "too many requests" in message:
            return "YOUTUBE_RATE_LIMITED"
    # A playlist link cut short, private, or only its owner's (Liked music): YouTube can't show it.
    if "playlist does not exist" in message or "playlist is private" in message or "unviewable" in message:
        return "PLAYLIST_NOT_FOUND"
    if "private video" in message or "video unavailable" in message or "has been removed" in message:
        return "SOURCE_REMOVED"
    if "http error 403" in message or "http error 410" in message:
        return "SOURCE_URL_EXPIRED"
    if "drm" in message:
        return "WEB_VIDEO_DRM"
    if "unsupported url" in message or "no video formats found" in message:
        return "WEB_VIDEO_UNSUPPORTED"
    if "log in" in message or "login required" in message or "logged-in" in message:
        return "WEB_VIDEO_SIGN_IN"
    if "http error 404" in message or "unable to download webpage" in message or ": not found." in message:
        return "WEB_VIDEO_NOT_FOUND"
    return "SOURCE_UNAVAILABLE"


def bounded_process(args, timeout, output_limit=2_000_000, cancelled=None, file_limit=400 * 1024**2):
    def limits():
        import resource

        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))

    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, preexec_fn=limits
    )
    output, errors = bytearray(), bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                raise ValueError("DOWNLOAD_CANCELLED")
            for key, _ in selector.select(timeout=0.2):
                data = os.read(key.fd, 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                if key.fileobj is process.stderr:
                    errors.extend(data)
                    del errors[:-65536]
                else:
                    output.extend(data)
                    if len(output) > output_limit:
                        raise ValueError("SOURCE_RESPONSE_TOO_LARGE")
            if not selector.get_map():
                if process.wait(timeout=2) != 0:
                    raise ValueError(failure_code(errors.decode("utf-8", errors="replace")))
                return bytes(output)
        raise ValueError("SOURCE_TIMEOUT")
    finally:
        selector.close()
        if process.poll() is None:
            import signal

            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def resolve_share_link(value):
    """Follow only the official SoundCloud short host, bounded and DNS-pinned."""
    from urllib.parse import urlsplit, urljoin
    from .cinema_adapters import public_url, PinnedHTTPS

    url = canonical_source(value)
    deadline = time.monotonic() + 30
    for _ in range(4):
        if time.monotonic() >= deadline:
            raise ValueError("SOURCE_TIMEOUT")
        parsed = urlsplit(url)
        if parsed.hostname in {"soundcloud.com", "www.soundcloud.com"}:
            return canonical_source(url)
        if parsed.hostname != "on.soundcloud.com":
            raise ValueError("SOURCE_LINK_UNRESOLVED")
        parsed, address = public_url(url)
        connection = PinnedHTTPS(parsed.hostname, address)
        connection.timeout = min(8, max(1, deadline - time.monotonic()))
        try:
            connection.request(
                "GET",
                parsed.path + ("?" + parsed.query if parsed.query else ""),
                headers={"User-Agent": "HouseOS/1.0", "Accept-Encoding": "identity"},
            )
            response = connection.getresponse()
            if response.status not in {301, 302, 303, 307, 308}:
                raise ValueError("SOURCE_LINK_UNRESOLVED")
            target = urljoin(url, response.getheader("Location", ""))
            next_url = urlsplit(target)
            if (
                next_url.scheme != "https"
                or next_url.hostname not in {"on.soundcloud.com", "soundcloud.com", "www.soundcloud.com"}
                or next_url.username
                or next_url.password
                or next_url.port not in (None, 443)
            ):
                raise ValueError("SOURCE_LINK_UNRESOLVED")
            url = target
        finally:
            connection.close()
    raise ValueError("SOURCE_LINK_UNRESOLVED")


def cached_audio_bytes():
    sizes = {}
    for path in ROOT.iterdir():
        try:
            info = path.lstat()
            if path.is_file() and not path.is_symlink():
                sizes[(info.st_dev, info.st_ino)] = info.st_size
        except FileNotFoundError:
            continue
    return sum(sizes.values())


def resolve_info(url, base, refresh=False):
    def extract(args, timeout):
        if url.startswith("https://www.youtube.com/") and time.monotonic() < YOUTUBE_PAUSE["until"]:
            raise ValueError(YOUTUBE_PAUSE["code"])
        return bounded_process(args, timeout)

    return cached_resolve(ROOT, url, base, extract, refresh)


def cleanup_download(item, complete=False):
    for path in ROOT.glob(item + ".media*"):
        if not complete or path.name != item + ".media":
            path.unlink(missing_ok=True)


class Text(HTMLParser):
    """A page's readable text and title (scripts, styles and forms dropped)."""

    SKIP = {"script", "style", "noscript", "template", "svg", "form", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self.title, self.depth, self.in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        self.depth += tag in self.SKIP
        self.in_title = self.in_title or tag == "title"

    def handle_endtag(self, tag):
        self.depth -= tag in self.SKIP and self.depth > 0
        self.in_title = self.in_title and tag != "title"
        if tag in {"p", "div", "li", "h1", "h2", "h3", "br", "tr", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.depth:
            self.parts.append(data)


def web(action, url):
    """The theme studio reads a public page's text or looks at a public picture. Only public
    HTTPS addresses (every redirect checked again), inside this service's network rules."""
    from .cinema_adapters import public_fetch
    from .playback import MediaError
    from .pictures import downscale

    try:
        content, headers = public_fetch(url, limit=2_000_000 if action == "page" else 8_000_000)
    except MediaError as error:
        raise ValueError(
            "UNSAFE_SOURCE"
            if error.code == "UNSAFE_SOURCE"
            else "SOURCE_RESPONSE_TOO_LARGE"
            if error.code == "PROBE_BUDGET_EXCEEDED"
            else "SOURCE_UNAVAILABLE"
        ) from None
    kind = headers.get("content-type", "").split(";")[0].strip().lower()
    if action == "image":
        import base64

        jpeg, width, height = downscale(content, 1024)
        return {"status": "completed", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode(),
                "width": width, "height": height}  # fmt: skip
    if kind not in {"text/html", "text/plain", "application/xhtml+xml"}:
        raise ValueError("PAGE_UNSUPPORTED")
    charset = re.search(r"charset=([\w-]+)", headers.get("content-type", ""))
    try:
        text = content.decode(charset.group(1) if charset else "utf-8", errors="replace")
    except LookupError:  # a charset Python doesn't know
        text = content.decode("utf-8", errors="replace")
    if kind == "text/plain":
        title, body = "", text
    else:
        parser = Text()
        parser.feed(text)
        title, body = parser.title, "".join(parser.parts)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n\n", body).strip()
    return {"status": "completed", "title": " ".join(title.split())[:200], "text": body[:7000],
            "truncated": len(body) > 7000}  # fmt: skip


def song_page(url):
    """A song link from a service HouseOS can't play (Spotify, Apple Music, Deezer, Tidal): what
    its public page says the song is (og:title, og:description), to find it on YouTube."""
    from html import unescape
    from urllib.parse import urlsplit
    from .cinema_adapters import public_fetch
    from .music import STREAMING_HOSTS
    from .playback import MediaError

    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in STREAMING_HOSTS):
        raise ValueError("UNSUPPORTED_SOURCE")
    try:
        content, _ = public_fetch(url, limit=1_000_000)
    except MediaError:
        raise ValueError("SOURCE_UNAVAILABLE") from None
    text = content.decode("utf-8", errors="replace")

    def meta(name):
        found = re.search(
            r'<meta[^>]+(?:property|name)="' + name + r'"[^>]*\scontent="([^"]*)"', text
        ) or re.search(r'<meta[^>]+content="([^"]*)"[^>]*(?:property|name)="' + name + '"', text)
        return " ".join(unescape(found.group(1)).split())[:200] if found else ""

    return {"status": "completed", "title": meta("og:title"), "description": meta("og:description")}


def execute(data):
    if data.get("action") == "ping":  # Control Room health
        return {"status": "ok"}
    if str(data.get("action")).startswith("games_"):  # Games (D33): metadata, emulators, links
        from .fetcher_games import execute as games_execute

        return games_execute(data)
    if data.get("action") == "cancel_download":
        item = str(UUID(data["item_id"]))
        (ROOT / (item + ".cancelled")).touch(mode=0o600)
        cleanup_download(item)
        return {"status": "completed"}
    if data.get("action") == "cache_prune":
        if data.get("keep_none"):  # the house keeps no songs: only the pinned ones stay
            return prune(ROOT, data.get("pins", []), maximum=0, reserve=0)
        return prune(ROOT, data.get("pins", []))
    if data.get("action") == "reuse":
        import stat

        original = ROOT / (str(UUID(data["cached_item_id"])) + ".media")
        target = ROOT / (str(UUID(data["item_id"])) + ".media")
        try:
            info = original.lstat()
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 400 * 1024**2:
                return {"status": "miss"}
            try:
                os.link(original, target, follow_symlinks=False)
            except FileExistsError:
                pass
            linked = target.lstat()
            if not stat.S_ISREG(linked.st_mode) or (linked.st_dev, linked.st_ino) != (
                info.st_dev,
                info.st_ino,
            ):
                return {"status": "miss"}
            os.utime(target, None, follow_symlinks=False)
            return {"status": "completed", "bytes": info.st_size}
        except OSError:
            return {"status": "miss"}
    if data.get("action") in {"page", "image"}:
        return web(data["action"], str(data.get("source_url") or ""))
    if data.get("action") == "song_page":
        return song_page(str(data.get("source_url") or ""))
    if data.get("action") == "canonical":
        return {"status": "completed", "source_url": resolve_share_link(data.get("source_url", ""))}
    base = [
        os.environ.get("HOUSEOS_RESOLVER_BIN", str(settings.runtime_root / "venvs/resolver/bin/yt-dlp")),
        "--ignore-config",
        "--no-plugin-dirs",
        "--no-cache-dir",
        "--js-runtimes",
        "node:/usr/bin/node",
        "--no-playlist",
        "--socket-timeout",
        "10",
        "--retries",
        "1",
        "--fragment-retries",
        "1",
        "--max-filesize",
        "400M",
        "--no-progress",
    ]
    plugin = os.environ.get("HOUSEOS_RESOLVER_PLUGIN_DIR")
    if plugin:
        base += ["--plugin-dirs", plugin]
    youtube = youtube_request(data)
    if youtube:
        if ROUTE["flag"]:
            base += [ROUTE["flag"]]
        cookie_file = os.environ.get("HOUSEOS_YOUTUBE_COOKIES")
        if cookie_file:
            base += ["--cookies", cookie_file]
        client = os.environ.get("HOUSEOS_YOUTUBE_CLIENT")
        if client:
            base += ["--extractor-args", "youtube:player_client=" + client]
        token_url = os.environ.get("HOUSEOS_YOUTUBE_POT_URL")
        if token_url:
            base += ["--extractor-args", "youtubepot-bgutilhttp:base_url=" + token_url]
    if data.get("action") in {"web_info", "web_video", "web_stream", "web_remove"}:
        from .fetcher_web import execute as web_execute

        if youtube and data["action"] != "web_remove" and time.monotonic() < YOUTUBE_PAUSE["until"]:
            raise ValueError(YOUTUBE_PAUSE["code"])
        return web_execute(data, [x for x in base if x not in {"--max-filesize", "400M"}])
    if data.get("action") in {"search", "playlist"}:
        if data["action"] == "search":
            query = data.get("query", "")
            if not isinstance(query, str) or not 1 <= len(query) <= 200:
                raise ValueError("INVALID_QUERY")
            maximum = data.get("limit", 5)
            if type(maximum) is not int or not 1 <= maximum <= 50:
                raise ValueError("INVALID_SEARCH_LIMIT")
            target = (
                ("scsearch" if data.get("source") == "soundcloud" else "ytsearch")
                + str(maximum)
                + ":"
                + query
            )
        else:
            from .music import playlist_source

            target = playlist_source(data.get("source_url", ""))
            maximum = 50
            start = data.get("start", 1)
            if type(start) is not int or not 1 <= start <= 5000:
                raise ValueError("INVALID_PLAYLIST_START")
        args = [x for x in base if x != "--no-playlist"]
        if youtube and time.monotonic() < YOUTUBE_PAUSE["until"]:
            raise ValueError(YOUTUBE_PAUSE["code"])
        info = json.loads(
            bounded_process(
                args
                + [
                    "--flat-playlist",
                    *(["--playlist-start", str(start)] if data["action"] == "playlist" else []),
                    "--playlist-end",
                    str((start if data["action"] == "playlist" else 1) + maximum - 1),
                    "--dump-single-json",
                    "--skip-download",
                    "--",
                    target,
                ],
                45,
            )
        )
        entries, gone = [], 0
        for entry in (info.get("entries") or [])[:maximum]:
            # YouTube keeps removed and private videos in a playlist under these names.
            if entry.get("availability") in {"private", "needs_auth", "subscriber_only"} or str(
                entry.get("title") or ""
            ).lower() in {"[deleted video]", "[private video]"}:
                gone += 1
                continue
            try:
                url = canonical_source(entry.get("webpage_url") or entry.get("url", ""))
            except Exception:
                continue
            entries.append(
                {
                    "source_url": url,
                    # A missing title is None, not absent: never the word "None".
                    "title": str(entry.get("title") or "Resolving source…")[:500],
                    "duration": entry.get("duration"),
                    "uploader": str(entry.get("uploader") or "")[:200],
                    "thumbnail": thumbnail_of(entry),
                }
            )
        return {
            "status": "completed",
            "items": entries,
            "unavailable": gone,
            "limit": maximum,
            "total": info.get("playlist_count"),
        }
    if data.get("action") in {"cancel_download", "live_stop", "live_renew", "live_status"}:
        from .fetcher_live import execute as live_execute

        return live_execute(ROOT, data["action"], data["item_id"])
    url = canonical_source(data.get("source_url", ""))
    if url.startswith("radio:"):
        from .radio import resolve, cached_station, icy_title, require_public

        if data.get("action") == "radio_title":  # every 30 s while playing: cache the directory
            station = cached_station(url[6:], int(time.time() // 3600))
            require_public(station["url"])
            return {"status": "completed", "title": icy_title(station["url"], station["name"])}
        station = resolve(url[6:])
        require_public(station["url"])
        if data.get("action") == "metadata":
            return {
                "status": "needs_confirmation",
                "code": "LIVE_STREAM_REQUIRES_APPROVAL",
                "is_live": True,
                "title": station["name"],
                "uploader": " · ".join(filter(None, ("Radio Browser", station["country"]))),
                "thumbnail": station.get("favicon"),
                "tags": [t.strip()[:60] for t in station.get("tags", "").split(",") if t.strip()][:15],
            }
        if data.get("action") != "live_start":
            raise ValueError("UNSUPPORTED_FETCH_ACTION")
        from .fetcher_live import execute as live_execute

        args = [
            "/usr/bin/ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-rw_timeout",
            "15000000",
            "-protocol_whitelist",
            "http,https,tcp,tls,crypto",
            "-i",
            station["url"],
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            "-f",
            "mp3",
            "pipe:1",
        ]
        return live_execute(ROOT, "live_start", data["item_id"], args)
    if data.get("action") == "live_start":
        from .fetcher_live import execute as live_execute

        args = base + ["--match-filter", "is_live", "-f", "bestaudio", "-o", "-", "--", url]
        return live_execute(ROOT, "live_start", data["item_id"], args)
    if data.get("action") == "long_start":
        # An hours-long track plays through the same owned pipe as live radio: yt-dlp's own
        # transfer (no direct-URL relay), nothing kept on disk, no seeking.
        from .fetcher_live import execute as live_execute

        if youtube and time.monotonic() < YOUTUBE_PAUSE["until"]:
            raise ValueError(YOUTUBE_PAUSE["code"])
        args = base + [
            "--match-filter",
            "!is_live & duration < 14400",
            "-f",
            "bestaudio/best",
            "-o",
            "-",
            "--",
            url,
        ]
        return live_execute(ROOT, "live_start", data["item_id"], args)
    if data.get("action") == "metadata":
        _, info = resolve_info(url, base)
        if info.get("is_live"):
            return {
                "status": "needs_confirmation",
                "code": "LIVE_STREAM_REQUIRES_APPROVAL",
                "is_live": True,
                "title": str(info.get("title", "Live stream"))[:500],
                "uploader": str(info.get("uploader", ""))[:200],
                "thumbnail": thumbnail_of(info),
            }
        return {
            "status": "completed",
            "title": str(info.get("title", "Unknown title"))[:500],
            "uploader": str(info.get("uploader", ""))[:200],
            "duration": info.get("duration"),
            "source_url": url,
            "thumbnail": thumbnail_of(info),
            # Only for the genre and artist guess; never shown raw.
            "artist": str(info.get("artist") or info.get("creator") or "")[:200],
            "genre": str(info.get("genre") or "")[:80],
            "tags": [str(t)[:60] for t in (info.get("tags") or [])[:30]],
        }
    if data.get("action") == "download":
        import shutil

        item = str(UUID(data["item_id"]))
        cancelled = ROOT / (item + ".cancelled")
        complete = False
        try:
            with source_lock(url):
                if shutil.disk_usage(ROOT).free < 2 * 1024**3 or cached_audio_bytes() > 10 * 1024**3:
                    raise ValueError("AUDIO_CACHE_FULL")
                target = ROOT / (item + ".media")
                if cancelled.exists():
                    raise ValueError("DOWNLOAD_CANCELLED")
                previous = COMPLETED.get(url)
                if previous:
                    reused = execute({"action": "reuse", "cached_item_id": previous, "item_id": item})
                    if reused["status"] == "completed":
                        complete = True
                        return reused
                ticket, _ = resolve_info(url, base)
                for attempt in range(2):
                    try:
                        bounded_process(
                            base
                            + [
                                "--match-filter",
                                "!is_live & duration < 14400",
                                "-f",
                                "bestaudio/best",
                                "--load-info-json",
                                str(ticket),
                                "-o",
                                str(target),
                            ],
                            300,
                            65536,
                            cancelled=cancelled.exists,
                        )
                        break
                    except ValueError as error:
                        if str(error) != "SOURCE_URL_EXPIRED" or attempt:
                            raise
                        ticket, _ = resolve_info(url, base, refresh=True)
                if not target.is_file() or target.stat().st_size > 400 * 1024 * 1024:
                    raise ValueError("AUDIO_DOWNLOAD_LIMIT")
                if cancelled.exists():
                    raise ValueError("DOWNLOAD_CANCELLED")
                os.chmod(target, 0o640)
                COMPLETED[url] = item
                if len(COMPLETED) > 128:
                    COMPLETED.pop(next(iter(COMPLETED)))
                complete = True
                return {"status": "completed", "bytes": target.stat().st_size}
        finally:
            cleanup_download(item, complete=complete and not cancelled.exists())
            cancelled.unlink(missing_ok=True)
    raise ValueError("UNSUPPORTED_FETCH_ACTION")


def thumbnail_of(info):
    """A public HTTPS artwork URL from yt-dlp data, if any (served later through a proxy)."""
    candidates = [info.get("thumbnail")] + [
        t.get("url") for t in reversed(info.get("thumbnails") or []) if isinstance(t, dict)
    ]
    for url in candidates:
        if isinstance(url, str) and url.startswith("https://") and len(url) <= 1000:
            return url
    return None


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        try:
            line = self.rfile.readline(8193)
            if len(line) > 8192:
                raise ValueError()
            data = json.loads(line)
            if data.get("action") in {
                "cancel_download",
                "live_stop",
                "live_renew",
                "live_status",
                "live_start",
                "long_start",
                "reuse",
                "cache_prune",
                "web_remove",
            }:
                result = run(data)
            elif data.get("action") == "games_link":
                if not GAME_LINKS.acquire(blocking=False):
                    result = {"status": "failed", "code": "SOURCE_BUSY"}
                else:
                    try:
                        result = run(data)
                    finally:
                        GAME_LINKS.release()
            elif str(data.get("action")).startswith("games_"):
                # A cover waits a moment at most (the page shows the drawn box); lists and emulators wait.
                if not GAMES.acquire(timeout=3 if data.get("action") == "games_art" else 120):
                    result = {"status": "failed", "code": "SOURCE_BUSY"}
                else:
                    try:
                        result = run(data)
                    finally:
                        GAMES.release()
            elif data.get("action") in {"web_video", "web_stream"}:
                if not WEB_VIDEO.acquire(blocking=False):
                    result = {"status": "failed", "code": "SOURCE_BUSY"}
                else:
                    try:
                        result = run(data)
                    finally:
                        WEB_VIDEO.release()
            elif not SLOW_REQUESTS.acquire(blocking=False):
                result = {"status": "failed", "code": "SOURCE_BUSY"}
            else:
                try:
                    result = run(data)
                finally:
                    SLOW_REQUESTS.release()
        except Exception as exc:
            known = {
                "DOWNLOAD_CANCELLED",
                "STREAM_FORMAT_UNSUPPORTED",
                "STREAM_LEASE_ENDED",
                "SOURCE_BUSY",
                "SOURCE_EXPIRED",
                "SOURCE_RANGE_UNSUPPORTED",
                "YOUTUBE_SIGN_IN_REQUIRED",
                "YOUTUBE_RATE_LIMITED",
                "SOURCE_UNAVAILABLE",
                "SOURCE_REMOVED",
                "PLAYLIST_NOT_FOUND",
                "SOURCE_REGION_BLOCKED",
                "YOUTUBE_AGE_RESTRICTED",
                "SOURCE_URL_EXPIRED",
                "SOURCE_RESPONSE_TOO_LARGE",
                "SOURCE_TIMEOUT",
                "AUDIO_CACHE_FULL",
                "AUDIO_DOWNLOAD_LIMIT",
                "UNSUPPORTED_FETCH_ACTION",
                "INVALID_QUERY",
                "SOURCE_LINK_UNRESOLVED",
                "UNSAFE_SOURCE",
                "PAGE_UNSUPPORTED",
                "IMAGE_UNSUPPORTED",
                "WEB_VIDEO_LINK_INVALID",
                "WEB_VIDEO_PLAYLIST",
                "WEB_VIDEO_LIVE",
                "WEB_VIDEO_TOO_LONG",
                "WEB_VIDEO_TOO_BIG",
                "WEB_VIDEO_NO_SPACE",
                "GAME_NO_SPACE",
                "GAME_LINK_PAGE",
                "WEB_VIDEO_DRM",
                "WEB_VIDEO_UNSUPPORTED",
                "WEB_VIDEO_SIGN_IN",
                "WEB_VIDEO_NOT_FOUND",
                "WEB_VIDEO_NOT_STREAMABLE",
            }
            code = str(exc) if isinstance(exc, ValueError) and str(exc) in known else "SOURCE_UNAVAILABLE"
            if code == "SOURCE_UNAVAILABLE" and not isinstance(exc, ValueError):
                print("fetch error:", type(exc).__name__, flush=True)
            if (
                code in {"YOUTUBE_SIGN_IN_REQUIRED", "YOUTUBE_RATE_LIMITED"}
                and time.monotonic() >= YOUTUBE_PAUSE["until"]
            ):
                YOUTUBE_PAUSE.update(until=time.monotonic() + 300, code=code)
            result = {"status": "failed", "code": code}
        self.wfile.write(json.dumps(result).encode() + b"\n")


def main():
    from .events import restart_on_request

    restart_on_request("fetch")
    if not settings.external_fetch_enabled:
        raise SystemExit("Fetcher disabled until sandbox verification")
    ROOT.mkdir(exist_ok=True)
    # No transfers survive this process: remove only UUID-scoped partial/control files.
    for path in ROOT.iterdir():
        identity, separator, suffix = path.name.partition(".")
        try:
            UUID(identity)
        except ValueError:
            continue
        # Pipes and leases of streams from a previous run can never be read again.
        pipe = suffix == "media" and path.is_fifo()
        if separator and (suffix.startswith("media.") or suffix in {"cancelled", "live.json"} or pipe):
            path.unlink(missing_ok=True)
    from .fetcher_web import startup as web_startup

    web_startup()
    if SOCKET.exists():
        SOCKET.unlink()
    os.umask(0o007)
    with socketserver.ThreadingUnixStreamServer(str(SOCKET), Handler) as server:
        server.daemon_threads = True
        os.chmod(SOCKET, 0o660)
        server.serve_forever()


if __name__ == "__main__":
    main()
