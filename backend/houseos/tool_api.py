"""Setup mode's one path over the app's own HTTP API: the routes its screens call, so no drift.

Only the settings routes in ALLOWED, and only for admins: house_api_routes lists them,
house_api_read runs one of their GETs in process (the route's own dependencies and checks run),
and house_api_propose changes nothing: it stores the exact request, the chat shows it on a card,
and the admin's own browser sends it on Confirm, with their session and CSRF token."""

import json
import re
import warnings
from datetime import timedelta
from functools import cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, routing
from fastapi.background import BackgroundTasks
from fastapi.dependencies.utils import request_params_to_args
from fastapi.encoders import jsonable_encoder
from pydantic import Field
from sqlalchemy import select
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import compile_path

from .auth import Input, require_actor, require_admin
from .db import get_db, new_id, utcnow
from .cinema_models import CinemaDevice
from .models import Operation, User

router = APIRouter(prefix="/assistant/proposals", tags=["assistant"])
PREFIX = "/api/v1"
# The settings Nox may read (GET) and propose (the rest): the route's own method and path.
# To add one: a settings route an admin screen calls, plus its GET to read it back. Never a
# two-step prepare/confirm, code changes, backups or restore, shutdown or restarts, sign-in,
# or deleting people or data. Not the access origins or a device's address either: those are
# addresses (ADDRESS), always set on their screen.
ALLOWED = {
    ("GET", "/admin/house-settings"),
    ("PUT", "/admin/house-settings"),
    ("GET", "/admin/users"),
    ("PUT", "/admin/users/{user_id}"),
    ("PUT", "/admin/users/{user_id}/budgets"),
    ("GET", "/auth/invites"),
    ("POST", "/auth/invites"),
    ("DELETE", "/auth/invites/{invite_id}"),
    ("GET", "/admin/integrations"),
    ("PUT", "/admin/integrations/{name}"),  # no secrets or addresses; a new host drops the key
    ("GET", "/admin/access"),
    ("GET", "/admin/assistants"),
    ("PUT", "/admin/assistants/{purpose}"),
    ("GET", "/admin/house-actions"),
    ("PUT", "/admin/house-actions/updates"),
    ("GET", "/admin/audio"),
    ("PUT", "/admin/audio/device"),
    ("GET", "/cinema/devices"),
    ("GET", "/tv"),
    ("PUT", "/tv/{device_id}/film-input"),
    ("GET", "/home"),
    ("PUT", "/home/selection"),
    ("PUT", "/home/{entity_id}/controls"),
    ("GET", "/music/auto"),
    ("PUT", "/music/auto"),
    ("GET", "/files/admin/policy"),
    ("PUT", "/files/admin/policy"),
    ("GET", "/languages"),
}
# Field names that hold a secret: those are pasted on their own screen, never sent through chat.
SECRET = re.compile(r"(?:^|_)(?:api_?key|keys?|token|password|secret|cookie|credentials?)(?:$|_)", re.I)
# Addresses: a new one could send the house's keys, prompts or media to another server.
ADDRESS = re.compile(r"(?:^|_)(?:url|host|hostname|origin|address|endpoint)$", re.I)
ON_SCREEN = re.compile(f"{SECRET.pattern}|{ADDRESS.pattern}", re.I)
# Path ids the card names (the request line shows only the id).
NAMED = {"user_id": User, "device_id": CinemaDevice}
PROPOSAL = "assistant.api_proposal"
TTL = timedelta(minutes=10)


class RouteSearch(Input):
    search: str = Field(default="", max_length=120, description="English words, e.g. 'quiet hours'.")


class ApiRead(Input):
    path: str = Field(min_length=1, max_length=500, description="A GET path, query included: /x?days=7")


class ApiProposal(Input):
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(min_length=1, max_length=500, description="The route's path, query included.")
    body: str = Field(default="", max_length=20000, description='The JSON body as text; "" for none.')
    summary: str = Field(min_length=1, max_length=160, description="One line: what this changes.")


def brief(schema, spec, depth=0):
    """A JSON schema in a few words: {"name": "string ≤80", "hours?": "integer 1..168 =2"}."""
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    if "enum" in schema or "const" in schema:
        return "|".join(map(str, schema.get("enum", [schema.get("const")])))
    options = [s for s in schema.get("anyOf", schema.get("oneOf", [])) if s.get("type") != "null"]
    if options:
        found = [brief(s, spec, depth) for s in options[:3]]
        return " or ".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in found)
    kind = schema.get("type", "any")
    if kind == "object" and schema.get("properties") and depth < 2:
        required = set(schema.get("required", []))
        return {
            name + ("" if name in required else "?"): brief(field, spec, depth + 1)
            for name, field in schema["properties"].items()
            if name != "idempotency_key"  # filled in by propose
        }
    if kind == "array":
        return [brief(schema.get("items", {}), spec, depth + 1)]
    text = kind + (f" ≤{schema['maxLength']}" if "maxLength" in schema else "")
    if "minimum" in schema or "maximum" in schema:
        text += " {}..{}".format(
            *(json.dumps(round(schema[k], 3)) if k in schema else "" for k in ("minimum", "maximum"))
        )
    return text + (f" ={json.dumps(schema['default'])}" if "default" in schema else "")


