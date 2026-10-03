"""Millennium Skin: every picture, by code. Run from the repository root:

    python3 docs/design/themes/y2k/make.py            # everything
    python3 docs/design/themes/y2k/make.py skins sky  # some groups

Groups: skins (9-slice frames, pixel 2x), pieces (spectrum, sparkle, LED), sky (page pictures,
clouds, flare), renders (Blender: hero, crest, empty toy, TV, room). Writes themes/y2k/art/.
The sprites (sprites.json) come from sprites_src.py, the tokens from tokens_src.py, the manifest
from manifest.py.

Pixel art is drawn at 1x and scaled by 2, the theme's one pixel size. Shared frames use chrome
that reads on both skins (dark gunmetal and light ice): outline, highlight top-left, shadow
bottom-right (the theme's one light)."""

import math
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "themes/_kit/art"))
from pixel import rgba, save, scale, sheet  # noqa: E402
from svg import render  # noqa: E402

ART = ROOT / "themes/y2k/art"
PX = 2  # the theme's one pixel size

# The chrome ramp (hue-shifted: shadows toward navy-violet, lights toward ice) and the LCD.
O = "#0b0d1c"  # outline
S = "#34385a"  # chrome shadow
D = "#5b6190"  # chrome dark
M = "#949cc4"  # chrome mid
L = "#c8cfec"  # chrome light
H = "#f5f7ff"  # glint
G = "#8dff6a"  # LCD lit
g = "#2f6b2c"  # LCD dim
Y = "#f4f06a"  # lemon segment
R = "#ff5a6e"  # red segment
T = (0, 0, 0, 0)


def grain(path, amount=4, seed=1):
    """Additive monochrome grain (+-amount levels) on a saved picture, so flat fills are not
    plastic. (The kit's add_grain blends toward mid-grey, which washes a picture out.)"""
    import numpy as np

    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.int16)
    rng = np.random.default_rng(seed)
    n = rng.normal(0, amount, a.shape[:2]).astype(np.int16)[..., None]
    a[..., :3] = np.clip(a[..., :3] + n, 0, 255)
    out = Image.fromarray(a.astype("uint8"), "RGBA")
    if out.getchannel("A").getextrema() == (255, 255):
        out = out.convert("RGB")
    out.save(path, quality=86, method=6)


def img(w, h):
    return Image.new("RGBA", (w, h), T)


def put(im, x, y, c):
    if 0 <= x < im.width and 0 <= y < im.height:
        im.putpixel((x, y), rgba(c))


def hline(im, x0, x1, y, c):
    for x in range(x0, x1 + 1):
        put(im, x, y, c)


def vline(im, x, y0, y1, c):
    for y in range(y0, y1 + 1):
        put(im, x, y, c)


def rivet(im, x, y):
    """A 3x3 chrome rivet: lit top-left, shadowed bottom-right."""
    for dx, dy, c in ((0, 0, L), (1, 0, M), (2, 0, D), (0, 1, M), (1, 1, H), (2, 1, S), (0, 2, D), (1, 2, S), (2, 2, O)):
        put(im, x + dx, y + dy, c)


# ------------------------------------------------------------------------------------------ skins
# The main window's two skins: gunmetal by night, Bondi plastic by day. Keys: O outline, BH body
# glint, B body, BS body shadow, TB title-bar base, RH/RD grip ridges, WD/WL the sunken LCD well's
# dark top-left and lit bottom-right edges, F the LCD glass (about 94 % opaque).
DECK = {
    "": {"O": "#06080f", "BH": "#626a96", "B": "#2c3152", "BS": "#12152a", "TB": "#3c4371",
         "RH": "#b3bbe2", "RD": "#161a31", "WD": "#020306", "WL": "#555c86", "F": (8, 15, 13, 240)},
    "-bondi": {"O": "#1b3a72", "BH": "#ffffff", "B": "#5bbad9", "BS": "#1f6c94", "TB": "#8cd3ea",
               "RH": "#ffffff", "RD": "#2a82aa", "WD": "#2b6e92", "WL": "#ffffff", "F": (236, 248, 246, 242)},
}  # fmt: skip
DECK_N, DECK_S, BAR = 36, 12, 9  # the box at 1x, its corner, the title bar's rows (18 px)


