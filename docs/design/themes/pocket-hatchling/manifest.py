"""theme.json, sprites.json and flavor.json (python3 manifest.py). A slot or layer is written only
when its picture exists in art/, so the theme builds at every step of make.py."""
from pal import SPRITE
from util import ART, THEME, write_json
import sprites_src

ROOM_BANNERS = ["listen", "watch", "games", "house", "files", "inbox", "me", "space", "smart-home",
                "party", "control", "ask"]

def slots():
    px = lambda image, fit="cover", **kw: {"image": image, "rendering": "pixel", "fit": fit, **kw}
    want = {
        "status.backdrop": px("art/status.png"),
        "home.hero.backdrop": px("art/hero.png"),
        "auth.crest": px("art/crest.png", "contain"),
        "watch.tv.bezel": px("art/tv.png", "contain"),
        "space.room.scene": px("art/room.png"),
        "state.empty": px("art/asleep.png", "contain"),
        "deck.surface": px("art/lcd-frame.png", "slice", slice=48),
        "sheet.surface": px("art/sheet-corner.png", "slice", slice=32),
        "panel.surface": px("art/panel-frame.png", "slice", slice=16),
        "header.banner": px("art/banner.png", rooms={r: f"art/banner-{r}.png" for r in ROOM_BANNERS}),
    }
    out = {}
    for slot, fill in want.items():
        if not (THEME / fill["image"]).exists():
            continue
        if "rooms" in fill:
            fill["rooms"] = {r: f for r, f in fill["rooms"].items() if (THEME / f).exists()} or None
            if not fill["rooms"]:
                del fill["rooms"]
        out[slot] = fill
    return out

NOT_CONTROL = ["home", "listen", "watch", "house", "files", "ask", "me", "smart-home", "inbox",
               "space", "party", "games"]

def layers():
    want = [
        # the homepage's tiled ground, drifting slowly (the Control Room keeps a plain ground)
        {"image": "art/tile.png", "where": "page", "fit": "repeat", "scale": 2, "drift": [4, 3],
         "rooms": NOT_CONTROL},
        # sparkles twinkling on the ground, and a few hearts drifting up
        {"image": "art/twinkle.png", "where": "page", "fit": "natural", "scale": 2,
         "particles": {"count": 16, "motion": "twinkle", "seconds": 4}, "rooms": NOT_CONTROL},
        {"image": "art/floaty.png", "where": "page", "fit": "natural", "scale": 2,
         "particles": {"count": 6, "motion": "rise", "seconds": 18}, "rooms": NOT_CONTROL},
        # now and then a shooting star crosses the top of the page, under the status bar
        {"image": "art/shooting-star.png", "where": "page", "fit": "natural", "scale": 2,
         "anchor": "top-left", "cross": {"seconds": 5, "every": 70, "from": "left"}},
        # Pip rides the status bar's garland like a zip line once in a while
        {"image": "art/walker.png", "where": "status", "fit": "natural", "scale": 2, "anchor": "top-left",
         "frames": {"count": 4, "fps": 4}, "cross": {"seconds": 14, "every": 60, "from": "left"}},
        # the hero's sky, under the hero picture (whose sky is clear)
        {"image": "art/sky.png", "where": "hero", "fit": "repeat-x", "scale": 2, "anchor": "top",
         "under": True},
        # the egg on its cloud in Home's hero: Pip blinks, and sometimes falls asleep
        {"image": "art/egg.png", "where": "hero", "fit": "natural", "scale": 2, "anchor": "bottom-right",
         "frames": {"count": 16, "fps": 2},
         "poke": {"image": "art/egg-poke.png", "frames": {"count": 8, "fps": 11},
                  "burst": {"image": "art/heart.png", "count": 8}}},
        # a star sticker in the hero's sky: poked, it turns like a coin
        {"image": "art/star.png", "where": "hero", "fit": "natural", "scale": 2, "anchor": "top-right",
         "poke": {"image": "art/star-spin.png", "frames": {"count": 8, "fps": 14},
                  "burst": {"image": "art/twinkle.png", "count": 6}}},
        # the shrine of web buttons at the rail's foot: poked, the buttons blink round the ring
        {"image": "art/shrine.png", "where": "rail-foot", "fit": "natural", "scale": 2, "anchor": "bottom",
         "poke": {"image": "art/shrine-poke.png", "frames": {"count": 8, "fps": 10}}},
        # the egg's sprout on the deck's shell: its leaves wiggle while music plays
        {"image": "art/sprout.png", "where": "deck", "fit": "natural", "scale": 2, "anchor": "top",
         "frames": {"count": 2, "fps": 3}, "playing": True,
         "poke": {"image": "art/sprout-poke.png", "frames": {"count": 6, "fps": 10},
                  "burst": {"image": "art/leaf.png", "count": 5}}},
        # Pip dances on the deck while music plays (Listen)
        {"image": "art/dance.png", "where": "deck", "fit": "natural", "scale": 2, "anchor": "bottom-right",
         "frames": {"count": 4, "fps": 4}, "playing": True, "rooms": ["listen"],
         "poke": {"image": "art/dance-poke.png", "frames": {"count": 6, "fps": 10},
                  "burst": {"image": "art/note.png", "count": 6}}},
        # hearts float up the LCD while music plays
        {"image": "art/heart.png", "where": "deck", "fit": "natural", "scale": 2, "playing": True,
         "opacity": 0.6, "particles": {"count": 4, "motion": "float", "seconds": 9}},
    ]
    return [l for l in want if (THEME / l["image"]).exists()]

