"""The fixed pictures: the crest (sign-in), the empty state, the TV's gilded frame, My Space's
chamber, the rail's stained-glass window. Native, saved × 3 (the crest shows at 96 px = 32 × 3)."""
import math

from lib import dith, disc, get, hline, new, noise, outline, paste, poly, put, rect, save, vline
from palette import BONE, CRIMSON, FLAME, GLASS, GOLD, MOON, MOSS, NIGHT, STONE


def crest():
    """The castle's arms: a crimson shield, a gold cross, bat wings spread behind it, a small
    crown of spikes. 32 × 32, light from the upper right."""
    im = new(32, 32)
    # wings: membranes between four finger bones, scalloped trailing edge; the right one moonlit
    W = (10, 9)
    tips = [(0, 9), (1, 16), (4, 20), (9, 21)]
    scallops = [(3, 13), (5, 17), (8, 18)]
    outline_pts = [W, (5, 5), (2, 6), tips[0], scallops[0], tips[1], scallops[1], tips[2], scallops[2], tips[3], (11, 19)]
    for side in (-1, 1):
        mirror = (lambda p: (p[0], p[1])) if side < 0 else (lambda p: (31 - p[0], p[1]))
        poly(im, [mirror(p) for p in outline_pts], NIGHT[4] if side < 0 else NIGHT[5])
        for t in tips:
            x0, y0 = mirror(W)
            x1, y1 = mirror(t)
            n = max(abs(x1 - x0), abs(y1 - y0))
            for i in range(n + 1):
                put(im, round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n), NIGHT[6] if side > 0 else NIGHT[5])
        for p in scallops:
            x, y = mirror(p)
            put(im, x, y - 1, CRIMSON[1])
        x, y = mirror((4, 5))
        put(im, x, y, NIGHT[6] if side > 0 else NIGHT[5])  # the wing's thumb claw
    # the shield
    for y in range(7, 28):
        half = 7 if y < 19 else int(7 - (y - 19) * 0.85)
        for x in range(16 - half, 16 + half):
            c = CRIMSON[3] if x < 16 else CRIMSON[4]
            put(im, x, y, c)
        if half > 0:
            put(im, 16 - half, y, GOLD[2])
            put(im, 16 + half - 1, y, GOLD[4])
    hline(im, 9, 23, 7, GOLD[5])
    hline(im, 9, 23, 8, GOLD[3])
    # the cross, gold, lit on its right
    for y in range(10, 24):
        put(im, 15, y, GOLD[4])
        put(im, 16, y, GOLD[5])
    for x in range(11, 21):
        put(im, x, 14, GOLD[4])
        put(im, x, 15, GOLD[3])
    put(im, 16, 14, GOLD[6])
    # a glint on the shield's upper right
    put(im, 21, 10, CRIMSON[6])
    put(im, 20, 9, CRIMSON[5])
    # a crown of three spikes
    for x, h in ((11, 3), (16, 5), (21, 3)):
        vline(im, x, 7 - h, 7, GOLD[3])
        put(im, x, 7 - h - 1, CRIMSON[5])
    hline(im, 10, 23, 6, GOLD[4])
    outline(im, NIGHT[0])
    return im


