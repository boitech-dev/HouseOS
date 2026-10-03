"""Bathhouse After Hours (sento-night): every picture of the theme, drawn by code.

    python3 docs/design/themes/sento-night/make.py            # everything
    python3 docs/design/themes/sento-night/make.py hero mural # some pieces

One palette (PAL below, locked on every picture), one light (warm lamps high on the left: tops
and left faces catch it, shadows fall right and down, toward teal), one pixel density: an art
pixel is 4 screen pixels on a desktop (pictures are drawn at the size that makes it so; layers at
scale 4). Pictures are text grids for objects and code for the big paintings. No words, no
letters, no numerals in any picture; the ♨ mark is a pictogram.
"""

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "themes/sento-night/art"
sys.path.insert(0, str(ROOT / "themes/_kit/art"))
from pixel import BAYER, Palette, save  # noqa: E402

# ---------------------------------------------------------------- the palette (one, locked)
# Each ramp hue-shifts: shadows lean teal-blue, lights lean warm (the lamps).
PAL = {
    # tile: the wet mosaic, night teal (ground, grout, glaze)
    "0": "#061015", "1": "#0b1d24", "2": "#102a33", "3": "#173a44", "4": "#1f4d57",
    "5": "#2b646c", "6": "#3f8285", "7": "#62a3a0", "8": "#93c7bf", "9": "#cfe8e0",
    # the mural's blues: sky, sea, the mountain (A deepest … H snow)
    "A": "#0d1433", "B": "#16245a", "C": "#22397f", "D": "#3156a6", "E": "#4d7cc4",
    "F": "#7ea6dc", "G": "#b3cdee", "H": "#e6eef6",
    # vermilion: the noren, the sun, lacquer (u deepest … z lightest)
    "u": "#3a0d0b", "v": "#6e1c14", "w": "#a8321f", "x": "#dd4f33", "y": "#f07e58", "z": "#ffb58f",
    # hinoki and dark wood, up to milk cream (a … h)
    "a": "#1c0f09", "b": "#36200f", "c": "#573417", "d": "#7d4f24", "e": "#a8743a",
    "f": "#cf9f5c", "g": "#ebc98c", "h": "#f8e6bb",
    # the yellow basins
    "i": "#6b4a08", "j": "#b88a12", "k": "#eab82a", "l": "#ffe070",
    # pine
    "p": "#0c2418", "q": "#1b3f28", "r": "#2f6038", "s": "#4f8a4a",
    # plum (a yukata, the dusk in the mural)
    "M": "#2e1733", "N": "#5a2f63", "O": "#9a5a9e",
    # ginger (the cat), white
    "o": "#e0913f", "W": "#fffaf0",
}
LOCK = Palette(**{f"c{k}": v for k, v in PAL.items()})


def rgb(ch):
    h = PAL[ch].lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


CLEAR = (0, 0, 0, 0)


def new(w, h, ch=None):
    return Image.new("RGBA", (w, h), rgb(ch) if ch else CLEAR)


def put(im, x, y, ch):
    if 0 <= x < im.width and 0 <= y < im.height:
        im.putpixel((x, y), rgb(ch) if ch else CLEAR)


def get(im, x, y):
    return im.getpixel((x, y))


def rect(im, x0, y0, x1, y1, ch):
    """Filled, x1/y1 exclusive."""
    for y in range(max(0, y0), min(im.height, y1)):
        for x in range(max(0, x0), min(im.width, x1)):
            im.putpixel((x, y), rgb(ch))


def hline(im, x0, x1, y, ch):
    rect(im, x0, y, x1, y + 1, ch)


def vline(im, x, y0, y1, ch):
    rect(im, x, y0, x + 1, y1, ch)


def dith(t, x, y):
    """True where an ordered dither of strength t (0–1) lights this pixel."""
    return t * 16 > BAYER[y % 4][x % 4] + 0.5


def grid(rows, legend=None):
    """A sprite from text rows in the palette's letters ('.' clear); legend remaps letters."""
    w = max(len(r) for r in rows)
    im = new(w, len(rows))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch not in ". ":
                im.putpixel((x, y), rgb((legend or {}).get(ch, ch)))
    return im


def stamp(im, sprite, x, y, flip=False):
    if isinstance(sprite, list):
        sprite = grid(sprite)
    if flip:
        sprite = sprite.transpose(Image.FLIP_LEFT_RIGHT)
    im.alpha_composite(sprite, (x, y))


def poly(im, pts, ch):
    ImageDraw.Draw(im).polygon(pts, fill=rgb(ch))


def ellipse(im, box, ch):
    ImageDraw.Draw(im).ellipse(box, fill=rgb(ch))


def line(im, pts, ch):
    ImageDraw.Draw(im).line(pts, fill=rgb(ch), width=1)


def mask_of(im):
    return [[im.getpixel((x, y))[3] > 0 for x in range(im.width)] for y in range(im.height)]


def outline(sprite, ch="0"):
    """A 1px outline around the opaque shape (grows the picture by 1 on each side)."""
    out = new(sprite.width + 2, sprite.height + 2)
    out.alpha_composite(sprite, (1, 1))
    m = mask_of(out)
    for y in range(out.height):
        for x in range(out.width):
            if m[y][x]:
                continue
            if any(0 <= x + dx < out.width and 0 <= y + dy < out.height and m[y + dy][x + dx]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out.putpixel((x, y), rgb(ch))
    return out


def scale(im, n):
    return im.resize((im.width * n, im.height * n), Image.NEAREST)


def done(im, name, n=1):
    """Lock to the palette, scale by a whole number, save."""
    LOCK.lock(im, name)
    path = save(scale(im, n) if n > 1 else im, ART / name)
    print(f"{name:28} {im.width * n}×{im.height * n}  {path.stat().st_size / 1024:.1f} KB")
    return im


def recolour(im, mapping):
    """Swap palette letters (a lamp's colour on an object, a darker copy for a shadow)."""
    table = {rgb(a)[:3]: rgb(b) for a, b in mapping.items()}
    out = im.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            p = px[x, y]
            if p[3] and p[:3] in table:
                px[x, y] = table[p[:3]]
    return out


# ---------------------------------------------------------------- shared motifs


def mosaic(im, box, face, grout, size=3, hi=None, lo=None, seed=1, glint=0.0, chips=None):
    """Small square tiles (size-1 px of glaze, 1 px of grout): the sentō's wet wall. hi/lo: a
    lit top-left pixel and a shaded bottom-right one per tile; chips: odd tiles in another glaze."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        for x in range(x0, x1):
            gx, gy = (x - x0) % size, (y - y0) % size
            ch = grout if gx == size - 1 or gy == size - 1 else face
            put(im, x, y, ch)
    for ty in range(y0, y1, size):
        for tx in range(x0, x1, size):
            if chips and rnd.random() < chips[1]:
                rect(im, tx, ty, min(tx + size - 1, x1), min(ty + size - 1, y1), chips[0])
            if hi and size > 2 and rnd.random() < 0.85:
                put(im, tx, ty, hi)
            if lo and size > 3:
                put(im, tx + size - 2, ty + size - 2, lo)
            if glint and rnd.random() < glint:
                put(im, tx, ty, "9")


def seigaiha(im, box, fg, bg, r=4, lit=None):
    """The overlapping-wave pattern (concentric arcs), as the tile band and the painted sea."""
    x0, y0, x1, y1 = box
    rect(im, x0, y0, x1, y1, bg)
    for row, cy in enumerate(range(y1 + r, y0 - r, -r)):
        off = (r if row % 2 else 0)
        for cx in range(x0 - 2 * r + off, x1 + 2 * r, 2 * r):
            for y in range(cy - r, cy + 1):
                for x in range(cx - r, cx + r + 1):
                    if not (x0 <= x < x1 and y0 <= y < y1):
                        continue
                    d = math.hypot(x - cx, y - cy)
                    if d <= r + 0.3:
                        ring = int(d + 0.5)
                        ch = fg if ring % 2 == 1 or ring == r else bg
                        if lit and ring == r and y < cy - r + 2:
                            ch = lit
                        put(im, x, y, ch)


def steam_band(im, box, ch, strength, seed=3, wisps=6):
    """Dithered vapour: soft horizontal wisps (the only way steam is drawn: ordered dither)."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    blobs = [(rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(18, 48), rnd.uniform(3, 7))
             for _ in range(wisps)]
    for y in range(y0, y1):
        for x in range(x0, x1):
            t = 0.0
            for bx, by, rx, ry in blobs:
                d = ((x - bx) / rx) ** 2 + ((y - by) / ry) ** 2
                t = max(t, 1 - d)
            if t > 0 and dith(min(1, t) * strength, x, y):
                put(im, x, y, ch)


def painted_sea(im, box, deep="D", crest="F", foam="H", seed=5):
    """The mural's sea: deep blue with rows of small curling crests, sparser far out."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    rect(im, x0, y0, x1, y1, deep)
    for row, y in enumerate(range(y0 + 1, y1, 2)):
        step = 6 + max(0, 3 - row)
        off = rnd.randrange(step)
        for x in range(x0 + off, x1, step):
            put(im, x, y, crest)
            put(im, x + 1, y, crest)
            if row > 0:
                put(im, x + 2, y - 1, foam)


def veil(im, x, y, length, ch, rise=0):
    """A drawn wisp of steam: a thin flat stroke, two pixels thick in the middle, its ends
    frayed with a dither; rise tilts it up to the right (steam drifting)."""
    for i in range(length):
        t = i / max(1, length - 1)
        yy = y - int(round(rise * t))
        edge = min(t, 1 - t) * length
        if edge < 2:
            if (i + yy) % 2 == 0:
                put(im, x + i, yy, ch)
        else:
            put(im, x + i, yy, ch)
            if 0.2 < t < 0.8:
                put(im, x + i, yy - 1, ch)


ONSEN_S = [  # ♨ drawn by hand for small sizes (11 × 16): three S lines rising out of an open bowl
    "..h..h..h..",
    ".h..h..h...",
    ".h..h..h...",
    "..h..h..h..",
    "...h..h..h.",
    "...h..h..h.",
    "..h..h..h..",
    ".h..h..h...",
    "h.h..h..h.h",
    "h.........h",
    "h.........h",
    "h.........h",
    ".h.......h.",
    ".h.......h.",
    "..hh...hh..",
    "....hhh....",
]


def onsen_mark(r=4.5, ch="h", thick=1, spacing=0.5):
    """♨ as a pictogram: an open bowl (a ring with a gap at the top) and three wavy S lines rising
    from its middle out through the gap. r is the bowl's radius."""
    rise = 2.4 * r
    w = int(2 * r + 3)
    h = int(rise + r + 3)
    im = new(w, h)
    cx, cy = (w - 1) / 2, h - r - 1.5
    for y in range(h):
        for x in range(w):
            d = math.hypot(x - cx, y - cy)
            ang = math.degrees(math.atan2(y - cy, x - cx))  # -90 is straight up
            if r - 0.5 - 0.5 * thick <= d <= r + 0.5 and not (-150 < ang < -30):
                put(im, x, y, ch)
    y0, y1 = int(round(cy - rise)), int(round(cy)) - 1
    for lx in (cx - r * spacing - thick / 2 + 0.5, cx - thick / 2 + 0.5, cx + r * spacing - thick / 2 + 0.5):
        for y in range(y0, y1 + 1):
            t = (y - y0) / max(1, y1 - y0)
            x = int(round(lx + 0.75 * math.sin(t * 2 * math.pi)))
            for k in range(thick):
                put(im, x + k, y, ch)
    return im


