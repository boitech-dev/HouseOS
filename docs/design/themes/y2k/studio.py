"""Millennium Skin's one studio (inside Blender): the chrome environment, the key light from the top
left, a lilac rim from behind, and the theme's materials. Every render imports it.

The environment is the Y2K chrome look: a lilac-to-sky-blue dome, a dark navy horizon band with a
bright line on it, a pale floor. The background itself renders transparent (film_transparent), so
it only shows in reflections and the art sits on each scheme's own ground."""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "themes/_kit/art"))

import bpy  # noqa: E402
from blender import camera, finish, light, material, reset, shape  # noqa: E402,F401

ART = ROOT / "themes/y2k/art"


def studio(strength: float = 1.0):
    reset()
    world = bpy.context.scene.world
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    bg = nodes["Background"]
    coord = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    links.new(coord.outputs["Generated"], sep.inputs[0])  # on the world: the ray's direction
    map_range = nodes.new("ShaderNodeMapRange")
    map_range.inputs["From Min"].default_value = -1
    map_range.inputs["From Max"].default_value = 1
    links.new(sep.outputs["Z"], map_range.inputs["Value"])
    links.new(map_range.outputs["Result"], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    cr.interpolation = "LINEAR"
    stops = [
        (0.0, (0.22, 0.2, 0.34)),     # far below: a dusky floor
        (0.44, (0.72, 0.7, 0.86)),    # the floor near the horizon, pale lilac
        (0.488, (0.015, 0.02, 0.06)), # the dark horizon band
        (0.5, (2.2, 2.2, 2.3)),       # the bright horizon line
        (0.51, (0.85, 0.92, 1.0)),    # pale sky just above it
        (0.62, (0.18, 0.4, 1.0)),     # sky blue
        (0.82, (0.42, 0.25, 0.95)),   # violet
        (1.0, (0.12, 0.08, 0.35)),    # the zenith, deep
    ]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, col in stops[1:-1]:
        e = cr.elements.new(pos)
        e.color = (*col, 1)
    links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.view_settings.view_transform = "Standard"  # punchy candy colours, no AgX greying
    bpy.context.scene.view_settings.look = "None"
    # The one light: a cool key from the top left, a lilac rim from behind.
    light("area", location=(-4, -4, 5), energy=900, size=5, colour=(0.96, 0.98, 1.0))
    light("area", location=(3, 4, 2.5), energy=500, size=4, colour=(0.8, 0.65, 1.0))
    light("area", location=(5, -3, -1), energy=120, size=3, colour=(0.7, 0.9, 1.0))


def principled(m):
    return m.node_tree.nodes["Principled BSDF"]


def chrome(tint=(0.92, 0.93, 0.96), roughness=0.04):
    return material("chrome", colour=tint, roughness=roughness)


def plastic(colour, roughness=0.08, transmission=0.9, speckle=False):
    """Clear candy plastic: transmission, a coat, a little volume absorption for depth."""
    m = material("translucent", colour=colour, roughness=roughness)
    p = principled(m)
    p.inputs["Transmission Weight"].default_value = transmission
    p.inputs["Coat Weight"].default_value = 1.0
    p.inputs["Coat Roughness"].default_value = 0.02
    nt = m.node_tree
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (*colour, 1)
    vol.inputs["Density"].default_value = 0.6
    nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    if speckle:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 140
        noise.inputs["Detail"].default_value = 1
        cramp = nt.nodes.new("ShaderNodeValToRGB")
        cramp.color_ramp.elements[0].position = 0.72
        cramp.color_ramp.elements[0].color = (0, 0, 0, 1)
        cramp.color_ramp.elements[1].position = 0.74
        cramp.color_ramp.elements[1].color = (1, 1, 1, 1)
        nt.links.new(noise.outputs["Fac"], cramp.inputs["Fac"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = (*colour, 1)
        mix.inputs["B"].default_value = (1, 1, 1, 1)
        nt.links.new(cramp.outputs["Color"], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    return m


def iridescent(base=(0.9, 0.9, 0.95)):
    """A disc's data side: chrome with rainbow arcs radiating from the hub (the angle around the
    centre drives a spectrum), under a thin film."""
    m = material("chrome", colour=base, roughness=0.12)
    p = principled(m)
    p.inputs["Thin Film Thickness"].default_value = 420
    p.inputs["Thin Film IOR"].default_value = 1.5
    nt = m.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "RADIAL"
    mapping = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    maths = nt.nodes.new("ShaderNodeMath")
    maths.operation = "PINGPONG"
    maths.inputs[1].default_value = 0.25
    nt.links.new(grad.outputs["Fac"], maths.inputs[0])
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = 4.0
    nt.links.new(maths.outputs[0], scale.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    spectrum = [(0.0, (0.9, 0.95, 1.0)), (0.18, (0.35, 0.7, 1.0)), (0.36, (0.4, 1.0, 0.75)),
                (0.54, (1.0, 0.95, 0.4)), (0.72, (1.0, 0.5, 0.75)), (0.9, (0.65, 0.45, 1.0)), (1.0, (0.9, 0.95, 1.0))]
    cr.elements[0].position, cr.elements[0].color = spectrum[0][0], (*spectrum[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = spectrum[-1][0], (*spectrum[-1][1], 1)
    for pos, col in spectrum[1:-1]:
        cr.elements.new(pos).color = (*col, 1)
    nt.links.new(scale.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


def glow(colour, strength=6.0):
    return material("matte", colour=colour, emission=colour, strength=strength)


def metaball(points, material=None, resolution=0.03, threshold=0.6):
    """Blobby chrome: metaball spheres [(x, y, z, radius)] merged into one surface."""
    mb = bpy.data.metaballs.new("blob")
    mb.resolution = resolution
    mb.render_resolution = resolution / 2
    mb.threshold = threshold
    for x, y, z, r in points:
        e = mb.elements.new()
        e.co = (x, y, z)
        e.radius = r
    obj = bpy.data.objects.new("blob", mb)
    bpy.context.collection.objects.link(obj)
    if material:
        mb.materials.append(material)
    return obj


def star(points=4, outer=1.0, inner=0.22, depth=0.18, material=None, location=(0, 0, 0), rotation=(0, 0, 0), bevel=0.05):
    """A four-point sparkle star as a solid: a flat star polygon, thick, bevelled and smooth."""
    import bmesh

    me = bpy.data.meshes.new("star")
    bm = bmesh.new()
    ring = []
    for i in range(points * 2):
        a = math.pi / 2 + i * math.pi / points
        r = outer if i % 2 == 0 else inner
        ring.append((math.cos(a) * r, math.sin(a) * r))
    top = [bm.verts.new((x, y, depth / 2)) for x, y in ring]
    bot = [bm.verts.new((x, y, -depth / 2)) for x, y in ring]
    ctop = bm.verts.new((0, 0, depth * 1.4))
    cbot = bm.verts.new((0, 0, -depth * 1.4))
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((top[i], top[j], ctop))
        bm.faces.new((bot[j], bot[i], cbot))
        bm.faces.new((top[i], bot[i], bot[j], top[j]))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("star", me)
    bpy.context.collection.objects.link(obj)
    obj.location, obj.rotation_euler = location, rotation
    if bevel:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width, mod.segments = bevel, 3
    for poly in me.polygons:
        poly.use_smooth = True
    if material:
        me.materials.append(material)
    return obj


def ring_disc(outer=1.0, hole=0.16, thickness=0.03, material=None, hub=None, location=(0, 0, 0), rotation=(0, 0, 0)):
    """A disc with a hole (a CD): a thin cylinder with a boolean hole and a clear hub."""
    disc = shape("cylinder", size=(outer, outer, thickness), location=location, rotation=rotation, material=material, smooth=True)
    bpy.ops.mesh.primitive_cylinder_add(location=location, rotation=rotation)
    cutter = bpy.context.active_object
    cutter.scale = (hole, hole, thickness * 4)
    mod = disc.modifiers.new("hole", "BOOLEAN")
    mod.object, mod.operation = cutter, "DIFFERENCE"
    cutter.hide_render = True
    cutter.hide_viewport = True
    if hub:
        h = shape("torus", size=1, location=location, rotation=rotation, material=hub)
        h.scale = (outer * 0.3, outer * 0.3, thickness * 12)
    return disc


def keychain_egg(x=0.0, y=0.0, z=0.0, s=1.0, tilt=-8, ring=True):
    """The theme's keychain egg (Nox's body): a clear Bondi shell with speckle, a darker core, an
    LCD window with a pixel smile, three chrome keys, and a grape ring through a chrome eyelet."""
    r = math.radians
    shape("sphere", size=(0.66 * s, 0.56 * s, 0.8 * s), location=(x, y, z), rotation=(0, r(tilt), 0),
          material=plastic((0.1, 0.62, 0.78), speckle=True))
    shape("sphere", size=(0.38 * s, 0.3 * s, 0.47 * s), location=(x, y + 0.05 * s, z + 0.05 * s), material=plastic((0.05, 0.3, 0.5), transmission=0.4))
    # The LCD sits inside the clear shell (seen through it): a dark bezel, green glass, lit pixels.
    sx, sy, sz = x - 0.01 * s, y - 0.44 * s, z + 0.15 * s
    shape("cube", size=(0.3 * s, 0.03 * s, 0.24 * s), location=(sx, sy + 0.01 * s, sz), rotation=(0, r(tilt), 0),
          material=material("matte", colour=(0.01, 0.015, 0.02), roughness=0.3), bevel=0.05 * s)
    shape("cube", size=(0.25 * s, 0.03 * s, 0.19 * s), location=(sx, sy - 0.005 * s, sz), rotation=(0, r(tilt), 0),
          material=glow((0.02, 0.1, 0.05), strength=1.0), bevel=0.03 * s)
    lit = glow((0.55, 1.0, 0.25), strength=6.0)
    for px, pz in ((-0.07, 0.05), (0.05, 0.05), (-0.08, -0.04), (-0.03, -0.07), (0.01, -0.07), (0.06, -0.04)):
        shape("cube", size=(0.03 * s, 0.012 * s, 0.03 * s), location=(sx + px * s, sy - 0.035 * s, sz + pz * s), rotation=(0, r(tilt), 0), material=lit)
    for dx in (-0.24, 0.0, 0.24):
        shape("sphere", size=0.085 * s, location=(x + dx * 0.85 * s - 0.02 * s, y - 0.53 * s, z - 0.33 * s + abs(dx) * 0.3 * s), material=chrome())
    if ring:
        t = shape("torus", size=1, location=(x + 0.05 * s, y, z + 1.0 * s), rotation=(r(80), r(25), 0), material=plastic((0.55, 0.2, 0.85)))
        t.scale = (0.3 * s, 0.3 * s, 0.3 * s)
        shape("sphere", size=0.09 * s, location=(x + 0.02 * s, y, z + 0.8 * s), material=chrome())


def pixel_picture(scene="sunset", strength=1.4):
    """A CRT's picture as pixel art (32 x 24, nearest-neighbour): a striped sun setting on a
    violet grid under a starry sky, or the egg's LCD smile. Emissive."""
    w, h = 32, 24
    px = [[(0.02, 0.02, 0.08)] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if y < 14:
                t = y / 14
                px[y][x] = (0.08 + 0.5 * t, 0.04 + 0.1 * t, 0.3 + 0.2 * t)
            else:
                px[y][x] = (0.05, 0.02, 0.18)
    if scene == "sunset":
        for y in range(4, 14):
            for x in range(10, 22):
                if (x - 15.5) ** 2 + (y - 13) ** 2 <= 36 and not (y in (9, 11, 13) and y > 8):
                    px[y][x] = (1.0, 0.55 + (13 - y) * 0.04, 0.2 + (13 - y) * 0.05)
        for y in range(14, h):
            for x in range(w):
                if y in (14, 16, 19, 23):
                    px[y][x] = (0.2, 0.9, 1.0)
            for j in range(-8, 9):  # rays to the vanishing point on the horizon
                x = round(16 + j * (y - 13) * 0.9)
                if 0 <= x < w:
                    px[y][x] = (0.2, 0.9, 1.0)
        for sx, sy in ((3, 2), (7, 5), (25, 3), (29, 7), (20, 1)):
            px[sy][sx] = (1, 1, 1)
    else:  # the smile
        px = [[(0.03, 0.14, 0.07)] * w for _ in range(h)]
        for x, y in ((11, 8), (12, 8), (11, 9), (12, 9), (19, 8), (20, 8), (19, 9), (20, 9),
                     (10, 14), (11, 15), (12, 16), (13, 16), (14, 16), (15, 16), (16, 16), (17, 16), (18, 16), (19, 16), (20, 15), (21, 14)):  # fmt: skip
            px[y][x] = (0.6, 1.0, 0.35)
    img = bpy.data.images.new(scene, w, h)
    img.pixels = [c for row in reversed(px) for rgb in row for c in (*rgb, 1.0)]
    m = bpy.data.materials.new("screen-" + scene)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image, tex.interpolation = img, "Closest"
    tex.extension = "EXTEND"
    # Map the screen's front (its local x and z, -1..1) onto the picture.
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    for axis, out in (("X", "X"), ("Z", "Y")):
        mad = nt.nodes.new("ShaderNodeMath")
        mad.operation = "MULTIPLY_ADD"
        mad.inputs[1].default_value, mad.inputs[2].default_value = 0.5, 0.5
        nt.links.new(sep.outputs[axis], mad.inputs[0])
        nt.links.new(mad.outputs[0], comb.inputs[out])
    nt.links.new(comb.outputs[0], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = strength
    p.inputs["Roughness"].default_value = 0.15
    p.inputs["Coat Weight"].default_value = 1.0
    return m


def crt(x=0.0, y=0.0, z=0.0, s=1.0, turn=0.0, scene="sunset"):
    """A clear Bondi CRT: a rounded clear case showing its insides (the tube with its glowing
    neck, a green board), a pixel picture on a slightly curved screen, chrome antennas, feet."""
    r = math.radians
    ca, sa = math.cos(r(turn)), math.sin(r(turn))

    def at(dx, dy, dz):  # an offset in the set's own frame, turned with it
        return (x + (dx * ca - dy * sa) * s, y + (dx * sa + dy * ca) * s, z + dz * s)

    rot = (0, 0, r(turn))
    shape("cube", size=(1.0 * s, 0.9 * s, 0.82 * s), location=at(0, 0.2, 0), rotation=rot, bevel=0.22 * s,
          material=plastic((0.3, 0.75, 0.88), roughness=0.08, transmission=1.0, speckle=True))
    shape("cone", size=(0.5 * s, 0.5 * s, 0.62 * s), location=at(0, 0.45, 0.02), rotation=(r(-90), 0, r(turn)),
          material=material("matte", colour=(0.06, 0.07, 0.12), roughness=0.3))
    shape("cylinder", size=(0.09 * s, 0.09 * s, 0.25 * s), location=at(0, 0.95, 0.02), rotation=(r(90), 0, r(turn)), material=glow((1.0, 0.45, 0.15), 3))
    shape("cube", size=(0.8 * s, 0.7 * s, 0.03 * s), location=at(0, 0.3, -0.6), rotation=rot, material=material("matte", colour=(0.05, 0.3, 0.14), roughness=0.5))
    for bx, by in ((-0.4, 0.1), (0.35, 0.5), (0.1, 0.7)):
        shape("cube", size=(0.12 * s, 0.1 * s, 0.05 * s), location=at(bx, by, -0.56), rotation=rot, material=material("matte", colour=(0.02, 0.02, 0.03)))
    scr = shape("cube", size=(0.74 * s, 0.05 * s, 0.56 * s), location=at(0, -0.63, 0.04), rotation=rot, bevel=0.12 * s,
                material=pixel_picture(scene))
    for side in (-1, 1):
        shape("cylinder", size=(0.018 * s, 0.018 * s, 0.38 * s), location=at(side * 0.22, 0.3, 1.12),
              rotation=(0, r(side * 28), 0), material=chrome())
        shape("sphere", size=0.05 * s, location=at(side * 0.4, 0.3, 1.45), material=chrome())
        shape("cylinder", size=(0.14 * s, 0.14 * s, 0.05 * s), location=at(side * 0.55, 0.2, -0.85), material=chrome())
    shape("sphere", size=(0.12 * s, 0.1 * s, 0.1 * s), location=at(0, 0.2, 0.85), material=chrome())
    return scr
