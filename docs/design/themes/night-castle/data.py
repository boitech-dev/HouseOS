"""theme.json and tokens.json for night-castle, from the same palette as the art.
    python3 docs/design/themes/night-castle/data.py"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from jsonw import write  # noqa: E402
from palette import BONE, CRIMSON, GOLD, NIGHT, STONE  # noqa: E402

THEME = HERE.parents[3] / "themes" / "night-castle"


def c(v):
    return {"$value": v}


def s(v, kind="string"):
    return {"$type": kind, "$value": v}


def text(family, size, weight, line, tracking=None, case=None):
    v = {"fontFamily": "{font.%s}" % family, "fontSize": size, "fontWeight": weight, "lineHeight": line}
    if tracking is not None:
        v["letterSpacing"] = tracking
    if case:
        v["textTransform"] = case
    return {"$value": v}


BEVEL = f"inset 1px 1px 0 {STONE[6]}, inset -1px -1px 0 {STONE[1]}"
GOLD_EDGE = f"1px solid {GOLD[3]}"

tokens = {
    "$schema": "../_schema/tokens.schema.json",
    "$description": "Night Castle: violet night, blue-grey stone, one crimson, tarnished gold, bone ink, candlelight. SNES 15-bit colours.",
    "seed": {
        "$type": "color",
        "neutral": c("oklch(0.56 0.03 285)"),
        "accent": c("oklch(0.5 0.19 22)"),
        "success": c("oklch(0.74 0.15 142)"),
        "warning": c("oklch(0.85 0.14 88)"),
        "danger": c("oklch(0.68 0.19 48)"),
        "info": c("oklch(0.72 0.1 232)"),
        "private": c("oklch(0.68 0.14 310)"),
    },
    "color": {
        "$type": "color",
        "bg": {
            "canvas": c(NIGHT[1]),
            "surface": c(STONE[2]),
            "raised": c(STONE[4]),
            "overlay": c("#141424"),
            "sunken": c(STONE[0]),
            "inverse": c(BONE[4]),
            "hover": c(STONE[5]),
            "pressed": c(STONE[6]),
            "selected": c(CRIMSON[1]),
        },
        "fg": {
            "default": c(BONE[4]),
            "muted": c(BONE[3]),
            "subtle": c(BONE[2]),
            "placeholder": c(BONE[2]),
            "disabled": c(STONE[6]),
            "inverse": c(NIGHT[1]),
            "link": c(GOLD[5]),
        },
        "border": {
            "subtle": c(STONE[4]),
            "default": c(STONE[5]),
            "strong": c(STONE[8]),
        },
        "focus-ring": c(GOLD[5]),
        "accent": {
            "soft": c("#281020"),
            "border": c(CRIMSON[4]),
        },
        "paper": {
            "bg": c("#e8e0c0"),
            "fg": c("#281808"),
            "muted": c("#584028"),
        },
        "room": {
            "home": c("oklch(0.86 0.09 85)"),
            "listen": c("oklch(0.72 0.16 18)"),
            "watch": c("oklch(0.82 0.06 250)"),
            "house": c("oklch(0.78 0.11 135)"),
            "files": c("oklch(0.8 0.07 45)"),
            "ask": c("oklch(0.74 0.12 305)"),
            "me": c("oklch(0.76 0.12 350)"),
            "control": c("oklch(0.76 0.04 250)"),
            "smart-home": c("oklch(0.82 0.13 65)"),
            "inbox": c("oklch(0.78 0.09 200)"),
            "space": c("oklch(0.74 0.1 280)"),
            "party": c("oklch(0.74 0.15 0)"),
            "games": c("oklch(0.78 0.12 165)"),
        },
        "sprite": {
            "$description": "The castle's pieces: k night outline, n/l/L stone, m moonlit steel, c bone, C gold light, V gold, w gold shadow, e/E/r crimson, v Nox's violet, g green glass, p candle yellow, P flame, i holy water",
            "outline": c(NIGHT[0]),
            "dark": c(NIGHT[4]),
            "mid-dark": c(STONE[5]),
            "mid": c(STONE[7]),
            "mist": c("#b8c0d0"),
            "light": c(BONE[4]),
            "light-dim": c(GOLD[5]),
            "accent": c("#d82838"),
            "accent-hi": c(CRIMSON[6]),
            "accent-deep": c(CRIMSON[2]),
            "familiar": c("#7050a0"),
            "familiar-mid": c(GOLD[4]),
            "familiar-deep": c(GOLD[2]),
            "good": c("#38a860"),
            "alert": c("#f8c040"),
            "paper": c("#f08820"),
            "ink": c("#58a0e8"),
        },
        "scrim": c("alpha(#080010, 78%)"),
        "shadow": c("#080010"),
    },
    "font": {
        "$type": "fontFamily",
        "display": c(["Grenze Gotisch", "serif"]),
        "body": c(["Vollkorn", "serif"]),
        "mono": c(["DotGothic16", "monospace"]),
    },
    "text": {
        "$type": "typography",
        "display-xl": text("display", 48, 800, 1.05, 0),
        "display-l": text("display", 37, 800, 1.1, 0),
        "display-m": text("display", 29, 800, 1.15, 0),
        "brand": text("display", 22, 800, 1.2, 0.01),
        "title-l": text("display", 23, 800, 1.2, 0.01),
        "title-m": text("display", 19, 800, 1.25, 0.01),
        "title-s": text("body", 16, 700, 1.3),
        "body-l": text("body", 18, 400, 1.5),
        "body-m": text("body", 16, 400, 1.5),
        "body-s": text("body", 14, 400, 1.45),
        "action": text("body", 15, 600, 1.2),
        "label": text("body", 13, 600, 1.25, 0.06, "uppercase"),
        "caption": text("body", 12, 400, 1.4, 0.01),
        "numeric": text("mono", 15, 400, 1.1),
    },
    "radius": {
        "$type": "dimension",
        "control": c("{radius.none}"),
        "card": c("{radius.none}"),
        "sheet": c("{radius.none}"),
        "chip": c("{radius.xs}"),
        "media": c("{radius.none}"),
        "avatar": c("{radius.full}"),
    },
    "elev": {
        "$type": "shadow",
        "1": c(f"2px 2px 0 alpha({NIGHT[0]}, 70%)"),
        "2": c(f"3px 3px 0 alpha({NIGHT[0]}, 70%)"),
        "3": c(f"4px 4px 0 alpha({NIGHT[0]}, 75%)"),
        "4": c(f"6px 6px 0 alpha({NIGHT[0]}, 80%)"),
    },
    "material": {
        "canvas": {
            "texture": s("none"),
        },
        "surface": {
            "texture": s("url(art/stone.png)"),
            "border": s(f"1px solid {STONE[5]}"),
            "shadow": s(f"inset 1px 1px 0 {STONE[4]}, inset -1px -1px 0 {STONE[0]}", "shadow"),
        },
        "raised": {
            "bg": s(STONE[4], "color"),
            "border": s(f"1px solid {STONE[1]}"),
            "shadow": s(BEVEL, "shadow"),
        },
        "overlay": {
            "border": s(GOLD_EDGE),
        },
        "sunken": {
            "border": s(f"1px solid {STONE[7]}"),
            "shadow": s(f"inset 2px 2px 0 {NIGHT[0]}", "shadow"),
        },
        "media": {
            "border": s(f"1px solid {STONE[1]}"),
        },
        "screen": {
            "bg": s(NIGHT[0], "color"),
        },
    },
    "part": {
        "page": {
            "scrim": s(f"alpha({NIGHT[1]}, 66%)", "color"),
            "ink-shadow": s(f"2px 2px 0 {NIGHT[0]}"),
            "quiet": s(f"alpha({STONE[2]}, 88%)", "color"),
            "gallery": s(f"alpha({STONE[1]}, 92%)", "color"),
        },
        "status": {
            "bg": s(NIGHT[0], "color"),
            "texture": s("url(art/battlements.png)"),
            "border": s(f"1px solid {GOLD[2]}"),
            "art-opacity": s("1"),
        },
        "rail": {
            "bg": s(STONE[1], "color"),
            "texture": s("url(art/stone.png)"),
            "border": s(f"1px solid {GOLD[2]}"),
            "ink-shadow": s(f"2px 2px 0 {NIGHT[0]}"),
        },
        "dock": {
            "bg": s(STONE[1], "color"),
            "texture": s("url(art/stone.png)"),
            "border": s(f"1px solid {GOLD[2]}"),
        },
        "nowbar": {
            "bg": s(STONE[2], "color"),
            "border": s(GOLD_EDGE),
            "radius": s("{radius.none}", "dimension"),
            "shadow": s(f"4px 4px 0 alpha({NIGHT[0]}, 75%)", "shadow"),
        },
        "header": {
            "kicker": s(GOLD[4], "color"),
            "banner-fade": s(NIGHT[1], "color"),
            "banner-wash": s(0.2, "number"),
        },
        "panel": {
            "head": s(GOLD[4], "color"),
            "border": s(f"1px solid {NIGHT[0]}"),
        },
        "control": {
            "bg": s(f"linear-gradient({STONE[5]}, {STONE[4]} 50%, {STONE[3]})"),
            "shadow": s(BEVEL, "shadow"),
            "primary-bg": s(f"linear-gradient({CRIMSON[4]}, {CRIMSON[3]} 55%, {CRIMSON[2]})"),
            "primary-shadow": s(f"inset 0 0 0 1px {GOLD[4]}, inset 2px 2px 0 {CRIMSON[5]}, inset -2px -2px 0 {CRIMSON[1]}", "shadow"),
        },
        "meter": {
            "track": s(CRIMSON[0], "color"),
            "pattern": s(f"repeating-linear-gradient(to right, transparent 0 5px, alpha({NIGHT[0]}, 85%) 5px 7px)"),
            "thumb": s(BONE[4], "color"),
            "thumb-radius": s("0", "dimension"),
        },
    },
    "dur": {"$type": "duration", "fast": c(100), "base": c(160), "slow": c(260)},
    "ease": {
        "$type": "cubicBezier",
        "standard": c([0.3, 0, 0.1, 1]),
        "emphasized": c([0.2, 0.8, 0.2, 1]),
    },
    "icon": {"stroke": s(2, "number")},
}


theme = {
    "$schema": "../_schema/theme.schema.json",
    "id": "night-castle",
    "schema": 1,
    "version": 4,
    "names": {"en": "The Vampire's Keep", "fr": "Le donjon du vampire"},
    "description": {
        "en": "A 16-bit gothic castle: candles, crimson and gold.",
        "fr": "Un château gothique 16 bits : bougies, pourpre et or.",
    },
    "schemes": ["dark"],
    "density": "comfortable",
    "identity": "pixel",
    "fonts": {"display": "Grenze Gotisch", "body": "Vollkorn", "mono": "DotGothic16"},
    "slots": {
        "home.hero.backdrop": {"image": "art/hero-keep.png", "rendering": "pixel", "fit": "cover"},
        "panel.surface": {"image": "art/frame-panel.png", "rendering": "pixel", "fit": "slice", "slice": 18},
        "rail.surface": {"image": "art/frame-panel.png", "rendering": "pixel", "fit": "slice", "slice": 18},
        "nowbar.surface": {"image": "art/frame-bar.png", "rendering": "pixel", "fit": "slice", "slice": 12},
        "dock.surface": {"image": "art/frame-bar.png", "rendering": "pixel", "fit": "slice", "slice": 12},
        "sheet.surface": {"image": "art/frame-sheet.png", "rendering": "pixel", "fit": "slice", "slice": 18},
        "auth.crest": {"image": "art/crest.png", "rendering": "pixel", "fit": "contain"},
        "state.empty": {"image": "art/empty-sconce.png", "rendering": "pixel", "fit": "contain"},
        "watch.tv.bezel": {"image": "art/tv-frame.png", "rendering": "pixel", "fit": "contain"},
        "space.room.scene": {"image": "art/chamber.png", "rendering": "pixel", "fit": "cover"},
        "deck.surface": {"image": "art/frame-deck.png", "rendering": "pixel", "fit": "slice", "slice": 15},
        "page.backdrop": {"image": "art/sky.png", "rendering": "smooth", "fit": "cover", "anchor": "bottom"},
        "header.banner": {"image": "art/banner-hall.png", "rendering": "pixel", "fit": "cover", "rooms": {
            "listen": "art/banner-chapel.png", "files": "art/banner-library.png", "control": "art/banner-clock.png",
            "me": "art/banner-throne.png", "space": "art/banner-quiet.png", "games": "art/banner-armory.png",
            "watch": "art/banner-gallery.png"}},
    },
    "layers": [
        {"image": "art/far-castle.png", "where": "page", "fit": "natural", "anchor": "bottom-right",
         "scale": 3, "rendering": "pixel", "depth": 0.15, "opacity": 0.42,
         "rooms": ["listen", "watch", "house", "files", "ask", "me", "smart-home", "inbox", "space", "party", "games"]},
        {"image": "art/clouds.png", "where": "page", "fit": "repeat-x", "anchor": "bottom", "scale": 3,
         "rendering": "pixel", "drift": [-5, 0]},
        {"image": "art/terrace.png", "where": "page", "fit": "repeat-x", "anchor": "bottom", "scale": 3,
         "rendering": "pixel", "depth": 0.45},
        {"image": "art/bats.png", "where": "page", "fit": "natural", "anchor": "left", "scale": 3,
         "rendering": "pixel", "frames": {"count": 2, "fps": 5}, "cross": {"seconds": 16, "every": 45, "from": "right"}},
        {"image": "art/hero-sky.png", "where": "hero", "fit": "natural", "anchor": "top-right", "scale": 3,
         "rendering": "pixel", "under": True},
        {"image": "art/bats.png", "where": "hero", "fit": "natural", "anchor": "top", "scale": 3,
         "rendering": "pixel", "frames": {"count": 2, "fps": 6}, "cross": {"seconds": 7, "every": 24, "from": "right"}},
        {"image": "art/gargoyle.png", "where": "hero", "fit": "natural", "anchor": "top-right", "scale": 3,
         "rendering": "pixel",
         "poke": {"frames": {"count": 7, "fps": 9}, "image": "art/gargoyle-wake.png",
                  "burst": {"image": "art/tiny-bat.png", "count": 5}}},
        {"image": "art/candelabra-foot.png", "where": "rail-foot", "fit": "natural", "anchor": "bottom", "scale": 3,
         "rendering": "pixel", "frames": {"count": 4, "fps": 5},
         "poke": {"frames": {"count": 8, "fps": 9}, "image": "art/candelabra-whip.png",
                  "burst": {"image": "art/heart-bit.png", "count": 4}}},
        {"image": "art/torch.png", "where": "status", "fit": "natural", "anchor": "bottom", "scale": 3,
         "rendering": "pixel", "frames": {"count": 4, "fps": 6},
         "poke": {"frames": {"count": 4, "fps": 8}, "image": "art/torch-flare.png",
                  "burst": {"image": "art/spark.png", "count": 6}}},
        {"image": "art/deck-candle.png", "where": "deck", "fit": "natural", "anchor": "bottom-left", "scale": 3,
         "rendering": "pixel", "frames": {"count": 4, "fps": 5},
         "poke": {"frames": {"count": 7, "fps": 9}, "image": "art/candle-snuff.png"}},
        {"image": "art/deck-candle.png", "where": "deck", "fit": "natural", "anchor": "bottom-right", "scale": 3,
         "rendering": "pixel", "frames": {"count": 4, "fps": 4},
         "poke": {"frames": {"count": 7, "fps": 9}, "image": "art/candle-snuff.png"}},
        {"image": "art/ember.png", "where": "deck", "scale": 3, "rendering": "pixel", "playing": True,
         "blend": "screen", "particles": {"count": 6, "motion": "rise", "seconds": 7}},
    ],
    "parts": {"header": "banner", "panel": "card", "dock": "flush", "nowbar": "floating"},
    "author": "HouseOS theme agent",
    "license": "CC-BY-4.0",
}


TITLES = {
    "dj": ("Master of the organ", "Maître de l’orgue"),
    "explorer": ("Torchbearer", "Porte-flambeau"),
    "night_owl": ("Child of the night", "Enfant de la nuit"),
    "early_bird": ("Up before the dawn", "Debout avant l’aube"),
    "weekend": ("Keeper of the feast", "Hôte du festin"),
    "genre_guardian": ("Sentinel of {genre}", "Sentinelle · {genre}"),
    "broken_record": ("The same hymn again", "Encore le même hymne"),
    "marathon": ("Until the last candle", "Jusqu’à la dernière bougie"),
    "radio_host": ("Bell ringer", "Sonneur de cloches"),
    "task_hero": ("Monster slayer", "Tueur de monstres"),
    "grocery_runner": ("Found the roast in the wall", "A trouvé le rôti du mur"),
    "planner": ("Keeper of the grimoire", "Gardien du grimoire"),
    "wall_poet": ("Scribe of the crypt", "Scribe de la crypte"),
    "courier": ("Swift as a thrown dagger", "Vif comme une dague"),
    "curator": ("Holder of every key", "Porteur de toutes les clés"),
    "high_scorer": ("Crowned in the great hall", "Couronné au château"),
    "collector": ("Collector of hearts", "Collectionneur de cœurs"),
    "game_hopper": ("Wanderer of the halls", "Rôdeur des couloirs"),
    "console_hopper": ("Crossed every realm", "A franchi chaque royaume"),
    "romhacker": ("Alchemist of the crystal", "Alchimiste du cristal"),
}
flavor = {"$description": "The Vampire's Keep: the house titles as a vampire hunter's feats; levels counted in hearts. English and French (tu).",
          **{f"title.{k}.name": {"en": en, "fr": fr} for k, (en, fr) in TITLES.items()},
          "title.star.mark": {"en": "♥", "fr": "♥"}}


def main():
    for k, (en, fr) in TITLES.items():
        assert len(en) <= 28 and len(fr) <= 28, k
    write(THEME / "flavor.json", flavor)
    write(THEME / "tokens.json", tokens)
    write(THEME / "theme.json", theme)
    print("tokens.json, theme.json written")


if __name__ == "__main__":
    main()
