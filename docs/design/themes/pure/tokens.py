"""Writes themes/pure/tokens.json and tokens.light.json (atomically). Run from the repository root:
    python3 docs/design/themes/pure/tokens.py
Pure: black concrete and white light (dark); its negative, cream paper and black ink (light)."""
import json, os, tempfile

OUT = "themes/pure"


def write(name, data):
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, os.path.join(OUT, name))


def v(x):
    return {"$value": x}


def group(kind, d):
    out = {"$type": kind} if kind else {}
    for k, x in d.items():
        out[k] = group(None, x) if isinstance(x, dict) and "$value" not in x else (x if isinstance(x, dict) else v(x))
    return out


def text(family, size, weight, lh, ls=0, case=None):
    t = {"fontFamily": "{font.%s}" % family, "fontSize": size, "fontWeight": weight, "lineHeight": lh}
    if ls:
        t["letterSpacing"] = ls
    if case:
        t["textTransform"] = case
    return v(t)


def sprites(ink, paper, mid, dim, deep):
    """Pieces are light (dark scheme) or ink (light scheme): the negative of each other."""
    return {
        "outline": paper, "dark": deep, "mid-dark": mid, "mid": mid, "mist": dim,
        "light": ink, "light-dim": dim, "accent": ink, "accent-hi": ink, "accent-deep": dim,
        "familiar": ink, "familiar-mid": dim, "familiar-deep": mid,
        "good": "{color.success.solid}", "alert": "{color.danger.solid}", "paper": ink, "ink": paper,
    }


def scene(black, low, mid, line, hi, mist, cream, light):
    return {"night-0": black, "night-1": low, "night-2": mid, "line": line, "line-hi": hi, "mist": mist,
            "cream": cream, "ember": light, "ember-hi": light, "ember-deep": mist, "lilac": mist, "moss": mist}


DARK = {
    "bg": {"canvas": "#000000", "surface": "#070707", "raised": "#0e0e0d", "overlay": "#0a0a0a",
           "sunken": "#000000", "inverse": "#f3f1eb", "hover": "#1a1a19", "pressed": "#262624",
           "selected": "#2e2e2c", "current": "#f3f1eb"},
    "fg": {"default": "#f3f1eb", "muted": "#c2bfb7", "subtle": "#a8a59d", "placeholder": "#94918a",
           "disabled": "#5a5853", "inverse": "#000000", "on-accent": "#000000", "link": "#f3f1eb",
           "current": "#000000"},
    "border": {"subtle": "#242423", "default": "#383836", "strong": "#8d8a83"},
    "focus-ring": "#f3f1eb",
    "accent": {"solid": "#f3f1eb", "solid-hover": "#ffffff", "soft": "#141413", "fg": "#f3f1eb",
               "border": "#f3f1eb"},
    "paper": {"bg": "#e9e2d2", "fg": "#0b0b0a", "muted": "#4a463e"},
    "scrim": "alpha(#000000, 78%)",
    "media-scrim": "alpha(#000000, 70%)",
    "shadow": "#000000",
    "sprite": sprites("#f3f1eb", "#000000", "#57554f", "#b9b5aa", "#1c1c1b"),
    "scene": scene("#000000", "#0b0b0a", "#1a1a19", "#3a3936", "#6d6a64", "#b9b5aa", "#e3d6bb", "#f3f1eb"),
}
LIGHT = {
    "bg": {"canvas": "#eee8db", "surface": "#f2ede3", "raised": "#f6f2ea", "overlay": "#f3eee4",
           "sunken": "#f8f5ef", "inverse": "#12110f", "hover": "#e3dccd", "pressed": "#d6cebc",
           "selected": "#d4ccb9", "current": "#12110f"},
    "fg": {"default": "#12110f", "muted": "#403d37", "subtle": "#55514a", "placeholder": "#68645b",
           "disabled": "#aaa396", "inverse": "#eee8db", "on-accent": "#f3eee3", "link": "#12110f",
           "current": "#eee8db"},
    "border": {"subtle": "#d8d0bf", "default": "#bdb4a2", "strong": "#6e685d"},
    "focus-ring": "#12110f",
    "accent": {"solid": "#12110f", "solid-hover": "#2c2a26", "soft": "#e5dfd1", "fg": "#12110f",
               "border": "#12110f"},
    "paper": {"bg": "#f8f5ef", "fg": "#12110f", "muted": "#4a463e"},
    "scrim": "alpha(#2a2721, 45%)",
    "media-scrim": "alpha(#000000, 66%)",
    "shadow": "#3a3326",
    "sprite": sprites("#12110f", "#eee8db", "#8f887b", "#4f4b44", "#d9d2c3"),
    "scene": scene("#eee8db", "#e3dccd", "#d2c9b6", "#a39a88", "#6e685d", "#4f4b44", "#6a5f4c", "#12110f"),
}
ROOMS = ["home", "listen", "watch", "house", "files", "ask", "me", "control", "smart-home", "inbox",
         "space", "party", "games"]