def deck_rows(c, n=DECK_N):
    """The main window at 1x (n x n): title bar rows 0-8 (outline, glint, two grip-ridge pairs,
    shadow), a lit LED in the left cap, a rivet in the right, a 2 px bevelled body, a sunken LCD
    well from row 9, the LCD glass filling the middle."""
    im = img(n, n)
    last = n - 1
    for y in range(n):
        for x in range(n):
            put(im, x, y, c["F"])
    # Title bar.
    hline(im, 0, last, 0, c["O"])
    hline(im, 1, last - 1, 1, c["BH"])
    for y, k in ((2, "TB"), (3, "RH"), (4, "RD"), (5, "RH"), (6, "RD"), (7, "TB"), (8, "BS")):
        hline(im, 1, last - 1, y, c[k])
    for x in list(range(1, 7)) + list(range(last - 6, last)):
        for y in range(2, 8):
            put(im, x, y, c["TB"])
    vline(im, 7, 2, 7, c["RD"])
    vline(im, last - 7, 2, 7, c["RD"])
    for x, y in ((3, 4), (4, 4), (3, 5), (4, 5)):
        put(im, x, y, G)
    put(im, 3, 4, "#e2ffd6")
    # The LED sits in a sunken socket: dark top-left, lit bottom-right.
    for x, y in ((2, 3), (3, 3), (4, 3), (2, 4), (2, 5)):
        put(im, x, y, c["O"])
    for x, y in ((5, 3), (5, 4), (5, 5), (5, 6), (2, 6), (3, 6), (4, 6)):
        put(im, x, y, c["BH"])
    rv = last - 5
    for dx, dy, k in ((0, 0, "BH"), (1, 0, "BH"), (2, 0, "RD"), (0, 1, "BH"), (1, 1, "RH"), (2, 1, "O"), (0, 2, "RD"), (1, 2, "O"), (2, 2, "O")):
        put(im, rv + dx, 3 + dy, c[k])
    # Body: outline, glint, body, then the well's dark edge (left); the well's lit edge, body,
    # shadow, outline (right); the same at the bottom.
    for y in range(1, last):
        put(im, 0, y, c["O"])
        put(im, last, y, c["O"])
    for y in range(BAR, last):
        put(im, 1, y, c["BH"])
        for x in (2, 3, 4):
            put(im, x, y, c["B"])
        put(im, last - 1, y, c["BS"])
        for x in (last - 4, last - 3, last - 2):
            put(im, x, y, c["B"])
    for x in range(1, last):
        for y in (last - 4, last - 3, last - 2):
            put(im, x, y, c["B"])
        put(im, x, last - 1, c["BS"])
    hline(im, 0, last, last, c["O"])
    put(im, 1, last - 1, c["B"])
    # The sunken well.
    hline(im, 5, last - 5, BAR, c["WD"])
    vline(im, 5, BAR, last - 5, c["WD"])
    hline(im, 6, last - 5, last - 5, c["WL"])
    vline(im, last - 5, BAR + 1, last - 5, c["WL"])
    return im


def deck_skin():
    """The music deck: a Winamp-2-era main window (see deck_rows), for the current palette."""
    return scale(deck_rows(DECK[CURRENT]), PX), DECK_S * PX


CURRENT = ""


def rail_skin():
    """The rail: a playlist window. The same bar and bevels, a longer ridge run, rivets at both
    ends, and a thin foot rail."""
    n, s = 36, 12
    im = img(n, n)
    last = n - 1
    hline(im, 0, last, 0, O)
    hline(im, 1, last - 1, 1, H)
    for y, c in ((2, L), (3, S), (4, L), (5, S)):
        hline(im, 1, last - 1, y, c)
    hline(im, 1, last - 1, 6, O)
    for x in range(1, 6):
        for y in range(2, 6):
            put(im, x, y, M if x > 1 else H)
    for x in range(last - 5, last):
        for y in range(2, 6):
            put(im, x, y, M if x < last - 1 else D)
    vline(im, 6, 2, 5, O)
    vline(im, last - 6, 2, 5, O)
    rivet(im, 2, 2)
    rivet(im, last - 4, 2)
    for y in range(1, last):
        put(im, 0, y, O)
        put(im, last, y, O)
    for y in range(7, last - 1):
        put(im, 1, y, H)
        put(im, last - 1, y, D)
    hline(im, 1, last - 1, last - 1, D)
    hline(im, 0, last, last, O)
    return scale(im, PX), s * PX


