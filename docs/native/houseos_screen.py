#!/usr/bin/env python3
"""Show on the TV, on the computer's side: HouseOS hands over a YouTube link, this opens it full
screen in the browser on this desktop, which Sunshine streams to Moonlight on the TV.

It asks HouseOS for work (a long poll on /api/v1/tv/screen/next with the house's screen key) and
tells it about this computer: Sunshine's host id and its "Desktop" app id, which let the TV open
Moonlight straight on this desktop, and whether a stream is on. When a video comes, it waits for
the stream (the TV may still be waking up), then opens the video in a window of its own, brings
it to the front and presses f (YouTube's full screen). While a stream is on, it keeps the
screen from blanking. Stdlib only; needs xdotool and an X11 desktop. Runs as the desktop user.

  houseos_screen.py            run (the desktop session starts it)
  houseos_screen.py --setup    ask for HouseOS's address and the screen key, save them (0600),
                               and start with the desktop from now on
  houseos_screen.py --check    show what it would report, without asking HouseOS
"""

import fcntl
import getpass
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
CONFIG = CONFIG_HOME / "houseos" / "screen.json"
INSTALLED = Path.home() / ".local" / "share" / "houseos" / "houseos_screen.py"
AUTOSTART = CONFIG_HOME / "autostart" / "houseos-screen.desktop"
SUNSHINE_CONFIG = CONFIG_HOME / "sunshine"
SUNSHINE_ASSETS = ("/usr/share/sunshine", "/usr/local/share/sunshine", "/app/share/sunshine")
SERVERINFO = "http://127.0.0.1:47989/serverinfo"
BROWSERS = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "firefox",
)
STREAM_WAIT = 60  # seconds for the TV to wake up and connect
PNG = b"\x89PNG\r\n\x1a\n"


def log(*words):
    print("houseos-screen:", *words, file=sys.stderr, flush=True)


# ---------- Sunshine ----------
def sunshine():
    """{"host_uuid", "streaming"} from Sunshine's public server info, or {} when it is off."""
    try:
        with urllib.request.urlopen(SERVERINFO, timeout=3) as reply:
            xml = reply.read(65536).decode("utf-8", "replace")
    except (OSError, ValueError):
        return {}
    uuid = re.search(r"<uniqueid>([0-9A-Fa-f-]{36})</uniqueid>", xml)
    state = re.search(r"<state>([^<]*)</state>", xml)
    return {
        "host_uuid": uuid.group(1) if uuid else "",
        "streaming": "BUSY" in (state.group(1) if state else ""),
    }


def sunshine_setting(name):
    try:
        for line in (SUNSHINE_CONFIG / "sunshine.conf").read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip()
    except OSError:
        pass
    return None


def assets_dir():
    found = [
        d for d in (os.environ.get("HOUSEOS_SUNSHINE_ASSETS"), *SUNSHINE_ASSETS) if d and Path(d).is_dir()
    ]
    return Path(found[0]) if found else Path(SUNSHINE_ASSETS[0])


def image_file(image):
    """The picture Sunshine hashes into an app's id (its validate_app_image_path), or None for
    its default box art."""

    def png(path):
        try:
            with path.open("rb") as picture:
                return path if picture.read(8) == PNG else None
        except OSError:
            return None

    if not image or Path(image).suffix.lower() != ".png":
        return None
    if (assets_dir() / image).exists():
        return png(assets_dir() / image)
    if image == "./assets/steam.png":
        return assets_dir() / "steam.png"
    return png(Path(image)) if Path(image).exists() else None


def sunshine_id(name, picture_sha256=""):
    """Sunshine's app id: CRC32 of the name and its picture's SHA-256 (hex), as a positive int32."""
    crc = zlib.crc32((name + picture_sha256).encode())
    return abs(crc - (1 << 32) if crc >= 1 << 31 else crc)


def app_id(name):
    """Sunshine's id for one of its apps, so Moonlight can open it directly; 0 without it."""
    path = Path(sunshine_setting("file_apps") or SUNSHINE_CONFIG / "apps.json")
    try:
        apps = json.loads(path.read_text()).get("apps", [])
    except (OSError, ValueError):
        return 0
    for app in apps:
        if str(app.get("name", "")).casefold() != name.casefold():
            continue
        picture = image_file(app.get("image-path", ""))
        return sunshine_id(app["name"], hashlib.sha256(picture.read_bytes()).hexdigest() if picture else "")
    return 0


