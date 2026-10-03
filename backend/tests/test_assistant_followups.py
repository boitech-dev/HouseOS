"""Current user requests retain identity context and can resolve an existing source choice."""

from houseos import assistant as a, cinema
from houseos import assistant_tools as t
from houseos.db import new_id
from houseos.models import User
from test_security import stub_provider_setup


def test_reservation_preserves_request_identity_context(provider_probe):
    _, db, actor, provider = provider_probe
    cfg = a.integration_config(db, provider)
    cfg["_resident_context"] = "Trusted request username and timezone context"
    a.reserve(db, actor, provider, cfg, [], [])
    assert cfg["_resident_context"] == "Trusted request username and timezone context"


def test_existing_source_choice_read_can_continue_to_selection(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    user = db.get(User, actor.id)
    user.preferences = {"timezone": "America/Toronto", "language": "en"}
    username = user.username
    db.commit()
    monkeypatch.setattr(
        cinema,
        "workflow",
        lambda *args: {
            "id": "workflow",
            "state": "awaiting_choice",
            "version": 2,
            "choice_set": {"id": "choices", "candidates": [{"rank": 1, "id": "source"}]},
        },
    )
    chosen = []

    def launch(identity, body, *_):
        chosen.append(body.source_id)
        return {
            "id": identity,
            "state": "awaiting_playback_confirmation",
            "confirmation_id": "confirmation",
            "preview": {"source": "source"},
        }

    monkeypatch.setattr(cinema, "launch", launch)
    seen = []
    calls = iter(
        [
            [{"id": "read", "name": "cinema_workflow", "args": {"id": "workflow"}}],
            [
                {
                    "id": "launch",
                    "name": "cinema_launch",
                    "args": {
                        "workflow_id": "workflow",
                        "version": 2,
                        "source_id": "source",
                        "device_id": "tv",
                        "subtitle_track": "off",
                    },
                }
            ],
        ]
    )

    def provider(provider, cfg, messages, schemas):
        seen.append(cfg["_resident_context"])
        return (
            ("Ready to prepare the selected source.", [], [], {"input_tokens": 1, "output_tokens": 1})
            if not schemas
            else ("", next(calls), [], {"input_tokens": 1, "output_tokens": 1})
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="1", context="cinema", idempotency_key=new_id()), actor, db)
    assert chosen == ["source"] and len(seen) == 2  # the confirmation card ends the turn
    assert username in seen[0] and "America/Toronto" in seen[0]
    assert result["cards"][0]["confirmation_id"] == "confirmation"
    assert result["status"] != "completed"  # Playback still requires exact explicit confirmation.


def test_failed_provider_turn_is_visible_and_does_not_hide_in_history(domain, monkeypatch):
    import httpx
    import pytest
    from fastapi import HTTPException

    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    created = a.create_conversation(a.NewConversation(title="A fresh task"), actor, db)

    def fail(*args):
        raise httpx.ReadTimeout("synthetic timeout")

    monkeypatch.setattr(a, "provider_round", fail)
    with pytest.raises(HTTPException) as error:
        a.chat(
            a.Chat(conversation_id=created["id"], message="Synthetic task", idempotency_key=new_id()),
            actor,
            db,
        )
    assert error.value.detail["code"] == "PROVIDER_TIMEOUT"
    page = a.conversation(created["id"], actor, db)
    assert [row["role"] for row in page["messages"]] == ["user", "assistant"]
    assert "The AI provider timed out" in page["messages"][-1]["content"]  # the real reason
    assert page["pending"] is False and page["progress"] is None


def test_personal_space_valid_character_tags_and_requested_limits():
    import pytest
    from pydantic import ValidationError
    from houseos.personal_space import SpaceConfig

    result = SpaceConfig(
        art_tags=["c.c._(code_geass)", "zero_two", "waifu"],
        subreddits=["singularity", "OpenAI", "science", "anime", "technology"],
        daily_count=20,
    )
    assert result.art_tags[0] == "c.c._(code_geass)" and len(result.subreddits) == 5
    for data in (
        {"daily_count": 21},
        {"subreddits": ["one", "two", "three", "four", "five", "six"]},
        {"art_tags": ["rating:e"]},
        {"art_tags": ["cat*"]},
    ):
        with pytest.raises(ValidationError):
            SpaceConfig(**data)


