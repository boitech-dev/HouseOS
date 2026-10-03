"""Every Nox tool in every bundle, called the way the chat loop calls it (assistant.execute_tool)
with minimal valid arguments made from its own schema, invalid arguments, and as a resident. No
tool may raise past its own error handling: the loop's catch-all must never be what saves a call.
New tools are covered automatically. Network, subprocesses and threads are refused."""

import json
import re
import signal
import socket
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import houseos.main  # noqa: F401  every router's tables exist before create_all
from houseos import assistant as a, assistant_tools as t, db as hdb, files, integrations
from houseos.auth import RESIDENT, Actor
from houseos.config import settings
from houseos.db import Base, new_id
from houseos.models import Integration, Record, User

SECRET = "fixture-sentinel-secret-7f3a9c"


def refused(*args, **kwargs):
    raise OSError(111, "refused in test_every_tool")


def too_slow(*_):
    raise TimeoutError("the tool took over 10 s")


@pytest.fixture
def house(quiet, tmp_path, monkeypatch):
    for name in ("runtime_root", "data_root", "storage_mount", "import_root"):
        monkeypatch.setattr(settings, name, tmp_path / name)
    (tmp_path / "data_root/staging").mkdir(parents=True)
    (tmp_path / "data_root/blobs").mkdir()
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(files, "storage_check", lambda: {"status": "healthy"})
    for method in ("connect", "connect_ex", "sendto", "sendmsg"):
        monkeypatch.setattr(socket.socket, method, refused)
    monkeypatch.setattr(socket, "getaddrinfo", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    for name in ("Popen", "run", "check_output", "call"):
        monkeypatch.setattr(subprocess, name, refused)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)  # background work stays off
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(hdb, "engine", engine)
    bound = dict(hdb.SessionLocal.kw)
    alarm = signal.signal(signal.SIGALRM, too_slow)
    hdb.SessionLocal.configure(bind=engine)  # tools that open their own session use this house
    try:
        with Session(engine, expire_on_commit=False) as db:
            from houseos.music import QueueState

            db.add(QueueState(id=1))
            people = []
            for name, role in (("Admin", "admin"), ("Rita", "resident")):
                user = User(
                    id=new_id(),
                    name=name,
                    username=name.lower(),
                    password_hash="-",
                    role=role,
                    permissions=list(RESIDENT),
                )
                db.add(user)
                people.append(Actor(user.id, name, role, RESIDENT))
            secret = json.dumps({"api_key": SECRET, "token": SECRET}).encode()
            secret = Fernet(settings.encryption_key.encode()).encrypt(secret).decode()
            for name in sorted(integrations.NAMES):
                config = {"model": "small", "daily_budget_microusd": 10**6, "password": SECRET}
                if name in integrations.ENDPOINTS:
                    config["base_url"] = "http://device.invalid:8123"
                db.add(Integration(name=name, enabled=True, config=config, encrypted_secret=secret))
            db.commit()
            yield db, people
    finally:
        hdb.SessionLocal.kw.clear()
        hdb.SessionLocal.kw.update(bound)
        signal.signal(signal.SIGALRM, alarm)
        engine.dispose()


def resolve(schema, defs):
    while "$ref" in schema:
        schema = defs[schema["$ref"].split("/")[-1]]
    return schema


