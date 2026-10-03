"""User-reported planning failures; no provider or physical device calls."""

from unittest.mock import Mock
from pydantic import Field
from houseos import assistant as a
from houseos import assistant_tools as t
from houseos.auth import Input
from houseos.db import new_id
from test_security import stub_provider_setup


def test_invalid_arguments_are_repaired_once_before_any_write(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)

    class Count(Input):
        episode: int = Field(ge=1)

    writes = []
    calls = []
    monkeypatch.setattr(
        a,
        "tool_registry",
        lambda _: {
            "fixture_action": (
                Count,
                "Exact episode",
                lambda b, *_: writes.append(b.episode) or {"status": "completed"},
            )
        },
    )

    def provider(_, cfg, messages, schemas):
        calls.append(messages.copy())
        if len(calls) < 3:
            return (
                "",
                [
                    {
                        "id": str(len(calls)),
                        "name": "fixture_action",
                        "args": {"episode": 0 if len(calls) == 1 else 1},
                    }
                ],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        return "Done.", [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Run the exact fixture task", idempotency_key=new_id()), actor, db)
    assert writes == [1] and result["status"] == "completed"
    assert "INVALID_TOOL_ARGUMENTS" in str(calls[1])


def test_reboot_request_never_substitutes_power_off(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    from houseos.cinema_tv import TVAction

    handler = Mock(return_value={"status": "needs_confirmation", "confirmation_id": "bad"})
    monkeypatch.setattr(a, "tool_registry", lambda _: {"tv_control": (TVAction, "Fixture TV", handler)})
    count = [0]

    def provider(*_):
        count[0] += 1
        if count[0] == 1 and _[3]:
            return (
                "",
                [{"id": "off", "name": "tv_control", "args": {"action": "power_off"}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        return (
            "A reboot is not available through this connection. Turning the TV off would not restart the Chromecast.",
            [],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(
        a.Chat(
            message="Reboot the Chromecast and play a movie once it is rebooted", idempotency_key=new_id()
        ),
        actor,
        db,
    )
    handler.assert_not_called()
    assert not any(c.get("confirmation_id") for c in result["cards"])
    assert "reboot" in result["reply"].lower()


def test_six_read_steps_can_reach_an_answer_without_request_limit(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    monkeypatch.setattr(
        a,
        "tool_registry",
        lambda _: {"fixture_read": (t.Empty, "Read", lambda *_: {"status": "completed", "item": "fixture"})},
    )
    rounds = [0]

    def provider(*_):
        rounds[0] += 1
        return (
            ("Found the requested movie.", [], [], {"input_tokens": 1, "output_tokens": 1})
            if rounds[0] == 7
            else (
                "",
                [{"id": str(rounds[0]), "name": "fixture_read", "args": {}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Look up the fixture movie", idempotency_key=new_id()), actor, db)
    assert result["reply"] == "Found the requested movie." and result["status"] == "completed"


def test_tv_continuation_requires_owned_verified_step_and_never_replays_controls(domain, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from houseos.models import Record

    db, (actor, other, _) = domain
    stub_provider_setup(monkeypatch)
    conversation = a.create_conversation(a.NewConversation(title="Fixture sequence"), actor, db)["id"]
    identity = new_id()
    path = f"/assistant/conversations/{conversation}/continue-tv/{identity}"
    record = Record(
        id=identity,
        kind="cinema.tv_confirmation",
        owner_id=actor.id,
        visibility="private",
        data={
            "consumed": True,
            "result": {"state": "command_sent", "action": "power_on", "destination": "Fixture TV"},
        },
    )
    db.add(record)
    db.add(
        a.ChatMessage(
            conversation_id=conversation,
            owner_id=actor.id,
            role="user",
            content="Turn on the TV and find Idiocracy in French without subtitles, starting at 14 minutes",
            sequence=1,
        )
    )
    db.add(
        a.ChatMessage(
            conversation_id=conversation,
            owner_id=actor.id,
            role="assistant",
            content="Confirm turning on the TV; movie selection comes next.",
            cards=[{"confirmation_id": identity, "continuation_path": path}],
            sequence=2,
        )
    )
    db.commit()
    with pytest.raises(HTTPException):
        a.continue_tv(conversation, identity, other, db)
    with pytest.raises(HTTPException):
        a.continue_tv(conversation, identity, actor, db)
    record.data = {**record.data, "result": {**record.data["result"], "state": "observed"}}
    db.commit()
    calls = []

    def provider(_, cfg, messages, schemas):
        calls.append(1)
        assert {s["name"] for s in schemas} == {
            "cinema_search",
            "cinema_details",
            "devices_list",
            "cinema_discover",
        }
        assert "14 minutes" in str(messages) and "Already verified TV action" in str(messages)
        return (
            "The TV is on. I can now find the movie sources.",
            [],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.continue_tv(conversation, identity, actor, db)
    assert a.continue_tv(conversation, identity, actor, db) == result
    assert calls == [1]


def test_optional_explanation_failure_keeps_confirmation_and_honest_fallback(domain, monkeypatch):
    import httpx

    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    writes = []
    rounds = [0]
    monkeypatch.setattr(
        a,
        "tool_registry",
        lambda _: {
            "fixture_preview": (
                t.Empty,
                "Preview",
                lambda *_: (
                    writes.append(1)
                    or {
                        "status": "needs_confirmation",
                        "confirmation_id": "fixture",
                        "preview": {"summary": "Confirm only this fixture action."},
                    }
                ),
            )
        },
    )

    def provider(*_):
        rounds[0] += 1
        if rounds[0] == 1:
            return (
                "",
                [{"id": "preview", "name": "fixture_preview", "args": {}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        raise httpx.ReadTimeout("fixture optional narration timeout")

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Prepare a fixture", idempotency_key=new_id()), actor, db)
    assert writes == [1] and result["cards"][0]["confirmation_id"] == "fixture"
    assert result["status"] == "needs_confirmation" and "confirm" in result["reply"].lower()


def test_source_progress_refresh_is_private_and_token_bounded(domain):
    from houseos.models import Operation

    db, (actor, other, _) = domain
    identity = new_id()
    db.add(
        Operation(
            id=identity,
            actor_id=actor.id,
            kind="cinema.discover",
            state="completed",
            result={
                "workflow_id": "fixture-workflow",
                "workflow": {
                    "version": 2,
                    "choice_set": {
                        "id": "fixture-choices",
                        "candidates": [
                            {"id": str(i), "release": "Fixture release", "height": 1080} for i in range(30)
                        ],
                    },
                },
            },
        )
    )
    db.commit()
    card = {"domain": "cinema", "operation_id": identity, "state": "accepted"}
    own = a.resolved_cards([card], actor, db)[0]
    assert own["state"] == "completed" and own["workflow_id"] == "fixture-workflow" and len(own["items"]) == 5
    assert a.resolved_cards([card], other, db)[0] == card
    compact = t.compact_workflow(
        {"choice_set": {"id": "set", "candidates": [{"id": str(i)} for i in range(30)]}}, 5
    )
    assert [x["id"] for x in compact["choice_set"]["candidates"]] == ["5", "6", "7", "8", "9"]
    assert compact["choice_set"]["next_offset"] == 10


def test_no_subtitles_discards_inapplicable_provider_placeholders():
    from houseos.assistant_cinema_contract import AgentDiscover

    value = AgentDiscover(
        media_id="fixture",
        idempotency_key="fixture-key",
        preferences={"subtitles_on": False, "subtitle_language": "none", "subtitle_track": "none"},
    )
    assert (
        value.preferences.subtitles_on is False
        and value.preferences.subtitle_language is None
        and value.preferences.subtitle_track is None
    )
    assert not a.restart_requested("Don't reboot the Chromecast; just find the movie")
    assert not a.restart_requested("Restart the movie on the TV")
    assert a.restart_requested("Redémarre le Chromecast puis lance le film")


def test_planning_limit_replaces_in_progress_text_with_the_limit_notice(domain, monkeypatch):
    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    monkeypatch.setattr(
        a, "tool_registry", lambda _: {"fixture_read": (t.Empty, "Read", lambda *_: {"status": "completed"})}
    )

    def provider(*args):
        monkeypatch.setattr(a, "PLANNING_SECONDS", -1)  # the next round would start past the limit
        return (
            "I'll look for it now…",
            [{"id": "read", "name": "fixture_read", "args": {}}],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Find it", idempotency_key=new_id()), actor, db)
    assert result["status"] == "limit_reached" and "step limit" in result["reply"]
