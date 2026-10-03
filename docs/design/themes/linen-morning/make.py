"""Kinari: every picture of the theme, drawn by code (numpy + Pillow, ink.py).

    python3 docs/design/themes/linen-morning/make.py            # everything
    python3 docs/design/themes/linen-morning/make.py hero crest # some pieces

One light: morning sun from the top left, through shoji paper: soft, warm, shadows falling to
the lower right. One medium: sumi ink washes on washi, with bleeding edges and dry-brush
streaks; walnut and kraft for the few solid objects; a single hanko red, always small."""

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from ink import *  # noqa: E402,F403

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "themes/linen-morning/art"
PIECES = {}


def piece(fn):
    PIECES[fn.__name__] = fn
    return fn


# ---------- textures ----------
def washi_delta(size, seed, strength=1.0):
    """The paper: soft cloudiness, long kozo fibres (lighter), a few darker bark flecks, grain."""
    cloud = smooth_noise(size, size, seed, 38) * 0.012 + smooth_noise(size, size, seed + 1, 9) * 0.006
    # lighter-than-ground fibres, short and soft (at full strength they read as hair)
    light = fibres(size, size, seed + 2, int(size * size / 2000), (8, 30), (0.6, 1.2)) * 0.024
    fine = fibres(size, size, seed + 3, int(size * size / 1400), (4, 12), (0.5, 0.8)) * 0.014
    flecks = fibres(size, size, seed + 4, int(size * size / 60000), (2, 4), (0.6, 1.0)) * -0.05
    return (cloud + light + fine + flecks) * strength


@piece
def textures():
    save(overlay_from_delta(washi_delta(384, 11)), ART / "washi.webp", quality=70, alpha_quality=50)
    save(overlay_from_delta(washi_delta(320, 23, 0.55)), ART / "washi-fine.webp", quality=70, alpha_quality=50)


# ---------- the Home hero: ink-wash mountains in morning mist ----------
def streaks(w, h, seed, stretch=8, size=3):
    """Noise stretched along the vertical: the grain of rock strokes, 0..1."""
    small = smooth_noise(max(8, h // stretch), w, seed, size) * 0.5 + 0.5
    return np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), float) / 255


def wash_layer(w, h, top, falloff, seed, rim=0.6, rim_px=5, texture=0.35, bleed_px=1.6, striate=0.0, soft=0.8):
    """A mountain wash under a ridge line `top` (px per column): dark at the ridge, fading down
    into mist, with a bled edge and vertical dry-brush texture (the cun strokes)."""
    x, y = grid_xy(w, h)
    depth = y - top[None, :]
    body = np.where(depth > 0, np.exp(-depth / falloff), 0.0)
    edge = np.where(depth > 0, np.exp(-depth / rim_px), 0.0) * rim
    mask = np.clip(body * (1 - rim) + edge, 0, 1)
    mask = blur(bleed(mask, seed, bleed_px, 7), soft)
    tex = smooth_noise(h, w, seed + 3, 3) * 0.5 + 0.5
    cun = np.clip((smooth_noise(h, w, seed + 5, 10) * 0.5 + 0.5), 0, 1)
    mask = mask * (1 - texture + texture * (0.55 * tex + 0.45 * cun))
    if striate:
        mask = mask * (1 - striate + striate * streaks(w, h, seed + 9) ** 1.5 * 1.6)
    return np.clip(mask, 0, 1)


def peaks(w, bumps, base, seed, rough=18, octaves=7):
    """A ridge line: gaussian peaks (x, height, width) over a base line, roughened by fractal noise."""
    xs = np.arange(w, dtype=float)
    top = np.full(w, float(base))
    for cx, hgt, wid, *skew in bumps:
        k = skew[0] if skew else 0
        d = (xs - cx) / wid
        d = np.where(d > 0, d * (1 + k), d * (1 - k))
        top -= hgt * np.exp(-d * d)
    top += ridge(w, seed, 0.55, octaves) * rough
    return top


def pine(c, cx, base_y, height, seed, ink, alpha=0.9):
    """A pine in brush dabs: a leaning, tapering trunk and flat clouds of needles, each cloud a
    cluster of small dabs with a bled edge (never ruled lines)."""
    rng = np.random.default_rng(seed)
    w, h = c.w, c.h
    lean = rng.uniform(-0.3, 0.3)
    ts = np.linspace(0, 1, 14)
    trunk = [(cx + lean * height * t + math.sin(t * 5 + seed) * height * 0.04, base_y - height * t) for t in ts]
    c.paint(ink, stroke_mask(w, h, trunk, [max(1.0, height * 0.06 * (1 - t * 0.75)) for t in ts]) * alpha)
    tiers = int(rng.integers(3, 5))
    m = np.zeros((h, w))
    for i in range(tiers):
        t = 0.45 + 0.55 * i / max(1, tiers - 1)
        tx, ty = cx + lean * height * t + math.sin(t * 5 + seed) * height * 0.04, base_y - height * t
        span = height * (0.36 - 0.2 * t) * rng.uniform(0.8, 1.2)
        off = rng.uniform(-0.4, 0.4) * span
        for _ in range(int(10 + span)):
            dx = rng.normal(off, span * 0.5)
            dy = rng.normal(0, height * 0.035) - abs(dx - off) * 0.08
            r = rng.uniform(0.8, 1.8) * max(1.0, height / 40)
            m = np.maximum(m, disc(w, h, tx + dx, ty + dy, r, 1.0) * rng.uniform(0.6, 1))
    m = bleed(m, seed, 0.8, 2)
    c.paint(ink, np.clip(m * 1.3, 0, 1) * alpha)


def taper(points, w0, w1=None, peak=0.3):
    """Widths along a stroke: swelling from the press to a dry tail."""
    n = len(points)
    w1 = w0 * 0.25 if w1 is None else w1
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        press = min(1, t / peak) if peak else 1
        out.append(max(0.5, (w0 * (1 - t) + w1 * t) * (0.55 + 0.45 * press)))
    return out


def hanko_seal(size, seed=1, marks="mountain"):
    """The small vermilion seal: a carved square, its marks abstract (never a character)."""
    s = size
    c = Canvas(s, s)
    m = rect(s, s, 0, 0, s, s, 0.8)
    m = bleed(m, seed, 0.8, 2) * (0.82 + 0.18 * (smooth_noise(s, s, seed, 2) * 0.5 + 0.5))
    c.paint(HANKO, np.clip(m * 1.2, 0, 1))
    carve = np.zeros((s, s))
    b = s * 0.12
    # a carved inner border, broken in one corner like an old stone seal
    carve += rect(s, s, b, b, s - b, s - b, 0.6) - rect(s, s, b + s * 0.06, b + s * 0.06, s - b - s * 0.06, s - b - s * 0.06, 0.6)
    carve *= 1 - rect(s, s, s * 0.66, s * 0.66, s, s, 0.6) * 0.9
    if marks == "mountain":
        # a carved plum blossom (a crest-like flower, never a character): five petals round a heart
        cx, cy, r = s * 0.5, s * 0.52, s * 0.2
        for k in range(5):
            ang = math.radians(-90 + k * 72)
            carve += disc(s, s, cx + math.cos(ang) * r, cy + math.sin(ang) * r, s * 0.115, 0.6)
        carve -= disc(s, s, cx, cy, s * 0.07, 0.6) * 1.5
    elif marks == "wave":
        for i in range(3):
            y0 = s * (0.36 + i * 0.14)
            carve += stroke_mask(s, s, [(s * 0.26, y0), (s * 0.42, y0 - s * 0.05), (s * 0.58, y0), (s * 0.74, y0 - s * 0.05)], [s * 0.05] * 4)
    carve = np.clip(carve, 0, 1)
    c.a = c.a * (1 - carve * 0.92)
    c.rgb = c.rgb * (1 - carve[..., None] * 0.92)
    return c


def paste(c, other, x0, y0, opacity=1.0):
    """Lay a smaller canvas onto c at (x0, y0)."""
    h, w = other.a.shape
    sl = (slice(y0, y0 + h), slice(x0, x0 + w))
    a = other.a * opacity
    c.rgb[sl] = c.rgb[sl] * (1 - a[..., None]) + other.rgb * opacity
    c.a[sl] = c.a[sl] * (1 - a) + a


