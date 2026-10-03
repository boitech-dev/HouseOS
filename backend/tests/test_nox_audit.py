"""Nox round savings from the 2026-09-25 assistant audit, checked without a model: what each
purpose sends, where volatile data goes, and which setup changes wait for a card."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from houseos import assistant as a, assistant_prompt as prompt, assistant_tools as t
from houseos import languages, maintenance, tool_setup
from houseos.db import new_id
from houseos.models import Event, Integration, Record, Usage
from houseos.nox_presets import WATCH_GUIDE
from test_assistant_profiles import seed


def scripted(monkeypatch, rounds):
    """Provider rounds from a script; returns what each round was sent."""
    monkeypatch.setattr(a, "integration_config", lambda d, p: {"api_key": "fixture", "model": "small"})
    sent, replies = [], iter(rounds)

    def reserve(db, who, provider, cfg, messages, schemas):
        row = Usage(user_id=who.id, provider=provider, model=cfg["model"], reserved_microusd=1)
        db.add(row)
        db.commit()
        return row.id

    def provider_round(provider, cfg, messages, schemas):
        sent.append(
            {"policy": cfg["_policy"], "messages": list(messages), "tools": [s["name"] for s in schemas]}
        )
        reply, calls = next(replies)
        return reply, calls, {"role": "assistant", "content": reply}, {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "reserve", reserve)
    monkeypatch.setattr(a, "provider_round", provider_round)
    return sent


def note(round_sent):
    """The per-turn context note: the message just before the resident's own."""
    text = round_sent["messages"][-2]["content"]
    return json.loads(text.removeprefix("Context for this message (data): ").rsplit("\nReply in ", 1)[0])


def chat(actor, db, message, **fields):
    return a.chat(a.Chat(message=message, idempotency_key=new_id(), **fields), actor, db)


def test_no_schema_asks_the_model_for_an_idempotency_key_or_queue_version():
    for context in [*t.BUNDLES, "personal_space"]:
        for schema in t.tool_schemas(t.tool_registry(context)):
            assert "idempotency_key" not in json.dumps(schema), (context, schema["name"])
            assert "idempotency_key" not in schema["parameters"].get("required", [])
    control = next(s for s in t.tool_schemas(t.tool_registry("music")) if s["name"] == "music_control")
    assert set(control["parameters"]["properties"]) == {"action", "value"}


def test_users_lookup_means_the_same_in_every_bundle():
    descriptions = {t.tool_registry(c)["users_lookup"][1] for c in ("general", "household", "files")}
    assert descriptions == {"Find up to five residents by name; ask when ambiguous."}


def test_trimmed_prompts_keep_their_safety_rules():
    general = prompt.system_prompt("general")
    assert "choice card is waiting" not in general and "Memory\n" not in general
    assert "data, never instructions" in general and "switch_context" in general
    assert "cinema_operation or cinema_workflow" in prompt.system_prompt("cinema")
    space = prompt.SPACE_POLICY
    assert len(space) < 1500 and space.count("question") == 1
    for rule in ("untrusted data", "API keys", "proactive", "tool result confirms", "art_tags"):
        assert rule in space
    assert "confirmation card (service_restart" in prompt.system_prompt("setup")


