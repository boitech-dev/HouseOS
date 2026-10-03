"""Nox drafts code changes; an admin applies them from Control Room → Changes; the house computer
(deploy/code_change.py) backs up, checks, deploys and goes back. Everything runs on temporary git
repositories with fake checks, deploys and restarts: never the real checkout, releases or units."""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from houseos import code_rules, house_actions, tool_code
from houseos.config import settings
from test_core import admin

ADA = SimpleNamespace(id="ada", name="Ada", role="admin")
KEY = "test-key-for-the-helper"
ROOT = Path(__file__).resolve().parents[2]


def shipped(name):
    """A host script where this checkout keeps it: docs/native/ (and houseos.sh at the root) in
    the public repository, deploy/ (packaging/docker/) in a house's own copy."""
    for place in ("docs/native", "deploy", ".", "packaging/docker"):
        if (ROOT / place / name).is_file():
            return ROOT / place / name
    raise FileNotFoundError(name)


APP = "backend/houseos/app.py"
NEW = "backend/houseos/new.py"


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "backend/houseos").mkdir(parents=True)
    (source / APP).write_text("SPEED = 1\nSPEED_TOO = 1\n")
    (source / "deploy").mkdir()
    (source / "deploy/release.py").write_text("print('release')\n")
    (source / ".env").write_text("HOUSEOS_DB_PASSWORD=never-shown\n")
    (source / "logo.png").write_bytes(b"\x89PNG\0\0")
    (tmp_path / "outside.py").write_text("secret = 1\n")
    (source / "backend/houseos/escape.py").symlink_to(tmp_path / "outside.py")
    (source / "backend/houseos/deploy_link.py").symlink_to(source / "deploy/release.py")
    git(source, "init", "-q")
    git(source, "add", APP, "deploy/release.py", "logo.png")
    git(source, "commit", "-qm", "base")
    monkeypatch.setattr(settings, "source_root", source)
    monkeypatch.setattr(settings, "runtime_root", tmp_path / "runtime")
    monkeypatch.setattr(settings, "encryption_key", KEY)
    return source


def tool(name, **body):
    """A tool as Nox's loop runs it: a refusal (HTTPException) becomes a failed result."""
    model, _, handler = tool_code.TOOLS[name]
    try:
        return handler(model(**body), ADA, None)
    except HTTPException as exc:
        return {"status": "failed", "error": exc.detail}


def test_not_set_up_says_so(monkeypatch):
    monkeypatch.setattr(settings, "source_root", None)
    assert "docs/CHANGING-HOUSEOS.md" in tool("code_read", path=APP)["error"]


def test_reads_and_drafts_only_inside_the_source_text_files(repo):
    for path in ("../outside.py", "/etc/passwd", ".git/config", ".env", "backend/.env.local", "logo.png",
                 "node_modules/x.js", "import/x.py", "backend/houseos/escape.py"):  # fmt: skip
        assert tool("code_write", path=path, content="x")["status"] == "failed", path
    # Readable, never drafted: what builds, checks, deploys and undoes a change.
    for path in ("deploy/code_change.py", "deploy/release.py", "backend/houseos/deploy_link.py",
                 "backend/tests/conftest.py", "backend/houseos/code_rules.py", "backend/pyproject.toml",
                 "backend/migrations/versions/0010_x.py", "frontend/scripts/build.mjs", "frontend/vite.config.ts",
                 "frontend/package.json", "themes/_kit/tour.cjs", "docs/native/code_change.py",
                 "packaging/docker/houseos.sh", "houseos.sh", "tools/code_index.py"):  # fmt: skip
        assert "by hand" in tool("code_write", path=path, content="x")["error"], path
    assert tool("code_read", path="deploy/release.py")["status"] == "completed"
    assert tool("code_read", path=".env")["status"] == "failed"
    assert "never-shown" not in json.dumps(tool("code_search", query="HOUSEOS"))
    found = tool("code_search", query="speed")["matches"]
    assert [m["line"] for m in found] == [1, 2] and found[0]["path"] == APP
    assert tool("code_read", path=APP)["text"] == "1: SPEED = 1\n2: SPEED_TOO = 1"


