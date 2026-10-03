"""Theme packs → resolved tokens. A pack is data only: `theme.json` (the manifest), `tokens.json`
(DTCG design tokens, only what differs from base) and optional `tokens.<scheme>.json` per scheme.

Resolution for one theme and scheme: base tokens → base scheme tokens → theme tokens → theme scheme
tokens; then a 12-step ramp per seed (`ramp.<seed>.1..12`); then `{references}` and the three
functions `mix(a, b, 40%)`, `alpha(a, 40%)`, `contrast(bg)` (the more legible end of the neutral
ramp on `bg`). Every value comes out final (colours as hex), so each theme's CSS is complete on its
own and a `data-theme` preview inside another theme shows exactly that theme.
"""

import json
import re
import shutil
from pathlib import Path

from . import color

ROOT = Path(__file__).resolve().parents[3] / "themes"


def copy_tree(src: Path, dst: Path, skip: tuple[str, ...] = ()) -> None:
    """Copy a theme folder's files but not their modes or ACLs: the house's service may not set
    a setgid bit (systemd RestrictSUIDSGID), and the target folder's own defaults should apply.
    `skip` names top-level entries to leave out."""
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):  # parents sort before their children
        relative = path.relative_to(src)
        if relative.parts[0] in skip:
            continue
        if path.is_dir():
            (dst / relative).mkdir(exist_ok=True)
        else:
            shutil.copyfile(path, dst / relative)


SCHEMES = ("dark", "light")
# A word for the brief only (older packs carry it): spacing is part of the size contract.
DENSITY = {"compact", "comfortable", "airy"}
# CSS custom property prefix per top-level group; seeds and ramps are inputs only (not emitted:
# components use meanings, never raw steps).
PREFIX = {
    "color": "c",
    "font": "font",
    "text": "text",
    "space": "space",
    "radius": "radius",
    "border": "border",
    "shape": "shape",
    "elev": "elev",
    "material": "mat",
    "part": "part",
    "dur": "dur",
    "ease": "ease",
    "motion": "motion",
    "icon": "icon",
    "z": "z",
    "chrome": "chrome",
    "bp": "bp",
}
INPUTS = {"seed", "ramp"}
# The contract: a theme changes how things look, never how big they are, so every theme fits the
# same screens. Fixed groups and tokens: z order, breakpoints, spacing, borders, chrome heights and
# icon boxes. Text may be tuned for a face's own proportions, inside TEXT_BAND (see check.type_band).
FIXED = {"z", "bp", "space", "border", "chrome"}
FIXED_TOKENS = {"icon.s", "icon.m", "icon.l"}
# Text inside components (buttons, rows, labels): at most 1px larger than Base, its line within 2px of
# Base's. Buttons, tabs and chips (action) keep Base's case and at most +0.02em of tracking; labels
# and captions 0.1em at most. Display styles (page titles) at most 10 % larger. The brand sits in
# fixed chrome: its line stays under 32px.
TEXT_BAND = {"px": 1, "line": 2, "display": 1.10, "brand_line": 32, "action_track": 0.02, "small_track": 0.1}
ROOMS = ("home", "listen", "watch", "house", "files", "ask", "me", "control")  # the places, distinct
# Rooms reached from those (Base lends them a neighbour's light; a theme may give each its own).
ALL_ROOMS = ROOMS + ("smart-home", "inbox", "space", "party", "games")

# Lightness per ramp step, and the share of the seed's chroma, per scheme. Step 9 is the seed.
STEPS = {
    "dark": (
        (0.17, 0.20, 0.235, 0.265, 0.295, 0.335, 0.41, 0.535, None, None, 0.83, 0.95),
        (0.15, 0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 1, 1, 0.7, 0.25),
    ),
    "light": (
        (0.99, 0.975, 0.955, 0.93, 0.905, 0.875, 0.80, 0.62, None, None, 0.47, 0.24),
        (0.08, 0.12, 0.25, 0.3, 0.35, 0.4, 0.5, 0.7, 1, 1, 0.85, 0.5),
    ),
}

REF = re.compile(r"\{([a-z0-9-]+(?:\.[a-z0-9-]+)+)\}")
FUNC = re.compile(r"\b(mix|alpha|contrast)\(")


