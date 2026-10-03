"""Provider catalogs, one-step connection and the budgeted harmless structured-tool probe."""

import json
import re
import time
from datetime import timedelta
from typing import Literal
import httpx
from .config import settings
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import Input, require_admin, refresh_actor
from .db import get_db, utcnow
from .models import Integration, Operation, User, Usage
from .integrations import AI_PROVIDERS, NATIVE_MODES, check_config, endpoint_url, integration_config
from .events import emit

router = APIRouter(prefix="/admin/providers", tags=["provider-checks"])
# Embedding, speech, image and moderation models cannot hold a conversation.
NOT_CHAT = re.compile(
    r"embed|tts|whisper|transcribe|dall-e|image|moderation|realtime|audio|sora|davinci|babbage|search"
)
# Known good small models tried first, by provider or subscription; else the first tool-capable model.
RECOMMENDED = {
    "openrouter": ("openai/gpt-5-mini", "anthropic/claude-haiku-4.5", "openai/gpt-4.1-mini"),
    "openai": ("gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini"),
    "anthropic": ("claude-haiku", "claude-sonnet"),
    "claude_code": ("sonnet",),
}


def configured(db, name):
    if name not in AI_PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    cfg = integration_config(db, name, include_disabled=True)
    if cfg.get("auth_mode") in {"codex", "claude_code"} or name == "compatible":
        return cfg
    if not cfg.get("api_key"):
        raise HTTPException(409, "Configure this provider first")
    return cfg


@router.get("/{name}/models")
def models(name: str, actor=Depends(require_admin), db=Depends(get_db)):
    if name not in AI_PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    row = db.get(Integration, "catalog." + name)
    return row.config if row else {"items": [], "status": "not_refreshed"}


class CatalogRefresh(Input):
    api_key: str | None = Field(default=None, max_length=8192)
    auth_mode: str | None = None
    base_url: str | None = Field(default=None, max_length=1024)


def normalized_model(item):
    from decimal import Decimal, InvalidOperation, ROUND_CEILING

    identity = item.get("id")
    if not isinstance(identity, str) or not 0 < len(identity) <= 160:
        return None
    result = {
        "id": identity,
        "name": str(item.get("name", item.get("display_name", identity)))[:160],
        "tool_support": "declared"
        if "tools" in (item.get("supported_parameters") or [])
        else "requires_probe",
        "context_length": item.get("context_length"),
        "supported_parameters": [
            p
            for p in (item.get("supported_parameters") or [])
            if p in {"tools", "reasoning", "reasoning_effort"}
        ],
    }
    prices = {}
    if type(result["context_length"]) is not int or result["context_length"] < 1:
        result["context_length"] = None
    for source, target in [
        ("prompt", "input_microusd_per_million"),
        ("completion", "output_microusd_per_million"),
        ("input_cache_read", "cached_input_microusd_per_million"),
        ("input_cache_write", "cache_write_microusd_per_million"),
        ("request", "request_microusd"),
    ]:
        try:
            price = Decimal(str((item.get("pricing") or {})[source]))
            if price.is_finite() and price >= 0:
                normalized = int(
                    (price * (10**6 if source == "request" else 10**12)).to_integral_value(
                        rounding=ROUND_CEILING
                    )
                )
                if normalized <= 2_000_000_000:
                    prices[target] = normalized
        except (KeyError, InvalidOperation, ValueError, TypeError):
            pass
    result["pricing"] = prices
    return result