def panel_skin():
    """Panels and sheets: a quieter window. Translucent ridges (white and navy at part strength)
    so the same frame reads on gunmetal and on ice: a title band 6 px, 2 px bevelled sides."""
    n, s = 24, 8
    im = img(n, n)
    last = n - 1
    hi, lo, lo2 = (255, 255, 255, 150), (10, 12, 30, 150), (10, 12, 30, 90)
    ridge_hi, ridge_lo = "#8c94be", "#11142a"
    hline(im, 0, last, 0, hi)
    for y, c in ((1, ridge_hi), (2, ridge_lo), (3, ridge_hi), (4, ridge_lo)):
        hline(im, 4, last - 4, y, c)
    # Rivets at both ends of the band.
    for x0 in (1, last - 3):
        for dx, dy, c in ((0, 1, (255, 255, 255, 170)), (1, 1, (255, 255, 255, 120)), (2, 1, lo), (0, 2, (255, 255, 255, 120)),
                          (1, 2, (255, 255, 255, 220)), (2, 2, lo), (0, 3, lo2), (1, 3, lo), (2, 3, lo)):  # fmt: skip
            put(im, x0 + dx, dy, c)
    hline(im, 1, last - 1, 5, lo2)
    for y in range(1, last):
        put(im, 0, y, hi)
        put(im, last, y, lo)
    hline(im, 1, last, last, lo)
    return scale(im, PX), s * PX


def panel_skin_light():
    """Panels and sheets by day: white and Bondi grip ridges, rivets, a chrome rim lit top-left."""
    n, s = 24, 8
    im = img(n, n)
    last = n - 1
    rim_hi, rim_lo = "#ffffff", "#7d8cb4"
    hline(im, 0, last, 0, rim_hi)
    for y, c in ((1, "#ffffff"), (2, "#3d95bd"), (3, "#ffffff"), (4, "#3d95bd")):
        hline(im, 4, last - 4, y, c)
    for x0 in (1, last - 3):
        for dx, dy, c in ((0, 1, "#ffffff"), (1, 1, "#d8f1fa"), (2, 1, "#2a6f93"), (0, 2, "#d8f1fa"),
                          (1, 2, "#ffffff"), (2, 2, "#2a6f93"), (0, 3, "#2a6f93"), (1, 3, "#2a6f93"), (2, 3, "#1b3a72")):  # fmt: skip
            put(im, x0 + dx, dy, c)
    hline(im, 1, last - 1, 5, (125, 140, 180, 120))
    for y in range(1, last):
        put(im, 0, y, rim_hi)
        put(im, last, y, rim_lo)
    hline(im, 1, last, last, rim_lo)
    return scale(im, PX), s * PX


def nowbar_skin():
    """The Now bar: a mini-player strip. Ridged end caps left and right, a glint along the top,
    a shadow along the bottom."""
    n, s = 18, 6
    im = img(n, n)
    last = n - 1
    hline(im, 0, last, 0, O)
    hline(im, 0, last, last, O)
    hline(im, 1, last - 1, 1, H)
    hline(im, 1, last - 1, last - 1, D)
    for y in range(1, last):
        put(im, 0, y, O)
        put(im, last, y, O)
    for y in range(2, last - 1):
        for x, c in ((1, H), (2, S), (3, L), (4, S)):
            put(im, x, y, c)
        for x, c in ((last - 4, L), (last - 3, S), (last - 2, L), (last - 1, S)):
            put(im, x, y, c)
    return scale(im, PX), s * PX


def dock_skin():
    """The dock: a chrome lip along its top (the button row of a player)."""
    n, s = 12, 4
    im = img(n, n)
    for x in range(n):
        put(im, x, 0, O)
        put(im, x, 1, H)
        put(im, x, 2, M)
        put(im, x, 3, D)
    return scale(im, PX), s * PX


# ----------------------------------------------------------------------------------------- pieces
def spectrum(suffix=""):
    """The title bar's visualiser: a run of the main window's grip ridges (30 x 9 at 1x) with a
    sunken LCD strip set into them, 5 bars dancing green, lemon and red. 8 frames; laid exactly
    over the skin (anchor top-right, scale 2)."""
    c = DECK[suffix]
    rng = random.Random(7)
    # The deck's layers sit inside its 16 px side padding, so the strip ends at the right cap's
    # separator (8 px at 1x from the edge) and is pure ridge run: it lines up with the skin.
    whole = deck_rows(c, 64)
    corner = whole.crop((64 - 8 - 30, 0, 64 - 8, BAR))
    base = [3, 4, 2, 4, 3]
    frames = []
    for f in range(8):
        im = corner.copy()
        x0, x1 = 11, 27
        hline(im, x0, x1, 2, c["WD"])
        vline(im, x0, 2, 7, c["WD"])
        hline(im, x0 + 1, x1, 7, c["WL"])
        vline(im, x1, 3, 7, c["WL"])
        for x in range(x0 + 1, x1):
            for y in range(3, 7):
                put(im, x, y, "#050b09")
        for i in range(5):
            h = max(1, min(4, base[i] + rng.choice((-2, -1, 0, 1, 1))))
            x = x0 + 1 + i * 3
            for level in range(4):
                y = 6 - level
                colour = (R if level == 3 else Y if level == 2 else G) if level < h else "#173222"
                put(im, x, y, colour)
                put(im, x + 1, y, colour)
        frames.append(im)
    return sheet(frames)


