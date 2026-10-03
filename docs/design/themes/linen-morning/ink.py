"""Kinari's painting kit: numpy and Pillow only. Colours from OKLCH, periodic noise, blur, ink
washes with bleeding edges, washi fibres, brush strokes. make.py draws every picture with it."""

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


# ---------- colour ----------
def oklch(L, C, h):
    """OKLCH → sRGB floats 0–1 (clipped)."""
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(x):
        x = min(1.0, max(0.0, x))
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return np.array([enc(r), enc(g), enc(bb)])


# The theme's inks (tokens.py has the same values).
SUMI = oklch(0.25, 0.014, 55)
SUMI_DEEP = oklch(0.2, 0.012, 55)
WALNUT = oklch(0.37, 0.04, 52)
WALNUT_LIGHT = oklch(0.5, 0.05, 58)
KRAFT = oklch(0.62, 0.07, 66)
KRAFT_LIGHT = oklch(0.8, 0.05, 72)
HINOKI = oklch(0.84, 0.045, 78)
KINARI = oklch(0.925, 0.021, 80)
WASHI = oklch(0.958, 0.013, 84)
WASHI_LIT = oklch(0.975, 0.012, 88)
HANKO = oklch(0.55, 0.175, 33)
HANKO_DEEP = oklch(0.47, 0.16, 31)
TATAMI = oklch(0.8, 0.06, 98)
TATAMI_DEEP = oklch(0.7, 0.065, 95)
INDIGO = oklch(0.3, 0.05, 255)
MATCHA = oklch(0.55, 0.08, 128)


# ---------- noise and blur ----------
def smooth_noise(h, w, seed, size):
    """Soft periodic noise with features around `size` px, -1..1."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((h, w))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-(fx**2 + fy**2) * (math.pi * size) ** 2 / 2)
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * g))
    out -= out.mean()
    return out / (np.abs(out).max() + 1e-9)


def blur(a, sigma, wrap=False):
    """Gaussian blur of a 2-D array (or each channel of a 3-D one); edges padded unless `wrap`."""
    if sigma <= 0:
        return a
    if a.ndim == 3:
        return np.dstack([blur(a[..., i], sigma, wrap) for i in range(a.shape[2])])
    pad = 0 if wrap else int(sigma * 3) + 1
    b = np.pad(a, pad, mode="edge") if pad else a
    h, w = b.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2 * (math.pi * sigma) ** 2 * (fx**2 + fy**2))
    out = np.real(np.fft.ifft2(np.fft.fft2(b) * g))
    return out[pad : pad + a.shape[0], pad : pad + a.shape[1]] if pad else out


def ridge(n, seed, rough=0.55, octaves=7):
    """A 1-D fractal line of n samples, -1..1 (mountain ridges, brush wobble)."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, n)
    out = np.zeros(n)
    amp, freq = 1.0, 2
    for _ in range(octaves):
        pts = rng.uniform(-1, 1, freq + 3)
        xs = np.linspace(0, 1, freq + 3)
        # smooth (cosine) interpolation between control points
        idx = np.clip((x * (freq + 2)).astype(int), 0, freq + 1)
        t = x * (freq + 2) - idx
        t = (1 - np.cos(t * math.pi)) / 2
        out += amp * (pts[idx] * (1 - t) + pts[idx + 1] * t)
        amp *= rough
        freq *= 2
    return out / (np.abs(out).max() + 1e-9)


# ---------- images ----------
class Canvas:
    """Premultiplied RGBA float canvas; paint() lays a colour through an alpha mask (0–1)."""

    def __init__(self, w, h, ground=None):
        self.w, self.h = w, h
        self.rgb = np.zeros((h, w, 3))
        self.a = np.zeros((h, w))
        if ground is not None:
            self.rgb[:] = ground
            self.a[:] = 1

    def paint(self, colour, mask):
        mask = np.clip(mask, 0, 1)
        colour = np.asarray(colour, float)
        if colour.ndim == 1:
            colour = colour[None, None, :]
        self.rgb = self.rgb * (1 - mask[..., None]) + colour * mask[..., None]
        self.a = self.a * (1 - mask) + mask

    def image(self):
        a = np.clip(self.a, 0, 1)
        rgb = np.where(a[..., None] > 1e-6, self.rgb / np.maximum(a[..., None], 1e-6), 0)
        arr = np.dstack([np.clip(rgb, 0, 1) * 255, a * 255]).round().astype(np.uint8)
        return Image.fromarray(arr, "RGBA")


def grid_xy(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(float)
    return x, y


def disc(w, h, cx, cy, r, soft=1.0):
    x, y = grid_xy(w, h)
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    return np.clip((r - d) / soft + 0.5, 0, 1)


def rect(w, h, x0, y0, x1, y1, soft=1.0):
    x, y = grid_xy(w, h)
    m = np.minimum.reduce([x - x0, x1 - x, y - y0, y1 - y]) / soft + 0.5
    return np.clip(m, 0, 1)


def polygon_mask(w, h, points, ss=4):
    """An anti-aliased filled polygon (points in px)."""
    im = Image.new("L", (w * ss, h * ss))
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in points], fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), float) / 255


