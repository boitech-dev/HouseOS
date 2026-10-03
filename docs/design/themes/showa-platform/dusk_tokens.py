"""The dark scheme: Shōwa Platform at dusk (tokens.dark.json), and the per-scheme pictures."""

from px import LINES, PAL


def v(value, kind=None, note=None):
    out = {"$value": value}
    if kind:
        out["$type"] = kind
    if note:
        out["$description"] = note
    return out


def _lighter(hexa, k=0.42, to=(255, 240, 214)):
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(c + (t - c) * k) for c, t in zip((r, g, b), to))


tokens = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Shōwa Platform at dusk: the same station at 7 p.m., navy enamel, lamplight cream, the red lamp.",
    "seed": {
        "$type": "color",
        "neutral": v("oklch(0.6 0.05 265)"),
        "accent": v("oklch(0.66 0.17 35)"),
        "success": v("oklch(0.72 0.13 150)"),
        "warning": v("oklch(0.8 0.13 80)"),
        "danger": v("oklch(0.66 0.17 20)"),
        "info": v("oklch(0.72 0.1 245)"),
        "private": v("oklch(0.72 0.11 318)"),
    },
    "color": {
        "$type": "color",
        "bg": {
            "canvas": v(PAL["u1"], note="the platform after dark"),
            "surface": v(PAL["u2"]), "raised": v("#2c3254"), "overlay": v(PAL["u2"]),
            "sunken": v(PAL["u0"]), "hover": v(PAL["u3"]), "pressed": v("#3d4470"),
            "selected": v("#3a3450", note="a warm dark step"), "inverse": v(PAL["c1"]),
        },
        "fg": {
            "default": v("#f5ead0", note="lamplight cream"), "muted": v("#cbc1ab"), "subtle": v("#cbc1ab"),
            "placeholder": v("#aaa293"), "inverse": v(PAL["n1"]), "link": v("#ff9a78"),
        },
        "border": {"subtle": v("#343a5c"), "default": v("#4b527c"), "strong": v("#8d92b4")},
        "accent": {"soft": v("#3a3048"), "fg": v("#ff9a78")},
        "paper": {"bg": v(PAL["q0"]), "fg": v("#f5ead0"), "muted": v("#cbc1ab")},
        "room": {**{k: v(_lighter(h, 0.5)) for k, h in LINES.items()}, "home": v("#cdbf9f")},
        "person": {str(i + 1): v(h) for i, h in enumerate(
            ["#f09a6e", "#7fb8e8", "#9ccf7e", "#e98ac4", "#e2c25a", "#6fd0c4", "#b49af0", "#f7c3a0"])},
        "sprite": {"light": v(PAL["c3"]), "outline": v(PAL["n0"]), "accent": v(PAL["r3"])},
        "scrim": v("alpha(#0b0d18, 60%)"),
    },
    "material": {
        "canvas": {"texture": v("url(art/slab-dusk.png)", "string")},
        "sunken": {"shadow": v("inset 0 2px 0 alpha(#000000, 25%)", "shadow")},
        "screen": {"bg": v("#1a2440", "color"), "glow": v("0 0 0 1px alpha(#ffd66a, 25%)", "shadow")},
    },
    "elev": {
        "$type": "shadow",
        "1": v("0 1px 0 alpha(#000000, 35%)"),
        "2": v("0 2px 0 alpha(#000000, 35%)"),
        "3": v("0 2px 0 alpha(#000000, 35%), 0 8px 18px alpha(#000000, 30%)"),
        "4": v("0 3px 0 alpha(#000000, 35%), 0 16px 40px alpha(#000000, 40%)"),
    },
    "part": {
        "status": {"bg": v(PAL["u2"], "color"), "border": v("1px solid #000000", "string")},
        "rail": {"bg": v("#202540", "color"), "border": v("1px solid #000000", "string"),
                 "texture": v("url(art/clapboard-dusk.png)", "string")},
        "dock": {"bg": v(PAL["u2"], "color")},
        "header": {"banner-fade": v(PAL["u1"], "color")},
        "control": {
            "bg": v("linear-gradient(180deg, alpha(#ffffff, 10%), alpha(#ffffff, 0%) 55%) {color.bg.raised}", "string"),
            "shadow": v("0 2px 0 alpha(#000000, 45%)", "shadow"),
            "primary-shadow": v("inset 0 1px 0 alpha(#ffffff, 25%), 0 2px 0 alpha(#000000, 55%)", "shadow"),
        },
        "meter": {
            "pattern": v("repeating-linear-gradient(90deg, transparent 0 11px, alpha(#1b1f35, 85%) 11px 13px)", "string"),
            "thumb": v("#f5ead0", "color"),
        },
    },
}

