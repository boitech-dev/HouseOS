"""An empty state: a square of sun on a concrete floor, and in it the shadow of a small bird
sitting in the window, out of sight. Nothing here yet, but someone is about."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concrete import *
from mathutils import Matrix

W, H = int(os.environ.get("W", 192)), int(os.environ.get("H", 192))
reset(ambient=0.03)
box((60, 60, 0.2), (0, 0, -0.1), concrete(0.5, "floor", scale=1.6), "floor")
sun_from = Vector((-0.35, -0.45, 0.82)).normalized()
centre = opening((0, 0, 0), sun_from, size=(1.3, 1.3), distance=3.0)
# the bird, perched on the sill (the opening's lower edge), in profile: a flat silhouette in the
# window's plane, so its shadow is its outline. Only the shadow is ever seen.
rot = sun_from.to_track_quat("Z", "Y").to_matrix().to_4x4()
BIRD = [(-0.2, 0.02), (-0.17, 0.075), (-0.05, 0.14), (0.05, 0.195), (0.09, 0.235), (0.14, 0.235),
        (0.17, 0.215), (0.215, 0.2), (0.165, 0.19), (0.14, 0.16), (0.12, 0.09), (0.07, 0.04),
        (0.035, 0.03), (0.035, 0.0), (0.025, 0.0), (0.02, 0.028), (-0.02, 0.028), (-0.08, 0.035)]
mesh = bpy.data.meshes.new("bird")
k = 1.15
mesh.from_pydata([(x * k, y * k - 0.65, 0) for x, y in BIRD], [], [list(range(len(BIRD)))])
bird = bpy.data.objects.new("bird", mesh)
bpy.context.collection.objects.link(bird)
bird.modifiers.new("solid", "SOLIDIFY").thickness = 0.01
bird.matrix_world = Matrix.Translation(centre) @ rot @ Matrix.Translation((-0.05, 0, 0))
bird.visible_camera = False
sun(sun_from, strength=5.0, angle=0.25)
camera(location=(0.0, -1.2, 7.0), look_at=(0.0, 0.05, 0), lens=88)
finish(out("empty.png"), W, H, samples=int(os.environ.get("S", 128)))