def test_invisible_characters_are_refused(repo):
    for text in ("x = 1  # \u202egnirts\n", "na\u200bme = 1\n", "\ufeffx = 1\n", "x = 1\rsafe = 1\n",
                 "x = 1\u2028y = 2\n", "x = '\x1b[2K'\n", "x = 1\x85\n", "t = '\U000e0041'\n", "\x00"):  # fmt: skip
        assert "Invisible" in tool("code_write", path=NEW, content=text)["error"], repr(text)
    assert "Invisible" in tool("code_write", path=NEW, content="x = 1\n", summary="a\rb")["error"]
    assert (
        tool("code_write", path=NEW, content="x = '\\u200b l\u2019heure 1\u202f:'\n\tpass\n")["status"]
        == "completed"
    )


def test_the_host_script_and_houseos_sh_allow_the_same_paths(tmp_path):
    samples = ["backend/houseos/music.py", "backend/houseos/sub/x.py", "backend/tests/test_x.py",
               "backend/tests/fixtures/a.json", "backend/tests/conftest.py", "backend/tests/sub/conftest.py",
               "backend/houseos/code_rules.py", "backend/houseos/addon_http.cjs", "backend/pyproject.toml",
               "backend/migrations/env.py", "frontend/src/music.tsx", "frontend/src/design/x.css",
               "frontend/scripts/x.mjs", "frontend/vite.config.ts", "themes/zabiwa/theme.json",
               "themes/_kit/x.json", "themes/base/fonts/x.txt", "docs/CHANGING-HOUSEOS.md", "docs/native/x.md",
               "deploy/code_change.py", "houseos.sh", "backend/houseos/../../deploy/x.py", "backend/houseos/.x.py",
               "backend//houseos/x.py", "/backend/houseos/x.py", "backend/houseos/x.py\nx", "backend/houseos/é.py",
               "backend/houseos/__init__.py", "backend/houseos/__INIT__.py", "Backend/Houseos/Code_Rules.py",
               "backend/tests/CONFTEST.py", "backend/houseos/sub/__init__.py", "BACKEND/houseos/x.PY",
               "backend/houseos/\u212a.py", "backend/houseos/\u017f.py"]  # fmt: skip
    python = {p for p in samples if code_rules.allowed(p)}
    assert python == {"backend/houseos/music.py", "backend/houseos/sub/x.py", "backend/tests/test_x.py",
                      "backend/tests/fixtures/a.json", "frontend/src/music.tsx", "frontend/src/design/x.css",
                      "themes/zabiwa/theme.json", "docs/CHANGING-HOUSEOS.md", "backend/houseos/sub/__init__.py",
                      "BACKEND/houseos/x.PY"}  # fmt: skip
    script = shipped("houseos.sh").read_text()
    [rule] = [line for line in script.splitlines() if line.startswith("nox_may_change()")]
    listed = subprocess.run(
        [
            "bash",
            "-c",
            rule + '\nfor p; do nox_may_change "$p" && printf "%s\\0" "$p"; done; true',
            "-",
            *samples,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # Docker's screens and bundled themes come prebuilt: houseos.sh allows the rest, the same way.
    assert set(listed.split("\0")) - {""} == {p for p in python if not p.startswith(("frontend/", "themes/"))}

    # And both compute the same digest of a draft (houseos.sh with jq, as the helper does).
    change = {
        "files": {"backend/houseos/a.py": "é = 1\n", "docs/B.md": "new\n"},
        "before": {"backend/houseos/a.py": ""},
    }
    (tmp_path / "change.json").write_text(json.dumps(change))
    functions = "\n".join(
        script[script.index(start) : script.index("\n}\n", script.index(start)) + 2]
        for start in ("sha() {", "code_digest() {")
    )
    if shutil.which("jq"):
        bash = subprocess.run(
            [
                "bash",
                "-c",
                functions + '\ncode_digest "$@"',
                "-",
                tmp_path / "change.json",
                *sorted(change["files"]),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert bash == code_rules.digest(change)


def test_edit_matches_once_and_the_diff_shows_it(repo):
    assert "2 times" in tool("code_edit", path=APP, old="SPEED", new="PACE")["error"]
    assert "isn't in the file" in tool("code_edit", path=APP, old="nope", new="x")["error"]
    done = tool("code_edit", path=APP, old="SPEED = 1\n", new="SPEED = 2\n", summary="Faster")
    assert done["status"] == "completed" and "Control Room → Changes" in done["next"]
    assert done["card"]["href"] == "/control?tab=changes"
    tool("code_write", path=NEW, content="NEW = True\n")
    assert (repo / APP).read_text() == "SPEED = 1\nSPEED_TOO = 1\n"  # the source never changes
    assert tool("code_read", path=APP)["drafted"] is True
    diff = tool("code_diff")
    assert diff["summary"] == "Faster" and diff["files"] == [APP, NEW]
    assert "-SPEED = 1\n+SPEED = 2\n" in diff["diff"] and "+NEW = True" in diff["diff"]
    [change] = tool_code.changes()
    assert change["base"] == git(repo, "rev-parse", "HEAD") and change["author"] == "Nox"
    tool("code_discard", path=NEW)
    assert tool("code_diff")["files"] == [APP]
    tool("code_discard")
    assert tool_code.changes() == []


def code_change(monkeypatch):
    """The host script, pointed at this test's temporary source and runtime from the start."""
    monkeypatch.setenv("HOUSEOS_SOURCE_ROOT", str(settings.source_root))
    monkeypatch.setenv("HOUSEOS_RUNTIME_ROOT", str(settings.runtime_root))
    spec = importlib.util.spec_from_file_location("houseos_code_change_test", shipped("code_change.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changes_page_is_admins_only_with_csrf_and_sends_a_signed_request(client, repo, monkeypatch):
    c, db = client
    admin(client)
    tool("code_edit", path=APP, old="SPEED = 1\n", new="SPEED = 2\n", summary="Faster")
    [change] = tool_code.changes()
    page = c.get("/api/v1/admin/changes").json()
    [row] = page["changes"]
    assert row["state"] == "draft" and row["diff"][0]["path"] == APP and not row["stale"]
    reviewed = {"digest": row["digest"]}

    token = c.headers.pop("X-CSRF-Token")
    assert c.post(f"/api/v1/admin/changes/{change['id']}/apply", json=reviewed).status_code == 403
    c.headers["X-CSRF-Token"] = token
    assert c.post(f"/api/v1/admin/changes/{change['id']}/undo").status_code == 409  # no backup yet
    assert c.post("/api/v1/admin/changes/not-an-id/apply", json=reviewed).status_code == 404
    # Apply binds to the diff on the admin's screen: Nox changing the draft since is refused.
    assert c.post(f"/api/v1/admin/changes/{change['id']}/apply").status_code == 409
    tool("code_edit", path=APP, old="SPEED_TOO = 1\n", new="SPEED_TOO = 3\n")
    refused = c.post(f"/api/v1/admin/changes/{change['id']}/apply", json=reviewed)
    assert refused.status_code == 409 and "look at it again" in refused.json()["detail"]
    reviewed = {"digest": c.get("/api/v1/admin/changes").json()["changes"][0]["digest"]}
    assert c.post(f"/api/v1/admin/changes/{change['id']}/apply", json=reviewed).json()["status"] == "accepted"
    assert c.get("/api/v1/admin/changes").json()["changes"][0]["state"] == "working"
    assert c.post(f"/api/v1/admin/changes/{change['id']}/apply", json=reviewed).status_code == 409

    # Frozen: Nox's tools start a new draft and the one sent to the house computer stays as it was.
    applied = tool_code.load(change["id"])
    assert tool("code_write", path=NEW, content="LATER = 1\n")["change"] != change["id"]
    assert tool_code.load(change["id"]) == applied and len(tool_code.changes()) == 2

    # The house computer's side reads only notes signed with the house's key, the digest inside.
    monkeypatch.setenv("HOUSEOS_ENCRYPTION_KEY", KEY)
    host = code_change(monkeypatch)
    inbox = settings.runtime_root / "run/helper-in"
    [note] = inbox.glob("*.json")
    forged = json.loads(note.read_text())
    forged["body"] = forged["body"].replace("code-apply", "code-keep")
    (inbox / "forged.json").write_text(json.dumps(forged))
    [request] = host.notes()
    assert request["action"] == "code-apply" and request["arg"] == change["id"] + ":" + reviewed["digest"]
    assert request["id"] == applied["requests"][-1]["id"]
    assert not list(inbox.iterdir())  # code notes and bad notes are consumed

    invite = c.post("/api/v1/auth/invites", json={"preset": "party", "expires_hours": 2}).json()
    guest = {
        "token": invite["token"],
        "name": "Guest",
        "username": "guest123",
        "password": "another-test-password",
    }
    c.headers["X-CSRF-Token"] = c.post("/api/v1/auth/redeem", json=guest).json()["csrf_token"]
    assert c.get("/api/v1/admin/changes").status_code == 403
    assert c.post(f"/api/v1/admin/changes/{change['id']}/keep").status_code == 403


def test_nothing_restarts_while_a_film_plays(client, repo, monkeypatch):
    # Songs resume after the restart (the resume-music marker), so only a film holds it back.
    from houseos import house_actions

    c, db = client
    admin(client)
    tool("code_edit", path=APP, old="SPEED = 1\n", new="SPEED = 2\n")
    [row] = c.get("/api/v1/admin/changes").json()["changes"]
    asked = []
    monkeypatch.setattr(house_actions, "house_busy", lambda db, music=True: asked.append(music) or True)
    for action in ("apply", "undo"):
        monkeypatch.setattr(tool_code, "backups", lambda: [row["id"]] if action == "undo" else [])
        refused = c.post(f"/api/v1/admin/changes/{row['id']}/{action}", json={"digest": row["digest"]})
        assert refused.status_code == 409 and "A film is playing" in refused.json()["detail"], action
    assert asked == [False, False]
    assert not (settings.runtime_root / "run/helper-in").exists()
    assert c.post(f"/api/v1/admin/changes/{row['id']}/keep").json()["status"] == "accepted"  # no restart


def test_a_stale_draft_cannot_be_applied(client, repo):
    c, db = client
    admin(client)
    tool("code_edit", path=APP, old="SPEED = 1\n", new="SPEED = 2\n")
    (repo / "backend/houseos/other.py").write_text("x = 1\n")
    git(repo, "add", "backend/houseos/other.py")
    git(repo, "commit", "-qm", "someone else")
    [row] = c.get("/api/v1/admin/changes").json()["changes"]
    assert row["stale"] is True
    refused = c.post(f"/api/v1/admin/changes/{row['id']}/apply", json={"digest": row["digest"]})
    assert refused.status_code == 409 and "draft it again" in refused.json()["detail"]


def test_the_host_leaves_other_readers_notes(repo, monkeypatch):
    monkeypatch.setenv("HOUSEOS_ENCRYPTION_KEY", KEY)
    host = code_change(monkeypatch)
    inbox = settings.runtime_root / "run/helper-in"
    other = house_actions.send("update")
    inbox.joinpath("junk.json").write_text("{}")
    assert host.notes() == [] and [p.stem for p in inbox.iterdir()] == [other]
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 3600)  # a note dated an hour ahead
    house_actions.send("code-keep", "0" * 12)
    monkeypatch.setattr(time, "time", real)
    assert host.notes() == [] and [p.stem for p in inbox.iterdir()] == [other]


def test_the_host_never_imports_the_app(tmp_path):
    """Its rules come from code_rules.py alone: the package's __init__ is app code."""
    loaded = subprocess.run(
        [sys.executable, "-c", "import importlib.util as u, sys\n"
         "s = u.spec_from_file_location('c', sys.argv[1]); s.loader.exec_module(u.module_from_spec(s))\n"
         "print(sorted(m for m in sys.modules if m.split('.')[0] == 'houseos'))", shipped("code_change.py")],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(ROOT / "backend"), "HOUSEOS_RUNTIME_ROOT": str(tmp_path)},
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert loaded.strip() == "[]"


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap is not installed")
def test_the_checks_jail_sees_only_the_checkout_and_its_tools(repo, tmp_path, monkeypatch):
    module = code_change(monkeypatch)
    runtime = tmp_path / "runtime"
    for name in ("frontend", "build/frontend", "venvs"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    (runtime / "venvs/app").symlink_to(sys.prefix)  # the app's venv, as the house has it
    module.RUNTIME, module.SOURCE, module.PYTHON = (
        runtime,
        repo.resolve(),
        str(runtime / "venvs/app/bin/python"),
    )
    seen = json.loads(module.run(
        module.PYTHON, "-c", "import json, os, socket, sqlalchemy, sys\nprint(json.dumps({"
        "'root': os.listdir('/'), 'venv': os.path.exists(sys.argv[1]), 'app': os.path.isfile('backend/houseos/app.py'),"
        "'net': socket.socket().connect_ex(('1.1.1.1', 53))}))", sys.prefix, jail=True,
    ))  # fmt: skip
    # The system, /tmp (the checkout here) and the Python it runs on; no /run, /var, /storage.
    assert set(seen["root"]) <= {
        "usr",
        "etc",
        "bin",
        "sbin",
        "lib",
        "lib64",
        "lib32",
        "dev",
        "proc",
        "tmp",
        "home",
    }
    assert seen["app"] and not seen["venv"] and seen["net"]  # the venv only where the checks look


def test_a_draft_saved_meanwhile_waits_for_apply(repo):
    """Nox's tools and the Changes page take turns: a request can't be dropped by a stale save."""
    done = []
    with tool_code.locked():
        writer = threading.Thread(target=lambda: done.append(tool("code_write", path=NEW, content="x = 1\n")))
        writer.start()
        writer.join(0.3)
        assert writer.is_alive() and not done
    writer.join(5)
    assert done[0]["status"] == "completed"


def test_the_broker_lets_the_code_user_restart_app_services_only(monkeypatch):
    import pwd

    real = pwd.getpwnam
    me = os.getuid()
    names = {"houseos": me + 1, "coder": me}
    monkeypatch.setattr(
        pwd, "getpwnam", lambda n: SimpleNamespace(pw_uid=names[n]) if n in names else real(n)
    )
    monkeypatch.setenv("HOUSEOS_CODE_USER", "coder")
    spec = importlib.util.spec_from_file_location("houseos_broker_test", shipped("control_broker.py"))
    broker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broker)
    ran = []
    monkeypatch.setattr(
        broker.subprocess,
        "run",
        lambda args, **_: ran.append(args) or SimpleNamespace(returncode=0, stdout=""),
    )

    def ask(action, service):
        ours, theirs = socket.socketpair()
        with ours, theirs:
            theirs.sendall(json.dumps({"action": action, "service": service}).encode() + b"\n")
            broker.Handler(ours, None, None)
            return json.loads(theirs.recv(1000))["status"]

    assert ask("restart", "api") == "accepted" and ask("status", "worker") == "observed"
    for action, service in (
        ("shutdown", "houseos"),
        ("restart", "audio"),
        ("restart", "media"),
        ("stop", "api"),
    ):
        assert ask(action, service) == "denied", (action, service)
    assert [args[-1] for args in ran] == [
        "houseos-api.service",
        "--property=ActiveState,SubState,ExecMainStatus,InvocationID",
    ]


@pytest.fixture
def host(repo, tmp_path, monkeypatch):
    """deploy/code_change.py on the temporary repository, with fake checks, deploy and restarts."""
    module = code_change(monkeypatch)
    runtime = tmp_path / "runtime"
    for name in ("releases/20260101T000000Z", "releases/20260102T000000Z", "run/code", "run/helper-out"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    (runtime / "current").symlink_to(runtime / "releases/20260102T000000Z")
    (runtime / "previous").symlink_to(runtime / "releases/20260101T000000Z")
    module.RUNTIME, module.SOURCE = runtime, repo.resolve()
    module.CLEAN = {**module.CLEAN, "PATH": os.environ["PATH"]}
    events = SimpleNamespace(check_ok=True, healthy=True, restarts=[], film=False)

    def deploy():  # as release.py: a new release becomes current, the old one previous
        release = runtime / "releases/20260103T000000Z"
        release.mkdir()
        (runtime / "previous").unlink()
        (runtime / "previous").symlink_to((runtime / "current").resolve())
        module.switch(release)

    def checks(before):
        if not events.check_ok:
            raise module.Failed("ruff check failed")

    monkeypatch.setattr(module, "failures", set)
    monkeypatch.setattr(module, "checks", checks)
    monkeypatch.setattr(module, "deploy", deploy)
    monkeypatch.setattr(module, "running", lambda: {"api", "worker"})
    monkeypatch.setattr(module, "restart", lambda services: events.restarts.append(sorted(services)))
    monkeypatch.setattr(module, "healthy", lambda services: events.healthy)
    monkeypatch.setattr(module, "film_on", lambda: events.film)
    tool("code_edit", path=APP, old="SPEED = 1\n", new="SPEED = 2\n", summary="Faster")
    tool("code_write", path=NEW, content="NEW = True\n")
    [change] = tool_code.changes()
    return module, change["id"], events, runtime, code_rules.digest(change)


def current(runtime):
    return (runtime / "current").resolve().name


def test_failed_checks_leave_the_checkout_as_it_was(host, repo):
    module, identity, events, runtime, reviewed = host
    base = git(repo, "rev-parse", "HEAD")
    events.check_ok = False
    with pytest.raises(module.Failed, match="did not pass its checks"):
        module.apply(identity, reviewed)
    assert git(repo, "rev-parse", "HEAD") == base and not git(repo, "tag", "-l")
    assert (repo / APP).read_text().startswith("SPEED = 1") and not (repo / NEW).exists()
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert current(runtime) == "20260102T000000Z" and not events.restarts


def test_an_unhealthy_house_goes_back_by_itself(host, repo):
    module, identity, events, runtime, reviewed = host
    base = git(repo, "rev-parse", "HEAD")
    events.healthy = False
    with pytest.raises(module.Failed, match="went back"):
        module.apply(identity, reviewed)
    assert git(repo, "rev-parse", "HEAD") == base and not git(repo, "tag", "-l")
    assert current(runtime) == "20260102T000000Z" and not (repo / NEW).exists()
    assert len(events.restarts) == 2


def test_apply_then_keep_deletes_the_backup(host, repo):
    module, identity, events, runtime, reviewed = host
    assert module.apply(identity, reviewed)["commit"]
    assert git(repo, "log", "-1", "--format=%s") == "Nox: Faster"
    assert (repo / NEW).read_text() == "NEW = True\n"
    assert git(repo, "tag", "-l") == "houseos-backup/" + identity
    assert current(runtime) == "20260103T000000Z" and events.restarts == [["api", "worker"]]
    # The backup release is `previous` now: Keep leaves the release in place, the tag goes.
    module.keep(identity)
    assert not git(repo, "tag", "-l") and (runtime / "releases/20260102T000000Z").is_dir()


def test_a_film_on_the_house_computer_holds_back_apply_and_undo(host, repo):
    module, identity, events, runtime, reviewed = host
    base = git(repo, "rev-parse", "HEAD")
    events.film = True
    with pytest.raises(module.Failed, match="A film is playing"):
        module.apply(identity, reviewed)
    assert git(repo, "rev-parse", "HEAD") == base and not git(repo, "tag", "-l")
    assert not (repo / NEW).exists() and current(runtime) == "20260102T000000Z" and not events.restarts
    events.film = False
    module.apply(identity, reviewed)
    events.film = True
    with pytest.raises(module.Failed, match="A film is playing"):
        module.undo(identity)
    assert git(repo, "tag", "-l") == "houseos-backup/" + identity and len(events.restarts) == 1


def test_the_film_check_keeps_the_database_address_out_of_the_log(repo, monkeypatch, tmp_path):
    monkeypatch.setenv("HOUSEOS_DATABASE_URL", "mysql://houseos:never-logged@127.0.0.1:1/houseos")
    module = code_change(monkeypatch)
    module.PYTHON = sys.executable
    assert module.film_on() is True  # no answer: wait
    assert "never-logged" not in "\n".join(module.LOG)


def test_apply_then_undo_returns_to_the_backup(host, repo):
    module, identity, events, runtime, reviewed = host
    base = git(repo, "rev-parse", "HEAD")
    module.apply(identity, reviewed)
    module.undo(identity)
    assert git(repo, "rev-parse", "HEAD") == base and not git(repo, "tag", "-l")
    assert current(runtime) == "20260102T000000Z" and not (repo / NEW).exists()


def test_the_host_applies_only_the_reviewed_diff(host, repo):
    module, identity, events, runtime, reviewed = host
    path = runtime / "run/code" / (identity + ".json")
    change = json.loads(path.read_text())
    with pytest.raises(module.Failed, match="edited after it was reviewed"):
        module.apply(identity, "0" * 64)
    # A path Nox may not change, even with a digest that matches it.
    for bad in ("deploy/release.py", "backend/houseos/deploy_link.py", "backend/tests/conftest.py"):
        edited = {**change, "files": {bad: "x\n"}, "before": {bad: ""}}
        path.write_text(json.dumps(edited))
        with pytest.raises(module.Failed, match="may not change"):
            module.apply(identity, code_rules.digest(edited))
    assert (repo / "deploy/release.py").read_text() == "print('release')\n"
    assert not git(repo, "tag", "-l") and not events.restarts


def test_the_host_refuses_a_file_that_differs_from_the_diffs_before(repo, host):
    module, identity, events, runtime, reviewed = host
    tool("code_discard")
    (repo / APP).write_text("SPEED = 9\nSPEED_TOO = 1\n")  # drafted over an edit nobody committed
    tool("code_edit", path=APP, old="SPEED_TOO = 1\n", new="SPEED_TOO = 2\n")
    git(repo, "checkout", "--", APP)
    [change] = tool_code.changes()
    with pytest.raises(module.Failed, match="not as the reviewed diff showed it"):
        module.apply(change["id"], code_rules.digest(change))
    assert not git(repo, "tag", "-l") and (repo / APP).read_text() == "SPEED = 1\nSPEED_TOO = 1\n"


def test_the_host_refuses_an_edited_checkout_and_reports_through_notes(host, repo, monkeypatch):
    module, identity, events, runtime, reviewed = host
    (repo / APP).write_text("edited by someone\n")
    with pytest.raises(module.Failed, match="edits nobody committed"):
        module.apply(identity, reviewed)
    git(repo, "checkout", "--", APP)

    monkeypatch.setenv("HOUSEOS_ENCRYPTION_KEY", KEY)
    request = house_actions.send("code-apply", identity + ":" + reviewed)
    module.main()
    report = json.loads((runtime / "run/helper-out" / (request + ".json")).read_text())
    assert report["state"] == "done" and "Keep it or undo it" in report["message"]
    assert tool_code.load(identity)

    # Nox's own list never carries what the house computer printed (test output); the page does.
    change = tool_code.load(identity)
    change["requests"].append({"action": "apply", "id": request, "at": 0, "by": "Ada"})
    tool_code.save(change)
    (runtime / "run/helper-out" / (request + ".log")).write_text("FAILED tests/x.py secret-looking output")
    listed = json.dumps(tool("code_list"))
    assert "Keep it or undo it" not in listed and "secret-looking" not in listed


def test_houseos_sh_parses_and_passes_shellcheck():
    script = shipped("houseos.sh")
    subprocess.run(["bash", "-n", script], check=True)
    if shutil.which("shellcheck"):
        found = subprocess.run(["shellcheck", "-S", "warning", script], capture_output=True, text=True)
        assert found.returncode == 0, found.stdout