def gleam():
    """A slow gleam for Home's picture: a soft slanted band of light (screen blend)."""
    w, h = 220, 520
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#000"/><stop offset="0.45" stop-color="#9fb8ff"/>
<stop offset="0.5" stop-color="#ffffff"/><stop offset="0.55" stop-color="#9fb8ff"/><stop offset="1" stop-color="#000"/></linearGradient>
<filter id="b"><feGaussianBlur stdDeviation="10"/></filter></defs>
<rect width="{w}" height="{h}" fill="#000"/>
<g filter="url(#b)"><polygon points="90,0 150,0 130,{h} 70,{h}" fill="url(#g)"/></g>
</svg>'''
    render(svg, ART / "gleam.webp", w, h)


def rail_led():
    """The playlist window's power LED, over the rivet of the rail's right cap (12x8 at 1x, the
    skin's own corner): lit, then a blink every four seconds (8 frames at 2 fps)."""
    frames = []
    for f in range(8):
        im = img(12, 8)
        lit = f != 7
        for x, y in ((7, 2), (8, 2), (7, 3), (8, 3)):
            put(im, x, y, G if lit else g)
        put(im, 7, 2, "#d8ffc8" if lit else "#3f7a3a")
        for x, y in ((9, 2), (9, 3), (7, 4), (8, 4), (9, 4)):
            put(im, x, y, O)
        frames.append(im)
    return sheet(frames)


def sparkle():
    """A four-point sparkle, 9x9 at 1x: a white core, ice arms, a lilac edge (reads on both)."""
    rows = [
        "....a....",
        "....b....",
        "....c....",
        "...bcb...",
        "abccwccba",
        "...bcb...",
        "....c....",
        "....b....",
        "....a....",
    ]
    legend = {"a": (150, 120, 230, 150), "b": (170, 190, 255, 230), "c": "#e6eeff", "w": "#ffffff"}
    im = img(9, 9)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in legend:
                put(im, x, y, legend[ch])
    return im


# -------------------------------------------------------------------------------------------- sky
def page_night():
    """Dark: a perspective matrix grid on a night floor, a far horizon glow, faint stars, and the
    soft haze of a lens flare low at the right. Calm: text sits over it."""
    w, h = 1600, 900
    hy = 540  # the horizon
    lines = []
    # Horizontal lines, closer together toward the horizon.
    for i in range(1, 26):
        t = i / 25
        y = hy + (h - hy) * (t ** 2.2)
        op = 0.08 + 0.32 * t
        lines.append(f'<line x1="0" y1="{y:.1f}" x2="{w}" y2="{y:.1f}" stroke="#6ad7ff" stroke-opacity="{op:.2f}" stroke-width="{1 + t * 0.6:.2f}"/>')
    # Rays to the vanishing point.
    vx = w * 0.62
    for i in range(-90, 91):  # well past both edges: no wedge, no seam
        x = vx + i * 110
        # Shallow rays (far to the side) fade out, so they never pile into a band at the horizon.
        op = 0.26 * min(1.0, (1500 / max(1, abs(i * 110))) ** 1.6)
        lines.append(f'<line x1="{vx:.1f}" y1="{hy}" x2="{x:.1f}" y2="{h}" stroke="#6ad7ff" stroke-opacity="{op:.3f}" stroke-width="1.1"/>')
    rng = random.Random(3)
    stars = "".join(
        f'<circle cx="{rng.uniform(0, w):.0f}" cy="{rng.uniform(0, hy - 60) ** 1.0:.0f}" r="{rng.choice((0.7, 0.9, 1.2, 1.6))}" fill="#dfe8ff" fill-opacity="{rng.uniform(0.25, 0.7):.2f}"/>'
        for _ in range(140)
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs>
 <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#070a1c"/><stop offset="0.45" stop-color="#0c1030"/>
  <stop offset="0.6" stop-color="#1c1450"/><stop offset="1" stop-color="#1c1450"/>
 </linearGradient>
 <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#16103e"/><stop offset="1" stop-color="#060818"/>
 </linearGradient>
 <radialGradient id="glow" cx="0.62" cy="0.6" r="0.5" gradientTransform="translate(0.31 0.3) scale(0.5 0.5) translate(-0.31 -0.3)">
  <stop offset="0" stop-color="#b98cff" stop-opacity="0.55"/><stop offset="0.4" stop-color="#6a4cff" stop-opacity="0.18"/>
  <stop offset="1" stop-color="#6a4cff" stop-opacity="0"/>
 </radialGradient>
 <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0" stop-color="#ffffff" stop-opacity="0.9"/><stop offset="0.08" stop-color="#cfe6ff" stop-opacity="0.45"/>
  <stop offset="0.35" stop-color="#7fa8ff" stop-opacity="0.1"/><stop offset="1" stop-color="#7fa8ff" stop-opacity="0"/>
 </radialGradient>
 <linearGradient id="streak" x1="0" x2="1"><stop offset="0" stop-color="#9fc4ff" stop-opacity="0"/>
  <stop offset="0.5" stop-color="#eaf4ff" stop-opacity="0.8"/><stop offset="1" stop-color="#9fc4ff" stop-opacity="0"/></linearGradient>
 <linearGradient id="streakv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9fc4ff" stop-opacity="0"/>
  <stop offset="0.5" stop-color="#eaf4ff" stop-opacity="0.6"/><stop offset="1" stop-color="#9fc4ff" stop-opacity="0"/></linearGradient>
 <filter id="soft"><feGaussianBlur stdDeviation="0.8"/></filter>
 <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#fff" stop-opacity="0.08"/><stop offset="0.12" stop-color="#fff" stop-opacity="0.75"/><stop offset="0.45" stop-color="#fff" stop-opacity="0.5"/><stop offset="1" stop-color="#fff" stop-opacity="0.2"/>
 </linearGradient>
 <mask id="gridfade"><rect x="0" y="{hy}" width="{w}" height="{h - hy}" fill="url(#fade)"/></mask>
</defs>
<rect width="{w}" height="{hy}" fill="url(#sky)"/>
<rect y="{hy}" width="{w}" height="{h - hy}" fill="url(#floor)"/>
{stars}
<ellipse cx="{vx}" cy="{hy}" rx="700" ry="200" fill="url(#glow)"/>
<g mask="url(#gridfade)">{''.join(lines)}</g>
<line x1="0" y1="{hy}" x2="{w}" y2="{hy}" stroke="#c9b6ff" stroke-opacity="0.28" stroke-width="1.2"/>
<g transform="translate(1340 190)">
 <circle r="120" fill="url(#halo)"/>
 <rect x="-300" y="-1" width="600" height="2" fill="url(#streak)" filter="url(#soft)"/>
 <rect x="-1" y="-70" width="2" height="140" fill="url(#streakv)" filter="url(#soft)"/>
 <circle r="46" fill="none" stroke="#9fc4ff" stroke-opacity="0.12" stroke-width="1.5"/>
 <polygon points="-150,52 -141,47 -132,52 -132,62 -141,67 -150,62" fill="#b48cff" fill-opacity="0.18"/>
 <circle cx="-230" cy="80" r="12" fill="#7fe0ff" fill-opacity="0.1"/>
</g>
</svg>'''
    render(svg, ART / "page-night.webp", w, h)
    grain(ART / "page-night.webp", 3, 4)


