"""A contact sheet of Pure's pieces in both schemes: python3 docs/design/themes/pure/sprite_sheet.py OUT.png"""
import json, sys
from PIL import Image, ImageDraw
d = json.load(open("themes/pure/sprites.json"))
S = {"dark": {"c": "#f3f1eb", "C": "#b9b5aa", "l": "#57554f", "n": "#1c1c1b", "k": "#000000", "bg": "#000000"},
     "light": {"c": "#12110f", "C": "#4f4b44", "l": "#8f887b", "n": "#d9d2c3", "k": "#eee8db", "bg": "#eee8db"}}
names = list(d["glyphs"])
z, cell, cols = 4, 76, 12
rows = (len(names) + cols - 1) // cols
img = Image.new("RGB", (cols * cell, rows * cell * 2), "#777")
for si, (scheme, pal) in enumerate(S.items()):
    for n, name in enumerate(names):
        x0, y0 = (n % cols) * cell, (si * rows + n // cols) * cell
        dr = ImageDraw.Draw(img)
        dr.rectangle([x0 + 1, y0 + 1, x0 + cell - 2, y0 + cell - 2], fill=pal["bg"])
        for y, r in enumerate(d["glyphs"][name]):
            for x, ch in enumerate(r):
                if ch != ".":
                    dr.rectangle([x0 + 6 + x * z, y0 + 6 + y * z, x0 + 5 + (x + 1) * z, y0 + 5 + (y + 1) * z], fill=pal[ch])
img.save(sys.argv[1])
