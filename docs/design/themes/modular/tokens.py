"""Modular's tokens, written as data: tokens.json (the system), tokens.light.json and
tokens.dark.json (the two inks). Run from the repository: python3 docs/design/themes/modular/tokens.py
Each file is written atomically (a temp file, then a rename) so a parallel build never reads half."""

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEME = HERE.parents[3] / "themes" / "modular"

# The three inks. The art is drawn in exactly these, so the page's own ground can swallow it.
PAPER = "#F2EFE8"  # warm poster paper, never blue
INK = "#141312"  # warm black
RED = "#EE3A1F"  # signal vermilion: the art's red where one picture serves both schemes
RED_L = "#CC2812"  # the light scheme's red: paper words on it pass 4.5
RED_D = "#FF4F2E"  # the dark scheme's red: black words on it pass 4.5


def v(value, desc=None):
    out = {"$value": value}
    if desc:
        out["$description"] = desc
    return out


def group(kind, items, desc=None):
    out = {"$type": kind} if kind else {}
    if desc:
        out["$description"] = desc
    for k, val in items.items():
        out[k] = val if isinstance(val, dict) and ("$value" in val or "$type" in val) else (
            group(None, val) if isinstance(val, dict) else v(val))
    return out


def typo(family, size, weight, height, track=0, case=None):
    t = {"fontFamily": "{font." + family + "}", "fontSize": size, "fontWeight": weight, "lineHeight": height}
    if track:
        t["letterSpacing"] = track
    if case:
        t["textTransform"] = case
    return v(t)


# ---------------------------------------------------------------- the system (both schemes)
system = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Modular: Swiss modular typography as a house. One grid of modules, black and white in duality, one signal red.",
    "font": group("fontFamily", {
        "display": ["Jersey 15", "sans-serif"],
        "body": ["Schibsted Grotesk", "sans-serif"],
        "mono": ["Space Mono", "monospace"],
    }),
    "text": group("typography", {
        # Jersey 15: a grotesk built on a square grid, heavy at one weight. Big and tight.
        "display-xl": typo("display", 48, 400, 1.0, -0.01),
        "display-l": typo("display", 37, 400, 1.0, -0.01),
        "display-m": typo("display", 29, 400, 1.05),
        "brand": typo("display", 25, 400, 1.1),
        "title-l": typo("body", 22, 700, 1.2, -0.01),
        "title-m": typo("body", 18, 700, 1.25, -0.01),
        "title-s": typo("body", 16, 700, 1.3),
        "body-l": typo("body", 18, 400, 1.45),
        "body-m": typo("body", 16, 400, 1.45),
        "body-s": typo("body", 14, 400, 1.45),
        "action": typo("body", 15, 600, 1.2, 0.01),
        "label": typo("body", 12, 600, 1.3, 0.09, "uppercase"),
        "caption": typo("body", 12, 500, 1.35, 0.02),
        "numeric": typo("mono", 13, 400, 1.3),
    }),
    "radius": group("dimension", {
        "xs": 0, "s": 0, "m": 0, "l": 0, "xl": 0,
        "control": "{radius.none}", "card": "{radius.none}", "sheet": "{radius.none}",
        "media": "{radius.none}", "chip": "{radius.full}", "avatar": "{radius.full}",
    }, "Squares and circles, nothing in between: boxes are square, chips and people are round."),
    "elev": group("shadow", {"1": "none", "2": "none", "3": "none", "4": "none"},
                  "No soft shadows: hierarchy comes from rules, black blocks and the red module."),
    "material": {
        "surface": group(None, {
            "border": v("1px solid {color.border.default}"), "shadow": v("none"),
        }),
        # the chosen segment: a paper tile boxed in ink (raised's shadow only draws there)
        "raised": group(None, {"border": v("1px solid {color.border.strong}"),
                               "shadow": v("inset 0 0 0 2px {color.fg.default}")}),
        "overlay": group(None, {"border": v("1px solid {color.border.strong}"), "shadow": v("none")}),
        "sunken": group(None, {"border": v("1px solid {color.border.strong}")}),
        "media": group(None, {"border": v("1px solid transparent"), "shadow": v("none")}),
        "paper": group(None, {"shadow": v("none")}),
    },
    "part": {
        "status": {
            "border": {"$type": "string", "$value": "1px solid {color.border.strong}"},
            "art-opacity": {"$type": "string", "$value": "1"},
        },
        "rail": {
            "border": {"$type": "string", "$value": "1px solid {color.border.strong}"},
        },
        "dock": {
            "border": {"$type": "string", "$value": "1px solid {color.border.strong}"},
        },
        "control": {
            "shadow": {"$type": "shadow", "$value": "none"},
        },
        "header": {
            "banner-wash": {"$type": "number", "$value": 0},
        },
        "nowbar": {
            "radius": {"$type": "dimension", "$value": "{radius.none}"},
            "shadow": {"$type": "shadow", "$value": "none"},
        },
        "panel": {
            "shadow": {"$type": "shadow", "$value": "none"},
            # the module in the corner: every panel is a sheet of the same grid
            "texture": {"$type": "string", "$value":
                        "linear-gradient({color.fg.default}, {color.fg.default}) top left / 8px 8px no-repeat"},
        },
        "sheet": {
            "shadow": {"$type": "shadow", "$value": "none"},
            # a poster's head: a black band along the top, the red module at its start
            "texture": {"$type": "string", "$value":
                        "linear-gradient({color.accent.solid}, {color.accent.solid}) top left / 48px 8px no-repeat, "
                        "linear-gradient({color.fg.default}, {color.fg.default}) top left / 100% 8px no-repeat"},
        },
        "meter": {
            "track": {"$type": "color", "$value": "{color.bg.pressed}"},
            "thumb-radius": {"$type": "dimension", "$value": "{radius.full}"},
            # The fill is cut into modules: a dot-matrix bar.
            "pattern": {"$type": "string", "$value":
                        "repeating-linear-gradient(90deg, transparent 0 6px, {color.bg.canvas} 6px 8px)"},
        },
    },
    "dur": group("duration", {"fast": 80, "base": 140, "slow": 200, "slower": 280}),
    "ease": group("cubicBezier", {
        "standard": [0.7, 0, 0.2, 1],
        "enter": "steps(4)",
        "exit": [0.5, 0, 1, 1],
        "emphasized": "steps(3)",
    }, "Snappy; things arrive in steps, like a module flipping."),
    "icon": {"stroke": {"$type": "number", "$value": 2}},
}


