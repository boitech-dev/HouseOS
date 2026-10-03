"""Admin-owned model assignments per assistant purpose; credentials and budgets stay provider-owned."""

import re
import time
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, select
from .auth import Input, require_admin
from .db import get_db, utcnow
from .models import Integration, Operation, Usage
from .integrations import AI_PROVIDERS, connected
from .events import emit

router = APIRouter(prefix="/admin/assistants", tags=["assistant-assignments"])
Purpose = Literal["general", "personal_space", "setup", "themes"]
PROFILES = ("general", "personal_space", "setup", "themes")


class Assignment(Input):
    provider: Literal[AI_PROVIDERS]
    model: str = Field(min_length=1, max_length=160)
    reasoning_effort: Literal["low", "medium", "high"] | None = None


def assignment(db, purpose):
    row = db.get(Integration, "assistant.roles")
    saved = (row.config or {}).get(purpose) if row else None
    if saved:
        return dict(saved)
    # Unassigned: the chosen default while it works, else the first working connection, API keys
    # before personal subscriptions.
    defaults = db.get(Integration, "budgets")
    preferred = (defaults.config.get("default_provider") if defaults else None) or AI_PROVIDERS[0]
    connection = db.get(Integration, preferred)
    if not connected(connection):
        working = [row for name in AI_PROVIDERS if connected(row := db.get(Integration, name))]
        working.sort(key=lambda row: row.config.get("auth_mode", "api") != "api")
        connection = working[0] if working else connection
    cfg = connection.config if connection else {}
    return {
        "provider": connection.name if connection else preferred,
        "model": cfg.get("model"),
        "reasoning_effort": cfg.get("reasoning_effort"),
    }


def apply_assignment(db, cfg, selected):
    """Apply exact model/pricing after every fresh provider read, before reserving spend."""
    model = selected.get("model")
    if not model:
        raise HTTPException(409, "An administrator must select a model for this assistant")
    changed = cfg.get("model") != model
    cfg["model"] = model
    cfg.pop("reasoning_effort", None)
    if selected.get("reasoning_effort"):
        cfg["reasoning_effort"] = selected["reasoning_effort"]
    if cfg.get("auth_mode") in {"codex", "claude_code"}:
        return
    catalog = db.get(Integration, "catalog." + selected["provider"])
    item = next((x for x in (catalog.config.get("items", []) if catalog else []) if x["id"] == model), None)
    if selected["provider"] == "openrouter" or changed:
        from .assistant import PRICING_KEYS

        for key in PRICING_KEYS:
            cfg.pop(key, None)
        if item and item.get("pricing"):
            cfg.update(item["pricing"])
            cfg["pricing_source"] = "provider model catalog"
            cfg["pricing_as_of"] = catalog.config.get("observed_at", "")


def tested(db, selected):
    """Whether the latest capability test of this exact model made the expected tool call."""
    probes = db.scalars(
        select(Operation)
        .where(Operation.kind == "provider.probe", Operation.state.in_(("verified", "unsupported", "failed")))
        .order_by(Operation.created_at.desc())
        .limit(50)
    )
    latest = next(
        (
            row
            for row in probes
            if (row.data["provider"], row.data["model"]) == (selected["provider"], selected["model"])
        ),
        None,
    )
    return bool(latest and latest.state == "verified")


@router.get("")
def profiles(actor=Depends(require_admin), db=Depends(get_db)):
    return {
        "items": [
            {
                "purpose": purpose,
                **(selected := assignment(db, purpose)),
                "ready": bool(selected["model"] and connected(db.get(Integration, selected["provider"]))),
                "tested": tested(db, selected),
            }
            for purpose in PROFILES
        ],
        "connections": [
            {
                "provider": name,
                "enabled": bool((r := db.get(Integration, name)) and r.enabled),
                "auth_mode": r.config.get("auth_mode", "api") if r else "api",
            }
            for name in AI_PROVIDERS
        ],
        # Models this house used lately, newest first: the picker offers them before the catalogue.
        "recent": [
            {"provider": provider, "model": model}
            for provider, model in db.execute(
                select(Usage.provider, Usage.model)
                .where(Usage.created_at >= utcnow() - timedelta(days=90))
                .group_by(Usage.provider, Usage.model)
                .order_by(func.max(Usage.created_at).desc())
                .limit(30)
            )
        ],
    }


