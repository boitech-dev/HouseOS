"""Your own integrations: installing from a git repository (a local one here), turning on and off,
their routes and keys (and the one door the Origin check leaves open for them), Nox tools and
cards, share buttons, Control Room's card, a broken one, updating and removing."""

import os
import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from houseos import assistant_tools, custom, custom_admin
from houseos.config import settings
from houseos.models import Event, Integration

HELLO = """
from fastapi import APIRouter, Depends

from houseos.custom import Parts, Share


def setup(house):
    router = APIRouter()
    seen = []

    class Note(house.Input):
        url: str

    @router.post("/note")
    def note(body: Note, actor=Depends(house.key_or_signed_in), db=Depends(house.get_db)):
        house.allowed(actor, "home.control")
        seen.append(body.url)
        house.record(db, "noted", {"count": len(seen)}, actor)
        db.commit()
        return {"seen": len(seen), "by": actor.name}

    @router.post("/private")
    def private(actor=Depends(house.signed_in)):
        return {"ok": True}

    def ping(body, actor, db):
        return house.ask_first(actor, db, "ping", {"url": body.url}, "Ping", {"value": body.url})

    def confirmed(data, actor, db):
        seen.append("confirmed " + data["url"])
        return {"status": "done", "seen": len(seen)}

    return Parts(
        router=router,
        key_routes=("/note",),
        tools={"hello_ping": (Note, "Ping something.", ping)},
        bundles=("general", "tv"),
        confirm={"ping": confirmed},
        shares=[Share("note", {"en": "Note it", "fr": "Note-le"}, r"https?://", "/note")],
        card=lambda actor, db: {
            "lines": [{"label": "Seen", "value": str(len(seen)), "tone": "success"}],
            "help": ["Step one."],
        },
    )
"""

MANIFEST = '{"id": "hello", "name": "Hello", "version": "1.0", "description": "Says hello."}'


@pytest.fixture(autouse=True)
def house(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "runtime_root", tmp_path / "runtime")
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    yield
    for integration_id in list(custom.LOADED):
        custom.unload(integration_id)
    custom.PROBLEMS.clear()


def write(folder: Path, manifest=MANIFEST, code=HELLO):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "houseos-integration.json").write_text(manifest)
    (folder / "integration.py").write_text(code)
    return folder


def git(*args, cwd):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd)}  # fmt: skip
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    """A repository on disk; file:// is allowed for tests only (the app takes https)."""
    monkeypatch.setenv("HOUSEOS_TEST_GIT_FILE", "1")
    folder = write(tmp_path / "repo")
    git("init", "-q", "-b", "main", cwd=folder)
    git("add", ".", cwd=folder)
    git("commit", "-q", "-m", "Hello 1.0", cwd=folder)
    return folder


def admin(c):
    response = c.post(
        "/api/v1/auth/bootstrap",
        json={
            "name": "Test Admin",
            "username": "testadmin",
            "password": "test-only-password-very-long",
            "setup_token": settings.bootstrap_token,
        },
    )
    assert response.status_code == 200, response.text
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def install(c, repository, token=None):
    """Check then install, as Control Room does (the address check is the only https rule)."""
    found = custom_admin.stage("file://" + str(repository), None, token)
    assert found["manifest"]["id"] == "hello" and "integration.py" in found["files"]
    assert found["source"]["subject"] == "Hello 1.0" and "token" not in found["source"]
    reply = c.post("/api/v1/admin/custom-integrations/install", json={"check_id": found["check_id"]})
    assert reply.status_code == 200, reply.text
    return reply.json()


def test_only_https_without_credentials_in_the_address():
    for url in ("http://git.example/x.git", "ssh://git@git.example/x.git", "https://me:pw@git.example/x.git"):
        with pytest.raises(Exception) as refused:
            custom_admin.checked_url(url)
        assert refused.value.status_code == 422
    assert custom_admin.checked_url(" https://git.example/me/x.git ") == "https://git.example/me/x.git"