def stroke_mask(w, h, points, widths, ss=4):
    """A brush stroke along points with a width per point (round joints), anti-aliased."""
    im = Image.new("L", (w * ss, h * ss))
    d = ImageDraw.Draw(im)
    pts = [(x * ss, y * ss) for x, y in points]
    for (x0, y0), (x1, y1), w0 in zip(pts, pts[1:], widths):
        r = max(0.5, w0 * ss / 2)
        d.line([(x0, y0), (x1, y1)], fill=255, width=int(round(r * 2)))
        d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), float) / 255


def dry_brush(mask, seed, streak=0.35, along="x", size=1.2):
    """Break a stroke's mask with dry-brush streaks: bristle lines where the ink runs out."""
    h, w = mask.shape
    rng = np.random.default_rng(seed)
    lines = rng.random(h)[:, None] * np.ones((1, w)) if along == "x" else rng.random(w)[None, :] * np.ones((h, 1))
    lines = blur(lines, 0.6)
    n = smooth_noise(h, w, seed + 1, 18 * size) * 0.5 + 0.5
    keep = np.clip((lines - streak * (1 - n)) * 3 + 0.4, 0, 1)
    return mask * keep


def bleed(mask, seed, amount=1.5, size=3.0):
    """Ink bleeding into paper: a displaced, slightly blurred edge with fibre-like feathering."""
    h, w = mask.shape
    nx = smooth_noise(h, w, seed, size) * amount * 2
    ny = smooth_noise(h, w, seed + 7, size) * amount * 2
    x, y = grid_xy(w, h)
    xi = np.clip(np.round(x + nx), 0, w - 1).astype(int)
    yi = np.clip(np.round(y + ny), 0, h - 1).astype(int)
    out = mask[yi, xi]
    return blur(out, amount * 0.35)


def fibres(w, h, seed, count, length=(20, 80), width=(0.5, 1.2), wrap=True, ss=3):
    """Washi's long kozo fibres: thin curving hairs, an alpha mask (0–1), tiles when `wrap`."""
    rng = np.random.default_rng(seed)
    im = Image.new("L", (w * ss, h * ss))
    d = ImageDraw.Draw(im)
    offsets = [(dx, dy) for dx in (-w, 0, w) for dy in (-h, 0, h)] if wrap else [(0, 0)]
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        ang = rng.uniform(0, math.pi * 2)
        L = rng.uniform(*length)
        wd = rng.uniform(*width)
        bend = rng.normal(0, 0.03)
        pts = []
        steps = max(4, int(L / 3))
        for i in range(steps):
            pts.append((x, y))
            ang += bend + rng.normal(0, 0.05)
            x += math.cos(ang) * L / steps
            y += math.sin(ang) * L / steps
        val = int(rng.uniform(120, 255))
        for dx, dy in offsets:
            d.line([((px + dx) * ss, (py + dy) * ss) for px, py in pts], fill=val, width=max(1, int(wd * ss)))
    return np.asarray(im.resize((w, h), Image.LANCZOS), float) / 255


def overlay_from_delta(delta, light=np.array([1.0, 0.99, 0.95]), dark=WALNUT):
    """A transparent texture that lightens where delta > 0 and darkens where delta < 0 on any
    light ground (delta in 0–1 lightness units against a ground of about L 0.93)."""
    h, w = delta.shape
    out = np.zeros((h, w, 4))
    lift = np.clip(delta, 0, None) / 0.07  # 0.07 is the room between the ground and paper-white
    sink = np.clip(-delta, 0, None) / 0.6
    a = np.clip(lift + sink, 0, 1)
    colour = np.where((delta >= 0)[..., None], light[None, None, :], dark[None, None, :])
    out[..., :3] = colour
    out[..., 3] = a
    return Image.fromarray((out * 255).round().astype(np.uint8), "RGBA")


def to_image(rgb, alpha=None):
    rgb = np.clip(rgb, 0, 1)
    if alpha is None:
        return Image.fromarray((rgb * 255).round().astype(np.uint8), "RGB")
    return Image.fromarray(np.dstack([rgb, np.clip(alpha, 0, 1)]).__mul__(255).round().astype(np.uint8), "RGBA")


def paper_grain(img: Image.Image, amount=0.02, seed=1):
    """Monochrome grain on the opaque parts, so flat washes don't look plastic."""
    arr = np.asarray(img).astype(float) / 255
    rng = np.random.default_rng(seed)
    g = rng.normal(0, amount, arr.shape[:2])
    arr[..., :3] = np.clip(arr[..., :3] + g[..., None], 0, 1)
    return Image.fromarray((arr * 255).round().astype(np.uint8), img.mode)


def save(img: Image.Image, path, quality=82, lossless=False, budget=200_000, alpha_quality=90):
    """WebP or PNG, written atomically; refuses a file over the 200 KB budget."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    if path.suffix == ".webp":
        img.save(tmp, "WEBP", quality=quality, method=6, lossless=lossless, exact=False, alpha_quality=alpha_quality)
    else:
        img.save(tmp, "PNG", optimize=True)
    size = tmp.stat().st_size
    if size > budget:
        tmp.unlink()
        raise SystemExit(f"{path.name}: {size} bytes, over the {budget} budget")
    os.replace(tmp, path)
    print(f"  {path.name}: {img.size[0]}×{img.size[1]}, {size // 1024} KB")
    return path