def colours(c, room, persons, data):
    out = dict(c)
    out["room"] = {r: room for r in ROOMS}
    out["person"] = {str(i + 1): p for i, p in enumerate(persons)}
    out["data"] = {str(i + 1): d for i, d in enumerate(data)}
    return out


# People keep a colour each (they must tell apart), in the theme's dignified, desaturated key.
PERSONS_DARK = ["oklch(0.94 0.02 85)", "oklch(0.84 0.02 250)", "oklch(0.74 0.02 85)", "oklch(0.64 0.02 250)",
                "oklch(0.89 0.02 250)", "oklch(0.79 0.02 85)", "oklch(0.69 0.02 250)", "oklch(0.6 0.02 85)"]
PERSONS_LIGHT = ["oklch(0.22 0.02 85)", "oklch(0.32 0.02 250)", "oklch(0.42 0.02 85)", "oklch(0.52 0.02 250)",
                 "oklch(0.27 0.02 250)", "oklch(0.37 0.02 85)", "oklch(0.47 0.02 250)", "oklch(0.56 0.02 85)"]
# Charts: ink first, then greys and the cream; statuses keep their own meanings.
DATA_DARK = ["#f3f1eb", "#e3d6bb", "#9d9a92", "#c9b58f", "#7d7a73", "#d9d6ce", "#a8977a", "#bdb9b0"]
DATA_LIGHT = ["#12110f", "#6a5f4c", "#7f776a", "#80683f", "#4a4640", "#3a332a", "#5c5347", "#2b2926"]