@router.put("/{purpose}")
def save(purpose: Purpose, body: Assignment, actor=Depends(require_admin), db=Depends(get_db)):
    # Serialize role edits so independent saves cannot erase another assignment.
    db.scalar(select(Integration).where(Integration.name == "budgets").with_for_update())
    connection = db.get(Integration, body.provider)
    if not connection or not connection.enabled:
        raise HTTPException(409, "Enable this provider connection first")
    catalog = db.get(Integration, "catalog." + body.provider)
    item = next(
        (x for x in (catalog.config.get("items", []) if catalog else []) if x["id"] == body.model), None
    )
    # A model id the list doesn't have yet (a new release) may be typed; the test round after
    # saving shows whether the provider accepts it.
    # The same shapes the sign-in bridges accept (claude_bridge / codex_bridge), so a saved id
    # can't fail later only because of its characters.
    shape = {"claude_code": r"(?!-)[\w.\[\]:-]{1,128}", "codex": r"(?!-)[\w./:-]{1,128}"}.get(
        (connection.config or {}).get("auth_mode"), r"(?!-)[\w.\[\]:/~-]{1,160}"
    )
    if not re.fullmatch(shape, body.model):
        raise HTTPException(422, "Type a model id without spaces, e.g. claude-opus-5-5")
    if body.provider == "openrouter" and item and item.get("tool_support") != "declared":
        raise HTTPException(422, "Select a model that advertises tool support")
    mode = connection.config.get("auth_mode", "api")
    if item and catalog.config.get("auth_mode", "api") != mode:
        raise HTTPException(409, "Refresh models for the current connection method")
    native = connection.config.get("auth_mode") in {"codex", "claude_code"}
    # OpenAI and Anthropic keys take an effort on their thinking models (a model without one
    # refuses it in the test round after saving); OpenRouter says per model.
    if (
        body.reasoning_effort
        and not native
        and body.provider not in {"openai", "anthropic"}
        and (body.provider != "openrouter" or "reasoning" not in (item or {}).get("supported_parameters", []))
    ):
        raise HTTPException(422, "This model does not advertise configurable reasoning effort")
    row = db.scalar(select(Integration).where(Integration.name == "assistant.roles").with_for_update())
    if not row:
        row = Integration(
            name="assistant.roles", enabled=True, config={p: assignment(db, p) for p in PROFILES}
        )
        db.add(row)
    row.config = {**row.config, purpose: body.model_dump()}
    emit(
        db,
        "audit.assistant_assignment_updated",
        {"purpose": purpose, "provider": body.provider, "model": body.model},
        actor.id,
    )
    db.commit()
    return {"status": "completed", "purpose": purpose, **body.model_dump()}


@router.post("/{purpose}/test")
def try_assignment(purpose: Purpose, actor=Depends(require_admin), db=Depends(get_db)):
    """One real short round with this assistant's own model, effort, instructions and tools.
    Nothing runs: a proposed tool call counts as an answer. Normal budgets apply."""
    from .assistant import (
        SPACE_POLICY,
        audit_request,
        provider_error,
        provider_round,
        record_usage_evidence,
        reserve,
        system_prompt,
        tool_registry,
        tool_schemas,
    )

    selected = assignment(db, purpose)
    schemas = tool_schemas(tool_registry(purpose))
    policy = SPACE_POLICY if purpose == "personal_space" else system_prompt(purpose)
    cfg = {"_purpose": purpose, "_assignment": selected, "_policy": policy}
    messages = [
        {
            "role": "user",
            "content": "HouseOS check after an administrator saved your model: say in one short "
            "sentence that you are ready. Do not call a tool.",
        }
    ]
    usage_id, started = None, time.monotonic()
    try:
        if not selected.get("model"):
            raise HTTPException(409, "Choose a model first")
        usage_id = reserve(db, actor, selected["provider"], cfg, messages, schemas)
        cfg["_timeout_seconds"] = (
            60  # a local model may first have to load into memory
            if selected["provider"] == "compatible"
            else {"medium": 45, "high": 60}.get(cfg.get("reasoning_effort"), 20)
        )
        reply, calls, _, reported = provider_round(selected["provider"], cfg, messages, schemas)
        if not (reply or calls):
            raise HTTPException(502, "The model returned an empty answer")
        result = {"status": "verified", "reply": reply[:300], "tools": len(schemas)}
    except Exception as exc:
        db.rollback()
        reported, detail = None, getattr(exc, "detail", None)
        code = getattr(getattr(exc, "response", None), "status_code", None) or getattr(
            exc, "status_code", None
        )
        said = provider_error(exc, cfg.get("api_key"))
        result = {
            "status": "failed",
            "message": detail.get("message", detail.get("code"))
            if isinstance(detail, dict)
            else detail
            or (
                "The model was still loading. Press Save and test again."
                if "Timeout" in type(exc).__name__ and selected["provider"] == "compatible"
                else "The provider did not answer in time"
                if "Timeout" in type(exc).__name__
                else f"The provider answered HTTP {code}" + (f": {said}" if said else "")
                if code
                else "The provider could not complete this reply"
            ),
        }
    seconds = round(time.monotonic() - started, 1)
    if usage_id:
        usage = db.get(Usage, usage_id)
        usage.status = "completed" if result["status"] == "verified" else "failed"
        usage.latency_ms = int(seconds * 1000)
        record_usage_evidence(db, usage, cfg, reported)
        audit_request(db, usage)
    result |= {
        "purpose": purpose,
        "provider": selected["provider"],
        "model": selected.get("model"),
        "seconds": seconds,
    }
    # tested() reads the latest of these for this provider and model.
    db.add(
        Operation(
            actor_id=actor.id,
            kind="provider.probe",
            state=result["status"],
            data={"provider": selected["provider"], "model": selected.get("model"), "purpose": purpose},
            result=result,
        )
    )
    db.commit()
    return result
