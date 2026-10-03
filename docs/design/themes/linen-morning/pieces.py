"""Kinari's pieces (sprites.json): the five avatars, Nox's six moods and the twenty title
medals, drawn as carved stamps: kamon discs in sumi and washi, the hanko red used on a few.
Room marks and transport keys stay HouseOS's pen-line icons on purpose: pen for the interface,
stamps for the pieces.

    python3 docs/design/themes/linen-morning/pieces.py            # writes sprites.json
    python3 docs/design/themes/linen-morning/pieces.py --show     # prints every grid
"""

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "themes/linen-morning/sprites.json"
N = 16
SS = 8  # supersampling for the geometry


# ---------- geometry on a 16 × 16 grid (pixel centres at i + 0.5) ----------
def shape(test, thr=0.5):
    """Cells whose coverage by `test(x, y)` is at least thr."""
    out = set()
    for j in range(N):
        for i in range(N):
            hit = sum(test(i + (a + 0.5) / SS, j + (b + 0.5) / SS) for a in range(SS) for b in range(SS))
            if hit / SS / SS >= thr:
                out.add((i, j))
    return out


def circle(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def poly(points):
    def inside(x, y):
        c = False
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
            if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
                c = not c
        return c

    return inside


def minus(a, b):
    return lambda x, y: a(x, y) and not b(x, y)


def union(*fs):
    return lambda x, y: any(f(x, y) for f in fs)


def ellipse(cx, cy, rx, ry, ang=0):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))

    def f(x, y):
        dx, dy = x - cx, y - cy
        u, v = dx * ca + dy * sa, -dx * sa + dy * ca
        return (u / rx) ** 2 + (v / ry) ** 2 <= 1

    return f


def rectf(x0, y0, x1, y1):
    return lambda x, y: x0 <= x <= x1 and y0 <= y <= y1


def ring(cx, cy, r0, r1):
    return lambda x, y: r0 * r0 <= (x - cx) ** 2 + (y - cy) ** 2 <= r1 * r1


class Grid:
    def __init__(self, w=N, h=N):
        self.w, self.h = w, h
        self.g = [["."] * w for _ in range(h)]

    def fill(self, cells, letter):
        for i, j in cells:
            if 0 <= i < self.w and 0 <= j < self.h:
                self.g[j][i] = letter
        return self

    def put(self, rows, letter_map=None, x=0, y=0):
        """Hand-drawn rows over the grid ('.' keeps what is there)."""
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch != "." and 0 <= x + i < self.w and 0 <= y + j < self.h:
                    self.g[y + j][x + i] = (letter_map or {}).get(ch, ch)
        return self

    def rows(self):
        return ["".join(r) for r in self.g]


SOLID = [
    ".....kkkkkk.....",
    "...kkkkkkkkkk...",
    "..kkkkkkkkkkkk..",
    ".kkkkkkkkkkkkkk.",
    ".kkkkkkkkkkkkkk.",
    "kkkkkkkkkkkkkkkk",
    "kkkkkkkkkkkkkkkk",
    "kkkkkkkkkkkkkkkk",
    "kkkkkkkkkkkkkkkk",
    "kkkkkkkkkkkkkkkk",
    "kkkkkkkkkkkkkkkk",
    ".kkkkkkkkkkkkkk.",
    ".kkkkkkkkkkkkkk.",
    "..kkkkkkkkkkkk..",
    "...kkkkkkkkkk...",
    ".....kkkkkk.....",
]
RING = [
    ".....kkkkkk.....",
    "...kkkkkkkkkk...",
    "..kkkPPPPPPkkk..",
    ".kkPPPPPPPPPPkk.",
    ".kkPPPPPPPPPPkk.",
    "kkPPPPPPPPPPPPkk",
    "kkPPPPPPPPPPPPkk",
    "kkPPPPPPPPPPPPkk",
    "kkPPPPPPPPPPPPkk",
    "kkPPPPPPPPPPPPkk",
    "kkPPPPPPPPPPPPkk",
    ".kkPPPPPPPPPPkk.",
    ".kkPPPPPPPPPPkk.",
    "..kkkPPPPPPkkk..",
    "...kkkkkkkkkk...",
    ".....kkkkkk.....",
]


