"""Writes themes/pure/sprites.json and flavor.json: Pure's pieces, drawn with squares.

c = the light (white in the dark, black ink in the light: pieces are the negative of each other
in the two schemes), C = the light dimmed, l = a mid grey (a cast shadow), n = a deep tone,
k = the ground (a hole cut into a piece). One pixel is one square; nothing is round but the moon
and the person."""
import json, os, tempfile

OUT = "themes/pure"


class G:
    def __init__(self, w=16, h=16):
        self.w, self.h = w, h
        self.px = [["."] * w for _ in range(h)]

    def dot(self, x, y, c="c"):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c
        return self

    def rect(self, x, y, w, h, c="c"):
        for j in range(y, y + h):
            for i in range(x, x + w):
                self.dot(i, j, c)
        return self

    def frame(self, x, y, w, h, c="c"):
        for i in range(x, x + w):
            self.dot(i, y, c).dot(i, y + h - 1, c)
        for j in range(y, y + h):
            self.dot(x, j, c).dot(x + w - 1, j, c)
        return self

    def hline(self, x0, x1, y, c="c"):
        return self.rect(x0, y, x1 - x0 + 1, 1, c)

    def vline(self, x, y0, y1, c="c"):
        return self.rect(x, y0, 1, y1 - y0 + 1, c)

    def dots(self, pts, c="c"):
        for x, y in pts:
            self.dot(x, y, c)
        return self

    def disc(self, cx, cy, r, c="c"):
        for j in range(self.h):
            for i in range(self.w):
                if (i + 0.5 - cx) ** 2 + (j + 0.5 - cy) ** 2 <= r * r:
                    self.dot(i, j, c)
        return self

    def rows(self):
        return ["".join(r) for r in self.px]


def text(rows):
    g = G(len(rows[0]), len(rows))
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            g.dot(x, y, ch)
    return g


glyphs = {}

# ---------------------------------------------------------------- Nox: a square of light
def nox(eyes, body="c", extra=()):
    g = G()
    g.rect(3, 3, 10, 10, body)
    # its shadow on the floor, thrown to the lower right by the one sun
    g.hline(5, 14, 13, "l").hline(6, 15, 14, "l")
    g.rect(13, 5, 1, 8, "l").rect(14, 7, 1, 7, "l")
    g.dots(eyes, "k")
    for x, y, c in extra:
        g.dot(x, y, c)
    return g.rows()

EYES = [(5, 6), (6, 6), (5, 7), (6, 7), (9, 6), (10, 6), (9, 7), (10, 7)]
glyphs["nox.idle"] = nox(EYES)
glyphs["nox.blink"] = nox([(5, 7), (6, 7), (9, 7), (10, 7)])
glyphs["nox.listening"] = nox([(5, 5), (6, 5), (5, 6), (6, 6), (9, 5), (10, 5), (9, 6), (10, 6)],
                              extra=[(14, 3, "C"), (15, 1, "C"), (15, 2, "C"), (15, 4, "C"), (15, 5, "C")])
glyphs["nox.thinking"] = nox([(4, 5), (5, 5), (8, 5), (9, 5)], extra=[(12, 1, "C"), (14, 0, "c"), (10, 1, "C")])
glyphs["nox.happy"] = nox([(5, 6), (6, 6), (4, 7), (7, 7), (9, 6), (10, 6), (8, 7), (11, 7),
                           (6, 10), (7, 10), (8, 10), (9, 10), (5, 9), (10, 9)])
glyphs["nox.error"] = nox([(4, 5), (6, 5), (5, 6), (4, 7), (6, 7), (9, 5), (11, 5), (10, 6), (9, 7), (11, 7)], body="C")

# ---------------------------------------------------------------- avatars (16 × 16 fills the ring)
moon = G().disc(8, 8, 6.6, "l").disc(10.2, 6.6, 5.6, ".")
moon = G().disc(8, 8, 6.6, "c")
for j in range(16):
    for i in range(16):
        if (i + 0.5 - 10.4) ** 2 + (j + 0.5 - 6.4) ** 2 <= 5.4 ** 2:
            moon.dot(i, j, "." if moon.px[j][i] != "." else ".")
