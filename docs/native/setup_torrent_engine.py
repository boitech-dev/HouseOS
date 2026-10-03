#!/usr/bin/env python3
"""The torrent player, once per native Linux install: TorrServer, so a stream add-on's versions play
without a debrid service. It listens on this computer only (127.0.0.1:8090); HouseOS turns to it
only after an admin ticks "Play torrents from this computer" in Control Room → Stream add-on. Safe to
run again. Run it with sudo:

  sudo python3 docs/native/setup_torrent_engine.py   (deploy/ in the source)

It installs the pinned TorrServer release (checked by its SHA-256) as its own user and unit, behind
a password (kept in HouseOS's secrets, so no web page on this computer can drive it), and sets it
quiet: no UPnP (no port opened on the router), sharing back capped, memory only, the
cache dropped when a film stops. Remove: systemctl disable --now houseos-torrent.
"""

import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

RELEASE = "MatriX.145"
SHA256 = "0819f0d697b778d85feb5d8c06becb2c63b06e7eedbb4690bafb460e220221b4"
BINARY = Path("/usr/local/lib/houseos/torrserver")
DATA = Path("/var/lib/houseos-torrent")
UNIT = Path("/etc/systemd/system/houseos-torrent.service")
ENGINE = "http://127.0.0.1:8090"
ENV_FILE = Path(
    os.environ.get(
        "HOUSEOS_ENV_FILE", "/etc/houseos/houseos.env"
    )
)
AUTH = {}
QUIET = {
    "DisableUPNP": True,
    "UploadRateLimit": 50,  # KB/s: BitTorrent always shares back; kept small
    "ConnectionsLimit": 25,
    "UseDisk": False,
    "RemoveCacheOnDrop": True,
    "EnableDLNA": False,
    "CacheSize": 256 * 1024 * 1024,
}


def run(*command):
    subprocess.run(command, check=True, capture_output=True, text=True)


def install():
    if not BINARY.is_file():
        url = f"https://github.com/YouROK/TorrServer/releases/download/{RELEASE}/TorrServer-linux-amd64"
        data = urllib.request.urlopen(url, timeout=120).read()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise SystemExit(
                "The TorrServer download doesn't match its checksum: not installed."
            )
        BINARY.parent.mkdir(parents=True, exist_ok=True)
        BINARY.write_bytes(data)
        BINARY.chmod(0o755)
    if subprocess.run(
        ["id", "houseos-torrent"], capture_output=True, check=False
    ).returncode:
        run(
            "useradd",
            "--system",
            "--no-create-home",
            "--shell",
            "/usr/sbin/nologin",
            "houseos-torrent",
        )
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.chown(DATA, "houseos-torrent", "houseos-torrent")
    # A password: HouseOS sends it; a page in a browser on this computer can't.
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    auth = next(
        (
            line.split("=", 1)[1]
            for line in lines
            if line.startswith("HOUSEOS_TORRENT_ENGINE_AUTH=")
        ),
        "",
    )
    if not auth:
        auth = "houseos:" + secrets.token_urlsafe(24)
        with os.fdopen(
            os.open(ENV_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a"
        ) as out:
            out.write(f"HOUSEOS_TORRENT_ENGINE_AUTH={auth}\n")
    user, password = auth.split(":", 1)
    (DATA / "accs.db").write_text(json.dumps({user: password}))
    os.chmod(DATA / "accs.db", 0o600)
    shutil.chown(DATA / "accs.db", "houseos-torrent", "houseos-torrent")
    global AUTH
    AUTH = {"Authorization": "Basic " + base64.b64encode(auth.encode()).decode()}
    UNIT.write_text(
        "[Unit]\nDescription=HouseOS torrent player (TorrServer, this computer only)\n"
        "After=network-online.target\n\n[Service]\nUser=houseos-torrent\n"
        f"ExecStart={BINARY} --ip 127.0.0.1 --port 8090 --path {DATA} --httpauth\n"
        "Restart=on-failure\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\n"
        f"ReadWritePaths={DATA}\nPrivateTmp=yes\nMemoryMax=1G\n\n[Install]\nWantedBy=multi-user.target\n"
    )
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "houseos-torrent")
    run("systemctl", "restart", "houseos-torrent")


def settle():
    for _ in range(30):
        try:
            urllib.request.urlopen(
                urllib.request.Request(ENGINE + "/echo", headers=AUTH), timeout=2
            )
            break
        except OSError:
            time.sleep(1)
    ask = lambda body: json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                ENGINE + "/settings",
                json.dumps(body).encode(),
                {"Content-Type": "application/json", **AUTH},
            ),
            timeout=10,
        ).read()
        or b"{}"
    )
    current = ask({"action": "get"})
    ask({"action": "set", "sets": {**current, **QUIET}})


if __name__ == "__main__":
    if os.geteuid():
        raise SystemExit("run with sudo")
    install()
    settle()
    print(
        "Torrent player ready on", ENGINE, "- turn it on in Control Room → Stream add-on."
    )
