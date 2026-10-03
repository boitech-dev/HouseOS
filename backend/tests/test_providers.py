"""Provider setup boundaries. Catalog/native replies are fixtures; no model calls."""

import json
import httpx
import pytest
from fastapi import HTTPException
from houseos import assistant as a, integrations as integrations, provider_checks as checks
from houseos.models import Integration, Usage


def mock_catalog(monkeypatch, reply):
    client = httpx.Client
    monkeypatch.setattr(
        checks.httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(reply), **kw)
    )


def test_complete_catalog_search_pricing_without_urls_or_password(setup, monkeypatch):
    db, (actor, _) = setup

    def reply(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/models"
        assert request.headers["authorization"] == "Bearer fixture-only"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": f"model-{i}",
                        "name": f"Model {i}",
                        "supported_parameters": ["tools"],
                        "pricing": {"prompt": "0.000001", "completion": "0.000002", "request": "0.0000001"},
                    }
                    for i in range(650)
                ]
            },
        )

    mock_catalog(monkeypatch, reply)
    result = checks.refresh("openrouter", checks.CatalogRefresh(api_key="fixture-only"), actor, db)
    assert len(result["items"]) == 650 and "fixture-only" not in json.dumps(result)
    price = result["items"][-1]["pricing"]
    assert price["input_microusd_per_million"] == 1_000_000 and price["request_microusd"] == 1
    integrations.save_integration(
        "openrouter",
        integrations.IntegrationInput(
            enabled=True,
            secret="fixture-only",
            config={
                "model": "model-649",
                "daily_budget_microusd": 1000000,
                "user_daily_budget_microusd": 250000,
            },
        ),
        actor,
        db,
    )
    row = db.get(Integration, "openrouter")
    assert row.config["output_microusd_per_million"] == 2_000_000
    assert all("fixture-only" not in json.dumps(item) for item in integrations.list_integrations(actor, db))
    # Unknown/new pricing must not inherit the old model's rates.
    integrations.save_integration(
        "openrouter",
        integrations.IntegrationInput(config={**row.config, "model": "unknown"}, secret=""),
        actor,
        db,
    )
    assert "input_microusd_per_million" not in row.config and row.encrypted_secret == ""


def test_catalog_failure_preserves_selection_and_paginates_anthropic(setup, monkeypatch):
    db, (actor, _) = setup
    db.add(Integration(name="anthropic", enabled=False, config={"model": "saved"}))
    db.commit()
    pages = []

    def reply(request):
        pages.append(dict(request.url.params))
        if len(pages) == 1:
            return httpx.Response(200, json={"data": [{"id": "one"}], "has_more": True, "last_id": "one"})
        return httpx.Response(200, json={"data": [{"id": "two"}], "has_more": False})

    mock_catalog(monkeypatch, reply)
    assert len(checks.refresh("anthropic", checks.CatalogRefresh(api_key="fixture"), actor, db)["items"]) == 2
    assert pages[1]["after_id"] == "one"
    # Replace the transport using the real class, not the already patched factory.
    monkeypatch.undo()
    mock_catalog(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(HTTPException):
        checks.refresh("anthropic", checks.CatalogRefresh(api_key="fixture"), actor, db)
    assert db.get(Integration, "anthropic").config["model"] == "saved"
    assert len(db.get(Integration, "catalog.anthropic").config["items"]) == 2


def test_native_personal_owner_and_no_credential_return(setup, monkeypatch):
    db, (alice, bob) = setup
    seen = []

    def native(name, action, **fields):
        seen.append((name, action))
        return (
            {"status": "local_sign_in_required"}
            if action == "login_start"
            else {"logged_in": False, "status": "signed_out"}
        )

    monkeypatch.setattr(checks, "native_request", native)
    checks.native_login("anthropic", alice, db)
    with pytest.raises(HTTPException) as denied:
        checks.native_status("anthropic", bob, db)
    assert denied.value.status_code == 403
    integrations.save_integration(
        "anthropic",
        integrations.IntegrationInput(enabled=True, config={"auth_mode": "claude_code", "model": "sonnet"}),
        alice,
        db,
    )
    cfg = integrations.integration_config(db, "anthropic")
    assert cfg["owner_user_id"] == alice.id and "api_key" not in cfg
    assert (
        next(item for item in a.status(bob, db)["providers"] if item["name"] == "anthropic")["available"]
        is False
    )
    checks.native_logout("anthropic", alice, db)
    assert db.get(Integration, "native.owner.anthropic") is None
    assert not db.get(Integration, "anthropic").enabled


def test_native_request_budget_and_unknown_billing(setup, monkeypatch):
    db, (actor, bob) = setup
    cfg = {
        "auth_mode": "codex",
        "owner_user_id": actor.id,
        "model": "native-model",
        "daily_request_limit": 1,
        "user_daily_request_limit": 1,
    }
    db.add(Integration(name="openai", enabled=True, config=cfg))
    db.commit()
    identity = a.reserve(db, actor, "openai", dict(cfg), [], [])
    record = db.get(Usage, identity)
    evidence = a.record_usage_evidence(db, record, cfg, {})
    db.commit()
    assert record.cost_microusd is None and record.status == "usage_unknown"
    assert evidence["cost_kind"] == "subscription" and record.reserved_microusd == 0
    with pytest.raises(HTTPException) as limit:
        a.reserve(db, actor, "openai", dict(cfg), [], [])
    assert limit.value.status_code == 429
    db.rollback()
    with pytest.raises(HTTPException) as denied:
        a.reserve(db, bob, "openai", dict(cfg), [], [])
    assert denied.value.status_code == 403
    captured = []
    monkeypatch.setattr(
        checks,
        "native_request",
        lambda provider, action, **fields: (
            captured.append(fields) or {"reply": "fixture", "calls": [], "wire": [], "usage": {}}
        ),
    )
    assert a.provider_round("openai", {**cfg, "_timeout_seconds": 9}, [], [])[0] == "fixture"
    assert captured[0]["timeout_seconds"] == 9


def test_price_parser_rejects_unknown_invalid_and_nonfinite():
    result = checks.normalized_model(
        {
            "id": "fixture",
            "context_length": "unknown",
            "supported_parameters": None,
            "pricing": {"prompt": "NaN", "completion": "-1", "request": "Infinity"},
        }
    )
    assert result["pricing"] == {} and result["context_length"] is None
