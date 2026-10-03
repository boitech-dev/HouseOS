"""Bathhouse After Hours: the header banners (286 × 40, 4 × on a desktop header), one per room.

Every banner shares a frieze along its top 8 rows (the part a phone sees above the title): the
lintel's shadow, a band of decorative wall tiles, a hinoki picture rail with small things on its
ledge and wind chimes. Under it, the tiled wall; past the words (x 188 and on, where a phone's
header never looks) each room has its corner of the bathhouse: something to stand on, a main
object 20–32 px tall, a few props, and the pool of a pendant lamp hung high on the left.
Rooms whose header has buttons (Watch, Games, Files) keep their corner's lower part plain,
since the buttons sit over it. Called from make.py (`make.py banners`).
"""

import math
import random

from make import (
    CAT_SLEEP, FRIDGE, FURIN, LAMP, MILK, PLANT, SCALE, STOOL, BASIN,
    dith, done, grid, hline, mosaic, new, put, rect, stamp, vline, get, rgb, onsen_mark,
    recolour,
)

W, H = 286, 40

LANTERN = [  # a red paper lantern (chōchin) on the string (7 × 11)
    "...0...",
    ".00000.",
    "0bbbbb0",
    "0xyxxw0",
    "0xxxxw0",
    "0wwwwv0",
    "0xyxxw0",
    "0xxxxw0",
    "0bbbbb0",
    ".00000.",
    "...l...",
]
UCHIWA = [  # a round paper fan with a painted wave (9 × 13)
    "..00000..",
    ".0hhhhh0.",
    "0hhhEhhh0",
    "0hhEhEhh0",
    "0hEhhhEh0",
    "0hhhhhhh0",
    ".0hhhhh0.",
    "..00e00..",
    "....e....",
    "....e....",
    "....e....",
    "....d....",
    "....0....",
]


# ---------------------------------------------------------------- the wall and the frieze


def wall(im):
    mosaic(im, (0, 0, W, H), "2", "1", size=3, seed=2, chips=("3", 0.04))


def frieze(im):
    """The top 8 rows: lintel shadow, a band of decorative tiles, the picture rail and its ledge."""
    rnd = random.Random(12)
    hline(im, 0, W, 0, "0")
    for x in range(W):
        put(im, x, 1, "0" if dith(0.5, x, 1) else "1")
    # the tile band: 3 px tiles, a jade one now and then, a vermilion one rarely
    for i, x0 in enumerate(range(0, W, 3)):
        c = "4"
        if i % 7 == 3:
            c = "6"
        if i % 23 == 11:
            c = "w"
        rect(im, x0, 2, x0 + 2, 4, c)
        put(im, x0, 2, "5" if c == "4" else "7" if c == "6" else "x")
        vline(im, x0 + 2, 2, 4, "1")
    hline(im, 0, W, 4, "1")
    # the picture rail: lit top, grain, shadow under it
    hline(im, 0, W, 5, "f")
    hline(im, 0, W, 6, "d")
    for x in range(0, W, 9):
        put(im, x + rnd.randint(0, 5), 6, "c")
    hline(im, 0, W, 7, "b")
    # things on the ledge (standing on row 5) and chimes hung from the lintel
    ledge = [
        (14, ["0hh0", "0WW0", "0hh0"]),                       # a milk bottle
        (40, [".xx.", "xyxw", "xxxw", ".ww."]),               # a daruma-red soap tin
        (71, ["hhhh.", "9999W", "hhhhh"]),                    # folded towels
        (104, ["..s.", ".rsr", ".00.", "0ee0"]),              # a potted fern
        (128, ["0hh0", "0WW0", "0hh0"]),
        (161, ["k.k", "kkk", "jkj"]),                         # a yellow basin, upside down
        (232, ["0hh0", "0oo0", "0hh0"]),                      # a fruit milk
        (262, ["hhhh.", "EEEE9", "hhhhh"]),
    ]
    for x, rows in ledge:
        g = grid(rows)
        stamp(im, g, x, 5 - g.height)
    for x in (58, 146, 214):
        chime = grid(FURIN).crop((0, 0, 8, 16))
        small = new(8, 8)
        small.alpha_composite(chime.crop((0, 0, 8, 7)), (0, 0))
        stamp(im, grid(["0", "0"]), x + 3, 0)
        stamp(im, chime.crop((1, 1, 7, 6)), x, 1)
        stamp(im, grid(["0", "h", "g"]), x + 2, 6)


