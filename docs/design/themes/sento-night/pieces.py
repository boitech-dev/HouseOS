"""Bathhouse After Hours: the pixel pieces (sprites.json), drawn as text grids.

    python3 docs/design/themes/sento-night/pieces.py    # writes themes/sento-night/sprites.json
                                                         # and a preview in the scratch folder

Letters are the art palette's (make.py PAL), each mapped to a color.sprite token, so the pieces
share the pictures' colours exactly: 0 outline · 3 dark tile · 5 teal · 7 mist · G pale blue ·
W white · h milk cream · c dark wood · e hinoki · g light hinoki · k basin yellow · D mural blue ·
x vermilion · z vermilion light · w vermilion deep · s pine · o ginger. Light from the upper left.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "themes/sento-night/sprites.json"

PALETTE = {
    "0": "outline", "3": "dark", "5": "ink", "7": "mist", "G": "light-dim", "W": "light",
    "h": "paper", "c": "familiar-deep", "e": "mid-dark", "g": "mid", "k": "familiar-mid",
    "D": "familiar", "x": "accent", "z": "accent-hi", "w": "accent-deep", "s": "good",
    "o": "alert",
}

# ------------------------------------------------------------------ Nox: the milk bottle
# One bottle, six moods. The vinyl cap tied at the neck, glass lit up-left, a teal label band.
BOTTLE = [
    "................",
    "......0000......",
    ".....0zxxx0.....",
    ".....0xxxw0.....",
    "......0ww0......",
    ".....0GWWh0.....",
    "....0GWWWWh0....",
    "...0GWWWWWWh0...",
    "...0GWWWWWWh0...",
    "...0GWWWWWWh0...",
    "...0GWWWWWWh0...",
    "...05577777550..",
    "...0GWWWWWWh0...",
    "...0GWWWWWWh0...",
    "....0hhhhhh0....",
    ".....000000.....",
]


def put(rows, x, y, ch):
    r = list(rows[y])
    r[x] = ch
    rows[y] = "".join(r)


def nox(face, extra=None, rows=None):
    g = list(rows or BOTTLE)
    for x, y, ch in face:
        put(g, x, y, ch)
    for x, y, ch in extra or []:
        put(g, x, y, ch)
    return g


EYES_OPEN = [(6, 8, "0"), (6, 9, "0"), (9, 8, "0"), (9, 9, "0")]
MOUTH = [(7, 10, "x"), (8, 10, "x")]
NOX = {
    "nox.idle": nox(EYES_OPEN + [(8, 10, "0")]),
    "nox.blink": nox([(6, 9, "0"), (5, 9, "0"), (9, 9, "0"), (10, 9, "0"), (8, 10, "0")]),
    # listening: eyes wide and up, the cap perked, sound rings arriving at the right
    "nox.listening": nox(
        [(6, 7, "0"), (6, 8, "0"), (9, 7, "0"), (9, 8, "0"), (7, 10, "0"), (8, 10, "0")],
        [(14, 5, "7"), (15, 6, "7"), (15, 7, "7"), (15, 8, "7"), (14, 9, "7"),
         (13, 6, "5"), (13, 7, "5"), (13, 8, "5")],
    ),
    # thinking: the glass fogs up (pale blue), eyes look up-left, bubbles rise in the milk
    "nox.thinking": nox(
        [(5, 7, "0"), (5, 8, "0"), (8, 7, "0"), (8, 8, "0"), (8, 10, "0")],
        [(10, 12, "G"), (9, 13, "G"), (10, 9, "G"), (4, 12, "7"), (4, 13, "7"),
         (13, 3, "7"), (14, 1, "G"), (15, 0, "W"), (12, 5, "7")],
    ),
    # happy: eyes shut in smiles, pink cheeks, a sparkle
    "nox.happy": nox(
        [(5, 9, "0"), (6, 8, "0"), (7, 9, "0"), (8, 9, "0"), (9, 8, "0"), (10, 9, "0"),
         (5, 10, "z"), (10, 10, "z"), (7, 10, "x"), (8, 10, "x")],
        [(14, 2, "k"), (13, 3, "k"), (15, 3, "k"), (14, 4, "k"), (14, 3, "W"), (2, 5, "k")],
    ),
}
# error: the cap has slipped off and lies at its foot, a crooked mouth, a drop spilt
_err = list(BOTTLE)
_err[1] = "................"
_err[2] = "................"
_err[3] = "................"
_err[4] = "......0000......"
NOX["nox.error"] = nox(
    [(6, 8, "0"), (5, 9, "0"), (7, 9, "0"), (9, 8, "0"), (10, 9, "0"), (8, 9, "0"),
     (7, 11, "0"), (8, 11, "5"), (9, 11, "0")],
    [(12, 13, "0"), (13, 13, "x"), (14, 13, "x"), (15, 13, "0"), (13, 14, "w"), (14, 14, "w"),
     (12, 15, "0"), (13, 15, "0"), (14, 15, "0"), (15, 15, "0"), (1, 14, "W"), (2, 15, "W"),
     (1, 15, "G"), (0, 15, "G")],
    rows=_err,
)

# ------------------------------------------------------------------ avatars (16 × 16, round)
AVATARS = {
    # the moon over the bath's water, its reflection broken by a ripple
    "avatar.moon": [
        "....00000000....",
        "..003333333300..",
        ".03333333333330.",
        ".03333hhhh33330.",
        "0333hhhWhhh33330",
        "0333hhhhhgh33330",
        "0333hhghhhh33330",
        "0333hhhhhhh33330",
        "03333hhhhh333330",
        "0555555555555550",
        "05577hhhh7755550",
        "0555555555555550",
        ".05577hh7755550.",
        ".05555555555550.",
        "..005555555500..",
        "....00000000....",
    ],
    # a bat crossing the moon over the chimney
    "avatar.bat": [
        "....00000000....",
        "..003333333300..",
        ".0333hhhhhh3330.",
        ".033hhhhhhhh330.",
        "033hhhhhhhhhh330",
        "03hh0hhhhhh0hh30",
        "03h000h00h000h30",
        "0300000000000030",
        "03000000000000G0",
        "03h00h0000h00h30",
        "033hhh0000hhh330",
        "033hhhhh0hhhh330",
        ".033hhhhhhhh330.",
        ".0333hhhhhh3330.",
        "..003333333300..",
        "....00000000....",
    ],
    # a crow on the bathhouse's tall chimney, smoke curling behind
    "avatar.raven": [
        "....00000000....",
        "..00DDDDDDDD00..",
        ".0DDDDDDDDDD7D0.",
        ".0DDD0000DDD7D0.",
        "0DDD000000DDD7D0",
        "0DD0x00000DDDDD0",
        "0D0000000000DDD0",
        "0DDD00000000000D",
        "0DDDD0000000DDD0",
        "0DDDDD00000DDDD0",
        "0DDDDDD0D0DDDDD0",
        "0DDD0eeeeeeee0D0",
        ".0DD0cecececc0D.",
        ".0DD0eeeeeeee00.",
        "..000cecececc0..",
        "....00000000....",
    ],
    # a camellia, the winter flower by the bathhouse door
    "avatar.rose": [
        "....00000000....",
        "..00ssss333300..",
        ".0sssss33xxx330.",
        ".0ss0s33xzzxx30.",
        "0sss0s3xzxxwxx30",
        "03ss0s3xxkkxxw30",
        "033s0sxxkhkkxw30",
        "03333sxxxkkxww30",
        "03333sxwxxxxww30",
        "033333swwxxww330",
        "0333s33swwww3330",
        "033sss33s3333330",
        ".03ss333s333330.",
        ".0333333s333330.",
        "..003333s33300..",
        "....00000000....",
    ],
    # the steam ghost that lives over the bath (a friendly puff with a face)
    "avatar.ghost": [
        "....00000000....",
        "..003333333300..",
        ".03333WWW333330.",
        ".0333WWWWWW3330.",
        "0333WWWWWWWG3330",
        "033WW0WWW0WG3330",
        "033WW0WWW0WWG330",
        "033WWWWxWWWWG330",
        "033WWWWWWWWWG330",
        "0333WWWWWWWG3330",
        "03333WWWWWG33330",
        "033333WGWW333330",
        ".033333WGGW7330.",
        ".05555555G55550.",
        "..005555555500..",
        "....00000000....",
    ],
}

# ------------------------------------------------------------------ room marks (16 × 16)
ROOMS = {
    # the bathhouse: the tall chimney, a curved roof, the noren at the door
    "room.home": [
        "............7...",
        ".............7..",
        "............000.",
        "......00....0e0.",
        "....003300..0c0.",
        "..00377773000c0.",
        ".0377777777730c0",
        "0377777777777730",
        "0000000000000000",
        ".0hhhhhhhhhhhh0.",
        ".0hxxxxxxxxxxh0.",
        ".0hxx0xxxx0xxh0.",
        ".0hxx0xhhx0xxh0.",
        ".0h0000000000h0.",
        ".0eeeeeeeeeeee0.",
        ".00000000000000.",
    ],
    # the tube radio: cloth grille, the glowing dial
    "room.listen": [
        "................",
        "................",
        "....00000000....",
        "..00eeeeeeee00..",
        ".0egggggggggge0.",
        "0egegegegegegce0",
        "0egggggggggggce0",
        "0egegegegegegce0",
        "0egggggggggggce0",
        "0ecccccccccccce0",
        "0ec0hhkhhhkh0ce0",
        "0ec0hhxhhhhh0ce0",
        "0ecc00000000cce0",
        "0ec0g0cccc0g0ce0",
        ".00000000000000.",
        "................",
    ],
    # the changing-room TV, rabbit ears
    "room.watch": [
        "...0.......0....",
        "....0.....0.....",
        ".....0...0......",
        "......000.......",
        ".00000000000000.",
        "0eeeeeeeeeeeeee0",
        "0e000000000ggce0",
        "0e0GWGGGGG0gcce0",
        "0e0GGGGGGG0ccce0",
        "0e0GGGGGGD0gcce0",
        "0e0GGGGGDD0ccce0",
        "0e000000000ccce0",
        "0eccccccccccccc0",
        ".00000000000000.",
        "...0c0....0c0...",
        "...000....000...",
    ],
    # the house: the milk fridge (groceries and chores live here)
    "room.house": [
        "..000000000000..",
        "..0WWWWWWWWWW0..",
        "..0WxxxxxxxxW0..",
        "..0WGGGGGGGGW0..",
        "..0WhhGhhGhhW0..",
        "..0WccGWWGooW0..",
        "..0W77777777W0..",
        "..0WhhGhhGhhW0..",
        "..0WWWGccGWWW0..",
        "..0W77777777W0..",
        "..0WGGGGGGGGW0..",
        "..0WWWWWWWWWW0..",
        "..055555555550..",
        "..053333333k50..",
        "..055555555550..",
        "..000......000..",
    ],
    # files: a locker key, the wooden plank on its brass ring
    "room.files": [
        "......0000......",
        ".....0kkkk0.....",
        "....0k0000k0....",
        "....0k0..0k0....",
        ".....0kkkk0.....",
        "......0kk0......",
        ".....000000.....",
        "....0geeeec0....",
        "....0gcccce0....",
        "....0gexxee0....",
        "....0gexxee0....",
        "....0geeeee0....",
        "....0gcccce0....",
        "....0geeeee0....",
        "....0ceeeec0....",
        ".....000000.....",
    ],
    # smart home: the enamel pendant lamp, lit
    "room.smart-home": [
        ".......00.......",
        ".......00.......",
        ".......00.......",
        "......0cc0......",
        ".....0cccc0.....",
        "...00555555000..",
        "..055777777550..",
        ".05777777777750.",
        "0000000000000000",
        "....0kWWWWk0....",
        ".....0kWWk0.....",
        "......0000......",
        "..k..........k..",
        "....k......k....",
        "................",
        "......k..k......",
    ],
    # games: the arcade cabinet by the door
    "room.games": [
        "...0000000000...",
        "..0xxxxxxxxxx0..",
        "..0xkzkzkzkzx0..",
        "..0000000000000.",
        "..0e3333333330..",
        "..0e3k33333x30..",
        "..0e333W333330..",
        "..0e33333s3330..",
        "..0e3333333330..",
        "..0e0000000000..",
        ".0eeeeeeeeeeee0.",
        ".0e0x0gg0k0k0e0.",
        ".00000000000000.",
        "..0eeeeeeeeee0..",
        "..0ecccccccce0..",
        "..000000000000..",
    ],
    # more: a stack of yellow basins, and more below
    "room.more": [
        "................",
        "..000000000000..",
        ".0kWkkkkkkkkkk0.",
        "..0kkkkkkkkkk0..",
        "..000000000000..",
        ".0kWkkkkkkkkkk0.",
        "..0kkkkkkkkkk0..",
        "..000000000000..",
        ".0kWkkkkkkkkkk0.",
        "..0kkkkkkkkkk0..",
        "...0kkkkkkkk0...",
        "....00000000....",
        "................",
        "...0...0...0....",
        "..000.000.000...",
        "................",
    ],
    # me: your yukata on its hanger
    "room.me": [
        ".......00.......",
        "......0..0......",
        ".........0......",
        "..000000000000..",
        ".0DDDDhhhhDDDD0.",
        "0DDGDDDhhDDDGDD0",
        "0DDDDDDhhDDDDDD0",
        "00DDDGDhhDGDDD00",
        "..0DDDDhhDDDD0..",
        "..0xxxxxxxxxx0..",
        "..0DDDDhhDDDD0..",
        "..0DDGDhhDDGD0..",
        "..0DDDDhhDDDD0..",
        "..0DDDDDhDDDD0..",
        "..0DDGDDhDDGD0..",
        "..000000000000..",
    ],
}

# ------------------------------------------------------------------ transport (9 × 9, cream)
TRANSPORT = {
    "transport.play": ["h........", "hhh......", "hhhhh....", "hhhhhhh..", "hhhhhhhhh",
                       "hhhhhhh..", "hhhhh....", "hhh......", "h........"],
    "transport.pause": ["hhh...hhh"] * 9,
    "transport.stop": [".........", ".hhhhhhh.", ".hhhhhhh.", ".hhhhhhh.", ".hhhhhhh.",
                       ".hhhhhhh.", ".hhhhhhh.", ".hhhhhhh.", "........."],
    "transport.next": ["h.....hh.", "hh....hh.", "hhh...hh.", "hhhh..hh.", "hhhhh.hh.",
                       "hhhh..hh.", "hhh...hh.", "hh....hh.", "h.....hh."],
    "transport.previous": [".hh.....h", ".hh....hh", ".hh...hhh", ".hh..hhhh", ".hh.hhhhh",
                           ".hh..hhhh", ".hh...hhh", ".hh....hh", ".hh.....h"],
}

# ------------------------------------------------------------------ the 20 medals (16 × 16)
MEDALS = {
    # dj: the portable transistor radio, its strap, its speaker
    "title.dj": [
        "....0000000.....",
        "...0.......0....",
        "..0.........0...",
        ".00000000000000.",
        "0xzxxxxxxxxxxxw0",
        "0x0000000xhkhxw0",
        "0x0h0h0h0xxxxxw0",
        "0x00000000x00xw0",
        "0x0h0h0h0x0kk0w0",
        "0x0000000x0kk0w0",
        "0x0h0h0h0xx00xw0",
        "0x0000000xxxxxw0",
        "0wwwwwwwwwwwwww0",
        ".00000000000000.",
        "................",
        "................",
    ],
    # explorer: a pair of geta, the wooden sandals, set down to walk
    "title.explorer": [
        "................",
        "..00000.........",
        ".0ggggg0........",
        ".0ggxgg0.00000..",
        ".0gxgxg00ggggg0.",
        ".0xgggx00ggxgg0.",
        ".0ggggc00gxgxg0.",
        ".0ggggc00xgggx0.",
        ".0ggggc00ggggc0.",
        ".0ggggc00ggggc0.",
        ".0ggggc00ggggc0.",
        ".0egggc00ggggc0.",
        "..00000.0egggc0.",
        ".........00000..",
        "................",
        "................",
    ],
    # night owl: the chimney under the moon, the last smoke going up
    "title.night_owl": [
        "..........000...",
        ".........0hhh0..",
        "........0hhhWh0.",
        "........0hhhhh0.",
        ".....7...0hhh0..",
        "....7.....000...",
        ".....7..........",
        "....7...........",
        "...0000.........",
        "...0ee0.........",
        "...0ce0.........",
        "...0ce0.........",
        ".000ce0000000...",
        "03333333333330..",
        "0377777777777330",
        "0000000000000000",
    ],
    # early bird: the first basin of the day, taken from the stack, the sun rising
    "title.early_bird": [
        "................",
        "................",
        ".....000000.....",
        "....0zzxxxx0....",
        "...0zxxxxxxw0...",
        "..0xxxxxxxxxw0..",
        "0000000000000000",
        "0WWkkkkkkkkkkkk0",
        ".0kkkkkkkkkkke0.",
        "..0kkkkkkkkke0..",
        "...0kkkkkkke0...",
        "....00000000....",
        "................",
        "..7777.77777.7..",
        "................",
        "................",
    ],
    # weekend: a towel folded on the head, the long Sunday soak
    "title.weekend": [
        "................",
        "....00000000....",
        "...0WWWWWWWG0...",
        "..0WWGWWGWWWG0..",
        "..0WWWWWWWWWG0..",
        "..0hhhhhhhhhh0..",
        "..0hh0hhhh0hh0..",
        "..0hhhhzzhhhh0..",
        "..0hhhhhhhhhh0..",
        "0000hhhhhhhh0000",
        "0777700000077770",
        "0G77777777777G70",
        "0777G77777G77770",
        "0555555555555550",
        ".05555555555550.",
        "..000000000000..",
    ],
    # genre guardian: the mural painter's brush and pot of blue
    "title.genre_guardian": [
        "............000.",
        "...........0ec0.",
        "..........0ec0..",
        ".........0ec0...",
        "........0ec0....",
        ".......0ec0.....",
        "......0GG0......",
        ".....0DD0.......",
        "....0DD0........",
        "...000000000....",
        "..0gggggggggg0..",
        "..0DDDDDDDDDD0..",
        "..0eDeeeeeeee0..",
        "..0eeeeeeeeee0..",
        "..0ceeeeeeeec0..",
        "...0000000000...",
    ],
    # broken record: the tap that always drips
    "title.broken_record": [
        "................",
        "....00000.......",
        "...0xxxxx0......",
        "....00W00.......",
        "......0.........",
        "...00000000000..",
        "..0GWWWWWWWWWG0.",
        "..07777777777G0.",
        "...00000000070..",
        "...........070..",
        "...........000..",
        "................",
        "...........0G0..",
        "..........0GWG0.",
        "..........0GGG0.",
        "...........000..",
    ],
    # marathon: the bath thermometer, red to the top
    "title.marathon": [
        "......0000......",
        ".....0WWW70.....",
        ".....0WxW70.....",
        ".....0WxW70.....",
        "....00WxW700....",
        ".....0WxW70.....",
        ".....0WxW70.....",
        "....00WxW700....",
        ".....0WxW70.....",
        ".....0WxW70.....",
        "....00WxW700....",
        ".....0WxW70.....",
        "....0xxxxxw0....",
        "....0xzxxxw0....",
        "....0wxxxww0....",
        ".....000000.....",
    ],
    # radio host: the electric fan, turning the airwaves
    "title.radio_host": [
        "....00000000....",
        "..00G7G7G7G700..",
        ".0G77G777G77G70.",
        ".07GG77777GG770.",
        "0G7777W0W777G7G0",
        "07G77W0x0W77G770",
        "0G7777W0W7777G70",
        ".07GG77777GG770.",
        ".0G77G777G77G70.",
        "..00G7G7G7G700..",
        "....00000000....",
        ".......07.......",
        ".......07.......",
        ".....000700.....",
        "...0777777770...",
        "...0000000000...",
    ],
    # task hero: the deck brush that scrubs the tiles
    "title.task_hero": [
        "..............00",
        ".............0e0",
        "............0e0.",
        "...........0e0..",
        "..........0e0...",
        ".........0e0....",
        "........0e0.....",
        ".......0e0......",
        "..000000000000..",
        ".0gggggggggggg0.",
        ".0eeeeeeeeeeee0.",
        ".0cccccccccccc0.",
        ".0kokokokokoko0.",
        ".0kokokokokoko0.",
        "..777.777.777...",
        "................",
    ],
    # grocery runner: a crate of milk bottles
    "title.grocery_runner": [
        "................",
        "..0000.00.0000..",
        "..0xx0.00.0DD0..",
        "..0hh0.0h0.0hh0.",
        "..0WW00WW00WWW0.",
        ".0hWW00cc00oWW0.",
        ".0hWW00cc00oWW0.",
        "0000000000000000",
        "0geeeeeeeeeeeee0",
        "0ecccccccccccce0",
        "0eeeeeeeeeeeeee0",
        "0ecccccccccccce0",
        "0eeeeeeeeeeeeee0",
        "0000000000000000",
        "................",
        "................",
    ],
    # planner: the bathhouse clock (hour ticks, no numbers)
    "title.planner": [
        "....00000000....",
        "..00eeeeeeee00..",
        ".0eehhhhhhhhee0.",
        ".0ehh0hhhh0hhe0.",
        "0ehhhhhhhhhhhhe0",
        "0eh0hhhh0hhhh0e0",
        "0ehhhhhh0hhhhhe0",
        "0ehhhhhh0hhhhhe0",
        "0eh0hhhh00000he0",
        "0ehhhhhhhhhhhhe0",
        ".0ehh0hhhh0hhe0.",
        ".0eehhhxhhhhee0.",
        "..00eeeeeeee00..",
        "....00000000....",
        ".......00.......",
        "......0ee0......",
    ],
    # wall poet: a paper crane
    "title.wall_poet": [
        "................",
        "..........0.....",
        ".........0h0....",
        "..0......0h0....",
        ".0h0....0hh0....",
        ".0hh0..0hhG0....",
        "..0hh00hhhG0....",
        "..0hhhhhhhhG0...",
        "...0hhhhhhhhG00.",
        "....0Ghhhhhhhhh0",
        ".....0GGhhhhh00.",
        "......0GGGhh0...",
        ".......00GG0....",
        ".........00.....",
        "................",
        "................",
    ],
    # courier: a furoshiki bundle, knotted on top
    "title.courier": [
        "................",
        "......00.00.....",
        ".....0Dh0hD0....",
        "......0DDD0.....",
        "....000DhD000...",
        "...0DDDDDDDDD0..",
        "..0DhDDDDDhDDD0.",
        ".0DDDDhDDDDDhDD0",
        ".0DhDDDDDhDDDDD0",
        ".0DDDDDhDDDDhDD0",
        ".0DDhDDDDDhDDDD0",
        "..0DDDDDhDDDDD0.",
        "...00DDDDDDD00..",
        ".....0000000....",
        "................",
        "................",
    ],
    # curator: the ring of locker keys
    "title.curator": [
        "......0000......",
        ".....0k00k0.....",
        "....0k0..0k0....",
        "....0k0..0k0....",
        ".....0kkkk0.....",
        "...00000000000..",
        "..0g0.0g0.0g0...",
        "..0e0.0e0.0e0...",
        "..0x0.0e0.0x0...",
        "..0e0.0x0.0e0...",
        "..0e0.0e0.0e0...",
        "..0c0.0e0.0c0...",
        "..000.0c0.000...",
        ".......00.......",
        "................",
        "................",
    ],
    # high scorer: the ping-pong bat and ball
    "title.high_scorer": [
        "................",
        "...00000........",
        "..0xxxxx0.......",
        ".0xzxxxxx0......",
        ".0xxxxxxx0......",
        ".0xxxxxxx0...00.",
        ".0xxxxxxw0..0WW0",
        "..0xxxxw0...0WG0",
        "...00000.....00.",
        ".....0ee0.......",
        "......0ee0......",
        ".......0ee0.....",
        "........0cc0....",
        ".........000....",
        "................",
        "................",
    ],
    # collector: the clasp purse of bath tokens
    "title.collector": [
        "................",
        "......0..0......",
        ".....0k00k0.....",
        "....00kk0kk0....",
        "...0kk0000kk0...",
        "..0xxxxxxxxxx0..",
        ".0xzxxxxxxxxxw0.",
        ".0xxxxxxxxxxxw0.",
        ".0xxxkxxkxxxxw0.",
        ".0xxxxxxxxxxxw0.",
        ".0wxxxxxxxxxww0.",
        "..0wwwwwwwwww0..",
        "...0000000000...",
        "..0k0.0k0.......",
        "..000.000.......",
        "................",
    ],
    # game hopper: the arcade stick and its buttons
    "title.game_hopper": [
        "................",
        "......000.......",
        ".....0xzx0......",
        ".....0xxw0......",
        "......000.......",
        ".......0........",
        ".......0........",
        ".......0........",
        "..000000000000..",
        ".05555555555550.",
        "055055550kk05550",
        "055055550kk05550",
        "0555555550055005",
        "0333333333333330",
        ".00000000000000.",
        "................",
    ],
    # console hopper: the coin massage chair
    "title.console_hopper": [
        "....00000000....",
        "...0xzxxxxxw0...",
        "...0xxxxxxxw0...",
        "...0xxxxxxxw0...",
        "...0xxxxxxxw0...",
        "...0wxxxxxww0...",
        ".000hwwwwwwh000.",
        ".0x0xxxxxxxx0x0.",
        ".0x0xxxxxxxx0x0.",
        ".0w0000000000w0.",
        ".0wxxxxxxxxxxw0.",
        ".0wwwwwwwwwwww0.",
        "..03333333333k0.",
        "..030......030..",
        "..000......000..",
        "................",
    ],
    # romhacker: the boiler-room wrench over its valve wheel
    "title.romhacker": [
        "................",
        ".....0000000....",
        "....0x0xxx0x0...",
        "...0x0.0x0.0x0..",
        "...0xx00x00xx0..",
        "...0xxxx0xxxx0..",
        "...0xx00x00xx0..",
        "...0x0.0x0.0x0..",
        "....0x0xxx0x0...",
        ".00..00000000...",
        "0770.......0....",
        "07G70....00.....",
        ".07G70.00.......",
        "..07G707........",
        "...0770.........",
        "....00..........",
    ],
}


def trim(rows):
    """Every row to the same width, 16 at most."""
    w = min(16, max(len(r) for r in rows))
    return [(r + "." * w)[:w] for r in rows]


def main():
    glyphs = {}
    for group in (AVATARS, NOX, ROOMS, TRANSPORT, MEDALS):
        for k, v in group.items():
            glyphs[k] = trim(v)
    data = {
        "$description": ("Bathhouse After Hours: Nox the milk bottle (six moods), night-bath "
                         "avatars, the bathhouse's room marks, milk-cream transport keys and "
                         "twenty sentō objects as medals. Drawn as text grids by "
                         "docs/design/themes/sento-night/pieces.py, CC-BY-4.0."),
        "palette": PALETTE,
        "glyphs": glyphs,
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)
    print(f"{len(glyphs)} pieces → {OUT.relative_to(ROOT)}")
    if len(sys.argv) > 1:
        preview(glyphs, sys.argv[1])


def preview(glyphs, out):
    sys.path.insert(0, str(Path(__file__).parent))
    from make import rgb
    from PIL import Image

    k, cols = 6, 10
    names = list(glyphs)
    rows_n = (len(names) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (16 * k + 8) + 8, rows_n * (16 * k + 8) + 8), (40, 44, 48, 255))
    for i, name in enumerate(names):
        g = glyphs[name]
        im = Image.new("RGBA", (16, 16), (24, 34, 40, 255))
        for y, row in enumerate(g):
            for x, ch in enumerate(row):
                if ch != ".":
                    im.putpixel((x, y), rgb(ch))
        sheet.alpha_composite(im.resize((16 * k, 16 * k), Image.NEAREST),
                              (8 + (i % cols) * (16 * k + 8), 8 + (i // cols) * (16 * k + 8)))
    sheet.save(out)


if __name__ == "__main__":
    main()
