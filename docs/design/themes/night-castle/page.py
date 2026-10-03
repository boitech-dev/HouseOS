"""The page's parallax (the heart of the theme), back to front:
  sky.png         page.backdrop: the night, stars, the dusk low on the horizon (1602 × 900)
  far-castle.png  layer, natural bottom-right, depth .15: the huge moon, the castle on its crag
  clouds.png      layer, repeat-x drift: flat SNES clouds sliding over the moon
  terrace.png     layer, repeat-x bottom, depth .45: the balustrade we stand behind
  bats.png        layer (hero.py), crossing now and then
All native, shown × 3; the moon (up-right) lights every right edge."""
import math

from lib import dith, disc, get, hline, new, noise, poly, put, rect, save, stars, vgrad, vline
from palette import BONE, CRIMSON, DUSK, FLAME, GOLD, MOON, MOSS, NIGHT, STONE


def sky():
    w, h = 534, 300
    im = new(w, h)
    vgrad(im, (0, 0, w, h), [NIGHT[0], NIGHT[1], NIGHT[1], NIGHT[2], NIGHT[3], NIGHT[4], DUSK[0], DUSK[1]])
    stars(im, (0, 0, w, 170), 11, 0.004, [MOON[1], MOON[0], NIGHT[6], BONE[2]])
    stars(im, (0, 0, w, 90), 12, 0.0015, [MOON[3], BONE[4]])
    rnd = noise(4)
    for _ in range(9):
        x, y = rnd.randrange(8, w - 8), rnd.randrange(6, 120)
        put(im, x, y, MOON[4])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            put(im, x + dx, y + dy, MOON[0])
    # the far mountains, barely there
    pts = [(0, 262)]
    for x in range(0, w + 12, 12):
        pts.append((x, 262 - 16 * abs(math.sin(x / 57.0)) - 9 * abs(math.sin(x / 23.0 + 1))))
    pts += [(w, 300), (0, 300)]
    poly(im, pts, NIGHT[2])
    for x in range(w):
        for y in range(220, 300):
            if get(im, x, y)[:3] == (0x18, 0x10, 0x28) and get(im, x, y - 1)[:3] != (0x18, 0x10, 0x28):
                put(im, x, y, NIGHT[3])
                break
    return im


