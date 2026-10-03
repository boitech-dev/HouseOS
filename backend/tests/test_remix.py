"""Remix: a theme made by hand in the Workshop, through the studio's own checks."""

import io
import json

import pytest
from fastapi import HTTPException
from PIL import Image

from houseos import remix, themes
from test_theme_studio import resident


def test_remix_starts_edits_previews_and_saves_only_what_passes(setup, studio_home):
    db, (alice, _) = setup
    carol = resident(db)
    started = remix.start(remix.Start(source="linen-morning", id="carol-linen", names={"en": "Carol's", "fr": "À Carol"}), carol, db)  # fmt: skip
    assert started["passed"]
    kept = json.loads((studio_home / "themes/carol-linen/theme.json").read_text())
    draft = remix.files("carol-linen", carol)
    assert draft["theme"]["names"]["en"] == "Carol's" and draft["theme"]["id"] == "carol-linen"
    # A change, previewed without being kept: its CSS is marked for the preview only.
    draft["theme"]["parts"] = {"panel": "flat"}
    body = remix.Draft(theme=draft["theme"], tokens=draft["tokens"], flavor=draft["flavor"], sprites={"palette": {"k": "outline"}, "glyphs": {"nox.idle": ["kk"]}})  # fmt: skip
    seen = remix.preview("carol-linen", body, carol)
    assert seen["passed"], seen.get("failures")
    assert '[data-theme="carol-linen--preview"]' in seen["css"]
    assert seen["info"]["parts"]["panel"] == "flat" and seen["info"]["sprites"]["glyphs"]["nox.idle"]
    assert json.loads((studio_home / "themes/carol-linen/theme.json").read_text()) == kept
    # Saved: kept. An unreadable change: refused with the failure, nothing changes.
    assert remix.save("carol-linen", body, carol, db)["passed"]
    bad = remix.Draft(theme=draft["theme"], tokens={"color": {"fg": {"default": {"$value": "#fbf6ec"}}}})
    refused = remix.save("carol-linen", bad, carol, db)
    assert not refused.get("passed") and any("Contrast" in f for f in refused["failures"])
    assert json.loads((studio_home / "themes/carol-linen/theme.json").read_text())["parts"] == {"panel": "flat"}
    # Someone else's draft stays theirs.
    with pytest.raises(HTTPException):
        remix.files("carol-linen", alice)


def test_pictures_are_reencoded_small_and_must_be_pictures(setup, studio_home):
    db, _ = setup
    carol = resident(db)
    made0 = remix.start(remix.Start(source="base", id="carol-art", names={"en": "Art", "fr": "Art"}), carol, db)
    assert made0["passed"], made0
    big = io.BytesIO()
    Image.effect_noise((2400, 1200), 90).convert("RGB").save(big, "PNG")

    class Upload:
        def __init__(self, data):
            self.file = io.BytesIO(data)

    made = remix.upload_art("carol-art", "banner", False, Upload(big.getvalue()), carol)
    kept = studio_home / "themes/carol-art" / made["path"]
    assert made["passed"] and kept.suffix == ".webp" and kept.stat().st_size <= 200_000
    assert max(Image.open(kept).size) <= 1600
    with pytest.raises(HTTPException):
        remix.upload_art("carol-art", "evil", False, Upload(b"<svg><script>alert(1)</script></svg>"), carol)


def test_bundled_theme_art_is_served_to_anyone_and_nothing_else():
    served = themes.bundled_file("zabiwa", "art", "crest-cross.webp")
    assert str(served.path).endswith("themes/zabiwa/art/crest-cross.webp")
    for theme_id, kind, name in [
        ("linen-morning", "art", "../theme.json"),
        ("linen-morning", "tokens", "x.svg"),
        ("_schema", "art", "slots.json"),
        ("nobody", "art", "x.svg"),
    ]:
        with pytest.raises(HTTPException):
            themes.bundled_file(theme_id, kind, name)