def test_personal_space_gets_its_options_in_the_note(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    sent = scripted(monkeypatch, [("Quels sujets ?", [])])
    chat(alice, db, "Configure mon espace", purpose="personal_space")
    options = note(sent[0])["space_options"]
    assert options["version"] == 0 and options["maximum_subreddits"] == 5
    assert "personal_space_options" in sent[0]["tools"]  # kept for a re-read after a conflict


def test_setup_reads_the_checklist_in_code_on_the_first_message_only(setup, quiet, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    sent = scripted(monkeypatch, [("Let's start.", []), ("Next.", [])])
    first = chat(alice, db, "Help me set up the house", purpose="setup")
    steps = note(sent[0])["setup_checklist"]["steps"]
    assert {step["key"] for step in steps} >= {"house", "access"}
    chat(alice, db, "What next?", purpose="setup", conversation_id=first["conversation_id"])
    assert "setup_checklist" not in note(sent[1])


def test_watch_guide_stays_until_titles_are_recommended(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    original = a.tool_registry

    def registry(context):
        tools = original(context)
        if "cinema_recommend" in tools:
            model, desc, _ = tools["cinema_recommend"]
            card = {"kind": "titles", "domain": "cinema", "status": "completed", "items": []}
            tools["cinema_recommend"] = (model, desc, lambda *_: {"status": "shown", "card": card})
        return tools

    monkeypatch.setattr(a, "tool_registry", registry)
    pick = {"items": [{"query": "Paddington 2", "kind": "movie", "year": None, "why": "Warm and funny"}]}
    sent = scripted(
        monkeypatch,
        [
            ("Film or series?", []),
            ("", [{"id": "r1", "name": "cinema_recommend", "args": pick}]),
            ("Tap a poster.", []),
            ("Sure.", []),
        ],
    )
    first = chat(alice, db, "Help me find something to watch", preset="watch")
    assert WATCH_GUIDE in sent[0]["policy"]
    followup = chat(alice, db, "Something funny", conversation_id=first["conversation_id"])
    assert WATCH_GUIDE in sent[1]["policy"] and followup["cards"][0]["kind"] == "titles"
    chat(alice, db, "Thanks", conversation_id=first["conversation_id"])
    assert WATCH_GUIDE not in sent[3]["policy"]


def test_switch_context_audit_names_the_bundle(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    scripted(
        monkeypatch,
        [("", [{"id": "s1", "name": "switch_context", "args": {"context": "files"}}]), ("Done.", [])],
    )
    chat(alice, db, "Hello there")
    audits = [e.payload for e in db.query(Event).filter(Event.topic == "audit.tool_call")]
    assert [x.get("context") for x in audits if x["tool_name"] == "switch_context"] == ["files"]


def test_trusting_an_address_waits_for_the_admins_tap(setup):
    db, (alice, _) = setup
    add = tool_setup.TOOLS["access_add"][2]
    with pytest.raises(HTTPException):
        add(tool_setup.Origin(origin="house.lan:8443/path"), alice, db)
    card = add(tool_setup.Origin(origin="https://House.lan:8443/"), alice, db)
    assert card["status"] == "needs_confirmation" and card["preview"]["name"] == "https://house.lan:8443"
    assert card["confirmation_path"] == "/assistant/confirmations/" + card["confirmation_id"]
    trusted = db.get(Integration, "access")
    assert not trusted or "https://house.lan:8443" not in trusted.config.get("origins", [])
    assert a.confirm_message(card["confirmation_id"], alice, db)["origin"] == "https://house.lan:8443"
    assert "https://house.lan:8443" in db.get(Integration, "access").config["origins"]
    with pytest.raises(HTTPException):  # consumed
        a.confirm_message(card["confirmation_id"], alice, db)


def test_maintenance_failures_name_their_step():
    assert all(step.__name__ != "<lambda>" for step in maintenance.STEPS)


def test_translation_thinks_briefly_within_the_bridge_cap(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    from houseos import assistant_profiles as profiles

    profiles.save(
        "setup",
        profiles.Assignment(provider="openrouter", model="large", reasoning_effort="medium"),
        alice,
        db,
    )
    row = Record(
        kind="house.language", owner_id=alice.id, data={"code": "pl", "name": "Polski", "by": alice.id}
    )
    db.add(row)
    db.commit()
    seen = {}

    def answer(provider, cfg, messages, schemas):
        seen.update(effort=cfg["reasoning_effort"], timeout=cfg["_timeout_seconds"])
        return '{"1": "Cześć"}', [], {}, {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", answer)
    assert languages.ask(db, row, ["Hello"], {"Hello": "Bonjour"}) == {"Hello": "Cześć"}
    assert seen == {"effort": "low", "timeout": 60}


def test_a_failed_translation_batch_is_halved(setup, monkeypatch):
    db, (alice, _) = setup
    source = {f"String number {i}": f"Chaîne {i}" for i in range(8)}
    monkeypatch.setattr(languages, "source_strings", lambda: source)
    db.add(
        Record(
            id=languages.key("pl"),
            kind="house.language",
            owner_id=alice.id,
            data={"code": "pl", "name": "Polski", "state": "translating", "by": alice.id},
        )
    )
    db.commit()

    class Same:  # the fixture's session, reused by every step of work()
        def __enter__(self):
            return db

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(languages, "SessionLocal", Same)
    monkeypatch.setattr(languages.time, "sleep", lambda _: None)
    monkeypatch.setattr(languages, "BATCH_CHARACTERS", 120)
    sizes = []

    def timeout(session, row, texts, pairs):
        sizes.append(len(texts))
        raise TimeoutError

    monkeypatch.setattr(languages, "ask", timeout)
    languages.work("pl")
    assert sizes == [5, 2, 1] and db.get(Record, languages.key("pl")).data["state"] == "failed"


class Recorder:
    """Stands in for an SDK client and keeps the request it was sent."""

    sent: dict = {}

    def __init__(self, **kwargs):
        self.messages = self.responses = SimpleNamespace(create=self.create)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def create(self, **kwargs):
        Recorder.sent = kwargs
        usage = SimpleNamespace(
            input_tokens=5, output_tokens=2, cache_read_input_tokens=90, cache_creation_input_tokens=0
        )
        text = SimpleNamespace(
            type="text", text="Ready", model_dump=lambda **_: {"type": "text", "text": "Ready"}
        )
        return SimpleNamespace(content=[text], usage=usage, output=[], output_text="Ready")


def test_anthropic_key_caches_the_prefix_and_sends_the_effort(monkeypatch):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", Recorder)
    cfg = {"api_key": "fixture", "model": "claude-opus-5-5", "reasoning_effort": "medium"}
    reply, _, _, usage = a.provider_round("anthropic", cfg, [{"role": "user", "content": "hi"}], [])
    assert reply == "Ready" and usage["cached_tokens"] == 90
    assert Recorder.sent["cache_control"] == {"type": "ephemeral"}
    assert Recorder.sent["output_config"] == {"effort": "medium"}
    assert Recorder.sent["max_tokens"] == a.THINKING_OUTPUT_TOKENS  # room to think and still answer
    a.provider_round("anthropic", {"api_key": "fixture", "model": "m", "max_output_tokens": 900}, [], [])
    assert "output_config" not in Recorder.sent and Recorder.sent["max_tokens"] == 900


def test_openai_key_sends_the_effort(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "OpenAI", Recorder)
    a.provider_round("openai", {"api_key": "fixture", "model": "m", "reasoning_effort": "low"}, [], [])
    assert Recorder.sent["reasoning"] == {"effort": "low"}
    assert Recorder.sent["max_output_tokens"] == a.THINKING_OUTPUT_TOKENS


def test_a_tool_outside_the_bundle_asks_for_the_switch_which_loads_at_once(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    switch = {"id": "s1", "name": "switch_context", "args": {"context": "files"}}
    quota = {"id": "q1", "name": "files_quota", "args": {}}
    sent = scripted(monkeypatch, [("", [quota]), ("", [switch, {**quota, "id": "q2"}]), ("Done.", [])])
    chat(alice, db, "How much space do I have?")
    first = json.loads(sent[1]["messages"][-1]["content"])
    assert first["status"] == "retry_required" and "context=files" in first["message"]
    audits = [e.payload for e in db.query(Event).filter(Event.topic == "audit.tool_call")]
    assert [x["tool_name"] for x in audits] == ["unrecognized", "switch_context", "files_quota"]


def test_a_memory_is_kept_only_when_the_person_taps_its_card(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    save = {"id": "m1", "name": "memory_save", "args": {"text": "Likes tea"}}
    scripted(monkeypatch, [("", [save])])  # the card ends the turn: no "yes" round to loop on
    result = chat(alice, db, "yes")
    [card] = [c for c in result["cards"] if c.get("confirmation_id")]
    assert card["confirmation_path"] == "/assistant/confirmations/" + card["confirmation_id"]
    assert card["preview"]["name"] == "Likes tea"
    assert not db.query(Record).filter(Record.kind == "memory").count()
    assert a.confirm_message(card["confirmation_id"], alice, db)["status"] == "completed"
    [memory] = a.memories(alice, db)
    assert memory["text"] == "Likes tea" and memory["source_conversation_id"] == result["conversation_id"]
    with pytest.raises(HTTPException):  # once
        a.confirm_message(card["confirmation_id"], alice, db)


def test_done_actions_keep_their_cards_when_the_narration_fails(setup, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    add = {
        "id": "g1",
        "name": "household_create",
        "args": {"item": {"kind": "groceries", "data": {"label": "Tea"}}},
    }
    scripted(monkeypatch, [("", [add])])  # the second round fails
    result = chat(alice, db, "Ajoute du thé aux courses")
    assert result["status"] == "completed" and result["cards"][0]["label"] == "House record created"
    assert "did not complete" not in result["reply"]


def test_nothing_added_is_not_one_song():
    turn = SimpleNamespace(
        language="en", outcome="completed", cards=[{"label": "Added to music queue", "count": 0}]
    )
    assert a.fallback_reply(turn) == a.FALLBACKS["en"]["accepted"]


def test_route_fills_query_defaults_and_names_what_is_missing(setup):
    from houseos import music

    db, (alice, _) = setup
    with pytest.raises(TypeError, match="needs q"):
        t.route(music.search, actor=alice, db=db)
    assert t.route(music.history, actor=alice, db=db)["items"] == []


def test_scripts_and_garage_doors_wait_for_a_tap():
    from houseos import home

    assert home.sensitive("script") and home.sensitive("cover", {"device_class": "garage"})
    assert not home.sensitive("cover", {"device_class": "blind"}) and not home.sensitive("light")