@cache
def routes():
    """Every /api/v1 route in the app's own order (the order requests are matched in)."""
    from .main import app

    with warnings.catch_warnings():  # a GET+HEAD route's duplicate operation id, harmless here
        warnings.simplefilter("ignore")
        spec = app.openapi()
    rows = []
    for route in routing.iter_route_contexts(app.routes):
        original = route.original_route
        if not isinstance(original, routing.APIRoute) or not route.path.startswith(PREFIX):
            continue
        path = route.path_format.removeprefix(PREFIX)
        regex = compile_path(route.path)[0]
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            op = spec["paths"].get(route.path_format, {}).get(method.lower(), {})
            body_schema = (op.get("requestBody") or {}).get("content", {}).get("application/json")
            doc = (original.description or "").strip().split("\n")[0]
            rows.append(
                {
                    "method": method,
                    "path": path,
                    "summary": " — ".join(filter(None, [op.get("summary", original.name), doc])),
                    "query": {
                        p["name"] + ("" if p.get("required") else "?"): brief(p.get("schema", {}), spec)
                        for p in op.get("parameters", [])
                        if p["in"] == "query"
                    },
                    "body": brief(body_schema["schema"], spec) if body_schema else None,
                    "allowed": (method, path) in ALLOWED,
                    "route": original,
                    "regex": regex,
                }
            )
    return rows


def find(method, target, actor):
    """The route a request to `target` (path?query) reaches, as the app would match it: its row,
    path, path values and query. Only ALLOWED routes, only for admins, only plain paths."""
    require_admin(actor)
    path, _, query = target.strip().partition("?")
    path = "/" + path.strip("/")
    # What the browser sends must be what was checked: no dot segments, escapes or fragments.
    if re.search(r"[^\w.\-/]", path) or {".", ".."} & set(path.split("/")) or re.search(r"[#\\]", query):
        raise HTTPException(422, "A plain path only: no ., .., %, \\, # or spaces")
    path = path.removeprefix(PREFIX) or "/"
    for row in routes():
        match = row["regex"].match(PREFIX + path)
        if match and row["method"] == method:
            if not row["allowed"]:
                raise HTTPException(404, f"{method} {row['path']} is not a setting Nox may use")
            return row, path, match.groupdict(), query
    raise HTTPException(404, f"No {method} route at {path}: search with house_api_routes")


def hidden(value, found=None, names=SECRET):
    """`value` with secret values hidden (they stay on the server); their names go in `found`."""
    found = [] if found is None else found
    if isinstance(value, dict):
        shown = {}
        for key, item in value.items():
            if key != "idempotency_key" and names.search(str(key)) and item is not None:  # "" clears one
                found.append(str(key))
                item = "[hidden]" if item else item
            shown[key] = hidden(item, found, names)
        return shown
    if isinstance(value, list):
        return [hidden(item, found, names) for item in value]
    return value


def trimmed(value, depth=0):
    if isinstance(value, list):
        more = [f"… {len(value) - 20} more (narrow with the query)"] if len(value) > 20 else []
        return [trimmed(item, depth + 1) for item in value[:20]] + more
    if isinstance(value, dict):
        return {k: trimmed(v, depth + 1) for k, v in value.items()} if depth < 5 else "…"
    return value[:500] + "…" if isinstance(value, str) and len(value) > 500 else value


def params(row, path_values, query):
    """Path and query values checked exactly as FastAPI checks a real request."""
    dependant = row["route"].dependant
    found, errors = request_params_to_args(dependant.path_params, path_values)
    values, more = request_params_to_args(dependant.query_params, QueryParams(query))
    if errors or more:
        raise HTTPException(422, "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in errors + more))
    return {**found, **values}


def call_get(row, path, path_values, query, actor, db):
    """The route's endpoint, its declared dependencies supplied through the same checks."""
    dependant = row["route"].dependant
    kwargs = params(row, path_values, query)
    for sub in dependant.dependencies:
        value = db if sub.call is get_db else require_admin(actor) if sub.call is require_admin else actor
        if sub.name:
            kwargs[sub.name] = value
    if dependant.request_param_name:
        from .tool_setup import browser

        kwargs[dependant.request_param_name] = Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": browser(db).url.scheme,
                "path": PREFIX + path,
                "query_string": query.encode(),
                "headers": [],
                "state": {},
            }
        )
    if dependant.response_param_name:
        kwargs[dependant.response_param_name] = Response()
    if dependant.background_tasks_param_name:
        kwargs[dependant.background_tasks_param_name] = BackgroundTasks()  # never run: a read only
    result = row["route"].endpoint(**kwargs)
    if isinstance(result, Response):
        raise HTTPException(415, "This route answers with a file or a stream, not data")
    return jsonable_encoder(result)


