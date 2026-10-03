import ipaddress
import json
import re
import socket
import ssl
from collections import Counter
from urllib.parse import urlparse
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import Input, require_admin
from .config import settings
from .db import get_db
from .models import Integration
from .events import emit

router = APIRouter(prefix="/admin/integrations", tags=["integrations"])
# AI connections, in the order Nox falls back to when no assistant model is assigned.
AI_PROVIDERS = ("openrouter", "compatible", "anthropic", "openai")
# Subscription sign-in through a pre-built bridge, per provider; every AI provider also takes "api".
NATIVE_MODES = {"openai": "codex", "anthropic": "claude_code"}
ENDPOINTS = {"jellyfin", "comet", "home_assistant", "compatible"}
# Default address and the read-only check behind "Test" for each household service.
LOCAL_TESTS = {
    "jellyfin": ("http://127.0.0.1:8096", "/Users"),
    "comet": ("http://127.0.0.1:8767", "/manifest.json"),
    "home_assistant": ("http://127.0.0.1:8123", "/api/"),
}
NAMES = {
    *AI_PROVIDERS,
    "real_debrid",
    "jellyfin",
    "comet",
    "cinemeta",
    "stream_addon",  # a Stremio add-on link the admin pastes; none is built in
    "opensubtitles",
    "cast",
    "home_assistant",
    "music",
    "budgets",
}
CONFIG_KEYS = {
    "base_url",
    "model",
    "daily_budget_microusd",
    "user_daily_budget_microusd",
    "input_microusd_per_million",
    "output_microusd_per_million",
    "cached_input_microusd_per_million",
    "cache_write_microusd_per_million",
    "max_output_tokens",
    "budget_warning_percent",
    "pricing_as_of",
    "pricing_source",
    "user_id",
    "device_id",
    "host",
    "port",
    "receiver_id",
    "sink",
    "entitlement_confirmed",
    "torrent_player",
    "external_fetch_verified",
    "currency",
    "subtitle_language",
    "language",
    "client_id",
    "receiver_base_url",
    "username",
    "user_agent",
    "auth_mode",
    "owner_user_id",
    "daily_request_limit",
    "user_daily_request_limit",
    "request_microusd",
    "reasoning_effort",
    "default_provider",
    "domains",
    "hidden",
    "shown",
    "curated",
    "panel_hidden",
}
# Home Assistant's exposure policy: the only list values, each item a domain or entity id.
LIST_KEYS = {
    "domains": r"[a-z0-9_]{1,40}",
    "hidden": r"[a-z0-9_]{1,40}\.[a-z0-9_]{1,200}",
    "shown": r"[a-z0-9_]{1,40}\.[a-z0-9_]{1,200}",
    # A control taken off a device's panel: "<entity id>:<control>".
    "panel_hidden": r"[a-z0-9_]{1,40}\.[a-z0-9_]{1,200}:[a-z_]{2,40}",
}


def integration_config(db, name, include_disabled=False):
    row = db.get(Integration, name)
    if not row or (not row.enabled and not include_disabled):
        return {}
    result = dict(row.config)
    result["enabled"] = row.enabled
    if row.encrypted_secret:
        if not settings.encryption_key:
            raise HTTPException(503, "Integration key store is unavailable")
        try:
            secret = json.loads(
                Fernet(settings.encryption_key.encode()).decrypt(row.encrypted_secret.encode())
            )
        except (InvalidToken, ValueError):
            raise HTTPException(503, "Integration key store requires recovery")
        result.update(secret)
    return result


def connected(row):
    """An enabled AI connection with its credential: a key, a keyless self-hosted server or a signed-in owner."""
    if not row or not row.enabled:
        return False
    if row.config.get("auth_mode", "api") != "api":
        return bool(row.config.get("owner_user_id"))
    return bool(row.encrypted_secret or (row.name == "compatible" and row.config.get("base_url")))


def endpoint(name, config):
    """Where a key for `name` goes: scheme, host and port of its address (its default when unset)."""
    u = urlparse(str(config.get("base_url") or LOCAL_TESTS.get(name, ("",))[0]).strip())
    try:
        port = u.port or {"http": 80, "https": 443}.get(u.scheme)
    except ValueError:
        port = None
    return u.scheme, u.hostname, port


