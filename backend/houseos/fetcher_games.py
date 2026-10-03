"""Games, inside the fetcher: public internet only, no secrets. Every address is built
here from a fixed list (the open libretro database and thumbnails, EmulatorJS pinned to one
release, libretro's RetroArch cores); the only address a person gives is a game link they paste,
downloaded as a plain file. Never a game from anywhere else. Files land in DIR, which the API,
the workers and the TV launcher read."""

import http.client
import io
import json
import os
import re
import shutil
import zipfile
from urllib.parse import quote, urljoin
from uuid import UUID

from .config import settings
from .games_systems import SYSTEMS

DIR = settings.runtime_root / "audio" / "games"
EMULATORJS = "4.2.3"  # upgrade: bump, check the loader's file list, clear DIR/emulatorjs
EJS_FILE = re.compile(
    r"(loader\.js|emulator\.min\.(js|css)|cores/[a-z0-9_]+-(legacy-)?wasm\.data|cores/reports/[a-z0-9_]+\.json"
    r"|compression/(extract7z|extractzip|libunrar)\.(js|wasm)|localization/[a-z]{2,3}-[A-Z]{2,3}\.json)"
)
DATS = (
    "metadat/no-intro", "metadat/redump", "metadat/fbneo-split", "metadat/hacks", "metadat/genre",
    "metadat/developer", "metadat/publisher", "metadat/releaseyear", "metadat/maxusers",
    "metadat/franchise",
)  # fmt: skip
ART = {"box": "Named_Boxarts", "title": "Named_Titles", "snap": "Named_Snaps"}
LINK_LIMIT = 16 * 1024**3  # a dual-layer DVD (8.5 GB) fits
KEEP_FREE = 6 * 1024**3  # the download waits on the system disk: never fill it


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    os.chmod(partial, 0o640)
    os.replace(partial, path)


def get(url, limit):
    from .cinema_adapters import public_fetch
    from .playback import MediaError

    try:
        return public_fetch(url, limit=limit)[0]
    except MediaError:
        return None  # missing (404) and unreachable look the same: nothing to keep


def thumbnail_name(name):
    """libretro-thumbnails' own rule: these characters become underscores."""
    return re.sub(r'[&*/:`<>?\\|"]', "_", name)


def execute(data):
    action = data["action"]
    if action == "games_dat":  # the open game list of one console, one file of it
        system = SYSTEMS[data["system"]]
        if data["file"] not in DATS:
            raise ValueError("UNSUPPORTED_FETCH_ACTION")
        target = DIR / "db" / "raw" / data["system"] / (data["file"].replace("/", "-") + ".dat")
        url = (
            "https://raw.githubusercontent.com/libretro/libretro-database/master/"
            + data["file"] + "/" + quote(system["libretro"]) + ".dat"
        )  # fmt: skip
        raw = get(url, 32_000_000)
        save(target, raw or b"")  # empty: this console has no such list; don't ask again
        return {"status": "completed", "bytes": len(raw or b"")}
    if action == "games_art":  # a cover, title screen or in-game picture by the game's exact name
        system = SYSTEMS[data["system"]]
        key = data["key"]
        if not re.fullmatch(r"[0-9a-f]{8}|[0-9a-f-]{36}", key) or data["kind"] not in ART:
            raise ValueError("UNSUPPORTED_FETCH_ACTION")
        url = "/".join(
            (
                "https://thumbnails.libretro.com",
                quote(system["libretro"]),
                ART[data["kind"]],
                quote(thumbnail_name(str(data["name"])[:300])) + ".png",
            )
        )
        raw = get(url, 4_000_000)
        found = bool(raw and raw.startswith(b"\x89PNG"))
        save(DIR / "art" / f"{key}-{data['kind']}.png", raw if found else b"")
        return {"status": "completed", "found": found}
    if action == "games_ejs":  # the in-browser emulator, one file when a game first needs it
        path = str(data.get("path", ""))
        if not EJS_FILE.fullmatch(path):
            raise ValueError("UNSUPPORTED_FETCH_ACTION")
        raw = get(f"https://cdn.emulatorjs.org/{EMULATORJS}/data/{path}", 96_000_000)
        if raw is None:
            raise ValueError("SOURCE_UNAVAILABLE")
        save(DIR / "emulatorjs" / EMULATORJS / path, raw)
        return {"status": "completed", "bytes": len(raw)}
    if action == "games_core":  # a RetroArch core for the TV, when a game first needs it
        core = str(data.get("core", ""))
        if core not in {s["tv"] for s in SYSTEMS.values()}:
            raise ValueError("UNSUPPORTED_FETCH_ACTION")
        name = core + "_libretro.so"
        raw = get(f"https://buildbot.libretro.com/nightly/linux/x86_64/latest/{name}.zip", 256_000_000)
        if raw is None:
            raise ValueError("SOURCE_UNAVAILABLE")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            save(DIR / "cores" / name, archive.read(name))
        return {"status": "completed"}
    if action == "games_link":  # a game file the person pasted a link to
        return link(str(UUID(data["item_id"])), str(data.get("source_url", "")))
    raise ValueError("UNSUPPORTED_FETCH_ACTION")