@piece
def hero():
    W, H = 1600, 560
    c = Canvas(W, H)
    x, y = grid_xy(W, H)
    rng = np.random.default_rng(9)
    far_ink = oklch(0.42, 0.025, 250)
    # dawn: a pale sun behind thin mist, a warm breath around it
    sx, sy = 1175, 132
    glow = np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2 * 170**2))
    c.paint(oklch(0.88, 0.055, 78), glow * 0.22)
    c.paint(WASHI_LIT, blur(disc(W, H, sx, sy, 40, 1.0), 3) * 0.7)
    # air: a last range, barely there
    top = peaks(W, [(300, 60, 220), (980, 90, 260), (1560, 70, 200)], 290, 13, 8)
    c.paint(far_ink, wash_layer(W, H, top, 40, 23, 0.3, 4, 0.2, soft=3.5) * 0.1)
    # the farthest range: bluish ink, very pale
    top = peaks(W, [(420, 90, 160), (760, 70, 200), (1020, 120, 150), (1480, 90, 160)], 330, 3, 10)
    c.paint(far_ink, wash_layer(W, H, top, 60, 31, 0.35, 4, soft=2.6) * 0.22)
    # the middle range
    top = peaks(W, [(620, 60, 120), (880, 110, 110, 0.3), (1300, 150, 120, -0.2)], 420, 5, 14)
    c.paint(oklch(0.33, 0.02, 200), wash_layer(W, H, top, 50, 41, 0.5, 4, soft=1.6) * 0.38)
    # the great peak: steep sansui rock on the right, dark shoulders, feet lost in the mist
    top = peaks(W, [(1212, 250, 48, 0.6), (1262, 330, 46, -0.1), (1318, 220, 40, 0.2), (1395, 250, 58, -0.35), (1120, 130, 70)], 540, 7, 12)
    feet = np.clip((H - 110 - y) / 130, 0, 1) ** 0.9
    c.paint(SUMI, wash_layer(W, H, top, 110, 51, 0.62, 8, 0.45, striate=0.55) * feet * 0.78)
    # hemp-fibre strokes down the flanks, in small groups: each group its own angle, length and
    # curve, some strokes broken where the brush lifted (never a regular comb)
    for g in range(8):
        gx = rng.uniform(1160, 1410)
        side = -1 if gx < 1232 or (1290 < gx < 1370) else 1
        ang = math.radians(rng.uniform(55, 86))
        for k in range(int(rng.integers(2, 5))):
            px = gx + rng.normal(0, 10)
            py = top[int(np.clip(px, 0, W - 1))] + rng.uniform(4, 50)
            L = rng.uniform(22, 95)
            a = ang + rng.normal(0, 0.08)
            bend = rng.uniform(-0.15, 0.35) * side
            pts = [(px + side * math.cos(a) * L * t + bend * L * t * t, py + math.sin(a) * L * t) for t in np.linspace(0, 1, 16)]
            m = stroke_mask(W, H, pts, taper(pts, rng.uniform(1.8, 3.8)))
            if rng.random() < 0.35:  # the brush lifts
                cut = rng.uniform(0.35, 0.65)
                yy = py + math.sin(a) * L * cut
                m *= 1 - np.exp(-((y - yy) / 3.5) ** 2)
            sm = dry_brush(m, int(px * 7 + k), rng.uniform(0.3, 0.6), "y")
            c.paint(SUMI_DEEP, sm * rng.uniform(0.22, 0.5) * feet)
    # moss dots (dian) along the ridges, in small clusters
    for px in (1262, 1394):
        for _ in range(int(rng.integers(2, 4))):
            qx = px + rng.normal(0, 6)
            qy = top[int(np.clip(qx, 0, W - 1))] + rng.uniform(1, 7)
            c.paint(SUMI_DEEP, bleed(disc(W, H, qx, qy, rng.uniform(1.8, 3.2), 1.0), int(qx), 0.7, 2) * 0.85)
    # small pines on the peak's shoulder, their size gives the peak its height
    for i, px in enumerate([1256, 1272, 1386]):
        pine(c, px, top[px] + 9, rng.uniform(18, 26), 60 + i, SUMI_DEEP, 0.85)
    # the near bank at the lower right: darkest ink, a hut under old pines
    top = peaks(W, [(1500, 70, 170), (1250, 26, 120)], 575, 11, 6)
    near = wash_layer(W, H, top, 34, 61, 0.7, 5, 0.4) * np.clip((x - 1080) / 160, 0, 1)
    c.paint(SUMI, near * 0.88)
    for i, (px, hh) in enumerate([(1398, 84), (1432, 60), (1552, 70)]):
        pine(c, px, top[px] + 8, hh, 80 + i, SUMI_DEEP, 0.95)
    hx = 1482
    hy = int(top[hx]) + 3
    c.paint(oklch(0.62, 0.035, 62), polygon_mask(W, H, [(hx - 15, hy), (hx + 15, hy), (hx + 13, hy - 13), (hx - 13, hy - 13)]) * 0.75)
    c.paint(SUMI_DEEP, rect(W, H, hx - 4, hy - 11, hx + 3, hy, 0.8) * 0.7)
    roof = [(hx - 24, hy - 10), (hx - 8, hy - 21), (hx + 9, hy - 22), (hx + 25, hy - 11)]
    c.paint(SUMI_DEEP, stroke_mask(W, H, roof, [3.5, 6, 6, 3]) * 0.92)
    # still water on the left: a few broken ripples and one boat, far out
    for i, (x0, x1, yy, wd) in enumerate([(860, 980, 470, 2.2), (1080, 1150, 494, 2.4), (900, 1010, 510, 2.0), (420, 520, 520, 1.6)]):
        pts = [(xx, yy + math.sin(xx / 37 + i) * 1.0) for xx in np.linspace(x0, x1, 24)]
        c.paint(SUMI, dry_brush(stroke_mask(W, H, pts, taper(pts, wd, 0.6, 0.15)), 70 + i, 0.55, "x") * 0.4)
    bx, by = 1030, 486
    hull = [(bx - 20, by - 3), (bx - 8, by + 2), (bx + 10, by + 2.5), (bx + 23, by - 4)]
    c.paint(SUMI_DEEP, stroke_mask(W, H, hull, [2.5, 4, 4, 2]) * 0.9)
    c.paint(SUMI_DEEP, stroke_mask(W, H, [(bx + 4, by - 1), (bx + 6, by - 12), (bx + 7, by - 15)], [1.6, 1.3, 1.0]) * 0.85)
    c.paint(SUMI_DEEP, disc(W, H, bx - 3, by - 5, 2.6, 1.0) * 0.9)  # the fisherman, a single dot
    # the painter's seal, small and low, beside the hut
    paste(c, hanko_seal(22, 3), 1318, 500, 0.92)
    c.a[-3:] = 0
    save(c.image(), ART / "hero-mountains.webp", quality=84)


# ---------- layers: mist, geese, a falling leaf, bamboo shadows ----------
@piece
def mist():
    """Morning mist for the hero: soft washi-white bands, seamless left to right (drifts)."""
    W, H = 1200, 240
    x, y = grid_xy(W, H)
    band = lambda cy, hw: np.exp(-((y - cy) / hw) ** 2)
    n1 = smooth_noise(H, W, 5, 60) * 0.5 + 0.5
    n2 = smooth_noise(H, W, 6, 22) * 0.5 + 0.5
    # the noise is periodic in x, so the tile wraps; bands sit where the valleys are
    a = band(52, 16) * 0.45 + band(100, 14) * 0.6 + band(190, 26) * 0.55
    a = a * np.clip(n1 * 1.6 - 0.35, 0, 1) * (0.7 + 0.3 * n2)
    save(to_image(np.ones((H, W, 3)) * WASHI_LIT, np.clip(a, 0, 0.7)), ART / "mist.webp", quality=70, alpha_quality=60)


def bird(c, cx, cy, span, phase, ink, alpha=0.95):
    """A goose far away: a body dab and two curved wing strokes; phase 0 up … 1 down."""
    lift = (0.5 - phase) * span * 0.9
    for side in (-1, 1):
        tip = (cx + side * span, cy - lift)
        mid = (cx + side * span * 0.45, cy - lift * 0.35 - span * 0.12)
        pts = [(cx + side * 1.2, cy), mid, tip]
        c.paint(ink, stroke_mask(c.w, c.h, pts, [2.0, 1.6, 0.6], ss=6) * alpha)
    c.paint(ink, disc(c.w, c.h, cx, cy + 0.3, 1.6, 0.8) * alpha)


@piece
def geese():
    """Four geese in a loose line, far off; four frames of wingbeats (a crossing layer)."""
    fw, fh = 96, 40
    frames = []
    flock = [(22, 14, 0.0), (36, 19, 0.3), (50, 23, 0.55), (68, 26, 0.85)]  # x, y, phase offset
    for f in range(4):
        c = Canvas(fw, fh)
        for i, (bx, by, off) in enumerate(flock):
            ph = (f / 4 + off) % 1
            ph = 0.5 - 0.5 * math.cos(ph * 2 * math.pi)
            bird(c, bx, by + (1 if f % 2 else 0) * (i % 2), 5.5 - i * 0.4, ph, oklch(0.36, 0.02, 60), 0.9)
        frames.append(c.image())
    sheet = Image.new("RGBA", (fw * 4, fh))
    for i, im in enumerate(frames):
        sheet.paste(im, (i * fw, 0))
    save(sheet, ART / "geese.webp", lossless=True)


