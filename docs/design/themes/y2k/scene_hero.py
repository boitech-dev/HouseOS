"""Home's hero: chrome blobs, a clear Bondi keychain egg on a grape ring, an iridescent disc and
chrome sparkle stars, floating, rendered twice: over a glowing matrix-grid floor that reflects them (hero-night.webp, the dark
skin) and among soft lilac-white clouds (hero.webp, Bondi). Transparent around them; 1440 x 480;
the left 40 % stays empty because the greeting sits there.

    blender -b --factory-startup -P docs/design/themes/y2k/scene_hero.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio import ART, keychain_egg, camera, chrome, finish, glow, iridescent, metaball, plastic, principled, shape, star, studio  # noqa: E402

import bpy  # noqa: E402

studio()
r = math.radians

# The big chrome blob, centre right: four balls melted together.
metaball(
    [(1.8, 0.4, 0.1, 1.0), (2.6, 0.2, 0.55, 0.68), (1.25, 0.1, -0.45, 0.58), (2.5, 0.0, -0.4, 0.48)],
    material=chrome(),
    resolution=0.04,
)

# The keychain egg: clear Bondi shell, a dark LCD window lit green, three chrome keys.
egg_x, egg_z = 0.4, -0.05
keychain_egg(egg_x, -0.5, egg_z, 1.0, tilt=-8)

# The disc behind, tilted, catching the rainbow.
bpy.ops.mesh.primitive_cylinder_add(vertices=128, location=(3.3, 1.4, 0.15), rotation=(r(58), r(-22), r(14)))
disc = bpy.context.active_object
disc.scale = (1.05, 1.05, 0.016)
disc.data.materials.append(iridescent())
bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_cylinder_add(vertices=64, location=(3.3, 1.4, 0.15), rotation=(r(58), r(-22), r(14)))
hole = bpy.context.active_object
hole.scale = (0.16, 0.16, 0.2)
cut = disc.modifiers.new("hole", "BOOLEAN")
cut.object, cut.operation = hole, "DIFFERENCE"
hole.hide_render = True
bpy.ops.mesh.primitive_torus_add(major_segments=64, location=(3.3, 1.4, 0.15), rotation=(r(58), r(-22), r(14)), major_radius=0.3, minor_radius=0.035)
bpy.context.active_object.data.materials.append(plastic((0.92, 0.96, 1.0), transmission=1.0))
bpy.ops.object.shade_smooth()

# Sparkles: two small chrome stars (the big one is a piece of its own that spins when clicked).
star(outer=0.3, inner=0.06, depth=0.1, material=chrome(), location=(-0.55, -0.9, 0.72), rotation=(r(90), r(-10), 0))
star(outer=0.22, inner=0.05, depth=0.08, material=chrome(), location=(1.2, -1.3, -0.72), rotation=(r(90), r(20), 0))

# Beads: a chrome one and a clear one.
shape("sphere", size=0.2, location=(3.05, -1.0, -0.7), material=chrome())
shape("sphere", size=0.2, location=(2.0, -0.6, -0.95), material=plastic((0.8, 0.4, 0.9)))



def grid_floor():
    """A black glass floor with cyan grid lines, fading out with distance (alpha)."""
    m = bpy.data.materials.new("grid")
    m.use_nodes = True
    nt = m.node_tree
    n, ln = nt.nodes, nt.links
    p = n["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.01, 0.01, 0.03, 1)
    p.inputs["Roughness"].default_value = 0.12
    p.inputs["Metallic"].default_value = 0.3
    coord = n.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ")
    ln.new(coord.outputs["Object"], sep.inputs[0])
    lines = []
    for axis in ("X", "Y"):
        mul = n.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 2.2
        ln.new(sep.outputs[axis], mul.inputs[0])
        fr = n.new("ShaderNodeMath"); fr.operation = "FRACT"; ln.new(mul.outputs[0], fr.inputs[0])
        lt = n.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.inputs[1].default_value = 0.028
        ln.new(fr.outputs[0], lt.inputs[0]); lines.append(lt)
    mx = n.new("ShaderNodeMath"); mx.operation = "MAXIMUM"
    ln.new(lines[0].outputs[0], mx.inputs[0]); ln.new(lines[1].outputs[0], mx.inputs[1])
    p.inputs["Emission Color"].default_value = (0.3, 0.8, 1.0, 1)
    strength = n.new("ShaderNodeMath"); strength.operation = "MULTIPLY"; strength.inputs[1].default_value = 1.7
    ln.new(mx.outputs[0], strength.inputs[0]); ln.new(strength.outputs[0], p.inputs["Emission Strength"])
    # Alpha: whole near the objects, gone by the edges of the frame.
    length = n.new("ShaderNodeVectorMath"); length.operation = "LENGTH"
    ln.new(coord.outputs["Object"], length.inputs[0])
    fade = n.new("ShaderNodeMapRange")
    fade.inputs["From Min"].default_value, fade.inputs["From Max"].default_value = 2.5, 7.5
    fade.inputs["To Min"].default_value, fade.inputs["To Max"].default_value = 1.0, 0.0
    ln.new(length.outputs["Value"], fade.inputs["Value"])
    ln.new(fade.outputs["Result"], p.inputs["Alpha"])
    bpy.ops.mesh.primitive_plane_add(size=20, location=(1.4, 1.0, -1.25))
    floor = bpy.context.active_object
    floor.data.materials.append(m)
    return [floor]


def clouds():
    """Soft cumulus puffs, lit by the key and lilac underneath."""
    white = bpy.data.materials.new("cloud")
    white.use_nodes = True
    p = white.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.97, 0.95, 1.0, 1)
    p.inputs["Roughness"].default_value = 1.0
    p.inputs["Subsurface Weight"].default_value = 0.4
    p.inputs["Subsurface Radius"].default_value = (0.8, 0.7, 1.0)
    p.inputs["Emission Color"].default_value = (0.8, 0.75, 1.0, 1)
    p.inputs["Emission Strength"].default_value = 0.25
    made = []
    for cx, cy, cz, k in ((-0.2, 1.6, -1.05, 1.0), (2.6, 2.2, -1.0, 1.25), (4.2, 1.2, 0.9, 0.55), (0.9, 2.6, 1.15, 0.5)):
        for dx, dz, rr in ((-0.8, 0, 0.45), (-0.3, 0.2, 0.62), (0.3, 0.25, 0.7), (0.9, 0.05, 0.5), (1.35, -0.05, 0.35)):
            made.append(shape("sphere", size=rr * k, location=(cx + dx * k, cy, cz + dz * k), material=white))
    return made


camera(location=(0.35, -13.2, 0.7), look_at=(0.35, 0, 0.08), lens=58)
night, day = grid_floor(), clouds()
for o in day:
    o.hide_render = True
finish(str(ART / "hero-night.webp"), 1440, 480, samples=160, transparent=True)
for o in day:
    o.hide_render = False
for o in night:
    o.hide_render = True
finish(str(ART / "hero.webp"), 1440, 480, samples=160, transparent=True)
