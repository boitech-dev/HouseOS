"""Local speech-to-text for the assistant (faster-whisper), in its own venv and unit.

The API writes each recording to a private file and asks over a Unix socket; this service
reads it, transcribes it and never keeps audio. The model loads on first use, prefers the
GPU and unloads after a quiet spell so games and renders get the card back."""

import gc
import json
import os
import socketserver
import threading
import time
from pathlib import Path

RUNTIME = Path(os.environ.get("HOUSEOS_RUNTIME_ROOT", os.environ.get("HOUSEOS_RUNTIME", "/var/lib/houseos")))
SOCKET = RUNTIME / "run" / "voice.sock"
INBOX = RUNTIME / "run" / "voice"
MODELS = RUNTIME / "models" / "whisper"
IDLE_SECONDS = int(os.environ.get("HOUSEOS_VOICE_IDLE_SECONDS", "600"))
# Speech-model codes offered to the house; any other language is detected by the model.
LANGUAGES = set("fr en es de it pt nl pl ru uk ja ko zh ar tr sv da no fi cs el he hu ro hi".split())

lock = threading.Lock()
state = {"model": None, "name": None, "used": 0.0, "gpu_failed": False}
# "0" never tries the graphics card; otherwise it is used when its model was downloaded.
GPU = os.environ.get("HOUSEOS_VOICE_GPU", "auto") != "0"


def cpu_model():
    """HOUSEOS_VOICE_MODEL, else "small"; "base" on ARM boards (Raspberry Pi) and computers with
    under 6 GB of memory, where "small" takes several seconds per sentence."""
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    weak = os.uname().machine in {"aarch64", "arm64", "armv7l"} or memory < 6 * 1024**3
    return os.environ.get("HOUSEOS_VOICE_MODEL") or ("base" if weak else "small")


def load():
    """GPU turbo model when the card has room; the CPU model (cpu_model) otherwise."""
    from faster_whisper import WhisperModel, download_model

    if state["model"] is not None:
        return state["model"]
    try:
        if not GPU or state["gpu_failed"]:
            raise RuntimeError("GPU not used")
        path = download_model("large-v3-turbo", cache_dir=str(MODELS), local_files_only=True)
        state["model"] = WhisperModel(path, device="cuda", compute_type="int8_float16")
        state["name"] = "large-v3-turbo@cuda"
    except Exception as exc:  # no CUDA, out of VRAM, or model missing: stay useful on CPU
        print("voice: GPU model unavailable, using CPU:", type(exc).__name__, flush=True)
        name = cpu_model()
        path = download_model(name, cache_dir=str(MODELS), local_files_only=True)
        threads = min(4, os.cpu_count() or 1)
        state["model"] = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=threads)
        state["name"] = name + "@cpu"
    return state["model"]


def prefetch(tries=144):
    """Docker: fetch the speech models once, in the background, so starting the house never
    waits on a download (native installs ship them and stay offline). Without internet, it
    tries again every 10 minutes for a day, then at the next start."""
    from faster_whisper import download_model

    gpu = ["large-v3-turbo"] if os.environ.get("HOUSEOS_VOICE_GPU") == "1" else []
    for _ in range(tries):
        state["preparing"] = True
        try:
            for name in [cpu_model(), *gpu]:
                download_model(name, cache_dir=str(MODELS))
            return
        except Exception as exc:
            print("voice: model download failed, retrying in 10 minutes:", type(exc).__name__, flush=True)
        finally:
            state["preparing"] = False
        time.sleep(600)


def unload_when_idle():
    while True:
        time.sleep(30)
        with lock:
            if state["model"] is not None and time.monotonic() - state["used"] > IDLE_SECONDS:
                state["model"] = state["name"] = None
                gc.collect()


