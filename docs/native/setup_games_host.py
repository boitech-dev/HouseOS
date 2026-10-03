#!/usr/bin/env python3
"""Games on the TV, once per native Linux install: Sunshine streams this computer's screen to
Moonlight on the TV; RetroArch plays the game. Safe to run again. Never starts a game, never moves
the music, never opens anything beyond the home network. Run it with sudo:

  sudo python3 deploy/setup_games_host.py --user <the desktop user> [--lan 192.168.1.0/24]

What it does, in order:
  1. installs Sunshine (its official package for this Ubuntu) and RetroArch (Flathub);
  2. gives the desktop user read access to the games and write access to the saves (ACLs);
  3. adds a silent sound output "houseos-games" that the game plays into and Sunshine streams
     (the house's music keeps its own speakers: its output is pinned to the one it uses now);
  4. configures Sunshine: one app, "HouseOS"; controllers only (no keyboard, no mouse, so a
     paired screen can never drive the desktop); its admin page for this computer only;
  5. makes a Sunshine admin password (kept in the house's secrets, never printed);
  6. opens Sunshine's ports to the home network only (ufw);
  7. starts Sunshine for the desktop user and tells HouseOS that TV play is ready.
"""

import argparse
import json
import os
import platform
import pwd
import secrets
import shutil
import subprocess
import urllib.request
from pathlib import Path

RUNTIME = Path(os.environ.get("HOUSEOS_RUNTIME_ROOT", "/opt/houseos/state"))
# The API's environment file (it pairs screens with Sunshine's password): --env-file changes it.
SECRETS = Path(os.environ.get("HOUSEOS_ENV_FILE", "/etc/houseos/houseos.env"))
SINK = "houseos-games"
PORTS = [("47984", "tcp"), ("47989", "tcp"), ("48010", "tcp"), ("47998:48000", "udp")]


def run(*command, user=None, check=True, env=None, quiet=False):
    if user:
        uid = pwd.getpwnam(user).pw_uid
        command = ("sudo", "-u", user, "env", f"XDG_RUNTIME_DIR=/run/user/{uid}",
                   f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus", *command)  # fmt: skip
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if check and result.returncode:
        raise SystemExit(f"failed: {' '.join(command[:6])}…\n{result.stderr[-800:]}")
    if not quiet and result.stdout.strip():
        print(result.stdout.strip()[-400:])
    return result


def install(user):
    if not shutil.which("sunshine"):
        release = json.load(
            urllib.request.urlopen("https://api.github.com/repos/LizardByte/Sunshine/releases/latest")
        )
        version = platform.freedesktop_os_release().get("VERSION_ID", "")
        arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
        asset = next(
            a for a in release["assets"] if a["name"].endswith(f"ubuntu{version}_{arch}.deb")
        )  # this Ubuntu's own build
        target = Path("/tmp") / asset["name"]
        urllib.request.urlretrieve(asset["browser_download_url"], target)
        run("apt-get", "install", "-y", str(target))
        target.unlink()
        print("Sunshine", release["tag_name"], "installed")
    if not shutil.which("ffplay"):  # the TV's "pick a game" screen
        run("apt-get", "install", "-y", "ffmpeg")
    if run("flatpak", "info", "org.libretro.RetroArch", check=False, quiet=True).returncode:
        run("flatpak", "install", "-y", "--system", "flathub", "org.libretro.RetroArch")
        print("RetroArch installed")


def access(user, data_root):
    games, saves = data_root / "media" / "games", data_root / "game-saves"
    cache = RUNTIME / "audio" / "games"
    for folder in (games, saves, cache, cache / "run", cache / "cores"):
        folder.mkdir(parents=True, exist_ok=True)
        shutil.chown(folder, "houseos", "houseos")
    for parent in (data_root, data_root / "media"):  # through, not into
        run("setfacl", "-m", f"u:{user}:x", str(parent))
    run("setfacl", "-R", "-m", f"u:{user}:rX,d:u:{user}:rX", str(games))
    run("setfacl", "-R", "-m", f"u:{user}:rwX,d:u:{user}:rwX,d:u:houseos:rwX", str(saves))
    # The fetcher (its own user, in the houseos group) writes here too: the group keeps rwx.
    run("setfacl", "-R", "-m", f"g::rwX,d:g::rwX,u:{user}:rwX,d:u:{user}:rwX,d:u:houseos:rwX", str(cache))


def sound(user):
    home = Path(pwd.getpwnam(user).pw_dir)
    conf = home / ".config/pipewire/pipewire-pulse.conf.d/houseos-games.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(
        "# HouseOS games (D33): a silent output the game plays into and Sunshine streams.\n"
        'pulse.cmd = [ { cmd = "load-module" args = "module-null-sink '
        f'sink_name={SINK} sink_properties=device.description=HouseOS-games" flags = [ ] }} ]\n'
    )
    shutil.chown(conf, user, user)
    sinks = run("pactl", "list", "short", "sinks", user=user, quiet=True).stdout
    if SINK not in sinks:  # now too, without restarting the sound server (the music keeps playing)
        run("pactl", "load-module", "module-null-sink", f"sink_name={SINK}",
            "sink_properties=device.description=HouseOS-games", user=user, quiet=True)  # fmt: skip
    # The house's music names its speakers instead of following "the default", which a stream moves.
    policy = RUNTIME / "run" / "audio-output.json"
    if policy.is_file():
        data = json.loads(policy.read_text())
        if data.get("sink") == "default":
            current = run("pactl", "get-default-sink", user=user, quiet=True).stdout.strip()
            if current and current != SINK:
                data["sink"] = current
                policy.write_text(json.dumps(data))
                print("music pinned to", current)


