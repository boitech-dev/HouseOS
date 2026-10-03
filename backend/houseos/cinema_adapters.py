"""Private media integrations. Responses returned to callers are normalized, never raw URLs."""

from __future__ import annotations
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit
import httpx
from .playback import MediaError, inspect_probe

MAX_JSON = 4_000_000


def public_url(url: str):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise MediaError(
            "UNSAFE_SOURCE", "The source address is not an allowed public HTTPS address.", "resolve"
        )
    try:
        addresses = {r[4][0] for r in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise MediaError(
            "PROVIDER_UNAVAILABLE", "The provider address could not be resolved.", "resolve", True
        ) from None
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise MediaError(
            "UNSAFE_SOURCE", "The source address resolves outside the public network.", "resolve"
        )
    # IPv4 first: many homes and Docker networks have no working IPv6 route, and a text sort
    # put IPv6 first, so every fetch failed or waited out its timeout there.
    return parsed, sorted(addresses, key=lambda address: (":" in address, address))[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=15, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def public_fetch(url: str, *, limit: int = MAX_JSON, range_end: int | None = None):
    """Validate every redirect, then connect to that checked address (no second DNS lookup)."""
    for _ in range(4):
        parsed, address = public_url(url)
        connection = PinnedHTTPS(parsed.hostname, address)
        try:
            headers = {"User-Agent": "HouseOS/1", "Accept-Encoding": "identity"}
            if range_end is not None:
                headers["Range"] = f"bytes=0-{range_end}"
            connection.request(
                "GET", parsed.path + ("?" + parsed.query if parsed.query else ""), headers=headers
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if response.status not in {200, 206}:
                raise MediaError("SOURCE_NOT_READY", "The media source is not available.", "resolve", True)
            content = response.read(limit + 1)
            if len(content) > limit:
                raise MediaError(
                    "PROBE_BUDGET_EXCEEDED", "The response exceeds the authorized byte budget.", "probe"
                )
            return content, {k.lower(): v for k, v in response.getheaders()}
        except (OSError, http.client.HTTPException):
            raise MediaError(
                "PROVIDER_UNAVAILABLE", "The provider request failed or timed out.", "resolve", True
            ) from None
        finally:
            connection.close()
    raise MediaError("UNSAFE_SOURCE", "The provider exceeded the redirect limit.", "resolve")


def public_json(url):
    raw, _ = public_fetch(url)
    try:
        return json.loads(raw)
    except ValueError:
        raise MediaError(
            "PROVIDER_UNAVAILABLE", "The provider returned an invalid response.", "discover"
        ) from None


def internal_base(config, default):
    from .integrations import endpoint_url

    try:
        return endpoint_url(config.get("base_url", default), resolve=True)
    except ValueError as error:
        raise MediaError("INTEGRATION_CONFIG_INVALID", str(error), "setup") from None


class DebridError(MediaError):
    """Only safe numeric diagnostics from a definitive upstream rejection."""

    def __init__(self, provider_code, http_status, operation):
        table = {
            6: (
                "DEBRID_RESOURCE_UNREACHABLE",
                "The debrid service could not reach this resource. Retry the same selected source.",
                True,
            ),
            7: ("SOURCE_UNAVAILABLE", "The debrid service could not find this resource.", False),
            16: ("SOURCE_UNSUPPORTED", "The debrid service does not support this hoster.", False),
            17: ("DEBRID_HOSTER_MAINTENANCE", "The source hoster is under maintenance.", True),
            19: ("DEBRID_HOSTER_UNAVAILABLE", "The source hoster is temporarily unavailable.", True),
            24: ("SOURCE_UNAVAILABLE", "The debrid service reports this file unavailable.", False),
            25: ("DEBRID_SERVICE_UNAVAILABLE", "The debrid service is temporarily unavailable.", True),
            28: ("SOURCE_REJECTED", "The debrid service does not allow this file.", False),
            30: ("SOURCE_INVALID", "The debrid service rejected this torrent as invalid.", False),
            35: ("SOURCE_REJECTED", "The debrid service blocked this file.", False),
            37: ("DEBRID_ENDPOINT_DISABLED", "The debrid service disabled this API endpoint.", False),
            31: (
                "ACCOUNT_ACTION_UNCERTAIN",
                "The debrid service reports this action already done; reconcile inventory.",
                False,
            ),
            33: (
                "ACCOUNT_ACTION_UNCERTAIN",
                "The debrid service reports this torrent already active; reconcile inventory.",
                False,
            ),
        }
        default = (
            "DEBRID_REQUEST_REJECTED",
            "The debrid service rejected this request; inspect the numeric provider error.",
            False,
        )
        if provider_code in {8, 9, 10, 11, 12, 13, 14, 15}:
            default = (
                "DEBRID_AUTH_EXPIRED",
                "The debrid service requires account reconnection or authorization.",
                False,
            )
        elif provider_code in {18, 20, 21, 22, 23, 26, 29, 36}:
            default = (
                "DEBRID_ACCOUNT_LIMIT",
                "The debrid service reports an account, traffic, IP, size or active-download limit.",
                False,
            )
        elif provider_code in {5, 34}:
            default = (
                "DEBRID_RATE_LIMIT",
                "The debrid service requested a pause before further requests.",
                True,
            )
        if provider_code is None:
            if http_status in {401, 403}:
                default = (
                    "DEBRID_AUTH_EXPIRED",
                    "The debrid service requires account reconnection or authorization.",
                    False,
                )
            elif http_status == 429:
                default = (
                    "DEBRID_RATE_LIMIT",
                    "The debrid service requested a pause before further requests.",
                    True,
                )
            elif http_status >= 500:
                default = (
                    "ACCOUNT_ACTION_UNCERTAIN",
                    "The debrid service returned an invalid server error; account action outcome is unknown.",
                    False,
                )
        code, message, retry = table.get(provider_code, default)
        if provider_code in {28, 35}:
            stage = {
                "add_magnet": "adding this torrent",
                "select_files": "selecting this file",
                "torrent_info": "reading this torrent",
                "unrestrict_link": "creating the playable link",
            }.get(operation, "processing this request")
            message = f"The debrid service rejected {stage} (provider code {provider_code}). It did not provide a more specific reason. Try another release."
        super().__init__(code, message, "resolve", retry)
        self.provider_code, self.http_status, self.operation = provider_code, http_status, operation

    def public(self):
        return {
            **super().public(),
            "provider_code": self.provider_code,
            "http_status": self.http_status,
            "operation": self.operation,
        }


def debrid_not_ready(info):
    state = info.get("status", "unknown")
    code, message = {
        "magnet_conversion": (
            "SOURCE_METADATA_PENDING",
            "The debrid service is retrieving torrent metadata; retry this same source shortly.",
        ),
        "waiting_files_selection": (
            "SOURCE_SELECTION_REQUIRED",
            "The exact media file has not been selected in the debrid service.",
        ),
        "queued": (
            "SOURCE_DOWNLOADING",
            "The debrid service queued this source; it is not ready for streaming yet.",
        ),
        "downloading": (
            "SOURCE_DOWNLOADING",
            "The debrid service is downloading this source; it is not ready for streaming yet.",
        ),
        "compressing": ("SOURCE_PREPARING", "The debrid service is preparing the selected file."),
        "uploading": ("SOURCE_PREPARING", "The debrid service is preparing the selected file."),
        "magnet_error": ("SOURCE_FAILED", "The debrid service could not retrieve this torrent metadata."),
        "error": ("SOURCE_FAILED", "The debrid service reports that this torrent failed."),
        "virus": ("SOURCE_REJECTED", "The debrid service rejected this torrent as unsafe."),
        "dead": ("SOURCE_UNAVAILABLE", "The debrid service reports this torrent is no longer available."),
    }.get(state, ("SOURCE_NOT_READY", "The debrid service has not finished preparing this source."))
    error = MediaError(
        code,
        message,
        "resolve",
        state in {"magnet_conversion", "queued", "downloading", "compressing", "uploading"},
    )
    error.rd_status = (
        state
        if state
        in {
            "magnet_conversion",
            "waiting_files_selection",
            "queued",
            "downloading",
            "compressing",
            "uploading",
            "magnet_error",
            "error",
            "virus",
            "dead",
        }
        else "unknown"
    )
    progress = info.get("progress")
    error.rd_progress = max(0, min(100, progress)) if type(progress) in {int, float} else None
    return error


def private_json(base, path, *, headers=None, method="GET", params=None, payload=None, form=None, timeout=15):
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                method, base + path, headers=headers, params=params, json=payload, data=form
            ) as response:
                if response.status_code >= 400 and base.startswith("https://api.real-debrid.com/"):
                    error_body = bytearray()
                    for chunk in response.iter_bytes():
                        error_body.extend(chunk)
                        if len(error_body) > 8000:
                            break
                    try:
                        code = json.loads(error_body).get("error_code")
                    except (ValueError, AttributeError):
                        code = None
                    operation = (
                        "add_magnet"
                        if path == "/torrents/addMagnet"
                        else "select_files"
                        if path.startswith("/torrents/selectFiles/")
                        else "torrent_info"
                        if path.startswith("/torrents/info/")
                        else "unrestrict_link"
                        if path == "/unrestrict/link"
                        else "account_request"
                    )
                    raise DebridError(code if type(code) is int else None, response.status_code, operation)
                if response.status_code in {401, 403}:
                    raise MediaError(
                        "INTEGRATION_AUTH_EXPIRED",
                        "The integration needs reconnection by an administrator.",
                        "resolve",
                    )
                if response.status_code == 429:
                    raise MediaError(
                        "PROVIDER_RATE_LIMIT",
                        "The provider rate limit was reached. Try later.",
                        "resolve",
                        True,
                    )
                if response.status_code >= 300:
                    raise MediaError(
                        "PROVIDER_UNAVAILABLE",
                        "The configured integration rejected the request.",
                        "resolve",
                        True,
                    )
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_JSON:
                        raise MediaError(
                            "PROBE_BUDGET_EXCEEDED", "The integration response is too large.", "resolve"
                        )
                return json.loads(content) if content else {}

    except (httpx.HTTPError, ValueError) as error:
        from .integrations import bad_certificate

        if bad_certificate(error):
            raise MediaError(
                "INTEGRATION_CONFIG_INVALID",
                "This service's certificate isn't valid for this address: use the name on its "
                "certificate, or its http:// address on your network.",
                "setup",
            ) from None
        raise MediaError(
            "PROVIDER_UNAVAILABLE", "The integration failed or returned invalid data.", "resolve", True
        ) from None


@lru_cache(maxsize=128)
def cinemeta_json(path, freshness_bucket):
    # Bounded public metadata cache; no credentials or user state, refresh every 15 min.
    return public_json("https://v3-cinemeta.strem.io" + path)


class Cinemeta:
    base = "https://v3-cinemeta.strem.io"

    def get(self, path):
        return cinemeta_json(path, int(time.time() // 900))

    def catalogs(self, kind):
        manifest = self.get("/manifest.json")
        return [
            {
                "id": row["id"],
                "name": str(row.get("name", row["id"]))[:80],
                "genres": [str(v)[:40] for v in row.get("genres", [])[:150]],
            }
            for row in manifest.get("catalogs", [])[:30]
            if row.get("type") == kind and row.get("id") in {"top", "year", "imdbRating"}
        ]

    def browse(self, kind="movie", catalog="top", genre="", offset=0):
        entry = next((v for v in self.catalogs(kind) if v["id"] == catalog), None)
        if entry and genre:
            # Human genre names map deterministically to the manifest's exact spelling.
            key = "".join(c for c in genre.casefold() if c.isalnum())
            aliases = {
                "sciencefiction": "scifi",
                "sciencefictionmovies": "scifi",
                "animated": "animation",
                "animatedmovies": "animation",
                "documentaries": "documentary",
                "romantic": "romance",
            }
            key = aliases.get(key, key)
            genre = next(
                (g for g in entry["genres"] if "".join(c for c in g.casefold() if c.isalnum()) == key), genre
            )
        if not entry or (genre and genre not in entry["genres"]) or (catalog == "year" and not genre):
            raise MediaError(
                "CATALOG_FILTER_INVALID", "Choose a supported catalog and genre or year.", "identify"
            )
        extras = [("genre", genre)] if genre else []
        extras.append(("skip", str(offset)))
        body = self.get(f"/catalog/{kind}/{catalog}/" + urlencode(extras, quote_via=quote) + ".json")
        raw = [m for m in body.get("metas", [])[:100] if str(m.get("id", "")).startswith("tt")]
        return {
            "items": [self.normalize(m) for m in raw[:24]],
            "next_offset": offset + 24 if len(raw) > 24 else None,
        }

    def search(self, query, kind="movie"):
        body = self.get(f"/catalog/{kind}/top/search={quote(query, safe='')}.json")
        return [
            self.normalize(m) for m in body.get("metas", [])[:20] if str(m.get("id", "")).startswith("tt")
        ]

    def details(self, identity, kind):
        body = self.get(f"/meta/{kind}/{quote(identity, safe='')}.json")
        item = body.get("meta")
        if not item:
            raise MediaError("METADATA_NOT_FOUND", "This title could not be identified.", "identify")
        result = self.normalize(item)
        result["episodes"] = [
            {
                "id": e.get("id"),
                "title": str(e.get("title", ""))[:200],
                "season": e.get("season"),
                "episode": e.get("episode"),
                "released": e.get("released"),
            }
            for e in item.get("videos", [])[:1000]
        ]
        return result

    @staticmethod
    def normalize(item):
        return {
            "canonical_id": str(item["id"]),
            "title": str(item.get("name", "Untitled"))[:240],
            "kind": item.get("type", "movie"),
            "year": str(item.get("releaseInfo", ""))[:16],
            "description": str(item.get("description", ""))[:2000],
            "_poster_url": str(item.get("poster", ""))[:2000],
            "genres": [str(v)[:40] for v in item.get("genres", [])[:15]],
            "rating": str(item.get("imdbRating") or "")[:5],
            "cast": [str(v)[:80] for v in (item.get("cast") or [])[:5]],
            "director": [str(v)[:80] for v in (item.get("director") or [])[:2]],
            "runtime": str(item.get("runtime") or "")[:16],
        }


class Comet:
    def __init__(self, config):
        if not config.get("enabled"):
            raise MediaError(
                "PROVIDER_UNCONFIGURED",
                "An administrator must configure the private source provider.",
                "setup",
            )
        self.base = internal_base(config, "http://127.0.0.1:8767")
        # Direct RD topology: no RD key is ever sent to Comet.
        self.config = config

    def manifest(self):
        manifest = private_json(self.base, "/manifest.json")
        resources = [r if isinstance(r, str) else r.get("name") for r in manifest.get("resources", [])]
        if "stream" not in resources:
            raise MediaError(
                "PROVIDER_CAPABILITY_MISSING",
                "The configured provider has no stream-discovery capability.",
                "discover",
            )
        return {"id": manifest.get("id"), "resources": resources}

    def streams(self, canonical_id, kind, season=None, episode=None):
        identity = canonical_id if kind == "movie" else f"{canonical_id}:{season}:{episode}"
        self.manifest()
        raw = private_json(self.base, f"/stream/{kind}/{quote(identity, safe=':')}.json", timeout=30)
        entries = raw.get("streams", [])[:1000]
        result = []
        for entry in entries:
            info_hash = str(entry.get("infoHash", "")).lower()
            # HTTP-only provider flows can smuggle credentials to upstream services.
            # Accept torrent identity only; HouseOS calls official RD itself.
            if len(info_hash) != 40 or any(c not in "0123456789abcdef" for c in info_hash):
                continue
            description = str(
                entry.get("description") or entry.get("title") or entry.get("name") or "Source"
            )[:2000]
            quality = re.search(
                r"(?<!\d)(4320|2160|1080|720|480)[pP]\b", str(entry.get("name", "")) + " " + description
            )
            seeds = re.search(r"👤\s*(\d{1,8})", description)
            result.append(
                {
                    "info_hash": info_hash,
                    "file_index": entry.get("fileIdx"),
                    "release": description[:300],
                    "size": entry.get("behaviorHints", {}).get("videoSize"),
                    "height_claim": int(quality.group(1)) if quality else None,
                    "seeders_claim": int(seeds.group(1)) if seeds else None,
                    "evidence": "provider_claim",
                    "state": "discovered",
                }
            )
        # Bound retained discovery without dropping every lower-resolution option
        # when a provider sorts hundreds of 4K releases first.
        buckets = {}
        seen = set()
        for source in result:
            if source["info_hash"] not in seen:
                seen.add(source["info_hash"])
                buckets.setdefault(source["height_claim"] or 0, []).append(source)
        selected = []
        for index in range(100):
            for bucket in buckets.values():
                if index < len(bucket):
                    selected.append(bucket[index])
                    if len(selected) == 100:
                        return selected
        return selected


def exact_movie_file(files, title, year):
    """Match the requested film inside packs; provider file indexes are not debrid ids."""

    def words(value):
        value = unicodedata.normalize("NFKD", value).casefold()
        return re.findall(r"[^\W_]+", "".join(c for c in value if not unicodedata.combining(c)))

    viable = [
        file
        for file in files
        if Path(str(file.get("path", ""))).suffix.lower() in {".mkv", ".mp4", ".m4v", ".webm"}
        and not {"sample", "trailer"}.intersection(words(Path(str(file.get("path", ""))).stem))
    ]
    wanted = words(title)
    matches = []
    for file in viable:
        tokens = words(Path(str(file.get("path", ""))).stem)
        if wanted and tokens[: len(wanted)] == wanted:
            remainder = tokens[len(wanted) :]
            if year and remainder and remainder[0] == str(year):
                matches.append(file)
    if len(matches) == 1:
        return matches[0]
    if len(viable) == 1:
        # Existing single-film releases can have opaque filenames. An explicit
        # conflicting year still must not select a remake or mislabeled film.
        tokens = words(Path(str(viable[0].get("path", ""))).stem)
        years = [token for token in tokens[len(wanted) :] if re.fullmatch(r"(?:19|20)\d{2}", token)]
        if not years or not year or str(year) in years:
            return viable[0]
    raise MediaError(
        "EPISODE_AMBIGUOUS",
        "The requested movie could not be uniquely matched to a file in this release. Choose another version.",
        "identify",
    )


class RealDebrid:
    base = "https://api.real-debrid.com/rest/1.0"

    def __init__(self, config):
        self.token = config.get("token") or config.get("api_key")
        if not config.get("enabled") or not self.token:
            raise MediaError(
                "DEBRID_UNCONFIGURED", "An administrator must connect the debrid service.", "setup"
            )
        if not config.get("entitlement_confirmed"):
            raise MediaError(
                "DEBRID_ENTITLEMENT_REQUIRED",
                "Confirm permitted account use before enabling household debrid playback.",
                "setup",
            )

    def call(self, method, path, form=None, params=None):
        rd_rate_limit()
        try:
            return private_json(
                self.base,
                path,
                method=method,
                headers={"Authorization": f"Bearer {self.token}"},
                form=form,
                params=params,
            )
        except MediaError as exc:
            if exc.code == "INTEGRATION_AUTH_EXPIRED":
                raise MediaError(
                    "DEBRID_AUTH_EXPIRED",
                    "The debrid service's authentication expired or this account cannot perform the operation.",
                    "resolve",
                ) from None
            raise

    def account(self):
        raw = self.call("GET", "/user")
        return {
            "type": raw.get("type"),
            "expiration": raw.get("expiration"),
            "premium_seconds": raw.get("premium"),
        }

    def inventory(self):
        return self.call("GET", "/torrents", params={"limit": 500})

    def info(self, torrent_id):
        return self.call("GET", "/torrents/info/" + quote(torrent_id, safe=""))

    def add(self, info_hash, *, check=None):
        for attempt in range(2):
            if check:
                check()
            try:
                return self.call(
                    "POST", "/torrents/addMagnet", form={"magnet": "magnet:?xt=urn:btih:" + info_hash}
                )["id"]
            except DebridError as exc:
                if attempt or exc.provider_code not in {6, 25}:
                    raise
                time.sleep(0.5)  # only definitive rejected requests; never timeout/unknown adds

    def select(self, torrent_id, file_id):
        return self.call(
            "POST", "/torrents/selectFiles/" + quote(torrent_id, safe=""), form={"files": str(file_id)}
        )

    def resolve(self, torrent_id, file_id, *, wait_seconds=0, check=None, selection_pending=False):
        deadline = time.monotonic() + min(max(wait_seconds, 0), 8)
        info = self.info(torrent_id)
        pending = {"magnet_conversion", "queued", "downloading", "compressing", "uploading"}
        if selection_pending:
            pending.add("waiting_files_selection")
        while info.get("status") in pending and time.monotonic() < deadline:
            if check:
                check()
            time.sleep(0.5)
            info = self.info(torrent_id)
        if info.get("status") != "downloaded":
            raise debrid_not_ready(info)
        selected = [f for f in info.get("files", []) if f.get("selected")]
        links = info.get("links", [])
        if len(selected) != len(links):
            raise MediaError(
                "EPISODE_AMBIGUOUS",
                "The debrid service's file-to-link correspondence is ambiguous.",
                "resolve",
            )
        index = next((i for i, file in enumerate(selected) if str(file["id"]) == str(file_id)), None)
        if index is None:
            raise MediaError(
                "EPISODE_MISMATCH", "The selected episode/file is absent from this source.", "resolve"
            )
        raw = self.call("POST", "/unrestrict/link", form={"link": links[index]})
        if not raw.get("download"):
            raise MediaError(
                "STREAM_RESOLUTION_FAILED", "The debrid service did not return a usable stream.", "resolve"
            )
        public_url(raw["download"])
        return raw["download"], raw.get("filesize")


class Jellyfin:
    def __init__(self, config):
        key = config.get("api_key") or config.get("token")
        self.user = config.get("user_id")
        if not config.get("enabled") or not key or not self.user:  # before the address: unset is not invalid
            raise MediaError(
                "JELLYFIN_UNCONFIGURED", "Configure a restricted Jellyfin library identity first.", "setup"
            )
        self.base = internal_base(config, "http://127.0.0.1:8096")
        self.headers = {
            "Authorization": 'MediaBrowser Client="HouseOS", Device="HouseOS Server", DeviceId="houseos-server-v1", Version="1.0", Token="'
            + key
            + '"',
            "X-Emby-Token": key,  # Emby ignores the MediaBrowser header
        }
        self.config = config

    def call(self, method, path, params=None, payload=None):
        return private_json(
            self.base, path, method=method, headers=self.headers, params=params, payload=payload
        )

    def search(self, query):
        return self.call(
            "GET",
            f"/Users/{quote(self.user, safe='')}/Items",
            params={
                "SearchTerm": query,
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
                "Fields": "ProviderIds,Overview,MediaSources",
                "Limit": 20,
            },
        ).get("Items", [])

    def library(self, kind, offset=0, limit=30):
        return self.call(
            "GET",
            f"/Users/{quote(self.user, safe='')}/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": "Series" if kind == "series" else "Movie",
                "Fields": "ProviderIds,Overview,Path",
                "SortBy": "SortName",
                "SortOrder": "Ascending",
                "StartIndex": offset,
                "Limit": limit,
            },
        )

    def item(self, item_id):
        return self.call("GET", f"/Users/{quote(self.user, safe='')}/Items/{quote(item_id, safe='')}")

    def episodes(self, item_id):
        return self.call(
            "GET",
            f"/Shows/{quote(item_id, safe='')}/Episodes",
            params={"UserId": self.user, "Fields": "ProviderIds,MediaSources", "Limit": 1000},
        ).get("Items", [])

    def playback_info(self, item_id):
        return self.call(
            "GET", f"/Items/{quote(item_id, safe='')}/PlaybackInfo", params={"UserId": self.user}
        )

    def sessions(self):
        return self.call("GET", "/Sessions", params={"ControllableByUserId": self.user})

    def play(self, session_id, item_id, position, audio_index=None, subtitle_index=-1, media_source_id=None):
        args = {
            "ItemIds": item_id,
            "PlayCommand": "PlayNow",
            "StartPositionTicks": round(position * 10_000_000),
            "SubtitleStreamIndex": subtitle_index,
        }
        if media_source_id is not None:
            args["MediaSourceId"] = media_source_id
        if audio_index is not None:
            args["AudioStreamIndex"] = int(audio_index)
        self.call("POST", f"/Sessions/{quote(session_id, safe='')}/Playing", params=args)

    def stream(self, item_id, source_id, byte_range=None, *, head=False):
        """Authenticated exact-library-source bytes; token never appears in a URL."""
        import re

        if byte_range and not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", byte_range):
            raise MediaError("INVALID_RANGE", "Only one valid byte range is supported.", "delivery")
        headers = {**self.headers, "Accept-Encoding": "identity"}
        if byte_range:
            headers["Range"] = byte_range
        client = httpx.Client(timeout=httpx.Timeout(10, connect=3), follow_redirects=False, trust_env=False)
        try:
            request = client.build_request(
                "HEAD" if head else "GET",
                self.base + "/Videos/" + quote(item_id, safe="") + "/stream",
                params={"Static": "true", "MediaSourceId": source_id},
                headers=headers,
            )
            response = client.send(request, stream=True)
            if response.status_code not in {200, 206, 416}:
                response.close()
                raise MediaError(
                    "JELLYFIN_SOURCE_UNAVAILABLE",
                    "The restricted Jellyfin identity cannot stream this exact library source.",
                    "delivery",
                    True,
                )
            output_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"content-range", "accept-ranges", "content-length"}
            }

            def chunks():
                try:
                    if not head:
                        yield from response.iter_raw(chunk_size=256 * 1024)
                except httpx.HTTPError:
                    raise MediaError(
                        "SOURCE_INTERRUPTED", "Jellyfin delivery was interrupted.", "delivery", True
                    ) from None
                finally:
                    response.close()
                    client.close()

            return response.status_code, output_headers, chunks()
        except MediaError:
            client.close()
            raise
        except httpx.HTTPError:
            client.close()
            raise MediaError(
                "JELLYFIN_UNAVAILABLE", "The local Jellyfin stream did not respond.", "delivery", True
            ) from None

    def subtitle(self, item_id, source_id, index):
        path = (
            "/Videos/"
            + quote(item_id, safe="")
            + "/"
            + quote(source_id, safe="")
            + "/Subtitles/"
            + str(int(index))
            + "/0/Stream.vtt"
        )
        try:
            with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
                with client.stream("GET", self.base + path, headers=self.headers) as response:
                    if response.status_code != 200:
                        raise MediaError(
                            "SUBTITLE_UNAVAILABLE",
                            "Jellyfin could not normalize the selected subtitle.",
                            "subtitles",
                        )
                    data = bytearray()
                    for block in response.iter_bytes(65536):
                        data.extend(block)
                        if len(data) > 2_000_000:
                            raise MediaError(
                                "SUBTITLE_LIMIT",
                                "The selected subtitle exceeds its preparation limit.",
                                "subtitles",
                            )
                    if not bytes(data).lstrip(b"\xef\xbb\xbf\r\n ").startswith(b"WEBVTT"):
                        raise MediaError(
                            "SUBTITLE_UNAVAILABLE",
                            "Jellyfin returned an unsupported subtitle document.",
                            "subtitles",
                        )
                    return bytes(data)
        except httpx.HTTPError:
            raise MediaError(
                "SUBTITLE_UNAVAILABLE", "Jellyfin subtitle retrieval failed.", "subtitles", True
            ) from None

    def control(self, session_id, command, position=None):
        if command == "volume":
            return self.call(
                "POST",
                f"/Sessions/{quote(session_id, safe='')}/Command",
                payload={"Name": "SetVolume", "Arguments": {"Volume": str(round(position))}},
            )
        mapping = {"pause": "Pause", "resume": "Unpause", "stop": "Stop", "seek": "Seek"}
        self.call(
            "POST",
            f"/Sessions/{quote(session_id, safe='')}/Playing/{mapping[command]}",
            params={"SeekPositionTicks": round(position * 10_000_000)} if command == "seek" else None,
        )


def jellyfin_inspection(source):
    streams = []
    for s in source.get("MediaStreams", []):
        typ = str(s.get("Type", "")).lower()
        stream = {
            "index": s["Index"],
            "codec_type": typ,
            "codec_name": s.get("Codec"),
            "profile": s.get("Profile"),
            "level": s.get("Level"),
            "width": s.get("Width"),
            "height": s.get("Height"),
            "channels": s.get("Channels"),
            "pix_fmt": s.get("PixelFormat"),
            "avg_frame_rate": s.get("RealFrameRate") or s.get("AverageFrameRate"),
            "color_transfer": s.get("ColorTransfer"),
            "tags": {"language": s.get("Language"), "title": s.get("Title")},
            "disposition": {
                "default": s.get("IsDefault"),
                "forced": s.get("IsForced"),
                "hearing_impaired": s.get("IsHearingImpaired"),
                "comment": s.get("IsCommentary"),
            },
        }
        if s.get("DvProfile") is not None:
            stream["side_data_list"] = [
                {"side_data_type": "DOVI configuration record", "dv_profile": s["DvProfile"]}
            ]
        streams.append(stream)
    result = inspect_probe(
        {
            "streams": streams,
            "format": {
                "format_name": {"mkv": "matroska,webm", "mp4": "mov,mp4,m4a,3gp,3g2,mj2"}.get(
                    source.get("Container"), source.get("Container", "")
                ),
                "duration": (source.get("RunTimeTicks") or 0) / 10_000_000,
                "bit_rate": source.get("Bitrate"),
            },
        }
    )
    external_ids = {
        str(stream["Index"])
        for stream in source.get("MediaStreams", [])
        if stream.get("Type") == "Subtitle" and stream.get("IsExternal")
    }
    for track in result["subtitles"]:
        if track["id"] in external_ids:
            track["external_jellyfin"] = True
    result["evidence"] = "jellyfin_media_streams"
    return result


def public_stream(url, byte_range=None, *, head=False):
    """Receiver streaming with pinned checked DNS and bounded per-read buffering."""
    import re

    if byte_range and not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", byte_range):
        raise MediaError("INVALID_RANGE", "Only one valid byte range is supported.", "delivery")
    if url.startswith("torrent:"):  # the torrent player on this computer (resolve_media, D35)
        return torrent_stream(url.removeprefix("torrent:"), byte_range, head=head)
    if url.startswith("local:"):  # a film saved on the house disk (resolve_media)
        from .cinema import saved_path
        from .cinema_delivery import local_stream

        return local_stream(saved_path(url.removeprefix("local:")), byte_range, head=head)
    for _ in range(4):
        parsed, address = public_url(url)
        connection = PinnedHTTPS(parsed.hostname, address)
        try:
            headers = {"Accept-Encoding": "identity", "User-Agent": "HouseOS/1"}
            if byte_range:
                headers["Range"] = byte_range
            connection.request(
                "HEAD" if head else "GET",
                parsed.path + ("?" + parsed.query if parsed.query else ""),
                headers=headers,
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.getheader("Location", ""))
                connection.close()
                continue
            if response.status not in {200, 206, 416}:
                connection.close()
                raise MediaError(
                    "SOURCE_EXPIRED", "The prepared source no longer serves media.", "delivery", True
                )
            output_headers = {
                k: v
                for k, v in response.getheaders()
                if k.lower() in {"content-range", "accept-ranges", "content-length"}
            }

            def chunks():
                try:
                    if not head:
                        while block := response.read(256 * 1024):
                            yield block
                except (OSError, http.client.HTTPException):
                    raise MediaError(
                        "SOURCE_INTERRUPTED", "Source delivery was interrupted.", "delivery", True
                    ) from None
                finally:
                    connection.close()

            return response.status, output_headers, chunks()
        except (OSError, http.client.HTTPException):
            connection.close()
            raise MediaError(
                "SOURCE_EXPIRED", "The prepared media connection failed.", "delivery", True
            ) from None
    raise MediaError("UNSAFE_SOURCE", "The media source exceeded its redirect limit.", "delivery")


# The player kept quiet (D35): no port opened on the router, sharing back capped, memory only.
TORRENT_QUIET = {
    "DisableUPNP": True,
    "UploadRateLimit": 50,  # KB/s: BitTorrent always shares back; kept small
    "ConnectionsLimit": 25,
    "UseDisk": False,
    "RemoveCacheOnDrop": True,
    "EnableDLNA": False,
}


def torrent_auth():
    from .config import settings

    if not settings.torrent_engine_auth:
        return {}
    import base64

    return {"Authorization": "Basic " + base64.b64encode(settings.torrent_engine_auth.encode()).decode()}


def torrent_player_ready():
    """Is the player here? Then set it quiet (native and Docker alike). False when it isn't."""
    import urllib.request

    from .config import settings

    def ask(body):
        request = urllib.request.Request(
            settings.torrent_engine.rstrip("/") + "/settings",
            json.dumps(body).encode(),
            {"Content-Type": "application/json", **torrent_auth()},
        )
        return json.loads(urllib.request.urlopen(request, timeout=5).read() or b"{}")

    try:
        ask({"action": "set", "sets": {**ask({"action": "get"}), **TORRENT_QUIET}})
        return True
    except (OSError, ValueError):
        return False


def torrent_stream(ref, byte_range=None, *, head=False):
    """One file of a torrent, from TorrServer (loopback): it downloads the pieces asked for first,
    so the TV starts before the whole file is here."""
    from .config import settings

    match = re.fullmatch(r"([0-9a-f]{40})/(\d{1,6})", ref)
    if not match:
        raise MediaError("SOURCE_EXPIRED", "This version needs a fresh source list.", "delivery")
    engine = urlsplit(settings.torrent_engine)
    # TorrServer numbers a torrent's files from 1; Stremio add-ons from 0.
    path = f"/stream?link={match[1]}&index={int(match[2]) + 1}&play"
    connection = http.client.HTTPConnection(engine.hostname, engine.port or 80, timeout=60)
    try:
        headers = {"Accept-Encoding": "identity", "User-Agent": "HouseOS/1", **torrent_auth()}
        if byte_range:
            headers["Range"] = byte_range
        connection.request("HEAD" if head else "GET", path, headers=headers)
        response = connection.getresponse()
    except ConnectionRefusedError:
        connection.close()
        raise MediaError(
            "TORRENT_PLAYER_UNAVAILABLE",
            "The torrent player isn't running on this computer.",
            "delivery",
            True,
        ) from None
    except (OSError, http.client.HTTPException):  # a cold torrent still looking for its peers
        connection.close()
        raise MediaError(
            "TORRENT_NO_PEERS", "Nobody is sharing this version right now.", "delivery", True
        ) from None
    if response.status not in {200, 206, 416}:
        connection.close()
        raise MediaError("TORRENT_NO_PEERS", "Nobody is sharing this version right now.", "delivery", True)
    output = {
        k: v
        for k, v in response.getheaders()
        if k.lower() in {"content-range", "accept-ranges", "content-length"}
    }

    def chunks():
        try:
            if not head:
                while block := response.read(256 * 1024):
                    yield block
        except (OSError, http.client.HTTPException):
            raise MediaError(
                "SOURCE_INTERRUPTED", "Source delivery was interrupted.", "delivery", True
            ) from None
        finally:
            connection.close()

    return response.status, output, chunks()


class OpenSubtitles:
    base = "https://api.opensubtitles.com/api/v1"

    def __init__(self, config):
        if not config.get("enabled") or not config.get("api_key"):
            raise MediaError(
                "SUBTITLE_PROVIDER_UNCONFIGURED",
                "Configure OpenSubtitles before external subtitle search.",
                "setup",
            )
        self.headers = {"Api-Key": config["api_key"], "User-Agent": config.get("user_agent") or "HouseOS v1"}

    def search(self, imdb_id, language_code, season=None, episode=None):
        params = {"imdb_id": imdb_id.removeprefix("tt"), "languages": language_code}
        if season is not None:
            params.update(season_number=season, episode_number=episode)
        result = private_json(self.base, "/subtitles", headers=self.headers, params=params)
        candidates = []
        for record in result.get("data", [])[:30]:
            attributes = record.get("attributes", {})
            for file in attributes.get("files", [])[:3]:
                candidates.append(
                    {
                        "file_id": file.get("file_id"),
                        "language": attributes.get("language"),
                        "release": str(attributes.get("release", ""))[:240],
                        "sdh": bool(attributes.get("hearing_impaired")),
                        "foreign_parts_only": bool(attributes.get("foreign_parts_only")),
                        "fps": attributes.get("fps"),
                        "match": "canonical_title_episode",
                        "timing": "unverified",
                    }
                )
        return candidates[:20]

    def download(self, file_id):
        result = private_json(
            self.base, "/download", method="POST", headers=self.headers, payload={"file_id": int(file_id)}
        )
        if not result.get("link"):
            raise MediaError(
                "SUBTITLE_UNAVAILABLE", "The subtitle provider did not grant a download.", "prepare"
            )
        content, _ = public_fetch(result["link"], limit=5_000_000)
        return content


def rd_rate_limit():
    """Cross-process counter, bounded below the vendor's 250/min ceiling."""
    import fcntl
    import os
    from .config import settings

    root = Path(settings.runtime_root) / "cinema"
    try:
        root.mkdir(mode=0o770, parents=True, exist_ok=True)
        fd = os.open(root / "rd-rate.json", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o660)
        with os.fdopen(fd, "r+") as file:
            # Maintenance/probes sometimes run privileged. Keep shared runtime state
            # owned by the runtime directory, never by that incidental caller.
            if os.geteuid() == 0:
                owner = root.stat()
                os.fchown(file.fileno(), owner.st_uid, owner.st_gid)
                os.fchmod(file.fileno(), 0o660)
            fcntl.flock(file, fcntl.LOCK_EX)
            raw = file.read(10000)
            stamps = json.loads(raw) if raw else []
            if not isinstance(stamps, list):
                raise ValueError("Invalid counter")
            now = time.time()
            stamps = [t for t in stamps if type(t) in (int, float) and t > now - 60]
            if len(stamps) >= 120:
                raise MediaError(
                    "DEBRID_RATE_LIMIT",
                    "HouseOS reached its bounded debrid request allowance. Try after one minute.",
                    "resolve",
                    True,
                )
            stamps.append(now)
            file.seek(0)
            file.truncate()
            json.dump(stamps, file)
            file.flush()
    except (OSError, ValueError):
        raise MediaError(
            "DEBRID_COUNTER_UNAVAILABLE",
            "The local shared debrid counter cannot be read or written. Check Cinema runtime ownership and counter integrity in Control Room.",
            "resolve",
            True,
        ) from None