def list_routes(body, actor, db):
    require_admin(actor)
    words = [w.rstrip("s") for w in re.findall(r"\w{3,}", body.search.casefold())]
    mine = [row for row in routes() if row["allowed"]]
    if not words:
        areas = {}
        for row in mine:
            area = row["path"].split("/")[2 if row["path"].startswith("/admin/") else 1]
            areas[area] = areas.get(area, 0) + 1
        return {"status": "completed", "areas": areas, "next": "search with a few words"}
    scored = []
    for row in mine:
        text = " ".join([row["method"], row["path"], row["summary"], json.dumps(row["body"])]).casefold()
        if score := sum(word in text for word in words):
            scored.append((-score, row["path"], row))
    return {
        "status": "completed",
        "routes": [
            {k: row[k] for k in ("method", "path", "summary", "query", "body") if row[k]}
            for _, _, row in sorted(scored, key=lambda item: item[:2])[:25]
        ],
    }


def read(body, actor, db):
    try:
        data = call_get(*find("GET", body.path, actor), actor, db)
    except HTTPException as exc:
        db.rollback()
        return {"status": "http_error", "http_status": exc.status_code, "detail": exc.detail}
    db.rollback()  # a read leaves nothing behind
    data = trimmed(hidden(data))
    if len(json.dumps(data, default=str)) > 8000:
        data = {"too_large": True, "keys": list(data)[:40] if isinstance(data, dict) else len(data)}
    return {"status": "completed", "http_status": 200, "data": data}


def lines(value, prefix=""):
    """A body as readable lines: "name: Maison bleue", "quiet.start: 22:00"."""
    if isinstance(value, dict) and value:
        return [line for key, item in value.items() for line in lines(item, f"{prefix}{key}.")]
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return [f"{prefix[:-1]}: {text}" if prefix else text]


def screen_for(path, actor, db):
    """The button to the screen where a secret or an address is set, or a person made admin."""
    from .integrations import AI_PROVIDERS
    from .tool_setup import DIALOGS, TABS, SettingsScreen, open_settings

    name = path.split("/")[3] if path.startswith("/admin/integrations/") else ""
    tab = next((tab for tab in TABS if f"/{tab}" in path), "setup")
    if path.startswith("/files/admin"):
        tab = "storage"
    if name in AI_PROVIDERS or path.startswith("/admin/assistants"):
        tab = "ai"
    return open_settings(SettingsScreen(tab=tab, open=name if name in DIALOGS else None), actor, db)


def propose(body, actor, db):
    from .tool_setup import confirmation

    try:
        row, path, path_values, query = find(body.method, body.path, actor)
        payload = json.loads(body.body) if body.body.strip() else None
    except HTTPException as exc:
        status = {403: "denied", 422: "invalid"}.get(exc.status_code, "not_found")
        return {"status": status, "detail": exc.detail}
    except ValueError as exc:
        return {"status": "invalid", "detail": f"body is not JSON: {exc}"}
    found = []
    hidden(payload, found, ON_SCREEN)
    hidden(dict(QueryParams(query)), found, ON_SCREEN)
    if found:
        return {
            **screen_for(path, actor, db),
            "status": "refused",
            "code": "SECRET_ON_SCREEN",
            "detail": f"{', '.join(found)}: set on its screen by the person, never through chat. Nothing was stored.",
        }
    route = row["route"]
    value = None
    try:
        if route.body_field is None and payload not in (None, {}):
            raise HTTPException(422, "this route takes no body")
        if route.body_field is not None:
            if isinstance(payload, dict) and "idempotency_key" in getattr(
                route.body_field.field_info.annotation, "model_fields", {}
            ):
                payload = {"idempotency_key": new_id(), **payload}
            value, errors = route.body_field.validate(payload, loc=("body",))
            if errors:
                raise HTTPException(
                    422,
                    "; ".join(
                        f"{'.'.join(map(str, e['loc'][1:])) or 'body'}: {e['msg']}" for e in errors[:5]
                    ),
                )
        values = params(row, path_values, query)
    except HTTPException as exc:
        return {"status": "invalid", "detail": exc.detail}
    # One tap must never make someone an admin, turn an account off or end a membership, or turn on
    # deleting files for good: those are done on their own screen.
    person = db.get(User, path_values["user_id"]) if row["path"] == "/admin/users/{user_id}" else None
    if (
        (person and (value.role == "admin" or not value.active or person.role == "admin"))
        or getattr(value, "permanent_delete_enabled", False)
        or values.get("revoke_membership")
    ):
        return {
            **screen_for(path, actor, db),
            "status": "refused",
            "code": "ON_ITS_SCREEN",
            "detail": "Admins, turning accounts off, ending memberships and deleting files for good "
            "are changed on their screen by the person, never from a chat card. Nothing was stored.",
        }
    shown = (
        [line for line in lines(payload) if not line.startswith("idempotency_key:")]
        if payload is not None
        else []
    )
    changed = shown
    if isinstance(payload, dict):
        try:  # what is set now, so the card leads with what changes
            now = set(lines(hidden(call_get(*find("GET", path, actor), actor, db))))
            changed = [line for line in shown if line not in now]
        except HTTPException:
            pass
        db.rollback()
    if body.method in {"PUT", "PATCH"} and shown and not changed:
        return {
            "status": "completed",
            "detail": "Already set that way: nothing would change, nothing was stored.",
        }
    request = f"{body.method} {path}" + (f"?{query}" if query else "")
    names = [
        f"{key} → {item.name}"
        for key, model in NAMED.items()
        if key in path_values and (item := db.get(model, path_values[key]))
    ]
    card = confirmation(
        actor,
        db,
        PROPOSAL,
        {"method": body.method, "path": path, "query": query, "body": payload, "summary": body.summary},
        "Change a setting",
        {
            "route": row["summary"],  # the route's own words lead; Nox's summary is the detail
            "request": request,
            "lines": names + changed,
            "unchanged": len(shown) - len(changed),
            "expires_at": (utcnow() + TTL).isoformat() + "Z",
        },
        ttl=TTL,
        path="/assistant/proposals/",
    )
    return {**card, "detail": body.summary}


