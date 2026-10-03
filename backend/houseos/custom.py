"""Your own integrations: code a household adds for its own devices and habits, without changing
HouseOS. Each one is a folder (installed from a git repository in Control Room → Integrations,
see custom_admin.py) with a `houseos-integration.json` manifest and a Python entry file whose
`setup(house)` returns what it adds:

- routes, served at /api/v1/custom/<id>/…, with the house's sign-in or one of the integration's
  own keys (for shortcuts, scripts and helpers on other computers, which can't sign in);
- Nox tools, in the bundles it names, with confirmation cards when they act on something;
- share buttons on Capture, for links that match its pattern (Android's share sheet);
- a card in Control Room: status lines and how-to steps it reports.

`House` below is everything an integration may rely on; the rest of HouseOS can change. The code
runs inside the app with its full rights, so it is installed only by an administrator, pinned to
a commit, and off until turned on. docs/CUSTOM-INTEGRATIONS.md is the guide."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import logging
import re
import secrets
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from .atomic import write_json
from .auth import Actor, Input, delegated_user, require_actor, require_admin, user_permissions
from .config import settings
from .db import get_db
from .events import emit
from .models import Integration

log = logging.getLogger("houseos")
MANIFEST = "houseos-integration.json"
ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")  # the row is "custom:<id>", 40 characters at most
ROW = "custom:"
LOCK = threading.RLock()
LOADED: dict[str, "Loaded"] = {}
PROBLEMS: dict[str, str] = {}  # id -> why it didn't load, in a sentence


def code_root():
    """Where installed integrations live (one folder each); replaced only by an install or update."""
    return settings.runtime_root / "integrations"


def state_root():
    return settings.runtime_root / "run" / "custom"


def problem(status, code, message):
    return HTTPException(status, {"code": code, "message": message})


# ---------- what an integration adds ----------
@dataclass
class Share:
    """A button on Capture for shared text matching `match` (a regular expression JavaScript and
    Python both read). Pressing it POSTs {field: the text} to the integration's `path`."""

    id: str
    label: str | dict
    match: str
    path: str
    field: str = "url"


@dataclass
class Parts:
    router: APIRouter | None = None
    # Path prefixes (under /api/v1/custom/<id>) that accept a key without the browser's Origin.
    key_routes: tuple[str, ...] = ()
    # name -> (input model, description, handler(body, actor, db)); names start with "<id>_".
    tools: dict = field(default_factory=dict)
    bundles: tuple[str, ...] = ("general",)
    # action -> handler(data, actor, db), for the cards House.ask_first prepares.
    confirm: dict = field(default_factory=dict)
    shares: list[Share] = field(default_factory=list)
    # (actor, db) -> {"lines": [{"label", "value", "tone"}], "help": [str, …]}
    card: Callable | None = None


@dataclass
class Loaded:
    id: str
    manifest: dict
    parts: Parts
    app: FastAPI
    modules: list[str]


# ---------- the integration's side: House ----------
class HomeAssistant:
    """The house's Home Assistant, as HouseOS already uses it: only the entities an administrator
    lets HouseOS see (Smart home) count as exposed."""

    def __init__(self, db):
        from . import home

        self._home = home
        self.base, self.headers, self.config = home.connection(db)

    def states(self):
        return self._home.ha(self.base, self.headers, "/api/states")

    def state(self, entity_id):
        return self._home.read_state(self.base, self.headers, entity_id)

    def exposed(self, entity_id):
        try:
            self._home.exposed_domain(self.config, entity_id)
            return True
        except HTTPException:
            return False

    def call(self, domain, service, data, timeout=10):
        if not re.fullmatch(r"[a-z0-9_]{1,60}", domain) or not re.fullmatch(r"[a-z0-9_]{1,60}", service):
            raise problem(422, "CUSTOM_HA_SERVICE", "That isn't a Home Assistant service name.")
        entity = (data or {}).get("entity_id")
        if entity and not self.exposed(entity):
            raise problem(403, "HOME_NOT_EXPOSED", "HouseOS isn't allowed to control this device.")
        return self._home.ha(
            self.base,
            self.headers,
            f"/api/services/{domain}/{service}",
            method="POST",
            payload=data,
            timeout=timeout,
        )


def house_db():
    """The house's database session, as the app itself gets it (with its overrides)."""
    override = DISPATCH.overrides.get(get_db)
    value = (override or get_db)()
    if inspect.isgenerator(value):
        yield from value
    else:
        yield value