tokens = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Pure: architecture made of light. Dark: black concrete, white light, hairlines. The light scheme (tokens.light.json) is its negative: cream paper, black ink. No hue; a warm cream is the rare second tone.",
    "seed": group("color", {
        "neutral": "oklch(0.52 0.004 85)", "accent": "oklch(0.96 0.006 85)",
        "success": "oklch(0.78 0.05 165)", "warning": "oklch(0.86 0.085 90)",
        "danger": "oklch(0.72 0.095 42)", "info": "oklch(0.76 0.05 240)", "private": "oklch(0.76 0.045 300)"}),
    "color": group("color", colours(DARK, "#e3d6bb", PERSONS_DARK, DATA_DARK)),
    "font": {"$type": "fontFamily", "display": v(["Archivo", "sans-serif"]),
             "body": v(["Instrument Sans", "sans-serif"]), "mono": v(["Fragment Mono", "monospace"])},
    "text": {"$type": "typography",
             "display-xl": text("display", 46, 300, 1.05, -0.03),
             "display-l": text("display", 36, 300, 1.08, -0.025),
             "display-m": text("display", 28, 300, 1.15, -0.02),
             "brand": text("display", 14, 600, 1.2, 0.18, "uppercase"),
             "title-l": text("body", 22, 500, 1.25, -0.01),
             "title-m": text("body", 18, 500, 1.3, -0.005),
             "title-s": text("body", 16, 600, 1.3),
             "body-l": text("body", 18, 400, 1.55),
             "body-m": text("body", 16, 400, 1.55),
             "body-s": text("body", 14, 400, 1.5),
             "action": text("body", 15, 500, 1.2, 0.01),
             "label": text("body", 12, 500, 1.3, 0.1, "uppercase"),
             "caption": text("body", 12, 400, 1.4, 0.01),
             "numeric": text("mono", 13, 400, 1.3)},
    "radius": {"$type": "dimension", "xs": v(0), "s": v(0), "m": v(0), "l": v(0), "xl": v(0), "full": v(0),
               "chip": v(0), "control": v(0), "card": v(0), "sheet": v(0), "media": v(0), "avatar": v(999)},
    "elev": {"$type": "shadow", "1": v("none"), "2": v("none"),
             "3": v("0 0 0 1px alpha({color.shadow}, 100%)"), "4": v("0 0 0 1px alpha({color.shadow}, 100%)")},
    "material": {
        "surface": {"border": v("1px solid {color.border.subtle}")},
        "raised": {"border": v("1px solid {color.border.default}"), "shadow": v("none")},
        "overlay": {"border": v("1px solid {color.border.default}")},
        "sunken": {"border": v("1px solid {color.border.strong}")},
        "media": {"border": v("1px solid {color.border.subtle}"), "shadow": v("none")},
        "paper": {"shadow": v("none")},
    },
    "part": {
        "page": {"scrim": v("alpha(#000000, 91%)"), "gallery": v("{color.bg.canvas}"), "quiet": v("{color.bg.canvas}")},
        "status": {"bg": v("#000000"), "border": v("1px solid {color.border.subtle}")},
        "rail": {"bg": v("#000000"), "border": v("1px solid {color.border.subtle}"),
                 "ink-shadow": v("0 0 6px #000000, 0 0 2px #000000")},
        "dock": {"bg": v("#000000"), "border": v("1px solid {color.border.default}")},
        "nowbar": {"bg": v("#050505"), "border": v("1px solid {color.border.default}"), "shadow": v("none")},
        "header": {"kicker": v("{color.room.home}"), "banner-fade": v("{color.bg.canvas}"),
                   "banner-wash": {"$type": "number", "$value": 0}},
        "panel": {"head": v("{color.fg.muted}")},
        "sheet": {"border": v("1px solid {color.border.default}")},
        "meter": {"track": v("{color.border.default}"), "thumb": v("{color.fg.default}"),
                  "thumb-radius": v(0)},
    },
    "dur": {"$type": "duration", "fast": v(90), "base": v(120), "slow": v(140), "slower": v(200)},
    "ease": {"$type": "cubicBezier", "standard": v([0.25, 0, 0, 1]), "enter": v([0, 0, 0, 1]),
             "exit": v([0.4, 0, 1, 1]), "emphasized": v([0.3, 0, 0, 1])},
    "icon": {"stroke": {"$type": "number", "$value": 1.25}},
}

light = {
    "$description": "Pure, the negative: cream paper and black ink; primary buttons are black blocks.",
    "seed": group("color", {
        "neutral": "oklch(0.55 0.012 85)", "accent": "oklch(0.2 0.004 85)",
        "success": "oklch(0.5 0.05 165)", "warning": "oklch(0.58 0.09 75)",
        "danger": "oklch(0.52 0.1 40)", "info": "oklch(0.5 0.06 245)", "private": "oklch(0.5 0.06 305)"}),
    "color": group("color", colours(LIGHT, "#5f5544", PERSONS_LIGHT, DATA_LIGHT)),
    "elev": {"$type": "shadow", "3": v("0 0 0 1px alpha({color.shadow}, 12%)"),
             "4": v("0 0 0 1px alpha({color.shadow}, 12%)")},
    "part": {
        "page": {"scrim": v("alpha(#eee8db, 84%)")},
        "status": {"bg": v("{color.bg.canvas}")},
        "rail": {"bg": v("{color.bg.canvas}"), "ink-shadow": v("0 0 6px #eee8db, 0 0 2px #eee8db")},
        "dock": {"bg": v("{color.bg.canvas}")},
        "nowbar": {"bg": v("#f6f2ea")},
    },
}

write("tokens.json", tokens)
write("tokens.light.json", light)
print("tokens written")