CAT_SLEEP = [  # a calico curled asleep, eyes shut, tail wrapped along the front (13 × 8)
    ".0.0.........",
    "0h0h0.00000..",
    "0hhhh0hoooh0.",
    "0h00h0hoo11h0",
    "0hhhhhhhhh1h0",
    ".0hhhhhhhhhh0",
    "..0ooooooooo0",
    "...000000000.",
]
MILK = ["0hh0", "0WW0", "0hh0", "0hh0"]  # a coffee-milk bottle, cap on


# ---------------------------------------------------------------- the mural (penki-e)


def fuji(im, cx, peak, base_y, half, snow_frac=0.42, ramp=("C", "D", "E"),
         snow=("H", "G", "F"), seed=2, crest=None):
    """The mountain: a short flat summit, concave flanks (steep high, flaring low), the lit left
    flank a step lighter, the snow cap reaching down in ridges of different lengths."""
    rnd = random.Random(seed)
    crest = crest or max(2, half // 10)
    height = base_y - peak

    def width(y):
        t = (y - peak) / height
        return crest + (half - crest) * (t ** 1.55)

    for y in range(peak, base_y):
        w = width(y)
        for x in range(int(round(cx - w)), int(round(cx + w)) + 1):
            u = (x - cx) / max(1.0, w)  # -1 left edge … 1 right edge
            ch = ramp[2] if u < -0.55 else ramp[1] if u < 0.05 else ramp[0]
            put(im, x, y, ch)
    # snow: ridge fingers, long and short alternating, a little random
    n = 13
    ends = []
    for i in range(n):
        u = i / (n - 1) * 2 - 1
        long = 1.0 if i % 2 == 0 else 0.72
        ends.append(peak + height * snow_frac * long * (1 - 0.25 * abs(u)) + rnd.uniform(-1.5, 1.5))
    for y in range(peak, int(max(ends)) + 1):
        w = width(y)
        for x in range(int(round(cx - w)), int(round(cx + w)) + 1):
            u = (x - cx) / max(1.0, w)
            f = (u + 1) / 2 * (n - 1)
            i0 = min(n - 1, max(0, int(f)))
            i1 = min(n - 1, i0 + 1)
            e = ends[i0] + (ends[i1] - ends[i0]) * (f - i0)
            if y <= e:
                ch = snow[0] if u < -0.1 else snow[1] if u < 0.5 else snow[2]
                if y > e - 1.2 and u > -0.1:
                    ch = snow[2]
                put(im, x, y, ch)
    for dx in range(-crest, crest + 1, 2):
        put(im, cx + dx, peak, snow[1])


def pine(im, x, y, h, flip=False, seed=5, spread=1.0):
    """A windswept black pine: a leaning, kinked red-brown trunk and flat cloud-shaped needle
    pads, dark below, lit along their upper-left edge (the lamp is up left)."""
    rnd = random.Random(seed)
    s = -1 if flip else 1
    # the trunk: leans away, kinks twice
    pts, tx, ty = [], float(x), float(y)
    for i in range(h):
        pts.append((int(round(tx)), int(round(ty))))
        ty -= 1
        tx += s * (0.55 if i < h * 0.4 else -0.2 if i < h * 0.7 else 0.6)
    for i, (px_, py) in enumerate(pts):
        thick = 3 if i < h * 0.35 else 2
        for d in range(thick):
            put(im, px_ + d * s * -1 if s < 0 else px_ + d, py, "d" if d == 0 else "c")
    # branches and pads
    tips = [pts[-1], pts[int(h * 0.62)], pts[int(h * 0.4)]]
    pads = [(tips[0][0] + s * 2, tips[0][1] - 1, int(9 * spread)),
            (tips[1][0] - s * int(7 * spread), tips[1][1] + 1, int(7 * spread)),
            (tips[1][0] + s * int(8 * spread), tips[1][1] - 2, int(6 * spread)),
            (tips[2][0] + s * int(10 * spread), tips[2][1] + 2, int(7 * spread)),
            (tips[0][0] - s * int(6 * spread), tips[0][1] + 3, int(5 * spread))]
    for (bx, by), (px_, py, _w) in zip([tips[0], tips[1], tips[1], tips[2], tips[0]], pads):
        line(im, [(bx, by), (px_, py + 1)], "c")
    for px_, py, w in pads:
        ry = max(2, w // 3)
        for yy in range(-ry, ry + 1):
            half = int(w * math.sqrt(max(0, 1 - (yy / (ry + 0.5)) ** 2)))
            for xx in range(-half, half + 1):
                ch = "q"
                if yy == ry or (yy == ry - 1 and rnd.random() < 0.4):
                    ch = "p"
                if yy <= -ry + 1:
                    ch = "r"
                    if xx < 0:
                        ch = "s"
                put(im, px_ + xx, py + yy, ch)
            if yy == ry:  # the needles' jagged underside
                for xx in range(-half, half + 1, 2):
                    put(im, px_ + xx, py + yy + 1, "p")


def boat(im, x, y):
    stamp(im, ["...h...", "...hh..", "...hhh.", "...hhhg", "...c...", "bdddddb", ".bbbbb."], x, y)


def crane_bird(im, x, y, ch="H"):
    stamp(im, grid([".H...H.", "..H.H..", "...H..."], {"H": ch}), x, y)


# ---------------------------------------------------------------- pictures


def page_mural():
    """page.backdrop, 400 × 225 (4 × on a 1440 × 900 window): the great Fuji mural up close,
    painted on big wall tiles, seen through steam; below it the wet mosaic wall and the bath.
    The part.page.scrim veils it: it is drawn a little brighter than it will look."""
    W, H = 400, 225
    im = new(W, H, "B")
    horizon = 134
    # sky: flat painted bands, dithered only where they meet
    bands = ["A", "B", "C", "D", "E"]
    for y in range(horizon):
        f = y / horizon * (len(bands) - 1)
        i = min(int(f), len(bands) - 2)
        edge = f - i
        for x in range(W):
            ch = bands[i + 1] if edge > 0.7 and dith((edge - 0.7) / 0.3, x, y) else bands[i]
            put(im, x, y, ch)
    # the sun, upper right, and the clouds across it
    ellipse(im, (326, 24, 356, 54), "w")
    ellipse(im, (328, 26, 354, 52), "x")
    for x, y in ((333, 30), (334, 30), (332, 31), (333, 31), (332, 32)):
        put(im, x, y, "y")
    for cx, cy, cw in ((340, 50, 70), (120, 40, 64), (60, 74, 40), (360, 92, 44), (172, 96, 30)):
        rect(im, cx - cw // 2, cy, cx + cw // 2, cy + 2, "E")
        hline(im, cx - cw // 2 + 5, cx + cw // 2 - 7, cy - 1, "F")
        hline(im, cx - cw // 2 + 9, cx + cw // 2 - 14, cy - 2, "G")
        hline(im, cx - cw // 2 + 4, cx + cw // 2 + 3, cy + 2, "D")
    # cranes flying home
    for bx, by, ch in ((150, 62, "G"), (162, 70, "F"), (141, 72, "F")):
        crane_bird(im, bx, by, ch)
    # the mountain, big, a little right of centre (a phone sees its middle)
    fuji(im, 222, 40, horizon + 3, 158, snow_frac=0.42, ramp=("C", "D", "E"),
         snow=("G", "F", "E"), seed=4, crest=9)
    # the foothills: rounded wooded shoulders, lit from the left
    for x in range(W):
        yy = horizon - 9 + int(round(3 * math.sin(x / 21) + 2 * math.sin(x / 8 + 1)))
        for y in range(yy, horizon + 4):
            put(im, x, y, "r" if y == yy else "q" if y < yy + 4 else "p")
        if x % 6 == 0:
            put(im, x, yy - 1, "q")
            put(im, x + 1, yy - 1, "r")
    # the rocky point, left, with its pines
    poly(im, [(0, horizon - 26), (26, horizon - 34), (58, horizon - 22), (88, horizon - 6),
              (104, horizon + 8), (0, horizon + 8)], "M")
    poly(im, [(0, horizon - 24), (24, horizon - 32), (40, horizon - 25), (22, horizon - 18),
              (0, horizon - 14)], "N")
    poly(im, [(40, horizon - 25), (58, horizon - 20), (80, horizon - 6), (60, horizon - 8)], "N")
    pine(im, 22, horizon - 30, 30, seed=3, spread=1.6)
    pine(im, 66, horizon - 20, 22, flip=True, seed=8, spread=1.2)
    # the sea: the painted wave-scale pattern, a sail far out
    seigaiha(im, (0, horizon + 4, W, 174), "D", "C", r=7, lit="E")
    boat(im, 300, horizon)
    # the big wall tiles the mural is painted on: a faint grid every 20 px
    for y in range(0, 174):
        for x in range(W):
            if x % 20 == 19 or y % 20 == 19:
                p = get(im, x, y)[:3]
                darker = {rgb(k)[:3]: d for k, d in (("E", "D"), ("D", "C"), ("C", "B"), ("B", "A"),
                          ("F", "E"), ("G", "F"), ("r", "q"), ("q", "p"), ("N", "M"),
                          ("x", "w"), ("y", "x"), ("s", "r"), ("d", "c"), ("c", "b"))}
                put(im, x, y, darker.get(p, "A"))
    # the mural's foot: a hinoki batten, the mosaic wall, the tub's rim, the water
    hline(im, 0, W, 174, "d")
    hline(im, 0, W, 175, "c")
    hline(im, 0, W, 176, "b")
    mosaic(im, (0, 177, W, 204), "4", "2", size=3, hi="5", seed=7, chips=("6", 0.05))
    rect(im, 0, 204, W, 208, "7")
    hline(im, 0, W, 204, "8")
    hline(im, 0, W, 207, "5")
    rect(im, 0, 208, W, H, "3")
    for x in range(0, W, 6):
        put(im, x + (x // 6) % 4, 211 + (x // 6) % 6, "5")
        put(im, x + 1 + (x // 6) % 4, 211 + (x // 6) % 6, "5")
    # steam: a veil over the water, another under the ceiling (the layers make it move)
    steam_band(im, (0, 186, W, 225), "6", 0.55, seed=11, wisps=9)
    steam_band(im, (0, 0, W, 40), "C", 0.5, seed=12, wisps=7)
    return done(im, "page-mural.png")


def painted_mural(im, box, seed=9, sun=True, vivid=True, fuji_at=0.56):
    """The mural in its frame on the back wall, at any size: stepped sky, the sun, clouds, cranes,
    the mountain, pines on a rocky point, the sea's crests, a sail."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    horizon = y0 + int(h * 0.74)
    bands = ["C", "D", "E", "F", "G"] if vivid else ["B", "C", "D", "E", "F"]
    for y in range(y0, horizon):
        f = (y - y0) / (horizon - y0) * (len(bands) - 1)
        i = min(int(f), len(bands) - 2)
        edge = f - i
        for x in range(x0, x1):
            # flat bands, dithered only across the two rows where they meet
            ch = bands[i + 1] if edge > 0.75 and dith((edge - 0.75) * 4, x, y) else bands[i]
            put(im, x, y, ch)
    cx = x0 + int(w * fuji_at)
    if sun:
        sx, sy, sr = x0 + int(w * 0.86), y0 + int(h * 0.22), max(3, h // 7)
        ellipse(im, (sx - sr, sy - sr, sx + sr, sy + sr), "x")
        put(im, sx - sr + 2, sy - sr + 2, "y")
        put(im, sx - sr + 3, sy - sr + 2, "y")
        put(im, sx - sr + 2, sy - sr + 3, "y")
    # clouds: flat strokes with a lit upper edge, one across the sun
    for fx, fy, fw in ((0.86, 0.33, 0.2), (0.16, 0.2, 0.2), (0.34, 0.42, 0.12)):
        ccx, ccy, cw = x0 + int(w * fx), y0 + int(h * fy), max(6, int(w * fw))
        hline(im, ccx - cw // 2, ccx + cw // 2, ccy, "G")
        hline(im, ccx - cw // 2 + 2, ccx + cw // 2 - 3, ccy - 1, "H")
        hline(im, ccx - cw // 2 + 3, ccx + cw // 2 + 2, ccy + 1, "F")
    crane_bird(im, x0 + int(w * 0.28), y0 + int(h * 0.14), "H")
    crane_bird(im, x0 + int(w * 0.33), y0 + int(h * 0.22), "G")
    fuji(im, cx, y0 + int(h * 0.1), horizon + 1, int((horizon - y0) * 1.7), snow_frac=0.42,
         seed=seed)
    # far shore, the foothills' dark line
    for x in range(x0, x1):
        yy = horizon - 2 + int(round(0.8 * math.sin(x / 5) + 0.6 * math.sin(x / 2.3)))
        for y in range(yy, horizon + 1):
            put(im, x, y, "r" if y == yy else "q")
    # the rocky point and its pines, left
    rock = [(x0, horizon - int(h * 0.2)), (x0 + int(w * 0.1), horizon - int(h * 0.26)),
            (x0 + int(w * 0.2), horizon - int(h * 0.12)), (x0 + int(w * 0.27), horizon + 1),
            (x0, horizon + 1)]
    poly(im, rock, "N")
    poly(im, [(x0, horizon - int(h * 0.19)), (x0 + int(w * 0.1), horizon - int(h * 0.25)),
              (x0 + int(w * 0.14), horizon - int(h * 0.18)), (x0, horizon - int(h * 0.1))], "O")
    if h < 40:
        stamp(im, PINE_S, x0 + int(w * 0.04), horizon - int(h * 0.26) - 5)
        stamp(im, PINE_S, x0 + int(w * 0.13), horizon - int(h * 0.14) - 5, flip=True)
    else:
        pine(im, x0 + int(w * 0.07), horizon - int(h * 0.24), max(5, int(h * 0.3)), seed=seed)
        pine(im, x0 + int(w * 0.17), horizon - int(h * 0.13), max(4, int(h * 0.22)), flip=True,
             seed=seed + 1)
    # the sea: painted crests
    if h < 40:
        painted_sea(im, (x0, horizon + 1, x1, y1), seed=seed)
    else:
        seigaiha(im, (x0, horizon + 1, x1, y1), "E", "D", r=3, lit="F")
    boat(im, x0 + int(w * 0.76), horizon - 5)


PINE_S = [  # a small black pine on the mural (8 × 7)
    "..rrss..",
    ".qqrrrq.",
    "...qq.rs",
    "rsq.dqqq",
    "qqqqd...",
    "....d...",
    "...cd...",
]
STOOL = [  # a hinoki stool, seen from a little above (10 × 6)
    ".hggggggf.",
    "gfffffffed",
    ".eeeeeeed.",
    "..c....c..",
    "..c....c..",
    "..b....b..",
]
BASIN = [  # a yellow wash basin (9 × 4)
    ".jkkkkkj.",
    "jlllllllk",
    ".jkkkkkj.",
    "..iiiii..",
]
LAMP = [  # an enamel pendant lamp, its bulb (6 × 4)
    "..00..",
    ".0cc0.",
    "0dfffd",
    ".llWl.",
]


def perspective_floor(im, box, vx, vy, K, f, ch, alt, grout, seed=1, alt_share=0.18):
    """A tiled floor in one-point perspective (K = focal length × eye height, f = focal length):
    square tiles in the world, crisp 1px grout where the tile index changes."""
    x0, y0, x1, y1 = box
    rnd = random.Random(seed)
    odd = {}

    def cell(x, y):
        z = K / (y + 0.5 - vy)
        return math.floor((x + 0.5 - vx) * z / f), math.floor(z)

    for y in range(y0, y1):
        for x in range(x0, x1):
            ix, iz = cell(x, y)
            lx, _ = cell(x - 1, y)
            _, uz = cell(x, y - 1)
            if ix != lx or iz != uz:
                c = grout
            else:
                if (ix, iz) not in odd:
                    odd[(ix, iz)] = rnd.random() < alt_share
                c = alt if odd[(ix, iz)] else ch
            put(im, x, y, c)


BASIN_L = grid([  # a yellow basin, bigger (10 × 5)
    ".0000000..",
    "0lllllllk0",
    "0kWkkkkkj0",
    ".0kkkkkj0.",
    "..000000..",
])
STOOL_L = grid([  # a hinoki stool, bigger (10 × 7)
    ".00000000.",
    "0hggggggf0",
    "0ffffffee0",
    "00eeeeee00",
    ".0c0..0c0.",
    ".0c0..0c0.",
    ".000..000.",
])
TOWEL = grid([  # a folded towel on the tub's rim (9 × 3)
    "0000000..",
    "0WWWWWW0.",
    "0xxxxxxw0",
    "099999980",
    "000000000",
])


def hero_hall():
    """home.hero.backdrop, 180 × 64 (4 × on a desktop): the bathing hall at closing time, in
    one-point perspective with the vanishing point on the left, so what a desktop shows (its
    right side) is the wall of taps and mirrors, the tub's end and the stools; the mural's Fuji
    stands right of centre. One pendant lamp hangs high; the cat sleeps on the rim."""
    W, H = 180, 64
    im = new(W, H, "1")
    vx, vy = 70, 24
    back_l, back_r = 12, 126
    top, floor_y = 4, 46
    rim_y = 36
    # ---- ceiling boards, receding
    for x in range(W):
        for y in range(0, top + 1):
            put(im, x, y, "1" if (x - vx) % 11 else "2")
    # ---- the back wall: the mural in its frame, a band of tile under it
    rect(im, back_l, top, back_r, rim_y, "3")
    painted_mural(im, (back_l + 1, top + 1, back_r - 1, 29), fuji_at=0.66)
    hline(im, back_l, back_r, top, "d")
    vline(im, back_l, top, 31, "d")
    vline(im, back_r - 1, top + 1, 31, "c")
    hline(im, back_l, back_r, 29, "e")
    hline(im, back_l + 1, back_r, 30, "c")
    mosaic(im, (back_l, 31, back_r, 32), "4", "3", size=2, seed=4)
    # ---- the water: two tones, the mural's reflection broken by ripples
    refl = {rgb(k)[:3]: v for k, v in (("B", "5"), ("C", "5"), ("D", "6"), ("E", "6"), ("F", "7"),
                                        ("G", "8"), ("H", "8"), ("q", "4"), ("r", "5"), ("x", "w"),
                                        ("s", "5"), ("N", "5"), ("O", "6"))}
    for y in range(32, rim_y):
        src = 28 - (y - 32) * 2
        for x in range(back_l, back_r):
            p = get(im, x + (1 if (y + x // 5) % 3 == 0 else 0), src)[:3]
            ch = refl.get(p, "6" if y % 2 else "5")
            if (x * 3 + y * 7) % 13 == 0:
                ch = "7"  # a ripple
            put(im, x, y, ch)
    # ---- the tub's rim: thick, lit on top, its shadow under; the tub's tiled front
    rect(im, back_l - 2, rim_y, back_r + 1, rim_y + 3, "8")
    hline(im, back_l - 2, back_r + 1, rim_y, "W")
    hline(im, back_l - 2, back_r + 1, rim_y + 1, "9")
    hline(im, back_l - 2, back_r + 1, rim_y + 3, "5")
    mosaic(im, (back_l - 2, rim_y + 4, back_r + 1, floor_y), "6", "4", size=2, seed=8,
           chips=("7", 0.06))
    hline(im, back_l - 2, back_r + 1, floor_y - 1, "3")
    # ---- the left wall, a sliver
    for x in range(0, back_l):
        t = (x - vx) / (back_l - vx)
        yt, yb = vy + (top - vy) * t, vy + (floor_y - vy) * t
        for y in range(H):
            if y > top and yt <= y < yb:
                put(im, x, y, "4" if (y + x) % 4 else "3")
    # ---- the right wall in perspective: tile, a row of washing places (mirror, taps), a ledge
    def wall_y(v, t):
        return vy + (v - vy) * t

    stations = [0.93 - k * 0.1 for k in range(5)]
    for x in range(back_r, W):
        t = (x - vx) / (back_r - vx)
        t2 = (x + 1 - vx) / (back_r - vx)
        u, u2 = 1 / t, 1 / t2
        yt, yb = wall_y(top, t), wall_y(floor_y, t)
        for y in range(max(0, int(yt)), min(H, int(yb) + 1)):
            v = vy + (y - vy) / t
            v2 = vy + (y + 1 - vy) / t
            ch = "5"
            if int(u * 24) != int(u2 * 24) or int(v / 3) != int(v2 / 3):
                ch = "4"  # grout, finer far away
            for uc in stations:
                du = u - uc
                if abs(du) <= 0.034 and 14 <= v < 23:  # the mirror
                    edge = abs(du) > 0.026 or v < 15 or v >= 22
                    ch = "c" if edge else ("G" if du < -0.01 else "F")
                    if not edge and v < 16.5 and du < 0:
                        ch = "H"
                elif abs(du) <= 0.014 and 26 <= v < 28:  # the tap's spout
                    ch = "9" if v < 27 else "7"
                elif 0.016 < abs(du) <= 0.028 and 25.5 <= v < 27:  # hot and cold
                    ch = "x" if du < 0 else "E"
            if 30 <= v < 32:
                ch = "W" if v < 31 else "8"  # the ledge
            elif 32 <= v < 33:
                ch = "4"
            put(im, x, y, ch)
        put(im, x, max(0, int(yt)), "b")
    # ---- the floor: wet tile in perspective
    perspective_floor(im, (0, floor_y, W, H), vx, vy, 150, 60, "5", "6", "4", seed=3)
    # ---- the pendant lamp, high: its warm bulb, its pool on the floor
    lx = 128
    vline(im, lx + 3, 0, 7, "0")
    stamp(im, grid([
        "..00000..",
        ".0ccccc0.",
        "0deeeeed0",
        "000000000",
        ".llWWWll.",
        "..l.l.l..",
    ]), lx - 1, 7)
    for y in range(floor_y + 1, H):
        for x in range(lx - 30, lx + 36):
            d = ((x - lx - 3) / 30) ** 2 + ((y - 56) / 9) ** 2
            if d > 1 or not (0 <= x < W):
                continue
            if d > 0.6 and not dith((1 - d) / 0.4, x, y):
                continue
            p = get(im, x, y)[:3]
            lit = {rgb("5")[:3]: "6", rgb("6")[:3]: "7", rgb("4")[:3]: "5"}
            if p in lit:
                put(im, x, y, lit[p])
    # ---- the washing places by the right wall: stools and basins, nearer is bigger
    stamp(im, STOOL, 130, 47)
    stamp(im, BASIN, 131, 44)
    stamp(im, STOOL_L, 144, 51)
    stamp(im, BASIN_L, 144, 47)
    stamp(im, STOOL_L, 162, 56)
    stamp(im, BASIN_L, 168, 59)
    # a basin pyramid by the tub's end
    for bx, by in ((96, 55), (105, 55), (114, 55), (100, 51), (109, 51), (104, 47)):
        stamp(im, BASIN_L, bx, by)
    for sx, sy, sw in ((146, 58, 10), (164, 63, 10), (96, 60, 29)):
        for x in range(sx, sx + sw):
            if get(im, x, sy)[3] and get(im, x, sy)[:3] in (rgb("5")[:3], rgb("6")[:3], rgb("7")[:3]):
                put(im, x, sy, "4")
    # ---- a wooden pail and a towel on the rim; the cat asleep at the rim's end
    stamp(im, TOWEL, 78, rim_y - 3)
    stamp(im, grid([".e......e.", "gfffffffff", "ecdcdcdcdd", "ecdcdcdcdd", ".cccccccc."]),
           60, rim_y - 3)
    stamp(im, CAT_SLEEP, 110, rim_y - 7)
    # ---- a drop falling from the steamy ceiling, and its ring on the water
    put(im, 70, 20, "H")
    put(im, 70, 21, "G")
    for x, y in ((67, 35), (68, 34), (69, 34), (70, 34), (71, 34), (72, 34), (73, 35)):
        put(im, x, y, "9")
    # ---- the painter hid the bathhouse cat on the mural's rocky point
    stamp(im, grid(["M.M..", "MMM..", ".MM..", ".MMM.", ".MMMM"]), back_l + 8, 17)
    # ---- steam off the water: drawn wisps drifting up over the mural's sea
    for wx, wy, wl, ch, r in ((20, 31, 22, "9", 2), (52, 28, 16, "G", 1), (84, 31, 20, "9", 2),
                              (100, 25, 12, "G", 1), (30, 24, 12, "G", 1)):
        veil(im, wx, wy, wl, ch, rise=r)
    return done(im, "hero-hall.png")


def hero_ground():
    """A hero layer drawn under the picture: the hall's dark tile continuing down, so on a phone
    the greeting sits on the bathhouse's own wall (not on the mural's giant pixels)."""
    im = new(6, 6)
    mosaic(im, (0, 0, 6, 6), "2", "1", size=3, seed=5)
    put(im, 0, 0, "3")
    return done(im, "hero-ground.png")


# ---------------------------------------------------------------- the lintel, the noren, the cat


def status_beam():
    """status.backdrop, 302 × 12 (4 × on a desktop): the hinoki lintel over the doorway. Only its
    top four rows are painted; below, the bar's own tile (part.status.texture) and its layers
    (the noren, the cat) show, since layers sit under a slot's picture."""
    W, H = 302, 12
    im = new(W, H)
    rect(im, 0, 0, W, 1, "c")
    rect(im, 0, 1, W, 3, "e")
    hline(im, 0, W, 3, "b")
    rnd = random.Random(4)
    x = 0
    while x < W:  # the grain: long darker strokes, a knot now and then
        n = rnd.randint(9, 26)
        hline(im, x, min(W, x + n), 1 + rnd.randint(0, 1), "d")
        x += n + rnd.randint(4, 12)
    for kx in (37, 151, 262):
        put(im, kx, 2, "c")
        put(im, kx + 1, 2, "d")
    hline(im, 0, W, 1, "f")  # the lamp catches the top edge
    for x in range(0, W, 3):
        if rnd.random() < 0.5:
            put(im, x, 1, "e")
    return done(im, "status-beam.png")


NOREN_W, NOREN_H, NOREN_AIR = 48, 22, 140


def noren_draw(swings, amps=(2.0, 1.2, 2.0), lifts=(0, 0, 0)):
    """One frame of the noren, 48 × 22: a bamboo rod, three split panels with sleeves over the
    rod, two soft folds each (light and dark), a shaded hem, the ♨ on the middle panel. swings:
    how far each panel's hem is pushed (−1 … 1, times amps px); lifts: rows a hem is raised (a
    panel pushed toward the viewer looks shorter)."""
    NW, NH = NOREN_W, NOREN_H
    mark = grid(ONSEN_S)
    mark_shadow = recolour(mark, {"h": "u"})
    fr = new(NW, NH)
    for i, (a, b) in enumerate([(0, 15), (16, 31), (32, 47)]):
        swing, amp, lift = swings[i], amps[i], lifts[i]
        bottom = NH - lift
        body = new(NW, NH)
        for y in range(2, bottom):
            for x in range(a, b):
                ch = "w"
                if y in (2, 3):
                    ch = "u" if y == 2 else "v"
                elif y >= bottom - 2:
                    ch = ("v", "u")[y - (bottom - 2)]
                elif x == a:
                    ch = "x"
                elif x == b - 1:
                    ch = "v"
                put(body, x, y, ch)
            if 4 <= y < bottom - 2:
                k = (y - 4) / (NH - 6)
                for fx in (a + 4, a + 10):
                    fx += int(round(swing * 1.2 * k))
                    put(body, fx, y, "x")
                    put(body, fx + 1, y, "v")
        for y in range(2, bottom):  # each row slides by more the lower it hangs
            dx = int(round(swing * amp * ((y - 2) / (NH - 3)) ** 1.6))
            fr.alpha_composite(body.crop((a, y, b, y + 1)), (a + dx, y))
        if i == 1:  # the mark moves with the cloth as one piece (a lifted hem hides its foot)
            mx = a + (b - a - mark.width) // 2 + int(round(swing * amp * 0.35))
            m = mark.crop((0, 0, mark.width, max(1, min(mark.height, bottom - 6))))
            fr.alpha_composite(recolour(m, {"h": "u"}), (mx + 1, 5))
            fr.alpha_composite(m, (mx, 4))
    hline(fr, 0, NW, 0, "g")  # the bamboo rod, nodes every eight
    hline(fr, 0, NW, 1, "e")
    for x in range(3, NW, 8):
        put(fr, x, 0, "e")
        put(fr, x, 1, "d")
    put(fr, 0, 1, "c")
    put(fr, NW - 1, 1, "c")
    return fr


def noren():
    """A header layer: the noren in the doorway, eight frames of a slow sway, each panel out of
    step with the next. The piece carries 140 px of air on its left, so it hangs past the room's
    words (and on a phone, out of view). Poked, it parts as if someone walked through: the side
    panels pushed apart, the middle one lifted, then everything swinging back."""
    step = NOREN_AIR + NOREN_W
    n = 8
    sheet_ = new(step * n, NOREN_H)
    for f in range(n):
        sw = [math.sin(2 * math.pi * f / n + i * 1.9) for i in range(3)]
        sheet_.alpha_composite(noren_draw(sw), (f * step + NOREN_AIR, 0))
    done(sheet_, "noren.png")
    push = [0.3, 0.9, 1.6, 2.2, 2.4, 2.0, 1.2, 0.3, -0.5, -0.6, -0.2, 0.0]
    poke = new(step * len(push), NOREN_H)
    for f, p in enumerate(push):
        fr = noren_draw((-p, p * 0.3, p), amps=(2.2, 1.0, 2.2),
                        lifts=(0, max(0, int(round(p * 2.5))), 0))
        poke.alpha_composite(fr, (f * step + NOREN_AIR, 0))
    return done(poke, "noren-parts.png")


CAT_BODY = [  # a calico trotting left, head turned to us, tail up (19 × 8, legs below)
    "..0...0............",
    ".0h0.0h0........00.",
    ".0hhhhh0.......0o0.",
    "0hW0hW0h0......0o0.",
    "0hhhhhhh0000000o0..",
    ".0hhzhhWWoooWWWh0..",
    "..0hhhhhooo111hh0..",
    "...0hhhhhhh111h0...",
]
CAT_LEGS = [  # four steps (19 × 2 each)
    ["...0h0.0h0..0h0.0h0", "...00..00...00..00."],
    ["....0h0h0....0h0h0.", "....00.00....00.00."],
    ["..0h0...0h00h0...0h", "..00....0000.....00"],
    ["....0h0h0....0h0h0.", "....00.00....00.00."],
]


def cat_walk():
    """A status layer: the bathhouse cat trotting along under the lintel now and then."""
    w, h = 19, 10
    sheet_ = new(w * 4, h)
    for i, legs in enumerate(CAT_LEGS):
        bob = 1 if i % 2 else 0
        body = grid(CAT_BODY)
        fr = new(w, h)
        fr.alpha_composite(grid(legs), (0, 8))
        fr.alpha_composite(body, (0, bob))
        sheet_.alpha_composite(fr, (i * w, 0))
    return done(sheet_, "cat-walk.png")


# ---------------------------------------------------------------- textures (SVG, pixel-exact)


def svg_tile(im, name, n=4, opacity=1.0):
    """A pixel picture as an SVG of rects (runs per row), each art pixel n × n: a crisp texture."""
    w, h = im.width, im.height
    rects = []
    for y in range(h):
        x = 0
        while x < w:
            p = im.getpixel((x, y))
            run = 1
            while x + run < w and im.getpixel((x + run, y)) == p:
                run += 1
            if p[3]:
                rects.append(f'<rect x="{x * n}" y="{y * n}" width="{run * n}" height="{n}" '
                             f'fill="#{p[0]:02x}{p[1]:02x}{p[2]:02x}"/>')
            x += run
    op = f' opacity="{opacity}"' if opacity < 1 else ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * n}" height="{h * n}" '
           f'viewBox="0 0 {w * n} {h * n}" shape-rendering="crispEdges"><g{op}>' + "".join(rects)
           + "</g></svg>")
    LOCK.lock(im, name)
    (ART / name).write_text(svg)
    print(f"{name:28} {w * n}×{h * n}  {len(svg) / 1024:.1f} KB")


def textures():
    # the bar under the lintel: the mural's wave-scale in dark tile (part.status.texture)
    im = new(8, 8)
    seigaiha(im, (0, 0, 8, 8), "3", "2", r=4, lit="4")
    svg_tile(im, "status-waves.svg")
    # sheets and dialogs: small wet tiles, only their grout drawn, faintly (the sheet's own
    # ground is the glaze): 12 px tiles, 2 px of grout
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12" '
           'shape-rendering="crispEdges"><g fill="#061015" opacity="0.32">'
           '<rect x="0" y="10" width="12" height="2"/><rect x="10" y="0" width="2" height="10"/>'
           '</g><rect x="0" y="0" width="2" height="1" fill="#ffffff" opacity="0.04"/></svg>')
    (ART / "tile.svg").write_text(svg)
    print(f"{'tile.svg':28} 12×12  {len(svg) / 1024:.1f} KB")
    # the dock and the nowbar's grain: nothing; the screen: faint scanlines
    im = new(1, 2)
    put(im, 0, 1, "1")
    svg_tile(im, "scanlines.svg", n=2, opacity=0.35)


# ---------------------------------------------------------------- page steam (layers)


def page_steam():
    """Page layers under the scrim: one puff (a particle that rises) and a vapour tile that drifts."""
    im = new(20, 12)
    for y in range(12):
        for x in range(20):
            d = ((x - 10) / 9.5) ** 2 + ((y - 7) / 5) ** 2
            d2 = ((x - 6) / 5) ** 2 + ((y - 4) / 3.5) ** 2
            t = max(1 - d, 1 - d2)
            if t > 0 and dith(min(1, t * 1.1), x, y):
                put(im, x, y, "8" if t > 0.7 and (x + y) % 2 else "7")
    done(im, "steam-puff.png")
    W, H = 100, 60
    im = new(W, H)
    rnd = random.Random(8)
    blobs = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(26, 40), rnd.uniform(6, 9))
             for _ in range(3)]
    for y in range(H):
        for x in range(W):
            t = 0
            for bx, by, rx, ry in blobs:
                dx = min(abs(x - bx), W - abs(x - bx))
                dy = min(abs(y - by), H - abs(y - by))
                t = max(t, 1 - (dx / rx) ** 2 - (dy / ry) ** 2)
            if t > 0.05:
                ch = "9" if t > 0.6 else "8" if t > 0.3 else "7"
                if t > 0.3 or dith(t / 0.3, x, y):
                    put(im, x, y, ch)
    done(im, "vapour.png")


# ---------------------------------------------------------------- the deck: the counter radio


def deck_dial():
    """The music deck as the counter's tube radio. Its case is a 9-slice (12 × 12 drawn, 4 ×,
    slice 16): rounded top corners, two-tone hinoki grain running along each side, a louvred
    speaker grille along the bottom with a knob in each bottom corner, a dark lacquer face for the
    words. In its top edge a dark-glass dial, backlit amber, with two rows of ticks and a long
    vermilion needle that wanders while music plays (one layer, 16 frames); a wisp of warmth
    curls off the case's top corner while it plays."""
    N = 12
    im = new(N, N)
    rect(im, 0, 0, N, N, "b")  # the middle (stretched): plain dark lacquer, nothing else
    # top edge: grain running along it, lit, then the recess into the face
    for y, ch in ((0, "a"), (1, "f"), (2, "e"), (3, "a")):
        hline(im, 0, N, y, ch)
    # side edges: grain running down; the left lit, the right in shade
    for x, ch in ((0, "a"), (1, "f"), (2, "d"), (3, "a")):
        vline(im, x, 3, N - 3, ch)
    for x, ch in ((N - 1, "a"), (N - 2, "d"), (N - 3, "c"), (N - 4, "a")):
        vline(im, x, 3, N - 3, ch)
    # bottom edge: the speaker's louvres
    for y, ch in ((N - 4, "a"), (N - 3, "d"), (N - 2, "b"), (N - 1, "a")):
        hline(im, 4, N - 4, y, ch)
    for y, ch in ((N - 4, "a"), (N - 3, "d"), (N - 2, "b"), (N - 1, "a")):
        hline(im, 0, 4, y, ch)
        hline(im, N - 4, N, y, ch)
    # rounded top corners
    for x, y in ((0, 0), (1, 0), (0, 1), (N - 1, 0), (N - 2, 0), (N - 1, 1)):
        put(im, x, y, None)
    put(im, 1, 1, "a")
    put(im, N - 2, 1, "a")
    put(im, 2, 1, "g")
    put(im, 1, 2, "g")
    # a knob in each bottom corner
    knob = grid([".00.", "0gf0", "0fd0", ".00."])
    stamp(im, knob, 0, N - 4)
    stamp(im, knob, N - 4, N - 4)
    done(im, "deck-radio.png", 4)
    W, n = 48, 16
    sheet_ = new(W * n, 4)
    for f in range(n):
        d = new(W, 4)
        hline(d, 0, W, 0, "a")
        hline(d, 0, W, 3, "a")
        for x in range(W):
            glow = 1 - abs(x - W / 2) / (W / 2)
            put(d, x, 1, "j" if glow > 0.35 else "i")
            put(d, x, 2, "i" if glow > 0.2 else "b")
        for x in range(2, W - 2, 6):
            put(d, x, 1, "l")  # long ticks
            put(d, x, 2, "k")
        for x in range(5, W - 2, 6):
            put(d, x, 2, "k")  # short ticks
        vline(d, 0, 0, 4, "a")
        vline(d, W - 1, 0, 4, "a")
        x = int(round(W / 2 + (W / 2 - 5) * math.sin(2 * math.pi * f / n)))
        vline(d, x, 0, 4, "x")
        put(d, x, 0, "z")
        sheet_.alpha_composite(d, (f * W, 0))
    done(sheet_, "deck-dial.png")
    # poked: the needle swings right across the band and back, as if someone spun the dial
    sweep = [0.5, 0.2, 0.0, 0.1, 0.45, 0.85, 1.0, 0.9, 0.6, 0.5]
    poke = new(W * len(sweep), 4)
    for f, t in enumerate(sweep):
        d = sheet_.crop((0, 0, W, 4)).copy()
        for y in range(4):  # clear the idle needle, redraw the scale under it
            for x in range(W):
                if get(d, x, y)[:3] in (rgb("x")[:3], rgb("z")[:3]):
                    put(d, x, y, "a" if y in (0, 3) else ("j" if y == 1 else "i"))
        x = 2 + int(round(t * (W - 5)))
        vline(d, x, 0, 4, "x")
        put(d, x, 0, "z")
        poke.alpha_composite(d, (f * W, 0))
    done(poke, "deck-dial-spin.png")
    done(grid([".ll", ".l.", "ll.", "ll."]), "bit-note.png")
    n, w = 6, 16
    wisp = new(w * n, 4)
    for f in range(n):
        for i in range(3):
            t = (f + i * 2) % n / n  # a curl rising and thinning
            y = 3 - int(t * 4)
            x = f * w + 6 + i * 2 + int(round(1.5 * math.sin(t * 6)))
            if 0 <= y < 4 and t < 0.85:
                put(wisp, x, y, "h" if t < 0.5 else "g")
                if t < 0.35:
                    put(wisp, x + 1, y, "g")
    done(wisp, "deck-wisp.png")


# ---------------------------------------------------------------- the hero's steam and drop


def hero_steam():
    """Hero layers: steam gathering under the ceiling at the top right, drifting (8 frames, a slow
    loop), and a drop that falls through the hall now and then (a crossing)."""
    W, H, n = 100, 20, 8
    sheet_ = new(W * n, H)
    # cream curls rising: each a thin S that climbs a row a frame and thins out as it goes
    curls = [(8, 0.0, 14), (26, 2.1, 17), (44, 4.0, 13), (61, 1.3, 16), (79, 3.2, 15), (93, 5.0, 12)]
    for f in range(n):
        fr = new(W, H)
        for x0, ph, ln in curls:
            base = H - 1 - ((f * 2 + int(ph * 3)) % 6)  # the curl's foot bobs as it rises
            for i in range(ln):
                y = base - i
                if y < 0:
                    break
                t = i / ln
                x = int(round(x0 + 1.8 * math.sin(i / 2.6 + ph + f * 0.8) * (0.4 + t)))
                if t < 0.55 or dith(1.4 - t * 1.5, x, y + f):
                    put(fr, x, y, "h" if t < 0.4 else "g")
                    if t < 0.25:
                        put(fr, x + 1, y, "g")
        # thin toward the piece's left edge so it has no hard start
        px_ = fr.load()
        for y in range(H):
            for x in range(20):
                if px_[x, y][3] and not dith(x / 20, x, y):
                    px_[x, y] = CLEAR
        sheet_.alpha_composite(fr, (f * W, 0))
    done(sheet_, "hero-steam.png")
    billow = new(W * 8, H)
    for f in range(8):
        fr = new(W, H)
        for x0, ph, ln in curls:
            base = H - 1 - (f % 4)
            for i in range(ln + 4):
                y = base - i
                if y < 0:
                    break
                t = i / (ln + 4)
                amp = 1.8 + f * 0.5
                x = int(round(x0 + amp * math.sin(i / 2.2 + ph + f * 1.3) * (0.4 + t)))
                if t < 0.7 or dith(1.6 - t * 1.6, x, y + f):
                    put(fr, x, y, "W" if t < 0.35 else "h")
                    put(fr, x + 1, y, "h" if t < 0.5 else "g")
        billow.alpha_composite(fr, (f * W, 0))
    done(billow, "hero-steam-billow.png")
    done(grid(["G", "H", "G"]), "bit-drop.png")
    drop = new(46, 3)
    put(drop, 0, 0, "G")
    put(drop, 0, 1, "H")
    put(drop, 0, 2, "G")
    done(drop, "hero-drop.png")


# ---------------------------------------------------------------- the rail


FURIN = [  # a glass wind chime: the bell, a painted goldfish, the clapper, the paper strip
    "...00...",
    "..0GG0..",
    ".0HGGG0.",
    "0HGxGGF0",
    "0GxxGGF0",
    "0FGGGFF0",
    ".000000.",
    "...0....",
    "...f....",
    "..0h0...",
    "..0h0...",
    "..0h0...",
    "..0g0...",
    "..0h0...",
    "..0g0...",
    "...0....",
]


def rail_wall():
    """rail.surface, 58 × 270 (≈4 × on a 1080 px window; cover, anchored bottom): a plain night-tile
    wall, calm under the room names, and low down the sentō's painted mural (the mountain, a red
    sun, the sea) behind the fridge and the cat, which stand on a hinoki ledge; the wainscot under
    it sits behind the Ask Nox card. Drawn low so that every window height keeps it below the
    room names."""
    W, H = 58, 270
    im = new(W, H)
    mosaic(im, (0, 0, W, H), "1", "0", size=4)
    y0, y1 = 184, 224
    for y in range(y0, y1):
        for x in range(W):
            put(im, x, y, "B" if dith((y - y0) / (y1 - y0) * 1.3, x, y) else "A")
    hline(im, 0, W, y0, "0")
    ellipse(im, (45, y0 + 5, 50, y0 + 10), "x")
    fuji(im, 24, y0 + 7, y1 - 9, 22, snow_frac=0.38, ramp=("B", "C", "D"), snow=("G", "F", "E"))
    rect(im, 0, y1 - 9, W, y1, "C")
    for x in range(1, W - 1, 4):
        put(im, x, y1 - 7 + (x // 4) % 3, "E")
        put(im, x + 1, y1 - 7 + (x // 4) % 3, "D")
    # the ledge the pieces stand on, then the wainscot
    hline(im, 0, W, y1, "d")
    hline(im, 0, W, y1 + 1, "c")
    rect(im, 0, y1 + 2, W, H, "b")
    for x in range(0, W, 8):
        vline(im, x, y1 + 2, H, "a")
    return done(im, "rail-wall.png")


FRIDGE = [  # the milk fridge: a lit sign stripe, three shelves of bottles, one gone (16 × 26)
    "0000000000000000",
    "0999999999999990",
    "09xxxxxxxxxxxx90",
    "09yyyyyyyyyyyy90",
    "09GGGGGGGGGGGG90",
    "09hhGhhGhhGhhG90",
    "09ddGWWGooGddH90",
    "09ddGWWGooGdHG90",
    "0977777777H77790",
    "09GGGGGGGHGGGG90",
    "09hhGhhGhHGhhG90",
    "09WWGddGHWGooG90",
    "09WWGddHWWGooG90",
    "097777H7777777790",
    "09hhGHGGGGGhhG90",
    "09ooHWWGGGGWWG90",
    "09oHGWWGGGGWWG90",
    "0977777777777790",
    "09GGGGGGGGGGGG90",
    "0999999999999990",
    "0444444444444440",
    "0433333333333340",
    "04333333333l3340",
    "0433333333333340",
    "0444444444444440",
    ".00..........00.",
]


def dock_shelf():
    """dock.surface, 98 × 16 (4 × on a phone): the shoe lockers by the door, their tall wooden
    keys, dim so the doors' names read."""
    W, H = 98, 16
    im = new(W, H, "b")
    for i, x0 in enumerate(range(-4, W, 14)):
        rect(im, x0, 1, x0 + 13, 15, "c")
        hline(im, x0, x0 + 13, 1, "d")
        vline(im, x0, 1, 15, "d")
        hline(im, x0 + 1, x0 + 13, 14, "a")
        kx = x0 + 10
        rect(im, kx, 3, kx + 2, 9, "e" if i % 4 else "d")
        put(im, kx, 3, "f")
    hline(im, 0, W, 0, "a")
    hline(im, 0, W, 15, "a")
    return done(im, "dock-shelf.png")


# ---------------------------------------------------------------- the rooms' banners

RADIO = [  # a tube radio in a wooden case: cloth grille, a glowing dial, two knobs (22 × 14)
    "....00000000000000....",
    "..00eeeeeeeeeeeeee00..",
    ".0effffffffffffffffe0.",
    "0efgggfgggfgggfgggfde0",
    "0efgfgfgfgfgfgfgfgfde0",
    "0efgggfgggfgggfgggfde0",
    "0efgfgfgfgfgfgfgfgfde0",
    "0efgggfgggfgggfgggfde0",
    "0edddddddddddddddddde0",
    "0ed0llhlhhlhhlhhlh0de0",
    "0ed0lhhhhxhhhhhhhh0de0",
    "0edd00000000000000dde0",
    "0ed0ff0dddddddd0ff0de0",
    ".0000000000000000000.",
]
PLANT = [  # a potted plant (8 × 10)
    "...s.r..",
    ".s.sr.r.",
    "..srsr..",
    "s.rsrr.r",
    ".rqrqqr.",
    "..qqqq..",
    ".0xxxx0.",
    ".0wxxw0.",
    "..0ww0..",
    "..0000..",
]
TV = [  # a CRT in a wooden case on a bracket, rabbit ears (22 × 20)
    ".....0.........0......",
    "......0.......0.......",
    ".......0.....0........",
    "........0...0.........",
    "......000000000.......",
    "..000000000000000000..",
    ".0eeeeeeeeeeeeeeeeee0.",
    "0ef000000000000000fde0",
    "0ef0GGGGGGGGGGGG0ffde0",
    "0ef0GHGFFFFFFFFG0f0de0",
    "0ef0GFFFFFFFFFFF0ffde0",
    "0ef0FFFFFFFFFFFF0f0de0",
    "0ef0FFFFFFFFFFFE0ffde0",
    "0ef0FFFFFFFFFFEE0ddde0",
    "0ef000000000000000dde0",
    "0edddddddddddddddddde0",
    ".00000000000000000000.",
    ".......0h0..0h0.......",
    "......0hhh00hhh0......",
    "......00000000000.....",
]
ARCADE = [  # an arcade cabinet by the door: lit marquee, the screen's little sprites (24 × 34)
    "..00000000000000000000..",
    ".0MMMMMMMMMMMMMMMMMMMM0.",
    ".0MzzkkzzkkzzkkzzkkzzM0.",
    ".0MkzzyzkzzyzkzzyzkzzM0.",
    ".0MMMMMMMMMMMMMMMMMMMM0.",
    "0NNN00000000000000000NN0",
    "0NN0AAAAAAAAAAAAAAAA0NN0",
    "0NN0AAAkAAAAAAAAxAAA0NN0",
    "0NN0AAAAAAAAAAAAAAAA0NN0",
    "0NN0AAAAAAHAAAAAAAAA0NN0",
    "0NN0AAAAAAAAAAAAAsAA0NN0",
    "0NN0AAxAAAAAAAAAAAAA0NN0",
    "0NN0AAAAAAAAAkkAAAAA0NN0",
    "0NN0AAAAAAAAAkkAAAAA0NN0",
    "0NN0AAAAAAAAAAAAAAAA0NN0",
    "0NN0000000000000000000N0",
    "0NNNNNNNNNNNNNNNNNNNNNN0",
    "00OOOOOOOOOOOOOOOOOOOO00",
    "0OO0x0OO0k0k0OOOOOOOOOO0",
    "0OOO0OOOO0O0OOOOOOOOOOO0",
    "000000000000000000000000",
    ".0NNNNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNNNN0.",
    ".0NNNN00000000000NNNNN0.",
    ".0NNNN0kkkk0bbbb0NNNNN0.",
    ".0NNNN00000000000NNNNN0.",
    ".0NNNNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNNNN0.",
]
PADDLES = [  # two ping-pong paddles hanging on a nail (14 × 12)
    "..0000...0000.",
    ".0xxxx0.0wwww0",
    "0xyxxxx0wxwwww0",
    "0xxxxxx0wwwwww0",
    "0xxxxxx0wwwwww0",
    ".0xxxx0.0wwww0",
    "..0ee0...0ee0.",
    "..0ee0...0ee0.",
    "..0ee0...0ee0.",
    "..0000...0000.",
    "..............",
    "..............",
]
SCALE = [  # the old dial scale: a round face with ticks, a red needle, on its column (16 × 26)
    "....00000000....",
    "..00hhhhhhhh00..",
    ".0hh0hh0hh0hhh0.",
    "0hh0hhhhhhhh0hh0",
    "0hhhhhhhhhhhhhh0",
    "0h0hhhhhhxhhh0h0",
    "0hhhhhhhxhhhhhh0",
    "0hhhhhhxhhhhhhh0",
    "0h0hhhh0hhhhh0h0",
    ".0hhhhhhhhhhhh0.",
    "..00hhhhhhhh00..",
    "....00000000....",
    "......0990......",
    "......0980......",
    "......0980......",
    "......0980......",
    "......0980......",
    "......0980......",
    "......0980......",
    "....00099800....",
    "..0099999998800.",
    ".099999999999880",
    ".088888888888880",
    ".000000000000000",
    "................",
    "................",
]
LOCKERS_OPEN = [  # three changing-room lockers, yours open: a red towel, a basket (30 × 26)
    "000000000000000000000000000000",
    "0dddddddd00000000000dddddddd00",
    "0dccccccd0bbbbbbbbb0dccccccd00",
    "0dccccccd0bbbbbbbbb0dccccccde0",
    "0dcccefcd0bxxxxxxbb0dcccefcde0",
    "0dcccefcd0bxyyyyxbb0dcccefcdf0",
    "0dccccfcd0bxxxxxxbb0dccccfcdf0",
    "0dccccccd0bxxxxxxbb0dccccccdf0",
    "0dccccccd0bwwwwwwbb0dccccccde0",
    "0dddddddd0bbbbbbbbb0dddddddde0",
    "0000000000000000000000000000d0",
    "0dddddddd0dddddddd00dddddddd00",
    "0dccccccd0dccccccd00dccccccd00",
    "0dccccccd0dccccccd00dccccccd00",
    "0dcccefcd0dcccefcd00dcccefcd00",
    "0dcccefcd0dcccefcd00dcccefcd00",
    "0dccccfcd0dccccfcd00dccccfcd00",
    "0dccccccd0dccccccd00dccccccd00",
    "0dccccccd0dccccccd00dccccccd00",
    "0dddddddd0dddddddd00dddddddd00",
    "000000000000000000000000000000",
]
def wall_tile(im, box, seed=2):
    mosaic(im, box, "2", "1", size=3, hi=None, seed=seed, chips=("3", 0.04))


# ---------------------------------------------------------------- slot pictures


def crest():
    """auth.crest, 40 × 40 (4 × in its 160 box): the ♨ mark set in a round tile medallion: twelve
    glazed vermilion tiles in a ring, lit from the top left, around a teal mosaic."""
    N = 40
    im = new(N, N)
    c = (N - 1) / 2
    seg = 2 * math.pi / 12
    for y in range(N):
        for x in range(N):
            d = math.hypot(x - c, y - c)
            if d > 19.7:
                continue
            ang = math.atan2(y - c, x - c)
            light = math.cos(ang - math.radians(-135))  # 1 toward the lamp (up left)
            if d > 18.9:
                ch = "0"
            elif d > 14.9:
                a_in = (ang + math.pi + seg / 2) % seg
                if a_in < 0.09 or a_in > seg - 0.09:
                    ch = "u"  # grout between ring tiles
                elif d > 18.0:
                    ch = "y" if light > 0.3 else "x" if light > -0.4 else "w"
                elif d < 15.9:
                    ch = "v" if light > -0.2 else "u"
                else:
                    ch = "x" if light > -0.5 else "w"
            elif d > 13.9:
                ch = "0"
            else:
                gx, gy = x % 3, y % 3
                ch = "3" if gx == 2 or gy == 2 else ("5" if (x // 3 * 7 + y // 3 * 3) % 5 else "4")
            put(im, x, y, ch)
    # the mark: ♨, three S lines rising out of an open bowl, cream over a dark drop shadow
    mark = new(20, 26)
    cx, cy, r = 9.5, 16.5, 8.6
    for y in range(26):
        for x in range(20):
            d = math.hypot(x - cx, y - cy)
            ang = math.degrees(math.atan2(y - cy, x - cx))
            if r - 1.6 <= d <= r + 0.4 and not (-148 < ang < -32):
                put(mark, x, y, "h")
    for x0, y1 in ((4, 12), (9, 15), (14, 12)):
        for y in range(0, y1):
            o = int(round(1.4 * math.sin(y / 12 * 2 * math.pi)))
            put(mark, x0 + o, y, "h")
            put(mark, x0 + o + 1, y, "h")
    mx, my = (N - 20) // 2, (N - 26) // 2
    im.alpha_composite(recolour(mark, {"h": "0"}), (mx + 1, my + 1))
    im.alpha_composite(mark, (mx, my))
    return done(im, "crest.png")


def empty_basin():
    """state.empty, 24 × 24 (4 × in its 96 box): an empty yellow basin, one drop about to land, the
    ripple in the water smiling back."""
    N = 24
    im = new(N, N)
    cx = 11.5
    # the body: a bowl narrowing to a foot, lit on the left
    for y in range(12, 21):
        t = (y - 12) / 8
        half = 10.5 - 3.5 * t ** 1.4
        for x in range(N):
            u = (x - cx) / half
            if abs(u) <= 1:
                ch = "l" if u < -0.55 else "k" if u < 0.35 else "j"
                if abs(u) > 0.93:
                    ch = "i"
                put(im, x, y, ch)
    rect(im, 7, 20, 17, 22, "j")
    hline(im, 7, 17, 21, "i")
    # the rim and the water inside
    for y in range(9, 15):
        for x in range(N):
            d = ((x - cx) / 11) ** 2 + ((y - 12) / 3.2) ** 2
            if d <= 1:
                put(im, x, y, "k" if d > 0.62 else "7")
                if d > 0.62 and y <= 11:
                    put(im, x, y, "l")
    for x, y in ((8, 12), (9, 13), (10, 13), (11, 13), (12, 13), (13, 13), (14, 12)):
        put(im, x, y, "9")  # the ripple, smiling
    put(im, 11, 11, "8")
    # the drop
    stamp(im, grid(["..0..", ".0H0.", "0HGF0", "0GFF0", ".000."]), 9, 0)
    # a streak of lamp light on the plastic
    vline(im, 4, 14, 17, "l")
    im = outline_dark(im)
    return done(im, "empty-basin.png")


def outline_dark(im):
    """A dark rim around a picture's shape, inside its box (no growing)."""
    out = im.copy()
    m = mask_of(im)
    for y in range(im.height):
        for x in range(im.width):
            if m[y][x]:
                continue
            if any(0 <= x + dx < im.width and 0 <= y + dy < im.height and m[y + dy][x + dx]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out.putpixel((x, y), rgb("0"))
    return out


def tv_slot():
    """watch.tv.bezel, 40 × 30 (4 × at the 160 px it is shown): the changing room's TV on its
    cabinet, a lace doily, rabbit ears, a camellia in a milk bottle."""
    im = new(40, 30)
    stamp(im, grid(TV), 8, 2)
    # the doily on top
    for x in range(12, 26):
        put(im, x, 7, "W" if x % 2 else "h")
    # a camellia in a milk bottle beside the ears
    stamp(im, grid([".xx.", "xyxr", ".rs.", "..s.", ".0h0", "0hh0", "0WW0", "0hh0", "0000"]), 31, 13)
    # the cabinet it stands on
    rect(im, 4, 22, 36, 30, "c")
    hline(im, 4, 36, 22, "f")
    hline(im, 4, 36, 23, "e")
    vline(im, 20, 24, 30, "b")
    put(im, 18, 26, "g")
    put(im, 22, 26, "g")
    vline(im, 4, 22, 30, "0")
    vline(im, 35, 22, 30, "0")
    return done(im, "tv.png")


MASSAGE_CHAIR = [  # the coin massage chair, red vinyl and cream piping (16 × 20)
    "...0000000000...",
    "..0wxxxxxxxxw0..",
    "..0xyyxxxxxxx0..",
    "..0xyxxxxxxxx0..",
    "..0xxxxxxxxxx0..",
    "..0xxxxxxxxxx0..",
    "..0xxxxxxxxxx0..",
    "..0wxxxxxxxxw0..",
    "000hwwwwwwwwh000",
    "0ww0xxxxxxxxx0w0",
    "0xy0xxxxxxxxx0x0",
    "0ww0000000000ww0",
    "0wwxxxxxxxxxxww0",
    "0wwwwwwwwwwwwww0",
    ".0bbbbbbbbbbbb0.",
    ".0bl0bbbbbbb0b0.",
    ".0b0........0b0.",
    ".00..........00.",
]
FAN = [  # a standing electric fan in its round cage (13 × 20)
    "....00000....",
    "..009G9G900..",
    ".0G9GG9GG9G0.",
    ".09GG888GG90.",
    "0G9G80008G9G0",
    "09GG80x08GG90",
    "0G9G80008G9G0",
    ".09GG888GG90.",
    ".0G9GG9GG9G0.",
    "..009G9G900..",
    "....00000....",
    "......08.....",
    "......08.....",
    "......08.....",
    "......08.....",
    "......08.....",
    "......08.....",
    "....00800....",
    "..088888880..",
    "..000000000..",
]
KAGO = [  # a rattan clothes basket with a folded yukata (14 × 7)
    "..NNNONNNN....",
    ".NOONNNNONN...",
    "0fefefefefefe0",
    "0efefefefefef0",
    "0fefefefefefe0",
    ".0efefefefef0.",
    "..0000000000..",
]


MASSAGE_CHAIR_L = grid([  # the coin massage chair: headrest, arms, control box, footrest (22 × 26)
    "......00000000........",
    ".....0wxxxxxxw0.......",
    ".....0xyyyyyxw0.......",
    ".....0xyxxxxxw0.......",
    ".....0wwwwwwww0.......",
    "....0xxxxxxxxxx0......",
    "....0xyxxxxxxxw0......",
    "....0xyxxxxxxxw0......",
    "....0xxxxxxxxxw0......",
    "....0xxhxxxxhxw0......",
    "....0xxxxxxxxxw0......",
    "....0xxhxxxxhxw0......",
    "...00xxxxxxxxxw000....",
    "..0w0wwwwwwwwww0x0....",
    "..0x0xxxxxxxxxx0xw0...",
    "..0x0xyxxxxxxxw0x00...",
    "000000000000000000....",
    "0333330000000000000...",
    "03x9D30xxxxxxxxxxw0...",
    "0333330wwwwwwwwwww0...",
    "0000000bbbbbbbbbb000..",
    ".....0bb0.....0bxxxw0.",
    ".....0b0.......0xyxxw0",
    ".....000........0xxxw0",
    "................000000",
])
CRANE = grid([  # a paper crane folded from a receipt, wings up (11 × 7)
    "h.........h",
    "Gh.......hG",
    ".Gh.....hG.",
    "..Ghhhhhh..",
    ".h.hGGGh.h.",
    "h...hGh...h",
    ".....h.....",
])


def space_room():
    """space.room.scene, 100 × 45 (4 × at 400 × 180): the changing room after hours. Your locker
    door stands open, a red towel over its edge; a paper crane on top; the coin massage chair
    with its control box and footrest; the fan, the scale; a bench in front with a basket and
    a yukata; one pendant lamp and its pool of light."""
    W, H = 100, 45
    im = new(W, H, "2")
    wall_tile(im, (0, 0, W, 30), seed=6)
    hline(im, 0, W, 0, "0")
    hline(im, 0, W, 3, "f")
    hline(im, 0, W, 4, "d")
    hline(im, 0, W, 5, "b")
    # the lamp's cone on the wall
    lx = 58
    for y in range(9, 30):
        half = 2 + (y - 9) * 0.8
        for x in range(int(lx - half), int(lx + half) + 1):
            p = get(im, x, y)[:3] if 0 <= x < W else None
            if p == rgb("2")[:3] and dith(1 - abs(x - lx) / (half + 1) * 0.6, x, y):
                put(im, x, y, "3")
    # the wainscot and the wooden floor
    rect(im, 0, 26, W, 33, "c")
    hline(im, 0, W, 26, "f")
    hline(im, 0, W, 27, "e")
    for x in range(3, W, 7):
        vline(im, x, 28, 33, "b")
    rect(im, 0, 33, W, H, "d")
    hline(im, 0, W, 33, "b")
    for y in (37, 41):
        hline(im, 0, W, y, "c")
    for x in range(4, W, 13):
        vline(im, x, 34, 37, "c")
        vline(im, x + 6, 38, 41, "c")
    for x in range(30, 86):  # the lamp's pool on the boards
        t = 1 - abs(x - 58) / 28
        if dith(t * 0.8, x, 35) or dith(t * 0.5, x, 36):
            put(im, x, 35 if dith(t * 0.8, x, 35) else 36, "e")
    # the lockers, left: six doors, yours (top middle) swung open
    rect(im, 2, 8, 38, 33, "a")
    for r in range(2):
        for c in range(3):
            x0, y0 = 3 + c * 12, 9 + r * 12
            if (r, c) == (0, 1):
                rect(im, x0, y0, x0 + 11, y0 + 11, "0")      # the open locker: dark inside
                stamp(im, grid(["0000000", "0NNONN0", "0ffeff0", "0efefe0"]), x0 + 2, y0 + 6)
                continue
            rect(im, x0, y0, x0 + 11, y0 + 11, "c")
            hline(im, x0, x0 + 11, y0, "d")
            vline(im, x0, y0, y0 + 11, "d")
            for vx_ in (x0 + 2, x0 + 5):
                hline(im, vx_, vx_ + 2, y0 + 2, "a")
            rect(im, x0 + 8, y0 + 5, x0 + 10, y0 + 7, "j")
            rect(im, x0 + 8, y0 + 7, x0 + 10, y0 + 10, "e")
    # your locker's door, swung out toward us: its inner side, thinner, the towel over its edge
    poly(im, [(26, 8), (30, 7), (30, 23), (26, 21)], "d")
    vline(im, 26, 8, 21, "e")
    vline(im, 30, 7, 23, "b")
    stamp(im, grid([".xxxxx", "xyxxxw", "xxxxxw", "xhhhhw", "xxxxxw", "xxxxxw", "wwwwww"]), 25, 6)
    # the crane on top of the lockers
    stamp(im, CRANE, 6, 1)
    # the massage chair, the fan, the scale
    stamp(im, MASSAGE_CHAIR_L, 42, 11)
    stamp(im, grid(FAN), 68, 16)
    stamp(im, grid(SCALE), 82, 10)
    # the pendant lamp
    vline(im, lx, 5, 8, "0")
    stamp(im, grid(["..000..", ".0ccc0.", "0deeed0", "0000000", ".lWWWl."]), lx - 3, 8)
    # a bench in front, a basket with a yukata and a towel on it
    rect(im, 12, 37, 72, 39, "e")
    hline(im, 12, 72, 37, "g")
    hline(im, 12, 72, 39, "c")
    for bx in (14, 68):
        rect(im, bx, 40, bx + 2, 44, "c")
    stamp(im, grid(KAGO), 18, 30)
    stamp(im, grid(["hhhhhh", "999999", "hhhhhW"]), 40, 34)
    stamp(im, grid(STOOL), 86, 38)
    stamp(im, grid(BASIN), 86, 35)
    return done(im, "changing-room.png")


def nowbar_frame():
    """nowbar.surface, a 9-slice frame (12 × 12 drawn, 4 ×, slice 16): the Now bar as a strip of
    vermilion lacquer with a brass rim lit from the top left and pixel-cut corners."""
    N = 12
    im = new(N, N)
    for y in range(N):
        for x in range(N):
            ex = min(x, N - 1 - x)
            ey = min(y, N - 1 - y)
            if ex + ey < 2:
                continue  # the cut corner
            e = min(ex, ey)
            if ex + ey == 2 or e == 0:
                ch = "u"
            elif e == 1:
                top_left = (y <= x and y < N / 2) or (x < y and x < N / 2)
                ch = "e" if top_left else "c"
            elif e == 2:
                ch = "u" if (y == N - 3 or x == N - 3) else "w"
            else:
                ch = "v"
            put(im, x, y, ch)
    return done(im, "nowbar-frame.png", 4)


def sheet_frame():
    """sheet.surface, a 9-slice (9 × 9 drawn, 4 ×, slice 12): every sheet and dialog opens under
    a noren's hem, a band of deep vermilion along its top edge; the rest is the sheet's tile."""
    im = new(9, 9)
    hline(im, 0, 9, 0, "w")
    hline(im, 0, 9, 1, "v")
    hline(im, 0, 9, 2, "u")
    return done(im, "sheet-hem.png", 4)


CAT_AWAKE = [  # head up, eyes open (13 × 9)
    ".0.0.........",
    "0h0h0........",
    "0hhhh0.00000.",
    "0W0W0h0hoooh0",
    "0hhxh0hoo11h0",
    ".0hh0hhhhh1h0",
    "..0hhhhhhhhh0",
    "..0ooooooooo0",
    "...000000000.",
]
CAT_STRETCH = [  # front paws out, rear up, tail high (18 × 9)
    "...............00.",
    "..............0o0.",
    "..........00000o0.",
    ".0.0.....0hhhhoo0.",
    "0h0h0..00hhooohh0.",
    "0hh0h00hhhhoo11h0.",
    "0h0h0hhhhhhhh11h0.",
    "00hh0hhhhhh00hh0..",
    "0000000.....0hh0..",
]
CAT_YAWN = [  # sitting up, a big yawn (12 × 12)
    ".0...0......",
    "0h0.0h0.....",
    "0hhhhh0.....",
    "0h0h0h0.....",
    "0hhxhh0.....",
    "0hxxxh0.....",
    ".0hhh0......",
    "0hhoo0......",
    "0hooo10...00",
    "0hhhh110.0o0",
    "0hhhhhh10o0.",
    ".0hh0hh000..",
]


def rail_foot_pieces():
    """rail-foot layers (the box just above Ask Nox, so they sit still on any screen): the milk
    fridge with its basins, its light humming (3 frames), and the bathhouse cat asleep on a bench
    beside it, flicking its tail now and then (6 frames). Both answer a click: the fridge's door
    swings open, a bottle clinks and caps pop; the cat wakes, stretches, yawns and curls up again."""
    # ---- the fridge, 29 × 32, anchored bottom-left
    FW, FH = 29, 32

    def fridge(light=0, door=0.0, clink=False):
        fr = new(FW, FH)
        body = grid(FRIDGE)
        if light == 1:
            body = recolour(body, {"G": "F"})
        elif light == 2:
            body = recolour(body, {"H": "W"})
        if door > 0:  # open: the glass door narrows toward its hinge on the left
            inside = recolour(body.crop((2, 2, 14, 19)), {"G": "W", "H": "W", "7": "8"})
            if clink:  # a bottle knocked up a pixel as the door swings
                col = inside.crop((5, 9, 7, 13))
                inside.paste(new(2, 4, "W"), (5, 9))
                inside.alpha_composite(col, (5, 8))
            body.paste(inside, (2, 2))
            dw = max(1, int(round(12 * (1 - door))))
            for y in range(2, 19):
                for x in range(dw):
                    put(body, 2 + x, y, "9" if x in (0, dw - 1) else "G")
            vline(body, 1, 1, 20, "0")
        fr.alpha_composite(body, (1, FH - 26))
        # on top: a folded towel and a fruit milk
        stamp(fr, grid(["hhhhhhh.", "EEEEEEEh", "hhhhhhhh"]), 3, FH - 29)
        stamp(fr, grid(["0hh0", "0oo0", "0hh0"]), 12, FH - 30)
        # beside it: a stool with a stack of basins
        stamp(fr, grid(STOOL), 18, FH - 6)
        for i in range(3):
            stamp(fr, grid(BASIN), 18, FH - 10 - i * 3)
        return fr

    idle = new(FW * 3, FH)
    for f in range(3):
        idle.alpha_composite(fridge(light=f), (f * FW, 0))
    done(idle, "foot-fridge.png")
    opens = [0.3, 0.7, 1.0, 1.0, 1.0, 1.0, 0.7, 0.3, 0.0, 0.0]
    poke = new(FW * len(opens), FH)
    for f, o in enumerate(opens):
        poke.alpha_composite(fridge(door=o, clink=f in (3, 4)), (f * FW, 0))
    done(poke, "foot-fridge-open.png")
    done(grid([".00.", "0hh0", "0hx0", ".00."]), "bit-cap.png")
    # ---- the cat on its bench, 22 × 20, anchored bottom-right
    CW, CH = 22, 20

    def bench(fr):
        rect(fr, 1, CH - 6, CW - 1, CH - 4, "e")
        hline(fr, 1, CW - 1, CH - 6, "g")
        hline(fr, 1, CW - 1, CH - 4, "c")
        for lx in (2, CW - 4):
            rect(fr, lx, CH - 3, lx + 2, CH, "c")
        stamp(fr, grid(["hhhhhhhhhhhhhh", "99999999999999"]), 3, CH - 8)  # its towel

    tails = [[(17, 11)], [(17, 11)], [(17, 11)], [(17, 10), (18, 9)], [(17, 10), (17, 9), (18, 8)],
             [(17, 10)]]
    idle = new(CW * 6, CH)
    for f, tail in enumerate(tails):
        fr = new(CW, CH)
        bench(fr)
        stamp(fr, CAT_SLEEP, 4, CH - 15)
        for x, y in tail:  # the tail's tip, lifting and dropping
            put(fr, x, y, "o")
            put(fr, x + 1, y, "0")
            put(fr, x, y - 1, "0")
        idle.alpha_composite(fr, (f * CW, 0))
    done(idle, "foot-cat.png")
    poses = [(CAT_AWAKE, 4, CH - 16), (CAT_AWAKE, 4, CH - 16), (CAT_STRETCH, 2, CH - 16),
             (CAT_STRETCH, 2, CH - 16), (CAT_STRETCH, 2, CH - 16), (CAT_YAWN, 6, CH - 19),
             (CAT_YAWN, 6, CH - 19), (CAT_AWAKE, 4, CH - 16), (CAT_SLEEP, 4, CH - 15),
             (CAT_SLEEP, 4, CH - 15)]
    poke = new(CW * len(poses), CH)
    for f, (pose, x, y) in enumerate(poses):
        fr = new(CW, CH)
        bench(fr)
        stamp(fr, grid(pose) if isinstance(pose, list) else pose, x, y)
        poke.alpha_composite(fr, (f * CW, 0))
    done(poke, "foot-cat-wakes.png")


PIECES = {
    "mural": page_mural,
    "hero": hero_hall,
    "beam": status_beam,
    "cat": cat_walk,
    "textures": textures,
    "steam": page_steam,
    "deck": deck_dial,
    "noren": noren,
    "herosteam": hero_steam,
    "heroground": hero_ground,
    "footpieces": rail_foot_pieces,
    "railwall": rail_wall,
    "dock": dock_shelf,
    "crest": crest,
    "empty": empty_basin,
    "tv": tv_slot,
    "space": space_room,
    "nowbar": nowbar_frame,
    "sheet": sheet_frame,
}

def banners_v2():
    """The header banners live in banners.py, beside this file."""
    sys.path.insert(0, str(Path(__file__).parent))
    import banners as b

    b.banners()


def sprites():
    """The pixel pieces (sprites.json) live in pieces.py, beside this file."""
    sys.path.insert(0, str(Path(__file__).parent))
    import pieces

    pieces.main()


PIECES["sprites"] = sprites
PIECES["banners"] = banners_v2

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PIECES)
    for name in wanted:
        PIECES[name]()
