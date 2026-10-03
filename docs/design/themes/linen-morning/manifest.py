"""Kinari's theme.json (names, slots, parts, layers), written atomically.
    python3 docs/design/themes/linen-morning/manifest.py"""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "themes/linen-morning/theme.json"
ROOMS = ["home", "listen", "watch", "house", "files", "ask", "me", "control", "smart-home", "inbox", "space", "party", "games"]


def art(name, **kw):
    return {"image": f"art/{name}", "rendering": "smooth", **kw}


manifest = {
    "$schema": "../_schema/theme.schema.json",
    "id": "linen-morning",
    "schema": 1,
    "version": 2,
    "names": {"en": "Kinari", "fr": "Kinari"},
    "description": {
        "en": "A quiet Japanese room: washi, walnut, sumi ink.",
        "fr": "Une pièce japonaise calme : washi, noyer, encre sumi.",
    },
    "schemes": ["light"],
    "density": "airy",
    "identity": "line",
    "fonts": {"display": "Shippori Mincho", "body": "Zen Kaku Gothic New", "mono": "M PLUS 1 Code"},
    "parts": {"header": "banner", "panel": "card", "dock": "flush", "nowbar": "floating"},
    "slots": {},
    "layers": [],
    "author": "HouseOS",
    "license": "MIT",
}

have = {p.name for p in (ROOT / "themes/linen-morning/art").iterdir()}
def maybe(slot, value):
    if value["image"][4:] in have:
        manifest["slots"][slot] = value
        if "rooms" in value:
            value["rooms"] = {r: f for r, f in value["rooms"].items() if f[4:] in have}
            if not value["rooms"]:
                del value["rooms"]

maybe("home.hero.backdrop", art("hero-mountains.webp", fit="cover"))
maybe("auth.crest", art("crest.webp", fit="contain"))
maybe("status.backdrop", art("status-heri.webp", fit="cover", anchor="bottom"))
maybe("rail.surface", art("rail-shoji.webp", fit="cover", anchor="top"))
maybe("dock.surface", art("dock-heri.webp", fit="cover", anchor="top"))
maybe("deck.surface", art("deck-kraft.webp", fit="slice", slice=40))
maybe("state.empty", art("empty-stone.webp", fit="contain"))
maybe("watch.tv.bezel", art("tv-walnut.webp", fit="contain"))
maybe("space.room.scene", art("space-tatami.webp", fit="cover"))
maybe("header.banner", art("banner-home.webp", fit="cover", rooms={r: f"art/banner-{r}.webp" for r in ROOMS if r != "home"}))

LAYERS = [
    {"image": "art/leaf-shadow.webp", "where": "page", "fit": "repeat", "anchor": "top-right", "blend": "multiply",
     "rendering": "smooth", "opacity": 0.32, "drift": [-2, 0], "depth": 0.25,
     "rooms": ["home"]},
    {"image": "art/mist.webp", "where": "hero", "fit": "repeat-x", "anchor": "top", "rendering": "smooth",
     "opacity": 0.9, "drift": [6, 0]},
    {"image": "art/geese.webp", "where": "hero", "fit": "natural", "anchor": "top-right", "rendering": "smooth",
     "cross": {"seconds": 38, "every": 200, "from": "right"}, "frames": {"count": 4, "fps": 3}},
    {"image": "art/leaf-fall.webp", "where": "hero", "fit": "natural", "anchor": "top-right", "rendering": "smooth",
     "cross": {"seconds": 12, "every": 150, "from": "top"}, "frames": {"count": 8, "fps": 4}},
    {"image": "art/incense.webp", "where": "deck", "fit": "natural", "anchor": "bottom-right", "rendering": "smooth",
     "frames": {"count": 8, "fps": 3}, "playing": True, "opacity": 0.8,
     "poke": {"frames": {"count": 10, "fps": 7}, "image": "art/incense-puff.webp"}},
    {"image": "art/scroll-foot.webp", "where": "rail-foot", "fit": "natural", "anchor": "bottom", "rendering": "smooth",
     "poke": {"frames": {"count": 11, "fps": 10}, "image": "art/scroll-sway.webp"}},
]
manifest["layers"] = [l for l in LAYERS if l["image"][4:] in have]
if not manifest["layers"]:
    del manifest["layers"]

for k in ("en", "fr"):
    assert len(manifest["names"][k]) <= 32 and len(manifest["description"][k]) <= 90, (k, len(manifest["description"][k]))
tmp = OUT.with_name(".theme.json.tmp")
tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
os.replace(tmp, OUT)
print("wrote", OUT, len(manifest["slots"]), "slots", len(manifest.get("layers", [])), "layers")