# ---------------------------------------------------------------- shared pieces of a corner


def lamp(im, x, cord_to, pool_to, spread=0.55):
    """A pendant lamp hung from the rail at x; its light falls in a cone to row pool_to: the wall
    tiles in the cone warm a step, softly at the edges (the theme's one light, high on the left)."""
    vline(im, x + 2, 8, cord_to, "0")
    stamp(im, LAMP_G, x - 1, cord_to)
    top = cord_to + 4
    for y in range(top, pool_to):
        half = 2 + (y - top) * spread
        for xx in range(int(x + 2 - half), int(x + 3 + half)):
            if not (0 <= xx < W):
                continue
            edge = min(xx - (x + 2 - half), (x + 3 + half) - xx) / 3
            if edge > 1 or dith(max(0.0, edge), xx, y):
                p = get(im, xx, y)[:3]
                near = (y - top) < (pool_to - top) * 0.45
                warm = {rgb("2")[:3]: "4" if near else "3", rgb("3")[:3]: "5" if near else "4"}
                if p in warm:
                    put(im, xx, y, warm[p])


LAMP_G = grid([  # a larger enamel pendant lamp (7 × 5)
    "..000..",
    ".0ccc0.",
    "0deeed0",
    "0000000",
    ".lWWWl.",
])


def wainscot(im, x0, x1, y):
    """Hinoki boards on the lower wall from row y down, a lit top rail."""
    rect(im, x0, y, x1, H, "c")
    hline(im, x0, x1, y, "f")
    hline(im, x0, x1, y + 1, "e")
    for x in range(x0 + 2, x1, 7):
        vline(im, x, y + 2, H, "b")
        put(im, x + 3, y + 5, "d")


def counter(im, x0, x1, y, h=12):
    """A hinoki counter: its lit top, a front of framed panels."""
    rect(im, x0, y, x1, min(H, y + h), "d")
    hline(im, x0 - 1, x1 + 1, y, "g")
    hline(im, x0 - 1, x1 + 1, y + 1, "e")
    hline(im, x0, x1, y + 2, "c")
    for x in range(x0 + 1, x1 - 6, 8):
        rect(im, x + 1, y + 4, x + 7, min(H, y + h - 1), "c")
        hline(im, x + 1, x + 7, y + 4, "b")
        vline(im, x + 1, y + 4, min(H, y + h - 1), "b")


def pool(im, x0, x1, y, ch="g"):
    """A warm pool of lamplight on a lit surface."""
    for x in range(x0, x1):
        t = 1 - abs((x - (x0 + x1) / 2) / ((x1 - x0) / 2))
        if dith(t, x, y):
            put(im, x, y, ch)


def shadow(im, x0, x1, y):
    """Things cast a short shadow to the right on what they stand on."""
    for x in range(x0, x1):
        p = get(im, x, y)[:3]
        darker = {rgb("g")[:3]: "e", rgb("e")[:3]: "d", rgb("f")[:3]: "e", rgb("d")[:3]: "c"}
        if p in darker:
            put(im, x, y, darker[p])


# ---------------------------------------------------------------- the objects (bigger, detailed)

