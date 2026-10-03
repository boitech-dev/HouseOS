"""Kinari's tokens.json, written atomically (a parallel build never reads half a file).
    python3 docs/design/themes/linen-morning/tokens.py
Palette (OKLCH): kinari ground, washi surfaces, kraft edges, walnut structure, sumi ink,
one hanko vermilion used tiny (focus ring, slider seal, sprites)."""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "themes/linen-morning/tokens.json"

SUMI = "oklch(0.25 0.014 55)"
WALNUT = "oklch(0.37 0.04 52)"
KRAFT = "oklch(0.62 0.07 66)"
KINARI = "oklch(0.925 0.021 80)"
WASHI = "oklch(0.958 0.013 84)"
HANKO = "oklch(0.55 0.175 33)"


def c(v):
    return {"$value": v}


def text(family, size, weight, line, tracking=None, case=None):
    v = {"fontFamily": family, "fontSize": size, "fontWeight": weight, "lineHeight": line}
    if tracking is not None:
        v["letterSpacing"] = tracking
    if case:
        v["textTransform"] = case
    return c(v)


def s(v, t="string"):
    return {"$type": t, "$value": v}


tokens = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Kinari: a quiet Japanese room in the morning. Unbleached cotton, washi, kraft, walnut and sumi; one small hanko red. Only what differs from Base (see BRIEF.md).",
    "seed": {
        "$type": "color",
        "neutral": c("oklch(0.55 0.03 70)"),
        "accent": c(SUMI),
        "success": c("oklch(0.56 0.1 138)"),
        "warning": c("oklch(0.6 0.12 78)"),
        "danger": c("oklch(0.46 0.15 29)"),
        "info": c("oklch(0.48 0.06 215)"),
        "private": c("oklch(0.45 0.06 268)"),
    },
    "color": {
        "$type": "color",
        "bg": {
            "canvas": c(KINARI),
            "surface": c(WASHI),
            "raised": c("oklch(0.968 0.011 84)"),
            "overlay": c("oklch(0.955 0.014 83)"),
            "sunken": c("oklch(0.905 0.022 78)"),
            "hover": c("oklch(0.89 0.026 76)"),
            "pressed": c("oklch(0.86 0.03 74)"),
            "selected": c("oklch(0.875 0.038 72)"),
            "inverse": c(SUMI),
        },
        "fg": {
            "default": c(SUMI),
            "muted": c("oklch(0.43 0.03 60)"),
            "subtle": c("oklch(0.45 0.03 62)"),
            "placeholder": c("oklch(0.47 0.03 64)"),
            "disabled": c("oklch(0.66 0.025 70)"),
            "inverse": c(WASHI),
            "on-accent": c(WASHI),
            "link": c(WALNUT),
        },
        "border": {
            "subtle": c("oklch(0.855 0.028 72)"),
            "default": c("oklch(0.78 0.04 68)"),
            "strong": c("oklch(0.56 0.05 60)"),
        },
        "focus-ring": c(HANKO),
        "accent": {
            "solid": c(SUMI),
            "solid-hover": c(WALNUT),
            "soft": c("oklch(0.885 0.03 72)"),
            "fg": c(WALNUT),
            "border": c("oklch(0.45 0.04 55)"),
        },
        "paper": {"bg": c("oklch(0.965 0.012 86)"), "fg": c(SUMI), "muted": c("oklch(0.43 0.03 60)")},
        "room": {
            "home": c("oklch(0.47 0.06 62)"),
            "listen": c("oklch(0.44 0.07 255)"),
            "watch": c("oklch(0.47 0.05 212)"),
            "house": c("oklch(0.52 0.07 125)"),
            "files": c("oklch(0.52 0.07 82)"),
            "ask": c("oklch(0.45 0.07 30)"),
            "me": c("oklch(0.51 0.05 172)"),
            "control": c("oklch(0.42 0.02 60)"),
            "games": c("oklch(0.52 0.07 48)"),
            "smart-home": c("oklch(0.5 0.05 105)"),
            "inbox": c("oklch(0.38 0.05 265)"),
            "space": c("oklch(0.45 0.06 152)"),
            "party": c("oklch(0.46 0.04 75)"),
        },
        "person": {
            "1": c("oklch(0.56 0.07 50)"),
            "2": c("oklch(0.46 0.07 255)"),
            "3": c("oklch(0.54 0.07 128)"),
            "4": c("oklch(0.47 0.07 30)"),
            "5": c("oklch(0.5 0.05 210)"),
            "6": c("oklch(0.6 0.07 85)"),
            "7": c("oklch(0.45 0.04 70)"),
            "8": c("oklch(0.4 0.03 55)"),
        },
        "shadow": c("oklch(0.3 0.035 55)"),
        "scrim": c("alpha(oklch(0.25 0.014 55), 38%)"),
        "sprite": {
            "outline": c(SUMI),
            "dark": c(WALNUT),
            "mid-dark": c("oklch(0.5 0.06 60)"),
            "mid": c(KRAFT),
            "mist": c("oklch(0.84 0.03 74)"),
            "light": c("oklch(0.42 0.03 58)"),
            "light-dim": c("oklch(0.9 0.022 78)"),
            "accent": c(HANKO),
            "accent-hi": c("oklch(0.66 0.15 38)"),
            "accent-deep": c("oklch(0.44 0.15 30)"),
            "familiar": c(SUMI),
            "familiar-mid": c("oklch(0.45 0.02 58)"),
            "familiar-deep": c("oklch(0.7 0.02 70)"),
            "good": c("oklch(0.5 0.09 132)"),
            "alert": c("oklch(0.5 0.15 29)"),
            "paper": c(WASHI),
            "ink": c(SUMI),
        },
        "scene": {
            "night-0": c(KINARI),
            "night-1": c(WASHI),
            "night-2": c("oklch(0.88 0.03 74)"),
            "line": c("oklch(0.62 0.05 64)"),
            "line-hi": c(WALNUT),
            "mist": c("oklch(0.8 0.03 72)"),
            "cream": c(WASHI),
            "ember": c(HANKO),
            "ember-hi": c("oklch(0.66 0.15 38)"),
            "ember-deep": c("oklch(0.44 0.15 30)"),
            "lilac": c("oklch(0.45 0.06 268)"),
            "moss": c("oklch(0.5 0.09 132)"),
        },
    },
    "font": {
        "$type": "fontFamily",
        "display": c(["Shippori Mincho", "serif"]),
        "body": c(["Zen Kaku Gothic New", "sans-serif"]),
        "mono": c(["M PLUS 1 Code", "monospace"]),
    },
    "text": {
        "$type": "typography",
        "display-xl": text("{font.display}", 44, 500, 1.15, 0.01),
        "display-l": text("{font.display}", 35, 500, 1.18, 0.01),
        "display-m": text("{font.display}", 28, 500, 1.22, 0.01),
        "brand": text("{font.display}", 18, 700, 1.2, 0.12),
        "title-l": text("{font.body}", 22, 500, 1.3),
        "title-m": text("{font.body}", 18, 500, 1.35),
        "title-s": text("{font.body}", 16, 700, 1.35),
        "body-l": text("{font.body}", 18, 400, 1.55),
        "body-m": text("{font.body}", 16, 400, 1.55),
        "body-s": text("{font.body}", 14, 400, 1.5),
        "action": text("{font.body}", 15, 500, 1.2, 0.02),
        "label": text("{font.body}", 13, 500, 1.25, 0.08),
        "caption": text("{font.body}", 12, 400, 1.4, 0.04),
        "numeric": text("{font.mono}", 14, 400, 1.2),
    },
    "radius": {
        "$type": "dimension",
        "xs": c(1),
        "s": c(2),
        "m": c(4),
        "l": c(6),
        "xl": c(8),
        "control": c("{radius.s}"),
        "card": c("{radius.m}"),
        "sheet": c("{radius.l}"),
        "chip": c("{radius.s}"),
        "media": c("{radius.xs}"),
        "avatar": c("{radius.full}"),
    },
    "elev": {
        "$type": "shadow",
        "1": c("0 1px 0 alpha({color.shadow}, 10%)"),
        "2": c("0 1px 0 alpha({color.shadow}, 8%), 0 3px 10px alpha({color.shadow}, 8%)"),
        "3": c("0 2px 0 alpha({color.shadow}, 6%), 0 10px 28px alpha({color.shadow}, 12%)"),
        "4": c("0 2px 0 alpha({color.shadow}, 8%), 0 18px 48px alpha({color.shadow}, 18%)"),
    },
    "material": {
        "canvas": {"texture": s("url(art/washi.webp)")},
        "surface": {
            "border": s("1px solid {color.border.subtle}"),
            "shadow": s("0 1px 0 alpha({color.shadow}, 7%)", "shadow"),
            "texture": s("url(art/washi-fine.webp)"),
        },
        "raised": {
            "border": s("1px solid {color.border.default}"),
            "shadow": s("0 1px 0 alpha({color.shadow}, 8%)", "shadow"),
        },
        "overlay": {"border": s("1px solid {color.border.default}")},
        "sunken": {"border": s("1px solid {color.border.strong}")},
        "paper": {
            "texture": s("url(art/washi-fine.webp)"),
            "shadow": s("0 1px 0 alpha({color.shadow}, 10%), 0 2px 6px alpha({color.shadow}, 6%)", "shadow"),
            "rotate": s("0.4deg"),
        },
        "media": {"border": s("1px solid alpha({color.shadow}, 14%)")},
    },
    "part": {
        "page": {"scrim": s("transparent", "color")},
        "status": {"border": s("1px solid oklch(0.27 0.03 250)"), "art-opacity": s("1")},
        "rail": {"border": s("1px solid {color.border.default}"), "texture": s("url(art/washi.webp)"),
                 "ink-shadow": s("0 0 6px {color.bg.surface}, 0 0 2px {color.bg.surface}")},
        "dock": {"border": s("1px solid transparent"), "texture": s("url(art/washi.webp)")},
        "nowbar": {"texture": s("url(art/washi-fine.webp)"), "border": s("1px solid {color.border.default}"),
                   "shadow": s("0 1px 0 alpha({color.shadow}, 8%), 0 8px 22px alpha({color.shadow}, 12%)", "shadow")},
        "header": {"banner-fade": s("{color.bg.canvas}", "color"), "banner-wash": {"$type": "number", "$value": 0}},
        "control": {
            "primary-shadow": s("inset 0 1px 0 alpha(#ffffff, 8%)", "shadow"),
        },
        "meter": {
            "track": s("oklch(0.8 0.035 70)", "color"),
            "thumb": s(HANKO, "color"),
            "thumb-radius": {"$type": "dimension", "$value": 2},
        },
    },
    "dur": {"$type": "duration", "fast": c(150), "base": c(300), "slow": c(460), "slower": c(760)},
    "ease": {
        "$type": "cubicBezier",
        "standard": c([0.4, 0, 0.2, 1]),
        "enter": c([0.2, 0, 0, 1]),
        "exit": c([0.4, 0, 0.6, 1]),
        "emphasized": c([0.3, 0.2, 0, 1]),
    },
    "icon": {"stroke": {"$type": "number", "$value": 1.4}},
}

tmp = OUT.with_name(".tokens.json.tmp")
tmp.write_text(json.dumps(tokens, indent=2, ensure_ascii=False) + "\n")
os.replace(tmp, OUT)
print("wrote", OUT)
