"""Pixel art by code: palettes with hue-shifted ramps, sprites from text grids, outlines, dither,
frames, 9-slice boxes and a palette lock. Pillow only.

    import sys; sys.path.insert(0, "themes/_kit/art")
    from pixel import *
    pal = Palette(stone=ramp("#5a6488", 5), ember=ramp("#f0ba72", 4, hue_shift=10))
    bat = grid(["..k.k..", ".kkkkk.", "k.kkk.k"], {"k": pal["stone"][0]})
    save(scale(bat, 3), "themes/<id>/art/bat.png")
"""

import colorsys
import random
from pathlib import Path

from PIL import Image, ImageDraw

BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def rgba(colour: str | tuple) -> tuple[int, int, int, int]:
    """'#rrggbb' or '#rrggbbaa' (or a tuple) → (r, g, b, a)."""
    if isinstance(colour, tuple):
        return colour if len(colour) == 4 else (*colour, 255)
    h = colour.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in range(0, len(h), 2)) + ((255,) if len(h) == 6 else ())


def hexa(colour) -> str:
    r, g, b, a = rgba(colour)
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def ramp(base: str, steps: int = 5, hue_shift: float = 12, spread: float = 0.55, saturate: float = 0.1):
    """Dark → light, the base in the middle. Shadows turn toward blue and lights toward yellow (by
    up to hue_shift degrees at each end), a little more saturated in the middle: the ramps pixel
    artists use, never plain lighter/darker copies of one hue."""
    r, g, b, _ = rgba(base)
    h, light, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)

    def toward(hue: float, target: float, degrees: float) -> float:
        gap = ((target - hue + 0.5) % 1) - 0.5  # the shortest way round
        return (hue + max(-degrees / 360, min(degrees / 360, gap))) % 1

    out = []
    for i in range(steps):
        t = i / (steps - 1) * 2 - 1 if steps > 1 else 0  # -1 darkest … +1 lightest
        hue = toward(h, 1 / 6 if t > 0 else 2 / 3, abs(t) * hue_shift)
        lit = min(0.97, max(0.03, light + t * spread * (light if t < 0 else 1 - light)))
        sat = min(1, max(0, s * (1 + saturate * (1 - abs(t)) - 0.25 * max(0, t))))
        cr, cg, cb = colorsys.hls_to_rgb(hue, lit, sat)
        out.append(f"#{round(cr * 255):02x}{round(cg * 255):02x}{round(cb * 255):02x}")
    return out


class Palette(dict):
    """Named colours or ramps. `lock(image)` fails on any colour not in it: one palette, kept."""

    def colours(self) -> set:
        found = set()
        for value in self.values():
            for c in value if isinstance(value, list) else [value]:
                found.add(rgba(c)[:3])
        return found

    def lock(self, image: Image.Image, name: str = "picture") -> Image.Image:
        allowed = self.colours()
        stray = {px[:3] for px in image.convert("RGBA").getdata() if px[3] and px[3] == 255} - allowed
        if stray:
            shown = ", ".join(hexa(c) for c in sorted(stray)[:8])
            raise ValueError(f"{name}: {len(stray)} colours outside the palette ({shown}…)")
        return image


def grid(rows: list[str], legend: dict[str, str]) -> Image.Image:
    """A sprite from text rows: one character per pixel, '.' or ' ' transparent."""
    width = max(map(len, rows))
    image = Image.new("RGBA", (width, len(rows)))
    px = image.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch not in ". ":
                px[x, y] = rgba(legend[ch])
    return image