RADIO_L = grid([  # the counter's tube radio: rounded case, cloth grille, lit dial, knobs (28 × 19)
    "......0000000000000000......",
    "....00eeeeeeeeeeeeeeee00....",
    "...0efffffffffffffffffe0...",
    "..0effgggggggggggggggffe0..",
    ".0efg00000000000000000gfde0.",
    ".0efg0gegegegeg0lhlhlh0gde0.",
    "0efg0egegegegegh0hhhhhh0gde0",
    "0efg0gegegegegeg0hxhhhh0gde0",
    "0efg0egegegegegh0lhlhlh0gde0",
    "0efg0gegegegegeg000000000de0",
    "0efg0egegegegegh0dddddd0gde0",
    "0efg0gegegegegeg0d0dd0d0gde0",
    "0efg00000000000000000000gde0",
    "0efggggggggggggggggggggggde0",
    "0edddddddddddddddddddddddde0",
    "0ed0gg0dddddddddddd0gg0ddde0",
    "0ed0ee0dddddddddddd0ee0ddde0",
    ".0000000000000000000000000.",
    "..00....................00..",
])
TEACUP = grid([  # a teacup, steam curling up (7 × 9)
    "...h...",
    "..h....",
    "...h...",
    "....h..",
    "...h...",
    "0000000",
    "0hhWhh0",
    ".0h9h0.",
    "..000..",
])
TV_L = grid([  # the changing-room TV on its wall bracket, rabbit ears (26 × 18)
    "....0................0....",
    ".....0..............0.....",
    "......0............0......",
    ".......0..........0.......",
    "........000000000.........",
    "000000000000000000000000..",
    "0eeeeeeeeeeeeeeeeeeeeee0..",
    "0ef000000000000000fggce0..",
    "0ef0HGGGFFFFFFFFE0fg0ce0..",
    "0ef0GGFFFFFFFFFFE0fggce0..",
    "0ef0GFFFFFFFFFFEE0fg0ce0..",
    "0ef0FFFFFFFFFFEEE0fggce0..",
    "0ef0FFFFFFFFFEEDE0ccc0e0..",
    "0ef000000000000000cccce0..",
    "0edddddddddddddddddddde0..",
    ".0000000000000000000000...",
    "..........0cc0............",
    "..........0cc0............",
])
ARCADE_L = grid([  # the arcade cabinet by the door (22 × 32)
    ".00000000000000000000.",
    "0MMMMMMMMMMMMMMMMMMMM0",
    "0MzkzkzkzkzkzkzkzkzkM0",
    "0MkzkzkzkzkzkzkzkzkzM0",
    "0MMMMMMMMMMMMMMMMMMMM0",
    "0NN000000000000000NNN0",
    "0NN0AAAAAAAAAAAAA0NNN0",
    "0NN0AAkAAAAAAAxAA0NNN0",
    "0NN0AAAAAAAHAAAAA0NNN0",
    "0NN0AAAAAAAAAAAsA0NNN0",
    "0NN0AxAAAAAAAAAAA0NNN0",
    "0NN0AAAAAkkAAAAAA0NNN0",
    "0NN0AAAAAkkAAAAAA0NNN0",
    "0NN0AAAAAAAAAAAAA0NNN0",
    "0NN000000000000000NNN0",
    "0NNNNNNNNNNNNNNNNNNNN0",
    "00OOOOOOOOOOOOOOOOOO00",
    "0OO0x0OO0k0k0OOOOOOOO0",
    "0OOO0OOOO0O0OOOOOOOOO0",
    "0000000000000000000000",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0NNNN000000000NNNNN0.",
    ".0NNNN0kkk0bbb0NNNNN0.",
    ".0NNNN000000000NNNNN0.",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0NNNNNNNNNNNNNNNNNN0.",
    ".0MMMMMMMMMMMMMMMMMM0.",
    ".00000000000000000000.",
])
PADDLES_L = grid([  # two ping-pong bats and a ball on a nail (16 × 13)
    "......00........",
    "..0000..0000....",
    ".0xxxx00wwww0...",
    "0xyxxxx0wxwww0..",
    "0xxxxxx0wwwww0..",
    "0xxxxxx0wwwww0..",
    ".0xxxx0.0www0...",
    "..0ee0...0ee0...",
    "..0ee0...0ee0.00",
    "..0ee0...0ee00WW",
    "..0cc0...0cc00WG",
    "..0000...0000.00",
    "................",
])
KEYS_BOARD = grid([  # a key board: hooks, plank keys on strings, one hook empty (30 × 12)
    "000000000000000000000000000000",
    "0ffffffffffffffffffffffffffff0",
    "0edededededededededededededee0",
    "000000000000000000000000000000",
    "..0...0...0...0...0...0...0...",
    ".0f0.0f0.0f0.....0f0.0f0.0f0..",
    ".0e0.0e0.0e0.....0e0.0e0.0e0..",
    ".0e0.0x0.0e0.....0x0.0e0.0e0..",
    ".0e0.0e0.0e0.....0e0.0e0.0e0..",
    ".0e0.0e0.0e0.....0e0.0e0.0e0..",
    ".0c0.0c0.0c0.....0c0.0c0.0c0..",
    "..0...0...0.......0...0...0...",
])
YUKATA_RACK = grid([  # a coat stand, a yukata hanging on it, an obi sash (18 × 30)
    ".........00.......",
    "........0ee0......",
    ".....000.00.000...",
    "....0e0..ee..0e0..",
    "..00000000000000..",
    ".0DDDDDDhDDDDDDD0.",
    "0DDGDDDDhhDDDDGDD0",
    "0DDDDDDhhhhDDDDDD0",
    "0DGDDDhhDDhhDDGDD0",
    "00DDDDhDDDDhDDDD00",
    ".0DDDhDDGDDDhDDD0.",
    ".0DDDhDDDDDDhDDD0.",
    ".0xxxxxxxxxxxxxx0.",
    ".0wwwwwwxwwwwwww0.",
    ".0DDDhDDDDDDhDDD0.",
    ".0DGDhDDDDGDhDGD0.",
    ".0DDDhDDDDDDhDDD0.",
    ".0DDDhDDGDDDhDDD0.",
    ".0DDDhDDDDDDhDDD0.",
    ".0DGDhDDDDDDhDGD0.",
    ".0DDDhDDDDDDhDDD0.",
    ".0000h000000h0000.",
    ".........ee.......",
    ".........ee.......",
    ".........ee.......",
    ".........ee.......",
    ".......00ee00.....",
    "......0eeeeee0....",
    "......00000000....",
    "..................",
])
ZABUTON = grid([  # a floor cushion with a round fan resting on it (14 × 6)
    "..00000000000.",
    ".0NNNNNNNNNN0.",
    "0NOONNNNNNNNN0",
    "0NNNNNNNNNNNM0",
    ".0MMMMMMMMMM0.",
    "..0000000000..",
])
GAUGE_L = grid([  # the boiler's pressure gauge (15 × 15)
    "....0000000....",
    "..00fffffff00..",
    ".0fghhhhhhhgf0.",
    ".0fhh0hhh0hhf0.",
    "0fhhhhhhhhhhhf0",
    "0fh0hhhhhhhxhf0",
    "0fhhhhhhhhxhhf0",
    "0fhhhhhh0xhhhf0",
    "0fh0hhhh0hhh0f0",
    "0fhhhhhhhhhhhf0",
    ".0fhh0hhhh0hf0.",
    ".0ffhhhhhhhff0.",
    "..00fffffff00..",
    "....0000000....",
    "......0ee0.....",
])
WHEEL_L = grid([  # a valve wheel (11 × 11)
    "...00000...",
    "..0xxxxx0..",
    ".0x0.x.0x0.",
    "0x0..x..0x0",
    "0x...x...x0",
    "0xxxx0xxxx0",
    "0x...x...x0",
    "0x0..x..0x0",
    ".0x0.x.0x0.",
    "..0xxxxx0..",
    "...00000...",
])
BOILER = grid([  # the bathhouse boiler: a riveted drum, its firebox glowing low (26 × 22)
    "....000000000000000000....",
    "..005555555555555555500...",
    ".05577777777777777775550..",
    "0557777777777777777755550.",
    "057777777777777777775555 0",
    "0577070707070707070755550.",
    "0577777777777777777755550.",
    "0577777777777777777755550.",
    "0577777777777777777755550.",
    "0577777777777777777755550.",
    "0577070707070707070755550.",
    "0555555555555555555555550.",
    "0333333333333333333333330.",
    "0330000000000000000003330.",
    "0330uvwxwvuvwxxwvuvw03330.",
    "0330vwxyxwvwxyyxwvwx03330.",
    "0330000000000000000003330.",
    "0333333333333333333333330.",
    "0000000000000000000000000.",
    ".00.................00....",
    "..........................",
    "..........................",
])
MIRROR_L = grid([  # an oval mirror on its dresser stand (16 × 22)
    ".....000000.....",
    "...00eeeeee00...",
    "..0eGHGGGGGGe0..",
    ".0eGHGGGGGGFFe0.",
    ".0eHGGGGGGFFFe0.",
    "0eGGGGGGGFFFEEe0",
    "0eGGGGGGFFFEEEe0",
    "0eGGGGGFFFEEEEe0",
    "0eGGGGFFFEEEEDe0",
    ".0eGGFFFEEEEDe0.",
    ".0eGFFFEEEEDDe0.",
    "..0eFFEEEEDDe0..",
    "...00eeeeee00...",
    ".....000000.....",
    "......0ee0......",
    ".0000000000000..",
    "0gffffffffffffe0",
    "0eddddddddddddc0",
    "0ed0000000000dc0",
    "0edd0hh00kk0ddc0",
    "0ccccccccccccccc",
    ".0............0.",
])
DRYER_L = grid([  # the hood hair dryer on its stand (14 × 26)
    "...00000000...",
    ".00GGGGGGGG00.",
    "0GG999999999G0",
    "0G99999999999G",
    "09999999999990",
    "0000000000000.",
    ".0333333333330",
    "..00000000000.",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "......0770....",
    "....00077000..",
    "...077777770..",
    "...000000000..",
])
BOARD_L = grid([  # the notice board: blank papers pinned, a paper crane (32 × 22)
    "00000000000000000000000000000000",
    "0dddddddddddddddddddddddddddddd0",
    "0deeeeeeeeeeeeeeeeeeeeeeeeeeeed0",
    "0de0x000ee0k000eeeeee00000eeeed0",
    "0de0hhhh0e0hhhh0eee0x0hhhh0eeed0",
    "0de0hggh0e0hhhh0eee0hhhhhh0eeed0",
    "0de0hhhh0e0hggh0eee0hgghhh0eeed0",
    "0de0hggh0e0hhhh0eee0hhhhgg0eeed0",
    "0de0hhhh0e0hggh0eee0hhhhhh0eeed0",
    "0de000000e000000eee00000000eeed0",
    "0deeeeeeeeeeeeeeeeeeeeeeeeeeeed0",
    "0de00000000eeeeee.h...eeeeeeeed0",
    "0de0hhhhhh0eeeeh...hh.eeeeeeeed0",
    "0de0hggghh0eeee.hhhhhGeeeeeeeed0",
    "0de0hhhhhh0eeeeee.hhGeeeeeeeeed0",
    "0de00000000eeeeeeeeGeeeeeeeeeed0",
    "0deeeeeeeeeeeeeeeeeeeeeeeeeeeed0",
    "0dddddddddddddddddddddddddddddd0",
    "00000000000000000000000000000000",
])
POSTBOX = grid([  # a red letter box on its post (10 × 24)
    "..000000..",
    ".0xxxxxx0.",
    "0xyyyyyyx0",
    "0xxxxxxxw0",
    "0x000000w0",
    "0xxxxxxxw0",
    "0xxxxxxxw0",
    "0xxxhxxxw0",
    "0xxxxxxxw0",
    "0xxxxxxxw0",
    "0wwwwwwww0",
    ".00000000.",
    "....0c0...",
    "....0c0...",
    "....0c0...",
    "....0c0...",
    "....0c0...",
    "....0c0...",
    "...00c00..",
    "..0ccccc0.",
    "..0000000.",
])
FAN_L = grid([  # a standing electric fan (15 × 26)
    ".....00000.....",
    "...009G9G900...",
    "..0G9GG9GG9G0..",
    ".0G9GG888GG9G0.",
    ".09GG88888GG90.",
    "0G9G8800088G9G0",
    "09GG8800x08GG90",
    "0G9G8800088G9G0",
    ".09GG88888GG90.",
    ".0G9GG888GG9G0.",
    "..0G9GG9GG9G0..",
    "...009G9G900...",
    ".....00000.....",
    ".......07......",
    ".......07......",
    ".......07......",
    ".......07......",
    ".......07......",
    ".......07......",
    ".......07......",
    ".....00700.....",
    "...07777770....",
    "...00000000....",
])
FUSEBOX = grid([  # a porcelain switch plate with its toggle, the fuse cover below (8 × 14)
    "00000000",
    "0hhhhhh0",
    "0h0000h0",
    "0h0cc0h0",
    "0h0W00h0",
    "0h0000h0",
    "0hhhhhg0",
    "00000000",
    "..0000..",
    ".0hhhh0.",
    "0hh00hh0",
    "0h0kk0g0",
    "0hh00gg0",
    ".000000.",
])
BANDAI_TOP = grid([  # on the attendant's counter: a bell, an abacus, a coin tray (40 × 9)
    "....0...................................",
    "...0f0.....00000000000000000000.........",
    "..0gff0....0e0000000000000000e0.........",
    ".0gffed0...0exhxhxhhxhxhxhxhxe0....0000.",
    "000000000..0e0000000000000000e0...0kkkk0",
    "...........0ehxhxhxxhxhxhhxhxe0..0kkkk0.",
    "...........0exhxhhxhhxhxhhxhxe0..000000.",
    "...........0e0000000000000000e0.........",
    "...........00000000000000000000.........",
])
GARLAND = ["x", "k", "E", "h", "s"]