def empty():
    """An empty state: a candle in an iron sconce, and a little bat asleep under it, upside down
    (the smile). 32 × 32."""
    im = new(32, 32)
    # the wall plate
    rect(im, 13, 8, 19, 26, STONE[3])
    vline(im, 18, 8, 26, STONE[5])
    vline(im, 13, 8, 26, STONE[1])
    put(im, 16, 10, NIGHT[0])
    put(im, 16, 23, NIGHT[0])
    # the arm and the dish
    for x in range(16, 23):
        put(im, x, 18 - (x - 16) // 3, NIGHT[0])
        put(im, x, 17 - (x - 16) // 3, STONE[4])
    hline(im, 19, 28, 16, GOLD[3])
    hline(im, 20, 27, 17, GOLD[2])
    put(im, 27, 16, GOLD[5])
    # the candle, drips of wax
    rect(im, 22, 7, 26, 16, BONE[4])
    vline(im, 22, 7, 16, BONE[2])
    vline(im, 25, 7, 16, BONE[5])
    put(im, 23, 7, BONE[5])
    put(im, 22, 10, BONE[3])
    put(im, 21, 11, BONE[4])
    put(im, 26, 12, BONE[4])
    # the flame
    for dx, dy, c in ((1, -1, FLAME[2]), (2, -1, FLAME[3]), (1, -2, FLAME[3]), (2, -2, FLAME[4]), (2, -3, FLAME[4]),
                      (1, -3, FLAME[3]), (2, -4, FLAME[3]), (2, -5, FLAME[2]), (1, 0, NIGHT[0]), (2, 0, NIGHT[0])):
        put(im, 22 + dx, 7 + dy, c)
    # warm light on the wall plate
    for y in range(4, 14):
        for x in range(13, 19):
            if get(im, x, y)[3] and dith(0.4 - abs(y - 8) * 0.05, x, y):
                put(im, x, y, GOLD[2])
    # the bat asleep, hanging from the arm by its feet
    bat = [
        "..k.k..",
        "..kkk..",
        ".kkkkk.",
        "kkkkkkk",
        "kkwkwkk",
        ".kkkkk.",
        "..krk..",
        "...k...",
    ]
    for y, row in enumerate(bat):
        for x, ch in enumerate(row):
            if ch == "k":
                put(im, 15 + x, 19 + y, NIGHT[2] if x < 3 else NIGHT[4])
            elif ch == "w":
                put(im, 15 + x, 19 + y, BONE[3])  # closed eyes, a line each
            elif ch == "r":
                put(im, 15 + x, 19 + y, CRIMSON[4])  # a tiny tongue: asleep, smiling
    outline(im, NIGHT[0])
    return im


def bezel():
    """The TV as a gilded frame on the castle wall: 54 × 40, a dark screen with the moon in it."""
    w, h = 54, 40
    im = new(w, h)
    for y in range(h):
        for x in range(w):
            d = min(x, y, w - 1 - x, h - 1 - y)
            lit = x > w - 1 - y or (y < 3 and x > 3)  # top and right face the moon
            if d == 0:
                c = NIGHT[0]
            elif d < 5:
                c = [GOLD[4], GOLD[3], GOLD[2], GOLD[3]][d - 1] if lit else [GOLD[3], GOLD[2], GOLD[1], GOLD[2]][d - 1]
                if d == 2 and (x + y) % 4 == 0:
                    c = GOLD[5] if lit else GOLD[3]  # beading
            elif d == 5:
                c = NIGHT[0]
            else:
                c = NIGHT[1]
            put(im, x, y, c)
    # corner scrolls
    for cx, cy in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)):
        disc(im, cx, cy, 2, GOLD[4])
        put(im, cx, cy, CRIMSON[4])
    # a crest at the top centre
    poly(im, [(w // 2 - 4, 0), (w // 2 + 4, 0), (w // 2, 4)], GOLD[4])
    put(im, w // 2, 1, CRIMSON[5])
    # the screen: night, the moon, a far tower
    for y in range(6, h - 6):
        for x in range(6, w - 6):
            if dith((y - 6) / (h - 12) * 0.7, x, y):
                put(im, x, y, NIGHT[2])
    disc(im, 36, 14, 5, MOON[3])
    disc(im, 37, 13, 4, MOON[4])
    rect(im, 14, 20, 20, 34, NIGHT[0])
    poly(im, [(13, 20), (21, 20), (17, 13)], NIGHT[0])
    put(im, 17, 25, FLAME[3])
    poly(im, [(6, 34), (20, 30), (34, 32), (48, 29), (48, 34)], NIGHT[0])
    return im


def chamber():
    """My Space: a castle bedchamber at night. A four-poster in crimson, a pointed window with the
    moon, its light on the floor; a desk, a candle, a book; the fire in a stone hearth, its light
    in bands on the flags; a coffin standing in the corner, lid ajar. 134 × 60 (× 3 ≈ 400 × 180).
    Two lights: the moon from the window (cold, left of centre), the fire (warm, right)."""
    w, h = 134, 60
    im = new(w, h, NIGHT[1])
    rnd = noise(12)
    FLOOR = 46
    # wall: ashlar, a little warmer toward the fire
    for y in range(0, FLOOR):
        for x in range(w):
            c = STONE[2]
            if y % 6 == 5 or (x + (y // 6) * 5) % 11 == 0:
                c = STONE[1]
            elif y % 6 == 0 and (x * 7 + y) % 5 < 2:
                c = STONE[3]
            put(im, x, y, c)
    # a dark band of shadow under the ceiling and a cornice
    rect(im, 0, 0, w, 3, NIGHT[1])
    hline(im, 0, w, 3, STONE[4])
    hline(im, 0, w, 4, NIGHT[0])
    # floor: flagstones in rows, joints darker
    for y in range(FLOOR, h):
        for x in range(w):
            row = (y - FLOOR) // 4
            c = STONE[1]
            if (y - FLOOR) % 4 == 3 or (x + row * 7) % 14 == 0:
                c = NIGHT[0]
            elif (y - FLOOR) % 4 == 0:
                c = STONE[2]
            put(im, x, y, c)
    hline(im, 0, w, FLOOR, STONE[4])  # skirting
    hline(im, 0, w, FLOOR - 1, STONE[1])

    # --- the fire's light on the floor: banded ellipses, no dither ---
    fx, fy = 101, 48
    for y in range(FLOOR + 1, h):
        for x in range(76, 128):
            d = math.hypot((x - fx) / 26, (y - fy) / 11)
            if d > 1 or get(im, x, y)[:3] == (0x08, 0x00, 0x10):
                continue
            put(im, x, y, FLAME[1] if d < 0.3 else (GOLD[2] if d < 0.6 else GOLD[1]))

    # --- the window: pointed, the moon in the night, leaded ---
    wx0, wx1, top = 50, 64, 7
    for y in range(top - 2, 32):
        for x in range(wx0 - 2, wx1 + 3):
            if pointed(x, y, wx0 - 2, wx1 + 2, top + 6):
                put(im, x, y, STONE[3] if x > (wx0 + wx1) // 2 else STONE[1])
    for y in range(top, 30):
        for x in range(wx0, wx1 + 1):
            if pointed(x, y, wx0, wx1, top + 6):
                put(im, x, y, NIGHT[2] if y < 14 else (NIGHT[3] if y < 22 else NIGHT[4]))
    disc(im, 59, 15, 3.4, MOON[3])
    disc(im, 59.6, 14.6, 2.4, MOON[4])
    put(im, 58, 16, MOON[2])
    put(im, 53, 11, MOON[2])
    put(im, 55, 22, MOON[1])
    vline(im, 57, top + 1, 30, NIGHT[0])
    hline(im, wx0, wx1 + 1, 19, NIGHT[0])
    rect(im, wx0 - 3, 30, wx1 + 4, 32, STONE[5])
    hline(im, wx0 - 3, wx1 + 4, 32, STONE[1])
    # moonlight falling onto the floor: a pale lozenge in two steps
    for y in range(FLOOR + 1, h):
        t = y - FLOOR
        a, b = 44 + t, 58 + t
        for x in range(a, b):
            if get(im, x, y)[:3] in ((0x10, 0x10, 0x20), (0x18, 0x18, 0x30)):
                put(im, x, y, STONE[3] if a + 2 < x < b - 2 else STONE[2])

    # --- the bed: a four-poster, crimson hangings, gold fringe ---
    rect(im, 3, 6, 45, 9, CRIMSON[2])  # the tester's valance
    hline(im, 3, 45, 6, CRIMSON[4])
    for x in range(3, 45):
        if x % 2 == 0:
            put(im, x, 9, GOLD[3])
    for x0 in (3, 42):  # posts, turned
        rect(im, x0, 6, x0 + 3, FLOOR + 1, GOLD[1])
        vline(im, x0 + 2, 6, FLOOR + 1, GOLD[3])
        for y in (14, 28, 40):
            hline(im, x0 - 1, x0 + 4, y, GOLD[2])
            put(im, x0 + 3, y, GOLD[4])
        put(im, x0 + 1, 5, GOLD[4])
        put(im, x0 + 1, 4, GOLD[5])
    # the curtain drawn back on the left: folds in three shades
    for y in range(10, FLOOR - 2):
        width = 8 - max(0, (y - 26) // 3) + max(0, (y - 36))
        for x in range(6, 6 + max(3, width)):
            k = (x - 6 + (y // 5)) % 4
            put(im, x, y, [CRIMSON[1], CRIMSON[2], CRIMSON[3], CRIMSON[2]][k])
    hline(im, 6, 12, 27, GOLD[3])  # the tie-back
    # headboard, dark wood with a carved arch
    rect(im, 6, 16, 42, 30, NIGHT[0])
    rect(im, 7, 17, 41, 30, GOLD[0])
    for x in range(10, 39):
        y = 20 - int(3 * math.sin((x - 10) / 29 * math.pi))
        put(im, x, y, GOLD[1])
    # mattress and quilt
    rect(im, 6, 30, 42, 38, BONE[2])
    hline(im, 6, 42, 30, BONE[3])
    for x0 in (10, 22):  # two pillows, lit from the window on their right
        rect(im, x0, 27, x0 + 9, 32, BONE[3])
        hline(im, x0 + 1, x0 + 8, 27, BONE[4])
        vline(im, x0 + 8, 28, 32, BONE[4])
        vline(im, x0, 28, 32, BONE[1])
    rect(im, 6, 33, 43, 42, CRIMSON[2])  # the quilt, falling over the side
    hline(im, 6, 43, 33, CRIMSON[4])
    for y in range(35, 42, 3):
        for x in range(8 + (y % 2) * 2, 42, 5):
            put(im, x, y, GOLD[2])
    rect(im, 6, 42, 43, 44, CRIMSON[1])
    hline(im, 6, 43, 44, GOLD[2])

    # --- the rug ---
    rect(im, 40, 50, 92, 58, CRIMSON[1])
    rect(im, 42, 51, 90, 57, CRIMSON[2])
    for x in range(42, 90, 3):
        put(im, x, 51, GOLD[2])
        put(im, x + 1, 56, GOLD[1])
    for cx in (56, 76):
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0), (0, 0)):
            put(im, cx + dx, 54 + dy, GOLD[3] if (dx, dy) != (0, 0) else CRIMSON[4])

    # --- the desk under the window's light: a book, a candle, a skull ---
    rect(im, 68, 34, 86, 36, GOLD[1])
    hline(im, 68, 86, 34, GOLD[2])
    for x in (69, 84):
        rect(im, x, 36, x + 2, FLOOR + 1, GOLD[0])
        put(im, x + 1, 38, GOLD[1])
    rect(im, 71, 31, 78, 34, CRIMSON[3])  # a closed book, gold edges
    hline(im, 71, 78, 31, CRIMSON[4])
    hline(im, 71, 78, 33, BONE[3])
    rect(im, 82, 27, 84, 34, BONE[4])  # the candle
    vline(im, 82, 27, 34, BONE[2])
    put(im, 83, 26, FLAME[3])
    put(im, 83, 25, FLAME[4])
    put(im, 82, 26, FLAME[2])
    disc(im, 79.5, 31.5, 1.6, BONE[3])  # a small skull
    put(im, 79, 31, NIGHT[0])
    put(im, 80, 31, NIGHT[0])

    # --- the hearth ---
    rect(im, 88, 16, 116, FLOOR + 1, STONE[3])
    for y in range(16, FLOOR + 1):
        put(im, 115, y, STONE[5])
        put(im, 88, y, STONE[1])
        if (y - 16) % 5 == 4:
            hline(im, 89, 115, y, STONE[2])
    rect(im, 86, 14, 118, 17, STONE[4])  # the mantel
    hline(im, 86, 118, 14, STONE[6])
    hline(im, 86, 118, 17, NIGHT[0])
    # the firebox: a pointed opening, black at the back
    for y in range(22, FLOOR + 1):
        for x in range(93, 111):
            if pointed(x, y, 93, 110, 28):
                put(im, x, y, NIGHT[0])
    # logs
    rect(im, 95, 43, 109, 45, GOLD[0])
    hline(im, 95, 109, 43, GOLD[1])
    # flames: tongues in bands, hottest at the heart
    for x in range(95, 109):
        hgt = 10 + int(5 * math.sin((x - 95) * 0.9) * math.sin((x - 93) / 16 * math.pi)) + (3 if x in (100, 101, 102) else 0)
        for y in range(43 - hgt, 43):
            t = (43 - y) / max(1, hgt)
            core = abs(x - 101.5) < 4 - t * 3
            c = FLAME[1] if t > 0.75 else (FLAME[2] if t > 0.45 else (FLAME[3] if not core else FLAME[4]))
            put(im, x, y, c)
    # the mantel's things: a candle, a small portrait
    rect(im, 90, 9, 92, 14, BONE[4])
    put(im, 91, 8, FLAME[3])
    put(im, 91, 7, FLAME[4])
    rect(im, 104, 6, 112, 14, GOLD[2])
    rect(im, 105, 7, 111, 13, NIGHT[2])
    disc(im, 108, 9.5, 1.5, BONE[1])
    hline(im, 104, 112, 6, GOLD[4])

    # --- the coffin, standing in the corner, lid ajar ---
    body = [(119, 20), (125, 16), (131, 16), (133, 22), (133, 46), (121, 46)]
    lid = [(117, 22), (122, 18), (127, 19), (126, 47), (116, 45)]
    poly(im, body, NIGHT[0])
    poly(im, [(120, 21), (125, 17), (130, 17), (132, 22), (132, 45), (122, 45)], CRIMSON[3])  # satin lining
    for y in range(22, 45, 3):
        hline(im, 124, 132, y, CRIMSON[4])  # tufts
    poly(im, lid, GOLD[0])
    for pts, c in (([(118, 22), (122, 19), (126, 20), (125, 46), (117, 44)], GOLD[1]),):
        poly(im, pts, c)
    # the lid's cross and its moonlit edge
    vline(im, 121, 25, 38, GOLD[4])
    hline(im, 119, 124, 29, GOLD[4])
    for y in range(19, 47):
        x = int(126 - (y - 19) * 0.04)
        put(im, x, y, GOLD[2])
    hline(im, 116, 134, FLOOR, STONE[4])
    return im


def pointed(x, y, x0, x1, spring):
    """Inside a pointed (equilateral-ish) arch spanning x0..x1 whose curve starts at `spring`."""
    if y >= spring:
        return x0 <= x <= x1
    w = x1 - x0 + 1
    r = w * 0.8
    return math.hypot(x - (x0 + r - 0.5), y - spring) <= r and math.hypot(x - (x1 + 0.5 - r), y - spring) <= r


if __name__ == "__main__":
    save(crest(), "crest.png")
    save(empty(), "empty-sconce.png")
    save(bezel(), "tv-frame.png")
    save(chamber(), "chamber.png")
    print("slots written")
