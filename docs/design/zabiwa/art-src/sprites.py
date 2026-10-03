"""Zabiwa's pieces: Nox as a porcelain mask under a gilt crown, the five avatars, fifteen medals.

One world with the fresques: bone porcelain, gilt, vermilion lips and crosses, ultramarine, black.
Writes themes/zabiwa/sprites.json; `--png <file>` also renders a sheet to look at.

    python3 docs/design/zabiwa/art-src/sprites.py [--png sheet.png]
"""

import json
import sys
from pathlib import Path

THEME = Path(__file__).resolve().parents[4] / "themes" / "zabiwa"
PALETTE = {
    "k": "outline", "n": "dark", "l": "mid-dark", "L": "mid", "m": "mist",
    "c": "light", "C": "light-dim", "e": "accent", "E": "accent-hi", "r": "accent-deep",
    "p": "alert", "g": "good", "v": "familiar", "V": "familiar-mid", "w": "familiar-deep",
}  # fmt: skip

# ---------- Nox: a porcelain mask in a black hood, a gilt halo behind (the fresques' saints) ----------
def sym(half: str) -> str:
    return half + half[::-1]


def layer(base: list[str], top: list[str]) -> list[str]:
    """`top` drawn over `base`; "." in `top` lets the base show."""
    return ["".join(t if t != "." else b for b, t in zip(br, tr)) for br, tr in zip(base, top)]


MASK = [
    sym("....eEEE"),
    sym("...eE..."),
    sym("..eE.kkk"),
    sym("..e.kkcc"),
    sym(".e.kkccc"),
    sym(".e.kcccc"),
    sym(".e.kcccc"),  # 6: brow
    sym(".e.kcccc"),  # 7: eyes
    sym("..ekcccc"),  # 8: under the eyes
    sym("..ekcccC"),  # 9: nose
    sym("...kcccc"),  # 10: lips
    sym("...kkccc"),
    sym("....kkcc"),
    sym(".....kkk"),
    sym("......ee"),  # 14: the gilt pendant
    sym(".......E"),
]


def nox(rows: dict[int, str], halo: str = "e") -> list[str]:
    grid = [r.replace("e", halo) if i < 9 else r for i, r in enumerate(MASK)]
    for i, row in rows.items():
        grid[i] = layer([grid[i]], [row])[0]
    assert len(grid) == 16 and all(len(r) == 16 for r in grid), grid
    return grid


LIPS = {10: sym(".......p")}
NOX = {
    "nox.idle": nox({6: sym(".....CC."), 7: sym(".....kk."), 8: sym(".....v.."), **LIPS}),
    "nox.blink": nox({7: sym("....Ckk."), 8: sym(".....v.."), **LIPS}),
    "nox.listening": nox({7: sym(".....kE."), 8: sym(".....v.."), 10: sym("......pp")}, halo="E"),
    "nox.thinking": nox({0: "....eEEEEEEe..E.", 1: "...eE......Ee.E.", 6: "....kkc...kkc...".ljust(16, "."),
                         7: sym(".....cc."), 10: sym(".......p")}),
    "nox.happy": nox({6: sym(".....kk."), 7: sym("....k..."), 8: sym(".....v.."), 10: sym("......pp"), 11: sym(".......p")}),
    "nox.error": nox({6: sym("....p.p."), 7: sym(".....p.."), 8: sym("....p.p."), 10: sym("......kk"),
                      4: ".e.kkcccpccccc".ljust(16, ".")}),
}