def far_castle():
    """The moon, huge, and the castle on its crag: distant, so violet and low in contrast."""
    w, h = 180, 240
    im = new(w, h)
    cx, cy, r = 108, 62, 36
    for y in range(cy - r - 8, cy + r + 9):
        for x in range(cx - r - 8, cx + r + 9):
            d = math.hypot(x - cx, y - cy)
            if r < d <= r + 3:
                put(im, x, y, NIGHT[5] if dith(0.8, x, y) else NIGHT[4])
            elif r + 3 < d <= r + 8 and dith((r + 8 - d) / 5 * 0.5, x, y):
                put(im, x, y, NIGHT[4])
    disc(im, cx, cy, r, MOON[2])  # a far, veiled moon: quieter than the hero's
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if math.hypot(x - cx, y - cy) > r:
                continue
            if math.hypot(x - cx - 8, y - cy + 10) > r + 2:
                put(im, x, y, MOON[1])
            if math.hypot(x - cx - 8, y - cy + 10) > r + 7:
                put(im, x, y, MOON[0])
    # maria: irregular seas (unions of offset blobs), flat clusters in one step darker
    for group in (((-12, -8, 7), (-6, -3, 6), (-16, -1, 5)), ((6, 7, 8), (12, 12, 6), (2, 14, 5)),
                  ((13, -15, 4), (17, -11, 3)), ((-5, 22, 4),)):
        for mx, my, mr in group:
            for y in range(cy + my - mr, cy + my + mr + 1):
                for x in range(cx + mx - mr, cx + mx + mr + 1):
                    if math.hypot(x - cx - mx, (y - cy - my) * 1.2) <= mr and math.hypot(x - cx, y - cy) < r - 1:
                        c = get(im, x, y)[:3]
                        put(im, x, y, MOON[1] if c == (0xb8, 0xc0, 0xd0) else MOON[0])
    for kx, ky in ((-20, -18), (4, -26), (22, 4), (-24, 14), (18, 20)):  # small craters, lit rims
        put(im, cx + kx, cy + ky, MOON[0])
        put(im, cx + kx + 1, cy + ky - 1, MOON[3])
    # the crag: faceted, moonlit on its right planes
    crag = [(20, 240), (30, 206), (44, 186), (52, 170), (66, 160), (150, 158), (160, 170), (172, 190),
            (180, 200), (180, 240)]
    poly(im, crag, NIGHT[1])
    for pts, c in (([(66, 160), (100, 160), (88, 184), (52, 176)], NIGHT[2]),
                   ([(120, 158), (150, 158), (160, 170), (150, 186), (124, 178)], NIGHT[2]),
                   ([(160, 170), (172, 190), (180, 200), (180, 240), (164, 214), (150, 186)], NIGHT[3]),
                   ([(88, 184), (124, 178), (150, 186), (164, 214), (120, 220), (96, 206)], NIGHT[2]),
                   ([(30, 206), (52, 176), (88, 184), (96, 206), (60, 222)], NIGHT[2])):
        poly(im, pts, c)
    # the castle: a skyline of towers, one dark silhouette against the dusk, rimmed by the moon
    body = NIGHT[1]
    towers = [  # x0, x1, top, roof height
        (56, 66, 128, 12), (70, 78, 108, 18), (82, 100, 94, 0), (86, 92, 80, 16), (104, 112, 118, 14),
        (116, 130, 102, 24), (134, 142, 122, 12), (146, 156, 134, 12),
    ]
    rect(im, 50, 140, 164, 162, body)
    for i in range(50, 164, 4):  # battlements on the curtain wall
        rect(im, i, 137, i + 2, 140, body)
    for x0, x1, top, rh in towers:
        rect(im, x0, top, x1, 162, body)
        if rh:
            mid = (x0 + x1 - 1) / 2
            poly(im, [(x0 - 1, top), (x1, top), (mid + 0.5, top - rh)], body)
            put(im, int(mid + 0.5), top - rh - 1, GOLD[2])
            for y in range(top - rh + 1, top):  # the roof's lit right slope
                t = (y - (top - rh)) / rh
                put(im, int(mid + 0.5 + t * (x1 - x0) / 2), y, NIGHT[5])
        else:
            for i in range(x0, x1, 3):
                rect(im, i, top - 2, i + 2, top, body)
        vline(im, x1 - 1, top, 162, NIGHT[4])  # the moon on their right faces
        put(im, x1 - 1, top, NIGHT[5])
    hline(im, 50, 164, 140, NIGHT[3])
    # a crimson flag on the tallest, and lit windows, dim with distance
    for i, hgt in enumerate((3, 3, 2, 1)):
        vline(im, 122 - i, 76 + (1 if i > 1 else 0), 76 + hgt, CRIMSON[3] if i else CRIMSON[4])
    for x, y in ((73, 116), (73, 124), (88, 90), (90, 104), (95, 104), (91, 120), (107, 126), (121, 112),
                 (125, 112), (123, 132), (137, 130), (150, 142), (61, 138), (99, 146), (59, 150), (129, 148)):
        put(im, x, y, GOLD[4] if (x + y) % 3 else FLAME[2])
        put(im, x, y + 1, GOLD[2])
    # the road winding up the crag, a line of torches
    for k, (x, y) in enumerate(((40, 226), (52, 214), (66, 204), (80, 196), (96, 190), (112, 184),
                                (126, 176), (136, 168))):
        put(im, x, y, NIGHT[4])
        put(im, x + 1, y, NIGHT[4])
        if k % 2 == 0:
            put(im, x, y - 1, FLAME[2])
    return im


