"""Millennium Skin's tokens, written as Python for brevity: run it to (re)write
themes/y2k/tokens.json (shared + the dark "classic skin"), tokens.dark.json and tokens.light.json
("Bondi"). JSON files are written atomically (temp file, then rename).

    python3 docs/design/themes/y2k/tokens_src.py
"""

import json
import os
from pathlib import Path

THEME = Path(__file__).resolve().parents[4] / "themes" / "y2k"


def v(value, desc=None, kind=None):
    out = {"$value": value}
    if kind:
        out["$type"] = kind
    if desc:
        out["$description"] = desc
    return out


def group(kind, **items):
    return {"$type": kind, **items}


# ---------------------------------------------------------------- shared + dark (the first scheme)
WHITE = "#ffffff"
BLACK = "#000000"

shared = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Millennium Skin: the house as a millennium media-player skin. Shared values and the dark 'classic skin' (gunmetal, bevels, LCD green, a hot amber gel). tokens.light.json is 'Bondi'. Written by docs/design/themes/y2k/tokens_src.py.",
    "seed": group(
        "color",
        neutral=v("oklch(0.55 0.03 258)", "Gunmetal with a blue cast: the skin's metal"),
        accent=v("oklch(0.8 0.155 66)", "Hot amber gel: the volume bar's hot end, the one 'act here'"),
        success=v("oklch(0.86 0.2 138)", "LCD green: playing, done, ready"),
        warning=v("oklch(0.9 0.15 102)", "Lemon LED"),
        danger=v("oklch(0.68 0.2 18)", "Strawberry LED"),
        info=v("oklch(0.74 0.12 228)", "Ice-blue LED"),
        private=v("oklch(0.72 0.14 305)", "Grape plastic: Nox and My Space"),
    ),
    "font": {
        "$type": "fontFamily",
        "display": v(["Michroma", "sans-serif"], "A wide techno face: the skin's name plate"),
        "body": v(["Lexend", "sans-serif"], "Clear, wide-spaced: reads like the UI fonts of the era, at 14 px"),
        "mono": v(["Kode Mono", "monospace"], "Squarish LCD digits for times and counts"),
    },
    "text": {
        "$type": "typography",
        "display-xl": v({"fontFamily": "{font.display}", "fontSize": 40, "fontWeight": 400, "lineHeight": 1.15, "letterSpacing": 0}),
        "display-l": v({"fontFamily": "{font.display}", "fontSize": 30, "fontWeight": 400, "lineHeight": 1.2, "letterSpacing": 0}),
        "display-m": v({"fontFamily": "{font.display}", "fontSize": 23, "fontWeight": 400, "lineHeight": 1.25}),
        "brand": v({"fontFamily": "{font.display}", "fontSize": 14, "fontWeight": 400, "lineHeight": 1.3, "letterSpacing": 0.04}),
        "label": v({"fontFamily": "{font.body}", "fontSize": 13, "fontWeight": 500, "lineHeight": 1.2, "letterSpacing": 0.02}),
        "numeric": v({"fontFamily": "{font.mono}", "fontSize": 14, "fontWeight": 500, "lineHeight": 1.2}),
    },
    "radius": group(
        "dimension",
        control=v(9, "Bevel lozenges: between a square skin button and a gel pill"),
        card=v(0, "Skin windows are square: the pixel frame is the corner"),
        sheet=v(0),
        chip=v("{radius.full}", "Gel pills"),
        media=v(3),
    ),
    "color": group(
        "color",
        bg={
            "canvas": v("oklch(0.155 0.04 270)", "Night blue behind the grid"),
            "surface": v("oklch(0.235 0.022 258)", "Gunmetal: skin windows"),
            "raised": v("oklch(0.3 0.024 256)", "Brushed metal buttons"),
            "overlay": v("oklch(0.215 0.024 260)"),
            "sunken": v("oklch(0.13 0.022 190)", "LCD glass: fields and screens"),
            "hover": v("oklch(0.35 0.026 256)"),
            "pressed": v("oklch(0.4 0.028 256)"),
            "selected": v("oklch(0.3 0.06 66)", "A warm amber glow under the chosen item"),
        },
        fg={
            "default": v("oklch(0.95 0.01 250)"),
            "muted": v("oklch(0.8 0.02 250)"),
            "subtle": v("oklch(0.78 0.02 250)"),
        },
        border={
            "subtle": v("oklch(0.32 0.02 258)"),
            "default": v("oklch(0.42 0.022 258)"),
            "strong": v("oklch(0.6 0.02 258)"),
        },
        room={
            "home": v("oklch(0.84 0.1 215)", "Bondi"),
            "listen": v("oklch(0.82 0.15 66)", "Tangerine"),
            "watch": v("oklch(0.8 0.12 265)", "Blueberry"),
            "house": v("oklch(0.86 0.17 135)", "Lime"),
            "files": v("oklch(0.88 0.12 98)", "Lemon"),
            "ask": v("oklch(0.78 0.14 305)", "Grape"),
            "me": v("oklch(0.8 0.13 350)", "Strawberry milk"),
            "control": v("oklch(0.8 0.03 250)", "Graphite"),
            "smart-home": v("oklch(0.84 0.12 175)", "Sage"),
            "inbox": v("oklch(0.82 0.1 235)", "Ice"),
            "space": v("oklch(0.8 0.12 325)", "Flower"),
            "party": v("oklch(0.78 0.17 20)", "Ruby"),
            "games": v("oklch(0.84 0.13 155)", "Clear green"),
        },
        person={
            "1": v("oklch(0.82 0.14 66)"),
            "2": v("oklch(0.82 0.11 215)"),
            "3": v("oklch(0.85 0.16 138)"),
            "4": v("oklch(0.76 0.16 18)"),
            "5": v("oklch(0.78 0.13 305)"),
            "6": v("oklch(0.9 0.13 102)"),
            "7": v("oklch(0.78 0.12 265)"),
            "8": v("oklch(0.8 0.12 350)"),
        },
        shadow=v("oklch(0.06 0.03 270)"),
        scrim=v("alpha(oklch(0.08 0.04 270), 74%)"),
        sprite={
            "outline": v("oklch(0.12 0.03 265)", "k: a dark outline"),
            "dark": v("oklch(0.3 0.03 258)", "n: gunmetal shadow"),
            "mid-dark": v("oklch(0.5 0.03 255)", "l: chrome shadow"),
            "mid": v("oklch(0.68 0.025 250)", "L: chrome"),
            "mist": v("oklch(0.84 0.02 245)", "m: chrome light"),
            "light": v("oklch(0.98 0.01 240)", "c: the glint"),
            "light-dim": v("oklch(0.9 0.03 230)", "C"),
            "accent": v("oklch(0.8 0.155 66)", "e: amber gel"),
            "accent-hi": v("oklch(0.92 0.1 85)", "E: amber highlight"),
            "accent-deep": v("oklch(0.6 0.15 50)", "r: amber shade"),
            "familiar": v("oklch(0.74 0.12 205)", "v: Bondi plastic (Nox)"),
            "familiar-mid": v("oklch(0.6 0.11 215)", "V: Bondi shade"),
            "familiar-deep": v("oklch(0.44 0.09 225)", "w: Bondi deep"),
            "good": v("oklch(0.86 0.2 138)", "g: LCD green"),
            "alert": v("oklch(0.68 0.2 18)", "p: strawberry"),
            "paper": v("oklch(0.18 0.03 170)", "P: LCD glass (dark)"),
            "ink": v("oklch(0.9 0.2 138)", "i: LCD segments (lit)"),
        },
        accent={"soft": v("oklch(0.29 0.055 215)", "Bondi-teal glass: Ask Nox's card, quiet accent grounds")},
        **{"focus-ring": v("oklch(0.86 0.2 138)", "LCD green: a lit outline, everywhere")},
    ),
    "material": {
        "canvas": {"bg": v("oklch(0.155 0.04 270)", kind="color")},
        "surface": {
            "bg": v("oklch(0.235 0.022 258)", kind="color"),
            "border": v("1px solid oklch(0.1 0.02 265)", "A black line around every skin window", "string"),
            "shadow": v("inset 1px 1px 0 alpha(#ffffff, 12%), inset -1px -1px 0 alpha(#000000, 40%), 0 2px 0 alpha({color.shadow}, 50%)", "The bevel: light top-left, dark bottom-right", "shadow"),
        },
        "raised": {
            "border": v("1px solid oklch(0.1 0.02 265)", kind="string"),
            "shadow": v("inset 1px 1px 0 alpha(#ffffff, 20%), inset -1px -1px 0 alpha(#000000, 45%)", kind="shadow"),
        },
        "overlay": {
            "bg": v("oklch(0.215 0.024 260)", kind="color"),
            "border": v("1px solid oklch(0.1 0.02 265)", kind="string"),
            "shadow": v("inset 1px 1px 0 alpha(#ffffff, 12%), 0 16px 48px alpha({color.shadow}, 60%)", kind="shadow"),
        },
        "sunken": {
            "bg": v("oklch(0.13 0.022 190)", kind="color"),
            "border": v("1px solid oklch(0.62 0.02 258)", kind="string"),
            "shadow": v("inset 1px 1px 0 alpha(#000000, 60%), inset -1px -1px 0 alpha(#ffffff, 8%)", "Sunken: the bevel turned inside out", "shadow"),
        },
        "screen": {
            "bg": v("oklch(0.13 0.03 170)", kind="color"),
            "fg": v("oklch(0.9 0.2 138)", "LCD green on black glass", "color"),
            "texture": v("repeating-linear-gradient(0deg, alpha(#000000, 22%) 0 1px, transparent 1px 3px)", "Scanlines", "string"),
            "glow": v("inset 0 0 18px alpha(oklch(0.86 0.2 138), 12%)", kind="shadow"),
        },
        "paper": {
            "bg": v("oklch(0.9 0.06 100)", "Notes: a clear lemon sticker", "color"),
            "fg": v("oklch(0.22 0.03 260)", kind="color"),
            "shadow": v("0 2px 0 alpha({color.shadow}, 45%)", kind="shadow"),
        },
    },
    "part": {
        "page": {
            "bg": v("oklch(0.155 0.04 270)", kind="color"),
            "gallery": v("transparent", "No mat: the skins are the only frames (the grid is drawn calm)", "color"),
            "scrim": v("alpha(oklch(0.155 0.04 270), 45%)", "Calms the night grid under the words", "color"),
        },
        "status": {
            "bg": v("oklch(0.2 0.024 260)", kind="color"),
            "border": v("1px solid oklch(0.08 0.02 265)", kind="string"),
            "texture": v("linear-gradient(#b3bbe2, #b3bbe2) left 0 bottom 4px / 100% 2px no-repeat, linear-gradient(#161a31, #161a31) left 0 bottom 2px / 100% 2px no-repeat, linear-gradient(180deg, alpha(#ffffff, 16%) 0 1px, alpha(#ffffff, 6%) 1px, alpha(#ffffff, 0%) 60%, alpha(#000000, 25%)), repeating-linear-gradient(90deg, alpha(#ffffff, 2%) 0 1px, alpha(#000000, 3%) 1px 3px)", "Brushed gunmetal: a lit top edge, fine vertical brushing", "string"),
        },
        "rail": {
            "bg": v("oklch(0.215 0.024 260)", "Gunmetal: the playlist window (the chosen room sinks into the night)", "color"),
            "border": v("1px solid oklch(0.08 0.02 265)", kind="string"),
            "ink-shadow": v("0 1px 0 #000000", "A 1 px drop under the rail's words, like skin text", "string"),
        },
        "dock": {
            "bg": v("oklch(0.21 0.024 260)", kind="color"),
            "border": v("1px solid transparent", kind="string"),
            "texture": v("linear-gradient(180deg, alpha(#ffffff, 8%), alpha(#000000, 20%))", kind="string"),
        },
        "nowbar": {
            "bg": v("oklch(0.17 0.026 262)", "The mini player's dark glass", "color"),
            "border": v("1px solid transparent", "The skin draws the edge", "string"),
            "radius": v(0, kind="dimension"),
            "shadow": v("0 6px 18px alpha({color.shadow}, 60%)", kind="shadow"),
        },
        "header": {
            "frame-bg": v("oklch(0.2 0.024 260)", "A gunmetal name plate", "color"),
            "frame-border": v("1px solid oklch(0.08 0.02 265)", kind="string"),
            "frame-texture": v("repeating-linear-gradient(180deg, #b3bbe2 0 2px, #161a31 2px 4px) left 10px top 2px / calc(100% - 20px) 8px no-repeat, linear-gradient(#626a96, #626a96) top / 100% 1px no-repeat, linear-gradient(#626a96, #626a96) left / 1px 100% no-repeat, linear-gradient(#06080f, #06080f) bottom / 100% 1px no-repeat, linear-gradient(#06080f, #06080f) right / 1px 100% no-repeat", "The name plate: two grip-ridge pairs across its top band, a 1 px bevel lit top-left", "string"),
        },
        "panel": {
            "border": v("1px solid oklch(0.08 0.02 265)", "The black line round each window; the skin adds the bevel and the title ridges", "string"),
            "shadow": v("0 2px 0 alpha({color.shadow}, 55%)", kind="shadow"),
        },
        "sheet": {
            "border": v("1px solid oklch(0.08 0.02 265)", kind="string"),
        },
        "control": {
            "bg": v("linear-gradient(180deg, alpha(#ffffff, 14%), alpha(#ffffff, 3%) 48%, alpha(#000000, 0%) 52%, alpha(#000000, 18%)) {color.bg.raised}", "Brushed metal: a soft sheen over the metal", "string"),
            "shadow": v("inset 1px 1px 0 alpha(#ffffff, 22%), inset -1px -1px 0 alpha(#000000, 50%), 0 1px 0 alpha(#000000, 55%)", "The bevel", "shadow"),
            "primary-bg": v("linear-gradient(180deg, alpha(#ffffff, 58%), alpha(#ffffff, 20%) 46%, alpha(#ffffff, 0%) 50%, alpha(#ffffff, 0%) 78%, alpha(#ffffff, 26%)) {color.accent.solid}", "A gel pill: a bright top half, a hard line at the middle, light pooling at the bottom", "string"),
            "primary-shadow": v("inset 0 -2px 3px alpha(oklch(0.45 0.14 45), 55%), inset 0 1px 0 alpha(#ffffff, 70%), 0 1px 0 alpha(#000000, 60%)", kind="shadow"),
        },
        "meter": {
            "track": v("oklch(0.13 0.022 190)", "An unlit LCD bar", "color"),
            "pattern": v("repeating-linear-gradient(90deg, transparent 0 3px, alpha(oklch(0.13 0.022 190), 85%) 3px 4px)", "LCD segments: a hairline gap every 4 px", "string"),
            "thumb": v("oklch(0.9 0.015 245)", "A chrome slider knob", "color"),
            "thumb-radius": v(3, "Square-ish, like a skin's knob", "dimension"),
        },
    },
    "dur": group("duration", fast=v(90), base=v(160), slow=v(260), slower=v(400)),
    "ease": group(
        "cubicBezier",
        standard=v([0.2, 0, 0, 1]),
        emphasized=v([0.3, 1.3, 0.5, 1], "A small gel bounce"),
    ),
    "icon": {"stroke": v(2, "Chunky skin glyphs", "number")},
}