def endpoint_url(value, *, path=False, resolve=False):
    """A service address typed by an admin: http(s), any host name or IP, no credentials or query.

    `resolve` re-checks where a host name points right before a request is made.
    """
    value = str(value).strip().rstrip("/")
    u = urlparse(value)
    try:
        port = u.port
    except ValueError:
        raise ValueError("Enter a valid port number")
    if u.scheme not in {"http", "https"} or not u.hostname:
        raise ValueError("Enter an address starting with http:// or https://")
    if u.username or u.password or u.params or u.query or u.fragment:
        raise ValueError("Remove any user name, password, ? or # part from the address")
    if u.path and not path:
        raise ValueError("Enter the address without a path")
    addresses = [u.hostname]
    if resolve:
        try:
            addresses = [
                info[4][0] for info in socket.getaddrinfo(u.hostname, port or 443, type=socket.SOCK_STREAM)
            ]
        except OSError:
            # Docker's network has no mDNS, so .local names only resolve on the host itself.
            hint = (
                ". Names ending in .local don't work from inside Docker: use the IP address."
                if settings.storage_container and u.hostname.endswith(".local")
                else ""
            )
            raise ValueError("This address could not be found" + hint)
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            ip = None
        # In a container, loopback is the container itself, not the server running it.
        if settings.storage_container and (address == "localhost" or (ip and ip.is_loopback)):
            raise ValueError("Inside Docker, use host.docker.internal or the server's LAN address")
        if ip and (ip.is_link_local or ip.is_multicast or ip.is_unspecified):
            raise ValueError("This address is not allowed")
    return value


def bad_certificate(error):
    """True when an https request failed because the server's certificate isn't trusted here."""
    while error:
        if isinstance(error, ssl.SSLCertVerificationError):
            return True
        error = error.__cause__ or error.__context__
    return False


class IntegrationInput(Input):
    enabled: bool = False
    config: dict = Field(default_factory=dict)
    secret: str | None = Field(default=None, max_length=8192)
    current_password: str | None = Field(default=None, max_length=256)


def check_config(name, config):
    if not set(config) <= CONFIG_KEYS:
        raise HTTPException(422, "Unsupported configuration field")
    if "reasoning_effort" in config and config["reasoning_effort"] not in {"low", "medium", "high"}:
        raise HTTPException(422, "Unsupported reasoning effort")
    if "default_provider" in config and (name != "budgets" or config["default_provider"] not in AI_PROVIDERS):
        raise HTTPException(422, "Unsupported default provider")
    for k, v in config.items():
        if k in LIST_KEYS and (
            name != "home_assistant"
            or not isinstance(v, list)
            or len(v) > 500
            or not all(isinstance(x, str) and re.fullmatch(LIST_KEYS[k], x) for x in v)
        ):
            raise HTTPException(422, "Unsupported Home Assistant device list")
        if isinstance(v, dict) or (isinstance(v, list) and k not in LIST_KEYS):
            raise HTTPException(422, "Configuration values must be scalar")
        if isinstance(v, str) and len(v) > 1024:
            raise HTTPException(422, "Configuration text is too long")
        if "microusd" in k and (not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 2_000_000_000):
            raise HTTPException(422, "Budget and pricing must be nonnegative integer micro-USD")
        if k in {"daily_request_limit", "user_daily_request_limit"} and (
            type(v) is not int or not 1 <= v <= 10000
        ):
            raise HTTPException(422, "Daily request limits must be between 1 and 10000")
        if k == "budget_warning_percent" and (type(v) is not int or not 1 <= v <= 100):
            raise HTTPException(422, "Budget warning percentage must be between 1 and 100")
        if k == "max_output_tokens" and (type(v) is not int or not 1 <= v <= 4096):
            raise HTTPException(422, "Output limit must be between 1 and 4096 tokens")
    if "base_url" in config:
        if name not in ENDPOINTS:
            raise HTTPException(422, "This integration has no configurable address")
        try:
            endpoint_url(config["base_url"], path=name == "compatible")
        except ValueError as error:
            raise HTTPException(422, str(error))
    if "host" in config and name != "cast":
        raise HTTPException(422, "Host is only configurable for an approved Cast device")
    if "receiver_base_url" in config:
        from .music_outputs import relay_base_url

        expected = relay_base_url()  # configured, else the address a running relay reports
        if not expected or config["receiver_base_url"] != expected:
            raise HTTPException(422, "Use the approved media relay address")
    if name == "cast" and "host" in config:
        try:
            ip = ipaddress.ip_address(config["host"])
        except ValueError:
            raise HTTPException(422, "Cast host must be a LAN address")
        # Without an approved household range, any private LAN address (never loopback/link-local).
        outside = (
            ip not in ipaddress.ip_network(settings.cast_lan_cidr)
            if settings.cast_lan_cidr
            else not ip.is_private or ip.is_loopback or ip.is_link_local
        )
        if outside or ip.is_multicast or ip.is_unspecified:
            raise HTTPException(422, "Cast host must be on the approved household LAN")


