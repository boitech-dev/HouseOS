"""Sharing projects only explicit canonical titles, never another resident's state."""

from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from houseos import cinema_watchlist as watchlist
from houseos.auth import Actor, RESIDENT, require_actor
from houseos.cinema import CinemaTitle, CinemaState
from houseos.db import Base, get_db, utcnow
from houseos.models import User, Record


def test_shared_watchlist_private_default_and_immediate_unshare_and_revoke():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(watchlist.router)
    actor = Actor("alice", "Alice", "resident", RESIDENT)
    app.dependency_overrides[require_actor] = lambda: actor
    with Session(engine, expire_on_commit=False) as db:
        app.dependency_overrides[get_db] = lambda: db
        db.add_all(
            [
                User(id=name, name=name, username=name, role="resident", password_hash="fixture")
                for name in ("alice", "bob")
            ]
        )
        db.add(
            CinemaTitle(
                id="title", canonical_id="tt-fixture", title="Shared film", kind="movie", data={"year": 2000}
            )
        )
        db.add(
            CinemaState(
                owner_id="alice",
                media_id="title",
                data={"watchlist": True, "position": 1234, "preferred_release": "PRIVATE_MARKER"},
                last_watched_at=utcnow(),
            )
        )
        db.commit()
        with TestClient(app) as c:
            assert c.get("/cinema/shared-watchlist").json()["items"] == []
            assert c.put("/cinema/shared-watchlist/title").status_code == 200
            assert c.put("/cinema/shared-watchlist/title").status_code == 200
            actor = Actor("bob", "Bob", "resident", RESIDENT)
            result = c.get("/cinema/shared-watchlist")
            assert len(result.json()["items"]) == 1
            assert result.json()["items"][0]["shared_by"]["id"] == "alice"
            assert (
                "PRIVATE_MARKER" not in result.text
                and "1234" not in result.text
                and "last_watched_at" not in result.text
            )
            assert c.delete("/cinema/shared-watchlist/title").status_code == 200
            assert len(c.get("/cinema/shared-watchlist").json()["items"]) == 1  # Bob cannot unshare Alice.
            db.get(User, "alice").active = False
            db.commit()
            assert c.get("/cinema/shared-watchlist").json()["items"] == []
            db.get(User, "alice").active = True
            db.get(User, "alice").expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
            assert c.get("/cinema/shared-watchlist").json()["items"] == []
            db.get(User, "alice").expires_at = None
            db.get(User, "alice").role = "guest"
            db.commit()
            assert c.get("/cinema/shared-watchlist").json()["items"] == []
            db.get(User, "alice").role = "resident"
            db.commit()
            actor = Actor("alice", "Alice", "resident", RESIDENT)
            assert c.delete("/cinema/shared-watchlist/title").status_code == 200
            assert c.get("/cinema/shared-watchlist").json()["items"] == []
            assert db.query(CinemaState).one().data["watchlist"] is True
            assert db.query(Record).filter_by(kind=watchlist.KIND).count() == 1
            actor = Actor("bob", "Bob", "guest", frozenset({"music.read"}))
            assert c.get("/cinema/shared-watchlist").status_code == 403
            assert c.put("/cinema/shared-watchlist/title").status_code == 403
    engine.dispose()
