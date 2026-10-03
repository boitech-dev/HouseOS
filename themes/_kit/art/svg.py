"""Vector art by code: write SVG (gradients, filters, feTurbulence paper and grain), render it to
a PNG or WebP at the exact size, and finish it (grain, a palette). Needs `rsvg-convert` (librsvg).

    from svg import render
    render(open("hero.svg").read(), "themes/<id>/art/hero.webp", 1600, 600)

An SVG may also ship as-is in art/ (textures, crisp shapes): no scripts, no outside links, no
fonts (text in pictures is never allowed: words come from the interface)."""

import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops


def render(svg: str, out, width: int, height: int, grain: float = 0.0, seed: int = 1) -> Path:
    """Rasterise `svg` (text) at width × height to `out` (.png or .webp); `grain` 0–0.1 adds film grain."""
    if not shutil.which("rsvg-convert"):
        raise SystemExit("rsvg-convert is missing (install librsvg2-bin)")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "out.png"
        subprocess.run(["rsvg-convert", "-w", str(width), "-h", str(height), "-o", str(png)],
                       input=svg.encode(), check=True)  # fmt: skip
        image = Image.open(png).convert("RGBA")
    if grain:
        image = add_grain(image, grain, seed)
    if out.suffix == ".webp":
        image.save(out, quality=86, method=6)
    else:
        image.save(out, optimize=True)
    return out


def add_grain(image: Image.Image, amount: float, seed: int = 1) -> Image.Image:
    """Monochrome noise, `amount` 0–0.1 of full range: flat vector fills stop looking plastic.
    Overlaid around mid-grey, so the picture keeps its own lights and darks (never washed grey)."""
    if not amount:
        return image
    rnd = random.Random(seed)
    noise = Image.new("L", image.size)
    noise.putdata([max(0, min(255, 128 + int(rnd.gauss(0, 255 * amount)))) for _ in range(image.width * image.height)])
    rgba = image.convert("RGBA")
    grained = ImageChops.overlay(rgba.convert("RGB"), Image.merge("RGB", (noise, noise, noise))).convert("RGBA")
    grained.putalpha(rgba.getchannel("A"))
    return grained


def limit(image: Image.Image, colours: int) -> Image.Image:
    """Quantise to `colours`: a vector picture that sits next to pixel art."""
    return image.convert("RGBA").quantize(colours, method=Image.Quantize.FASTOCTREE).convert("RGBA")
