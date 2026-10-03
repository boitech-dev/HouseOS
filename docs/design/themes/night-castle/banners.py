"""Header banners, one per wing of the castle: native 400 × 54, shown about × 3 behind each room's
title. The title sits on the left (and, on phones, in the middle third), so those stay dark wall;
the ceiling runs across the top; each room's own thing stands on the right, lit by the moon
through a window or by candles."""
import math

from lib import dith, disc, get, hline, new, noise, poly, put, rect, save, vline
from pixel import rgba as pixel_rgba  # noqa: E402  (lib put the toolkit on the path)
from palette import BONE, CRIMSON, FLAME, GLASS, GOLD, MOON, MOSS, NIGHT, STONE

W, H = 400, 54


def wall(seed=1):
    im = new(W, H, NIGHT[1])
    rnd = noise(seed)
    for y in range(H):
        for x in range(W):
            if y % 6 == 5 or (x + (y // 6) * 7) % 14 == 0:
                put(im, x, y, NIGHT[0])
            elif y % 6 == 0 and rnd.random() < 0.18:
                put(im, x, y, NIGHT[2])
    return im


def vault(im, bays=(0, 100, 200, 300, 400)):
    """Rib vaults along the top: pointed arcs springing from each pilaster."""
    for x0 in bays:
        rect(im, x0 - 3, 0, x0 + 4, H, STONE[1])  # pilaster
        vline(im, x0 + 3, 0, H, STONE[3])
        vline(im, x0 - 3, 0, H, NIGHT[0])
        rect(im, x0 - 4, 14, x0 + 5, 17, STONE[2])  # capital
        hline(im, x0 - 4, x0 + 5, 14, STONE[4])
        put(im, x0 + 4, 15, GOLD[2])
    for a, b in zip(bays, bays[1:]):
        mid = (a + b) / 2
        for x in range(a + 4, b - 3):
            t = abs(x - mid) / ((b - a) / 2)
            y = int(15 - 15 * (1 - t ** 1.6))  # a pointed arc from capital to capital
            for yy in range(0, y):
                if get(im, x, yy)[:3] == (0x10, 0x08, 0x18):
                    put(im, x, yy, NIGHT[0])  # the vault's web in shadow
            put(im, x, y, STONE[3] if x > mid else STONE[2])
            put(im, x, y + 1, NIGHT[0])


def lancet(im, x0, y0, w, h, lit=True):
    """A tall pointed window: dark leaded glass, moonlit on its right, a trefoil at the top."""
    rnd = noise(x0)
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            spring = y0 + w * 0.6
            if y < spring:
                r = w * 0.85
                inside = (math.hypot(x - (x0 + r - 0.5), y - spring) <= r) and (
                    math.hypot(x - (x0 + w - r - 0.5), y - spring) <= r)
            else:
                inside = True
            if not inside:
                continue
            u = (x - x0) / max(1, w - 1)
            quarry = ((x - x0) // 3 + (y - y0) // 4) % 3
            c = [GLASS[0], NIGHT[4], GLASS[1]][quarry]
            if lit and u > 0.55 and (y - y0) < h * 0.6:
                c = [MOON[0], GLASS[1], MOON[1]][quarry]  # where the moon strikes the glass
            if (x - x0 + (y - y0)) % 4 == 0 and (x - x0 - (y - y0)) % 4 == 0:
                c = NIGHT[0]  # lead: a diamond lattice
            if x == x0 + w // 2:
                c = STONE[2]  # the mullion
            put(im, x, y, c)
    # a red pane at the top, a glint
    put(im, x0 + w // 2 - 1, y0 + 3, CRIMSON[4])
    put(im, x0 + w // 2 + 1, y0 + 3, CRIMSON[3])
    # outline and sill
    for y in range(y0 - 1, y0 + h + 1):
        for x in range(x0 - 1, x0 + w + 1):
            if not get(im, x, y)[3] or get(im, x, y)[:3] in ((0x10, 0x08, 0x18), (0x08, 0x00, 0x10), (0x18, 0x10, 0x28)):
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    c = get(im, x + dx, y + dy)[:3]
                    if c in ((0x10, 0x20, 0x60), (0x30, 0x18, 0x48), (0x20, 0x40, 0xa0), (0x58, 0x60, 0x78), (0x88, 0x90, 0xa8)):
                        put(im, x, y, STONE[3] if dx < 0 else STONE[1])
                        break
    hline(im, x0 - 2, x0 + w + 2, y0 + h, STONE[4])


def beam(im, x0, x1, y0, slope=0.6, strength=0.22):
    """A shaft of moonlight falling down-left from a window (a sparse dither, never over text rows)."""
    for y in range(y0, H):
        off = (y - y0) * slope
        for x in range(int(x0 - off), int(x1 - off)):
            t = strength * (1 - (y - y0) / (H - y0))
            if dith(t, x, y):
                put(im, x, y, NIGHT[3])


def candle(im, x, y, h=5):
    rect(im, x, y, x + 2, y + h, BONE[3])
    put(im, x + 1, y, BONE[4])
    put(im, x, y + h - 1, BONE[1])
    put(im, x, y - 1, FLAME[3])
    put(im, x, y - 2, FLAME[4])
    put(im, x + 1, y - 1, FLAME[2])


def candelabrum(im, x, y):
    """Three candles on a gold stand."""
    vline(im, x, y, y + 12, GOLD[3])
    put(im, x + 1, y + 4, GOLD[4])
    hline(im, x - 5, x + 6, y, GOLD[3])
    hline(im, x - 3, x + 4, y + 12, GOLD[2])
    for dx in (-5, 0, 5):
        candle(im, x + dx - 1 + (1 if dx == 0 else 0), y - 6)


def hall():
    """The great hall (every room without its own): tall windows, moonbeams."""
    im = new(W, H)
    for x in (286, 318, 350, 382):
        lancet(im, x, 20, 11, 30)
        beam(im, x - 4, x + 11, 50, 0.9, 0.18)
    candelabrum(im, 308, 40)
    return im


def chapel():
    """Listen: the chapel's organ, its pipes in gold, a rose window above."""
    im = new(W, H)
    # rose window
    cx, cy, r = 340, 14, 11
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            d = math.hypot(x - cx, y - cy)
            if d > r:
                continue
            a = math.atan2(y - cy, x - cx)
            k = int((a + math.pi) / (2 * math.pi) * 8) % 8
            c = [GLASS[1], CRIMSON[4], GLASS[5], GOLD[4], GLASS[2], CRIMSON[3], GLASS[7], GOLD[3]][k]
            if d < 3:
                c = GOLD[5]
            if abs(d - 7) < 0.6 or d > r - 1 or (abs(math.sin(a * 4)) < 0.18 and d > 3):
                c = NIGHT[0]
            put(im, x, y, c)
    # organ case and pipes
    rect(im, 284, 30, 398, 54, STONE[1])
    hline(im, 284, 398, 30, GOLD[3])
    pipes = [(288, 20), (294, 16), (300, 12), (306, 16), (312, 20), (368, 20), (374, 16), (380, 12),
             (386, 16), (392, 20)]
    for i, (px, top) in enumerate(pipes):
        h = 30 - top
        rect(im, px, top + 14, px + 4, 44, GOLD[2])
        vline(im, px + 3, top + 14, 44, GOLD[4])
        vline(im, px, top + 14, 44, GOLD[1])
        put(im, px + 1, top + 13, GOLD[5])
        rect(im, px + 1, 38, px + 3, 40, NIGHT[0])  # the pipe's mouth
    rect(im, 322, 36, 358, 54, STONE[2])  # the console
    hline(im, 322, 358, 36, STONE[4])
    for x in range(324, 356, 2):  # keys
        put(im, x, 40, BONE[4])
        put(im, x + 1, 40, NIGHT[0])
    candle(im, 318, 30)
    candle(im, 360, 30)
    return im


def library():
    """Files: shelves to the ceiling, spines in faded crimson, green and blue, a ladder."""
    im = new(W, H)
    rnd = noise(5)
    for x0, x1 in ((280, 334), (344, 398)):
        rect(im, x0, 18, x1, 54, STONE[1])
        for sy in range(20, 54, 8):
            hline(im, x0, x1, sy + 7, GOLD[1])
            x = x0 + 1
            while x < x1 - 2:
                w = rnd.choice((2, 2, 3))
                h = rnd.choice((5, 6, 6, 7))
                c = rnd.choice([CRIMSON[2], CRIMSON[3], MOSS[1], MOSS[2], GLASS[0], GLASS[1], GOLD[2], STONE[4]])
                rect(im, x, sy + 7 - h, x + w, sy + 7, c)
                put(im, x, sy + 7 - h + 1, GOLD[3] if rnd.random() < 0.4 else c)
                x += w + (1 if rnd.random() < 0.2 else 0)
        vline(im, x1 - 1, 18, 54, STONE[3])
    # the ladder leaning on the right shelves
    for y in range(18, 54):
        put(im, 370 - (y - 18) // 6, y, GOLD[2])
        put(im, 378 - (y - 18) // 6, y, GOLD[2])
        if y % 5 == 0:
            hline(im, 370 - (y - 18) // 6, 379 - (y - 18) // 6, y, GOLD[3])
    # a hanging lantern
    vline(im, 339, 0, 22, NIGHT[0])
    rect(im, 337, 22, 342, 28, GOLD[2])
    rect(im, 338, 23, 341, 27, FLAME[3])
    put(im, 339, 24, FLAME[4])
    return im


def clockwork():
    """Control: inside the clock tower: great gears, a pendulum, a lever."""
    im = new(W, H)

    def gear(cx, cy, r, teeth, c, lit, phase=0.0):
        for y in range(cy - r - 2, cy + r + 3):
            for x in range(cx - r - 2, cx + r + 3):
                d = math.hypot(x - cx, y - cy)
                a = math.atan2(y - cy, x - cx) + phase
                tooth = (math.sin(a * teeth) > 0.3)
                if d <= r or (d <= r + 2 and tooth):
                    col = lit if (x - cx) - (y - cy) > r * 0.3 else c
                    if r * 0.35 < d < r * 0.75 and abs(math.sin(a * 3)) > 0.35:
                        continue  # the spokes' gaps
                    put(im, x, y, col)
        disc(im, cx, cy, 2, NIGHT[0])
        put(im, cx, cy, GOLD[5])

    gear(318, 30, 16, 12, GOLD[2], GOLD[3])
    gear(354, 15, 10, 9, STONE[3], STONE[5], 0.3)
    gear(372, 44, 12, 10, GOLD[1], GOLD[2], 0.1)
    gear(292, 46, 7, 8, STONE[3], STONE[5])
    # the pendulum
    vline(im, 392, 0, 44, STONE[4])
    disc(im, 392, 46, 5, GOLD[3])
    disc(im, 393, 45, 2, GOLD[5])
    return im


def throne():
    """Me: the throne room: a high-backed throne, crimson drapes, gold."""
    im = new(W, H)
    # drapes from the ceiling, tied back
    for x0 in (282, 384):
        for x in range(x0, x0 + 16):
            for y in range(0, H):
                sway = int(3 * math.sin(y / 8))
                if x0 + (y // 3) * 0 <= x + sway < x0 + 16:
                    c = CRIMSON[2] if (x + y // 4) % 5 else CRIMSON[1]
                    if (x - x0) % 5 == 4:
                        c = CRIMSON[3]
                    put(im, x, y, c)
        hline(im, x0, x0 + 16, 30, GOLD[4])
    # the throne
    tx = 340
    poly(im, [(tx - 14, 54), (tx - 14, 22), (tx - 10, 10), (tx, 4), (tx + 10, 10), (tx + 14, 22), (tx + 14, 54)], GOLD[2])
    poly(im, [(tx - 10, 54), (tx - 10, 22), (tx - 7, 14), (tx, 9), (tx + 7, 14), (tx + 10, 22), (tx + 10, 54)], CRIMSON[2])
    for y in range(12, 40):
        put(im, tx + 9, y, CRIMSON[3])
    rect(im, tx - 16, 38, tx + 17, 42, GOLD[3])  # the seat
    hline(im, tx - 16, tx + 17, 38, GOLD[5])
    rect(im, tx - 18, 30, tx - 13, 42, GOLD[2])  # arms
    rect(im, tx + 13, 30, tx + 18, 42, GOLD[3])
    put(im, tx, 5, CRIMSON[5])  # a ruby at the crest
    put(im, tx, 15, BONE[4])
    # steps before it
    for i in range(3):
        hline(im, tx - 26 + i * 3, tx + 27 - i * 3, 46 + i * 3, STONE[4])
        rect(im, tx - 26 + i * 3, 47 + i * 3, tx + 27 - i * 3, 49 + i * 3, STONE[2])
    candle(im, 306, 34)
    candle(im, 374, 34)
    return im


def armory():
    """Games: the armoury: a rack of sub-weapons: dagger, axe, cross, holy water, a stopwatch."""
    im = new(W, H)
    rect(im, 280, 20, 398, 50, STONE[1])
    hline(im, 280, 398, 20, GOLD[3])
    hline(im, 280, 398, 49, GOLD[2])
    # a shield between crossed swords
    cx = 340
    for i in range(24):
        put(im, cx - 12 + i, 22 + i, MOON[2])
        put(im, cx + 12 - i, 22 + i, MOON[2])
    for y in range(24, 46):
        half = 8 if y < 36 else int(8 - (y - 36) * 0.8)
        for x in range(cx - half, cx + half + 1):
            put(im, x, y, CRIMSON[3] if x < cx else CRIMSON[4])
        put(im, cx - half, y, GOLD[3])
        put(im, cx + half, y, GOLD[4])
    hline(im, cx - 8, cx + 9, 24, GOLD[4])
    for y in range(28, 42):  # a gold cross on the shield
        put(im, cx, y, GOLD[5])
    hline(im, cx - 4, cx + 5, 32, GOLD[5])
    # dagger
    for i in range(12):
        put(im, 286 + i, 34 - i // 3, MOON[3])
    hline(im, 284, 288, 33, GOLD[3])
    # axe
    vline(im, 306, 24, 46, GOLD[1])
    poly(im, [(307, 26), (314, 23), (316, 30), (313, 36), (307, 32)], MOON[2])
    vline(im, 315, 25, 34, MOON[3])
    # holy water vial
    rect(im, 362, 32, 368, 42, GLASS[2])
    rect(im, 363, 29, 367, 32, BONE[3])
    put(im, 366, 34, GLASS[3])
    # stopwatch
    disc(im, 385, 36, 6, GOLD[3])
    disc(im, 385, 36, 4, BONE[4])
    vline(im, 385, 32, 36, NIGHT[0])
    hline(im, 385, 388, 36, NIGHT[0])
    rect(im, 384, 28, 387, 30, GOLD[4])
    return im


def gallery():
    """Watch: the portrait gallery: heavy gilded frames on the wall, their canvases dark."""
    im = new(W, H)
    for x0, y0, w, h, scene in ((282, 22, 24, 22, 0), (316, 18, 38, 30, 1), (364, 22, 26, 22, 2)):
        rect(im, x0 - 3, y0 - 3, x0 + w + 3, y0 + h + 3, GOLD[2])
        hline(im, x0 - 3, x0 + w + 3, y0 - 3, GOLD[4])
        vline(im, x0 + w + 2, y0 - 3, y0 + h + 3, GOLD[4])
        rect(im, x0 - 1, y0 - 1, x0 + w + 1, y0 + h + 1, NIGHT[0])
        rect(im, x0, y0, x0 + w, y0 + h, NIGHT[2])
        if scene == 1:  # a moonlit landscape
            disc(im, x0 + w - 10, y0 + 8, 4, MOON[2])
            poly(im, [(x0, y0 + h), (x0, y0 + 20), (x0 + 12, y0 + 14), (x0 + 24, y0 + 20), (x0 + w, y0 + 16),
                      (x0 + w, y0 + h)], NIGHT[4])
        else:  # a dark portrait: a pale face in shadow
            disc(im, x0 + w // 2, y0 + 9, 4, BONE[1])
            poly(im, [(x0 + 4, y0 + h), (x0 + w // 2, y0 + 13), (x0 + w - 4, y0 + h)], NIGHT[0])
            put(im, x0 + w // 2 - 1, y0 + 9, CRIMSON[4] if scene == 2 else NIGHT[0])
            put(im, x0 + w // 2 + 1, y0 + 9, CRIMSON[4] if scene == 2 else NIGHT[0])
    # a velvet rope on posts
    for x in (276, 396):
        vline(im, x, 44, 54, GOLD[3])
        put(im, x, 43, GOLD[5])
    for x in range(276, 397):
        put(im, x, 45 + int(3 * math.sin((x - 276) / 120 * math.pi)), CRIMSON[3])
    return im


def cobweb(im, x0, y0, flip=False, size=9):
    """A web in a vault's corner: radial threads and sagging arcs, faint."""
    sx = -1 if flip else 1
    for k in range(4):
        ang = (k + 0.5) / 4 * math.pi / 2
        for r in range(size):
            put(im, x0 + sx * round(math.cos(ang) * r), y0 + round(math.sin(ang) * r), STONE[3])
    for r in (3, 6, 9):
        for i in range(0, 16):
            ang = i / 15 * math.pi / 2
            rr = r + 0.8 * math.sin(i / 15 * math.pi * 4)
            if dith(0.8, x0 + i, y0):
                put(im, x0 + sx * round(math.cos(ang) * rr), y0 + round(math.sin(ang) * rr), STONE[2])


HANGINGS = {  # each wing its own hangings: (tapestry field, lattice, pennant, pennant edge)
    1: (CRIMSON[0], CRIMSON[1], NIGHT[3], NIGHT[4]),
    2: ("#101838", "#102060", CRIMSON[1], CRIMSON[2]),
    3: (MOSS[0], MOSS[1], CRIMSON[1], CRIMSON[2]),
    4: (NIGHT[2], NIGHT[3], GOLD[1], GOLD[2]),
    5: (CRIMSON[0], CRIMSON[1], CRIMSON[1], CRIMSON[2]),
    6: (NIGHT[2], NIGHT[4], CRIMSON[1], CRIMSON[2]),
    7: ("#101838", NIGHT[3], NIGHT[3], NIGHT[4]),
    8: (NIGHT[2], NIGHT[3], NIGHT[2], NIGHT[3]),
}


def tapestry(im, x0, x1, y0, y1, seed):
    """A dark hanging: crimson-black field, a gold thread border, a lattice, a bat in the middle."""
    hline(im, x0 - 2, x1 + 2, y0, GOLD[2])  # the rod
    put(im, x0 - 3, y0, GOLD[4])
    put(im, x1 + 2, y0, GOLD[4])
    for y in range(y0 + 1, y1):
        for x in range(x0, x1):
            field, lattice = HANGINGS[seed][:2]
            c = field
            if (x - x0 + y) % 8 == 0 or (x - x0 - y) % 8 == 0:
                c = lattice
            if x in (x0 + 2, x1 - 3) or y == y0 + 3:
                c = GOLD[1]
            if x in (x0, x1 - 1):
                c = NIGHT[0]
            put(im, x, y, c)
    cx, cy = (x0 + x1) // 2, y0 + 30
    bat = ["k.......k", "kk.k.k.kk", "kkkkkkkkk", ".kkkkkkk.", "..k.k.k.."]
    for yy, row in enumerate(bat):
        for xx, ch in enumerate(row):
            if ch == "k":
                put(im, cx - 4 + xx, cy + yy, NIGHT[0])
    for x in range(x0, x1, 3):  # a fringe at the bottom
        put(im, x, y1, GOLD[1])


def pennant(im, x0, y0, w, h, c1, c2):
    """A hanging banner with a swallowtail, from a pole."""
    hline(im, x0 - 1, x0 + w + 1, y0, GOLD[2])
    for y in range(y0 + 1, y0 + h):
        for x in range(x0, x0 + w):
            if y > y0 + h - 5 and abs(x - (x0 + w / 2 - 0.5)) < (y - (y0 + h - 5)):
                continue
            put(im, x, y, c2 if x == x0 + w - 1 else c1)
    for y in range(y0 + 4, y0 + h - 6, 5):
        hline(im, x0 + 1, x0 + w - 1, y, GOLD[1])


def sconce(im, x, y):
    """A torch in an iron bracket on a pilaster: the only warm light behind the title."""
    vline(im, x, y, y + 5, NIGHT[0])
    hline(im, x - 1, x + 2, y + 1, GOLD[1])
    put(im, x, y - 1, FLAME[2])
    put(im, x, y - 2, FLAME[3])
    put(im, x + 1, y - 1, FLAME[1])
    put(im, x, y - 3, FLAME[1])


def curtain(im, x0=300):
    """The calm right end: a heavy velvet drape from a gold rod, tied back low."""
    hline(im, x0, W, 1, GOLD[2])
    for y in range(2, H):
        for x in range(x0, W):
            sway = int(2 * math.sin(y / 9 + x / 30)) if y > 30 else 0
            k = (x - x0 + sway) % 10
            c = [NIGHT[0], NIGHT[1], NIGHT[1], CRIMSON[0], CRIMSON[1], CRIMSON[0], NIGHT[1], NIGHT[1], NIGHT[0], NIGHT[0]][k]
            put(im, x, y, c)
    for x in range(x0, W):  # the valance, a deeper fold with a gold fringe
        for y in range(2, 9):
            put(im, x, y, CRIMSON[0] if (x // 6) % 2 else NIGHT[1])
        if x % 2 == 0:
            put(im, x, 9, GOLD[1])
    vline(im, x0, 2, H, NIGHT[0])  # its edge
    vline(im, x0 + 1, 2, H, CRIMSON[1])
    hline(im, x0 + 1, x0 + 9, 36, GOLD[2])  # the tie-back's tassel
    put(im, x0 + 9, 37, GOLD[3])


def base(seed):
    """Every wing's wall: vaults with webs, a tapestry and a banner behind the title, torches on
    the pilasters, and the curtain at the right end (header buttons sit there)."""
    im = wall(seed)
    vault(im)
    for x0 in (0, 100, 200):
        cobweb(im, x0 + 4, 17 if x0 else 1, size=7)
        cobweb(im, x0 + 96, 17 if x0 else 1, flip=True, size=6)
    tapestry(im, 22, 78, 5, 54, seed)
    pennant(im, 126, 18, 13, 30, *HANGINGS[seed][2:])
    pennant(im, 160, 18, 13, 26, *HANGINGS[(seed % 8) + 1][2:])
    sconce(im, 100, 24)
    sconce(im, 200, 24)
    return im


SHIFT = -96  # the wings' props, drawn for 280–400, stand in 184–304 (clear of the phone's crop edge
             # and of the header buttons over the right quarter)


def banner(props, seed):
    im = base(seed)
    if props:
        shifted = new(W, H)
        shifted.alpha_composite(props().crop((-SHIFT, 0, W, H)), (0, 0))
        # on phones the subtitle crosses the props' lower half: there they stand in shadow,
        # two dark tones that keep their shapes
        px = shifted.load()
        for y in range(26, H):
            for x in range(W):
                r, g, b, a = px[x, y]
                if a and y >= 26 + max(0, x - 180) * 0.1:  # a cast shadow's edge, falling to the left
                    lit = (r * 3 + g * 6 + b) / 10 > (70 if y < 36 else 110)
                    px[x, y] = pixel_rgba(NIGHT[3] if lit else NIGHT[0])
        im.alpha_composite(shifted)
    curtain(im)
    return im


BANNERS = {"banner-hall.png": lambda: banner(hall, 1), "banner-chapel.png": lambda: banner(chapel, 2),
           "banner-library.png": lambda: banner(library, 3), "banner-clock.png": lambda: banner(clockwork, 4),
           "banner-throne.png": lambda: banner(throne, 5), "banner-armory.png": lambda: banner(armory, 6),
           "banner-gallery.png": lambda: banner(gallery, 7), "banner-quiet.png": lambda: banner(None, 8)}

if __name__ == "__main__":
    for name, fn in BANNERS.items():
        save(fn(), name, scale=1)
    print("banners written")
