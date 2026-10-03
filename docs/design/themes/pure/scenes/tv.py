"""The TV's frame: a screen set deep in a block of concrete, its glow on the reveals."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *

W, H = int(os.environ.get("W", 480)), int(os.environ.get("H", 360))
reset(ambient=0.05)
block = box((3.2, 1.0, 2.4), (0, 0.5, 0), concrete(0.5, "block", scale=2.0), "block")
holes = []
for x in (-1.36, 1.36):
    for z in (-0.95, 0.95):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.06, location=(x, 0, z), rotation=(radians(90), 0, 0), vertices=24)
        holes.append(bpy.context.active_object)
cut(block, holes)
cut(block, [box((2.5, 3, 1.42), (0.0, 0.5, 0.12))])
glow = bpy.data.materials.new("screen")
glow.use_nodes = True
e = glow.node_tree.nodes.new("ShaderNodeEmission")
e.inputs["Color"].default_value = (0.86, 0.88, 0.9, 1)
e.inputs["Strength"].default_value = 1.4
glow.node_tree.links.new(e.outputs[0], glow.node_tree.nodes["Material Output"].inputs[0])
box((2.6, 0.02, 1.5), (0, 0.8, 0.12), glow, "screen")
sun(Vector((-1.0, -0.5, 0.9)), strength=0.9, angle=0.5)
camera(location=(-0.9, -12, 0.8), look_at=(0, 0.3, 0), lens=100)
finish(out("tv.png"), W, H, samples=int(os.environ.get("S", 128)), transparent=True)
