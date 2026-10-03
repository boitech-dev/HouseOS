"""The castle's palette: SNES 15-bit honest (every channel a multiple of 8), five ramps and a candle.
One light: the moon, high and to the right (cold rim light on the right/top edges); candles and
torches are the only warm light, low and local. Shadows fall down-left and turn violet."""

# Night: the sky and the ground, violet to black.
NIGHT = ["#080010", "#100818", "#181028", "#201038", "#301848", "#402058", "#582868"]
# Dusk glow along the horizon, behind the castle: violet into wine into ember.
DUSK = ["#482050", "#602048", "#782040", "#902838", "#a83830"]
# Stone: blue-grey, violet in the shadows, a little warm in the light (hue-shifted).
STONE = ["#080810", "#101020", "#181830", "#202838", "#303848", "#404858", "#586070", "#707888", "#9098a0", "#b8b8b0"]
# Moss on old stone.
MOSS = ["#182018", "#283820", "#405028", "#587030"]
# Crimson: blood, velvet, the accent.
CRIMSON = ["#280008", "#480010", "#700818", "#981020", "#c02030", "#e04040", "#f87860"]
# Gold, tarnished: ornament.
GOLD = ["#281808", "#503010", "#805020", "#a87828", "#d0a040", "#f0d070", "#f8f0b0"]
# Bone: the ink.
BONE = ["#686050", "#908870", "#b8b098", "#d8d0b8", "#f0e8d0", "#f8f8e8"]
# Candlelight.
FLAME = ["#782008", "#c04810", "#f08820", "#f8c040", "#f8e880", "#f8f8d8"]
# Moonlight and the stained glass's cold panes.
MOON = ["#586078", "#8890a8", "#b8c0d0", "#d8d8e0", "#f0f0e8"]
GLASS = ["#102060", "#2040a0", "#3868d0", "#58a0e8", "#207048", "#38a860", "#602898", "#9048c8", "#101838"]

ALL = NIGHT + DUSK + STONE + MOSS + CRIMSON + GOLD + BONE + FLAME + MOON + GLASS


def check():
    for c in ALL:
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        assert r % 8 == 0 and g % 8 == 0 and b % 8 == 0, c


check()
