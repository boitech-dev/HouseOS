"""Installed themes: anyone who lives here designs, an administrator shares; packs are data only."""

import hashlib
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from houseos import themes
from houseos.auth import Actor, require_actor
from houseos.config import settings
from houseos.db import get_db
from houseos.theme_kit import tokens as t

ADMIN = Actor("u-admin", "Ada", "admin", frozenset())
ALICE = Actor("u-alice", "Alice", "resident", frozenset())
BOB = Actor("u-bob", "Bob", "resident", frozenset())
GUEST = Actor("u-guest", "Gus", "guest", frozenset())


class Db:
    def add(self, _):
        pass

    def commit(self):
        pass


def pack(theme_id="dusk-test", extra=None, tamper=None):
    """A pack made from Carved Night's data under another id, optionally with extra files."""
    folder = t.ROOT / "carved-night"
    manifest = json.loads((folder / "theme.json").read_text())
    manifest.update(id=theme_id, slots={}, layers=[])
    files = {
        "theme.json": json.dumps(manifest).encode(),
        "tokens.json": (folder / "tokens.json").read_bytes(),
        "flavor.json": json.dumps({"title.dj.name": {"en": "The DJ", "fr": "Le DJ"}}).encode(),
    } | (extra or {})
    sums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    if tamper:
        files[tamper] = files[tamper] + b" "
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr("checksums.json", json.dumps(sums))
    return buffer.getvalue()


