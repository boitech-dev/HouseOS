"""Legacy (carved-night): every picture of the theme, drawn by code.

    python3 docs/design/themes/carved-night/make.py            # everything → themes/carved-night/art
    python3 docs/design/themes/carved-night/make.py hero crest  # only these

Pixel art on one grid: every picture is drawn at native size and scaled ×3 (slots), or shipped at
native size with "scale": 3 (layers). One palette (PAL below), locked on every picture; one light:
the moon, high on the left, cool; warm candle and ember light from the windows.
"""

import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "themes/_kit/art"))
from PIL import Image  # noqa: E402

from pixel import BAYER, Palette, rgba, save, scale  # noqa: E402

OUT = ROOT / "themes/carved-night/art"
X = 3  # the one pixel size

# ---------------------------------------------------------------- palette
PAL = Palette(
    # night: moonlit violet-blue, shadows toward indigo, lights toward lilac
    night=["#05060f", "#0a0b1c", "#10122a", "#171a38", "#20244a", "#2b305e", "#3a4076", "#4e5690",
           "#6a72ab", "#8e95c8", "#b8bde2", "#dfe0f4"],
    moon=["#fff9e8", "#f1e8cf", "#d9cfb6", "#b3adc4"],
    ember=["#3a1418", "#6e2a22", "#a8472a", "#d9713a", "#f0a052", "#f8c878", "#ffe6a8", "#fff6dc"],
    wood=["#1e1018", "#2e1a24", "#442834", "#5e3a40", "#7e5450", "#a2735e"],
    velvet=["#2a0c1e", "#4c1430", "#76203e", "#a4344e", "#cf5a68"],
    paper=["#e8dcc2"],
    warm=["#171329", "#221630", "#2f1b30", "#43222c"],  # candlelight on night walls
    gas=["#0f2a26", "#1d4538", "#346a4c", "#5f9464", "#a9d18e", "#dcefb4"],
    brass=["#3a2612", "#6a4a1e", "#a07a30", "#d4ac52", "#f0d488"],
    ghost=["#7d8fd0", "#aebdf0", "#dce6ff", "#f6f9ff"],
    lilac=["#3e2f66", "#5e4a92", "#8a72be", "#b8a2e4"],
)
N, M, E, W, V, G, B, H, L, R = (PAL[k] for k in ("night", "moon", "ember", "wood", "velvet", "gas", "brass", "ghost", "lilac", "warm"))
CLEAR = (0, 0, 0, 0)


