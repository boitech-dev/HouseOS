"""Frames for two pokes, into $Y2K_FRAMES (make.py stitches them):
- star-NN.png (80 x 80): the hero's chrome star (bottom-right of Home's picture, clear of the words), at rest then spinning a full turn;
- egg-NN.png (96 x 144): the keychain egg hanging from its ring, at rest then swinging and settling."""

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import camera, chrome, finish, keychain_egg, star, studio  # noqa: E402

import bpy  # noqa: E402

r = math.radians
OUT = Path(os.environ.get("Y2K_FRAMES", "/tmp/y2k-frames"))
OUT.mkdir(parents=True, exist_ok=True)

# The star.
studio()
s = star(outer=0.9, inner=0.17, depth=0.22, material=chrome(), location=(0, 0, 0), rotation=(r(90), 0, 0))
camera(location=(0, -4.3, 0.2), look_at=(0, 0, 0), lens=60)
for i in range(12):
    s.rotation_euler = (r(90), 0, r(14 + i * 30))
    finish(str(OUT / f"star-{i:02d}.png"), 80, 80, samples=96, transparent=True)

# The egg: everything parented to a pivot at the top of its ring.
studio()
before = set(bpy.data.objects)
keychain_egg(0, 0, -0.35, 1.0, tilt=-6)
pivot = bpy.data.objects.new("pivot", None)
bpy.context.collection.objects.link(pivot)
pivot.location = (0.05, 0, 0.93)
bpy.context.view_layer.update()
for o in set(bpy.data.objects) - before - {pivot}:
    o.parent = pivot
    o.matrix_parent_inverse = pivot.matrix_world.inverted()
camera(location=(0.1, -5.6, -0.2), look_at=(0.02, 0, -0.25), lens=60)
for i, a in enumerate((0, 16, 24, 12, -10, -20, -12, 6, 12, 4, -4, 0)):
    pivot.rotation_euler = (0, r(a), 0)
    finish(str(OUT / f"egg-{i:02d}.png"), 96, 144, samples=96, transparent=True)
