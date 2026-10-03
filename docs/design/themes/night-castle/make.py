"""Regenerates every picture and data file of the night-castle theme (The Vampire's Keep).
    python3 docs/design/themes/night-castle/make.py
Then: theme_kit check night-castle, theme_kit build (through the lock), tour.cjs night-castle."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import banners  # noqa: E402
import data  # noqa: E402
import frames  # noqa: E402
import hero  # noqa: E402
import page  # noqa: E402
import pieces  # noqa: E402
import railfoot  # noqa: E402
import slots  # noqa: E402
from lib import ART, save  # noqa: E402


def main():
    # the hero and its sky (Home), the bats (hero and page)
    save(hero.make(), "hero-keep.png", scale=1)
    save(hero.sky(), "hero-sky.png", scale=1)
    save(hero.bats(), "bats.png", scale=1)
    save(hero.gargoyle(), "gargoyle.png", scale=1)
    save(hero.gargoyle_wake(), "gargoyle-wake.png", scale=1)
    save(hero.tiny_bat(), "tiny-bat.png", scale=1)
    # the page's parallax
    save(page.sky(), "sky.png", scale=3)
    save(page.far_castle(), "far-castle.png", scale=1)
    save(page.clouds(), "clouds.png", scale=1)
    save(page.terrace(), "terrace.png", scale=1)
    # frames and textures
    save(frames.panel_frame(), "frame-panel.png")
    save(frames.nowbar_frame(), "frame-bar.png")
    save(frames.sheet_frame(), "frame-sheet.png")
    import pixel
    pixel.scale(frames.stone_texture(), 3).save(ART / "stone.png", optimize=True)
    save(frames.battlements_texture(), "battlements.png")
    save(frames.deck_frame(), "frame-deck.png")
    save(frames.ember(), "ember.png", scale=1)
    save(frames.deck_candle(), "deck-candle.png", scale=1)
    save(frames.torch(), "torch.png", scale=1)
    save(frames.candle_snuff(), "candle-snuff.png", scale=1)
    save(frames.torch_flare(), "torch-flare.png", scale=1)
    save(frames.spark(), "spark.png", scale=1)
    # banners, one per wing
    for name, fn in banners.BANNERS.items():
        save(fn(), name, scale=1)
    # fixed pictures
    save(slots.crest(), "crest.png")
    save(slots.empty(), "empty-sconce.png")
    save(slots.bezel(), "tv-frame.png")
    save(slots.chamber(), "chamber.png")
    save(railfoot.idle(), "candelabra-foot.png", scale=1)
    save(railfoot.whip(), "candelabra-whip.png", scale=1)
    save(railfoot.heart(), "heart-bit.png", scale=1)
    # pieces, words, tokens, manifest
    pieces.main()
    data.main()
    total = sum(p.stat().st_size for p in ART.iterdir())
    big = max(ART.iterdir(), key=lambda p: p.stat().st_size)
    print(f"art: {len(list(ART.iterdir()))} files, {total // 1024} KB, largest {big.name} {big.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