def fill(schema, defs, name=""):
    """Minimal valid arguments from a JSON schema."""
    schema = resolve(schema, defs)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if resolve(o, defs).get("type") != "null"]
            return fill(options[0], defs, name)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {p: fill(schema["properties"][p], defs, p) for p in schema.get("required", [])}
    if kind == "array":
        item = schema.get("items", {"type": "string"})
        return [fill(item, defs, name) for _ in range(max(1, schema.get("minItems", 1)))]
    if kind == "boolean":
        return True
    if kind in ("integer", "number"):
        low = schema.get("minimum", schema.get("exclusiveMinimum", -1) + 1)
        low = max(low, 1) if name in ("version", "expected_version") else low
        low = min(low, schema.get("maximum", low))
        return int(low) if kind == "integer" else float(low)
    if schema.get("format") == "date-time":
        return (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    if schema.get("format") == "date":
        return datetime.now(UTC).date().isoformat()
    if re.search(r"(^|_)ids?$", name):
        return new_id()
    if "url" in name or schema.get("format") == "uri":
        return "https://example.invalid/x"
    if schema.get("pattern"):
        for candidate in ("2", "en", "abc", "a-b", "a", "#112233", "12:00", "x1"):
            if re.search(schema["pattern"], candidate):
                return candidate
    text = {"query": "jazz", "text": "tea", "name": "test", "body": "hello"}.get(name, "test")
    text = text.ljust(schema.get("minLength", 1), "x")
    return text[: schema.get("maxLength", 1000)]


def args_for(model):
    schema = model.model_json_schema()
    return fill(schema, schema.get("$defs", {}))


def run(db, actor, context, registry, name, args):
    """One call as the loop makes it; returns (result, the exception that escaped the tool)."""
    model, description, handler = registry[name]
    escaped = []

    def watched(body, who, session):
        try:
            return handler(body, who, session)
        except (HTTPException, ValidationError):
            raise  # the loop's own failure shapes
        except BaseException as exc:
            escaped.append(exc)
            raise

    turn = SimpleNamespace(
        registry={**registry, name: (model, description, watched)},
        actor=actor,
        context=context,
        conversation_id=None,
        body=SimpleNamespace(message="please remember this", purpose="general"),
        user_message=SimpleNamespace(id=new_id()),
        argument_repair_used=False,
        music_candidates={},
        music_repair_used=False,
    )
    signal.setitimer(signal.ITIMER_REAL, 10)  # a hung tool fails instead of hanging the suite
    try:
        result = a.execute_tool(turn, db, {"name": name, "args": json.loads(json.dumps(args)), "id": "c1"})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    db.rollback()
    if result.get("code") == "TOOL_ERROR" and not escaped:
        escaped.append(RuntimeError("the loop's catch-all answered"))
    return result, (escaped[0] if escaped else None)


def seed(db, admin):
    """Real rows, so id-taking tools reach their logic rather than only 'not found'."""
    general = t.tool_registry("general")
    for kind, data in (("tasks", {"title": "Dishes"}), ("groceries", {"label": "Milk"})):
        run(db, admin, "general", general, "household_create", {"item": {"kind": kind, "data": data}})
    run(db, admin, "files", t.tool_registry("files"), "files_folder", {"name": "Docs"})
    run(db, admin, "general", general, "radio_queue", {"id": new_id()})
    memory = a.save_memory(a.Memory(text="likes tea"), admin, db)
    task = db.query(Record).filter(Record.kind == "household.tasks").one()
    grocery = db.query(Record).filter(Record.kind == "household.groceries").one()
    folder = db.query(files.FileEntry).one()
    from houseos import music

    item = db.query(music.QueueItem).one()
    queued = {"item_id": item.id, "expected_version": music.queue(db).version}
    db.rollback()
    return {
        "memory_delete": {"id": memory["id"]},
        "task_action": {"id": task.id, "version": task.version, "action": "claim"},
        "groceries_purchase": {"items": [{"id": grocery.id, "version": grocery.version}], "purchased": True},
        "files_move": {"id": folder.id, "version": folder.version, "name": "Docs2"},
        "files_prepare": {"id": folder.id, "version": folder.version, "action": "trash"},
        "files_read_excerpt": {"file_id": folder.id, "version": folder.version},
        "music_remove": queued,
        "music_veto": queued,
        "music_reorder": queued,
        "music_add": {"source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        "music_save": {"source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        "access_add": {"origin": "https://house.example.lan"},
        "theme_read": {"id": "pure", "file": "theme.json"},
    }


def contexts():
    for context in [*t.BUNDLES, "personal_space", "themes"]:
        yield context, t.tool_registry(context)


def test_every_catalogue_tool_is_reachable_from_a_bundle():
    bundled = {name for names in t.BUNDLES.values() for name in names}
    assert set(t.tool_catalogue()) - bundled == set()


def test_every_tool_runs_without_an_unhandled_error(house):
    db, (admin, rita) = house
    overrides = seed(db, admin)
    problems, seen = [], set()
    for context, registry in contexts():
        for name, (model, description, _) in registry.items():
            if (name, description) in seen:  # the same tool in another bundle
                continue
            seen.add((name, description))
            valid = overrides.get(name) or args_for(model)
            schema = model.model_json_schema()
            required = [r for r in schema.get("required", []) if r != "idempotency_key"]
            invalid = {**valid, required[0]: {"wrong": ["type"]}} if required else {"bogus_field": 1}
            for label, actor, args in (
                ("valid", admin, valid),
                ("invalid", admin, invalid),
                ("resident", rita, valid),
            ):
                result, escaped = run(db, actor, context, registry, name, args)
                where = f"{context}/{name} {label}"
                if escaped:
                    problems.append(f"{where}: {type(escaped).__name__}: {escaped}")
                if label == "invalid" and result.get("code") != "INVALID_TOOL_ARGUMENTS":
                    problems.append(f"{where}: invalid arguments were not refused: {result}")
                if SECRET in json.dumps(result, default=str):
                    problems.append(f"{where}: a stored secret reached the result")
    assert len(seen) > 100
    assert problems == []