def test_transient_provider_retry_has_own_reservation_without_tool_replay(domain, monkeypatch):
    import httpx
    from sqlalchemy import select
    from houseos.models import Usage

    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    writes = []
    monkeypatch.setattr(
        a,
        "tool_registry",
        lambda _: {
            "fixture_write": (
                t.Empty,
                "Synthetic action",
                lambda *_: writes.append(1) or {"status": "completed"},
            )
        },
    )
    rounds = []

    def provider(*_):
        rounds.append(1)
        if len(rounds) == 1:
            return (
                "",
                [{"id": "once", "name": "fixture_write", "args": {}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        if len(rounds) == 2:
            response = httpx.Response(503, request=httpx.Request("POST", "https://provider.invalid"))
            raise httpx.HTTPStatusError("synthetic unavailable", request=response.request, response=response)
        return "Action complete.", [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Perform synthetic action", idempotency_key=new_id()), actor, db)
    assert result["status"] == "completed" and len(rounds) == 3 and writes == [1]
    usage = list(db.scalars(select(Usage).where(Usage.user_id == actor.id)))
    assert len(usage) == 3 and sum(row.status == "failed" for row in usage) == 1
    assert next(row for row in usage if row.status == "failed").reserved_microusd > 0


def test_art_tag_lookup_returns_bounded_real_names_and_keeps_queries_literal(monkeypatch):
    from houseos import personal_space as space
    from houseos.auth import Actor, RESIDENT

    calls = []

    def fetch(url):
        calls.append(url)
        return [{"name": f"character_{i}", "post_count": 30 - i, "category": 4} for i in range(10)] + [
            {"name": "bad:operator", "post_count": 9, "category": 0}
        ]

    monkeypatch.setattr(space, "public_json", fetch)
    space.lookup_art_tags.cache_clear()
    result = space.art_tags("Fresh Character", Actor("test", "test", "resident", RESIDENT))
    assert len(result["items"]) == 5 and result["items"][0]["tag"] == "character_0"
    assert "fresh_character%2A" in calls[0]
    assert "all ratings" in result["count_scope"]
    space.lookup_art_tags.cache_clear()


def test_legacy_failed_orphan_request_is_marked_history_not_pending(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    conversation = a.create_conversation(a.NewConversation(title="Earlier task"), actor, db)["id"]
    db.add(
        a.ChatMessage(
            conversation_id=conversation,
            owner_id=actor.id,
            role="user",
            content="Earlier synthetic action",
            sequence=1,
        )
    )
    db.add(
        a.ChatReceipt(
            owner_id=actor.id,
            conversation_id=conversation,
            request_key=new_id(),
            request_hash="0" * 64,
            state="failed",
        )
    )
    db.commit()
    captured = []

    def provider(_, cfg, messages, schemas):
        captured.extend(messages)
        return "Hello.", [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    a.chat(a.Chat(conversation_id=conversation, message="Hi", idempotency_key=new_id()), actor, db)
    assert captured[-1]["content"] == "Hi"
    assert any("it is not pending" in item.get("content", "") for item in captured)
    assert "Earlier synthetic action" in str(captured)


def test_first_round_has_the_needed_tools_without_switching():
    def loaded(message):
        return set(t.tool_registry(a.initial_context(message)))

    assert {"music_search", "music_add_candidates", "music_control"} <= loaded(
        "Play a classic song from the 90s"
    )
    assert "music_search" in loaded("Mets une chanson des années 90")
    assert "cinema_discover" in loaded("Play the movie Song of the Sea")
    assert {"household_create", "groceries_purchase"} <= loaded("Add milk to the groceries")
    assert "household_create" in loaded("Ajoute du lait aux courses")
    assert "calendar_agenda" in loaded("What's on the calendar tomorrow?")
    assert "files_folder" in loaded("Crée un dossier Factures")
    assert "music_history" in loaded("Show my music history")
    assert a.initial_context("Add the movie Dune to my tasks") == "cinema"
    assert a.initial_context("Tell me a joke") is None  # keeps the conversation's current tools
    assert a.initial_context("Add milk to the groceries") == "general"


def test_openrouter_null_tool_calls_is_a_plain_reply(monkeypatch):
    from houseos import assistant as a

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{"message": {"role": "assistant", "content": "Hi", "tool_calls": None}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            }

    class Client:
        def __init__(self, timeout):
            assert timeout == 7

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(a.httpx, "Client", Client)
    reply, calls, _, usage = a.provider_round(
        "openrouter", {"api_key": "k", "model": "m", "_timeout_seconds": 7}, [], []
    )
    assert (reply, calls, usage["input_tokens"]) == ("Hi", [], 3)


def test_reply_language_follows_the_message_not_the_account_default():
    from houseos.assistant_prompt import reply_language

    for message in (
        "What's playing right now?",
        "Pause the music",
        "Add milk and eggs to the groceries",
        "Hi!",
    ):
        assert reply_language(message, "fr") == "en", message
    for message in (
        "Mets 3 chansons de Daft Punk",
        "Qu'est-ce qui passe ?",
        "Baisse le son de la télé à 15",
        "Salut",
    ):
        assert reply_language(message, "en") == "fr", message
    assert reply_language("Daft Punk", "fr") == "fr"  # no signal keeps the resident's setting
