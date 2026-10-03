"""Fixtures shared across test files: an isolated database with residents (domain, setup,
client), the files API over it (file_app), and quiet stand-ins for sockets and services."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Text, cast, create_engine, delete, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from houseos import files as f, household as h, integrations
from houseos.auth import RESIDENT, Actor, require_actor
from houseos.config import settings
from houseos.db import Base, get_db, new_id
from houseos.models import Event, Integration, Record, User


@pytest.fixture(autouse=True)
def fresh_audio_output_snapshot():
    # audio.output_snapshot caches pactl results for 2 s; tests patch outputs per case.
    from houseos import audio

    audio._outputs_cache = (0.0, None)


@pytest.fixture
def domain():
    if os.environ.get("HOUSEOS_TEST_MARIADB") == "1":
        url = os.environ["DATABASE_URL"].replace("mysql://", "mysql+pymysql://", 1)
        engine = create_engine(url, hide_parameters=True)
        assert engine.url.database == "houseos_test", "Refusing to write outside isolated houseos_test"
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        actors = []
        for name in ("Alice", "Bob", "Cara"):
            user = User(
                id=new_id(),
                name=name,
                username=name.lower() + "-" + new_id()[:8],
                password_hash="test-only",
                role="resident",
                permissions=list(RESIDENT),
            )
            db.add(user)
            actors.append(Actor(user.id, name, "resident", RESIDENT))
        db.commit()
        try:
            yield db, actors
        finally:
            if engine.dialect.name != "sqlite":
                # Remove exactly this fixture's randomly generated actors and dependent rows.
                # Never drop/truncate tables in the shared test database.
                db.rollback()
                ids = [a.id for a in actors]
                records = db.scalars(select(Record.id).where(Record.owner_id.in_(ids))).all()
                entries = db.scalars(select(f.FileEntry.id).where(f.FileEntry.owner_id.in_(ids))).all()
                from houseos.notifications import PushSubscription, PushDelivery
                from houseos.assistant import ChatReceipt, ChatMessage
                from houseos.models import Usage, SessionToken, Operation, Job

                notices = db.scalars(
                    select(h.HouseholdNotification.id).where(h.HouseholdNotification.user_id.in_(ids))
                ).all()
                subs = db.scalars(select(PushSubscription.id).where(PushSubscription.user_id.in_(ids))).all()
                db.execute(delete(Job).where(Job.actor_id.in_(ids)))
                db.execute(delete(Operation).where(Operation.actor_id.in_(ids)))
                db.execute(delete(ChatReceipt).where(ChatReceipt.owner_id.in_(ids)))
                db.execute(delete(ChatMessage).where(ChatMessage.owner_id.in_(ids)))
                db.execute(delete(Usage).where(Usage.user_id.in_(ids)))
                db.execute(delete(SessionToken).where(SessionToken.user_id.in_(ids)))
                db.execute(
                    delete(PushDelivery).where(
                        or_(PushDelivery.subscription_id.in_(subs), PushDelivery.notification_id.in_(notices))
                    )
                )
                db.execute(delete(PushSubscription).where(PushSubscription.user_id.in_(ids)))
                db.execute(
                    delete(h.MessageRecipient).where(
                        or_(h.MessageRecipient.user_id.in_(ids), h.MessageRecipient.message_id.in_(records))
                    )
                )
                db.execute(delete(h.HouseholdNotification).where(h.HouseholdNotification.user_id.in_(ids)))
                db.execute(delete(h.HouseholdReceipt).where(h.HouseholdReceipt.actor_id.in_(ids)))
                db.execute(delete(h.TaskOccurrence).where(h.TaskOccurrence.template_id.in_(records)))
                db.execute(delete(f.FileConfirmation).where(f.FileConfirmation.actor_id.in_(ids)))
                db.execute(
                    delete(f.FileGrant).where(
                        or_(f.FileGrant.user_id.in_(ids), f.FileGrant.file_id.in_(entries))
                    )
                )
                db.execute(delete(f.UploadReservation).where(f.UploadReservation.owner_id.in_(ids)))
                db.execute(delete(f.FileEntry).where(f.FileEntry.owner_id.in_(ids)))
                db.execute(delete(Record).where(Record.owner_id.in_(ids)))
                event_conditions = [Event.user_id.in_(ids)] + [
                    cast(Event.payload, Text).contains(identifier, autoescape=True)
                    for identifier in records + entries
                ]
                db.execute(delete(Event).where(or_(*event_conditions)))
                db.execute(delete(User).where(User.id.in_(ids)))
                db.commit()
    engine.dispose()


@pytest.fixture
def file_app(domain, tmp_path, monkeypatch):
    db, actors = domain
    real_storage = os.environ.get("HOUSEOS_TEST_STORAGE_REAL") == "1"
    # The real disk: set HOUSEOS_STORAGE_MOUNT and HOUSEOS_STORAGE_UUID; tests write under <mount>/scratch.
    scratch = Path(settings.storage_mount) / "scratch"
    root = scratch / ("houseos-test-" + new_id()) if real_storage else tmp_path / "data"
    (root / "staging").mkdir(parents=True)
    (root / "blobs").mkdir()
    monkeypatch.setattr(settings, "data_root", root)
    monkeypatch.setattr(settings, "runtime_root", tmp_path / "runtime")
    if not real_storage:
        monkeypatch.setattr(f, "storage_check", lambda: {"status": "healthy"})
    app = FastAPI()
    app.include_router(f.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_actor] = lambda: actors[0]
    try:
        with TestClient(app) as client:
            yield client, db, actors, root, app
    finally:
        if real_storage:
            import shutil

            assert root.parent == scratch and root.name.startswith("houseos-test-")
            shutil.rmtree(root)


@pytest.fixture
def client(monkeypatch):
    from houseos.main import app
    from houseos.music import QueueState

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "bootstrap_token", "test-only-bootstrap-token-capability")
    monkeypatch.setattr(settings, "cookie_secure", False)
    with Session(engine, expire_on_commit=False) as db:
        db.add(QueueState(id=1))
        db.add(Integration(name="budgets", config={}, enabled=False))
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app, headers={"Origin": settings.allowed_origins.split(",")[0]}) as c:
            yield c, db
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(integrations.settings, "encryption_key", Fernet.generate_key().decode())
    with Session(engine, expire_on_commit=False) as db:
        actors = []
        for name in ("Alice", "Bob"):
            user = User(
                id=new_id(),
                username=name,
                name=name,
                role="admin",
                permissions=list(RESIDENT),
                password_hash="unused",
            )
            db.add(user)
            actors.append(Actor(user.id, name, "admin", RESIDENT))
        db.commit()
        yield db, actors


@pytest.fixture
def music_domain(domain, monkeypatch):
    db, actors = domain
    assert db.bind.dialect.name == "mysql", "Run with HOUSEOS_TEST_MARIADB=1"
    from houseos import music as m, music_library as lib

    q = SimpleNamespace(current_id=None, desired="paused", failures=0, sleep_at=None, version=1)
    monkeypatch.setattr(m, "queue", lambda db: q)
    monkeypatch.setattr(m, "read_queue", lambda db: q)
    monkeypatch.setattr(lib, "queue", lambda db: q)
    try:
        yield db, actors, q
    finally:
        db.rollback()
        db.execute(delete(m.QueueItem).where(m.QueueItem.owner_id.in_([a.id for a in actors])))
        db.commit()


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    """No sockets, no uploads server, no speakers: a brand-new container."""
    from houseos import house_setup

    monkeypatch.setattr(house_setup, "RUN", tmp_path)
    monkeypatch.setattr(settings, "audio_socket", tmp_path / "audio.sock")
    monkeypatch.setattr(settings, "codex_socket", tmp_path / "codex.sock")
    monkeypatch.setattr(settings, "claude_socket", tmp_path / "claude.sock")
    monkeypatch.setattr(settings, "tusd_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "storage_container", True)
    import houseos.music as music

    monkeypatch.setattr(music, "bridge", lambda *a, **k: {"status": "unavailable"})
    return tmp_path


@pytest.fixture
def studio_home(tmp_path, monkeypatch):
    from houseos import assistant as a

    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(a, "start_background", lambda target, *args: target(*args))
    return tmp_path


@pytest.fixture
def provider_probe(domain, monkeypatch):
    from houseos import assistant as a, provider_checks as checks
    from houseos.auth import passwords

    db, (alice, _, _) = domain
    name = "test-" + new_id()[:12]
    user = db.get(User, alice.id)
    user.role, user.password_hash = "admin", passwords.hash("fixture-password")
    actor = Actor(alice.id, alice.name, "admin", alice.permissions)
    cfg = {
        "model": "test-model",
        "input_microusd_per_million": 0,
        "output_microusd_per_million": 1_000_000,
        "daily_budget_microusd": 1000,
        "user_daily_budget_microusd": 1000,
        "max_output_tokens": 32,
    }
    db.add(Integration(name=name, enabled=True, config=cfg))
    db.commit()
    monkeypatch.setattr(checks, "AI_PROVIDERS", (name,))

    def config(session, identity, **kwargs):
        return {**session.get(Integration, identity).config, "api_key": "fixture-not-real"}

    monkeypatch.setattr(checks, "integration_config", config)
    monkeypatch.setattr(a, "integration_config", config)
    try:
        yield checks, db, actor, name
    finally:
        db.rollback()
        db.execute(delete(Integration).where(Integration.name == name))
        db.commit()
