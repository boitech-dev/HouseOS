"""Pixel drawing helpers for Pocket Hatchling (Pillow, aliased: every edge is a whole pixel).
Light comes from the top left: `shade()` puts a highlight rim top-left and a shadow rim
bottom-right on any shape, so every blob, cloud and sticker is lit the same way."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "themes" / "_kit" / "art"))
import pixel  # noqa: E402  (the kit: rgba, grid, scale, sheet, save, Palette)
from pal import ALL, INK, WHITE  # noqa: E402

rgba = pixel.rgba
PALETTE = pixel.Palette(all=ALL)


def new(w, h, fill=None):
    return Image.new("RGBA", (w, h), rgba(fill) if fill else (0, 0, 0, 0))


def mask_of(im):
    return im.getchannel("A").point(lambda a: 255 if a else 0)


def ellipse(im, box, fill):
    ImageDraw.Draw(im).ellipse(box, fill=rgba(fill))
    return im


def rect(im, box, fill):
    ImageDraw.Draw(im).rectangle(box, fill=rgba(fill))
    return im


def poly(im, pts, fill):
    ImageDraw.Draw(im).polygon(pts, fill=rgba(fill))
    return im


def line(im, pts, fill, width=1):
    ImageDraw.Draw(im).line(pts, fill=rgba(fill), width=width)
    return im


def px(im, x, y, fill):
    if 0 <= x < im.width and 0 <= y < im.height:
        im.putpixel((x, y), rgba(fill))


def grid(rows, legend):
    return pixel.grid(rows, legend)


def paste(dst, src, xy):
    dst.alpha_composite(src, (int(xy[0]), int(xy[1])))
    return dst


def ring(im, colour, diagonal=False, grow=True):
    """A 1 px line around the opaque shape. grow: the picture gets 1 px bigger on each side."""
    src = im
    if grow:
        src = new(im.width + 2, im.height + 2)
        src.alpha_composite(im, (1, 1))
    a = src.getchannel("A").load()
    out = src.copy()
    near = [(1, 0), (-1, 0), (0, 1), (0, -1)] + ([(1, 1), (1, -1), (-1, 1), (-1, -1)] if diagonal else [])
    w, h = src.size
    for y in range(h):
        for x in range(w):
            if a[x, y]:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and a[x + dx, y + dy] for dx, dy in near):
                out.putpixel((x, y), rgba(colour))
    return out


def outline(im, colour=INK, grow=True):
    return ring(im, colour, False, grow)


def sticker(im, border=WHITE, ink=INK):
    """Die-cut: a white border (rounded, 8 neighbours) and the plum outline outside it."""
    return outline(ring(im, border, True), ink)


def shade(im, light=None, dark=None, rim=1, keep=None):
    """Light from the top left: pixels whose up-left neighbour (rim px away) is outside the shape
    take `light`; those whose down-right neighbour is outside take `dark`. `keep`: colours left
    alone (outlines, features)."""
    out = im.copy()
    a = im.getchannel("A").load()
    src = im.load()
    keep = {rgba(c)[:3] for c in (keep or [INK]) if c}
    w, h = im.size
    inside = lambda x, y: 0 <= x < w and 0 <= y < h and a[x, y] and src[x, y][:3] not in keep
    for y in range(h):
        for x in range(w):
            if not inside(x, y):
                continue
            if dark and not all(inside(x + d, y + d) for d in range(1, rim + 1)):
                out.putpixel((x, y), rgba(dark))
            elif light and not all(inside(x - d, y - d) for d in range(1, rim + 1)):
                out.putpixel((x, y), rgba(light))
    return out


def recolour(im, mapping):
    m = {rgba(k)[:3]: rgba(v) for k, v in mapping.items()}
    out = im.copy()
    data = [m.get(p[:3], p) if p[3] else p for p in im.getdata()]
    out.putdata(data)
    return out


def flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def blob(w, h, fill):
    """An aliased ellipse filling a w × h box."""
    return ellipse(new(w, h), (0, 0, w - 1, h - 1), fill)


def puffs(w, h, bumps, fill, edge, dark=None):
    """Round puffs drawn back to front, each ringed in `edge` so the one in front shows its
    curve: clouds, cloud banks, cotton. bumps: (cx, cy, r)."""
    im = new(w, h)
    d = ImageDraw.Draw(im)
    for cx, cy, r in bumps:
        d.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), fill=rgba(edge))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rgba(fill))
    if dark:
        im = shade(im, None, dark, rim=2, keep=[edge])
    return im


def cloud(w, h, fill, seed=0, edge=None, dark=None):
    """A puffy cloud on a flat bottom: three to five round bumps, the middle ones tallest; the
    bumps' curves show on its upper half only, like a drawn cloud."""
    import random
    rnd = random.Random(seed)
    n = 3 if w < 30 else 4 if w < 50 else 5
    bumps = []
    for i in range(n):
        t = (i + 0.5) / n
        r = int(h * (0.34 + 0.26 * (1 - abs(t - 0.5) * 2)) + rnd.randint(-1, 1))
        cx = int(r + 1 + t * (w - 2 * r - 2))
        bumps.append((cx, h - 2 - r, r))
    im = puffs(w, h, bumps, fill, edge or fill)
    for cx, cy, r in bumps:
        rect(im, (cx - r, cy + 1, cx + r, h - 2), fill)
    rect(im, (bumps[0][0], h - 2 - bumps[0][2], bumps[-1][0], h - 2), fill)
    if dark:
        im = shade(im, None, dark, rim=2, keep=[edge] if edge else None)
    return im


def lock(im, name):
    return PALETTE.lock(im, name)


def save(im, path, zoom=1):
    """Lock to the palette, scale by a whole number and save as an exact palette PNG (every
    colour kept as drawn, transparency per entry): pixel art stays small."""
    lock(im, Path(path).name)
    out = pixel.scale(im, zoom) if zoom > 1 else im
    colours = sorted({p if p[3] else (0, 0, 0, 0) for p in out.getdata()})
    if len(colours) > 256:
        out.save(path, optimize=True)
        return Path(path)
    index = {c: i for i, c in enumerate(colours)}
    p = Image.new("P", out.size)
    p.putdata([index[q if q[3] else (0, 0, 0, 0)] for q in out.getdata()])
    p.putpalette([v for c in colours for v in c[:3]])
    p.save(path, optimize=True, transparency=bytes(c[3] for c in colours))
    return Path(path)