# slot → its dusk picture
PICTURES = {
    "status.backdrop": "status-dusk.png", "home.hero.backdrop": "hero-dusk.png",
    "space.room.scene": "office-dusk.png",
    "panel.surface": "plate-dusk.png", "sheet.surface": "plate-dusk.png", "deck.surface": "pa-box-dusk.png",
    "nowbar.surface": "ticket-dusk.png", "dock.surface": "dock-dusk.png",
}


def layers():
    day = {"schemes": ["light"]}
    dusk = {"schemes": ["dark"]}
    return [
        {"image": "art/status-sky.png", "where": "status", "fit": "repeat-x", "anchor": "top", "scale": 2,
         "drift": [12, 0], "under": True, **day},
        {"image": "art/status-sky-dusk.png", "where": "status", "fit": "repeat-x", "anchor": "top", "scale": 2,
         "drift": [6, 0], "under": True, **dusk},
        {"image": "art/train-far.png", "where": "status", "fit": "natural", "scale": 2, "anchor": "bottom-left",
         "frames": {"count": 2, "fps": 6}, "cross": {"seconds": 14, "every": 45, "from": "right"}, **day},
        {"image": "art/train-far-dusk.png", "where": "status", "fit": "natural", "scale": 2, "anchor": "bottom-left",
         "frames": {"count": 2, "fps": 6}, "cross": {"seconds": 14, "every": 45, "from": "right"}, **dusk},
        {"image": "art/swallows.png", "where": "status", "fit": "natural", "scale": 2, "anchor": "top-left",
         "frames": {"count": 2, "fps": 8}, "cross": {"seconds": 5, "every": 25, "from": "left"}},
        {"image": "art/crossing.png", "where": "status", "fit": "natural", "scale": 2, "anchor": "bottom",
         "poke": {"image": "art/crossing-blink.png", "frames": {"count": 6, "fps": 5}}},
        {"image": "art/bench-end.png", "where": "hero", "fit": "natural", "scale": 2, "anchor": "bottom-right",
         "frames": {"count": 12, "fps": 1}, "poke": {"image": "art/bench-end-wake.png", "frames": {"count": 10, "fps": 8}}, **day},
        {"image": "art/bench-end-dusk.png", "where": "hero", "fit": "natural", "scale": 2, "anchor": "bottom-right",
         "frames": {"count": 12, "fps": 1}, "poke": {"image": "art/bench-end-wake-dusk.png", "frames": {"count": 10, "fps": 8}}, **dusk},
        {"image": "art/vending-foot.png", "where": "rail-foot", "fit": "natural", "scale": 2, "anchor": "bottom",
         "poke": {"image": "art/vending-can.png", "frames": {"count": 10, "fps": 9}}, **day},
        {"image": "art/vending-foot-dusk.png", "where": "rail-foot", "fit": "natural", "scale": 2, "anchor": "bottom",
         "poke": {"image": "art/vending-can-dusk.png", "frames": {"count": 10, "fps": 9}}, **dusk},
        {"image": "art/firefly.png", "where": "status", "fit": "natural", "scale": 2,
         "particles": {"count": 8, "motion": "float", "seconds": 12}, **dusk},
        {"image": "art/furin.png", "where": "deck", "fit": "natural", "scale": 2, "anchor": "top-right",
         "frames": {"count": 4, "fps": 3}, "playing": True},
    ]