@router.post("/{name}/models/refresh")
def refresh(name: str, body: CatalogRefresh | None = None, actor=Depends(require_admin), db=Depends(get_db)):
    if name not in AI_PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    cfg = integration_config(db, name, include_disabled=True)
    mode = (body.auth_mode if body else None) or cfg.get("auth_mode", "api")
    if mode not in {"api", NATIVE_MODES.get(name, "api")}:
        raise HTTPException(422, "Unsupported connection method")
    if mode != "api":
        ensure_native_owner(db, actor, name, claim=False)
        payload = native_request(name, "models")
        raw = payload.get("items", [])

    else:
        key = (body.api_key if body else None) or cfg.get("api_key")
        if key and len(key) > 8192:
            raise HTTPException(422, "API key is too long")
        if not key and name not in {"openrouter", "compatible"}:
            raise HTTPException(409, "Enter an API key first")
        urls = {
            "openai": "https://api.openai.com/v1/models",
            "anthropic": "https://api.anthropic.com/v1/models",
            "openrouter": "https://openrouter.ai/api/v1/models",
        }
        if name == "compatible":
            from .assistant import compatible_base, is_ollama

            try:
                base = (body.base_url if body else None) or cfg.get("base_url", "")
                urls[name] = compatible_base(base) + "/models"
            except ValueError as error:
                raise HTTPException(422, str(error))
        headers = {"Authorization": "Bearer " + key} if key else {}
        if name == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        raw = []
        params = {}
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                for _ in range(50):
                    response = client.get(urls[name], headers=headers, params=params)
                    response.raise_for_status()
                    if len(response.content) > 12 * 1024**2:
                        raise ValueError("Catalog too large")
                    payload = response.json()
                    batch = payload.get("data", [])
                    if not isinstance(batch, list):
                        raise ValueError("Invalid catalog")
                    raw.extend(batch)
                    if len(raw) > 10000:
                        raise ValueError("Catalog limit reached")
                    if name != "anthropic" or not payload.get("has_more"):
                        break
                    cursor = payload.get("last_id")
                    if not cursor or cursor == params.get("after_id"):
                        raise ValueError("Invalid catalog cursor")
                    params = {"after_id": cursor, "limit": 100}
                else:
                    raise ValueError("Catalog pagination limit reached")
                if name == "compatible" and is_ollama(urls[name].removesuffix("/models")):
                    # Ollama's list does not say which models can use tools; each model's details do.
                    root = urls[name].removesuffix("/models").removesuffix("/v1")
                    for item in raw[:15]:  # ponytail: first 15 models only, to bound the wait
                        try:
                            shown = client.post(
                                root + "/api/show", json={"model": item.get("id")}, timeout=3
                            ).json()
                        except (httpx.HTTPError, ValueError, AttributeError):
                            continue
                        if isinstance(shown, dict) and "tools" in (shown.get("capabilities") or []):
                            item["supported_parameters"] = ["tools"]
        except (httpx.HTTPError, ValueError) as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            raise HTTPException(
                502,
                "The provider rejected this API key. Check it and try again."
                if status in {401, 403}
                else "Provider model catalog unavailable; saved selection is unchanged"
                if name != "compatible"
                else "This server answered but has no model list at this address. Check that the address"
                " ends in /v1, for example http://host.docker.internal:11434/v1."
                if status == 404
                else (
                    "Could not reach this server. Check the address and that it is running."
                    + (
                        " If it runs on this computer, it must listen on all addresses"
                        " (Ollama: OLLAMA_HOST=0.0.0.0; LM Studio: turn on Serve on Local Network)"
                        " and the firewall must let Docker reach its port."
                        if settings.storage_container
                        else ""
                    )
                ),
            )
    items = [model for item in raw if isinstance(item, dict) and (model := normalized_model(item))]
    items = list({item["id"]: item for item in items}.values())
    if mode == "api" and name in {"openai", "compatible"}:
        items = [item for item in items if not NOT_CHAT.search(item["id"])]
    actor = refresh_actor(db, actor)
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    row = db.get(Integration, "catalog." + name)
    if not row:
        row = Integration(name="catalog." + name)
        db.add(row)
    row.config = {
        "items": items,
        "auth_mode": mode,
        "observed_at": utcnow().isoformat() + "Z",
        "status": "refreshed",
        "selection_changes": False,
    }
    db.commit()
    return row.config


def recommended(key, items):
    for hint in RECOMMENDED.get(key, ()):
        for item in items:
            if item["id"] == hint or item["id"].startswith(hint + "-"):
                return item["id"]
    capable = [item for item in items if item["tool_support"] == "declared"] or items
    return capable[0]["id"] if capable else None


class Connect(Input):
    auth_mode: Literal["api", "codex", "claude_code"] = "api"
    api_key: str | None = Field(default=None, max_length=8192)
    base_url: str | None = Field(default=None, max_length=1024)