def leaf_shape(w, h, cx, cy, length, width, ang, ss=4, curve=0.15):
    """A lanceolate leaf (bamboo, willow): a polygon along a slightly curved midrib."""
    pts_l, pts_r = [], []
    ca, sa = math.cos(ang), math.sin(ang)
    for t in np.linspace(0, 1, 18):
        wid = width * math.sin(math.pi * t ** 0.8) * (1 - 0.25 * t)
        bend = curve * length * (t - 0.5) ** 2
        px, py = (t - 0.3) * length, bend
        for sign, pts in ((1, pts_l), (-1, pts_r)):
            qx, qy = px, py + sign * wid / 2
            pts.append((cx + qx * ca - qy * sa, cy + qx * sa + qy * ca))
    return pts_l + pts_r[::-1]


@piece
def leaf_fall():
    """One dry bamboo leaf tumbling down: eight frames (it turns and sways), a rare crossing."""
    fw, fh, n = 72, 48, 8
    sheet = Image.new("RGBA", (fw * n, fh))
    for f in range(n):
        t = f / n * 2 * math.pi
        c = Canvas(fw, fh)
        flip = math.cos(t)
        width = 5.0 * max(0.18, abs(flip))
        cx = 28 + math.sin(t) * 7
        pts = leaf_shape(fw, fh, cx, 24, 26, width, math.radians(18 + 22 * math.sin(t)))
        m = polygon_mask(fw, fh, pts)
        col = oklch(0.6, 0.075, 68) if flip > 0 else oklch(0.52, 0.06, 64)
        c.paint(col, m * 0.95)
        c.paint(oklch(0.42, 0.05, 60), np.clip(m - blur(m, 1.2) * 0.2, 0, 1) * 0.0)
        sheet.paste(c.image(), (f * fw, 0))
    save(sheet, ART / "leaf-fall.webp", lossless=True)


@piece
def leaf_shadow():
    """Bamboo leaves' shadows falling on the shoji-paper wall: a large seamless tile, clusters
    in one corner and air elsewhere; the nearer leaves sharper (they drift, slowly)."""
    W, H, ss = 1400, 1000, 2
    rng = np.random.default_rng(21)
    sharp = Image.new("L", (W * ss, H * ss))
    soft = Image.new("L", (W * ss, H * ss))
    from PIL import ImageDraw
    ds, dd = ImageDraw.Draw(sharp), ImageDraw.Draw(soft)
    offsets = [(dx, dy) for dx in (-W, 0, W) for dy in (-H, 0, H)]

    def poly(draw, pts, val):
        for dx, dy in offsets:
            draw.polygon([((px + dx) * ss, (py + dy) * ss) for px, py in pts], fill=val)

    def line(draw, pts, width, val):
        for dx, dy in offsets:
            draw.line([((px + dx) * ss, (py + dy) * ss) for px, py in pts], fill=val, width=int(width * ss))

    # one culm's twigs from the top right: the nearer twig sharper, the farther softer
    for draw, (bx, by), nodes, scale, val, slope in ((ds, (1250, 30), 7, 1.0, 235, 0.55), (dd, (1130, 250), 5, 0.85, 205, 0.35)):
        twig = [(bx - i * 18 * scale, by + i * 18 * scale * slope + (i / 29) ** 2 * 120 * scale) for i in range(30)]
        line(draw, twig, 2.6 * scale, val)
        for k in range(nodes):
            i = min(29, 4 + k * 3 + int(rng.integers(0, 3)))
            tx, ty = twig[i]
            dx, dy = rng.uniform(-18, 4) * scale, rng.uniform(10, 26) * scale
            line(draw, [(tx, ty), (tx + dx, ty + dy)], 1.6 * scale, val)
            tx, ty = tx + dx, ty + dy
            fan = rng.uniform(95, 135)
            n = int(rng.integers(2, 5))
            for j in range(n):
                ang = math.radians(fan + (j - (n - 1) / 2) * rng.uniform(20, 32) + rng.normal(0, 6))
                L = rng.uniform(100, 175) * scale
                wd = rng.uniform(13, 17) * scale
                cx, cy = tx + math.cos(ang) * L * 0.3, ty + math.sin(ang) * L * 0.3
                poly(draw, leaf_shape(W, H, cx, cy, L, wd, ang, curve=rng.uniform(-0.12, 0.12)), val)
    a1 = np.asarray(sharp.resize((W, H), Image.LANCZOS), float) / 255
    a2 = np.asarray(soft.resize((W, H), Image.LANCZOS), float) / 255
    a = np.maximum(blur(a1, 2.0, wrap=True) * 0.34, blur(a2, 5.0, wrap=True) * 0.2)
    save(to_image(np.ones((H, W, 3)) * oklch(0.34, 0.03, 60), a), ART / "leaf-shadow.webp", quality=60, alpha_quality=40)


# ---------- tatami and its heri (status bar, dock) ----------
def tatami(w, h, seed, reed=6, warp=28, colour=None):
    """Tatami weave: rounded igusa reeds along the width, warp threads crossing every `warp` px."""
    colour = oklch(0.85, 0.038, 86) if colour is None else colour
    x, y = grid_xy(w, h)
    rng = np.random.default_rng(seed)
    rows = np.arange(h) // reed
    tone = rng.normal(0, 0.018, rows.max() + 1)[rows][:, None]
    phase = (y % reed) / reed
    round_ = np.sin(phase * math.pi) * 0.05 - 0.03  # each reed lit on top, a groove below
    warp_line = np.exp(-(((x + (rows % 2)[:, None] * warp / 2) % warp) - warp / 2) ** 2 / 2.0) * -0.05
    lum = tone + round_ + warp_line + smooth_noise(h, w, seed, 40) * 0.015
    return np.clip(colour[None, None, :] * (1 + lum[..., None] * 1.7), 0, 1)


def heri(w, h, seed):
    """The heri, tatami's cloth border: dark indigo-sumi twill, a kraft thread at each edge and
    a small woven diamond (hishi) repeating along it."""
    x, y = grid_xy(w, h)
    base = oklch(0.27, 0.03, 250)
    twill = (np.sin((x + y) * math.pi / 2.0) * 0.5 + 0.5) * 0.05
    lum = twill + smooth_noise(h, w, seed, 12) * 0.03
    rgb = base[None, None, :] * (1 + lum[..., None] * 2)
    # the diamond motif, one every 3 heights
    period = h * 3
    cx = (x % period) - period / 2
    cy = y - h / 2
    dia = np.clip((h * 0.26 - (np.abs(cx) * 0.55 + np.abs(cy))) * 1.5, 0, 1)
    rgb = rgb * (1 - dia[..., None] * 0.35) + oklch(0.5, 0.04, 60)[None, None, :] * dia[..., None] * 0.35
    edge = np.clip(1 - np.minimum(y, h - 1 - y) / 1.2, 0, 1)
    rgb = rgb * (1 - edge[..., None] * 0.55) + KRAFT[None, None, :] * edge[..., None] * 0.55
    return rgb


@piece
def status():
    """The status bar: a strip of tatami with its heri along the bottom (the room's first line)."""
    W, H = 2400, 96
    rgb = tatami(W, H, 3)
    hb = 18
    rgb[H - hb:] = heri(W, hb, 4)
    shade = np.exp(-np.maximum(0, (H - hb) - np.arange(H))[:, None] / 3.0) * 0.08
    rgb[: H - hb] *= 1 - shade[: H - hb, :, None]
    save(to_image(rgb), ART / "status-heri.webp", quality=78)


@piece
def dock():
    """The phone dock: the heri along its top edge, washi below (its own ground shows)."""
    W, H = 780, 128
    rgb = np.zeros((H, W, 3))
    a = np.zeros((H, W))
    hb = 12
    rgb[:hb] = heri(W, hb, 7)
    a[:hb] = 1
    sh = np.exp(-(np.arange(H) - hb) / 3.0)[:, None] * (np.arange(H) >= hb)[:, None] * 0.12
    rgb[hb:] = oklch(0.3, 0.03, 60)
    a = np.maximum(a, sh * np.ones((1, W)))
    save(to_image(rgb, a), ART / "dock-heri.webp", quality=80)


# ---------- the rail: a shoji panel ----------
@piece
def rail():
    """The rail as a shoji: tall panes of fibred paper lit from the top left, a kumiko lattice of
    thin walnut bars (low contrast, so names read over it), a walnut stile on the right."""
    W, H = 464, 2000
    c = Canvas(W, H)
    x, y = grid_xy(W, H)
    light = np.exp(-((x + 80) / 700) ** 2 - ((y + 80) / 1100) ** 2)
    c.paint(np.array([1.0, 0.985, 0.94]), light * 0.6)
    # fibres in the paper, lighter than it: the sun behind shows them
    f = fibres(W, H, 31, 900, (8, 26), (0.6, 1.1), wrap=False)
    c.paint(np.array([1.0, 0.99, 0.96]), f * (0.25 + 0.5 * light))
    bar = WALNUT_LIGHT
    lattice = np.zeros((H, W))
    for gx in (116, 348):  # two slender mullions (between the marks and the names, after the names)
        lattice = np.maximum(lattice, rect(W, H, gx - 2, 0, gx + 2, H, 0.8))
    for gy in range(260, H, 360):  # a rail every 180 px on screen
        lattice = np.maximum(lattice, rect(W, H, 0, gy - 2, W - 8, gy + 2, 0.8))
    c.paint(bar, lattice * 0.2)
    c.paint(oklch(0.5, 0.04, 60), np.roll(lattice, (3, 3), (0, 1)) * (1 - lattice) * 0.05)  # their soft shadows
    stile = rect(W, H, W - 8, 0, W, H, 0.8)
    grain = streaks(W, H, 5, 30, 2) * 0.2 + 0.8
    c.paint(WALNUT_LIGHT * grain[..., None], stile)
    c.paint(oklch(0.62, 0.05, 66), rect(W, H, W - 8, 0, W - 6, H, 0.8) * 0.6)
    save(c.image(), ART / "rail-shoji.webp", quality=80)


