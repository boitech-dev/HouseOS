"""Look at the pieces: every grid at 8× on the theme's grounds (python3 preview.py out.png [prefix])."""
import sys
from PIL import Image, ImageDraw
from pal import LEGEND, P3, CREAM, LAV3, LCD3
import sprites_src as S

def draw(grid, z):
    h, w = len(grid), max(map(len, grid))
    im = Image.new("RGBA", (w * z, h * z))
    d = ImageDraw.Draw(im)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch not in ". ":
                d.rectangle([x * z, y * z, x * z + z - 1, y * z + z - 1], fill=LEGEND[ch])
    return im

def sheet(items, out, z=8):
    cell = 16 * z + 16
    cols = 6
    rows = (len(items) + cols - 1) // cols
    grounds = [CREAM, P3, LAV3]
    im = Image.new("RGB", (cols * cell * 1 + 8, rows * (cell + 60) + 8), (60, 50, 70))
    d = ImageDraw.Draw(im)
    for n, (name, grid) in enumerate(items):
        x, y = 8 + (n % cols) * cell, 8 + (n // cols) * (cell + 60)
        g = grounds[n % 3]
        d.rectangle([x, y, x + cell - 16, y + cell - 16], fill=g)
        sp = draw(grid, z)
        im.paste(sp, (x + (16 * z - sp.width) // 2, y + (16 * z - sp.height) // 2), sp)
        small = draw(grid, 2)
        d.rectangle([x, y + cell - 12, x + 40, y + cell + 30], fill=g)
        im.paste(small, (x + 4, y + cell - 8), small)
        d.text((x + 48, y + cell), name, fill=(240, 240, 240))
    im.save(out)

if __name__ == "__main__":
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""
    items = [(k, v) for k, v in S.ALL.items() if k.startswith(prefix)]
    sheet(items, sys.argv[1])