# ---------------------------------------------------------------- the corners

def c_default(im):
    lamp(im, 196, 11, 36)
    wainscot(im, 188, W, 31)
    # a bench, a basin pyramid on it, towels on the wall, the clock
    rect(im, 204, 27, 262, 29, "e")
    hline(im, 204, 262, 27, "g")
    for lx in (206, 258):
        rect(im, lx, 29, lx + 2, 34, "c")
    for i, (bx, by) in enumerate(((214, 23), (223, 23), (232, 23), (218, 19), (227, 19), (223, 15))):
        stamp(im, BASIN, bx, by)
    pool(im, 190, 214, 27)
    stamp(im, STOOL, 240, 21)
    stamp(im, grid(["hhhhhh", "999999", "hhhhhW"]), 244, 18)
    towel_rail(im, 250, 10, 3)
    clock_l(im, 270, 9)


def towel_rail(im, x, y, n):
    hline(im, x, x + 9 * n, y, "9")
    for i in range(n):
        c = ["9", "x", "E"][i % 3]
        c2 = {"9": "8", "x": "w", "E": "D"}[c]
        tx = x + 1 + i * 9
        rect(im, tx, y + 1, tx + 7, y + 14, c)
        vline(im, tx + 6, y + 1, y + 14, c2)
        hline(im, tx, tx + 7, y + 10, c2)
        hline(im, tx, tx + 7, y + 11, "h" if c != "9" else "7")


