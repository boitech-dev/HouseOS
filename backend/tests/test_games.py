"""Games (D33): a file is named from the open database, versions group into one card, a folder is
read in place, saves belong to one person, and only the emulator's own files are fetched."""

import zipfile
import zlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from houseos import files, games, games_catalog as catalog, games_tv
from houseos.auth import Actor, require_actor
from houseos.db import get_db, new_id
from houseos.fetcher_games import EJS_FILE
from houseos.games_patch import apply
from houseos.models import Record

DAT = """clrmamepro ( name "Nintendo - Super Nintendo Entertainment System" )
game ( name "Tiny Quest (USA)" region "USA" rom ( name "Tiny Quest (USA).sfc" size 8 crc {crc} ) )
game ( name "Tiny Quest (Europe)" region "Europe" rom ( name "Tiny Quest (Europe).sfc" size 8 crc 0BADF00D ) )
"""
GENRE = 'game ( comment "Tiny Quest (USA)" genre "Role-playing (RPG)" rom ( crc {crc} ) )'
ROM = b"TINYQUEST"


@pytest.fixture
def book(monkeypatch):
    crc = f"{zlib.crc32(ROM):08X}"
    built = catalog.build({"metadat/no-intro": DAT.format(crc=crc), "metadat/genre": GENRE.format(crc=crc)})
    monkeypatch.setattr(catalog, "catalogue", lambda system: built)
    return crc.lower()


def test_a_file_is_named_from_its_fingerprint_or_its_name(tmp_path, book):
    rom = tmp_path / "tq.sfc"
    rom.write_bytes(ROM)
    crcs, size, name = catalog.fingerprint(rom, "snes")
    assert crcs == [book] and size == len(ROM)
    facts = catalog.describe("snes", crcs, name)
    assert (facts["title"], facts["region"], facts["genre"]) == ("Tiny Quest", "USA", "Role-playing (RPG)")
    # A copier header (512 bytes) is looked past; a zip is read without unpacking.
    body = ROM.ljust(1024, b"\0")
    (tmp_path / "h.smc").write_bytes(b"\0" * 512 + body)
    assert catalog.fingerprint(tmp_path / "h.smc", "snes")[0] == [
        f"{zlib.crc32(body):08x}",
        f"{zlib.crc32(b'\0' * 512 + body):08x}",
    ]
    with zipfile.ZipFile(tmp_path / "tq.zip", "w") as z:
        z.writestr("Tiny Quest (USA).sfc", ROM)
    assert catalog.fingerprint(tmp_path / "tq.zip", "snes")[0] == [book]
    # Renamed, or a translation: known by name; the translation is a hack of the original.
    assert catalog.describe("snes", [], "tiny_quest_usa.sfc")["title"] == "Tiny Quest"
    assert catalog.describe("snes", [], "tq.sfc")["matched"] is False
    hack = catalog.describe("snes", [], "Tiny Quest (USA) [T+Fre].sfc")
    assert hack["hack"] and hack["base"] == "Tiny Quest" and hack["art_name"] == "Tiny Quest (USA)"


def test_titles_read_like_titles():
    assert (
        catalog.clean("Legend of Zelda, The - A Link to the Past (USA)")
        == "The Legend of Zelda - A Link to the Past"
    )
    assert catalog.clean("Mega Man X (USA) (Rev 1).sfc") == "Mega Man X"
    assert catalog.clean("Final Fight Vol. 2") == "Final Fight Vol. 2"


def test_a_patch_makes_a_romhack():
    assert apply(b"ABCDEF", b"PATCH" + b"\x00\x00\x01\x00\x02XY" + b"EOF") == b"AXYDEF"
    with pytest.raises(ValueError, match="GAME_PATCH_INVALID"):
        apply(b"ABC", b"not a patch")


def test_only_the_emulators_own_files_are_fetched():
    assert EJS_FILE.fullmatch("cores/snes9x-wasm.data") and EJS_FILE.fullmatch("loader.js")
    for bad in ("../secret", "cores/../../x", "https://evil/x.js", "src/emulator.js.map"):
        assert not EJS_FILE.fullmatch(bad)


def game(db, owner, title, region, system="snes", **data):
    row = Record(
        id=new_id(), kind="game.rom", owner_id=owner.id, visibility="house",
        data={"state": "ready", "identified": True, "system": system, "title": title, "region": region,
              "source": "upload", "_path": "/nowhere", **data},
    )  # fmt: skip
    db.add(row)
    db.commit()
    return row


