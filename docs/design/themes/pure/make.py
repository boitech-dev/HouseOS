"""Pure: every picture, from code. Run from the repository root:

    python3 docs/design/themes/pure/make.py            # render every scene, then finish the art
    python3 docs/design/themes/pure/make.py --no-render # finish from the last renders only
    python3 docs/design/themes/pure/make.py hero crest  # only these

Renders (Blender, scenes/*.py, one sun, one concrete) land in /tmp/pure-renders; the finishing
step turns each into the theme's art in themes/pure/art/.

One picture serves both schemes, because a slot has one picture: each render is split into
light and shadow around a middle grey. The light is kept as warm white with its own alpha, the
shadow as black ink with its own alpha. Over the black ground only the light shows (a low-key
print); over the cream paper only the shadow shows (a high-key print): the negative of each
other, from the same negative."""
import os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ART = "themes/pure/art"
RENDERS = os.environ.get("PURE_RENDERS", "/tmp/pure-renders")
BLENDER = os.environ.get("HOUSEOS_BLENDER", os.path.expanduser("~/.local/bin/blender"))
LIGHT = np.array([251, 247, 238]) / 255.0   # the sun's white (a hair of cream)
SHADOW = np.array([12, 11, 10]) / 255.0     # ink
DARK_GROUND = np.array([0, 0, 0]) / 255.0
LIGHT_GROUND = np.array([238, 232, 219]) / 255.0


