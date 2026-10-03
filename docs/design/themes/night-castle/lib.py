"""Drawing helpers for night-castle: native-size pixel canvases, one light (the moon, up-right),
the SNES palette locked on every picture, saved at a whole-number scale."""
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "themes/_kit/art"))
sys.path.insert(0, str(HERE))
import pixel  # noqa: E402
from palette import ALL  # noqa: E402

ART = ROOT / "themes/night-castle/art"
PAL = pixel.Palette(all=ALL)
SCALE = 3  # the theme's one pixel size: every native pixel is 3 × 3 screen pixels
BAYER = pixel.BAYER


def new(w, h, colour=None):
    return Image.new("RGBA", (w, h), pixel.rgba(colour) if colour else (0, 0, 0, 0))


def put(im, x, y, c):
    if 0 <= x < im.width and 0 <= y < im.height:
        im.putpixel((int(x), int(y)), pixel.rgba(c) if c else (0, 0, 0, 0))


def get(im, x, y):
    if 0 <= x < im.width and 0 <= y < im.height:
        return im.getpixel((int(x), int(y)))
    return (0, 0, 0, 0)


def rect(im, x0, y0, x1, y1, c):
    """Inclusive-exclusive box fill."""
    ImageDraw.Draw(im).rectangle((x0, y0, x1 - 1, y1 - 1), fill=pixel.rgba(c))


def poly(im, pts, c):
    ImageDraw.Draw(im).polygon(pts, fill=pixel.rgba(c))


def hline(im, x0, x1, y, c):
    for x in range(x0, x1):
        put(im, x, y, c)


def vline(im, x, y0, y1, c):
    for y in range(y0, y1):
        put(im, x, y, c)


def disc(im, cx, cy, r, c):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                put(im, x, y, c)


def dith(t, x, y):
    """True where an ordered dither of strength t (0..1) lands."""
    return t * 16 > BAYER[y % 4][x % 4] + 0.5


def vgrad(im, box, colours, dithered=True):
    pixel.bands(im, box, colours, vertical=True, dithered=dithered)


def stars(im, box, seed, density, colours):
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    n = int((x1 - x0) * (y1 - y0) * density)
    for _ in range(n):
        x, y = rnd.randrange(x0, x1), rnd.randrange(y0, y1)
        c = rnd.choice(colours)
        put(im, x, y, c)


def twinkle_star(im, x, y, core, glow):
    put(im, x, y, core)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        put(im, x + dx, y + dy, glow)


def fade_alpha(im, left=0, bottom=0, top=0, right=0):
    """Dither the picture out to transparent over `left` px from the left edge, etc."""
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            t = 1.0
            if left:
                t = min(t, x / left)
            if right:
                t = min(t, (im.width - 1 - x) / right)
            if bottom:
                t = min(t, (im.height - 1 - y) / bottom)
            if top:
                t = min(t, y / top)
            if t < 1 and not dith(max(0, t), x, y):
                px[x, y] = (0, 0, 0, 0)
    return im


def outline(im, c, sides=((1, 0), (-1, 0), (0, 1), (0, -1))):
    """A 1-px outline around opaque pixels, in place (no growth: stays inside the canvas)."""
    src = im.copy()
    for y in range(im.height):
        for x in range(im.width):
            if src.getpixel((x, y))[3]:
                continue
            for dx, dy in sides:
                if get(src, x + dx, y + dy)[3]:
                    put(im, x, y, c)
                    break
    return im


def paste(dst, src, x, y):
    dst.alpha_composite(src, (int(x), int(y)))


def flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def sprite(rows, legend):
    return pixel.grid(rows, legend)


def save(im, name, scale=SCALE):
    """Lock to the palette, scale by a whole number, save as a palette PNG."""
    PAL.lock(im, name)
    out = pixel.scale(im, scale) if scale > 1 else im
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / name
    data = list(out.convert("RGBA").getdata())
    data = [(0, 0, 0, 0) if a == 0 else (r, g, b, a) for r, g, b, a in data]
    colours = sorted(set(data))
    if len(colours) <= 256:
        index = {c: i for i, c in enumerate(colours)}
        pal = Image.new("P", out.size)
        pal.putdata([index[c] for c in data])
        pal.putpalette([v for c in colours for v in c[:3]])
        pal.info["transparency"] = bytes(c[3] for c in colours)
        pal.save(path, optimize=True, transparency=bytes(c[3] for c in colours))
        assert list(Image.open(path).convert("RGBA").getdata()) == data, name
    else:
        out.save(path, optimize=True)
    return path


def lerp(a, b, t):
    return a + (b - a) * t


def noise(seed):
    rnd = random.Random(seed)
    return rnd


def circle_pts(cx, cy, r, n=64, a0=0, a1=2 * math.pi):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