def test_versions_are_one_card_and_a_duplicate_hides(domain, monkeypatch):
    db, (alice, bob, _) = domain
    monkeypatch.setattr(games, "house_language", lambda db: "fr")
    usa = game(db, alice, "Tiny Quest", "USA")
    europe = game(db, alice, "Tiny Quest", "Europe")
    game(db, bob, "Tiny Quest", "USA", duplicate_of=usa.id)
    cards = [c for c in games.cards(db, alice) if c["title"] == "Tiny Quest"]
    assert len(cards) == 1 and cards[0]["versions"] == 2
    assert cards[0]["id"] == europe.id  # a French house opens the European version first


def test_a_folder_is_read_in_place(domain, monkeypatch, tmp_path):
    db, (alice, _, _) = domain
    monkeypatch.setattr(files, "storage_check", lambda: None)
    monkeypatch.setattr(files.settings, "import_root", tmp_path)
    monkeypatch.setattr(files.settings, "data_root", tmp_path / "house")
    root = tmp_path / "Games"
    (root / "SNES").mkdir(parents=True)
    (root / "PS1").mkdir()
    (root / "SNES" / "Tiny Quest (USA).sfc").write_bytes(ROM)
    (root / "PS1" / "Disc (USA).cue").write_text("FILE")
    (root / "PS1" / "Disc (USA) (Track 1).bin").write_bytes(b"x")
    (root / "notes.txt").write_text("hi")
    folder = Record(
        id=new_id(), kind="games.folder", owner_id=alice.id, visibility="house", data={"path": str(root)}
    )
    db.add(folder)
    db.commit()
    games.scan(db, folder)
    db.commit()
    mine = lambda: [r for r in games.games(db) if r.data.get("folder_id") == folder.id]  # noqa: E731
    found = {r.data["file"]: r.data["system"] for r in mine()}
    assert found == {"Tiny Quest (USA).sfc": "snes", "Disc (USA).cue": "psx"}
    assert (root / "SNES" / "Tiny Quest (USA).sfc").read_bytes() == ROM  # untouched
    (root / "SNES" / "Tiny Quest (USA).sfc").unlink()
    games.scan(db, folder)
    db.commit()
    assert [r.data["file"] for r in mine()] == ["Disc (USA).cue"]
    # The file comes back (a drive plugged in again): the same game returns, no crash.
    (root / "SNES" / "Tiny Quest (USA).sfc").write_bytes(ROM)
    games.scan(db, folder)
    db.commit()
    assert sorted(r.data["file"] for r in mine()) == ["Disc (USA).cue", "Tiny Quest (USA).sfc"]


def test_saves_belong_to_one_person_and_a_folder_game_is_only_hidden(domain, monkeypatch, tmp_path):
    db, (alice, bob, _) = domain
    monkeypatch.setattr(files, "storage_check", lambda: None)
    monkeypatch.setattr(games.settings, "data_root", tmp_path)
    row = game(db, alice, "Tiny Quest", "USA", source="folder")
    who = {"actor": alice}
    app = FastAPI()
    app.include_router(games.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_actor] = lambda: who["actor"]
    c = TestClient(app)
    assert c.put(f"/games/{row.id}/save", content=b"SRAM").status_code == 200
    assert c.get(f"/games/{row.id}/save").content == b"SRAM"
    who["actor"] = bob
    assert c.get(f"/games/{row.id}/save").status_code == 204  # Bob sees only his own
    who["actor"] = Actor(bob.id, bob.name, "admin", bob.permissions)
    assert c.get(f"/games/{row.id}/save").status_code == 204  # an admin too
    who["actor"] = alice
    assert c.delete(f"/games/{row.id}?version={row.version}").status_code == 403
    who["actor"] = Actor(bob.id, bob.name, "admin", bob.permissions)
    assert c.delete(f"/games/{row.id}?version={row.version}").json()["hidden"] is True
    assert (tmp_path / "game-saves" / alice.id / row.id / "save.srm").read_bytes() == b"SRAM"


