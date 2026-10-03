"""Home's hero: the chapter picture without its title. A flying staircase on pointed arches climbs
out of the mist to the keep's open gate; torches along it; a dead tree on the right. The sky is
left clear: the hero's layers put the night, the moon and the bats behind it.
Native 240 × 90, saved × 3. The moon (a layer) sits up-right: every rim light is on the right."""
import math

from lib import (ART, disc, dith, fade_alpha, get, hline, new, noise, paste, poly, put, rect, save,
                 stars, vgrad, vline)
from palette import BONE, CRIMSON, DUSK, FLAME, GOLD, MOON, MOSS, NIGHT, STONE

W, H = 240, 90
RIM, RIM2 = MOON[1], MOON[0]


def blocks(im, x0, y0, x1, y1, base, dark, light=None, seed=1, bw=6, bh=3):
    """Ashlar: a face of stone blocks, mortar in `dark`, a lit top row per block in `light`."""
    rnd = noise(seed)
    for y in range(y0, y1):
        row = (y - y0) // bh
        off = (row % 2) * (bw // 2)
        for x in range(x0, x1):
            if get(im, x, y)[3] == 0:
                continue
            c = base
            if (y - y0) % bh == bh - 1:
                c = dark
            elif (x - x0 + off) % bw == 0:
                c = dark
            elif light and (y - y0) % bh == 0 and rnd.random() < 0.55:
                c = light
            put(im, x, y, c)


def silhouette_fill(im, pts, c):
    poly(im, pts, c)


def roof(im, x0, x1, base_y, apex_y, dark, mid, lit, rim):
    """A pointed cone roof: dark on the left, lit on the right, a gold finial."""
    mid_x = (x0 + x1) / 2
    for y in range(apex_y, base_y + 1):
        t = (y - apex_y) / max(1, base_y - apex_y)
        half = t * (x1 - x0) / 2 + 0.5
        a, b = int(round(mid_x - half)), int(round(mid_x + half))
        for x in range(a, b + 1):
            u = (x - a) / max(1, b - a)
            c = dark if u < 0.45 else (mid if u < 0.8 else lit)
            if (y - apex_y) % 3 == 2 and u > 0.2:  # tile courses
                c = dark if u < 0.8 else mid
            put(im, x, y, c)
        put(im, b, y, rim)
    # eaves: a lip one pixel wider
    hline(im, x0 - 1, x1 + 2, base_y + 1, dark)
    put(im, x1 + 1, base_y + 1, rim)
    vline(im, int(mid_x), apex_y - 3, apex_y, GOLD[3])
    put(im, int(mid_x), apex_y - 4, GOLD[5])


def tower(im, x0, x1, top, bottom, seed):
    rect(im, x0, top, x1, bottom, STONE[3])
    blocks(im, x0, top, x1, bottom, STONE[3], STONE[1], STONE[4], seed)
    w = x1 - x0
    # moon on the right face: the last third lit, the left third in shadow
    for y in range(top, bottom):
        for x in range(x0, x1):
            u = (x - x0) / w
            c = get(im, x, y)
            if u < 0.3 and c[:3] != tuple(int(STONE[1][i:i + 2], 16) for i in (1, 3, 5)):
                put(im, x, y, STONE[2] if dith(0.7, x, y) else STONE[3])
            elif u > 0.78 and (y - top) % 3 != 2:
                put(im, x, y, STONE[5] if not dith(0.3, x, y) else STONE[4])
        put(im, x1 - 1, y, RIM)
        put(im, x0, y, STONE[1])
    # a string course and machicolations under the top
    hline(im, x0 - 1, x1 + 1, top, STONE[1])
    hline(im, x0 - 1, x1 + 1, top + 1, STONE[4])
    put(im, x1, top + 1, RIM)
    for x in range(x0, x1, 3):
        put(im, x, top + 2, NIGHT[0])


def window(im, x, y, lit=True, tall=4):
    """A lancet: 3 wide, pointed top; lit windows glow."""
    if lit:
        core, edge = FLAME[3], FLAME[2]
    else:
        core, edge = NIGHT[0], NIGHT[1]
    put(im, x + 1, y, edge)
    for yy in range(y + 1, y + tall):
        put(im, x, yy, edge)
        put(im, x + 1, yy, core)
        put(im, x + 2, yy, edge)
    hline(im, x - 1, x + 4, y + tall, STONE[1])  # sill shadow
    if lit:
        put(im, x + 1, y + 1, FLAME[4])


def battlements(im, x0, x1, y, c, rim=None, step=5, merlon=3, h=2):
    for x in range(x0, x1):
        if (x - x0) % step < merlon:
            for yy in range(y - h, y):
                put(im, x, yy, c)
            if rim and (x - x0) % step == merlon - 1:
                vline(im, x, y - h, y, rim)


def torch(im, x, y, frame=0):
    """A brazier on a post, lit: post from y down 6 px, bowl, flame."""
    vline(im, x, y, y + 7, NIGHT[0])
    put(im, x + 1, y + 2, STONE[4])
    hline(im, x - 1, x + 2, y, GOLD[2])
    put(im, x + 1, y, GOLD[4])
    flames = [
        [(0, -1, FLAME[3]), (0, -2, FLAME[4]), (-1, -1, FLAME[2]), (1, -1, FLAME[2]), (0, -3, FLAME[2])],
        [(0, -1, FLAME[3]), (0, -2, FLAME[3]), (1, -2, FLAME[2]), (-1, -1, FLAME[2]), (1, -3, FLAME[1])],
    ][frame % 2]
    for dx, dy, c in flames:
        put(im, x + dx, y + dy, c)


def glow(im, cx, cy, r, colours, only_opaque=True):
    """Warm light on nearby stone: dithered rings of the flame's colours over what is there."""
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            d = math.hypot(x - cx, y - cy) / r
            if d > 1 or (only_opaque and get(im, x, y)[3] == 0):
                continue
            c = get(im, x, y)
            if c[:3] in {tuple(int(k[i:i + 2], 16) for i in (1, 3, 5)) for k in FLAME}:
                continue
            i = min(len(colours) - 1, int(d * len(colours)))
            if dith(1 - d * 0.9, x, y):
                put(im, x, y, colours[i])


def arch_opening(im, x0, x1, top, bottom):
    """A pointed arch cut out of the masonry (clear: the sky shows through)."""
    w = x1 - x0
    r = w * 0.8
    for y in range(top, bottom):
        for x in range(x0, x1):
            # two circles meeting at a point: the gothic arch
            spring = top + w * 0.7
            if y >= spring:
                inside = True
            else:
                inside = (math.hypot(x - (x0 + r), y - spring) <= r + 0.2) and (
                    math.hypot(x - (x1 - 1 - r), y - spring) <= r + 0.2)
            if inside:
                put(im, x, y, None)
    # voussoir rim: the lit right edge of the opening's left jamb stays dark; the arch's inner
    # left edge catches the moon


def glow_soft(im, cx, cy, r, near, far):
    """Firelight on stone: a sparse dither of warm colours on opaque pixels only."""
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            d = math.hypot(x - cx, (y - cy) * 1.3) / r
            c = get(im, x, y)
            if d > 1 or not c[3] or c[:3] in WARM:
                continue
            if dith((1 - d) * 0.45, x, y):
                put(im, x, y, near if d < 0.5 else far)


WARM = {tuple(int(k[i:i + 2], 16) for i in (1, 3, 5)) for k in FLAME + GOLD}


def stair_y(x):
    """The treads' height at x: 10 steps of 4 up, 10 across, from (24, 90) to the gate sill."""
    i = max(0, min(10, (x - 24) // 10))
    return 90 - 4 * (i + 1)


def make():
    im = new(W, H)
    rnd = noise(7)

    # --- far ridge with a ruined watchtower: violet, the air between us and it ------------------
    ridge = [(0, 72), (10, 68), (22, 70), (34, 63), (46, 66), (58, 60), (70, 63), (84, 57), (100, 60),
             (116, 58), (116, 90), (0, 90)]
    poly(im, ridge, NIGHT[3])
    rect(im, 60, 44, 66, 61, NIGHT[3])  # the far tower, broken at the top
    for x, h in ((60, 44), (61, 42), (62, 43), (63, 45), (64, 44), (65, 46)):
        vline(im, x, h, 61, NIGHT[3])
    put(im, 62, 50, FLAME[1])  # one far window, still lit
    for x in range(0, 116):
        for y in range(40, 90):
            if get(im, x, y)[3] and not get(im, x, y - 1)[3]:
                put(im, x, y, NIGHT[4])
                if not get(im, x + 1, y - 1)[3] and get(im, x + 1, y)[3] is not None:
                    pass

    # --- the crag under the keep: big faceted rock, the right planes in moonlight ---------------
    crag = [(116, 90), (118, 74), (122, 64), (128, 56), (192, 56), (198, 62), (204, 70), (202, 78),
            (210, 90)]
    poly(im, crag, STONE[1])
    facets = [
        ([(128, 56), (150, 56), (140, 70), (124, 66)], STONE[2]),
        ([(150, 56), (176, 56), (170, 72), (140, 70)], STONE[2]),
        ([(176, 56), (192, 56), (198, 62), (190, 74), (170, 72)], STONE[3]),
        ([(190, 74), (198, 62), (204, 70), (202, 78)], STONE[4]),
        ([(140, 70), (170, 72), (164, 86), (134, 84)], STONE[1]),
        ([(170, 72), (190, 74), (202, 78), (196, 88), (164, 86)], STONE[3]),
    ]
    for pts, c in facets:
        poly(im, pts, c)
    for y in range(54, 90):
        for x in range(114, 214):
            c = get(im, x, y)
            if c[3] and not get(im, x + 1, y)[3]:
                put(im, x, y, RIM)  # moon on the crag's right edge
            elif c[3] and not get(im, x, y - 1)[3]:
                put(im, x, y, STONE[4])
    for k in range(14):  # cracks: short diagonals, a lit pixel under each
        x, y = 124 + (k * 37) % 76, 60 + (k * 23) % 26
        for t in range(3 + k % 3):
            if get(im, x + t, y + t // 2)[3]:
                put(im, x + t, y + t // 2, NIGHT[1])
                if get(im, x + t, y + t // 2 + 1)[3]:
                    put(im, x + t, y + t // 2 + 1, STONE[4])
    for x in range(128, 192):  # moss and grass along the lip
        if rnd.random() < 0.55:
            put(im, x, 56, MOSS[2] if rnd.random() < 0.6 else MOSS[3])
        if rnd.random() < 0.25:
            put(im, x, 57, MOSS[1])

    # --- the keep ---------------------------------------------------------------------------
    rect(im, 124, 38, 196, 57, STONE[3])  # the curtain wall
    blocks(im, 124, 38, 196, 57, STONE[3], STONE[2], STONE[4], 3, bw=7)
    battlements(im, 124, 196, 38, STONE[3], RIM2)
    hline(im, 124, 196, 38, STONE[5])
    vline(im, 195, 36, 57, RIM)
    hline(im, 124, 196, 56, STONE[1])
    tower(im, 126, 138, 20, 57, 11)  # left tower
    battlements(im, 125, 139, 20, STONE[3], RIM2, step=4, merlon=2)
    roof(im, 125, 138, 16, 5, NIGHT[1], STONE[2], STONE[4], RIM)
    tower(im, 146, 170, 19, 57, 12)  # the great keep: battlemented, a spire turret at its corner
    battlements(im, 145, 171, 19, STONE[3], RIM2, step=4, merlon=2, h=3)
    tower(im, 163, 170, 14, 22, 14)
    roof(im, 162, 170, 12, 5, NIGHT[1], STONE[2], STONE[4], RIM)
    # a crimson pennant on the spire, blowing away from the moon
    for i, h in enumerate((3, 3, 2, 2, 1, 1)):
        for yy in range(h):
            put(im, 165 - i - 1, 2 + yy + (1 if i > 3 else 0), CRIMSON[4] if yy else CRIMSON[5])
    tower(im, 178, 190, 24, 57, 13)  # right turret
    roof(im, 177, 190, 21, 10, NIGHT[1], STONE[2], STONE[4], RIM)
    poly(im, [(170, 30), (178, 36), (178, 57), (170, 57)], STONE[2])  # a buttress
    vline(im, 177, 36, 57, STONE[4])
    window(im, 131, 26, lit=True)
    window(im, 131, 40, lit=False)
    window(im, 150, 24, lit=True, tall=7)
    window(im, 157, 24, lit=True, tall=7)
    window(im, 153, 38, lit=False, tall=5)
    window(im, 162, 42, lit=True)
    window(im, 182, 30, lit=False)
    window(im, 182, 42, lit=True)
    # a stained-glass rose over the gate: one pane of each colour, a glint
    disc(im, 164, 32, 2.3, STONE[1])
    for dx, dy, c in ((0, 0, GOLD[5]), (-1, 0, CRIMSON[5]), (1, 0, CRIMSON[5]), (0, -1, "#3868d0"),
                      (0, 1, "#3868d0")):
        put(im, 164 + dx, 32 + dy, c)
    # the gate, open at the top of the stair, candlelight inside, the portcullis raised
    gx0, gx1 = 131, 141
    for y in range(38, 53):
        for x in range(gx0, gx1 + 1):
            d = abs(x - (gx0 + gx1) / 2)
            if y >= 38 + d * 1.2:
                inner = d < 4 and y > 39 + d * 1.2
                if not inner:
                    put(im, x, y, STONE[5] if x > (gx0 + gx1) / 2 else STONE[1])  # voussoirs
                else:
                    put(im, x, y, NIGHT[0] if y < 44 else (CRIMSON[1] if y < 48 else (CRIMSON[2] if y < 50 else FLAME[1])))
    for x in range(gx0 + 2, gx1 - 1, 2):
        put(im, x, 44, STONE[1])
        put(im, x, 45, STONE[1])  # the portcullis's teeth, raised
    hline(im, gx0 + 2, gx1 - 1, 51, FLAME[2])
    for x in range(gx0 - 4, gx1 + 5):  # light spilling onto the landing
        if dith(1 - abs(x - 136) / 9, x, 52):
            put(im, x, 52, GOLD[4])
    glow_soft(im, 136, 50, 6, GOLD[2], GOLD[1])

    # --- the flying stair ---------------------------------------------------------------------
    # masonry under the stair: from the treads down to the ground, then arches cut out of it
    for x in range(20, 134):
        ty = stair_y(x) if x < 130 else 52
        for y in range(ty, 90):
            put(im, x, y, STONE[3])
    # arches between piers (the sky shows through them)
    piers = [(20, 25), (48, 54), (78, 84), (108, 114)]
    for (a0, a1), (b0, b1) in zip(piers, piers[1:]):
        top = stair_y(b0) + 7
        arch_opening(im, a1, b0, top, 90)
    # after cutting: shade the masonry: courses, moonlit right edges of piers, dark left edges
    for x in range(20, 134):
        for y in range(40, 90):
            c = get(im, x, y)
            if not c[3] or c[:3] != (0x20, 0x28, 0x38):
                continue
            if y % 4 == 3 or (x + (y // 4) * 5) % 10 == 0:
                put(im, x, y, STONE[2])
            if not get(im, x + 1, y)[3]:
                put(im, x, y, RIM2)
            elif not get(im, x - 1, y)[3]:
                put(im, x, y, STONE[1])
            elif not get(im, x, y + 1)[3]:
                put(im, x, y, STONE[1])  # the arch's soffit in shadow
    # the stringer: a moulding under the treads
    for x in range(20, 130):
        ty = stair_y(x)
        put(im, x, ty + 4, STONE[1])
        put(im, x, ty + 5, STONE[4])
    # treads and risers
    for i in range(11):
        x0 = 24 + 10 * i - 10 if i else 20
        x1 = 24 + 10 * i
        ty = 90 - 4 * (i + 1) if i < 11 else 52
        for x in range(max(20, 24 + 10 * (i - 1)), min(130, 24 + 10 * i)):
            pass
    for x in range(20, 130):
        ty = stair_y(x)
        put(im, x, ty, STONE[7])  # tread nose, lit
        put(im, x, ty + 1, STONE[5])
        if (x - 24) % 10 == 0 and x > 24:  # riser: the step up is one step back
            for y in range(ty, ty + 4):
                put(im, x - 1, y, STONE[4])
            put(im, x - 1, ty + 3, STONE[2])
    # the landing before the gate
    hline(im, 124, 142, 52, STONE[7])
    hline(im, 124, 142, 53, STONE[5])
    # a balustrade along the near edge: handrail on balusters, parallel to the flight
    def rail_y(x):
        return 90 - 4 - (x - 24) * 0.4 - 5

    for x in range(22, 128):
        ry = int(round(rail_y(x)))
        put(im, x, ry, STONE[6])
        put(im, x, ry - 1, STONE[8] if x % 2 else STONE[7])
        if x % 3 == 0:
            for y in range(ry + 1, stair_y(x)):
                put(im, x, y, STONE[4])
    # newel posts with gold caps, and braziers on three of them
    for x in (26, 66, 106):
        ry = int(round(rail_y(x)))
        rect(im, x - 1, ry - 3, x + 2, stair_y(x), STONE[4])
        vline(im, x + 1, ry - 3, stair_y(x), RIM2)
        hline(im, x - 1, x + 2, ry - 3, GOLD[3])
        put(im, x + 1, ry - 3, GOLD[5])
    for x in (66, 106):
        ry = int(round(rail_y(x))) - 4
        for dx, dy, c in ((0, -1, FLAME[3]), (0, -2, FLAME[4]), (-1, -1, FLAME[2]), (1, -1, FLAME[2]),
                          (0, -3, FLAME[2]), (0, 0, GOLD[4]), (-1, 0, GOLD[2]), (1, 0, GOLD[2])):
            put(im, x + dx, ry + dy, c)
        glow_soft(im, x, ry, 6, GOLD[2], GOLD[1])

    # --- the dead tree, right: a silhouette the moon can sit behind ------------------------------
    def branch(x, y, ang, length, width, depth):
        for s in range(int(length)):
            xx = x + math.cos(ang) * s
            yy = y - math.sin(ang) * s
            for w in range(-int(width // 2), int(width - width // 2)):
                put(im, xx + w, yy, NIGHT[0])
            if width >= 3:
                put(im, xx + width // 2, yy, STONE[2])  # moonlight on the trunk's right side
        if depth > 0:
            ex, ey = x + math.cos(ang) * length, y - math.sin(ang) * length
            branch(ex, ey, ang + 0.5 + rnd.random() * 0.25, length * 0.6, max(1, width - 1), depth - 1)
            branch(ex, ey, ang - 0.42 - rnd.random() * 0.25, length * 0.72, max(1, width - 1), depth - 1)

    branch(226, 90, math.pi / 2 + 0.1, 28, 4, 4)
    poly(im, [(204, 90), (208, 84), (218, 82), (232, 83), (240, 80), (240, 90)], NIGHT[1])
    hline(im, 208, 240, 83, STONE[2])

    # --- the gargoyle on the first newel (a discovery): a winged, horned watcher ----------------
    g = [
        "k..............",
        "kk.............",
        "kSk.......kk...",
        "kSSk.....k.k...",
        "kSSSk...kSSk...",
        ".kSSSk.kSsSSk..",
        ".kSSSSkSsSrSk..",
        "..kSSSSSsSSSSkk",
        "...kSSSSSSSSSSk",
        "....kSSSSSSSkk.",
        "....kSSSSSSSk..",
        "...kSSkSSkSSk..",
        "...kkk.kk.kkk..",
    ]
    leg = {"k": NIGHT[0], "S": STONE[4], "s": STONE[6], "r": CRIMSON[5]}
    for yy, row in enumerate(g):
        for xx, ch in enumerate(row):
            if ch != ".":
                put(im, 5 + xx, 63 + yy, leg[ch])
    rect(im, 8, 76, 20, 90, STONE[3])  # its pedestal
    vline(im, 19, 76, 90, RIM2)
    hline(im, 7, 21, 76, STONE[6])
    hline(im, 7, 21, 77, STONE[2])

    # --- mist along the bottom, and a lick of it through the arches ------------------------
    for y in range(74, 90):
        t = (y - 74) / 16
        for x in range(0, W):
            wave = math.sin(x / 9 + y / 4) * 0.2
            if dith(min(1, t * 0.95 + wave), x, y):
                put(im, x, y, NIGHT[4] if (x // 3 + y) % 4 else NIGHT[5])
    return im


def sky():
    """The hero's sky layer, native 240 × 86, shown × 3 at the hero's top-right: the night
    gradient down to the dusk, the moon high on the right (inside a phone's 112 px band too),
    stars; dithered out to the left and bottom."""
    w, h = 240, 86
    im = new(w, h)
    vgrad(im, (0, 0, w, h), [NIGHT[1], NIGHT[2], NIGHT[3], NIGHT[4], DUSK[0], DUSK[1]])
    stars(im, (0, 0, w, 60), 3, 0.01, [MOON[2], MOON[1], NIGHT[6], BONE[3]])
    for x, y in ((40, 12), (110, 20), (88, 6), (150, 36)):
        put(im, x, y, MOON[4])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            put(im, x + dx, y + dy, MOON[1])
    cx, cy, r = 200, 19, 14
    for y in range(cy - r - 5, cy + r + 6):
        for x in range(cx - r - 5, cx + r + 6):
            d = math.hypot(x - cx, y - cy)
            if r < d <= r + 2:
                put(im, x, y, NIGHT[6] if dith(0.75, x, y) else NIGHT[5])
            elif r + 2 < d <= r + 4 and dith((r + 4 - d) / 2 * 0.5, x, y):
                put(im, x, y, NIGHT[5])
    disc(im, cx, cy, r, MOON[4])
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if math.hypot(x - cx, y - cy) > r:
                continue
            lx, ly = x - (cx + 4), y - (cy - 4)  # the shadow side: a disc offset toward the light
            if math.hypot(lx, ly) > r + 1:
                put(im, x, y, MOON[3])
            if math.hypot(lx, ly) > r + 3.5:
                put(im, x, y, MOON[2])
    for mx, my, mr, c in ((-5, -3, 4, MOON[3]), (3, 3, 4, MOON[3]), (-2, 8, 2, MOON[2]),
                          (6, -7, 2, MOON[3]), (-8, 3, 2, MOON[2]), (3, 3, 2, MOON[2])):
        disc(im, cx + mx, cy + my, mr, c)
    for kx, ky in ((-9, -4), (1, -10), (8, 7), (-4, 10), (10, -2)):
        put(im, cx + kx, cy + ky, MOON[2])
        put(im, cx + kx + 1, cy + ky - 1, MOON[4])
    for y in range(cy - r - 1, cy + r + 2):
        for x in range(cx - r - 1, cx + r + 2):
            d = math.hypot(x - cx, y - cy)
            if r - 1 < d <= r and (x - cx) * 0.6 - (y - cy) * 0.8 < 0:
                put(im, x, y, MOON[2])

    def streak(x0, x1, y, th):
        for x in range(x0, x1):
            t = (x - x0) / (x1 - x0)
            half = th * math.sin(t * math.pi) ** 0.7
            top, bot = int(y - half), int(y + half * 0.6)
            for yy in range(top, bot + 1):
                put(im, x, yy, NIGHT[5])
            put(im, x, top, NIGHT[6] if math.hypot(x - cx, top - cy) > r else MOON[1])
            put(im, x, bot, NIGHT[4])

    streak(176, 236, cy + 8, 2)
    streak(160, 200, cy + 14, 2)
    fade_alpha(im, left=90, bottom=20)
    return im


def bats():
    """Three bats in formation, 2 frames (wings up, wings down): a strip for frames + cross."""
    up = [
        "k.........k",
        "kk.......kk",
        "kkk.k.k.kkk",
        ".kkkkkkkkk.",
        "..kkkrkkk..",
        "....kkk....",
    ]
    down = [
        "...........",
        "....k.k....",
        "..kkkkkkk..",
        ".kkkkrkkkk.",
        "kkk.kkk.kkk",
        "k.........k",
    ]
    small_up = ["k.....k", "kk.k.kk", ".kkkkk.", "..krk..", "...k..."]
    small_down = [".......", "..k.k..", ".kkkkk.", "kkkrkkk", "k.....k"]
    fw, fh = 40, 22
    frames = []
    for f in range(2):
        im = new(fw, fh)
        for (rows, ox, oy) in ((up if f == 0 else down, 2, 4), (small_down if f == 0 else small_up, 20, 1),
                              (small_up if f == 0 else small_down, 30, 12)):
            for yy, row in enumerate(rows):
                for xx, ch in enumerate(row):
                    if ch == "k":
                        put(im, ox + xx, oy + yy, NIGHT[0])
                    elif ch == "r":
                        put(im, ox + xx, oy + yy, CRIMSON[5])
        frames.append(im)
    strip = new(fw * 2, fh)
    for i, fr in enumerate(frames):
        paste(strip, fr, i * fw, 0)
    return strip


def preview(scale=3):
    """For looking only: the hero over its sky, as the app stacks them (not shipped)."""
    s, h = sky(), make()
    out = new(240, 100, NIGHT[1])
    paste(out, s, 0, 0)
    paste(out, h, 0, 10)
    from PIL import Image
    return out.resize((240 * scale, 100 * scale), Image.NEAREST)


if __name__ == "__main__":
    save(make(), "hero-keep.png", scale=1)
    save(sky(), "hero-sky.png", scale=1)
    save(bats(), "bats.png", scale=1)
    preview().save("/tmp/claude-1000/-storage-projects-houseos/c2f33739-800d-4beb-a1d2-3bb184e4e102/scratchpad/hero-preview.png")
    print("hero written")


GARGOYLE = [  # perched at the hero's lower right, facing into the scene (left); moon on its back
    "....................",
    "....................",
    "....................",
    "......k.k...........",
    ".....kSkSk..........",
    "....kSSSSSk.....kk..",
    "...kSrSSSSSk...kdSk.",
    "..kSSSSSSSSk..kddSk.",
    "..kkSSkSSSSSkkdddSk.",
    "...kSSkSSSSSSddddSk.",
    "....kkSSSSsSSdddSk..",
    "......kSSSsSSSSSSk..",
    ".....kSSkSSSSkSSk...",
    "...kkkkkkkkkkkkkkkk.",
    "...kLLLLLLLLLLLLLmk.",
    "...kkkkkkkkkkkkkkkk.",
]
WINGS_UP = [(r, c) for r, row in enumerate([
    "..............k....",
    ".............kdk...",
    "............kdddk..",
    "...........kddddSk.",
    "..........kdddddSk.",
]) for c, ch in enumerate(row) if ch != "."]


def gargoyle_frame(eye=0, wings=False, jaw=False):
    legend = {"k": NIGHT[0], "S": STONE[4], "s": STONE[6], "d": STONE[2], "L": STONE[3], "m": STONE[5],
              "r": [CRIMSON[3], CRIMSON[5], CRIMSON[6]][eye]}
    im = new(20, 16)
    for y, row in enumerate(GARGOYLE):
        for x, ch in enumerate(row):
            if ch != ".":
                put(im, x, y, legend[ch])
    # the moon on its back: a rim down the right side of the body
    for y in range(4, 13):
        for x in range(19, 0, -1):
            c = get(im, x, y)
            if c[3] and c[:3] != (8, 0, 16):
                put(im, x, y, STONE[6] if y < 10 else STONE[5])
                break
    if wings:
        for r, c in WINGS_UP:
            ch = "..............k....|.............kdk...|............kdddk..|...........kddddSk.|..........kdddddSk.".split("|")[r][c]
            put(im, c, r + 1, legend[ch])
    if eye == 2:
        put(im, 4, 6, CRIMSON[4])  # the glow spills
        put(im, 5, 5, CRIMSON[3])
    if jaw:
        put(im, 2, 8, NIGHT[0])
        put(im, 3, 8, CRIMSON[2])
        put(im, 2, 9, STONE[4])
        put(im, 3, 9, BONE[4])  # a fang
    return im


def gargoyle():
    return gargoyle_frame()


def gargoyle_wake():
    """The poke: its eye kindles, it opens its wings and hisses, and settles again."""
    frames = [gargoyle_frame(1), gargoyle_frame(2), gargoyle_frame(2, wings=True), gargoyle_frame(2, True, True),
              gargoyle_frame(2, True, True), gargoyle_frame(2, True), gargoyle_frame(1)]
    out = new(20 * len(frames), 16)
    for i, fr in enumerate(frames):
        paste(out, fr, i * 20, 0)
    return out


def tiny_bat():
    im = new(5, 3)
    for x, y in ((0, 0), (4, 0), (1, 1), (3, 1), (2, 2), (0, 1), (4, 1)):
        put(im, x, y, NIGHT[5])  # wings catching the moon, so they read on the night
    put(im, 2, 1, NIGHT[0])
    put(im, 2, 0, CRIMSON[4])
    return im