def enso(size, seed, width=0.1, gap=35, ink=None, start=-60):
    """An ensō: one breath of the brush round a circle, a loaded start, bristle streaks that
    follow the stroke and a dry, split tail."""
    ink = SUMI if ink is None else ink
    c = Canvas(size, size)
    x, y = grid_xy(size, size)
    cx = cy = size / 2
    r = size * 0.36
    ang = (np.degrees(np.arctan2(y - cy, x - cx)) - start) % 360
    t = ang / (360 - gap)  # progress along the stroke, 0..1 (beyond 1: the gap)
    wob = 1 + 0.035 * np.sin(t * 6.3 + seed) + 0.025 * t
    rho = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (r * wob)  # 1 on the stroke's centre line
    half = width * size / r / 2 * (0.6 + 0.4 * np.sin(np.clip(t * 5, 0, 1) * math.pi / 2)) * (1 - 0.5 * np.clip(t, 0, 1) ** 1.6)
    across = (rho - 1) / np.maximum(half, 1e-3)  # -1..1 across the stroke
    body = np.clip((1 - np.abs(across)) * size / 30, 0, 1) * (t <= 1)
    # bristles: a pattern across the stroke, constant along it; ink runs out towards the tail
    rng = np.random.default_rng(seed)
    bristle = np.interp(across, np.linspace(-1, 1, 40), blur(rng.random((1, 40)), 0.8)[0])
    dry = np.clip(t - 0.45, 0, 1) * 1.6
    keep = np.clip((bristle - dry * 0.9) * 4 + 0.6, 0, 1)
    head = np.exp(-((t * (360 - gap)) / 12) ** 2) * 0.3  # the brush pressed down at the start
    m = np.clip(body * keep + body * head, 0, 1)
    a0 = math.radians(start)
    a0 += math.radians(4)
    m = np.maximum(m, disc(size, size, cx + r * math.cos(a0), cy + r * math.sin(a0), width * size * 0.4, size / 50) * 0.95)
    m = bleed(m, seed, size / 400, size / 90)
    c.paint(ink, m)
    return c


def bamboo(c, x0, y0, x1, y1):
    """A bamboo culm in sumi, rising through the paper, nodes and a spray of leaves."""
    W, H = c.w, c.h
    cx = x0 + (x1 - x0) * 0.42
    seg = [y1 - 6, y1 - 70, y1 - 128, y1 - 178, y0 + 40, y0 + 4]
    for a, b in zip(seg, seg[1:]):
        pts = [(cx + (y1 - yy) * 0.04, yy) for yy in np.linspace(a - 3, b + 3, 10)]
        m = stroke_mask(W, H, pts, [7.5] * 10)
        c.paint(SUMI, dry_brush(bleed(m, int(a), 0.6, 2), int(a), 0.25, "y") * 0.72)
        nx = cx + (y1 - b) * 0.04
        c.paint(SUMI_DEEP, stroke_mask(W, H, [(nx - 6, b + 2), (nx + 6, b + 1)], [3, 2.4]) * 0.9)
    rng = np.random.default_rng(4)
    for (nx, ny, fan, n) in ((cx + 9, y0 + 60, 20, 3), (cx - 2, y1 - 130, 160, 2), (cx + 6, y1 - 175, 30, 3)):
        c.paint(SUMI, stroke_mask(W, H, [(nx, ny), (nx + math.cos(math.radians(fan)) * 18, ny - 6)], [1.6, 1.2]) * 0.8)
        for j in range(n):
            ang = math.radians(fan + (j - (n - 1) / 2) * 28 + 22)
            L = rng.uniform(34, 46)
            bx, by = nx + math.cos(math.radians(fan)) * 16, ny - 5
            m = polygon_mask(W, H, leaf_shape(W, H, bx + math.cos(ang) * L * 0.3, by + math.sin(ang) * L * 0.3, L, 7.5, ang, curve=0.15))
            c.paint(SUMI, bleed(m, j + int(nx), 0.5, 2) * rng.uniform(0.7, 0.92))


