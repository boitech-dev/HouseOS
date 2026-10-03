"""My Space: a Y2K bedroom corner, rendered twice: at night (room-night.webp, the dark skin: a
starry window, the lava lamp and the CRT lighting the room) and by day (room.webp, Bondi: a blue
sky with a cloud in the window, a pale lilac wall). A clear CRT with a pixel sunset on a white desk,
a lava lamp, a CD tower, a clear flip phone, a chrome star pinned up, a grape beanbag on a speckled
rug. 800 x 360 (the slot is 160 x 72, scaled)."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import ART, camera, chrome, crt, finish, glow, iridescent, light, material, plastic, shape, star, studio  # noqa: E402

import bpy  # noqa: E402

r = math.radians


def speckled(colour, dots=(1, 1, 1), scale_=60):
    """A matte material with confetti speckle (the rug)."""
    m = material("matte", colour=colour, roughness=0.95)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexVoronoi")
    noise.inputs["Scale"].default_value = scale_
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (*dots, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.09, (*colour, 1)
    nt.links.new(noise.outputs["Distance"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


def room(day):
    studio(strength=0.4 if day else 0.3)
    wall = material("matte", colour=(0.62, 0.55, 0.9) if day else (0.17, 0.12, 0.38), roughness=0.9)
    shape("plane", size=(8, 3, 1), location=(0, 2.0, 1.5), rotation=(r(90), 0, 0), material=wall)
    shape("plane", size=(8, 4, 1), location=(0, 0, -0.9), material=material("matte", colour=(0.5, 0.42, 0.7) if day else (0.22, 0.1, 0.36), roughness=0.95))
    shape("cylinder", size=(1.6, 1.1, 0.01), location=(1.9, 0.2, -0.89), material=speckled((0.55, 0.3, 0.85) if day else (0.35, 0.15, 0.55), (0.3, 0.9, 1.0)))
    # The window.
    sky = glow((0.35, 0.6, 1.0), 0.8) if day else glow((0.08, 0.1, 0.35), 1.0)
    shape("cube", size=(0.95, 0.02, 0.62), location=(2.4, 1.97, 1.55), material=sky)
    if day:
        for cx, cz, cr in ((2.2, 1.45, 0.16), (2.4, 1.5, 0.2), (2.6, 1.45, 0.15)):
            shape("sphere", size=(cr, 0.02, cr * 0.7), location=(cx, 1.94, cz), material=glow((1, 1, 1), 1.2))
    else:
        for sx, sz in ((2.0, 1.8), (2.6, 1.35), (2.9, 1.9), (2.2, 1.2), (2.75, 1.65)):
            shape("sphere", size=0.025, location=(sx, 1.94, sz), material=glow((1, 1, 1), 6))
    for dz in (0.64, -0.64):
        shape("cube", size=(1.0, 0.05, 0.035), location=(2.4, 1.95, 1.55 + dz), material=chrome())
    for dx in (0.98, -0.98, 0):
        shape("cube", size=(0.035, 0.05, 0.66), location=(2.4 + dx, 1.95, 1.55), material=chrome())
    if day:
        light("sun", location=(3, -2, 5), energy=0.8, colour=(1, 0.97, 0.92), look_at=(0, 1, 0), angle=4)
    # The desk and its things.
    shape("cube", size=(2.2, 0.8, 0.06), location=(-0.3, 0.9, 0.0), material=plastic((0.95, 0.95, 1.0), roughness=0.2, transmission=0.3), bevel=0.04)
    for lx in (-2.3, 1.7):
        shape("cylinder", size=(0.05, 0.05, 0.45), location=(lx, 0.9, -0.45), material=chrome())
    crt(-0.45, 1.0, 0.72, 0.62, turn=10)
    # Lava lamp.
    shape("cone", size=(0.28, 0.28, 0.3), location=(1.25, 0.9, 0.36), material=chrome())
    shape("cylinder", size=(0.2, 0.2, 0.5), location=(1.25, 0.9, 1.1), material=plastic((1.0, 0.45, 0.75), transmission=1.0))
    for bz, br in ((0.8, 0.13), (1.12, 0.09), (1.38, 0.07)):
        shape("sphere", size=br, location=(1.25, 0.9, bz), material=glow((1.0, 0.25, 0.55), 1.8))
    shape("cone", size=(0.21, 0.21, 0.14), location=(1.25, 0.9, 1.66), rotation=(r(180), 0, 0), material=chrome())
    light("point", location=(1.25, 0.5, 1.1), energy=40 if day else 60, colour=(1.0, 0.45, 0.65))
    # A clear flip phone lying open on the desk.
    for dy, rx in ((0.55, 0), (0.25, 20)):
        shape("cube", size=(0.13, 0.16, 0.02), location=(0.55, dy, 0.09 + (0.03 if rx else 0)), rotation=(r(rx), 0, r(20)), bevel=0.02,
              material=plastic((0.3, 0.75, 0.9), transmission=0.9))
    # A CD tower on the floor: clear jewel cases with rainbow discs inside.
    shape("cube", size=(0.08, 0.3, 1.0), location=(-2.55, 0.9, 0.1), material=chrome())
    for i in range(12):
        z = -0.8 + i * 0.15
        shape("cube", size=(0.36, 0.28, 0.06), location=(-2.2, 0.9, z), material=plastic((0.9, 0.95, 1.0), transmission=1.0))
        shape("cylinder", size=(0.12, 0.12, 0.012), location=(-2.2, 0.75, z), rotation=(r(90), 0, r(i * 20)), material=iridescent())
    # Wall star, beanbag.
    star(outer=0.32, inner=0.07, depth=0.1, material=chrome(), location=(-1.2, 1.9, 1.85), rotation=(r(90), r(10), 0))
    shape("sphere", size=(0.75, 0.65, 0.42), location=(1.9, 0.2, -0.55), material=plastic((0.55, 0.2, 0.85), roughness=0.1, transmission=0.2))
    light("point", location=(-0.45, 0.2, 0.8), energy=30, colour=(0.4, 0.9, 1.0))
    camera(location=(0.1, -5.0, 1.05), look_at=(0.1, 1.0, 0.75), lens=34)
    finish(str(ART / ("room.webp" if day else "room-night.webp")), 800, 360, samples=160)


room(day="--day" in sys.argv)
