"""Shōwa Platform: the palette and the small drawing kit every picture uses.

One palette (PAL), one light (the afternoon sun, high on the left: highlights top-left, shadows
bottom-right in cool blue-violet), one pixel size (every picture is drawn at 1 and shown at 2×).
"""

import json
import math
import os
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "themes/_kit/art"))
from pixel import BAYER, Palette, rgba  # noqa: E402

ART = ROOT / "themes/showa-platform/art"
THEME = ROOT / "themes/showa-platform"

# name: hex. Grouped by material; every picture is locked to this list.
PAL = {
    # navy enamel: lettering, frames, the coolest shadows
    "n0": "#141c33", "n1": "#1f2b4d", "n2": "#2e4172", "n3": "#45609a", "n4": "#7288b8",
    # cream enamel, paper and concrete
    "c0": "#fffaf0", "c1": "#f7eed6", "c2": "#eadcb8", "c3": "#d4bf93", "c4": "#b09a72",
    "s1": "#aaa6bd", "s2": "#8a88a6",  # cast shadow on cream (cool)
    # signal red
    "r0": "#6e1c18", "r1": "#a52a1f", "r2": "#cf3f28", "r3": "#ec6a44", "r4": "#f7a47e",
    # summer sky
    "k0": "#2f6fb8", "k1": "#4f8fd0", "k2": "#75b0e3", "k3": "#a4cff0", "k4": "#d2e9f7",
    # cumulus
    "w0": "#ffffff", "w1": "#eef2f7", "w2": "#c9d6e8", "w3": "#9fb2cf", "w4": "#7d8fb4",
    # far hills (air between)
    "h0": "#5b7fa6", "h1": "#7a9dbf", "h2": "#9dbad3",
    # greens
    "g0": "#1f3d2c", "g1": "#2f5a37", "g2": "#467d42", "g3": "#6ea653", "g4": "#a8cc6a",
    # sunflower, brass, crossing stripes
    "y0": "#8a5a12", "y1": "#c8841c", "y2": "#eeb42a", "y3": "#f8d860",
    # wood
    "b0": "#3b2618", "b1": "#5e3d24", "b2": "#8a5c36", "b3": "#b58450", "b4": "#d8ad74",
    # steel, ballast
    "t0": "#4a4652", "t1": "#6e6a76", "t2": "#9a96a0", "t3": "#c9c5cc",
    # ticket green (the card), and the cat's ginger
    "p0": "#b9d7b0", "p1": "#d6ead0",
    "o0": "#9a5226", "o1": "#e0913a", "o2": "#f6c78a",
}
# The line colours of the house's map: one per room (also color.room.* in tokens.json).
LINES = {
    "home": "#56627e", "listen": "#b04b21", "watch": "#27679a", "games": "#18746c",
    "house": "#3d762f", "files": "#7c6214", "ask": "#84499a", "me": "#b83455",
    "control": "#34457a", "smart-home": "#24744c", "inbox": "#3b5fbe", "space": "#a2437a",
    "party": "#995f1f",
}
PAL.update({"L-" + k: v for k, v in LINES.items()})

# Dusk: the same station at 7 p.m. in August. Every day colour has its dusk twin (the sky goes
# indigo to apricot, the land cools, lamps come on); UI steps for the dark scheme (u*, q*).
DUSK = {
    "k0": "#262454", "k1": "#40356f", "k2": "#744680", "k3": "#c0647a", "k4": "#eb9a6c",
    "w0": "#ffd49e", "w1": "#f5a488", "w2": "#c07488", "w3": "#80527f", "w4": "#4c3b68",
    "h0": "#302c56", "h1": "#3f3864", "h2": "#584a78",
    "g0": "#0f1a1f", "g1": "#1a2c2b", "g2": "#264335", "g3": "#35573d", "g4": "#4f7045",
    "c0": "#e9c9a2", "c1": "#c9a88a", "c2": "#a88b76", "c3": "#7e6a63", "c4": "#5e5058",
    "s1": "#4c4466", "s2": "#3a3452",
    "b0": "#1c120c", "b1": "#321f15", "b2": "#4f3422", "b3": "#6e4d31", "b4": "#8e6a45",
    "t0": "#28252f", "t1": "#3e3a47", "t2": "#5c5766", "t3": "#8a8494",
    "y0": "#5e3e10", "y1": "#8c5f18", "y2": "#b88426", "y3": "#d8a848",
    "p0": "#4d6a52", "p1": "#6b8a6c",
}
PAL.update({"d-" + k: v for k, v in DUSK.items()})
PAL.update({
    "lamp0": "#fff0b8", "lamp1": "#ffd66a", "lamp2": "#f0a53a", "fly": "#dcf57a",
    "u0": "#141829", "u1": "#1b1f35", "u2": "#252a47", "u3": "#343a62", "u4": "#4b527c",
    "q0": "#1c3026", "q1": "#284232", "q2": "#3f6a4c",
})
LOCK = Palette(**{k: v for k, v in PAL.items()})


