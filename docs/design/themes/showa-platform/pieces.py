"""The smaller pictures: moving pieces (railcar is in scenes), the name boards over each room,
the vending machine at the rail's foot, the crest, the empty bench, the waiting-room TV, and
the frames (panels, sheets, the Now bar's ticket, the dock's platform edge, the rail's wall)."""

import math

from px import _grain, LINES, Cv, rnd
from scenes import wheel_emblem

# ---------------------------------------------------------------- moving pieces


def dragonfly(frame):
    """A red dragonfly, flying left; two wing beats."""
    cv = Cv(12, 6)
    wings = (["..w..w......", ".ww.ww......"], [".w..w.......", "..ww.ww....."])[frame]
    cv.sprite(wings, {"w": "k4"}, 1, 0)
    cv.sprite(["kr..........", "krrrrrrrrrr.", "k...........", ], {"k": "r0", "r": "r2"}, 0, 2)
    cv.px(1, 2, "r3")
    wl = (["..w..w......", ".ww.ww......"], [".w..w.......", "..ww.ww....."])[1 - frame]
    for j, row in enumerate(wl):
        for i, ch in enumerate(row):
            if ch == "w":
                cv.px(1 + i, 4 + j, "w2")
    return cv


def furin(frame):
    """8 × 30: a glass wind bell hung from the deck frame's top-right corner (over the frame's
    edge, clear of the player's menu): a short string, the bell with a red goldfish band, the
    clapper, a long cream paper strip that catches the breeze. 4 frames; it only sways while
    music plays."""
    cv = Cv(8, 30)
    sway = (0, 1, 0, -1)[frame]
    cv.vline(4, 0, 4, "t3")
    bell = [
        "..kkk..",
        ".kwwwk.",
        "kwhwwwk",
        "kwrrrwk",
        "kwwwwwk",
        "kkkkkkk",
    ]
    cv.sprite(bell, {"k": "n1", "w": "k4", "h": "c0", "r": "r2"}, 1, 4)
    cv.vline(4 + (sway > 0) - (sway < 0), 10, 13, "t3")
    cv.px(4, 11, "y2")
    for j in range(15):
        ox = 2 + round((j + 2) / 17 * sway * 2)
        c = "r2" if j >= 13 else "c0"
        cv.hline(ox, ox + 4, 13 + j, c)
        cv.px(ox + 3, 13 + j, "c3" if c == "c0" else "r1")
    return cv


# ---------------------------------------------------------------- the name boards (header.banner)

BADGE = {  # 10 × 10 colour pictograms for each room's badge, after the room.* marks
    "listen": ["........k.", ".......k..", "kkkkkkkkkk", "kiiiiiiiik", "kiCkCkiPPk", "kiCkCkiPek", "kiCkCkiPPk", "kiiiiiiiik", "kkkkkkkkkk", ".k......k."],
    "watch": [".k....k...", "..k..k....", "kkkkkkkkkk", "kimmmmmkik", "kimPmmmkPk", "kimmmmmkik", "kigggggkPk", "kigggggkik", "kkkkkkkkkk", ".k......k."],
    "games": ["....kk....", "....kk....", "..kkkkkk..", ".kppppppk.", "kpeeeeeepk", "knnnnnnnnk", ".kPPPPPPk.", "..kCCCCk..", "...kCCk...", "....kk...."],
    "house": ["kkkkkkkkkk", "kiiiiiiiik", "kiPPiPPPik", "kiPeiPkPik", "kiPPiPPPik", "kiiiiiiiik", "kiPPPiPPik", "kiPkPiPgik", "kiiiiiiiik", "kkkkkkkkkk"],
    "files": ["...kkkk...", "...k..k...", "kkkkkkkkkk", "kvvkvvkvvk", "kvvkvvkvvk", "kkkkppkkkk", "kvvkvvkvvk", "kvvkvvkvvk", "kkkkkkkkkk", ".k......k."],
    "ask": ["k........k", "kk......kk", "kvkkkkkkvk", "kvvvvvvvvk", "kvkkvvkkvk", "kvkPvvkPvk", "kvvvPPvvvk", ".kvPePPvk.", "..kkkkkk..", ".........."],
    "me": ["..........", "...kkkk...", ".kknnnnkk.", "knnnkpknnk", "knnnnnnnnk", "kkkkkkkkkk", "keeeeeeeek", ".kkkkkkkk.", "..kkkkkk..", ".........."],
    "control": ["kk....kk..", "kek..kgk..", ".kek.kk...", "..kekk....", "...kkk....", "kkkkkkkkkk", "kllllllllk", "klkklkklkk", "kkkkkkkkkk", ".........."],
    "smart-home": ["..kkkkk...", "..kgggk...", "..kgPgk...", "..kgggk...", "..knnnk...", "..knknk...", "..kkkkk...", "....kl....", "....kl....", "..kkkkkk.."],
    "inbox": ["..........", "kkkkkkkkkk", "kkPPPPPPkk", "kPkPPPPkPk", "kPPkPPkPPk", "kPPPkkPPPk", "kPPPPPPPPk", "kPPPPPPePk", "kkkkkkkkkk", ".........."],
    "party": ["...kkkk...", "..kkkkkk..", ".keeeeeek.", "kePeeeeeek", "kerrrrrrek", "keeeeeeeek", "kerrrrrrek", ".keeeeeek.", "..kkkkkk..", "...k..k..."],
}
BADGE_INK = {"k": "n1", "e": "r2", "r": "r1", "P": "c0", "C": "c3", "i": "b2", "m": "k2", "p": "y2",
             "g": "g2", "v": "o1", "n": "n2", "l": "t1"}


