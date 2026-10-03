from .models import Event


def emit(db, topic: str, payload: dict, user_id: str | None = None):
    event = Event(topic=topic, payload=payload, user_id=user_id)
    db.add(event)
    return event


def failure_site(exc: BaseException) -> str:
    """Exception type and code locations only: messages can carry URLs or credentials."""
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)
    # The deepest HouseOS frames say what failed; the library ones only say how.
    ours = [f for f in frames if "/houseos/" in f.filename and "site-packages" not in f.filename][-3:]
    ours = ours or frames[-3:]
    return (
        type(exc).__name__
        + " at "
        + " <- ".join(f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno}:{f.name}" for f in reversed(ours))
    )


def heartbeat(name: str, every: float = 15.0, _last: dict = {}):  # noqa: B006 (per-process memo)
    """Tell Control Room this background service is alive; at most one write per `every` s."""
    import time

    if time.monotonic() - _last.get(name, -every) < every:
        return
    _last[name] = time.monotonic()
    from .db import SessionLocal, utcnow
    from .models import Integration

    with SessionLocal() as db:
        row = db.get(Integration, name + "_heartbeat") or Integration(name=name + "_heartbeat")
        row.config = {"observed_at": utcnow().isoformat() + "Z"}
        db.merge(row)
        db.commit()


def restart_on_request(name: str):
    """Docker: Control Room restarts a service by leaving a note in the shared run folder;
    the service exits and its restart policy starts it again (no Docker access needed)."""
    import os
    import threading
    import time

    from .config import settings

    note = settings.runtime_root / "run" / "restart" / name

    def watch():
        while True:
            time.sleep(2)
            try:
                note.unlink()
            except OSError:
                continue
            print(f"restart requested from Control Room: {name}", flush=True)
            os._exit(75)  # non-zero: systemd's on-failure and Docker's policy both restart

    if settings.storage_container:
        threading.Thread(target=watch, daemon=True, name="restart-on-request").start()
