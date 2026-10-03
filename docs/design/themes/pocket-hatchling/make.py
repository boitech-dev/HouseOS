"""Every picture of Pocket Hatchling, drawn by code (python3 make.py [name…]).
Pixel art on one 2 × grid: slots are saved at 2 ×, layers at 1 × with "scale": 2 in theme.json.
Light from the top left; plum outlines; candy ramps from pal.py. No words in any picture."""
import random
import sys

from draw import *  # noqa: F403
from pal import *  # noqa: F403
from util import ART

ART.mkdir(exist_ok=True)
MADE = {}


def art(fn):
    MADE[fn.__name__] = fn
    return fn


HEART5 = ["k.k.", "kkkk"]  # placeholder, replaced below


def heart(fill, size=5, outline_ink=None):
    rows = {
        5: [".k.k.", "kkkkk", "kkkkk", ".kkk.", "..k.."],
        7: [".kk.kk.", "kkkkkkk", "kkkkkkk", "kkkkkkk", ".kkkkk.", "..kkk..", "...k..."],
        3: ["k.k", "kkk", ".k."],
    }[size]
    im = grid(rows, {"k": fill})
    return outline(im, outline_ink) if outline_ink else im


def spark(fill, size=5, core=None):
    """A four-point sparkle."""
    rows = {
        3: [".k.", "kkk", ".k."],
        5: ["..k..", "..k..", "kkkkk", "..k..", "..k.."],
        7: ["...k...", "...k...", "..kkk..", "kkkkkkk", "..kkk..", "...k...", "...k..."],
    }[size]
    im = grid(rows, {"k": fill})
    if core:
        px(im, size // 2, size // 2, core)
    return im


@art
def tile():
    """The page: a handmade homepage's tiled ground: a soft lavender check, a pink heart and a
    small white twinkle on the diagonal, 32 × 32 (64 px on screen). Kept low in contrast: text
    lies on it; the sparkle and heart particles bring the life."""
    im = new(32, 32, CANVAS)
    rect(im, (16, 0, 31, 15), CANVAS2)
    rect(im, (0, 16, 15, 31), CANVAS2)
    paste(im, heart(P4, 5), (6, 6))
    paste(im, spark(WHITE, 5), (22, 22))
    for x, y in ((24, 8), (8, 24)):
        px(im, x, y, WHITE)
    save(im, ART / "tile.png")


@art
def twinkle():
    """A sparkle for the page's twinkling particles: lemon arms, a white heart. 7 × 7 (14 px)."""
    im = spark(LEM2, 7, WHITE)
    for x, y in ((3, 2), (3, 4), (2, 3), (4, 3)):
        px(im, x, y, WHITE)
    save(im, ART / "twinkle.png")


@art
def floaty():
    """A soft heart drifting up the page now and then (a particle): pink with a deeper edge."""
    im = grid([".ll.ll.", "lLPlLLl", "lLLLLLl", ".lLLLl.", "..lLl..", "...l..."], {"l": P1, "L": P3, "P": WHITE})
    save(im, ART / "floaty.png")



# ---------------------------------------------------------------- Pip on the LCD, and the egg

import sprites_src  # noqa: E402

def sprite(name, legend=None):
    return grid(sprites_src.ALL[name], legend or LEGEND)


LCD_INK = {k: LCD0 for k in "kn"}  # the LCD shows Pip as dark segments only


def lcd_pip(face="idle", sprout="up", chin=None):
    """Pip in 1-bit LCD segments: outline, eyes, mouth and the shell's crack; the rest is the
    screen showing through."""
    g = sprites_src.pip(sprites_src.FACES[face], sprout, chin or sprites_src.CHIN)
    return grid([row.replace("v", ".").replace("V", ".").replace("w", ".").replace("P", ".")
                 .replace("m", ".").replace("L", ".").replace("C", ".").replace("E", ".")
                 .replace("g", ".").replace("r", "k").replace("e", "k").replace("i", ".")
                 for row in g], {"k": LCD0})


def egg_mask(w, h, bulge=0.13):
    """An egg: narrower at the top, fuller below."""
    im = new(w, h)
    cx = (w - 1) / 2
    for y in range(h):
        t = (y + 0.5) / h * 2 - 1
        half = (w / 2) * max(0.0, 1 - t * t) ** 0.5 * (1 + bulge * t) / (1 + bulge * 0.35)
        for x in range(w):
            if abs(x - cx) <= half - 0.25:
                im.putpixel((x, y), rgba(P2))
    return im


def rounded(w, h, r, fill):
    im = new(w, h)
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=rgba(fill))
    return im


SHADE = {LEM1: LEM0, BERRY: BERRY_DEEP, MINT1: MINT0, LAV1: LAV0, P1: P0, P2: P1, BLU1: BLU0}


def button(d, fill, shine=True):
    """A round rubber button, 5 or 7 across, shine top left."""
    rows = {7: ["..kkk..", ".kPaak.", "kPaaaak", "kaaaadk", "kaaaadk", ".kaddk.", "..kkk.."],
            5: [".kkk.", "kPaak", "kaadk", "kaddk", ".kkk."]}[7 if d >= 6 else 5]
    return grid(rows, {"k": INK, "a": fill, "d": SHADE.get(fill, INK2), "P": WHITE if shine else fill})