class ThemeError(ValueError):
    """A pack that cannot be built; the message says exactly what and where."""


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except ValueError as error:
        raise ThemeError(f"{path.name}: not valid JSON ({error})") from None


def flatten(tree: dict, prefix=(), inherited=None) -> dict[str, dict]:
    """DTCG groups → {"color.bg.canvas": {"value":…, "type":…, "description":…}}."""
    out = {}
    kind = tree.get("$type", inherited)
    for key, node in tree.items():
        if key.startswith("$"):
            continue
        if not isinstance(node, dict):
            raise ThemeError(
                f"{'.'.join((*prefix, key))}: a token is an object with $value, "
                'e.g. {"seed": {"neutral": {"$value": "oklch(0.5 0.02 80)"}}}'
            )
        path = (*prefix, key)
        if "$value" in node:
            out[".".join(path)] = {
                "value": node["$value"],
                "type": node.get("$type", kind),
                "description": node.get("$description", ""),
            }
        else:
            out |= flatten(node, path, kind)
    return out


def ramp(seed: str, scheme: str) -> list[str]:
    lightness, chroma, hue = color.to_oklch(color.parse(seed))
    levels, shares = STEPS[scheme]
    out = []
    for step, (level, share) in enumerate(zip(levels, shares), 1):
        if step == 9:
            level = lightness
        elif step == 10:  # hover: a touch towards more contrast with the ground
            level = min(0.97, lightness + 0.05) if scheme == "dark" else max(0.05, lightness - 0.05)
        out.append(color.to_hex((*color.oklch_to_srgb(level, chroma * share, hue), 1.0)))
    return out


class Theme:
    def __init__(self, folder: Path):
        self.folder, self.id = folder, folder.name
        self.manifest = read(folder / "theme.json")
        if not self.manifest:
            raise ThemeError(f"{folder.name}: theme.json is missing")

    @property
    def schemes(self) -> list[str]:
        return list(self.manifest.get("schemes") or ["dark"])

    def layers(self, scheme: str) -> list[dict]:
        return [
            flatten(read(self.folder / "tokens.json")),
            flatten(read(self.folder / f"tokens.{scheme}.json")),
        ]


def load(theme_id: str, root: Path | None = None) -> Theme:
    root = root or ROOT
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", theme_id or ""):
        raise ThemeError("A theme id is lowercase words joined by hyphens, like linen-morning")
    folder = root / theme_id
    if not folder.is_dir():
        raise ThemeError(f"No theme {theme_id!r} in {root}")
    return Theme(folder)


def merged(theme: Theme, scheme: str, base: Theme) -> dict[str, dict]:
    tokens: dict[str, dict] = {}
    for layer in (*base.layers(scheme), *(theme.layers(scheme) if theme.id != base.id else [])):
        for name, token in layer.items():
            known = tokens.get(name)
            if known is None and theme.id != base.id and name.split(".")[0] not in INPUTS:
                if not any(name in b for b in base.layers(scheme)):
                    raise ThemeError(f"Unknown token {name!r} (see `theme_kit tokens` for the catalogue)")
            if known and theme.id != base.id and token.get("type") and token["type"] != known.get("type"):
                raise ThemeError(f"{name}: its type is {known.get('type')!r}; a theme can't change it")
            tokens[name] = {**(known or {}), **{k: v for k, v in token.items() if v not in ("", None)}}
    for name, token in list(tokens.items()):
        if name.startswith("seed."):
            for step, value in enumerate(ramp(str(token["value"]), scheme), 1):
                tokens[f"ramp.{name[5:]}.{step}"] = {"value": value, "type": "color", "description": ""}
    return tokens


def resolve(tokens: dict[str, dict]) -> dict[str, object]:
    done: dict[str, object] = {}

    def value_of(name, trail=()):
        if name in done:
            return done[name]
        if name in trail:
            raise ThemeError("Reference loop: " + " → ".join((*trail, name)))
        if name not in tokens:
            raise ThemeError(f"{trail[-1] if trail else name}: refers to unknown token {{{name}}}")
        raw = tokens[name]["value"]
        done[name] = evaluate(raw, (*trail, name))
        return done[name]

    def evaluate(raw, trail):
        if isinstance(raw, dict):
            return {key: evaluate(item, trail) for key, item in raw.items()}
        if not isinstance(raw, str):
            return raw
        whole = REF.fullmatch(raw)
        if whole:
            return value_of(whole[1], trail)
        text = REF.sub(lambda m: str(value_of(m[1], trail)), raw)
        try:
            return functions(text, lambda name, args: function(name, args, tokens, value_of, trail))
        except ThemeError as error:
            # Name the tokens it was made from: the typo is usually there, not here.
            used = ", ".join("{" + ref + "}" for ref in REF.findall(raw))
            raise ThemeError(f"{error} (made from {used})" if used else str(error)) from None

    for name in tokens:
        value_of(name)
    return done


