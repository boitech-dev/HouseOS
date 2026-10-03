"""Every check a theme must pass, all code (no model looks at anything). `check(id)` returns the
results; `report(results)` is the REPORT.md a theme folder carries.

What is checked and why is the contract in docs/design/SYSTEM.md and themes/README.md."""

import itertools
import re
from pathlib import Path

from . import color, tokens as t

TEXT, UI = 4.5, 3.0
BUNDLED_FONTS = {"Jacquard 12", "Alegreya Sans", "IBM Plex Mono", "system"}
ART_TYPES = {".svg", ".png", ".webp"}
ART_MAX, PACK_MAX, FONTS_MAX = 200_000, 2_000_000, 800_000
# A theme's words are only its names for the house titles: every other sentence is HouseOS's own,
# practical (what's here, what to do); a theme's look is pictures and shapes, not text.
SLOT_KINDS = {"name": 28, "mark": 3}  # longest text per kind
SLOT = re.compile(r"^(title\.[a-z_]+\.name|title\.star\.mark)$")
SPRITE_MAX = 16  # a redrawn piece fits the box of the one it replaces
UNSAFE_SVG = re.compile(r"<script|<foreignObject|<!ENTITY|\bon[a-z]+\s*=|javascript:|"
                        r"(?:href|src)\s*=\s*[\"']?\s*(?:https?:|//|data:)|url\(\s*[\"']?\s*(?:https?:|//)", re.I)  # fmt: skip
GROUNDS = ("canvas", "surface", "raised", "overlay", "sunken")
STATUS = ("success", "warning", "danger", "info")


class Results(list):
    def add(self, check, ok, detail="", warn=False):
        self.append((check, "pass" if ok else "warn" if warn else "fail", detail))

    @property
    def failed(self):
        return [r for r in self if r[1] == "fail"]


def manifest(theme: t.Theme, out: Results):
    m = theme.manifest
    problems = []
    if m.get("id") != theme.id:
        problems.append(f"id must be {theme.id!r} (the folder name)")
    for key in ("schema", "version"):
        if not isinstance(m.get(key), int) or m[key] < 1:
            problems.append(f"{key} must be a whole number from 1")
    for key in ("names", "description"):
        if not all(
            isinstance((m.get(key) or {}).get(lang), str) and m[key][lang].strip() for lang in ("en", "fr")
        ):
            problems.append(f"{key} needs en and fr")
    schemes = m.get("schemes")
    if not schemes or not set(schemes) <= set(t.SCHEMES) or len(set(schemes)) != len(schemes):
        problems.append("schemes: dark and/or light")
    if m.get("identity", "line") not in ("line", "pixel"):
        problems.append("identity: line (icons) or pixel (sprites)")
    for key in ("slots", "parts"):
        if not isinstance(m.get(key, {}), dict):
            problems.append(f"{key}: an object")
    parts = t.read(t.ROOT / "_schema/parts.json")
    for part, variant in (m.get("parts") or {}).items():
        if part not in parts or part.startswith("$") or variant not in parts[part]["variants"]:
            problems.append(f"parts.{part}: one of the variants in themes/_schema/parts.json")
    if m.get("rooms", "distinct") not in ("distinct", "unified"):
        problems.append("rooms: distinct (each room its own light) or unified (one light)")
    if (m.get("names") or {}).get("en") == "Your theme" or (m.get("description") or {}).get(
        "en", ""
    ).startswith("One sentence:"):
        problems.append("names and description: still the template's words")
    if m.get("density", "comfortable") not in t.DENSITY:
        problems.append("density: compact, comfortable or airy")
    if not isinstance(m.get("fonts"), dict) or set(m["fonts"]) != {"display", "body", "mono"}:
        problems.append("fonts: display, body and mono")
    elif not all(isinstance(f, str) and t.FAMILY.fullmatch(f) for f in m["fonts"].values()):
        problems.append("fonts: family names are plain words (letters, digits, spaces, hyphens)")
    credit = m.get("credit")
    if credit is not None and not (
        isinstance(credit, dict) and set(credit) == {"en", "fr"}
        and all(isinstance(v, str) and 0 < len(v) <= 40 for v in credit.values())
    ):  # fmt: skip
        problems.append("credit: {en, fr}, who made it, 40 characters at most (plain text, never a link)")
    if len(m.get("names", {}).get("fr", "")) > 32 or len(m.get("names", {}).get("en", "")) > 32:
        problems.append("names: 32 characters at most")
    out.add("Manifest", not problems, "; ".join(problems))


# A material's edge always takes 1px, so a borderless look is a transparent edge, not none.
EDGE = re.compile(r"1px (solid|dashed|dotted) \S.*")
# Mechanical motion (a flap board, an LCD): a few steps instead of a curve.
STEPS = re.compile(r"steps\(([1-9]|1[0-2])(, ?(start|end|jump-none|jump-both))?\)")


