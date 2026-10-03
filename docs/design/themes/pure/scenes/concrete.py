"""Pure's one set of materials and its one light, shared by every scene (inside Blender).
The light: a single low sun, warm white, from the upper left, through openings only. Everything
else is dark: the world gives almost nothing, so shadows are near black and light is the only
ornament. Camera language: frontal, level, architectural (lens 35–50 or orthographic)."""
import sys, os
from math import radians
sys.path.insert(0, "themes/_kit/art")
import bpy
from mathutils import Vector
from blender import reset as _reset, camera, finish  # noqa: F401

SUN_COLOUR = (1.0, 0.95, 0.86)  # late sun on concrete: the theme's cream


def reset(ambient=0.012):
    ambient = float(os.environ.get("AMBIENT", ambient))
    _reset(world=(ambient, ambient, ambient * 1.04), strength=1.0)
    s = bpy.context.scene
    s.view_settings.view_transform = "Standard"
    if os.environ.get("BOUNCES"):  # a paper print: no bounced light, so every shadow is the sun's, crisp
        s.cycles.diffuse_bounces = int(os.environ["BOUNCES"])
    s.view_settings.look = "None"


def concrete(tone=0.5, name="concrete", scale=1.0, seams=None, mottle=1.0):
    """Béton brut: a mottled grey (`mottle` its strength), faint shuttering grain, small pores."""
    strength = mottle
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    n, l = nt.nodes, nt.links
    p = n["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.82
    tc = n.new("ShaderNodeTexCoord")
    mottle = n.new("ShaderNodeTexNoise")
    mottle.inputs["Scale"].default_value = 3.0 * scale
    mottle.inputs["Detail"].default_value = 8
    mottle.inputs["Roughness"].default_value = 0.6
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    lo = 1 - 0.18 * strength
    ramp.color_ramp.elements[0].color = (tone * lo, tone * lo, tone * (lo - 0.02), 1)
    ramp.color_ramp.elements[1].position = 0.7
    hi = 1 + 0.05 * strength
    ramp.color_ramp.elements[1].color = (tone * hi, tone * (hi - 0.01), tone * (hi - 0.05 * strength), 1)
    l.new(tc.outputs["Object"], mottle.inputs["Vector"])
    l.new(mottle.outputs["Fac"], ramp.inputs["Fac"])
    # pores: small dark dimples
    pores = n.new("ShaderNodeTexVoronoi")
    pores.feature = "F1"
    pores.inputs["Scale"].default_value = 90.0 * scale
    pr = n.new("ShaderNodeMapRange")
    pr.inputs["From Min"].default_value = 0.0
    pr.inputs["From Max"].default_value = 0.08
    l.new(tc.outputs["Object"], pores.inputs["Vector"])
    l.new(pores.outputs["Distance"], pr.inputs["Value"])
    mix = n.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.35
    l.new(ramp.outputs["Color"], mix.inputs[6])
    inv = n.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    l.new(pr.outputs["Result"], inv.inputs[1])
    l.new(inv.outputs[0], mix.inputs["Factor"])
    blackish = n.new("ShaderNodeRGB"); blackish.outputs[0].default_value = (0.35, 0.35, 0.35, 1)
    # factor = (1 - pore distance): pores darken; scale it down
    fac = n.new("ShaderNodeMath"); fac.operation = "MULTIPLY"; fac.inputs[1].default_value = 0.4
    l.new(inv.outputs[0], fac.inputs[0])
    l.new(fac.outputs[0], mix.inputs["Factor"])
    l.new(blackish.outputs[0], mix.inputs[7])
    colour_out = mix.outputs[2]
    if seams:  # shuttering seams (world position): fine dark lines on the panel grid
        pw, ph = seams
        geo = n.new("ShaderNodeNewGeometry")
        sep = n.new("ShaderNodeSeparateXYZ")
        l.new(geo.outputs["Position"], sep.inputs[0])
        lines = []
        for axis, size in (("X", pw), ("Z", ph)):
            div = n.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = size
            l.new(sep.outputs[axis], div.inputs[0])
            fr = n.new("ShaderNodeMath"); fr.operation = "PINGPONG"; fr.inputs[1].default_value = 0.5
            l.new(div.outputs[0], fr.inputs[0])  # distance to the nearest seam, 0–0.5 panels
            lt = n.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.inputs[1].default_value = 0.0035 / size
            l.new(fr.outputs[0], lt.inputs[0])
            lines.append(lt)
        mx = n.new("ShaderNodeMath"); mx.operation = "MAXIMUM"
        l.new(lines[0].outputs[0], mx.inputs[0]); l.new(lines[1].outputs[0], mx.inputs[1])
        dark = n.new("ShaderNodeMix"); dark.data_type = "RGBA"; dark.blend_type = "MULTIPLY"
        l.new(mx.outputs[0], dark.inputs["Factor"])
        l.new(colour_out, dark.inputs[6])
        dark.inputs[7].default_value = (0.45, 0.45, 0.45, 1)
        colour_out = dark.outputs[2]
    l.new(colour_out, p.inputs["Base Color"])
    # bump from both
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.002
    add = n.new("ShaderNodeMath"); add.operation = "ADD"
    l.new(mottle.outputs["Fac"], add.inputs[0])
    l.new(pr.outputs["Result"], add.inputs[1])
    l.new(add.outputs[0], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def box(size, location, material=None, name="box"):
    bpy.ops.mesh.primitive_cube_add(location=location)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if material:
        o.data.materials.append(material)
    return o


def cut(target, cutters):
    """Boolean difference of every cutter from target; the cutters are removed."""
    if not cutters:
        return target
    bpy.ops.object.select_all(action="DESELECT")
    for c in cutters:
        c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    if len(cutters) > 1:
        bpy.ops.object.join()
    tool = bpy.context.active_object
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation, mod.object, mod.solver = "DIFFERENCE", tool, "EXACT"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(tool)
    return target


def tie_holes(x0, x1, z0, z1, y, panel=(1.8, 0.9), r=0.022, depth=0.03):
    """Form-tie holes: 3 × 2 per shuttering panel, the wall's grid (and seams as fine grooves)."""
    cutters = []
    pw, ph = panel
    import math
    i0, i1 = math.floor(x0 / pw), math.ceil(x1 / pw)
    j0, j1 = math.floor(z0 / ph), math.ceil(z1 / ph)
    for i in range(i0, i1):
        for j in range(j0, j1):
            for hx in (pw / 6, pw / 2, 5 * pw / 6):
                for hz in (ph / 4, 3 * ph / 4):
                    x, z = i * pw + hx, j * ph + hz
                    if x0 < x < x1 and z0 < z < z1:
                        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth * 2, location=(x, y, z),
                                                            rotation=(radians(90), 0, 0), vertices=24)
                        cutters.append(bpy.context.active_object)
    return cutters


def sun(direction_from, strength=6.0, angle=0.4):
    """The one light: a sun from `direction_from` (a vector pointing at the sun). SUNANGLE
    overrides its softness (a paper print wants crisper shadows)."""
    angle = float(os.environ.get("SUNANGLE", angle))
    data = bpy.data.lights.new("sun", "SUN")
    data.energy, data.color, data.angle = strength, SUN_COLOUR, radians(angle)
    o = bpy.data.objects.new("sun", data)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = (-Vector(direction_from)).to_track_quat("-Z", "Y").to_euler()
    return o


def black():
    m = bpy.data.materials.new("void")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.01, 0.01, 0.01, 1)
    p.inputs["Roughness"].default_value = 1.0
    return m