FIELD = [
    ".....kkkkkk.....",
    "...kkPPPPPPkk...",
    "..kPPPPPPPPPPk..",
    ".kPPPPPPPPPPPPk.",
    ".kPPPPPPPPPPPPk.",
    "kPPPPPPPPPPPPPPk",
    "kPPPPPPPPPPPPPPk",
    "kPPPPPPPPPPPPPPk",
    "kPPPPPPPPPPPPPPk",
    "kPPPPPPPPPPPPPPk",
    "kPPPPPPPPPPPPPPk",
    ".kPPPPPPPPPPPPk.",
    ".kPPPPPPPPPPPPk.",
    "..kPPPPPPPPPPk..",
    "...kkPPPPPPkk...",
    ".....kkkkkk.....",
]


def sumi_disc():
    """An avatar: a fine sumi ring on a washi field, its motif in sumi."""
    return Grid().put(FIELD)


def ink(rows):
    """Motif rows drawn with P become sumi on the avatar's washi field."""
    return [r.replace("P", "k") for r in rows]


def medal():
    """A medal: a washi disc in a heavy sumi ring (a kamon)."""
    return Grid().put(RING)


# ---------- avatars ----------
def avatars():
    out = {}
    g = sumi_disc()
    g.fill(shape(minus(circle(7.6, 8.2, 5.0), circle(9.8, 6.8, 4.4))), "k")
    out["avatar.moon"] = g
    out["avatar.bat"] = sumi_disc().put(ink([  # a bat crest, wings spread and scalloped
        "................",
        "................",
        "................",
        "................",
        "......P..P......",
        "......PPPP......",
        ".PP...PPPP...PP.",
        "..PPPPPPPPPPPP..",
        "...PPPPPPPPPP...",
        "....PPPPPPPP....",
        "....P.PPPP.P....",
        ".......PP.......",
        "................",
    ]))
    g = sumi_disc()  # a crow, in profile, sumi on washi
    crow = union(ellipse(8.2, 9, 3.9, 2.6, -18), circle(11.4, 6.4, 1.9), poly([(12.8, 5.8), (15, 6.6), (12.8, 7.2)]),
                 poly([(4.8, 9.6), (1.6, 11.2), (2.2, 12), (5.6, 10.8)]))
    g.fill(shape(crow, 0.45), "k")
    g.fill({(11, 6)}, "P")
    g.fill({(7, 12), (9, 12)}, "k")
    out["avatar.raven"] = g
    g = sumi_disc()  # a camellia: five sumi petals, a small red heart
    petals = union(*[circle(8 + 3.1 * math.cos(math.radians(-90 + k * 72)), 8 + 3.1 * math.sin(math.radians(-90 + k * 72)), 2.5) for k in range(5)])
    g.fill(shape(petals, 0.45), "k")
    g.fill(shape(circle(8, 8, 2.0)), "L")
    g.fill({(8, 8), (7, 8), (8, 7), (7, 7)}, "e")
    out["avatar.rose"] = g
    out["avatar.ghost"] = sumi_disc().put(ink([  # a little ghost, its tail trailing
        "................",
        "................",
        "................",
        "......PPPP......",
        ".....PPPPPP.....",
        "....PPPPPPPP....",
        "....PkPPPkPP....",
        "....PPPPPPPP....",
        "....PPPPPPPP....",
        "....PPPPPPPP....",
        "....PP.PP.PPP...",
        "....P..P...PPP..",
        "..............P.",
    ]))
    out["avatar.ghost"].g[6][5] = "P"
    out["avatar.ghost"].g[6][9] = "P"
    return out


# ---------- Nox: an ink cat, sitting ----------
CAT = [
    "................",
    "...k........k...",
    "...kk......kk...",
    "...kkk....kkk...",
    "...kkkkkkkkkk...",
    "..kkkkkkkkkkkk..",
    "..kkkkkkkkkkkk..",
    "..kkkkkkkkkkkk..",
    "..kkkkkkkkkkkk..",
    "...kkkkkkkkkk...",
    "....kkkkkkkk....",
    "...kkkkkkkkkk...",
    "..kkkkkkkkkkkk..",
    "..kkkkkkkkkkkk.k",
    "..kkkkkkkkkkkkkk",
    "...kkkkkkkkkkkk.",
]