def outline(image: Image.Image, colour=None, selective: float = 0.0) -> Image.Image:
    """A 1px outline around the opaque shape. `selective` (0–1): the outline takes the darkened
    colour of the pixel it touches instead of one ink, softer on light edges (sel-out)."""
    src = image.convert("RGBA")
    out = Image.new("RGBA", (src.width + 2, src.height + 2))
    out.paste(src, (1, 1))
    a, px = out.load(), src.load()
    for y in range(out.height):
        for x in range(out.width):
            if a[x, y][3]:
                continue
            near = [px[x - 1 + dx, y - 1 + dy] for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
                    if 0 <= x - 1 + dx < src.width and 0 <= y - 1 + dy < src.height and px[x - 1 + dx, y - 1 + dy][3]]  # fmt: skip
            if near:
                if selective and colour is None:
                    r, g, b, _ = near[0]
                    k = 1 - selective * 0.6
                    a[x, y] = (int(r * k * 0.5), int(g * k * 0.5), int(b * k * 0.55), 255)
                else:
                    a[x, y] = rgba(colour or "#000000")
    return out


def dither(a, b, t: float, x: int, y: int):
    """Ordered (Bayer 4×4) mix: `a` at t=0, `b` at t=1, a patterned blend between."""
    return b if t * 16 > BAYER[y % 4][x % 4] + 0.5 else a


def bands(image: Image.Image, box, colours: list[str], vertical: bool = True, dithered: bool = True):
    """A stepped gradient through `colours` in box (x0, y0, x1, y1), dithered between steps."""
    x0, y0, x1, y1 = box
    px, n = image.load(), len(colours) - 1
    span = (y1 - y0) if vertical else (x1 - x0)
    for y in range(y0, y1):
        for x in range(x0, x1):
            f = ((y - y0) if vertical else (x - x0)) / max(1, span - 1) * n
            i = min(int(f), n - 1) if n else 0
            c = dither(colours[i], colours[i + 1], f - i, x, y) if dithered and n else colours[round(f)]
            px[x, y] = rgba(c)
    return image


def scale(image: Image.Image, n: int) -> Image.Image:
    """Whole-number nearest-neighbour scaling: pixels stay square and sharp."""
    return image.resize((image.width * n, image.height * n), Image.NEAREST)


def sheet(frames: list[Image.Image]) -> Image.Image:
    """Frames side by side, for a layer's "frames": {"count": len(frames)}."""
    w, h = frames[0].size
    out = Image.new("RGBA", (w * len(frames), h))
    for i, frame in enumerate(frames):
        out.paste(frame, (i * w, 0))
    return out


def nine(corner: Image.Image, edge: Image.Image, middle=None) -> Image.Image:
    """A 9-slice box (3s × 3s) from its top-left corner and top edge (both s × s), turned for the
    other sides; the middle filled with `middle` (a colour) or left clear. Use with
    {"fit": "slice", "slice": s} on a surface."""
    s = corner.width
    out = Image.new("RGBA", (3 * s, 3 * s), rgba(middle) if middle else (0, 0, 0, 0))
    for turn, (cx, cy), (ex, ey) in ((0, (0, 0), (s, 0)), (270, (2 * s, 0), (2 * s, s)),
                                     (180, (2 * s, 2 * s), (s, 2 * s)), (90, (0, 2 * s), (0, s))):  # fmt: skip
        out.paste(corner.rotate(turn), (cx, cy))
        out.paste(edge.rotate(turn), (ex, ey))
    return out


def speckle(image: Image.Image, colour, density: float, seed: int, box=None):
    """Scattered single pixels (stars, grain, moss) in box, seeded so every run is the same."""
    rnd, px = random.Random(seed), image.load()
    x0, y0, x1, y1 = box or (0, 0, image.width, image.height)
    for _ in range(int((x1 - x0) * (y1 - y0) * density)):
        px[rnd.randrange(x0, x1), rnd.randrange(y0, y1)] = rgba(colour)
    return image


def canvas(width: int, height: int, colour=None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height), rgba(colour) if colour else (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def save(image: Image.Image, path, colours: int | None = None) -> Path:
    """An optimised PNG (or WebP by its name). `colours`: a palette PNG, the smallest for pixel art."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".webp":
        image.save(path, quality=86, method=6)
    elif colours:
        image.convert("RGBA").quantize(colours, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)
    else:
        image.save(path, optimize=True)
    return path