def out(name):
    """Where a render lands; VARIANT (e.g. "light", a scheme's own print) is added to its name."""
    if os.environ.get("VARIANT"):
        name = name.replace(".png", "-" + os.environ["VARIANT"] + ".png")
    d = os.environ.get("PURE_RENDERS", "/tmp/pure-renders")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def opening(target, sun_from, shape="slit", size=(0.16, 20), turn=0.0, distance=7.0):
    """The one opening the sun comes through: a screen of four black slabs around a hole of
    `size` (w, h), `distance` from `target` towards the sun, the hole turned by `turn` radians.
    Never in frame: it only shapes the light."""
    from mathutils import Matrix
    d = Vector(sun_from).normalized()
    centre = Vector(target) + d * distance
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4() @ Matrix.Rotation(turn, 4, "Z")
    w, h = size
    big = 40
    m = black()
    parts = [((big, big, 0.05), (-(w / 2 + big / 2), 0, 0)), ((big, big, 0.05), ((w / 2 + big / 2), 0, 0)),
             ((w, big, 0.05), (0, h / 2 + big / 2, 0)), ((w, big, 0.05), (0, -(h / 2 + big / 2), 0))]
    for dims, loc in parts:
        o = box(dims, (0, 0, 0), m, "screen")
        o.matrix_world = Matrix.Translation(centre) @ rot @ Matrix.Translation(loc)
        o.visible_camera = False  # it shapes the light; nobody sees it
        o.visible_glossy = False
    return centre


def openings(target, sun_from, holes, distance=7.0, turn=0.0):
    """A screen with several openings: holes are (kind, x, y, w, h) in the screen's plane around
    its centre, kind "rect" or "disc". Invisible to the camera: it only shapes the light."""
    from mathutils import Matrix
    d = Vector(sun_from).normalized()
    centre = Vector(target) + d * distance
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4() @ Matrix.Rotation(turn, 4, "Z")
    plate = box((60, 60, 0.05), (0, 0, 0), black(), "screen")
    cutters = []
    for kind, x, y, w, h in holes:
        if kind == "disc":
            bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1, location=(x, y, 0), vertices=96)
            c = bpy.context.active_object
            c.scale = (w, h, 1)
        else:
            c = box((w, h, 1), (x, y, 0))
        cutters.append(c)
    cut(plate, cutters)
    plate.matrix_world = Matrix.Translation(centre) @ rot
    plate.visible_camera = False
    plate.visible_glossy = False
    return centre


def haze(size, location, density=0.02):
    """Air with a little dust in it, so the sun's blade is seen in the air, not only where it lands."""
    m = bpy.data.materials.new("haze")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = density
    v.inputs["Color"].default_value = (1, 1, 1, 1)
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    o = box(size, location, m, "haze")
    o.visible_shadow = False
    return o
