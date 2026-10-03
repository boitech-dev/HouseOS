"""The theme pipeline: colour maths, the bundled themes, the generated CSS, checks and packs."""

import hashlib
import io
import json
import shutil
import zipfile

import pytest

from houseos.theme_kit import build, check, color, pack, tokens as t


def test_colour_maths():
    color.self_check()
    dark, light = color.parse("#0e1020"), color.parse("#efe7d6")
    assert round(color.contrast(light, dark), 1) == 15.3
    assert color.contrast(color.parse("#ffffff80"), dark) < color.contrast(color.parse("#ffffff"), dark)


def test_generated_css_matches_the_theme_folders():
    """`npm run build` uses the committed CSS: it must be what the themes say (run `theme_kit build`)."""
    fresh = build.build(out=None)
    for name, text in fresh.items():
        assert (build.GENERATED / name).read_text() == text, (
            f"{name} is stale: run `python3 -m houseos.theme_kit build`"
        )
    schema = t.ROOT / "_schema/tokens.schema.json"
    assert schema.read_text() == build.token_schema(t.load("base")), "tokens.schema.json is stale: run build"
    manifest = t.ROOT / "_schema/theme.schema.json"
    assert manifest.read_text() == build.manifest_schema(), "theme.schema.json is stale: run build"


def test_every_bundled_theme_passes_and_canary_covers_every_colour():
    for theme in build.bundled():
        if theme.manifest.get("debug"):
            continue
        results, _ = check.check(theme.id)
        assert not results.failed, (theme.id, results.failed)
    base = t.load("base")
    colours = {row["token"] for row in t.catalogue(base) if row["token"].startswith("color.")}
    canary = {name for name in t.flatten(t.read(t.ROOT / "canary/tokens.json")) if name.startswith("color.")}
    assert colours == canary, "remake it: python3 -m houseos.theme_kit canary"


def test_every_theme_block_is_complete_and_rooms_are_resolved():
    css = build.build(out=None)["themes.css"]
    base = t.load("base")
    names = set(t.variables(base, "dark", base))
    for theme in build.bundled():
        values = t.variables(theme, theme.schemes[0], base)
        assert set(values) == names, theme.id  # a preview inside another theme shows only this one
        assert f'[data-theme="{theme.id}"][data-room="listen"]' in css
    assert "var(" not in css  # final values only: nothing to go stale


@pytest.fixture
def themes(tmp_path):
    root = tmp_path / "themes"
    shutil.copytree(t.ROOT / "base", root / "base")
    shutil.copytree(t.ROOT / "carved-night", root / "night")
    manifest = json.loads((root / "night/theme.json").read_text())
    (root / "night/theme.json").write_text(json.dumps({**manifest, "id": "night"}))
    return root


