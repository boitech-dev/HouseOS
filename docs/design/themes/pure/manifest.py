"""Writes themes/pure/theme.json (atomically). python3 docs/design/themes/pure/manifest.py"""
import json, os, tempfile

OUT = "themes/pure"
manifest = {
    "$schema": "../_schema/theme.schema.json",
    "id": "pure",
    "schema": 1,
    "version": 1,
    "names": {"en": "Pure", "fr": "Pur"},
    "description": {
        "en": "Architecture of light: black concrete, white light.",
        "fr": "Une architecture de lumière : béton noir, lumière blanche.",
    },
    "schemes": ["dark", "light"],
    "density": "airy",
    "identity": "line",
    "rooms": "unified",
    "fonts": {"display": "Archivo", "body": "Instrument Sans", "mono": "Fragment Mono"},
    "parts": {"header": "banner", "panel": "outlined", "dock": "flush", "nowbar": "docked"},
    "slots": {},
    "layers": [],
    "author": "HouseOS",
    "license": "CC-BY-4.0",
}


def smooth(image, fit="cover", **more):
    return {"image": "art/" + image, "rendering": "smooth", "fit": fit, **more}


ROOMS = ["listen", "watch", "house", "files", "games", "me", "control", "smart-home", "inbox", "party", "ask"]
BANNERS = {room: {"dark": f"art/banner-{room}.webp", "light": f"art/banner-{room}-light.webp"} for room in ROOMS}
BANNERS["space"] = BANNERS["me"]
FRAME = {"image": "art/frame-drawing.png", "rendering": "pixel", "fit": "slice", "slice": 16}
SLOTS = {
    "home.hero.backdrop": smooth("hero-stair.webp", schemes={"light": "art/hero-stair-light.webp"}),
    "page.backdrop": smooth("page-wall.webp", anchor="top", schemes={"light": "art/page-wall-light.webp"}),
    "header.banner": smooth("banner-default.webp", rooms=BANNERS, schemes={"light": "art/banner-default-light.webp"}),
    "auth.crest": smooth("crest-opening.webp", "contain", schemes={"light": "art/crest-opening-light.webp"}),
    "state.empty": smooth("empty-sill.webp", "contain", schemes={"light": "art/empty-sill-light.webp"}),
    "watch.tv.bezel": smooth("tv-niche.webp", "contain"),
    "space.room.scene": smooth("room-bench.webp", schemes={"light": "art/room-bench-light.webp"}),
    "deck.surface": FRAME,
    "sheet.surface": FRAME,
}
LAYERS = [
    # the sun passes over the whole house now and then: a window's light (dark), its frame's shadow (light)
    {"image": "art/sun-window.webp", "where": "page", "fit": "natural", "anchor": "left", "rendering": "smooth",
     "opacity": 0.15, "above": True, "cross": {"seconds": 45, "every": 240, "from": "left"}},
    # concrete's pores, over everything
    {"image": "art/grain.png", "where": "page", "fit": "repeat", "rendering": "pixel", "opacity": 0.05, "above": True},
    # the roof slit: light along the top of the house
    {"image": "art/seam-roof.webp", "where": "status", "fit": "cover", "anchor": "top", "rendering": "smooth"},
    # the rail's foot: a slit at the end of a corridor; touch it and a cloud passes over the sun
    {"image": "art/foot-slit.webp", "where": "rail-foot", "fit": "natural", "anchor": "bottom", "rendering": "smooth",
     "schemes": ["dark"], "poke": {"image": "art/foot-slit-cloud.webp", "frames": {"count": 8, "fps": 9}}},
    {"image": "art/foot-slit-light.webp", "where": "rail-foot", "fit": "natural", "anchor": "bottom",
     "rendering": "smooth", "schemes": ["light"],
     "poke": {"image": "art/foot-slit-light-cloud.webp", "frames": {"count": 8, "fps": 9}}},
    # the rail meets the page along a seam of light
    {"image": "art/seam-rail.webp", "where": "rail", "fit": "natural", "anchor": "right", "rendering": "smooth"},
    # dust turning in the hero's blade of sun (the night print only: on paper it would not show)
    {"image": "art/mote.png", "where": "hero", "fit": "natural", "rendering": "smooth", "opacity": 0.6,
     "schemes": ["dark"], "particles": {"count": 10, "motion": "float", "seconds": 18}},
    # while music plays, a seam of light walks slowly across the deck
    {"image": "art/deck-blade.webp", "where": "deck", "fit": "repeat", "rendering": "smooth", "opacity": 0.14,
     "playing": True, "drift": [5, 0]},
]
have = lambda fill: os.path.exists(os.path.join(OUT, fill["image"]))
manifest["slots"] = {k: f for k, f in SLOTS.items() if have(f)}
manifest["layers"] = [l for l in LAYERS if have(l)]
fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".tmp")
with os.fdopen(fd, "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
os.replace(tmp, os.path.join(OUT, "theme.json"))
print("theme.json written")
