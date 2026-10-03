"""Writes themes/showa-platform/tokens.json and theme.json (atomically). The colours that also
live in the pictures come from px.PAL / px.LINES, so the enamel on screen and in the art match."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from px import LINES, PAL, THEME, write_json  # noqa: E402


def v(value, kind=None, note=None):
    out = {"$value": value}
    if kind:
        out["$type"] = kind
    if note:
        out["$description"] = note
    return out


tokens = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Shōwa Platform: navy lettering on cream enamel, one signal red, a summer sky, a line colour per room.",
    "seed": {
        "$type": "color",
        "neutral": v("oklch(0.44 0.065 262)"),
        "accent": v("oklch(0.555 0.175 33)"),
        "success": v("oklch(0.52 0.12 148)"),
        "warning": v("oklch(0.6 0.13 70)"),
        "danger": v("oklch(0.46 0.17 12)"),
        "info": v("oklch(0.5 0.12 250)"),
        "private": v("oklch(0.5 0.13 318)"),
    },
    "color": {
        "$type": "color",
        "bg": {
            "canvas": v("#f1e7cd", note="the platform's sunlit concrete"),
            "surface": v(PAL["c1"], note="cream enamel"),
            "raised": v("#fbf5e6"),
            "overlay": v(PAL["c1"]),
            "sunken": v(PAL["c0"], note="white enamel: fields"),
            "hover": v(PAL["c2"]),
            "pressed": v("#dfcea4"),
            "selected": v("#ead7a6", note="a warm cream step: the chosen door"),
            "inverse": v(PAL["n1"]),
        },
        "fg": {"inverse": v(PAL["c1"])},
        "accent": {"soft": v("#f2e2bb", note="a warm cream step, never salmon")},
        "border": {
            "subtle": v("#ddcda4"),
            "default": v("#c7b27f"),
            "strong": v("#76748b", note="control edges, 3:1 on every ground"),
        },
        "paper": {
            "bg": v(PAL["p1"], note="the card ticket's pale green"),
            "fg": v("{ramp.neutral.12}"),
            "muted": v("{ramp.neutral.11}"),
        },
        "room": {k: v(h) for k, h in LINES.items()},
        "person": {str(i + 1): v(h) for i, h in enumerate(
            ["#c4582a", "#2f78b0", "#4a8a3a", "#a8467e", "#94761a", "#1d8a82", "#8a4fa0", "#c0395a"])},
        "sprite": {
            "outline": v(PAL["n1"]), "dark": v(PAL["n2"]), "mid-dark": v(PAL["t1"]), "mid": v(PAL["n4"]),
            "mist": v(PAL["k2"]), "light": v(PAL["n3"]), "light-dim": v(PAL["c3"]), "paper": v(PAL["c0"]),
            "accent": v(PAL["r2"]), "accent-hi": v(PAL["r3"]), "accent-deep": v(PAL["r1"]),
            "familiar": v(PAL["o1"]), "familiar-mid": v(PAL["o2"]), "familiar-deep": v(PAL["o0"]),
            "good": v(PAL["g2"]), "alert": v(PAL["y2"]), "ink": v(PAL["b2"]),
        },
        "shadow": v(PAL["n0"]),
        "scrim": v("alpha(#1f2b4d, 45%)"),
    },
    "radius": {
        "$type": "dimension",
        "xs": v(2), "s": v(3), "m": v(4), "l": v(6), "xl": v(8),
        "chip": v("{radius.xs}"), "card": v("{radius.s}"), "sheet": v("{radius.l}"),
    },
    "elev": {
        "$type": "shadow",
        "1": v("0 1px 0 alpha(#1f2b4d, 22%)"),
        "2": v("0 2px 0 alpha(#1f2b4d, 20%)"),
        "3": v("0 2px 0 alpha(#1f2b4d, 22%), 0 8px 18px alpha(#1f2b4d, 16%)"),
        "4": v("0 3px 0 alpha(#1f2b4d, 22%), 0 16px 40px alpha(#1f2b4d, 24%)"),
    },
    "material": {
        "canvas": {"texture": v("url(art/slab.png)", "string")},
        "surface": {
            "border": v("1px solid {color.border.subtle}", "string"),
            "shadow": v("{elev.1}", "shadow"),
        },
        "raised": {"border": v("1px solid {color.border.default}", "string")},
        "sunken": {"border": v("1px solid {color.border.strong}", "string"),
                   "shadow": v("inset 0 2px 0 alpha(#1f2b4d, 8%)", "shadow")},
        "overlay": {"border": v("1px solid {ramp.neutral.9}", "string")},
        "paper": {"texture": v("none", "string"), "rotate": v("1deg", "string")},
        "screen": {
            "bg": v("#dbe9f3", "color"),
            "glow": v("0 0 0 1px alpha(#2e4172, 30%)", "shadow"),
        },
    },
    "font": {
        "$type": "fontFamily",
        "display": v(["Dela Gothic One", "serif"]),
        "body": v(["Barlow", "sans-serif"]),
        "mono": v(["Overpass Mono", "monospace"]),
    },
    "text": {
        "$type": "typography",
        "display-xl": v({"fontFamily": "{font.display}", "fontSize": 44, "fontWeight": 400, "lineHeight": 1.1}),
        "display-l": v({"fontFamily": "{font.display}", "fontSize": 34, "fontWeight": 400, "lineHeight": 1.15}),
        "display-m": v({"fontFamily": "{font.display}", "fontSize": 27, "fontWeight": 400, "lineHeight": 1.2}),
        "brand": v({"fontFamily": "{font.display}", "fontSize": 18, "fontWeight": 400, "lineHeight": 1.2}),
        "title-l": v({"fontFamily": "{font.body}", "fontSize": 22, "fontWeight": 700, "lineHeight": 1.25}),
        "title-m": v({"fontFamily": "{font.body}", "fontSize": 18, "fontWeight": 700, "lineHeight": 1.3}),
        "title-s": v({"fontFamily": "{font.body}", "fontSize": 16, "fontWeight": 700, "lineHeight": 1.3}),
        "body-l": v({"fontFamily": "{font.body}", "fontSize": 18, "fontWeight": 400, "lineHeight": 1.5}),
        "body-m": v({"fontFamily": "{font.body}", "fontSize": 16, "fontWeight": 400, "lineHeight": 1.5}),
        "body-s": v({"fontFamily": "{font.body}", "fontSize": 15, "fontWeight": 400, "lineHeight": 1.4}),
        "action": v({"fontFamily": "{font.body}", "fontSize": 16, "fontWeight": 600, "lineHeight": 1.15}),
        "label": v({"fontFamily": "{font.body}", "fontSize": 14, "fontWeight": 600, "lineHeight": 1.15, "letterSpacing": 0.02}),
        "caption": v({"fontFamily": "{font.body}", "fontSize": 13, "fontWeight": 500, "lineHeight": 1.3, "letterSpacing": 0.01}),
        "numeric": v({"fontFamily": "{font.mono}", "fontSize": 14, "fontWeight": 600, "lineHeight": 1.2}),
    },
    "dur": {"$type": "duration", "fast": v(90), "base": v(160), "slow": v(240), "slower": v(360)},
    "ease": {
        "$type": "cubicBezier",
        "standard": v([0.6, 0, 0.1, 1]),
        "enter": v("steps(4)"),
        "emphasized": v([0.7, 0, 0.2, 1]),
    },
    "icon": {"stroke": v(2, "number")},
    "part": {
        "page": {"scrim": v("transparent", "color")},
        "status": {
            "bg": v(PAL["c1"], "color"),
            "border": v("1px solid {ramp.neutral.12}", "string"),
            "art-opacity": v("1", "string"),
        },
        "rail": {
            "bg": v("#efe3c4", "color"),
            "border": v("1px solid {ramp.neutral.12}", "string"),
            "texture": v("url(art/clapboard.png)", "string"),
        },
        "dock": {
            "bg": v(PAL["c1"], "color"),
            "border": v("1px solid {color.border.default}", "string"),
        },
        "nowbar": {
            "bg": v("transparent", "color"),
            "border": v("1px solid transparent", "string"),
            "radius": v(0, "dimension"),
            "shadow": v("none", "shadow"),
        },
        "header": {"banner-fade": v(PAL["c1"], "color"), "banner-wash": v(0, "number")},
        "hero": {"fade": v("28%", "string")},
        "panel": {
            "bg": v("transparent", "color"),
            "border": v("1px solid transparent", "string"),
            "radius": v(0, "dimension"),
            "shadow": v("none", "shadow"),
            "head": v("{color.accent.fg}", "color"),
        },
        "sheet": {
            "bg": v("transparent", "color"),
            "border": v("1px solid transparent", "string"),
            "radius": v(0, "dimension"),
        },
        "control": {
            "bg": v("linear-gradient(180deg, alpha(#ffffff, 70%), alpha(#ffffff, 0%) 55%) {color.bg.raised}", "string",
                    "cream enamel, the light catching its top"),
            "shadow": v("0 2px 0 alpha(#1f2b4d, 22%)", "shadow", "the plate's lip"),
            "primary-bg": v("linear-gradient(180deg, alpha(#ffe3c8, 28%), alpha(#ffe3c8, 0%) 50%, alpha(#6e1c18, 18%)) {color.accent.solid}",
                            "string", "signal-red enamel"),
            "primary-shadow": v("inset 0 1px 0 alpha(#ffffff, 30%), 0 2px 0 alpha(#6e1c18, 55%)", "shadow"),
        },
        "meter": {
            "pattern": v("repeating-linear-gradient(90deg, transparent 0 11px, alpha(#fffaf0, 80%) 11px 13px)", "string",
                         "a strip of tickets: a perforation every 13 px"),
            "thumb": v(PAL["n1"], "color"),
            "thumb-radius": v(2, "dimension"),
        },
    },
}

manifest_extra = {
    "slots": {
        "status.backdrop": {"image": "art/status.png", "rendering": "pixel", "fit": "cover"},
        "home.hero.backdrop": {"image": "art/hero.png", "rendering": "pixel", "fit": "cover"},
        "auth.crest": {"image": "art/crest.png", "rendering": "pixel", "fit": "contain"},
        "watch.tv.bezel": {"image": "art/tv.png", "rendering": "pixel", "fit": "contain"},
        "space.room.scene": {"image": "art/office.png", "rendering": "pixel", "fit": "cover"},
        "state.empty": {"image": "art/empty.png", "rendering": "pixel", "fit": "contain"},
        "header.banner": {"image": "art/board-listen.png", "rendering": "pixel", "fit": "cover", "anchor": "top",
                          "rooms": {r: f"art/board-{r}.png" for r in LINES if r not in ("home", "listen")}},
        "panel.surface": {"image": "art/plate.png", "rendering": "pixel", "fit": "slice", "slice": 16},
        "sheet.surface": {"image": "art/plate.png", "rendering": "pixel", "fit": "slice", "slice": 16},
        "deck.surface": {"image": "art/pa-box.png", "rendering": "pixel", "fit": "slice", "slice": 16},
        "nowbar.surface": {"image": "art/ticket.png", "rendering": "pixel", "fit": "slice", "slice": 28},
        "dock.surface": {"image": "art/dock.png", "rendering": "pixel", "fit": "cover", "anchor": "top"},
    },
    "layers": [],  # dusk_tokens.layers() fills it: day and dusk layers, pokes
}

import dusk_tokens  # noqa: E402

for slot, picture in dusk_tokens.PICTURES.items():
    manifest_extra["slots"][slot]["schemes"] = {"dark": "art/" + picture}
manifest_extra["layers"] = dusk_tokens.layers()

if __name__ == "__main__":
    import json

    write_json(THEME / "tokens.json", tokens)
    write_json(THEME / "tokens.dark.json", dusk_tokens.tokens)
    m = json.loads((THEME / "theme.json").read_text())
    m.update(manifest_extra)
    m["schemes"] = ["light", "dark"]
    m["parts"] = {"header": "banner", "panel": "card", "dock": "flush", "nowbar": "docked"}
    m["author"] = "Shōwa Platform studio (drawn by code)"
    write_json(THEME / "theme.json", m)
    print("ok")
