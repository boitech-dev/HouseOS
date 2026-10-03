"""The downloadable guide "Make your own HouseOS theme": one self-contained HTML page.

    python3 frontend/tools/theme-guide.py [--template T] [--out FILE]

Fills themes/_kit/guide.html:
  {{covers}} {{gallery}}  the bundled themes' own pictures: their cards (art/card-<scheme>.webp) and tour shots (shots/ is
                          local: run `node themes/_kit/tour.cjs <id>` for each theme first)
  {{pieces}}              each theme's Nox, avatars, room marks, medals (sprites.json) and its
                          only words, the title names and star mark (flavor.json)
  {{slots}}               the art slots' names (themes/_schema/slots.json)
  {{pic:path|alt|class|width}}  any picture in the repository as an <img>; with a width it is
                          re-encoded as WebP at that width (screenshots), without one it is
                          embedded as it is (pixel art)
  {{uri:path}}            a picture's data: URI, for the page's CSS
Every picture is embedded as a data: URI, so the page works opened from disk as well as served at
/guides/make-a-theme.html. Python 3 and Pillow.
"""

import argparse
import base64
import html
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
from houseos.theme_kit import build  # noqa: E402
from houseos.theme_kit import tokens as t  # noqa: E402

IMAGE_MAX, PAGE_MAX = 200_000, 4_000_000
CALM = build.PICKER[:4]  # the pickers show the calm themes first, then the worlds
MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg"}
# Nothing of the machine it was made on may leak into a page people download.
# Written with escaped slashes (the same pattern) so the privacy scan doesn't read it as a path.
LEAKS = re.compile(r"\/home\/|\/storage\/|\/tmp\/|127\.0\.0\.1|localhost|192\.168\.|\b10\.\d+\.\d+\.\d+")
esc = html.escape


def embed(rel: str, width: int | None = None) -> tuple[str, int, int]:
    """(data URI, width, height) of a picture in the repository."""
    path = REPO / rel
    if not path.is_file():
        hint = " (run node themes/_kit/tour.cjs <id>: shots/ is local)" if "/shots/" in rel else ""
        raise SystemExit(f"{rel} is missing{hint}")
    image = Image.open(path)
    if width is None:
        data, mime = path.read_bytes(), MIME[path.suffix]
    else:
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        if image.width > width:
            image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=80, method=6)
        data, mime = buffer.getvalue(), "image/webp"
    if len(data) > IMAGE_MAX:
        raise SystemExit(f"{rel}: {len(data) // 1024} KB embedded (200 KB at most): give it a smaller width")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}", image.width, image.height


def img(rel: str, alt: str, css: str = "", width: int | None = None) -> str:
    uri, w, h = embed(rel, width)
    return f'<img class="{css}" src="{uri}" width="{w}" height="{h}" alt="{esc(alt)}" loading="lazy" decoding="async">'


def shown() -> list[t.Theme]:
    return [x for x in build.bundled() if not x.manifest.get("hidden") and not x.manifest.get("debug")]


def covers(themes: list[t.Theme]) -> str:
    return "".join(
        f'<figure>{img(f"themes/{x.id}/shots/{x.schemes[0]}-phone-home.png", f"{x.manifest["names"]["en"]}: Home on a phone", "", 240)}'
        f'<figcaption>{esc(x.manifest["names"]["en"])}</figcaption></figure>'
        for x in themes
    )


def card(theme: t.Theme) -> str:
    m, schemes = theme.manifest, theme.schemes
    name, layers = m["names"]["en"], m.get("layers", [])
    phone = schemes[-1]  # a theme with two schemes shows its second one on the phone
    pokes = sum("poke" in layer for layer in layers)
    facts = [" and ".join(schemes), f"{len(m.get('slots', {}))} slots", f"{len(layers)} layers"] + ([f"{pokes} pokes"] if pokes else [])
    return (
        f'<article class="theme"><div class="stage">'
        f'<figure class="desk">{img(f"themes/{theme.id}/art/card-{schemes[0]}.webp", f"{name}: Home on a desktop, {schemes[0]}", "", 560)}'
        f'<span class="scheme">{schemes[0]}</span></figure>'
        f'<figure class="phone">{img(f"themes/{theme.id}/shots/{phone}-phone-listen.png", f"{name}: Listen on a phone, {phone}", "", 300)}'
        f'<span class="scheme">{phone}</span></figure></div>'
        f'<h3>{esc(name)}</h3><p>{esc(m["description"]["en"])}</p>'
        f'<p class="facts">{" · ".join(facts)} · <code>{theme.id}</code></p></article>'
    )


def gallery(themes: list[t.Theme]) -> str:
    calm = [x for x in themes if x.id in CALM]
    worlds = [x for x in themes if x.id not in CALM]
    return (
        '<h3 class="group">Calm <span>type, light and a few pictures</span></h3>'
        f'<div class="themes">{"".join(map(card, calm))}</div>'
        '<h3 class="group">Worlds <span>a place, every part drawn</span></h3>'
        f'<div class="themes">{"".join(map(card, worlds))}</div>'
    )


def sprite(rows: list[str], palette: dict[str, str], zoom: int, alt: str) -> str:
    w, h = max(len(r) for r in rows), len(rows)
    image = Image.new("RGBA", (w, h))
    for y, row in enumerate(rows):
        for x, letter in enumerate(row):
            if letter in palette:
                image.putpixel((x, y), tuple(int(palette[letter][i : i + 2], 16) for i in (1, 3, 5)) + (255,))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    return f'<img class="px" src="{uri}" width="{w * zoom}" height="{h * zoom}" alt="{esc(alt)}">'