def test_play_on_the_tv_says_what_and_for_whom(domain, monkeypatch, tmp_path):
    db, (alice, _, _) = domain
    monkeypatch.setattr(games.settings, "data_root", tmp_path)
    monkeypatch.setattr(games_tv, "RUN", tmp_path / "run")
    monkeypatch.setattr(games_tv, "CACHE", tmp_path)
    monkeypatch.setattr(games_tv, "host_ready", lambda: True)
    (tmp_path / "cores").mkdir()
    (tmp_path / "cores" / "snes9x_libretro.so").write_bytes(b"core")
    rom = tmp_path / "media" / "games" / "snes" / "tq.sfc"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(ROM)
    row = game(db, alice, "Tiny Quest", "USA", _path=str(rom))
    assert games_tv.tv_play(games_tv.Play(game_id=row.id), alice, db)["state"] == "waiting"
    import json

    picked = json.loads((tmp_path / "run" / "next.json").read_text())
    assert (picked["path"], picked["user_id"], picked["core"]) == (
        str(rom),
        alice.id,
        str(tmp_path / "cores" / "snes9x_libretro.so"),
    )
    assert picked["saves"] == str(tmp_path / "game-saves" / alice.id / row.id)


def test_the_find_link_is_a_web_address():
    from houseos.house_settings import HouseSettings

    assert "{title}" in HouseSettings().games_find_url  # a web search by default
    for fine in ("https://example.org/?q={title}", ""):
        assert HouseSettings(games_find_url=fine).games_find_url == fine
    for refused in (
        "javascript:alert(1)",
        "magnet:?xt=x",
        "app://library?q={title}",
        "data:text/html,x",
        "no scheme",
    ):
        with pytest.raises(ValueError):
            HouseSettings(games_find_url=refused)


def test_a_linked_dvd_fits_but_never_fills_the_system_disk(monkeypatch, tmp_path):
    import shutil
    from types import SimpleNamespace

    from houseos import cinema_adapters, fetcher_games

    body = {"length": 8 * 1024**3}

    class Answer:
        status = 200

        def getheader(self, name, default=None):
            return str(body["length"]) if name == "Content-Length" else default

        def read(self, n):
            return b""

    class Connection:
        def __init__(self, host, address):
            pass

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return Answer()

        def close(self):
            pass

    monkeypatch.setattr(fetcher_games, "DIR", tmp_path)
    monkeypatch.setattr(cinema_adapters, "public_url", lambda url: (SimpleNamespace(
        hostname="example.com", path="/dvd.iso", query=""), "93.184.216.34"))  # fmt: skip
    monkeypatch.setattr(cinema_adapters, "PinnedHTTPS", Connection)
    free = {"bytes": 40 * 1024**3}
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=free["bytes"]))
    assert fetcher_games.link(new_id(), "https://example.com/dvd.iso")["status"] == "completed"
    free["bytes"] = 12 * 1024**3  # 8 GB would leave under 6 GB on the system disk
    with pytest.raises(ValueError, match="GAME_NO_SPACE"):
        fetcher_games.link(new_id(), "https://example.com/dvd.iso")
    free["bytes"], body["length"] = 40 * 1024**3, 17 * 1024**3
    with pytest.raises(ValueError, match="SOURCE_RESPONSE_TOO_LARGE"):
        fetcher_games.link(new_id(), "https://example.com/dvd.iso")
    Answer.getheader = lambda self, name, default=None: (
        "text/html; charset=utf-8" if name == "Content-Type" else default
    )
    with pytest.raises(ValueError, match="GAME_LINK_PAGE"):  # a download page, not the file
        fetcher_games.link(new_id(), "https://example.com/download/a-game-7528")


