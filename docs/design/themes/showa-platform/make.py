"""Regenerates every picture of Shōwa Platform (themes/showa-platform/art) and its pieces
(sprites.json). Run from anywhere: python3 docs/design/themes/showa-platform/make.py [names…]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pieces  # noqa: E402
import scenes  # noqa: E402
from px import LINES, out  # noqa: E402
from pixel import sheet  # noqa: E402


def frames(fn, n):
    return sheet([fn(f).im for f in range(n)])


JOBS = {
    "hero": lambda: out(scenes.hero(cat=False), "hero.png"),
    "status": lambda: out(scenes.status(), "status.png"),
    "status-sky": lambda: out(scenes.status_sky(), "status-sky.png", scale=1),
    "train-far": lambda: out(frames(scenes.train_far, 2), "train-far.png", scale=1),
    "swallows": lambda: out(frames(scenes.swallows, 2), "swallows.png", scale=1),
    "furin": lambda: out(frames(pieces.furin, 4), "furin.png", scale=1),
    "boards": lambda: [out(pieces.board(room), f"board-{room}.png") for room in LINES if room != "home"],
    "crest": lambda: out(pieces.crest(), "crest.png"),
    "empty": lambda: out(pieces.empty(), "empty.png"),
    "tv": lambda: out(pieces.tv(), "tv.png"),
    "office": lambda: out(scenes.office(), "office.png"),
    "plate": lambda: out(pieces.plate(), "plate.png"),
    "pa-box": lambda: out(pieces.pa_box(), "pa-box.png"),
    "ticket": lambda: out(pieces.ticket(), "ticket.png"),
    "dock": lambda: out(pieces.dock(), "dock.png"),
    "clapboard": lambda: out(pieces.clapboard(), "clapboard.png"),
    "slab": lambda: out(pieces.slab(), "slab.png"),
}


def main(only):
    for name, job in JOBS.items():
        if not only or name in only:
            print(name, job())




def write_sprites(preview=None):
    """sprites.json (atomically), and a preview sheet of every piece at 4× in the theme's colours."""
    import sprites
    from px import PAL, THEME, write_json
    from PIL import Image

    glyphs = sprites.all_glyphs()
    write_json(THEME / "sprites.json", {
        "$description": "Shōwa Platform: Nox the station cat, stamp-rally avatars, station pictograms, "
                        "enamel transport keys, twenty station objects as medals. Drawn by "
                        "docs/design/themes/showa-platform/sprites.py.",
        "palette": sprites.PALETTE,
        "glyphs": glyphs,
    })
    if preview:
        import tokens_make
        hexes = {name: val["$value"] for name, val in tokens_make.tokens["color"]["sprite"].items()}
        cols, cell = 10, 16 * 4 + 8
        sheet = Image.new("RGBA", (cols * cell, ((len(glyphs) + cols - 1) // cols) * cell), PAL["c2"])
        for n, rows in enumerate(glyphs.values()):
            im = Image.new("RGBA", (16, 16))
            for y, row in enumerate(rows):
                for x, ch in enumerate(row):
                    if ch != ".":
                        im.putpixel((x, y), tuple(int(hexes[sprites.PALETTE[ch]][i:i + 2], 16) for i in (1, 3, 5)) + (255,))
            sheet.paste(im.resize((64, 64), Image.NEAREST), ((n % cols) * cell + 4, (n // cols) * cell + 4), im.resize((64, 64), Image.NEAREST))
        sheet.save(preview)
    return THEME / "sprites.json"


JOBS.update({
    "dusk": lambda: [
        out(scenes.hero_dusk(), "hero-dusk.png"),
        out(scenes.status_dusk(), "status-dusk.png"),
        out(scenes.status_sky_dusk(), "status-sky-dusk.png", scale=1),
        out(frames(scenes.train_far_dusk, 2), "train-far-dusk.png", scale=1),
        out(scenes.office_dusk(), "office-dusk.png"),
        out(pieces.firefly(), "firefly.png", scale=1),
    ] + [out(pieces.dusk_ui(p), f"{p}-dusk.png") for p in ("plate", "pa-box", "ticket", "dock", "clapboard", "slab")],
})
def poke_jobs():
    turn = pieces.SUNFLOWER_TURN
    made = []
    for dusk, tag in ((False, ""), (True, "-dusk")):
        made.append(out(sheet([pieces.bench_end(h, dusk=dusk).im for h in turn]), f"bench-end{tag}.png", scale=1))
        made.append(out(sheet([pieces.bench_end("L", c, dusk=dusk).im for c in pieces.CAT_POKE]),
                        f"bench-end-wake{tag}.png", scale=1))
        made.append(out(pieces.vending_piece(dusk=dusk), f"vending-foot{tag}.png", scale=1))
        made.append(out(sheet([pieces.vending_piece(dusk=dusk, **s).im for s in pieces.VENDING_POKE]),
                        f"vending-can{tag}.png", scale=1))
    made.append(out(pieces.crossing_blink(0), "crossing.png", scale=1))
    made.append(out(sheet([pieces.crossing_blink(f).im for f in range(6)]), "crossing-blink.png", scale=1))
    return made


JOBS["pokes"] = poke_jobs
JOBS["sprites"] = lambda: write_sprites("/tmp/showa-platform-sprites.png")


if __name__ == "__main__":
    main(sys.argv[1:])
