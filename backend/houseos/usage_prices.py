"""Real prices for the AI models this house uses, looked up on demand from each model's own
OpenRouter page data (no key, no model call): the price the page shows first, for its default
provider; a model without such a page is skipped. Only models used in the last 30 days or assigned
to an assistant are kept; subscription sign-ins (ChatGPT, Claude) are left out, since what
they cost is the subscription, not tokens. The usage page then estimates what API requests
without a reported cost would have cost."""

import re
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .auth import require_admin
from .db import get_db, utcnow
from .models import Integration, Usage

router = APIRouter(tags=["usage"])
CATALOGUE = "https://openrouter.ai/api/v1/models"
MODEL_PAGE = "https://openrouter.ai/api/v1/models/{id}/endpoints"  # openrouter.ai/<id>, as data
VENDORS = {"openai": "openai/", "anthropic": "anthropic/"}


def slug(model):
    """claude-opus-5-5, anthropic/claude-opus-5.5 and claude-opus-5-5-20260101 all say the same."""
    name = str(model).lower().lstrip("~").split(":")[0].split("/")[-1].replace(".", "-")
    return re.sub(r"-(\d{8}|latest)$", "", name)


def match(provider, model, entries):
    """The OpenRouter entry for one model, or None."""
    if provider == "openrouter":
        exact = entries.get(str(model).lower())
        if exact:
            return exact
    prefix = VENDORS.get(provider, "")
    for identity, entry in entries.items():
        if identity.startswith(prefix) and slug(identity) == slug(model):
            return entry
    return None


def per_million(value):
    try:
        return round(float(value) * 1_000_000, 6)
    except (TypeError, ValueError):
        return None


def wanted(db):
    """(provider, model) pairs used lately or assigned; subscription sign-ins excluded."""
    from .assistant_profiles import PROFILES, assignment
    from .integrations import AI_PROVIDERS

    pairs = set(
        db.execute(
            select(Usage.provider, Usage.model)
            .where(Usage.created_at >= utcnow() - timedelta(days=30))
            .distinct()
        ).all()
    )
    pairs |= {(a["provider"], a["model"]) for a in (assignment(db, p) for p in PROFILES) if a.get("model")}
    subscriptions = {
        name
        for name in AI_PROVIDERS
        if (row := db.get(Integration, name))
        and (row.config or {}).get("auth_mode") in {"codex", "claude_code"}
    }
    return {(p, m) for p, m in pairs if p and m and p not in subscriptions}


def saved(db):
    row = db.get(Integration, "usage.prices")
    return (row.config or {}) if row else {}


@router.post("/admin/usage/prices")
def look_up(actor=Depends(require_admin), db=Depends(get_db)):
    pairs = wanted(db)
    db.commit()  # no connection held while OpenRouter answers
    prices, missing = {}, []
    try:
        with httpx.Client(timeout=15, trust_env=False, headers={"User-Agent": "HouseOS/1"}) as client:
            response = client.get(CATALOGUE)
            response.raise_for_status()
            entries = {str(e.get("id", "")).lower().lstrip("~"): e for e in response.json().get("data", [])}
            for provider, model in sorted(pairs):
                entry = match(provider, model, entries)
                # The model's own page (openrouter.ai/<id>) as data: who serves it, at what price.
                page = client.get(MODEL_PAGE.format(id=str(entry["id"]).lstrip("~"))) if entry else None
                offers = (
                    (page.json().get("data") or {}).get("endpoints") or [] if page and page.is_success else []
                )
                pricing = (offers[0].get("pricing") or {}) if offers else {}
                rates = {
                    "input": per_million(pricing.get("prompt")),
                    "output": per_million(pricing.get("completion")),
                    "cached": per_million(pricing.get("input_cache_read")),
                }
                if rates["input"] is not None and rates["output"] is not None:
                    prices[f"{provider}|{model}"] = {
                        **rates,
                        "matched": entry["id"],
                        "served_by": offers[0].get("provider_name"),
                    }
                else:
                    missing.append({"provider": provider, "model": model})
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "OpenRouter's price pages didn't answer; try again later") from None
    row = db.get(Integration, "usage.prices") or Integration(name="usage.prices", config={}, enabled=True)
    row.config = {"as_of": utcnow().isoformat() + "Z", "source": "OpenRouter model pages", "prices": prices}
    db.add(row)
    db.commit()
    return {"as_of": row.config["as_of"], "priced": len(prices), "missing": missing}


def estimate(row, prices):
    """Micro-dollars one request would have cost at the looked-up price, or None."""
    rate = prices.get(f"{row.provider}|{row.model}")
    if not rate or not (row.input_tokens or row.output_tokens):
        return None
    cached = min(row.cached_tokens or 0, row.input_tokens or 0)
    dollars = (
        ((row.input_tokens or 0) - cached) * rate["input"]
        + cached * (rate["cached"] if rate.get("cached") is not None else rate["input"])
        + (row.output_tokens or 0) * rate["output"]
    ) / 1_000_000
    return round(dollars * 1_000_000)
