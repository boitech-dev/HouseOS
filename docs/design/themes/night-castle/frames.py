"""Frames and textures: the HUD's gold-framed stat boxes, the stone the castle is built of.
9-slice frames are drawn whole (so the moon's light stays up-right: top and right edges bright,
bottom and left in shadow), native, then saved × 3 so a slice of N native px is 3N screen px."""
import math

from lib import get, new, put, save
from palette import BONE, CRIMSON, FLAME, GOLD, MOON, NIGHT, STONE
from PIL import Image


def lit(side, bright, dark):
    return bright if side in ("top", "right") else dark


def side_of(x, y, w, h):
    d = {"top": y, "left": x, "bottom": h - 1 - y, "right": w - 1 - x}
    return min(d, key=d.get), min(d.values())


def ring_frame(size, rings, corner=None):
    """A square 9-slice source, size = 3 slices; rings[i] = (bright, dark) or None (clear)."""
    im = new(size, size)
    for y in range(size):
        for x in range(size):
            side, d = side_of(x, y, size, size)
            if d < len(rings) and rings[d]:
                b, k = rings[d]
                put(im, x, y, lit(side, b, k))
    if corner:
        for flip_x in (False, True):
            for flip_y in (False, True):
                bright = (flip_x and not flip_y)  # the top-right corner faces the moon
                for yy, row in enumerate(corner):
                    for xx, ch in enumerate(row):
                        if ch == ".":
                            continue
                        c = CORNER[ch][1 if bright else 0]
                        x = size - 1 - xx if flip_x else xx
                        y = size - 1 - yy if flip_y else yy
                        put(im, x, y, c)
    return im


CORNER = {  # letter → (in shadow, in moonlight)
    "G": (GOLD[3], GOLD[4]),
    "g": (GOLD[2], GOLD[3]),
    "H": (GOLD[4], GOLD[6]),
    "k": (NIGHT[0], NIGHT[0]),
    "r": (CRIMSON[3], CRIMSON[4]),
    "R": (CRIMSON[5], CRIMSON[6]),
}

BOSS = [  # a gold boss with a ruby, on the corner
    "kkkkkk",
    "kGGGGk",
    "kGHHgk",
    "kGHRrk",
    "kGgrgk",
    "kkkkk.",
]


def panel_frame():
    rings = [(GOLD[4], GOLD[3]), (NIGHT[0], NIGHT[0]), (STONE[5], STONE[2])]
    return ring_frame(18, rings, BOSS)


def nowbar_frame():
    rings = [(GOLD[4], GOLD[3]), (NIGHT[0], NIGHT[0]), (STONE[4], STONE[2])]
    small = ["kkkk", "kGHk", "kHRk", "kkk."]
    return ring_frame(12, rings, small)


SHEET_CORNER = [  # a gold corner with a ruby, a little larger than the panels'
    "kkkkkk",
    "kGGGGk",
    "kGHHgk",
    "kGHRrk",
    "kGgrgk",
    "kkkkk.",
]


def sheet_frame():
    """Sheets and dialogs: gold, a dark groove, a crimson velvet line; thin enough that the
    sheet's own padding clears it."""
    rings = [(GOLD[4], GOLD[3]), (NIGHT[0], NIGHT[0]), (CRIMSON[4], CRIMSON[2])]
    return ring_frame(18, rings, SHEET_CORNER)


def stone_texture():
    """A tile of ashlar over any ground: mortar as a translucent shadow, a few moonlit chips.
    32 × 16 native (two courses, joints staggered), × 3."""
    w, h = 32, 16
    im = Image.new("RGBA", (w, h))
    shadow = (8, 0, 16, 56)
    chip = (144, 152, 160, 18)
    for y in range(h):
        for x in range(w):
            course = y // 8
            joint = (x + course * 8) % 16 == 0
            if y % 8 == 7 or joint:
                im.putpixel((x, y), shadow)
            elif y % 8 == 0 and (x * 5 + y) % 7 < 3:
                im.putpixel((x, y), chip)
    for x, y in ((5, 3), (22, 11), (27, 4), (12, 13)):
        im.putpixel((x, y), (8, 0, 16, 45))
    return im