def _within(value, limit: float) -> bool:
    m = re.fullmatch(r"(-?[\d.]+)(deg)?", str(value).strip())
    return bool(m) and abs(float(m[1])) <= limit


def contract(theme: t.Theme, base: t.Theme, out: Results):
    problems = []
    base_values = {}
    for scheme in base.schemes:
        for layer in base.layers(scheme):
            base_values |= {k: v["value"] for k, v in layer.items()}
    if theme.id != base.id:
        for scheme in theme.schemes:
            for layer in theme.layers(scheme):
                for name, token in layer.items():
                    group = name.split(".")[0]
                    if group in t.FIXED or name in t.FIXED_TOKENS:
                        problems.append(f"{name} is fixed by the contract (sizes never change)")
                    elif (
                        group in ("material", "part")
                        and name.endswith(".border")
                        and not EDGE.fullmatch(str(token["value"]))
                    ):
                        problems.append(f"{name}: an edge is 1px (solid, dashed or dotted), any colour")
                    elif name == "material.sunken.border" and "transparent" in str(token["value"]):
                        problems.append(f"{name}: fields keep a visible edge (not transparent)")
                    elif (
                        group == "ease"
                        and isinstance(token["value"], str)
                        and not STEPS.fullmatch(token["value"])
                    ):
                        problems.append(
                            f"{name}: an easing is a cubic-bezier list, or steps(n) for mechanical motion"
                        )
                    elif name.endswith(".art-opacity") and not _within(token["value"], 1):
                        problems.append(f"{name}: an opacity from 0 to 1")
                    elif name == "material.paper.rotate" and not _within(token["value"], 2):
                        problems.append(f"{name}: paper tilts 2deg at most")
                    elif (
                        group == "material"
                        and name.startswith("material.media")
                        and "filter" in str(token["value"])
                    ):
                        problems.append(f"{name}: real posters and covers are never filtered")
    out.add("Contract (fixed sizes, media)", not problems, "; ".join(problems))


def values(theme: t.Theme, base: t.Theme, out: Results) -> dict[str, dict[str, str]]:
    """{scheme: {--var: value}}, or {} when the theme doesn't resolve."""
    resolved = {}
    try:
        for scheme in theme.schemes:
            resolved[scheme] = t.variables(theme, scheme, base)
            for name, value in resolved[scheme].items():
                if name.startswith("--c-") and not color.is_colour(value):
                    raise t.ThemeError(f"{name}: {value!r} is not a colour")
    except t.ThemeError as error:
        out.add("Tokens resolve", False, str(error))
        return {}
    out.add("Tokens resolve", True, f"{len(next(iter(resolved.values())))} values per scheme")
    return resolved


def _metrics(value: str) -> tuple[float, float]:
    """A font shorthand's size and line height, in px."""
    m = re.search(r"([\d.]+)px/([\d.]+)(px)?", value)
    size = float(m[1])
    return size, float(m[2]) if m[3] else size * float(m[2])


def type_band(v: dict[str, str], base_v: dict[str, str], scheme: str, out: Results):
    """Text may suit its face but not grow the layout: see tokens.TEXT_BAND."""
    band, problems = t.TEXT_BAND, []
    for name, value in v.items():
        m = re.fullmatch(r"--text-([a-z0-9-]+)", name)
        if not m or name.endswith(("-tracking", "-case")) or name not in base_v:
            continue
        (size, line), (was, was_line) = _metrics(value), _metrics(base_v[name])
        style = m[1]
        if style == "brand":
            if line > band["brand_line"]:
                problems.append(
                    f"brand's line is {line:g}px ({band['brand_line']}px at most: it sits in the status bar)"
                )
        elif style.startswith("display"):
            if size > was * band["display"]:
                problems.append(f"{style} is {size:g}px ({was * band['display']:.0f}px at most)")
        else:
            if size > was + band["px"]:
                problems.append(f"{style} is {size:g}px (Base {was:g}px; {was + band['px']:g}px at most)")
            if abs(line - was_line) > band["line"]:
                problems.append(f"{style}'s line is {line:.1f}px (Base {was_line:.1f}px; ±{band['line']}px)")
            track = float(v.get(name + "-tracking", "0em")[:-2])
            if style == "action":
                if track > float(base_v.get(name + "-tracking", "0em")[:-2]) + band["action_track"]:
                    problems.append(
                        f"action tracking {track:g}em (buttons keep their width: Base +{band['action_track']}em)"
                    )
                if v.get(name + "-case", "none") != base_v.get(name + "-case", "none"):
                    problems.append("action keeps Base's case (capitals widen every button)")
            elif style in ("label", "caption") and track > band["small_track"]:
                problems.append(f"{style} tracking {track:g}em ({band['small_track']}em at most)")
    out.add(f"Text sizes fit the layout ({scheme})", not problems, "; ".join(problems))