def render(scene, w, h, samples=128, **extra):
    """Render a scene; `extra` (VARIANT, AMBIENT, SUNANGLE, HAZE...) goes to it as environment."""
    env = dict(os.environ, W=str(w), H=str(h), S=str(samples), PURE_RENDERS=RENDERS, **{k: str(v) for k, v in extra.items()})
    subprocess.run([BLENDER, "-b", "--factory-startup", "-P", f"{HERE}/scenes/{scene}.py"], check=True,
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    name = f"{scene}-{os.environ.get('ROOM')}" if scene == "banner" else scene
    if extra.get("VARIANT"):
        name += "-" + extra["VARIANT"]
    return os.path.join(RENDERS, name + ".png")


def luminance(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float64) / 255.0
    return a @ np.array([0.2126, 0.7152, 0.0722])


def clean(img, size=3):
    """Denoise a print's alpha (render grain made the paper prints smudgy): a median, then the
    small rest of the grain is left to the webp."""
    r, g, b, a = img.split()
    return Image.merge("RGBA", (r, g, b, a.filter(ImageFilter.MedianFilter(size))))


def vignette(shape, inner=0.55, outer=1.0):
    """1 in the middle, fading to 0 at the edges (a pool, not a rectangle)."""
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    r = np.hypot((x - w / 2) / (w / 2), (y - h / 2) / (h / 2))
    return np.clip((outer - r) / (outer - inner), 0, 1) ** 1.5


def drawing(L, thr=0.35, line=2, fill=0.8, ink=0.85, close=7, dots=True, edge_ink=None):
    """The paper print of a patch of sun, drawn rather than photographed: the lit shapes filled
    with light, outlined by a crisp ink line `line` px wide, and the form-tie holes that fall in
    them as ink dots. Nothing else: the rest is clean paper."""
    lit = Image.fromarray(((L > thr) * 255).astype(np.uint8))
    hull = lit.filter(ImageFilter.MaxFilter(close)).filter(ImageFilter.MinFilter(close))
    h = np.asarray(hull) > 127
    inner = np.asarray(hull.filter(ImageFilter.MinFilter(2 * line + 1))) > 127
    edge = h & ~inner
    holes = h & ~(np.asarray(lit) > 127) & inner if dots else np.zeros_like(h)
    a = np.zeros(L.shape + (4,))
    a[h] = [*LIGHT, fill]
    if edge_ink is None or edge_ink > 0:
        a[edge] = [*SHADOW, ink if edge_ink is None else edge_ink]
    a[holes] = [*SHADOW, ink]
    return Image.fromarray((a * 255).round().astype(np.uint8), "RGBA")


def split(L, mid=0.14, light_gain=1.0, shadow_gain=0.85, light_gamma=1.0, shadow_gamma=1.0, grain=0.0, seed=1,
          shadow_mask=None, floor=0.0, mask=None):
    """Luminance (0–1, display) → RGBA: light above `mid`, shadow below it."""
    if grain:
        rng = np.random.default_rng(seed)
        L = np.clip(L + rng.normal(0, grain, L.shape), 0, 1)
    up = np.clip((L - mid) / (1 - mid), 0, 1) ** light_gamma * light_gain
    up = np.clip((up - floor) / (1 - floor), 0, 1)  # no haze: the faintest light goes to black
    down = np.clip((mid - L) / mid, 0, 1) ** shadow_gamma * shadow_gain
    if shadow_mask is not None:
        down = down * shadow_mask
    alpha = np.clip(up + down, 0, 1)
    if mask is not None:
        alpha = alpha * mask
    light = up > 0
    rgb = np.where(light[..., None], LIGHT, SHADOW)
    out = np.dstack([rgb, alpha])
    return Image.fromarray((out * 255).round().astype(np.uint8), "RGBA")


def over(img, ground):
    a = np.asarray(img).astype(np.float64) / 255.0
    rgb = a[..., :3] * a[..., 3:] + ground * (1 - a[..., 3:])
    return Image.fromarray((rgb * 255).round().astype(np.uint8), "RGB")


def preview(img, name):
    """Both schemes side by side, to look at: /tmp/pure-renders/<name>-both.png."""
    w, h = img.size
    both = Image.new("RGB", (w, h * 2 + 8), (128, 128, 128))
    both.paste(over(img, DARK_GROUND), (0, 0))
    both.paste(over(img, LIGHT_GROUND), (0, h + 8))
    both.save(os.path.join(RENDERS, f"{name}-both.png"))


def save(img, name, quality=82, alpha_step=4):
    path = os.path.join(ART, name)
    if name.endswith(".webp"):
        if img.mode == "RGBA" and alpha_step > 1:  # render grain in the alpha: 64 levels and a
            r, g, b, a = img.split()          # hair of blur keep it smooth and small
            a = a.filter(ImageFilter.GaussianBlur(0.5))
            a = Image.fromarray((np.asarray(a) // alpha_step * alpha_step).astype(np.uint8))
            img = Image.merge("RGBA", (r, g, b, a))
        img.save(path, "WEBP", quality=quality, alpha_quality=100, method=6)
    else:
        img.save(path, optimize=True)
    size = os.path.getsize(path)
    assert size <= 200_000, f"{name}: {size} bytes"
    print(f"  {name}: {img.size[0]}×{img.size[1]}, {size // 1000} KB")
    preview(img, name.split(".")[0])


# ---------------------------------------------------------------- the pictures
def hero(do_render):
    src = render("hero", 1320, 440, 160) if do_render and not os.environ.get("ONLY_LIGHT") else f"{RENDERS}/hero.png"
    L = luminance(src)
    # each scheme its own print of the same negative: the night print keeps the wall's low tones
    save(split(L, mid=0.03, shadow_gain=0, light_gamma=0.9, floor=0.02), "hero-stair.webp")
    # the paper print from its own render: no haze, a crisper sun, many samples; then denoised
    src = render("hero", 1320, 440, 512, VARIANT="light", HAZE=0, SUNANGLE=0.1, BOUNCES=0, AMBIENT=3.4) if do_render else f"{RENDERS}/hero-light.png"
    L = luminance(src)
    save(clean(split(L, mid=0.82, shadow_gain=1.0)), "hero-stair-light.webp")


def page(do_render):
    src = render("page", 1600, 900, 256, SUNANGLE=0.06) if do_render else f"{RENDERS}/page.png"
    L = luminance(src)
    save(split(L, mid=0.125, shadow_gain=0, shadow_gamma=0.8), "page-wall.webp")
    # the paper print: the wall is clean paper; only the window's patch is drawn, its outline in
    # ink and the six form-tie holes it falls on
    save(drawing(L, thr=0.45, line=2, fill=0.9, ink=0.9, close=9, edge_ink=0.0), "page-wall-light.webp", alpha_step=1)


def convex(mask):
    """The convex hull of a mask, filled (Andrew's monotone chain on its pixels' corners)."""
    ys, xs = np.nonzero(mask)
    pts = sorted(set(zip(xs.tolist(), ys.tolist())))
    def half(points):
        out = []
        for p in points:
            while len(out) >= 2 and (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0]) <= 0:
                out.pop()
            out.append(p)
        return out
    hull = half(pts)[:-1] + half(pts[::-1])[:-1]
    m = Image.new("L", (mask.shape[1], mask.shape[0]), 0)
    ImageDraw.Draw(m).polygon(hull, fill=255)
    return np.asarray(m) > 127


def empty(do_render):
    src = render("empty", 384, 384, 384, SUNANGLE=0.08) if do_render else f"{RENDERS}/empty.png"
    L = luminance(src)
    lit = L > 0.3
    patch = convex(lit)
    core = np.asarray(Image.fromarray((patch * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 127
    bird = core & ~lit
    # night: the patch of sun, the bird a hole in it. Paper: the patch drawn, the bird in ink.
    night = np.zeros(L.shape + (4,)); night[..., :3] = LIGHT
    night[..., 3] = np.clip((L - 0.2) / 0.8, 0, 1) * 0.95
    inner = np.asarray(Image.fromarray((patch * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5))) > 127
    day = np.zeros(L.shape + (4,))
    day[patch] = [*LIGHT, 0.95]
    day[patch & ~inner] = [*SHADOW, 0.9]
    day[bird] = [*SHADOW, 0.9]
    for img, name in ((night, "empty-sill.webp"), (day, "empty-sill-light.webp")):
        im = Image.fromarray((img * 255).round().astype(np.uint8), "RGBA").resize((192, 192), Image.LANCZOS)
        save(im, name, alpha_step=1)
    ys, xs = np.nonzero(patch); by, bx = np.nonzero(bird)
    print(f"  bird / patch width: {(bx.max() - bx.min()) / (xs.max() - xs.min()):.2f}")


def crest(do_render):
    src = render("crest", 320, 320, 384) if do_render else f"{RENDERS}/crest.png"
    save(clean(split(luminance(src), mid=0.015, shadow_gain=0, light_gamma=0.9)), "crest-opening.webp", alpha_step=1)
    src = render("crest", 320, 320, 384, VARIANT="light", SUNANGLE=0.08) if do_render else f"{RENDERS}/crest-light.png"
    # the day print over the paper: the paper is the block's light; its shadow and the void are ink
    save(clean(split(luminance(src), mid=0.82, shadow_gain=1.0, light_gamma=1.0)), "crest-opening-light.webp", alpha_step=1)


ROOMS = ["default", "listen", "watch", "house", "files", "games", "me", "control", "smart-home", "inbox",
         "party", "ask"]


def fade_left(img, start=0.28, end=0.55):
    """The banner's words sit on the left: the picture is clear there, whatever the crop."""
    a = np.asarray(img).astype(np.float64)
    w = a.shape[1]
    x = np.linspace(0, 1, w)
    k = np.clip((x - start) / (end - start), 0, 1)
    k = k * k * (3 - 2 * k)
    a[..., 3] *= k[None, :]
    return Image.fromarray(a.round().astype(np.uint8), "RGBA")


def banners(do_render):
    for room in ROOMS:
        src = f"{RENDERS}/banner-{room}.png"
        if do_render:
            os.environ["ROOM"] = room
            src = render("banner", 1800, 240, 128)
        L = luminance(src)
        ys, xs = np.nonzero(np.asarray(Image.fromarray(((L > 0.35) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))))
        print(f"  {room}: light from {xs.min() / L.shape[1]:.0%} to {xs.max() / L.shape[1]:.0%} of the width, "
              f"{ys.min() * 160 // L.shape[0]}–{ys.max() * 160 // L.shape[0]} px from the top (of 160)")
        save(split(L, mid=0.2, shadow_gain=0, light_gamma=0.9), f"banner-{room}.webp", alpha_step=1)
        save(drawing(L), f"banner-{room}-light.webp", alpha_step=1)


# ------------------------------------------------------------ drawn, not rendered
def soft_shape(size, polys, blur):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for poly in polys:
        d.polygon(poly, fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur))


def grain(_):
    """Concrete's pores over everything, faint: specks of light and of shadow (either scheme)."""
    rng = np.random.default_rng(7)
    n = 192
    a = np.zeros((n, n, 4))
    pick = rng.random((n, n))
    a[pick < 0.05] = [*LIGHT, 1]
    a[pick > 0.95] = [*SHADOW, 1]
    img = Image.fromarray((a * 255).astype(np.uint8), "RGBA")
    save(img, "grain.png")


def mote(_):
    """Motes of dust: a small one for the hero's beam (dark), and larger ones floating over the
    page, of light over the black and of ink over the paper (its negative)."""
    for n, power, colour, name in ((10, 2, LIGHT, "mote.png"), (16, 1.4, LIGHT, "mote-page.png"),
                                   (16, 1.4, SHADOW, "mote-ink.png")):
        y, x = np.mgrid[0:n, 0:n]
        r = np.hypot(x - n / 2 + 0.5, y - n / 2 + 0.5) / (n / 2)
        a = np.clip(1 - r, 0, 1) ** power
        img = Image.fromarray((np.dstack([np.ones((n, n, 3)) * colour, a]) * 255).round().astype(np.uint8), "RGBA")
        save(img, name)


def beam(_):
    """While music plays, blades of sun walk slowly across the deck: a steep soft blade of light
    (the hero's, small), and along its edge a hairline of shadow for the paper scheme. The tile
    repeats seamlessly: the blade runs corner to corner."""
    W, H = 360, 720
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    # distance to the line from (0, H) to (W, 0), wrapped horizontally so the tile repeats
    u = (x + y * W / H) % W                      # 0..W along the slant
    d = np.minimum(np.abs(u - W / 2), W - np.abs(u - W / 2))
    light = np.exp(-(np.maximum(d, 0) / 20.0) ** 4) * 0.8 + np.exp(-(d / 55.0) ** 2) * 0.15
    edge = (np.abs(u - (W / 2 + 21)) < 0.9).astype(float) * 0.5
    a = np.zeros((H, W, 4))
    a[..., :3] = np.where((edge > light)[..., None], SHADOW, LIGHT)
    a[..., 3] = np.clip(np.maximum(light, edge), 0, 1)
    save(Image.fromarray((a * 255).round().astype(np.uint8), "RGBA"), "deck-blade.webp", alpha_step=1)


def frame(_):
    """The deck's and the sheets' frame, as on an architectural drawing: hairlines that overshoot
    at the corners. A 9-slice of 16 px: each line is a light hairline and, one pixel inside it,
    an ink hairline, so the frame is drawn in either scheme."""
    s = 16
    n = 3 * s
    a = np.zeros((n, n, 4))
    lw, iw = [*LIGHT, 0.5], [*SHADOW, 0.42]
    for off, col in ((5, lw), (6, iw)):
        a[off, :, :] = col           # top
        a[n - 1 - off, :, :] = col   # bottom
        a[:, off, :] = col           # left
        a[:, n - 1 - off, :] = col   # right
    # the overshoot stays, the frame's middle is clear
    a[s:2 * s, s:2 * s] = 0
    img = Image.fromarray((a * 255).round().astype(np.uint8), "RGBA")
    save(img, "frame-drawing.png")


def seams(_):
    """Light where the building's parts meet: along the top of the house (the roof slit, the
    status bar) and down the rail's edge. A light hairline with its glow, and one pixel beside it
    an ink hairline for the paper scheme."""
    W, H = 2880, 96
    a = np.zeros((H, W, 4)); a[..., :3] = LIGHT
    x = np.linspace(0, 1, W)
    along = (0.25 + 0.75 * np.exp(-((x - 0.18) / 0.35) ** 2))        # brightest near the sun
    y = np.arange(H)[:, None]
    a[..., 3] = np.clip(along[None, :] * (0.95 * (y < 2) + 0.18 * np.exp(-y / 7.0) * (y >= 2)), 0, 1)
    a[2:3, :, :3] = SHADOW; a[2:3, :, 3] = 0.35 * along
    save(Image.fromarray((a * 255).round().astype(np.uint8), "RGBA"), "seam-roof.webp", alpha_step=1)
    W, H = 40, 1200
    a = np.zeros((H, W, 4)); a[..., :3] = LIGHT
    yy = np.linspace(0, 1, H)
    along = 0.2 + 0.8 * np.exp(-((yy - 0.62) / 0.3) ** 2)
    xx = np.arange(W)[None, :]
    d = (W - 1 - xx)
    a[..., 3] = np.clip(along[:, None] * (0.8 * (d < 1) + 0.12 * np.exp(-d / 8.0) * (d >= 1)), 0, 1)
    a[:, W - 2, :3] = SHADOW; a[:, W - 2, 3] = 0.3 * along
    save(Image.fromarray((a * 255).round().astype(np.uint8), "RGBA"), "seam-rail.webp", alpha_step=1)


def tv(do_render):
    src = render("tv", 480, 360, 256) if do_render else f"{RENDERS}/tv.png"
    save(Image.open(src).convert("RGBA"), "tv-niche.webp", quality=88, alpha_step=1)


def room(do_render):
    src = render("room", 800, 360, 512, SUNANGLE=0.1) if do_render else f"{RENDERS}/room.png"
    L = luminance(src)
    save(split(L, mid=0.03, shadow_gain=0, light_gamma=0.9, floor=0.01), "room-bench.webp")
    save(clean(split(L, mid=0.12, shadow_gain=0.85, light_gamma=0.9)), "room-bench-light.webp")


def foot(do_render):
    """The rail's foot: a slit window at the end of a corridor. A piece at its own size, and the
    poke's sheet: touch it and a cloud passes over the sun, the light fades and comes back."""
    src = render("foot", 464, 480, 512, SUNANGLE=0.1) if do_render else f"{RENDERS}/foot.png"
    L = luminance(src)
    night = split(L, mid=0.03, shadow_gain=0, light_gamma=0.8, floor=0.01,
                  mask=np.maximum(vignette(L.shape, 0.35, 1.05), (L > 0.3)))
    # the paper print: clean, like the hero's: the walls in soft ink, the slit and its line
    # paper-white; no box: the print fades out to the paper itself long before its edges
    edge = np.clip(np.minimum.reduce([
        np.linspace(0, 1, L.shape[1])[None, :].repeat(L.shape[0], 0) / 0.22,
        np.linspace(1, 0, L.shape[1])[None, :].repeat(L.shape[0], 0) / 0.22,
        np.linspace(0, 1, L.shape[0])[:, None].repeat(L.shape[1], 1) / 0.18,
        np.linspace(1, 0, L.shape[0])[:, None].repeat(L.shape[1], 1) / 0.08]), 0, 1)
    edge = edge * edge * (3 - 2 * edge)
    day = clean(split(L, mid=0.15, shadow_gain=0.75, light_gamma=0.75, mask=edge))
    size = (216, 224)
    CLOUD = [0.8, 0.5, 0.28, 0.2, 0.28, 0.5, 0.8, 1.0]   # the light, frame by frame, as a cloud passes
    for img, name in ((night, "foot-slit"), (day, "foot-slit-light")):
        piece = img.resize(size, Image.LANCZOS)
        save(piece, name + ".webp", alpha_step=1)
        a = np.asarray(piece).astype(np.float64)
        is_light = (a[..., 0] > 128)
        sheet = Image.new("RGBA", (size[0] * len(CLOUD), size[1]))
        for i, k in enumerate(CLOUD):
            f = a.copy()
            if name.endswith("light"):
                # by day a cloud softens everything toward the paper: the corridor's shade pales,
                # the slit's light stays; nothing outside the print changes
                f[..., 3] = np.where(is_light, f[..., 3], f[..., 3] * k)
            else:
                f[..., 3] = np.where(is_light, f[..., 3] * k, f[..., 3])  # at night the light dims
            sheet.paste(Image.fromarray(f.round().astype(np.uint8), "RGBA"), (i * size[0], 0))
        save(sheet, name + "-cloud.webp", alpha_step=1)


JOBS = {"foot": foot, "tv": tv, "room": room, "seams": seams, "hero": hero, "page": page, "empty": empty, "crest": crest, "banners": banners,
        "grain": grain, "mote": mote, "beam": beam, "frame": frame}

if __name__ == "__main__":
    os.makedirs(ART, exist_ok=True)
    os.makedirs(RENDERS, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_render = "--no-render" not in sys.argv
    for name in args or JOBS:
        print(name)
        JOBS[name](do_render)