@router.post("/{name}/connect")
def connect(name: str, body: Connect, actor=Depends(require_admin), db=Depends(get_db)):
    """One step after a key, an address or a finished sign-in: choose a model, enable, assign, test."""
    from .assistant import PRICING_KEYS
    from .assistant_profiles import PROFILES, Assignment, save as assign
    from .integrations import IntegrationInput, connected, save_integration

    if body.base_url is not None:
        check_config(name, {"base_url": body.base_url})
    if body.auth_mode != "api" and not native_request(name, "status").get("logged_in"):
        raise HTTPException(409, "Finish signing in first.")
    catalog = refresh(
        name,
        CatalogRefresh(api_key=body.api_key, auth_mode=body.auth_mode, base_url=body.base_url),
        actor,
        db,
    )
    model = recommended(name if body.auth_mode == "api" else body.auth_mode, catalog["items"])
    if not model:
        raise HTTPException(409, "No chat model was found. Load or download a model, then try again.")
    row = db.get(Integration, name)
    config = dict(row.config) if row else {}
    if config.get("model") != model:
        for key in (*PRICING_KEYS, "reasoning_effort"):
            config.pop(key, None)
    # Priced models use the dollar limits; unpriced models and subscriptions count requests.
    config = {
        "daily_budget_microusd": 1_000_000,
        "user_daily_budget_microusd": 250_000,
        "daily_request_limit": 100,
        "user_daily_request_limit": 100,
        **config,
        "auth_mode": body.auth_mode,
        "model": model,
        **({"base_url": endpoint_url(body.base_url, path=True)} if body.base_url else {}),
    }
    save_integration(
        name, IntegrationInput(enabled=True, config=config, secret=body.api_key or None), actor, db
    )
    roles = db.get(Integration, "assistant.roles")
    if not roles or not connected(db.get(Integration, roles.config.get("general", {}).get("provider", ""))):
        try:
            for purpose in PROFILES:
                assign(purpose, Assignment(provider=name, model=model), actor, db)
        except HTTPException:
            db.rollback()
    result = {"status": "connected", "provider": name, "model": model, "tested": None}
    # Self-hosted models and subscriptions cost nothing extra per request, so test them right away.
    if body.auth_mode != "api" or name == "compatible":
        test = confirm(prepare(name, Probe(), actor, db)["confirmation_id"], actor, db)
        result["tested"] = test["status"]
        if test["status"] == "failed":  # why, for the connect dialog
            result |= {"test_code": test["code"], "test_detail": test.get("detail")}
    return result


def configuration_revision(row):
    import hashlib

    # Timestamp alone has second precision on MariaDB and misses rapid configuration edits.
    value = {"config": row.config, "secret_ciphertext": row.encrypted_secret, "enabled": row.enabled}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Probe(Input):
    current_password: str | None = None


@router.post("/{name}/probe/prepare")
def prepare(name: str, body: Probe, actor=Depends(require_admin), db=Depends(get_db)):
    cfg = configured(db, name)
    if not cfg.get("model"):
        raise HTTPException(409, "Select a model first")
    if cfg.get("auth_mode") in {"codex", "claude_code"}:
        ensure_native_owner(db, actor, name)
    row = Operation(
        actor_id=actor.id,
        kind="provider.probe",
        state="needs_confirmation",
        expires_at=utcnow() + timedelta(minutes=2),
        data={
            "provider": name,
            "model": cfg["model"],
            "config_revision": configuration_revision(db.get(Integration, name)),
        },
    )
    db.add(row)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": row.id,
        "preview": {
            "provider": name,
            "model": cfg["model"],
            "requests": 1,
            "billing": "native personal subscription"
            if cfg.get("auth_mode") in {"codex", "claude_code"}
            else "paid API",
            "data": "Synthetic HouseOS tool echo only; no resident content",
            "budget": "Normal daily reservations and limits apply",
        },
    }