def battlements_texture():
    """The status bar is the wall walk: merlons against the night, 16 × 16 native (× 3 = 48)."""
    w, h = 16, 16
    im = new(w, h)
    for y in range(h):
        for x in range(w):
            merlon = 1 <= x <= 10
            top = 9 if merlon else 13
            if y >= top:
                c = STONE[1]
                if y == top:
                    c = STONE[3] if x > 3 else STONE[2]
                elif merlon and x == 10 and y < 13:
                    c = STONE[2]  # the merlon's moonlit side
                elif y % 4 == 0 or (x + (y // 4) * 4) % 8 == 0:
                    c = NIGHT[0]
                put(im, x, y, c)
    return im


def deck_frame():
    """The music deck as a reliquary: gold, a groove, a crimson velvet lining; 5 native per
    slice (15 px, inside the deck's 16 px padding), the middle lined in dark velvet."""
    rings = [(GOLD[4], GOLD[3]), (NIGHT[0], NIGHT[0]), (CRIMSON[3], CRIMSON[2]), (CRIMSON[1], CRIMSON[1])]
    rings += [(CRIMSON[0], CRIMSON[0])] * 4
    boss = ["kkkkk", "kGHGk", "kHRrk", "kGrgk", "kkkk."]
    return ring_frame(15, rings, boss)


def ember():
    """An ember from the deck's candles: a hot core, a halo (drawn with blend screen)."""
    im = new(3, 3)
    for x, y in ((0, 0), (2, 0), (0, 2), (2, 2)):
        put(im, x, y, FLAME[0])
    for x, y in ((1, 0), (0, 1), (2, 1), (1, 2)):
        put(im, x, y, FLAME[2])
    put(im, 1, 1, FLAME[5])
    return im


FLAMES = [  # four flickers of a candle flame, 3 × 5, bottom row at the wick
    ["..p..", ".pP..", ".PPp.", ".PcP.", "..k.."],
    [".....", "..p..", ".pPp.", ".PcP.", "..k.."],
    ["...p.", "..Pp.", ".pPP.", ".PcP.", "..k.."],
    [".....", ".p...", ".pPp.", ".PcPp", "..k.."],
]
FLAME_INK = {"p": FLAME[2], "P": FLAME[3], "c": FLAME[5], "k": NIGHT[0]}


def draw_flame(im, x, y, f):
    """The flame's 5 × 5 box with its top-left at (x, y)."""
    for yy, row in enumerate(FLAMES[f % 4]):
        for xx, ch in enumerate(row):
            if ch != ".":
                put(im, x + xx, y + yy, FLAME_INK[ch])


VOTIVE_FLAMES = [[".p.", "pPp", ".c."], ["..p", ".Pp", ".c."], [".p.", ".Pp", ".c."], ["p..", "pP.", ".c."]]


def votive(flame_rows, smoke=()):
    """A votive candle in a gold cup, 5 × 5: it sits in the deck frame's corner (its padding)."""
    im = new(5, 5)
    for yy, row in enumerate(flame_rows):
        for xx, ch in enumerate(row):
            if ch != ".":
                put(im, 1 + xx, yy, {"p": FLAME[2], "P": FLAME[4], "c": FLAME[5], "e": CRIMSON[4], "k": NIGHT[0]}[ch])
    for x, y, c in smoke:
        put(im, x, y, c)
    for x in range(1, 4):
        put(im, x, 3, BONE[4] if x < 3 else BONE[5])
    for x in range(5):
        put(im, x, 4, GOLD[3] if x < 4 else GOLD[5])
    put(im, 0, 3, GOLD[2])
    put(im, 4, 3, GOLD[4])
    return im


def deck_candle():
    """The deck's two votives, 4 flicker frames."""
    return strip([votive(f) for f in VOTIVE_FLAMES])


def candle_snuff():
    """The poke: a breath bends the flame, it dies to a red wick, smokes, and catches again."""
    return strip([
        votive(["p..", "Pp.", ".c."]),
        votive(["...", "...", ".p."]),
        votive(["...", "...", ".e."], [(2, 1, STONE[5])]),
        votive(["...", "...", ".k."], [(2, 1, STONE[5]), (1, 0, STONE[5])]),
        votive(["...", "...", ".k."], [(1, 0, STONE[4]), (3, 0, STONE[3])]),
        votive(["...", "...", ".P."]),
        votive(["...", ".p.", ".c."]),
    ])


def torch():
    """A torch in an iron sconce on the wall walk, 7 × 16 per frame, 4 frames (the status bar)."""
    frames = []
    for f in range(4):
        im = new(7, 16)
        draw_flame(im, 1, 1, f)
        # a wider blaze under the flame
        for x in range(1, 6):
            put(im, x, 6, FLAME[1] if x in (1, 5) else FLAME[2])
        # the torch's head (wrapped) and its stick
        for x in range(2, 5):
            put(im, x, 7, GOLD[1])
            put(im, x, 8, GOLD[2] if x < 4 else GOLD[3])
        for y in range(9, 14):
            put(im, 3, y, GOLD[1])
        # the iron sconce
        for x in range(1, 6):
            put(im, x, 11, NIGHT[0])
        put(im, 1, 10, NIGHT[0])
        put(im, 5, 10, NIGHT[0])
        put(im, 5, 11, STONE[3])
        for y in range(12, 16):
            put(im, 3, y, NIGHT[0])
        put(im, 2, 15, NIGHT[0])
        put(im, 4, 15, NIGHT[0])
        frames.append(im)
    return strip(frames)


def torch_flare():
    """The torch's poke: struck, it roars up (a taller blaze) and settles; sparks fly (burst)."""
    frames = []
    blazes = [
        ["..p..", ".pPp.", "pPcPp", "PccPp", ".PcP.", "..P.."],
        [".p.p.", "pPpPp", "PcccP", "PccPP", "pPcPp", ".PPP."],
        ["..p..", ".pPp.", "pPcPp", "PccPp", ".PcP.", "..P.."],
        [".....", "..p..", ".pPp.", ".PcP.", ".pPp.", "..P.."],
    ]
    for rows in blazes:
        im = new(7, 16)
        for yy, row in enumerate(rows):
            for xx, ch in enumerate(row):
                if ch != ".":
                    put(im, 1 + xx, yy, FLAME_INK[ch])
        for x in range(1, 6):
            put(im, x, 6, FLAME[1] if x in (1, 5) else FLAME[2])
        for x in range(2, 5):
            put(im, x, 7, GOLD[1])
            put(im, x, 8, GOLD[2] if x < 4 else GOLD[3])
        for y in range(9, 14):
            put(im, 3, y, GOLD[1])
        for x in range(1, 6):
            put(im, x, 11, NIGHT[0])
        put(im, 1, 10, NIGHT[0])
        put(im, 5, 10, NIGHT[0])
        put(im, 5, 11, STONE[3])
        for y in range(12, 16):
            put(im, 3, y, NIGHT[0])
        put(im, 2, 15, NIGHT[0])
        put(im, 4, 15, NIGHT[0])
        frames.append(im)
    return strip(frames)


def spark():
    im = new(2, 2)
    put(im, 0, 0, FLAME[5])
    put(im, 1, 0, FLAME[3])
    put(im, 0, 1, FLAME[3])
    return im


def strip(frames):
    w, h = frames[0].size
    out = new(w * len(frames), h)
    for i, fr in enumerate(frames):
        out.alpha_composite(fr, (i * w, 0))
    return out


if __name__ == "__main__":
    save(panel_frame(), "frame-panel.png")
    save(nowbar_frame(), "frame-bar.png")
    save(sheet_frame(), "frame-sheet.png")
    tex = stone_texture()
    from lib import ART
    import pixel
    pixel.scale(tex, 3).save(ART / "stone.png", optimize=True)
    save(battlements_texture(), "battlements.png")
    save(deck_frame(), "frame-deck.png")
    save(ember(), "ember.png", scale=1)
    save(deck_candle(), "deck-candle.png", scale=1)
    save(torch(), "torch.png", scale=1)
    save(candle_snuff(), "candle-snuff.png", scale=1)
    save(torch_flare(), "torch-flare.png", scale=1)
    save(spark(), "spark.png", scale=1)
    print("frames written")