def cloud_svg(cx, cy, scale_, seed, shade="#b7a6ee", body="#ffffff"):
    """A puffy early-web cloud: overlapping domes on a flat base, lit top-left, lilac beneath."""
    rng = random.Random(seed)
    puffs = []
    x = -1.0
    while x < 1.0:
        r = rng.uniform(0.28, 0.5) * (1 - abs(x) * 0.45)
        puffs.append((x, -r * 0.55, r))
        x += r * rng.uniform(0.7, 1.0)
    # A second row of taller domes in the middle.
    for _ in range(3):
        xx = rng.uniform(-0.45, 0.45)
        r = rng.uniform(0.35, 0.55)
        puffs.append((xx, -r * 0.95, r))
    body_shapes = "".join(f'<circle cx="{cx + px * scale_:.1f}" cy="{cy + py * scale_:.1f}" r="{pr * scale_:.1f}"/>' for px, py, pr in puffs)
    base = f'<rect x="{cx - scale_ * 1.05:.1f}" y="{cy - scale_ * 0.25:.1f}" width="{scale_ * 2.1:.1f}" height="{scale_ * 0.25:.1f}" rx="{scale_ * 0.12:.1f}"/>'
    return f'''<g>
 <g fill="{shade}">{body_shapes}{base}</g>
 <g fill="{body}" transform="translate({-scale_ * 0.04:.1f} {-scale_ * 0.07:.1f})" filter="url(#soft)">{body_shapes}</g>
</g>'''