def confident(text, segments, language_probability):
    """Clear enough to send without review: real words, no hiss or mumbling in between.
    ponytail: fixed Whisper thresholds; tune if residents see too many or too few auto-sends."""
    if len(text.split()) < 2 or not segments:
        return False
    logprob = sum(s.avg_logprob for s in segments) / len(segments)
    silence = max(s.no_speech_prob for s in segments)
    return logprob > -0.6 and silence < 0.4 and (language_probability or 0) >= 0.7


def device():
    """Where the next transcription runs: "gpu" once the card has proven itself or while it
    is still worth trying (its model is downloaded), otherwise "cpu"."""
    if state["name"]:
        return "gpu" if state["name"].endswith("@cuda") else "cpu"
    wanted = GPU and not state["gpu_failed"] and any(MODELS.glob("*large-v3-turbo*"))
    return "gpu" if wanted else "cpu"


def run(path, language):
    model = load()
    state["used"] = time.monotonic()
    segments, info = model.transcribe(
        str(path),
        language=language if language in LANGUAGES else None,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    segments = list(segments)
    state["used"] = time.monotonic()
    return segments, info


def transcribe(name, language):
    path = (INBOX / name).resolve()
    if path.parent != INBOX.resolve() or not path.is_file():
        return {"status": "failed", "code": "VOICE_FILE_MISSING"}
    try:
        with lock:
            try:
                segments, info = run(path, language)
            except Exception as exc:
                if not (state["name"] or "").endswith("@cuda"):
                    raise
                # A card that loads but cannot run (missing CUDA libraries, VRAM taken by a
                # game): drop it for this process and answer on the CPU instead.
                print("voice: GPU failed, switching to CPU:", type(exc).__name__, flush=True)
                state.update(model=None, name=None, gpu_failed=True)
                gc.collect()
                segments, info = run(path, language)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        return {
            "status": "completed",
            "text": text[:2000],
            "language": info.language,
            "duration": round(info.duration, 1),
            "model": state["name"],
            "confident": confident(text, segments, info.language_probability),
        }
    except Exception as exc:
        print("voice: transcription failed:", type(exc).__name__, flush=True)
        return {"status": "failed", "code": "VOICE_TRANSCRIPTION_FAILED"}
    finally:
        path.unlink(missing_ok=True)  # recordings never outlive their transcription


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            request = json.loads(self.rfile.readline(4096))
            if not isinstance(request, dict):
                raise ValueError("not a request")
            if request.get("command") == "transcribe":
                reply = transcribe(str(request.get("name", "")), request.get("language"))
            elif request.get("command") == "status":
                reply = {
                    "status": "ok",
                    "loaded": state["name"],
                    "device": device(),
                    "preparing": bool(state.get("preparing")),
                }
            else:
                reply = {"status": "failed", "code": "VOICE_UNKNOWN_COMMAND"}
        except (ValueError, OSError):
            reply = {"status": "failed", "code": "VOICE_BAD_REQUEST"}
        self.wfile.write(json.dumps(reply).encode() + b"\n")


def restart_when_asked():
    """Same as events.restart_on_request, kept here: this service runs without the app's
    libraries on native installs."""
    note = RUNTIME / "run" / "restart" / "voice"
    while True:
        time.sleep(2)
        try:
            note.unlink()
        except OSError:
            continue
        os._exit(75)


def main():
    if os.environ.get("HOUSEOS_STORAGE_CONTAINER") == "true":  # Control Room's restart note
        threading.Thread(target=restart_when_asked, daemon=True).start()
        threading.Thread(target=prefetch, daemon=True).start()
    INBOX.mkdir(mode=0o700, exist_ok=True)
    for stale in INBOX.iterdir():
        stale.unlink(missing_ok=True)
    SOCKET.unlink(missing_ok=True)
    threading.Thread(target=unload_when_idle, daemon=True).start()
    with socketserver.ThreadingUnixStreamServer(str(SOCKET), Handler) as server:
        os.chmod(SOCKET, 0o600)  # only the API (same service user) may ask
        server.serve_forever()


if __name__ == "__main__":
    main()
