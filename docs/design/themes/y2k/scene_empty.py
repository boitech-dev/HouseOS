"""The empty state: the keychain egg alone, a smile on its LCD. 192 x 192, transparent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import ART, camera, finish, keychain_egg, studio  # noqa: E402

studio()
keychain_egg(0, 0, -0.1, 1.0, tilt=-10)
camera(location=(0.25, -5.4, 0.5), look_at=(0, 0, 0.18), lens=60)
finish(str(ART / "empty.webp"), 192, 192, samples=160, transparent=True)