# ---------- avatars: 16 × 16, filling the ring ----------
AVATARS = {
    # A bone crescent with a gilt rim and one gilt star, on ultramarine night.
    "avatar.moon": [
        ".....wwwwww.....",
        "...wwwwwwwwww...",
        "..wwwwccccwwEw..",
        ".wwwcccCCwwwwww.",
        ".wwccCCwwwwwwww.",
        "wwccCCwwwwwwwwww",
        "wwccCwwwwwwwwwww",
        "wcccCwwwwwwwwEww",
        "wcccCwwwwwwwEEEw",
        "wwccCwwwwwwwwEww",
        "wwccCCwwwwwwwwww",
        ".wwccCCwwwwwwww.",
        ".wwwcccCCwwwwww.",
        "..wwwwccccwwww..",
        "...wwwwwwwwww...",
        ".....wwwwww.....",
    ],
    # A black bat crossing a gilt moon, vermilion eyes.
    "avatar.bat": [
        ".....eeeeee.....",
        "...eeEEEEEEee...",
        "..eEEEEEEEEEee..",
        ".eEEEEEEEEEEEee.",
        ".eEEEEkEEkEEEee.",
        "eEEEEEkkkkEEEeee",
        "ekEEEkkpkpkkEEke",
        "ekkEkkkkkkkkkkke",
        "ekkkkkkkkkkkkkke",
        "ekkkkkkkkkkkkkke",
        "eekkkkkkkkkkkkee",
        ".eekkeekkeekkee.",
        ".eekeeeekeeeeke.",
        "..eeeeeeeeeeee..",
        "...eerrrrrree...",
        ".....eeeeee.....",
    ],
    # A raven on a branch against ultramarine night, a bone moon behind, a gilt eye.
    "avatar.raven": [
        ".....wwwwww.....",
        "...wwwwwwwwww...",
        "..wwwwwwwwCccw..",
        ".wwwwwkkkwwCccw.",
        ".wwwwkkkkkwwCcw.",
        "wwwwkkEkkkwwwCcw",
        "wwwkkkkkkkwwwwww",
        "wwkkkwkkkkkwwwww",
        "wwwwwwkkkkkkwwww",
        "wwwwwwkkkkkkkwww",
        "wwwwwwkkkkkkkkww",
        ".wwwwwwkkkkkkkw.",
        ".wwwwwwwkkkwwkkw",
        "..rrrrrrrerrrrr.",
        "...wwwwkwwkwww..",
        ".....wwwwww.....",
    ],
    # The vermilion rose of the fresques, jade leaves, on black.
    "avatar.rose": [
        ".....nnnnnn.....",
        "...nnnnnnnnnn...",
        "..nnnnppppnnnn..",
        ".nnnnppkpppnnnn.",
        ".nnnppkppkppnnn.",
        "nnnnpkppppkpnnnn",
        "nnnnpppkkpppnnnn",
        "nnnnnppppppnnnnn",
        "nnnnnnppppnnnnnn",
        "nnggnnnkknnnggnn",
        "nnnggnnkknnggnnn",
        ".nnnggnkkngnnnn.",
        ".nnnnnnkknnnnnn.",
        "..nnnnnkknnnnn..",
        "...nnnnnnnnnn...",
        ".....nnnnnn.....",
    ],
    # The white mask with the red cross, the hood around it.
    "avatar.ghost": [
        ".....kkkkkk.....",
        "...kkkcccckkk...",
        "..kkccccccccck..",
        ".kkcccccpccccck.",
        ".kccccccpcccccc.",
        "kkccpppppppppcck",
        "kkcccccCpCcccckk",
        "kkcckkccpcckkckk",
        "kkcckpccpccpkckk",
        "kkccccccpcccccck",
        "kkcccccCCCccccck",
        ".kkcccccpccccck.",
        ".kkkcccppccccck.",
        "..kkkccccccckk..",
        "...kkkkcccckk...",
        ".....kkkkkk.....",
    ],
}

