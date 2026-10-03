"""Colour maths for themes, standard library only: OKLCH ⇄ sRGB, mixing, WCAG contrast (the gate),
APCA (advice), OKLab distance and a colour-vision simulation."""

import math
import re

RGBA = tuple[float, float, float, float]  # sRGB 0–1, alpha 0–1

_HEX = re.compile(r"#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
_OKLCH = re.compile(r"oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*(?:/\s*([\d.]+)(%?))?\s*\)")


def parse(text: str) -> RGBA:
    """`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`, `oklch(L C H [/ A])` or `transparent`."""
    text = text.strip()
    if text == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if m := _HEX.fullmatch(text):
        h = m[1]
        if len(h) <= 4:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        return tuple(int(h[i : i + 2], 16) / 255 for i in range(0, 8, 2))  # type: ignore[return-value]
    if m := _OKLCH.fullmatch(text):
        lightness = float(m[1]) / (100 if m[2] else 1)
        alpha = 1.0 if m[5] is None else float(m[5]) / (100 if m[6] else 1)
        return (*oklch_to_srgb(lightness, float(m[3]), float(m[4])), alpha)
    raise ValueError(f"not a colour: {text!r}")


def is_colour(text: str) -> bool:
    try:
        parse(text)
        return True
    except ValueError:
        return False


def to_hex(c: RGBA) -> str:
    r, g, b, a = (round(max(0.0, min(1.0, v)) * 255) for v in c)
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _gam(v):
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def srgb_to_oklab(c: RGBA):
    r, g, b = (_lin(v) for v in c[:3])
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_linear(lightness, a, b):
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )


def oklch_to_srgb(lightness: float, chroma: float, hue: float):
    """In gamut by lowering chroma (keeps lightness and hue, as CSS gamut mapping does)."""
    lightness, h = max(0.0, min(1.0, lightness)), math.radians(hue)

    def linear(c):
        return _oklab_to_linear(lightness, c * math.cos(h), c * math.sin(h))

    def inside(rgb):
        return all(-1e-3 <= v <= 1 + 1e-3 for v in rgb)

    if not inside(linear(chroma)):
        low, high = 0.0, chroma  # the most chroma that still fits
        for _ in range(24):
            middle = (low + high) / 2
            low, high = (middle, high) if inside(linear(middle)) else (low, middle)
        chroma = low
    return tuple(_gam(max(0.0, min(1.0, v))) for v in linear(chroma))


def to_oklch(c: RGBA):
    lightness, a, b = srgb_to_oklab(c)
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def mix(a: RGBA, b: RGBA, amount: float) -> RGBA:
    """`color-mix(in srgb, a amount, b)`: premultiplied, as browsers do."""
    wa, wb = amount * a[3], (1 - amount) * b[3]
    alpha = wa + wb
    if alpha == 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (*((x * wa + y * wb) / alpha for x, y in zip(a[:3], b[:3])), alpha)


def over(top: RGBA, bottom: RGBA) -> RGBA:
    """`top` painted on an opaque `bottom`."""
    t = top[3]
    return (*(x * t + y * (1 - t) for x, y in zip(top[:3], bottom[:3])), 1.0)


def luminance(c: RGBA) -> float:
    r, g, b = (_lin(v) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: RGBA, bg: RGBA) -> float:
    """WCAG 2.x ratio; a translucent colour counts as painted on what is behind it."""
    fg = over(fg, bg) if fg[3] < 1 else fg
    high, low = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def apca(fg: RGBA, bg: RGBA) -> float:
    """APCA-W3 0.0.98G Lc (advice only; WCAG 2 is the gate)."""
    fg = over(fg, bg) if fg[3] < 1 else fg

    def y(c):
        r, g, b = (v**2.4 for v in c[:3])
        v = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
        return v if v > 0.022 else v + (0.022 - v) ** 1.414

    text, back = y(fg), y(bg)
    if abs(back - text) < 0.0005:
        return 0.0
    if back > text:
        lc = (back**0.56 - text**0.57) * 1.14
        return 0.0 if lc < 0.1 else (lc - 0.027) * 100
    lc = (back**0.65 - text**0.62) * 1.14
    return 0.0 if lc > -0.1 else (lc + 0.027) * 100


def distance(a: RGBA, b: RGBA) -> float:
    """OKLab ΔE (0–1 scale; 0.02 is just noticeable)."""
    return math.dist(srgb_to_oklab(a), srgb_to_oklab(b))


# Machado et al. 2009, deuteranopia at full severity, in linear RGB.
_DEUTAN = ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881))


def deutan(c: RGBA) -> RGBA:
    rgb = [_lin(v) for v in c[:3]]
    out = [sum(m * v for m, v in zip(row, rgb)) for row in _DEUTAN]
    return (*(_gam(max(0.0, min(1.0, v))) for v in out), c[3])


def self_check():
    assert to_hex(parse("#abc")) == "#aabbcc" and to_hex(parse("#11223380")) == "#11223380"
    assert round(contrast(parse("#000"), parse("#fff")), 2) == 21.0
    assert to_hex(parse("oklch(1 0 0)")) == "#ffffff" and to_hex(parse("oklch(0 0 0)")) == "#000000"
    red = parse("oklch(0.628 0.2577 29.23)")
    assert distance(red, parse("#ff0000")) < 0.01, to_hex(red)
    assert to_hex(mix(parse("#ffffff"), parse("#000000"), 0.5)) == "#808080"
    assert round(apca(parse("#000"), parse("#fff"))) == 106


if __name__ == "__main__":
    self_check()
    print("color: ok")