@pytest.fixture
def house(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    app = FastAPI()
    app.include_router(themes.router)
    app.include_router(themes.files)
    app.dependency_overrides[get_db] = lambda: Db()
    who = {"actor": ALICE}
    app.dependency_overrides[require_actor] = lambda: who["actor"]

    def as_(actor):
        who["actor"] = actor
        return client

    with TestClient(app) as client:
        yield as_


def upload(client, data, name="x.houseos-theme"):
    return client.post("/themes/import", files={"file": (name, data, "application/zip")})


def test_draft_request_share_and_visibility(house):
    alice = house(ALICE)
    made = upload(alice, pack()).json()
    assert made["status"] == "draft" and made["mine"] and made["css"].startswith("/themes/dusk-test.css?v=")
    # A draft is its owner's (and visible to admins, who review requests); others don't see it.
    assert [i["id"] for i in house(BOB).get("/themes").json()["items"]] == []
    assert house(BOB).get("/themes/dusk-test.css").status_code == 404
    assert house(ADMIN).get("/themes").json()["items"][0]["id"] == "dusk-test"
    # The owner can ask, not share; an admin shares.
    assert house(ALICE).put("/themes/dusk-test/status", json={"status": "shared"}).status_code == 403
    assert (
        house(ALICE).put("/themes/dusk-test/status", json={"status": "requested"}).json()["status"]
        == "requested"
    )
    assert house(BOB).put("/themes/dusk-test/status", json={"status": "shared"}).status_code == 404
    assert (
        house(ADMIN).put("/themes/dusk-test/status", json={"status": "shared"}).json()["status"] == "shared"
    )
    css = house(BOB).get("/themes/dusk-test.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    # Generated here, only custom properties for this theme (and nothing from the pack).
    assert css.text.startswith("@layer theme {") and '[data-theme="dusk-test"]' in css.text
    assert "url(" not in css.text and "@import" not in css.text
    # Guests use the house's themes but don't make their own; the export round-trips.
    assert upload(house(GUEST), pack("guest-made")).status_code == 403
    exported = house(BOB).get("/themes/dusk-test/pack")
    assert exported.status_code == 200 and zipfile.ZipFile(io.BytesIO(exported.content)).read("theme.json")
    assert house(BOB).delete("/themes/dusk-test").status_code == 404
    assert house(ALICE).delete("/themes/dusk-test").json() == {"removed": "dusk-test"}
    assert house(ADMIN).get("/themes").json()["items"] == []


@pytest.mark.parametrize(
    "data, words",
    [
        (b"not a zip", "Not a HouseOS theme pack"),
        (pack(extra={"art/x.svg": b"<svg><script>alert(1)</script></svg>"}), "not allowed in SVG"),
        (pack(extra={"theme.css": b"body{display:none}"}), "theme data"),
        (pack(extra={"art/../../escape.png": b"x"}), "theme data"),
        (pack(tamper="tokens.json"), "checksum"),
        (pack("carved-night"), "can't be used"),
        (pack("Bad Id"), "can't be used"),
        (b"PK" + b"\0" * (3_600_000), "at most"),
    ],
)
def test_malicious_or_broken_packs_are_refused(house, data, words):
    answer = upload(house(ALICE), data)
    assert answer.status_code == 422, answer.text
    assert words in answer.text
    assert house(ADMIN).get("/themes").json()["items"] == []


def test_ids_belong_to_their_owner_and_checks_gate_a_theme(house, tmp_path):
    assert upload(house(ALICE), pack()).status_code == 200
    assert upload(house(BOB), pack()).status_code == 409
    assert upload(house(ALICE), pack()).status_code == 200  # the owner updates it
    unreadable = json.loads((t.ROOT / "carved-night/tokens.json").read_text())
    unreadable["color"] = {"fg": {"default": {"$value": "#101010"}}, "bg": {"canvas": {"$value": "#111111"}}}
    bad = pack("low-contrast", extra={"tokens.json": json.dumps(unreadable).encode()})
    answer = upload(house(ALICE), bad)
    assert answer.status_code == 422 and "Contrast" in answer.text
    assert not (tmp_path / "themes/low-contrast").exists()


def test_art_is_served_to_those_who_see_the_theme_and_cannot_run(house):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    alice = house(ALICE)
    assert upload(alice, pack(extra={"art/window.png": png})).status_code == 200
    art = alice.get("/themes/dusk-test/art/window.png")
    assert art.status_code == 200 and "sandbox" in art.headers["content-security-policy"]
    assert house(BOB).get("/themes/dusk-test/art/window.png").status_code == 404
    assert alice.get("/themes/dusk-test/art/..%2Ftheme.json").status_code == 404
    assert alice.get("/themes/dusk-test/other/window.png").status_code == 404


def test_textures_come_only_from_the_theme_art_and_are_served_there(house):
    tokens = json.loads((t.ROOT / "carved-night/tokens.json").read_text())
    tokens.setdefault("material", {}).setdefault("paper", {})["texture"] = {
        "$value": "url(https://x.test/a.png)"
    }
    answer = upload(house(ALICE), pack(extra={"tokens.json": json.dumps(tokens).encode()}))
    assert answer.status_code == 422 and "from the theme's own art" in answer.text
    tokens["material"]["paper"]["texture"] = {"$value": "url(art/grain.svg)"}
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="1" height="1"/></svg>'
    made = upload(
        house(ALICE), pack(extra={"tokens.json": json.dumps(tokens).encode(), "art/grain.svg": svg})
    )
    assert made.status_code == 200, made.text
    assert "url(/themes/dusk-test/art/grain.svg)" in house(ALICE).get("/themes/dusk-test.css").text


def tokens_with(**groups):
    tokens = json.loads((t.ROOT / "carved-night/tokens.json").read_text())
    for path, value in groups.items():
        node = tokens
        *parents, leaf = path.split("__")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return json.dumps(tokens).encode()


@pytest.mark.parametrize(
    "change",
    [
        {"material__paper__texture": {"$value": "none; } body { display: none } :root { --x: 0"}},
        {"material__paper__texture": {"$value": "URL(https://x.test/a.png)"}},
        {"material__paper__texture": {"$value": 'image-set("https://x.test/a.png" 1x)'}},
        {"material__paper__texture": {"$value": 'url("art/a.png)") , url(https://x.test/b.png'}},
        {"radius__card": {"$type": "string", "$value": "4px } body { color: red"}},
        {"font__display": {"$value": ['Evil", monospace; } body { x: "', "serif"]}},
        {"material__paper__shadow": {"$value": "0 0 1px red /* */"}},
    ],
)
def test_a_token_value_can_never_escape_its_declaration(house, change):
    answer = upload(house(ALICE), pack("inject", extra={"tokens.json": tokens_with(**change)}))
    assert answer.status_code == 422, answer.text
    assert house(ADMIN).get("/themes").json()["items"] == []


def test_malformed_packs_are_refused_in_words_not_crashes(house):
    manifest = json.loads((t.ROOT / "carved-night/theme.json").read_text())
    for change in ({"names": "x"}, {"fonts": ["a"]}, {"slots": []}, {"description": 3}):
        broken = pack(
            "broken", extra={"theme.json": json.dumps(manifest | {"id": "broken"} | change).encode()}
        )
        answer = upload(house(ALICE), broken)
        assert answer.status_code == 422, (change, answer.status_code, answer.text)
    listy = pack("listy", extra={"flavor.json": b"[1, 2]"})
    assert upload(house(ALICE), listy).status_code == 422


def test_a_shared_theme_changed_by_its_owner_goes_back_to_review(house):
    assert upload(house(ALICE), pack()).status_code == 200
    house(ALICE).put("/themes/dusk-test/status", json={"status": "requested"})
    assert (
        house(ADMIN).put("/themes/dusk-test/status", json={"status": "shared"}).json()["status"] == "shared"
    )
    again = upload(house(ALICE), pack())  # the owner changes it
    assert again.json()["status"] == "requested"
    assert house(BOB).get("/themes").json()["items"] == []  # the house no longer sees it until approved


def test_a_theme_with_its_own_fonts_round_trips(house, tmp_path):
    from houseos.theme_kit import pack as kit_pack

    folder = tmp_path / "src"
    import shutil

    shutil.copytree(t.ROOT / "base", folder / "base")
    copy = shutil.copytree(t.ROOT / "linen-morning", folder / "linen-copy")
    manifest = json.loads((copy / "theme.json").read_text()) | {"id": "linen-copy"}
    (copy / "theme.json").write_text(json.dumps(manifest))
    data = kit_pack.pack("linen-copy", folder, tmp_path / "x.houseos-theme").read_bytes()
    answer = upload(house(ALICE), data)
    assert answer.status_code == 200, answer.text[:500]
    css = house(ALICE).get("/themes/linen-copy.css").text
    assert "@font-face" in css and "/themes/linen-copy/fonts/" in css