@piece
def scroll():
    """A hanging scroll at the rail's foot: walnut rods, a kraft mounting, washi in the middle
    with a bamboo culm in sumi and the red seal; its shadow falls to the lower right."""
    W, H = 464, 480
    c = Canvas(W, H)
    x0, x1 = 152, 312
    top, bot = 44, 452
    # the cord and the nail
    c.paint(WALNUT, stroke_mask(W, H, [(x0 + 22, top + 4), (W / 2, 10), (x1 - 22, top + 4)], [2, 2, 2]) * 0.9)
    c.paint(SUMI, disc(W, H, W / 2, 10, 4, 1))
    # shadow on the wall
    sh = blur(rect(W, H, x0 + 8, top + 10, x1 + 8, bot + 8, 1), 7)
    c.paint(oklch(0.35, 0.03, 60), sh * 0.22)
    # mounting: kraft cloth with a finer band above and below the paper
    c.paint(oklch(0.72, 0.055, 68), rect(W, H, x0, top, x1, bot, 0.8))
    tex = smooth_noise(H, W, 3, 2) * 0.5 + 0.5
    c.paint(oklch(0.64, 0.06, 64), rect(W, H, x0, top, x1, bot, 0.8) * tex * 0.25)
    c.paint(oklch(0.34, 0.035, 250), rect(W, H, x0, top + 34, x1, top + 46, 0.8) * 0.85)
    c.paint(oklch(0.34, 0.035, 250), rect(W, H, x0, bot - 70, x1, bot - 58, 0.8) * 0.85)
    # the paper
    px0, py0, px1, py1 = x0 + 16, top + 56, x1 - 16, bot - 80
    c.paint(WASHI_LIT, rect(W, H, px0, py0, px1, py1, 0.8))
    f = fibres(W, H, 5, 60, (6, 20), (0.5, 0.8), wrap=False)
    c.paint(np.array([0.93, 0.9, 0.84]), f * rect(W, H, px0, py0, px1, py1, 0.8) * 0.35)
    bamboo(c, px0, py0, px1, py1)
    paste(c, hanko_seal(16, 5), int(px1 - 28), int(py1 - 34))
    # rods: a thin one on top, the roller with its knobs below
    c.paint(WALNUT, rect(W, H, x0 - 2, top - 6, x1 + 2, top + 2, 1))
    c.paint(SUMI, rect(W, H, x0 - 14, bot - 6, x1 + 14, bot + 6, 1.5))
    for kx in (x0 - 20, x1 + 20):
        c.paint(WALNUT, disc(W, H, kx, bot, 9, 1))
        c.paint(oklch(0.55, 0.05, 60), disc(W, H, kx - 3, bot - 3, 3, 1) * 0.6)
    # it hangs at the rail's foot as a piece (drawn at its size there, 232 × 220) that a click
    # sets swaying once on its nail: eleven frames, a breath of air and back to rest
    big = c.image()
    fw, fh, k = 232, 220, 0.455

    def hung(angle):
        turned = big.rotate(angle, resample=Image.BICUBIC, center=(W / 2, 10))
        small = turned.resize((round(W * k), round(H * k)), Image.LANCZOS)
        frame = Image.new("RGBA", (fw, fh))
        frame.alpha_composite(small, ((fw - small.width) // 2, 0))
        return frame

    save(hung(0), ART / "scroll-foot.webp", quality=88)
    angles = [0, 1.6, 2.6, 2.2, 0.9, -0.7, -1.4, -1.0, -0.3, 0.3, 0]
    sheet = Image.new("RGBA", (fw * len(angles), fh))
    for i, a in enumerate(angles):
        sheet.alpha_composite(hung(a), (i * fw, 0))
    save(sheet, ART / "scroll-sway.webp", quality=86)


# ---------- the crest ----------
@piece
def crest():
    """The house's crest: one ensō, brushed in a breath, and the red seal stamped beside its open
    end. Nothing inside: the empty centre is the point (ma)."""
    S = 480
    c = Canvas(S, S)
    e = enso(440, 21, 0.13, 42, start=-50)
    paste(c, e, 20, 12)
    paste(c, hanko_seal(76, 7), 356, 360, 0.97)
    save(c.image(), ART / "crest.webp", quality=90)


# ---------- header banners: one object per room, ink on nothing ----------
def smooth_path(pts, n=6):
    """Catmull-Rom through the points, so a few points make a brush curve."""
    if len(pts) < 3:
        return pts
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = map(np.array, (p[i - 1], p[i], p[i + 1], p[i + 2]))
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append(tuple(q))
    out.append(tuple(pts[-1]))
    return out


class Brush:
    """The hero's hand, for single objects: washes that pool at their edges and bleed, brush
    strokes made of bristles that run dry, dabs. No pen outlines. Pixels are 2× (a 460 × 240 box
    shows 230 × 120 on screen). Light from the top left: washes lighten towards it."""

    def __init__(self, w=460, h=240, seed=1):
        self.c = Canvas(w, h)
        self.w, self.h = w, h
        self.seed = seed
        self.x, self.y = grid_xy(w, h)

    def _next(self):
        self.seed += 1
        return self.seed

    def wash(self, pts, alpha=0.4, colour=None, light=0.35, pool=0.35, smooth=True, bleed_px=1.3):
        """A wash: lighter towards the top-left light, darker where the ink pools at its edge."""
        s = self._next()
        alpha = min(1.0, alpha * 1.3)
        pts = smooth_path(list(pts) + [pts[0]], 8) if smooth else pts
        m = polygon_mask(self.w, self.h, pts)
        m = blur(bleed(m, s, bleed_px, 11), 1.1)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        t = np.clip(((self.x - x0) / max(1, x1 - x0) + (self.y - y0) / max(1, y1 - y0)) / 2, 0, 1)
        tone = (1 - light) + light * t  # 1 at the shadow side
        grain = 0.82 + 0.18 * (smooth_noise(self.h, self.w, s, 5) * 0.5 + 0.5)
        edge = np.clip(m - blur(m, 5), 0, 1) * pool * 2.2
        self.c.paint(SUMI if colour is None else colour, np.clip(m * tone * grain * alpha + edge * alpha, 0, 1))

    def brush(self, pts, width=10, alpha=0.9, dry=0.3, bristles=9, colour=None, taper_to=0.3, smooth=True, press=0.25):
        """One stroke of a brush: bristles side by side, each running dry at its own point."""
        s = self._next()
        rng = np.random.default_rng(s)
        pts = smooth_path(pts, 8) if smooth and len(pts) > 2 else [tuple(q) for a, b in zip(pts, pts[1:]) for q in np.linspace(a, b, 12, endpoint=False)] + [pts[-1]]
        P = np.array(pts, float)
        d = np.gradient(P, axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], 1)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-6)
        n = len(P)
        t = np.linspace(0, 1, n)
        wid = width * (taper_to + (1 - taper_to) * (1 - t)) * (0.6 + 0.4 * np.clip(t / press, 0, 1))
        m = np.zeros((self.h, self.w))
        for k in range(bristles):
            off = (k / (bristles - 1) - 0.5) if bristles > 1 else 0
            end = int(n * (1 - dry * rng.random() * (0.4 + abs(off))))
            if end < 3:
                continue
            q = P[:end] + nrm[:end] * (off * wid[:end, None])
            bw = np.maximum(0.8, wid[:end] / bristles * 1.9)
            mk = stroke_mask(self.w, self.h, [tuple(v) for v in q], list(bw), ss=3)
            m = np.maximum(m, mk * rng.uniform(0.7, 1.0))
        m = bleed(m, s, 0.7, 2.5)
        self.c.paint(SUMI if colour is None else colour, np.clip(m * 1.1, 0, 1) * alpha)

    def dab(self, x, y, r, alpha=0.9, colour=None, squash=1.0):
        s = self._next()
        m = np.clip((r - np.sqrt((self.x - x) ** 2 + ((self.y - y) / squash) ** 2)) / 1.2 + 0.5, 0, 1)
        self.c.paint(SUMI if colour is None else colour, bleed(m, s, 0.8, 2) * alpha)

    def glow(self, x, y, r, alpha=0.8, colour=None):
        m = np.exp(-((self.x - x) ** 2 + (self.y - y) ** 2) / (2 * r * r))
        self.c.paint(WASHI_LIT if colour is None else colour, m * alpha)

    def ellipse(self, cx, cy, rx, ry, a0=0, a1=360, n=40):
        return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in np.linspace(a0, a1, n)]


PALE = oklch(0.62, 0.02, 60)  # a thinned ink for far lines


def ink_home(b):  # a tea bowl on its foot, steam rising
    b.wash([(118, 140), (342, 136), (330, 178), (298, 212), (160, 214), (128, 180)], 0.55, smooth=True)
    b.brush([(112, 140), (170, 131), (240, 134), (300, 129), (348, 138)], 11, 0.9, dry=0.35)
    b.wash([(196, 214), (262, 214), (266, 232), (192, 232)], 0.75, smooth=False)
    b.glow(170, 160, 26, 0.35)
    for x0, sway in ((196, 1), (230, -1), (262, 1)):
        b.brush([(x0, 118), (x0 + 10 * sway, 88), (x0 - 6 * sway, 58), (x0 + 8 * sway, 24)], 4, 0.3, dry=0.5, bristles=3, taper_to=0.1)


def ink_listen(b):  # a wind bell in a breeze, its blank paper strip lifting
    b.brush([(236, 2), (236, 40)], 3, 0.8, bristles=2, dry=0)
    b.wash(b.ellipse(236, 86, 52, 48, 180, 360) + [(288, 92), (184, 92)], 0.42, light=0.6)
    b.brush([(180, 90), (236, 96), (292, 90)], 6, 0.85, dry=0.3)
    b.glow(214, 64, 14, 0.5)
    b.brush([(236, 94), (238, 128)], 2.5, 0.8, bristles=2, dry=0)
    b.dab(238, 132, 5, 0.9)
    b.wash([(228, 138), (250, 136), (278, 226), (252, 232)], 0.16, colour=KRAFT, smooth=False, light=0.2)
    for i, y in enumerate((150, 178, 206)):
        b.brush([(308 + i * 6, y), (348 + i * 8, y - 8), (380 + i * 6, y - 2)], 2.5, 0.28, dry=0.5, bristles=3, taper_to=0.1)


def ink_watch(b):  # a round window: a pine branch across a pale moon, one circle of the brush
    cx, cy, r = 236, 118, 100
    b.glow(cx + 34, cy - 30, 30, 0.8)
    b.brush(b.ellipse(cx, cy, r, r, -80, 250, 60), 13, 0.85, dry=0.45, bristles=11, taper_to=0.5)
    b.brush([(cx - 92, cy + 38), (cx - 40, cy + 16), (cx + 10, cy + 26), (cx + 70, cy + 6)], 6, 0.85, dry=0.3, taper_to=0.2)
    rng = np.random.default_rng(5)
    for bx, by in ((cx - 44, cy + 12), (cx + 8, cy + 20), (cx + 58, cy + 2)):
        for _ in range(7):
            b.dab(bx + rng.normal(0, 12), by - 10 + rng.normal(0, 4), rng.uniform(5, 8), 0.6, squash=0.45)
    b.wash([(cx - 96, cy + 56), (cx + 96, cy + 56), (cx + 80, cy + 76), (cx - 80, cy + 76)], 0.18, smooth=False)


def ink_games(b):  # two go stones on the board's last lines
    for x in (120, 186, 252, 318, 384):
        b.brush([(x, 40), (x, 236)], 2.2, 0.28, bristles=2, dry=0.3, taper_to=0.8, smooth=False)
    for y in (70, 136, 202):
        b.brush([(90, y), (410, y)], 2.2, 0.28, bristles=2, dry=0.3, taper_to=0.8, smooth=False)
    b.wash(b.ellipse(252, 138, 34, 30), 0.95, light=0.5, pool=0.2)
    b.glow(240, 126, 7, 0.45, np.array([1, 1, 1]))
    b.wash(b.ellipse(320, 70, 34, 30), 0.12, light=0.2, pool=0.9)
    b.glow(310, 60, 12, 0.6)


def ink_house(b):  # a bamboo broom leaning, its bristles one dry sweep
    b.brush([(330, 2), (290, 90), (262, 150)], 7, 0.9, dry=0.1, bristles=4, taper_to=0.8)
    b.brush([(266, 150), (250, 176), (226, 206), (196, 232)], 44, 0.75, dry=0.7, bristles=15, taper_to=1.2, press=0.05)
    b.brush([(252, 146), (276, 156)], 5, 0.9, bristles=3, dry=0)