# ---------- the desktop ----------
def x(*args, timeout=10):
    """One xdotool/xset call: its output, or "" when it failed."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def keep_awake():
    x("xset", "s", "reset")
    x("xset", "dpms", "force", "on")


def windows():
    return set(x("xdotool", "search", "--onlyvisible", "--name", ".").split())


def title(window):
    return x("xdotool", "getwindowname", window)


def fullscreen(window):
    screen = x("xdotool", "getdisplaygeometry").split()
    size = re.search(r"Geometry: (\d+)x(\d+)", x("xdotool", "getwindowgeometry", window))
    return bool(screen and size) and size.groups() == tuple(screen[:2])


def wait_for(check, seconds, step=0.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(step)
    return None


class Screen:
    def __init__(self, browser):
        self.browser = browser
        self.window = None  # the window the last video opened in

    def close_last(self):
        if self.window and "YouTube" in title(self.window):  # still ours, still a video
            x("xdotool", "windowactivate", "--sync", self.window, "key", "--clearmodifiers", "ctrl+shift+w")
            wait_for(lambda: self.window not in windows(), 5)
        self.window = None

    def open(self, url):
        """Open the video in a new browser window, in front, full screen. Raises with a sentence."""
        keep_awake()
        self.close_last()
        before = windows()
        subprocess.Popen(
            [self.browser, "--new-window", url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        window = wait_for(lambda: next(iter(sorted(windows() - before)), None), 20)
        if not window:
            raise RuntimeError("The browser didn't open a window.")
        self.window = window
        x("xdotool", "windowactivate", "--sync", window)
        # The title becomes "<video> - YouTube - <browser>" once the page knows its video.
        if not wait_for(lambda: re.search(r".+ - YouTube", title(window)), 25):
            raise RuntimeError("YouTube didn't load in time.")
        time.sleep(2)  # the player starts a moment after the title
        for _ in range(3):
            x("xdotool", "windowactivate", "--sync", window, "key", "--clearmodifiers", "f")
            if wait_for(lambda: fullscreen(window), 3):
                return
        raise RuntimeError("The video opened, but not full screen.")


# ---------- HouseOS ----------
class HouseOS:
    def __init__(self, base, key):
        self.base, self.key = base.rstrip("/"), key

    def call(self, path, body=None, timeout=10):
        request = urllib.request.Request(
            self.base + "/api/v1/tv/screen" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return json.loads(reply.read() or b"{}")

    def report(self, job, state, **extra):
        try:
            self.call("/jobs/" + urllib.parse.quote(job["id"]), {"state": state, **extra})
        except (OSError, ValueError) as error:
            log("couldn't report", state, error)


def about(app):
    stream = sunshine()
    return {
        "host_uuid": stream.get("host_uuid", ""),
        "app_id": app_id(app) if stream else 0,
        "streaming": "true" if stream.get("streaming") else "false",
        "name": socket.gethostname(),
    }


def handle(house, screen, job, app):
    stream = sunshine()
    house.report(job, "claimed", streaming=bool(stream.get("streaming")))
    try:
        if job.get("expect_stream") and not stream.get("streaming"):
            log("waiting for the TV to connect")
            if not wait_for(lambda: (keep_awake(), sunshine().get("streaming"))[1], STREAM_WAIT, 1):
                log("no stream yet; opening anyway")
        screen.open(job["url"])
        house.report(job, "opened")
    except Exception as error:  # whatever went wrong, HouseOS hears it in a sentence
        house.report(job, "failed", detail=str(error)[:300])
        log("failed:", error)


def run(config):
    house = HouseOS(config["url"], config["key"])
    app = config.get("app", "Desktop")
    browser = config.get("browser") or next((b for b in BROWSERS if shutil.which(b)), None)
    if not browser or not shutil.which("xdotool"):
        sys.exit("houseos-screen: needs a browser and xdotool (sudo apt install xdotool).")
    screen = Screen(browser)
    pause = 5
    while True:
        info = about(app)
        if info["streaming"] == "true":
            keep_awake()  # a video plays without anyone touching the mouse
        try:
            reply = house.call(
                "/next?" + urllib.parse.urlencode({**info, "browser": browser, "wait": 25}), timeout=40
            )
            pause = 5
        except urllib.error.HTTPError as error:
            log(
                "HouseOS refused:",
                error.code,
                "(a new screen key? run --setup again)" if error.code == 401 else "",
            )
            time.sleep(60 if error.code == 401 else pause)
            continue
        except (OSError, ValueError) as error:
            log("HouseOS isn't answering:", error)
            time.sleep(pause)
            pause = min(pause * 2, 60)
            continue
        if reply.get("job"):
            handle(house, screen, reply["job"], app)


def single():
    """One helper per desktop session: a second start leaves quietly."""
    folder = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
    lock = open(folder / "houseos-screen.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)
    return lock


def setup():
    if not shutil.which("xdotool"):
        sys.exit("Install xdotool first: sudo apt install xdotool")
    saved = {}
    try:
        saved = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        pass
    url = input(f"HouseOS address [{saved.get('url', 'http://127.0.0.1:8990')}]: ").strip()
    url = url or saved.get("url", "http://127.0.0.1:8990")
    key = getpass.getpass("Screen key (Control Room → Devices → Show on the TV): ").strip()
    try:
        HouseOS(url, key).call("/next?wait=0")
    except urllib.error.HTTPError as error:
        sys.exit(f"HouseOS refused it ({error.code}). Check the address and the key.")
    except (OSError, ValueError) as error:
        sys.exit(f"HouseOS didn't answer at {url}: {error}")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text("")
    CONFIG.chmod(0o600)
    CONFIG.write_text(json.dumps({**saved, "url": url, "key": key}, indent=2))
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__file__, INSTALLED)
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART.write_text(
        "[Desktop Entry]\nType=Application\nName=HouseOS: Show on the TV\n"
        f"Exec={sys.executable} {INSTALLED}\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n"
    )
    subprocess.Popen(
        [sys.executable, str(INSTALLED)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print("Saved. The helper is running and starts with the desktop from now on.")


def main():
    if "--setup" in sys.argv:
        return setup()
    if "--check" in sys.argv:
        config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        info = about(config.get("app", "Desktop"))
        print(
            json.dumps(
                {**info, "display": os.environ.get("DISPLAY"), "xdotool": bool(shutil.which("xdotool"))}
            )
        )
        return
    try:
        config = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        sys.exit(f"houseos-screen: not set up yet; run {sys.argv[0]} --setup")
    _lock = single()  # noqa: F841 (held for the process's life)
    run(config)


if __name__ == "__main__":
    main()