@router.get("")
def list_integrations(actor=Depends(require_admin), db=Depends(get_db)):
    rows = {x.name: x for x in db.scalars(select(Integration))}
    return [
        {
            "name": name,
            "enabled": bool(rows.get(name) and rows[name].enabled),
            "configured": bool(rows.get(name)),
            "has_secret": bool(rows.get(name) and rows[name].encrypted_secret),
            "config": rows[name].config if name in rows else {},
            "status": "configured_unverified" if rows.get(name) and rows[name].enabled else "disabled",
        }
        for name in sorted(NAMES)
    ]


@router.put("/{name}")
def save_integration(name: str, body: IntegrationInput, actor=Depends(require_admin), db=Depends(get_db)):
    if name not in NAMES:
        raise HTTPException(404, "Unknown integration")
    check_config(name, body.config)
    if body.config.get("auth_mode", "api") not in {"api", NATIVE_MODES.get(name, "api")}:
        raise HTTPException(422, "Unsupported sign-in method for this provider")
    if body.config.get("auth_mode") in {"codex", "claude_code"}:
        from .provider_checks import ensure_native_owner

        ensure_native_owner(db, actor, name, claim=True)
        body.config["owner_user_id"] = actor.id
        body.config.setdefault("daily_request_limit", 100)
        body.config.setdefault("user_daily_request_limit", 100)
    else:
        body.config.pop("owner_user_id", None)
    if name == "openrouter" and body.config.get("model"):
        catalog = db.get(Integration, "catalog.openrouter")
        selected = next(
            (
                item
                for item in (catalog.config.get("items", []) if catalog else [])
                if item["id"] == body.config["model"]
            ),
            None,
        )
        if body.config.get("reasoning_effort") and (
            not selected or "reasoning" not in selected.get("supported_parameters", [])
        ):
            raise HTTPException(
                422, "Refresh the model catalog and select a model supporting reasoning effort"
            )
        from .assistant import PRICING_KEYS

        for key in PRICING_KEYS:
            body.config.pop(key, None)
        if selected and selected.get("pricing"):
            body.config.update(selected["pricing"])
            body.config["pricing_as_of"] = catalog.config.get("observed_at", "")
            body.config["pricing_source"] = "https://openrouter.ai/api/v1/models"
    row = db.get(Integration, name)
    if not row:
        row = Integration(name=name, config={})
        db.add(row)
    new, old = endpoint(name, body.config), endpoint(name, row.config)
    if new != old:
        emit(db, "audit.integration_endpoint_changed", {"name": name, "host": new[1]}, actor.id)
        row.encrypted_secret = ""  # a key never follows a new host: it is pasted again for it
    if body.secret is not None:
        if not settings.encryption_key:
            raise HTTPException(503, "Integration key store is unavailable")
        secret = {"api_key": body.secret, "token": body.secret}
        if name == "stream_addon" and body.secret:
            from .cinema_sources import configured_base
            from .playback import MediaError

            # Stremio's "Install" button gives the same link as stremio://.
            link = re.sub(r"^stremio://", "https://", body.secret.strip(), flags=re.I)
            try:
                configured_base({**body.config, "manifest_url": link})
            except MediaError as error:
                raise HTTPException(422, error.message) from None
            secret = {"manifest_url": link}
        row.encrypted_secret = (
            Fernet(settings.encryption_key.encode()).encrypt(json.dumps(secret).encode()).decode()
            if body.secret
            else ""
        )
    if name == "stream_addon" and body.config.get("torrent_player") is True:
        from .cinema_adapters import torrent_player_ready

        if not torrent_player_ready():
            raise HTTPException(
                422,
                "The torrent player isn't installed yet. Docker: ./houseos.sh torrents on. "
                "Linux: sudo python3 docs/native/setup_torrent_engine.py. Then save again.",
            )
    row.config, row.enabled = body.config, body.enabled
    emit(db, "audit.integration_updated", {"name": name, "enabled": body.enabled}, actor.id)
    db.commit()
    return {"status": "completed", "name": name, "verified": False}


