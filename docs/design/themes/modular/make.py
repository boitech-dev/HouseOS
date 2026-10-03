"""Modular's pictures, all drawn by code on one grid of modules (squares, quarter circles, dots).

    python3 docs/design/themes/modular/make.py            # every picture into themes/modular/art/
    python3 docs/design/themes/modular/make.py --preview  # plus previews on both grounds (scratch)

Every picture is SVG in three inks only: PAPER, INK and RED, on a clear ground. The page's own
ground swallows one of the inks: on the light paper the PAPER shapes vanish (they read as cuts in
the black), on the dark paper the INK shapes vanish (only what was cut out shows). So each picture
is its own negative when the scheme changes. No letters or numerals anywhere."""

import math
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ART = ROOT / "themes" / "modular" / "art"
sys.path.insert(0, str(ROOT / "themes" / "_kit" / "art"))

PAPER, INK, RED = "#F2EFE8", "#141312", "#EE3A1F"
RED_L, RED_D = "#CC2812", "#FF4F2E"  # each scheme's own red (the buttons' red)
GREY = "#8A867E"  # the page grid only: a mid tone that reads faintly on both papers
TONE = "#3A3834"  # night: the buildings' grey, a step up from the dark paper
SKY, RULE = "#000001", "#000002"  # roles only: what shows through a window, the ground line

# How a picture's roles print. "both": one file for both schemes (the page swallows one ink).
# "light": day. "night": the dark scheme's own picture (blocks in grey, windows lit, the sky
# black). "neg": the dark scheme's picture as a true negative (ink and paper swapped).
MAPS = {
    "both": {INK: INK, PAPER: PAPER, RED: RED, SKY: PAPER, RULE: INK},
    "light": {INK: INK, PAPER: PAPER, RED: RED_L, SKY: PAPER, RULE: INK},
    "night": {INK: TONE, PAPER: PAPER, RED: RED_D, SKY: INK, RULE: "#6E6A63"},
    "neg": {INK: PAPER, PAPER: INK, RED: RED_D, SKY: INK, RULE: PAPER},
}


# ------------------------------------------------------------------ the module vocabulary
def f(n):
    return f"{n:.2f}".rstrip("0").rstrip(".")


def sector(cx, cy, R, r=0.0, a0=0, a1=90):
    """A ring sector (r > 0) or a pie (r = 0), angles in degrees, 0 = east, 90 = south."""
    def pt(rad, a):
        return cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    x0, y0 = pt(R, a0)
    x1, y1 = pt(R, a1)
    if r <= 0:
        return f"M{f(cx)} {f(cy)}L{f(x0)} {f(y0)}A{f(R)} {f(R)} 0 {large} 1 {f(x1)} {f(y1)}Z"
    x2, y2 = pt(r, a1)
    x3, y3 = pt(r, a0)
    return (f"M{f(x0)} {f(y0)}A{f(R)} {f(R)} 0 {large} 1 {f(x1)} {f(y1)}"
            f"L{f(x2)} {f(y2)}A{f(r)} {f(r)} 0 {large} 0 {f(x3)} {f(y3)}Z")


# A pie's quadrant by the direction it bulges from its centre (SVG angles, y down).
DIRS = {"se": (0, 90), "sw": (90, 180), "nw": (180, 270), "ne": (270, 360),
        "n": (180, 360), "s": (0, 180), "e": (270, 450), "w": (90, 270), "o": (0, 359.99)}


class Pic:
    """A picture on a grid of `cell` px; every coordinate is in cells. Paint order = call order."""

    def __init__(self, w, h, cell=1):
        self.w, self.h, self.cell, self.parts = w, h, cell, []

    def path(self, d, fill):
        self.parts.append(f'<path d="{d}" fill="{fill}"/>')
        return self

    def rect(self, x, y, w, h, fill):
        c = self.cell
        self.parts.append(f'<rect x="{f(x * c)}" y="{f(y * c)}" width="{f(w * c)}" height="{f(h * c)}" fill="{fill}"/>')
        return self

    def dot(self, x, y, r, fill):
        """A circle centred at (x, y), radius r."""
        c = self.cell
        self.parts.append(f'<circle cx="{f(x * c)}" cy="{f(y * c)}" r="{f(r * c)}" fill="{fill}"/>')
        return self

    def pie(self, x, y, R, way, fill, r=0.0):
        """A quarter (ne, se, sw, nw), half (n, s, e, w) or whole (o) circle centred at (x, y),
        radius R; with r > 0, a ring of that inner radius."""
        c = self.cell
        a0, a1 = DIRS[way]
        if way == "o":
            if r <= 0:
                return self.dot(x, y, R, fill)
            d = (f"M{f((x - R) * c)} {f(y * c)}a{f(R * c)} {f(R * c)} 0 1 0 {f(2 * R * c)} 0"
                 f"a{f(R * c)} {f(R * c)} 0 1 0 {f(-2 * R * c)} 0Z"
                 f"M{f((x - r) * c)} {f(y * c)}a{f(r * c)} {f(r * c)} 0 1 1 {f(2 * r * c)} 0"
                 f"a{f(r * c)} {f(r * c)} 0 1 1 {f(-2 * r * c)} 0Z")
            self.parts.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/>')
            return self
        return self.path(sector(x * c, y * c, R * c, r * c, a0, a1), fill)

    def cut(self, x, y, w, h, fill, cx, cy, R, way):
        """A w × h block with a pie (centre cx, cy, radius R) cut out of it: one path, so no ink
        hides under the paper and no hairline shows where their edges meet."""
        c = self.cell
        box = f"M{f(x * c)} {f(y * c)}h{f(w * c)}v{f(h * c)}h{f(-w * c)}Z"
        a0, a1 = DIRS[way]
        self.parts.append(f'<path d="{box}{sector(cx * c, cy * c, R * c, 0, a0, a1)}" fill="{fill}" fill-rule="evenodd"/>')
        return self

    def svg(self):
        body = "".join(self.parts)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" shape-rendering="geometricPrecision">{body}</svg>\n')

    def save(self, name, variant="both"):
        out = ART / name
        tmp = out.with_suffix(".tmp")
        colours = MAPS[variant]
        tmp.write_text(re.sub(r"#[0-9A-Fa-f]{6}", lambda m: colours.get(m.group(0), m.group(0)), self.svg()))
        os.replace(tmp, out)
        return out


