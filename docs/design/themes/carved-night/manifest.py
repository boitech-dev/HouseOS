"""Writes themes/carved-night/theme.json (atomically): the manifest, its slots and layers.
    python3 docs/design/themes/carved-night/manifest.py"""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "themes/carved-night/theme.json"
ART = ROOT / "themes/carved-night/art"


def px(image, fit="cover", **more):
    return {"image": "art/" + image, "rendering": "pixel", "fit": fit, **more}


M = {
    "$schema": "../_schema/theme.schema.json",
    "id": "carved-night",
    "schema": 1,
    "version": 2,
    "names": {"en": "Legacy", "fr": "Legacy"},
    "description": {
        "en": "The haunted manor under the moon, by candlelight.",
        "fr": "Le manoir hanté sous la lune, à la bougie.",
    },
    "schemes": ["dark"],
    "density": "comfortable",
    "identity": "pixel",
    "fonts": {"display": "Jacquard 12", "body": "Alegreya Sans", "mono": "IBM Plex Mono"},
    "parts": {"header": "banner", "panel": "card", "dock": "flush", "nowbar": "floating"},
    "slots": {},
    "layers": [],
    "author": "HouseOS",
    "license": "MIT",
}
S = M["slots"]
S["home.hero.backdrop"] = px("hero.png")
S["page.backdrop"] = px("sky.png")
optional = {
    "status.backdrop": px("roofline.png"),
    "auth.crest": px("crest.png", "contain"),
    "watch.tv.bezel": px("tv.png", "contain"),
    "space.room.scene": px("bedroom.png"),
    "state.empty": px("ghost.png", "contain"),
    "rail.surface": px("column.png", "slice", slice=24),
    "deck.surface": px("deck-frame.png", "slice", slice=15),
    "header.banner": px("banner-hall.png", rooms={
        room: f"art/banner-{name}.png" for room, name in (
            ("listen", "parlour"), ("party", "parlour"), ("watch", "screening"), ("house", "kitchen"),
            ("inbox", "kitchen"), ("files", "library"), ("games", "attic"), ("control", "cellar"),
            ("smart-home", "cellar"), ("me", "bedroom"))
        if (ART / f"banner-{name}.png").exists()}),
    "sheet.surface": px("sheet-frame.png", "slice", slice=18),
    "panel.surface": px("panel-frame.png", "slice", slice=12),
    "nowbar.surface": px("nowbar-frame.png", "slice", slice=12),
}
for slot, fill in optional.items():
    if (ART / fill["image"][4:]).exists():
        if "rooms" in fill and not fill["rooms"]:
            del fill["rooms"]
        S[slot] = fill

L = M["layers"]
def layer(image, **kv):
    if (ART / image).exists():
        L.append({"image": "art/" + image, **kv})

N3 = dict(fit="natural", scale=3)
# the night behind the pages
layer("clouds.png", where="page", fit="repeat-x", anchor="top", scale=3, drift=[-4, 0], opacity=0.9)
layer("manor.png", where="page", anchor="bottom-right", frames={"count": 32, "fps": 2}, depth=0.06, **N3)
layer("near.png", where="page", anchor="bottom-left", frames={"count": 8, "fps": 2}, depth=0.12, **N3)
layer("bat.png", where="page", anchor="left", frames={"count": 2, "fps": 6}, cross={"seconds": 14, "every": 61, "from": "left"}, **N3)
# Home's sky
layer("star.png", where="hero", anchor="top", cross={"seconds": 2, "every": 83, "from": "right"}, **N3)
# pokes (desktop, a click): the owl on its post at the corner of Home's picture turns its head and hoots
layer("owl.png", where="hero", anchor="bottom-right", frames={"count": 16, "fps": 4}, **N3,
      poke={"image": "art/owl-poke.png", "frames": {"count": 10, "fps": 10},
            "burst": {"image": "art/bit-feather.png", "count": 3}})
# the rail's foot: a candle on a side table; the roofline's cat and smoke
layer("candle-table.png", where="rail-foot", anchor="bottom", frames={"count": 8, "fps": 6}, **N3,
      poke={"image": "art/candle-table-poke.png", "frames": {"count": 6, "fps": 10},
            "burst": {"image": "art/bit-spark.png", "count": 4}})
layer("status-life.png", where="status", anchor="top", frames={"count": 16, "fps": 4}, **N3,
      poke={"image": "art/status-poke.png", "frames": {"count": 8, "fps": 8}})
# the rooms: flickering sconces everywhere, the ancestor who blinks, someone behind the curtain
layer("sconces.png", where="header", anchor="top", frames={"count": 4, "fps": 5}, **N3)
layer("portrait.png", where="header", anchor="top", frames={"count": 16, "fps": 3},
      rooms=["ask", "space", "listen", "party", "files"], **N3,
      poke={"image": "art/portrait-poke.png", "frames": {"count": 8, "fps": 8}})
layer("curtain.png", where="header", anchor="top", frames={"count": 24, "fps": 3}, rooms=["me"], **N3,
      poke={"image": "art/curtain-poke.png", "frames": {"count": 8, "fps": 9}})
# the wireless cabinet's candle on its bottom rail (the deck's layers sit inside its padding), burning while music plays
layer("deck-flame.png", where="deck", anchor="bottom-right", frames={"count": 4, "fps": 5}, playing=True, **N3,
      poke={"image": "art/deck-flame-poke.png", "frames": {"count": 6, "fps": 8},
            "burst": {"image": "art/bit-smoke.png", "count": 2}})
if not M["layers"]:
    del M["layers"]

tmp = OUT.with_suffix(".json.tmp")
tmp.write_text(json.dumps(M, indent=2, ensure_ascii=False) + "\n")
os.replace(tmp, OUT)
print("wrote", OUT, len(S), "slots", len(M.get("layers", [])), "layers")