def ink_files(b):  # a paulownia box tied with a flat cord
    b.wash([(130, 96), (350, 96), (350, 228), (130, 228)], 0.22, colour=KRAFT, smooth=False, light=0.5)
    b.wash([(118, 70), (362, 70), (362, 100), (118, 100)], 0.34, colour=KRAFT, smooth=False, light=0.5)
    b.wash([(118, 96), (362, 96), (362, 104), (118, 104)], 0.35, smooth=False)
    b.brush([(240, 64), (240, 230)], 7, 0.8, colour=INDIGO, dry=0.2, bristles=5, smooth=False)
    b.brush([(112, 84), (368, 84)], 7, 0.8, colour=INDIGO, dry=0.2, bristles=5, smooth=False)
    b.brush([(240, 84), (212, 58), (196, 70), (240, 84), (270, 54), (288, 66), (240, 84)], 5, 0.85, colour=INDIGO, bristles=4, dry=0.1)
    b.brush([(240, 86), (220, 124)], 5, 0.8, colour=INDIGO, bristles=4, dry=0.3)
    b.brush([(240, 86), (262, 128)], 5, 0.8, colour=INDIGO, bristles=4, dry=0.3)


def ink_ask(b):  # Nox asleep: one mass of ink curled round, ears up, tail across
    b.wash(b.ellipse(254, 176, 104, 52), 0.75, light=0.55, pool=0.25)
    b.wash(b.ellipse(176, 158, 44, 36) , 0.8, light=0.45, pool=0.2)
    b.wash([(140, 146), (144, 100), (170, 128)], 0.9, smooth=False, light=0.2)
    b.wash([(184, 126), (206, 98), (214, 144)], 0.9, smooth=False, light=0.2)
    b.brush([(354, 180), (340, 216), (276, 234), (196, 228)], 16, 0.9, dry=0.35, bristles=9, taper_to=0.3)
    b.brush([(154, 160), (168, 158)], 3, 0.8, colour=WASHI_LIT, bristles=2, dry=0)
    b.brush([(184, 160), (198, 157)], 3, 0.8, colour=WASHI_LIT, bristles=2, dry=0)


def ink_me(b):  # a paper crane: planes of wash, the light on its back
    back = [(170, 150), (236, 120), (262, 40), (286, 124), (380, 96), (318, 150), (262, 170)]
    b.wash([(236, 120), (262, 40), (286, 124), (262, 170)], 0.6, smooth=False, light=0.5)
    b.wash([(286, 124), (380, 96), (318, 150), (262, 170)], 0.28, smooth=False, light=0.4)
    b.wash([(236, 120), (140, 146), (200, 156), (262, 170)], 0.18, smooth=False, light=0.4)
    b.wash([(262, 170), (318, 150), (344, 222), (300, 196)], 0.45, smooth=False, light=0.3)
    b.brush([(140, 146), (118, 116), (108, 122)], 5, 0.85, bristles=4, dry=0.2, smooth=False)
    b.brush([(262, 40), (262, 168)], 2, 0.4, bristles=2, dry=0.2, smooth=False)


def ink_control(b):  # a single stone in raked gravel
    cx, cy = 250, 178
    for r in (64, 88, 112, 136):
        b.brush(b.ellipse(cx, cy + 6, r * 1.45, r * 0.42, 190, 350, 40), 5, 0.22, dry=0.4, bristles=5, taper_to=0.9)
    b.wash([(196, 186), (206, 150), (236, 126), (272, 124), (300, 146), (308, 186)], 0.85, light=0.6, pool=0.2)
    b.glow(238, 140, 16, 0.35)


def ink_smart_home(b):  # a stone lantern, its window lit
    b.wash([(166, 64), (236, 28), (306, 64), (292, 78), (180, 78)], 0.8, smooth=False, light=0.4)
    b.dab(236, 22, 7, 0.9)
    b.wash([(196, 80), (276, 80), (276, 138), (196, 138)], 0.45, smooth=False, light=0.5)
    b.glow(236, 108, 20, 0.9, oklch(0.9, 0.08, 80))
    b.wash([(180, 138), (292, 138), (282, 154), (190, 154)], 0.7, smooth=False)
    b.wash([(220, 154), (252, 154), (256, 216), (216, 216)], 0.5, smooth=False, light=0.5)
    b.wash([(190, 214), (282, 214), (290, 234), (182, 234)], 0.65, smooth=False)


def ink_inbox(b):  # a folded letter tied with a cord
    b.wash([(130, 80), (342, 70), (352, 206), (140, 216)], 0.12, colour=KRAFT, smooth=False, light=0.4, pool=0.8)
    b.wash([(130, 80), (242, 150), (342, 70)], 0.1, smooth=False, light=0.2)
    b.brush([(250, 60), (258, 222)], 5, 0.85, colour=INDIGO, bristles=4, dry=0.25, smooth=False)
    b.brush([(254, 142), (224, 118), (214, 134), (254, 142), (284, 114), (296, 130), (254, 142)], 4, 0.85, colour=INDIGO, bristles=3, dry=0.1)


def ink_space(b):  # My Space shows its own room picture beside a narrower header: no object
    pass


def ink_space_unused(b):  # one flowering branch in a dark vase
    b.wash([(222, 150), (256, 150), (272, 196), (262, 236), (214, 236), (204, 196)], 0.85, light=0.55, pool=0.2)
    b.brush([(240, 152), (234, 104), (214, 62), (180, 30)], 6, 0.9, dry=0.35, bristles=6, taper_to=0.25)
    b.brush([(234, 110), (268, 80), (300, 70)], 4.5, 0.85, dry=0.4, bristles=5, taper_to=0.2)
    for x, y, r in ((180, 30, 6), (204, 50, 5), (300, 70, 6), (276, 76, 4.5)):
        b.dab(x, y, r, 0.9, colour=HANKO if (x, y) == (300, 70) else SUMI)


def ink_party(b):  # a taiko drum on its stand, two sticks
    b.wash(b.ellipse(236, 120, 78, 84), 0.4, colour=WALNUT, light=0.5)
    b.wash(b.ellipse(236, 120, 38, 78), 0.16, light=0.3, pool=0.8)
    b.glow(222, 100, 20, 0.5)
    for a in range(0, 360, 30):
        b.dab(236 + 38 * math.cos(math.radians(a)), 120 + 78 * math.sin(math.radians(a)), 2.6, 0.85)
    b.brush([(180, 190), (158, 238)], 6, 0.85, bristles=4, dry=0.2, smooth=False)
    b.brush([(292, 190), (314, 238)], 6, 0.85, bristles=4, dry=0.2, smooth=False)
    b.brush([(168, 218), (304, 218)], 5, 0.75, bristles=4, dry=0.4, smooth=False)
    b.brush([(330, 20), (286, 88)], 6, 0.9, bristles=4, dry=0.1, taper_to=0.8)
    b.brush([(362, 32), (306, 94)], 6, 0.9, bristles=4, dry=0.1, taper_to=0.8)


BANNERS = {"home": ink_home, "listen": ink_listen, "watch": ink_watch, "games": ink_games,
           "house": ink_house, "files": ink_files, "ask": ink_ask, "me": ink_me,
           "control": ink_control, "smart-home": ink_smart_home, "inbox": ink_inbox,
           "space": ink_space, "party": ink_party}


@piece
def banners():
    """Each room's banner: 2400 × 320 (2×), transparent so the washi runs on, one object in the
    hero's ink hand in the right third (out of the phone's centre crop), about 110 px tall on
    screen, paling downwards where the header's buttons sit."""
    for room, draw in BANNERS.items():
        b = Brush(460, 240, seed=len(room) * 13)
        draw(b)
        # pale where the buttons sit: full ink in the top half, a third of it at the foot
        fade = np.clip(1 - (b.y - 96) / 56 * 0.82, 0.18, 1)  # full ink above the buttons, faint beside them
        b.c.a *= fade
        b.c.rgb *= fade[..., None]
        full = Image.new("RGBA", (2400, 320))
        full.alpha_composite(b.c.image(), (1700, 8))
        save(full, ART / f"banner-{room}.webp", quality=84)