def pieces(themes: list[t.Theme]) -> str:
    base = t.load("base")
    stats = (REPO / "frontend/src/house_stats.tsx").read_text()
    houseos = dict(re.findall(r'^  (\w+): \["[\w-]+", "([^"]+)"', stats, re.M))  # HouseOS's own title names
    titles = [k.split(".", 1)[1] for k in json.loads((REPO / "themes/_schema/sprites.ids.json").read_text()) if k.startswith("title.")]
    inputs, tabs, panels, css = [], [], [], []
    for n, theme in enumerate(themes):
        name = theme.manifest["names"]["en"]
        sprites, flavor = t.read(theme.folder / "sprites.json"), t.read(theme.folder / "flavor.json")
        glyphs = sprites.get("glyphs", {})
        v = t.variables(theme, theme.schemes[0], base)
        palette = {k: v[f"--c-sprite-{colour}"] for k, colour in sprites.get("palette", {}).items()}

        def row(prefix: str, zoom: int, label: str) -> str:
            keys = [k for k in glyphs if k.startswith(prefix)]
            if not keys:
                return ""
            cells = "".join(f"<figure>{sprite(glyphs[k], palette, zoom, f'{name}: {k}')}<figcaption>{k.split('.')[1]}</figcaption></figure>" for k in keys)
            return f'<div class="prow"><h4>{label}</h4><div class="cells">{cells}</div></div>'

        medals = []
        for title in titles:
            own, words = glyphs.get(f"title.{title}"), flavor.get(f"title.{title}.name")
            default = houseos.get(title, title.replace("_", " ").capitalize())
            picture = sprite(own, palette, 2, f"{name}: the {default} medal") if own else '<span class="own" title="HouseOS\'s own line icon"></span>'
            named = (f'<b>{esc(words["en"])}</b><i>{esc(words["fr"])}</i>') if words else "<b class=\"muted\">HouseOS's own name</b>"
            medals.append(f'<li>{picture}<div>{named}<small>HouseOS: {esc(default)}</small></div></li>')
        star = flavor.get("title.star.mark", {}).get("en", "★")
        inputs.append(f'<input type="radio" name="pieces" id="pc-{n}"{" checked" if n == 0 else ""}>')
        tabs.append(f'<label for="pc-{n}">{esc(name)}</label>')
        style = f"--pbg:{v['--c-bg-canvas']};--pfg:{v['--c-fg-default']};--pmuted:{v['--c-fg-muted']};--pline:{v['--c-border-default']};--psurface:{v['--c-bg-surface']}"
        panels.append(
            f'<div class="ppanel" id="pp-{n}" style="{style}">'
            f'{row("nox.", 4, "Nox, 6 moods")}{row("avatar.", 4, "The 5 avatars")}{row("room.", 2, "Room marks")}'
            f'<div class="prow"><h4>20 medals and their names <span class="star">star mark <b>{esc(star)}</b></span></h4>'
            f'<ul class="medals">{"".join(medals)}</ul></div></div>'
        )
        css.append(f"#pc-{n}:checked~#pp-{n}{{display:block}}#pc-{n}:checked~.ptabs [for=pc-{n}]{{background:var(--ink);color:var(--bg);border-color:var(--ink)}}"
                   f"#pc-{n}:focus-visible~.ptabs [for=pc-{n}]{{outline:3px solid var(--accent);outline-offset:2px}}")  # fmt: skip
    return f'<style>{"".join(css)}</style><div class="viewer">{"".join(inputs)}<div class="ptabs">{"".join(tabs)}</div>{"".join(panels)}</div>'


def render(template: str) -> str:
    themes = shown()
    slots = [k for k in json.loads((REPO / "themes/_schema/slots.json").read_text()) if not k.startswith("$")]
    page = re.sub(r"<!--.*?-->\n", "", template, count=1, flags=re.S)  # the template's own note
    page = page.replace("{{covers}}", covers(themes)).replace("{{gallery}}", gallery(themes)).replace("{{pieces}}", pieces(themes))
    page = page.replace("{{slots}}", "".join(f"<li><code>{s}</code></li>" for s in slots))
    page = re.sub(r"\{\{uri:([^}|]+)\}\}", lambda m: embed(m[1])[0], page)
    page = re.sub(r"\{\{pic:([^}|]+)\|([^}|]*)(?:\|([^}|]*))?(?:\|(\d+))?\}\}", lambda m: img(m[1], m[2], m[3] or "", int(m[4]) if m[4] else None), page)
    left = re.findall(r"\{\{[^}]*\}\}", page)
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    text = re.sub(r"data:image/[a-z+]+;base64,[A-Za-z0-9+/=]+", "", page)
    if LEAKS.search(text):
        raise SystemExit(f"the page names this machine: {LEAKS.search(text)[0]!r}")
    if len(page.encode()) > PAGE_MAX:
        raise SystemExit(f"the page is {len(page.encode()) // 1024} KB (4 MB at most)")
    return page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--template", type=Path, default=REPO / "themes/_kit/guide.html")
    parser.add_argument("--out", type=Path, default=REPO / "frontend/public/guides/make-a-theme.html")
    args = parser.parse_args()
    page = render(args.template.read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page)
    print(f"{args.out.name}: {len(page.encode()) // 1024} KB, {page.count('<img ')} pictures")


if __name__ == "__main__":
    main()
