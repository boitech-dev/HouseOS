"""Narrow local audio bridge. Never accepts a URL, command array or player option."""

import json
import re
import os
import socket
import socketserver
import subprocess
import threading
import time
import stat
import pwd
from pathlib import Path

from .atomic import write_json
from .config import settings
from .audio_volume import VolumeRamp

SOCKET = settings.runtime_root / "run/mpv.sock"
MEDIA = settings.runtime_root / "audio"
POLICY = settings.runtime_root / "run/audio-output.json"
player = None
live_item = None
# Where "default" plays, decided once at startup: "pulse" (PulseAudio/PipeWire default output),
# "alsa" (the sound card, no sound server) or "none" (a silent clock that phones and Cast follow).
server = "pulse"
# Evens out songs, never within a song: each file's overall loudness is measured once (ffmpeg
# EBU R128, in the background while the song before it plays) and one fixed gain is set before
# it starts. Quiet uploads (YouTube's -14 LUFS copies next to -9 masters) get +20 %; ear-splitting
# masters lose 15 %; everything else plays exactly as released. A boosted song whose peaks would
# then clip gets a brick-wall guard at 0 dB that only ever touches those few peaks. Live radio
# can't be measured ahead and plays as is. On by default; Control Room → House.
QUIET, LOUD = -13.0, -7.0  # LUFS; this house's library centres on -9
BOOST, CUT = 1.58, -1.41  # dB: ×1.2 and ×0.85 in amplitude
GAINS = {}  # (inode, size, mtime) → filter, while the bridge runs
AHEAD = threading.Lock()  # one background measuring pass at a time
ahead_at = 0.0


def song_filter(lufs, peak):
    """The mpv audio filter for one song from its integrated loudness and true peak (dBFS)."""
    if lufs > LOUD:
        return f"lavfi=[volume={CUT}dB]"
    if lufs >= QUIET:
        return ""
    guard = ",alimiter=limit=0.97:attack=1:release=50:level=disabled" if peak + BOOST > -0.3 else ""
    return f"lavfi=[volume={BOOST}dB{guard}]"


def measure(path):
    """The song's filter, measured once per file (a second or two of ffmpeg), none on failure."""
    try:
        info = path.stat()
    except OSError:
        return ""
    key = (info.st_ino, info.st_size, info.st_mtime_ns)
    if key not in GAINS:
        try:
            out = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path), "-vn"]
                + ["-af", "ebur128=peak=true", "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=60,
            ).stderr.split("Summary:")[-1]
            lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", out).group(1))
            peak = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", out).group(1))
        except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
            return ""
        if len(GAINS) > 2000:
            GAINS.clear()
        GAINS[key] = song_filter(lufs, peak)
    return GAINS[key]


def level_filter(path):
    return measure(path) if policy().get("normalize", True) else ""


def measure_ahead():
    """Measures staged songs not yet known, newest first, so the next one starts at once. A kept
    song is staged as a hard link that keeps its old mtime; the link itself updates ctime."""
    if not AHEAD.acquire(blocking=False):
        return  # already measuring
    try:
        newest = lambda p: max(p.stat().st_mtime, p.stat().st_ctime)  # noqa: E731
        files = sorted(MEDIA.glob("*.media"), key=newest, reverse=True)[:20]
        for path in files:
            if path.is_file() and not path.is_symlink():
                measure(path)
    except OSError:
        return
    finally:
        AHEAD.release()


def measure_soon(every=0):
    """In the background, never in a command's way (the bridge answers one request at a time).
    `every`: at most once per that many seconds (the worker asks for state every second)."""
    global ahead_at
    if every and time.monotonic() - ahead_at < every:
        return
    ahead_at = time.monotonic()
    if policy().get("normalize", True) and not AHEAD.locked():
        threading.Thread(target=measure_ahead, daemon=True).start()