def test_checks_catch_what_the_contract_forbids(themes):
    folder = themes / "night"
    data = json.loads((folder / "tokens.json").read_text())
    data["color"]["fg"]["muted"] = {"$value": "#2a2d50"}  # unreadable on the night
    data["z"] = {"dock": {"$type": "number", "$value": 99}}  # fixed by the contract
    data["color"]["room"]["listen"] = data["color"]["room"]["watch"] = {"$value": "#f0ba72"}  # the same
    (folder / "tokens.json").write_text(json.dumps(data))
    (folder / "flavor.json").write_text(
        json.dumps({"title.dj.name": {"en": "The DJ"}, "room.listen.kicker": {"en": "x", "fr": "x"}})
    )
    (folder / "art").mkdir(exist_ok=True)
    (folder / "art/moon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    )
    (folder / "hack.js").write_text("alert(1)")
    results, _ = check.check("night", themes)
    failed = " ".join(f"{name}: {detail}" for name, _, detail in results.failed)
    for expected in ("--c-fg-muted on --c-bg-canvas", "z.dock is fixed", "--c-room-listen and --c-room-watch",
                     "title.dj.name: needs en and fr", "room.listen.kicker: not a flavour slot", "moon.svg: scripts",
                     "hack.js: themes are data only"):  # fmt: skip
        assert expected in failed, (expected, failed)


def test_a_theme_never_changes_sizes(themes):
    """Every theme fits the same screens: spacing, chrome and icon boxes are fixed, and text keeps
    to its band (a face may be tuned 1px, a display title 15 %)."""
    folder = themes / "night"
    data = json.loads((folder / "tokens.json").read_text())
    data["space"] = {"4": {"$type": "dimension", "$value": 20}}
    data["chrome"] = {"dock": {"$type": "dimension", "$value": 68}}
    data["icon"]["m"] = {"$type": "dimension", "$value": 24}
    data["text"]["action"]["$value"]["fontSize"] = 18
    data["text"]["display-l"]["$value"]["fontSize"] = 44
    data["text"]["label"]["$value"]["letterSpacing"] = 0.3
    data["text"]["action"]["$value"]["textTransform"] = "uppercase"
    data["material"]["surface"]["border"] = {"$value": "6px double {color.border.subtle}"}
    data["material"]["paper"]["rotate"] = {"$type": "string", "$value": "12deg"}
    (folder / "tokens.json").write_text(json.dumps(data))
    manifest = json.loads((folder / "theme.json").read_text())
    (folder / "theme.json").write_text(json.dumps({**manifest, "density": "airy"}))
    results, _ = check.check("night", themes)
    failed = " ".join(f"{name}: {detail}" for name, _, detail in results.failed)
    for expected in ("space.4 is fixed", "chrome.dock is fixed", "icon.m is fixed",
                     "action is 18px (Base 15px; 16px at most)", "display-l is 44px", "label tracking 0.3em",
                     "action keeps Base's case", "material.surface.border: an edge is 1px",
                     "material.paper.rotate: paper tilts 2deg at most"):  # fmt: skip
        assert expected in failed, (expected, failed)
    # "airy" is a word for the brief: spacing stays Base's.
    night = t.variables(t.load("night", themes), "dark", t.load("base", themes))
    assert night["--space-5"] == "24px"


def test_unknown_tokens_and_loops_are_named(themes):
    folder = themes / "night"
    (folder / "tokens.json").write_text(
        json.dumps({"color": {"bg": {"cnavas": {"$type": "color", "$value": "#000"}}}})
    )
    with pytest.raises(t.ThemeError, match="Unknown token 'color.bg.cnavas'"):
        t.variables(t.load("night", themes), "dark", t.load("base", themes))
    (folder / "tokens.json").write_text(
        json.dumps(
            {
                "color": {
                    "bg": {
                        "canvas": {"$value": "{color.bg.surface}"},
                        "surface": {"$value": "{color.bg.canvas}"},
                    }
                }
            }
        )
    )
    with pytest.raises(t.ThemeError, match="Reference loop"):
        t.variables(t.load("night", themes), "dark", t.load("base", themes))


def test_packs_round_trip_and_refuse_anything_but_theme_data(themes, tmp_path):
    made = pack.pack("night", themes, tmp_path / "night.houseos-theme")
    installed = tmp_path / "installed"
    shutil.copytree(themes / "base", installed / "base")
    theme_id, results = pack.unpack(made.read_bytes(), installed, "moonlit")
    assert theme_id == "moonlit" and not results.failed and (installed / "moonlit/tokens.json").exists()

    def forged(extra: dict[str, bytes], sums=True):
        buffer = io.BytesIO()
        with zipfile.ZipFile(made) as source, zipfile.ZipFile(buffer, "w") as z:
            files = {n: source.read(n) for n in source.namelist() if n != "checksums.json"} | extra
            for name, data in files.items():
                z.writestr(name, data)
            z.writestr(
                "checksums.json",
                json.dumps({n: hashlib.sha256(d).hexdigest() for n, d in files.items()} if sums else {}),
            )
        return buffer.getvalue()

    for bad, message in (
        (forged({"../../evil.json": b"{}"}), "only theme data"),
        (forged({"art/x.js": b"alert(1)"}), "only theme data"),
        (forged({}, sums=False), "damaged"),
        (b"not a zip", "Not a HouseOS theme pack"),
    ):
        with pytest.raises(t.ThemeError, match=message):
            pack.unpack(bad, installed)
    broken = forged(
        {
            "tokens.json": json.dumps(
                {"color": {"fg": {"default": {"$type": "color", "$value": "#101010"}}}}
            ).encode()
        }
    )
    theme_id, results = pack.unpack(broken, installed, "unreadable")
    assert results.failed and not (installed / "unreadable").exists()  # failing packs are not kept


def test_fonts_come_only_under_the_ofl_with_french_and_their_licence(tmp_path):
    from houseos.theme_kit import font

    def meta(**change):
        info = {"family": "Test Serif", "license": "OFL-1.1", "subsets": ["latin", "latin-ext"],
                "weights": [400, 700], "styles": ["normal"], "variants": {
                    w: {"normal": {s: {"url": {"woff2": f"https://cdn/{s}-{w}.woff2"}} for s in ("latin", "latin-ext")}}
                    for w in ("400", "700")}}  # fmt: skip
        return json.dumps(info | change).encode()

    def serve(answer):
        def get(url, limit):
            if "api.fontsource" in url:
                return answer
            return b"licence text" if url.endswith("OFL.txt") else b"wOF2" + b"0" * 32

        return get

    assert font.add(tmp_path, "test-serif", (400, 700), get=serve(meta())) == "Test Serif"
    names = sorted(p.name for p in (tmp_path / "fonts").iterdir())
    assert names == ["test-serif-OFL-LICENSE.txt"] + [
        f"test-serif-{s}-{w}-normal.woff2" for s in ("latin", "latin-ext") for w in (400, 700)
    ]
    for change, words in (
        ({"license": "Apache-2.0"}, "Open Font License"),
        ({"subsets": ["latin"]}, "Latin Extended"),
        ({"weights": [400]}, "no weight 700"),
    ):
        with pytest.raises(t.ThemeError, match=words):
            font.add(tmp_path, "test-serif", (400, 700), get=serve(meta(**change)))
    with pytest.raises(t.ThemeError, match="Fontsource id"):
        font.add(tmp_path, "../etc", get=serve(meta()))


def test_parts_slots_pieces_and_titles_are_the_themes_to_shape(themes):
    """A theme styles each part, picks size-neutral variants, fills slots its own way,
    redraws pieces by id and names the house titles; anything else is refused by name."""
    folder = themes / "night"
    manifest = json.loads((folder / "theme.json").read_text())
    (folder / "art").mkdir(exist_ok=True)
    (folder / "art/banner.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    good = {
        **manifest,
        "parts": {"panel": "flat", "nowbar": "docked"},
        "slots": {**manifest.get("slots", {}), "header.banner": {"image": "art/banner.png", "rendering": "smooth", "fit": "contain"}},
    }
    (folder / "theme.json").write_text(json.dumps(good))
    data = json.loads((folder / "tokens.json").read_text())
    data["part"] = {"dock": {"border": {"$value": "1px dashed #445566"}}}
    data["ease"] = {**data.get("ease", {}), "standard": {"$value": "steps(4, end)"}}
    (folder / "tokens.json").write_text(json.dumps(data))
    (folder / "sprites.json").write_text(json.dumps({
        "palette": {"k": "outline", "e": "accent"},
        "glyphs": {"avatar.moon": ["kk", "ke"], "title.dj": [".k.", "kek"]},
    }))  # fmt: skip
    (folder / "flavor.json").write_text(json.dumps({
        "title.dj.name": {"en": "Station master", "fr": "Chef de gare"},
        "title.star.mark": {"en": "◆", "fr": "◆"},
    }))  # fmt: skip
    results, _ = check.check("night", themes)
    assert not results.failed, results.failed
    info = build.entry(t.load("night", themes), t.load("base", themes))
    assert info["parts"] == {"header": "plain", "panel": "flat", "dock": "flush", "nowbar": "docked"}
    assert info["sprites"]["glyphs"]["title.dj"] == [".k.", "kek"]
    # Each of those, wrong, is named.
    (folder / "theme.json").write_text(json.dumps({**good, "parts": {"panel": "huge"},
        "slots": {"header.banner": {"image": "art/banner.png", "fit": "tile"}}}))  # fmt: skip
    data["part"]["dock"]["border"] = {"$value": "4px solid #445566"}
    data["ease"]["standard"] = {"$value": "linear(0, 1)"}
    (folder / "tokens.json").write_text(json.dumps(data))
    (folder / "sprites.json").write_text(json.dumps({
        "palette": {"k": "outline"}, "glyphs": {"avatar.dragon": ["k"], "nox.idle": ["k" * 20]},
    }))  # fmt: skip
    (folder / "flavor.json").write_text(json.dumps({"title.boss.name": {"en": "Boss", "fr": "Chef"}}))
    results, _ = check.check("night", themes)
    failed = " ".join(f"{name}: {detail}" for name, _, detail in results.failed)
    for expected in ("parts.panel", "header.banner: an image takes", "part.dock.border: an edge is 1px",
                     "ease.standard: an easing", "avatar.dragon: not a piece", "nox.idle: 16 × 16",
                     "title.boss.name: not a house title"):  # fmt: skip
        assert expected in failed, (expected, failed)


def test_theme_copies_leave_modes_behind(tmp_path):
    """The house's service may not set setgid bits (RestrictSUIDSGID): copies take files only."""
    source = tmp_path / "src"
    (source / "art").mkdir(parents=True)
    (source / "art/a.png").write_bytes(b"x")
    (source / "house.json").write_text("{}")
    source.chmod(0o2770)
    t.copy_tree(source, tmp_path / "dst", skip=("house.json",))
    assert (tmp_path / "dst/art/a.png").read_bytes() == b"x"
    assert not (tmp_path / "dst/house.json").exists()
    assert not (tmp_path / "dst").stat().st_mode & 0o2000


def test_surfaces_take_a_picture_in_any_fit_and_a_frame_as_a_9_slice(tmp_path):
    """Every part's surface slot: cover, contain, stretch or slice (surfaces only, with its px)."""
    from PIL import Image

    root = tmp_path / "themes"
    shutil.copytree(t.ROOT / "base", root / "base")
    shutil.copytree(t.ROOT / "_schema", root / "_schema")
    shutil.copytree(t.ROOT / "base", root / "framed")
    folder = root / "framed"
    (folder / "art").mkdir()
    Image.new("RGBA", (48, 48)).save(folder / "art/panel-frame.png")
    manifest = {**json.loads((folder / "theme.json").read_text()), "id": "framed"}

    def slots(fills):
        (folder / "theme.json").write_text(json.dumps({**manifest, "slots": fills}))
        results, _ = check.check("framed", root)
        return " ".join(detail for name, state, detail in results if name == "Art slots" and state == "fail")

    frame = {"image": "art/panel-frame.png", "rendering": "pixel", "fit": "slice", "slice": 16}
    assert slots({"panel.surface": frame, "dock.surface": {"image": "art/panel-frame.png", "fit": "stretch"}}) == ""
    assert "for surfaces" in slots({"state.empty": {**frame}})  # a frame is for a part's surface
    assert "for surfaces" in slots({"panel.surface": {**frame, "slice": 0}})
    assert "goes with fit" in slots({"panel.surface": {"image": "art/panel-frame.png", "slice": 8}})


def test_layers_move_only_what_the_kit_allows(tmp_path):
    """Layers: a picture per place, one way of moving each, frames that split evenly, faint overlays,
    and pictures for a room (a slot's "rooms") from the theme's own art."""
    from PIL import Image

    root = tmp_path / "themes"
    shutil.copytree(t.ROOT / "base", root / "base")
    shutil.copytree(t.ROOT / "_schema", root / "_schema")
    shutil.copytree(t.ROOT / "base", root / "lay")
    folder = root / "lay"
    (folder / "art").mkdir()
    Image.new("RGBA", (48, 16)).save(folder / "art/sheet.png")
    manifest = {**json.loads((folder / "theme.json").read_text()), "id": "lay"}

    def failures(**extra):
        (folder / "theme.json").write_text(json.dumps({**manifest, **extra}))
        results, _ = check.check("lay", root)
        return " ".join(d for name, state, d in results if name in ("Layers", "Art slots", "Manifest") and state == "fail")

    good = [
        {"image": "art/sheet.png", "where": "page", "fit": "repeat", "drift": [12, 0]},
        {"image": "art/sheet.png", "where": "hero", "fit": "natural", "frames": {"count": 3, "fps": 6},
         "cross": {"seconds": 8, "every": 30, "from": "right"}, "rooms": ["home"]},
        {"image": "art/sheet.png", "where": "deck", "particles": {"count": 12, "motion": "rise"}, "playing": True},
        {"image": "art/sheet.png", "where": "page", "above": True, "opacity": 0.1, "fit": "repeat"},
    ]  # fmt: skip
    assert failures(layers=good) == ""
    assert "splits" not in failures(layers=good) and "frames" in failures(
        layers=[{**good[1], "frames": {"count": 5}}]
    )
    assert "one of drift" in failures(layers=[{**good[0], "cross": {"seconds": 4}}])
    assert "above" in failures(layers=[{**good[3], "opacity": 0.5}])
    assert "where" in failures(layers=[{"image": "art/sheet.png", "where": "sky"}])
    assert "image is art" in failures(layers=[{"image": "https://example.org/x.png", "where": "page"}])
    assert "at most" in failures(layers=[good[0]] * 13)
    # A piece that answers a click: a reaction sheet of its own frame size, a small burst.
    Image.new("RGBA", (64, 16)).save(folder / "art/poke.png")
    poked = {**good[1], "poke": {"image": "art/poke.png", "frames": {"count": 4, "fps": 12}, "burst": {"image": "art/sheet.png", "count": 6}}}
    assert failures(layers=[poked]) == ""
    assert "frames of the piece" in failures(layers=[{**poked, "poke": {**poked["poke"], "frames": {"count": 3}}}])
    assert "natural piece" in failures(layers=[{**good[0], "poke": poked["poke"]}])
    assert "burst" in failures(layers=[{**poked, "poke": {**poked["poke"], "burst": {"image": "art/sheet.png", "count": 40}}}])
    assert failures(credit={"en": "Theme by someone", "fr": "Thème par quelqu'un"}) == ""
    assert "credit" in failures(credit={"en": "x" * 41, "fr": "x"})
    room = {"image": "art/sheet.png", "rendering": "pixel", "rooms": {"listen": "art/sheet.png"}}
    assert failures(slots={"header.banner": room}) == ""
    assert "rooms" in failures(slots={"header.banner": {**room, "rooms": {"attic": "art/sheet.png"}}})