SKY_DEFS = '''<defs>
 <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="5"/></filter>
 <filter id="softer" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="14"/></filter>
</defs>'''


def page_sky():
    """Light: a lilac sky, pale at the bottom, with a few low puffy clouds and a sun glow at the
    top left (the theme's light). Pale enough for navy text anywhere."""
    w, h = 1600, 900
    clouds = "".join([
        cloud_svg(260, 760, 190, 1), cloud_svg(1250, 820, 240, 2), cloud_svg(820, 880, 150, 3),
        cloud_svg(1480, 330, 90, 4, shade="#c9bdf3"), cloud_svg(520, 250, 70, 5, shade="#cfc4f5"),
    ])  # fmt: skip
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
{SKY_DEFS}
<defs>
 <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#b9a8f0"/><stop offset="0.5" stop-color="#d7cdf8"/><stop offset="1" stop-color="#eee9ff"/>
 </linearGradient>
 <radialGradient id="sun" cx="0.1" cy="0.05" r="0.6">
  <stop offset="0" stop-color="#ffffff" stop-opacity="0.85"/><stop offset="0.35" stop-color="#ffffff" stop-opacity="0.25"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
 </radialGradient>
</defs>
<rect width="{w}" height="{h}" fill="url(#sky)"/>
<rect width="{w}" height="{h}" fill="url(#sun)"/>
<g opacity="0.9">{clouds}</g>
</svg>'''
    render(svg, ART / "page-sky.webp", w, h)
    grain(ART / "page-sky.webp", 3, 5)


def clouds_tile():
    """A seamless strip of small clouds that drifts across the page (repeat-x). Soft-light blend:
    clear by day, a faint haze by night."""
    w, h = 1200, 260
    parts = []
    for i, (cx, cy, sc) in enumerate(((140, 190, 70), (520, 150, 55), (860, 210, 85), (1130, 120, 40))):
        parts.append(cloud_svg(cx, cy, sc, 20 + i, shade="#cbbff5"))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{SKY_DEFS}{''.join(parts)}</svg>'''
    render(svg, ART / "clouds.webp", w, h)


