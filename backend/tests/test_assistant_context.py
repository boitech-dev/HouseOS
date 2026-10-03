"""Regression checks for bounded actor context and ordered tool failures; no paid calls."""

import json

from sqlalchemy import select

from houseos import assistant as a
from houseos import assistant_tools as t
from houseos.db import new_id
from houseos.models import Record
from test_security import stub_provider_setup


def test_context_return_memory_relevance_and_valid_bounds():
    assert t.ContextSwitch(context="general").context == "general"
    rows = [{"id": str(i), "kind": "fact", "text": "Unrelated " + "x" * 990} for i in range(6)]
    rows.append({"id": "relevant", "kind": "preference", "text": "French subtitles"})
    chosen = a.relevant_memories(rows, "Use French subtitles")
    assert chosen[0]["id"] == "relevant"
    assert len(json.dumps(chosen, ensure_ascii=False)) <= 2000
    history = [a.ChatMessage(role="user", content="x" * 6000, cards=[]) for _ in range(10)]
    bounded = a.bounded_history(history)
    assert len(bounded) == 3 and "omitted" in bounded[0]["content"]
    assert sum(len(item["content"]) for item in bounded) < 12200


def test_failed_prerequisite_stops_remaining_model_writes(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    calls = [
        {"id": "first", "name": "household_update", "args": {"invalid": True}},
        {
            "id": "second",
            "name": "household_create",
            "args": {"item": {"kind": "groceries", "data": {"label": "Must not create"}}},
        },
    ]
    monkeypatch.setattr(
        a, "provider_round", lambda *args: ("Done", calls, [], {"input_tokens": 1, "output_tokens": 1})
    )
    result = a.chat(
        a.Chat(message="Update this then add grocery", context="household", idempotency_key=new_id()),
        alice,
        db,
    )
    assert result["status"] == "action_stopped" and result["reply"] != "Done"
    assert not db.scalars(
        select(Record).where(Record.owner_id == alice.id, Record.kind == "household.groceries")
    ).all()


def test_memory_provenance_and_opt_in_derived_delete(domain, monkeypatch):
    db, (alice, bob, _) = domain
    stub_provider_setup(monkeypatch)
    rounds = iter(
        [
            (
                "",
                [
                    {
                        "id": "save",
                        "name": "memory_save",
                        "args": {"text": "French subtitles", "kind": "preference"},
                    }
                ],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            ),
            ("Saved", [], [], {"input_tokens": 1, "output_tokens": 1}),
        ]
    )
    monkeypatch.setattr(a, "provider_round", lambda *args: next(rounds))
    result = a.chat(a.Chat(message="Remember French subtitles", idempotency_key=new_id()), alice, db)
    a.confirm_message(result["cards"][0]["confirmation_id"], alice, db)
    memory = a.memories(alice, db)[0]
    assert memory["source_conversation_id"] == result["conversation_id"] and memory["source_message_id"]
    other = a.save_memory(a.Memory(text="Other resident memory"), bob, db)
    manual = a.save_memory(a.Memory(text="Independent memory"), alice, db)
    a.delete_conversation(result["conversation_id"], alice, db, delete_derived_memories=True)
    assert [item["id"] for item in a.memories(alice, db)] == [manual["id"]]
    assert a.memories(bob, db)[0]["id"] == other["id"]


def test_new_tool_bundles_are_small_and_use_exact_confirmation_paths():
    for context in ("music_library", "cinema_library", "tv", "files"):
        tools = a.tool_registry(context)
        assert (
            len(tools) <= 15
        )  # Dedicated bundles include source pagination, movie timer and context switch.
        for model, _, _ in tools.values():
            assert isinstance(t.strict_schema(model.model_json_schema()), dict)
    assert "music_remove" in a.tool_registry("music_library")
    assert "cinema_save_locally" in a.tool_registry("cinema_library")
    assert t.tv_card({"confirmation_id": "test"})["confirmation_path"] == "/cinema/device-confirmations/test"
    assert (
        t.playlist_card({"confirmation_id": "test"})["confirmation_path"] == "/music/playlists/test/confirm"
    )


def test_excerpt_requires_exact_single_use_actor_confirmation(domain, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from houseos import files
    from houseos.tool_household import FileExcerpt
    from houseos.models import Operation

    db, (alice, bob, _) = domain
    file = files.FileEntry(id=new_id(), owner_id=alice.id, scope="personal", name="note.txt", version=1)
    convo = Record(id=new_id(), owner_id=alice.id, kind="conversation", data={})
    db.add_all([file, convo])
    db.commit()
    reads = []
    monkeypatch.setattr(
        files,
        "read_excerpt",
        lambda *args, **kwargs: reads.append(kwargs) or {"text": "Approved excerpt", "file_id": file.id},
    )
    prepared = a.prepare_file_excerpt(FileExcerpt(file_id=file.id, version=1), alice, db)
    assert not reads  # Preparation does not disclose/read bytes.
    op = db.get(Operation, prepared["confirmation_id"])
    op.data = {**op.data, "conversation_id": convo.id}
    db.commit()
    with pytest.raises(HTTPException):
        a.confirm_file_excerpt(op.id, bob, db)
    db.rollback()
    result = a.confirm_file_excerpt(op.id, alice, db)
    assert result["status"] == "completed" and reads[0]["version"] == 1
    history = a.conversation(convo.id, alice, db)["messages"]
    assert "untrusted document data" in history[0]["content"] and "Approved excerpt" in history[0]["content"]
    with pytest.raises(HTTPException):
        a.confirm_file_excerpt(op.id, alice, db)
    assert len(reads) == 1


def test_crashed_request_can_be_reconciled_without_inaccessible_old_key(domain, monkeypatch):
    from datetime import timedelta
    import pytest
    from fastapi import HTTPException
    from houseos.db import utcnow

    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    convo = Record(id=new_id(), owner_id=alice.id, kind="conversation", data={})
    db.add(convo)
    db.flush()
    stale = a.ChatReceipt(
        owner_id=alice.id,
        request_key=new_id(),
        request_hash="fixture",
        conversation_id=convo.id,
        state="running",
        created_at=utcnow() - timedelta(minutes=16),
    )
    db.add(stale)
    db.commit()
    monkeypatch.setattr(
        a, "provider_round", lambda *args: pytest.fail("Reconciliation cannot dispatch a model")
    )
    request = a.Chat(message="New explicit request", conversation_id=convo.id, idempotency_key=new_id())
    with pytest.raises(HTTPException) as stopped:
        a.chat(request, alice, db)
    assert stopped.value.status_code == 409
    assert db.get(a.ChatReceipt, stale.id).state == "unverified"
    monkeypatch.setattr(
        a,
        "provider_round",
        lambda *args: ("Read-only reply", [], [], {"input_tokens": 1, "output_tokens": 1}),
    )
    assert a.chat(request, alice, db)["status"] == "completed"


def test_material_calendar_edit_requires_exact_current_confirmation(domain):
    import pytest
    from fastapi import HTTPException
    from houseos import household as h, tool_household as t

    db, (alice, _, _) = domain
    event = h.create_record(
        db,
        alice,
        "calendar",
        h.CreateRecord(
            data={"title": "Tea", "start": "2026-10-01T10:00:00", "end": "2026-10-01T11:00:00"},
            idempotency_key=new_id(),
        ),
    )
    preview = t.edit_house(
        t.HouseEdit(
            item=t.CalendarEdit(
                kind="calendar",
                id=event["id"],
                version=event["version"],
                data=t.CalendarPatch(start="2026-10-01T10:30:00"),
            )
        ),
        alice,
        db,
    )
    assert preview["status"] == "needs_confirmation"
    assert h.get_record(db, alice, "calendar", event["id"]).version == event["version"]
    result = a.confirm_message(preview["confirmation_id"], alice, db)
    assert result["status"] == "completed" and result["version"] > event["version"]
    with pytest.raises(HTTPException):
        a.confirm_message(preview["confirmation_id"], alice, db)
