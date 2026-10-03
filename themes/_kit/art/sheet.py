"""A contact sheet of a theme's art, to look at before building: every picture at its own size
and zoomed (pixel art nearest-neighbour), with its name and size.

    python3 themes/_kit/art/sheet.py themes/<id>/art  /tmp/<id>-art.png
Then open the PNG (an agent: read it as an image) and judge it at 1× and zoomed."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

CELL, PAD = 320, 12


def contact(folder, out) -> Path:
    files = sorted(p for p in Path(folder).iterdir() if p.suffix in (".png", ".webp"))
    cols = 3
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (CELL + PAD) + PAD, rows * (CELL + 44) + PAD), (40, 40, 44))
    draw = ImageDraw.Draw(sheet)
    for n, path in enumerate(files):
        image = Image.open(path).convert("RGBA")
        x, y = PAD + (n % cols) * (CELL + PAD), PAD + (n // cols) * (CELL + 44)
        fit = min(CELL / image.width, (CELL - 20) / image.height)
        zoom = max(1, int(fit)) if fit >= 1 else fit
        shown = image.resize((max(1, int(image.width * zoom)), max(1, int(image.height * zoom))),
                             Image.NEAREST if zoom >= 1 else Image.LANCZOS)  # fmt: skip
        checker = Image.new("RGB", shown.size, (90, 90, 96))
        sheet.paste(checker, (x, y))
        sheet.paste(shown, (x, y), shown)
        draw.text((x, y + shown.height + 4), f"{path.name}  {image.width}×{image.height}  ×{zoom:.2g}", fill=(230, 230, 230))
    out = Path(out)
    sheet.save(out)
    return out


if __name__ == "__main__":
    print(contact(sys.argv[1], sys.argv[2]))