def type_rules(v: dict[str, str], scheme: str, out: Results):
    problems = []
    families = {}
    for name, value in v.items():
        m = re.fullmatch(r"--text-([a-z0-9-]+)", name)
        if m and not name.endswith(("-tracking", "-case")):
            size = float(re.search(r"([\d.]+)px/", value)[1])
            if size < 11:
                problems.append(f"{m[1]} is {size:g}px (11px at least)")
            families[m[1]] = value.split("/", 1)[1].split(" ", 1)[1]
    display, body = v["--font-display"], v["--font-body"]
    for style, family in families.items():
        if style.startswith("body") and family == display and display != body:
            problems.append(f"{style} uses the display face (body text never does)")
    for name in ("--dur-fast", "--dur-base", "--dur-slow", "--dur-slower"):
        if float(v[name][:-2]) > 1000:
            problems.append(f"{name} over 1s")
    stroke = float(v["--icon-stroke"])
    if not 1 <= stroke <= 3:
        problems.append("icon stroke 1–3")
    out.add(f"Type, motion and icon bounds ({scheme})", not problems, "; ".join(problems))


def contrast(v: dict[str, str], scheme: str, out: Results) -> list[tuple]:
    """The contrast matrix; returns its rows for the report."""
    c = {
        name: color.parse(value)
        for name, value in v.items()
        if name.startswith(("--c-", "--mat-", "--part-")) and color.is_colour(value)
    }
    canvas = c["--c-bg-canvas"]
    ground = lambda name: color.over(c[name], canvas) if c[name][3] < 1 else c[name]  # noqa: E731
    pairs = []
    grounds = [f"--c-bg-{g}" for g in (*GROUNDS, "hover", "selected")]
    for fg in ("--c-fg-default", "--c-fg-muted"):
        pairs += [(fg, g, TEXT) for g in grounds]
    pairs += [
        (fg, f"--c-bg-{g}", TEXT)
        for fg in ("--c-fg-subtle", "--c-fg-link", "--c-accent-fg")
        for g in ("canvas", "surface", "raised", "overlay")
    ]
    pairs += [
        ("--c-fg-placeholder", "--c-bg-sunken", TEXT),
        ("--c-fg-on-accent", "--c-accent-solid", TEXT),
        ("--c-fg-current", "--c-bg-current", TEXT),
        ("--c-accent-fg", "--c-accent-soft", TEXT),
        ("--c-fg-inverse", "--c-bg-inverse", TEXT),
        ("--c-paper-fg", "--c-paper-bg", TEXT),
        ("--c-paper-muted", "--c-paper-bg", TEXT),
        ("--c-private-fg", "--c-private-soft", TEXT),
        ("--c-private-solid", "--c-bg-canvas", UI),
        ("--mat-inverse-fg", "--mat-inverse-bg", TEXT),
        ("--mat-paper-fg", "--mat-paper-bg", TEXT),
    ]
    for s in STATUS:
        pairs += [
            (f"--c-{s}-fg", f"--c-{s}-soft", TEXT),
            (f"--c-{s}-fg", "--c-bg-canvas", TEXT),
            (f"--c-{s}-solid", "--c-bg-canvas", UI),
        ]
    pairs += [("--c-fg-default", f"--mat-{m}-bg", TEXT) for m in ("surface", "raised", "overlay", "sunken")]
    pairs += [("--mat-screen-fg", "--mat-screen-bg", TEXT), ("--part-nowbar-fg", "--part-nowbar-bg", TEXT)]
    pairs += [("--c-border-strong", f"--c-bg-{g}", UI) for g in ("canvas", "surface", "raised", "overlay")]
    pairs += [("--c-focus-ring", g, UI) for g in grounds[:5]]
    for room, rv in t.room_variables(v).items():
        light = color.parse(rv["--c-room"])
        c[f"room {room}"], c[f"room {room} text"] = light, color.parse(rv["--c-room-fg"])
        c[f"room {room} soft"] = color.over(color.parse(rv["--c-room-soft"]), canvas)
        pairs += [(f"room {room}", "--c-bg-canvas", UI), (f"room {room}", "--c-bg-surface", UI),
                  (f"room {room} text", f"room {room}", TEXT), ("--c-focus-ring", f"room {room} soft", UI)]  # fmt: skip
    pairs += [(f"--c-person-{n}", g, UI) for n in range(1, 9) for g in ("--c-bg-canvas", "--c-bg-surface")]
    pairs += [(f"--c-data-{n}", "--c-bg-canvas", UI) for n in range(1, 9)]
    pairs += [("--c-sprite-light", "--c-bg-canvas", UI), ("--c-sprite-accent", "--c-bg-canvas", UI)]
    rows, failures = [], []
    for fg, bg, need in pairs:
        back = ground(bg)
        ratio = color.contrast(c[fg], back)
        rows.append((fg, bg, ratio, need, abs(color.apca(c[fg], back))))
        if ratio < need:
            failures.append(f"{fg} on {bg}: {ratio:.2f} (needs {need:g})")
    out.add(f"Contrast ({scheme}, {len(pairs)} pairs)", not failures, "; ".join(failures))
    return rows


