from unittest.mock import patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from houseos import personal_space as space
from houseos.auth import Actor, require_actor
from houseos.db import get_db
from houseos.playback import MediaError
import test_cinema


def test_feed_rejects_entities_and_unsafe_links():
    space.feed_items.cache_clear()
    xml = b"<rss><channel><item><title>Good</title><link>https://www.bbc.com/news/articles/123</link></item><item><title>Bad</title><link>javascript:alert(1)</link></item></channel></rss>"
    with patch.object(space, "public_fetch", return_value=(xml, {})):
        assert [v["title"] for v in space.feed_items("technology", 0)] == ["Good"]
    with patch.object(space, "public_fetch", return_value=(b"<!DOCTYPE rss><rss/>", {})):
        with pytest.raises(MediaError):
            space.feed_items("technology", 1)
    space.feed_items.cache_clear()


def test_favorites_private_idempotent_and_guest_denied():
    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    app = FastAPI()
    app.include_router(space.router)
    app.dependency_overrides[get_db] = fixture.app.dependency_overrides[get_db]
    actor = fixture.actor
    app.dependency_overrides[require_actor] = lambda: actor
    client = TestClient(app)
    try:
        with patch.object(space, "anime_detail", return_value={"id": "1", "title": "Fixture anime"}):
            assert client.put("/personal-space/favorites/1").status_code == 200
            assert client.put("/personal-space/favorites/1").status_code == 200
        assert len(client.get("/personal-space/favorites").json()["items"]) == 1
        actor = Actor("resident-two", "Two", "resident", frozenset())
        assert client.get("/personal-space/favorites").json()["items"] == []
        client.delete("/personal-space/favorites/1")
        actor = fixture.actor
        assert len(client.get("/personal-space/favorites").json()["items"]) == 1
        client.delete("/personal-space/favorites/1")
        assert client.get("/personal-space/favorites").json()["items"] == []
        actor = Actor("guest", "Guest", "guest", frozenset())
        assert client.get("/personal-space/anime").status_code == 403
    finally:
        fixture.tearDown()
