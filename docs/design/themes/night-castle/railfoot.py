"""The rail's foot: a compact shrine standing just above Ask Nox. A gold candelabrum of three
candles on a stone altar draped in crimson, a heart relic in a gold reliquary at its foot, a
pointed niche of shadow behind, a strip of flagstones. 70 × 68 native, shown × 3 (210 × 204),
whole-scaled down by the platform when the rail's foot is short.
Idle: the three flames flicker (4 frames). Poke (the whip): the candles flare and burst, a heart
drops from the candelabrum and bounces on the altar; a few hearts fly (burst)."""
import math

from lib import get, hline, new, outline, paste, put, rect, vline
from palette import BONE, CRIMSON, FLAME, GOLD, MOON, NIGHT, STONE

W, H = 70, 68
CANDLES = ((22, 27), (35, 19), (48, 27))  # (x of the candle's left column, top of the wax)
FLOOR = 62

FLICKER = [  # 3 × 5 flames, bottom row at the wick
    [".p.", ".P.", "pPp", "PcP", ".k."],
    [".p.", "pP.", "pPp", "PcP", ".k."],
    ["...", ".p.", "pPp", "PcP", ".k."],
    ["..p", ".Pp", "pPp", "PcP", ".k."],
]
FLARE = [".p.", "pPp", "PcP", "PcP", "cPc", "PcP", ".k."]
INK = {"p": FLAME[2], "P": FLAME[3], "c": FLAME[5], "k": NIGHT[0]}
HEART = [".ee.ee.", "eEeeeee", "eeeeeer", ".eeeer.", "..eer..", "...r..."]
HEART_INK = {"e": CRIMSON[4], "E": CRIMSON[6], "r": CRIMSON[2]}


def grid_at(im, x, y, rows, ink):
    for yy, row in enumerate(rows):
        for xx, ch in enumerate(row):
            if ch != ".":
                put(im, x + xx, y + yy, ink[ch])


def niche(im):
    """The pointed niche behind: shadow inside, a stone surround lit on its right."""
    for y in range(2, FLOOR):
        for x in range(8, 62):
            spring = 22
            inside = y >= spring or (math.hypot(x - (8 + 43), y - spring) <= 43 and math.hypot(x - (61 - 43), y - spring) <= 43)
            if not inside:
                continue
            edge = not (y >= spring and 11 <= x <= 58) and not (
                math.hypot(x - 51, y - spring) <= 40 and math.hypot(x - 18, y - spring) <= 40 and y > 5)
            if edge or x in (8, 9, 10, 59, 60, 61):
                put(im, x, y, STONE[4] if x > 35 else STONE[2])
            else:
                put(im, x, y, NIGHT[1] if y < 40 else NIGHT[2])
    # a few courses in the surround, a moonlit rim on the right
    for y in range(24, FLOOR, 5):
        hline(im, 8, 11, y, NIGHT[0])
        hline(im, 58, 62, y, STONE[2])
    for y in range(2, FLOOR):
        for x in range(61, 34, -1):
            if get(im, x, y)[3]:
                put(im, x, y, MOON[0])
                break


def floor(im):
    rect(im, 0, FLOOR, W, H, STONE[2])
    hline(im, 0, W, FLOOR, STONE[4])
    for x in range(0, W, 9):
        vline(im, x, FLOOR + 1, H, STONE[1])
    hline(im, 0, W, H - 2, STONE[1])