# ---------- medals: a gilt medallion, a bone or vermilion emblem inside ----------
RING = [
    ".....eeeeee.....",
    "...eeEEEEEEee...",
    "..eEEkkkkkkeee..",
    ".eEkkkkkkkkkkre.",
    ".eEkkkkkkkkkkre.",
    "eEkkkkkkkkkkkkre",
    "eEkkkkkkkkkkkkre",
    "eEkkkkkkkkkkkkre",
    "eEkkkkkkkkkkkkre",
    "eEkkkkkkkkkkkkre",
    "eEkkkkkkkkkkkkre",
    ".eEkkkkkkkkkkre.",
    ".eekkkkkkkkkkre.",
    "..eeekkkkkkrre..",
    "...eerrrrrree...",
    ".....eeeeee.....",
]
EMBLEMS = {  # 8 × 8, set into the medallion at (4, 4); "." shows the black field
    "dj": ["..cccc..", ".cmmmmc.", "cmmccmmc", "cmcppcmc", "cmcppcmc", "cmmccmmc", ".cmmmmc.", "..cccc.."],
    "explorer": ["...c....", "...cc...", "..ccc...", "pppcEccc", "cccEcppp", "...ccc..", "...cc...", "....c..."],
    "night_owl": ["..cc....", ".cc...E.", "cc....EE", "cc......", "cc...E..", "ccc.....", ".cccc...", "..cccc.."],
    "early_bird": ["...E....", "E..E..E.", ".E.EE.E.", "..EEEE..", "EEEEEEEE", "........", "cccccccc", "........"],
    "weekend": ["c......c", "cc....cc", "cpc..cpc", "cppccppc", ".cppppc.", "..cppc..", "...cc...", "..cccc.."],
    "genre_guardian": ["cccccccc", "cccppccc", "cccppccc", "cppppppc", "cccppccc", ".ccppcc.", "..cccc..", "...cc..."],
    "broken_record": ["..cccc..", ".cmm.mc.", "cmmc.pmc", "cmc.pcmc", "cm.ppcmc", "cmp.cmmc", ".cm.mmc.", "..c.cc.."],
    "marathon": ["cccccccc", ".cEEEEc.", "..cEEc..", "...cc...", "...cc...", "..cppc..", ".cppppc.", "cccccccc"],
    "radio_host": ["..cccc..", ".cmcmcc.", ".ccmcmc.", ".cmcmcc.", "..cccc..", "...cc...", "p..cc..p", ".pccccp."],
    "task_hero": [".......c", "......cc", ".....cc.", "c...cc..", "cc.cc...", ".ccc....", "..c.....", "pppppppp"],
    "grocery_runner": ["...cc...", "..c..c..", ".c....c.", "cccccccc", "cmcmcmcc", ".cmcmcc.", ".cmcmcc.", "..cccc.."],
    "planner": ["c.c..c.c", "cccccccc", "cmmmmmmc", "cmcmcmcc", "cmcmcpcc", "cmcmcmcc", "cmmmmmmc", "cccccccc"],
    "wall_poet": ["......cc", ".....cmc", "....cmc.", "...cmc..", "..cmc...", ".cmc....", ".pc.....", "p.......",],
    "courier": ["cccccccc", "ccmmmmcc", "cmcmmcmc", "cmmccmmc", "cmmmmmmc", "cccccccc", "...pp...", "....p..."],
    "curator": ["........", "..cccc..", ".cc..cc.", "cc.EE.cc", "cc.Ek.cc", ".cc..cc.", "..cccc..", "........"],
}


def medal(emblem: list[str]) -> list[str]:
    rows = [list(r) for r in RING]
    for y, row in enumerate(emblem):
        for x, ch in enumerate(row):
            if ch != ".":
                rows[4 + y][4 + x] = ch
    return ["".join(r) for r in rows]


def glyphs() -> dict[str, list[str]]:
    out = {**NOX, **AVATARS, **{f"title.{k}": medal(v) for k, v in EMBLEMS.items()}}
    for name, grid in out.items():
        assert len(grid) <= 16 and all(len(r) <= 16 for r in grid), name
        assert set("".join(grid)) <= set(PALETTE) | {"."}, (name, set("".join(grid)) - set(PALETTE))
    return out


def sheet(path: str, grid: dict[str, list[str]]) -> None:
    from PIL import Image, ImageDraw

    tokens = json.loads((THEME / "tokens.json").read_text())["color"]["sprite"]
    rgb = {k: tokens[v]["$value"] for k, v in PALETTE.items()}
    s, per = 12, 8
    names = list(grid)
    im = Image.new("RGB", (per * 17 * s, (len(names) // per + 1) * 17 * s), "#222222")
    draw = ImageDraw.Draw(im)
    for i, name in enumerate(names):
        ox, oy = (i % per) * 17 * s, (i // per) * 17 * s
        for y, row in enumerate(grid[name]):
            for x, ch in enumerate(row):
                if ch != ".":
                    draw.rectangle([ox + x * s, oy + y * s, ox + x * s + s - 1, oy + y * s + s - 1], rgb[ch])
    im.save(path)


if __name__ == "__main__":
    grid = glyphs()
    (THEME / "sprites.json").write_text(
        json.dumps({"$description": "Zabiwa's pieces, made by docs/design/zabiwa/art-src/sprites.py.",
                    "palette": PALETTE, "glyphs": grid}, indent=1) + "\n")  # fmt: skip
    if "--png" in sys.argv:
        sheet(sys.argv[sys.argv.index("--png") + 1], grid)
    print(f"{len(grid)} pieces")
