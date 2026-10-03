"""Action batching and backend-derived cards; no providers or physical output."""

from houseos import assistant as a
from houseos import assistant_tools as t
from houseos.db import new_id
from test_security import stub_provider_setup


def test_all_accepted_music_calls_are_applied_before_recap(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    seen = []

    def write(body, *_):
        seen.append(body.query)
        return {"status": "accepted", "operation_id": new_id(), "title": body.query}

    monkeypatch.setattr(a, "tool_registry", lambda _: {"music_add": (t.Search, "Synthetic queue", write)})
    rounds = []

    def provider(*_):
        rounds.append(1)
        return (
            "",
            [
                {"id": str(i), "name": "music_add", "args": {"query": title}}
                for i, title in enumerate(["First classic", "Second classic", "Third classic"])
            ],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Play three classic songs", idempotency_key=new_id()), actor, db)
    assert seen == ["First classic", "Second classic", "Third classic"]
    assert len(rounds) == 1 and len(result["cards"]) == 3
    assert [c["items"][0]["title"] for c in result["cards"]] == seen
    assert all(c["href"] == "/music" and c["status"] == "accepted" for c in result["cards"])
    assert "3" in result["reply"]


def test_confirmation_still_stops_remaining_writes(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    seen = []

    def write(body, *_):
        seen.append(body.query)
        return {"status": "needs_confirmation", "confirmation_id": new_id(), "preview": {"name": body.query}}

    monkeypatch.setattr(
        a, "tool_registry", lambda _: {"files_prepare": (t.Search, "Synthetic preview", write)}
    )
    monkeypatch.setattr(
        a,
        "provider_round",
        lambda *_: (
            "",
            [
                {"id": "1", "name": "files_prepare", "args": {"query": "first"}},
                {"id": "2", "name": "files_prepare", "args": {"query": "second"}},
            ],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        ),
    )
    result = a.chat(a.Chat(message="Review these two files", idempotency_key=new_id()), actor, db)
    assert seen == ["first"] and result["cards"][0]["confirmation_id"]
    assert result["cards"][0]["items"][0]["title"] == "first"


def test_completed_house_record_has_concrete_result_and_domain_link(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    count = []

    def provider(*_):
        count.append(1)
        return (
            (
                "",
                [
                    {
                        "id": "1",
                        "name": "household_create",
                        "args": {"item": {"kind": "groceries", "data": {"label": "Milk", "quantity": "2"}}},
                    }
                ],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
            if len(count) == 1
            else ("Done.", [], [], {"input_tokens": 1, "output_tokens": 1})
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(
        a.Chat(message="Add two milk cartons", context="household", idempotency_key=new_id()), actor, db
    )
    assert result["cards"][0]["label"] == "House record created"
    assert result["cards"][0]["items"][0]["title"] == "Milk"
    assert result["cards"][0]["href"] == "/house"


def test_cinema_queue_clear_prepares_actor_bound_one_shot_confirmation(domain, monkeypatch):
    from houseos import cinema_queue
    from fastapi import HTTPException
    import pytest

    db, (actor, other, _) = domain
    monkeypatch.setattr(
        cinema_queue,
        "list_queue",
        lambda *_: {
            "total": 2,
            "revision": "a" * 64,
            "items": [{"title": "First movie"}, {"title": "Second movie"}],
        },
    )
    calls = []

    def clear(body, owner, db):
        calls.append((body.revision, owner.id))
        db.commit()
        return {"status": "cleared", "removed": 2}

    monkeypatch.setattr(cinema_queue, "clear_queue", clear)
    result = a.prepare_cinema_queue_clear(t.Empty(), actor, db)
    assert calls == [] and result["count"] == 2
    with pytest.raises(HTTPException):
        a.confirm_message(result["confirmation_id"], other, db)
    assert a.confirm_message(result["confirmation_id"], actor, db)["removed"] == 2
    with pytest.raises(HTTPException):
        a.confirm_message(result["confirmation_id"], actor, db)
    assert calls == [("a" * 64, actor.id)]
