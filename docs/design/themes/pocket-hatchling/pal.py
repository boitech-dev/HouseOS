"""Pocket Hatchling's one palette: candy plastic, plum ink, the LCD, one berry accent.
Every picture and every token comes from here (make.py locks each picture to it)."""

INK = "#2b1638"      # the outline and the text: plum, never black
INK2 = "#4e2c63"
INK3 = "#7b5a91"
# bubblegum (shadows toward berry-violet, lights toward peach)
P0, P1, P2, P3, P4 = "#b03a78", "#e56aa3", "#f79bc5", "#fcc7de", "#ffe6f1"
BERRY, BERRY_DEEP = "#bd1860", "#8a0f45"   # the one accent: primary actions
MINT0, MINT1, MINT2, MINT3 = "#2d8c79", "#5ccaa9", "#a2e8cf", "#dcf8ec"
LAV0, LAV1, LAV2, LAV3, LAV4 = "#6653ad", "#9a86e0", "#c6b7f4", "#e5dcfc", "#f2edfe"
LEM0, LEM1, LEM2, LEM3 = "#c4880f", "#f4c93c", "#fde37d", "#fff5c6"
BLU0, BLU1, BLU2, BLU3 = "#3c74b8", "#76b0ea", "#afd5f8", "#ddeefe"
# the LCD: reflective grey-green, dark segment ink, the ghost of unlit pixels
LCD0, LCD1, LCD2, LCD3, LCD4 = "#27311f", "#4b5a3b", "#8c9b71", "#b3c192", "#cbd6ad"
WHITE, CREAM, SHELL = "#ffffff", "#fff9f0", "#fff1dc"
CORAL = "#f0605d"
CANVAS, CANVAS2, SURFACE = "#efe8fd", "#ebe2fc", "#fffaf4"   # the page and the cards

ALL = [INK, INK2, INK3, P0, P1, P2, P3, P4, BERRY, BERRY_DEEP, MINT0, MINT1, MINT2, MINT3,
       LAV0, LAV1, LAV2, LAV3, LAV4, LEM0, LEM1, LEM2, LEM3, BLU0, BLU1, BLU2, BLU3,
       LCD0, LCD1, LCD2, LCD3, LCD4, WHITE, CREAM, SHELL, CORAL, CANVAS, CANVAS2, SURFACE]

# sprites.json letters → color.sprite.* tokens → these colours (tokens.json says the same)
SPRITE = {
    "k": ("outline", INK), "n": ("dark", LAV0), "l": ("mid-dark", P1), "L": ("mid", P2),
    "m": ("mist", LAV2), "c": ("light", INK3), "C": ("light-dim", P3), "e": ("accent", BERRY),
    "E": ("accent-hi", MINT2), "r": ("accent-deep", MINT0), "v": ("familiar", LEM2),
    "V": ("familiar-mid", LEM1), "w": ("familiar-deep", LEM0), "g": ("good", MINT1),
    "p": ("alert", CORAL), "P": ("paper", WHITE), "i": ("ink", BLU1),
}
LEGEND = {k: v[1] for k, v in SPRITE.items()}