def distinct(v: dict[str, str], scheme: str, out: Results, rooms: str = "distinct"):
    c = lambda name: color.parse(v[name])  # noqa: E731
    problems, advice = [], []
    groups = {
        "states": [f"--c-{s}-solid" for s in ("accent", *STATUS)],
        # A limited-ink theme ("rooms": "unified") may light every room the same.
        "rooms": [f"--c-room-{r}" for r in t.ROOMS] if rooms != "unified" else [],
        "people": [f"--c-person-{n}" for n in range(1, 9)],
    }
    for group, names in groups.items():
        for a, b in itertools.combinations(names, 2):
            if color.distance(c(a), c(b)) < 0.04:
                problems.append(f"{group}: {a} and {b} look the same")
    for a, b in (("--c-success-solid", "--c-danger-solid"), ("--c-warning-solid", "--c-danger-solid")):
        if color.distance(color.deutan(c(a)), color.deutan(c(b))) < 0.05:
            advice.append(
                f"{a} and {b} are close for red-green colour blindness (the word and mark still tell them apart)"
            )
    out.add(f"Distinct colours ({scheme})", not problems, "; ".join(problems))
    if advice:
        out.add(f"Colour-blind advice ({scheme})", False, "; ".join(advice), warn=True)


def files(theme: t.Theme, out: Results):
    folder, problems = theme.folder, []
    fonts = theme.manifest.get("fonts") or {}
    font_files = sorted((folder / "fonts").glob("*.woff2")) if (folder / "fonts").is_dir() else []
    for role, family in fonts.items():
        if family in BUNDLED_FONTS:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(family).lower()).strip("-")
        own = [f for f in font_files if f.name.startswith(slug)]
        if not own:
            problems.append(f"font {family!r} ({role}): add its woff2 files to fonts/ (theme_font does this)")
        elif not any("latin-ext" in f.name for f in own):
            problems.append(f"font {family!r}: needs the latin-ext files too (French: œ « » ’)")
    if (
        font_files
        and not list((folder / "fonts").glob("*LICENSE*"))
        and not list((folder / "fonts").glob("*OFL*"))
    ):
        problems.append("fonts/ needs the font licence file")
    if sum(f.stat().st_size for f in font_files) > FONTS_MAX:
        problems.append(f"fonts over {FONTS_MAX // 1000} KB")
    art = [p for p in (folder / "art").rglob("*") if p.is_file()] if (folder / "art").is_dir() else []
    for p in art:
        if p.suffix.lower() not in ART_TYPES:
            problems.append(f"art/{p.name}: use SVG, PNG or WebP")
        elif p.stat().st_size > ART_MAX:
            problems.append(f"art/{p.name}: over {ART_MAX // 1000} KB")
        elif p.suffix.lower() == ".svg" and UNSAFE_SVG.search(p.read_text(errors="replace")):
            problems.append(f"art/{p.name}: scripts, events and outside links are not allowed in SVG")
    if sum(p.stat().st_size for p in art) > PACK_MAX:
        problems.append(f"art over {PACK_MAX // 1_000_000} MB in all")
    for p in folder.rglob("*"):
        if p.relative_to(folder).parts[0] == "shots":  # the tour's screenshots: local, never shipped
            continue
        if p.is_file() and p.suffix.lower() in {".js", ".mjs", ".ts", ".tsx", ".html", ".py", ".sh", ".css"}:
            problems.append(f"{p.relative_to(folder)}: themes are data only (no code or CSS)")
    out.add("Fonts, art and files", not problems, "; ".join(problems))


URL = re.compile(r"url\(\s*([\"']?)([^)\"']*)\1\s*\)")


def images(theme: t.Theme, resolved: dict[str, dict[str, str]], out: Results):
    """Textures and other images in tokens: only the theme's own art/ files (never the web)."""
    problems = set()
    for v in resolved.values():
        for name, value in v.items():
            for _, target in URL.findall(value):
                if not re.fullmatch(r"art/[a-z0-9][a-z0-9._-]*\.(svg|png|webp)", target):
                    problems.add(f"{name}: url({target}) must be a file in the theme's art/")
                elif not (theme.folder / target).is_file():
                    problems.add(f"{name}: {target} is missing")
    out.add("Images in tokens", not problems, "; ".join(sorted(problems)))


