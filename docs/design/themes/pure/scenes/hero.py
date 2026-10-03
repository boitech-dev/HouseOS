"""Home's hero: a blade of low sun through a roof slit, across a cantilevered concrete stair."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *
from mathutils import Vector

W, H = int(os.environ.get("W", 1320)), int(os.environ.get("H", 440))
reset()
con = concrete(0.52)
wall = box((10, 0.4, 5), (1, 0.2, 2.5), concrete(0.52, "wall", seams=(1.8, 0.9)), "wall")
cut(wall, tie_holes(-4, 6, 0, 5, 0.0))
box((10, 8, 0.2), (1, -4, -0.1), concrete(0.45, "floor", 0.8), "floor")
# the stair: treads cantilevered from the wall, rising to the right
for i in range(14):
    box((0.34, 0.95, 0.07), (0.4 + i * 0.3, -0.475, 0.2 + i * 0.19), con, f"tread{i}")
# the one opening: a long slit in a screen between the sun and the room (never in frame)
sun_from = Vector((-0.55, -0.9, 1.25)).normalized()
opening((1.8, 0, 1.4), sun_from, size=(0.24, 20), turn=0.8)
sun(sun_from, strength=9.0, angle=0.25)
if os.environ.get('HAZE', '1') == '1':
    haze((12, 1.9, 5.4), (1, -1.0, 2.75), density=float(os.environ.get('DENSITY', 0.05)))
camera(location=(0.4, -7.5, 1.35), look_at=(0.4, 0, 1.45), lens=34)
finish(out("hero.png"), W, H, samples=int(os.environ.get("S", 96)))
