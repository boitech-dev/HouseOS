"""The big pictures: the platform (Home), the line (status bar), the stationmaster's office (My
Space). Drawn at 1×, shown at 2×. Light from the upper left."""

import math

from px import _grain, Cv, cloud, rnd, tone

# ---------------------------------------------------------------- small reusable things


def sky(cv, y0, y1, names=("k0", "k1", "k2", "k3", "k4")):
    cv.bands((0, y0, cv.w, y1), list(names))


def ridge(cv, y_base, amp, seed, names, x0=0, x1=None, rough=1.0):
    """A far hill line: filled below the ridge, the face toward the light a step lighter."""
    r = rnd(seed)
    phases = [r.uniform(0, 6.28) for _ in range(4)]
    freqs = [0.011, 0.023, 0.051, 0.11]
    amps = [1.0, 0.5, 0.22 * rough, 0.1 * rough]
    x1 = cv.w if x1 is None else x1
    tops = []
    for x in range(x0, x1):
        h = sum(a * math.sin(x * f + p) for a, f, p in zip(amps, freqs, phases))
        tops.append(int(y_base - amp * (0.55 + 0.45 * h)))
    for i, x in enumerate(range(x0, x1)):
        top = tops[i]
        slope = tops[i] - tops[i - 1] if i else 0
        for y in range(top, cv.h):
            c = names[0]
            if y - top < 2 and slope > 0:  # a face turned to the sun
                c = names[1]
            cv.px(x, y, c)
    return tops