def clock_l(im, x, y):
    """A round wall clock, ticks only (13 × 13)."""
    g = grid([
        "....00000....",
        "..00ddddd00..",
        ".0dhhhhhhhd0.",
        ".0hh0hhh0hh0.",
        "0dhhhhhhhhhd0",
        "0dh0hh0hh0hd0",
        "0dhhhh0hhhhd0",
        "0dhhhh00000d0",
        "0dh0hhhhh0hd0",
        ".0hhhhhhhhh0.",
        ".0dhh0hh0hd0.",
        "..00ddddd00..",
        "....00000....",
    ])
    stamp(im, g, x, y)


def c_listen(im):
    lamp(im, 192, 9, 30)
    counter(im, 188, W, 28)
    stamp(im, RADIO_L, 208, 9)
    shadow(im, 208, 238, 28)
    pool(im, 190, 212, 28)
    stamp(im, TEACUP, 240, 19)
    stamp(im, PLANT, 252, 18)
    stamp(im, grid(MILK), 264, 24)
    stamp(im, grid(MILK), 269, 24)
    # records leaning in a crate at the end of the counter
    stamp(im, grid(["0000000", "0x0D0k0", "0x0D0k0", "0w0C0j0", "0000000"]), 276, 23)


def c_watch(im):
    lamp(im, 194, 9, 22)
    stamp(im, TV_L, 204, 2)
    stamp(im, grid(["0cc0", "0cc0", "0cc0"]), 214, 18)  # the bracket
    wainscot(im, 188, W, 33)
    counter(im, 196, 230, 25, 8)  # a low cabinet under the set
    stamp(im, grid(["..x.", ".xyx", "..s.", ".0h0", "0hh0", "0WW0", "0hh0"]), 200, 18)  # a camellia
    stamp(im, grid(["00000", "0DDD0", "0CCC0", "00000", "0xxx0", "0www0", "00000"]), 218, 18)  # tapes


