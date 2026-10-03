"""One bounded network producer. The player only receives an owned local FIFO."""

import os
import selectors
import signal
import subprocess
import threading
import time
from pathlib import Path
from uuid import UUID

from .atomic import write_json

LIMIT = 400 * 1024**2
ACTIVE = {}
LOCK = threading.Lock()
WRITE_LOCK = threading.Lock()


def manifest(root, identity, data):
    with WRITE_LOCK:  # the last update wins
        write_json(root / (identity + ".live.json"), data, 0o640)


def snapshot(state):
    return {key: state[key] for key in ["item_id", "expires_at", "state", "bytes"]}


def pump(root, state, args):
    process, fifo_fd = None, None
    try:
        # Wait only for the intended local reader; never let fifo.open block a worker.
        wait_until = time.monotonic() + 30
        first_byte = 90  # YouTube's player challenge can take a while before the first byte
        while time.monotonic() < wait_until and not state["stop"].is_set():
            try:
                fifo_fd = os.open(
                    root / (state["item_id"] + ".media"), os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW
                )
                break
            except OSError:
                time.sleep(0.1)
        if fifo_fd is None:
            state["state"], state["code"] = "failed", "LIVE_READER_NOT_READY"
            return
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/nonexistent"},
        )
        state["state"] = "streaming"
        manifest(root, state["item_id"], snapshot(state))
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        last_data = time.monotonic()
        try:
            while not state["stop"].is_set() and time.time() < state["expires_at"]:
                events = selector.select(0.2)
                if not events:
                    if time.monotonic() - last_data > (first_byte if not state["bytes"] else 45):
                        state["state"], state["code"] = "failed", "LIVE_SOURCE_STALLED"
                        break
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    state["state"] = "stopped" if process.wait(timeout=2) == 0 else "failed"
                    state["code"] = "LIVE_ENDED" if state["state"] == "stopped" else "LIVE_SOURCE_FAILED"
                    break
                last_data = time.monotonic()
                state["bytes"] += len(chunk)
                if state["bytes"] > LIMIT:
                    state["state"], state["code"] = "expired", "LIVE_BYTE_LIMIT"
                    break
                offset = 0
                while (
                    offset < len(chunk) and not state["stop"].is_set() and time.time() < state["expires_at"]
                ):
                    try:
                        offset += os.write(fifo_fd, chunk[offset:])
                    except BlockingIOError:
                        time.sleep(0.1)
            else:
                state["state"], state["code"] = (
                    ("stopped", "LIVE_STOPPED")
                    if state["stop"].is_set()
                    else ("expired", "LIVE_LEASE_EXPIRED")
                )
        finally:
            selector.close()
    except BrokenPipeError:
        state["state"], state["code"] = "stopped", "LIVE_READER_CLOSED"
    except (OSError, subprocess.SubprocessError):
        state["state"], state["code"] = "failed", "LIVE_SOURCE_FAILED"
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        if fifo_fd is not None:
            os.close(fifo_fd)
        manifest(root, state["item_id"], snapshot(state))


def execute(root: Path, action: str, item_id: str, args=None):
    identity = str(UUID(item_id))
    with LOCK:
        state = ACTIVE.get(identity)
        if action == "live_start":
            if state:
                if state["state"] in {"waiting", "streaming"}:
                    return {"status": "completed", **snapshot(state)}
                # Replaying a finished stream (repeat, recovery): a fresh pipe; any old
                # reader keeps its own handle on the unlinked one.
                del ACTIVE[identity]
                old = root / (identity + ".media")
                if old.is_fifo():
                    old.unlink()
            if any(value["state"] in {"waiting", "streaming"} for value in ACTIVE.values()):
                return {"status": "failed", "code": "LIVE_DESTINATION_BUSY"}
            if len(ACTIVE) > 100:
                for key in list(ACTIVE):
                    if ACTIVE[key]["state"] not in {"waiting", "streaming"}:
                        del ACTIVE[key]
            target = root / (identity + ".media")
            # A leftover FIFO belongs to an interrupted generation: never reuse silently.
            if target.exists() or target.is_symlink():
                return {"status": "failed", "code": "LIVE_RESOURCE_EXISTS"}
            os.mkfifo(target, 0o640)
            state = {
                "item_id": identity,
                "expires_at": time.time() + 3600,
                "state": "waiting",
                "bytes": 0,
                "stop": threading.Event(),
            }
            ACTIVE[identity] = state
            manifest(root, identity, snapshot(state))
            threading.Thread(target=pump, args=(root, state, args), daemon=True).start()
            return {"status": "completed", **snapshot(state)}
        if not state:
            return {"status": "failed", "code": "LIVE_SESSION_UNAVAILABLE"}
        if action == "live_stop":
            state["stop"].set()
            return {"status": "accepted", "item_id": identity}
        if action == "live_renew":
            if state["state"] not in {"waiting", "streaming"}:
                return {"status": "failed", "code": "LIVE_ALREADY_FINISHED"}
            state["expires_at"] = time.time() + 3600
            manifest(root, identity, snapshot(state))
            return {"status": "completed", **snapshot(state)}
        return {"status": "observed", **snapshot(state), "code": state.get("code")}