def owned(identity, actor, db):
    op = db.scalar(
        select(Operation)
        .where(Operation.id == identity, Operation.actor_id == actor.id, Operation.kind == PROPOSAL)
        .with_for_update()
    )
    if not op:
        raise HTTPException(404, "Proposal not found")
    return op


@router.post("/{identity}/take")
def take(identity: str, actor=Depends(require_actor), db=Depends(get_db)):
    """The stored request, once, to its owner's browser, which sends it with their own session."""
    op = owned(identity, actor, db)
    if op.state != "needs_confirmation" or op.expires_at <= utcnow():
        raise HTTPException(409, "Confirmation expired or consumed")
    op.state = "sent"
    db.commit()
    data = op.data
    return {
        "method": data["method"],
        "path": data["path"] + ("?" + data["query"] if data["query"] else ""),
        "body": data["body"],
    }


class Outcome(Input):
    ok: bool
    status: int = Field(ge=0, le=599)
    detail: str = Field(default="", max_length=300)


@router.post("/{identity}/outcome")
def outcome(identity: str, body: Outcome, actor=Depends(require_actor), db=Depends(get_db)):
    """What the browser got back, so Nox sees it next turn (and verifies by reading back)."""
    op = owned(identity, actor, db)
    if op.state != "sent":
        raise HTTPException(409, "This proposal was not sent")
    op.state = "completed" if body.ok else "failed"
    op.result = body.model_dump()
    db.commit()
    return {"status": op.state}


def resolve_card(card, actor, db):
    """A proposal card as it stands now: waiting, sent, done, refused or expired."""
    op = db.scalar(
        select(Operation).where(
            Operation.id == str(card.get("confirmation_id") or ""),
            Operation.actor_id == actor.id,
            Operation.kind == PROPOSAL,
        )
    )
    if not op:
        return
    state = "expired" if op.state == "needs_confirmation" and op.expires_at <= utcnow() else op.state
    if state == "needs_confirmation":
        return
    card.update(confirmation_id=None, state=state, status=state)
    card["message"] = {
        "completed": "Confirmed: sent from your browser, and done.",
        "failed": str((op.result or {}).get("detail") or "Refused with no reason given."),
        "sent": "Sent from your browser; its answer wasn't recorded.",
        "expired": "Not confirmed in time; nothing was sent.",
    }[state]


TOOLS = {
    "house_api_routes": (
        RouteSearch,
        "Find the house settings you may change (the routes their screens use): method, path, "
        "summary, query and body fields (? = optional). Without words: the areas.",
        list_routes,
    ),
    "house_api_read": (
        ApiRead,
        "Run one of those settings' GET routes: current values. Secrets come back hidden.",
        read,
    ),
    "house_api_propose": (
        ApiProposal,
        "Propose one settings change (POST/PUT/PATCH/DELETE): stored exactly as given and shown on a "
        "card; the person's own browser sends it when they confirm. A PUT body is usually whole: read "
        "the current values first and change only what was asked.",
        propose,
    ),
}
