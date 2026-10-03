"""The addresses HouseOS may be opened at.

Seeded from HOUSEOS_ALLOWED_ORIGINS; the first admin's address is adopted when the setup
code is accepted, and admins add or remove addresses in Control Room → Access. Every
state-changing request must come from one of these origins; every request's Host must
belong to one of them (DNS-rebinding guard), except while the house has no account yet.
"""

import time
from urllib.parse import urlsplit

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select

from .auth import Input, require_admin
from .config import settings
from .db import SessionLocal, get_db
from .events import emit
from .models import Integration, User

router = APIRouter(tags=["access"])
DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize(value: str) -> str | None:
    """`https://House.lan:443/` → `https://house.lan`; None when it is not an origin."""
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname or parts.username or parts.password:
        return None
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        return None
    host = parts.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{host}" + (f":{port}" if port and port != DEFAULT_PORTS[parts.scheme] else "")


def configured() -> list[str]:
    origins, bad = [], []
    for value in filter(None, (v.strip() for v in settings.allowed_origins.split(","))):
        (origins if normalize(value) else bad).append(normalize(value) or value)
    if bad:
        raise SystemExit(
            "HOUSEOS_ALLOWED_ORIGINS must list full addresses such as https://house.lan; not: "
            + ", ".join(bad)
        )
    return origins


ENV_ORIGINS = frozenset(configured())
_cache = {"at": 0.0, "origins": frozenset(), "open": True}


def state() -> dict:
    """Trusted origins and whether the house still waits for its first account (5 s cache)."""
    if time.monotonic() - _cache["at"] > 5:
        # Checked again in 5 s even when the database is down; the last list stays in force.
        _cache["at"], _cache["origins"] = time.monotonic(), _cache["origins"] or ENV_ORIGINS
        with SessionLocal() as db:
            row = db.get(Integration, "access")
            saved = (row.config or {}).get("origins", []) if row else []
            _cache["origins"] = ENV_ORIGINS | frozenset(saved) | announced(db)
            _cache["open"] = _cache["open"] and not db.scalar(select(func.count()).select_from(User))
    return _cache


def announced(db) -> frozenset:
    """The address the media relay announces on the Wi-Fi (https://houseos.local:8443): it
    names this house, so it is trusted without an admin adding it."""
    from .discovery import ANNOUNCED

    row = db.get(Integration, ANNOUNCED)
    origin = normalize((row.config or {}).get("origin") or "") if row else None
    return frozenset([origin] if origin else [])


def forget():
    _cache["at"] = 0.0


def host_allowed(host: str, origins) -> bool:
    try:
        name = urlsplit("//" + (host or "")).hostname
    except ValueError:
        return False
    return name == "testserver" or any(urlsplit(o).hostname == name for o in origins)


def own_origin(request: Request) -> str | None:
    return normalize(f"{request.url.scheme}://{request.headers.get('host', '')}")


def rejection(kind: str, value: str) -> str:
    where = value or "an unknown address"
    return (
        f"HouseOS was opened at {where}, which is not one of its trusted addresses yet. "
        "An administrator can add it in Control Room → Access, or list it in HOUSEOS_ALLOWED_ORIGINS."
        if kind == "origin"
        else f"HouseOS does not answer to the name {where}. An administrator can add this address in "
        "Control Room → Access, or list it in HOUSEOS_ALLOWED_ORIGINS."
    )


def adopt(db, origin: str, actor_id: str | None = None):
    row = db.get(Integration, "access") or Integration(name="access", config={}, enabled=True)
    saved = list((row.config or {}).get("origins", []))
    if origin not in saved and origin not in ENV_ORIGINS:
        row.config = {**(row.config or {}), "origins": saved + [origin]}
        db.add(row)
        emit(db, "admin.access_added", {"origin": origin}, actor_id)
    forget()


class NewOrigin(Input):
    origin: str = Field(min_length=8, max_length=200)


@router.get("/admin/access")
def list_access(request: Request, actor=Depends(require_admin), db=Depends(get_db)):
    row = db.get(Integration, "access")
    saved = (row.config or {}).get("origins", []) if row else []
    return {
        "current": own_origin(request),
        "secure": request.url.scheme == "https",
        "origins": [{"origin": o, "source": "settings"} for o in sorted(ENV_ORIGINS)]
        + [{"origin": o, "source": "house"} for o in saved if o not in ENV_ORIGINS]
        + [{"origin": o, "source": "wifi"} for o in announced(db) - ENV_ORIGINS - set(saved)],
    }


@router.post("/admin/access")
def add_access(body: NewOrigin, actor=Depends(require_admin), db=Depends(get_db)):
    origin = normalize(body.origin)
    if not origin:
        raise HTTPException(422, "Use a full address such as https://house.example.lan")
    adopt(db, origin, actor.id)
    db.commit()
    return {"origin": origin}


@router.delete("/admin/access")
def remove_access(origin: str, request: Request, actor=Depends(require_admin), db=Depends(get_db)):
    origin = normalize(origin) or origin
    if origin == request.headers.get("origin"):
        raise HTTPException(409, "You are using this address right now; remove it from another one")
    if origin in ENV_ORIGINS:
        raise HTTPException(409, "This address comes from HOUSEOS_ALLOWED_ORIGINS; change it there")
    if origin in announced(db):
        raise HTTPException(
            409, "HouseOS announces this address on the Wi-Fi; HOUSEOS_MDNS_NAME turns it off"
        )
    row = db.get(Integration, "access")
    saved = (row.config or {}).get("origins", []) if row else []
    if origin not in saved:
        raise HTTPException(404, "Unknown address")
    row.config = {**row.config, "origins": [o for o in saved if o != origin]}
    emit(db, "admin.access_removed", {"origin": origin}, actor.id)
    db.commit()
    forget()
    return {"removed": origin}


HTTPS_ROOT = Path("/https/caddy/pki/authorities/local/root.crt")  # the Docker HTTPS door's CA


@router.get("/access/certificate")
def certificate():
    """The built-in HTTPS door's root certificate, to install on phones once (public data)."""
    try:
        pem = HTTPS_ROOT.read_bytes()
    except OSError:
        raise HTTPException(404, "This install has no built-in HTTPS certificate")
    return Response(
        pem,
        media_type="application/x-x509-ca-cert",
        headers={"Content-Disposition": 'attachment; filename="houseos-root.crt"'},
    )
