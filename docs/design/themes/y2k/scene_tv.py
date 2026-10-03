"""The Watch room's TV: a clear Bondi CRT on chrome feet, its picture a soft blue glow. 480 x 360."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import ART, camera, crt, finish, studio  # noqa: E402

studio()
crt(0, 0, 0, 1.0, turn=-24)
camera(location=(1.4, -5.2, 1.1), look_at=(0, 0, 0.25), lens=50)
finish(str(ART / "tv.webp"), 480, 360, samples=160, transparent=True)
