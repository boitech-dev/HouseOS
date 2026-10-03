import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from uuid import uuid4
from houseos import fetcher_live as live


class LiveProducerTests(unittest.TestCase):
    def wait_for(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(condition())

    def test_fifo_streams_only_local_bytes_and_lease_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, identity = Path(temporary), str(uuid4())
            result = live.execute(
                root,
                "live_start",
                identity,
                [
                    sys.executable,
                    "-c",
                    'import os,time; os.write(1,b"synthetic-live-fixture"); time.sleep(10)',
                ],
            )
            self.assertEqual(result["status"], "completed")
            self.assertLessEqual(result["expires_at"], time.time() + 3600)
            fifo = os.open(root / (identity + ".media"), os.O_RDONLY | os.O_NONBLOCK)
            try:
                self.wait_for(lambda: live.ACTIVE[identity]["state"] == "streaming")
                received = b""
                deadline = time.monotonic() + 3
                while not received and time.monotonic() < deadline:
                    try:
                        received = os.read(fifo, 100)
                    except BlockingIOError:
                        pass
                    time.sleep(0.02)
                self.assertEqual(received, b"synthetic-live-fixture")
                manifest = json.loads((root / (identity + ".live.json")).read_text())
                self.assertEqual(set(manifest), {"item_id", "expires_at", "state", "bytes"})
                self.assertEqual(live.execute(root, "live_renew", identity)["status"], "completed")
                other = live.execute(root, "live_start", str(uuid4()), [])
                self.assertEqual(other["code"], "LIVE_DESTINATION_BUSY")
                live.execute(root, "live_stop", identity)
                self.wait_for(lambda: live.ACTIVE[identity]["state"] == "stopped")
            finally:
                os.close(fifo)
                live.ACTIVE[identity]["stop"].set()
                self.wait_for(lambda: live.ACTIVE[identity]["state"] not in {"waiting", "streaming"})
                time.sleep(0.1)

    def test_expired_lease_terminates_producer_and_cannot_renew(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, identity = Path(temporary), str(uuid4())
            live.execute(root, "live_start", identity, [sys.executable, "-c", "import time; time.sleep(10)"])
            fifo = os.open(root / (identity + ".media"), os.O_RDONLY | os.O_NONBLOCK)
            try:
                self.wait_for(lambda: live.ACTIVE[identity]["state"] == "streaming")
                live.ACTIVE[identity]["expires_at"] = time.time() - 1
                self.wait_for(lambda: live.ACTIVE[identity]["state"] == "expired")
                self.assertEqual(live.execute(root, "live_renew", identity)["code"], "LIVE_ALREADY_FINISHED")
            finally:
                os.close(fifo)
                live.ACTIVE[identity]["stop"].set()
                time.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