def board(room):
    """800 × 80: the top of a station-name board, all of it within the 32 px above the title.
    A navy rim, a thick band in the room's line colour (lit edge, shaded edge), the room's badge
    at the centre, arrows to the neighbouring stations, screws; below, white enamel where the
    title sits, fading into the platform."""
    W, H = 800, 80
    cv = Cv(W, H)
    line = "L-" + room
    if room == "space":  # the office picture sits right above the title on phones: keep clear
        return cv
    cv.hline(0, W, 0, "n0")
    cv.hline(0, W, 1, "n2")
    cv.hline(0, W, 2, "n1")
    cv.rect(0, 3, W, 14, line)
    cv.hline(0, W, 3, "c0/90")   # the band's lit upper edge
    cv.hline(0, W, 12, "n0/70")  # its shaded lower edge
    cv.hline(0, W, 13, "n0/110")
    cv.hline(0, W, 14, "n1")
    cv.hline(0, W, 15, "n0/70")
    # screws holding the board, and a chip in the enamel near one of them
    for sx in (W // 2 - 300, W // 2 + 300, W // 2 - 110, W // 2 + 110):
        cv.sprite(["hC.", "Ctl", ".lt"], {"h": "c0", "C": "c3", "t": "t0", "l": "t1"}, sx, 6)
    cv.sprite(["nn", "nt", ".b"], {"n": "n0", "t": "t0", "b": "b1"}, W // 2 + 304, 9)
    # arrows to the neighbouring stations: white enamel, navy edge
    arrow = [
        "....kk..............",
        "...kPk..............",
        "..kPPkkkkkkkkkkkkkk.",
        ".kPPPPPPPPPPPPPPPPk.",
        "..kPPkkkkkkkkkkkkkk.",
        "...kPk..............",
        "....kk..............",
    ]
    for ax, flip in ((W // 2 - 196, False), (W // 2 + 176, True)):
        cv.sprite(arrow, {"k": "n1", "P": "c0"}, ax, 5, flip=flip)
    # the badge, 14 across, the room's pictogram in colour
    cx, cy = W // 2 - 0.5, 7.5
    cv.disc(cx, cy, 7.2, "n1")
    cv.disc(cx, cy, 6.2, "c0")
    for j, row in enumerate(BADGE.get(room, BADGE["listen"])):
        for i, ch in enumerate(row):
            x, y = W // 2 - 5 + i, 3 + j
            if ch != "." and (x + 0.5 - cx - 0.5) ** 2 + (y + 0.5 - cy - 0.5) ** 2 < 6.4 ** 2:
                cv.px(x, y, BADGE_INK[ch])
    return cv


# ---------------------------------------------------------------- the rail's foot


def vending(pressed=None, can=0, lit=False):
    """104 × 112: the platform's drinks machine glowing, a crate of empties, a sunflower in a
    pot, on a strip of platform floor. For the poke: `pressed` lights one selection button,
    `can` 1 = a can falling behind the flap (the clunk), 2 = the can waiting in the tray,
    `lit` = the sign flickers brighter."""
    W, H = 104, 112
    cv = Cv(W, H)
    floor = 100
    cv.rect(0, floor, W, H, "c2")
    cv.hline(0, W, floor, "c3")
    cv.hline(0, W, floor + 5, "c0")
    for x in range(W):
        for y in range(floor + 6, H):
            if _grain(x, y, 13):
                cv.px(x, y, "c3")
    # the machine's glow on the floor
    for y in range(floor + 1, floor + 9):
        for x in range(26, 74):
            d = abs(x - 50) / 26 + (y - floor) / 12
            if d < 1:
                cv.dither(x, y, cv.get(x, y), "y3", (1 - d) * 0.7)
    # its light on the wall behind (a faint halo, dithered)
    mx0, mx1, my0 = 30, 70, 14
    for y in range(0, floor):
        for x in range(0, W):
            d = math.hypot((x - 50) / 34, (y - 56) / 40)  # ends inside the piece on every side
            if d < 1:
                cv.dither(x, y, cv.get(x, y), "y3/90", (1 - d) * 0.55)
    # the machine: red body, cream front, a lit window of bottles, a lit sign on top
    cv.rect(mx0, my0, mx1, floor, "r2")
    cv.vline(mx0, my0, floor, "r3")
    cv.vline(mx1 - 1, my0, floor, "r1")
    cv.vline(mx1 - 2, my0 + 2, floor, "r1")
    cv.hline(mx0, mx1, my0, "r3")
    cv.hline(mx0 - 1, mx1 + 1, floor - 1, "r0")
    # top sign box, lit from inside
    cv.rect(mx0 + 2, my0 + 2, mx1 - 3, my0 + 11, "n1")
    cv.rect(mx0 + 3, my0 + 3, mx1 - 4, my0 + 10, "y3")
    cv.rect(mx0 + 3, my0 + 8, mx1 - 4, my0 + 10, "y2")
    if lit:
        cv.rect(mx0 + 3, my0 + 3, mx1 - 4, my0 + 10, "c0")
    # its pictogram: a bottle with a marble
    bx = (mx0 + mx1) // 2 - 1
    cv.sprite([".kk.", ".kk.", "kkkk", "kcck", "kkkk", "kkkk"], {"k": "r1", "c": "c0"}, bx - 1, my0 + 3)
    # the window: three shelves of bottles
    wx0, wx1, wy0, wy1 = mx0 + 3, mx1 - 4, my0 + 14, my0 + 48
    cv.rect(wx0 - 1, wy0 - 1, wx1 + 1, wy1 + 1, "n0")
    cv.rect(wx0, wy0, wx1, wy1, "c0")
    kinds = [("p0", "k3"), ("o1", "o2"), ("k2", "k4"), ("r3", "r4"), ("g3", "g4")]
    for s, sy in enumerate((wy0 + 2, wy0 + 13, wy0 + 24)):
        cv.hline(wx0, wx1, sy + 9, "c3")
        for i, x in enumerate(range(wx0 + 2, wx1 - 2, 5)):
            a, b = kinds[(i + s * 2) % len(kinds)]
            cv.sprite([".b.", ".a.", "aba", "aaa", "aaa", "aba", "aaa"], {"a": a, "b": b}, x, sy + 2)
    cv.hline(wx0, wx1, wy0, "c1")
    for y in range(wy0, wy1, 3):  # a reflection across the glass
        cv.px(wx0 + (y - wy0) // 2, y, "w0")
    # selection buttons, coin slot, return, the tray
    for i, x in enumerate(range(wx0 + 1, wx1, 5)):
        cv.rect(x, wy1 + 3, x + 3, wy1 + 5, "c1" if i % 2 else "y2")
        if pressed == i:
            cv.rect(x, wy1 + 3, x + 3, wy1 + 5, "r4")
            cv.px(x + 1, wy1 + 4, "c0")
    cv.rect(mx1 - 11, wy1 + 9, mx1 - 5, wy1 + 20, "c1")
    cv.vline(mx1 - 8, wy1 + 11, wy1 + 15, "n0")
    cv.rect(mx1 - 10, wy1 + 17, mx1 - 6, wy1 + 19, "n1")
    cv.rect(mx0 + 4, floor - 14, mx1 - 5, floor - 5, "n0")
    cv.rect(mx0 + 5, floor - 13, mx1 - 6, floor - 6, "n1")
    cv.hline(mx0 + 5, mx1 - 6, floor - 13, "t0")
    if can == 1:  # the flap swings in, a can's rim showing: the clunk
        cv.rect(mx0 + 5, floor - 13, mx1 - 6, floor - 11, "t1")
        cv.rect(mx0 + 16, floor - 11, mx0 + 22, floor - 8, "r2")
        cv.hline(mx0 + 16, mx0 + 22, floor - 11, "t3")
        for dx, dy in ((-3, -2), (-4, 0), (26, -2), (27, 0)):  # the machine shudders
            cv.px(mx0 + 4 + dx if dx < 0 else mx0 + dx, floor - 12 + dy, "n3")
    elif can == 2:  # the can lies in the tray: red, a cream band, a steel top
        cv.rect(mx0 + 12, floor - 10, mx0 + 26, floor - 6, "r2")
        cv.hline(mx0 + 12, mx0 + 26, floor - 10, "r3")
        cv.rect(mx0 + 17, floor - 10, mx0 + 20, floor - 6, "c0")
        cv.vline(mx0 + 26, floor - 10, floor - 6, "t3")
        cv.vline(mx0 + 27, floor - 9, floor - 7, "t2")
    # a trash box for empties, a crate, a potted sunflower on the left
    cv.rect(76, floor - 20, 92, floor, "b2")
    cv.vline(76, floor - 20, floor, "b3")
    cv.vline(91, floor - 20, floor, "b1")
    for y in (floor - 20, floor - 13, floor - 6):
        cv.hline(76, 92, y, "b1")
    for x in range(78, 91, 4):
        cv.sprite(["k", "a", "a"], {"k": "t0", "a": "p0"}, x, floor - 23)
    # the potted sunflower
    cv.rect(8, floor - 10, 20, floor, "r1")
    cv.hline(7, 21, floor - 10, "r2")
    cv.vline(8, floor - 9, floor, "r2")
    cv.vline(14, 54, floor - 10, "g1")
    for ly, side in ((72, -1), (80, 1), (64, 1)):
        cv.sprite(["gg..", ".ggg", "..gG"] if side > 0 else ["..gg", "ggg.", "Gg.."], {"g": "g2", "G": "g3"},
                  14 + (1 if side > 0 else -4), ly)
    head = [
        "...yYy...",
        "..YyYyY..",
        ".yYoooYy.",
        "yYoOooOYy",
        "YyooOooyY",
        "yYoOooOYy",
        ".yYoooYy.",
        "..yYyYy..",
        "...yyy...",
    ]
    cv.sprite(head, {"y": "y2", "Y": "y3", "o": "b1", "O": "b2"}, 10, 46)
    return cv


# ---------------------------------------------------------------- the crest, the empty state, the TV


def crest():
    """80 × 80: the line's emblem, an enamel badge with a winged wheel."""
    S = 80
    cv = Cv(S, S)
    c = S / 2 - 0.5
    cv.disc(c, c, 38, "n0")
    cv.disc(c, c, 37, "n2")
    cv.disc(c, c, 32, "c0")
    cv.disc(c, c, 31, "c1")
    cv.ring(c, c, 29, "n2", 1)
    # an enamel gleam on the rim, top left
    for a in range(200, 260, 3):
        ang = math.radians(a)
        cv.px(round(c + 35 * math.cos(ang)), round(c + 35 * math.sin(ang)), "n3")
    # rivets on the rim
    for a in range(0, 360, 45):
        ang = math.radians(a + 22.5)
        x, y = round(c + 34.5 * math.cos(ang)), round(c + 34.5 * math.sin(ang))
        cv.px(x, y, "c3")
        cv.px(x + 1, y + 1, "n0")
    # rails converging under the wheel
    for y in range(52, 66):
        t = (y - 52) / 14
        for s in (-1, 1):
            cv.px(round(c + s * (3 + t * 12)), y, "n3")
    for y in range(55, 66, 3):
        t = (y - 52) / 14
        cv.hline(round(c - 4 - t * 13), round(c + 5 + t * 13), y, "c3")
    # wings: three clean rows of feathers each side, the top row longest, lit from the left
    for side in (-1, 1):
        for k, (dy, reach, lift) in enumerate(((-7, 30, 6), (-1, 25, 4), (5, 19, 2))):
            for x in range(9, reach + 1):
                t = (x - 9) / (reach - 9)
                top = round(c + dy - lift * t)
                thick = 4 if x < reach - 2 else 3 - (x - (reach - 2))
                for j in range(max(1, thick)):
                    col = "n1" if j == thick - 1 else ("n3" if j == 0 and side < 0 else "n2")
                    cv.px(round(c + side * x), top + j, col)
            # the feather ends: small notches every 4 px on the lower edge
            for x in range(12, reach - 2, 4):
                t = (x - 9) / (reach - 9)
                cv.px(round(c + side * x), round(c + dy - lift * t) + 4, "n1")
    # the wheel: rim, spokes, a red hub
    cv.disc(c, c, 11, "n1")
    cv.disc(c, c, 9, "c1")
    for a in range(0, 360, 45):
        ang = math.radians(a)
        for r in range(2, 9):
            cv.px(round(c + r * math.cos(ang)), round(c + r * math.sin(ang)), "n2")
    cv.disc(c, c, 2.6, "r2")
    cv.px(round(c - 1), round(c - 1), "r4")
    cv.ring(c, c, 11, "n0", 1)
    # a star of the sun over the wheel
    cv.sprite(["..r..", ".rrr.", "rrrrr", ".rrr.", "..r.."], {"r": "r2"}, round(c) - 2, 14)
    return cv


def empty():
    """48 × 48: an empty bench, a straw hat left on it, a dragonfly resting on the brim."""
    cv = Cv(48, 48)
    # shadow
    for x in range(8, 44):
        cv.px(x, 43, "s1" if x % 2 else "c3")
    # bench: two back slats on posts, a thick seat whose top catches the light, legs
    for lx in (6, 40):
        cv.vline(lx, 14, 44, "b1")
        cv.vline(lx + 1, 14, 44, "b0")
    for y in (15, 21):
        cv.rect(3, y, 45, y + 4, "b2")
        cv.hline(3, 45, y, "b4")
        cv.hline(3, 45, y + 3, "b1")
    cv.rect(2, 31, 46, 34, "b4")
    cv.hline(2, 46, 31, "c2")
    cv.rect(2, 34, 46, 36, "b2")
    cv.hline(2, 46, 36, "b0")
    # the straw hat: brim, crown, red ribbon
    hat = [
        ".......yyyyyy.......",
        "......yYYYYYyy......",
        "......yYyyyyyy......",
        "......rrrrrrrr......",
        "..yyyyYyyyyyyyyyyy..",
        ".yYYYYyYYyYyyyyyyyy.",
        "..ooooooooooooooooo.",
    ]
    cv.sprite(hat, {"y": "y2", "Y": "y3", "r": "r2", "o": "y1"}, 14, 24)
    cv.px(28, 28, "r1")
    cv.px(29, 29, "r1")
    cv.px(30, 30, "r1")
    # the dragonfly on the brim
    cv.sprite(["w.w....", ".w.....", "rrrrrr.", ".w.....", "w.w...."], {"w": "k4", "r": "r2"}, 31, 25)
    cv.px(31, 27, "r0")
    return cv


def tv():
    """80 × 60: the waiting room's television on its legs, rabbit ears up."""
    cv = Cv(80, 60)
    # antenna
    cv.line(40, 12, 30, 1, "t1")
    cv.line(41, 12, 52, 2, "t1")
    cv.px(30, 1, "c0")
    cv.px(52, 2, "c0")
    cv.rect(37, 10, 45, 13, "t0")
    # cabinet
    cv.rect(10, 13, 70, 50, "b1")
    cv.rect(11, 14, 69, 49, "b2")
    cv.hline(11, 69, 14, "b3")
    cv.vline(11, 14, 49, "b3")
    for y in range(17, 48, 4):
        cv.hline(12, 68, y, "b2")
    # screen with rounded corners, a glass sheen, and the line outside on it
    sx0, sy0, sx1, sy1 = 15, 17, 55, 46
    cv.rect(sx0 - 1, sy0 - 1, sx1 + 1, sy1 + 1, "n0")
    cv.rect(sx0, sy0, sx1, sy1, "h1")
    cv.rect(sx0, sy0 + 17, sx1, sy1, "g2")
    cv.rect(sx0, sy0 + 18, sx1, sy0 + 20, "t2")
    cv.hline(sx0, sx1, sy0 + 18, "c0")
    cv.rect(sx0 + 6, sy0 + 12, sx0 + 24, sy0 + 18, "c1")
    cv.rect(sx0 + 6, sy0 + 15, sx0 + 24, sy0 + 18, "r2")
    for wx in range(sx0 + 8, sx0 + 23, 4):
        cv.rect(wx, sy0 + 13, wx + 2, sy0 + 15, "n2")
    for y in range(sy0, sy1, 2):
        for x in range(sx0, sx1):
            if (x + y) % 11 == 0:
                cv.px(x, y, "k4")
    for (x, y) in ((sx0, sy0), (sx1 - 1, sy0), (sx0, sy1 - 1), (sx1 - 1, sy1 - 1)):
        cv.px(x, y, "n0")
    cv.line(sx0 + 3, sy0 + 2, sx0 + 9, sy0 + 2, "w1")
    cv.line(sx0 + 2, sy0 + 3, sx0 + 2, sy0 + 7, "w1")
    # the dial panel: speaker grille and two knobs
    cv.rect(58, 17, 67, 46, "b1")
    for y in range(19, 30, 2):
        cv.hline(59, 66, y, "b0")
    for ky in (34, 41):
        cv.disc(62.5, ky, 2.6, "c2")
        cv.px(62, ky - 2, "c0")
        cv.px(63, ky, "n1")
    # legs
    for x0, x1 in ((16, 12), (64, 68)):
        cv.line(x0, 50, x1, 58, "b0")
        cv.line(x0 + 1, 50, x1 + 1, 58, "b1")
    cv.hline(12, 70, 50, "b0")
    return cv


# ---------------------------------------------------------------- frames and textures


def plate():
    """24 × 24 (slice 8 → 16 on screen): the enamel plate for panels and sheets. Pixel-rounded
    corners, the lip lit top-left and heavy in shade bottom-right, a cream margin with a slotted
    mounting screw in each corner, the navy inset line, plain cream for the content."""
    W = 24
    cv = Cv(W, W)
    for y in range(W):
        for x in range(W):
            edge = min(x, y, W - 1 - x, W - 1 - y)
            dark = min(W - 1 - x, W - 1 - y) < min(x, y)
            c = "c1"
            if edge == 0:
                c = "s2" if dark else "c3"
            elif edge == 1:
                c = "c3" if dark else "c0"
            elif edge == 6:
                c = "n1" if dark else "n2"
            cv.px(x, y, c)
    for x, y in ((0, 0), (1, 0), (0, 1)):
        for fx, fy in ((x, y), (W - 1 - x, y), (x, W - 1 - y), (W - 1 - x, W - 1 - y)):
            cv.px(fx, fy, (0, 0, 0, 0))
    cv.px(1, 1, "c3")
    for fx, fy in ((W - 2, 1), (1, W - 2), (W - 2, W - 2)):
        cv.px(fx, fy, "s2")
    for fx, fy in ((6, 6), (W - 7, 6), (6, W - 7), (W - 7, W - 7)):
        cv.px(fx, fy, "c1")
    screw = ["hCt", "lll", "Cts"]  # lit rim, the slot across, shade bottom-right
    for sx, sy in ((2, 2), (W - 5, 2), (2, W - 5), (W - 5, W - 5)):
        cv.sprite(screw, {"h": "c0", "C": "c3", "t": "t1", "l": "t0", "s": "s2"}, sx, sy)
    return cv


def pa_box():
    """24 × 24 (slice 8 → 16 on screen, the deck's padding): the station's PA box, navy enamel
    round a cream face plate. A speaker grille along the top, bolts in the corners, a small red
    'on' lamp in the top-left corner, the lip lit top-left."""
    W = 24
    cv = Cv(W, W)
    for y in range(W):
        for x in range(W):
            edge = min(x, y, W - 1 - x, W - 1 - y)
            dark = min(W - 1 - x, W - 1 - y) < min(x, y)
            c = "c1"
            if edge == 0:
                c = "n0"
            elif edge == 1:
                c = "n1" if dark else "n3"
            elif edge <= 5:
                c = "n2"
                if 8 <= x < 16 and 2 <= y <= 5:  # the grille, between the corners
                    c = "n0" if y % 2 == 0 else "n4"
            elif edge == 6:
                c = "n1" if not dark else "n3"
            elif edge == 7:
                c = "c3" if not dark else "c1"
            cv.px(x, y, c)
    for x, y in ((0, 0), (W - 1, 0), (0, W - 1), (W - 1, W - 1)):
        cv.px(x, y, (0, 0, 0, 0))
    for bx, by in ((W - 5, 3), (2, W - 5), (W - 5, W - 5)):
        cv.sprite(["hC", "Ct"], {"h": "t3", "C": "t1", "t": "n0"}, bx, by)
    cv.sprite(["rR", "rr"], {"r": "r2", "R": "r4"}, 3, 3)  # the lamp: the PA is on
    return cv


def ticket():
    """42 × 42 (slice 14 → 28 on screen: the Now bar's whole height, so the middle rows vanish):
    a pale green card ticket, its printed border, and the gate clipper's V notch cut into its
    right end (the left end holds the cover)."""
    W = 42
    cv = Cv(W, W)
    cv.rect(0, 0, W, W, "p1")
    for x in range(W):
        cv.px(x, W - 1, "p0")
    for x in range(3, W - 3):
        cv.px(x, 3, "g2")
        cv.px(x, W - 4, "g2")
    for y in range(3, W - 3):
        cv.px(3, y, "g2")
        cv.px(W - 4, y, "g2")
    # the notch: the two right corners meet at row 14 | 28 (the middle rows collapse), so its
    # upper half ends the top-right corner and its lower half starts the bottom-right one
    for j, depth in enumerate((1, 2, 3, 4, 5)):
        for x in range(depth):
            cv.px(W - 1 - x, 9 + j, (0, 0, 0, 0))
            cv.px(W - 1 - x, W - 10 - j, (0, 0, 0, 0))
        cv.px(W - 1 - depth, 9 + j, "g2")
        cv.px(W - 1 - depth, W - 10 - j, "p0")
    for y in range(14, W - 14):
        for x in range(0, 6):
            cv.px(W - 1 - x, y, (0, 0, 0, 0))
    return cv


def dock():
    """215 × 32: the platform's edge under the phone's doors: the yellow tactile strip with its
    raised dots, then the concrete, lit from the top."""
    W, H = 215, 32
    cv = Cv(W, H)
    cv.rect(0, 0, W, H, "c1")
    cv.hline(0, W, 0, "c4")
    cv.rect(0, 1, W, 5, "y2")
    cv.hline(0, W, 5, "y1")
    for x in range(1, W, 3):
        cv.px(x, 2, "y3")
        cv.px(x, 3, "y1")
    cv.hline(0, W, 6, "c3")
    for x in range(W):
        for y in range(8, H):
            if _grain(x, y, 19):
                cv.px(x, y, "c2")
    return cv


def clapboard():
    """32 × 12 tile: the station house's painted cream boards, one lit lip each (the rail's
    texture; faint: the names read on it as on flat colour)."""
    cv = Cv(32, 12)
    for y in (0, 6):
        cv.hline(0, 32, y, "c0/150")
        cv.hline(0, 32, y + 5, "c3/110")
        for x in (5, 19, 27):
            cv.px(x + (y // 6) * 7, y + 2, "c3/60")
    return cv


def slab():
    """96 × 48 tile: the platform's concrete paving, staggered joints and a few grains (faint:
    words read on it as on flat colour)."""
    cv = Cv(96, 48)
    for x in range(96):
        cv.px(x, 23, "c3/45")
        cv.px(x, 47, "c3/45")
    for y in range(24):
        cv.px(47, y, "c3/45")
        cv.px(95, y + 24, "c3/45")
    for i, (x, y) in enumerate(((7, 11), (30, 5), (18, 29), (40, 36), (11, 40), (26, 18), (70, 9), (61, 33), (84, 41), (77, 16))):
        cv.px(x, y, "c4/45" if i % 2 else "c0/120")
    return cv


def haze():
    """48 × 12 tile: heat shimmer over the platform, thin wavering light lines (faint layer)."""
    cv = Cv(48, 12)
    for row, phase in ((3, 0.0), (8, 1.7)):
        for x in range(48):
            y = row + round(1.2 * math.sin(x / 48 * 2 * math.pi * 2 + phase))
            if (x + row) % 6 < 4:
                cv.px(x, y, "c0")
    return cv


_HEADS = {
    "L": ["..Yy...", ".yYyy..", "oOyyyY.", "ooyyYy.", "oOyyyY.", ".yYyy..", "..Yy..."],
    "M": ["..yYy..", ".Yyyyy.", "yoOoyyY", "yoooyyy", "yoOoyyY", ".Yyyyy.", "..yYy.."],
    "F": ["..yYy..", ".YyyyY.", "yyoOoyy", "YyoooyY", "yyoOoyy", ".YyyyY.", "..yYy.."],
}


def sunflower_frame(head):
    """12 × 32: a sunflower in a wooden planter at the platform's end; its head turns."""
    cv = Cv(12, 32)
    cv.vline(6, 9, 26, "g1")
    cv.vline(7, 12, 26, "g2")
    for lx, ly, flip in ((2, 15, False), (8, 19, True)):
        cv.sprite(["gg..", ".gGg", "..gg"], {"g": "g2", "G": "g3"}, lx, ly, flip=flip)
    cv.sprite(_HEADS[head], {"y": "y2", "Y": "y3", "o": "b1", "O": "b2"}, 3, 3)
    cv.rect(1, 26, 12, 32, "b2")
    cv.hline(1, 12, 26, "b4")
    cv.hline(1, 12, 29, "b1")
    cv.vline(1, 26, 32, "b3")
    cv.vline(11, 26, 32, "b1")
    return cv


SUNFLOWER_TURN = "LLLLLMFFFFFM"


# ---------------------------------------------------------------- dusk (the dark scheme)


def vending_dusk(**state):
    """The drinks machine after dark: everything round it at dusk, the machine itself lit, its
    light spilling on the wall and the floor."""
    from px import glow, rgba, to_dusk, C
    day = vending(**state)
    cv = to_dusk(day)
    for y in range(13, 100):
        for x in range(29, 72):
            p = day.get(x, y)
            if p[3] == 255:
                cv.px(x, y, p)
    glow(cv, 50, 104, 40, 8, "lamp1", 0.7)
    r = rnd(4)
    for y in range(0, 100):  # the halo on the (clear) wall behind
        for x in range(0, 104):
            d = math.hypot((x - 50) / 44, (y - 57) / 41)  # ends inside the piece on every side
            if d < 1 and not cv.get(x, y)[3]:
                cv.px(x, y, "lamp1/%d" % int(8 + (1 - d) * 46))
    return cv


def firefly():
    cv = Cv(3, 3)
    cv.sprite([".f.", "fFf", ".f."], {"f": "fly/90", "F": "lamp0"})
    return cv


def dusk_ui(piece):
    """The frames and textures for the dark scheme, recoloured into the dusk UI steps."""
    from px import recolour
    maps = {
        "plate": {"c1": "u2", "c0": "u4", "c3": "u1", "s2": "u0", "n2": "y1", "n1": "y0", "t1": "t2", "t0": "u0"},
        "pa-box": {"c1": "u1", "c3": "u0"},
        "ticket": {"p1": "q0", "p0": "q1", "g2": "q2"},
        "dock": {"c1": "u2", "c4": "u0", "c3": "u1", "c2": "u3"},
        "clapboard": {"c0": "u2", "c3": "u0"},
        "slab": {"c3": "u0", "c4": "u0", "c0": "u3"},
    }
    source = {"plate": plate, "pa-box": pa_box, "ticket": ticket, "dock": dock, "clapboard": clapboard,
              "slab": slab}[piece]()
    return recolour(source, maps[piece])


def to_dusk_sunflower(head):
    from px import to_dusk
    return to_dusk(sunflower_frame(head))


# ---------------------------------------------------------------- pokes (desktop clicks)

VENDING_TOP = 10  # rows cut from the top of the rail-foot piece (empty wall)
VENDING_POKE = [dict(pressed=2), dict(pressed=2), dict(pressed=2, lit=True), dict(can=1), dict(can=1),
                dict(can=2), dict(can=2), dict(can=2, lit=True), dict(can=2), dict(can=2)]


def vending_piece(dusk=False, **state):
    cv = (vending_dusk if dusk else vending)(**state)
    out = Cv(cv.w, cv.h - VENDING_TOP)
    out.paste(cv.im.crop((0, VENDING_TOP, cv.w, cv.h)), 0, 0)
    return out


def furin_ring(frame):
    """The furin rung by a click: a quick wide swing that settles (8 frames)."""
    sway = (2, -2, 2, -1, 1, -1, 1, 0)[frame]
    cv = Cv(8, 30)
    cv.vline(4, 0, 4, "t3")
    bell = ["..kkk..", ".kwwwk.", "kwhwwwk", "kwrrrwk", "kwwwwwk", "kkkkkkk"]
    cv.sprite(bell, {"k": "n1", "w": "k4", "h": "c0", "r": "r2"}, 1 + (1 if sway > 1 else -1 if sway < -1 else 0) // 1, 4)
    cv.vline(4 + (1 if sway > 0 else -1 if sway < 0 else 0), 10, 13, "t3")
    cv.px(4 + (1 if sway > 0 else -1 if sway < 0 else 0), 11, "y2")
    for j in range(15):
        ox = 2 + round((j + 2) / 17 * sway * 1.6)
        ox = max(0, min(4, ox))
        c = "r2" if j >= 13 else "c0"
        cv.hline(ox, ox + 4, 13 + j, c)
        cv.px(ox + 3, 13 + j, "c3" if c == "c0" else "r1")
    return cv


def air():
    """A breath of air from the bell: a short curved line (the poke's burst)."""
    cv = Cv(4, 2)
    cv.sprite(["cc..", "..cc"], {"c": "k2"})
    return cv


# the station cat on the bench, frames bottom-aligned on the seat (piece row 20)
CAT = {
    "sleep": [
        "..k..k............",
        ".kOk.kOk..........",
        ".kooookook........",
        "koooooooookkkkk...",
        "kowwoowwoooooook..",
        "koooOOooooooooOok.",
        "kOOPPOooooooooooOk",
        ".kPPkkoooooooooOk.",
        "..kk..kkkkkkkkkk..",
    ],
    "awake": [
        "..k..k............",
        ".kOk.kOk..........",
        ".kooookook........",
        "koooooooookkkkk...",
        "koPkooPkoooooook..",
        "koooOOooooooooOok.",
        "kOOPPOooooooooooOk",
        ".kPPkkoooooooooOk.",
        "..kk..kkkkkkkkkk..",
    ],
    "sit": [
        "..k..k..........",
        ".kOk.kOk........",
        ".kooookok.......",
        "kooooooook......",
        "koPkooPkok......",
        "kooooooook......",
        ".koooreooOk.....",
        "..kkoooooOkkk...",
        "..kPPoooooooOk..",
        ".kPPPooooooooOk.",
        "kPPkoooooooooOk.",
        ".kkkkkkkkkkkkk..",
    ],
    "stretch": [
        "...................k..",
        "..................kok.",
        ".................koOk.",
        "..k..k..........kook..",
        ".kOk.kOk.......koook..",
        ".kooookok...kkkooook..",
        "kooooooookkkoooooook..",
        "koPkooPkoooooooooook..",
        "kooooooooooooooOoook..",
        ".kkPPkkkkkkkkkkkPPk...",
        ".kPPk..........kook...",
        "kPPk...........kPPk...",
    ],
    "yawn": [
        "...................k..",
        "..................kok.",
        ".................koOk.",
        "..k..k..........kook..",
        ".kOk.kOk.......koook..",
        ".kooookok...kkkooook..",
        "kooooooookkkoooooook..",
        "koPkooPkoooooooooook..",
        "krroooooooooooooOoook.",
        "krrPPkkkkkkkkkkkPPk...",
        ".kPPk..........kook...",
        "kPPk...........kPPk...",
    ],
}
CAT_POKE = ["awake", "awake", "sit", "stretch", "yawn", "yawn", "stretch", "sit", "awake", "sleep"]


def bench_end(head="L", cat="sleep", dusk=False):
    """72 × 32: the bench's end of Home's picture, as a piece: the station cat asleep on the seat
    (a click wakes it: it sits up, stretches, yawns and curls up again) and the turning
    sunflower in its planter. Anchored bottom-right, it sits on the picture's own bench."""
    from px import to_dusk
    cv = Cv(72, 32)
    rows = CAT[cat]
    cv.sprite(rows, {"k": "b0", "o": "o1", "O": "o2", "w": "o0", "P": "c0", "r": "r2", "e": "n0"},
              2, 21 - len(rows))
    cv.paste(sunflower_frame(head), 60, 0)
    return to_dusk(cv) if dusk else cv


def crossing_blink(frame):
    """70 × 24, clear but for the level crossing's two red lamps (the status strip's crossing sits
    at x 65 of this piece when it is anchored at the strip's centre). A click makes them blink
    left-right twice, as when a train is coming; clear again after. The same in both schemes."""
    from px import glow
    cv = Cv(70, 24)
    side = (None, -1, 1, -1, 1, None)[frame]
    if side:
        x = 65 + side
        cv.px(x, 12, "lamp0")
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            cv.px(x + dx, 12 + dy, "r3/200")
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (-2, 0), (2, 0), (0, -2), (0, 2)):
            cv.px(x + dx, 12 + dy, "r3/90")
    return cv
