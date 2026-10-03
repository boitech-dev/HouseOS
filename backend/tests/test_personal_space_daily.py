import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from houseos import personal_space as space


def test_first_visit_fetches_nothing_and_configuration_is_private(domain, monkeypatch):
    db, (alice, bob, _) = domain
    monkeypatch.setattr(space, "daily_source", lambda *args: pytest.fail("Unconfigured space must not fetch"))
    assert space.configuration(alice, db) == {
        "configured": False,
        "version": 0,
        "config": None,
        "setup_complete": False,
        "conversation_id": None,
    }
    assert space.today(alice, db) == {"configured": False, "sections": []}
    saved = space.configure(
        space.SpaceConfig(
            news_interests=["technology"], subreddits=["r/Science"], art_tags=["cityscape"], daily_count=7
        ),
        alice,
        db,
    )
    assert saved["status"] == "configured" and saved["version"] == 1
    assert saved["subreddits"] == ["science"]
    assert space.configuration(bob, db)["configured"] is False
    with pytest.raises(HTTPException) as stale:
        space.configure(space.SpaceConfig(news_interests=["culture"]), alice, db)
    assert stale.value.status_code == 409
    for data in [
        {"subreddits": ["../../admin"]},
        {"subreddits": ["https://example.org"]},
        {"art_tags": ["rating:e"]},
        {"daily_count": 99},
    ]:
        with pytest.raises(ValidationError):
            space.SpaceConfig(**data)


def test_daily_snapshot_is_bounded_cached_source_attributed_and_private(domain, monkeypatch):
    db, (alice, bob, _) = domain
    space.configure(
        space.SpaceConfig(
            news_interests=["science", "technology"],
            subreddits=["science"],
            art_tags=["landscape"],
            daily_count=7,
        ),
        alice,
        db,
    )
    calls = []

    def source(kind, key, day):
        calls.append((kind, key, day))
        rows = [
            {
                "id": kind + key + str(i),
                "title": key + str(i),
                "provider": key,
                "_image_url": "https://cdn.donmai.us/example.jpg",
            }
            for i in range(20)
        ]
        return {"kind": kind, "key": key, "status": "ready", "items": rows}

    monkeypatch.setattr(space, "daily_source", source)
    result = space.today(alice, db)
    assert [len(section["items"]) for section in result["sections"]] == [7, 7, 7]
    assert all("_image_url" not in item for section in result["sections"] for item in section["items"])
    assert result["sections"][0]["items"][0]["provider"] == "fr_science"
    assert result["sections"][0]["items"][1]["provider"] == "fr_technology"
    assert space.today(alice, db) == result and len(calls) == 4
    assert space.today(bob, db)["sections"] == []
    with pytest.raises(HTTPException) as private:
        space.illustration_image(1, bob, db)
    assert private.value.status_code == 404


def test_sources_fail_truthfully_without_fake_fallback(domain, monkeypatch):
    db, (alice, _, _) = domain
    space.configure(space.SpaceConfig(subreddits=["science"]), alice, db)
    from houseos.playback import MediaError

    monkeypatch.setattr(
        space,
        "reddit_daily",
        lambda *args: (_ for _ in ()).throw(MediaError("SOURCE_NOT_READY", "Unavailable", "discover")),
    )
    result = space.today(alice, db)
    assert result["sections"][0]["items"] == []
    assert result["sections"][0]["sources"] == [
        {"key": "science", "status": "unavailable", "code": "SOURCE_NOT_READY"}
    ]
    assert result["retry_after"] > 0


def test_reddit_parser_rejects_entities_and_arbitrary_links():
    from houseos.playback import MediaError

    with pytest.raises(MediaError):
        space.parse_atom(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x/>', "science")
    xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A title</title><link href="https://www.reddit.com/r/Science/comments/test"/></entry><entry><title>Rejected</title><link href="http://127.0.0.1/private"/></entry></feed>'
    result = space.parse_atom(xml, "science")
    assert len(result) == 1 and result[0]["title"] == "A title"


def test_partial_configuration_preserves_modules_and_only_explicit_empty_disables(domain):
    db, (alice, _, _) = domain
    space.configure(
        space.SpaceConfig(
            news_interests=["science"], art_tags=["scenery"], daily_count=8, news_language="en"
        ),
        alice,
        db,
    )
    updated = space.configure(
        space.SpaceConfig(expected_version=1, subreddits=["technology"], news_interests=None, art_tags=None),
        alice,
        db,
    )
    assert updated["news_interests"] == ["science"] and updated["art_tags"] == ["scenery"]
    assert updated["daily_count"] == 8 and updated["news_language"] == "en"
    removed = space.configure(space.SpaceConfig(expected_version=2, news_interests=[]), alice, db)
    assert (
        removed["news_interests"] == []
        and removed["subreddits"] == ["technology"]
        and removed["art_tags"] == ["scenery"]
    )


def test_setup_resumes_until_resident_confirms_then_preserves_history(domain):
    from houseos import assistant
    from houseos.models import Record

    db, (alice, bob, _) = domain
    identity = assistant.create_conversation(
        assistant.NewConversation(title="My setup", purpose="personal_space"), alice, db
    )["id"]
    space.configure(space.SpaceConfig(subreddits=["science"]), alice, db)
    db.expire_all()  # Reload from persisted state, as after a browser refresh.
    current = space.configuration(alice, db)
    assert current["conversation_id"] == identity and not current["setup_complete"]
    assert space.configuration(bob, db)["conversation_id"] is None
    with pytest.raises(HTTPException):
        space.finish_setup(alice, db, identity, "change it, not good yet")
    with pytest.raises(HTTPException):
        space.finish_setup(bob, db, identity, "looks good")
    space.finish_setup(alice, db, identity, "c'est bon")
    finished = space.configuration(alice, db)
    assert finished["setup_complete"] and finished["conversation_id"] is None
    assert db.get(Record, identity).deleted_at is None
    assert any(row["id"] == identity for row in assistant.conversations(alice, db, purpose="personal_space"))
    newer = assistant.create_conversation(
        assistant.NewConversation(title="Change my space", purpose="personal_space"), alice, db
    )["id"]
    assert space.configuration(alice, db)["conversation_id"] == newer
    with pytest.raises(HTTPException):
        space.finish_setup(alice, db, identity, "looks good")
    # Force equal database timestamps and hostile UUID order: pointer still wins.
    old_row, new_row = db.get(Record, identity), db.get(Record, newer)
    new_row.updated_at = old_row.updated_at
    db.commit()
    db.expire_all()
    assert space.configuration(alice, db)["conversation_id"] == newer


def test_refreshes_at_twelve_hour_boundary(domain, monkeypatch):
    db, (alice, _, _) = domain
    space.configure(space.SpaceConfig(news_interests=["science"]), alice, db)
    clock = [1789992001.0]
    monkeypatch.setattr(space.time, "time", lambda: clock[0])
    calls = []

    def source(kind, key, bucket):
        calls.append(bucket)
        return {"kind": kind, "key": key, "status": "ready", "items": []}

    monkeypatch.setattr(space, "daily_source", source)
    space.today(alice, db)
    space.today(alice, db)
    assert len(calls) == 1
    clock[0] += 43200
    space.refresh_configured_spaces(db)
    assert len(calls) == 2 and calls[0] != calls[1]
