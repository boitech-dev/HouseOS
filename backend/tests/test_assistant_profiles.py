"""Role model selection, cost freshness and separate personal-space context."""

import pytest
from fastapi import HTTPException
from houseos import assistant as a, assistant_profiles as profiles
from houseos import assistant_tools as t
from houseos.db import new_id
from houseos.models import Integration, Record, Usage


def seed(db):
    base = {
        "model": "small",
        "daily_budget_microusd": 1000000,
        "user_daily_budget_microusd": 1000000,
        "input_microusd_per_million": 1,
        "output_microusd_per_million": 1,
    }
    db.add_all(
        [
            Integration(name="budgets", enabled=True, config={"default_provider": "openrouter"}),
            Integration(name="openrouter", enabled=True, config=base),
            Integration(
                name="catalog.openrouter",
                config={
                    "auth_mode": "api",
                    "items": [
                        {
                            "id": name,
                            "tool_support": "declared",
                            "supported_parameters": ["reasoning"],
                            "pricing": {
                                "input_microusd_per_million": price,
                                "output_microusd_per_million": price,
                            },
                        }
                        for name, price in [("small", 10), ("large", 100)]
                    ],
                },
            ),
        ]
    )
    db.commit()


def test_separate_roles_and_model_pricing_are_reserved_fresh(setup):
    db, (actor, _) = setup
    seed(db)
    profiles.save(
        "personal_space",
        profiles.Assignment(provider="openrouter", model="large", reasoning_effort="low"),
        actor,
        db,
    )
    assert profiles.assignment(db, "general")["model"] == "small"
    selected = profiles.assignment(db, "personal_space")
    cfg = {
        "_purpose": "personal_space",
        "_assignment": selected,
        "_policy": "space policy",
        "_resident_context": "resident context",
    }
    usage = a.reserve(db, actor, "openrouter", cfg, [{"role": "user", "content": "hello"}], [])
    assert db.get(Usage, usage).model == "large"
    assert cfg["input_microusd_per_million"] == 100 and cfg["_policy"] == "space policy"
    assert cfg["reasoning_effort"] == "low"
    profiles.save("personal_space", profiles.Assignment(provider="openrouter", model="small"), actor, db)
    with pytest.raises(HTTPException) as error:
        a.reserve(db, actor, "openrouter", cfg, [], [])
    assert error.value.status_code == 409


def test_personal_space_isolation_and_admin_owned_routing(setup, monkeypatch):
    db, (actor, bob) = setup
    seed(db)
    monkeypatch.setattr(a, "integration_config", lambda d, p: {"api_key": "fixture", "model": "small"})

    def reserve(d, who, provider, cfg, messages, schemas):
        assert provider == "openrouter"  # Caller cannot override admin routing.
        assert cfg["_policy"] == a.SPACE_POLICY
        assert not any("general private memory" in str(m) for m in messages)
        assert {t["name"] for t in schemas} == {
            "personal_space_options",
            "personal_space_configure",
            "personal_space_today",
            "personal_space_art_tags",
            "personal_space_finish",
        }
        row = Usage(user_id=who.id, provider=provider, model=cfg["model"], reserved_microusd=1)
        d.add(row)
        d.commit()
        return row.id

    monkeypatch.setattr(a, "reserve", reserve)
    monkeypatch.setattr(
        a,
        "provider_round",
        lambda *args: ("Quels sujets vous intéressent ?", [], [], {"input_tokens": 1, "output_tokens": 1}),
    )
    db.add(Record(kind="memory", owner_id=actor.id, data={"text": "general private memory", "kind": "fact"}))
    db.commit()
    result = a.chat(
        a.Chat(
            message="Configure mon espace",
            purpose="personal_space",
            provider="anthropic",
            idempotency_key=new_id(),
        ),
        actor,
        db,
    )
    assert len(a.conversations(actor, db, purpose="personal_space")) == 1
    assert a.conversations(actor, db, purpose="general") == []
    assert a.conversations(bob, db, purpose="personal_space") == []
    with pytest.raises(HTTPException) as error:
        a.chat(
            a.Chat(
                message="Use general tools",
                purpose="general",
                conversation_id=result["conversation_id"],
                idempotency_key=new_id(),
            ),
            actor,
            db,
        )
    assert error.value.status_code == 409


def test_no_myspace_tools_can_escalate_to_household():
    tools = a.tool_registry("personal_space")
    assert set(tools) == {
        "personal_space_options",
        "personal_space_configure",
        "personal_space_today",
        "personal_space_art_tags",
        "personal_space_finish",
    }
    assert "switch_context" not in tools and "memory_list" not in tools


def test_cinema_tools_cover_version_inspection_and_late_destination():
    tools = a.tool_registry("cinema")
    launch = tools["cinema_launch"][0](
        workflow_id="w", version=2, source_id="s", device_id="d", audio_track="1", position=4416
    )
    assert (launch.audio_track, launch.position, launch.replace) == ("1", 4416, False)
    assert "cinema_select" not in tools  # one tap: discover (pre-checked) then launch
    assert t.space_summary({"configured": True, "day": "2026-09-20", "sections": []})["day"] == "2026-09-20"


