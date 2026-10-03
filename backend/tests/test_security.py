"""Independent regression proofs for reviewed auth/AI boundaries. No paid calls."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from houseos import assistant as a
from houseos import assistant_tools as t
from houseos.auth import Actor
from houseos.db import new_id, utcnow
from houseos.models import Integration, Record, SessionToken, Usage, User


def test_mariadb_budget_race_with_old_snapshots(domain):
    if os.environ.get("HOUSEOS_TEST_MARIADB") != "1":
        pytest.skip("Run with isolated MariaDB test credentials")
    db, (alice, bob, _) = domain
    name = "test-" + new_id()[:12]
    # Exactly one minimal request (800 max output tokens at one microUSD per token) fits.
    cfg = {
        "model": "test-model",
        "input_microusd_per_million": 0,
        "output_microusd_per_million": 1_000_000,
        "daily_budget_microusd": 1000,
        "user_daily_budget_microusd": 1000,
    }
    db.add(Integration(name=name, enabled=True, config=cfg))
    db.commit()
    barrier = Barrier(2)

    def reserve(actor):
        with Session(db.get_bind(), expire_on_commit=False) as session:
            session.scalar(select(func.count()).select_from(Usage))
            barrier.wait()
            try:
                a.reserve(session, actor, name, dict(cfg), [{"role": "user", "content": "test"}], [])
                return 200
            except HTTPException as exc:
                session.rollback()
                return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (alice, bob)))
        assert sorted(results) == [200, 429]
        db.rollback()
        assert db.scalar(select(func.sum(Usage.reserved_microusd)).where(Usage.provider == name)) == 800
    finally:
        db.rollback()
        db.execute(delete(Usage).where(Usage.provider == name))
        db.execute(delete(Integration).where(Integration.name == name))
        db.commit()


def with_session(db, actor):
    identity = new_id().replace("-", "") + new_id().replace("-", "")
    db.add(
        SessionToken(
            token_hash=identity,
            user_id=actor.id,
            csrf_token="fixture",
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    db.commit()
    return Actor(actor.id, actor.name, actor.role, actor.permissions, identity)


def stub_provider_setup(monkeypatch):
    cfg = {
        "api_key": "fixture-not-a-real-secret",
        "model": "test-model",
        "input_microusd_per_million": 1,
        "output_microusd_per_million": 1,
    }
    monkeypatch.setattr(a, "integration_config", lambda db, name: dict(cfg))

    def reserve(db, actor, provider, config, messages, schemas):
        row = Usage(user_id=actor.id, provider="test", model="test-model", reserved_microusd=1)
        db.add(row)
        db.commit()
        return row.id

    monkeypatch.setattr(a, "reserve", reserve)


def test_revoked_session_cannot_execute_returned_ai_tool(domain, monkeypatch):
    db, (alice, _, _) = domain
    alice = with_session(db, alice)
    stub_provider_setup(monkeypatch)
    label = "forbidden-after-revocation-" + new_id()

    def provider(*args):
        with Session(db.get_bind()) as other:
            other.execute(delete(SessionToken).where(SessionToken.token_hash == alice.session_hash))
            other.commit()
        return (
            "",
            [
                {
                    "id": "tool-1",
                    "name": "household_create",
                    "args": {"item": {"kind": "groceries", "data": {"label": label}}},
                }
            ],
            [],
            {"input_tokens": 10, "output_tokens": 10, "cached_tokens": 0},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    with pytest.raises(HTTPException) as stopped:
        a.chat(a.Chat(message="Add one item", context="household", idempotency_key=new_id()), alice, db)
    assert stopped.value.status_code == 401
    db.rollback()
    assert (
        db.scalars(
            select(Record).where(Record.kind == "household.groceries", Record.owner_id == alice.id)
        ).all()
        == []
    )


def test_new_conversation_request_replay_does_not_dispatch_again(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    dispatched = []

    def provider(*args):
        dispatched.append(1)
        return "Test reply", [], [], {"input_tokens": 10, "output_tokens": 10, "cached_tokens": 0}

    monkeypatch.setattr(a, "provider_round", provider)
    request = a.Chat(message="Hello", idempotency_key=new_id())
    first = a.chat(request, alice, db)
    second = a.chat(request, alice, db)
    assert first == second
    assert len(dispatched) == 1
    assert (
        len(
            db.scalars(select(Record).where(Record.kind == "conversation", Record.owner_id == alice.id)).all()
        )
        == 1
    )


def test_household_file_tool_contracts_reuse_permissions(domain):
    from houseos import tool_household as tools
    from pydantic import ValidationError

    db, (alice, bob, _) = domain
    bundle = tools.build_tools("household")
    assert len(bundle) == 10
    assert len(tools.build_tools("files")) == 8
    for model, _, _ in list(bundle.values()) + list(tools.build_tools("files").values()):
        assert model.model_config.get("extra") == "forbid"
    model, _, create = bundle["household_create"]
    result = create(
        model.model_validate({"item": {"kind": "board", "data": {"title": "House tool test"}}}), alice, db
    )
    assert result["status"] == "completed"
    editmodel, _, edit = bundle["household_update"]
    updated = edit(
        editmodel.model_validate(
            {
                "item": {
                    "kind": "board",
                    "id": result["id"],
                    "version": result["version"],
                    "data": {"title": "Changed", "pinned": None},
                }
            }
        ),
        alice,
        db,
    )
    assert updated["summary"]["title"] == "Changed"
    with pytest.raises(HTTPException):
        edit(
            editmodel.model_validate(
                {
                    "item": {
                        "kind": "board",
                        "id": result["id"],
                        "version": updated["version"],
                        "data": {"title": "Cannot edit another author"},
                    }
                }
            ),
            bob,
            db,
        )
    with pytest.raises(ValidationError):
        model.model_validate(
            {"item": {"kind": "board", "data": {"title": "No generic commands", "shell": "anything"}}}
        )


def test_strict_schema_preserves_title_property_and_nested_defaults():
    from houseos.tool_household import HouseCreate, HouseEdit

    schema = t.strict_schema(HouseCreate.model_json_schema())
    task = schema["$defs"]["TaskData"]
    assert "title" in task["properties"] and "title" in task["required"]
    assert "title" not in task
    payload = {"item": {"kind": "tasks", "data": {"title": "A task", "status": None, "timezone": None}}}
    normalized = t.omit_default_nulls(payload, HouseCreate)
    validated = HouseCreate.model_validate(normalized)
    assert validated.item.data.status == "open"
    assert validated.item.data.timezone == "UTC"  # unset: the house setting is filled in later
    patch = {
        "item": {
            "kind": "tasks",
            "id": "fixture",
            "version": 1,
            "data": {"title": "Changed", "assignee_id": None},
        },
        "clear_fields": None,
    }
    normalized = t.omit_default_nulls(patch, HouseEdit)
    assert "assignee_id" in normalized["item"]["data"]
    assert HouseEdit.model_validate(normalized).clear_fields == []


def test_deleted_conversation_cannot_replay_cached_private_reply(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    monkeypatch.setattr(
        a, "provider_round", lambda *args: ("Private reply", [], [], {"input_tokens": 1, "output_tokens": 1})
    )
    request = a.Chat(message="Private question", idempotency_key=new_id())
    result = a.chat(request, alice, db)
    a.delete_conversation(result["conversation_id"], alice, db)
    with pytest.raises(HTTPException) as stopped:
        a.chat(request, alice, db)
    assert stopped.value.status_code == 404
    receipt = db.scalar(select(a.ChatReceipt).where(a.ChatReceipt.owner_id == alice.id))
    assert receipt.state == "deleted" and receipt.result == {}


def test_plain_reply_is_not_returned_or_saved_after_session_revocation(domain, monkeypatch):
    db, (alice, _, _) = domain
    alice = with_session(db, alice)
    stub_provider_setup(monkeypatch)

    def provider(*args):
        with Session(db.get_bind()) as other:
            other.execute(delete(SessionToken).where(SessionToken.token_hash == alice.session_hash))
            other.commit()
        return "Private reply", [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    with pytest.raises(HTTPException) as stopped:
        a.chat(a.Chat(message="Private question", idempotency_key=new_id()), alice, db)
    assert stopped.value.status_code == 401
    assert not db.scalars(
        select(a.ChatMessage).where(a.ChatMessage.owner_id == alice.id, a.ChatMessage.role == "assistant")
    ).all()
    receipt = db.scalar(select(a.ChatReceipt).where(a.ChatReceipt.owner_id == alice.id))
    assert receipt.state == "failed" and receipt.result["reply"] == ""


def test_delete_during_provider_stops_without_resurrecting_conversation(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)

    def provider(*args):
        with Session(db.get_bind()) as other:
            convo = other.scalar(
                select(Record).where(Record.owner_id == alice.id, Record.kind == "conversation")
            )
            a.delete_conversation(convo.id, alice, other)
        return "Must not resurrect", [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    with pytest.raises(HTTPException) as stopped:
        a.chat(a.Chat(message="Private question", idempotency_key=new_id()), alice, db)
    assert stopped.value.status_code == 404
    assert not db.scalars(select(a.ChatMessage).where(a.ChatMessage.owner_id == alice.id)).all()
    receipt = db.scalar(select(a.ChatReceipt).where(a.ChatReceipt.owner_id == alice.id))
    assert receipt.state == "deleted" and receipt.result == {}


def test_missing_usage_retains_unknown_cost_and_budget_reservation(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    monkeypatch.setattr(a, "provider_round", lambda *args: ("Reply", [], [], {}))
    a.chat(a.Chat(message="Hello", idempotency_key=new_id()), alice, db)
    usage = db.scalar(select(Usage).where(Usage.user_id == alice.id))
    assert usage.status == "usage_unknown" and usage.cost_microusd is None
    assert usage.reserved_microusd == 1


def test_usage_evidence_prices_cache_and_provider_reported_cost(domain):
    db, (alice, _, _) = domain
    cfg = {
        "input_microusd_per_million": 1_000_000,
        "output_microusd_per_million": 2_000_000,
        "cached_input_microusd_per_million": 100_000,
        "cache_write_microusd_per_million": 1_250_000,
        "pricing_as_of": "2026-09-20",
        "api_key": "must-never-be-recorded",
    }
    record = Usage(user_id=alice.id, provider="anthropic", model="test", reserved_microusd=1000)
    db.add(record)
    db.flush()
    evidence = a.record_usage_evidence(
        db,
        record,
        cfg,
        {"input_tokens": 100, "output_tokens": 10, "cached_tokens": 40, "cache_write_tokens": 20},
    )
    assert record.cost_microusd == 89  # 40 normal + 4 cached + 25 written + 20 output
    assert evidence["cost_kind"] == "estimated"
    assert "api_key" not in evidence["pricing_snapshot"]
    record.provider = "openrouter"
    evidence = a.record_usage_evidence(
        db, record, cfg, {"input_tokens": 100, "output_tokens": 10, "cost_usd": "0.0000121"}
    )
    assert record.cost_microusd == 13 and evidence["cost_kind"] == "provider_reported"
    cfg.pop("cached_input_microusd_per_million")
    second = Usage(user_id=alice.id, provider="openai", model="test", reserved_microusd=1000)
    db.add(second)
    db.flush()
    evidence = a.record_usage_evidence(
        db, second, cfg, {"input_tokens": 100, "output_tokens": 10, "cached_tokens": 40}
    )
    assert second.cost_microusd is None and evidence["cost_kind"] == "unknown"
    db.commit()


def test_ai_audit_records_no_private_content(domain, monkeypatch):
    from houseos.models import Event

    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    rounds = iter(
        [
            (
                "",
                [{"id": "call-1", "name": "memory_list", "args": {}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            ),
            ("Private answer must not be logged", [], [], {"input_tokens": 1, "output_tokens": 1}),
        ]
    )
    monkeypatch.setattr(a, "provider_round", lambda *args: next(rounds))
    a.chat(a.Chat(message="Private question must not be logged", idempotency_key=new_id()), alice, db)
    rows = db.scalars(
        select(Event).where(
            Event.user_id == alice.id, Event.topic.in_(["audit.ai_request", "audit.tool_call"])
        )
    ).all()
    assert len(rows) == 3
    for row in rows:
        assert set(row.payload) <= {
            "usage_id",
            "provider",
            "model",
            "status",
            "latency_ms",
            "tool_calls",
            "tool_name",
            "operation_id",
            "workflow_id",
            "confirmation_id",
        }
        assert "Private" not in str(row.payload)


def test_worker_stale_generation_and_finished_job_do_not_execute(domain, monkeypatch):
    from houseos import worker
    from houseos.models import Job

    db, (alice, _, _) = domain
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(
        worker, "fetch", lambda *args, **kwargs: pytest.fail("Stale worker executed an external action")
    )
    row = Job(
        actor_id=alice.id,
        logical_key="test-" + new_id(),
        kind="music.metadata",
        payload={"item_id": "absent"},
        state="running",
        generation=2,
    )
    db.add(row)
    db.commit()
    try:
        worker.run_job((row.id, 1, row.kind, row.payload))
        db.refresh(row)
        assert row.state == "running" and row.generation == 2 and row.error_code is None
        row.state = "completed"
        db.commit()
        worker.run_job((row.id, 2, row.kind, row.payload))
        db.refresh(row)
        assert row.state == "completed" and row.error_code is None
    finally:
        db.rollback()
        db.execute(delete(Job).where(Job.id == row.id))
        db.commit()


def test_memory_expiry_and_edit_are_private_and_timezone_explicit(domain):
    from pydantic import ValidationError

    db, (alice, bob, _) = domain
    with pytest.raises(ValidationError):
        a.Memory(text="bad expiry", expires_at="2026-01-01T12:00:00")
    expired = a.save_memory(a.Memory(text="Expired", expires_at="2020-01-01T00:00:00Z"), alice, db)
    active = a.save_memory(a.Memory(text="Current"), alice, db)
    assert [x["id"] for x in a.memories(alice, db)] == [active["id"]]
    with pytest.raises(HTTPException) as denied:
        a.edit_memory(active["id"], a.Memory(text="Wrong user"), bob, db)
    assert denied.value.status_code == 404
    a.edit_memory(expired["id"], a.Memory(text="New explicit memory"), alice, db)
    assert len(a.memories(alice, db)) == 2


def test_abandoned_receipt_returns_unverified_without_replaying(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    monkeypatch.setattr(
        a, "provider_round", lambda *args: ("Original reply", [], [], {"input_tokens": 1, "output_tokens": 1})
    )
    request = a.Chat(message="Hello", idempotency_key=new_id())
    a.chat(request, alice, db)
    receipt = db.scalar(select(a.ChatReceipt).where(a.ChatReceipt.owner_id == alice.id))
    receipt.state, receipt.result = "running", {}
    receipt.created_at = utcnow() - timedelta(minutes=16)
    db.commit()
    monkeypatch.setattr(a, "provider_round", lambda *args: pytest.fail("Interrupted request replayed"))
    assert a.chat(request, alice, db)["status"] == "unverified"


def test_budget_warning_is_durable_and_deduplicated(domain):
    db, (alice, _, _) = domain
    name = "test-" + new_id()[:12]
    cfg = {
        "model": "test",
        "input_microusd_per_million": 0,
        "output_microusd_per_million": 1_000_000,
        "daily_budget_microusd": 2000,
        "user_daily_budget_microusd": 2000,
        "budget_warning_percent": 40,
    }
    db.add(Integration(name=name, enabled=True, config=cfg))
    db.commit()
    try:
        for _ in range(2):
            a.reserve(db, alice, name, dict(cfg), [], [])
        warnings = [
            r.data
            for r in db.scalars(
                select(Record).where(Record.kind == "usage.warning", Record.owner_id == alice.id)
            )
        ]
        assert {row["scope"] for row in warnings} == {"user", "provider"}
        assert len(warnings) == 2
        assert all(row["threshold_percent"] == 40 for row in warnings)
    finally:
        db.rollback()
        db.execute(delete(Integration).where(Integration.name == name))
        db.commit()


def test_next_turn_receives_compact_workflow_ids_without_source_dump():
    row = a.ChatMessage(
        role="assistant",
        content="Choose a source",
        cards=[
            {
                "domain": "cinema",
                "id": "workflow-id",
                "version": 3,
                "state": "awaiting_choice",
                "choice_set": {
                    "id": "frozen-choice-set",
                    "candidates": [{"raw_provider_object": "never send"}],
                },
                "private_url": "never send",
                "preview": {"full_source": "never send"},
            }
        ],
    )
    message = a.history_message(row)
    assert all(
        value in message["content"] for value in ("workflow-id", "frozen-choice-set", "awaiting_choice")
    )
    assert "never send" not in message["content"]


def test_all_tool_schemas_have_strict_required_property_parity():
    def inspect(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for child in node.values():
                inspect(child)
        elif isinstance(node, list):
            for child in node:
                inspect(child)

    for context in ("general", "music", "cinema", "household", "files", "diagnostics"):
        for model, _, _ in a.tool_registry(context).values():
            inspect(t.strict_schema(model.model_json_schema()))


def test_general_media_context_switch_and_next_turn_natural_choice(domain, monkeypatch):
    from houseos import cinema, cinema_jobs

    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    title = cinema.CinemaTitle(
        id=new_id(), canonical_id=new_id(), title="Fixture movie", kind="movie", data={}
    )
    db.add(title)
    db.commit()
    frozen = {
        "id": "workflow-test",
        "state": "awaiting_choice",
        "version": 2,
        "choice_set": {
            "id": "choices-test",
            "candidates": [{"id": "source-test", "rank": 1, "height": 2160}],
        },
    }
    monkeypatch.setattr(cinema_jobs, "discover", lambda body, actor, session: dict(frozen))
    selected = []

    def launch(identity, body, actor, session):
        selected.append((identity, body.source_id, body.device_id))
        return {
            "id": identity,
            "state": "needs_confirmation",
            "status": "needs_confirmation",
            "version": 3,
            "confirmation_id": "confirm-test",
            "preview": {"action": "prepare playback"},
        }

    monkeypatch.setattr(cinema, "launch", launch)
    rounds = []

    def provider(provider, cfg, messages, schemas):
        if not schemas:
            return (
                "Confirm this exact source before playback.",
                [],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        rounds.append([item["name"] for item in schemas])
        if len(rounds) == 1:
            assert "cinema_discover" not in rounds[-1]
            return (
                "",
                [{"id": "switch", "name": "switch_context", "args": {"context": "cinema"}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        if len(rounds) == 2:
            assert "cinema_discover" in rounds[-1]
            return (
                "",
                [
                    {
                        "id": "discover",
                        "name": "cinema_discover",
                        "args": {"media_id": title.id, "device_id": "device-test"},
                    }
                ],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        if len(rounds) == 3:
            assert operation_id in str(messages)
            return (
                "",
                [{"id": "operation", "name": "cinema_operation", "args": {"id": operation_id}}],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        assert "cinema_launch" in rounds[-1]
        context = str(messages)
        assert "workflow-test" in context and "choices-test" in context
        return (
            "",
            [
                {
                    "id": "launch",
                    "name": "cinema_launch",
                    "args": {
                        "workflow_id": "workflow-test",
                        "version": 2,
                        "source_id": "source-1",
                        "device_id": "tv",
                        "subtitle_track": "off",
                    },
                }
            ],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    first = a.chat(a.Chat(message="Put Dune 2 on", idempotency_key=new_id()), alice, db)
    assert first["status"] == "accepted"
    operation_id = first["cards"][0]["operation_id"]
    # Scope the real DB claim to this fixture actor; never drain unrelated queued jobs.
    from houseos.models import Job

    original_select = cinema_jobs.select

    def fixture_select(*entities):
        query = original_select(*entities)
        return query.where(Job.actor_id == alice.id) if entities and entities[0] is Job else query

    monkeypatch.setattr(cinema_jobs, "select", fixture_select)
    assert cinema_jobs.process_one_operation(db) is True
    observed = cinema_jobs.get_operation(operation_id, alice, db)
    assert observed["status"] == "completed" and observed["workflow"]["choice_set"]["id"] == "choices-test"
    second = a.chat(
        a.Chat(message="1", conversation_id=first["conversation_id"], idempotency_key=new_id()), alice, db
    )
    assert second["status"] == "needs_confirmation"
    assert selected == [("workflow-test", "source-1", "tv")]
    assert len(rounds) == 4


def test_conversation_message_order_survives_timestamp_ties(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    expected = []

    def provider(provider, cfg, messages, schemas):
        expected.append(messages[-1]["content"])
        return "Reply to " + messages[-1]["content"], [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    identity = None
    for index in range(3):
        result = a.chat(
            a.Chat(message=f"Question {index}", conversation_id=identity, idempotency_key=new_id()), alice, db
        )
        identity = result["conversation_id"]
    rows = db.scalars(select(a.ChatMessage).where(a.ChatMessage.conversation_id == identity)).all()
    for row in rows:
        row.created_at = utcnow().replace(microsecond=0)
    db.commit()
    history = a.conversation(identity, alice, db)["messages"]
    assert [row["content"] for row in history] == [
        value for index in range(3) for value in (f"Question {index}", f"Reply to Question {index}")
    ]


def test_context_switch_does_not_reset_round_budget(domain, monkeypatch):
    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    dispatched = []

    def provider(*args):
        dispatched.append(1)
        return (
            "Unverified provider narrative",
            [{"id": str(len(dispatched)), "name": "switch_context", "args": {"context": "cinema"}}],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Switch topic", idempotency_key=new_id()), alice, db)
    assert len(dispatched) == 8 and result["status"] == "limit_reached"
    assert "Unverified provider narrative" not in result["reply"]


def test_openrouter_adapter_preserves_cost_and_missing_usage(monkeypatch):
    import httpx

    original_client = httpx.Client
    payload = {
        "choices": [{"message": {"content": "Reply"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "cost": 0.0000121,
            "prompt_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 20},
        },
    }
    requests = []

    def respond(request):
        import json

        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(a.httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    cfg = {"api_key": "fixture", "model": "fixture-model", "max_output_tokens": 17}
    reply, calls, message, reported = a.provider_round("openrouter", cfg, [], [])
    assert requests[-1]["max_tokens"] == 17
    assert reported["input_tokens"] == 100 and reported["cost_usd"] == 0.0000121
    assert reported["cached_tokens"] == 40 and reported["cache_write_tokens"] == 20
    payload["usage"] = None
    reported = a.provider_round("openrouter", cfg, [], [])[3]
    assert reported["input_tokens"] is None and reported["output_tokens"] is None
    assert reported["cost_usd"] is None


def test_anthropic_adapter_includes_cache_tokens_in_total(monkeypatch):
    import anthropic
    from types import SimpleNamespace

    class Client:
        def __init__(self, **kwargs):
            self.messages = SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    content=[],
                    usage=SimpleNamespace(
                        input_tokens=40,
                        output_tokens=10,
                        cache_read_input_tokens=40,
                        cache_creation_input_tokens=20,
                    ),
                )
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(anthropic, "Anthropic", Client)
    reported = a.provider_round("anthropic", {"api_key": "fixture", "model": "fixture"}, [], [])[3]
    assert reported == {
        "input_tokens": 100,
        "output_tokens": 10,
        "cached_tokens": 40,
        "cache_write_tokens": 20,
    }


def test_paid_probe_is_synthetic_budgeted_and_single_use(provider_probe, monkeypatch):
    checks, db, actor, name = provider_probe
    marker = "private-resident-content-" + new_id()
    db.add(Record(owner_id=actor.id, kind="memory", data={"text": marker}))
    db.commit()
    calls = []

    def provider(provider, cfg, messages, schemas):
        import json

        assert marker not in json.dumps([messages, schemas])
        assert schemas[0]["name"] == "houseos_probe"
        calls.append(1)
        return (
            "",
            [{"id": "echo", "name": "houseos_probe", "args": {"echo": "houseos"}}],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    prepared = checks.prepare(name, checks.Probe(current_password="fixture-password"), actor, db)
    result = checks.confirm(prepared["confirmation_id"], actor, db)
    assert result["status"] == "verified" and result["structured_tool_call"] is True
    usage = db.scalar(select(Usage).where(Usage.user_id == actor.id))
    assert usage.reserved_microusd == 32 and usage.cost_microusd == 1
    with pytest.raises(HTTPException) as replay:
        checks.confirm(prepared["confirmation_id"], actor, db)
    assert replay.value.status_code == 409 and len(calls) == 1


def test_paid_probe_rejects_wrong_schema(provider_probe, monkeypatch):
    checks, db, actor, name = provider_probe
    monkeypatch.setattr(
        a,
        "provider_round",
        lambda *args: (
            "",
            [{"name": "houseos_probe", "args": {"echo": "wrong"}}],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        ),
    )
    prepared = checks.prepare(name, checks.Probe(current_password="fixture-password"), actor, db)
    assert checks.confirm(prepared["confirmation_id"], actor, db)["status"] == "unsupported"


def test_paid_probe_detects_config_edit_even_with_identical_timestamp(provider_probe, monkeypatch):
    checks, db, actor, name = provider_probe
    prepared = checks.prepare(name, checks.Probe(current_password="fixture-password"), actor, db)
    row = db.get(Integration, name)
    old = row.updated_at
    row.config = {**row.config, "model": "changed-model"}
    db.commit()
    row.updated_at = old
    db.commit()
    monkeypatch.setattr(a, "provider_round", lambda *args: pytest.fail("Stale model probe dispatched"))
    with pytest.raises(HTTPException) as stale:
        checks.confirm(prepared["confirmation_id"], actor, db)
    assert stale.value.status_code == 409
    assert not db.scalars(select(Usage).where(Usage.user_id == actor.id)).all()


def test_per_user_zero_budget_prevents_paid_probe(provider_probe, monkeypatch):
    checks, db, actor, name = provider_probe
    user = db.get(User, actor.id)
    user.preferences = {"ai_daily_budgets": {name: 0}}
    db.commit()
    monkeypatch.setattr(a, "provider_round", lambda *args: pytest.fail("Disabled user budget dispatched"))
    prepared = checks.prepare(name, checks.Probe(current_password="fixture-password"), actor, db)
    assert checks.confirm(prepared["confirmation_id"], actor, db)["status"] == "failed"
    assert not db.scalars(select(Usage).where(Usage.user_id == actor.id)).all()


def test_queued_discovery_stops_model_loop_with_operation_reference(domain, monkeypatch):
    from houseos import cinema_jobs, cinema

    db, (alice, _, _) = domain
    stub_provider_setup(monkeypatch)
    title = cinema.CinemaTitle(
        id=new_id(), canonical_id=new_id(), title="Fixture queued title", kind="movie", data={}
    )
    db.add(title)
    db.commit()
    monkeypatch.setattr(
        cinema_jobs,
        "enqueue_discovery",
        lambda *args: {"status": "accepted", "operation_id": "pending-operation"},
    )
    calls = []

    def provider(*args):
        calls.append(1)
        return (
            "",
            [
                {
                    "id": "discover",
                    "name": "cinema_discover",
                    "args": {"media_id": title.id, "device_id": "device"},
                }
            ],
            [],
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="Find sources", context="cinema", idempotency_key=new_id()), alice, db)
    assert result["status"] == "accepted" and len(calls) == 1
    assert result["cards"][0]["operation_id"] == "pending-operation"
    # Accepted work is announced as started, never as done.
    assert result["reply"] == "On it. Details below."


def test_openai_adapter_uses_configured_output_limit(monkeypatch):
    import openai
    from types import SimpleNamespace

    observed = []

    class Client:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            observed.append(kwargs)
            return SimpleNamespace(output=[], output_text="Reply", usage=None)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(openai, "OpenAI", Client)
    reported = a.provider_round(
        "openai", {"api_key": "fixture", "model": "fixture", "max_output_tokens": 19}, [], []
    )[3]
    assert observed[0]["max_output_tokens"] == 19
    assert reported["input_tokens"] is None and reported["output_tokens"] is None