def functions(text: str, call) -> str:
    """Evaluate mix()/alpha()/contrast() wherever they are in a value, innermost first."""
    while m := FUNC.search(text):
        depth, end = 0, None
        for i in range(m.end() - 1, len(text)):
            depth += (text[i] == "(") - (text[i] == ")")
            if depth == 0:
                end = i
                break
        if end is None:
            raise ThemeError(f"Unclosed {m[1]}( in {text!r}")
        inner = functions(text[m.end() : end], call)
        text = text[: m.start()] + call(m[1], [part.strip() for part in split(inner)]) + text[end + 1 :]
    return text


def split(args: str) -> list[str]:
    """Commas at the top level only (colours like oklch(…) stay whole)."""
    parts, depth, current = [], 0, ""
    for char in args:
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return [*parts, current]


def function(name, args, tokens, value_of, trail):
    def share(text):
        if not re.fullmatch(r"\d+(\.\d+)?%", text):
            raise ThemeError(f"{trail[-1]}: {name}() needs a percentage, got {text!r}")
        return float(text[:-1]) / 100

    try:
        if name == "mix" and len(args) == 3:
            return color.to_hex(color.mix(color.parse(args[0]), color.parse(args[1]), share(args[2])))
        if name == "alpha" and len(args) == 2:
            c = color.parse(args[0])
            return color.to_hex((*c[:3], c[3] * share(args[1])))
        if name == "contrast" and len(args) == 1:
            back = color.parse(args[0])
            ends = [value_of("ramp.neutral.1", trail), value_of("ramp.neutral.12", trail)]
            return max(ends, key=lambda c: color.contrast(color.parse(c), back))
    except ValueError as error:
        raise ThemeError(f"{trail[-1]}: {error}") from None
    raise ThemeError(
        f"{trail[-1]}: {name}() takes {'3' if name == 'mix' else '2' if name == 'alpha' else '1'} values"
    )


def css_name(path: str) -> str | None:
    head, *rest = path.split(".")
    if head in INPUTS:
        return None
    prefix = PREFIX.get(head)
    if prefix is None:
        raise ThemeError(f"{path}: unknown token group {head!r}")
    return "--" + "-".join([prefix, *rest])


# What a value may contain once it's CSS: it must stay inside its own declaration. No
# statement or block breaks, no quotes, comments, escapes, at-rules, and no image but the theme's
# own art (url(art/<file>)); a font family is plain words.
UNSAFE = re.compile(r"[;{}<>\\@\"'`]|/\*|\*/|!important", re.I)
FUNCTIONS = re.compile(r"([a-z-]+)\(", re.I)
# Functions that fetch or inject something; every other CSS function only computes a value.
LOADING = {
    "image-set",
    "-webkit-image-set",
    "image",
    "element",
    "cross-fade",
    "expression",
    "paint",
    "attr",
    "src",
}
ART_URL = re.compile(r"url\(art/[a-z0-9][a-z0-9._-]{0,60}\.(svg|png|webp)\)", re.I)
FAMILY = re.compile(r"[A-Za-z0-9-][A-Za-z0-9 -]{0,59}")
CASES = {"none", "uppercase", "lowercase", "capitalize"}


def safe(text: str, path: str) -> str:
    """A final CSS value, or ThemeError if it could escape its declaration."""
    if UNSAFE.search(text):
        raise ThemeError(f"{path}: {text!r} holds characters a value may not contain")
    for name in FUNCTIONS.findall(text):
        if name.lower() in LOADING:
            raise ThemeError(f"{path}: {name}() is not allowed in a theme value")
    for found in re.finditer(r"url\(", text, re.I):
        if not ART_URL.match(text, found.start()):
            raise ThemeError(f"{path}: an image is url(art/<file>) from the theme's own art/")
    return text