# ---------------------------------------------------------------- drawing
class Pic:
    """A native-size picture with exact, un-antialiased drawing."""

    def __init__(self, w, h, fill=None):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w, h), rgba(fill) if fill else CLEAR)
        self.px = self.im.load()

    def dot(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[x, y] = rgba(c) if c else CLEAR

    def get(self, x, y):
        return self.px[x, y] if 0 <= x < self.w and 0 <= y < self.h else CLEAR

    def rect(self, x0, y0, x1, y1, c):  # inclusive
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.px[x, y] = rgba(c) if c else CLEAR

    def hline(self, x0, x1, y, c):
        self.rect(min(x0, x1), y, max(x0, x1), y, c)

    def vline(self, x, y0, y1, c):
        self.rect(x, min(y0, y1), x, max(y0, y1), c)

    def line(self, x0, y0, x1, y1, c):
        """Bresenham: clean single-pixel lines."""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.dot(x0, y0, c)
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
        """A filled polygon (scanline, pixel centres)."""
        ys = [p[1] for p in pts]
        for y in range(max(0, int(min(ys))), min(self.h, int(max(ys)) + 1)):
            cy = y + 0.5
            xs = []
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
                if (y0 <= cy < y1) or (y1 <= cy < y0):
                    xs.append(x0 + (cy - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                for x in range(int(math.ceil(a - 0.5)), int(math.floor(b - 0.5)) + 1):
                    self.dot(x, y, c)

    def disc(self, cx, cy, r, c):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                    self.dot(x, y, c)

    def ring(self, cx, cy, r0, r1, c, t=None):
        """Pixels between radii r0..r1; with t (0–1), Bayer-dithered at that coverage."""
        for y in range(int(cy - r1 - 1), int(cy + r1 + 2)):
            for x in range(int(cx - r1 - 1), int(cx + r1 + 2)):
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if r0 <= d < r1 and (t is None or t * 16 > BAYER[y % 4][x % 4] + 0.5):
                    self.dot(x, y, c)

    def paste(self, other, x, y):
        src = other.im if isinstance(other, Pic) else other
        self.im.alpha_composite(src, (x, y))
        self.px = self.im.load()

    def vgrad(self, x0, y0, x1, y1, colours, curve=1.0):
        """A dithered vertical ramp through colours (top → bottom)."""
        n = len(colours) - 1
        for y in range(y0, y1 + 1):
            f = ((y - y0) / max(1, y1 - y0)) ** curve * n
            i = min(int(f), n - 1)
            t = f - i
            for x in range(x0, x1 + 1):
                self.dot(x, y, colours[i + 1] if t * 16 > BAYER[y % 4][x % 4] + 0.5 else colours[i])

    def flip(self):
        p = Pic(self.w, self.h)
        p.im = self.im.transpose(Image.FLIP_LEFT_RIGHT)
        p.px = p.im.load()
        return p

    def outline(self, c, sides="lrtb"):
        """A 1px outline hugging the opaque shape."""
        src = self.im.copy().load()
        for y in range(self.h):
            for x in range(self.w):
                if src[x, y][3]:
                    continue
                for dx, dy, s in ((-1, 0, "r"), (1, 0, "l"), (0, -1, "b"), (0, 1, "t")):
                    if s in sides and 0 <= x + dx < self.w and 0 <= y + dy < self.h and src[x + dx, y + dy][3]:
                        self.dot(x, y, c)
                        break


def export(pic, name, x=X):
    im = pic.im if isinstance(pic, Pic) else pic
    PAL.lock(im, name)
    path = save(scale(im, x) if x > 1 else im, OUT / name)
    kb = path.stat().st_size / 1000
    print(f"  {name:28} {im.width * x}×{im.height * x}  {kb:6.1f} KB")
    if kb > 200:
        raise SystemExit(f"{name}: {kb:.0f} KB, over the 200 KB budget")
    return path


# ---------------------------------------------------------------- the manor
def manor(lit=None, ghost=None, candle=0):
    """The house: a Victorian manor, 104 × 80, moonlight from the upper left.
    lit: which windows glow (names; None: the usual ones). ghost: 0..1, a ghost crossing the
    tower's top window (None: none). candle: 0..2, the porch lamp's flicker."""
    p = Pic(104, 80)
    ink = N[0]
    gy = 79  # ground

    def gable(x0, apex_x, apex_y, x1, eave_y, lit_side=N[2], dark_side=N[1], rows=3):
        """A gable roof: the moonlit left slope a step brighter, shingle rows, a lit bargeboard."""
        p.poly([(x0, eave_y + 1), (apex_x + 0.5, apex_y), (x1 + 1, eave_y + 1)], dark_side)
        p.poly([(x0, eave_y + 1), (apex_x + 0.5, apex_y), (apex_x + 0.5, eave_y + 1)], lit_side)
        for y in range(apex_y + 3, eave_y + 1, rows):
            for x in range(x0, x1 + 1):
                c = p.get(x, y)[:3]
                if c == rgba(lit_side)[:3] and (x + y) % 3:
                    p.dot(x, y, N[1])
                elif c == rgba(dark_side)[:3] and (x + y) % 3:
                    p.dot(x, y, N[0])
        p.line(x0, eave_y, apex_x, apex_y, N[6])  # bargeboard in moonlight
        p.line(apex_x + 1, apex_y + 1, x1, eave_y, N[3])
        p.hline(x0 - 1, x1 + 1, eave_y + 1, ink)

    def walls(x0, y0, x1, face=N[2], edge=N[5], course=N[1]):
        p.rect(x0, y0, x1, gy, face)
        p.vline(x0, y0, gy, edge)
        p.vline(x1, y0, gy, N[1])
        for y in range(y0 + 4, gy, 5):
            p.hline(x0 + 1, x1 - 1, y, course)
            for x in range(x0 + 1 + (y // 5) % 2 * 3, x1, 6):  # stone joints
                p.dot(x, y + 1, course)

    # --- right wing (set back: a step darker)
    walls(74, 46, 98, N[1], N[4], N[0])
    gable(71, 86, 32, 101, 46, N[2], N[1])
    # --- main block
    walls(30, 35, 76)
    gable(25, 53, 9, 81, 35)
    p.vline(53, 3, 9, N[6])  # finial and cresting
    p.dot(53, 2, N[8])
    p.hline(52, 54, 5, N[6])
    # round window in the gable, a rose of mullions
    p.disc(53.5, 24.5, 4.4, ink)
    p.disc(53.5, 24.5, 3.3, N[1])
    p.hline(51, 56, 24, ink)
    p.vline(53, 22, 27, ink)
    # chimneys, brick-capped, the left face lit
    for cx, top, hgt in ((64, 10, 13), (40, 17, 8)):
        p.rect(cx, top, cx + 3, top + hgt, N[2])
        p.vline(cx, top, top + hgt, N[5])
        p.vline(cx + 3, top, top + hgt, N[1])
        p.rect(cx - 1, top - 1, cx + 4, top, N[4])
        p.hline(cx - 1, cx + 3, top - 1, N[6])
        p.dot(cx + 1, top - 2, ink)
    # --- the tower, in front
    walls(12, 27, 31)
    p.hline(11, 32, 27, N[5])  # cornice
    p.hline(11, 32, 28, ink)
    p.poly([(9, 27), (21.5, 0), (34, 27)], N[1])
    p.poly([(9, 27), (21.5, 0), (21.5, 27)], N[2])
    for y in range(5, 26, 3):
        for x in range(9, 35):
            c = p.get(x, y)[:3]
            if c == rgba(N[2])[:3] and (x + y) % 2:
                p.dot(x, y, N[1])
            elif c == rgba(N[1])[:3] and (x + y) % 2:
                p.dot(x, y, N[0])
    p.line(9, 26, 21, 1, N[6])
    p.hline(8, 35, 26, ink)
    p.dot(8, 25, N[5])  # the flare
    p.dot(35, 25, N[3])
    p.vline(21, 0, 2, N[8])  # the finial
    p.dot(21, 0, M[0])
    # a widow's walk on the right wing
    for x in range(78, 95, 2):
        p.vline(x, 44, 45, N[4])
    # --- the porch
    p.rect(40, 65, 68, gy, N[0])
    gable(38, 54, 57, 70, 64, N[2], N[1], 2)
    for cx in (41, 49, 59, 67):
        p.vline(cx, 66, gy - 3, N[5])
        p.dot(cx + 1, 66, N[3])
    p.rect(51, 67, 57, gy - 3, ink)  # the door
    p.rect(52, 68, 56, gy - 3, W[2])
    p.vline(54, 68, gy - 3, W[1])
    p.dot(55, 73, B[3])
    p.rect(52, 67, 56, 67, E[3])  # transom light
    p.rect(39, gy - 2, 69, gy - 2, N[4])  # steps
    p.rect(37, gy - 1, 71, gy, N[3])
    p.hline(38, 70, gy - 1, N[5])
    lamp = (E[6], E[5], E[7])[candle % 3]
    p.dot(46, 69, lamp)
    p.dot(46, 68, E[4])
    p.dot(46, 70, E[3])
    p.dot(46, 67, ink)

    # --- windows: arched, mullioned; lit ones glow candle-warm and warm the stone around them
    def window(x, y, w, h, on):
        p.rect(x - 1, y, x + w, y + h, ink)
        p.hline(x, x + w - 1, y - 1, ink)  # the arch
        glass = E[4] if on else N[1]
        p.rect(x, y, x + w - 1, y + h - 1, glass)
        if on:
            p.rect(x, y + h // 2, x + w - 1, y + h - 1, E[3])
            p.dot(x, y, E[6])
            mull = E[2]
        else:
            p.dot(x, y + 1, N[5])  # the moon in dark glass
            p.dot(x + 1, y, N[4])
            mull = ink
        if w >= 3:
            p.vline(x + w // 2, y, y + h - 1, mull)
        p.hline(x, x + w - 1, y + h // 2 - 1, mull)
        p.hline(x - 1, x + w, y + h, N[5])  # sill, moonlit

    lit = {"t2", "m1", "m4", "w1", "g2"} if lit is None else lit
    window(19, 33, 5, 7, "t1" in lit)
    window(19, 46, 5, 7, "t2" in lit)
    window(19, 59, 5, 7, "t3" in lit)
    for i, x in enumerate((35, 44, 62, 70)):
        window(x, 41, 3 if x in (35, 70) else 4, 7, f"m{i + 1}" in lit)
    window(44, 52, 4, 7, "g1" in lit)
    window(61, 52, 4, 7, "g2" in lit)
    window(80, 53, 4, 6, "w1" in lit)
    window(89, 53, 4, 6, "w2" in lit)
    window(85, 38, 3, 4, "w3" in lit)
    # a ghost drifting past the tower's top window
    if ghost is not None:
        gx = 17 + round(ghost * 9)
        for dy, row in enumerate((".hh.", "hHHh", "hkHk", "hHHh", "h.h.")):
            for dx, ch in enumerate(row):
                x, y = gx + dx, 34 + dy
                if ch != "." and 19 <= x <= 23 and 33 <= y <= 39 and (x, y) != (21, 35):
                    p.dot(x, y, {"h": H[1], "H": H[3], "k": N[3]}[ch])
    return p


# ---------------------------------------------------------------- nature
def dead_tree(p, x, y, height, seed, colour, lean=0.0, hi=None, spread=0.55):
    """A bare, twisted tree: a tapering trunk forking into crooked branches and fine twigs."""
    rnd = random.Random(seed)

    def branch(x0, y0, ang, length, thick, depth):
        x1 = x0 + math.cos(ang) * length
        y1 = y0 - math.sin(ang) * length
        steps = max(1, int(length * 1.5))
        wob = rnd.uniform(0.4, 1.2)
        for s in range(steps + 1):
            t = s / steps
            bx = x0 + (x1 - x0) * t + math.sin(t * 5 + seed + depth) * wob * min(1, length / 8)
            by = y0 + (y1 - y0) * t
            w = max(1, round(thick * (1 - 0.35 * t)))
            for k in range(w):
                p.dot(round(bx) - w // 2 + k, round(by), colour)
            if hi and w >= 2 and ang > 1.2:
                p.dot(round(bx) - w // 2, round(by), hi)  # the moonlit edge
        if length < 2.5 or depth > 6:
            return
        n = 3 if depth in (1, 2) and rnd.random() < 0.6 else 2
        for i in range(n):
            turn = (i - (n - 1) / 2) * spread * 1.6 + rnd.uniform(-0.25, 0.25)
            branch(x1, y1, ang + turn, length * rnd.uniform(0.62, 0.8), max(1, thick - 1), depth + 1)
        if thick <= 2 and rnd.random() < 0.7:  # a twig
            ta = ang + rnd.choice((-1, 1)) * rnd.uniform(0.8, 1.3)
            p.line(round(x1), round(y1), round(x1 + math.cos(ta) * 2), round(y1 - math.sin(ta) * 2), colour)

    for dx in range(-3, 4):  # roots
        p.dot(x + dx, y, colour)
    p.dot(x - 4, y + 1, colour)
    p.dot(x + 4, y + 1, colour)
    trunk = max(2, min(5, round(height / 20)))
    branch(x, y, math.pi / 2 + lean, height * 0.3, trunk, 0)


def fence(p, x0, x1, y, colour, hi):
    """Wrought iron: spear-headed bars, two rails, a finial post every so often."""
    for x in range(x0, x1 + 1, 3):
        post = (x - x0) % 18 == 0
        top = y - (12 if post else 10)
        p.vline(x, top, y, colour)
        p.dot(x, top - 1, hi)  # spear tip catching the moon
        if post:
            p.rect(x - 1, top, x + 1, top + 1, colour)
            p.dot(x, top - 2, hi)
    p.hline(x0, x1, y - 8, colour)
    p.hline(x0, x1, y - 2, colour)
    for x in range(x0 + 1, x1, 3):
        p.dot(x, y - 7, colour)  # scrolls between the bars
        p.dot(x + 1, y - 7, colour)


def hill(p, x0, x1, top, bottom, fill, rim, seed=0, bump=0.0):
    """A soft hill: a sine-bumped curve, rim-lit by the moon."""
    for x in range(x0, x1 + 1):
        t = (x - x0) / max(1, x1 - x0)
        yy = top + (bottom - top) * (1 - math.sin(t * math.pi) ** 0.8) + math.sin(t * 9 + seed) * bump
        yy = round(yy)
        p.vline(x, yy, p.h - 1, fill)
        p.dot(x, yy, rim)


def stars(p, box, n, seed, colours=(None,), cross_above=0):
    """Stars: mostly single pixels, some a dim pair; a rare four-point star only above
    `cross_above` (the top band of a sky, far from any control)."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    for _ in range(n):
        x, y = rnd.randrange(x0, x1), rnd.randrange(y0, y1)
        c = rnd.choice(colours)
        p.dot(x, y, c)
        roll = rnd.random()
        if roll < 0.04 and y < cross_above:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p.dot(x + dx, y + dy, N[6])
            p.dot(x, y, N[10])
        elif roll < 0.16:
            p.dot(x + 1, y, N[5])


def moon(p, cx, cy, r, halo=True):
    """A big full moon with its halo (two solid rings, or dithered) and a few quiet craters."""
    if halo == "solid":
        p.ring(cx, cy, r, r + 7, N[4])
        p.ring(cx, cy, r, r + 3, N[5])
    elif halo:
        p.ring(cx, cy, r, r + 14, N[4], 0.25)
        p.ring(cx, cy, r, r + 9, N[5], 0.35)
        p.ring(cx, cy, r, r + 4, N[6], 0.5)
    p.disc(cx, cy, r, M[1])
    # shading: toward the lower right, lilac
    for y in range(int(cy - r), int(cy + r) + 1):
        for x in range(int(cx - r), int(cx + r) + 1):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if d < r:
                lx, ly = (x + 0.5 - cx) / r, (y + 0.5 - cy) / r
                shade = (lx + ly) * 0.5 + (d / r) ** 3 * 0.5
                if shade > 0.55 and BAYER[y % 4][x % 4] < 8:
                    p.dot(x, y, M[2])
                if shade > 0.75:
                    p.dot(x, y, M[2])
                if shade < -0.45:
                    p.dot(x, y, M[0])
    rnd = random.Random(7)
    for _ in range(int(r * 0.9)):
        a, d = rnd.uniform(0, 6.28), rnd.uniform(0, r * 0.75)
        x, y = round(cx + math.cos(a) * d), round(cy + math.sin(a) * d)
        cr = rnd.choice((1, 1, 1.6, 2.2))
        if cr > 1:
            p.disc(x, y, cr, M[2])
            p.dot(x - 1, y - 1, M[3]) if cr > 2 else None
        else:
            p.dot(x, y, M[2])


def cloud(p, x, y, w, seed, body=None, lit=None, rim=None):
    """A long, thin streak of night cloud: flat below, a few low humps, lit on top by the moon."""
    body, lit, rim = body or N[4], lit or N[6], rim or N[8]
    rnd = random.Random(seed)
    layer = Pic(p.w, p.h)
    humps = [(rnd.uniform(0.1, 0.9), rnd.uniform(0.5, 1.0)) for _ in range(3)]
    for xx in range(int(x), int(x + w)):
        t = (xx - x) / w
        top = 1.2 * math.sin(t * math.pi) ** 0.5
        for cx, hgt in humps:
            top += hgt * 2.6 * max(0, 1 - abs(t - cx) * 7)
        th = round(top)
        for yy in range(y - th, y + 1):
            layer.dot(xx, yy, body)
        layer.dot(xx, y - th, lit if 0.08 < t < 0.92 else body)
        if th >= 2 and rnd.random() < 0.5:
            layer.dot(xx, y - th, rim)
        if BAYER[y % 4][xx % 4] < 8:
            layer.dot(xx, y, N[3])  # dim belly
    # frayed ends
    for k in range(6):
        layer.dot(int(x) - k * 2 - 2, y, body if k % 2 == 0 else None)
        layer.dot(int(x + w) + k * 2 + 1, y - (k % 2), body if k % 3 else None)
    p.paste(layer, 0, 0)


def bat(p, x, y, frame=0, c=None):
    """A tiny bat, wings up (0) or down (1)."""
    c = c or N[0]
    rows = ("k.....k", "kk.k.kk", ".kkkkk.", "...k...") if frame == 0 else (".......", "..k.k..", "kkkkkkk", "k..k..k")
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == "k":
                p.dot(x + dx, y + dy, c)


# ---------------------------------------------------------------- pictures
def hero():
    """Home's cover: the manor on its hill under a huge moon (240 × 90 → 720 × 270)."""
    p = Pic(240, 90)
    p.vgrad(0, 0, 239, 89, [N[1], N[2], N[3], N[4], N[5]], curve=1.4)
    stars(p, (0, 0, 240, 62), 80, 3, (N[6], N[7], N[8], N[9]), cross_above=18)
    moon(p, 104, 30, 17, "solid")
    cloud(p, 186, 12, 44, 9)
    cloud(p, 6, 34, 40, 2)
    cloud(p, 50, 58, 30, 4, N[3], N[5], N[6])
    # far hills, then the manor's hill rising to the right
    hill(p, -60, 140, 72, 96, N[3], N[5], 1, 1.0)
    hill(p, 100, 300, 70, 110, N[2], N[4], 3, 0.8)
    house = manor()
    p.paste(house, 128, 3)
    # a path climbing to the porch, and the lamp's light on it
    for y in range(83, 90):
        x0 = 182 - (y - 82) * 3
        for x in range(x0, x0 + 6 + (y - 83)):
            p.dot(x, y, N[4] if (x + y) % 5 else N[5])
    p.hline(166, 200, 82, N[3])
    # the fence along the hill, the trees framing it
    fence(p, 120, 239, 88, N[0], N[6])
    dead_tree(p, 78, 89, 96, 11, N[0], -0.12, N[3])
    # the moon again over the crown, crossed only by three thin twigs, a cloud across its foot
    moon(p, 104, 30, 17, False)
    for pts in (((86, 25), (90, 23), (93, 20), (95, 16)), ((90, 23), (94, 24)), ((87, 35), (91, 33), (95, 30)),
                ((91, 33), (93, 35))):
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            p.line(xa, ya, xb, yb, N[0])
    cloud(p, 76, 44, 60, 5)
    # Nox, the house's black cat, on the last fence post: two green eyes
    for dx, dy, c in ((0, 0, N[0]), (1, 0, N[0]), (3, 0, N[0]), (4, 0, N[0]), (0, 1, N[0]), (1, 1, N[0]), (2, 1, N[0]),
                      (3, 1, N[0]), (4, 1, N[0]), (1, 1, G[4]), (3, 1, G[4]), (0, 2, N[0]), (1, 2, N[0]), (2, 2, N[0]),
                      (3, 2, N[0]), (4, 2, N[0]), (1, 3, N[0]), (2, 3, N[0]), (3, 3, N[0]), (0, 4, N[0]), (1, 4, N[0]),
                      (2, 4, N[0]), (3, 4, N[0]), (4, 4, N[0]), (0, 5, N[0]), (1, 5, N[0]), (2, 5, N[0]), (3, 5, N[0]),
                      (4, 5, N[0]), (5, 5, N[0]), (6, 4, N[0]), (6, 3, N[0]), (0, 0, N[4]), (4, 0, N[4])):
        p.dot(208 + dx, 71 + dy, c)
    bat(p, 10, 44)
    bat(p, 24, 50, 1)
    bat(p, 170, 6, 1)
    # candlelight spilling from the windows and the porch onto the stone and the path
    for wx, wy in ((19 + 128, 46 + 3), (35 + 128, 41 + 3), (70 + 128, 41 + 3), (61 + 128, 52 + 3), (80 + 128, 53 + 3)):
        glow(p, wx + 2, wy + 4, 5, None, 0.5, only_clear=False)
    for y in range(82, 90):  # the porch lamp's pool of ember light on the path
        half = 12 - abs(y - 85.5) * 2.2
        for x in range(round(172 - half), round(172 + half) + 1):
            d = abs(x - 172) / max(1, half)
            if p.get(x, y)[:3] in (rgba(N[4])[:3], rgba(N[5])[:3], rgba(N[3])[:3]) and (1 - d) * 16 > BAYER[y % 4][x % 4] + 3:
                p.dot(x, y, E[2] if d < 0.35 else E[1])
    # the old family plot on the near hill: three leaning stones, moonlit on the left
    for gx, gy, h, lean in ((22, 84, 6, 0), (34, 86, 5, 1), (48, 85, 7, -1)):
        p.rect(gx, gy - h, gx + 4, gy, N[2])
        p.hline(gx + 1, gx + 3, gy - h - 1, N[2])
        p.vline(gx, gy - h, gy, N[5])
        p.dot(gx + 1, gy - h - 1, N[5])
        p.hline(gx + 1, gx + 3, gy - h + 2, N[1])  # an engraved line, no letters
        if lean:
            p.dot(gx + (4 if lean > 0 else 0) + lean, gy - h, N[2])
    # a lamp post on the path with its lantern lit
    p.vline(98, 66, 88, N[0])
    p.hline(96, 100, 88, N[0])
    p.rect(96, 62, 100, 66, N[0])
    p.rect(97, 63, 99, 65, E[5])
    p.dot(98, 64, E[7])
    p.hline(95, 101, 61, N[0])
    p.dot(98, 60, N[0])
    glow(p, 98, 64, 9, None, 0.55, only_clear=False)
    # the ground: the near hill and a low mist over it
    hill(p, 60, 150, 86, 94, N[1], N[3], 5, 0.4)
    for x in range(240):  # a low mist: long dithered bands
        for y in range(84, 90):
            t = (y - 84) / 6 * (0.6 + 0.4 * math.sin(x / 11))
            if t * 16 > BAYER[y % 4][x % 4] + 6 and p.get(x, y)[:3] != rgba(N[0])[:3]:
                p.dot(x, y, N[5])
    return p


def sky():
    """page.backdrop: the night behind every page (534 × 300 → 1602 × 900): a deep sky, the moon
    high on the left (clear of the rail), stars, far hills. Layers draw over it, the scrim over all."""
    p = Pic(534, 300)
    p.vgrad(0, 0, 533, 299, [N[1], N[1], N[2], N[3], N[4]], curve=1.2)
    stars(p, (0, 0, 534, 230), 280, 21, (N[5], N[6], N[7], N[8]), cross_above=40)
    # the moon high on the left, drawn in its dimmer lilac (the page's words may pass over it)
    p.ring(140, 44, 20, 26, N[4])
    p.ring(140, 44, 20, 22, N[5])
    p.disc(140, 44, 20, M[3])
    rnd = random.Random(9)
    for _ in range(16):
        a, d = rnd.uniform(0, 6.28), rnd.uniform(0, 15)
        p.disc(round(140 + math.cos(a) * d), round(44 + math.sin(a) * d), rnd.choice((1, 1.5, 2.2)), N[8])
    for y in range(24, 65):
        for x in range(120, 161):
            if math.hypot(x + 0.5 - 140, y + 0.5 - 44) < 20 and (x - 140) + (y - 44) > 14 and BAYER[y % 4][x % 4] < 8:
                p.dot(x, y, N[7])
    hill(p, -80, 300, 244, 330, N[2], N[4], 7, 1.5)
    hill(p, 220, 640, 236, 320, N[3], N[5], 8, 1.2)
    hill(p, 120, 470, 262, 330, N[2], N[4], 9, 0.8)
    for x, y in ((40, 268), (46, 270), (71, 266), (90, 272), (128, 270), (330, 262), (338, 263)):
        p.dot(x, y, E[3])  # far windows on the hills
    return p


def clouds_tile():
    """A drifting band of cloud streaks, a seamless tile (240 × 90, shown ×3): they cross the moon."""
    p = Pic(240, 90)
    for x, y, w, seed in ((10, 30, 70, 41), (120, 52, 90, 42), (-40, 74, 60, 43), (200, 74, 60, 43), (150, 16, 40, 44),
                          (60, 64, 50, 45)):
        cloud(p, x, y, w, seed)
    return p  # seamless: the streaks at -40 and 200 are the same cloud, a tile apart


def page_ghost(p, x, y, fade=0.0):
    """A ghost drifting in the garden (7 × 9), bright enough to find under the page's scrim."""
    rows = ("..hhh..", ".hHHHh.", "hHkHkHh", "hHHHHHh", "hHHpHHh", "hHHHHHh", "hHHHHHh", "hH.hH.h", "h...h..")
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch != "." and BAYER[(y + dy) % 4][(x + dx) % 4] / 16 >= fade:
                p.dot(x + dx, y + dy, {"h": H[1], "H": H[3], "k": N[2], "p": H[0]}[ch])


def manor_scene(frame=0, frames=32):
    """The page's manor on its hill (220 × 120, 32 frames side by side): now and then a ghost
    slips out of the tower's window and drifts down the garden; the porch lamp flickers."""
    p = Pic(220, 120)
    hill(p, 0, 300, 96, 150, N[2], N[5], 12, 0.6)
    ghost = (frame - 8) / 4 if 8 <= frame <= 12 else None
    lit = {"t2", "m1", "m4", "w1", "g2"} | ({"t1"} if 6 <= frame <= 14 else set())
    house = manor(lit=lit, ghost=ghost, candle=(frame * 7) % 3)
    p.paste(house, 100, 26)
    for y in range(106, 120):  # the path down the hill, lamp-lit
        x0 = 154 - (y - 105) * 2
        for x in range(x0, x0 + 7 + (y - 106) // 2):
            p.dot(x, y, N[4] if (x + y) % 6 else N[5])
    if 12 < frame <= 26:  # out in the garden: drifting down and to the left, fading at the end
        t = (frame - 12) / 14
        page_ghost(p, round(116 - t * 40), round(62 + t * 30 + math.sin(t * 9) * 2), max(0, (t - 0.6) * 2.5))
    fence(p, 90, 219, 116, N[0], N[6])
    return p


def manor_sheet():
    out = Image.new("RGBA", (220 * 32, 120))
    for i in range(32):
        out.paste(manor_scene(i).im, (i * 220, 0))
    return out


def near_scene(frame=0):
    """The garden close by (170 × 110, 8 frames): a dead tree, the iron fence and the owl on its
    post, who blinks. Drawn clear of the rail, with a little parallax."""
    p = Pic(170, 110)
    for x in range(0, 170):  # the near ground
        top = round(100 - 3 * math.sin(x / 50))
        p.vline(x, top, 109, N[1])
        p.dot(x, top, N[3])
    fence(p, 60, 169, 106, N[0], N[6])
    dead_tree(p, 108, 100, 110, 23, N[0], 0.15, N[4])
    ox, oy = 146, 84  # the owl on a post: tufts, a pale face disc, two amber eyes
    owl = (".k...k.", ".kk.kk.", "kkkkkkk", "kmEkEmk", "kmmrmmk", "kLmLmLk", "kLLmLLk", ".kLLLk.", "..k.k..")
    blink = frame == 5
    for dy, row in enumerate(owl):
        for dx, ch in enumerate(row):
            if ch != ".":
                c = {"k": N[0], "m": N[5], "E": (N[4] if blink else E[5]), "r": E[3], "L": N[3]}[ch]
                p.dot(ox + dx, oy + dy, c)
    p.dot(ox + 2, oy + 3, N[0] if not blink else N[4])
    p.dot(ox + 4, oy + 3, N[0] if not blink else N[4])
    if not blink:
        p.dot(ox + 2, oy + 3, E[5])
        p.dot(ox + 4, oy + 3, E[5])
    p.rect(ox + 2, oy + 9, ox + 4, 106, N[0])  # its post
    p.dot(ox + 2, oy + 9, N[5])
    return p


def bat_sheet():
    """A bat, two wing beats (13 × 8 each)."""
    rows = [("kk.........kk", ".kkk.....kkk.", "..kkkk.kkkk..", "...kkkkkkk...", ".....kEk.....", "......k......", "", ""),
            ("", "", "....k...k....", "...kkk.kkk...", ".kkkkkkkkkkk.", "kk..kkEkk..kk", "k.....k.....k", "")]
    out = Pic(26, 8)
    for f, frame in enumerate(rows):
        for dy, row in enumerate(frame):
            for dx, ch in enumerate(row):
                if ch != ".":
                    out.dot(f * 13 + dx, dy, N[0] if ch == "k" else E[4])
    return out


def shooting_star():
    """A shooting star with a fading, dithered tail (40 × 3)."""
    p = Pic(40, 3)
    p.dot(1, 1, M[0])
    p.dot(0, 1, H[3])
    p.dot(1, 0, H[2])
    p.dot(1, 2, H[2])
    for x in range(2, 40):
        t = x / 40
        if t < 0.3 or BAYER[1][x % 4] / 16 > (t - 0.3) * 1.4:
            p.dot(x, 1, H[2] if t < 0.25 else H[1] if t < 0.55 else H[0])
    return p


def candle(p, x, y, h=6, frame=0, wax=None, lit=True, flame=None):
    """A candle standing at (x, y) (its foot), h tall, a flame in four flickers. flame: "flare"
    (tall and white-hot), "low" (guttering), "out" (a glowing wick and smoke), None (normal)."""
    wax = wax or M[1]
    p.rect(x, y - h + 1, x + 1, y, wax)
    p.vline(x + 1, y - h + 2, y, M[2])  # the shaded side
    p.dot(x, y - h + 2, M[0])
    if frame % 2 == 0:
        p.dot(x + 1, y - h + 3, M[1])  # a drip
    if not lit:
        return
    p.dot(x, y - h, N[0])  # the wick
    if flame == "out":
        p.dot(x, y - h, E[2])
        for k in range(1, 4 + frame % 2):
            p.dot(x + (k % 2) * (1 if frame % 2 else -1), y - h - k, N[5] if k < 3 else N[4])
        return
    if flame == "low":
        p.dot(x + frame % 2, y - h - 1, E[3])
        return
    fx = x + (0, 0, 1, 0)[frame % 4]
    top = (3, 4, 3, 2)[frame % 4] if flame != "flare" else 5
    if flame == "flare":
        p.dot(x - 1, y - h - 2, E[5])
        p.dot(x + 1, y - h - 3, E[5])
    for k in range(top):
        p.dot(fx, y - h - 1 - k, (E[6], E[5], E[4], E[3])[min(3, k)] if k else E[7])
    p.dot(fx - 1 if frame % 2 else fx + 1, y - h - 1, E[4])


def glow(p, cx, cy, r, colour=None, t=0.3, only_clear=True):
    """A pool of light around (cx, cy): on clear pixels a sparse dither of `colour`; on walls
    (only_clear False) the wall's dark pixels warm up in steps through the warm ramp."""
    for y in range(int(cy - r), int(cy + r) + 1):
        for x in range(int(cx - r), int(cx + r) + 1):
            d = math.hypot(x - cx, y - cy) / r
            if d >= 1:
                continue
            here = p.get(x, y)
            if only_clear:
                if not here[3] and (1 - d) * t * 16 > BAYER[y % 4][x % 4] + 0.5:
                    p.dot(x, y, colour)
                continue
            dark = {rgba(c)[:3]: i for i, c in enumerate((N[0], N[1], N[2], R[0], R[1], R[2]))}
            if here[3] and here[:3] in dark:
                lift = (1 - d) * 3.2 + BAYER[y % 4][x % 4] / 16 - 0.5
                step = min(3, max(0, int(lift)))
                if step:
                    p.dot(x, y, R[step - 1] if dark[here[:3]] < 2 else R[min(3, step)])


RIDGE = 9  # the main roof's ridge row in the status strip
CHIMNEYS = ((96, 3, 5), (150, 1, 6), (238, 2, 6), (290, 4, 5))  # x, top row, width
CAT_X = 198


def roofline():
    """status.backdrop: one long roofline of the manor against the stars (400 × 16 → 1200 × 48):
    a low wing, a turret's cone, the main ridge with iron cresting, chimneys with pots, lit
    dormers, the far gable and a weathervane; the cat sits on the ridge (its tail is a layer)."""
    p = Pic(400, 16)
    p.vgrad(0, 0, 399, 15, [N[1], N[2], N[4], N[5]], curve=1.3)
    stars(p, (0, 0, 400, 7), 60, 51, (N[5], N[6], N[7]))
    k, rim = N[0], N[6]
    p.poly([(0, 16), (0, 11), (20.5, 5), (41, 11), (41, 16)], k)  # the low wing
    p.line(0, 11, 20, 5, rim)
    p.rect(50, 6, 64, 15, k)  # the turret and its cone
    p.poly([(47, 7), (57.5, -1), (68, 7)], k)
    p.line(47, 6, 57, -1, rim)
    p.vline(50, 7, 15, N[3])
    p.rect(55, 9, 56, 11, E[4])
    p.rect(66, RIDGE, 336, 15, k)  # the main roof
    p.hline(66, 336, RIDGE, N[4])
    for x in range(67, 336, 2):  # iron cresting
        p.dot(x, RIDGE - 1, k)
        if x % 6 == 1:
            p.dot(x, RIDGE - 2, k)
    for y in range(RIDGE + 2, 16, 2):  # slate courses, faint
        for x in range(66 + (y // 2) % 2 * 2, 336, 4):
            p.dot(x, y, N[1])
    for x, top, w in CHIMNEYS:  # chimneys and their pots
        p.rect(x, top + 2, x + w - 1, RIDGE, k)
        p.vline(x, top + 2, RIDGE, N[5])
        p.rect(x + 1, top, x + 2, top + 1, k)
        p.rect(x + w - 3, top + 1, x + w - 2, top + 1, k)
        p.hline(x - 1, x + w, top + 2, N[2])
    for x, lit in ((120, True), (176, False), (262, True)):  # dormers
        p.poly([(x - 1, RIDGE + 4), (x + 3.5, RIDGE - 1), (x + 8, RIDGE + 4)], k)
        p.line(x - 1, RIDGE + 3, x + 3, RIDGE - 1, rim)
        p.rect(x + 2, RIDGE + 2, x + 4, RIDGE + 4, E[4] if lit else N[2])
    p.poly([(330, 16), (330, 10), (351.5, 3), (373, 10), (373, 16)], k)  # the far gable
    p.line(330, 10, 351, 3, rim)
    p.disc(351.5, 9, 1.6, N[2])  # its round window
    p.rect(373, 11, 399, 15, k)
    p.vline(386, 3, 11, N[3])  # the weathervane: a rooster over its arrow
    p.hline(383, 390, 5, N[3])
    for x, y in ((385, 2), (386, 1), (387, 2), (388, 1), (386, 2)):
        p.dot(x, y, N[3])
    return p  # (the cat on the ridge is the status layer: it moves)


CAT_POSES = {  # 8 × 6 from (CAT_X - 2, RIDGE - 6): k fur, g eyes, m the moon on its back
    "sit": ["........", "........", "..k.k...", "..gkg...", ".mkkk...", ".kkkkk.."],
    "wide": ["........", "..k.k...", "..kkk...", "..GkG...", ".mkkk...", ".kkkkk.."],
    "stand": ["......k.", "......k.", "k.k...k.", "gkg...k.", "mkkkkkk.", ".k.k.k.k"],
    "arch": ["...mm..k", "..kkkk.k", "kkk..kkk", "gk....k.", "k.....k.", "k.....k."],
    "stretch": ["........", "......kk", ".....kk.", "k.k.kkk.", "gkgmkk..", "kkkkk.k."],
}


def ridge_cat(p, pose="sit", tail=0):
    """The cat on the roof's ridge, in a pose; sitting, its tail curls or flicks (tail 0–4)."""
    for dy, row in enumerate(CAT_POSES[pose]):
        for dx, ch in enumerate(row):
            if ch != ".":
                p.dot(CAT_X - 2 + dx, RIDGE - 6 + dy, {"k": N[0], "g": G[4], "G": G[5], "m": N[5]}[ch])
    if pose in ("sit", "wide"):
        tails = (((3, 2), (4, 1), (5, 0), (5, -1)), ((3, 2), (4, 2), (5, 1), (6, 1)), ((3, 2), (4, 2), (5, 2), (6, 2)),
                 ((3, 2), (4, 1), (5, 1), (6, 0)), ((3, 2), (4, 1), (5, 0), (6, -1)))
        for dx, dy in tails[tail]:
            p.dot(CAT_X + dx, RIDGE - 3 + dy, N[0])


def chimney_smoke(p, frame, big=0):
    for n, (x, top, w) in enumerate(CHIMNEYS[1:3]):
        for puff in range(3):
            t = ((frame + puff * 5 + n * 3) % 16) / 16
            px, py = x + w // 2 + round(t * 9), top - round(t * 9)
            if 0 <= py < 16:
                c = N[5] if t < 0.4 else N[4] if t < 0.75 else N[3]
                p.dot(px, py, c)
                if t > 0.3 or big:
                    p.dot(px + 1, py, c)


def status_life(frame):
    """The status strip's layer (400 × 16, 16 frames): the cat flicks its tail now and then, and
    smoke rises from two chimneys, drifting with the wind."""
    p = Pic(400, 16)
    ridge_cat(p, "sit", max(0, frame - 11))
    chimney_smoke(p, frame)
    return p


def status_poke(frame):
    """Poke the roofline: the cat's eyes go wide, it gets up, arches its back, stretches long and
    sits down again (8 frames, the strip's own size)."""
    p = Pic(400, 16)
    ridge_cat(p, ("wide", "stand", "arch", "arch", "stretch", "stretch", "stand", "sit")[frame])
    chimney_smoke(p, frame * 2, big=1)
    return p


def crest():
    """auth.crest: the manor's keyhole escutcheon in cast brass, the moonlit night seen through
    the keyhole (32 × 32 → 96). Drawn as a half and mirrored: a true casting is symmetric."""
    half = [max(1, round(9.6 * math.sin(math.pi * (y + 0.5) / 31) ** 0.75)) + (1 if y in (6, 7, 23, 24) else 0)
            for y in range(31)]  # widths of the plate's right half: a pointed oval with four scrolled ears
    p = Pic(32, 32)
    for y, w in enumerate(half):
        for x in range(16 - w, 16 + w):
            p.dot(x, y, B[2])
    for y in range(32):  # cast light: bright upper left, deep lower right, a lit ridge down the middle
        for x in range(32):
            if p.get(x, y)[:3] == rgba(B[2])[:3]:
                t = (x - 16) / 10 + (y - 15) / 32
                if t < -0.35:
                    p.dot(x, y, B[3])
                if t < -0.7 and BAYER[y % 4][x % 4] < 9:
                    p.dot(x, y, B[4])
                if t > 0.45:
                    p.dot(x, y, B[1])
    p.outline(N[0])
    # an engraved border inside the edge
    for y, w in enumerate(half):
        if 2 < y < 29 and w > 3:
            p.dot(16 - w + 2, y, B[1])
            p.dot(16 + w - 3, y, B[0])
    # rivets at the ears and the tips
    for x, y in ((9, 8), (22, 8), (8, 16), (23, 16), (15, 27), (16, 27)):
        p.dot(x, y, B[4] if x < 16 else B[3])
        p.dot(x, y + 1, B[0])
    # the keyhole: round head, flared slot, the night inside with the moon and the manor
    for y in range(6, 24):
        for x in range(10, 22):
            head = math.hypot(x + 0.5 - 16, y + 0.5 - 11.5) < 4.2
            slot = 13 <= y <= 22 and abs(x + 0.5 - 16) <= 1.1 + (y - 13) * 0.17
            if head or slot:
                t = (y - 7) / 16
                p.dot(x, y, N[2] if t < 0.35 else N[3] if t < 0.7 else N[4])
    p.disc(16, 11.5, 2.7, M[1])  # the full moon filling the keyhole's round
    p.dot(17, 12, M[2])
    p.dot(15, 13, M[2])
    p.dot(17, 10, M[2])
    p.dot(15, 10, M[0])
    p.dot(16, 18, N[7])
    for x, y in ((12, 10), (12, 11), (12, 12), (13, 9), (14, 8)):  # the hole's inner shadow
        p.dot(x, y, N[0])
    return p


def ghost_empty():
    """state.empty: a friendly ghost with a candle, nothing here yet (32 × 32 → 96)."""
    p = Pic(32, 32)
    body = Pic(32, 32)
    body.disc(15.5, 11, 8.2, H[2])
    body.rect(8, 11, 23, 23, H[2])
    for x in range(8, 24):  # the wavy hem
        wave = round(1.5 + 1.5 * math.sin((x - 8) / 16 * math.pi * 3))
        body.vline(x, 23, 23 + wave, H[2])
    # shading: moonlit from the upper left
    for y in range(32):
        for x in range(32):
            if body.get(x, y)[3]:
                t = (x - 15) / 9 + (y - 12) / 14
                if t > 0.55:
                    body.dot(x, y, H[1])
                if t > 1.05 and BAYER[y % 4][x % 4] < 9:
                    body.dot(x, y, H[0])
                if t < -0.8:
                    body.dot(x, y, H[3])
    body.outline(L[0])
    p.paste(body, 0, 0)
    # the face: two soft eyes, a small smile, a blush
    for x, y in ((12, 11), (12, 12), (18, 11), (18, 12)):
        p.dot(x, y, N[1])
    p.dot(12, 11, N[3])
    p.dot(18, 11, N[3])
    p.hline(14, 16, 15, N[2])
    p.dot(13, 14, N[2])
    p.dot(17, 14, N[2])
    p.dot(10, 14, V[4])
    p.dot(20, 14, V[4])
    # two little arms, one waving
    for x, y in ((7, 17), (6, 16), (6, 15)):
        p.dot(x, y, H[3])
    p.dot(5, 15, L[0]); p.dot(5, 16, L[0]); p.dot(6, 14, L[0]); p.dot(7, 18, L[0]); p.dot(6, 17, L[0])
    for x, y in ((24, 18), (25, 19)):
        p.dot(x, y, H[1])
    p.dot(26, 19, L[0]); p.dot(25, 20, L[0]); p.dot(26, 18, L[0]); p.dot(25, 18, L[0])
    # its shadow on the floor
    for x in range(10, 23):
        if BAYER[30 % 4][x % 4] < 8:
            p.dot(x, 30, L[0])
    return p


TABLE_FLAME = (  # the candle's flame per frame: (height, belly half-width, heat 0–2); it never moves sideways
    (9, 1, 1), (10, 2, 2), (11, 2, 2), (10, 2, 1), (8, 1, 0), (9, 2, 1), (11, 2, 2), (10, 1, 1))


def table_flame(p, x, y, frame=0, mode=None):
    """The candle's flame on its wick at (x, y), a teardrop changing shape in place: taller or
    shorter, fuller or slimmer, hotter or cooler. mode: "flare", "low", "out", "smoke"."""
    if mode in ("out", "smoke"):
        p.dot(x, y, E[2] if mode == "out" else N[0])
        for k, dx in ((1, 0), (2, 1), (3, 1), (4, 0), (5, -1), (6, -1), (7, 0)):
            if mode == "out" and k > 4 or mode == "smoke" and k < 3:
                continue
            p.dot(x + dx, y - k, N[9] if k < 4 else N[8] if k < 6 else N[7])
        return
    if mode == "low":
        p.dot(x, y - 1, E[4])
        p.dot(x, y - 2, E[5])
        p.dot(x, y - 3, E[3])
        return
    h, half, heat = (14, 2, 2) if mode == "flare" else TABLE_FLAME[frame % len(TABLE_FLAME)]
    hot = (E[5], E[6], E[7])[heat]
    for k in range(h):  # the body, from the wick up
        t = k / (h - 1)
        width = 0 if t > 0.7 else half if 0.15 < t < 0.55 else min(1, half)
        for dx in range(-width, width + 1):
            edge = abs(dx) == width and width > 0
            c = E[3] if edge and t < 0.2 else E[4] if edge else hot if t < 0.45 else E[5] if t < 0.75 else E[4]
            p.dot(x + dx, y - 1 - k, c)
    p.dot(x, y - 1, N[3])  # the blue root at the wick
    p.dot(x, y - 1 - h, E[3])  # the tip
    if mode == "flare":
        for dx, dy in ((-3, 6), (3, 8), (-2, 11)):
            p.dot(x + dx, y - dy, E[4])


def candle_table(frame=0, mode=None):
    """The rail's foot: a little carved side table on the floorboards, a brass candlestick with
    one tall candle, two old books and a teacup (62 × 72 with the flame's headroom; moonlight from
    the upper left)."""
    p = Pic(62, 64)
    # the floorboards and the rug's fringe it stands on
    p.rect(2, 58, 59, 63, W[1])
    p.hline(2, 59, 58, W[3])
    for x in range(6, 58, 11):
        p.vline(x, 59, 63, W[0])
    p.rect(8, 57, 53, 58, V[1])
    p.hline(8, 53, 57, V[2])
    for x in range(8, 54, 2):
        p.dot(x, 59, M[3])
    # the table: a thick top with a lit edge, an apron with a drawer, turned legs
    p.rect(6, 36, 55, 38, W[3])
    p.hline(6, 55, 36, W[5])
    p.hline(6, 55, 38, W[1])
    p.rect(9, 39, 52, 44, W[2])
    p.hline(9, 52, 44, W[1])
    p.rect(24, 40, 37, 43, W[1])
    p.dot(30, 41, B[3])
    for lx in (11, 49):
        for y in range(45, 57):
            w = 1 if (y - 45) % 5 in (0, 4) else 2
            p.hline(lx - w + 1, lx + w - 1 + 1, y, W[2])
            p.dot(lx - w + 1, y, W[4])
        p.hline(lx - 1, lx + 2, 56, W[1])
    # two old books, a ribbon hanging out
    p.rect(12, 32, 26, 35, V[2])
    p.hline(12, 26, 32, V[3])
    p.vline(12, 32, 35, V[1])
    p.rect(14, 29, 25, 31, G[1])
    p.hline(14, 25, 29, G[2])
    p.hline(15, 24, 30, P_BOOK)
    p.vline(22, 36, 38, V[4])
    # a teacup and saucer
    p.hline(40, 48, 35, M[2])
    p.rect(41, 31, 46, 34, M[1])
    p.vline(41, 31, 34, M[0])
    p.dot(47, 32, M[2])
    p.dot(47, 33, M[2])
    p.hline(42, 45, 31, W[2])
    # the brass candlestick: a round foot, a turned stem, a drip pan
    p.rect(27, 33, 35, 35, B[2])
    p.hline(27, 35, 33, B[4])
    p.vline(27, 33, 35, B[3])
    p.rect(30, 22, 32, 32, B[2])
    p.vline(30, 22, 32, B[4])
    p.rect(29, 26, 33, 26, B[3])
    p.rect(27, 20, 35, 21, B[3])
    p.hline(27, 35, 20, B[4])
    # the candle, a drip running down its side
    p.rect(30, 8, 32, 19, M[1])
    p.vline(32, 8, 19, M[2])
    p.vline(30, 8, 19, M[0])
    p.vline(33, 12, 15, M[1])
    p.dot(33, 16, M[2])
    p.dot(31, 7, N[0])  # the wick
    out = Pic(62, 72)  # 8 rows of headroom for the flame (and its flare)
    out.paste(p, 0, 8)
    table_flame(out, 31, 15, frame, mode)
    return out


def candle_table_layer(frame, mode=None):
    """The rail-foot piece (62 × 72 per frame, 186 × 216 at ×3)."""
    return candle_table(frame, mode)


def candle_table_poke(frame):
    """Poke the candle: it flares, gutters to a bead, goes out in a curl of smoke, relights
    (6 frames, 0.6 s)."""
    return candle_table(frame, ("flare", "low", "out", "smoke", "low", None)[frame])


def column():
    """rail.surface: a carved stone column, 9-slice (78 × 200 → 234 × 600, slice 24 = 8 native)."""
    p = Pic(78, 200, N[1])
    for x in range(8, 70, 5):  # fluting, faint
        p.vline(x, 8, 191, N[2])
        p.vline(x + 1, 8, 191, "#0a0b1c")
    for x0, x1, c in ((0, 0, N[0]), (1, 1, N[4]), (2, 2, N[2]), (3, 4, N[1]), (5, 5, N[3]), (6, 7, N[1])):
        for x in range(x0, x1 + 1):
            p.vline(x, 0, 199, c)
            p.vline(77 - x, 0, 199, {N[4]: N[2], N[3]: N[2]}.get(c, c))
    for y0, c in ((0, N[0]), (1, N[4]), (2, N[3]), (3, N[2]), (4, N[1]), (5, N[3]), (6, N[1]), (7, N[0])):
        p.hline(0, 77, y0, c)
        p.hline(0, 77, 199 - y0, {N[4]: N[2], N[3]: N[2]}.get(c, c))
    # a carved rosette in each corner
    for cx, cy in ((3.5, 3.5), (73.5, 3.5), (3.5, 195.5), (73.5, 195.5)):
        p.disc(cx, cy, 3.3, N[2])
        p.disc(cx, cy, 2, N[4])
        p.dot(int(cx), int(cy), N[6])
        p.dot(int(cx) + 1, int(cy) + 1, N[1])
    return p


def tv():
    """watch.tv.bezel: the house's television, a carved wooden cabinet (54 × 40 → 162 × 120)."""
    p = Pic(54, 40)
    # the cabinet
    p.rect(3, 6, 50, 35, W[2])
    p.poly([(3, 7), (8, 2), (45, 2), (50, 7)], W[3])  # the carved crown
    p.hline(8, 45, 2, W[5])
    p.line(3, 6, 8, 2, W[5])
    p.vline(3, 7, 35, W[4])
    p.vline(50, 7, 35, W[1])
    p.hline(3, 50, 35, W[1])
    p.disc(26.5, 3.5, 2.2, W[4])  # a rosette on the crown
    p.dot(26, 3, W[5])
    for x in range(10, 44, 4):
        p.dot(x, 4, W[1])
    # the screen: a rounded tube, the glow of a film, a pale ghost waving from it
    p.rect(7, 9, 36, 31, N[0])
    p.rect(8, 10, 35, 30, N[5])
    p.vgrad(9, 11, 34, 29, [N[7], N[6], N[5]])
    for (x, y) in ((8, 10), (35, 10), (8, 30), (35, 30)):
        p.dot(x, y, N[0])
    for y in range(11, 30, 2):
        for x in range(9, 35):
            if BAYER[y % 4][x % 4] < 6:
                p.dot(x, y, N[5])
    p.dot(10, 12, H[3])
    p.dot(11, 12, H[2])
    p.dot(10, 13, H[2])
    g = ((".hh.", "hHHh", "hkHk", "hHHh", "hHHh", "h.h."))
    for dy, row in enumerate(g):
        for dx, ch in enumerate(row):
            if ch != ".":
                p.dot(20 + dx, 17 + dy, {"h": H[1], "H": H[3], "k": N[3]}[ch])
    p.dot(24, 18, H[2])  # a waving hand
    # the knobs and the speaker grille
    for y in (12, 19):
        p.disc(43.5, y + 0.5, 2.3, B[1])
        p.disc(43.2, y + 0.2, 1.4, B[3])
        p.dot(43, y, B[4])
    for y in range(24, 32, 2):
        p.hline(40, 47, y, W[0])
        p.hline(40, 47, y + 1, W[3])
    # legs
    for x in (6, 45):
        p.rect(x, 36, x + 2, 39, W[1])
        p.dot(x, 36, W[4])
    return p


DECK_S = 5  # the deck frame's cell, native (15 px on screen: inside the deck's 16 px padding)


def deck_frame():
    """deck.surface: the music player as a walnut wireless cabinet, a 9-slice frame (15 × 15 → 45
    × 45, slice 15): a lit moulding, a brass inlay, brass scrolls in three corners and a candle in
    its pan in the fourth (its flame is the deck's layer)."""
    s = DECK_S
    n = 3 * s
    p = Pic(n, n, W[1])
    lit = {0: W[0], 1: W[3], 2: W[2], 3: B[2], 4: W[0]}
    shade = {0: W[0], 1: W[1], 2: W[2], 3: B[1], 4: W[0]}
    for i in range(n):
        for k in range(5):
            p.dot(i, k, lit[k])
            p.dot(k, i, lit[k])
            p.dot(i, n - 1 - k, shade[k])
            p.dot(n - 1 - k, i, shade[k])
    p.dot(3, 3, B[4])
    scroll = ((1, 1, B[4]), (2, 1, B[3]), (3, 1, B[3]), (1, 2, B[3]), (1, 3, B[3]), (3, 2, B[2]), (2, 3, B[2]), (2, 2, B[0]))
    for fx, fy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        for x, y, c in scroll:
            p.dot(x if not fx else n - 1 - x, y if not fy else n - 1 - y, c)
    return p


def deck_candle(flame=0):
    """The deck's candle stub in its brass pan, standing on the cabinet's bottom rail by the
    corner (5 × 5). flame: 0–3 flickers, "flare", "low", "out", "smoke"."""
    p = Pic(DECK_S, DECK_S)
    p.hline(0, 4, 4, B[3])
    p.dot(0, 4, B[4])
    p.dot(4, 4, B[1])
    p.vline(2, 2, 3, M[1])
    p.dot(3, 3, M[2])
    if flame == "flare":
        p.vline(2, 0, 1, E[6])
        p.dot(1, 0, E[5])
        p.dot(3, 0, E[5])
    elif flame == "low":
        p.dot(2, 1, E[3])
    elif flame in ("out", "smoke"):
        p.dot(2, 1, E[2] if flame == "out" else N[0])
        p.dot(2 if flame == "out" else 3, 0, N[5])
    else:
        p.dot(2, 1, E[4])
        p.dot(2 + (0, 0, 1, -1)[flame % 4], 0, (E[6], E[5], E[7], E[5])[flame % 4])
    return p


def deck_flame(frame):
    """The deck's candle, flickering while music plays (4 frames)."""
    return deck_candle(frame)


def deck_flame_poke(frame):
    """Poke the deck's candle: it flares, gutters, goes out in a curl of smoke, relights (6 frames)."""
    return deck_candle(("flare", "low", "out", "smoke", "low", 0)[frame])


# ---------------------------------------------------------------- the rooms (header banners)
# A banner is 400 × 53 native (1200 × 159 on screen) behind a room's title. It fades out from 45 %
# of its height, so every subject sits in the top 36 rows; the title and its tip cover the left,
# phones show the middle third, and the header's buttons sit over the right quarter, which stays
# a quiet wall (dimmed two steps). Fixtures that move are header layers drawn at the same pixels:
# sconces at x 150 and 240, the ancestor's portrait at x 188, the bedroom's curtain at x 208
# (where the banner, scaled 1.006 and centred, and a layer, centred at ×3, agree within a pixel).
BW, BH = 400, 53
LAYER_DY = 11  # a header layer starts at the title's top: 32 px (≈ 11 rows) under the banner's top
SCONCES = (150, 240)
PORTRAIT_X = 188
CURTAIN_X = 264  # the bedroom's right curtain, a header layer
P_BOOK = "#e8dcc2"
FLOOR = 36  # where furniture stands


def ramp_step(colour, k):
    """The colour k steps lighter (k > 0) or darker along its own ramp in PAL."""
    rgb = rgba(colour)[:3]
    for name, ramp in PAL.items():
        ramp = ramp if isinstance(ramp, list) else [ramp]
        ramp = ramp[::-1] if name == "moon" else ramp  # the moon's ramp runs light to dark
        for i, c in enumerate(ramp):
            if rgba(c)[:3] == rgb:
                return ramp[max(0, min(len(ramp) - 1, i + k))]
    return colour


def dim(p, box, steps=2):
    """Darken a box by `steps` along each colour's ramp (the quiet end behind the buttons)."""
    x0, y0, x1, y1 = box
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            c = p.get(x, y)
            if c[3] and c[:3] not in (rgba(N[0])[:3],):
                p.dot(x, y, ramp_step(c, -steps))
    return p


WARM = {N[0]: R[0], N[1]: R[0], N[2]: R[1], N[3]: R[2], N[4]: R[3], R[0]: R[1], R[1]: R[2], R[2]: R[3]}


def warm(p, cx, cy, r, strength=1.0):
    """Candlelight on the room: nearer the flame, the wall steps into the warm ramp, dithered."""
    table = {rgba(a)[:3]: b for a, b in WARM.items()}
    for y in range(int(cy - r), int(cy + r) + 1):
        for x in range(int(cx - r), int(cx + r) + 1):
            d = math.hypot(x - cx, (y - cy) * 1.2) / r
            if d >= 1:
                continue
            level = (1 - d) * 2.2 * strength + BAYER[y % 4][x % 4] / 16 - 0.5
            c = p.get(x, y)
            for _ in range(max(0, int(level))):
                if c[3] and c[:3] in table:
                    c = rgba(table[c[:3]])
                elif c[3] and c[:3] in {rgba(v)[:3] for v in W + V + B}:
                    c = rgba(ramp_step(c, 1))
            p.dot(x, y, c)


def moonbeam(p, x0, x1, y0, slope=0.9, y1=BH - 1):
    """A shaft of moonlight from a window (x0–x1 at y0) falling down and to the right."""
    for y in range(y0, y1 + 1):
        dx = (y - y0) * slope
        for x in range(round(x0 + dx), round(x1 + dx * 1.3) + 1):
            if BAYER[y % 4][x % 4] < 9 and p.get(x, y)[3]:
                p.dot(x, y, ramp_step(p.get(x, y), 1))


def room_shell(paper=None, motif=None, panels=True):
    """Wall, dado, wainscot, skirting and a plank floor; furniture stands at FLOOR."""
    paper, motif = paper or N[2], motif or N[3]
    p = Pic(BW, BH, paper)
    for y in range(6, 24, 9):  # a sparse damask in a half-drop
        for x in range((y // 9) % 2 * 7 + 3, BW, 14):
            for dx, dy in ((0, 0), (-1, 1), (1, 1), (0, 2), (0, -1)):
                p.dot(x + dx, y + dy, motif)
    p.hline(0, BW - 1, 0, N[0])  # crown moulding
    p.rect(0, 1, BW - 1, 2, N[3])
    p.hline(0, BW - 1, 1, N[4])
    p.hline(0, BW - 1, 3, N[1])
    p.hline(0, BW - 1, 26, N[4])  # the dado rail, its top in the light
    p.hline(0, BW - 1, 27, N[1])
    if panels:
        for x in range(2, BW, 20):  # wainscot panels
            p.rect(x, 29, x + 16, 33, N[3])
            p.rect(x + 1, 30, x + 15, 32, N[2])
            p.hline(x, x + 16, 33, N[1])
    p.rect(0, 34, BW - 1, 35, W[0])  # skirting
    p.hline(0, BW - 1, 34, W[2])
    p.rect(0, FLOOR, BW - 1, BH - 1, W[1])  # the floor: planks
    for y in range(FLOOR, BH, 3):
        p.hline(0, BW - 1, y, W[0])
        for x in range((y * 13) % 29, BW, 29):
            p.vline(x, y + 1, y + 2, W[0])
            p.dot(x + 3, y + 1, W[2])
    return p


def window(p, x0, x1, y0=6, y1=22, moon_at=None):
    """A tall arched window: night blue panes, the moon in one, mullions; its moonbeam."""
    p.rect(x0 - 1, y0, x1 + 1, y1 + 1, W[1])
    p.vgrad(x0, y0 + 1, x1, y1, [N[5], N[6], N[5], N[4]])
    cx = (x0 + x1) / 2
    for x in range(x0 - 1, x1 + 2):  # the arch
        top = y0 + 1 - round(2.5 * math.sin(math.pi * (x - x0 + 1) / (x1 - x0 + 2)))
        p.vline(x, top, y0, W[1] if x in (x0 - 1, x1 + 1) else N[5])
        p.dot(x, top - 1, W[1])
    if moon_at:
        p.disc(moon_at[0], moon_at[1], 2.2, M[1])
    p.vline(round(cx), y0 - 1, y1, W[1])
    p.hline(x0, x1, (y0 + y1) // 2, W[1])
    p.hline(x0 - 2, x1 + 2, y1 + 1, W[3])  # the sill
    moonbeam(p, x0, x1, y1 + 2)


def frame(p, x, y, w, h, inside=None):
    """A gilt picture frame, lit on its top-left edge."""
    p.rect(x, y, x + w - 1, y + h - 1, B[1])
    p.hline(x, x + w - 1, y, B[3])
    p.vline(x, y, y + h - 1, B[3])
    p.dot(x, y, B[4])
    p.rect(x + 1, y + 1, x + w - 2, y + h - 2, inside or N[2])


def portrait(p, x, y, eyes=True):
    """The ancestor in oils: dark hair, a face lit from the left, a lace collar (14 × 18)."""
    frame(p, x, y, 14, 18, W[1])
    p.vgrad(x + 2, y + 2, x + 11, y + 15, [W[2], W[1], W[0]])
    p.disc(x + 7, y + 7.5, 2.8, W[0])  # the hair
    p.rect(x + 5, y + 7, x + 9, y + 9, M[2])  # the face
    p.vline(x + 9, y + 7, y + 9, W[4])
    look = {True: "open", False: "closed"}.get(eyes, eyes)
    if look in ("closed", "wink"):
        p.hline(x + 5, x + 6 if look == "wink" else x + 9, y + 8, M[3])
        if look == "wink":
            p.dot(x + 8, y + 8, W[0])
        else:
            p.dot(x + 7, y + 8, M[2])
    else:  # the pupils: straight at you, or rolled up, right or left
        dx, dy = {"open": (0, 0), "up": (0, -1), "right": (1, 0), "left": (-1, 0)}[look]
        p.dot(x + 6 + dx, y + 8 + dy, W[0])
        p.dot(x + 8 + dx, y + 8 + dy, W[0])
    p.rect(x + 3, y + 11, x + 11, y + 15, N[1])  # the dark coat
    p.hline(x + 5, x + 9, y + 10, M[1])  # the collar
    p.dot(x + 7, y + 12, B[3])  # a brooch


def wall_sconce(p, x, y, frame=0):
    """A brass wall sconce, its candle and flame (the flame in four flickers)."""
    p.vline(x + 1, y + 6, y + 10, B[1])  # the back plate
    p.dot(x + 1, y + 6, B[3])
    p.line(x + 1, y + 8, x - 1, y + 6, B[2])  # the arm
    p.rect(x - 2, y + 5, x + 1, y + 5, B[3])  # the drip pan
    p.hline(x - 2, x + 1, y + 6, B[1])
    candle(p, x - 1, y + 4, 4, frame)


def cobweb(p, x, y, flip=False):
    s = -1 if flip else 1
    for i in range(7):
        p.dot(x + s * i, y, N[4])
        p.dot(x, y + i, N[4])
        p.dot(x + s * (6 - i), y + i, N[4] if i % 2 == 0 else N[3])
    for i in range(4):
        p.dot(x + s * i, y + i, N[4])
        p.dot(x + s * (3 - i) + s, y + i + 1, N[3])


def rug(p, x0, x1, colour=None):
    colour = colour or V[1]
    p.rect(x0, FLOOR + 2, x1, FLOOR + 6, colour)
    p.hline(x0, x1, FLOOR + 2, ramp_step(colour, 1))
    for x in range(x0 + 2, x1 - 1, 4):
        p.dot(x, FLOOR + 4, B[1])
    for x in range(x0, x1 + 1, 2):  # fringe
        p.dot(x, FLOOR + 7, M[3])


def lit_room(p, sconces=SCONCES):
    """The candles' warmth on the walls (the sconces themselves are a header layer)."""
    for x in sconces:
        warm(p, x, 13, 18, 0.6)
    return p


def quiet(p):
    """The right quarter, where the header's buttons sit: two steps darker, eased in by dither."""
    src = Pic(BW, BH)
    src.paste(p, 0, 0)
    for y in range(BH):
        for x in range(284, BW):
            t = min(1, (x - 284) / 28)
            k = 2 if t * 16 > BAYER[y % 4][x % 4] + 0.5 else (1 if t * 32 > BAYER[y % 4][x % 4] + 0.5 else 0)
            c = src.get(x, y)
            if k and c[3] and c[:3] != rgba(N[0])[:3]:
                p.dot(x, y, ramp_step(c, -k))
    return p


def banner_hall():
    """Hall (My Space, Ask and any other room): the stair, the clock, the rug, the coat stand."""
    p = room_shell()
    window(p, 118, 132, moon_at=(128, 10))
    rug(p, 36, 170)
    # an umbrella stand by the door, low and in shadow
    p.rect(16, 28, 24, FLOOR, W[1])
    p.hline(16, 24, 28, W[3])
    p.line(18, 28, 16, 22, N[4])
    p.line(22, 28, 23, 21, N[4])
    p.dot(16, 21, N[5])
    # the grandfather clock
    p.rect(206, 8, 216, FLOOR, W[1])
    p.poly([(205, 9), (211.5, 3), (218, 9)], W[2])
    p.vline(206, 8, FLOOR, W[3])
    p.disc(211.5, 13.5, 3.2, B[2])
    p.disc(211.5, 13.5, 2.3, M[1])
    p.line(211, 13, 211, 11, N[0])
    p.line(211, 13, 213, 14, N[0])
    p.rect(209, 19, 214, 32, N[0])
    p.vline(211, 19, 29, B[1])
    p.disc(211.5, 30, 1.6, B[3])
    # the stair, climbing to the right, balusters and a moonlit rail
    for i in range(10):
        x0, y0 = 222 + i * 8, FLOOR - i * 3
        p.rect(x0, y0, 300, FLOOR, N[3])
        p.hline(x0, 300, y0, N[5])
        for k in (1, 5):
            p.vline(x0 + k, y0 - 8, y0 - 1, W[2])
    p.line(222, FLOOR - 9, 300, FLOOR - 9 - 29, W[4])
    p.line(222, FLOOR - 8, 300, FLOOR - 8 - 29, W[2])
    p.rect(220, FLOOR - 12, 223, FLOOR, W[2])  # the newel post and its brass finial
    p.vline(220, FLOOR - 12, FLOOR, W[4])
    p.rect(220, FLOOR - 14, 223, FLOOR - 13, B[3])
    # the far end: a dark doorway, a second portrait in shadow
    p.rect(330, 6, 360, FLOOR, N[1])
    p.poly([(330, 7), (345.5, 1), (361, 7)], N[1])
    p.vline(329, 5, FLOOR, W[2])
    p.vline(361, 5, FLOOR, W[2])
    frame(p, 372, 8, 12, 14, W[1])
    cobweb(p, BW - 1, 4, True)
    return quiet(lit_room(p))


def banner_parlour():
    """Listen: the parlour: the record cabinet, the gramophone, the velvet armchair."""
    p = room_shell(motif=V[0])
    window(p, 118, 132, moon_at=(123, 9))
    rug(p, 150, 296)
    # a velvet footstool, left
    p.rect(26, 30, 46, 33, V[1])
    p.hline(26, 46, 30, V[2])
    p.vline(28, 34, FLOOR, W[2])
    p.vline(44, 34, FLOOR, W[2])
    # the record cabinet: records on top, carved doors
    p.rect(158, 24, 186, FLOOR, W[2])
    p.hline(158, 186, 24, W[4])
    p.vline(158, 24, FLOOR, W[3])
    for x in (160, 173):
        p.rect(x, 27, x + 11, 34, W[1])
        p.hline(x, x + 11, 27, W[3])
        p.dot(x + 10, 30, B[3])
    for i, x in enumerate(range(160, 185, 2)):  # records standing in a rack on top
        p.vline(x, 18 + (i * 5) % 3, 23, (N[0], V[1], N[0], W[1], E[1])[i % 5])
    # the gramophone on its table
    p.rect(204, 28, 236, 29, W[3])
    p.vline(206, 30, FLOOR, W[2])
    p.vline(234, 30, FLOOR, W[2])
    p.rect(208, 23, 230, 27, W[2])
    p.hline(208, 230, 23, W[4])
    p.hline(210, 228, 22, N[0])  # the record
    p.dot(219, 22, E[3])
    horn = Pic(BW, BH)
    for i in range(40):  # the horn: a tube swelling into a bell whose mouth faces you
        t = i / 39
        horn.disc(226 - t * 10, 20 - t * 10, 0.8 + t ** 2.4 * 6, B[2])
    for y in range(BH):
        for x in range(BW):
            if horn.get(x, y)[3] and not horn.get(x - 1, y - 1)[3]:
                horn.dot(x, y, B[4])
            elif horn.get(x, y)[3] and not horn.get(x + 1, y + 1)[3]:
                horn.dot(x, y, B[1])
    horn.outline(B[0])
    mx, my = 216.5, 10
    horn.disc(mx, my, 6.4, B[0])
    horn.disc(mx, my, 5.8, B[3])
    horn.disc(mx + 0.4, my + 0.4, 4.6, B[1])
    horn.disc(mx + 1, my + 1, 3, B[0])
    horn.disc(mx + 1.5, my + 1.5, 1.4, W[0])
    p.paste(horn, 0, 0)
    # the armchair
    p.rect(252, 18, 280, FLOOR - 2, V[2])
    p.disc(266, 19, 13, V[2])
    for x, y in ((258, 20), (266, 17), (274, 20), (262, 25), (270, 25)):
        p.dot(x, y, V[1])
    p.rect(248, 26, 255, FLOOR - 1, V[3])
    p.vline(248, 26, FLOOR - 1, V[4])
    p.rect(277, 26, 284, FLOOR - 1, V[1])
    p.rect(252, 30, 280, 33, V[3])
    p.hline(252, 280, 30, V[4])
    p.vline(250, FLOOR - 1, FLOOR, W[1])
    p.vline(282, FLOOR - 1, FLOOR, W[1])
    # the far end: a tall window heavily curtained
    for x in range(318, 362):
        p.vline(x, 4, FLOOR, (V[2], V[1], V[0], V[1])[(x - 318) % 4])
    p.rect(314, 2, 366, 5, V[1])
    return quiet(lit_room(p))


def banner_screening():
    """Watch: the screening room: rows of velvet seats, the projector, the screen and curtains."""
    p = room_shell(paper=N[1], motif=N[2], panels=False)
    # the screen between velvet curtains
    p.rect(250, 7, 296, 28, N[5])
    p.vgrad(251, 8, 295, 27, [N[8], N[7], N[6]])
    p.disc(284, 13, 2.5, M[1])  # the film: a moon over hills, a tiny manor
    for x in range(251, 296):
        top = round(23 - 2.5 * math.sin((x - 251) / 44 * math.pi))
        p.vline(x, top, 27, N[5])
        p.dot(x, top, N[6])
    for x, y in ((266, 21), (267, 20), (268, 21), (266, 22), (268, 22), (267, 22)):
        p.dot(x, y, N[4])
    for x0, x1 in ((244, 252), (294, 302)):
        for x in range(x0, x1 + 1):
            p.vline(x, 3, FLOOR - 2, (V[3], V[2], V[1], V[2])[(x - x0) % 4])
    p.rect(240, 2, 306, 4, V[1])  # the valance and its tassels
    for x in range(242, 306, 5):
        p.dot(x, 5, B[3])
    # the projector on its stand, and its beam
    p.rect(172, 19, 186, 25, N[4])
    p.hline(172, 186, 19, N[6])
    p.disc(176, 16, 3.2, N[5])
    p.disc(183, 16, 3.2, N[5])
    p.dot(176, 16, N[2])
    p.dot(183, 16, N[2])
    p.rect(187, 21, 189, 23, B[2])
    p.vline(178, 26, FLOOR, N[4])
    p.hline(174, 182, FLOOR, N[4])
    for x in range(190, 244):
        t = (x - 190) / 54
        for y in range(round(21 - t * 13), round(23 + t * 5)):
            if BAYER[y % 4][x % 4] < 1 + t * 3:
                p.dot(x, y, N[6] if t < 0.7 else N[7])
    # rows of seats across the room, their backs catching the screen's glow
    for row, (y, c) in enumerate(((27, V[0]), (31, V[0]))):
        for x in range(4 + row * 7, 240, 14):
            p.rect(x, y, x + 10, FLOOR + 1 + row, c)
            p.hline(x, x + 10, y, ramp_step(c, 1))
    p.rect(310, 3, 399, FLOOR, V[0])  # the far curtain
    return quiet(lit_room(p, (150,)))


def banner_kitchen():
    """House: the kitchen: jars, herbs drying on a beam, the table, the hearth and its cauldron."""
    p = room_shell(motif=N[3])
    window(p, 118, 132, moon_at=(129, 9))
    # shelves of jars, left
    p.hline(8, 96, 9, W[3])  # a high shelf of jars, above the room's title
    p.hline(8, 96, 10, W[1])
    for i, x in enumerate(range(10, 94, 5)):
        c = (G[1], B[1], V[1], G[2], L[1], E[1], W[3])[i % 7]
        p.rect(x, 6, x + 2, 8, c)
        p.hline(x, x + 2, 5, W[3])
    p.rect(62, 29, 72, FLOOR, N[4])  # a flour sack, in shadow
    p.hline(62, 72, 29, N[5])
    # a beam with herbs and garlic drying
    p.rect(140, 4, 206, 5, W[2])
    p.hline(140, 206, 4, W[4])
    for i, x in enumerate(range(144, 204, 7)):
        p.vline(x, 6, 7, N[4])
        if i % 3 == 2:
            p.disc(x, 9, 1.4, M[2])
            p.dot(x, 8, M[1])
        else:
            for k in range(3):
                p.dot(x - 1 + (k % 2) * 2, 8 + k, G[2] if k < 2 else G[1])
            p.vline(x, 8, 10, G[3])
    # the table, a loaf, a basket of apples, a candle stub
    p.rect(150, 25, 206, 26, W[3])
    p.hline(150, 206, 25, W[4])
    for x in (153, 203):
        p.rect(x, 27, x + 1, FLOOR, W[2])
    p.rect(160, 22, 170, 24, E[2])  # the loaf
    p.hline(161, 169, 21, E[3])
    p.rect(182, 21, 194, 24, W[4])  # the basket
    for x in range(183, 194, 3):
        p.disc(x, 20, 1.3, V[3])
    p.line(182, 21, 188, 16, W[4])
    p.line(188, 16, 194, 21, W[4])
    # the hearth: a chimney breast of stone, the mantel, the fire and the cauldron
    p.rect(212, 4, 292, FLOOR, N[4])
    for y in range(6, FLOOR, 4):
        for x in range(212 + (y // 4) % 2 * 4, 292, 8):
            p.vline(x, y, y + 3, N[3])
        p.hline(212, 292, y, N[3])
    p.vline(212, 4, FLOOR, N[5])
    p.rect(208, 25, 296, 26, W[3])
    p.hline(208, 296, 25, W[4])
    p.rect(226, 27, 278, FLOOR, N[0])
    warm(p, 252, FLOOR, 22, 1.2)
    p.rect(226, 27, 278, FLOOR, N[0])
    for x in range(229, 276):  # the fire
        h = 3 + 4 * math.sin((x - 229) / 47 * math.pi) + 1.5 * math.sin(x * 1.7)
        for k in range(int(h)):
            p.dot(x, FLOOR - k, (E[6], E[5], E[4], E[3], E[2], E[1])[min(5, k * 6 // max(1, int(h)))])
    p.disc(252, 31, 5.5, N[0])  # the cauldron, lit from below
    p.hline(245, 259, 27, N[3])
    for x in range(247, 258):
        p.dot(x, 35, E[2])
    p.dot(250, 26, G[4])
    p.dot(254, 25, G[3])
    # the far end: a dresser with plates
    p.rect(320, 8, 364, FLOOR, W[1])
    for y in (14, 22):
        p.hline(320, 364, y, W[3])
        for x in range(323, 362, 7):
            p.disc(x + 2, y - 3, 2.4, M[2])
    return quiet(lit_room(p))


def banner_library():
    """Files: the library: a globe, a reading table and its green lamp, shelves, the ladder."""
    p = room_shell(motif=W[1])
    window(p, 118, 132, moon_at=(128, 9))
    # the globe on a low stand
    p.disc(26, 28, 4, G[1])
    p.disc(25, 27, 2.5, G[2])
    p.dot(24, 26, B[1])
    p.line(21, 24, 31, 32, B[1])
    p.vline(26, 32, FLOOR, W[2])
    p.hline(22, 30, FLOOR, W[2])
    # a stack of books on the floor
    for i, c in enumerate((V[2], G[1], B[1], L[1])):
        p.rect(56 + i % 2, FLOOR - 2 - i * 2, 70 - i, FLOOR - 1 - i * 2, c)
    # the reading table and its green-shaded lamp
    p.rect(156, 27, 184, 28, W[3])
    p.vline(158, 29, FLOOR, W[2])
    p.vline(182, 29, FLOOR, W[2])
    p.rect(166, 25, 170, 26, B[2])
    p.vline(168, 20, 24, B[2])
    p.rect(162, 17, 174, 20, G[2])
    p.hline(162, 174, 17, G[4])
    p.rect(174, 24, 180, 26, P_BOOK)
    warm(p, 168, 24, 11, 0.8)
    # shelves, floor to ceiling, a pilaster for the sconce between two cases
    rnd = random.Random(13)
    for x0, x1 in ((204, 236), (244, 300)):
        p.rect(x0, 4, x1, FLOOR, W[1])
        for y in (4, 12, 20, 28):
            p.hline(x0, x1, y + 7, W[3])
            x = x0 + 1
            while x < x1 - 1:
                w = rnd.choice((1, 2, 2))
                h = rnd.randrange(5, 8)
                c = rnd.choice((V[2], V[1], G[1], G[2], B[1], L[1], N[3], W[3], E[1]))
                p.rect(x, y + 7 - h, min(x1 - 1, x + w - 1), y + 6, c)
                if rnd.random() < 0.3:
                    p.dot(x, y + 8 - h, B[3])
                x += w
        p.vline(x0, 4, FLOOR, W[3])
        p.vline(x1, 4, FLOOR, W[0])
    p.rect(237, 4, 243, FLOOR, N[3])  # the pilaster
    p.vline(237, 4, FLOOR, N[5])
    # the rolling ladder on its rail, in the candle's light
    p.hline(244, 300, 5, B[2])
    p.line(268, 5, 262, FLOOR, W[4])
    p.line(275, 5, 269, FLOOR, W[4])
    for y in range(9, FLOOR, 5):
        t = (y - 5) / (FLOOR - 5)
        p.hline(round(268 - t * 6), round(275 - t * 6), y, W[5])
    # the far end: more shelves in shadow
    p.rect(312, 4, 399, FLOOR, W[0])
    for y in (11, 19, 27):
        p.hline(312, 399, y, W[2])
    return quiet(lit_room(p))


def banner_attic():
    """Games: the attic: rafters, a round window, a trunk, a dollhouse of the manor, a rocking horse."""
    p = room_shell(paper=W[1], motif=W[2], panels=False)
    for x in range(0, BW, 20):  # boarded walls
        p.vline(x, 4, 33, W[0])
    # the round window and its moonbeam
    p.disc(125, 13, 7.5, W[3])
    p.disc(125, 13, 6, N[5])
    p.vgrad(119, 7, 131, 19, [N[6], N[5], N[4]])
    for y in range(BH):
        for x in range(BW):
            d = math.hypot(x + 0.5 - 125, y + 0.5 - 13)
            if 6 <= d < 7.5:
                p.dot(x, y, W[3] if y < 13 else W[2])
    p.disc(128, 10, 2, M[1])
    p.hline(119, 131, 13, W[2])
    p.vline(125, 7, 19, W[2])
    moonbeam(p, 119, 131, 21, 1.1)
    # the trunk, brass-bound
    p.rect(26, 30, 60, FLOOR, W[1])
    p.rect(26, 28, 60, 29, W[2])
    p.hline(26, 60, 28, W[3])
    for x in (30, 43, 56):
        p.vline(x, 28, FLOOR, B[1])
    p.rect(41, 31, 45, 32, B[2])
    # the dollhouse (the manor in miniature, its windows lit), the rocking horse, the toys:
    # drawn on a sheet of their own and set down right of the phone's title
    toys = Pic(BW, BH)
    attic_toys(toys)
    p.paste(toys, 36, 0)
    # the roof coming down over the far end, its rafters
    p.poly([(250, 0), (BW, 0), (BW, 30)], N[1])
    for i in range(6):
        x = 262 + i * 24
        p.line(x, 0, x + 26, 22, W[1])
    cobweb(p, 1, 4)
    return quiet(lit_room(p))


def attic_toys(t):
    """The attic's toys, drawn from x 160 (the banner sets them down further right)."""
    t.rect(160, 26, 188, FLOOR, W[3])
    t.rect(162, 16, 186, 26, N[3])
    t.poly([(160, 17), (174, 8), (188, 17)], N[2])
    t.line(160, 16, 174, 8, N[5])
    t.rect(165, 10, 168, 16, N[3])  # its little tower
    t.poly([(164, 11), (166.5, 5), (169, 11)], N[2])
    for x, y, lit in ((165, 19, True), (171, 19, False), (177, 19, True), (182, 19, False), (168, 23, False), (179, 23, True)):
        t.rect(x, y, x + 2, y + 2, E[4] if lit else N[1])
    t.rect(173, 23, 175, 26, W[1])
    # the rocking horse
    t.line(205, FLOOR, 235, FLOOR, W[4])
    t.line(203, FLOOR - 1, 205, FLOOR, W[4])
    t.line(235, FLOOR, 237, FLOOR - 1, W[4])
    t.vline(210, 28, FLOOR - 1, W[3])
    t.vline(229, 28, FLOOR - 1, W[3])
    t.rect(209, 22, 230, 27, W[4])
    t.rect(226, 13, 230, 22, W[4])
    t.rect(228, 11, 235, 15, W[4])
    t.dot(232, 12, N[0])
    for y in range(13, 23):
        t.dot(225, y, V[3])
    t.hline(204, 209, 22, V[3])
    t.rect(214, 20, 220, 22, V[2])  # the saddle
    # blocks, a top and a ball
    for x, y, c in ((248, 31, V[3]), (254, 31, G[3]), (251, 26, B[3])):
        t.rect(x, y, x + 4, y + 4, c)
        t.hline(x, x + 4, y, M[1])
        t.vline(x + 4, y, y + 4, N[1])
    t.poly([(264, 29), (270, 29), (267, 36)], E[3])
    t.hline(264, 270, 29, E[5])
    t.vline(267, 26, 28, W[4])
    t.disc(284, 32, 3.5, L[2])
    t.dot(283, 30, L[3])


def banner_cellar():
    """Control Room: the cellar, kept calm: wine racks, the stair down, barrels, the boiler."""
    p = room_shell(paper=N[2], motif=N[2], panels=False)
    for y in range(5, 34, 4):  # brick courses
        p.hline(0, BW - 1, y, N[3])
        for x in range((y // 4) % 2 * 5, BW, 10):
            p.vline(x, y + 1, y + 3, N[3])
    # a small barred window high up, and its beam
    p.rect(118, 5, 132, 10, N[5])
    for x in range(119, 132, 3):
        p.vline(x, 5, 10, N[1])
    moonbeam(p, 118, 132, 11, 1.0)
    # a lone barrel on its end, left, low
    p.rect(24, 26, 38, FLOOR, W[1])
    p.hline(24, 38, 26, W[2])
    p.hline(24, 38, 29, N[2])
    p.hline(24, 38, 33, N[2])
    # the wine racks: a lattice of bottle ends, right of the title
    p.rect(146, 12, 200, FLOOR, W[1])
    for y in range(14, FLOOR, 4):
        for x in range(148, 200, 4):
            p.dot(x, y, (G[1], V[1], G[2], V[2])[(x + y) % 4])
            p.dot(x + 1, y, W[0])
    p.hline(146, 200, 12, W[3])
    # the pipes along the ceiling
    for y, c, hi in ((5, B[1], B[2]), (8, E[1], E[2])):
        p.hline(140, 299, y, c)
        p.hline(140, 299, y - 1, hi)
        for x in range(150, 300, 28):
            p.rect(x, y - 2, x + 1, y + 1, B[2])
    # barrels on their side, stacked
    for cx, cy in ((212, 30), (228, 30), (220, 21)):
        p.disc(cx, cy, 6.5, W[2])
        p.disc(cx, cy, 5, W[1])
        p.disc(cx, cy, 2, W[2])
        p.dot(cx - 3, cy - 3, W[4])
    # gauges on a board (no numbers), over the barrels
    p.rect(206, 8, 238, 13, W[1])
    for x, a in ((212, 0.6), (222, -0.4), (232, 1.1)):
        p.disc(x, 10.5, 2.4, B[2])
        p.disc(x, 10.5, 1.7, M[2])
        p.dot(round(x + math.cos(a - 1.57)), round(10 + math.sin(a - 1.57)), V[2])
    # the boiler, riveted, its grate glowing
    p.rect(250, 12, 296, FLOOR, N[4])
    p.disc(273, 14, 23, N[4])
    for y in range(0, FLOOR + 1):
        for x in range(250, 297):
            if p.get(x, y)[:3] == rgba(N[4])[:3]:
                if x > 288:
                    p.dot(x, y, N[3])
                elif x < 254:
                    p.dot(x, y, N[6])
    for x in range(252, 296, 6):
        p.dot(x, 16, N[6])
        p.dot(x, 33, N[6])
    p.rect(262, 22, 284, 32, N[0])
    for x in range(264, 283, 3):
        p.vline(x, 24, 30, (E[4], E[3], E[5])[x % 3])
    warm(p, 273, 34, 16, 1.0)
    p.rect(310, 8, 399, FLOOR, N[1])  # the far end: the cellar's dark
    return quiet(lit_room(p))


def banner_bedroom():
    """Me: a bedroom of the manor: the dressing table, the curtained window, the four-poster bed."""
    p = room_shell(motif=R[1])
    # a low chest at the foot of the room, left
    p.rect(20, 28, 48, FLOOR, W[1])
    p.hline(20, 48, 28, W[3])
    p.dot(34, 31, B[2])
    p.rect(66, 30, 76, FLOOR, V[1])  # a stool
    p.hline(66, 76, 30, V[2])
    # the nightstand and its candle
    p.rect(206, 24, 222, FLOOR, W[2])
    p.hline(206, 222, 24, W[4])
    candle(p, 212, 23, 5, 1)
    p.rect(216, 21, 221, 23, V[2])
    p.hline(216, 221, 21, P_BOOK)
    warm(p, 213, 17, 12, 0.9)
    # the window and its curtains (the right curtain is a header layer: someone hides there)
    p.rect(244, 5, 264, 25, N[5])
    p.vgrad(245, 6, 263, 24, [N[4], N[5], N[6]])
    p.disc(259, 10, 2.6, M[1])
    p.vline(254, 5, 25, W[1])
    p.hline(245, 263, 15, W[1])
    p.rect(242, 26, 266, 27, W[3])
    moonbeam(p, 245, 263, 28, 0.8)
    curtain(p, 238, 245)
    curtain(p, CURTAIN_X, CURTAIN_X + 7)
    p.hline(236, 272, 3, B[2])
    # the four-poster bed, running on into the room's quiet end
    p.rect(276, 3, 277, FLOOR, W[3])
    p.rect(350, 3, 351, FLOOR, W[3])
    p.rect(274, 2, 353, 5, V[1])
    p.hline(274, 353, 2, V[3])
    for x in range(276, 352, 5):
        p.vline(x, 6, 7, V[2])
    p.rect(278, 18, 349, 24, W[2])
    p.hline(278, 349, 18, W[4])
    p.rect(278, 25, 349, 33, V[2])
    p.hline(278, 349, 25, V[4])
    p.rect(282, 21, 296, 26, M[1])
    p.rect(300, 21, 314, 26, M[1])
    p.hline(282, 314, 26, M[2])
    for x in range(280, 348, 6):
        p.dot(x, 30, V[3])
    p.rect(278, 33, 349, 35, V[1])
    p.rect(362, 6, 396, FLOOR, W[1])  # a wardrobe in the dark
    p.vline(379, 6, FLOOR, W[0])
    return quiet(lit_room(p))


def curtain(p, x0, x1, ghost=None, sway=0, wide=False):
    """A velvet curtain in folds; with ghost (0–1), a little ghost peeks out from behind it;
    sway (0–2) swings its hem after someone brushed past; wide: the ghost's eyes, startled."""
    for x in range(x0, x1 + 1):
        p.vline(x, 4, 30, (V[2], V[1], V[3])[(x - x0 + sway) % 3])
    for k in range(sway):  # the hem swinging out
        p.vline(x1 + 1 + k, 22 + k * 3, 30, V[1] if k else V[2])
    p.hline(x0, x1, 4, V[4])
    p.hline(x0 + 1, x1 - 1, 20, B[2])  # the tie-back
    if ghost:
        gx = x1 + 1 - round(ghost * 5)
        if wide:
            for dx, dy, c in ((0, 0, H[2]), (1, 0, H[3]), (2, 0, H[3]), (3, 0, H[2]), (0, 1, H[3]), (1, 1, N[1]), (2, 1, H[3]),
                              (3, 1, N[1]), (4, 1, H[2]), (0, 2, H[3]), (1, 2, N[1]), (2, 2, H[3]), (3, 2, N[1]), (4, 2, H[2]),
                              (0, 3, H[2]), (1, 3, H[3]), (2, 3, N[2]), (3, 3, H[2]), (4, 3, H[1]), (0, 4, H[1]), (2, 4, H[1]),
                              (4, 4, H[1]), (5, 1, L[0]), (5, 2, L[0]), (5, 3, L[0])):
                p.dot(gx + dx, 10 + dy, c)
            return
        for dx, dy, c in ((0, 0, H[2]), (1, 0, H[2]), (2, 0, H[2]), (0, 1, H[2]), (1, 1, N[1]), (2, 1, H[3]), (3, 1, H[2]),
                          (0, 2, H[2]), (1, 2, H[3]), (2, 2, H[3]), (3, 2, H[2]), (0, 3, H[1]), (1, 3, H[2]), (2, 3, H[1]),
                          (3, 3, H[1]), (4, 1, L[0]), (4, 2, L[0]), (3, 0, L[0])):
            p.dot(gx + dx, 11 + dy, c)


def header_layer(draw, frames, span=BW // 2):
    """A header layer: the banner's pixels from row LAYER_DY down, drawn at ×3 over the banner and
    centred on it; span (half its width, native) keeps a pokeable piece no wider than its subject."""
    x0, w = BW // 2 - span, 2 * span
    out = Image.new("RGBA", (w * frames, 24))
    for f in range(frames):
        big = Pic(BW, BH)
        draw(big, f)
        out.paste(big.im.crop((x0, LAYER_DY, x0 + w, LAYER_DY + 24)), (f * w, 0))
    return out


PORTRAIT_SPAN = BW // 2 - PORTRAIT_X  # the portrait's piece: x 188–211
CURTAIN_SPAN = CURTAIN_X + 12 - BW // 2  # the curtain's piece: x 124–275


def portrait_poke(p, f):
    """Poke the ancestor: it rolls its eyes up and round, then winks (8 frames)."""
    portrait(p, PORTRAIT_X, 12, eyes=("up", "up", "right", "left", "open", "wink", "wink", "open")[f])


def curtain_poke(p, f):
    """Poke the curtain: the ghost pops out startled, ducks back, the curtain swings (8 frames)."""
    ghost, sway, wide = [(1, 0, True), (1, 0, True), (0.6, 0, False), (0.2, 1, False), (0, 2, False), (0, 1, False),
                         (0, 2, False), (0, 0, False)][f]
    curtain(p, CURTAIN_X, CURTAIN_X + 7, ghost or None, sway, wide)


def sconce_layer(p, f):
    for i, x in enumerate(SCONCES):
        wall_sconce(p, x, 8, (f + i * 2) % 4)


def portrait_layer(p, f):
    portrait(p, PORTRAIT_X, 12, eyes="closed" if f in (13, 14) else "open")


def curtain_layer(p, f):
    ghost = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.2, 0.5, 0.8, 1, 1, 1, 0.8, 0.4, 0, 0, 0, 0, 0, 0][f]
    curtain(p, CURTAIN_X, CURTAIN_X + 7, ghost or None)


def bedroom():
    """space.room.scene: your room in the manor (134 × 60 → 402 × 180); what matters sits in the
    middle band (phones crop the top and bottom)."""
    p = Pic(134, 60, N[1])
    for y in range(3, 50, 7):
        for x in range((y // 7) % 2 * 5, 134, 10):
            for dx, dy in ((0, 0), (-1, 1), (1, 1), (0, 2), (0, -1)):
                p.dot(x + dx, y + dy, L[0])
    p.rect(0, 0, 133, 2, N[2])
    p.hline(0, 133, 3, N[3])
    p.rect(0, 50, 133, 59, W[0])
    p.hline(0, 133, 50, W[2])
    for y in (53, 56):
        for x in range((y * 5) % 11, 134, 22):
            p.hline(x, x + 1, y, W[1])
    # the window: the night outside, the moon, a bat
    p.rect(10, 8, 40, 44, W[2])
    p.vgrad(12, 10, 38, 42, [N[2], N[3], N[4], N[5]])
    p.poly([(10, 10), (25, 2), (41, 10)], W[2])
    p.poly([(12, 10), (25, 4), (39, 10)], N[2])
    p.disc(31, 16, 4.3, M[1])
    p.dot(32, 17, M[2])
    p.dot(29, 16, M[2])
    hill(p, 12, 38, 36, 44, N[1], N[4], 2, 0.5)
    dead_tree(p, 17, 41, 22, 5, N[0], 0.1)
    bat(p, 22, 14, 1)
    p.vline(25, 8, 42, W[1])
    p.hline(12, 38, 26, W[1])
    p.rect(9, 43, 42, 45, W[3])  # the sill
    for x0, x1 in ((4, 11), (39, 46)):  # curtains
        for x in range(x0, x1 + 1):
            p.vline(x, 4, 48, (V[2], V[1], V[3])[(x - x0) % 3])
        p.hline(x0, x1, 4, V[4])
    p.hline(2, 48, 3, B[2])
    portrait(p, 88, 8)
    # the bed
    p.rect(64, 6, 65, 50, W[3])
    p.rect(128, 6, 129, 50, W[3])
    p.rect(62, 4, 131, 8, V[1])
    p.hline(62, 131, 4, V[3])
    for x in range(64, 130, 5):
        p.vline(x, 9, 11, V[2])
    p.rect(66, 28, 127, 34, W[2])
    p.hline(66, 127, 28, W[4])
    p.rect(66, 34, 127, 46, V[2])
    p.hline(66, 127, 34, V[4])
    p.rect(70, 31, 84, 36, M[1])
    p.rect(88, 31, 102, 36, M[1])
    p.hline(70, 102, 36, M[2])
    for x in range(68, 126, 6):
        p.dot(x, 41, V[3])
    p.rect(66, 46, 127, 49, V[1])
    # a small friendly ghost peeking from under the cover
    for dx, dy, c in ((110, 32, H[2]), (111, 31, H[2]), (112, 31, H[2]), (113, 32, H[2]), (110, 33, H[1]), (113, 33, H[1]),
                      (111, 32, N[1]), (112, 32, H[3])):
        p.dot(dx, dy, c)
    p.hline(109, 114, 34, V[3])
    # the nightstand, a candle, a book
    p.rect(48, 38, 60, 50, W[2])
    p.hline(48, 60, 38, W[4])
    p.rect(50, 42, 58, 43, W[1])
    candle(p, 52, 37, 6, 0)
    p.rect(55, 35, 59, 37, V[2])
    p.hline(55, 59, 35, P_BOOK)
    glow(p, 53, 28, 13, None, 0.5, only_clear=False)
    # a rug
    p.rect(40, 54, 100, 57, V[1])
    p.hline(40, 100, 54, V[3])
    for x in range(42, 100, 4):
        p.dot(x, 56, B[2])
    return p


def frame9(kind):
    """A 9-slice frame of 3 × 3 cells, each s native pixels (slice = 3s on screen), clear inside.
    panel: a carved groove with an iron stud at each corner. sheet: a wider moulding with brass
    corner brackets. nowbar: the groove with brass corner scrolls."""
    s = {"panel": 4, "sheet": 6, "nowbar": 4}[kind]
    p = Pic(3 * s, 3 * s)
    n = 3 * s
    if kind in ("panel", "nowbar"):
        for i in range(1, n - 1):  # the groove: in shadow top-left, its lower lip lit
            p.dot(i, 1, N[0])
            p.dot(1, i, N[0])
            p.dot(i, n - 2, N[3])
            p.dot(n - 2, i, N[3])
        if kind == "panel":
            for cx, cy in ((0, 0), (n - 4, 0), (0, n - 4), (n - 4, n - 4)):  # studs
                p.rect(cx, cy, cx + 3, cy + 3, None)
                p.rect(cx + 1, cy + 1, cx + 2, cy + 2, N[4])
                p.dot(cx + 1, cy + 1, N[7])
                p.dot(cx + 2, cy + 2, N[1])
        else:
            for fx, fy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                for x, y in ((1, 1), (2, 1), (3, 1), (1, 2), (1, 3), (3, 2), (2, 3)):
                    p.dot(x if not fx else n - 1 - x, y if not fy else n - 1 - y, B[2] if (x, y) != (1, 1) else B[4])
    else:
        shade = {N[4]: N[1], N[2]: N[2], N[1]: N[3], N[0]: N[0]}
        for i in range(n):
            for k, c in ((0, N[4]), (1, N[2]), (2, N[1]), (3, N[0])):
                p.dot(i, k, c)
                p.dot(k, i, c)
                p.dot(i, n - 1 - k, shade[c])
                p.dot(n - 1 - k, i, shade[c])
        for fx in (0, 1):  # brass corner brackets
            for fy in (0, 1):
                for x, y in ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 1), (2, 2), (5, 1), (1, 5)):
                    p.dot(x if not fx else n - 1 - x, y if not fy else n - 1 - y, B[3] if (x + y) < 3 else B[2])
    return p


OWL = {  # 9 × 10 over a fence post; k dark, m pale face, E eyes, r beak, L breast, n back of the head
    "front": [".k.....k.", ".kk...kk.", "kkkkkkkkk", "kmmkkkmmk", "kmEmkmEmk", "kmmmrmmmk", "kkLkkkLkk", "kLkLkLkLk",
              ".kLLkLLk.", "..kk.kk.."],
    "blink": [".k.....k.", ".kk...kk.", "kkkkkkkkk", "kmmkkkmmk", "kkkmkmkkk", "kmmmrmmmk", "kkLkkkLkk", "kLkLkLkLk",
              ".kLLkLLk.", "..kk.kk.."],
    "wide": [".k.....k.", ".kk...kk.", "kkkkkkkkk", "kmEEkEEmk", "kmEEkEEmk", "kmmmrmmmk", "kkLkkkLkk", "kLkLkLkLk",
             ".kLLkLLk.", "..kk.kk.."],
    "side": ["...k.....", "..kk.....", ".kkkkkkk.", "kmmkkkkk.", "rmEmkkkk.", "kmmmkkkk.", "kkLkkkLk.", "kLkLkLkLk",
             ".kLLkLLk.", "..kk.kk.."],
    "back": [".k.....k.", ".kk...kk.", "kkkkkkkkk", "knnnnnnnk", "knnknnnnk", "knnnnnnnk", "kkLkkkLkk", "kLkLkLkLk",
             ".kLLkLLk.", "..kk.kk.."],
    "hoot": [".k.....k.", "kkk...kkk", "kkkkkkkkk", "kmmkkkmmk", "kmEmkmEmk", "kmmrrrmmk", "kkLkrkLkk", "kLkLkLkLkk",
             "kkLLkLLkk", "..kk.kk.."],
}


def owl_piece(pose):
    """The owl on its fence post (11 × 20): Home's picture, bottom right."""
    p = Pic(11, 20)
    for dy, row in enumerate(OWL[pose]):
        for dx, ch in enumerate(row[:11]):
            if ch != ".":
                p.dot(1 + dx, dy, {"k": N[0], "m": N[4], "E": E[5], "r": E[3], "L": N[3], "n": N[2]}[ch])
    p.dot(2, 1, N[5])  # the moon on its tufts
    p.rect(4, 10, 6, 19, N[0])  # the post
    p.vline(4, 10, 19, N[4])
    p.rect(3, 10, 7, 10, N[0])
    return p


def owl_idle(frame):
    return owl_piece("blink" if frame == 11 else "front")


def owl_poke(frame):
    """Poke the owl: its eyes go wide, its head turns right round and back, and it hoots."""
    return owl_piece(("wide", "wide", "side", "back", "back", "side", "front", "hoot", "hoot", "front")[frame])


def bit(kind):
    """Little bits a poke throws: a spark, a small feather, a puff of smoke."""
    p = Pic(3, 2)
    if kind == "spark":
        p.dot(0, 0, E[6])
        p.dot(1, 1, E[3])
    elif kind == "feather":
        p.hline(0, 2, 0, N[5])
        p.dot(1, 1, N[4])
    else:
        p.hline(0, 1, 0, N[5])
        p.dot(1, 1, N[4])
    return p


def sheet_of(fn, n):
    """Frames of a picture side by side (a layer's "frames")."""
    first = fn(0)
    out = Image.new("RGBA", (first.w * n, first.h))
    for i in range(n):
        out.paste(fn(i).im, (i * first.w, 0))
    return out


def sheet_look():
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "themes/_kit/art/sheet.py"), str(OUT), "/tmp/carved-night-sheet.png"], check=True)


JOBS = {
    "hero": lambda: export(hero(), "hero.png"),
    "sky": lambda: export(sky(), "sky.png"),
    "clouds": lambda: export(clouds_tile(), "clouds.png", 1),
    "manor": lambda: export(manor_sheet(), "manor.png", 1),
    "near": lambda: export(sheet_of(near_scene, 8), "near.png", 1),
    "bat": lambda: export(bat_sheet(), "bat.png", 1),
    "star": lambda: export(shooting_star(), "star.png", 1),
    "roofline": lambda: export(roofline(), "roofline.png"),
    "status-life": lambda: [export(sheet_of(status_life, 16), "status-life.png", 1),
                            export(sheet_of(status_poke, 8), "status-poke.png", 1)],
    "crest": lambda: export(crest(), "crest.png"),
    "ghost": lambda: export(ghost_empty(), "ghost.png"),
    "candle-table": lambda: [export(sheet_of(candle_table_layer, 8), "candle-table.png", 1),
                             export(sheet_of(candle_table_poke, 6), "candle-table-poke.png", 1)],
    "bits": lambda: [export(bit("spark"), "bit-spark.png", 1), export(bit("feather"), "bit-feather.png", 1),
                     export(bit("smoke"), "bit-smoke.png", 1)],
    "owl": lambda: [export(sheet_of(owl_idle, 16), "owl.png", 1), export(sheet_of(owl_poke, 10), "owl-poke.png", 1)],
    "column": lambda: export(column(), "column.png"),
    "tv": lambda: export(tv(), "tv.png"),
    "deck": lambda: [export(deck_frame(), "deck-frame.png"), export(sheet_of(deck_flame, 4), "deck-flame.png", 1),
                     export(sheet_of(deck_flame_poke, 6), "deck-flame-poke.png", 1)],
    **{f"banner-{n}": (lambda n=n: export(globals()["banner_" + n](), f"banner-{n}.png"))
       for n in ("hall", "parlour", "screening", "kitchen", "library", "attic", "cellar", "bedroom")},
    "header-layers": lambda: [export(header_layer(sconce_layer, 4), "sconces.png", 1),
                              export(header_layer(portrait_layer, 16, PORTRAIT_SPAN), "portrait.png", 1),
                              export(header_layer(portrait_poke, 8, PORTRAIT_SPAN), "portrait-poke.png", 1),
                              export(header_layer(curtain_layer, 24, CURTAIN_SPAN), "curtain.png", 1),
                              export(header_layer(curtain_poke, 8, CURTAIN_SPAN), "curtain-poke.png", 1)],
    "bedroom": lambda: export(bedroom(), "bedroom.png"),
    "frames": lambda: [export(frame9(k), f"{k}-frame.png") for k in ("panel", "sheet", "nowbar")],
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or list(JOBS)
    for name in wanted:
        JOBS[name]()