def c_games(im):
    lamp(im, 240, 9, 30)
    stamp(im, ARCADE_L, 189, 7)
    stamp(im, PADDLES_L, 214, 4)
    wainscot(im, 212, W, 30)


def c_house(im):
    lamp(im, 192, 9, 34)
    wainscot(im, 188, W, 34)
    stamp(im, grid(FRIDGE), 222, 13)
    stamp(im, CAT_SLEEP, 223, 6)
    stamp(im, grid(SCALE), 202, 12)
    stamp(im, grid(["..0000..", ".0kkkk0.", "0kkkkkk0", "0jjjjjj0", ".000000."]), 244, 30)
    stamp(im, grid(MILK), 250, 30)
    # a crate of empty bottles waiting for the milkman
    stamp(im, grid(["0h0h0h0", "0W0W0W0", "0000000", "0eeeeee0", "0cccccc0", "00000000"]), 258, 28)


def c_space(im):
    lamp(im, 192, 9, 34)
    wainscot(im, 188, W, 33)
    stamp(im, YUKATA_RACK, 206, 6)
    stamp(im, ZABUTON, 232, 29)
    stamp(im, grid(UCHIWA), 236, 20)
    stamp(im, grid(["hhhhhh", "EEEEEE", "hhhhhW"]), 252, 30)
    stamp(im, grid([".0000.", "0hhhh0", "0hWWh0", ".0000."]), 262, 29)  # a bar of soap