def tree_clump(cv, x, y, r, seed, names=("g0", "g1", "g2", "g3")):
    rr = rnd(seed)
    blobs = [(x + rr.uniform(-r, r), y + rr.uniform(-r * 0.4, r * 0.3), r * rr.uniform(0.45, 0.8)) for _ in range(5)]
    for yy in range(int(y - r * 1.6), int(y + r * 1.2)):
        for xx in range(int(x - r * 2), int(x + r * 2)):
            best = None
            for cx, cy, br in blobs:
                d2 = (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2
                if d2 <= br * br:
                    h = math.sqrt(br * br - d2)
                    if best is None or cy - h < best[0]:
                        best = (cy - h, cx, cy, br, h)
            if best:
                _, cx, cy, br, h = best
                t = (-(xx - cx) * 0.55 - (yy - cy) * 0.75) / br * 0.5 + 0.5
                tone(cv, xx, yy, t, list(names))


def sunflower(cv, x, y, stem, face="left", big=False):
    """A sunflower head at (x, y) on a stem `stem` pixels long, facing the sun (left)."""
    # stem and two leaves
    cv.vline(x, y + 2, y + stem, "g1")
    cv.px(x + 1, y + 4, "g2")
    for ly, side in ((y + stem // 2, -1), (y + stem // 2 + 3, 1)):
        cv.px(x + side, ly, "g2")
        cv.px(x + 2 * side, ly, "g3")
        cv.px(x + 2 * side, ly - 1, "g2")
        cv.px(x + 3 * side, ly - 1, "g3")
    if big:
        rows = [
            ".yYy.",
            "YyoyY",
            "yoooy",
            "YyoyY",
            ".yYy.",
        ]
    else:
        rows = [
            ".Y.",
            "yoY",
            ".y.",
        ]
    legend = {"y": "y2", "Y": "y3", "o": "b1"}
    if face == "left":
        legend = {"y": "y2", "Y": "y3", "o": "b1"}
    off = len(rows) // 2
    cv.sprite(rows, legend, x - off, y - off)


def swallow(cv, x, y):
    cv.sprite(["n.....n", ".nn.nn.", "...n..."], {"n": "n1"}, x, y)


def crow(cv, x, y):
    cv.sprite([".nn.", "nnnn", ".nnn", "..n."], {"n": "n0"}, x, y)


# ---------------------------------------------------------------- the platform (Home's hero)

FAR_RAIL = 98  # the far track's rail top: the railcar layer rides on it


def cumulonimbus(cv):
    """The summer tower: a wide flat base, a column, cauliflower tops lit from the left."""
    blobs = []
    r = rnd(5)
    # base
    for x in range(176, 316, 12):
        blobs.append((x + r.uniform(-3, 3), 64 + r.uniform(-2, 2), 11 + r.uniform(-2, 3)))
    # column rising, narrowing
    for y, half, rad in ((50, 52, 13), (38, 44, 12), (27, 36, 11), (17, 28, 10), (9, 20, 8)):
        for k in range(4):
            x = 246 - half + k * (2 * half) / 3 + r.uniform(-4, 4)
            blobs.append((x, y + r.uniform(-3, 3), rad * r.uniform(0.8, 1.15)))
    # little bubbles on the lit edge
    for _ in range(10):
        a = r.uniform(3.4, 5.2)
        blobs.append((246 + 48 * math.cos(a) * 0.8, 36 + 36 * math.sin(a) * 0.9, r.uniform(4, 7)))
    cloud(cv, blobs, base=74)


def telegraph_pole(cv, x, top, bottom):
    cv.vline(x, top, bottom, "b1")
    cv.vline(x + 1, top + 1, bottom, "b0")
    cv.hline(x - 4, x + 6, top + 2, "b1")
    cv.hline(x - 3, x + 5, top + 5, "b1")
    for ix in (x - 4, x - 1, x + 2, x + 5):
        cv.px(ix, top + 1, "c0")
    for ix in (x - 3, x + 4):
        cv.px(ix, top + 4, "c0")


def hero(cat=True):
    W, H = 360, 128
    cv = Cv(W, H)
    horizon = 84
    sky(cv, 0, horizon + 4)
    cumulonimbus(cv)
    cloud(cv, [(52, 40, 9), (64, 34, 10), (78, 40, 8), (42, 46, 6), (88, 46, 5), (70, 28, 6)], base=49)
    cloud(cv, [(128, 58, 5), (136, 55, 6), (144, 59, 4)], base=62)
    cloud(cv, [(330, 58, 5), (340, 55, 6), (350, 59, 5)], base=62)
    swallow(cv, 150, 18)
    swallow(cv, 166, 26)
    # far mountains, then the forest at their foot
    ridge(cv, horizon - 2, 14, 7, ("h2", "h2"))
    ridge(cv, horizon + 2, 9, 3, ("h1", "h2"), rough=1.4)
    for i, x in enumerate(range(4, W, 9)):
        r = rnd(i)
        if r.random() < 0.85:
            tree_clump(cv, x + r.randint(-3, 3), horizon + 3 + r.randint(0, 2), 3.2 + r.random() * 1.6, i,
                       names=("g0", "g1", "g1", "g2"))
    cv.rect(0, horizon + 4, W, horizon + 6, "g1")
    # a farmhouse under the trees, its roof catching the sun
    fx = 108
    cv.rect(fx, horizon + 1, fx + 14, horizon + 6, "c2")
    cv.rect(fx + 3, horizon + 3, fx + 5, horizon + 6, "b1")
    cv.poly([(fx - 2, horizon + 1), (fx + 3, horizon - 4), (fx + 11, horizon - 4), (fx + 16, horizon + 1)], "t0")
    cv.hline(fx + 3, fx + 11, horizon - 4, "t2")
    # paddies: rows of young rice, lighter toward the sun
    for y in range(horizon + 6, 95):
        for x in range(W):
            band = y - horizon - 6
            c = "g3" if (x // 2 + band) % 6 else "g2"
            if band == 0:
                c = "g2"
            if (x + y * 3) % 23 == 0:
                c = "g4"
            cv.px(x, y, c)
    # the road to the crossing
    for y in range(horizon + 6, 95):
        t = (y - horizon - 6) / (95 - horizon - 6)
        cx, half = 172 - t * 3, 1 + t * 4
        cv.hline(int(cx - half), int(cx + half) + 1, y, "c3")
        cv.px(int(cx - half), y, "c4")
    # sunflowers along the paddy edge, facing the sun (behind the far track)
    for x, y, s, big in ((192, 86, 9, True), (199, 88, 7, False), (205, 84, 11, True), (212, 87, 8, False),
                         (218, 85, 10, True), (225, 88, 7, False), (60, 88, 7, False), (66, 86, 9, True)):
        sunflower(cv, x, y, s, big=big)
    # telegraph poles along the far line, their wires sagging
    poles = [22, 132, 242, 352]
    for p in poles:
        telegraph_pole(cv, p, 46, 96)
    for a, b in zip([-88] + poles, poles + [462]):
        for x in range(max(0, a), min(W, b)):
            t = (x - a) / (b - a)
            sag = 4 * 4 * t * (1 - t)
            cv.px(x, int(48 + sag), "n2")
            cv.px(x, int(51 + sag * 0.8), "n3")
    crow(cv, 92, 46)
    # the level crossing on the far side: striped post, crossbuck, two lamps
    x = 180
    for y in range(74, 97):
        cv.px(x, y, "n0" if (y // 2) % 2 else "y2")
        cv.px(x + 1, y, "n1" if (y // 2) % 2 else "y1")
    buck = ["y.....y", ".y...y.", "..y.y..", "...n...", "..y.y..", ".y...y.", "y.....y"]
    cv.sprite(buck, {"y": "y2", "n": "n0"}, x - 3, 67)
    cv.rect(x - 3, 76, x + 5, 79, "n0")
    cv.px(x - 2, 77, "r2")
    cv.px(x + 3, 77, "r3")
    # the far track on its low embankment (the railcar rides on FAR_RAIL)
    cv.rect(0, 95, W, 101, "t2")
    cv.hline(0, W, 95, "c4")
    for x in range(W):
        for y in range(96, 101):
            if (x * 7 + y * 13) % 5 == 0:
                cv.px(x, y, "t1")
    cv.hline(0, W, FAR_RAIL, "t3")
    cv.hline(0, W, FAR_RAIL + 1, "t0")
    for x in range(2, W, 4):
        cv.px(x, FAR_RAIL + 2, "b1")
    # grass between the tracks, a low fence, a few wildflowers
    cv.rect(0, 101, W, 106, "g2")
    for x in range(W):
        if (x * 5) % 7 == 0:
            cv.px(x, 101, "g3")
        if (x * 11) % 29 == 0:
            cv.px(x, 102, "y3")
        if (x * 13) % 31 == 0:
            cv.px(x, 103, "c0")
    for x in range(W):
        cv.px(x, 103, "b2") if x % 3 else None
        if x % 9 == 0:
            cv.vline(x, 102, 106, "b1")
    # the near track: ballast, sleepers, rails
    cv.rect(0, 106, W, 113, "t2")
    for x in range(W):
        for y in range(106, 113):
            if (x * 7 + y * 13) % 5 == 0:
                cv.px(x, y, "t1")
            elif (x * 3 + y * 11) % 7 == 0:
                cv.px(x, y, "t3")
    for x in range(1, W, 5):
        cv.hline(x, x + 3, 110, "b1")
        cv.hline(x, x + 3, 111, "b0")
    for y in (107, 111):
        cv.hline(0, W, y, "t3")
        cv.hline(0, W, y + 1, "t0")
    # the platform: its edge in shade, the top in sun, the white safety line
    cv.rect(0, 113, W, 117, "s2")
    cv.hline(0, W, 113, "c4")
    cv.rect(0, 117, W, H, "c2")
    cv.hline(0, W, 117, "c0")
    cv.hline(0, W, 118, "c1")
    cv.hline(0, W, 120, "c0")
    for x in range(W):
        for y in range(121, H):
            if _grain(x, y, 17):
                cv.px(x, y, "c3")
    # the canopy's shade on the platform, lower right
    for y in range(117, H):
        for x in range(268 - (y - 117) * 2, W):
            cv.dither(x, y, cv.get(x, y), "c3", 0.5)
    # red fire buckets on their rack
    for i, bx in enumerate((248, 254, 260)):
        cv.sprite(["kkkkk", "krRrk", "krrrk", ".kbk."], {"k": "r0", "r": "r2", "R": "r3", "b": "r1"}, bx, 116)
    cv.rect(246, 120, 267, 121, "b1")
    cv.vline(247, 121, 126, "b0")
    cv.vline(265, 121, 126, "b0")
    # the bench, the station cat asleep on it, its cap beside it
    cv.rect(286, 116, 330, 118, "b3")
    cv.hline(286, 330, 116, "b4")
    cv.hline(286, 330, 118, "b1")
    cv.rect(286, 110, 330, 112, "b3")
    cv.hline(286, 330, 110, "b4")
    cv.hline(286, 330, 112, "b1")
    for lx in (288, 326):
        cv.vline(lx, 112, 126, "b1")
        cv.vline(lx + 1, 118, 126, "b0")
    # the station cat, curled asleep on the seat: ears up, eyes shut, white paws, tail round
    cat = [
        "..k..k............",
        ".kOk.kOk..........",
        ".kooookook........",
        "koooooooookkkkk...",
        "kowwoowwoooooook..",
        "koooOOooooooooOok.",
        "kOOPPOooooooooooOk",
        ".kPPkkoooooooooOk.",
        "..kk..kkkkkkkkkk..",
    ]
    if cat:  # (the Home picture leaves it to the bench-end layer, which can wake it)
        cv.sprite(cat, {"k": "b0", "o": "o1", "O": "o2", "w": "o0", "P": "c0"}, 290, 108)
    cv.sprite([".nnn.", "nnynn", "kkkkk"], {"n": "n2", "y": "y2", "k": "n0"}, 316, 113)
    # the canopy from the right: roof edge, a bracket, the hanging name board, the clock
    cv.rect(250, 0, W, 7, "b1")
    cv.hline(250, W, 0, "b2")
    cv.hline(250, W, 7, "b0")
    for x in range(252, W, 7):
        cv.vline(x, 1, 7, "b2")
    cv.line(W - 1, 26, W - 22, 8, "b1")
    cv.line(W - 1, 27, W - 22, 9, "b0")
    bx0, by0, bx1, by1 = 258, 13, 318, 35
    for rx in (bx0 + 6, bx1 - 7):
        cv.vline(rx, 8, by0, "n1")
    cv.rect(bx0, by0, bx1, by1, "n1")
    cv.rect(bx0 + 1, by0 + 1, bx1 - 1, by1 - 1, "c0")
    cv.rect(bx0 + 2, by0 + 2, bx1 - 2, by1 - 7, "c1")
    cv.rect(bx0 + 1, by1 - 6, bx1 - 1, by1 - 1, "n2")
    cv.hline(bx0 + 1, bx1 - 1, by1 - 6, "r2")
    cv.hline(bx0 + 1, bx1 - 1, by1 - 1, "n0")
    cv.sprite(["..c", ".cc", "ccc", ".cc", "..c"], {"c": "c0"}, bx0 + 3, by1 - 6)
    cv.sprite(["c..", "cc.", "ccc", "cc.", "c.."], {"c": "c0"}, bx1 - 6, by1 - 6)
    ex, ey = (bx0 + bx1) // 2, by0 + 7
    wheel_emblem(cv, ex, ey)
    kx, ky = 338, 22
    cv.vline(kx, 8, ky - 6, "n1")
    cv.disc(kx, ky, 6, "n1")
    cv.disc(kx, ky, 5, "c0")
    for a in range(12):
        ang = a / 12 * 6.283
        cv.px(round(kx + 4.2 * math.sin(ang)), round(ky - 4.2 * math.cos(ang)), "n4" if a % 3 else "n1")
    cv.line(kx, ky, kx, ky - 4, "n1")
    cv.line(kx, ky, kx + 2, ky + 1, "n1")
    cv.px(kx, ky, "r2")
    return cv


def wheel_emblem(cv, ex, ey, ink="n2", hub="r2"):
    """The line's emblem, small: a wheel with a wing either side."""
    cv.ring(ex, ey, 4.2, ink, 1.3)
    cv.px(ex, ey, hub)
    for dy, reach in ((-2, 12), (0, 10), (2, 8)):
        cv.hline(ex - reach, ex - 4, ey + dy, ink)
        cv.hline(ex + 5, ex + reach + 1, ey + dy, ink)


def railcar(frame=0):
    """A two-car diesel railcar, cream over red, crossing on the far track (to the left). Its
    wheels sit on FAR_RAIL when the picture is anchored to the hero's bottom."""
    car, gap = 50, 2
    W = car * 2 + gap
    body = 13
    Hh = body + (128 - FAR_RAIL)
    cv = Cv(W, Hh)
    wheel = body - 1
    for i in range(2):
        x0 = i * (car + gap)
        cv.rect(x0, 1, x0 + car, wheel, "c1")
        cv.hline(x0 + 1, x0 + car - 1, 0, "t1")
        cv.hline(x0, x0 + car, 1, "c0")
        cv.rect(x0, 7, x0 + car, wheel, "r2")
        cv.hline(x0, x0 + car, 7, "r3")
        cv.hline(x0, x0 + car, wheel - 1, "r1")
        for wx in range(x0 + 7, x0 + car - 6, 5):
            cv.rect(wx, 3, wx + 3, 6, "n2")
            cv.px(wx, 3, "k3")
        for dx in (x0 + 3, x0 + car - 6):
            cv.rect(dx, 2, dx + 3, wheel - 1, "c2")
            cv.rect(dx, 3, dx + 3, 5, "n3")
        cv.hline(x0, x0 + car, wheel, "n0")
        for bx in (x0 + 5, x0 + car - 12):
            cv.hline(bx, bx + 8, wheel, "t0")
            for wx in (bx + 1, bx + 5):
                cv.px(wx + (frame % 2), wheel, "t2")
        # the engine's exhaust pipe on the roof
        cv.px(x0 + car // 2, 0, "t0")
    cv.rect(0, 2, 1, wheel - 1, "c0")
    cv.px(0, 9, "y3")
    cv.px(W - 1, 9, "r3")
    cv.hline(car, car + gap, 9, "t0")
    return cv


# ---------------------------------------------------------------- the line (status bar)


def status():
    """960 × 24: the line along the top of every page, its sky left clear (the drifting sky and
    clouds pass behind it, status_sky). Far hills, catenary, a crossing at the centre, sunflowers,
    a crow on the wire, the rail at its foot: the train (train_far) rides on row 21."""
    W, H = 960, 24
    cv = Cv(W, H)
    # far, flat clouds resting on the hills: they stay while the near sky drifts behind the line
    r = rnd(31)
    x = 20
    while x < W - 30:
        w = r.randint(5, 11)
        cloud(cv, [(x, 13, w * 0.45), (x + w * 0.5, 12, w * 0.55), (x + w, 13.5, w * 0.4)], base=15,
              names=("w3", "w2", "w2", "w1", "w1"))
        x += r.randint(70, 190)
    ridge(cv, 17, 5, 21, ("h1", "h2"), rough=1.2)
    for x in range(0, W, 4):
        rr = rnd(x)
        if rr.random() < 0.55:
            tree_clump(cv, x, 17, 2 + rr.random(), x, names=("g0", "g1", "g1", "g2"))
    cv.rect(0, 17, W, 20, "g2")
    for x in range(W):
        if _grain(x, 17, 4):
            cv.px(x, 17, "g3")
        if _grain(x, 19, 9):
            cv.px(x, 19, "g1")
    # the embankment: bright rail, sleepers, ballast
    cv.rect(0, 20, W, 24, "t2")
    cv.hline(0, W, 20, "c4")
    cv.hline(0, W, 21, "t3")
    for x in range(0, W, 7):
        cv.px(x, 21, "c0")
    cv.hline(0, W, 22, "t0")
    for x in range(W):
        cv.px(x, 23, "b1" if x % 3 == 0 else ("t1" if _grain(x, 23, 3) else "t2"))
    # masts every 120, sagging messenger wire, straight contact wire at row 5
    masts = list(range(40, W, 120))
    for m in masts:
        cv.vline(m, 1, 21, "n1")
        cv.px(m, 0, "n1")
        cv.hline(m - 3, m + 1, 3, "n1")
    for a, b in zip([-80] + masts, masts + [W + 80]):
        for x in range(max(0, a), min(W, b)):
            t = (x - a) / (b - a)
            cv.px(x, int(1 + 3 * 4 * t * (1 - t)), "n2")
            cv.px(x, 5, "n1")
    # the level crossing near the centre
    x = W // 2 + 30
    for y in range(9, 21):
        cv.px(x, y, "n0" if (y // 2) % 2 else "y2")
    cv.sprite(["y...y", ".y.y.", "..n..", ".y.y.", "y...y"], {"y": "y2", "n": "n0"}, x - 2, 6)
    cv.px(x - 1, 12, "r2")
    cv.px(x + 1, 12, "r2")
    for sx in (W // 2 - 60, W // 2 - 54, W // 2 + 120, W // 2 + 126, W // 2 - 300, W // 2 + 330):
        cv.vline(sx, 14, 20, "g1")
        cv.sprite([".Y.", "YoY", ".Y."], {"Y": "y2", "o": "b1"}, sx - 1, 12)
    crow(cv, W // 2 - 140, 1)
    return cv


def status_sky():
    """480 × 24 tile: the sky behind the line, five different clouds at uneven gaps (a layer that
    drifts slowly under the strip)."""
    W, H = 480, 24
    cv = Cv(W, H)
    sky(cv, 0, H, ("k1", "k2", "k3", "k4"))
    for blobs, base in (
        ([(30, 10, 4), (36, 8, 5), (43, 10, 4)], 12),
        ([(104, 13, 3), (109, 11, 4), (115, 13, 3), (120, 14, 2)], 15),
        ([(190, 9, 5), (198, 6, 6), (207, 8, 5), (214, 10, 4), (184, 11, 3)], 13),
        ([(300, 14, 3), (305, 13, 3)], 15),
        ([(378, 10, 4), (386, 7, 6), (395, 5, 5), (403, 9, 5), (410, 11, 3)], 13),
    ):
        cloud(cv, blobs, base=base)
    return cv


def train_far(frame=0):
    """The local train seen across the fields: two cars, cream over red, pantograph on the
    wire. 24 rows tall like the strip, so it rides exactly on the strip's rail."""
    car = 44
    W, H = car * 2 + 4, 24
    cv = Cv(W, H)
    for i in range(2):
        x0 = i * (car + 2)
        # body: cream upper, red lower, a cream stripe, rounded front on the lead car
        cv.rect(x0, 9, x0 + car, 20, "c1")
        cv.hline(x0, x0 + car, 9, "c0")
        cv.rect(x0, 15, x0 + car, 20, "r2")
        cv.hline(x0, x0 + car, 15, "r3")
        cv.hline(x0, x0 + car, 19, "r1")
        cv.hline(x0 + 1, x0 + car - 1, 8, "t1")  # roof
        # windows
        for wx in range(x0 + 5, x0 + car - 4, 5):
            cv.rect(wx, 11, wx + 3, 14, "n2")
            cv.px(wx, 11, "k3")
        # doors
        for dx in (x0 + 3, x0 + car - 6):
            cv.rect(dx, 10, dx + 3, 19, "c2")
            cv.rect(dx, 11, dx + 3, 13, "n3")
        # bogies and wheels on the rail
        for bx in (x0 + 5, x0 + car - 11):
            cv.rect(bx, 20, bx + 7, 21, "t0")
            for wx in (bx + 1, bx + 5):
                cv.px(wx, 20, "n0")
                cv.px(wx + (frame % 2), 20, "t2")
        cv.hline(x0, x0 + car, 20, "n0")
    # the lead car's front (left: it runs to the left)
    cv.rect(0, 10, 1, 19, "c0")
    cv.px(1, 17, "y3")  # headlight
    cv.px(car * 2 + 1, 17, "r3")  # tail lamp
    # pantograph on the lead car, touching the wire (row 5)
    px0 = 16
    cv.hline(px0 - 3, px0 + 4, 5, "t0")
    cv.line(px0 - 2, 6, px0 + 1, 8, "t0")
    cv.line(px0 + 3, 6, px0, 8, "t0")
    if frame == 1:
        cv.px(px0 + 1, 4, "y3")  # a tiny spark on the wire
    # the coupler gap
    cv.hline(car, car + 2, 17, "t0")
    return cv


# ---------------------------------------------------------------- the stationmaster's office (My Space)


def office():
    """200 × 90: the stationmaster's office on an August afternoon. Cream wall over a wooden
    wainscot, the window on the platform, the ticket rack, the pendulum clock, the desk with
    its telephone and dating press, the cap on its hook, the fan turning the heat around."""
    W, H = 200, 90
    cv = Cv(W, H)
    # wall, wainscot, floor
    cv.rect(0, 0, W, 56, "c1")
    for x in range(W):
        for y in range(0, 56):
            if _grain(x, y, 29):
                cv.px(x, y, "c2")
    cv.hline(0, W, 0, "c3")
    cv.rect(0, 56, W, 74, "b2")
    for x in range(0, W, 8):
        cv.vline(x, 57, 74, "b1")
        cv.vline(x + 1, 57, 74, "b3")
    cv.hline(0, W, 56, "b4")
    cv.hline(0, W, 57, "b1")
    cv.rect(0, 74, W, H, "c3")
    cv.hline(0, W, 74, "b0")
    for x in range(0, W, 12):
        cv.vline(x, 75, H, "c4")
    # the window on the platform, sunlight pouring in (its patch on the floor)
    wx0, wy0, wx1, wy1 = 10, 8, 62, 46
    sky(cv, wy0, wy1 - 12, ("k1", "k2", "k3", "k4"))
    cv.rect(0, wy0, wx0, wy1, "c1")
    cv.rect(wx1, wy0, W, wy1, "c1")
    for x in range(W):
        for y in range(0, 56):
            if (x < wx0 or x >= wx1 or y < wy0 or y >= wy1) and _grain(x, y, 29):
                cv.px(x, y, "c2")
    cloud(cv, [(34, 22, 6), (42, 18, 7), (50, 23, 5)], base=26)
    cv.rect(wx0, wy1 - 12, wx1, wy1 - 8, "h1")
    cv.rect(wx0, wy1 - 8, wx1, wy1 - 5, "g2")
    cv.rect(wx0, wy1 - 5, wx1, wy1, "c2")
    cv.hline(wx0, wx1, wy1 - 5, "c0")
    for sx in (16, 22, 52):
        cv.vline(sx, wy1 - 12, wy1 - 5, "g1")
        cv.sprite([".y.", "yoy", ".y."], {"y": "y2", "o": "b1"}, sx - 1, wy1 - 14)
    # frame and mullions
    cv.rect(wx0 - 2, wy0 - 2, wx1 + 2, wy0, "b1")
    cv.rect(wx0 - 2, wy1, wx1 + 2, wy1 + 3, "b1")
    cv.hline(wx0 - 3, wx1 + 3, wy1, "b3")
    cv.vline(wx0 - 2, wy0, wy1, "b1")
    cv.vline(wx0 - 1, wy0, wy1, "b2")
    cv.vline(wx1, wy0, wy1, "b2")
    cv.vline(wx1 + 1, wy0, wy1, "b1")
    cv.vline((wx0 + wx1) // 2, wy0, wy1, "b1")
    cv.hline(wx0, wx1, (wy0 + wy1) // 2 - 4, "b1")
    # the light patch on the floor
    for y in range(76, H):
        for x in range(20 + (y - 76) * 2, 70 + (y - 76) * 2):
            cv.dither(x, y, cv.get(x, y), "c1", 0.6)
    # the ticket rack: pigeonholes of colour-coded card tickets
    rx0, ry0 = 72, 6
    cv.rect(rx0, ry0, rx0 + 42, ry0 + 36, "b1")
    cv.rect(rx0 + 1, ry0 + 1, rx0 + 41, ry0 + 35, "b0")
    colours = ["p0", "c0", "r4", "k3", "y3", "p1", "o2"]
    for j in range(5):
        for i in range(7):
            x, y = rx0 + 2 + i * 6, ry0 + 2 + j * 7
            cv.rect(x, y, x + 5, y + 6, "b2")
            c = colours[(i * 3 + j * 2) % len(colours)]
            if (i + j * 3) % 5:
                cv.rect(x + 1, y + 1, x + 4, y + 6, c)
                cv.px(x + 1, y + 1, "c0")
    # the pendulum clock
    kx, ky = 132, 10
    cv.rect(kx - 7, ky - 4, kx + 8, ky + 30, "b1")
    cv.rect(kx - 6, ky - 3, kx + 7, ky + 29, "b2")
    cv.vline(kx - 6, ky - 3, ky + 29, "b3")
    cv.disc(kx + 0.5, ky + 5, 5.5, "b0")
    cv.disc(kx + 0.5, ky + 5, 4.6, "c0")
    cv.line(kx, ky + 5, kx, ky + 2, "n1")
    cv.line(kx, ky + 5, kx + 2, ky + 6, "n1")
    cv.rect(kx - 3, ky + 13, kx + 4, ky + 27, "b0")
    cv.vline(kx, ky + 13, ky + 23, "y1")
    cv.disc(kx + 0.5, ky + 23, 1.8, "y2")
    cv.px(kx - 1, ky + 22, "y3")
    # the calendar: a grid of days, one crossed in red
    cx0, cy0 = 150, 12
    cv.rect(cx0, cy0, cx0 + 18, cy0 + 22, "c0")
    cv.rect(cx0, cy0, cx0 + 18, cy0 + 5, "r2")
    for j in range(4):
        for i in range(5):
            cv.px(cx0 + 2 + i * 3, cy0 + 8 + j * 3, "n4")
    cv.px(cx0 + 8, cy0 + 14, "r2")
    cv.px(cx0 + 9, cy0 + 13, "r2")
    cv.vline(cx0 + 9, cy0 - 2, cy0, "t0")
    # the cap on its hook, the hand lamp below it
    cv.px(180, 10, "t0")
    cv.sprite(["..nnnnn...", ".nnnnnnnn.", "nnnnynnnnn", "kkkkkkkkkk", ".kkkkkkk.."], {"n": "n2", "y": "y2", "k": "n0"}, 175, 11)
    cv.rect(179, 24, 186, 34, "t1")
    cv.rect(180, 26, 185, 31, "y3")
    cv.hline(178, 187, 24, "t0")
    cv.px(182, 22, "t0")
    cv.px(183, 23, "t0")
    # the desk
    dy = 50
    cv.rect(66, dy, 170, dy + 3, "b3")
    cv.hline(66, 170, dy, "b4")
    cv.hline(66, 170, dy + 3, "b0")
    cv.rect(68, dy + 4, 96, 76, "b2")
    cv.rect(69, dy + 5, 95, dy + 11, "b3")
    cv.rect(69, dy + 13, 95, dy + 19, "b3")
    cv.px(82, dy + 8, "y2")
    cv.px(82, dy + 16, "y2")
    cv.vline(166, dy + 4, 78, "b1")
    # on the desk: telephone, dating press, a ledger, a glass of barley tea
    cv.sprite(["..kkkkkk..", ".kk....kk.", ".kkkkkkkk.", "kkkkkkkkkk", "kkkcckkkkk", "kkkkkkkkkk"], {"k": "n0", "c": "c0"}, 72, dy - 6)
    # the dating press: a cast-iron body, the slot for the ticket, the lever, brass plate
    press = [
        "....kk....",
        "...kllk...",
        "..kkllkk..",
        ".kttttttk.",
        ".ktkkkktkk",
        ".kttppttk.",
        "kttttttttk",
        "kkkkkkkkkk",
    ]
    cv.sprite(press, {"k": "n0", "l": "t2", "t": "t0", "p": "y2"}, 95, dy - 8)
    cv.line(104, dy - 6, 108, dy - 11, "t1")
    cv.px(108, dy - 12, "r2")
    # the desk's shadow on the wainscot and floor, falling right
    for y in range(dy + 4, 76):
        for x in range(96, 168):
            if not (x < 97 and y < 76):
                cv.dither(x, y, cv.get(x, y), "b1" if y < 74 else "c4", 0.35)
    cv.rect(112, dy - 3, 128, dy, "n2")
    cv.hline(112, 128, dy - 3, "c0")
    cv.rect(114, dy - 5, 128, dy - 3, "r1")
    cv.sprite(["k..k", "kbbk", "kbbk", "kkkk"], {"k": "k4", "b": "y1"}, 134, dy - 4)
    # the electric fan on its stand
    fx, fy = 146, dy - 12
    cv.disc(fx, fy, 6.5, "k3")
    cv.ring(fx, fy, 6.5, "k1", 1)
    for a in range(0, 360, 90):
        ang = math.radians(a + 30)
        for r in range(1, 6):
            cv.px(round(fx + r * math.cos(ang)), round(fy + r * math.sin(ang)), "k4")
    cv.px(fx, fy, "n1")
    cv.vline(fx, fy + 6, dy, "t1")
    cv.hline(fx - 3, fx + 4, dy - 1, "t0")
    # the chair, and the hand flags in their holder by the door frame
    cv.rect(108, 58, 124, 60, "b1")
    cv.vline(110, 60, 76, "b0")
    cv.vline(122, 60, 76, "b0")
    cv.rect(122, 44, 124, 60, "b1")
    cv.rect(186, 46, 194, 74, "b1")
    cv.vline(187, 36, 46, "b0")
    cv.vline(191, 36, 46, "b0")
    cv.rect(188, 36, 192, 40, "r2")
    cv.rect(192, 36, 196, 40, "g2")
    return cv


# ---------------------------------------------------------------- dusk (the dark scheme)


def _stars(cv, rows, seed, only=("d-k0", "d-k1")):
    from px import C
    keep = {C(n)[:3] for n in only}
    r = rnd(seed)
    for _ in range(cv.w // 6):
        x, y = r.randrange(cv.w), r.randrange(rows)
        if cv.get(x, y)[:3] in keep:
            cv.px(x, y, "lamp0" if r.random() < 0.3 else "c0")


def hero_dusk():
    """The same platform at 7 p.m.: the tower lit apricot from the set sun, stars, the canopy's
    lamp on and its pool of light, the farmhouse window, the crossing's red lamps."""
    from px import glow, to_dusk
    cv = to_dusk(hero(cat=False))
    _stars(cv, 40, 3)
    # the canopy lamp at the roof's left end, and its light on the platform
    lx = 252
    cv.vline(lx, 7, 12, "n1")
    cv.sprite(["kkkk", "kLLk", ".ll."], {"k": "n1", "L": "lamp0", "l": "lamp1"}, lx - 1, 12)
    glow(cv, lx + 1, 14, 9, 6, "lamp1", 0.55)
    glow(cv, lx + 10, 122, 46, 9, "lamp1", 0.32)
    # the clock's face lit from inside
    glow(cv, 338, 22, 7, 7, "lamp1", 0.25)
    # the farmhouse window
    cv.rect(111, 87, 113, 90, "lamp1")
    glow(cv, 112, 88, 6, 4, "lamp2", 0.4)
    # the crossing's lamps glowing red
    for x in (178, 183):
        glow(cv, x, 77, 3.5, 3.5, "r3", 0.6)
    return cv


def railcar_dusk(frame=0):
    """The railcar at dusk: its windows lit, the headlight on."""
    from px import recolour
    cv = recolour(railcar(frame), {"n2": "lamp1", "k3": "lamp0", "c1": "d-c1", "c0": "d-c0", "c2": "d-c2",
                                   "r2": "r1", "r3": "r2", "t1": "d-t1", "t2": "d-t2"})
    cv.px(0, 9, "lamp0")
    return cv


def status_dusk():
    from px import glow, to_dusk
    cv = to_dusk(status())
    x = cv.w // 2 + 30
    glow(cv, x, 12, 3, 3, "r3", 0.7)
    return cv


def status_sky_dusk():
    """The dusk sky tile under the strip: indigo over apricot, a few rose clouds, early stars."""
    from px import to_dusk
    cv = to_dusk(status_sky())
    _stars(cv, 8, 9, only=("d-k1", "d-k2"))
    return cv


def train_far_dusk(frame=0):
    from px import recolour
    cv = recolour(train_far(frame), {"n2": "lamp1", "k3": "lamp0", "c1": "d-c1", "c0": "d-c0", "c2": "d-c2",
                                     "r2": "r1", "r3": "r2", "t1": "d-t1", "t2": "d-t2"})
    cv.px(1, 17, "lamp0")
    return cv


def office_dusk():
    """The office after the last train: the window at dusk, the hand lamp lit."""
    from px import glow, to_dusk
    cv = to_dusk(office())
    glow(cv, 182, 29, 14, 12, "lamp1", 0.5)
    cv.rect(180, 26, 185, 31, "lamp0")
    glow(cv, 60, 70, 60, 16, "lamp2", 0.15)
    return cv


def swallows(frame=0):
    """16 × 7: two swallows skimming the line, wings up then down (2 frames): they cross the
    status strip now and then, in both schemes."""
    cv = Cv(16, 7)
    up = ["k...k", ".kkk.", "..k.."]
    down = [".....", "kkkkk", "k.k.k"]
    for x, y in ((0, 1), (9, 3)):
        cv.sprite((up, down)[(frame + (x > 0)) % 2], {"k": "n1"}, x, y)
        cv.px(x + 2, y + 3, "n1")  # the forked tail
        cv.px(x + 3, y + 4, "n1")
    return cv