def test_a_link_left_by_a_restart_finishes_or_says_so_and_is_logged(domain, monkeypatch, tmp_path):
    import json
    import os
    import time

    from sqlalchemy.orm import Session

    from houseos import activity
    from houseos.models import Event

    db, (alice, _, _) = domain
    monkeypatch.setattr(games, "SessionLocal", lambda: Session(db.bind, expire_on_commit=False))
    monkeypatch.setattr(games, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(games.settings, "data_root", tmp_path / "house")
    monkeypatch.setattr(games, "identify", lambda identity: None)
    incoming = tmp_path / "cache" / "incoming"
    incoming.mkdir(parents=True)
    (tmp_path / "house").mkdir()
    done = game(db, alice, "My Disc.iso", None, system="ps2", state="downloading", source="link")
    (incoming / done.id).write_bytes(b"ISO" * 100)
    assert games.progress(done.id) == {"bytes": 300, "total": None}
    (incoming / (done.id + ".json")).write_text(
        json.dumps({"total": 300, "status": "completed", "name": "My Disc.iso", "bytes": 300})
    )
    stalled = game(db, alice, "Big.iso", None, system="ps2", state="downloading", source="link")
    (incoming / stalled.id).write_bytes(b"x")
    old = time.time() - games.STALLED - 5
    os.utime(incoming / stalled.id, (old, old))
    games.recover(db)
    db.rollback()  # MariaDB: read past this session's snapshot
    assert db.get(Record, done.id).data["state"] == "ready"
    assert not any(incoming.iterdir())  # the download and its note are let go
    left = db.get(Record, stalled.id).data
    assert (left["state"], left["error"]) == ("failed", "GAME_LINK_INTERRUPTED")
    games.recover(db)  # once: a finished row is left alone
    db.rollback()
    lines = [activity.describe(e, {}) for e in db.query(Event).filter(Event.topic == "games.activity")]
    lines = [line for line in lines if line["values"]["title"] in {"My Disc", "Big.iso"}]
    said = {(line["category"], line["level"], line["template"].format(**line["values"])) for line in lines}
    assert ("games", "good", "My Disc is ready to play") in said
    assert ("games", "problem", "Couldn't download Big.iso") in said
    assert len(lines) == 2


def test_a_link_copy_that_fills_the_disk_or_loses_the_race_leaves_nothing(domain, monkeypatch, tmp_path):
    import errno

    from sqlalchemy.orm import Session

    db, (alice, _, _) = domain
    monkeypatch.setattr(games, "SessionLocal", lambda: Session(db.bind, expire_on_commit=False))
    monkeypatch.setattr(games, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(games.settings, "data_root", tmp_path / "house")
    monkeypatch.setattr(games, "identify", lambda identity: None)
    incoming = tmp_path / "cache" / "incoming"
    incoming.mkdir(parents=True)
    (tmp_path / "house").mkdir()
    done = {"status": "completed", "name": "Disc.iso"}

    def full(source, target):
        open(target, "wb").write(b"IS")
        raise OSError(errno.ENOSPC, "No space left on device")

    row = game(db, alice, "Disc.iso", None, system="ps2", state="downloading", source="link")
    (incoming / row.id).write_bytes(b"ISO")
    monkeypatch.setattr(games.shutil, "copyfile", full)
    games.finish(row.id, done)
    db.expire_all()
    assert db.get(Record, row.id).data["error"] == "GAME_NO_SPACE"
    assert not [p for p in (tmp_path / "house").rglob("*") if p.is_file()] and not any(incoming.iterdir())

    # Another finish won while this one copied: its copy goes, the winner's row stays.
    row = game(db, alice, "Disc2.iso", None, system="ps2", state="downloading", source="link")
    (incoming / row.id).write_bytes(b"ISO")

    def raced(source, target):
        open(target, "wb").write(b"ISO")
        with Session(db.bind) as other:
            won = other.get(Record, row.id)
            won.data = {**won.data, "state": "failed", "error": "GAME_LINK_INTERRUPTED"}
            other.commit()

    monkeypatch.setattr(games.shutil, "copyfile", raced)
    games.finish(row.id, done)
    db.expire_all()
    assert db.get(Record, row.id).data["error"] == "GAME_LINK_INTERRUPTED"
    assert not [p for p in (tmp_path / "house").rglob("*") if p.is_file()]

    # A claimed row is left to its finisher; a bad archive fails the row instead of wedging the sweep.
    row = game(db, alice, "Disc3.iso", None, system="ps2", state="downloading", source="link")
    row.data = {**row.data, "_finishing": {"token": "other", "at": games.time.time()}}
    db.commit()
    (incoming / row.id).write_bytes(b"ISO")
    games.finish(row.id, done)
    db.expire_all()
    assert db.get(Record, row.id).data["state"] == "downloading" and (incoming / row.id).exists()

    import zipfile

    def broken(path, system):
        raise zipfile.BadZipFile("File is not a zip file")

    row = game(db, alice, "Cart.zip", None, system="snes", state="downloading", source="link")
    (incoming / row.id).write_bytes(b"<html>")
    monkeypatch.setattr(games.catalog, "fingerprint", broken)
    games.finish(row.id, {"status": "completed", "name": "Cart.zip"})
    db.expire_all()
    assert db.get(Record, row.id).data["error"] == "GAME_LINK_UNAVAILABLE"
    assert not (incoming / row.id).exists()
