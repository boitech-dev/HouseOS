"""One replaceable volume fade, shared by the private audio bridge."""

import math
import threading
import time


class VolumeRamp:
    def __init__(self, read, write, clock=time.monotonic):
        self.read, self.write, self.clock = read, write, clock
        self.lock = threading.Condition()
        self.target = None
        self.error = False
        self.thread = None

    def request(self, target):
        if not math.isfinite(target):
            raise ValueError("Invalid volume")
        with self.lock:
            self.start = float(self.read())
            self.started = self.clock()
            self.target = target
            self.error = False
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, name="volume-fade", daemon=True)
                self.thread.start()
            self.lock.notify()

    def cancel(self):
        with self.lock:
            self.target = None
            self.error = False

    def state(self):
        with self.lock:
            return {"volume_target": self.target, "volume_fade_failed": self.error}

    def step(self):
        # Called under the same lock as retarget/cancel: no late old-target writes.
        if self.target is None:
            return
        fraction = min(1.0, max(0.0, (self.clock() - self.started) / 0.35))
        eased = fraction * fraction * (3 - 2 * fraction)
        self.write(self.start + (self.target - self.start) * eased)
        if fraction >= 1:
            self.target = None

    def run(self):
        with self.lock:
            while True:
                self.lock.wait_for(lambda: self.target is not None)
                try:
                    self.step()
                except (OSError, ValueError, TypeError):
                    self.target, self.error = None, True
                self.lock.wait(timeout=0.02)
