import time
from concurrent.futures import ThreadPoolExecutor
from .db import SessionLocal
from .events import failure_site, heartbeat
from .cinema_prepare import process_one_preparation
from .cinema_jobs import process_one_operation


def prepare():
    with SessionLocal() as db:
        process_one_preparation(db)


def web():
    """Watch → Web: read, download and play waiting links, one at a time (cinema_web)."""
    from .cinema_web import process_one_web

    with SessionLocal() as db:
        while process_one_web(db):
            db.expire_all()


def main():
    from .events import restart_on_request

    from .cinema_web import recover

    restart_on_request("cinema-worker")
    with SessionLocal() as db:
        recover(db)
    # One bounded preparation lane; discovery must not wait for a whole film. Web videos have
    # their own lane: an hour-long download never holds up a film.
    with (
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="cinema-preparation") as pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="cinema-web") as web_pool,
    ):
        pending = downloading = None
        while True:
            try:
                if pending is None or pending.done():
                    if pending is not None:
                        try:
                            pending.result()
                        except Exception as exc:
                            print("cinema_preparation_failed", failure_site(exc), flush=True)
                    pending = pool.submit(prepare)
                if downloading is None or downloading.done():
                    if downloading is not None:
                        try:
                            downloading.result()
                        except Exception as exc:
                            print("cinema_web_failed", failure_site(exc), flush=True)
                    downloading = web_pool.submit(web)
                with SessionLocal() as db:
                    busy = process_one_operation(db)
                heartbeat("cinema_worker")
            except Exception as exc:
                busy = False
                print("cinema_operation_failed", failure_site(exc), flush=True)
            time.sleep(0.2 if busy else 2)  # right after a job, its follow-up is usually waiting


if __name__ == "__main__":
    main()