def c_files(im):
    lamp(im, 194, 9, 24)
    stamp(im, KEYS_BOARD, 194, 9)
    # shoe lockers below (plain, the header's buttons sit over them)
    for x0 in range(188, W, 12):
        rect(im, x0, 24, x0 + 11, H, "c")
        hline(im, x0, x0 + 11, 24, "e")
        vline(im, x0, 24, H, "d")
        rect(im, x0 + 8, 27, x0 + 10, 33, "e")
        put(im, x0 + 8, 27, "g")


def c_control(im):
    lamp(im, 190, 9, 30)
    for y, lo in ((10, "4"), (14, "3")):
        rect(im, 188, y, W, y + 3, "5")
        hline(im, 188, W, y, "7")
        hline(im, 188, W, y + 2, lo)
        for x in (196, 232, 270):
            rect(im, x, y - 1, x + 2, y + 4, "6")
    rect(im, 262, 10, 265, H, "5")
    vline(im, 262, 10, H, "7")
    vline(im, 264, 10, H, "4")
    stamp(im, BOILER, 206, 17)
    stamp(im, GAUGE_L, 238, 17)
    stamp(im, WHEEL_L, 268, 18)
    rect(im, 188, 38, W, H, "3")


def c_me(im):
    lamp(im, 192, 9, 30)
    wainscot(im, 188, W, 33)
    stamp(im, MIRROR_L, 204, 11)
    stamp(im, DRYER_L, 228, 9)
    towel_rail(im, 252, 10, 3)
    stamp(im, grid(["..0..", ".0h0.", "0hhh0", "0kkk0", "00000"]), 207, 28)  # a jar of cream