def cat(eyes, mouth=None, ears=None, extra=None):
    g = Grid().put(CAT)
    if ears == "up":  # listening: taller ears
        g.put(["...k........k...", "...kk......kk..."], y=0)
        g.put(["..k..........k..", "..kk........kk.."], y=0)
        g.g[0][3] = "."; g.g[0][12] = "."
    for (i, j), ch in eyes.items():
        g.g[j][i] = ch
    for (i, j), ch in (mouth or {}).items():
        g.g[j][i] = ch
    for (i, j), ch in (extra or {}).items():
        g.g[j][i] = ch
    return g


def nox():
    open_eyes = {(5, 6): "C", (6, 6): "C", (9, 6): "C", (10, 6): "C", (5, 7): "C", (6, 7): "k", (9, 7): "k", (10, 7): "C"}
    nose = {(7, 8): "e", (8, 8): "e"}
    out = {}
    out["nox.idle"] = cat(open_eyes, nose)
    out["nox.blink"] = cat({(5, 7): "m", (6, 7): "m", (9, 7): "m", (10, 7): "m"}, nose)
    out["nox.listening"] = cat({**open_eyes, (6, 6): "C", (9, 6): "C", (6, 7): "k", (9, 7): "k"}, nose, ears="up")
    # thinking: eyes closed low, three small dots rising beside the head
    out["nox.thinking"] = cat({(5, 7): "m", (6, 7): "m", (9, 7): "m", (10, 7): "m"}, nose,
                              extra={(14, 3): "L", (15, 1): "L", (13, 5): "L"})
    # happy: smiling eyes (arches) and a red blush of the seal colour
    out["nox.happy"] = cat({(5, 7): "C", (6, 6): "C", (7, 7): "C", (8, 7): "C", (9, 6): "C", (10, 7): "C"},
                           {(7, 9): "e", (8, 9): "e"}, extra={(3, 8): "E", (12, 8): "E"})
    out["nox.happy"].g[7][7] = "k"; out["nox.happy"].g[7][8] = "k"
    out["nox.happy"].g[7][6] = "k"; out["nox.happy"].g[7][9] = "k"
    out["nox.happy"].g[6][5] = "k"; out["nox.happy"].g[6][10] = "k"
    out["nox.happy"].g[7][5] = "C"; out["nox.happy"].g[7][10] = "C"
    # error: crossed eyes, ears flat
    err = {(5, 6): "C", (6, 7): "C", (6, 6): "k", (5, 7): "k", (9, 6): "k", (10, 6): "C", (9, 7): "C", (10, 7): "k"}
    g = cat(err, {(7, 9): "C", (8, 9): "C"})
    g.put(["................", "................", "..kkk......kkk..", "..kkkk....kkkk.."], y=0)
    out["nox.error"] = g
    return out