# ---------- the music deck: a kraft card with its seal; incense while music plays ----------
@piece
def deck():
    """A kraft label, 9-slice (corners 40 px kept whole): kraft with its fibres and flecks, a
    deckled top edge, a walnut double rule printed 6 px in, the red seal in the lower right."""
    W, H = 360, 360
    base = oklch(0.875, 0.042, 72)
    x, y = grid_xy(W, H)
    lum = smooth_noise(H, W, 3, 14) * 0.014 + smooth_noise(H, W, 4, 3) * 0.006
    lum += fibres(W, H, 6, 520, (4, 16), (0.4, 0.8), wrap=False) * -0.06
    lum += fibres(W, H, 7, 260, (6, 20), (0.5, 0.9), wrap=False) * 0.035
    lum += fibres(W, H, 8, 60, (2, 5), (0.7, 1.1), wrap=False) * -0.2
    rgb = base[None, None, :] * (1 + lum[..., None] * 1.4)
    # the deckle: a torn, fibrous top edge (transparent above it), a little lighter where thin
    rng = np.random.default_rng(12)
    edge = 2.5 + blur(rng.random((1, W)), 1.2)[0] * 3 + np.abs(np.sin(np.arange(W) / 7.0)) * 0.6
    a = np.clip(y - edge[None, :] + 0.5, 0, 1)
    thin = np.clip(1 - (y - edge[None, :]) / 3, 0, 1)
    rgb = rgb * (1 - thin[..., None] * 0.25) + np.array([1, 0.97, 0.9]) * thin[..., None] * 0.25
    # the printed double rule, walnut, slightly uneven like a stamp
    ink = oklch(0.4, 0.045, 55)
    rule = np.zeros((H, W))
    for inset, wd in ((12, 1.6), (17, 1.0)):
        outer = rect(W, H, inset, inset, W - inset, H - inset, 0.6)
        inner = rect(W, H, inset + wd, inset + wd, W - inset - wd, H - inset - wd, 0.6)
        rule = np.maximum(rule, outer - inner)
    rule *= 0.8 + 0.2 * (smooth_noise(H, W, 9, 4) * 0.5 + 0.5)
    rgb = rgb * (1 - rule[..., None] * 0.85) + ink * rule[..., None] * 0.85
    img = to_image(rgb, a)
    seal = hanko_seal(13, 11).image()  # stamped on the rule's top right corner, clear of the controls
    img.paste(seal, (W - 22, 8), seal)
    save(img, ART / "deck-kraft.webp", quality=88)


def incense_frame(f, n=8, puff=None):
    """One frame of the incense: bowl, stick, ember, the thread of smoke at phase f/n; `puff`
    (0–1) adds a single slow puff leaving the tip and rising, widening, fading."""
    fw, fh = 72, 150
    c = Canvas(fw, fh)
    c.paint(SUMI, blur(polygon_mask(fw, fh, smooth_path([(40, 136), (66, 136), (64, 146), (42, 146), (40, 136)], 6)), 0.6) * 0.9)
    c.paint(oklch(0.55, 0.02, 60), rect(fw, fh, 42, 135, 64, 137, 0.6) * 0.5)
    tipx, tipy = 44, 96
    c.paint(oklch(0.48, 0.06, 55), stroke_mask(fw, fh, [(55, 136), (tipx, tipy)], [2.0, 1.6]) * 0.95)
    glow = 1.0 if puff is None else 1 + 0.8 * math.sin(min(1, puff * 3) * math.pi)  # the ember brightens as it breathes out
    c.paint(HANKO, disc(fw, fh, tipx, tipy, 1.8, 0.6))
    c.paint(oklch(0.7, 0.14, 45), disc(fw, fh, tipx, tipy, 3.5 * glow, 2) * min(1, 0.35 * glow))
    ph = f / n * 2 * math.pi
    pts, wd = [], []
    for t in np.linspace(0, 1, 60):
        yy = tipy - 3 - t * (tipy - 6)
        sway = math.sin(t * 6.0 - ph) * (1 + 11 * t ** 1.3) + math.sin(t * 13 + ph * 2) * 2.5 * t ** 2
        curl = 5 * t ** 3 * math.sin(ph + 1)
        pts.append((tipx + sway + curl + 4 * t, yy))
        wd.append(0.9 + 7 * t ** 1.4)
    m = blur(stroke_mask(fw, fh, pts, wd), 1.4)
    m *= 0.75 + 0.25 * (smooth_noise(fh, fw, 50 + int(f), 5) * 0.5 + 0.5)
    yy = grid_xy(fw, fh)[1]
    fade = np.clip((yy - 4) / (tipy - 4), 0, 1) ** 0.8
    c.paint(oklch(0.62, 0.012, 60), m * fade * 0.5)
    if puff is not None and puff > 0:
        # the puff: a little curl of denser smoke, rolling over as it climbs
        py = tipy - 6 - puff * 70
        px = tipx + 3 + math.sin(puff * 4) * 5
        r = 3 + puff * 11
        x, y = grid_xy(fw, fh)
        ang = math.atan2(0, 1) + puff * 5
        ring = np.exp(-((np.sqrt((x - px) ** 2 + (y - py) ** 2) - r) / (1.6 + puff * 3)) ** 2)
        swirl = 0.6 + 0.4 * np.cos(np.arctan2(y - py, x - px) - ang)
        c.paint(oklch(0.58, 0.012, 60), blur(ring * swirl, 1.2) * 0.6 * (1 - puff) ** 1.2)
    return c.image()


@piece
def incense():
    """A stick of incense in a small ash bowl, its tip a hanko-red ember, its smoke thickening,
    curling and fading upwards; eight frames, each curl a little different. A click draws one
    slow puff from it (ten frames)."""
    fw, fh, n = 72, 150, 8
    sheet = Image.new("RGBA", (fw * n, fh))
    for f in range(n):
        sheet.paste(incense_frame(f, n), (f * fw, 0))
    save(sheet, ART / "incense.webp", quality=82)
    k = 10
    sheet = Image.new("RGBA", (fw * k, fh))
    for f in range(k):
        sheet.paste(incense_frame(f * 0.8 % n, n, puff=(f + 1) / (k + 1)), (f * fw, 0))
    save(sheet, ART / "incense-puff.webp", quality=82)


# ---------- small pictures: the empty state, the TV, My Space ----------
@piece
def empty():
    """The empty state: one river stone in raked gravel, a single leaf resting on it."""
    S = 288
    c = Canvas(S, S)
    cx, cy = 144, 170
    for r in (70, 92, 114):
        pts = [(cx + r * 1.15 * math.cos(math.radians(a)), cy + 14 + r * 0.42 * math.sin(math.radians(a))) for a in np.linspace(0, 360, 90)]
        c.paint(SUMI, bleed(stroke_mask(S, S, pts, [2.4] * 90), r, 0.6, 2) * 0.28)
    stone = [(84, 186), (92, 152), (126, 128), (170, 126), (204, 146), (212, 184), (188, 200), (110, 202)]
    m = blur(bleed(polygon_mask(S, S, smooth_path(stone + stone[:1], 8)), 3, 0.7, 10), 0.8)
    y = grid_xy(S, S)[1]
    c.paint(SUMI, m * np.clip(0.95 - (y - 126) / 110, 0.45, 0.95))
    c.paint(WASHI_LIT, blur(disc(S, S, 132, 144, 22, 1.5), 6) * m * 0.4)  # the morning light on its top
    leaf = polygon_mask(S, S, leaf_shape(S, S, 170, 128, 58, 13, math.radians(-18), curve=0.2))
    c.paint(oklch(0.62, 0.08, 68), leaf * 0.95)
    c.paint(oklch(0.45, 0.06, 62), stroke_mask(S, S, [(158, 131), (196, 118)], [1.4, 0.8]) * 0.6)
    save(c.image(), ART / "empty-stone.webp", quality=88)


def grain_ramp(w, h, seed, along="x"):
    """Walnut grain in three steps (dark, mid, light), flowing along `along`."""
    x, y = grid_xy(w, h)
    u, v = (x, y) if along == "x" else (y, x)
    flow = v / 3.2 + smooth_noise(h, w, seed, 60) * 1.6 + np.sin(u / 90 + seed) * 0.8 + smooth_noise(h, w, seed + 2, 8) * 0.25
    g = np.sin(flow) * 0.5 + 0.5 + smooth_noise(h, w, seed + 1, 3) * 0.15
    steps = np.digitize(g, [0.38, 0.72])
    ramp = np.array([oklch(0.3, 0.035, 48), oklch(0.36, 0.04, 52), oklch(0.43, 0.045, 56)])
    return ramp[steps]