def clouds():
    """Flat night clouds with a lit upper lip, in a tile that loops; rows at the moon's height
    (the tile and the far castle both sit on the bottom, so they line up)."""
    w, h = 256, 240
    im = new(w, h)

    def cloud(x0, length, y, th, seed):
        rnd = noise(seed)
        bumps = [(rnd.uniform(0, 1), rnd.uniform(0.5, 1)) for _ in range(4)]
        for i in range(length):
            x = (x0 + i) % w
            t = i / length
            half = th * math.sin(t * math.pi) ** 0.6
            for p, a in bumps:
                half += th * 0.6 * a * math.exp(-((t - p) * 7) ** 2)
            top, bot = int(y - half), int(y + half * 0.45)
            for yy in range(top, bot + 1):
                put(im, x, yy, NIGHT[3])
            put(im, x, top, NIGHT[5])
            put(im, x, top + 1, NIGHT[4])
            put(im, x, bot, NIGHT[2])

    cloud(10, 96, 70, 4, 1)
    cloud(140, 70, 86, 3, 2)
    cloud(200, 110, 48, 3, 3)
    cloud(80, 50, 104, 2, 4)
    return im


def terrace():
    """The balustrade in front of us: dark stone, a moonlit rim, ivy, a pedestal with an urn."""
    w, h = 192, 60
    im = new(w, h)
    rail_top, base = 26, 50
    # coping and plinth
    rect(im, 0, rail_top, w, rail_top + 4, STONE[2])
    hline(im, 0, w, rail_top, STONE[5])
    hline(im, 0, w, rail_top + 3, STONE[0])
    rect(im, 0, base, w, h, STONE[1])
    hline(im, 0, w, base, STONE[4])
    # balusters: vase-shaped, every 8 px, one missing (a ruin)
    profile = [3, 2, 2, 2, 1, 1, 2, 2, 3, 3, 3, 3, 2, 2, 3, 3]
    for bx in range(4, w, 8):
        if bx in (100, 108):
            continue
        for i, hw in enumerate(profile):
            y = rail_top + 4 + i
            if y >= base:
                break
            for dx in range(-hw, hw + 1):
                c = STONE[2] if dx < hw else STONE[4]
                if dx <= -hw + 1 and hw > 1:
                    c = STONE[1]
                put(im, bx + dx, y, c)
        for y in range(rail_top + 4 + len(profile), base):
            hline(im, bx - 2, bx + 3, y, STONE[2])
            put(im, bx + 2, y, STONE[5])
    # a broken baluster lying there
    rect(im, 101, base - 3, 110, base, STONE[2])
    hline(im, 101, 110, base - 3, STONE[5])
    # the pedestal and its urn
    px = 160
    rect(im, px - 9, 14, px + 10, h, STONE[2])
    vline(im, px + 9, 14, h, MOON[0])
    vline(im, px - 9, 14, h, STONE[0])
    hline(im, px - 10, px + 11, 14, STONE[5])
    hline(im, px - 10, px + 11, 15, STONE[1])
    for y in range(20, 48, 5):
        hline(im, px - 8, px + 9, y, STONE[1])
    urn = [4, 6, 7, 7, 6, 4, 3, 2, 4, 5]
    for i, hw in enumerate(urn):
        y = 4 + i
        for dx in range(-hw, hw + 1):
            put(im, px + dx, y, STONE[5] if dx > hw - 2 else (STONE[1] if dx < -hw + 2 else STONE[3]))
    hline(im, px - 5, px + 6, 3, STONE[5])
    # ivy over the coping and down the pedestal
    rnd = noise(9)
    for x in range(120, 176):
        n = int(3 + 3 * math.sin(x / 5) + rnd.random() * 3)
        for y in range(rail_top - 1, rail_top - 1 + n):
            if rnd.random() < 0.7:
                put(im, x, y, MOSS[0] if rnd.random() < 0.5 else MOSS[1])
    for y in range(16, 44):
        for x in range(px - 9, px - 4):
            if rnd.random() < 0.35 * (1 - (y - 16) / 40):
                put(im, x, y, MOSS[0] if rnd.random() < 0.6 else MOSS[1])
    # a candle stub on the coping, never lit (it is only stone here)
    return im


if __name__ == "__main__":
    save(sky(), "sky.png", scale=3)
    save(far_castle(), "far-castle.png", scale=1)
    save(clouds(), "clouds.png", scale=1)
    save(terrace(), "terrace.png", scale=1)
    print("page written")