def altar(im):
    """A stone altar, a crimson cloth with a gold hem hanging over its front."""
    rect(im, 16, 44, 55, FLOOR, STONE[3])
    vline(im, 54, 44, FLOOR, STONE[5])
    vline(im, 16, 44, FLOOR, STONE[1])
    rect(im, 14, 42, 57, 45, STONE[4])  # the mensa
    hline(im, 14, 57, 42, STONE[6])
    for x in range(18, 54):  # the cloth, folds and a gold hem
        low = 53 + (1 if (x // 4) % 2 else 0)
        for y in range(45, low):
            put(im, x, y, CRIMSON[2] if (x % 4) else CRIMSON[1])
        put(im, x, low, GOLD[3] if x % 2 else GOLD[2])
    put(im, 53, 46, CRIMSON[3])


def reliquary(im, lit=False):
    """The heart relic at the altar's foot: a gold box, a crystal front, a heart inside."""
    x0, y0 = 30, 54
    rect(im, x0, y0, x0 + 11, FLOOR, GOLD[2])
    hline(im, x0, x0 + 11, y0, GOLD[4])
    vline(im, x0 + 10, y0, FLOOR, GOLD[4])
    rect(im, x0 + 2, y0 + 2, x0 + 9, FLOOR - 1, NIGHT[0])
    grid_at(im, x0 + 2, y0 + 2, [".e.e.", "eEeee", ".eee.", "..r.."][:FLOOR - 1 - y0 - 2],
            {"e": CRIMSON[5] if lit else CRIMSON[4], "E": CRIMSON[6], "r": CRIMSON[2]})
    put(im, x0 + 8, y0 + 2, MOON[3])  # a glint on the crystal
    put(im, x0 + 5, y0 - 1, GOLD[4])  # a finial
    put(im, x0 + 5, y0 - 2, GOLD[5])


def candelabrum(im):
    """Gold: a foot on the altar, a knopped stem, two curved arms, three cups."""
    rect(im, 31, 40, 41, 42, GOLD[2])  # the foot
    hline(im, 31, 41, 40, GOLD[4])
    rect(im, 33, 38, 39, 40, GOLD[3])
    for y in range(26, 38):  # the stem, a knop
        put(im, 35, y, GOLD[3])
        put(im, 36, y, GOLD[4])
    rect(im, 34, 31, 38, 33, GOLD[3])
    put(im, 37, 31, GOLD[5])
    for side in (-1, 1):  # the arms, curving up to the outer cups
        for i in range(12):
            x = 36 + side * (1 + i)
            y = 38 - round(3.4 * (i / 11) ** 0.7)
            put(im, x, y, GOLD[4] if side > 0 else GOLD[3])
            put(im, x, y + 1, GOLD[2])
    for cx, top in CANDLES:  # cups (drip pans)
        cup = top + 7
        hline(im, cx - 1, cx + 4, cup, GOLD[3])
        put(im, cx + 3, cup, GOLD[5])
        hline(im, cx, cx + 3, cup + 1, GOLD[2])


def candle(im, cx, top, flame=None, state="lit"):
    """A candle of wax from `top` to its cup; its flame, or its fate under the whip."""
    if state in ("lit", "flare"):
        rect(im, cx, top, cx + 3, top + 7, BONE[4])
        vline(im, cx, top, top + 7, BONE[2])
        vline(im, cx + 2, top + 1, top + 7, BONE[5])
        put(im, cx + 3, top + 3, BONE[4])  # a drip over the lip
        if state == "lit":
            grid_at(im, cx, top - 5, FLICKER[flame % 4], INK)
        else:
            grid_at(im, cx, top - 7, FLARE, INK)
    elif state == "burst":
        rect(im, cx, top + 5, cx + 3, top + 7, BONE[3])
        for dx, dy, c in ((1, -1, FLAME[5]), (0, -2, FLAME[4]), (2, -2, FLAME[4]), (-2, -1, BONE[4]),
                          (4, -3, BONE[4]), (-1, -5, FLAME[3]), (3, -6, FLAME[3]), (1, -4, FLAME[5]),
                          (-3, 2, BONE[3]), (5, 1, BONE[3])):
            put(im, cx + 1 + dx, top + 2 + dy, c)
    else:  # a stub, smoking
        rect(im, cx, top + 5, cx + 3, top + 7, BONE[2])
        if state == "smoke":
            for dx, dy in ((1, 3), (2, 2), (1, 0)):
                put(im, cx + dx, top + dy, STONE[5])


def scene(flame=0, state="lit", heart_y=None, lit_relic=False):
    im = new(W, H)
    niche(im)
    floor(im)
    altar(im)
    reliquary(im, lit_relic)
    candelabrum(im)
    for i, (cx, top) in enumerate(CANDLES):
        candle(im, cx, top, flame + i, state)
    if heart_y is not None:  # the dropped heart
        grid_at(im, 32, heart_y, HEART, HEART_INK)
    outline(im, NIGHT[0])
    return im


def strip(frames):
    w, h = frames[0].size
    out = new(w * len(frames), h)
    for i, fr in enumerate(frames):
        paste(out, fr, i * w, 0)
    return out


def idle():
    return strip([scene(f) for f in range(4)])


def whip():
    """Flare, burst, a heart falls from the candelabrum onto the altar, bounces, rests."""
    return strip([
        scene(0, "flare"),
        scene(0, "burst"),
        scene(0, "smoke", heart_y=20),
        scene(0, "smoke", heart_y=28),
        scene(0, "stub", heart_y=36, lit_relic=True),
        scene(0, "stub", heart_y=32, lit_relic=True),
        scene(0, "stub", heart_y=36, lit_relic=True),
        scene(0, "stub", heart_y=36, lit_relic=True),
    ])


def heart():
    """One of the few hearts that fly (the burst), 5 × 4."""
    im = new(5, 4)
    grid_at(im, 0, 0, [".e.e.", "eEeee", ".eee.", "..r.."], HEART_INK)
    return im
