"""Every page's wall: béton brut on its shuttering grid, one square window's patch of sun."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *

W, H = int(os.environ.get("W", 1600)), int(os.environ.get("H", 900))
reset(ambient=0.12)
wall = box((12, 0.4, 7), (0, 0.2, 0), concrete(0.5, "wall", seams=(1.8, 0.9)), "wall")
cut(wall, tie_holes(-6, 6, -3.5, 3.5, 0.0))
sun_from = Vector((-0.75, -0.8, 0.9)).normalized()
opening((1.55, 0, 0.55), sun_from, size=(1.25, 1.25), turn=0.0, distance=5)
sun(sun_from, strength=7.0, angle=0.35)
camera(location=(0.0, -10, 0.0), look_at=(0.0, 0, 0.0), ortho=7.2)
finish(out("page.png"), W, H, samples=int(os.environ.get("S", 96)))