def test_media_tools_are_compact_opt_in_and_paginate_backend(monkeypatch):
    from houseos import cinema

    assert "music_history" not in a.tool_registry("general")
    assert "music_history" in a.tool_registry("music_library")
    assert {"cinema_queue", "cinema_queue_add", "cinema_queue_remove"} <= set(
        a.tool_registry("cinema_library")
    )
    assert {"cinema_discover", "cinema_launch"} <= set(a.tool_registry("cinema"))
    result = t.compact_workflow(
        {
            "workflow": {
                "id": "w",
                "version": 2,
                "provisional": [{"id": str(i), "release": "x" * 300} for i in range(12)],
            }
        },
        5,
    )
    assert [r["id"] for r in result["workflow"]["provisional"]] == ["5", "6", "7", "8", "9"]
    assert result["workflow"]["provisional_next_offset"] == 10
    offsets = []

    def state(filter, actor, db, offset=0):
        offsets.append(offset)
        return {
            "items": [
                {
                    "media_id": str(i),
                    "title": "Movie",
                    "position": 22,
                    "episodes": ["large"] * 100,
                    "description": "large",
                }
                for i in range(11)
            ],
            "next_offset": 100,
        }

    monkeypatch.setattr(cinema, "media_state", state)
    result = t.shared_watchlist(t.MediaStateRead(filter="history", offset=50), None, None)
    assert offsets == [50] and result["next_offset"] == 60
    assert len(result["items"]) == 10 and set(result["items"][0]) == {"media_id", "title", "position"}


def test_a_claude_sign_in_keeps_its_chosen_effort(setup):
    """Opus at medium for setup through a Claude subscription; the bridge receives "medium"."""
    from houseos import claude_bridge, codex_bridge

    db, (actor, _) = setup
    seed(db)
    db.add_all(
        [
            Integration(
                name="anthropic",
                enabled=True,
                config={"auth_mode": "claude_code", "model": "claude-opus-5-5"},
            ),
            Integration(
                name="catalog.anthropic",
                config={"auth_mode": "claude_code", "items": [{"id": "claude-opus-5-5"}]},
            ),
        ]
    )
    db.commit()
    profiles.save(
        "setup",
        profiles.Assignment(provider="anthropic", model="claude-opus-5-5", reasoning_effort="medium"),
        actor,
        db,
    )
    assert profiles.assignment(db, "setup")["reasoning_effort"] == "medium"
    for bridge in (claude_bridge, codex_bridge):
        assert bridge.effort({"effort": "medium"}) == "medium"
        assert bridge.effort({"effort": "extreme"}) == "low" and bridge.effort({}) == "low"
    # OpenAI and Anthropic keys take an effort (their models think); the test round checks it.
    db.add(Integration(name="catalog.openai", config={"auth_mode": "api", "items": [{"id": "gpt-x"}]}))
    db.add(Integration(name="openai", enabled=True, config={"model": "gpt-x"}))
    db.commit()
    profiles.save(
        "general",
        profiles.Assignment(provider="openai", model="gpt-x", reasoning_effort="high"),
        actor,
        db,
    )
    assert profiles.assignment(db, "general")["reasoning_effort"] == "high"
    with pytest.raises(HTTPException):  # a self-hosted server has no reasoning setting
        db.add(Integration(name="compatible", enabled=True, config={"model": "local"}))
        db.commit()
        profiles.save(
            "general",
            profiles.Assignment(provider="compatible", model="local", reasoning_effort="high"),
            actor,
            db,
        )


def test_a_saved_assignment_is_tested_with_its_own_prompt_tools_and_effort(setup, monkeypatch):
    """A model id the list lacks may be saved; the test round uses the profile's real setup."""
    db, (actor, _) = setup
    seed(db)
    profiles.save(
        "setup",
        profiles.Assignment(provider="openrouter", model="vendor/brand-new", reasoning_effort=None),
        actor,
        db,
    )
    seen = {}

    def answer(provider, cfg, messages, schemas):
        seen.update(
            policy=cfg["_policy"],
            tools={s["name"] for s in schemas},
            model=cfg["model"],
            timeout=cfg["_timeout_seconds"],
        )
        return "Ready.", [], [], {"input_tokens": 10, "output_tokens": 2}

    monkeypatch.setattr(a, "provider_round", answer)
    result = profiles.try_assignment("setup", actor, db)
    assert result["status"] == "verified" and result["model"] == "vendor/brand-new"
    assert seen["policy"] == a.system_prompt("setup") and "setup_checklist" in seen["tools"]
    assert seen["timeout"] == 20
    state = profiles.profiles(actor, db)
    assert next(i for i in state["items"] if i["purpose"] == "setup")["tested"] is True
    assert {"provider": "openrouter", "model": "vendor/brand-new"} in state["recent"]

    def signed_out(*args):
        raise HTTPException(503, {"code": "CLAUDE_SIGN_IN_REQUIRED", "message": "Sign in again."})

    monkeypatch.setattr(a, "provider_round", signed_out)
    result = profiles.try_assignment("setup", actor, db)
    assert (result["status"], result["message"]) == ("failed", "Sign in again.")
    assert not next(i for i in profiles.profiles(actor, db)["items"] if i["purpose"] == "setup")["tested"]


def test_every_profile_fits_the_native_bridges():
    for purpose in profiles.PROFILES:  # the Claude and Codex bridges take at most 32 tools
        assert 0 < len(a.tool_registry(purpose)) <= 32
