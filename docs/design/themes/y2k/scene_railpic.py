"""The rail's picture, in the hero's language: a big rainbow disc and a chrome blob behind the
playlist window (make.py frosts that window so the room names read), a chain of chrome and candy
beads under the house's name, a chrome star. It stops above the rail's foot (the flip phone
and the egg sit there), fading out. Transparent ground, rendered
into $Y2K_FRAMES/railpic.png at 231 x 460 (100 px to a unit, orthographic); make.py composes each
scheme's version (rail-night.png / rail-day.png)."""

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import camera, chrome, finish, iridescent, metaball, plastic, shape, star, studio  # noqa: E402

import bpy  # noqa: E402

r = math.radians
OUT = Path(os.environ.get("Y2K_FRAMES", "/tmp/y2k-frames"))
OUT.mkdir(parents=True, exist_ok=True)
W, H = 231, 460


def at(x, y, depth=0.0):
    """Pixel coordinates (from the top left) to the scene: 100 px a unit, facing the camera."""
    return ((x - W / 2) / 100, depth, (H / 2 - y) / 100)


studio()
# The disc behind the window, tilted, its rim showing below it.
bpy.ops.mesh.primitive_cylinder_add(vertices=128, location=at(150, 255, 1.0), rotation=(r(72), r(-24), r(8)))
disc = bpy.context.active_object
disc.scale = (1.75, 1.75, 0.02)
disc.data.materials.append(iridescent())
bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_torus_add(major_segments=64, location=at(150, 255, 0.9), rotation=(r(72), r(-24), r(8)), major_radius=0.45, minor_radius=0.05)
bpy.context.active_object.data.materials.append(plastic((0.92, 0.96, 1.0), transmission=1.0))
# A chrome blob low at the left of the window.
metaball([(-0.8, 0.2, 1.05, 0.5), (-0.45, 0.2, 0.8, 0.36), (-1.0, 0.2, 0.7, 0.3)], material=chrome(), resolution=0.03)
# The bead chain under the name, a star at the top right.
candy = [(0.55, 0.2, 0.85), (1.0, 0.4, 0.7), (0.3, 0.85, 1.0), (0.55, 1.0, 0.4)]
for i, x in enumerate(range(16, 220, 13)):
    mat = chrome() if i % 2 == 0 else plastic(candy[(i // 2) % 4], transmission=0.8)
    shape("sphere", size=0.045, location=at(x, 55), material=mat)
star(outer=0.16, inner=0.035, depth=0.05, material=chrome(), location=at(206, 32, -0.2), rotation=(r(90), r(10), 0))
camera(location=(0, -10, 0), look_at=(0, 0, 0), ortho=W / 100)
bpy.context.scene.camera.data.sensor_fit = "HORIZONTAL"
finish(str(OUT / "railpic.png"), W, H, samples=128, transparent=True)
