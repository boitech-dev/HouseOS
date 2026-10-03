"""My Space: a small concrete room, one square window, the sun's patch on the floor and on a
low bench. The person's room: quiet, with a place to sit in the light."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *

W, H = int(os.environ.get("W", 800)), int(os.environ.get("H", 360))
reset(ambient=0.03)
con = concrete(0.5, "room", seams=(1.8, 0.9), mottle=0.5)
box((8, 6.3, 0.2), (0, 1.15, -0.1), concrete(0.45, "floor", 0.8), "floor")
back = box((8, 0.3, 4), (0, 4.15, 2), con, "back")
cut(back, [box((1.3, 1, 1.3), (-1.6, 4.15, 2.0))])
sky = bpy.data.materials.new("sky")
sky.use_nodes = True
e = sky.node_tree.nodes.new("ShaderNodeEmission")
e.inputs["Color"].default_value = (*SUN_COLOUR, 1)
e.inputs["Strength"].default_value = 1.6
sky.node_tree.links.new(e.outputs[0], sky.node_tree.nodes["Material Output"].inputs[0])
beyond = box((1.6, 0.02, 1.6), (-1.6, 4.6, 2.0), sky, "beyond")
beyond.visible_shadow = False
box((0.3, 6.3, 4), (-3.4, 1.15, 2), con, "left")
box((0.3, 6.3, 4), (3.4, 1.15, 2), con, "right")
box((8, 6.3, 0.3), (0, 1.15, 4.1), con, "ceiling")
box((2.4, 0.6, 0.42), (-0.2, 2.5, 0.21), con, "bench")
sun(Vector((-0.45, 1.0, 1.25)), strength=8.0, angle=0.3)
camera(location=(0.0, -3.2, 1.5), look_at=(0.0, 4, 1.25), lens=26)
finish(out("room.png"), W, H, samples=int(os.environ.get("S", 128)))
