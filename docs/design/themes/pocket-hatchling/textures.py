"""The two SVG tiles (python3 textures.py): glitter in the candy plastic, and the LCD's ghost grid."""
import random
from pal import WHITE, P0, LEM2, LCD0, MINT1
from util import ART

def glitter():
    rnd = random.Random(11)
    flecks = []
    for _ in range(9):
        x, y = rnd.randrange(0, 32), rnd.randrange(0, 32)
        colour, op = rnd.choice([(WHITE, 0.75), (WHITE, 0.55), (P0, 0.18), (LEM2, 0.6)])
        size = rnd.choice([1, 1, 2])
        flecks.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" fill="{colour}" fill-opacity="{op}"/>')
    # one four-point sparkle per tile
    flecks.append(f'<path d="M22 5h1v2h2v1h-2v2h-1v-2h-2v-1h2z" fill="{WHITE}" fill-opacity="0.8"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" '
            'shape-rendering="crispEdges">' + "".join(flecks) + "</svg>")

def lcd():
    # 3 px pixels with a 1 px gap: the unlit segments' ghost
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4" viewBox="0 0 4 4" '
            f'shape-rendering="crispEdges"><path d="M0 3h4v1H0zM3 0h1v3H3z" fill="{LCD0}" fill-opacity="0.07"/></svg>')

def dots():
    # the sticker sheet's printed grid, for the rail
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" '
            f'shape-rendering="crispEdges"><rect x="7" y="7" width="2" height="2" fill="{MINT1}" fill-opacity="0.45"/></svg>')

if __name__ == "__main__":
    ART.mkdir(exist_ok=True)
    (ART / "glitter.svg").write_text(glitter())
    (ART / "lcd.svg").write_text(lcd())
    (ART / "dots.svg").write_text(dots())
    print("glitter.svg, lcd.svg")