# ------------------------------------------------------------------ previews
SCRATCH = Path(os.environ.get("MODULAR_PREVIEW", "/tmp/claude-1000/modular-preview"))


def raster(svg_path, w, h):
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "x.png"
        subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(png), str(svg_path)], check=True)
        return Image.open(png).convert("RGBA")


def on_grounds(files, w, h, name, mask=None):
    """The picture on the light paper and on the dark paper, side by side (with the hero's fade):
    one file on both, or the light file on paper and the dark file on the dark paper."""
    import numpy as np
    from PIL import Image
    files = list(files) * (2 if len(files) == 1 else 1)
    sheet = Image.new("RGB", (w * 2 + 30, h + 20), "#777777")
    for i, (ground, svg_path) in enumerate(zip((PAPER, INK), files)):
        img = raster(svg_path, w, h)
        if mask:
            img.putalpha(Image.fromarray(np.minimum(np.array(img.getchannel("A")), mask(w, h)).astype("uint8")))
        box = Image.new("RGBA", (w, h), ground)
        box.alpha_composite(img)
        sheet.paste(box.convert("RGB"), (10 + i * (w + 10), 10))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sheet.save(SCRATCH / f"{name}.png")
    return SCRATCH / f"{name}.png"


def fade(direction, start):
    import numpy as np

    def m(w, h):
        if direction == "right":  # transparent at the left, opaque from `start` of the width
            ramp = np.clip(np.arange(w) / (w * start), 0, 1)
            return np.tile(ramp * 255, (h, 1))
        ramp = np.clip((h - np.arange(h)) / (h * (1 - start)), 0, 1)  # opaque down to start
        return np.tile((ramp * 255)[:, None], (1, w))
    return m


def contact(out):
    """Every preview (each picture on both papers) and the pieces, stacked: the contact sheet."""
    from PIL import Image
    files = sorted(p for p in SCRATCH.glob("*.png") if p.stem.split("-")[-1].isdigit() or p.stem == "sprites")
    ims = [Image.open(f).convert("RGB") for f in files]
    ims = [i if i.width <= 1400 else i.resize((1400, round(i.height * 1400 / i.width))) for i in ims]
    sheet = Image.new("RGB", (1400, sum(i.height + 8 for i in ims)), "#555555")
    y = 0
    for i in ims:
        sheet.paste(i, (0, y))
        y += i.height + 8
    sheet.save(out)
    print("  contact sheet", out)