# ---------- medals: kamon, one motif each ----------
def medals():
    m = {}

    def M(name, *layers):
        g = medal()
        for cells, letter in layers:
            g.fill(cells, letter)
        m["title." + name] = g

    # dj: a record, its grooves and the red label
    M("dj", (shape(circle(8, 8, 5.2)), "k"), (shape(ring(8, 8, 3.2, 3.9), 0.5), "n"), (shape(circle(8, 8, 1.9)), "n"), ({(8, 8), (7, 8), (8, 7), (7, 7)}, "e"))
    # explorer: a mountain with its snow
    M("explorer", (shape(poly([(2.4, 12), (8, 3.2), (13.6, 12)])), "k"), (shape(poly([(6.2, 6.1), (8, 3.2), (9.8, 6.1), (8.8, 7), (8, 6.2), (7.2, 7)]), 0.45), "P"))
    # night owl: a crescent and one star
    M("night_owl", (shape(minus(circle(7.2, 8.4, 4.6), circle(9.2, 7.0, 4.0))), "k"), ({(11, 4), (12, 5), (11, 5), (10, 5), (11, 6)}, "L"))
    # early bird: the sun rising over a line
    M("early_bird", (shape(minus(circle(8, 10.5, 4.2), rectf(0, 10.5, 16, 16))), "n"), ({(7, 9), (8, 9)}, "e"), (shape(rectf(2.5, 11.2, 13.5, 12.2)), "k"),
      ({(3, 6), (4, 7), (12, 6), (11, 7), (8, 3), (8, 4)}, "k"))
    # weekend: a tea bowl, steam
    M("weekend", (shape(minus(ellipse(8, 8.6, 4.8, 3.6), rectf(0, 0, 16, 8.4))), "k"), (shape(rectf(3.2, 8.2, 12.8, 8.9)), "k"),
      ({(6, 5), (7, 4), (6, 3), (9, 6), (10, 5), (9, 4)}, "L"))
    # genre guardian: a shrine gate
    M("genre_guardian", (shape(union(rectf(2.6, 4.2, 13.4, 5.4), rectf(3.6, 6.6, 12.4, 7.4), rectf(4.6, 5, 5.8, 12.6), rectf(10.2, 5, 11.4, 12.6))), "k"),
      ({(7, 5), (8, 5)}, "e"))
    # broken record: a ring cracked through
    M("broken_record", (shape(ring(8, 8, 2.4, 5.2)), "k"), (shape(poly([(8.4, 2), (9.6, 2), (8.2, 8), (9.4, 8), (7.6, 14), (6.6, 14), (7.6, 9), (6.6, 9)]), 0.4), "P"))
    # marathon: a tortoise shell (kikkō), endurance
    m["title.marathon"] = medal().put([
        "................",
        "................",
        "................",
        "......kkkk......",
        ".....kLLLLk.....",
        "....kLkkkkLk....",
        "...kLkLLLLkLk...",
        "...kLkLLLLkLk...",
        "...kLkLLLLkLk...",
        "...kLkLLLLkLk...",
        "....kLkkkkLk....",
        ".....kLLLLk.....",
        "......kkkk......",
    ])
    # radio host: a round bell (suzu), its loop and its slit
    m["title.radio_host"] = medal().put([
        "................",
        "................",
        "................",
        ".......kk.......",
        "......k..k......",
        ".....kkkkkk.....",
        "....kLLLLLLk....",
        "...kLmLLLLLLk...",
        "...kLLLLLLLLk...",
        "...kkkkkkkkkk...",
        "...kLLLkkLLLk...",
        "....kLLkkLLk....",
        ".....kkkkkk.....",
    ])
    # task hero: a broom, leaning
    m["title.task_hero"] = medal().put([
        "................",
        "................",
        "............n...",
        "...........n....",
        "..........n.....",
        ".........n......",
        "........n.......",
        ".......kk.......",
        "......LLLk......",
        ".....LkLkLk.....",
        "....LkLkLkL.....",
        "...LkLkLkL......",
        "....LLLkL.......",
    ])
    # grocery runner: a daikon, its leaves
    M("grocery_runner", (shape(poly([(5.6, 7), (10.4, 7), (8.6, 13.6), (7.4, 13.6)]), 0.45), "C"), (shape(poly([(5.6, 7), (10.4, 7), (8.6, 13.6), (7.4, 13.6)]), 0.45) - shape(poly([(6.2, 7.6), (9.8, 7.6), (8.2, 12.8), (7.8, 12.8)]), 0.45), "k"),
      (shape(union(ellipse(6.2, 4.6, 1.2, 2.6, -20), ellipse(9.8, 4.6, 1.2, 2.6, 20), ellipse(8, 4.0, 1.0, 2.8))), "g"))
    # planner: an open folding fan
    m["title.planner"] = medal().put([
        "................",
        "................",
        "................",
        "....kkkkkkkk....",
        "...kLkLLkLLkk...",
        "...kLkLkLkLLk...",
        "....kLkLkLLk....",
        "....kLLkLkLk....",
        ".....kLkLkk.....",
        ".....kLkkLk.....",
        "......kkkk......",
        ".......kk.......",
        ".......ee.......",
    ])
    # wall poet: a brush, its tip wet with red
    M("wall_poet", (shape(poly([(11.6, 2.6), (12.8, 3.8), (6.2, 10.4), (5, 9.2)]), 0.4), "n"), (shape(poly([(5, 9.2), (6.2, 10.4), (4.6, 12.6), (3.2, 12.8), (3.4, 11.4)]), 0.4), "k"),
      ({(3, 12)}, "e"))
    # courier: a folded letter tied with a knot
    M("courier", (shape(rectf(3.2, 5.2, 12.8, 11.2)), "C"), (shape(rectf(3.2, 5.2, 12.8, 11.2)) - shape(rectf(4.2, 6.2, 11.8, 10.2)), "k"),
      ({(4, 6), (5, 7), (6, 7), (7, 8), (8, 8), (9, 7), (10, 7), (11, 6)}, "k"), (shape(rectf(7.4, 4.2, 8.6, 12.2)), "n"), ({(7, 8), (8, 8)}, "e"))
    # curator: a vase with one flowering branch
    m["title.curator"] = medal().put([
        "................",
        "................",
        "..........e.....",
        "......e..n......",
        ".......n.n......",
        "........nn......",
        ".......kk.......",
        ".......kk.......",
        "......kkkk......",
        ".....kkkkkk.....",
        ".....kkkkkk.....",
        "......kkkk......",
        ".......kk.......",
    ])
    # high scorer: a gourd with its red cord
    m["title.high_scorer"] = medal().put([
        "................",
        "................",
        "........k.......",
        ".......kLk......",
        "......kLLLk.....",
        "......kLLLk.....",
        ".......eee......",
        "......kLLLk.....",
        ".....kLmLLLk....",
        ".....kLLLLLk....",
        ".....kLLLLLk....",
        "......kLLLk.....",
        ".......kkk......",
    ])
    # collector: a scallop shell
    m["title.collector"] = medal().put([
        "................",
        "................",
        "................",
        ".....kkkkkk.....",
        "....kLkLLkLk....",
        "...kLLkLLkLLk...",
        "...kLkLLLLkLk...",
        "...kLkLLLLkLk...",
        "....kLkLLkLk....",
        ".....kLkkLk.....",
        "......kLLk......",
        ".....kkkkkk.....",
        "................",
    ])
    # game hopper: a spinning top
    M("game_hopper", (shape(poly([(3, 7.2), (13, 7.2), (8, 13.4)])), "k"), (shape(rectf(3, 7.2, 13, 8.4)), "n"), ({(7, 7), (8, 7)}, "e"), (shape(rectf(7.4, 3, 8.6, 7.2)), "n"))
    # console hopper: a kendama: the ball above its cup
    M("console_hopper", (shape(circle(8, 5.4, 2.6)), "n"), ({(7, 4), (8, 4)}, "e"), (shape(union(rectf(4.2, 9, 11.8, 10.2), rectf(7.4, 10, 8.6, 13.2), rectf(5, 8.2, 6, 9.2), rectf(10, 8.2, 11, 9.2))), "k"))
    # romhacker: a key, old iron
    M("romhacker", (shape(ring(5.8, 8, 1.4, 2.8)), "k"), (shape(rectf(8.4, 7.4, 13, 8.6)), "k"), (shape(union(rectf(11, 8.4, 12, 10.4), rectf(12.6, 8.4, 13.4, 9.8))), "k"))
    return m


def build():
    pieces = {**avatars(), **nox(), **medals()}
    # "rose" etc keep their ids; every grid is 16 × 16
    return {
        "$description": "Kinari: the pieces as carved stamps. Kamon discs in sumi and washi, the hanko red on a few, Nox an ink cat. Drawn by code (docs/design/themes/linen-morning/pieces.py).",
        "palette": {"k": "outline", "n": "dark", "l": "mid-dark", "L": "mid", "m": "mist", "C": "light-dim",
                    "e": "accent", "E": "accent-hi", "r": "accent-deep", "g": "good", "P": "paper"},
        "glyphs": {k: v.rows() for k, v in pieces.items()},
    }


if __name__ == "__main__":
    data = build()
    if "--show" in sys.argv:
        for name, rows in data["glyphs"].items():
            print(name)
            print("\n".join(rows))
    tmp = OUT.with_name(".sprites.json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)
    print("wrote", OUT, len(data["glyphs"]), "pieces")