def live_manifest(item):
    owner = pwd.getpwnam("houseos-fetch").pw_uid
    path = MEDIA / (item + ".live.json")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != owner or not stat.S_ISREG(info.st_mode) or info.st_size > 2048:
            raise ValueError("Invalid stream lease")
        with os.fdopen(fd, "r", closefd=False) as stream:
            data = json.load(stream)
    finally:
        os.close(fd)
    expires = data.get("expires_at")
    if (
        data.get("item_id") != item
        or data.get("state") not in {"waiting", "streaming"}
        or not isinstance(expires, (int, float))
        or not time.time() < expires <= time.time() + 3602
    ):
        raise ValueError("Stream lease unavailable")
    info = (MEDIA / (item + ".media")).lstat()
    if not stat.S_ISFIFO(info.st_mode) or info.st_uid != owner:
        raise ValueError("Invalid stream FIFO")
    return data


def save_policy(value):
    write_json(POLICY, value, 0o644)


def policy():
    try:
        value = json.loads(POLICY.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def default_sink():
    result = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=3)
    if result.returncode or not result.stdout.strip():
        raise OSError("Computer default output unavailable")
    return result.stdout.strip()


def detect_server(wait=30):
    """A configured sound server (PULSE_SERVER) may still be starting at boot: wait for it,
    then fall back to the sound card, then to silence. Never raises."""
    deadline = time.monotonic() + (wait if os.environ.get("PULSE_SERVER") else 0)
    while True:
        try:
            default_sink()
            return "pulse"
        except (OSError, subprocess.SubprocessError):
            if time.monotonic() >= deadline:
                break
            time.sleep(1)
    cards = Path("/dev/snd").glob("pcmC*D*p")
    return "alsa" if any(os.access(card, os.W_OK) for card in cards) else "none"


# Always offered: no sound here, only phones and Cast speakers (they follow this clock).
SILENT = {"id": "none", "name": "No sound from this computer", "state": "SILENT"}


def outputs():
    if server == "alsa":
        return (
            [{"id": "default", "name": "This computer's sound card", "state": "DEFAULT"}]
            + alsa_outputs()
            + [SILENT]
        )
    if server == "none":
        return [{"id": "default", "name": "This computer has no speakers", "state": "SILENT"}, SILENT]
    result = subprocess.run(
        ["pactl", "-f", "json", "list", "sinks"], capture_output=True, text=True, timeout=3
    )
    if result.returncode:
        raise OSError("Audio outputs unavailable")
    return (
        [{"id": "default", "name": "This computer's speakers", "state": "DEFAULT"}]
        + [
            {
                "id": s["name"],
                "name": s.get("description", s["name"]),
                "state": s.get("state"),
                "kind": kind(s["name"]),
            }
            for s in json.loads(result.stdout)
        ]
        + [SILENT]
    )


def move_to(sink):
    """Switch speakers, even mid-song: between outputs of the same sound server mpv just
    changes device; otherwise the player restarts and the song resumes where it was.
    Returns a refusal, or None when the new output is in use."""
    target = device(sink)
    if mpv(["get_property", "idle-active"]) is True:
        start_player(sink)
        return None
    current = mpv(["get_property", "current-ao"])
    if target and current and target.split("/")[0] == current:
        mpv(["set_property", "audio-device", target])
        return None
    if live_item:  # a live stream's pipe cannot be reopened by a new player
        return {"status": "blocked", "code": "LIVE_OUTPUT_SWITCH"}
    path, position = mpv(["get_property", "path"]), mpv(["get_property", "time-pos"]) or 0
    paused = mpv(["get_property", "pause"])
    start_player(sink)
    mpv(["set_property", "start", str(position) if position else "none"])
    mpv(["loadfile", path, "replace"])
    mpv(["set_property", "pause", bool(paused)])
    return None


_alsa_cache = (0.0, [])