def slots(theme: t.Theme, out: Results):
    known = {
        k: v for k, v in t.read(theme.folder.parent / "_schema/slots.json").items() if not k.startswith("$")
    }
    if not known:
        known = {k: v for k, v in t.read(t.ROOT / "_schema/slots.json").items() if not k.startswith("$")}
    problems, blurry = [], []
    for slot, fill in (theme.manifest.get("slots") or {}).items():
        if slot not in known:
            problems.append(f"{slot}: not an art slot (themes/_schema/slots.json)")
        elif isinstance(fill, dict) and "scene" in fill:
            if known[slot]["kind"] != "scene" or fill.get("scene") not in ("hall", "room") or len(fill) > 1:
                problems.append(f'{slot}: a scene slot takes {{"scene": "hall" | "room"}}')
        elif isinstance(fill, dict):
            fit, surface = fill.get("fit", "cover"), known[slot]["kind"] == "surface"
            if (
                set(fill) - {"image", "rendering", "fit", "slice", "anchor", "rooms", "schemes"}
                or fill.get("anchor", "center") not in ("top", "center", "bottom")
                or fill.get("rendering", "pixel")
                not in (
                    "pixel",
                    "smooth",
                )
                or fit not in ("cover", "contain", "stretch", "slice")
            ):
                problems.append(
                    f"{slot}: an image takes image, rendering (pixel|smooth), fit (cover|contain|stretch|slice)"
                    " and anchor (top|center|bottom: the part kept whole when a tall picture is cropped)"
                )
            elif fit == "slice" and not (
                surface and isinstance(fill.get("slice"), int) and 1 <= fill["slice"] <= 400
            ):
                problems.append(f'{slot}: slice (a 9-slice frame) is for surfaces, with "slice": 1–400 px')
            elif "slice" in fill and fit != "slice":
                problems.append(f'{slot}: "slice" goes with fit "slice"')
            elif not (isinstance(fill.get("image"), str) and (theme.folder / fill["image"]).is_file()
                      and fill["image"].startswith("art/")):  # fmt: skip
                problems.append(f"{slot}: image is art/<file> in the theme folder")
            elif "rooms" in fill and not own_pictures(theme, fill["rooms"], t.ALL_ROOMS):
                problems.append(f"{slot}: rooms is {{room: art/<file>}} (or {{room: {{dark|light: art/<file>}}}}), a picture for one room")
            elif "schemes" in fill and not own_pictures(theme, fill["schemes"], theme.schemes):
                problems.append(f"{slot}: schemes is {{dark|light: art/<file>}}, a picture for one of the theme's schemes")
            elif fill.get("rendering") == "smooth" and fit != "slice" and known[slot].get("min"):
                small = too_small(theme.folder / fill["image"], known[slot]["min"])
                if small:
                    blurry.append(f"{slot}: {small}")
        elif not isinstance(fill, str) or not (
            (fill.startswith("art/") and (theme.folder / fill).is_file())
            or re.fullmatch(r"/art/[a-z0-9-]+\.(png|svg|webp)", fill)
        ):
            problems.append(f"{slot}: an image is art/<file> in the theme folder")
    out.add("Art slots", not problems, "; ".join(problems))
    if blurry:  # advice only: a small picture still works, it just isn't sharp
        out.add("Art sizes", False, "; ".join(blurry) + " (draw it bigger, or mark it pixel)", warn=True)


def own_pictures(theme: t.Theme, pictures, keys) -> bool:
    """{room or scheme: art/<file>}: another picture of the theme's own for those. A room's may
    itself differ by scheme: {room: {dark|light: art/<file>}}."""
    own = lambda file: isinstance(file, str) and file.startswith("art/") and (theme.folder / file).is_file()  # noqa: E731
    return isinstance(pictures, dict) and all(
        key in keys and (own(file) or (keys is t.ALL_ROOMS and isinstance(file, dict) and file
                                       and all(s in theme.schemes and own(f) for s, f in file.items())))
        for key, file in pictures.items()
    )  # fmt: skip


# Layers: pictures the app moves (design/layers.tsx), as far as the person's motion level allows.
LAYER = {
    "where": ("page", "hero", "header", "rail", "rail-foot", "status", "deck"),
    "fit": ("cover", "contain", "repeat", "repeat-x", "natural"),
    "anchor": ("center", "top", "bottom", "left", "right", "top-left", "top-right", "bottom-left", "bottom-right"),
    "blend": ("normal", "screen", "multiply", "overlay", "soft-light"),
    "rendering": ("pixel", "smooth"),
}
LAYER_KEYS = {*LAYER, "image", "rooms", "schemes", "scale", "opacity", "above", "under", "poke", "depth", "drift", "cross", "frames",
              "particles", "playing"}  # fmt: skip