def test_install_is_off_until_turned_on_and_runs_nothing_before(client, repository):
    c, db = client
    admin(c)
    installed = install(c, repository, token="secret-token")
    assert installed["enabled"] is False and installed["loaded"] is False and installed["has_token"]
    assert not (settings.runtime_root / "integrations/hello/.git").exists()
    row = db.get(Integration, "custom:hello")
    assert "secret-token" not in str(row.config) and "secret-token" not in row.encrypted_secret
    assert custom_admin.unseal(row) == "secret-token"
    assert c.post("/api/v1/custom/hello/note", json={"url": "https://x.test"}).status_code == 404

    on = c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": True}).json()
    assert on["loaded"] and on["adds"] == {
        "routes": True,
        "tools": ["hello_ping"],
        "shares": ["note"],
        "card": True,
    }
    assert c.post("/api/v1/custom/hello/note", json={"url": "https://x.test"}).json() == {
        "seen": 1,
        "by": "Test Admin",
    }
    listed = c.get("/api/v1/admin/custom-integrations").json()["items"][0]
    assert listed["card"] == {
        "lines": [{"label": "Seen", "value": "1", "tone": "success"}],
        "help": ["Step one."],
    }
    assert db.query(Event).filter(Event.topic == "custom.hello.noted").count() == 1

    c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": False})
    assert c.post("/api/v1/custom/hello/note", json={"url": "https://x.test"}).status_code == 404


def test_keys_open_only_the_key_routes_and_only_with_the_key(client, repository):
    c, db = client
    admin(c)
    install(c, repository)
    c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": True})
    made = c.post("/api/v1/admin/custom-integrations/hello/keys", json={"name": "Phone"}).json()
    key = made["key"]
    assert key.startswith("hos_hello_")
    assert key not in (settings.runtime_root / "run/custom/hello/keys.json").read_text()
    listed = c.get("/api/v1/admin/custom-integrations").json()["items"][0]["keys"]
    assert [k["name"] for k in listed] == ["Phone"] and "hash" not in listed[0]

    # A shortcut: no cookie, no Origin, only the key.
    c.cookies.clear()
    bare = {"Origin": "", "X-CSRF-Token": ""}
    sent = c.post(
        "/api/v1/custom/hello/note",
        json={"url": "https://x.test"},
        headers=bare | {"Authorization": "Bearer " + key},
    )
    assert sent.status_code == 200 and sent.json()["by"] == "Test Admin"
    wrong = c.post(
        "/api/v1/custom/hello/note",
        json={"url": "https://x.test"},
        headers=bare | {"Authorization": "Bearer nope"},
    )
    assert wrong.status_code == 401
    # Not a key route: the Origin check stands, key or not; without a key, a key route checks it too.
    assert (
        c.post("/api/v1/custom/hello/private", headers=bare | {"Authorization": "Bearer " + key}).status_code
        == 403
    )
    assert (
        c.post("/api/v1/custom/hello/note", json={"url": "https://x.test"}, headers=bare).status_code == 403
    )
    # And the key is nobody's sign-in elsewhere.
    assert (
        c.get("/api/v1/admin/custom-integrations", headers={"Authorization": "Bearer " + key}).status_code
        == 401
    )

    admin_again = c.post(
        "/api/v1/auth/login", json={"username": "testadmin", "password": "test-only-password-very-long"}
    )
    c.headers["X-CSRF-Token"] = admin_again.json()["csrf_token"]
    c.delete(f"/api/v1/admin/custom-integrations/hello/keys/{made['id']}")
    gone = c.post(
        "/api/v1/custom/hello/note",
        json={"url": "https://x.test"},
        headers=bare | {"Authorization": "Bearer " + key},
    )
    assert gone.status_code == 401


def test_nox_tools_cards_and_share_buttons(client, repository):
    c, db = client
    admin(c)
    install(c, repository)
    c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": True})
    assert "hello_ping" in assistant_tools.tool_registry("general")
    assert "hello_ping" in assistant_tools.tool_registry("tv")
    assert "hello_ping" not in assistant_tools.tool_registry("music")
    assert "hello_ping" not in assistant_tools.tool_registry("setup")

    model, _, handler = custom.tools("general")["hello_ping"]
    from houseos.auth import RESIDENT, Actor
    from houseos.models import User

    user = db.query(User).one()
    actor = Actor(user.id, user.name, "admin", RESIDENT)
    card = handler(model(url="https://x.test"), actor, db)
    assert card["status"] == "needs_confirmation"
    done = c.post(card["confirmation_path"].replace("/assistant", "/api/v1/assistant"))
    assert done.status_code == 200 and done.json() == {"status": "done", "seen": 1}
    again = c.post(card["confirmation_path"].replace("/assistant", "/api/v1/assistant"))
    assert again.status_code == 409  # once

    shares = c.get("/api/v1/custom-integrations/shares").json()["items"]
    assert shares == [
        {"integration": "hello", "id": "note", "label": {"en": "Note it", "fr": "Note-le"},
         "match": "https?://", "path": "/note", "field": "url"}
    ]  # fmt: skip


