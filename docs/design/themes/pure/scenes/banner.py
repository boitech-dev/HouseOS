"""A room's header: its own opening, its patch of light on the wall. ROOM picks the opening."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *

W, H = int(os.environ.get("W", 1800)), int(os.environ.get("H", 240))
ROOM = os.environ.get("ROOM", "default")
reset(ambient=0.12)
# a quiet wall (half the mottle): in a room's header the light is what is drawn, with the few
# form-tie holes it happens to fall on
wall = box((16, 0.4, 3), (0, 0.2, 0), concrete(0.5, "wall", mottle=0.5), "wall")
AT = (1.32, 0, 0.35)   # where the patch lands: 61 % of the width, in the band 16–64 px from the top
holes = []
for x in (AT[0] - 0.675, AT[0] - 0.225, AT[0] + 0.225, AT[0] + 0.675):
    for z in (AT[2] - 0.225, AT[2] + 0.225):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.018, depth=0.06, location=(x, 0, z),
                                            rotation=(radians(90), 0, 0), vertices=24)
        holes.append(bpy.context.active_object)
cut(wall, holes)
# every room's opening, in the screen's plane (metres); the patch lands to the right of centre
HOLES = {
    "default": [("rect", 0, 0, 0.1, 0.5)],
    "listen": [("rect", x, 0, 0.07, h) for x, h in ((-0.4, 0.14), (-0.2, 0.3), (0.0, 0.44), (0.2, 0.22), (0.4, 0.1))],
    "watch": [("rect", 0, 0, 0.9, 0.36)],
    "house": [("rect", x, y, 0.16, 0.16) for x in (-0.28, 0, 0.28) for y in (-0.14, 0.14)],
    "files": [("rect", 0, y, 1.0, 0.045) for y in (-0.2, -0.1, 0.0, 0.1, 0.2)],
    "games": [("rect", -0.14, 0.14, 0.28, 0.28), ("rect", 0.14, -0.14, 0.28, 0.28)],
    "me": [("disc", 0, 0, 0.44, 0.44)],
    "control": [("rect", 0, 0, 1.9, 0.025)],
    "smart-home": [("rect", 0, 0.07, 0.34, 0.34), ("rect", 0, -0.2, 0.34, 0.04)],
    "inbox": [("rect", 0, 0, 0.6, 0.07)],
    "party": [("rect", x * 0.13, y * 0.13, 0.06, 0.06) for x in range(-3, 4) for y in range(-2, 3) if (x + y) % 2 == 0],
    "ask": [("rect", 0, 0, 0.24, 0.24)],
}
sun_from = Vector((-0.45, -0.9, 0.5)).normalized()
K = 0.74
openings(AT, sun_from, [(k, x * K, y * K, w * K, h * K) for k, x, y, w, h in HOLES[ROOM]], distance=6)
sun(sun_from, strength=7.0, angle=0.12)
camera(location=(0.0, -10, 0.0), look_at=(0.0, 0, 0.0), ortho=12.0)
finish(out(f"banner-{ROOM}.png"), W, H, samples=int(os.environ.get("S", 96)))