@router.post("/probe/confirm/{identity}")
def confirm(identity: str, actor=Depends(require_admin), db=Depends(get_db)):
    from .assistant import reserve, provider_error, provider_round, record_usage_evidence, audit_request

    row = db.scalar(
        select(Operation).where(Operation.id == identity, Operation.actor_id == actor.id).with_for_update()
    )
    if (
        not row
        or row.kind != "provider.probe"
        or row.state != "needs_confirmation"
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(409, "Probe confirmation expired or consumed")
    cfg = configured(db, row.data["provider"])
    if configuration_revision(db.get(Integration, row.data["provider"])) != row.data["config_revision"]:
        raise HTTPException(409, "Provider settings changed; prepare another probe")
    name = row.data["provider"]
    row.state = "executing"
    db.commit()
    messages = [
        {
            "role": "user",
            "content": "This is a synthetic capability test. Call houseos_probe exactly once with echo set to houseos. Do not do anything else.",
        }
    ]
    schemas = [
        {
            "name": "houseos_probe",
            "description": "Harmless synthetic echo; no side effects",
            "parameters": {
                "type": "object",
                "properties": {"echo": {"type": "string", "enum": ["houseos"]}},
                "required": ["echo"],
                "additionalProperties": False,
            },
        }
    ]
    usage_id = None
    started = time.monotonic()
    try:
        approved_revision = row.data["config_revision"]
        usage_id = reserve(db, actor, name, cfg, messages, schemas)
        if name == "compatible":
            cfg["_timeout_seconds"] = 60  # a local model may first have to load into memory
        if configuration_revision(db.get(Integration, name)) != approved_revision:
            usage = db.get(Usage, usage_id)
            usage.status, usage.cost_microusd, usage.reserved_microusd = "cancelled", 0, 0
            record_usage_evidence(db, usage, cfg)
            db.commit()
            raise HTTPException(409, "Provider settings changed; prepare another probe")
        _, calls, _, reported = provider_round(name, cfg, messages, schemas)
        actor = refresh_actor(db, actor)
        if actor.role != "admin":
            raise HTTPException(403, "Administrator authorization changed")
        usage = db.get(Usage, usage_id)
        record_usage_evidence(db, usage, cfg, reported)
        usage.latency_ms = int((time.monotonic() - started) * 1000)
        usage.tool_calls = len(calls)
        audit_request(db, usage)
        passed = (
            len(calls) == 1
            and calls[0].get("name") == "houseos_probe"
            and calls[0].get("args") == {"echo": "houseos"}
        )
        result = {
            "status": "verified" if passed else "unsupported",
            "model": cfg["model"],
            "structured_tool_call": passed,
            "scope": "one synthetic schema; full assistant evaluation remains separate",
        }
    except Exception as exc:
        db.rollback()
        if usage_id:
            usage = db.get(Usage, usage_id)
            if usage.status != "cancelled":
                usage.status = "failed"
            record_usage_evidence(db, usage, cfg)
            audit_request(db, usage)
        said = provider_error(exc, cfg.get("api_key"))
        loading = name == "compatible" and isinstance(exc, (httpx.TimeoutException, TimeoutError))
        result = {
            "status": "failed",
            "code": "PROVIDER_TIMEOUT" if loading else "PROVIDER_PROBE_FAILED",
            "message": "The model was still loading. Run the test again."
            if loading
            else f"The provider said: {said}."
            if said
            else "Check credentials, budget and structured-tool support",
            **({"detail": said} if said else {}),
        }
    row = db.get(Operation, identity)
    row.state = result["status"]
    row.result = result
    emit(
        db,
        "audit.provider_probe",
        {"provider": name, "model": cfg["model"], "status": result["status"]},
        actor.id,
    )
    db.commit()
    return result


def request_helper_update() -> bool:
    """Ask for the AI helpers' clients to be updated now: deploy/update_bridge_clis.py watches
    these files on a native install, and each bridge container checks its own in Docker."""
    for engine in ("claude", "codex"):
        (settings.runtime_root / "run" / f"bridge-update-{engine}").touch()
    return True


@router.post("/helpers/update")
def update_helpers(actor=Depends(require_admin), db=Depends(get_db)):
    """Update the ChatGPT and Claude sign-in clients now instead of waiting for the daily check."""
    request_helper_update()
    emit(db, "audit.helpers_update", {}, actor.id)
    db.commit()
    return {"status": "requested"}


def native_request(name, action, **fields):
    if name == "openai":
        from .codex_client import request
    elif name == "anthropic":
        from .claude_client import request
    else:
        raise HTTPException(404, "No native client for this provider")
    result = request(action, **fields)
    if result.get("error"):
        code = result["error"]
        message = (
            "Sign in to your personal native account in Control Room → AI."
            if code.endswith("SIGN_IN_REQUIRED")
            else "Claude didn't accept that code. Press Cancel sign-in, start again, and paste the code from the new page."
            if code.endswith("LOGIN_CODE_REJECTED")
            else "Sign-in did not finish. Start again and paste the newest code."
            if code.endswith("LOGIN_FAILED")
            else "Paste the code shown after signing in, or a token made by claude setup-token."
            if code.endswith("TOKEN_INVALID")
            else "The native model request timed out. No automatic replay occurred; inspect any earlier operation before retrying."
            if code.endswith("TIMEOUT")
            else "Your native client is busy. Wait for the current request to finish."
            if code.endswith("BUSY")
            else "This model needs a newer Claude Code. HouseOS is updating it now: try again in a few minutes."
            if code.endswith("UPDATE_REQUIRED") and request_helper_update()
            else "This sign-in is not available on this install."
            if code.endswith("UNAVAILABLE")
            else "The sign-in helper could not complete this request. Try again."
        )
        raise HTTPException(503, {"code": code, "message": message})
    return result


def ensure_native_owner(db, actor, name, claim=False):
    if name not in NATIVE_MODES:
        raise HTTPException(404, "No native client for this provider")
    # Serialize the first claim without introducing schema or storing native credentials.
    if claim:
        actor = refresh_actor(db, actor)
        list(db.scalars(select(User).where(User.role == "admin").order_by(User.id).with_for_update()))
        if actor.role != "admin":
            raise HTTPException(403, "Administrator required")
    key = "native.owner." + name
    row = db.get(Integration, key)
    if row and row.config.get("owner_user_id") != actor.id:
        raise HTTPException(
            403,
            "This native profile belongs to another resident. Use your own API connection; native subscriptions are not shared.",
        )
    if claim and not row:
        row = Integration(name=key, enabled=True, config={"owner_user_id": actor.id})
        db.add(row)
    if claim:
        # Release the admin-row locks now: the bridge call that follows can take up to a
        # minute, and holding them made every other admin request (and the sign-in) wait.
        db.commit()
    return row


@router.get("/{name}/native/status")
def native_status(name: str, actor=Depends(require_admin), db=Depends(get_db)):
    ensure_native_owner(db, actor, name)
    try:
        result = native_request(name, "status")
    except HTTPException as error:
        # No bridge on this install (for example Docker without it): a state, not a failure.
        if str(error.detail.get("code", "")).endswith("UNAVAILABLE"):
            return {"status": "unavailable", "logged_in": False}
        raise
    return {**result, "scope": "personal native profile; not shared with residents"}


@router.post("/{name}/native/login")
def native_login(name: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = ensure_native_owner(db, actor, name, claim=True)
    result = native_request(name, "login_start")
    if result.get("login_id"):
        row.config = {**row.config, "login_id": result["login_id"]}
        db.commit()
    emit(db, "audit.native_signin_started", {"provider": name}, actor.id)
    db.commit()
    return result


class NativeCode(Input):
    code: str = Field(min_length=1, max_length=4096)


@router.post("/{name}/native/login/code")
def native_code(name: str, body: NativeCode, actor=Depends(require_admin), db=Depends(get_db)):
    """Finish sign-in with the code from the sign-in page, or a token made by `claude setup-token`."""
    ensure_native_owner(db, actor, name, claim=True)
    code = body.code.strip()
    started = time.monotonic()
    kind = "token" if code.startswith("sk-ant-") else "code"
    print(f"native sign-in {name}: {kind} received ({len(code)} chars)", flush=True)
    try:
        result = (
            native_request(name, "login_token", token=code)
            if kind == "token"
            else native_request(name, "login_code", code=code)
        )
    except HTTPException as exc:
        code_name = exc.detail.get("code") if isinstance(exc.detail, dict) else exc.status_code
        print(
            f"native sign-in {name}: failed {code_name} after {time.monotonic() - started:.1f} s", flush=True
        )
        raise
    print(
        f"native sign-in {name}: {result.get('status')} after {time.monotonic() - started:.1f} s", flush=True
    )
    emit(db, "audit.native_signin_completed", {"provider": name}, actor.id)
    db.commit()
    return result


@router.post("/{name}/native/login/cancel")
def native_cancel(name: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = ensure_native_owner(db, actor, name)
    result = native_request(name, "login_cancel", login_id=row.config.get("login_id", "") if row else "")
    if row:
        row.config = {k: v for k, v in row.config.items() if k != "login_id"}
        db.commit()
    return result


@router.post("/{name}/native/logout")
def native_logout(name: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = ensure_native_owner(db, actor, name)
    result = native_request(name, "logout")
    if row:
        db.delete(row)
    integration = db.get(Integration, name)
    if integration and integration.config.get("auth_mode") in {"codex", "claude_code"}:
        integration.enabled = False
    emit(db, "audit.native_signout", {"provider": name}, actor.id)
    db.commit()
    return result