def glitter(im, colours, density, seed, region=None):
    """Single flecks on the plastic (only where it is already that plastic's base colour)."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = region or (0, 0, im.width, im.height)
    base = im.getpixel((im.width // 2, im.height // 2))
    for _ in range(int((x1 - x0) * (y1 - y0) * density)):
        x, y = rnd.randrange(x0, x1), rnd.randrange(y0, y1)
        if im.getpixel((x, y)) == base:
            im.putpixel((x, y), rgba(rnd.choice(colours)))
    return im


ICONS5 = {  # the pictograms printed round the screen (5 × 5): food, light, play, care
    "apple": ["..k..", ".kkk.", "kkkkk", "kkkkk", ".kkk."],
    "bulb": [".kkk.", "k...k", "k...k", ".kkk.", "..k.."],
    "ball": [".kkk.", "k.k.k", "kkkkk", "k.k.k", ".kkk."],
    "heart": [".k.k.", "kkkkk", "kkkkk", ".kkk.", "..k.."],
    "duck": [".kk..", "kkkk.", ".kkkk", ".kkk.", "....."],
    "star": ["..k..", ".kkk.", "kkkkk", ".k.k.", "k...k"],
    "moon": [".kkk.", "kk...", "kk...", "kk...", ".kkk."],
    "note": ["..kkk", "..k.k", "..k..", "kkk..", "kkk.."],
}


def icon5(name, colour):
    return grid(ICONS5[name], {"k": colour})


def leaves(size=1):
    rows = {2: [".kk.....kk.", "kEgk...kgEk", "kggk...kggk", ".kggk.kggk.", "..kkkrkkk..", "....kr.k...", ".....r....."],
            1: ["kk.....kk", "kEgk.kgEk", ".kggkggk.", "..kkrkk..", "....r...."],
            0: ["k...k", "kgkgk", ".krk."]}[size]
    return grid(rows, {"k": INK, "g": MINT1, "E": MINT2, "r": MINT0})


def device(w, h, screen=None, seed=3, icons=True, sprout=True):
    """The keychain egg, lit from the top left: bubblegum shell with glitter, a lavender face
    plate with the care pictograms printed round a recessed LCD (the `screen` image drawn on it),
    three rubber buttons and a sprout on top like Pip's own."""
    shell = egg_mask(w, h)
    shell = shade(shell, P3, P1, rim=max(1, w // 22))
    shell = shade(shell, None, P0, rim=1)
    glitter(shell, [WHITE, P4, P3, LEM3], 0.035, seed, (2, 2, w - 3, h - 3))
    # gloss: a short curved streak high on the left
    for i in range(max(3, h // 9)):
        x = int(w * 0.2) + (i * i) // max(4, h // 5)
        y = int(h * 0.13) + i
        if shell.getpixel((x, y))[3]:
            px(shell, x, y, WHITE)
    ew = int(w * 0.66)
    eh = int(h * (0.5 if icons else 0.42))
    plate = rounded(ew, eh, max(3, ew // 5), LAV3)
    plate = shade(plate, WHITE, LAV2)
    top_row = ["apple", "bulb", "ball", "heart"]
    bottom_row = ["duck", "star", "moon", "note"]
    sw = ew - 6
    sh = eh - (16 if icons else 8)
    lcd = rounded(sw, sh, max(2, sw // 8), LCD3)
    ImageDraw.Draw(lcd).rounded_rectangle((0, 0, sw - 1, sh - 1), max(2, sw // 8), outline=rgba(LCD1))
    for x in range(2, sw - 2):
        if lcd.getpixel((x, 1)) == rgba(LCD3):
            lcd.putpixel((x, 1), rgba(LCD2))
    lcd = outline(lcd)
    ly = 7 if icons else 3
    paste(plate, lcd, ((ew - lcd.width) // 2 - 1, ly))
    if screen is not None:
        paste(plate, screen, ((ew - screen.width) // 2 - 1, ly + (lcd.height - screen.height) // 2 + 1))
    if icons:
        step = (ew - 8) / 4
        for i, (t, b) in enumerate(zip(top_row, bottom_row)):
            x = int(4 + step * i + (step - 5) / 2)
            paste(plate, icon5(t, BERRY if t == "heart" else LAV1), (x, 1))
            paste(plate, icon5(b, LAV1), (x, ly + lcd.height + 1))
    plate = outline(plate)
    px_ = (w - plate.width) // 2
    py_ = int(h * 0.19)
    paste(shell, plate, (px_, py_))
    bd = max(4, w // 9)
    by = py_ + plate.height + max(1, h // 28)
    gap = bd + max(2, w // 18)
    for i, colour in enumerate((LEM1, BERRY, MINT1)):
        b = button(bd, colour)
        paste(shell, b, (w // 2 - b.width // 2 + (i - 1) * gap, by + (1 if i != 1 else 0)))
    body = outline(shell)
    if not sprout:
        return body
    lf = leaves(2 if w >= 46 else 1 if w >= 30 else 0)
    out = new(body.width, body.height + lf.height - 2)
    paste(out, lf, ((out.width - lf.width) // 2, 0))
    paste(out, body, (0, lf.height - 2))
    return out


def charm_chain(length, colour=LAV2):
    """A ball chain hanging straight down: beads with a dark edge."""
    im = new(3, length)
    for y in range(0, length, 3):
        rect(im, (0, y, 2, y + 1), INK)
        px(im, 1, y, colour)
    return im


@art
def crest():
    """Sign-in: the egg itself, Pip awake on its screen, a heart charm on a ball chain from its
    keyring and a star sticker stuck on the shell. 80 × 80 (160 on screen)."""
    im = new(80, 80)
    d = device(56, 62, lcd_pip("idle"), seed=5)
    dx, dy = 5, 80 - d.height - 1
    paste(im, d, (dx, dy))
    ring_im = new(7, 7)
    ellipse(ring_im, (0, 0, 6, 6), INK)
    ellipse(ring_im, (1, 1, 5, 5), LAV2)
    ellipse(ring_im, (2, 2, 4, 4), (0, 0, 0, 0))
    rx, ry = dx + d.width - 13, dy + 11
    # the ball chain: up and over the shoulder, then straight down beside the egg
    for i, (x, y) in enumerate([(rx + 7, ry), (rx + 9, ry - 1), (rx + 11, ry), (rx + 13, ry + 2)]):
        rect(im, (x, y, x + 1, y + 1), INK)
        px(im, x, y, LAV2)
    chain = charm_chain(26)
    paste(im, chain, (rx + 13, ry + 4))
    paste(im, ring_im, (rx, ry - 2))
    charm = sticker(heart(P1, 7))
    paste(im, charm, (rx + 9, ry + 29))
    star = sticker(spark(LEM1, 7))
    paste(im, star, (dx + 3, dy + d.height - 24))
    for x, y, c in ((4, 14, LEM1), (13, 6, WHITE), (70, 64, WHITE)):
        paste(im, spark(c, 5), (x, y))
    save(im, ART / "crest.png", 2)



MINI = {  # Pip small enough for a little screen (11 × 10), as LCD segments
    "awake": ["....k.k....", ".....k.....", "...kkkkk...", "..k.....k..", ".k..k.k..k.",
              ".k.......k.", ".kk.kkk.kk.", ".k.k.k.k.k.", "..k.....k..", "...kkkkk..."],
    "blink": ["....k.k....", ".....k.....", "...kkkkk...", "..k.....k..", ".k.......k.",
              ".k.kk.kk.k.", ".kk.kkk.kk.", ".k.k.k.k.k.", "..k.....k..", "...kkkkk..."],
    "sleep": ["...........", "....k.k....", "...kkkkk...", "..k.....k..", ".k.......k.",
              ".k.kk.kk.k.", ".kk.....kk.", ".k.k.k.k.k.", "..k.....k..", "...kkkkk..."],
}
BUBBLES = [[], ["k"], [".k.", "k.k", ".k."], [".kk.", "k..k", "k..k", ".kk."]]


def mini_pip(face="awake", bubble=0, hop=0):
    im = new(17, 12)
    paste(im, grid(MINI[face], {"k": LCD0}), (3, 2 - hop))
    if bubble:
        b = grid(BUBBLES[bubble], {"k": LCD0})
        paste(im, b, (12, 6 - b.height))
    return im


def soft_cloud(w, h, seed=4):
    """A puffy cloud with no inner lines: round bumps on a flat base, a lavender belly on its
    lower right, a lavender outline."""
    rnd = random.Random(seed)
    im = new(w, h)
    ellipse(im, (0, h // 2 - 2, w - 1, h - 1), WHITE)
    n = 4
    for i in range(n):
        r = int(h * (0.42 if i in (1, 2) else 0.32)) + rnd.randint(0, 1)
        cx = int(w * (i + 0.8) / (n + 0.6))
        cy = h // 2 - (r // 3 if i in (1, 2) else 0)
        ellipse(im, (cx - r, cy - r, cx + r, cy + r), WHITE)
    im = shade(im, None, LAV3, rim=2)
    return outline(im, LAV1)


@art
def egg():
    """Home's hero: the egg resting on a puffy cloud in the bottom right. Pip on its screen is
    awake and blinks; every eight seconds the screen dims, the egg sways as Pip nods off and a
    bubble swells outside the shell. 16 frames of 76 × 64, 2 a second, drawn at scale 2."""
    frames = []
    story = ["awake"] * 3 + ["blink"] + ["awake"] * 4 + ["blink", "awake"] + ["sleep"] * 6
    bubbles = [0] * 10 + [1, 2, 3, 4, 3, 2]
    bob = [0] * 10 + [0, 1, 1, 0, 1, 1]
    cl = soft_cloud(74, 20)
    for n, (face, bub, dy) in enumerate(zip(story, bubbles, bob)):
        f = new(76, 64)
        screen = mini_pip(face)
        if face == "sleep":  # the screen dims: Pip in the ghost ink
            screen = recolour(screen, {LCD0: LCD1})
        d = device(40, 44, screen, seed=7, icons=False)
        if face == "sleep":
            d = recolour(d, {LCD3: LCD2})
        paste(f, d, (14, 3 + dy))
        paste(f, cl, (1, 64 - cl.height))
        if bub:
            r = [0, 3, 4, 5, 6][bub]
            b = new(2 * r + 1, 2 * r + 1)
            ellipse(b, (0, 0, 2 * r, 2 * r), BLU1)
            ellipse(b, (1, 1, 2 * r - 1, 2 * r - 1), BLU3)
            px(b, 2, 2, WHITE); px(b, 3, 2, WHITE); px(b, 2, 3, WHITE)
            paste(f, b, (58 - r, 12 - r))
            px(f, 55, 18, BLU1); px(f, 54, 20, BLU1)
        frames.append(f)
    save(pixel.sheet(frames), ART / "egg.png")



def puff(w, h, seed, fill=WHITE, dark=LAV3, edge=LAV2):
    """A cloud with volume: puffs ringed in lavender, a lavender belly, lit top left."""
    c = cloud(w, h, fill, seed, edge, dark)
    return outline(c, LAV1)


def bank(W, H, base, rmin, rmax, seed, fill, edge, dark, light=None):
    """A long row of puffs across the whole width, their bottoms off the picture."""
    rnd = random.Random(seed)
    bumps, x = [], -rmax
    while x < W + rmax:
        r = rnd.randint(rmin, rmax)
        bumps.append((x, base + rnd.randint(-2, 3), r))
        x += int(r * 1.3) + rnd.randint(0, 3)
    im = puffs(W, H, bumps, fill, edge, dark)
    if light:
        im = shade(im, light, None, keep=[edge, dark])
    rect(im, (0, base, W - 1, H - 1), fill)
    return outline(im, LAV1, grow=False)


def medal(name):
    """A medal sticker as a picture (the same drawing as sprites.json)."""
    return sprite("title." + name)


def sky_bands(im, stops, y0, y1):
    """A pastel sky in dithered bands (Bayer), top to bottom."""
    pixel.bands(im, (0, y0, im.width, y1), stops, vertical=True, dithered=True)


def arc(im, cx, cy, r, colours, width):
    """Concentric bands of a rainbow, outermost first."""
    d = ImageDraw.Draw(im)
    for i, colour in enumerate(colours):
        rr = r - i * width
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=rgba(colour))
    rr = r - len(colours) * width
    return rr


@art
def sky():
    """The hero's sky (a layer under the hero picture, repeat-x): baby blue at the top through
    lavender to bubblegum, in dithered bands. 4 × 240 at scale 2: 480 px, so a tall phone hero
    is sky all the way down behind its words."""
    im = new(4, 240)
    sky_bands(im, [BLU3, LAV3, P4, P4, P4], 0, 240)
    save(im, ART / "sky.png")


@art
def hero():
    """Home: the pet's world, a homepage sky: a big rainbow over a floor of clouds, sparkles,
    floating hearts, stickers, and a little webring of web buttons in the top right (the egg
    rests on the clouds bottom right, a layer). 344 × 128 (688 × 256 on screen); the left fades
    under the greeting; the sky is its own layer beneath."""
    W, H = 344, 128
    im = new(W, H)
    RX, RY, RR = 196, 140, 116
    rb = new(W, H)
    inner = arc(rb, RX, RY, RR, [P2, LEM2, MINT2, BLU2, LAV2], 6)
    hole = new(W, H)
    ellipse(hole, (RX - inner, RY - inner, RX + inner, RY + inner), WHITE)
    rbd = rb.load(); hd = hole.load()
    for y in range(H):
        for x in range(W):
            if hd[x, y][3]:
                rbd[x, y] = (0, 0, 0, 0)
    rb = shade(rb, WHITE, None, keep=[INK])
    paste(im, rb, (0, 0))
    rnd = random.Random(21)
    for _ in range(40):
        x, y = rnd.randrange(8, W - 8), rnd.randrange(4, 84)
        c = rnd.choice([WHITE, WHITE, LEM2, P3])
        if rnd.random() < 0.3:
            paste(im, spark(c, 5), (x, y))
        else:
            px(im, x, y, c)
    for x, y, c in ((96, 12, P2), (128, 44, MINT2), (282, 36, P3), (60, 60, LAV2)):
        paste(im, outline(heart(c, 7)), (x, y))
    for (x, y, w, h, seed) in ((66, 28, 34, 12, 1), (150, 64, 26, 10, 2), (214, 86, 40, 14, 3)):
        paste(im, puff(w, h, seed), (x, y))
    paste(im, bank(W, H, H - 22, 9, 15, 8, LAV3, LAV2, None, WHITE), (0, 0))
    paste(im, bank(W, H, H - 8, 8, 13, 5, WHITE, LAV2, LAV3), (0, 0))
    # a webring pinned to the sky, top right
    for i, spec in enumerate([(P2, P4, P1, "heart", "dots"), (MINT2, MINT3, MINT1, "star", "stripes"),
                              (LEM2, LEM3, LEM1, "note", "check")]):
        paste(im, badge(*spec), (W - 58, 4 + i * 12))
    for name, x, y in (("grocery_runner", 150, 10), ("weekend", 244, 34), ("dj", 110, 56),
                       ("courier", 180, 82), ("high_scorer", 262, 70)):
        paste(im, medal(name), (x, y))
    save(im, ART / "hero.png", 2)



def lace(w, colour=WHITE, edge=P0, period=8, depth=4):
    """A lace trim: a band with round scallops hanging below and an eyelet over each."""
    im = new(w, 3 + depth + 1)
    rect(im, (0, 0, w - 1, 2), colour)
    for x in range(-period, w + period, period):
        ellipse(im, (x, 3 - depth // 2, x + period - 1, 3 + depth - 1), colour)
    im = outline(im, edge, grow=False)
    for x in range(-period, w + period, period):
        px(im, x + period // 2 - 1, 2, edge)
    return im


@art
def status():
    """The status strip over the bar's bubblegum ground: a garland of pennants and hearts along
    the top, a lace trim along the bottom, and clear between them, where Pip sometimes hops
    past (the walker layer, drawn behind this strip). 1200 × 24 (2400 × 48: pixel-exact)."""
    W, H = 1200, 24
    im = new(W, H)
    # the garland's string, sagging a little between pins
    for x in range(W):
        y = 1 + int(2.2 * (1 - ((x % 60) / 30 - 1) ** 2))
        px(im, x, y, P0)
    for i, x in enumerate(range(6, W, 20)):
        y = 2 + int(2.2 * (1 - (((x + 3) % 60) / 30 - 1) ** 2))
        if i % 2 == 0:
            paste(im, outline(heart([P4, LEM3, MINT3][(i // 2) % 3], 5), P0), (x - 1, y))
        else:
            paste(im, spark(WHITE, 5), (x, y + 1))
    paste(im, lace(W, WHITE, P0, 10, 5), (0, H - 9))
    save(im, ART / "status.png", 2)



@art
def shooting_star():
    """Now and then across the top of the page: a star trailing candy stripes. The picture is
    40 tall so the star passes just under the status bar (48 px), in the page's top margin."""
    W, H = 72, 40
    im = new(W, H)
    y = 29
    for i, c in enumerate((P2, LEM2, MINT2, BLU2)):
        for x in range(0, 58):
            # the trail thins out toward its tail: every other pixel, then every fourth
            if x > 30 or (x > 14 and x % 2 == 0) or x % 4 == 0:
                px(im, x, y - 3 + i * 2, c)
                px(im, x, y - 2 + i * 2, c)
    star = outline(grid(["...k...", "..kkk..", "kkkkkkk", ".kkkkk.", "..kkk..", ".kk.kk.", "k.....k"],
                        {"k": LEM1}))
    star = shade(star, LEM3, LEM0, keep=[INK])
    paste(im, star, (W - star.width - 1, y - 5))
    px(im, W - 6, y - 2, WHITE)
    save(im, ART / "shooting-star.png")


@art
def walker():
    """Now and then Pip rides the status bar's garland like a zip line, hanging by its sprout,
    swinging a little (4 frames of 18 × 19), in front of the garland."""
    base, blink, happy = sprite("nox.idle"), sprite("nox.blink"), sprite("nox.happy")
    hook = grid(["kkkk", "k..k"], {"k": INK2})
    frames = []
    for pic, dx in ((base, 1), (happy, 2), (blink, 1), (happy, 0)):
        f = new(18, 19)
        paste(f, hook, (7, 1))
        paste(f, pic, (dx, 3))
        frames.append(f)
    save(pixel.sheet(frames), ART / "walker.png")


@art
def dance():
    """While music plays Pip climbs out onto the egg's bottom-right corner and dances, notes
    popping (Listen only). Four frames of 20 × 22, anchored bottom right, over the shell."""
    note = grid([".kk", ".kk", ".k.", "kk.", "kk."], {"k": BERRY})
    frames = []
    for n, (name, hop) in enumerate((("nox.idle", 0), ("nox.happy", 3), ("nox.blink", 1), ("nox.happy", 3))):
        f = new(20, 22)
        paste(f, sprite(name), (2, 5 - hop + 1))
        if n in (1, 3):
            paste(f, note, (0 if n == 1 else 17, 0 if n == 1 else 2))
        frames.append(f)
    save(pixel.sheet(frames), ART / "dance.png")


@art
def heart_particle():
    """A candy heart floating up the deck while music plays: plum outline, a shine."""
    im = grid([".kk.kk.", "kPLkLLk", "kLLLLLk", "kLLLLlk", ".kLLlk.", "..klk..", "...k..."],
              {"k": INK, "L": P2, "l": P1, "P": WHITE})
    save(im, ART / "heart.png")


@art
def lcd_frame():
    """The music deck is the egg itself: a 9-slice of pearly bubblegum shell (glitter in its
    corners, lit top left), a lavender face-plate ring, a bevelled LCD recess, and three rubber
    buttons in the bottom-left corner. 72 × 72 at 2 × (144), corners 24 (slice 48); the shell
    band is 8 art px = the deck's 16 px padding, so the player sits on the screen."""
    S = 72
    im = new(S, S)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, S - 1, S - 1), 12, fill=rgba(INK))
    d.rounded_rectangle((1, 1, S - 2, S - 2), 11, fill=rgba(P2))
    # plastic lit from the top left: a light rim, a berry-pink shadow rim
    shell = new(S, S)
    ImageDraw.Draw(shell).rounded_rectangle((1, 1, S - 2, S - 2), 11, fill=rgba(P2))
    shell = shade(shell, P3, P1, rim=2)
    shell = shade(shell, P4, P0, rim=1)
    paste(im, shell, (0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, S - 7, S - 7), 6, fill=rgba(LAV3))      # the face-plate ring
    d.rounded_rectangle((7, 7, S - 8, S - 8), 5, fill=rgba(LCD4))      # the recess: light below right
    d.rounded_rectangle((7, 7, S - 9, S - 9), 5, fill=rgba(LCD1))      # shadow above left
    d.rounded_rectangle((8, 8, S - 9, S - 9), 4, fill=rgba(LCD3))      # the screen
    # glitter only in the corners (the edges stretch)
    rnd = random.Random(8)
    for _ in range(400):
        x, y = rnd.randrange(2, S - 2), rnd.randrange(2, S - 2)
        corner = (x < 22 or x >= S - 22) and (y < 22 or y >= S - 22)
        if corner and im.getpixel((x, y))[:3] in (rgba(P2)[:3], rgba(P3)[:3], rgba(P1)[:3]) and rnd.random() < 0.55:
            px(im, x, y, rnd.choice([WHITE, P4, LEM3, WHITE, P1]))
    # a gloss streak round the top-left corner
    for x, y in ((4, 9), (4, 8), (4, 7), (5, 6), (5, 5), (6, 4), (7, 4), (8, 4), (9, 4), (10, 3)):
        px(im, x - 1, y - 1, WHITE)
    # three rubber buttons on the shell, bottom left
    for i, c in enumerate((LEM1, BERRY, MINT1)):
        bt = grid([".kk.", "kPak", "kadk", ".kk."], {"k": INK, "P": WHITE, "a": c, "d": SHADE[c]})
        paste(im, bt, (8 + i * 5, S - 6))
    save(im, ART / "lcd-frame.png", 2)



def dashed_outline(mask_im, colour, on=2, off=2):
    """The kiss-cut line a peeled sticker leaves on its sheet: a dashed ring round a shape."""
    ringed = ring(mask_im, colour, False)
    out = new(ringed.width, ringed.height)
    n = 0
    for y in range(ringed.height):
        for x in range(ringed.width):
            p = ringed.getpixel((x, y))
            if p[3] and p[:3] == rgba(colour)[:3]:
                if (x + y) % (on + off) < on:
                    out.putpixel((x, y), p)
    return out


def lace_v(h, colour=WHITE, edge=MINT1, period=10, depth=5):
    """Lace running down a right-hand edge, scallops pointing left."""
    return lace(h, colour, edge, period, depth).rotate(90, expand=True)


BADGE_ICON = {"heart": BERRY, "star": LEM0, "note": LAV0, "moon": BLU0, "apple": P0, "duck": MINT0}


def badge(fill, light, dark, icon, pattern):
    """A little web button in the old 88 × 31 manner, 24 × 9: a bevel, a pictogram at the
    left, a pattern where words would be (never words)."""
    im = new(24, 9, fill)
    for x in range(24):
        px(im, x, 0, light); px(im, x, 8, dark)
    for y in range(9):
        px(im, 0, y, light); px(im, 23, y, dark)
    paste(im, icon5(icon, BADGE_ICON[icon]), (2, 2))
    for x in range(9, 22):
        for y in range(2, 7):
            if pattern == "check" and (x // 2 + y // 2) % 2 == 0:
                px(im, x, y, light)
            elif pattern == "stripes" and (x + y) % 4 == 0:
                px(im, x, y, dark)
            elif pattern == "dots" and x % 3 == 0 and y % 3 == 1:
                px(im, x, y, WHITE)
            elif pattern == "wave" and y == 4 + ((x // 2) % 2):
                px(im, x, y, dark)
    return outline(im)


SHRINE_BADGES = [(P2, P4, P1, "heart", "dots"), (LEM2, LEM3, LEM1, "star", "stripes"),
                 (LAV2, LAV3, LAV1, "note", "wave"), (BLU2, BLU3, BLU1, "moon", "check"),
                 (MINT2, MINT3, MINT1, "duck", "stripes"), (P3, P4, P2, "apple", "check")]


def shrine_img(lit=(), swing=0, face="heart"):
    """The rail's foot: a little shrine of web buttons pinned to a lace-topped board, and the
    egg hanging on its ball chain in front. `lit`: the buttons flashing; `swing`: the egg's
    sway. 103 × 107."""
    W, H = 103, 107
    im = new(W, H)
    board = outline(shade(rounded(66, 62, 6, P3), P4, P2))
    bx, by = 3, 36
    paste(im, board, (bx, by))
    paste(im, lace(68, WHITE, P0, 8, 4), (bx - 1, by - 4))
    for i, (fill, light, dark, icon, pattern) in enumerate(SHRINE_BADGES):
        b = badge(WHITE, LEM3, light, icon, pattern) if i in lit else badge(fill, light, dark, icon, pattern)
        paste(im, b, (bx + 5 + (i % 2) * 29, by + 8 + (i // 2) * 16))
    pin = grid([".kk.", "kPek", "keek", ".kk."], {"k": INK, "P": WHITE, "e": BERRY})
    chain = charm_chain(26)
    screen = grid(ICONS5["heart"], {"k": LCD0}) if face == "heart" else mini_pip("awake")
    d = device(34, 40, screen, seed=9, icons=False)
    dx = W - d.width - 2
    paste(im, chain, (dx + d.width // 2 - 1 + (swing > 0) - (swing < 0), 8))
    paste(im, pin, (dx + d.width // 2 - 2, 5))
    paste(im, d, (dx + swing, 30))
    paste(im, sticker(spark(LEM1, 7)), (0, by + 50))
    paste(im, medal("grocery_runner"), (bx + 44, by + 50))
    return im


@art
def shrine():
    """The shrine at the rail's foot (a rail-foot layer, so it can be poked), and its reaction:
    the web buttons blink one after another like a webring, the egg swaying on its chain
    (8 frames)."""
    save(shrine_img(), ART / "shrine.png")
    frames = []
    for n in range(8):
        lit = (n,) if n < 6 else (tuple(range(6)) if n == 6 else ())
        frames.append(shrine_img(lit, [-1, 1, -1, 1, -1, 1, 0, 0][n], "heart"))
    save(pixel.sheet(frames), ART / "shrine-poke.png")



def moon_sticker():
    rows = ["....kkkk.....", "..kkvvvvk....", ".kvPvvvk.....", "kvPvvvk......", "kvvvvk.......",
            "kvvvvk.......", "kvvvvk.......", "kvvvvvk......", ".kvvvvvk..kk.", ".kwvvvvvkkvk.",
            "..kwwvvvvvvk.", "...kkwwwwkk..", ".....kkkk...."]
    return sticker(grid(rows, LEGEND))


def big_pip_asleep():
    """Pip drawn large (26 × 27) for the empty state: eyes shut, cheeks pink, the sprout
    drooping, sitting in the bottom of its shell."""
    body = blob(22, 20, LEM2)
    body = shade(body, LEM3, LEM1, rim=2)
    body = outline(body)
    for x0 in (5, 14):  # closed eyes, curved down
        for dx, dy in ((0, 0), (1, 1), (2, 1), (3, 0)):
            px(body, x0 + dx, 10 + dy, INK)
    for x0 in (3, 17):
        rect(body, (x0, 13, x0 + 2, 13), P2)
    px(body, 11, 14, INK); px(body, 12, 14, INK)
    shell = new(26, 12)
    ellipse(shell, (0, -12, 25, 11), WHITE)
    for x in range(26):
        top = 1 + abs((x % 6) - 3)
        for y in range(0, top):
            px(shell, x, y, (0, 0, 0, 0))
        px(shell, x, top, INK)
    shell = outline(shade(shell, None, LAV3, rim=2, keep=[INK]))
    sprout = grid(["kk.......", "kgk....kk", ".kgk..kgk", "..kgkkgk.", "...kkrk..", ".....r..."],
                  {"k": INK, "g": MINT1, "r": MINT0})
    im = new(28, 32)
    paste(im, sprout, (9, 0))
    paste(im, body, (2, 5))
    paste(im, shell, (0, 18))
    return im


@art
def asleep():
    """Empty states: Pip asleep in its shell on a cloud pillow, a bubble at its nose, the moon
    stuck up beside it. 48 × 48 (96)."""
    im = new(48, 48)
    paste(im, puff(44, 14, 12), (2, 33))
    paste(im, big_pip_asleep(), (9, 10))
    b = new(9, 9)
    ellipse(b, (0, 0, 8, 8), BLU1)
    ellipse(b, (1, 1, 7, 7), BLU3)
    px(b, 2, 2, WHITE); px(b, 3, 2, WHITE); px(b, 2, 3, WHITE)
    paste(im, b, (36, 22))
    paste(im, moon_sticker(), (0, 0))
    for x, y, c in ((38, 5, LEM1), (43, 13, WHITE), (20, 2, WHITE)):
        paste(im, spark(c, 5), (x, y))
    save(im, ART / "asleep.png", 2)


@art
def tv():
    """Watch's screens: a toy television, lavender plastic, star-tipped antennae, a heart on its
    screen and two knobs. 80 × 60 (160 × 120)."""
    W, H = 80, 60
    im = new(W, H)
    # antennae
    line(im, [(34, 16), (24, 4)], INK)
    line(im, [(46, 16), (58, 3)], INK)
    paste(im, outline(spark(LEM1, 5)), (20, 0))
    paste(im, outline(heart(P2, 5)), (55, 0))
    body = rounded(66, 40, 9, LAV2)
    body = shade(body, LAV3, LAV1, rim=2)
    glitter(body, [WHITE, LAV3], 0.02, 3, (3, 3, 63, 37))
    body = outline(body)
    paste(im, body, (7, 14))
    scr = rounded(42, 30, 6, LCD3)
    ImageDraw.Draw(scr).rounded_rectangle((0, 0, 41, 29), 6, outline=rgba(LCD1))
    scr = outline(scr)
    paste(scr, grid(sprites_src.pip(sprites_src.FACES["happy"], "joy"),
                    {k: LCD0 for k in "kvVwPmLlCeEgrip"}) if False else lcd_pip("happy", "joy"), (14, 7))
    paste(im, scr, (12, 19))
    for i, c in enumerate((P1, MINT1)):
        paste(im, button(7, c), (61, 22 + i * 10))
    for x in (60, 63, 66):
        rect(im, (x, 43, x + 1, 47), LAV0)
    # little legs
    rect(im, (15, 55, 19, 58), INK); rect(im, (61, 55, 65, 58), INK)
    rect(im, (16, 55, 18, 57), LAV1); rect(im, (62, 55, 64, 57), LAV1)
    save(im, ART / "tv.png", 2)



def flags(w, colours, seed=0, drop=3):
    """Bunting across a width: a sagging string and little pennants."""
    im = new(w, 10)
    for x in range(w):
        y = int(drop * (1 - ((x / w) * 2 - 1) ** 2))
        px(im, x, y, INK2)
    for i, x in enumerate(range(3, w - 5, 8)):
        y = int(drop * (1 - (((x + 2) / w) * 2 - 1) ** 2)) + 1
        paste(im, grid(["kkkkk", "kcccck"[:5], ".kck.", "..k.."], {"k": INK2, "c": colours[i % len(colours)]}), (x, y))
    return im


@art
def room():
    """My Space: Pip's room. Heart wallpaper, a window with a cloud, bunting, a bed made from
    half an eggshell with a quilt, a shelf of treasures, a round rug and Pip on it. 200 × 90
    (400 × 180; phones see the middle band)."""
    W, H = 200, 90
    im = new(W, H, P4)
    for y in range(4, 60, 12):
        for x in range(4 + (y // 12 % 2) * 12, W, 24):
            paste(im, heart(P3, 5), (x, y))
            px(im, x + 14, y + 8, WHITE)
    # chair rail and floor
    rect(im, (0, 58, W - 1, 60), WHITE)
    rect(im, (0, 61, W - 1, 61), P2)
    for y in range(62, H, 6):
        for x in range(0, W, 8):
            rect(im, (x, y, x + 7, y + 5), LAV3 if (x // 8 + y // 6) % 2 else WHITE)
    paste(im, flags(W, [LEM2, MINT2, BLU2, P2, LAV2], drop=4), (0, 0))
    # the window
    win = rounded(40, 38, 10, BLU3)
    paste(win, puff(20, 8, 2), (10, 18))
    paste(win, spark(WHITE, 5), (26, 6))
    win = outline(ring(win, WHITE, False), INK)
    paste(im, win, (14, 12))
    for x in (10, 49):
        curtain = new(9, 36, P2)
        curtain = shade(curtain, P3, P1)
        paste(im, outline(curtain), (x, 10))
    rect(im, (8, 9, 61, 10), INK2)
    # a framed picture: a tiny rainbow
    fr = new(24, 20, WHITE)
    rb = new(20, 16, BLU3)
    arc(rb, 10, 18, 10, [P2, LEM2, MINT2, BLU2], 2)
    ellipse(rb, (4, 12, 16, 24), BLU3)
    paste(fr, rb, (2, 2))
    paste(im, outline(fr), (74, 14))
    # the bed: half an eggshell on the floor, a quilt of hearts pulled up to the pillow
    bed = new(56, 22)
    ellipse(bed, (0, -22, 55, 21), WHITE)
    bed = shade(bed, None, LAV3, rim=2)
    for x in range(0, 56, 6):  # the crack along its rim
        for dx, dy in ((0, 2), (1, 1), (2, 0), (3, 1), (4, 2)):
            px(bed, x + dx, dy, INK)
    quilt = rounded(50, 12, 4, P2)
    for x in range(3, 48, 9):
        paste(quilt, heart(P4, 3), (x, 4))
    quilt = outline(shade(quilt, P3, P1))
    pillow = outline(shade(rounded(16, 9, 4, WHITE), None, LAV3))
    bedi = new(60, 36)
    paste(bedi, pillow, (40, 2))
    paste(bedi, quilt, (3, 7))
    paste(bedi, outline(bed), (1, 13))
    shadow = blob(54, 6, LAV2)
    paste(im, shadow, (130, 70))
    paste(im, bedi, (128, 38))
    # the shelf of treasures
    rect(im, (124, 22, 190, 24), P1)
    rect(im, (124, 25, 190, 25), P0)
    pot = grid(["..kk.kk..", ".kgEkEgk.", "..kkrkk..", "kkkkkkkkk", "kLLLLLLLk", ".kLLLLLk.", ".kkkkkkk."], {**LEGEND})
    paste(im, pot, (128, 15))
    tiny = grid(["...kkkk...", "..kaaaak..", ".kaPmmmak.", ".kamddmak.", "kaamddmaak", "kaammmmaak",
                 "kaaaaaaabk", "kaYaEaGabk", ".kaaaaabk.", "..kbbbbk..", "...kkkk..."],
                {"k": INK, "a": P2, "b": P1, "P": WHITE, "m": LAV3, "d": LCD3, "Y": LEM1, "E": BERRY, "G": MINT1})
    paste(im, tiny, (146, 11))
    paste(im, medal("dj"), (160, 6))
    paste(im, medal("high_scorer"), (175, 6))
    # rug and Pip
    rug = blob(56, 14, P3)
    for x in range(4, 52, 6):
        px(rug, x, 7, WHITE)
    rug = outline(shade(rug, P4, P2), P1)
    paste(im, rug, (64, 70))
    paste(im, sprite("nox.happy"), (84, 60))
    # a webring of little web buttons pinned on the wall
    for i, spec in enumerate([(LAV2, LAV3, LAV1, "star", "wave"), (MINT2, MINT3, MINT1, "heart", "dots")]):
        paste(im, badge(*spec), (100, 30 + i * 12))
    paste(im, sticker(spark(LEM1, 7)), (58, 46))
    save(im, ART / "room.png", 2)



ICONS5.update({
    "cog": [".k.k.", "kkkkk", ".k.k.", "kkkkk", ".k.k."],
})

# Each room's homepage band: its own ground, its own motif (8 art px or so), its own hem.
M = {  # motifs; letters: k ink, a main, b shade, w white, e berry, y lemon
    "heart": [".aa.aa.", "awaaaab", "aaaaaab", ".aaaab.", "..aab..", "...b..."],
    "note": ["...kkkk", "...kkkk", "...k..k", "...k..k", "...k..k", ".kkk.kk", "kkkk.kk", ".kk...."],
    "star": ["...y...", "...y...", "..yyy..", "yyyyyyy", ".yyyyy.", "..yyy..", ".yy.yy.", ".y...y."],
    "moon": [".yyy.", "yy...", "y....", "y....", "yy...", ".yyy."],
    "pad": [".kkkkkkkk.", "kaaaaaaaak", "kakaaaaeak", "kkkkaaeaek", "kakaaaaeak", "kaaakkaaak", ".kkk..kkk."],
    "cloud": ["...ww...", ".wwwwww.", "wwwwwwww", "wwwwwwww", ".bbbbbb."],
    "env": ["kkkkkkkkk", "kwkwwwkwk", "kwwkwkwwk", "kwwwewwwk", "kwwwwwwwk", "kkkkkkkkk"],
    "folder": ["kkkk.....", "kyyykkkkk", "kyyyyyyyk", "kyyyyyyyk", "kyyyyyyyk", "kkkkkkkkk"],
    "bulb": [".kkk.", "kyyyk", "kywyk", "kyyyk", ".kyk.", ".kbk.", "..k.."],
    "bubble": [".kkkkkk.", "kwwwwwwk", "kwkwkwwk", "kwwwwwwk", ".kkwkkk.", "..kk...."],
    "bow": ["kk...kk", "kak.kak", "kaakaak", "kak.kak", "kk.k.kk", "...k..."],
    "gift": ["..e.e..", "kkkkkkk", "kaaeaak", "kkkkkkk", "kaaeaak", "kaaeaak", "kkkkkkk"],
}


def motif(name, main, shade=None, white=WHITE):
    return grid(M[name], {"k": INK, "a": main, "b": shade or main, "w": white, "e": BERRY, "y": main})


def hem(im, y, kind, colour, edge=INK):
    """The band's lower edge: scallops, a zigzag, a heart row or a cloud line."""
    W = im.width
    if kind == "scallop":
        for x in range(0, W, 8):
            ellipse(im, (x, y - 2, x + 7, y + 2), colour)
    elif kind == "zigzag":
        for x in range(W):
            for yy in range(y - 2, y + 1 + (2 - abs((x % 6) - 3)) // 1 - 1):
                px(im, x, yy, colour)
    elif kind == "clouds":
        for x in range(-3, W, 7):
            ellipse(im, (x, y - 3, x + 8, y + 2), colour)
    elif kind == "flat":
        rect(im, (0, y - 2, W - 1, y), colour)
    return im


def band(ground, motifs, hem_kind, hem_colour, step=24, pattern=None, rows=(2, 10)):
    """A homepage band 1000 × 80: the band fills rows 2–10 and its hem ends by row 12 (24 px),
    so the title's caps below keep a clear gap of 8 px or more."""
    W, H = 1000, 80
    im = new(W, H)
    y0, y1 = rows
    b = new(W, H)
    rect(b, (0, y0, W - 1, y1), ground)
    hem(b, y1 + 1, hem_kind, hem_colour if hem_kind != "flat" else ground)
    if pattern:
        pattern(b, y0, y1)
    b = outline(b, INK, grow=False)
    rect(b, (0, y0, W - 1, y0), INK)
    for i, x in enumerate(range(6, W, step)):
        m = motifs[i % len(motifs)]
        top = y0 + 1 + (y1 - y0 - m.height) // 2 + (1 if i % 2 and m.height < 8 else 0)
        paste(b, m, (x, top))
    paste(im, b, (0, 0))
    return im


def stripes_diag(colour, period=6):
    def f(im, y0, y1):
        for y in range(y0 + 1, y1 + 1):
            for x in range(im.width):
                if (x + y) % period < period // 2:
                    px(im, x, y, colour)
    return f


def staff(colour):
    def f(im, y0, y1):
        for y in range(y0 + 2, y1, 2):
            for x in range(im.width):
                px(im, x, y, colour)
    return f


def checks(colour, cell=3):
    def f(im, y0, y1):
        for y in range(y0 + 1, y1 + 1):
            for x in range(im.width):
                if ((x // cell) + ((y - y0 - 1) // cell)) % 2 == 0:
                    px(im, x, y, colour)
    return f


def rainbow_rows(im, y0, y1):
    cols = [P2, LEM2, MINT2, BLU2, LAV2]
    for y in range(y0 + 1, y1 + 1):
        rect(im, (0, y, im.width - 1, y), cols[((y - y0 - 1) * len(cols)) // (y1 - y0)])


def dots(colour, step=4):
    def f(im, y0, y1):
        for y in range(y0 + 2, y1, step // 2 + 1):
            for x in range((y % 2) * 2, im.width, step):
                px(im, x, y, colour)
    return f


def banner_art(name):
    h = lambda c: motif("heart", c, P1)  # noqa: E731
    specs = {
        "banner": (P3, [h(P2), outline(spark(WHITE, 5), P0)], "scallop", WHITE, 20, dots(P4)),
        "listen": (P3, [motif("note", INK), h(P1), motif("note", INK), outline(spark(WHITE, 5), P0)], "scallop", P2, 18, staff(P2)),
        "watch": (BLU0, [motif("star", LEM2), motif("moon", LEM1), spark(WHITE, 5)], "clouds", LAV3, 16, dots(BLU1, 6)),
        "games": (MINT2, [motif("pad", LAV2), h(P2)], "zigzag", MINT1, 20, dots(MINT3, 5)),
        "house": (WHITE, [], "scallop", LEM2, 24, checks(LEM2)),
        "files": (LAV3, [motif("folder", LEM2), spark(WHITE, 5)], "flat", None, 20, dots(LAV2)),
        "inbox": (BLU3, [motif("env", WHITE), h(P2)], "flat", None, 20, stripes_diag(BLU2, 8)),
        "me": (P4, [motif("bow", P1), outline(spark(LEM2, 5), LEM0)], "scallop", P3, 18, dots(P3)),
        "space": (BLU2, [motif("cloud", WHITE, LAV3)], "clouds", WHITE, 17, dots(BLU3, 6)),
        "smart-home": (LEM3, [motif("bulb", LEM1, LEM0), outline(spark(WHITE, 5), LEM0)], "scallop", LEM2, 18, None),
        "party": (WHITE, [motif("gift", P2), outline(spark(LEM2, 5), LEM0), h(MINT2)], "zigzag", P2, 18, rainbow_rows),
        "control": (LAV3, [], "flat", None, 30, stripes_diag(WHITE, 8)),
        "ask": (LAV3, [motif("bubble", WHITE), outline(spark(WHITE, 5), LAV1)], "scallop", LAV2, 20, dots(LAV2)),
    }
    ground, motifs, hk, hc, step, pattern = specs[name]
    if name == "house":  # the checkerboard carries a little heart now and then
        motifs = [new(1, 1), new(1, 1), h(P2)]
    if name == "control":  # construction stripes, candy-coloured, and nothing else: calm
        motifs = [new(1, 1)]
    return band(ground, motifs, hk, hc, step, pattern)


BANNERS = ["banner", "listen", "watch", "games", "house", "files", "inbox", "me", "space",
           "smart-home", "party", "control", "ask"]


@art
def banners():
    """Each room's header: a homepage band of its own (hearts, staff and notes, a night of stars,
    game pads, a checkerboard, folders, airmail, bows, clouds, bulbs, a rainbow with gifts,
    candy construction stripes, speech bubbles). 1000 × 80 (2000 × 160, pixel-exact on any
    width): the hem ends 12 art px down, 8 px or more above the title's caps."""
    for name in BANNERS:
        file = "banner.png" if name == "banner" else f"banner-{name}.png"
        save(banner_art(name), ART / file, 2)


@art
def sheet_corner():
    """Sheets and dialogs: a heart sticker stuck in the bottom-right corner, its top corner
    peeling. A 9-slice with nothing else (48 × 48 at 2 ×, 16 px corners: slice 32)."""
    im = new(48, 48)
    rows = [".LL...LL.", "LPLL.LLLL", "LPLLLLLLL", "LLLLLLLLl", ".LLLLLLl.", "..LLLll..", "...Lll...", "....l...."]
    h = grid(rows, {"L": P2, "l": P1, "P": WHITE})
    h = outline(ring(h, WHITE, False), INK)
    # the right lobe's white edge peeling up, a lavender shadow under the fold
    for (x, y, c) in ((10, 1, (0, 0, 0, 0)), (11, 2, (0, 0, 0, 0)), (10, 2, WHITE), (9, 2, LAV2), (10, 3, LAV2)):
        px(h, x, y, c)
    paste(im, h, (48 - h.width - 3, 48 - h.height - 3))
    save(im, ART / "sheet-corner.png", 2)


@art
def sprout():
    """The sprout on top of the egg (the deck's shell): two leaves that wiggle while music
    plays (2 frames of 13 × 8), anchored at the top middle, over the shell's band."""
    rows = [
        [".kk.......kk.", "kEgk.....kgEk", "kggk.....kggk", ".kggk...kggk.", "..kkkk.kkkk..", ".....krk.....", ".....krk.....", "......k......"],
        ["kk.........kk", "kEgk.....kgEk", ".kggk...kggk.", "..kggk.kggk..", "...kkkrkkk...", ".....krk.....", ".....krk.....", "......k......"],
    ]
    legend = {"k": INK, "g": MINT1, "E": MINT2, "r": MINT0}
    save(pixel.sheet([grid(r, legend) for r in rows]), ART / "sprout.png")


@art
def panel_frame():
    """Every card's frame, a 9-slice inside its 16 px padding (8 art px): a pink pinstripe all
    round, a dotted lace fan in each corner, and a little plum-edged heart stuck on the top-left corner.
    24 × 24 at 2 × (slice 16)."""
    S = 24
    im = new(S, S)
    # the pinstripe (solid, so the stretched edges stay clean)
    for i in range(3, S - 3):
        for (x, y) in ((i, 3), (i, S - 4), (3, i), (S - 4, i)):
            px(im, x, y, P3)
    # lace fans in the corners: white quarter-rounds with a dotted pink rim
    for cx, cy in ((0, 0), (S - 1, 0), (0, S - 1), (S - 1, S - 1)):
        for y in range(8):
            for x in range(8):
                X, Y = (x if cx == 0 else S - 1 - x), (y if cy == 0 else S - 1 - y)
                d2 = x * x + y * y
                if d2 < 20:
                    px(im, X, Y, P4 if d2 >= 4 else P3)
                elif d2 < 34 and (x + y) % 2 == 0:
                    px(im, X, Y, P1)
    h = outline(grid([".L.L.", "LPLLL", "LLLLl", ".LLl.", "..l.."], {"L": P2, "l": P1, "P": WHITE}))
    paste(im, h, (0, 0))
    save(im, ART / "panel-frame.png", 2)


@art
def egg_poke():
    """Poke the egg on Home: it hops twice, Pip beams on its screen (8 frames of the egg's own
    76 × 64); hearts burst out (the deck's candy heart)."""
    cl = soft_cloud(74, 20)
    frames = []
    for dy, face in ((0, "awake"), (-2, "awake"), (-3, "awake"), (-3, "blink"), (0, "awake"),
                     (-2, "awake"), (-1, "awake"), (0, "awake")):
        f = new(76, 64)
        screen = new(17, 12)
        paste(screen, grid(["....k.k....", ".....k.....", "...kkkkk...", "..k.....k..", ".k.k...k.k.",
                            ".kk.k.k.kk.", ".k..kkk..k.", ".k.k.k.k.k.", "..k.....k..", "...kkkkk..."],
                           {"k": LCD0}) if face == "awake" else grid(MINI["blink"], {"k": LCD0}), (3, 2))
        d = device(40, 44, screen, seed=7, icons=False)
        paste(f, cl, (1, 64 - cl.height))
        paste(f, d, (14, 3 + dy))
        frames.append(f)
    save(pixel.sheet(frames), ART / "egg-poke.png")


def coin_star(width):
    """A star sticker seen turning: `width` of its 11 columns shown, squeezed about the middle."""
    star = sticker(grid(["...k...", "..kkk..", "kkkkkkk", ".kkkkk.", "..kkk..", ".kk.kk.", "k.....k"], {"k": LEM1}))
    star = shade(star, None, None)
    if width >= star.width:
        return star
    cols = [round(i * (star.width - 1) / max(1, width - 1)) for i in range(width)] if width > 1 else [star.width // 2]
    out = new(star.width, star.height)
    x0 = (star.width - width) // 2
    for i, c in enumerate(cols):
        for y in range(star.height):
            out.putpixel((x0 + i, y), star.getpixel((c, y)))
    if width <= 3:  # edge-on: a plum sliver
        for y in range(star.height):
            if out.getpixel((star.width // 2, y))[3]:
                out.putpixel((star.width // 2, y), rgba(INK))
    return out


@art
def star_sticker():
    """A star sticker stuck in the hero's sky (top right, clear of the words); poked, it turns
    round like a coin and sparkles fly (8 frames of 13 × 13)."""
    save(coin_star(13), ART / "star.png")
    save(pixel.sheet([coin_star(w) for w in (13, 9, 5, 1, 5, 9, 13, 13)]), ART / "star-spin.png")


@art
def sprout_poke():
    """Poke the sprout on the deck's shell: it springs up and flops, leaves flying
    (6 frames of the sprout's 13 × 8)."""
    legend = {"k": INK, "g": MINT1, "E": MINT2, "r": MINT0}
    rows = [
        ["kk.........kk", "kEgk.....kgEk", ".kggk...kggk.", "..kggk.kggk..", "...kkkrkkk...", ".....krk.....", ".....krk.....", "......k......"],
        [".....kk.kk...", "....kEgkgEk..", "....kggkggk..", ".....kkrkk...", "......krk....", "......krk....", ".....krk.....", "......k......"],
        ["......k......", ".....kEk.....", ".....kgk.....", ".....kgk.....", "......r......", "......r......", ".....krk.....", "......k......"],
        ["...kk...kk...", "..kEgk.kgEk..", "..kggkrkggk..", "...kkkrkkk...", "......r......", "......r......", ".....krk.....", "......k......"],
        [".............", "kkk.......kkk", "kEggk...kggEk", ".kkggkrkggkk.", "....kkrkk....", "......r......", ".....krk.....", "......k......"],
        [".kk.......kk.", "kEgk.....kgEk", "kggk.....kggk", ".kggk...kggk.", "..kkkk.kkkk..", ".....krk.....", ".....krk.....", "......k......"],
    ]
    save(pixel.sheet([grid(r, legend) for r in rows]), ART / "sprout-poke.png")
    save(grid([".kk", "kEk", "kk."], legend), ART / "leaf.png")


@art
def dance_poke():
    """Poke Pip on the deck's corner: a big jump, a twirl (it turns its back and round), a
    landing squash; notes fly (6 frames of 20 × 22)."""
    front, happy = sprite("nox.happy"), sprite("nox.idle")
    back = grid([row.replace("L", "v").replace("k", "k") for row in sprites_src.pip(
        [".kvvvvvvvvvvvvk.", ".kvvvvvvvvvvvvk.", ".kvvvvvvvvvvvvk.", ".kvvvvvvvvvvvvk."], "up")], LEGEND)
    frames = []
    for pic, dy, flipit in ((happy, 1, False), (front, -3, False), (back, -5, False), (front, -5, True),
                            (front, -2, False), (happy, 1, False)):
        f = new(20, 22)
        paste(f, flip(pic) if flipit else pic, (2, 6 + dy))
        frames.append(f)
    save(pixel.sheet(frames), ART / "dance-poke.png")
    save(grid([".kk", ".kk", ".k.", "kk.", "kk."], {"k": BERRY}), ART / "note.png")


if __name__ == "__main__":
    names = sys.argv[1:] or list(MADE)
    for name in names:
        MADE[name]()
        print("made", name)
