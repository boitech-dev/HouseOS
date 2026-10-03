"""The sign-in crest: a square within a square.
Night (default): a block of concrete in shade, a deep square opening and the day beyond it; the
sun behind the block throws the opening's square of light on the floor in front of it.
Day (VARIANT=light): the same block in cream daylight, the opening the one ink void, its shadow
on the floor."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *

W, H = int(os.environ.get("W", 320)), int(os.environ.get("H", 320))
DAY = os.environ.get("VARIANT") == "light"
reset(ambient=0.3 if DAY else 0.035)
block = box((2.0, 1.0, 2.0), (0, 0.5, 1.0), concrete(0.8 if DAY else 0.5, "block", scale=2.2, mottle=0.6), "block")
holes = []
for x in (-0.62, 0.62):
    for z in (0.38, 1.62):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.028, depth=0.06, location=(x, 0, z), rotation=(radians(90), 0, 0), vertices=24)
        holes.append(bpy.context.active_object)
cut(block, holes)
cut(block, [box((0.72, 3, 0.72), (0.0, 0.5, 1.0))])
box((40, 40, 0.2) if DAY else (20, 13.0, 0.2), (0, 0, -0.1) if DAY else (0, -3.0, -0.1), concrete(0.8 if DAY else 0.45, "floor", 1.2, mottle=0.15 if DAY else 0.5), "floor")
if DAY:
    box((0.72, 0.9, 0.72), (0, 0.56, 1.0), black(), "void")  # the opening: nothing but depth, ink
    sun(Vector((0.7, -0.8, 1.0)), strength=2.6, angle=0.08)
else:
    sky = bpy.data.materials.new("sky")
    sky.use_nodes = True
    e = sky.node_tree.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*SUN_COLOUR, 1)
    e.inputs["Strength"].default_value = 2.2
    sky.node_tree.links.new(e.outputs[0], sky.node_tree.nodes["Material Output"].inputs[0])
    glow = box((0.95, 0.02, 0.95), (0, 1.06, 1.0), sky, "beyond")
    glow.visible_shadow = False
    glow.visible_diffuse = False  # the day is seen through the opening, it lights nothing
    box((40, 0.2, 20), (0, 9, 5), black(), "night").visible_shadow = False  # beyond the floor: nothing
    # the sun behind the block, low: its square of light lands on the floor in front
    sun_from = Vector((0.12, 1.0, 0.55))
    openings((0, 0.5, 1.0), sun_from, [("rect", 0, 0, 0.72, 0.72)], distance=4)
    sun(sun_from, strength=6.0, angle=0.08)
if DAY:
    camera(location=(-2.2, -12, 7.0), look_at=(0, 0, 0.8), lens=118)
else:
    camera(location=(-0.8, -14, 5.2), look_at=(0, 0, 0.75), lens=118)
finish(out("crest.png"), W, H, samples=int(os.environ.get("S", 256)))
