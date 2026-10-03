"""The theme pipeline's command line (standard library only; run from the repository):

PYTHONPATH=backend python3 -m houseos.theme_kit <command>

new <id> [--from <id>] [--scheme dark|light]   start a theme folder in themes/
build                                          themes/ → frontend/src/design/generated/
check <id>|--all                               every automated check; writes REPORT.md
tokens                                         the token catalogue (the authoring reference)
canary                                         remake themes/canary (the debug theme)
pack <id>                                      <id>.houseos-theme, to share or install
font <id> <fontsource-id> [--role display|body|mono] [--weights 400,700] [--italic]
                                               an OFL family into themes/<id>/fonts (+ its licence)
"""

import argparse
import json
import shutil
import sys

from . import build as b, check as c, font as f, pack as p, tokens as t


def new(theme_id: str, source: str | None, scheme: str | None):
    t.load(source or "base")  # the source exists
    if not t.re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", theme_id):
        sys.exit("A theme id is lowercase words joined by hyphens, like linen-morning")
    folder = t.ROOT / theme_id
    if folder.exists():
        sys.exit(f"themes/{theme_id} already exists")
    templates = t.ROOT / "_studio/templates"
    if source and source != "base":
        shutil.copytree(t.ROOT / source, folder, ignore=shutil.ignore_patterns("REPORT.md", "card-*.webp"))
    else:
        folder.mkdir()
        for name in ("tokens.json", "BRIEF.md"):
            shutil.copy2(templates / name, folder / name)
        shutil.copy2(templates / "theme.json", folder / "theme.json")
    manifest = json.loads((folder / "theme.json").read_text())
    manifest.update(id=theme_id, version=1)
    if scheme:
        manifest["schemes"] = [scheme]
    if scheme == "light" and (not source or source == "base"):
        # A light ground needs darker colours to read: start from Base's checked light seeds.
        tree = json.loads((folder / "tokens.json").read_text())
        light = t.read(t.ROOT / "base/tokens.light.json").get("seed", {})
        tree["seed"].update({k: v for k, v in light.items() if not k.startswith("$")})
        (folder / "tokens.json").write_text(json.dumps(tree, indent=2, ensure_ascii=False) + "\n")
    (folder / "theme.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(
        f"Made themes/{theme_id}. Next: write BRIEF.md, set the seeds in tokens.json, then build and check."
    )


def check(theme_id: str) -> bool:
    results, matrix = c.check(theme_id)
    (t.ROOT / theme_id / "REPORT.md").write_text(c.report(theme_id, results, matrix))
    for name, status, detail in results:
        mark = {"pass": "✓", "warn": "!", "fail": "✗"}[status]
        print(f"{mark} {name}" + (f": {detail}" if detail and status != "pass" else ""))
    print(f"{theme_id}: {'FAIL' if results.failed else 'PASS'} (REPORT.md written)")
    return not results.failed


def canary():
    """The debug theme: every colour a different loud value, odd radii and a typewriter face, so a
    screen drawn in it shows at once anything that doesn't come from a token (tests/theme-canary)."""
    base = t.load("base")
    tree: dict = {}
    names = [row["token"] for row in t.catalogue(base)]
    colours = [n for n in names if n.startswith("color.")]
    for i, name in enumerate(colours):
        node = tree
        for part in name.split(".")[:-1]:
            node = node.setdefault(part, {})
        node[name.split(".")[-1]] = {"$type": "color", "$value": f"oklch(0.72 0.2 {(i * 137.508) % 360:.1f})"}
    tree["font"] = {
        "$type": "fontFamily",
        **{k: {"$value": ["Courier New", "monospace"]} for k in ("display", "body", "mono")},
    }
    tree["radius"] = {
        "$type": "dimension",
        "none": {"$value": 1},
        **{k: {"$value": 17} for k in ("xs", "s", "m", "l", "xl", "full")},
    }
    folder = t.ROOT / "canary"
    folder.mkdir(exist_ok=True)
    (folder / "tokens.json").write_text(json.dumps(tree, indent=1) + "\n")
    manifest = {
        "id": "canary", "schema": 1, "version": 1, "debug": True, "hidden": True,
        "names": {"en": "Canary", "fr": "Canari"},
        "description": {"en": "Debug: shows what doesn't follow the theme.", "fr": "Débogage : montre ce qui ne suit pas le thème."},
        "schemes": ["dark"], "density": "comfortable",
        "fonts": {"display": "system", "body": "system", "mono": "system"},
        "slots": {}, "author": "HouseOS", "license": "MIT",
    }  # fmt: skip
    (folder / "theme.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"themes/canary: {len(colours)} colours")


def font(theme_id: str, fontsource_id: str, role: str | None, weights: str, italic: bool):
    folder = t.load(theme_id).folder
    family = f.add(folder, fontsource_id, tuple(int(w) for w in weights.split(",")), italic)
    if role:
        manifest = json.loads((folder / "theme.json").read_text())
        manifest["fonts"][role] = family
        (folder / "theme.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        tree = t.read(folder / "tokens.json")
        fallback = {"display": "serif", "body": "sans-serif", "mono": "monospace"}[role]
        tree.setdefault("font", {"$type": "fontFamily"})[role] = {"$value": [family, fallback]}
        (folder / "tokens.json").write_text(json.dumps(tree, indent=2, ensure_ascii=False) + "\n")
    print(f"{family} is in themes/{theme_id}/fonts" + (f" and set as the {role} face" if role else ""))


def tokens():
    rows = t.catalogue(t.load("base"))
    print("| Token | CSS | Type | Themeable | Base | What it is for |\n|---|---|---|---|---|---|")
    for row in rows:
        print(
            f"| `{row['token']}` | `{row['css']}` | {row['type']} | {row['themeable']} | `{row['base']}` | {row['description']} |"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="theme_kit", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    n = sub.add_parser("new")
    n.add_argument("id")
    n.add_argument("--from", dest="source")
    n.add_argument("--scheme", choices=t.SCHEMES)
    sub.add_parser("build")
    k = sub.add_parser("check")
    k.add_argument("id", nargs="?")
    k.add_argument("--all", action="store_true")
    sub.add_parser("tokens")
    sub.add_parser("canary")
    a = sub.add_parser("pack")
    a.add_argument("id")
    o = sub.add_parser("font")
    o.add_argument("id")
    o.add_argument("fontsource")
    o.add_argument("--role", choices=("display", "body", "mono"))
    o.add_argument("--weights", default="400,700")
    o.add_argument("--italic", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            new(args.id, args.source, args.scheme)
        elif args.command == "build":
            for name in b.build():
                print(f"wrote frontend/src/design/generated/{name}")
        elif args.command == "check":
            ids = [x.id for x in b.bundled() if not x.manifest.get("debug")] if args.all else [args.id]
            if not all([check(theme_id) for theme_id in ids]):
                sys.exit(1)
        elif args.command == "tokens":
            tokens()
        elif args.command == "canary":
            canary()
        elif args.command == "pack":
            print(p.pack(args.id))
        elif args.command == "font":
            font(args.id, args.fontsource, args.role, args.weights, args.italic)
    except t.ThemeError as error:
        sys.exit(f"theme_kit: {error}")


if __name__ == "__main__":
    main()
