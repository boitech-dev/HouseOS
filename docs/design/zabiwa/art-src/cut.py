"""Zabiwa: every art slot cut from the artist's five fresques, as WebP.

The originals are © Zabiwa and stay outside the repository (SRC); only these crops ship, and
none is a whole work: the artist's full paintings are never published.
Rules: crops are taken at the originals' own resolution (never upscaled, never blurred, never
stretched: every output keeps its crop's exact aspect ratio), and no face, mask or ship is cut
through. Coordinates are in each original's pixels.

Some slots need designed light rather than a plain crop:
- the page's picture is at half light everywhere, a wall for the panels;
- the banners are veiled for the type over them, deepest at the left where the title starts;
- the rail's picture is the whole vertical fresque, dimmed under the room names and Ask Nox,
  in full light in the open middle;
- the sign-in crest is a round cameo in a gilt hairline ring.

    python3 docs/design/zabiwa/art-src/cut.py --src <folder with the five originals>
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

if "--src" not in sys.argv[:-1] and __name__ == "__main__":
    sys.exit("usage: cut.py --src <the folder with the artist's five originals, 1.jpg to 5.jpg>")
SRC = Path(sys.argv[sys.argv.index("--src") + 1]) if "--src" in sys.argv[:-1] else Path("originals")
OUT = Path(__file__).resolve().parents[4] / "themes" / "zabiwa" / "art"
BUDGET = 200 * 1024  # the kit's limit per image

# name: (source, crop box, treatment). Output size = the crop's own size.
CUTS = {
    # The header banner: the storm and spires along the top of the cathedral fresque; dark sky
    # where the title sits, the moon, the red spire and the gold sun toward the middle.
    "banner-spires.webp": ("3.jpg", (0, 0, 1500, 210), "title"),
    # Home: the whole gothic panorama (the artist's choice), mirrored, so its left (the hooded woman,
    # the white-haired face, the red-eyed mask) sits at the right of the greeting, in full light, at
    # full height; its right (the cathedral) runs off under the fade toward the words.
    "hero-panorama-full.webp": ("5.jpg", (0, 0, 2000, 469), "mirror"),
    # The rail, full height: the whole city column, from the sky's spiral and the plane, down the
    # Sign-in: the crowned woman with the cross, the top-left of the gothic fresque.
    "crest-cross.webp": ("1.jpg", (92, 0, 342, 250), "cameo"),
    # Watch: the boy in the bubble helmet, a sky inside it like a screen.
    "tv-helmet.webp": ("2.jpg", (1250, 400, 1730, 760), None),
    # Behind every page: the gothic fresque's saints and masks, from the red-haired mask to the
    # rose (its left fifth, with the crowned woman, stays out: a detail, not the work), at half
    # light so the panels and their type stand clear of it (part.page.scrim adds a little more).
    "page-saints.webp": ("1.jpg", (400, 0, 2000, 833), "veil"),
}


def ramp(t: float) -> float:
    """Smoothstep: gradients without a visible edge."""
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def light(size: tuple[int, int], level) -> Image.Image:
    """A greyscale light map, level(x, y) in 0–1."""
    w, h = size
    im = Image.new("L", size)
    im.putdata([int(255 * level(x / w, y / h)) for y in range(h) for x in range(w)])
    return Image.merge("RGB", [im] * 3)


def title(im: Image.Image) -> Image.Image:
    """Type lies over the whole banner on a phone (kicker, title, tagline) and over its left on a
    wide screen: 30 % at the left edge, rising to 55 % at the right, so the gilt still glows."""
    return ImageChops.multiply(im, light(im.size, lambda x, y: 0.3 + 0.25 * ramp(x / 0.8)))


def rail(im: Image.Image) -> Image.Image:
    """The whole vertical fresque, lit like a gallery wall: 24 % under the room names at the top and
    under Ask Nox at the foot (white type stays above 8:1 even on the white clouds, and the texture stays quiet), full light in
    the open middle. The rail is 232 wide: this 390-wide strip is drawn at 0.6 of its own pixels."""

    def level(x: float, y: float) -> float:
        up, down = ramp((y - 0.44) / 0.12), 1 - ramp((y - 0.78) / 0.1)
        return 0.24 + 0.76 * up * down

    return ImageChops.multiply(im, light(im.size, level))


def veil(im: Image.Image) -> Image.Image:
    """The page's picture: half light everywhere, a wall the panels hang on (it also keeps this
    dense fresque under the kit's 200 KB)."""
    return ImageChops.multiply(im, light(im.size, lambda x, y: 0.5))


def cameo(im: Image.Image) -> Image.Image:
    """A round cameo, its edge a gilt hairline (drawn 4× and scaled down, so the circle is smooth)."""
    from PIL import ImageDraw

    n, big = im.width, im.width * 4
    mask, ring = Image.new("L", (big, big)), Image.new("L", (big, big))
    ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)
    ImageDraw.Draw(ring).ellipse([0, 0, big - 1, big - 1], outline=255, width=14)
    mask, ring = mask.resize((n, n), Image.LANCZOS), ring.resize((n, n), Image.LANCZOS)
    out = Image.composite(Image.new("RGB", im.size, (201, 162, 74)), im, ring).convert("RGBA")
    out.putalpha(mask)
    return out


def save(im: Image.Image, path: Path) -> tuple[int, int]:
    for quality in (90, 86, 82, 78, 74, 70):
        im.save(path, "WEBP", quality=quality, method=6, alpha_quality=90)
        if path.stat().st_size <= BUDGET * 0.9:
            break
    return path.stat().st_size, quality


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, (source, box, how) in CUTS.items():
        im = Image.open(SRC / source).convert("RGB").crop(box)
        im = {"title": title, "rail": rail, "cameo": cameo, "veil": veil, "mirror": ImageOps.mirror}.get(how, lambda i: i)(im)
        n, q = save(im, OUT / name)
        total += n
        print(f"{name:26} {im.width}×{im.height}  q{q}  {n // 1024} KB")
    print(f"all art: {total // 1024} KB")


if __name__ == "__main__":
    main()
