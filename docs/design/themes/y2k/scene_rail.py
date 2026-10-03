"""The rail's foot: a clear Bondi flip phone (its board, chips and battery showing through the shell,
a chrome barrel hinge, a bead strap ending in the crest's chrome star). Rendered as frames of
120 x 240 into $Y2K_FRAMES (make.py stitches them): frame 0 is the phone at rest, closed; the
others are the poke: it flips open, its LCD lights, a pixel heart beats, it folds shut again."""

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import camera, chrome, finish, glow, material, plastic, shape, star, studio  # noqa: E402

import bpy  # noqa: E402

r = math.radians
OUT = Path(os.environ.get("Y2K_FRAMES", "/tmp/y2k-frames"))
OUT.mkdir(parents=True, exist_ok=True)
studio()


def empty(name, location=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    e.location = location
    e.parent = parent
    return e


def under(obj, parent):
    obj.parent = parent
    return obj


root = empty("phone")
root.rotation_euler = (0, 0, r(-16))
hinge = empty("hinge", location=(0, -0.1, 0), parent=root)
shell = plastic((0.25, 0.72, 0.85), roughness=0.06, transmission=1.0, speckle=True)
board = material("matte", colour=(0.05, 0.32, 0.16), roughness=0.5)
chip = material("matte", colour=(0.02, 0.02, 0.03), roughness=0.3)
gold = material("brushed", colour=(0.95, 0.75, 0.35))


def half(parent, z, h, y=0.0):
    """A clear rounded slab with a board and chips inside, in the parent's space."""
    under(shape("cube", size=(0.4, 0.1, h / 2), location=(0, y, z), bevel=0.08, material=shell), parent)
    under(shape("cube", size=(0.32, 0.02, h / 2 * 0.86), location=(0, y + 0.03, z), material=board), parent)
    for cx, cz, w in ((-0.12, 0.35, 0.08), (0.1, 0.1, 0.1), (-0.08, -0.2, 0.06), (0.12, -0.4, 0.05)):
        under(shape("cube", size=(w, 0.025, w), location=(cx, y, z + cz * h / 2), material=chip), parent)
    for gx in (-0.14, 0.14):
        under(shape("cube", size=(0.012, 0.022, h / 2 * 0.7), location=(gx, y + 0.01, z), material=gold), parent)


# The body (keypad half), in the phone's space; the lid in the hinge's (modelled open, upright).
half(root, -0.74, 1.44)
under(shape("cube", size=(0.26, 0.03, 0.3), location=(0, 0.05, -0.9), material=material("brushed", colour=(0.7, 0.72, 0.78))), root)
for row in range(4):
    for col in (-1, 0, 1):
        under(shape("sphere", size=0.042, location=(col * 0.12, -0.11, -0.5 - row * 0.2), material=chrome()), root)
under(shape("sphere", size=(0.1, 0.05, 0.055), location=(0.0, -0.11, -0.25), material=plastic((1.0, 0.6, 0.15), transmission=0.5)), root)
half(hinge, 0.7, 1.36, y=0.1)
under(shape("cylinder", size=(0.1, 0.1, 0.22), location=(0, 0.0, 0.0), rotation=(0, r(90), 0), material=chrome()), hinge)
# The LCD on the lid's inner face: a dark bezel, the glass, a pixel heart.
under(shape("cube", size=(0.32, 0.015, 0.4), location=(0, -0.005, 0.78), bevel=0.03, material=material("matte", colour=(0.01, 0.01, 0.02))), hinge)
screen_off = glow((0.01, 0.04, 0.02), 0.6)
screen_on = glow((0.06, 0.4, 0.16), 0.9)
screen = under(shape("cube", size=(0.29, 0.015, 0.36), location=(0, -0.02, 0.78), bevel=0.02, material=screen_off), hinge)
lit = glow((0.6, 1.0, 0.4), 6)
heart = []
for px, pz in ((-0.1, 0.94), (0.1, 0.94), (-0.18, 0.86), (0.0, 0.86), (0.18, 0.86), (-0.1, 0.78), (0.1, 0.78), (0.0, 0.78),
               (-0.18, 0.94), (0.18, 0.94), (0.0, 0.7), (-0.1, 0.86), (0.1, 0.86)):
    heart.append(under(shape("cube", size=(0.045, 0.012, 0.045), location=(px, -0.04, pz), material=lit), hinge))
# The strap: beads down from the body's corner to the chrome star charm.
for i, (c, z) in enumerate((((0.55, 0.2, 0.85), -1.55), ((1.0, 0.4, 0.7), -1.7), ((0.3, 0.85, 1.0), -1.85))):
    under(shape("sphere", size=0.07, location=(0.24 + i * 0.015, 0.0, z), material=plastic(c, transmission=0.8)), root)
under(star(outer=0.22, inner=0.05, depth=0.07, material=chrome(), location=(0.3, 0.0, -2.1), rotation=(r(90), r(14), 0)), root)
camera(location=(0.15, -6.8, -0.3), look_at=(0.04, 0, -0.38), lens=62)

OPEN, SHUT = -8, 179
# (lid angle, screen lit, heart shown, heart scale): rest, flip open, light, beat twice, fold.
FRAMES = [(SHUT, 0, 0, 1), (130, 0, 0, 1), (70, 0, 0, 1), (10, 0, 0, 1), (OPEN, 1, 0, 1), (OPEN, 1, 1, 1),
          (OPEN, 1, 1, 1.35), (OPEN, 1, 1, 1), (OPEN, 1, 1, 1.35), (OPEN, 1, 1, 1), (60, 0, 0, 1), (140, 0, 0, 1)]  # fmt: skip
for i, (angle, on, show, beat) in enumerate(FRAMES):
    hinge.rotation_euler = (r(angle), 0, 0)
    screen.data.materials[0] = screen_on if on else screen_off
    for h in heart:
        h.hide_render = not show
        h.scale = (0.045 * beat, 0.012, 0.045 * beat)
    finish(str(OUT / f"phone-{i:02d}.png"), 120, 240, samples=96, transparent=True)