def theme():
    return {
        "$schema": "../_schema/theme.schema.json",
        "id": "pocket-hatchling",
        "schema": 1,
        "version": 3,
        "names": {"en": "Pocket Hatchling", "fr": "Éclosion de poche"},
        "description": {
            "en": "A keychain pet on a glittery handmade homepage.",
            "fr": "Un animal de poche sur une page perso pailletée.",
        },
        "schemes": ["light"],
        "density": "comfortable",
        "identity": "pixel",
        "fonts": {"display": "DynaPuff", "body": "Nunito", "mono": "Pixelify Sans"},
        "slots": slots(),
        "layers": layers(),
        "parts": {"header": "banner", "panel": "card", "dock": "floating", "nowbar": "floating"},
        "author": "HouseOS theme studio (art by code, original)",
        "license": "MIT",
    }

TITLES = {
    "dj": ("Mixtape maker", "Pro de la mixtape"),
    "explorer": ("Balloon wanderer", "Balade en montgolfière"),
    "night_owl": ("Up past lights-out", "Debout après l’extinction"),
    "early_bird": ("First to hatch", "Première éclosion"),
    "weekend": ("Ice-cream weekend", "Week-end glace"),
    "genre_guardian": ("Fan club of {genre}", "Fan-club · {genre}"),
    "broken_record": ("Same song, again!", "Encore la même !"),
    "marathon": ("Never-sleep pet", "Zéro dodo"),
    "radio_host": ("Antenna twitcher", "Antenne en alerte"),
    "task_hero": ("Sparkle sweeper", "Coup de balai magique"),
    "grocery_runner": ("Strawberry fetcher", "Cueillette de fraises"),
    "planner": ("Alarm setter", "Réglé comme un réveil"),
    "wall_poet": ("Sticker poet", "Poésie en autocollants"),
    "courier": ("Love-letter courier", "Mots doux express"),
    "curator": ("Keeper of favourites", "Trésor des favoris"),
    "high_scorer": ("Top of the high scores", "En tête des records"),
    "collector": ("Shiny collector", "Collection brillante"),
    "game_hopper": ("Hop-hop gamer", "Saute-mouton des jeux"),
    "console_hopper": ("Every-console pal", "Toutes les consoles"),
    "romhacker": ("Cartridge tinkerer", "Bidouille de cartouche"),
}

def flavor():
    out = {"$description": "Pocket Hatchling's words: only the house titles' names, sticker-book style. French says tu."}
    for key, (en, fr) in TITLES.items():
        assert len(en) <= 28 and len(fr) <= 28, key
        out[f"title.{key}.name"] = {"en": en, "fr": fr}
    out["title.star.mark"] = {"en": "♥", "fr": "♥"}
    return out

def sprites():
    used = {ch for g in sprites_src.ALL.values() for row in g for ch in row if ch != "."}
    return {
        "$description": "Pocket Hatchling's pieces, pixel-drawn by code (docs/design/themes/pocket-hatchling/sprites_src.py): Pip the hatchling as Nox, five kawaii avatars, twenty die-cut sticker medals, LCD-toy room marks and rubber-button keys.",
        "palette": {k: SPRITE[k][0] for k in sorted(used)},
        "glyphs": sprites_src.ALL,
    }

if __name__ == "__main__":
    write_json(THEME / "theme.json", theme())
    write_json(THEME / "sprites.json", sprites())
    write_json(THEME / "flavor.json", flavor())
    print("theme.json, sprites.json, flavor.json written;", len(slots()), "slots,", len(layers()), "layers")