def sunshine(user):
    home = Path(pwd.getpwnam(user).pw_dir)
    folder = home / ".config/sunshine"
    folder.mkdir(parents=True, exist_ok=True)
    launcher = RUNTIME / "current" / "deploy" / "houseos_game.py"
    (folder / "sunshine.conf").write_text(
        "# HouseOS (D33): written by deploy/setup_games_host.py\n"
        "sunshine_name = HouseOS\n"
        f"audio_sink = {SINK}\nvirtual_sink = {SINK}\n"
        "keyboard = disabled\nmouse = disabled\n"
        "origin_web_ui_allowed = pc\nupnp = disabled\n"
        "capture = kms\n"  # straight from the graphics card: no screen-sharing prompt to answer
    )
    (folder / "apps.json").write_text(
        json.dumps(
            {
                "env": {},
                "apps": [
                    {
                        "name": "HouseOS",
                        "cmd": str(launcher),
                        "prep-cmd": [{"do": "", "undo": f"{launcher} --stop"}],
                        "exclude-global-prep-cmd": "false",
                        "auto-detach": "false",
                    }
                ],
            },
            indent=2,
        )
    )
    run("chown", "-R", f"{user}:{user}", str(folder))
    # The admin password: made here, kept in the house's secrets (the API pairs screens with it).
    lines = SECRETS.read_text().splitlines() if SECRETS.exists() else []
    if not any(line.startswith("HOUSEOS_SUNSHINE_PASSWORD=") for line in lines):
        password = secrets.token_urlsafe(24)
        run("sudo", "-u", user, "sunshine", "--creds", "houseos", password, quiet=True)
        existed = SECRETS.exists()
        with os.fdopen(os.open(SECRETS, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a") as out:
            out.write(f"HOUSEOS_SUNSHINE_USER=houseos\nHOUSEOS_SUNSHINE_PASSWORD={password}\n")
        if not existed:
            shutil.chown(SECRETS, user, user)
        print("Sunshine password stored in", SECRETS.name)


def firewall(lan):
    if not shutil.which("ufw"):
        return print("no ufw: open", ", ".join(f"{p}/{proto}" for p, proto in PORTS), "to your home network")
    for port, proto in PORTS:
        run("ufw", "allow", "from", lan, "to", "any", "port", port, "proto", proto,
            "comment", "HouseOS games (Sunshine)", quiet=True)  # fmt: skip


def start(user):
    units = run("systemctl", "--user", "list-unit-files", "--no-legend", user=user, quiet=True).stdout
    unit = next((u.split()[0] for u in units.splitlines() if "unshine" in u), "sunshine.service")
    run("systemctl", "--user", "enable", unit, user=user, quiet=True)
    run("systemctl", "--user", "restart", unit, user=user, quiet=True)  # it reads its config at start
    run(
        str(RUNTIME / "current" / "deploy" / "houseos_game.py"),
        "--report",
        user=user,
        check=False,
        quiet=True,
    )
    print("Sunshine running as", unit)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user", required=True, help="the desktop user whose screen is streamed")
    parser.add_argument("--lan", default="192.168.1.0/24", help="the home network (ufw)")
    parser.add_argument("--data-root", default="/mnt/house-storage/houseos")
    args = parser.parse_args()
    if os.geteuid():
        raise SystemExit("run with sudo")
    install(args.user)
    access(args.user, Path(args.data_root))
    sound(args.user)
    sunshine(args.user)
    firewall(args.lan)
    start(args.user)
    print("TV play ready: install Moonlight on the TV, then pair it in HouseOS → Games → Set up.")


if __name__ == "__main__":
    main()
