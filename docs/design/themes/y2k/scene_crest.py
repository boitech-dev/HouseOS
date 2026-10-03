"""The sign-in crest: a chrome four-point star inside a clear Bondi orb, a chrome ring round it,
a little sparkle. 320 x 320, transparent."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import ART, camera, chrome, finish, plastic, shape, star, studio  # noqa: E402

import bpy  # noqa: E402

r = math.radians
studio()
bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, location=(0, 0, 0))
orb = bpy.context.active_object
orb.scale = (1.0, 1.0, 1.0)
bpy.ops.object.shade_smooth()
orb.data.materials.append(plastic((0.35, 0.8, 0.95), roughness=0.03, transmission=1.0))
star(outer=0.72, inner=0.14, depth=0.2, material=chrome(), location=(0, 0, 0), rotation=(r(90), r(8), 0))
bpy.ops.mesh.primitive_torus_add(major_segments=96, minor_segments=16, major_radius=1.28, minor_radius=0.045, location=(0, 0, 0), rotation=(r(72), r(-18), 0))
bpy.ops.object.shade_smooth()
bpy.context.active_object.data.materials.append(chrome())
star(outer=0.2, inner=0.045, depth=0.06, material=chrome(), location=(1.05, -0.9, 0.95), rotation=(r(90), 0, 0))
camera(location=(0, -6.2, 0.45), look_at=(0, 0, 0.02), lens=60)
finish(str(ART / "crest.webp"), 320, 320, samples=160, transparent=True)
