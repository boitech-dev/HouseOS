import threading
import time
import unittest
from unittest.mock import patch
from houseos.worker import WorkerTasks


class ResponsiveWorkerTests(unittest.TestCase):
    def test_controls_run_while_metadata_and_preparation_are_blocked(self):
        release = threading.Event()
        metadata_entered, preparation_entered, controlled = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        jobs = {"metadata": True, "control": False}

        def claim(_, kinds):
            if "music.control" in kinds and jobs["control"]:
                jobs["control"] = False
                return ("control",)
            if "music.metadata" in kinds and jobs["metadata"]:
                jobs["metadata"] = False
                return ("metadata",)

        def run(job):
            if job == ("metadata",):
                metadata_entered.set()
                release.wait(5)
            else:
                controlled.set()

        def prepare():
            preparation_entered.set()
            release.wait(5)

        tasks = WorkerTasks()
        try:
            with (
                patch("houseos.worker.cancel_removed_downloads"),
                patch("houseos.worker.claim", claim),
                patch("houseos.worker.run_job", run),
                patch("houseos.worker.advance", prepare),
                patch("houseos.worker.prefetch_next", prepare),
            ):
                tasks.tick("owner")
                self.assertTrue(metadata_entered.wait(1))
                self.assertTrue(preparation_entered.wait(1))
                jobs["control"] = True
                started = time.monotonic()
                tasks.tick("owner")
                self.assertTrue(controlled.is_set())
                self.assertLess(time.monotonic() - started, 0.2)
                self.assertFalse(release.is_set())
        finally:
            release.set()
            tasks.close()

    def test_cancelled_generation_cannot_load_after_slow_fetch(self):
        import tempfile
        from pathlib import Path
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from types import SimpleNamespace
        from houseos.db import Base
        from houseos.models import User
        from houseos.music import QueueState, QueueItem
        from houseos.worker import advance

        entered, release = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as temporary:
            engine = create_engine("sqlite:///" + str(Path(temporary) / "worker.sqlite"))
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                db.add(
                    User(
                        id="resident",
                        name="Resident",
                        username="resident",
                        password_hash="unused",
                        role="resident",
                    )
                )
                db.add(QueueState(id=1, desired="playing"))
                db.add(
                    QueueItem(
                        id="source",
                        owner_id="resident",
                        source_url="https://www.youtube.com/watch?v=abcdefghijk",
                        position=1,
                        status="ready",
                    )
                )
                db.commit()

            def fetch(*args, **kwargs):
                entered.set()
                release.wait(3)
                return {"status": "completed"}

            with (
                patch("houseos.worker.SessionLocal", lambda: Session(engine, expire_on_commit=False)),
                patch(
                    "houseos.worker.settings",
                    SimpleNamespace(audio_enabled=True, runtime_root=Path(temporary)),
                ),
                patch("houseos.worker.fetch", fetch),
                patch("houseos.worker.bridge") as player,
            ):
                thread = threading.Thread(target=advance)
                thread.start()
                self.assertTrue(entered.wait(1))
                with Session(engine) as db:
                    q = db.get(QueueState, 1)
                    q.desired, q.current_id = "paused", None
                    db.commit()
                release.set()
                thread.join(2)
                self.assertFalse(thread.is_alive())
                player.assert_not_called()
                # A song an earlier pass left "resolving" is tried again, not waited on forever.
                with Session(engine) as db:
                    q = db.get(QueueState, 1)
                    q.desired, q.current_id = "playing", "source"
                    db.get(QueueItem, "source").status = "resolving"
                    db.commit()
                player.return_value = {"status": "command_sent"}
                advance()
                self.assertEqual(player.call_args.args[0], "load")
                with Session(engine) as db:
                    self.assertEqual(db.get(QueueItem, "source").status, "buffering")
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