# ---------------------------------------------------------------- the two inks
def scheme(paper, ink, *, dark):
    """One scheme's colours. `paper` is the ground, `ink` the text: the dark scheme swaps them."""
    mid = lambda share: f"mix({ink}, {paper}, {share}%)"  # noqa: E731  a tone between the inks
    red_text = "#FF5B3F" if dark else "#B8260F"
    red = RED_D if dark else RED_L
    return {
        "$schema": "../_schema/tokens.schema.json",
        "$description": ("Modular, dark: black paper, white ink, the same red." if dark
                         else "Modular, light: warm paper, black ink, one signal red."),
        "seed": group("color", {
            "neutral": "oklch(0.55 0.006 80)",
            "accent": ink,
            "success": "oklch(0.74 0.12 185)" if dark else "oklch(0.52 0.1 190)",
            "warning": "oklch(0.82 0.15 85)" if dark else "oklch(0.58 0.12 75)",
            "danger": "oklch(0.64 0.22 5)" if dark else "oklch(0.45 0.19 8)",
            "info": "oklch(0.7 0.13 250)" if dark else "oklch(0.48 0.16 258)",
            "private": "oklch(0.72 0.1 300)" if dark else "oklch(0.5 0.12 300)",
        }),
        "color": {
            "$type": "color",
            "bg": group(None, {
                "canvas": paper, "surface": paper, "raised": paper, "overlay": paper,
                "sunken": mid(5), "inverse": ink,
                "hover": mid(8), "pressed": mid(18), "selected": mid(16),
                "current": ink,  # where you are: an ink block with paper words
            }),
            "fg": group(None, {
                "default": ink, "muted": mid(70), "subtle": mid(66), "placeholder": mid(68),
                "disabled": mid(38), "inverse": paper, "on-accent": paper, "link": ink, "current": paper,
            }),
            "border": group(None, {"subtle": mid(18), "default": mid(80), "strong": ink}),
            "focus-ring": v(ink),
            "accent": group(None, {
                # the accent is the ink: chosen chips, switches, slider fills are black blocks;
                # red is only the main button (part.control.primary-bg) and its hover
                "solid": ink, "solid-hover": "#FF6A4D" if dark else "#A82010",
                "soft": mid(7),
                "fg": red_text, "border": ink,
            }),
            "paper": group(None, {"bg": paper, "fg": ink, "muted": mid(70)}),
            # Unified rooms: every room's light is the ink (selected marks, progress): black blocks.
            "room": group(None, {r: ink for r in (
                "home", "listen", "watch", "house", "files", "ask", "me", "control",
                "smart-home", "inbox", "space", "party", "games")}),
            # people: ink discs with paper initials, eight steps of the ink so each stays their own
            "person": group(None, {str(n + 1): mid(100 - 7 * n) for n in range(8)}),
            "data": group(None, {
                "1": red, "2": ink, "3": mid(50),
                "4": "oklch(0.62 0.13 255)" if dark else "oklch(0.48 0.14 258)",
                "5": "oklch(0.8 0.14 90)" if dark else "oklch(0.6 0.12 85)", "6": mid(70),
                "7": "oklch(0.7 0.13 150)" if dark else "oklch(0.5 0.11 155)",
                "8": "oklch(0.68 0.14 330)" if dark else "oklch(0.52 0.15 335)",
            }),
            "scrim": v(f"alpha({paper}, 78%)" if not dark else f"alpha({paper}, 80%)"),
            "media-scrim": v("alpha(#000000, 66%)"),
            "shadow": v(INK),
            "sprite": group(None, {
                "outline": ink, "dark": mid(80), "mid-dark": mid(55), "mid": mid(35),
                "mist": mid(20), "light": ink, "light-dim": mid(70),
                "accent": red, "accent-hi": "#FF7A5E", "accent-deep": "#B0240E",
                "familiar": ink, "familiar-mid": mid(60), "familiar-deep": mid(85),
                "good": "{ramp.success.9}", "alert": "{ramp.danger.9}",
                "paper": paper, "ink": ink,
            }, "k ink · c paper · e red · n/l/L/m ink tones toward paper"),
        },
        "part": {
            "control": {"primary-bg": {"$type": "string", "$value": red}},
            # quiet buttons on the page stand on a module tile, so they keep an edge by night
            "page": {"quiet": {"$type": "color", "$value": mid(6)}},
        },
    }


def write(name, data):
    path = THEME / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    write("tokens.json", system)
    write("tokens.light.json", scheme(PAPER, INK, dark=False))
    write("tokens.dark.json", scheme(INK, PAPER, dark=True))
    print("tokens written")
