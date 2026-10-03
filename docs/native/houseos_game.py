#!/usr/bin/env python3
"""HouseOS on the TV: what Sunshine starts when Moonlight opens "HouseOS".

It plays the game picked in HouseOS (run/next.json) in RetroArch, full screen, with that person's
saves: the in-game save is copied both ways with the browser's (save.srm), and RetroArch keeps its
own snapshot so the TV resumes where it stopped. Picking another game switches; Stop stops.
Nothing picked yet: a waiting screen says where to pick. Stdlib only; runs as the desktop user.

  houseos_game.py           the Sunshine app command
  houseos_game.py --stop       Sunshine's "undo" command (the stream ended)
  houseos_game.py --report     tell HouseOS that TV play works here (setup does this)
  houseos_game.py --self-check with a fake RetroArch
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNTIME = Path(os.environ.get("HOUSEOS_RUNTIME_ROOT", "/opt/houseos/state"))
RUN = RUNTIME / "audio" / "games" / "run"
FLATPAK = os.environ.get("HOUSEOS_GAME_FLATPAK", "flatpak")
APP = "org.libretro.RetroArch"
FRESH = 1800  # a pick older than this waits for a new one: someone else may be on the couch
SINK = "houseos-games"  # the games' own sound output, which Sunshine streams (never the music's)


def read(name):
    try:
        return json.loads((RUN / name).read_text())
    except (OSError, ValueError):
        return None


def write(name, data):
    RUN.mkdir(parents=True, exist_ok=True)
    partial = RUN / (name + ".part")
    partial.write_text(json.dumps(data))
    os.replace(partial, RUN / name)


def status(state, pick=None, since=None):
    write("tv.json", {
        "state": state, "at": time.time(), "since": since, "game_id": (pick or {}).get("game_id"),
        "user_id": (pick or {}).get("user_id"), "player": (pick or {}).get("player"),
    })  # fmt: skip


def report_host():
    """Tell HouseOS that TV play works here (it shows the TV button only then)."""
    try:
        info = subprocess.run([FLATPAK, "info", APP], capture_output=True, text=True, timeout=20)
        version = next(
            (ln.split(":", 1)[1].strip() for ln in info.stdout.splitlines() if "Version" in ln), ""
        )
    except (OSError, subprocess.SubprocessError):
        version = ""
    write("host.json", {"retroarch": version or None, "at": time.time()})


def config(pick, folder):
    tv = folder / "tv"
    tv.mkdir(parents=True, exist_ok=True)
    (folder / "tv-states").mkdir(exist_ok=True)
    lines = {
        "savefile_directory": tv, "savestate_directory": folder / "tv-states",
        "system_directory": pick["bios"], "savestate_auto_save": "true", "savestate_auto_load": "true",
        "autosave_interval": "10", "video_fullscreen": "true", "pause_nonactive": "false",
        "config_save_on_exit": "false", "audio_driver": "pulse", "kiosk_mode_enable": "true",
        "menu_show_load_content": "false", "menu_show_load_core": "false",
        "menu_show_online_updater": "false", "menu_show_core_updater": "false",
        "input_menu_toggle_gamepad_combo": "3",  # L1 + R1 + Start + Select: the menu (Quit is there)
        "input_autodetect_enable": "true", "notification_show_autoconfig": "false",
    }  # fmt: skip
    path = folder / "tv" / "houseos.cfg"
    path.write_text("".join(f'{k} = "{v}"\n' for k, v in lines.items()))
    return path


def launch(pick):
    folder = Path(pick["saves"])
    game, core = Path(pick["path"]), Path(pick["core"])
    cfg = config(pick, folder)
    shared, own = folder / "save.srm", folder / "tv" / (game.stem + ".srm")
    if shared.is_file() and (not own.is_file() or shared.stat().st_mtime > own.stat().st_mtime):
        shutil.copyfile(shared, own)  # the browser played last: continue from its save
    command = [
        FLATPAK, "run", f"--filesystem={game.parent}:ro", f"--filesystem={core.parent}:ro",
        f"--filesystem={pick['bios']}:ro", f"--filesystem={folder}", f"--env=PULSE_SINK={SINK}",
        APP, "-f", "-L", str(core), "--appendconfig", str(cfg), str(game),
    ]  # fmt: skip
    return subprocess.Popen(command, start_new_session=True), own, shared


def sync(own, shared, seen):
    """RetroArch wrote the in-game save: hand it to the browser side too."""
    try:
        mtime = own.stat().st_mtime
    except FileNotFoundError:
        return seen
    if mtime > seen:
        shutil.copyfile(own, shared.with_suffix(".part"))
        os.replace(shared.with_suffix(".part"), shared)
    return mtime


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)  # RetroArch saves on the way out
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def waiting_screen():
    """Full screen while nothing is picked, so the stream never shows the desktop."""
    text = "Pick a game in HouseOS on your phone"
    graph = (
        "color=c=0x16131f:s=1920x1080:r=5,"
        f"drawtext=text='{text}':fontcolor=0xf3e9d2:fontsize=56:x=(w-text_w)/2:y=(h-text_h)/2"
    )
    try:
        return subprocess.Popen(
            ["ffplay", "-hide_banner", "-loglevel", "quiet", "-fs", "-an", "-f", "lavfi", graph],
            stdin=subprocess.DEVNULL, start_new_session=True,
        )  # fmt: skip
    except OSError:
        return None


def main():
    report_host()
    (RUN / "stop").unlink(missing_ok=True)
    screen, process, current, own, shared, seen, since = None, None, None, None, None, 0.0, None
    deadline = time.time() + 600
    try:
        while True:
            pick = read("next.json")
            fresh = pick and time.time() - pick.get("at", 0) < FRESH
            if (RUN / "stop").exists():
                break
            if fresh and (current is None or pick["at"] != current["at"]):
                if process:  # another game was picked: switch
                    stop(process)
                    seen = sync(own, shared, seen)
                if screen:
                    stop(screen)
                    screen = None
                process, own, shared = launch(pick)
                current, seen, since = pick, time.time(), time.time()
            if process is None:
                if time.time() > deadline:
                    break
                screen = screen or waiting_screen()
                status("waiting")
            elif process.poll() is not None:  # quit from RetroArch's menu: the stream ends
                break
            else:
                seen = sync(own, shared, seen)
                status("playing", current, since)
            time.sleep(1)
    finally:
        stop(process)
        stop(screen)
        if own:
            sync(own, shared, seen)
        status("idle")


def self_check():
    global RUN, FLATPAK
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        RUN = tmp / "run"
        fake = tmp / "flatpak"
        fake.write_text(
            "#!/bin/sh\n[ \"$1\" = info ] && { echo 'Version: 1.22.2'; exit 0; }\n"
            'for a; do last="$a"; done\nstem=$(basename "${last%.*}")\n'
            'echo SRAM > "$SAVES/tv/$stem.srm"; sleep 30\n'
        )
        fake.chmod(0o755)
        FLATPAK = str(fake)
        saves = tmp / "saves"
        os.environ["SAVES"] = str(saves)
        (saves / "tv").mkdir(parents=True)
        (saves / "save.srm").write_text("OLD")
        game = tmp / "Game (USA).sfc"
        game.write_text("rom")
        write("next.json", {"at": time.time(), "game_id": "g", "user_id": "u", "player": "Sam",
                            "path": str(game), "core": str(tmp / "snes9x_libretro.so"),
                            "saves": str(saves), "bios": str(tmp)})  # fmt: skip
        import threading

        threading.Timer(3, lambda: (RUN / "stop").touch()).start()
        main()
        assert read("host.json")["retroarch"] == "1.22.2"
        assert read("tv.json")["state"] == "idle"
        assert (saves / "save.srm").read_text() == "SRAM\n", "the TV's save reaches the browser"
        assert 'savestate_auto_load = "true"' in (saves / "tv" / "houseos.cfg").read_text()
    print("houseos_game ok")


if __name__ == "__main__":
    if "--stop" in sys.argv:
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "stop").touch()
    elif "--report" in sys.argv:
        report_host()
    elif "--self-check" in sys.argv:
        self_check()
    else:
        main()