def C(name):
    """A palette colour as RGBA; 'name/alpha' (0–255) for a see-through one."""
    if "/" in name:
        n, a = name.split("/")
        return rgba(PAL[n])[:3] + (int(a),)
    return rgba(PAL[name])


class Cv:
    """A pixel canvas: everything drawn with palette names, no anti-aliasing anywhere."""

    def __init__(self, w, h, fill=None):
        self.im = Image.new("RGBA", (w, h), C(fill) if fill else (0, 0, 0, 0))
        self.w, self.h = w, h
        self.d = ImageDraw.Draw(self.im)
        self.p = self.im.load()

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.p[x, y] = C(c) if isinstance(c, str) else c

    def get(self, x, y):
        return self.p[x, y] if 0 <= x < self.w and 0 <= y < self.h else (0, 0, 0, 0)

    def rect(self, x0, y0, x1, y1, c):
        """Filled, x1/y1 exclusive."""
        if x1 > x0 and y1 > y0:
            self.d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=C(c))

    def hline(self, x0, x1, y, c):
        self.rect(x0, y, x1, y + 1, c)

    def vline(self, x, y0, y1, c):
        self.rect(x, y0, x + 1, y1, c)

    def line(self, x0, y0, x1, y1, c):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.px(x0, y0, c)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def poly(self, pts, c):
        self.d.polygon(pts, fill=C(c))

    def disc(self, cx, cy, r, c):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.px(x, y, c)

    def ring(self, cx, cy, r, c, width=1.0):
        for y in range(int(cy - r - 2), int(cy + r + 3)):
            for x in range(int(cx - r - 2), int(cx + r + 3)):
                d = math.hypot(x - cx, y - cy)
                if r - width < d <= r:
                    self.px(x, y, c)

    def sprite(self, rows, legend, x=0, y=0, flip=False):
        for j, row in enumerate(rows):
            if flip:
                row = row[::-1]
            for i, ch in enumerate(row):
                if ch not in ". ":
                    self.px(x + i, y + j, legend[ch] if ch in legend else ch_default(ch))

    def dither(self, x, y, a, b, t):
        self.px(x, y, b if t * 16 > BAYER[y % 4][x % 4] + 0.5 else a)

    def bands(self, box, names, vertical=True):
        x0, y0, x1, y1 = box
        n = len(names) - 1
        span = (y1 - y0) if vertical else (x1 - x0)
        for y in range(y0, y1):
            for x in range(x0, x1):
                f = ((y - y0) if vertical else (x - x0)) / max(1, span - 1) * n
                i = min(int(f), n - 1)
                self.dither(x, y, names[i], names[i + 1], f - i)

    def paste(self, other, x, y):
        im = other.im if isinstance(other, Cv) else other
        self.im.alpha_composite(im, (x, y))

    def flipped(self):
        out = Cv(self.w, self.h)
        out.im = self.im.transpose(Image.FLIP_LEFT_RIGHT)
        out.d, out.p = ImageDraw.Draw(out.im), out.im.load()
        return out


def ch_default(ch):
    raise KeyError(f"no colour for {ch!r}")


def x2(im, n=2):
    im = im.im if isinstance(im, Cv) else im
    return im.resize((im.width * n, im.height * n), Image.NEAREST)


def out(im, name, scale=2):
    """Lock to the palette, scale by a whole number, save as an optimised PNG in art/."""
    im = im.im if isinstance(im, Cv) else im
    LOCK.lock(im, name)
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / name
    (x2(im, scale) if scale > 1 else im).save(path, optimize=True)
    return path


