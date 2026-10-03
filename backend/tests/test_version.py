"""One version everywhere: every file that states it agrees with houseos.__version__."""

import json
import re
from pathlib import Path

from houseos import __version__

ROOT = Path(__file__).resolve().parents[2]
# This repository keeps the public root under packaging/; the public copy has it at its root.
DOCKER = ROOT / "packaging/docker" if (ROOT / "packaging/docker").is_dir() else ROOT
README = ROOT / "packaging/public/README.md" if (ROOT / "packaging/public").is_dir() else ROOT / "README.md"


def test_every_copy_of_the_version_agrees():
    short = ".".join(__version__.split(".")[:2])
    assert f'version = "{__version__}"' in (ROOT / "backend/pyproject.toml").read_text()
    assert json.loads((ROOT / "frontend/package.json").read_text())["version"] == __version__
    for name in ("docker-compose.yml", "compose.gpu.yml", "compose.helper.yml"):
        tags = re.findall(r"image: houseos[\w-]*:([\d.]+)", (DOCKER / name).read_text())
        assert tags and set(tags) == {short}, name
    readme = README.read_text()
    assert f"version-{__version__}-" in readme  # the badge
    assert f'RELEASE = "{short}"' in (ROOT / "frontend/src/whats_new.ts").read_text()