@piece
def tv():
    """The TV: a walnut frame with mitred corners (grain turning at the joins, lit top left),
    a sumi-dark screen holding the soft reflection of a shoji."""
    W, H = 480, 360
    c = Canvas(W, H)
    x, y = grid_xy(W, H)
    X0, Y0, X1, Y1, T = 20, 18, 460, 318, 26
    horiz, vert = grain_ramp(W, H, 3, "x"), grain_ramp(W, H, 7, "y")
    outer = rect(W, H, X0, Y0, X1, Y1, 1.0)
    inner = rect(W, H, X0 + T, Y0 + T, X1 - T, Y1 - T, 1.0)
    frame = outer * (1 - inner)
    # a mitre: each pixel belongs to the side it is nearest to
    dl, dr, dt, db = x - X0, X1 - x, y - Y0, Y1 - y
    is_h = np.minimum(dt, db) < np.minimum(dl, dr)
    wood = np.where(is_h[..., None], horiz, vert)
    c.paint(wood, frame)
    joins = np.abs(np.abs(dl - dt)) < 0.8
    for cond in (np.abs(dl - dt) < 0.9, np.abs(dr - dt) < 0.9, np.abs(dl - db) < 0.9, np.abs(dr - db) < 0.9):
        c.paint(oklch(0.24, 0.03, 45), cond * frame * 0.7)
    # the light from the top left: bevels lit on top and left, dark on bottom and right
    c.paint(oklch(0.6, 0.05, 62), (rect(W, H, X0, Y0, X1, Y0 + 2, 0.6) + rect(W, H, X0, Y0, X0 + 2, Y1, 0.6)).clip(0, 1) * 0.7)
    c.paint(oklch(0.2, 0.02, 45), (rect(W, H, X0, Y1 - 2, X1, Y1, 0.6) + rect(W, H, X1 - 2, Y0, X1, Y1, 0.6)).clip(0, 1) * 0.6)
    c.paint(oklch(0.2, 0.02, 45), (rect(W, H, X0 + T - 2, Y0 + T - 2, X1 - T + 2, Y0 + T, 0.6) + rect(W, H, X0 + T - 2, Y0 + T, X0 + T, Y1 - T, 0.6)).clip(0, 1) * 0.6)
    # the screen, and a shoji seen in it: a soft grid of light towards the top left
    scr = rect(W, H, X0 + T, Y0 + T, X1 - T, Y1 - T, 0.8)
    c.paint(SUMI_DEEP, scr)
    sx0, sy0, sx1, sy1 = 70, 60, 220, 220
    panes = rect(W, H, sx0, sy0, sx1, sy1, 1)
    for gx in np.linspace(sx0, sx1, 4)[1:-1]:
        panes *= 1 - rect(W, H, gx - 3, sy0, gx + 3, sy1, 1)
    for gy in np.linspace(sy0, sy1, 5)[1:-1]:
        panes *= 1 - rect(W, H, sx0, gy - 3, sx1, gy + 3, 1)
    refl = blur(panes, 7) * np.clip(1 - (x - sx0) / 260, 0, 1) * np.clip(1 - (y - sy0) / 260, 0, 1)
    c.paint(np.array([0.95, 0.92, 0.85]), refl * scr * 0.1)
    for fx in (72, 408):
        c.paint(SUMI, rect(W, H, fx - 14, Y1, fx + 14, Y1 + 20, 1))
    c.paint(oklch(0.3, 0.03, 60), blur(rect(W, H, 40, Y1 + 18, 460, Y1 + 28, 1), 5) * 0.25)
    save(c.image(), ART / "tv-walnut.webp", quality=88)


@piece
def space_room():
    """My Space: a tatami room in the morning, in the hero's ink. The floor is drawn in true
    perspective: 2:1 mats with their heri on the long edges, a rhombus of shoji light across
    them, a square zabuton with its shadow. The wall: shoji on the left, the alcove on the right
    with a scroll and one branch. Composed for the phone's centre band (rows 90–345)."""
    W, H = 960, 432
    c = Canvas(W, H, KINARI)
    x, y = grid_xy(W, H)
    HZ, VX, FH, F = 118.0, 470.0, 312.0, 430.0  # horizon, vanishing x, camera height × focal, focal
    back = HZ + FH / 2.35  # the wall meets the floor
    # ---- the floor: every pixel's place on the ground (u across, z away)
    z = np.where(y > back - 1, FH / np.maximum(y - HZ, 1e-3), 0)
    u = (x - VX) * z / F
    floor = np.clip(y - back + 0.5, 0, 1)
    # mats of 1 × 0.5: the back rows run away from us, the front row lies across
    long_away = z > 1.45
    zz = z - 1.45
    uu = np.where(long_away, u / 0.5, u / 1.0 + 0.5)
    vv = np.where(long_away, zz / 1.0, (z - 1.0) / 0.45)
    fu, fv = uu - np.floor(uu), vv - np.floor(vv)
    reeds = np.where(long_away, np.sin(zz * 2 * math.pi / 0.012), np.sin(u * 2 * math.pi / 0.012))
    mat = oklch(0.82, 0.05, 92)[None, None, :] * (1 + reeds[..., None] * 0.02 + smooth_noise(H, W, 3, 30)[..., None] * 0.02)
    c.paint(mat, floor)
    # heri on each mat's long edges (thicker nearer), the short edges a thin groove
    hw = 0.035  # the heri's width, in mat widths
    long_edge = np.where(long_away, np.minimum(fu, 1 - fu) < hw, np.minimum(fv, 1 - fv) < hw * 1.2)
    short_edge = np.where(long_away, np.minimum(fv, 1 - fv) < 0.006 * z, np.minimum(fu, 1 - fu) < 0.004 * z)
    heri_c = oklch(0.27, 0.03, 250)
    c.paint(heri_c, blur(long_edge * floor * 1.0, 0.6) * 0.9)
    c.paint(oklch(0.62, 0.05, 88), blur(short_edge * floor * 1.0, 0.6) * 0.6)
    # the shoji's light on the mats: a soft rhombus, thrown down and to the right
    lx0, lx1, lz0, lz1 = -1.35, -0.35, 1.55, 2.25
    shear = (z - lz0) * 0.55
    rhombus = ((u - shear > lx0) & (u - shear < lx1) & (z > lz0) & (z < lz1)) * floor
    c.paint(np.array([1, 0.985, 0.92]), blur(rhombus * 1.0, 8) * 0.75)
    # ---- the wall: shoji on the left, lit; posts and a lintel in walnut; the alcove
    wall = 1 - floor
    c.paint(oklch(0.9, 0.024, 78), wall * np.clip(1 - (y - back) , 0, 1))
    sx0, sx1, top = 40, 400, 30
    shoji = rect(W, H, sx0, top, sx1, back, 0.8)
    c.paint(np.array([1, 0.985, 0.94]), shoji)
    c.paint(np.array([0.97, 0.94, 0.86]), fibres(W, H, 9, 400, (6, 20), (0.5, 0.9), wrap=False) * shoji * 0.4)
    bars = np.zeros((H, W))
    for gx in np.linspace(sx0, sx1, 7):
        bars = np.maximum(bars, rect(W, H, gx - 2, top, gx + 2, back, 0.8))
    for gy in np.linspace(top, back, 6):
        bars = np.maximum(bars, rect(W, H, sx0, gy - 2, sx1, gy + 2, 0.8))
    c.paint(oklch(0.72, 0.045, 74), bars * shoji)
    c.paint(oklch(0.86, 0.03, 74), rect(W, H, 580, top, 920, back - 16, 0.8))  # the alcove, deeper
    c.paint(oklch(0.4, 0.04, 55), rect(W, H, 580, back - 22, 920, back - 10, 0.8))
    # scroll with an ensō, a vase with one branch and its red bud
    c.paint(oklch(0.72, 0.055, 68), rect(W, H, 720, 44, 776, 206, 0.8))
    c.paint(WASHI_LIT, rect(W, H, 726, 62, 770, 184, 0.8))
    paste(c, enso(40, 3, 0.14, 40), 728, 96)
    b = Brush(W, H, 90)
    b.c = c
    b.wash([(854, 250), (872, 250), (880, 226), (870, 208), (858, 208), (846, 226)], 0.8, light=0.5)
    b.brush([(863, 208), (858, 172), (844, 144), (822, 124)], 4, 0.9, dry=0.3, bristles=4, taper_to=0.3)
    b.dab(822, 124, 4, 0.95, colour=HANKO)
    # ink contours: posts, lintel, the wall's foot, the alcove's frame (dry, bled)
    for px in (sx0 - 8, sx1 + 6, 570, 922):
        b.brush([(px, 0), (px, back + 2)], 12, 0.8, dry=0.25, bristles=6, taper_to=0.9, smooth=False, colour=WALNUT)
    b.brush([(0, 16), (W, 16)], 12, 0.85, dry=0.3, bristles=6, taper_to=0.9, smooth=False, colour=WALNUT)
    b.brush([(0, back), (W, back)], 5, 0.8, dry=0.2, bristles=4, taper_to=1, smooth=False)
    # the zabuton: a square on the floor, indigo, its shadow soft to the lower right
    def ground(uq, zq):
        return (VX + uq * F / zq, HZ + FH / zq)
    sq = [ground(0.12, 1.62), ground(0.52, 1.62), ground(0.52, 1.25), ground(0.12, 1.25)]
    shadow = [(px + 12, py + 6) for px, py in sq]
    c.paint(oklch(0.3, 0.03, 60), blur(polygon_mask(W, H, shadow), 7) * 0.3)
    front = [sq[3], sq[2], (sq[2][0], sq[2][1] + 12), (sq[3][0], sq[3][1] + 12)]
    b.wash(front, 0.95, colour=oklch(0.28, 0.04, 250), light=0.2, smooth=False, bleed_px=0.6)
    b.wash([(sq[0][0], sq[0][1] - 4), (sq[1][0], sq[1][1] - 4), sq[2], sq[3]], 0.9, colour=oklch(0.38, 0.05, 250), light=0.5, pool=0.25, smooth=False, bleed_px=0.6)
    cx_, cy_ = ground(0.32, 1.42)
    b.dab(cx_, cy_ - 2, 3, 0.8, colour=oklch(0.25, 0.03, 250))
    img = paper_grain(c.image(), 0.01, 2)
    save(img.convert("RGB"), ART / "space-tatami.webp", quality=84)

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PIECES)
    for name in wanted:
        print(name)
        PIECES[name]()
