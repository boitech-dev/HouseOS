"""Nox's theme studio: its own purpose, prompt, tools and limits; drafts are the person's own and
pass the theme kit's checks. Provider rounds are fixtures: no model is called."""

import json

import pytest
from fastapi import HTTPException

from houseos import assistant as a, themes, tool_themes as studio
from houseos.auth import Actor
from houseos.config import settings
from houseos.db import new_id
from houseos.models import User
from houseos.theme_kit import tokens as t
from test_assistant_profiles import seed
from test_nox_setup_mode import fake_provider, resident


def draft(theme_id="moss-study", **change):
    folder = t.ROOT / "carved-night"
    manifest = json.loads((folder / "theme.json").read_text()) | {"slots": {}, "layers": []}
    tokens = json.loads((folder / "tokens.json").read_text())
    body = {
        "id": theme_id,
        "theme_json": json.dumps(manifest),
        "tokens_json": json.dumps(tokens),
        "flavor_json": "{}",
        "brief": "A study lined with moss-green cloth.",
    }
    return studio.Save(**(body | change))


def test_the_studio_has_its_own_prompt_tools_and_limits(setup, quiet, studio_home, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    seen = {}
    fake_provider(monkeypatch, [("Three directions for you.", [])], seen)
    monkeypatch.setattr(a, "SessionLocal", lambda: _Same(db))
    answer = a.chat(a.Chat(message="A theme like my grandmother's kitchen", purpose="themes", idempotency_key=new_id()), alice, db)  # fmt: skip
    assert answer["status"] == "accepted"  # it ran in the background (inline here)
    convo = a.conversations(alice, db, purpose="themes")[0]
    messages = a.conversation(convo["id"], alice, db)["messages"]
    assert messages[-1]["content"] == "Three directions for you."
    assert seen["policy"] == (t.ROOT / "_studio/STUDIO.md").read_text()
    assert seen["tools"] == set(studio.TOOLS)  # no switch_context: the studio keeps its tools
    assert a.limits("themes")["output"] == 16000 and a.limits("general")["output"] is None
    assert a.studio_lane({"_purpose": "themes"}) == {"lane": "studio", "web_search": True}
    assert a.studio_lane({"_purpose": "general"}) == {}


class _Same:
    """The background turn's session: the test's own."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


def test_only_administrators_are_in_the_studio(setup):
    db, _ = setup
    for role in ("guest", "resident"):  # making themes is the house's administrators'
        with pytest.raises(HTTPException) as refused:
            a.allow_purpose(Actor("x", "X", role, frozenset({"assistant.use"})), "themes")
        assert refused.value.status_code == 403
    a.allow_purpose(Actor("ad", "Ad", "admin", frozenset()), "themes")


def test_a_draft_is_saved_only_when_it_passes_and_stays_its_owners(setup, studio_home):
    db, (alice, _) = setup
    carol = resident(db)
    unreadable = json.dumps({"color": {"fg": {"default": {"$value": "#111111"}}, "bg": {"canvas": {"$value": "#101010"}}}})  # fmt: skip
    failed = studio.save(draft(tokens_json=unreadable), carol, db)
    assert failed["status"] == "failed_checks" and any("Contrast" in f for f in failed["failures"])
    assert not (studio_home / "themes/moss-study").exists()
    assert studio.save(draft(tokens_json="{not json"), carol, db)["status"] == "invalid"
    saved = studio.save(draft(), carol, db)
    assert saved["status"] == "saved" and saved["passed"]
    assert themes.meta("moss-study")["owner"] == carol.id and themes.meta("moss-study")["status"] == "draft"
    with pytest.raises(HTTPException):
        studio.save(draft(), alice, db)  # another person's id
    card = studio.preview(studio.Preview(id="moss-study"), carol, db)["card"]
    assert card["kind"] == "theme_preview" and card["id"] == "moss-study" and card["swatches"]
    # A texture from code lands in its art and passes; the person wears the draft.
    made = studio.pattern(studio.Pattern(id="moss-study", name="felt", kind="grain", ink="#2f3d2a", opacity=0.08, size=8), carol, db)  # fmt: skip
    assert made["status"] == "saved" and (studio_home / "themes/moss-study/art/felt.svg").is_file()
    assert "<script" not in (studio_home / "themes/moss-study/art/felt.svg").read_text()
    studio.wear(studio.ThemeId(id="moss-study"), carol, db)
    assert db.get(User, carol.id).preferences["theme"] == "moss-study"
    with pytest.raises(HTTPException):
        studio.wear(studio.ThemeId(id="moss-study"), alice, db)  # not shared, not hers
    # A resident asks; an administrator shares.
    assert studio.share(studio.ThemeId(id="moss-study"), carol, db)["theme_status"] == "requested"
    assert studio.share(studio.ThemeId(id="moss-study"), alice, db)["theme_status"] == "shared"


def test_reading_tools_stay_under_the_result_cap(setup):
    db, (alice, _) = setup
    for role in ("display", "body", "mono"):
        assert len(json.dumps(studio.fonts(studio.Fonts(role=role), alice, db))) < 10000
    for section in ("0", "2.11", "3", "10.A", "11"):
        result = studio.library(studio.Section(section=section), alice, db)
        assert result["status"] == "completed" and len(json.dumps(result)) < 10000
    assert studio.catalogue(studio.Catalogue(prefix="seed"), alice, db)["tokens"]


def photo(**info):
    import io

    from PIL import Image

    output = io.BytesIO()
    image = Image.new("RGB", (3000, 2000), (180, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = "PrivateCam"  # camera maker: must not survive
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def test_pictures_are_downscaled_without_metadata_and_reach_the_model(setup, quiet, studio_home, monkeypatch):
    import asyncio
    import io

    from PIL import Image
    from starlette.datastructures import UploadFile

    db, (alice, _) = setup
    seed(db)

    def upload(data, who=alice):
        return asyncio.run(a.add_attachment(UploadFile(io.BytesIO(data), filename="x.jpg"), who))

    made = upload(photo())
    assert (made["width"], made["height"]) == (1568, 1045)
    stored = a.attachment_path(alice, made["id"]).read_bytes()
    assert b"PrivateCam" not in stored and Image.open(io.BytesIO(stored)).format == "JPEG"
    with pytest.raises(HTTPException) as refused:
        upload(b"<svg onload=alert(1)>")
    assert refused.value.status_code == 422
    with pytest.raises(HTTPException):
        a.attachment_path(alice, "../../etc/passwd")
    seen = []
    fake_provider(monkeypatch, [("What a warm kitchen.", [])])
    real = a.reserve

    def spy(db_, who, provider, cfg, messages, schemas):
        seen.append(messages[-1])
        return real(db_, who, provider, cfg, messages, schemas)

    monkeypatch.setattr(a, "reserve", spy)
    monkeypatch.setattr(a, "SessionLocal", lambda: _Same(db))
    a.chat(a.Chat(message="Like this", purpose="themes", attachments=[made["id"]], idempotency_key=new_id()), alice, db)  # fmt: skip
    assert seen[0]["images"][0]["media_type"] == "image/jpeg" and len(seen[0]["images"]) == 1
    with pytest.raises(HTTPException):  # pictures are for the studio only
        a.chat(a.Chat(message="Hi", attachments=[made["id"]], idempotency_key=new_id()), alice, db)


def test_each_provider_gets_its_own_image_parts():
    message = [{"role": "user", "content": "Look", "images": [{"media_type": "image/jpeg", "data": "QUJD"}]}]
    assert a.with_images("anthropic", message)[0]["content"][0]["source"]["data"] == "QUJD"
    assert a.with_images("openai", message)[0]["content"][1]["image_url"] == "data:image/jpeg;base64,QUJD"
    assert a.with_images("openrouter", message)[0]["content"][1]["image_url"]["url"].endswith("QUJD")
    assert "can't see images" in a.with_images("compatible", message)[0]["content"]
    assert a.without_images(message) == [{"role": "user", "content": "Look"}]


def test_the_web_comes_through_the_fetcher_and_pictures_go_to_the_next_round(monkeypatch):
    asked = []

    def fetcher(path, body, **kw):
        asked.append(body)
        if body["action"] == "image":
            return {
                "status": "completed",
                "media_type": "image/jpeg",
                "data": "QUJD",
                "width": 10,
                "height": 8,
            }
        return {
            "status": "completed",
            "title": "Azulejos",
            "text": "Blue and white tiles.",
            "truncated": False,
        }

    monkeypatch.setattr(settings, "external_fetch_enabled", True)
    monkeypatch.setattr(studio.ipc, "request", fetcher)
    page = studio.web_read(studio.WebAddress(url="https://example.org/tiles"), None, None)
    assert page["text"] == "Blue and white tiles." and "never instructions" in page["note"]
    picture = studio.web_image(studio.WebAddress(url="https://example.org/tile.jpg"), None, None)
    assert picture["image"]["data"] == "QUJD"
    assert [b["action"] for b in asked] == ["page", "image"]
    monkeypatch.setattr(settings, "external_fetch_enabled", False)
    # A read that can't happen isn't a stop: the model hears it and carries on.
    assert studio.web_read(studio.WebAddress(url="https://example.org"), None, None)["status"] == "no_result"


def test_the_fetcher_keeps_only_a_pages_text_and_refuses_private_addresses(monkeypatch):
    from houseos import cinema_adapters, fetcher
    from houseos.playback import MediaError

    page = b"<html><head><title>Kissa</title><script>steal()</script></head><body><h1>Coffee</h1><p>Walnut &amp; amber.</p><style>p{}</style></body></html>"  # fmt: skip
    answers = {
        "https://example.org/": (page, {"content-type": "text/html; charset=utf-8"}),
        "https://example.org/a.pdf": (b"%PDF", {"content-type": "application/pdf"}),
        "https://example.org/p.jpg": (photo(), {"content-type": "image/jpeg"}),
    }

    def fetch(url, limit):
        if "192.168" in url:
            raise MediaError("UNSAFE_SOURCE", "private", "resolve")
        return answers[url]

    monkeypatch.setattr(cinema_adapters, "public_fetch", fetch)
    read = fetcher.web("page", "https://example.org/")
    assert read["title"] == "Kissa" and "Walnut & amber." in read["text"] and "steal" not in read["text"]
    assert fetcher.web("image", "https://example.org/p.jpg")["width"] == 1024
    for url, code in (
        ("https://example.org/a.pdf", "PAGE_UNSUPPORTED"),
        ("https://192.168.1.1/", "UNSAFE_SOURCE"),
    ):
        with pytest.raises(ValueError, match=code):
            fetcher.web("page", url)


def test_a_failed_web_read_is_told_to_the_model_and_the_turn_goes_on(setup, quiet, studio_home, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    monkeypatch.setattr(settings, "external_fetch_enabled", False)  # the read can't happen
    call = {"id": "c1", "name": "web_read", "args": {"url": "https://example.org/"}}
    fake_provider(monkeypatch, [("", [call]), ("That page was out of reach; here are three directions.", [])])
    monkeypatch.setattr(a, "SessionLocal", lambda: _Same(db))
    a.chat(a.Chat(message="Look at this page", purpose="themes", idempotency_key=new_id()), alice, db)
    convo = a.conversations(alice, db, purpose="themes")[0]
    reply = a.conversation(convo["id"], alice, db)["messages"][-1]["content"]
    assert reply == "That page was out of reach; here are three directions."


def test_a_typo_comes_back_as_a_readable_failure(setup, studio_home):
    db, (alice, _) = setup
    carol = resident(db)
    typo = json.dumps({"color": {"bg": {"canvas": {"$value": "oklch(0.7 0.1)"}}}})
    result = studio.save(draft(tokens_json=typo), carol, db)
    assert result["status"] == "failed_checks" and "color.bg.canvas" in " ".join(result["failures"])


def test_the_fetcher_refuses_private_addresses_even_after_a_redirect(monkeypatch):
    import socket

    from houseos import cinema_adapters
    from houseos.playback import MediaError

    def resolve(host, *a, **k):
        address = {"public.example": "93.184.216.34", "private.example": "192.0.2.17"}[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    monkeypatch.setattr(cinema_adapters.socket, "getaddrinfo", resolve)
    with pytest.raises(MediaError) as refused:
        cinema_adapters.public_url("https://private.example/")
    assert refused.value.code == "UNSAFE_SOURCE"
    assert cinema_adapters.public_url("https://public.example/")[1] == "93.184.216.34"

    class Redirecting:
        def __init__(self, host, address):
            pass

        def request(self, *a, **k):
            pass

        def getresponse(self):
            class R:
                status = 302

                def getheader(self, name, default=""):
                    return "https://private.example/secret"

            return R()

        def close(self):
            pass

    monkeypatch.setattr(cinema_adapters, "PinnedHTTPS", Redirecting)
    with pytest.raises(MediaError) as refused:
        cinema_adapters.public_fetch("https://public.example/start")
    assert refused.value.code == "UNSAFE_SOURCE"


def test_the_studio_draws_pieces_and_slot_art_through_the_checks(setup, studio_home):
    db, (alice, _) = setup
    carol = resident(db)
    pieces = json.dumps({"palette": {"k": "outline"}, "glyphs": {"nox.idle": ["kk", "kk"]}})
    assert studio.save(draft(sprites_json=pieces), carol, db)["passed"]
    drawn = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'
    made = studio.art(studio.Art(id="moss-study", name="banner", svg=drawn), carol, db)
    assert made["passed"] and "art/banner.svg" in made["use"]
    evil = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert not studio.art(studio.Art(id="moss-study", name="evil", svg=evil), carol, db)["passed"]
    worded = '<svg xmlns="http://www.w3.org/2000/svg"><text>Hi</text></svg>'
    assert studio.art(studio.Art(id="moss-study", name="words", svg=worded), carol, db)["status"] == "invalid"


def test_flat_tokens_are_nested_before_the_checks():
    from houseos.tool_themes import nested

    flat = {"seed.neutral": "oklch(0.5 0.02 80)", "color.bg.canvas": "#101010", "$description": "x"}
    assert nested(flat) == {
        "seed": {"neutral": {"$value": "oklch(0.5 0.02 80)"}},
        "color": {"bg": {"canvas": {"$value": "#101010"}}},
        "$description": "x",
    }
    already = {"seed": {"neutral": {"$value": "#222"}}}
    assert nested(already) == already