def signed_in(request: Request, db=Depends(house_db)):
    return require_actor(request, db)


class House:
    """What HouseOS gives an integration. Dependencies go in FastAPI routes; the rest are plain
    calls. This is the stable surface: an integration should need nothing else from HouseOS."""

    get_db = staticmethod(house_db)
    signed_in = staticmethod(signed_in)
    Input = Input  # request bodies: unknown fields are refused

    def __init__(self, integration_id):
        self.id = integration_id
        self.folder = state_root() / integration_id / "data"
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)

    # who is asking
    def key_only(self, request: Request, db=Depends(house_db)):
        """For key routes: the administrator who created the key sent, while the key and their
        account hold. Never the browser's sign-in."""
        return key_actor(self.id, db, bearer(request))

    def key_or_signed_in(self, request: Request, db=Depends(house_db)):
        """The key when one is sent (those requests skipped the Origin check), else the sign-in."""
        if request.headers.get("authorization") is not None:
            return key_actor(self.id, db, bearer(request))
        return require_actor(request, db)

    @staticmethod
    def allowed(actor, *permissions):
        """Administrators, or anyone with one of these permissions (e.g. "home.control")."""
        if actor.role != "admin" and not set(permissions) & set(actor.permissions):
            raise HTTPException(403, "Permission denied")

    # what it can use
    @staticmethod
    def home_assistant(db):
        """The house's Home Assistant (raises a sentence when it isn't connected)."""
        return HomeAssistant(db)

    def record(self, db, event, payload, actor=None):
        """A line in the house's activity diary (no private content)."""
        emit(db, f"custom.{self.id}.{event}"[:120], payload, actor.id if actor else None)

    def ask_first(self, actor, db, action, data, label, preview):
        """A Nox confirmation card; when it is confirmed, Parts.confirm[action] runs."""
        from .tool_setup import confirmation

        return confirmation(actor, db, f"custom.{self.id}.{action}", data, label, preview)

    @staticmethod
    def problem(status, code, message):
        """An error a person can act on: {"code", "message"}."""
        return problem(status, code, message)


# ---------- keys ----------
def keys_file(integration_id):
    folder = state_root() / integration_id
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder / "keys.json"


def keys(integration_id):
    try:
        return json.loads(keys_file(integration_id).read_text())
    except (OSError, ValueError):
        return []


def digest(key):
    return hashlib.sha256(key.encode()).hexdigest()


def bearer(request):
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value[:7].lower() == "bearer " else None


def key_actor(integration_id, db, key):
    refused = problem(401, "CUSTOM_KEY_REFUSED", "This key isn't valid any more.")
    if not key:
        raise refused
    found = next(
        (k for k in keys(integration_id) if secrets.compare_digest(digest(key), k.get("hash", ""))), None
    )
    user = delegated_user(db, found.get("user_id")) if found else None
    if not user or user.role != "admin":
        raise refused
    return Actor(user.id, user.name, user.role, user_permissions(user), None)


def create_key(integration_id, name, actor):
    key = f"hos_{integration_id}_" + secrets.token_urlsafe(32)
    entry = {
        "id": secrets.token_hex(6),
        "name": name,
        "hash": digest(key),
        "user_id": actor.id,
        "by": actor.name,
        "created_at": time.time(),
    }
    write_json(keys_file(integration_id), [*keys(integration_id), entry])
    return key, entry


def remove_key(integration_id, key_id):
    left = [k for k in keys(integration_id) if k.get("id") != key_id]
    write_json(keys_file(integration_id), left)


def public_keys(integration_id):
    return [{k: v for k, v in entry.items() if k != "hash"} for entry in keys(integration_id)]


# ---------- loading ----------
def read_manifest(folder: Path):
    """The manifest, checked; raises ValueError with a sentence."""
    try:
        data = json.loads((folder / MANIFEST).read_text())
    except (OSError, ValueError):
        raise ValueError(f"No readable {MANIFEST} at the top of the repository.") from None
    if not isinstance(data, dict) or not ID.match(str(data.get("id", ""))):
        raise ValueError("Its id must be lowercase letters, digits or _ (2–32, starting with a letter).")
    entry = str(data.get("entry") or "integration.py")
    if "/" in entry or "\\" in entry or not entry.endswith(".py") or not (folder / entry).is_file():
        raise ValueError(f"Its entry file ({entry}) is missing.")
    return {
        "id": data["id"],
        "name": str(data.get("name") or data["id"])[:60],
        "version": str(data.get("version") or "")[:30],
        "description": str(data.get("description") or "")[:300],
        "entry": entry,
    }


