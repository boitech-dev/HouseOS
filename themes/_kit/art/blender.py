"""3D renders by code with Blender (headless): chrome, translucent plastic, concrete, glass, light
through a window. A scene is a small Python file that imports this module inside Blender:

    # docs/design/themes/<id>/scene_hero.py
    import sys; sys.path.insert(0, "themes/_kit/art")
    from blender import *
    reset()
    blob = shape("sphere", size=1.2, material=material("chrome"))
    camera(location=(0, -6, 1.5), look_at=(0, 0, 0.6), lens=60)
    light("area", location=(3, -3, 5), energy=800, size=4)
    finish("themes/<id>/art/hero.webp", 1600, 600)

and is rendered from the shell (or with `render()` from ordinary Python):

    blender -b --factory-startup -P docs/design/themes/<id>/scene_hero.py

Cycles, GPU when there is one, a fixed seed and the denoiser: the same picture every run.
Blender is found on PATH or at ~/.local/bin/blender (HOUSEOS_BLENDER overrides)."""

import os
import shutil
import subprocess
from pathlib import Path

try:
    import bpy  # inside Blender

    INSIDE = True
except ImportError:
    INSIDE = False


def render(scene: str, blender: str | None = None) -> None:
    """From ordinary Python: run a scene file in a headless Blender."""
    exe = blender or os.environ.get("HOUSEOS_BLENDER") or shutil.which("blender") or str(Path.home() / ".local/bin/blender")
    subprocess.run([exe, "-b", "--factory-startup", "-P", scene], check=True)


# ---------- inside Blender ----------
def reset(world=(0.02, 0.02, 0.025), strength: float = 1.0):
    """An empty scene with a plain world colour (the light that fills shadows)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    w = bpy.data.worlds.new("world")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*world, 1)
    bg.inputs["Strength"].default_value = strength


PRESETS = {
    # base colour, metallic, roughness, transmission, ior, coat
    "chrome": ((0.9, 0.9, 0.92), 1.0, 0.06, 0.0, 1.45, 0.0),
    "brushed": ((0.72, 0.73, 0.76), 1.0, 0.32, 0.0, 1.45, 0.0),
    "plastic": ((0.1, 0.5, 0.7), 0.0, 0.18, 0.0, 1.46, 0.6),
    "translucent": ((0.2, 0.6, 0.75), 0.0, 0.12, 0.92, 1.46, 0.8),
    "glass": ((0.95, 0.97, 1.0), 0.0, 0.02, 1.0, 1.5, 0.0),
    "concrete": ((0.55, 0.54, 0.52), 0.0, 0.85, 0.0, 1.45, 0.0),
    "paper": ((0.86, 0.82, 0.74), 0.0, 0.95, 0.0, 1.45, 0.0),
    "matte": ((0.5, 0.5, 0.5), 0.0, 0.6, 0.0, 1.45, 0.0),
}


def material(kind: str = "matte", colour=None, roughness=None, emission=None, strength: float = 4.0):
    """A Principled material from a preset; `colour` (r, g, b 0–1) tints it, `emission` makes it glow."""
    base, metal, rough, trans, ior, coat = PRESETS[kind]
    m = bpy.data.materials.new(kind)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*(colour or base), 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough if roughness is None else roughness
    p.inputs["Transmission Weight"].default_value = trans
    p.inputs["IOR"].default_value = ior
    p.inputs["Coat Weight"].default_value = coat
    if emission:
        p.inputs["Emission Color"].default_value = (*emission, 1)
        p.inputs["Emission Strength"].default_value = strength
    return m


def shape(kind: str = "cube", size=1.0, location=(0, 0, 0), rotation=(0, 0, 0), material=None, bevel: float = 0.0, smooth=True):
    """A primitive (cube, sphere, cylinder, torus, plane, cone), scaled by `size` (a number or x, y, z)."""
    add = {"cube": bpy.ops.mesh.primitive_cube_add, "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
           "cylinder": bpy.ops.mesh.primitive_cylinder_add, "torus": bpy.ops.mesh.primitive_torus_add,
           "plane": bpy.ops.mesh.primitive_plane_add, "cone": bpy.ops.mesh.primitive_cone_add}[kind]  # fmt: skip
    add(location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.scale = (size, size, size) if isinstance(size, (int, float)) else size
    if bevel:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width, mod.segments = bevel, 4
    if smooth and kind != "cube":
        bpy.ops.object.shade_smooth()
    if material:
        obj.data.materials.append(material)
    return obj


def camera(location=(0, -6, 2), look_at=(0, 0, 0), lens: float = 50, ortho: float | None = None):
    """The camera, aimed at `look_at`; `ortho` (a width in metres) for flat, architectural views."""
    from mathutils import Vector

    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.active_object
    cam.rotation_euler = (Vector(look_at) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam.data.type, cam.data.ortho_scale = "ORTHO", ortho
    else:
        cam.data.lens = lens
    bpy.context.scene.camera = cam
    return cam


def light(kind: str = "area", location=(3, -3, 5), energy: float = 500, size: float = 2, colour=(1, 1, 1), look_at=(0, 0, 0), angle: float = 0.5):
    """A light: area (soft), sun (hard shadows: `angle` in degrees of softness), point or spot."""
    from math import radians

    from mathutils import Vector

    data = bpy.data.lights.new(kind, kind.upper())
    data.energy, data.color = energy, colour
    if kind == "area":
        data.size = size
    if kind == "sun":
        data.angle = radians(angle)
    obj = bpy.data.objects.new(kind, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(look_at) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    return obj


def finish(out: str, width: int, height: int, samples: int = 96, transparent: bool = False, seed: int = 1, exposure: float = 0.0):
    """Render to `out` (.png, or .webp through Pillow when available) at width × height."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            if any(d.type == backend for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == backend
                scene.cycles.device = "GPU"
                break
        except TypeError:
            continue
    scene.cycles.samples, scene.cycles.seed, scene.cycles.use_denoising = samples, seed, True
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = width, height, 100
    scene.render.film_transparent = transparent
    scene.view_settings.exposure = exposure
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    target = Path(out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    png = target.with_suffix(".render.png")
    scene.render.filepath = str(png)
    bpy.ops.render.render(write_still=True)
    if target.suffix == ".png":
        png.replace(target)
    else:  # .webp: Blender's own Python has no Pillow; convert with ImageMagick
        subprocess.run(["magick", str(png), "-strip", "-quality", "86", str(target)], check=True)
        png.unlink()