def link(identity, url):
    """Stream a public HTTPS file to DIR/incoming/<id>, checking every redirect's address."""
    from .cinema_adapters import PinnedHTTPS, public_url
    from .playback import MediaError

    target = DIR / "incoming" / identity
    target.parent.mkdir(parents=True, exist_ok=True)
    note = target.with_name(identity + ".json")  # the size to expect, then how it ended (games.sweep)
    try:
        for _ in range(5):
            try:
                parsed, address = public_url(url)
            except MediaError:
                raise ValueError("UNSAFE_SOURCE") from None
            connection = PinnedHTTPS(parsed.hostname, address)
            try:
                connection.timeout = 60
                connection.request(
                    "GET",
                    parsed.path + ("?" + parsed.query if parsed.query else ""),
                    headers={"User-Agent": "HouseOS/1", "Accept-Encoding": "identity"},
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.getheader("Location", ""))
                    continue
                if response.status != 200:
                    raise ValueError("SOURCE_UNAVAILABLE")
                if (
                    (response.getheader("Content-Type") or "")
                    .lower()
                    .startswith(("text/html", "application/xhtml"))
                ):
                    raise ValueError("GAME_LINK_PAGE")  # a site's page about the game, not its file
                room = min(LINK_LIMIT, shutil.disk_usage(target.parent).free - KEEP_FREE)
                length = int(response.getheader("Content-Length") or 0)
                if length > LINK_LIMIT:
                    raise ValueError("SOURCE_RESPONSE_TOO_LARGE")
                if length > room:
                    raise ValueError("GAME_NO_SPACE")
                disposition = response.getheader("Content-Disposition") or ""
                named = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition)
                name = (named.group(1) if named else parsed.path.rsplit("/", 1)[-1]) or "game"
                note.write_text(json.dumps({"total": length}))
                size = 0
                with open(target, "wb") as out:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > room:
                            raise ValueError(
                                "SOURCE_RESPONSE_TOO_LARGE" if size > LINK_LIMIT else "GAME_NO_SPACE"
                            )
                        out.write(chunk)
                os.chmod(target, 0o640)
                from urllib.parse import unquote

                result = {"status": "completed", "name": unquote(name)[-200:], "bytes": size}
                note.write_text(json.dumps({"total": length, **result}))
                return result
            except (OSError, http.client.HTTPException):
                raise ValueError("SOURCE_TIMEOUT") from None
            finally:
                connection.close()
        raise ValueError("UNSAFE_SOURCE")
    except BaseException as error:
        target.unlink(missing_ok=True)
        code = str(error) if isinstance(error, ValueError) else "SOURCE_UNAVAILABLE"
        note.write_text(json.dumps({"status": "failed", "code": code}))
        raise