def write_json(path, data):
    """Atomic: a parallel build never reads half a file."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def rnd(seed):
    return random.Random(seed)


# Shading with the one light: normal · light, the sun high on the left, a little in front.
LIGHT = (-0.55, -0.7, 0.45)
_ll = math.sqrt(sum(v * v for v in LIGHT))
LIGHT = tuple(v / _ll for v in LIGHT)


def lit(nx, ny, nz):
    return nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]


def tone(cv, x, y, t, names):
    """t 0–1 → one of the names (dark → light), dithered at the steps."""
    n = len(names) - 1
    f = max(0.0, min(0.999, t)) * n
    i = min(int(f), n - 1)
    frac = f - i
    # only dither near the step, so clusters stay clean
    if frac < 0.4:
        cv.px(x, y, names[i])
    elif frac > 0.6:
        cv.px(x, y, names[i + 1])
    else:
        cv.dither(x, y, names[i], names[i + 1], (frac - 0.4) / 0.2)


def cloud(cv, blobs, base, names=("w4", "w3", "w2", "w1", "w0"), soft=1.6):
    """A cumulus from circles (cx, cy, r), flat at `base`: one height field over all the lobes,
    smoothed so they merge, lit by the one light (rim light top-left, pockets in shade)."""
    import numpy as np

    xs = [b[0] - b[2] for b in blobs] + [b[0] + b[2] for b in blobs]
    ys = [b[1] - b[2] for b in blobs]
    x0, x1 = int(min(xs)) - 2, int(max(xs)) + 3
    y0, y1 = int(min(ys)) - 2, int(base) + 1
    gy, gx = np.mgrid[y0:y1, x0:x1] + 0.5
    h = np.zeros(gx.shape)
    for cx, cy, r in blobs:
        d2 = (gx - cx) ** 2 + (gy - cy) ** 2
        h = np.maximum(h, np.sqrt(np.clip(r * r - d2, 0, None)))
    inside = h > 0
    inside &= gy <= base
    # smooth the field (a small box blur, a few passes) so neighbouring lobes join
    hs = h.copy()
    for _ in range(int(soft * 2)):
        p = np.pad(hs, 1, mode="edge")
        hs = (p[1:-1, 1:-1] * 2 + p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 6
    ny, nx = np.gradient(hs)
    nz = np.full(hs.shape, 1.6)
    ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    nx, ny, nz = -nx / ln, -ny / ln, nz / ln
    t = (nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]) * 1.15 - 0.02
    t -= np.clip(gy - (base - 7), 0, None) * 0.07  # the flat base sits in its own shade
    for j in range(gx.shape[0]):
        for i in range(gx.shape[1]):
            if inside[j, i]:
                tone(cv, x0 + i, y0 + j, float(t[j, i]), list(names))


def _grain(x, y, one_in):
    """A scattered grain, the same every run: true for about one pixel in `one_in`."""
    h = (x * 73856093) ^ (y * 19349663) ^ 0x5BD1E995
    h = (h * 2654435761) & 0xFFFFFFFF
    return h % one_in == 0


def recolour(im, mapping):
    """A new image with palette colours swapped by name (alpha kept)."""
    im = im.im if isinstance(im, Cv) else im
    table = {rgba(PAL[a])[:3]: rgba(PAL[b])[:3] for a, b in mapping.items()}
    out = im.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a and (r, g, b) in table:
                px[x, y] = table[(r, g, b)] + (a,)
    cv = Cv(out.width, out.height)
    cv.im, cv.d, cv.p = out, ImageDraw.Draw(out), out.load()
    return cv


def to_dusk(im):
    return recolour(im, {k: "d-" + k for k in DUSK})


def glow(cv, cx, cy, rx, ry, colour="lamp1", strength=0.6, box=None):
    """A lamp's light: a dithered ellipse of `colour` over what's there."""
    x0, y0, x1, y1 = box or (int(cx - rx), int(cy - ry), int(cx + rx) + 1, int(cy + ry) + 1)
    for y in range(max(0, y0), min(cv.h, y1)):
        for x in range(max(0, x0), min(cv.w, x1)):
            d = math.hypot((x - cx) / rx, (y - cy) / ry)
            if d < 1 and cv.get(x, y)[3]:
                cv.dither(x, y, cv.get(x, y), colour, (1 - d) * strength)
