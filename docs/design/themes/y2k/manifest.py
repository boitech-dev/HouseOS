"""Millennium Skin's theme.json (manifest, slots, layers), written atomically.

    python3 docs/design/themes/y2k/manifest.py
"""

import json
import os
from pathlib import Path

THEME = Path(__file__).resolve().parents[4] / "themes" / "y2k"


def smooth(image, fit="cover", **extra):
    return {"image": image, "rendering": "smooth", "fit": fit, **extra}


def pixel(image, fit="cover", **extra):
    return {"image": image, "rendering": "pixel", "fit": fit, **extra}


# Sparkles stay out of the rooms whose empty states and greetings sit on the open page.
SPARKLE = ["listen", "watch", "house", "files", "inbox", "party", "me"]
# Every room but the Control Room, which stays calm: no drifting or twinkling behind its forms.
CALM = ["home", "listen", "watch", "house", "files", "ask", "me", "smart-home", "inbox", "space", "party", "games"]

manifest = {
    "$schema": "../_schema/theme.schema.json",
    "id": "y2k",
    "schema": 1,
    "version": 1,
    "names": {"en": "Millennium Skin", "fr": "Skin an 2000"},
    "description": {
        "en": "A Y2K media-player skin: chrome, LCD, clear plastic.",
        "fr": "Un skin de lecteur de l’an 2000 : chrome, LCD, plastique.",
    },
    "schemes": ["dark", "light"],
    "density": "comfortable",
    "identity": "pixel",
    "fonts": {"display": "Michroma", "body": "Lexend", "mono": "Kode Mono"},
    "slots": {
        "home.hero.backdrop": smooth("art/hero-night.webp", schemes={"light": "art/hero.webp"}),
        "page.backdrop": smooth("art/page-night.webp", schemes={"light": "art/page-sky.webp"}),
        "auth.crest": smooth("art/crest.webp", "contain"),
        "state.empty": smooth("art/empty.webp", "contain"),
        "watch.tv.bezel": smooth("art/tv.webp", "contain"),
        "space.room.scene": smooth("art/room-night.webp", schemes={"light": "art/room.webp"}),
        "deck.surface": pixel("art/skin-deck.png", "slice", slice=24, schemes={"light": "art/skin-deck-bondi.png"}),
        "rail.surface": pixel("art/skin-rail.png", "slice", slice=24, schemes={"light": "art/skin-rail-bondi.png"}),
        "panel.surface": pixel("art/skin-panel.png", "slice", slice=16, schemes={"light": "art/skin-panel-bondi.png"}),
        "sheet.surface": pixel("art/skin-panel.png", "slice", slice=16, schemes={"light": "art/skin-panel-bondi.png"}),
        "nowbar.surface": pixel("art/skin-nowbar.png", "slice", slice=12, schemes={"light": "art/skin-nowbar-bondi.png"}),
        "dock.surface": pixel("art/skin-dock.png", "slice", slice=8, schemes={"light": "art/skin-dock-bondi.png"}),
    },
    "parts": {"header": "framed", "panel": "card", "dock": "flush", "nowbar": "floating"},
    "layers": [
        # The rail's picture (the hero's language: a rainbow disc behind a frosted playlist window).
        {"image": "art/rail-night.webp", "where": "rail", "fit": "natural", "anchor": "top", "rendering": "smooth", "schemes": ["dark"]},
        {"image": "art/rail-day.webp", "where": "rail", "fit": "natural", "anchor": "top", "rendering": "smooth", "schemes": ["light"]},
        {"image": "art/rail-led.png", "where": "rail", "fit": "natural", "anchor": "top-right", "scale": 2,
         "rendering": "pixel", "frames": {"count": 8, "fps": 2}},
        {"image": "art/clouds.webp", "where": "page", "fit": "repeat-x", "anchor": "top", "rendering": "smooth",
         "opacity": 0.75, "drift": [-5, 0], "depth": 0.15, "rooms": CALM, "schemes": ["light"]},
        {"image": "art/sparkle.png", "where": "page", "scale": 2, "rendering": "pixel",
         "particles": {"count": 8, "motion": "twinkle", "seconds": 7}, "rooms": SPARKLE},
        {"image": "art/flare.webp", "where": "page", "fit": "natural", "anchor": "top", "rendering": "smooth",
         "blend": "screen", "opacity": 0.85, "cross": {"seconds": 16, "every": 150, "from": "left"}, "rooms": CALM},
        {"image": "art/spectrum.png", "where": "deck", "fit": "natural", "anchor": "top-right", "scale": 2,
         "rendering": "pixel", "frames": {"count": 8, "fps": 8}, "playing": True, "rooms": ["home", "listen"], "schemes": ["dark"],
         "poke": {"image": "art/spectrum-spike.png", "frames": {"count": 6, "fps": 12}}},
        {"image": "art/spectrum-bondi.png", "where": "deck", "fit": "natural", "anchor": "top-right", "scale": 2,
         "rendering": "pixel", "frames": {"count": 8, "fps": 8}, "playing": True, "rooms": ["home", "listen"], "schemes": ["light"],
         "poke": {"image": "art/spectrum-spike-bondi.png", "frames": {"count": 6, "fps": 12}}},
        # Pokes (desktop): the flip phone flips open and a heart beats on its LCD; the keychain egg
        # swings on its ring; the hero's chrome star spins and throws sparkles.
        {"image": "art/phone.webp", "where": "rail-foot", "fit": "natural", "anchor": "bottom-left", "rendering": "smooth",
         "poke": {"image": "art/phone-poke.webp", "frames": {"count": 11, "fps": 12}, "burst": {"image": "art/bit-heart.png", "count": 6}}},
        {"image": "art/egg.webp", "where": "rail-foot", "fit": "natural", "anchor": "right", "rendering": "smooth",
         "poke": {"image": "art/egg-poke.webp", "frames": {"count": 12, "fps": 14}, "burst": {"image": "art/bit-lcd.png", "count": 5}}},
        {"image": "art/star.webp", "where": "hero", "fit": "natural", "anchor": "bottom-right", "rendering": "smooth",
         "poke": {"image": "art/star-poke.webp", "frames": {"count": 12, "fps": 16}, "burst": {"image": "art/bit-sparkle.png", "count": 8}}},
        {"image": "art/gleam.webp", "where": "hero", "fit": "natural", "anchor": "left", "rendering": "smooth",
         "blend": "screen", "opacity": 0.35, "cross": {"seconds": 5, "every": 45, "from": "left"}},
    ],
    "author": "HouseOS theme agent",
    "license": "CC-BY-4.0",
}


if __name__ == "__main__":
    path = THEME / "theme.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    print("theme.json written")