def alsa_outputs():
    """Each sound-card output (analog, HDMI, USB…) as mpv sees it, without a sound server.
    Cached 30 s: state polls ask for outputs every second."""
    global _alsa_cache
    if time.monotonic() - _alsa_cache[0] < 30:
        return _alsa_cache[1]
    try:
        listing = subprocess.run(
            ["mpv", "--no-config", "--audio-device=help"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = [
        {"id": ident, "name": label.split("/")[0], "state": "IDLE", "kind": kind(label)}
        for ident, label in re.findall(r"'(alsa/plughw:[^']+)' \(([^)]*)\)", listing)
    ]
    _alsa_cache = (time.monotonic(), found)
    return found


def kind(name):
    """What sort of output a PipeWire/PulseAudio sink is, from its conventional name."""
    name = name.lower()
    for key, label in (("bluez", "bluetooth"), ("hdmi", "hdmi"), ("usb", "usb")):
        if key in name:
            return label
    return "speakers"


def device(sink):
    """The mpv audio device for a chosen output, or None for silence."""
    if sink == "default":
        return {"pulse": lambda: "pulse/" + default_sink(), "alsa": lambda: "alsa/default"}.get(
            server, lambda: None
        )()
    if sink and sink.startswith("alsa/"):
        return sink
    return "pulse/" + sink if sink and sink != "none" else None


_outputs_cache = (0.0, None)


def output_snapshot(fresh):
    """(default sink or None, current output ids). State polls arrive every second from the
    worker and every client; they reuse a 2 s snapshot instead of spawning pactl each time."""
    global _outputs_cache
    at, value = _outputs_cache
    if fresh or value is None or time.monotonic() - at > 2:
        try:
            default = default_sink() if server == "pulse" else device("default")
        except (OSError, subprocess.SubprocessError):
            default = None
        value = (default, {s["id"] for s in outputs()})
        _outputs_cache = (time.monotonic(), value)
    return value


def start_player(sink="default"):
    global player
    volume_ramp.cancel()
    if player is not None:
        player.terminate()
        try:
            player.wait(timeout=3)
        except subprocess.TimeoutExpired:
            player.kill()
            player.wait(timeout=2)
    if SOCKET.exists():
        SOCKET.unlink()
    args = [
        "mpv",
        "--no-config",
        "--load-scripts=no",
        "--ytdl=no",
        "--idle=yes",
        "--pause=yes",
        "--no-video",
        "--audio-display=no",
        "--volume=" + str(min(90, policy().get("volume_cap", 100))),
        "--volume-max=100",
        "--terminal=no",
        "--audio-fallback-to-null=no",
        "--input-ipc-server=" + str(SOCKET),
    ]
    target = device(sink)
    args.extend(["--ao=" + target.split("/")[0], "--audio-device=" + target] if target else ["--ao=null"])
    player = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if SOCKET.exists():
            return
        if player.poll() is not None:
            break
        time.sleep(0.05)
    raise OSError("Audio player startup failed")


def mpv(command):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        s.connect(str(SOCKET))
        s.sendall(json.dumps({"command": command, "request_id": 1}).encode() + b"\n")
        buf = b""
        while len(buf) < 65536:
            chunk = s.recv(4096)
            if not chunk:
                raise OSError("Player disconnected")
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = json.loads(line)
                if msg.get("request_id") == 1:
                    if msg.get("error") != "success":
                        if command[0] == "get_property" and msg.get("error") == "property unavailable":
                            return None
                        raise OSError("Player rejected command")
                    return msg.get("data")
    raise OSError("Player response too large")


volume_ramp = VolumeRamp(
    lambda: mpv(["get_property", "volume"]), lambda value: mpv(["set_property", "volume", value])
)


def execute(data):
    global live_item
    action = data.get("command")
    if action in {"load", "play", "test_output"} and (settings.runtime_root / "run/shutdown.json").exists():
        return {"status": "blocked", "code": "HOUSEOS_SHUTTING_DOWN"}
    selected = policy()
    selected.setdefault("sink", "default")
    if (
        action in {"state", "load", "play", "test_output"}
        and selected["sink"] == "default"
        and server == "pulse"
    ):
        sink, present = output_snapshot(fresh=action != "state")
        if sink is None:
            raise OSError("Computer default output unavailable")
        if sink not in present:
            mpv(["set_property", "pause", True])
            return {"status": "unavailable", "code": "DEFAULT_SINK_UNAVAILABLE", "paused": True}
        if mpv(["get_property", "audio-device"]) != "pulse/" + sink:
            mpv(["set_property", "audio-device", "pulse/" + sink])
    if action == "volume_cap":
        cap = data.get("value")
        if type(cap) is not int or not 0 <= cap <= 100:
            raise ValueError("Invalid volume cap")
        volume_ramp.cancel()
        mpv(["set_property", "volume", min(mpv(["get_property", "volume"]) or 0, cap)])
        selected["volume_cap"] = cap
        save_policy(selected)
        return {"status": "configured", "volume_cap": cap}
    if action == "normalize":
        value = data.get("value")
        if type(value) is not bool:
            raise ValueError("Invalid normalize setting")
        # Takes effect from the next song: never a jump in the middle of one.
        selected["normalize"] = value
        save_policy(selected)
        return {"status": "configured", "normalize": value}
    if action == "outputs":
        return {
            "sound_server": server,
            "items": outputs(),
            "selected": selected.get("sink"),
            "physical_verified": bool(selected.get("verified")),
            "playback_enabled": settings.audio_enabled,
        }
    if action == "select_output":
        sink = data.get("sink")
        if sink not in {s["id"] for s in outputs()}:
            raise ValueError("Unknown physical output")
        moved = move_to(sink)
        if moved:
            return moved
        save_policy({"sink": sink, "verified": False, "volume_cap": selected.get("volume_cap", 100)})
        return {"status": "configured", "sink": sink, "physical_verified": False}
    if action == "verify_output":
        if selected.get("sink") != data.get("sink") or not selected.get("test_sent"):
            raise ValueError("Output changed or not tested")
        selected["verified"] = bool(data.get("heard"))
        selected["verified_at"] = time.time()
        save_policy(selected)
        return {
            "status": "recorded",
            "physical_verified": selected["verified"],
            "evidence": "administrator attestation",
        }
    if action == "test_output":
        if selected.get("sink") != data.get("sink") or selected.get("sink") not in {
            s["id"] for s in outputs()
        }:
            raise ValueError("Output changed")
        if mpv(["get_property", "idle-active"]) is not True:
            raise ValueError("Stop playback before test")
        volume_ramp.cancel()
        import wave, math, struct

        path = MEDIA / "speaker-check.wav"
        with wave.open(str(path), "wb") as tone:
            tone.setnchannels(1)
            tone.setsampwidth(2)
            tone.setframerate(44100)
            tone.writeframes(
                b"".join(
                    struct.pack("<h", int(2500 * math.sin(2 * math.pi * 440 * n / 44100)))
                    for n in range(44100)
                )
            )
        mpv(["set_property", "volume", min(25, selected.get("volume_cap", 100))])
        mpv(["set_property", "start", "none"])
        mpv(["loadfile", str(path), "replace"])
        mpv(["set_property", "pause", False])
        selected["test_sent"] = True
        save_policy(selected)
        return {"status": "command_sent", "physical_verified": False, "duration_seconds": 1}
    if action == "state":
        measure_soon(every=15)  # the next song, staged meanwhile, is measured before its turn
        if live_item:
            try:
                live_manifest(live_item)
            except (OSError, ValueError, KeyError):
                mpv(["stop"])
                live_item = None
                return {"status": "observed", "idle": True, "paused": True, "code": "LIVE_LEASE_ENDED"}
        default, present = output_snapshot(fresh=False)
        if selected.get("sink") and selected["sink"] not in present:
            mpv(["set_property", "pause", True])
            return {"status": "unavailable", "code": "SELECTED_SINK_DISAPPEARED", "paused": True}
        return {
            "status": "observed",
            "idle": mpv(["get_property", "idle-active"]),
            "paused": mpv(["get_property", "pause"]),
            "position": mpv(["get_property", "time-pos"]),
            "item_id": Path(mpv(["get_property", "path"]) or "").stem,
            "duration": mpv(["get_property", "duration"]),
            "volume": mpv(["get_property", "volume"]),
            **volume_ramp.state(),
            "output": selected.get("sink"),
            "resolved_output": default if selected.get("sink", "default") == "default" else selected["sink"],
            "muted": mpv(["get_property", "mute"]),
            "audio_backend": mpv(["get_property", "current-ao"]),
            "physical_verified": bool(selected.get("verified")),
            "live": bool(live_item),
            "seek_supported": not bool(live_item),
        }
    if action == "load":
        if not settings.audio_enabled or selected.get("sink") not in {s["id"] for s in outputs()}:
            return {"status": "blocked", "code": "PHYSICAL_OUTPUT_NOT_ENABLED"}
        from uuid import UUID

        item = str(UUID(data["item_id"]))
        path = MEDIA / (item + ".media")
        if path.is_symlink():
            return {"status": "failed", "code": "AUDIO_FILE_MISSING"}
        position = data.get("position", 0)
        if not isinstance(position, (int, float)) or not 0 <= position <= 14400:
            raise ValueError("Invalid resume position")
        live = False
        if path.exists() and stat.S_ISFIFO(path.lstat().st_mode):
            live_manifest(item)
            live = True
        elif not path.is_file():
            return {"status": "failed", "code": "AUDIO_FILE_MISSING"}
        # The start option, then a plain loadfile: the same commands on mpv 0.35 (Debian) and 0.38+.
        mpv(["set_property", "start", str(position) if position and not live else "none"])
        mpv(["set_property", "af", "" if live else level_filter(path)])
        mpv(["loadfile", str(path), "replace"])
        live_item = item if live else None
        measure_soon()
        mpv(["set_property", "pause", not settings.audio_enabled])
    elif action in {"pause", "play"}:
        if action == "play" and (
            not settings.audio_enabled or selected.get("sink") not in {s["id"] for s in outputs()}
        ):
            return {"status": "blocked", "code": "PHYSICAL_OUTPUT_NOT_ENABLED"}
        mpv(["set_property", "pause", action == "pause"])
    elif action == "stop":
        mpv(["stop"])
        live_item = None
    elif action == "seek":
        if live_item:
            return {"status": "denied", "code": "LIVE_SEEK_UNSUPPORTED"}
        mpv(["seek", max(0, min(float(data.get("value", 0)), 86400)), "absolute"])
    elif action == "volume":
        value = float(data.get("value", 90))
        import math

        if not math.isfinite(value):
            raise ValueError("Invalid volume")
        volume_ramp.request(max(0, min(value, selected.get("volume_cap", 100))))
    elif action == "mute":
        mpv(["set_property", "mute", bool(data.get("value", True))])
    else:
        return {"status": "denied", "code": "UNKNOWN_COMMAND"}
    return {"status": "command_sent"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            line = self.rfile.readline(8193)
            if len(line) > 8192:
                raise ValueError()
            result = execute(json.loads(line))
        except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
            result = {"status": "failed", "code": "AUDIO_COMMAND_FAILED"}
        self.wfile.write(json.dumps(result).encode() + b"\n")


def main():
    from .events import restart_on_request

    restart_on_request("audio")
    settings.runtime_root.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    for path in (SOCKET, settings.audio_socket):
        if path.exists():
            path.unlink()
    os.umask(0o007)
    global server
    server = detect_server()
    selected = policy().get("sink", "default")
    try:
        if selected not in {s["id"] for s in outputs()}:
            selected = "none"
        start_player(selected)
    except (OSError, subprocess.SubprocessError):
        start_player("none")  # the clock keeps time for phones and Cast even without speakers
    try:
        with socketserver.UnixStreamServer(str(settings.audio_socket), Handler) as listener:
            os.chmod(settings.audio_socket, 0o660)
            listener.serve_forever()
    finally:
        player.terminate()
        player.wait(timeout=5)


if __name__ == "__main__":
    main()