def flare():
    """A lens flare that glides across now and then: a hot core, an anamorphic streak, a chain of
    hexagon ghosts. For a screen blend: black is nothing."""
    w, h = 640, 200
    hexes = []
    for i, (x, r, c, o) in enumerate(((430, 16, "#7fe0ff", 0.35), (500, 26, "#b48cff", 0.22), (560, 10, "#9dffb0", 0.3), (600, 34, "#ff9ad5", 0.14))):
        pts = " ".join(f"{x + r * math.cos(a * math.pi / 3):.1f},{100 + (x - 160) * 0.12 + r * math.sin(a * math.pi / 3):.1f}" for a in range(6))
        hexes.append(f'<polygon points="{pts}" fill="{c}" fill-opacity="{o}"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs>
 <radialGradient id="core"><stop offset="0" stop-color="#ffffff"/><stop offset="0.15" stop-color="#e6f6ff" stop-opacity="0.9"/><stop offset="0.5" stop-color="#6fb8ff" stop-opacity="0.25"/><stop offset="1" stop-color="#6fb8ff" stop-opacity="0"/></radialGradient>
 <linearGradient id="streak" x1="0" x2="1"><stop offset="0" stop-color="#7fb8ff" stop-opacity="0"/><stop offset="0.5" stop-color="#e8f4ff" stop-opacity="0.9"/><stop offset="1" stop-color="#7fb8ff" stop-opacity="0"/></linearGradient>
 <filter id="b"><feGaussianBlur stdDeviation="1.2"/></filter>
</defs>
<rect width="{w}" height="{h}" fill="#000"/>
<ellipse cx="160" cy="100" rx="90" ry="90" fill="url(#core)"/>
<rect x="0" y="98" width="{w * 0.62:.0f}" height="4" fill="url(#streak)" filter="url(#b)"/>
<g filter="url(#b)">{''.join(hexes)}</g>
</svg>'''
    render(svg, ART / "flare.webp", w, h)


# ---------------------------------------------------------------------------------------- renders
SCENES = ["scene_hero.py", "scene_crest.py", "scene_empty.py", "scene_tv.py", "scene_room.py"]


def renders(only=None):
    exe = str(Path.home() / ".local/bin/blender")
    for scene in SCENES:
        if only and scene not in only:
            continue
        for extra in ([], ["--", "--day"]) if scene == "scene_room.py" else ([],):
            subprocess.run([exe, "-b", "--factory-startup", "-P", str(HERE / scene), *extra], check=True, capture_output=True)
        print("rendered", scene)


CHROME = {"O": O, "S": S, "D": D, "M": M, "L": L, "H": H}
# Bondi: the same skins in clear blue plastic, a navy outline, white glints (the light scheme).
BONDI = {"O": "#22407a", "S": "#2a7ca4", "D": "#46a0c6", "M": "#8ed2e9", "L": "#c8eef8", "H": "#ffffff"}


def skins():
    global O, S, D, M, L, H, CURRENT
    for suffix, ramp in (("", CHROME), ("-bondi", BONDI)):
        O, S, D, M, L, H = (ramp[k] for k in "OSDMLH")
        CURRENT = suffix
        parts = {"deck": deck_skin(), "rail": rail_skin(), "nowbar": nowbar_skin(), "dock": dock_skin()}
        parts["panel"] = panel_skin() if not suffix else panel_skin_light()
        for part, (image, slice_) in parts.items():
            save(image, ART / f"skin-{part}{suffix}.png")
            print(f"skin-{part}{suffix}.png", image.size, "slice", slice_)
    O, S, D, M, L, H = (CHROME[k] for k in "OSDMLH")


def pieces():
    for suffix in ("", "-bondi"):
        save(spectrum(suffix), ART / f"spectrum{suffix}.png")
    gleam()
    save(sparkle(), ART / "sparkle.png")
    save(rail_led(), ART / "rail-led.png")


def sky():
    page_night()
    page_sky()
    clouds_tile()
    flare()


def spike(suffix=""):
    """The spectrum's poke: every bar jumps to the red, peaks hang, then they fall (6 frames)."""
    c = DECK[suffix]
    whole = deck_rows(c, 64)
    corner = whole.crop((64 - 8 - 30, 0, 64 - 8, BAR))
    frames = []
    for h in (4, 4, 3, 4, 2, 1):
        im = corner.copy()
        x0, x1 = 11, 27
        hline(im, x0, x1, 2, c["WD"])
        vline(im, x0, 2, 7, c["WD"])
        hline(im, x0 + 1, x1, 7, c["WL"])
        vline(im, x1, 3, 7, c["WL"])
        for x in range(x0 + 1, x1):
            for y in range(3, 7):
                put(im, x, y, "#050b09")
        for i in range(5):
            hh = max(1, h - (i % 2 if h < 4 else 0))
            x = x0 + 1 + i * 3
            for level in range(4):
                y = 6 - level
                colour = (R if level == 3 else Y if level == 2 else G) if level < hh else "#173222"
                put(im, x, y, colour)
                put(im, x + 1, y, colour)
        frames.append(im)
    return sheet(frames)


def bits():
    """The bits a poke throws: pixel hearts (the phone), sparkles (the star), lit LCD pixels (the
    egg). Drawn at 1x, saved at the theme's 2x."""
    heart = img(7, 6)
    rows = [".kk.kk.", "kpPkppk", "kpppppk", ".kpppk.", "..kpk..", "...k..."]
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                put(heart, x, y, {"k": "#3a0d2a", "p": "#ff5aa0", "P": "#ffd0e6"}[ch])
    save(scale(heart, PX), ART / "bit-heart.png")
    save(scale(sparkle(), PX), ART / "bit-sparkle.png")
    lcd = img(3, 3)
    for x in range(3):
        for y in range(3):
            put(lcd, x, y, "#8dff6a" if (x, y) != (0, 0) else "#e2ffd6")
    save(scale(lcd, PX), ART / "bit-lcd.png")


def pokes():
    """Render the poke frames (Blender) and stitch the pieces: phone.webp and phone-poke.webp
    (the rail foot's flip phone), star.webp and star-poke.webp (Home's chrome star), egg.webp and
    egg-poke.webp (the rail foot's keychain egg); the spectrum's spike sheets; the burst bits."""
    import os
    import tempfile

    exe = str(Path.home() / ".local/bin/blender")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "Y2K_FRAMES": tmp}
        for scene in ("scene_rail.py", "scene_pokes.py"):
            subprocess.run([exe, "-b", "--factory-startup", "-P", str(HERE / scene)], check=True, capture_output=True, env=env)
        for name, count, back in (("phone", 12, False), ("star", 12, True), ("egg", 12, True)):
            frames = [Image.open(Path(tmp) / f"{name}-{i:02d}.png").convert("RGBA") for i in range(count)]
            frames[0].save(ART / f"{name}.webp", quality=88, method=6)
            poke = frames[1:] + ([frames[0]] if back else [])
            sheet(poke).save(ART / f"{name}-poke.webp", quality=88, method=6)
            print(f"{name}-poke.webp", len(poke), "frames")
    for suffix in ("", "-bondi"):
        save(spike(suffix), ART / f"spectrum-spike{suffix}.png")
    bits()


def rail_pictures():
    """The rail's picture per scheme: the render (scene_railpic.py) on the scheme's ground, the
    playlist window over the room names frosted (blurred, then a glass tint) with a chrome rim and a
    rainbow sheen along its top, fading out above the rail's foot
    (the flip phone and the egg), 231 x 460 so it is never scaled. The rail skin's
    frame shows through the transparent edges (4 px sides, 14 px top)."""
    import os
    import tempfile

    exe = str(Path.home() / ".local/bin/blender")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "Y2K_FRAMES": tmp}
        subprocess.run([exe, "-b", "--factory-startup", "-P", str(HERE / "scene_railpic.py")], check=True, capture_output=True, env=env)
        art = Image.open(Path(tmp) / "railpic.png").convert("RGBA")
    w, h = art.size
    win = (8, 60, w - 8, 408)
    for name, top, bottom, glass, rim_hi, rim_lo, fade in (
        ("rail-night.png", (27, 31, 60), (14, 17, 38), (12, 16, 34, 178), (150, 160, 210, 255), (4, 5, 12, 255), (14, 17, 38)),
        ("rail-day.png", (240, 242, 252), (222, 230, 247), (248, 250, 255, 172), (255, 255, 255, 255), (125, 140, 180, 255), (222, 230, 247)),
    ):
        ground = Image.new("RGBA", (w, h))
        px = ground.load()
        for y in range(h):
            t = y / (h - 1)
            c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            for x in range(w):
                px[x, y] = (*c, 255)
        ground.alpha_composite(art)
        # The frosted playlist window.
        box = ground.crop(win).filter(ImageFilter.GaussianBlur(7))
        box.alpha_composite(Image.new("RGBA", box.size, glass))
        ground.paste(box, win[:2])
        d = ImageDraw.Draw(ground)
        d.line([(win[0], win[1]), (win[2] - 1, win[1])], fill=rim_hi)
        d.line([(win[0], win[1]), (win[0], win[3] - 1)], fill=rim_hi)
        d.line([(win[0], win[3] - 1), (win[2] - 1, win[3] - 1)], fill=rim_lo)
        d.line([(win[2] - 1, win[1]), (win[2] - 1, win[3] - 1)], fill=rim_lo)
        import colorsys

        for x in range(win[0] + 1, win[2] - 1):
            rr, gg, bb = colorsys.hsv_to_rgb(0.55 + 0.45 * (x - win[0]) / (win[2] - win[0]), 0.45, 1.0)
            d.point((x, win[1] + 1), fill=(round(rr * 255), round(gg * 255), round(bb * 255), 200))
        # The skin's frame shows through: clear sides and title bar.
        a = ground.getchannel("A")
        ImageDraw.Draw(a).rectangle([0, 0, w, 13], fill=0)
        ImageDraw.Draw(a).rectangle([0, 0, 3, h], fill=0)
        ImageDraw.Draw(a).rectangle([w - 4, 0, w, h], fill=0)
        ap = a.load()
        for y in range(h - 30, h):  # fade out above the rail's foot
            for x in range(w):
                ap[x, y] = round(ap[x, y] * (h - 1 - y) / 30)
        ground.putalpha(a)
        ground.save(ART / name.replace(".png", ".webp"), quality=90, method=6)
        print(name.replace(".png", ".webp"))


GROUPS = {"skins": skins, "pieces": pieces, "sky": sky, "renders": renders, "pokes": pokes, "rail": rail_pictures}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(GROUPS)
    for name in wanted:
        if name.startswith("scene_"):
            renders([name])
        else:
            GROUPS[name]()