# ------------------------------------------------------------------ Home's hero
def hero():
    """The theme's cover poster: a street of module houses on a canal. 1200 × 400 on a 25 px grid
    (48 × 16). The street stands on a line at 52 % of the height, so on phones (the lower 45 %
    fades) every door ends above the fade; below the line its reflection, bars of the same
    widths, can fade away. Wide screens show the right 60 % (the left fades): the street starts
    at 37 %. By day black houses under a black sun (hero.svg); by night grey houses with lit
    windows, a crescent and stars (hero-dark.svg): the same drawing, printed in its night inks."""
    p = Pic(1200, 400, 50)
    B, e = 4.2, 0.02  # the street's line (52 %); a hair of overlap so no seam shows
    # sky: the moon (paper) rising behind the roofs, the ink disc biting it: the sun by day
    p.dot(19.7, 0.92, 0.76, PAPER).dot(20.05, 0.62, 0.66, INK)
    for x, y in ((11, 0.9), (13.1, 0.35), (15, 1.1), (17.3, 0.45), (22.6, 0.4), (23.3, 1.0)):
        p.dot(x, y, 0.07, PAPER)
    houses = []
    win = 0.45  # a window module

    def low(x, w, h):
        p.rect(x, B - h, w, h, INK)
        ws = [(x + 0.3 + 0.8 * i, 0.5) for i in range(int((w - 0.2) // 0.8))]
        for wx, ww in ws:
            p.rect(wx, B - h + 0.35, ww, 0.25, PAPER)
        houses.append((x, w, ws))

    def shed(x, w, h, way="ne"):
        p.rect(x, B - h - e, w, h + e, INK).pie(x if way == "ne" else x + w, B - h, w, way, INK)
        p.dot(x + w / 2, B - h / 2 - 0.1, 0.25, PAPER)
        houses.append((x, w, [(x + w / 2 - 0.25, 0.5)]))

    def dome(x, w, h, door=False):
        p.rect(x, B - h - e, w, h + e, INK).pie(x + w / 2, B - h, w / 2, "n", INK)
        ws = [(x + 0.3, win), (x + w - 0.3 - win, win)]
        for wx, ww in ws:
            p.rect(wx, B - h + 0.15, ww, win, PAPER)
        if door:
            p.rect(x + w / 2 - 0.25, B - 0.8, 0.5, 0.8, RED)
        houses.append((x, w, ws))

    def tower(x, w, h, n=3):
        p.rect(x, B - h - e, w, h + e, INK).pie(x + w / 2, B - h, w / 2, "n", INK)
        for k in range(n):
            p.dot(x + w / 2, B - h + 0.45 + 0.7 * k, 0.22, PAPER)
        houses.append((x, w, [(x + w / 2 - 0.22, 0.44)]))

    def saw(x, w, h):
        p.rect(x, B - h - e, w, h + e, INK)
        for k in range(2):
            p.pie(x + k * w / 2, B - h, w / 2, "ne", INK)
        ws = [(x + 0.3 + 0.65 * i, 0.35) for i in range(3)]
        for wx, ww in ws:
            for j in range(2):
                p.rect(wx, B - h + 0.3 + 0.6 * j, ww, 0.35, PAPER)
        houses.append((x, w, ws))

    low(9.4, 1.8, 0.9)
    shed(11.35, 1.5, 1.1)
    dome(13.0, 2.2, 1.3, door=True)
    tower(15.35, 1.1, 2.6)
    saw(16.6, 2.2, 1.6)
    shed(18.95, 1.5, 1.0, way="nw")
    tower(20.6, 1.1, 2.0, n=2)
    dome(21.85, 1.6, 0.9)
    # the street's line and, below it, the reflection: bars of each house's width, shortening
    p.rect(9, B, 14.9, 0.07, RULE)
    for x, w, windows in houses:
        for k, share in enumerate((0.8, 0.5, 0.25)):
            bw = w * share
            p.rect(x + (w - bw) / 2, B + 0.45 + 0.4 * k, bw, 0.15, INK)
        for wx, ww in windows:  # lit windows ripple in the water (paper: seen only by night)
            p.rect(wx, B + 0.2, ww, 0.09, PAPER)
    return p


# ------------------------------------------------------------------ the page's grid
def grid():
    """One module of the page grid: a dot where the lines cross (24 px). Mid grey, so the same
    tile reads faintly on the light and the dark paper."""
    p = Pic(24, 24)
    return p.dot(12, 12, 1.25, GREY)


# ------------------------------------------------------------------ room emblems (banners)
# Gerstner's programme: every room is a 4 × 3 grid of 24 px modules; the red module is one cell,
# and it steps to a new place in each room. Ink shapes with paper cut into them.
def emblem(p, room, ox, oy):
    """Draw `room`'s emblem with its top-left at cell (ox, oy) of a 24 px grid."""
    def R(x, y, w, h, c=INK):
        p.rect(ox + x, oy + y, w, h, c)

    def D(x, y, r, c=INK):
        p.dot(ox + x, oy + y, r, c)

    def P(x, y, rad, way, c=INK, r=0.0):
        p.pie(ox + x, oy + y, rad, way, c, r)

    e = 0.03
    if room == "home":
        R(1.75, 0.1, 0.4, 0.9); R(0.5, 1.5 - e, 2, 1.5 + e); P(1.5, 1.5, 1, "n")
        R(0.75, 1.75, 0.4, 0.4, PAPER); R(1.4, 2.1, 0.45, 0.9, PAPER)
        D(3.5, 2.5, 0.5, RED)
    elif room == "listen":
        P(0, 3, 3, "ne"); P(0, 3, 2.25, "ne", PAPER, 1.75); P(0, 3, 1.25, "ne", PAPER, 0.75)
        D(3.5, 2.5, 0.5, RED)
    elif room == "watch":
        R(0, 0, 3, 2.25); R(0.25, 0.25, 2.5, 1.75, PAPER); R(1.25, 2.25 - e, 0.5, 0.5 + e); R(0.75, 2.75, 1.5, 0.25)
        D(3.5, 0.5, 0.5, RED)
    elif room == "games":
        R(1, 0, 1, 3); R(0, 1, 3, 1); D(1.5, 1.5, 0.25, PAPER)
        D(3.5, 0.75, 0.4); D(3.5, 2.25, 0.4, RED)
    elif room == "house":
        for i, y in enumerate((0, 1.125, 2.25)):
            R(0, y, 0.75, 0.75, RED if i == 0 else INK)
            if i:
                R(0.19, y + 0.19, 0.37, 0.37, PAPER)
            R(1.25, y + 0.25, 2.75 - i * 0.75, 0.25)
    elif room == "files":
        R(0, 0.5, 1.5, 0.5 + e); P(1.5, 1, 0.5, "nw" if False else "ne")
        R(0, 1, 4, 2); R(0.25, 1.25, 3.5, 0.25, PAPER)
        R(3, 0, 1, 0.75, RED)
    elif room == "ask":
        D(1.5, 1.5, 1.5); P(0, 3, 1, "ne")
        for x in (0.75, 1.5, 2.25):
            D(x, 1.5, 0.2, PAPER)
        D(3.5, 0.5, 0.5, RED)
    elif room == "me":
        D(1.5, 0.75, 0.75); P(1.5, 3, 1.5, "n"); P(1.5, 3, 0.6, "n", PAPER); D(1.5, 0.75, 0.3, PAPER)
        D(3.5, 2.5, 0.5, RED)
    elif room == "control":
        for x, k, c in ((0.5, 0.75, INK), (1.75, 2.25, RED), (3, 1.25, INK)):
            R(x - 0.125, 0, 0.25, 3); R(x - 0.5, k - 0.5, 1, 1, c)
            if c == INK:
                D(x, k, 0.2, PAPER)
    elif room == "smart-home":
        D(1.5, 1.25, 1.25); P(1.5, 1.25, 0.6, "s", PAPER); R(1, 2.5 - e, 1, 0.5 + e)
        R(3, 2, 1, 1, RED)
    elif room == "inbox":
        R(0, 1.25, 4, 1.75); P(2, 1.25, 1, "s", PAPER)
        R(1.5, 0, 1, 0.75, RED)
    elif room == "space":
        R(0, 0, 2, 2); R(0.94, 0, 0.12, 2, PAPER); R(0, 0.94, 2, 0.12, PAPER)
        D(3, 0.5, 0.5); R(2.9, 0.5, 0.2, 2.25); R(0, 2.75, 3, 0.25, RED)
    elif room == "party":
        for x, y, r in ((0.5, 0.5, 0.35), (2, 0.25, 0.2), (1.25, 1.5, 0.5), (3.25, 1.25, 0.3),
                        (0.4, 2.5, 0.25), (2.5, 2.5, 0.4)):
            D(x, y, r)
        P(3, 3, 1, "nw"); D(3.5, 0.5, 0.35, RED); D(1.25, 1.5, 0.25, PAPER); P(3, 3, 0.5, "nw", PAPER)


ROOMS = ["home", "listen", "watch", "games", "house", "files", "ask", "me", "control",
         "smart-home", "inbox", "space", "party"]


def banner(room):
    """A room's banner: 1200 × 160, its emblem as a running head at the top right, 64 × 48 on a
    16 px module, 14 px under the status rule and above the header's buttons (the title sits at
    the left; phones crop the banner to its quiet middle). Day: banner-<room>.svg, ink with paper
    cuts; night: banner-<room>-dark.svg, the true negative (a paper emblem, ink cuts)."""
    p = Pic(1200, 160, 16)
    emblem(p, room, (1200 - 28 - 8) / 16 - 4, 0.875)
    return p


# ------------------------------------------------------------------ the sign-in crest
def crest():
    """The house's emblem, 160 square on a 20 px grid (8 × 8): the hero's dome house and shed on
    their line. Day: black house under a black sun (crest.svg); night: grey house, lit windows,
    a crescent (crest-dark.svg)."""
    p = Pic(160, 160, 20)
    e = 0.03
    p.dot(5.9, 2.0, 1.3, PAPER).dot(6.5, 1.5, 1.15, INK)
    p.rect(1, 4.5 - e, 3.8, 3 + e, INK).pie(2.9, 4.5, 1.9, "n", INK)
    p.rect(1.5, 5, 0.9, 0.9, PAPER).rect(3.4, 5, 0.9, 0.9, PAPER)
    p.rect(2.4, 6.1, 1, 1.4, RED)
    p.rect(5.1, 6, 2.1, 1.5 + e, INK).pie(5.1, 6, 2.1, "ne", INK)
    p.dot(6.15, 6.75, 0.35, PAPER)
    p.rect(0.5, 7.5, 7.2, 0.12, RULE)
    return p


# ------------------------------------------------------------------ the empty state
def empty():
    """A module face with a quarter-circle smile, 96 square (a 4 × 4 grid of 24)."""
    p = Pic(96, 96, 24)
    p.rect(0.5, 0.5, 3, 3, INK)
    p.rect(1, 1.25, 0.5, 0.5, PAPER).rect(2.5, 1.25, 0.5, 0.5, PAPER)
    p.pie(2, 2.25, 0.75, "s", PAPER)
    p.dot(3.5, 0.5, 0.35, RED)
    return p


# ------------------------------------------------------------------ the rail's foot
def rail_foot(p=None, ways=None, red=(2, 3), ox=0.0):
    """A column of the programme at the rail's foot, 200 square on a 25.8 px grid: four rows of
    four modules, each turned a quarter further than its neighbour (a Gerstner permutation), the
    red one once. Ink blocks with paper quarters cut in, alternating with bare ink quarter
    rings: by night only the paper quarters remain. `ways` gives each cell's turn (the poke's
    shuffles), `red` the red cell; `ox` shifts the drawing right by that many cells."""
    p = p or Pic(200, 200, 200 / 7.75)
    turn = ["ne", "se", "sw", "nw"]
    centre = {"ne": (0, 1), "se": (0, 0), "sw": (1, 0), "nw": (1, 1)}
    for row in range(4):
        for col in range(4):
            x, y = ox + 0.5 + col * 1.75, 0.5 + row * 1.75
            way = turn[ways[row][col] if ways else (row + col) % 4]
            cx, cy = centre[way]
            if (row, col) == red:
                p.pie(x + cx * 1.5, y + cy * 1.5, 1.5, way, RED)
                continue
            if (row + col) % 2:  # every other cell a bare quarter ring: the programme breathes
                p.pie(x + cx * 1.5, y + cy * 1.5, 1.5, way, INK, r=0.5)
                p.pie(x + cx * 1.5, y + cy * 1.5, 0.5, way, PAPER)
                continue
            rad = 1.5 if row % 2 == 0 else 0.75
            p.cut(x, y, 1.5, 1.5, INK, x + cx * 1.5, y + cy * 1.5, rad, way)
            p.pie(x + cx * 1.5, y + cy * 1.5, rad, way, PAPER)
    return p


SHUFFLES = 10


def rail_foot_shuffle():
    """The rail foot's poke: ten new arrangements of the same sixteen modules (each cell a random
    quarter turn, the red quarter in a new cell), played as a quick shuffle; the grid stays on
    one of them at random (poke stay: random). Ten frames of 200 × 200 side by side."""
    import random
    rnd = random.Random(16)
    p = Pic(200 * SHUFFLES, 200, 200 / 7.75)
    seen = set()
    for f_ in range(SHUFFLES):
        while True:
            ways = tuple(tuple(rnd.randrange(4) for _ in range(4)) for _ in range(4))
            red = (rnd.randrange(4), rnd.randrange(4))
            if (ways, red) not in seen:
                seen.add((ways, red))
                break
        rail_foot(p, ways=ways, red=red, ox=f_ * 7.75)
    return p


# ------------------------------------------------------------------ My Space
def space_room():
    """The person's room, 480 × 216 on a 24 px grid (20 × 9; the slot is 160 × 72), everything
    in the middle 60 % (x 4–16) so a phone's crop keeps it: a wall and a floor line, a window
    (the sun's sky by day, a moon in it by night), a framed module on the wall, a floor lamp,
    a chair (square seat, quarter-circle back) and the red rug on the floor.
    Day: space-room.svg; night: space-room-dark.svg (the lamp's bulb and the moon light up)."""
    p = Pic(480, 216, 24)
    e = 0.03
    F = 7  # the floor line
    p.rect(3, F, 14, 0.14, RULE)
    # the window: an ink frame, four panes of sky; a moon in the sky (paper: night only)
    p.rect(4.5, 1.5, 3.5, 3.5, INK)
    for x in (4.85, 6.4):
        for y in (1.85, 3.4):
            p.rect(x, y, 1.25, 1.25, SKY)
    p.dot(7, 2.35, 0.4, PAPER).dot(7.2, 2.2, 0.35, SKY)
    # a poster on the wall: an ink sheet with a paper disc and a quarter cut from it
    p.rect(9.25, 1.75, 1.75, 2.5, INK).dot(10.125, 2.75, 0.55, PAPER).pie(9.25, 4.25, 0.9, "ne", PAPER)
    # the chair: a quarter-circle back, a square seat, two legs
    p.pie(12, 5.2, 1.7, "ne", INK).rect(12 - e, 5.2, 2.2, 0.6, INK)
    p.rect(12, 5.8 - e, 0.35, F - 0.3 - 5.8 + e, INK).rect(13.85, 5.8 - e, 0.35, F - 0.3 - 5.8 + e, INK)
    # the floor lamp: a half-circle shade, its bulb (paper: lit at night), a pole, a foot
    p.pie(15.5, 2.3, 1.1, "n", INK).rect(15.4, 2.3 - e, 0.2, F - 2.3, INK).rect(14.9, F - 0.2, 1.2, 0.2, INK)
    p.pie(15.5, 2.3, 0.45, "s", PAPER)
    # the red rug, lying on the floor under the chair
    p.rect(10.2, F - 0.3, 4.4, 0.3, RED)
    return p


# ------------------------------------------------------------------ the TV bezel
def tv_bezel():
    """The frame around the TV picture: 480 × 360, a module-thick frame on a 24 px grid with a
    paper hairline inside and a red standby dot. Day: an ink frame; night (tv-bezel-dark.svg):
    a grey frame, the hairline lit."""
    p = Pic(480, 360, 24)
    t = 1  # frame thickness in modules
    p.rect(0, 0, 20, t, INK).rect(0, 15 - t, 20, t, INK).rect(0, 0, t, 15, INK).rect(20 - t, 0, t, 15, INK)
    p.rect(t - 0.125, t - 0.125, 20 - 2 * t + 0.25, 0.08, PAPER)
    p.rect(t - 0.125, 15 - t + 0.045, 20 - 2 * t + 0.25, 0.08, PAPER)
    p.rect(t - 0.125, t - 0.125, 0.08, 15 - 2 * t + 0.25, PAPER)
    p.rect(20 - t + 0.045, t - 0.125, 0.08, 15 - 2 * t + 0.25, PAPER)
    p.dot(18.5, 14.5, 0.22, RED)
    return p


# ------------------------------------------------------------------ the music deck's skin
def deck_frame():
    """The deck as a poster: a 9-slice frame (48 × 48, corners 16): a 1 px ink rule round it, a
    black head band along the top and one red square at its start. Day: deck.svg; night
    (deck-dark.svg): the negative, a paper frame and band."""
    p = Pic(48, 48)
    p.rect(0, 0, 48, 1, INK).rect(0, 47, 48, 1, INK).rect(0, 0, 1, 48, INK).rect(47, 0, 1, 48, INK)
    p.rect(0, 0, 48, 6, INK)
    return p


def deck_module(frame=0):
    """The deck's red module (a layer piece in its top-left corner, 16 × 16): a square."""
    return Pic(16, 16).rect(0, 0, 16, 16, RED)


def deck_module_flip():
    """Its poke: the module runs through the programme, quarter → half → dot → quarter → half →
    square (6 frames of 16 × 16), and stays as one of them at random (poke stay: random)."""
    p = Pic(96, 16)
    p.pie(0, 0, 16, "se", RED)          # a quarter, hinged at the corner
    p.pie(24, 0, 8, "s", RED)           # a half, hanging from the band
    p.dot(40, 8, 8, RED)                # a dot: the module edge-on
    p.pie(64, 0, 16, "sw", RED)         # the quarter, hinged the other way
    p.pie(80, 8, 8, "w", RED)           # a half, flat edge to the right
    p.rect(80, 0, 16, 16, RED)          # the square again
    return p


# ------------------------------------------------------------------ little movers (layers)
def spectrum():
    """While music plays, a dot-matrix level meter runs along the deck's foot (inside its
    padding): a 96 × 10 tile of red square dots, columns one or two high, drifting sideways."""
    import random
    rnd = random.Random(7)
    p = Pic(96, 10)
    for i in range(16):
        h = rnd.choice((1, 1, 2, 2, 2, 1))
        for k in range(h):
            p.rect(i * 6 + 1, 10 - 5 * (k + 1) + 1, 4, 4, RED)
    return p


def ruler():
    """The status bar as a ruler: one tick dot per 24 px module along its foot (24 × 48 tile)."""
    return Pic(24, 48).dot(12, 43, 1.25, GREY)


def walker():
    """The red module that walks the status bar's ruler now and then (12 × 48, dot on the line)."""
    return Pic(12, 48).rect(2, 39, 8, 8, RED)


# ------------------------------------------------------------------ pixel pieces (sprites.json)
# The same programme at 16 × 16: one pixel is one module unit. k = ink, p = paper, e = red; the
# scheme swaps ink and paper, so every piece is its own negative in the dark.
class Grid:
    def __init__(self, w=16, h=16):
        self.w, self.h = w, h
        self.px = [["."] * w for _ in range(h)]

    def put(self, x, y, ch):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = ch

    def rect(self, x, y, w, h, ch="k"):
        for j in range(y, y + h):
            for i in range(x, x + w):
                self.put(i, j, ch)
        return self

    def disc(self, cx, cy, r, ch="k", way="o"):
        """Pixels whose centres fall in the circle (cx, cy, r), limited to a quadrant/half."""
        for j in range(self.h):
            for i in range(self.w):
                dx, dy = i + 0.5 - cx, j + 0.5 - cy
                if dx * dx + dy * dy > r * r + 0.01:
                    continue
                ok = {"o": True, "ne": dx >= 0 and dy <= 0, "nw": dx <= 0 and dy <= 0,
                      "se": dx >= 0 and dy >= 0, "sw": dx <= 0 and dy >= 0,
                      "n": dy <= 0, "s": dy >= 0, "e": dx >= 0, "w": dx <= 0}[way]
                if ok:
                    self.put(i, j, ch)
        return self

    def rows(self):
        return ["".join(r) for r in self.px]


def nox(mood):
    g = Grid()
    g.disc(2, 6, 4, "k", "ne").disc(14, 6, 4, "k", "nw")  # quarter-circle ears
    g.rect(2, 6, 12, 9)
    if mood == "listening":
        g.disc(2, 6, 4, "e", "ne")
    eyes = {
        "idle": lambda: g.rect(5, 9, 2, 2, "p").rect(9, 9, 2, 2, "p"),
        "blink": lambda: g.rect(5, 10, 2, 1, "p").rect(9, 10, 2, 1, "p"),  # the module flips edge-on
        "listening": lambda: g.rect(5, 8, 2, 2, "p").rect(9, 8, 2, 2, "p"),
        "thinking": lambda: g.rect(6, 8, 2, 2, "p").rect(10, 8, 2, 2, "p").rect(13, 1, 2, 2, "e"),
        "happy": lambda: [g.put(x, y, "p") for x, y in ((5, 10), (6, 9), (7, 10), (9, 10), (10, 9), (11, 10))],
        "error": lambda: g.rect(5, 9, 2, 2, "e").rect(9, 9, 2, 2, "e"),
    }
    eyes[mood]()
    if mood == "happy":
        g.rect(4, 12, 1, 1, "e").rect(11, 12, 1, 1, "e")
    if mood in ("idle", "blink"):
        g.rect(7, 13, 2, 1, "p")
    return g.rows()


def avatar(kind):
    g = Grid()
    if kind == "moon":  # a crescent from two equal circles, a red star square
        g.disc(8, 8, 7).disc(11, 8, 6.5, ".").rect(12, 2, 2, 2, "e")
    elif kind == "bat":  # a square body, two quarter-disc wings, square ears, red eyes
        g.disc(6, 5, 6, "k", "sw").disc(10, 5, 6, "k", "se").rect(6, 3, 4, 9)
        g.rect(6, 1, 1, 2).rect(9, 1, 1, 2).rect(7, 5, 1, 1, "e").rect(8, 5, 1, 1, "e")
        for x in (2, 13):
            g.disc(x, 11.5, 1.6, ".")
    elif kind == "raven":  # a half-disc body, a round head, a red quarter beak, a square tail
        g.disc(8, 14, 6, "k", "n").disc(10, 6, 3).disc(13, 6, 3, "e", "se").rect(0, 11, 3, 3)
        g.rect(10, 5, 1, 1, "p").rect(6, 14, 1, 2).rect(9, 14, 1, 2)
    elif kind == "rose":  # four quarter petals opening from a red heart, a stem, a quarter leaf
        for cx, cy, way in ((7, 6, "nw"), (9, 6, "ne"), (7, 8, "sw"), (9, 8, "se")):
            g.disc(cx, cy, 4.5, "k", way)
        g.rect(7, 6, 2, 2, "e").rect(7, 12, 2, 4).disc(7, 15, 3, "k", "nw")
    elif kind == "ghost":
        g.disc(8, 7, 6, "k", "n").rect(2, 7, 12, 7)
        for x in (3.5, 8, 12.5):
            g.disc(x, 15, 1.6, ".")
        g.rect(5, 6, 2, 2, "p").rect(9, 6, 2, 2, "p").rect(7, 10, 2, 1, "e")
    return g.rows()


def room_mark(room):
    g = Grid()
    if room == "home":
        g.rect(10, 1, 3, 5).disc(8, 8, 7, "k", "n").rect(1, 8, 14, 8)
        g.rect(7, 10, 3, 6, "p").rect(3, 10, 2, 2, "p").rect(12, 10, 2, 2, "e")
    elif room == "listen":
        g.disc(1, 15, 14, "k", "ne").disc(1, 15, 11, "p", "ne").disc(1, 15, 8, "k", "ne").disc(1, 15, 5, "p", "ne")
        g.disc(1, 15, 3, "e", "ne")
    elif room == "watch":
        g.rect(0, 2, 16, 11).rect(2, 4, 12, 7, "p").rect(7, 13, 2, 2).rect(4, 15, 8, 1)
        g.rect(11, 8, 2, 2, "e")
    elif room == "house":
        for i, y in enumerate((1, 6, 11)):
            g.rect(0, y, 4, 4, "e" if i == 0 else "k")
            if i:
                g.rect(1, y + 1, 2, 2, "p")
            g.rect(6, y + 1, 10 - 3 * i, 2)
    elif room == "files":
        g.rect(0, 2, 7, 3).disc(7, 5, 3, "k", "ne").rect(0, 5, 16, 10).rect(2, 7, 12, 1, "p")
    elif room == "smart-home":
        # a bulb: a round glass, a red filament, a neck and a threaded base in bars
        g.disc(8, 6, 5.5).rect(5, 9, 6, 3).rect(6, 5, 1, 4, "p").rect(9, 5, 1, 4, "p").rect(6, 5, 4, 1, "e")
        g.rect(5, 12, 6, 1, ".").rect(5, 13, 6, 1).rect(6, 14, 4, 1, ".").rect(6, 15, 4, 1)
    elif room == "games":
        g.rect(5, 1, 6, 14).rect(1, 5, 14, 6).rect(7, 7, 2, 2, "p").rect(12, 7, 2, 2, "e")
        g.rect(12, 1, 3, 3, "."); g.rect(1, 1, 3, 3, ".")
    elif room == "more":
        for x in (1, 6.5, 12):
            pass
        g.rect(0, 6, 4, 4).rect(6, 6, 4, 4).rect(12, 6, 4, 4, "e")
    elif room == "me":
        g.disc(8, 4.5, 3.5).disc(8, 16, 7.5, "k", "n").disc(8, 16, 3, "p", "n")
    return g.rows()


MEDAL = {  # each medal is an ink tile with its motif cut in paper, and the red module once
    "dj": lambda g: g.disc(8, 8, 6, "p").disc(8, 8, 3, "k").disc(8, 8, 1.5, "e"),
    "explorer": lambda g: g.disc(8, 8, 6, "p", "ne").disc(8, 8, 6, "p", "sw").rect(7, 7, 2, 2, "e"),
    "night_owl": lambda g: g.disc(5, 7, 3, "p").disc(11, 7, 3, "p").rect(4, 6, 2, 2).rect(10, 6, 2, 2).rect(7, 10, 2, 3, "e"),
    "early_bird": lambda g: g.disc(8, 14, 6, "p", "n").rect(7, 2, 2, 2, "e"),
    "weekend": lambda g: g.rect(2, 4, 5, 8, "p").rect(9, 4, 5, 8, "p").rect(10, 5, 3, 3, "e"),
    "genre_guardian": lambda g: g.rect(3, 2, 10, 6, "p").disc(8, 8, 5, "p", "s").disc(8, 7, 1.6, "e"),
    "broken_record": lambda g: g.disc(7, 8, 6, "p", "w").disc(9, 8, 6, "p", "e").rect(7, 1, 2, 14).disc(8, 8, 1.5, "e"),
    "marathon": lambda g: g.disc(8, 8, 6.5, "p").disc(8, 8, 4.5, "k").rect(12, 3, 2, 2, "e"),
    "radio_host": lambda g: g.disc(2, 14, 12, "p", "ne").disc(2, 14, 9, "k", "ne").disc(2, 14, 6, "p", "ne").disc(2, 14, 3, "e", "ne"),
    "task_hero": lambda g: [g.rect(x, y, 2, 2, "p") for x, y in ((2, 8), (4, 10), (6, 12), (8, 10), (10, 8), (12, 6))] and g.rect(12, 2, 2, 2, "e"),
    "grocery_runner": lambda g: g.disc(8, 7, 6, "p", "s").rect(2, 5, 12, 2, "p").disc(5, 4, 1.6, "e").disc(10, 3.5, 1.6, "p"),
    "planner": lambda g: [g.rect(2 + i * 4, 2 + j * 4, 3, 3, "e" if (i, j) == (2, 1) else "p") for i in range(3) for j in range(3)],
    "wall_poet": lambda g: g.rect(2, 3, 12, 2, "p").rect(2, 7, 8, 2, "p").rect(2, 11, 10, 2, "p").rect(12, 7, 2, 2, "e"),
    "courier": lambda g: g.rect(1, 4, 14, 9, "p").disc(1, 4, 7, "k", "se").disc(15, 4, 7, "k", "sw").disc(8, 10, 1.6, "e"),
    "curator": lambda g: g.rect(2, 2, 12, 12, "p").rect(4, 4, 8, 8, "k").disc(8, 8, 2, "e"),
    "high_scorer": lambda g: g.rect(2, 10, 3, 4, "p").rect(6, 7, 3, 7, "p").rect(10, 4, 3, 10, "p").rect(10, 2, 3, 2, "e"),
    "collector": lambda g: g.disc(5, 5, 2.5, "p").disc(11, 5, 2.5, "p").disc(5, 11, 2.5, "p").disc(11, 11, 2.5, "e"),
    "game_hopper": lambda g: g.rect(6, 2, 4, 12, "p").rect(2, 6, 12, 4, "p").rect(7, 7, 2, 2, "e"),
    "console_hopper": lambda g: g.rect(1, 3, 8, 6, "p").rect(7, 7, 8, 6, "p").rect(8, 8, 6, 4, "k").rect(10, 9, 2, 2, "e"),
    "romhacker": lambda g: [g.rect(2 + i * 3, 2 + j * 3, 2, 2, "e" if (i, j) == (3, 0) else ("k" if (i, j) == (1, 2) else "p")) for i in range(4) for j in range(4)],
}


def medal(name):
    g = Grid().rect(0, 0, 16, 16)
    MEDAL[name](g)
    return g.rows()


def contour(rows):
    """A paper contour round a mark (the empty pixels touching it): paper on the paper rail, it
    vanishes; on the current room's ink block it draws the mark in line, so it never sinks."""
    h, w = len(rows), len(rows[0])
    out = [list(r) for r in rows]
    for y in range(h):
        for x in range(w):
            if rows[y][x] == "." and any(
                0 <= x + dx < w and 0 <= y + dy < h and rows[y + dy][x + dx] in "ke"
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                out[y][x] = "p"
    return ["".join(r) for r in out]


def sprites():
    glyphs = {}
    for mood in ("idle", "blink", "listening", "thinking", "happy", "error"):
        glyphs[f"nox.{mood}"] = nox(mood)
    for kind in ("moon", "bat", "raven", "rose", "ghost"):
        glyphs[f"avatar.{kind}"] = avatar(kind)
    for room in ("home", "listen", "watch", "house", "files", "smart-home", "games", "more", "me"):
        glyphs[f"room.{room}"] = contour(room_mark(room))
    for name in MEDAL:
        glyphs[f"title.{name}"] = medal(name)
    return {"$description": "Modular's pieces: the module programme at 16 x 16. k ink, p paper, e red; "
                            "the scheme swaps ink and paper, so each piece is its own negative in the dark.",
            "palette": {"k": "ink", "p": "paper", "e": "accent"}, "glyphs": glyphs}


def sprite_sheet(data, out):
    from PIL import Image, ImageDraw
    names = list(data["glyphs"])
    cols, z, pad = 10, 6, 8
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (16 * z + pad) * 2 + pad, rows * (16 * z + pad) + pad), "#777")
    colours = {"k": [INK, PAPER], "p": [PAPER, INK], "e": [RED, RED]}
    for n, name in enumerate(names):
        r, c = divmod(n, cols)
        for side in (0, 1):
            x0 = pad + side * cols * (16 * z + pad) + c * (16 * z + pad)
            y0 = pad + r * (16 * z + pad)
            d = ImageDraw.Draw(sheet)
            d.rectangle([x0, y0, x0 + 16 * z - 1, y0 + 16 * z - 1], fill=[PAPER, INK][side])
            for j, row in enumerate(data["glyphs"][name]):
                for i, ch in enumerate(row):
                    if ch != ".":
                        d.rectangle([x0 + i * z, y0 + j * z, x0 + i * z + z - 1, y0 + j * z + z - 1], fill=colours[ch][side])
    sheet.save(out)
    return out


# name: (drawing, preview sizes, variants). One variant: "both" (one file for both schemes).
# Two: the light file is <name>.svg, the dark one <name>-dark.svg.
PIECES = {
    "hero.svg": (hero, [(660, 220, "right", 0.4), (358, 119, "down", 0.55)], ("light", "night")),
    "crest.svg": (crest, [(160, 160, None, 0)], ("light", "night")),
    "space-room.svg": (space_room, [(480, 216, None, 0)], ("light", "night")),
    "tv-bezel.svg": (tv_bezel, [(480, 360, None, 0)], ("light", "night")),
    "empty.svg": (empty, [(96, 96, None, 0)], ("light", "neg")),
    "deck.svg": (deck_frame, [(320, 200, None, 0)], ("light", "neg")),
    "spectrum.svg": (spectrum, [], ("both",)),
    "grid.svg": (grid, [(96, 96, None, 0)], ("both",)),
    "ruler.svg": (ruler, [], ("both",)),
    "walker.svg": (walker, [], ("both",)),
    "rail-foot.svg": (rail_foot, [(200, 200, None, 0)], ("both",)),
    "rail-foot-shuffle.svg": (rail_foot_shuffle, [(2000, 200, None, 0)], ("both",)),
    "deck-module.svg": (deck_module, [], ("light", "neg")),
    "deck-module-flip.svg": (deck_module_flip, [(400, 80, None, 0)], ("light", "neg")),
    **{f"banner-{r}.svg": ((lambda r=r: banner(r)), [(1200, 160, None, 0)], ("light", "neg")) for r in ROOMS},
}

if __name__ == "__main__":
    ART.mkdir(parents=True, exist_ok=True)
    import json
    data = sprites()
    target = ROOT / "themes" / "modular" / "sprites.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n")
    os.replace(tmp, target)
    print("made themes/modular/sprites.json,", len(data["glyphs"]), "pieces")
    if "--preview" in sys.argv:
        SCRATCH.mkdir(parents=True, exist_ok=True)
        print("  preview", sprite_sheet(data, SCRATCH / "sprites.png"))
    for name, (make, views, variants) in PIECES.items():
        pic = make()
        outs = []
        for k, variant in enumerate(variants):
            outs.append(pic.save(name if k == 0 else name.replace(".svg", "-dark.svg"), variant))
            print("made", outs[-1].relative_to(ROOT), outs[-1].stat().st_size, "bytes")
        if "--preview" in sys.argv:
            for i, (w, h, way, start) in enumerate(views):
                print("  preview", on_grounds(outs, w, h, f"{Path(name).stem}-{i}", way and fade(way, start)))
    if "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        contact(sys.argv[i + 1] if len(sys.argv) > i + 1 else "/tmp/modular-sheet.png")