LAYERS_MAX, PARTICLES_MAX, ABOVE_OPACITY = 12, 48, 0.15
PARTICLE_MOTION, CROSS_FROM = ("rise", "fall", "float", "twinkle"), ("left", "right", "top", "bottom")


def _number(value, low, high) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high


def layer_problems(theme: t.Theme, n: int, layer) -> list[str]:
    if not isinstance(layer, dict):
        return [f"layers[{n}]: an object"]
    at, problems = f"layers[{n}]", []
    unknown = set(layer) - LAYER_KEYS
    if unknown:
        problems.append(f"{at}: unknown {', '.join(sorted(unknown))}")
    image = layer.get("image")
    if not (isinstance(image, str) and image.startswith("art/") and (theme.folder / image).is_file()):
        return problems + [f"{at}: image is art/<file> in the theme folder"]
    for key, allowed in LAYER.items():
        if key in layer and layer[key] not in allowed:
            problems.append(f"{at}.{key}: one of {', '.join(allowed)}")
    if "where" not in layer:
        problems.append(f"{at}.where: one of {', '.join(LAYER['where'])}")
    if "rooms" in layer and not (
        isinstance(layer["rooms"], list) and layer["rooms"] and set(layer["rooms"]) <= set(t.ALL_ROOMS)
    ):
        problems.append(f"{at}.rooms: a list of rooms (home, listen…) it shows in")
    if "schemes" in layer and not (
        isinstance(layer["schemes"], list) and layer["schemes"] and set(layer["schemes"]) <= set(theme.schemes)
    ):
        problems.append(f"{at}.schemes: a list of the theme's schemes (dark, light) it shows in")
    if "scale" in layer and not (isinstance(layer["scale"], int) and 1 <= layer["scale"] <= 8):
        problems.append(f"{at}.scale: a whole number 1–8 (pixel art drawn bigger)")
    if "opacity" in layer and not _number(layer["opacity"], 0.05, 1):
        problems.append(f"{at}.opacity: 0.05–1")
    if layer.get("above") is True and (layer.get("where") != "page" or layer.get("opacity", 1) > ABOVE_OPACITY):
        problems.append(f"{at}.above: over the page only, with opacity {ABOVE_OPACITY} at most (text stays readable)")
    if "under" in layer and not (layer["under"] is True and layer.get("where") in ("page", "hero", "status", "header") and not layer.get("above")):
        problems.append(f"{at}.under: true, behind the place's own picture (page, hero, status or header)")
    if "depth" in layer and not _number(layer["depth"], 0, 1):
        problems.append(f"{at}.depth: 0–1 (how far it follows the pointer and scrolling)")
    fit = layer.get("fit", "cover")
    moves = [key for key in ("drift", "cross", "particles") if key in layer]
    if len(moves) > 1:
        problems.append(f"{at}: one of drift, cross or particles")
    drift = layer.get("drift")
    if drift is not None and not (
        isinstance(drift, list) and len(drift) == 2 and all(_number(v, -200, 200) for v in drift)
        and fit in ("repeat", "repeat-x")
    ):  # fmt: skip
        problems.append(f"{at}.drift: [x, y] px a second (±200), on a repeat or repeat-x picture")
    cross = layer.get("cross")
    if cross is not None and not (
        isinstance(cross, dict) and set(cross) <= {"seconds", "every", "from"} and fit == "natural"
        and _number(cross.get("seconds"), 2, 120) and _number(cross.get("every", cross.get("seconds")), cross.get("seconds", 2), 600)
        and cross.get("from", "left") in CROSS_FROM
    ):  # fmt: skip
        problems.append(f"{at}.cross: {{seconds 2–120, every (seconds–600), from left|right|top|bottom}}, a natural picture")
    frames = layer.get("frames")
    if frames is not None:
        if not (isinstance(frames, dict) and set(frames) <= {"count", "fps"} and isinstance(frames.get("count"), int)
                and 2 <= frames["count"] <= 32 and _number(frames.get("fps", 6), 1, 24)):  # fmt: skip
            problems.append(f"{at}.frames: {{count 2–32, fps 1–24}}, frames side by side")
        elif fit != "natural":
            problems.append(f"{at}.frames: a natural picture (drawn at its size, one frame shown)")
        elif image.endswith((".png", ".webp")) and (width := picture_size(theme.folder / image)[0]) % frames["count"]:
            problems.append(f"{at}.frames: {width} px wide doesn't split into {frames['count']} frames")
    particles = layer.get("particles")
    if particles is not None and not (
        isinstance(particles, dict) and set(particles) <= {"count", "motion", "seconds"}
        and isinstance(particles.get("count"), int) and 1 <= particles["count"] <= 24
        and particles.get("motion") in PARTICLE_MOTION and _number(particles.get("seconds", 8), 2, 60)
    ):  # fmt: skip
        problems.append(f"{at}.particles: {{count 1–24, motion rise|fall|float|twinkle, seconds 2–60}}")
    if "poke" in layer:
        problems += poke_problems(theme, at, layer, image)
    if "playing" in layer and not (isinstance(layer["playing"], bool) and (not layer["playing"] or layer.get("where") == "deck")):
        problems.append(f"{at}.playing: true on a deck layer (it moves only while music plays), or false")
    return problems