def family_list(value) -> str:
    families = value if isinstance(value, list) else [value]
    for family in families:
        if not isinstance(family, str) or not FAMILY.fullmatch(family):
            raise ThemeError(f"{family!r}: a font family is plain words (letters, digits, spaces, hyphens)")
    return ", ".join(f'"{f}"' if " " in f else f for f in families)


def css_value(value, kind: str | None, path="") -> str:
    if kind == "fontFamily":
        return family_list(value)
    return safe(raw_value(value, kind), path)


def raw_value(value, kind) -> str:
    if kind == "color":
        return color.to_hex(color.parse(str(value)))
    if kind == "dimension" and isinstance(value, (int, float)):
        return f"{round(value, 2):g}px"
    if kind == "duration" and isinstance(value, (int, float)):
        return f"{value:g}ms"
    if kind == "cubicBezier" and isinstance(value, list):
        return "cubic-bezier(" + ", ".join(f"{v:g}" for v in value) + ")"
    return str(value)


def text_style(value: dict) -> dict[str, str]:
    """A composite text style → the `font` shorthand, tracking and case."""
    family = family_list(value["fontFamily"])
    weight, size, height, tracking = (
        value.get("fontWeight", 400), value["fontSize"], value.get("lineHeight", 1.4), value.get("letterSpacing", 0),
    )  # fmt: skip
    if not all(
        isinstance(n, (int, float)) and not isinstance(n, bool) for n in (weight, size, height, tracking)
    ):
        raise ThemeError("a text style's weight, size, line height and letter spacing are numbers")
    case = str(value.get("textTransform", "none"))
    if case not in CASES:
        raise ThemeError(f"textTransform is one of {', '.join(sorted(CASES))}")
    return {"": f"{weight:g} {size:g}px/{height:g} {family}", "-tracking": f"{tracking:g}em", "-case": case}


def variables(theme: Theme, scheme: str, base: Theme) -> dict[str, str]:
    """{"--c-bg-canvas": "#0e1020", …}: every token of this theme and scheme, final."""
    tokens = merged(theme, scheme, base)
    values = resolve(tokens)
    out = {}
    for path, value in values.items():
        name = css_name(path)
        if name is None:
            continue
        kind = tokens[path]["type"]
        try:
            if kind == "typography":
                for suffix, text in text_style(value).items():
                    out[name + suffix] = text
            else:
                out[name] = css_value(value, kind, path)
        except ThemeError as error:
            raise ThemeError(str(error) if str(error).startswith(path) else f"{path}: {error}") from None
        except (ValueError, TypeError, KeyError, AttributeError) as error:  # a typo: say where
            raise ThemeError(f"{path}: {value!r} is not a valid {kind} ({error})") from None
    return out


def room_variables(values: dict[str, str]) -> dict[str, dict[str, str]]:
    """Per room: its light, the text that sits on it, and a soft fill and line made from it."""
    out = {}
    for room in ALL_ROOMS:
        light = color.parse(values[f"--c-room-{room}"])
        on = max(
            (values["--c-fg-default"], values["--c-fg-inverse"]),
            key=lambda c: color.contrast(color.parse(c), light),
        )
        out[room] = {
            "--c-room": values[f"--c-room-{room}"],
            "--c-room-fg": on,
            "--c-room-soft": color.to_hex(color.mix(light, (0, 0, 0, 0), 0.16)),
            "--c-room-line": color.to_hex(color.mix(light, color.parse(values["--c-border-default"]), 0.38)),
        }
    return out


def catalogue(base: Theme) -> list[dict]:
    """The authoring reference: every token, what it is for and its Base value."""
    rows = []
    tokens = merged(base, base.schemes[0], base)
    for path, token in tokens.items():
        name = css_name(path)
        if name is None and not path.startswith("seed."):
            continue
        group = path.split(".")[0]
        rows.append(
            {
                "token": path,
                "css": name or "(input: makes ramp." + path[5:] + ".1–12)",
                "type": token.get("type"),
                "description": token.get("description", ""),
                "themeable": "no"
                if group in FIXED or path in FIXED_TOKENS
                else "within the text band"
                if group == "text"
                else "yes",
                "base": json.dumps(token["value"])
                if isinstance(token["value"], (dict, list))
                else str(token["value"]),
            }
        )
    return rows
