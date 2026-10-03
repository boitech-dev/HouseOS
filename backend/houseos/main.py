import importlib
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

from . import __version__
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from . import access, custom, custom_admin  # noqa: F401 (custom_admin adds the install routes)
from .config import settings

app = FastAPI(title="HouseOS", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)


@app.on_event("startup")
def restartable():
    import threading

    from .cinema_explore import warm
    from .events import restart_on_request

    restart_on_request("api")
    threading.Thread(target=warm, name="warm-indexes", daemon=True).start()
    threading.Thread(target=start_custom, name="custom-integrations", daemon=True).start()


def start_custom():
    """Your own integrations that are turned on (custom.py); one that fails only says why."""
    from . import custom
    from .db import SessionLocal

    try:
        with SessionLocal() as db:
            custom.start(db)
    except Exception as error:
        logging.getLogger("houseos").warning("custom integrations didn't start: %s", type(error).__name__)


def refused(request: Request, message: str, status: int):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=status)
    from html import escape

    return HTMLResponse(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>HouseOS</title><body style="font:16px system-ui;max-width:36rem;margin:3rem auto;padding:0 1rem">'
        f"<h1>Almost there</h1><p>{escape(message)}</p></body>",
        status_code=status,
    )


@app.middleware("http")
async def boundaries(request: Request, call_next):
    import time

    try:
        # Fresh (5 s cache): no hop through the request threads, which a busy page fills up.
        fresh = time.monotonic() - access._cache["at"] <= 5
        trust = access._cache if fresh else await run_in_threadpool(access.state)
    except SQLAlchemyError:
        trust = access._cache
    host = request.headers.get("host", "")
    tls_ask = request.url.path == "/api/v1/access/tls-ask"  # Caddy asks as api:8990
    if not trust["open"] and not tls_ask and not access.host_allowed(host, trust["origins"]):
        return refused(request, access.rejection("host", host), 400)
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if (settings.runtime_root / "run/shutdown.json").exists() and not request.url.path.startswith(
            "/api/v1/admin/services/shutdown/"
        ):
            return JSONResponse(
                {"detail": "HouseOS is shutting down; reopen its desktop launcher to restart"},
                status_code=503,
            )
        origin = access.normalize(request.headers.get("origin") or "")
        first_account = trust["open"] and request.url.path == "/api/v1/auth/bootstrap" and origin
        # An integration's key routes (shortcuts, scripts, helpers) send its key and no cookie or
        # Origin: no browser can forge that header across sites, and those routes take only the key.
        custom_key = (
            "authorization" in request.headers
            and request.url.path.startswith("/api/v1/custom/")
            and custom.key_route(request.url.path)
        )
        if origin not in trust["origins"] and not first_account and not custom_key:
            return refused(request, access.rejection("origin", request.headers.get("origin", "")), 403)
    try:
        response = await call_next(request)
    except Exception as exc:
        # Upstream URLs, credentials and request bodies never enter exception logs.
        import uuid
        from .events import failure_site

        correlation = str(uuid.uuid4())
        logging.getLogger("houseos").error("request_failed correlation=%s %s", correlation, failure_site(exc))
        try:
            from .db import SessionLocal
            from .events import emit

            with SessionLocal() as db:
                emit(
                    db,
                    "audit.application_error",
                    {
                        "correlation_id": correlation,
                        "status": "failed",
                        "code": "UNEXPECTED_FAILURE",
                        # what was asked (no query, no body) and where it broke, for the log
                        "request": f"{request.method} {request.url.path.removeprefix('/api/v1')}"[:120],
                        "where": failure_site(exc)[:120],
                    },
                )
                db.commit()
        except Exception:
            pass  # The original error must remain reportable during a database outage.
        response = JSONResponse(
            {"detail": "Operation unavailable", "correlation_id": correlation}, status_code=500
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self'; media-src 'self' blob: https:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        {"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]},
        status_code=422,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    from .events import failure_site

    logging.getLogger("houseos").error(
        "database_operation_failed %s %s %s", request.method, request.url.path, failure_site(exc)
    )
    return JSONResponse(
        {"detail": "Database operation unavailable; retry after refreshing state"}, status_code=503
    )


for name in (
    "access",
    "auth",
    "core",
    "integrations",
    "household",
    "files",
    "music",
    "cinema",
    "assistant",
    "notifications",
    "control_room",
    "audio_admin",
    "provider_checks",
    "backup_policy",
    "account",
    "house_settings",
    "cinema_watchlist",
    "personal_space",
    "assistant_profiles",
    "storage_admin",
    "stats",
    "house_setup",
    "discovery",
    "home",
    "house_actions",
    "tv_remote",
    "activity",
    "languages",
    "remix",  # before themes: /themes/remix/<id> is the editor's, not a theme called "remix"
    "themes",
    "usage_prices",
    "games",
    "tool_api",  # Nox's proposals: the browser takes and reports them
    "tool_code",  # Control Room → Changes
    "custom",  # your own integrations: Capture's share buttons
):
    module = importlib.import_module("houseos." + name)
    app.include_router(module.router, prefix="/api/v1")
app.include_router(custom.admin, prefix="/api/v1")  # installing them (custom_admin.py)
custom.DISPATCH.overrides = app.dependency_overrides  # one set of overrides for the house and them
app.mount("/api/v1/custom", custom.DISPATCH)  # their own routes, before the screens' catch-all
app.include_router(importlib.import_module("houseos.themes").files)  # installed themes' CSS, fonts, art
app.include_router(importlib.import_module("houseos.games").files)  # the emulator, fetched when needed


@app.post("/capture/share", include_in_schema=False)
def unsupported_share():
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HouseOS Capture</title><h1>Nothing was saved</h1><p>Open and install HouseOS first, or select your files manually in Capture. This browser is not yet ready to receive shared files.</p><a href="/capture">Open Capture</a></html>',
        status_code=409,
        headers={"Cache-Control": "no-store"},
    )


PLAYER_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' blob: 'wasm-unsafe-eval' 'unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob: data:; "
    "font-src 'self' data:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str, request: Request):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    root = settings.frontend_dist.resolve()
    if path not in {"", "index.html", "sw.js"}:
        target = (root / path).resolve()
        if target.is_relative_to(root) and target.is_file():
            return FileResponse(target)
        # No files under assets-legacy/ (Legacy is a theme): a stale request gets a 404, not the page.
        if path.startswith(("assets/", "assets-legacy/", "art/")):
            return JSONResponse({"detail": "Not found"}, status_code=404)
    name = "sw.js" if path == "sw.js" else "index.html"
    if (root / name).is_file():
        headers = {"Cache-Control": "no-cache"}
        # The emulator's page only: WebAssembly, its cores' generated code, workers made from blobs.
        if path.startswith("games/play/"):
            headers["Content-Security-Policy"] = PLAYER_CSP
        return FileResponse(root / name, headers=headers)
    return JSONResponse({"application": "HouseOS", "status": "frontend_build_pending"}, status_code=503)