POKES_MAX, BURST_MAX = 6, 12


def poke_problems(theme: t.Theme, at: str, layer: dict, image: str) -> list[str]:
    """A piece that answers a click (desktop): a reaction sheet played once, maybe a small burst."""
    poke, problems = layer["poke"], []
    if not (isinstance(poke, dict) and set(poke) <= {"image", "frames", "burst", "stay"} and poke.get("stay", "random") == "random"
            and layer.get("fit") == "natural"
            and not layer.get("above")):  # fmt: skip
        return [f"{at}.poke: {{frames, image?, burst?, stay? \"random\"}} on a natural piece"]
    frames = poke.get("frames")
    if not (isinstance(frames, dict) and set(frames) <= {"count", "fps"} and isinstance(frames.get("count"), int)
            and 2 <= frames["count"] <= 32 and _number(frames.get("fps", 10), 1, 24)):  # fmt: skip
        problems.append(f"{at}.poke.frames: {{count 2–32, fps 1–24}}, the reaction played once")
    sheet = poke.get("image", image)
    if not (isinstance(sheet, str) and sheet.startswith("art/") and (theme.folder / sheet).is_file()):
        return problems + [f"{at}.poke.image: art/<file> in the theme folder"]
    width, height = picture_size(theme.folder / image)
    if width and not problems and sheet != image:
        frame = width // layer.get("frames", {}).get("count", 1) if isinstance(layer.get("frames"), dict) else width
        if picture_size(theme.folder / sheet) != (frame * frames["count"], height):
            problems.append(f"{at}.poke.image: {frames['count']} frames of the piece's size ({frame} × {height}) side by side")
    burst = poke.get("burst")
    if burst is not None and not (
        isinstance(burst, dict) and set(burst) == {"image", "count"} and isinstance(burst["count"], int)
        and 1 <= burst["count"] <= BURST_MAX and isinstance(burst["image"], str) and burst["image"].startswith("art/")
        and (theme.folder / burst["image"]).is_file()
    ):  # fmt: skip
        problems.append(f"{at}.poke.burst: {{image art/<file>, count 1–{BURST_MAX}}}")
    return problems


def layers(theme: t.Theme, out: Results):
    found = theme.manifest.get("layers", [])
    if not isinstance(found, list):
        return out.add("Layers", False, "layers: a list")
    problems = [p for n, layer in enumerate(found) for p in layer_problems(theme, n, layer)]
    if len(found) > LAYERS_MAX:
        problems.append(f"{len(found)} layers, {LAYERS_MAX} at most")
    if sum(1 for layer in found if isinstance(layer, dict) and "poke" in layer) > POKES_MAX:
        problems.append(f"{POKES_MAX} pieces that answer a click at most")
    particles = sum(layer.get("particles", {}).get("count", 0) for layer in found if isinstance(layer, dict)
                    and isinstance(layer.get("particles"), dict) and isinstance(layer["particles"].get("count"), int))  # fmt: skip
    if particles > PARTICLES_MAX:
        problems.append(f"{particles} particles, {PARTICLES_MAX} at most in all")
    out.add("Layers", not problems, "; ".join(problems))