def forget_modules(integration_id):
    prefix = f"houseos_custom_{integration_id}"
    for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
        del sys.modules[name]


def check_parts(integration_id, parts):
    if not isinstance(parts, Parts):
        raise ValueError("setup(house) must return houseos.custom.Parts.")
    for name in parts.tools:
        if not name.startswith(integration_id + "_"):
            raise ValueError(f"Its Nox tool {name} must start with {integration_id}_.")
    for prefix in parts.key_routes:
        if not prefix.startswith("/") or prefix == "/":
            raise ValueError("Each key route must be a path under the integration, like /show.")
    for share in parts.shares:
        re.compile(share.match)
        if not share.path.startswith("/"):
            raise ValueError("A share button's path must start with /.")


def load(integration_id):
    """Import an installed integration and serve it. Returns None, or why it didn't load."""
    folder = code_root() / integration_id
    with LOCK:
        unload(integration_id)
        try:
            manifest = read_manifest(folder)
            if manifest["id"] != integration_id:
                raise ValueError("Its manifest names another id.")
            package = f"houseos_custom_{integration_id}"
            spec = importlib.util.spec_from_file_location(
                package, folder / manifest["entry"], submodule_search_locations=[str(folder)]
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[package] = module
            spec.loader.exec_module(module)
            parts = module.setup(House(integration_id))
            check_parts(integration_id, parts)
        except Exception as error:  # its code, not ours: say why, keep the house running
            forget_modules(integration_id)
            PROBLEMS[integration_id] = f"{type(error).__name__}: {error}"[:300]
            log.warning("custom integration %s didn't load: %s", integration_id, PROBLEMS[integration_id])
            return PROBLEMS[integration_id]
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        if parts.router is not None:
            app.include_router(parts.router)
        modules = [n for n in sys.modules if n == package or n.startswith(package + ".")]
        LOADED[integration_id] = Loaded(integration_id, manifest, parts, app, modules)
        PROBLEMS.pop(integration_id, None)
        return None


def unload(integration_id):
    with LOCK:
        LOADED.pop(integration_id, None)
        PROBLEMS.pop(integration_id, None)
        forget_modules(integration_id)


def installed(db):
    rows = db.scalars(select(Integration).where(Integration.name.like(ROW + "%")))
    return {row.name[len(ROW) :]: row for row in rows}


def start(db):
    """At startup: load every integration that is turned on."""
    for integration_id, row in installed(db).items():
        if row.enabled:
            load(integration_id)


# ---------- serving ----------
class Dispatch:
    """/api/v1/custom/<id>/… → that integration's own app, while it is loaded."""

    def __init__(self):
        self.overrides: dict = {}  # the app's dependency overrides (main.py), for house_db

    async def __call__(self, scope, receive, send):
        path = scope["path"]
        root = scope.get("root_path", "")
        if root and path.startswith(root):
            path = path[len(root) :]
        path = path.removeprefix("/api/v1/custom")
        integration_id, _, rest = path.lstrip("/").partition("/")
        loaded = LOADED.get(integration_id)
        if scope["type"] != "http" or not loaded:
            response = JSONResponse({"detail": "Not found"}, status_code=404)
            return await response(scope, receive, send)
        child = {**scope, "path": "/" + rest, "raw_path": quote("/" + rest).encode(), "root_path": ""}
        await loaded.app(child, receive, send)


DISPATCH = Dispatch()


def key_route(path):
    """Whether this /api/v1/custom path is one its integration opens to keys (Origin skipped)."""
    integration_id, _, rest = path.removeprefix("/api/v1/custom/").partition("/")
    loaded = LOADED.get(integration_id)
    rest = "/" + rest
    return bool(loaded) and any(
        rest == prefix or rest.startswith(prefix.rstrip("/") + "/") for prefix in loaded.parts.key_routes
    )


# ---------- Nox ----------
def tools(context):
    """The tools turned-on integrations add to this bundle of Nox's."""
    found = {}
    for loaded in list(LOADED.values()):
        if context in loaded.parts.bundles:
            found.update(loaded.parts.tools)
    return found


def confirm(row, actor, db):
    """A confirmed card from House.ask_first: run the integration's handler once."""
    from .db import utcnow

    _, integration_id, action = (row.kind.split(".", 2) + ["", ""])[:3]
    loaded = LOADED.get(integration_id)
    handler = loaded.parts.confirm.get(action) if loaded else None
    if row.state != "needs_confirmation" or row.expires_at <= utcnow() or not handler:
        raise HTTPException(409, "Confirmation expired or consumed")
    row.state = "completed"
    db.commit()  # one confirmation acts at most once
    return handler(row.data, actor, db)


# ---------- what people see ----------
router = APIRouter(prefix="/custom-integrations", tags=["custom"])


@router.get("/shares")
def shares(actor: Actor = Depends(require_actor)):
    """Capture's buttons for shared links, from the integrations turned on."""
    return {
        "items": [
            {"integration": loaded.id, **share.__dict__}
            for loaded in list(LOADED.values())
            for share in loaded.parts.shares
        ]
    }


def card(loaded, actor, db):
    if not loaded or not loaded.parts.card:
        return None
    try:
        reply = loaded.parts.card(actor, db) or {}
        return {"lines": list(reply.get("lines") or [])[:20], "help": list(reply.get("help") or [])[:20]}
    except Exception as error:
        return {
            "lines": [
                {"label": "Status", "value": f"{type(error).__name__}: {error}"[:200], "tone": "danger"}
            ]
        }


def describe(integration_id, row, actor, db):
    loaded = LOADED.get(integration_id)
    config = row.config or {}
    parts = loaded.parts if loaded else None
    return {
        "id": integration_id,
        "enabled": row.enabled,
        "loaded": bool(loaded),
        "problem": PROBLEMS.get(integration_id),
        "manifest": config.get("manifest") or {},
        "source": {k: v for k, v in (config.get("source") or {}).items() if k != "token"},
        "has_token": bool(row.encrypted_secret),
        "installed_at": config.get("installed_at"),
        "updated_at": config.get("updated_at"),
        "adds": {
            "routes": bool(parts and parts.router),
            "tools": sorted(parts.tools) if parts else [],
            "shares": [s.id for s in parts.shares] if parts else [],
            "card": bool(parts and parts.card),
        },
        "keys": public_keys(integration_id),
        "card": card(loaded, actor, db),
    }


class Enabled(BaseModel):
    enabled: bool


class KeyName(Input):
    name: str = Field(min_length=1, max_length=60)


admin = APIRouter(prefix="/admin/custom-integrations", tags=["custom"])


@admin.get("")
def list_installed(actor: Actor = Depends(require_admin), db=Depends(get_db)):
    return {"items": [describe(i, row, actor, db) for i, row in sorted(installed(db).items())]}


def row_or_404(db, integration_id):
    row = db.get(Integration, ROW + integration_id) if ID.match(integration_id) else None
    if not row:
        raise problem(404, "CUSTOM_UNKNOWN", "No integration by that name is installed.")
    return row


@admin.put("/{integration_id}/enabled")
def set_enabled(
    integration_id: str, body: Enabled, actor: Actor = Depends(require_admin), db=Depends(get_db)
):
    row = row_or_404(db, integration_id)
    failed = load(integration_id) if body.enabled else unload(integration_id)
    row.enabled = body.enabled and not failed
    emit(db, "audit.custom.enabled", {"id": integration_id, "enabled": row.enabled}, actor.id)
    db.commit()
    if failed:
        raise problem(422, "CUSTOM_LOAD_FAILED", "It didn't start: " + failed)
    return describe(integration_id, row, actor, db)


@admin.post("/{integration_id}/keys")
def new_key(integration_id: str, body: KeyName, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    row_or_404(db, integration_id)
    key, entry = create_key(integration_id, body.name.strip(), actor)
    emit(db, "audit.custom.key", {"id": integration_id, "action": "created", "name": entry["name"]}, actor.id)
    db.commit()
    return {"key": key, "id": entry["id"]}


@admin.delete("/{integration_id}/keys/{key_id}")
def delete_key(integration_id: str, key_id: str, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    row_or_404(db, integration_id)
    remove_key(integration_id, key_id)
    emit(db, "audit.custom.key", {"id": integration_id, "action": "removed"}, actor.id)
    db.commit()
    return {"removed": key_id}


def remove_files(integration_id):
    unload(integration_id)
    shutil.rmtree(code_root() / integration_id, ignore_errors=True)
    shutil.rmtree(state_root() / integration_id, ignore_errors=True)