@router.post("/{name}/test")
def test_integration(name: str, actor=Depends(require_admin), db=Depends(get_db)):
    cfg = integration_config(db, name)
    if not cfg:
        return {"status": "not_configured", "name": name}
    if cfg.get("auth_mode") in {"codex", "claude_code"}:
        from .provider_checks import ensure_native_owner, native_request

        ensure_native_owner(db, actor, name)
        return {
            **native_request(name, "status"),
            "scope": "Native authentication status; model inference not tested",
        }
    if name == "stream_addon":
        from .cinema_sources import addon_request, configured_base
        from .playback import MediaError

        try:
            base, _ = configured_base(cfg)
            result = addon_request(base + "/manifest.json", urlparse(base).netloc)
            manifest = json.loads(result.get("body", "{}"))
            status = "reachable" if result["status"] == 200 and manifest.get("id") else "upstream_error"
        except (MediaError, ValueError):
            status = "unreachable"
        return {"status": status, "name": name, "scope": "Configured addon reachability; playback unverified"}
    urls = {
        "openai": "https://api.openai.com/v1/models",
        "anthropic": "https://api.anthropic.com/v1/models",
        "openrouter": "https://openrouter.ai/api/v1/key",
        "real_debrid": "https://api.real-debrid.com/rest/1.0/user",
        "cinemeta": "https://v3-cinemeta.strem.io/manifest.json",
    }
    headers = {}
    if cfg.get("api_key"):
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    if name == "anthropic":
        headers = {"x-api-key": cfg.get("api_key", ""), "anthropic-version": "2023-06-01"}
    if name == "jellyfin":
        headers = {
            "Authorization": 'MediaBrowser Client="HouseOS", Device="HouseOS", DeviceId="houseos", Version="1.0.0", Token="'
            + cfg.get("api_key", "")
            + '"',
            "X-Emby-Token": cfg.get("api_key", ""),  # Emby ignores the MediaBrowser header
        }
    if name == "home_assistant":
        headers = {"Authorization": "Bearer " + cfg.get("token", "")}
    if name in LOCAL_TESTS:
        default, path = LOCAL_TESTS[name]
        try:
            urls[name] = endpoint_url(cfg.get("base_url", default), resolve=True) + path
        except ValueError as error:
            return {"status": "invalid_address", "name": name, "message": str(error)}
    if name not in urls:
        return {"status": "unverified", "name": name, "reason": "Use the component-specific diagnostic"}
    result = {"name": name, "scope": "read-only API reachability; playback unverified"}
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.get(urls[name], headers=headers)
        status = (
            "reachable"
            if response.is_success
            else "authentication_failed"
            if response.status_code in {401, 403}
            else "upstream_error"
        )
        if name == "jellyfin" and response.is_success:
            # An authenticated list proves the key works and lets the admin pick whose library to show.
            result["users"] = [{"id": u["Id"], "name": u["Name"]} for u in response.json()[:100]]
        if name == "home_assistant" and response.is_success:
            # The TVs it can switch on, turn up or change input on: the admin picks one.
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                states = client.get(urls[name].removesuffix("/api/") + "/api/states", headers=headers).json()
            result["players"] = sorted(
                (
                    {
                        "id": e["entity_id"],
                        "name": (e.get("attributes") or {}).get("friendly_name") or e["entity_id"],
                    }
                    for e in states
                    if str(e.get("entity_id", "")).startswith("media_player.")
                ),
                key=lambda player: player["name"].casefold(),
            )[:100]
            # How many devices of each kind it has, to choose what HouseOS may control.
            kinds = Counter(str(e.get("entity_id", "")).split(".")[0] for e in states)
            result["domains"] = dict(sorted(kinds.items())[:100])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        status = "unreachable"
        if bad_certificate(error):
            service = {"jellyfin": "Jellyfin", "home_assistant": "Home Assistant"}.get(name, "This service")
            result["message"] = (
                f"{service}'s certificate isn't valid for this address: use the name on its "
                "certificate, or its http:// address on your network."
            )
    emit(db, "audit.integration_test", {"name": name, "status": status}, actor.id)
    db.commit()
    return {**result, "status": status}