def picture_size(path) -> tuple[int, int]:
    """(width, height) of a PNG or WebP; (0, 0) without Pillow (a kit without it skips the sums)."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:  # noqa: BLE001
        return (0, 0)


def too_small(path, least):
    """ "W × H, smaller than W × H" when a smooth picture would be upscaled in its box."""
    width, height = picture_size(path)  # (0, 0): SVG, or no Pillow: nothing to say
    if not width:
        return ""
    return (
        f"{width} × {height}, smaller than {least[0]} × {least[1]}"
        if width < least[0] or height < least[1]
        else ""
    )


def flavour(theme: t.Theme, out: Results):
    data = t.read(theme.folder / "flavor.json")
    problems = []
    for key, texts in data.items():
        if key.startswith("$"):
            continue
        if not SLOT.match(key):
            problems.append(f"{key}: not a flavour slot")
            continue
        if key.endswith(".name") and key[: -len(".name")] not in t.read(t.ROOT / "_schema/sprites.ids.json"):
            problems.append(f"{key}: not a house title (themes/_schema/sprites.ids.json lists them)")
            continue
        if not isinstance(texts, dict) or not all(
            isinstance(texts.get(lang), str) and texts[lang].strip() for lang in ("en", "fr")
        ):
            problems.append(f"{key}: needs en and fr")
            continue
        limit = SLOT_KINDS[key.rsplit(".", 1)[1]]
        for lang in ("en", "fr"):
            if len(texts[lang]) > limit:
                problems.append(f"{key} ({lang}): {len(texts[lang])} characters, {limit} at most")
    out.add("Flavour text (en + fr)", not problems, "; ".join(problems))


def sprites(theme: t.Theme, v: dict[str, str], out: Results):
    data = t.read(theme.folder / "sprites.json")
    if not data:
        return
    problems = []
    palette = data.get("palette") or {}
    for letter, name in palette.items():
        if len(letter) != 1 or letter == "." or f"--c-sprite-{name}" not in v:
            problems.append(f"palette {letter!r} → {name!r}: one letter to a color.sprite token")
    known = {k for k in t.read(t.ROOT / "_schema/sprites.ids.json") if not k.startswith("$")}
    for name, grid in (data.get("glyphs") or {}).items():
        if name not in known:
            problems.append(f"{name}: not a piece a theme can redraw (themes/_schema/sprites.ids.json)")
            continue
        if not isinstance(grid, list) or not grid or not all(isinstance(row, str) for row in grid):
            problems.append(f"{name}: a glyph is a list of rows")
            continue
        if len(grid) > SPRITE_MAX or max(map(len, grid)) > SPRITE_MAX:
            problems.append(f"{name}: {SPRITE_MAX} × {SPRITE_MAX} pixels at most")
            continue
        unknown = {ch for row in grid for ch in row if ch != "." and ch not in palette}
        if unknown:
            problems.append(f"{name}: letters {''.join(sorted(unknown))} are not in the palette")
    out.add("Sprites", not problems, "; ".join(problems))


def check(theme_id: str, root: Path | None = None) -> tuple[Results, dict]:
    root = root or t.ROOT
    base = t.load("base", root)
    theme = t.load(theme_id, root)
    out = Results()

    def run(name, step, *args):
        """A malformed file (a list where an object belongs…) fails its check, never the kit."""
        try:
            return step(*args)
        except (AttributeError, TypeError, KeyError, ValueError, IndexError) as error:
            out.add(name, False, f"a file is malformed here ({type(error).__name__}: {error})"[:300])

    run("Manifest", manifest, theme, out)
    run("Contract (fixed sizes, media)", contract, theme, base, out)
    resolved = run("Tokens resolve", values, theme, base, out) or {}
    matrix = {}
    for scheme, v in resolved.items():
        run(f"Type, motion and icon bounds ({scheme})", type_rules, v, scheme, out)
        if theme.id != base.id:
            base_v = t.variables(base, scheme if scheme in base.schemes else base.schemes[0], base)
            run(f"Text sizes fit the layout ({scheme})", type_band, v, base_v, scheme, out)
        matrix[scheme] = run(f"Contrast ({scheme})", contrast, v, scheme, out) or []
        run(f"Distinct colours ({scheme})", distinct, v, scheme, out, theme.manifest.get("rooms", "distinct"))
    run("Fonts, art and files", files, theme, out)
    run("Images in tokens", images, theme, resolved, out)
    run("Art slots", slots, theme, out)
    run("Layers", layers, theme, out)
    run("Flavour text (en + fr)", flavour, theme, out)
    if resolved:
        run("Sprites", sprites, theme, next(iter(resolved.values())), out)
    return out, matrix


def report(theme_id: str, results: Results, matrix: dict) -> str:
    """REPORT.md: generated by `theme_kit check`, never edited by hand."""
    verdict = "FAIL" if results.failed else "PASS"
    lines = [f"# {theme_id}: {verdict}", "", "Generated by `python3 -m houseos.theme_kit check`; do not edit.", "",
             "| Check | Result | Detail |", "|---|---|---|"]  # fmt: skip
    lines += [
        f"| {name} | {status} | {detail.replace('|', '/') or '–'} |" for name, status, detail in results
    ]
    for scheme, rows in matrix.items():
        lines += [
            "",
            f"## Contrast, {scheme}",
            "",
            "| Foreground | Background | WCAG | Needs | APCA Lc |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {fg} | {bg} | {ratio:.2f}{'' if ratio >= need else ' ✗'} | {need:g} | {lc:.0f} |"
            for fg, bg, ratio, need, lc in rows
        ]
    return "\n".join(lines) + "\n"