glyphs["avatar.moon"] = moon.rows()
glyphs["avatar.bat"] = text([
    "................",
    "................",
    "................",
    "......c..c......",
    "......cccc......",
    "c.....cccc.....c",
    "cc...cccccc...cc",
    "ccc.cccccccc.ccc",
    "cccccccccccccccc",
    "cccccccccccccccc",
    "cc.cc.cccc.cc.cc",
    "c...c..cc..c...c",
    ".......cc.......",
    "................",
    "................",
    "................"]).rows()
glyphs["avatar.raven"] = text([
    "................",
    "................",
    ".........cccc...",
    "........cccccc..",
    "........cckccccc",
    "........cccccc..",
    "......ccccccc...",
    "....ccccccccc...",
    "..ccccccccccc...",
    ".cccccccccccc...",
    "cccccccccccc....",
    "cc...ccccccc....",
    "........c..c....",
    "........c..c....",
    ".......cc.cc....",
    "................"]).rows()
rose = G()
# a square rose: petals as a square spiral turning in to its heart
rose.frame(1, 1, 14, 14).rect(1, 1, 3, 1, ".")
rose.frame(3, 3, 10, 10).rect(10, 12, 3, 1, ".")
rose.frame(5, 5, 6, 6).rect(5, 5, 1, 3, ".")
rose.rect(7, 7, 2, 2)
glyphs["avatar.rose"] = rose.rows()
glyphs["avatar.ghost"] = text([
    "................",
    "....cccccccc....",
    "...cccccccccc...",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..ccc..cc..ccc..",
    "..ccc..cc..ccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..ccccc..ccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cc.cccc.cccc..",
    "..c...cc...cc...",
    "................"]).rows()

# ---------------------------------------------------------------- room marks: each room's opening, as in
# its header: a thin frame (the wall's edge) and the light that falls through it
def mark(draw):
    g = G()
    draw(g)
    return g.rows()