def c_inbox(im):
    lamp(im, 192, 9, 30)
    wainscot(im, 188, W, 33)
    stamp(im, BOARD_L, 202, 9)
    stamp(im, POSTBOX, 244, 12)
    stamp(im, grid(["000000", "0hhhh0", "0h00h0", "0hhhh0", "000000"]), 258, 28)  # a letter


def c_smart(im):
    lamp(im, 192, 9, 32)
    wainscot(im, 188, W, 33)
    stamp(im, FAN_L, 206, 10)
    stamp(im, FUSEBOX, 228, 12)
    vline(im, 232, 23, 33, "0")
    stamp(im, grid(LAMP), 248, 14)
    vline(im, 250, 8, 14, "0")
    stamp(im, grid(["..00..", ".0kk0.", "0kWWk0", ".0kk0.", "..00.."]), 262, 18)  # a bulb, spare


def c_ask(im):
    lamp(im, 194, 9, 22)
    # the bandai: a high counter with a raised lip, the attendant's things on it
    counter(im, 188, W, 22, 18)
    stamp(im, BANDAI_TOP, 202, 13)
    stamp(im, grid(MILK), 250, 18)
    stamp(im, TEACUP, 260, 13)
    pool(im, 190, 212, 22)


def c_party(im):
    lamp(im, 196, 9, 34)
    wainscot(im, 188, W, 33)
    for x in range(188, W):
        y = 10 + int(round(3 * math.sin((x - 188) / (W - 188) * math.pi)))
        put(im, x, y, "0")
    for x in range(192, W - 4, 16):
        y = 10 + int(round(3 * math.sin((x + 3 - 188) / (W - 188) * math.pi)))
        stamp(im, grid(LANTERN), x, y)
    # a paper garland under them, in the house's colours
    for i, x in enumerate(range(190, W, 3)):
        y = 22 + int(round(2 * math.sin((x - 190) / 20)))
        put(im, x, y, GARLAND[i % len(GARLAND)])
        put(im, x + 1, y + 1, GARLAND[i % len(GARLAND)])
    stamp(im, grid(UCHIWA), 214, 25)
    stamp(im, grid(UCHIWA), 250, 24, flip=True)


CORNERS = {
    "banner.png": c_default,
    "banner-listen.png": c_listen,
    "banner-watch.png": c_watch,
    "banner-games.png": c_games,
    "banner-house.png": c_house,
    "banner-space.png": c_space,
    "banner-files.png": c_files,
    "banner-control.png": c_control,
    "banner-me.png": c_me,
    "banner-inbox.png": c_inbox,
    "banner-smart.png": c_smart,
    "banner-ask.png": c_ask,
    "banner-party.png": c_party,
}


def banners():
    for name, corner in CORNERS.items():
        im = new(W, H, "1")
        wall(im)
        frieze(im)
        corner(im)
        done(im, name)
