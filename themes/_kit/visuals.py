"""The theme kit's pictures of the parts (themes/_kit/visuals/*.webp), from shots.cjs's
screenshots. AGENT-KIT.md links them and the downloadable guide shows them. Python 3 + Pillow; run
from anywhere:

    node themes/_kit/shots.cjs --out <folder>
    python3 themes/_kit/visuals.py <folder>

Every picture is WebP and at most 200 KB (quality steps down until it fits).
"""

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "themes/_kit/visuals"
BUDGET = 200_000


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        for folder in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"):
            if Path(folder, name).exists():
                return ImageFont.truetype(str(Path(folder, name)), size)
    return ImageFont.load_default(size)


def save(image: Image.Image, name: str) -> None:
    for quality in range(84, 30, -6):
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "WEBP", quality=quality, method=6)
        if buffer.tell() <= BUDGET:
            (OUT / f"{name}.webp").write_bytes(buffer.getvalue())
            print(f"{name}.webp  {image.width}×{image.height}  {buffer.tell() // 1024} KB  q{quality}")
            return
    raise SystemExit(f"{name}: over 200 KB even at low quality; make it smaller")


def fit(image: Image.Image, width: int) -> Image.Image:
    return image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)


def tag(draw: ImageDraw.ImageDraw, xy, text: str, fill: str, size=20, ink="#0b0b0b") -> None:
    f = font(size)
    x, y = xy
    left, top, right, bottom = draw.textbbox((x + 10, y + 5), text, font=f)
    draw.rounded_rectangle((x, y, right + 10, bottom + 7), radius=6, fill=fill)
    draw.text((x + 10, y + 5), text, font=f, fill=ink)


def outline(draw, box, colour, width=4, dashed=False):
    x, y, w, h = box
    if not dashed:
        draw.rectangle((x + 2, y + 2, x + w - 2, y + h - 2), outline=colour, width=width)
        return
    for a, b in (((x, y), (x + w, y)), ((x, y + h), (x + w, y + h)), ((x, y), (x, y + h)), ((x + w, y), (x + w, y + h))):
        length = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        for s in range(0, length, 24):
            e = min(s + 14, length)
            if a[1] == b[1]:
                draw.line((a[0] + s, a[1], a[0] + e, a[1]), fill=colour, width=width)
            else:
                draw.line((a[0], a[1] + s, a[0], a[1] + e), fill=colour, width=width)


def parts_map(shots: Path) -> None:
    boxes = json.loads((shots / "boxes.json").read_text())
    desk, phone = Image.open(shots / "map-desktop.png"), Image.open(shots / "map-phone.png")
    d = ImageDraw.Draw(desk)
    b = boxes["desktop"]
    main = b["main"][0]
    outline(d, (main[0] + 6, main[1] + 6, main[2] - 12, 900 - main[1] - 12), "#ffffff", 3, dashed=True)
    outline(d, b["rail"][0], "#ffb000")
    outline(d, b["status"][0], "#22d3ee")
    outline(d, b["hero"][0], "#ff5fa8")
    for panel in b["panel"][:2]:
        outline(d, panel, "#8be04e")
    tag(d, (12, 400), "RAIL  rail.surface · rail.art", "#ffb000")
    tag(d, (560, 8), "STATUS BAR  status.backdrop", "#22d3ee")
    tag(d, (b["hero"][0][0] + 580, b["hero"][0][1] + 12), "HOME HERO  home.hero.backdrop", "#ff5fa8")
    for panel in b["panel"][:2]:
        tag(d, (panel[0] + panel[2] - 330, panel[1] + panel[3] - 44), "PANEL  panel.surface (9-slice)", "#8be04e")
    tag(d, (1040, 860), "PAGE  page.backdrop + scrim", "#ffffff")
    p = boxes["phone"]
    d = ImageDraw.Draw(phone)
    outline(d, p["status"][0], "#22d3ee")
    outline(d, p["header"][0], "#ff5fa8")
    outline(d, p["now"][0], "#ff8a3d")
    outline(d, p["dock"][0], "#b794ff")
    tag(d, (150, 78), "HEADER  header.banner", "#ff5fa8", 16)
    tag(d, (100, p["now"][0][1] - 34), "NOW BAR  nowbar.surface", "#ff8a3d", 16)
    tag(d, (130, p["dock"][0][1] - 34), "DOCK  dock.surface", "#b794ff", 16)
    tag(d, (150, 420), "PAGE", "#ffffff", 16)
    canvas = Image.new("RGB", (1440 + 48 + 390 + 48, 900 + 96), "#15151a")
    canvas.paste(desk, (24, 72))
    canvas.paste(phone, (1440 + 72, 72 + 28))
    c = ImageDraw.Draw(canvas)
    c.text((24, 20), "Desktop · Home (from 900 px: rail, status bar)", font=font(26), fill="#f2f2f2")
    c.text((1440 + 72, 20), "Phone · a room", font=font(26), fill="#f2f2f2")
    save(fit(canvas, 1600), "parts-map")


def strips(shots: Path) -> None:
    variants = ("plain", "banner", "framed")
    images = [Image.open(shots / f"header-{v}.png") for v in variants]
    canvas = Image.new("RGB", (images[0].width, sum(i.height for i in images) + 6 * (len(images) - 1)), "#15151a")
    y = 0
    for variant, image in zip(variants, images):
        canvas.paste(image, (0, y))
        tag(ImageDraw.Draw(canvas), (canvas.width - 300, y + 14), f"header: {variant}", "#ffd84d", 20)
        y += image.height + 6
    save(canvas, "header-variants")
    panels = [Image.open(shots / f"panel-{v}.png") for v in ("card", "flat", "outlined")]
    w = panels[0].width
    canvas = Image.new("RGB", (w * 3 + 24 * 2, panels[0].height + 56), "#15151a")
    for n, (variant, image) in enumerate(zip(("card", "flat", "outlined"), panels)):
        canvas.paste(image, (n * (w + 24), 56))
        tag(ImageDraw.Draw(canvas), (n * (w + 24), 10), f"panel: {variant}", "#ffd84d", 22)
    save(fit(canvas, 1500), "panel-variants")


def screens(shots: Path) -> None:
    for name, note, colour in (
        ("art-do", "DO  framed title · plaques · gallery ground · scrim · panel edges", "#8be04e"),
        ("art-dont", "DON'T  bare page pieces straight on the picture", "#ff6b6b"),
    ):
        image = Image.open(shots / f"{name}.png")
        tag(ImageDraw.Draw(image), (560, 848), note, colour, 22)
        save(fit(image, 1200), name)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    shots = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    parts_map(shots)
    strips(shots)
    screens(shots)
    total = sum(p.stat().st_size for p in OUT.glob("*.webp"))
    print(f"{len(list(OUT.glob('*.webp')))} pictures, {total // 1024} KB in themes/_kit/visuals/")