# ---------------------------------------------------------------- light: Bondi
light = {
    "$description": "Bondi: translucent ice and Bondi-blue plastic over a lilac cloud sky, chrome edges, aqua gel buttons with dark ink.",
    "seed": group(
        "color",
        neutral=v("oklch(0.55 0.035 255)"),
        accent=v("oklch(0.76 0.12 212)", "Aqua gel, dark ink on it"),
        success=v("oklch(0.55 0.15 145)", "Lime, deepened for a light ground"),
        warning=v("oklch(0.58 0.15 58)", "Tangerine"),
        danger=v("oklch(0.55 0.2 15)", "Strawberry"),
        info=v("oklch(0.5 0.16 265)", "Blueberry"),
        private=v("oklch(0.52 0.18 305)", "Grape"),
    ),
    "color": group(
        "color",
        bg={
            "canvas": v("oklch(0.9 0.045 295)", "Lilac sky"),
            "surface": v("alpha(oklch(0.985 0.012 240), 80%)", "Translucent ice plastic"),
            "raised": v("oklch(0.96 0.015 240)"),
            "overlay": v("alpha(oklch(0.975 0.014 240), 90%)"),
            "sunken": v("oklch(0.995 0.005 240)", "A clear window"),
            "hover": v("oklch(0.92 0.03 225)"),
            "pressed": v("oklch(0.88 0.04 222)"),
            "selected": v("oklch(0.88 0.07 212)", "Bondi tint"),
        },
        fg={
            "default": v("oklch(0.24 0.05 265)", "Navy ink"),
            "muted": v("oklch(0.4 0.04 262)"),
            "subtle": v("oklch(0.42 0.04 262)"),
            "link": v("oklch(0.45 0.12 225)"),
        },
        accent={"fg": v("oklch(0.44 0.11 222)", "Bondi, deep enough to read as text"), "soft": v("{ramp.accent.3}")},
        border={
            "subtle": v("oklch(0.86 0.025 250)"),
            "default": v("oklch(0.76 0.03 250)"),
            "strong": v("oklch(0.55 0.04 255)"),
        },
        room={
            "home": v("oklch(0.55 0.11 215)"),
            "listen": v("oklch(0.56 0.16 50)"),
            "watch": v("oklch(0.5 0.15 265)"),
            "house": v("oklch(0.52 0.15 140)"),
            "files": v("oklch(0.52 0.11 90)"),
            "ask": v("oklch(0.52 0.17 305)"),
            "me": v("oklch(0.58 0.17 355)"),
            "control": v("oklch(0.48 0.03 255)"),
            "smart-home": v("oklch(0.5 0.1 175)"),
            "inbox": v("oklch(0.55 0.1 240)"),
            "space": v("oklch(0.56 0.16 325)"),
            "party": v("oklch(0.55 0.19 20)"),
            "games": v("oklch(0.5 0.12 155)"),
        },
        person={
            "1": v("oklch(0.56 0.15 55)"),
            "2": v("oklch(0.55 0.11 215)"),
            "3": v("oklch(0.56 0.15 140)"),
            "4": v("oklch(0.56 0.18 18)"),
            "5": v("oklch(0.52 0.16 305)"),
            "6": v("oklch(0.52 0.11 92)"),
            "7": v("oklch(0.5 0.14 265)"),
            "8": v("oklch(0.56 0.16 350)"),
        },
        shadow=v("oklch(0.35 0.08 280)"),
        scrim=v("alpha(oklch(0.4 0.08 290), 38%)"),
        sprite={
            "outline": v("oklch(0.3 0.06 265)"),
            "dark": v("oklch(0.5 0.05 258)"),
            "mid-dark": v("oklch(0.66 0.04 255)"),
            "mid": v("oklch(0.8 0.03 250)"),
            "mist": v("oklch(0.9 0.02 245)"),
            "light": v("oklch(0.3 0.06 265)", "c: in Bondi the high-contrast ink"),
            "light-dim": v("oklch(0.95 0.02 230)"),
            "accent": v("oklch(0.54 0.11 220)"),
            "accent-hi": v("oklch(0.9 0.08 205)"),
            "accent-deep": v("oklch(0.52 0.11 222)"),
            "familiar": v("oklch(0.72 0.13 212)"),
            "familiar-mid": v("oklch(0.58 0.12 218)"),
            "familiar-deep": v("oklch(0.44 0.1 225)"),
            "good": v("oklch(0.62 0.17 140)"),
            "alert": v("oklch(0.58 0.2 15)"),
            "paper": v("oklch(0.3 0.05 190)"),
            "ink": v("oklch(0.9 0.19 138)"),
        },
        **{"focus-ring": v("oklch(0.42 0.14 262)", "Blueberry: 3:1 on ice and sky")},
    ),
    "material": {
        "canvas": {"bg": v("oklch(0.9 0.045 295)", kind="color")},
        "surface": {
            "bg": v("alpha(oklch(0.985 0.012 240), 80%)", kind="color"),
            "border": v("1px solid alpha(#ffffff, 95%)", "A lit plastic rim", "string"),
            "shadow": v("inset 0 -1px 0 alpha(oklch(0.55 0.08 250), 25%), 0 1px 0 alpha(oklch(0.4 0.08 270), 18%), 0 6px 20px alpha(oklch(0.4 0.1 285), 14%)", kind="shadow"),
        },
        "raised": {
            "bg": v("oklch(0.96 0.015 240)", kind="color"),
            "border": v("1px solid oklch(0.72 0.035 250)", kind="string"),
            "shadow": v("inset 0 1px 0 #ffffff, 0 1px 2px alpha(oklch(0.35 0.08 270), 18%)", kind="shadow"),
        },
        "overlay": {
            "bg": v("alpha(oklch(0.975 0.014 240), 88%)", kind="color"),
            "border": v("1px solid #ffffff", kind="string"),
            "shadow": v("0 16px 48px alpha(oklch(0.35 0.1 285), 24%)", kind="shadow"),
            "blur": v("blur(14px) saturate(1.3)", "Frosted plastic: the sky shows through", "string"),
        },
        "sunken": {
            "bg": v("oklch(0.995 0.005 240)", kind="color"),
            "border": v("1px solid oklch(0.55 0.04 255)", kind="string"),
            "shadow": v("inset 0 1px 2px alpha(oklch(0.35 0.08 270), 22%)", kind="shadow"),
        },
        "screen": {
            "bg": v("oklch(0.24 0.05 200)", kind="color"),
            "fg": v("oklch(0.92 0.18 138)", kind="color"),
        },
        "paper": {
            "bg": v("oklch(0.96 0.06 100)", kind="color"),
            "fg": v("oklch(0.24 0.05 265)", kind="color"),
            "shadow": v("0 2px 6px alpha(oklch(0.35 0.08 270), 20%)", kind="shadow"),
        },
    },
    "part": {
        "page": {
            "bg": v("oklch(0.9 0.045 295)", kind="color"),
            "gallery": v("transparent", "No mat: the skins are the only frames (the sky is drawn pale)", "color"),
            "scrim": v("alpha(oklch(0.9 0.045 295), 30%)", "Pales the sky under the words", "color"),
        },
        "status": {
            "bg": v("oklch(0.95 0.018 250)", kind="color"),
            "border": v("1px solid oklch(0.72 0.035 255)", kind="string"),
            "texture": v("linear-gradient(#ffffff, #ffffff) left 0 bottom 4px / 100% 2px no-repeat, linear-gradient(#2a82aa, #2a82aa) left 0 bottom 2px / 100% 2px no-repeat, linear-gradient(180deg, alpha(#ffffff, 95%) 0 1px, alpha(#ffffff, 60%) 1px, alpha(#ffffff, 0%) 55%, alpha(oklch(0.55 0.06 260), 14%))", "Chrome-white plastic: a glint on top, a cool shade below", "string"),
        },
        "rail": {
            "bg": v("alpha(oklch(0.97 0.02 250), 72%)", "Frosted ice: the sky shows through", "color"),
            "border": v("1px solid alpha(#ffffff, 90%)", kind="string"),
            "ink-shadow": v("0 1px 0 alpha(#ffffff, 80%)", "A white drop under the rail's words, like embossed plastic", "string"),
        },
        "dock": {
            "bg": v("alpha(oklch(0.97 0.02 250), 97%)", "Nearly solid ice: nothing on the page ghosts through", "color"),
            "border": v("1px solid transparent", kind="string"),
            "texture": v("linear-gradient(180deg, alpha(#ffffff, 70%), alpha(#ffffff, 0%) 60%)", kind="string"),
        },
        "nowbar": {
            "bg": v("alpha(oklch(0.97 0.02 250), 97%)", "Nearly solid ice: nothing on the page ghosts through", "color"),
            "shadow": v("0 6px 18px alpha(oklch(0.35 0.1 285), 22%)", kind="shadow"),
        },
        "header": {
            "frame-bg": v("alpha(oklch(0.985 0.012 240), 82%)", "A frosted name plate", "color"),
            "frame-border": v("1px solid #ffffff", kind="string"),
            "frame-texture": v("repeating-linear-gradient(180deg, #ffffff 0 2px, #2a82aa 2px 4px) left 10px top 2px / calc(100% - 20px) 8px no-repeat, linear-gradient(#ffffff, #ffffff) top / 100% 1px no-repeat, linear-gradient(#ffffff, #ffffff) left / 1px 100% no-repeat, linear-gradient(#7d8cb4, #7d8cb4) bottom / 100% 1px no-repeat, linear-gradient(#7d8cb4, #7d8cb4) right / 1px 100% no-repeat", "The name plate by day: white and Bondi grip ridges, a chrome bevel", "string"),
        },
        "panel": {
            "border": v("1px solid alpha(oklch(0.45 0.06 265), 45%)", kind="string"),
            "shadow": v("0 6px 20px alpha(oklch(0.4 0.1 285), 14%)", kind="shadow"),
        },
        "sheet": {
            "border": v("1px solid alpha(oklch(0.45 0.06 265), 45%)", kind="string"),
        },
        "control": {
            "bg": v("linear-gradient(180deg, alpha(#ffffff, 90%), alpha(#ffffff, 30%) 48%, alpha(#ffffff, 0%) 52%, alpha(oklch(0.5 0.05 250), 10%)) {color.bg.raised}", "Chrome-white plastic", "string"),
            "shadow": v("inset 0 1px 0 #ffffff, inset 0 -1px 0 alpha(oklch(0.5 0.05 250), 25%), 0 1px 2px alpha(oklch(0.35 0.08 270), 20%)", kind="shadow"),
            "primary-bg": v("linear-gradient(180deg, alpha(#ffffff, 62%), alpha(#ffffff, 24%) 46%, alpha(#ffffff, 0%) 50%, alpha(#ffffff, 0%) 76%, alpha(#ffffff, 34%)) {color.accent.solid}", "The aqua gel pill", "string"),
            "primary-shadow": v("inset 0 -2px 4px alpha(oklch(0.45 0.12 225), 45%), inset 0 1px 0 #ffffff, 0 2px 4px alpha(oklch(0.4 0.12 225), 30%)", kind="shadow"),
        },
        "meter": {
            "track": v("oklch(0.84 0.03 245)", kind="color"),
            "pattern": v("linear-gradient(180deg, alpha(#ffffff, 65%), alpha(#ffffff, 0%) 55%)", "A gel tube", "string"),
            "thumb": v("oklch(0.98 0.01 240)", kind="color"),
            "thumb-radius": v("{radius.full}", "A clear bead", "dimension"),
        },
    },
}


def write(name, data):
    path = THEME / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    write("tokens.json", shared)
    write("tokens.light.json", light)
    print("tokens written")
