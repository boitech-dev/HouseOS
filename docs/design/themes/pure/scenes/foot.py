"""The rail's foot: a slit window at the end of a corridor, the day beyond it, its line of sun
drawn along the floor towards you."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *

W, H = int(os.environ.get("W", 464)), int(os.environ.get("H", 480))
reset(ambient=0.01)
con = concrete(0.5, "foot", seams=(1.8, 0.9))
box((6, 12, 0.2), (0, -2, -0.1), concrete(0.45, "floor", 0.8), "floor")
back = box((6, 0.3, 5), (0, 4.15, 2.5), con, "back")
cut(back, [box((0.14, 1, 2.6), (0, 4.15, 1.3 + 0.0))])
box((0.3, 12, 5), (-1.2, -2, 2.5), con, "left")
box((0.3, 12, 5), (1.2, -2, 2.5), con, "right")
sky = bpy.data.materials.new("sky")
sky.use_nodes = True
e = sky.node_tree.nodes.new("ShaderNodeEmission")
e.inputs["Color"].default_value = (*SUN_COLOUR, 1)
e.inputs["Strength"].default_value = 6.0
sky.node_tree.links.new(e.outputs[0], sky.node_tree.nodes["Material Output"].inputs[0])
b = box((1, 0.02, 3), (0, 4.6, 1.4), sky, "beyond"); b.visible_shadow = False
sun(Vector((0.0, 1.0, 0.28)), strength=7.0, angle=0.3)
camera(location=(0.0, -2.5, 1.2), look_at=(0.0, 4, 1.0), lens=30)
finish(out("foot.png"), W, H, samples=int(os.environ.get("S", 128)))