def slant(g, x, y0, y1, c="c"):   # a blade of sun, one pixel wide, falling to the right
    for i, y in enumerate(range(y0, y1 + 1)):
        g.dot(x + i // 2, y, c)

glyphs["room.home"] = mark(lambda g: (g.frame(1, 1, 14, 14, "C"), slant(g, 4, 2, 13), slant(g, 5, 2, 13)))
glyphs["room.listen"] = mark(lambda g: [g.vline(x, 8 - h, 7 + h) for x, h in ((3, 1), (5, 3), (7, 5), (9, 4), (11, 2))])
glyphs["room.watch"] = mark(lambda g: (g.frame(1, 4, 14, 7), g.hline(5, 10, 13, "C")))
glyphs["room.house"] = mark(lambda g: [g.rect(x, y, 3, 3) for x in (2, 7, 12) for y in (4, 9)] if False else
                            [g.rect(x, y, 2, 2) for x in (3, 7, 11) for y in (5, 9)])
glyphs["room.files"] = mark(lambda g: [g.hline(2, 13, y) for y in (3, 6, 9, 12)])
glyphs["room.smart-home"] = mark(lambda g: (g.frame(4, 2, 8, 8), g.rect(6, 4, 4, 4, "C"), g.hline(4, 11, 12)))
glyphs["room.games"] = mark(lambda g: (g.frame(2, 2, 6, 6), g.rect(8, 8, 6, 6, "C"), g.frame(8, 8, 6, 6)))
glyphs["room.more"] = mark(lambda g: [g.rect(x, 7, 2, 2) for x in (3, 7, 11)])
glyphs["room.me"] = G().disc(8, 8, 6.5).disc(8, 8, 5.5, ".").rows()

# every mark throws a shadow of the ground's colour, one pixel to the lower right (the sun's
# direction): unseen on the page, it draws the mark when the room is the current one, a solid block
def shadowed(rows):
    g = text(rows)
    for y in range(g.h - 1, -1, -1):
        for x in range(g.w - 1, -1, -1):
            if rows[y][x] != "." and x + 1 < g.w and y + 1 < g.h and rows[y + 1][x + 1] == ".":
                g.dot(x + 1, y + 1, "k")
    return g.rows()

for k in [k for k in glyphs if k.startswith("room.")]:
    glyphs[k] = shadowed(glyphs[k])

# ---------------------------------------------------------------- transport (9 × 9)
def t(rows):
    return text(rows).rows()
glyphs["transport.play"] = t(["cc.......", "cccc.....", "cccccc...", "cccccccc.", "ccccccccc", "cccccccc.", "cccccc...", "cccc.....", "cc......."])
glyphs["transport.pause"] = t(["ccc...ccc"] * 9)
glyphs["transport.stop"] = t(["ccccccccc"] * 9)
glyphs["transport.next"] = t(["c.....cc.", "ccc...cc.", "ccccc.cc.", "cccccccc.", "cccccccc.", "cccccccc.", "ccccc.cc.", "ccc...cc.", "c.....cc."])
glyphs["transport.previous"] = t([r[::-1] for r in glyphs["transport.next"]])

# ---------------------------------------------------------------- medals: a plaque, a mark on it
def medal(draw):
    g = G()
    g.frame(0, 0, 16, 16, "C")
    draw(g)
    return g.rows()

# the medals: one plaque, one geometric mark each (stairs, slits, nested squares, lines of light)
M = {}
M["dj"] = lambda g: (g.frame(3, 3, 10, 10), g.frame(5, 5, 6, 6), g.rect(7, 7, 2, 2))
M["explorer"] = lambda g: [g.rect(3 + 2 * i, 11 - 2 * i, 2, 2 + 2 * i) for i in range(5)]
M["night_owl"] = lambda g: (g.frame(3, 3, 10, 10, "C"), g.rect(9, 5, 2, 2))
M["early_bird"] = lambda g: (g.hline(3, 12, 11), g.rect(6, 8, 4, 3))
M["weekend"] = lambda g: (g.rect(4, 4, 3, 8), g.rect(9, 4, 3, 8))
M["genre_guardian"] = lambda g: (g.frame(4, 3, 8, 10), g.vline(7, 5, 10), g.vline(8, 5, 10))
M["broken_record"] = lambda g: (g.frame(3, 3, 10, 10), g.frame(5, 5, 6, 6), g.rect(7, 7, 2, 2), g.rect(10, 3, 3, 3, "."), g.rect(10, 5, 1, 1, "."))
def meander(g):  # a Greek-key corridor, walked end to end
    for x0 in (2, 8):
        g.vline(x0, 4, 11).hline(x0, x0 + 5, 4).vline(x0 + 5, 4, 9).hline(x0 + 2, x0 + 5, 9).vline(x0 + 2, 6, 9).hline(x0 + 2, x0 + 3, 6)
    g.hline(2, 13, 11)
M["marathon"] = meander
M["radio_host"] = lambda g: (g.rect(3, 11, 2, 2), g.hline(3, 7, 8), g.vline(7, 8, 12), g.hline(3, 10, 5), g.vline(10, 5, 12), g.hline(3, 13, 2), g.vline(13, 2, 12))
M["task_hero"] = lambda g: (g.vline(10, 1, 9), g.rect(9, 10, 3, 3), g.hline(3, 5, 12), g.vline(3, 4, 12))  # square and plumb
M["grocery_runner"] = lambda g: (g.hline(2, 13, 7), g.hline(2, 13, 13), g.rect(4, 4, 2, 3), g.rect(8, 5, 3, 2),
                                  g.rect(3, 10, 3, 3), g.rect(10, 10, 2, 3))
M["planner"] = lambda g: ([g.frame(3 + 4 * i, 3 + 4 * j, 3, 3) for i in range(3) for j in range(3)], g.rect(7, 7, 3, 3))
M["wall_poet"] = lambda g: [g.hline(3, 3 + n, y) for y, n in ((3, 9), (5, 7), (7, 9), (9, 5), (11, 8))]
M["courier"] = lambda g: (g.frame(2, 3, 8, 10), g.vline(9, 6, 9, "."), g.rect(11, 7, 2, 2))
M["curator"] = lambda g: (g.frame(2, 2, 12, 12), g.frame(4, 4, 8, 8, "C"), g.rect(6, 6, 4, 4))
M["high_scorer"] = lambda g: [g.rect(3 + 3 * i, 12 - 2 * i - 1, 2, 2 * i + 2) for i in range(4)]
M["collector"] = lambda g: [g.rect(3 + 6 * i, 3 + 6 * j, 4, 4) for i in range(2) for j in range(2)]
M["game_hopper"] = lambda g: [g.rect(x, y, 3, 3) for x, y in ((2, 11), (6, 7), (10, 3))]
M["console_hopper"] = lambda g: [(g.frame(x, 5, 3, 8), g.hline(x + 1, x + 1, 12, ".")) for x in (3, 7, 11)]
M["romhacker"] = lambda g: (g.rect(3, 3, 5, 5), g.rect(9, 3, 4, 5), g.rect(3, 9, 5, 4), g.rect(10, 10, 4, 4))
for k, f in M.items():
    glyphs["title." + k] = medal(f)

for k, rows in glyphs.items():
    assert len(rows) <= 16 and all(len(r) == len(rows[0]) <= 16 for r in rows), k

sprites = {
    "$description": "Pure: pieces made of squares of light. c is the light (white in the dark, ink in the light scheme), l its shadow, k a hole to the ground.",
    "palette": {"c": "light", "C": "light-dim", "l": "mid-dark", "n": "dark", "k": "outline"},
    "glyphs": glyphs,
}

T = {
    "dj": ("The resonant room", "La salle qui résonne"),
    "explorer": ("Every stair climbed", "Toutes les marches"),
    "night_owl": ("After the last light", "Après la dernière lueur"),
    "early_bird": ("First light", "Première lumière"),
    "weekend": ("Long shadows", "Les ombres longues"),
    "genre_guardian": ("Keeper of {genre}", "Gardien du genre {genre}"),
    "broken_record": ("One note, again", "Une seule note, encore"),
    "marathon": ("The long corridor", "Le long couloir"),
    "radio_host": ("Voice in the hall", "La voix dans le hall"),
    "task_hero": ("Square and plumb", "D’équerre et d’aplomb"),
    "grocery_runner": ("Keeper of the larder", "Gardien du garde-manger"),
    "planner": ("On the grid", "Sur la trame"),
    "wall_poet": ("Words on concrete", "Des mots sur le béton"),
    "courier": ("Through the opening", "Par l’ouverture"),
    "curator": ("The gallery wall", "Le mur de la galerie"),
    "high_scorer": ("Top of the stairs", "En haut de l’escalier"),
    "collector": ("A full shelf", "L’étagère pleine"),
    "game_hopper": ("Room to room", "De pièce en pièce"),
    "console_hopper": ("Every doorway", "Chaque embrasure"),
    "romhacker": ("Rebuilt by hand", "Rebâti à la main"),
}
flavor = {"$description": "Pure: the house titles, named for light, stairs and concrete. English and French (tu)."}
for k, (en, fr) in T.items():
    assert len(en) <= 28 and len(fr) <= 28, k
    flavor[f"title.{k}.name"] = {"en": en, "fr": fr}
flavor["title.star.mark"] = {"en": "■", "fr": "■"}


def write(name, data):
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, os.path.join(OUT, name))


write("sprites.json", sprites)
write("flavor.json", flavor)
print(len(glyphs), "pieces")