def test_a_broken_integration_says_why_and_the_house_carries_on(client, tmp_path):
    c, db = client
    admin(c)
    folder = write(tmp_path / "broken", code="def setup(house):\n    raise RuntimeError('no TV here')\n")
    from houseos.auth import Actor

    user_actor = Actor("x", "Test Admin", "admin", frozenset())
    custom_admin.install_folder(db, folder, custom.read_manifest(folder), {"kind": "folder"}, user_actor)
    refused = c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": True})
    assert refused.status_code == 422 and "no TV here" in refused.json()["detail"]["message"]
    listed = c.get("/api/v1/admin/custom-integrations").json()["items"][0]
    assert listed["enabled"] is False and "no TV here" in listed["problem"]
    assert c.get("/api/v1/auth/status").status_code == 200


@pytest.mark.parametrize(
    "manifest, says",
    [
        ('{"id": "Bad Id"}', "lowercase"),
        ('{"id": "hello", "entry": "../x.py"}', "entry file"),
        ("not json", "readable"),
    ],
)
def test_manifests_are_checked(tmp_path, manifest, says):
    folder = write(tmp_path / "x", manifest=manifest)
    with pytest.raises(ValueError) as error:
        custom.read_manifest(folder)
    assert says in str(error.value)


def test_update_keeps_keys_and_token_then_remove_takes_everything(client, repository):
    c, db = client
    admin(c)
    install(c, repository, token="secret-token")
    c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": True})
    c.post("/api/v1/admin/custom-integrations/hello/keys", json={"name": "Phone"})
    (repository / "integration.py").write_text(HELLO.replace('"Ping something."', '"Ping, version two."'))
    git("commit", "-q", "-am", "Hello 2.0", cwd=repository)

    row = db.get(Integration, "custom:hello")
    row.config = {**row.config, "source": {**row.config["source"], "url": "file://" + str(repository)}}
    db.commit()
    found = c.post("/api/v1/admin/custom-integrations/hello/check-update").json()
    assert found["source"]["subject"] == "Hello 2.0" and found["current"] != found["source"]["commit"]
    updated = c.post(
        "/api/v1/admin/custom-integrations/hello/update", json={"check_id": found["check_id"]}
    ).json()
    assert updated["enabled"] and updated["loaded"] and updated["source"]["subject"] == "Hello 2.0"
    assert [k["name"] for k in updated["keys"]] == ["Phone"] and updated["has_token"]
    assert custom.tools("general")["hello_ping"][1] == "Ping, version two."

    assert c.delete("/api/v1/admin/custom-integrations/hello").status_code == 200
    assert not (settings.runtime_root / "integrations/hello").exists()
    assert not (settings.runtime_root / "run/custom/hello").exists()
    assert db.get(Integration, "custom:hello") is None
    assert c.post("/api/v1/custom/hello/note", json={"url": "https://x.test"}).status_code == 404


def test_the_documented_example_works(client):
    c, db = client
    admin(c)
    example = Path(__file__).resolve().parents[2] / "docs/examples/hello-integration"
    import shutil

    from houseos.auth import Actor

    copy = settings.runtime_root / "example"
    shutil.copytree(example, copy)
    custom_admin.install_folder(
        db, copy, custom.read_manifest(copy), {"kind": "folder"}, Actor("x", "A", "admin", frozenset())
    )
    assert c.put("/api/v1/admin/custom-integrations/hello/enabled", json={"enabled": True}).status_code == 200
    kept = c.post("/api/v1/custom/hello/keep", json={"url": "https://example.org/a"})
    assert kept.json()["status"] == "kept"
    card = c.get("/api/v1/admin/custom-integrations").json()["items"][0]["card"]
    assert card["lines"][0]["value"] == "https://example.org/a"
    assert (
        c.post("/api/v1/custom/hello/keep", json={"url": "nope"}).json()["detail"]["code"]
        == "HELLO_NOT_A_LINK"
    )
