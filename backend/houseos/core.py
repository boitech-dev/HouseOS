import json
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select, or_, text, delete, func, and_
from . import __version__
from .auth import require_actor, require_admin, require_permission, Input, digest, DELEGABLE, account_usable
from .db import get_db, SessionLocal, utcnow
from .models import User, Event, SessionToken, Integration, Usage, Operation, Record, Job
from .config import settings
from .events import emit

router = APIRouter(tags=["core"])


class Preferences(Input):
    language: str = Field(default="en", pattern="^(en|fr|es)$")
    motion: str = Field(default="subtle", pattern="^(still|subtle|full)$")
    timezone: str = "UTC"  # GET /preferences shows the house setting instead
    notifications: bool = False
    time_display: str = Field(default="24h", pattern="^(12h|24h)$")
    sounds: bool = False
    theme: str = Field(default="", pattern="^$|^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)  # "" = the house's
    scheme: str = Field(default="", pattern="^(|dark|light|device)$")  # "" = the theme's own
    seen_release: str = Field(default="", pattern=r"^$|^\d{1,2}\.\d{1,2}$")  # "What's new" shown up to this
    onboarded: str = Field(default="", pattern="^(|admin|resident|guest)$")  # their welcome, done once
    tour_seen: bool = False  # took Nox's tour of the house (else a dot on Nox asks for it)


# ponytail: presence lives in this API process (one process); lost on restart, refilled in 2 s.
PRESENT: dict[str, float] = {}


@router.get("/people")
def people(actor=Depends(require_actor), db=Depends(get_db)):
    """Residents, their avatar, and whether HouseOS is open on one of their devices."""
    import time

    require_permission(actor, "household.read")
    return [
        {
            "id": u.id,
            "name": u.name,
            "avatar": (u.preferences or {}).get("avatar", "crest"),
            "home": time.monotonic() - PRESENT.get(u.id, -1e9) < 30,
        }
        for u in db.scalars(
            select(User).where(
                User.active.is_(True), or_(User.expires_at.is_(None), User.expires_at > utcnow())
            )
        )
    ]


@router.get("/preferences")
def preferences(actor=Depends(require_actor), db=Depends(get_db)):
    from .house_settings import resident_defaults

    return {
        **Preferences().model_dump(),
        **resident_defaults(db, actor.role),
        **db.get(User, actor.id).preferences,
    }


@router.put("/preferences")
def save_preferences(body: Preferences, actor=Depends(require_actor), db=Depends(get_db)):
    try:
        ZoneInfo(body.timezone)
    except Exception:
        raise HTTPException(422, "Unknown timezone")
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    user.preferences = {**user.preferences, **body.model_dump(exclude_unset=True)}
    emit(db, "preferences.updated", {}, actor.id)
    db.commit()
    return user.preferences


@router.get("/events")
def events(request: Request, actor=Depends(require_actor), db=Depends(get_db)):
    try:
        # A fresh connection starts at the newest event; only reconnects replay what they missed.
        after = int(request.headers["last-event-id"]) if "last-event-id" in request.headers else None
    except ValueError:
        raise HTTPException(400, "Invalid event cursor")
    token_hash = digest(request.cookies.get("houseos_session", ""))

    def poll(cursor):
        # Release the database connection before yielding to a slow/disconnected client.
        with SessionLocal() as db:
            session = db.get(SessionToken, token_hash)
            user = db.get(User, actor.id)
            revoked = not session or session.expires_at <= utcnow() or not account_usable(user)
            messages = []
            if cursor is None:
                cursor = db.scalar(select(func.coalesce(func.max(Event.id), 0)))
            elif not revoked:
                q = select(Event).where(
                    Event.id > cursor,
                    or_(
                        Event.user_id == actor.id,
                        # House-wide changes reach everyone; audit notes stay out of the stream.
                        and_(Event.user_id.is_(None), Event.topic.notlike("audit.%")),
                    ),
                )
                if user.role == "guest":
                    q = q.where(or_(Event.user_id == actor.id, Event.topic.like("music.%")))
                for row in db.scalars(q.order_by(Event.id).limit(100)):
                    cursor = row.id
                    messages.append(
                        f"id: {row.id}\nevent: change\ndata: {json.dumps({'topic': row.topic, 'payload': row.payload})}\n\n"
                    )
        return revoked, cursor, messages

    async def stream():
        # Async so an open tab holds a worker thread only during each short poll, not the sleep.
        import asyncio
        from starlette.concurrency import run_in_threadpool
        from sqlalchemy.exc import SQLAlchemyError

        import time

        cursor = after
        for _ in range(120):
            PRESENT[actor.id] = time.monotonic()
            try:
                revoked, cursor, messages = await run_in_threadpool(poll, cursor)
            except SQLAlchemyError:
                yield "event: unavailable\ndata: {}\n\n"
                return
            if revoked:
                yield "event: revoked\ndata: {}\n\n"
                return
            for message in messages:
                yield message
            # The id keeps the browser's Last-Event-ID current even when nothing changed.
            yield f": heartbeat\nid: {cursor}\n\n"
            await asyncio.sleep(2)

    # The sign-in check's connection goes back to the pool: a stream lasts minutes, and every
    # open tab would otherwise keep one of the pool's connections the whole time.
    db.close()
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "application": "HouseOS", "version": __version__}


@router.get("/access/tls-ask")
def tls_ask(domain: str = ""):
    """The HTTPS door (Caddy's on-demand TLS) asks before it makes a certificate for a name: yes
    while the house waits for its first account, then only for its trusted addresses. Exempt from
    the host check (Caddy asks as api:8990)."""
    from . import access

    trust = access.state()
    if trust["open"] or access.host_allowed(domain, trust["origins"]):
        return {"status": "ok"}
    raise HTTPException(403, "Not one of this house's addresses")


@router.get("/admin/health")
def admin_health(actor=Depends(require_admin), db=Depends(get_db)):
    import shutil
    import subprocess

    checks = [
        {
            "component": "database",
            "status": "ok",
            "evidence": "Query succeeded",
            "observed_at": utcnow().isoformat() + "Z",
        }
    ]
    db.execute(text("SELECT 1"))
    from .files import storage_check

    try:
        valid = bool(storage_check())  # the same check every write makes
    except HTTPException:
        valid = False
    try:
        disk = shutil.disk_usage(settings.data_root.parent)
        checks.append(
            {
                "component": "storage",
                "status": "ok" if valid else "blocked",
                "free_bytes": disk.free,
                "evidence": "Expected filesystem mounted" if valid else "Mount identity mismatch",
            }
        )
    except OSError:
        checks.append({"component": "storage", "status": "unavailable"})
    for name in ["real_debrid", "stream_addon", "jellyfin", "cast"]:
        row = db.get(Integration, name)
        if row and row.enabled:  # what is not set up is listed in Setup, not as a problem here
            checks.append({"component": name, "status": "configured_unverified"})
    marker = db.get(Integration, "worker_heartbeat")
    try:
        observed = marker.config["observed_at"]
        fresh = utcnow() - datetime.fromisoformat(observed).replace(tzinfo=None) < timedelta(seconds=30)
        checks.append(
            {"component": "music_worker", "status": "ok" if fresh else "stale", "observed_at": observed}
        )
    except (AttributeError, KeyError, ValueError):
        checks.append({"component": "music_worker", "status": "unverified"})
    try:
        if not settings.private_remote_url:
            raise OSError("no private remote address configured")
        result = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=3)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        checks.append(
            {
                "component": "tailscale",
                "status": "ok" if data.get("BackendState") == "Running" else "unverified",
                "evidence": data.get("BackendState", "Local status unavailable"),
            }
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass  # no tailnet on this install: nothing to report

    confirmed = (db.get(Integration, "health_confirmed") or Integration(config={})).config or {}
    for check in checks:
        check["tab"] = HEALTH_TABS.get(check["component"], "services")
        mark = confirmed.get(check["component"])
        row = db.get(Integration, check["component"])
        # A person's "it works" holds until that connection's settings change.
        if mark and check["status"] in CONFIRMABLE and not (row and row.updated_at.isoformat() > mark["at"]):
            check |= {"status": "confirmed", "confirmed_by": mark["by"], "observed_at": mark["at"]}
    return {"observed_at": utcnow().isoformat() + "Z", "checks": checks}


HEALTH_TABS = {
    "database": "services",
    "storage": "storage",
    "real_debrid": "integrations",
    "stream_addon": "integrations",
    "jellyfin": "integrations",
    "cast": "devices",
    "music_worker": "services",
    "tailscale": "access",
}
# Only "not proven yet" can be vouched for; measured failures stay failures.
CONFIRMABLE = {"configured_unverified", "unverified"}


@router.post("/admin/health/{component}/confirm")
def confirm_health(component: str, actor=Depends(require_admin), db=Depends(get_db)):
    if component not in HEALTH_TABS:
        raise HTTPException(404, "Unknown check")
    row = db.scalar(select(Integration).where(Integration.name == "health_confirmed").with_for_update())
    if row is None:
        row = Integration(name="health_confirmed", config={}, enabled=True)
        db.add(row)
    row.config = {**(row.config or {}), component: {"at": utcnow().isoformat(), "by": actor.name}}
    emit(db, "audit.health_confirmed", {"component": component}, actor.id)
    db.commit()
    return {"status": "confirmed", "component": component}


@router.get("/admin/recovery")
def recovery_status(actor=Depends(require_admin)):
    return backup_status()


def backup_status() -> dict:
    """The last backup as the backup script reported it (no secrets): when, where, the ones kept."""
    path = settings.runtime_root / "run/backup-status.json"
    try:
        data = json.loads(path.read_text())
        stamp = str(data.get("created_at") or "")
        if len(stamp) == 16 and stamp[8] == "T":  # the backup script writes 20260925T021500Z
            data["created_at"] = (
                f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
            )
        return {
            "container": settings.storage_container,
            **{
                k: data.get(k)
                for k in [
                    "created_at",
                    "location",
                    "restore_verified",
                    "key_recovery_verified",
                    "user_file_backup",
                    "disaster_recovery",
                    "retention",
                    "keep",
                    "backups",
                ]
            },
        }
    except (OSError, ValueError):
        return {"container": settings.storage_container, "created_at": None}


@router.get("/admin/jobs")
def jobs(state: str = "", actor=Depends(require_admin), db=Depends(get_db)):
    q = select(Job)
    if state == "active":  # what the house is waiting on right now
        q = q.where(Job.state.in_(["pending", "running", "unverified"]))
    elif state:
        q = q.where(Job.state == state)
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "state": row.state,
            "attempts": row.attempts,
            "generation": row.generation,
            "next_run": row.next_run.isoformat() + "Z",
            "lease_until": row.lease_until.isoformat() + "Z" if row.lease_until else None,
            "error_code": row.error_code,
            "operation_id": row.payload.get("operation_id"),
        }
        for row in db.scalars(q.order_by(Job.next_run.desc()).limit(100))
    ]


@router.get("/admin/users")
def users(actor=Depends(require_admin), db=Depends(get_db)):
    return [
        {
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "role": u.role,
            "active": u.active,
            "permissions": u.permissions,
            "expires_at": u.expires_at,
            "ai_daily_budgets": u.preferences.get("ai_daily_budgets", {}),
        }
        for u in db.scalars(select(User))
    ]


class UserChange(Input):
    active: bool
    role: str = Field(pattern="^(admin|resident|guest)$")
    permissions: list[str] = Field(default_factory=list)
    current_password: str | None = None


class UserBudget(Input):
    daily_microusd: dict[str, int] = Field(default_factory=dict)
    current_password: str | None = Field(default=None, max_length=256)


@router.put("/admin/users/{user_id}/budgets")
def user_budget(user_id: str, body: UserBudget, actor=Depends(require_admin), db=Depends(get_db)):
    if set(body.daily_microusd) - {"openai", "anthropic", "openrouter"} or any(
        type(v) is not int or not 0 <= v <= 2_000_000_000 for v in body.daily_microusd.values()
    ):
        raise HTTPException(422, "Use nonnegative integer micro-USD limits per provider")
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404, "User not found")
    user.preferences = {**user.preferences, "ai_daily_budgets": body.daily_microusd}
    emit(db, "audit.user_budget_updated", {"user_id": user_id, "status": "completed"}, actor.id)
    db.commit()
    return {
        "daily_microusd": body.daily_microusd,
        "missing_provider": "inherits configured default",
        "zero": "paid requests disabled",
    }


@router.put("/admin/users/{user_id}")
def change_user(user_id: str, body: UserChange, actor=Depends(require_admin), db=Depends(get_db)):
    admins = db.scalars(
        select(User)
        .where(
            User.role == "admin",
            User.active.is_(True),
            or_(User.expires_at.is_(None), User.expires_at > utcnow()),
        )
        .order_by(User.id)
        .with_for_update()
    ).all()
    own = next((u for u in admins if u.id == actor.id), None)
    if not own:
        raise HTTPException(403, "Administrator required")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if body.active and user.username.startswith("deleted-"):
        raise HTTPException(409, "Deleted accounts cannot be reactivated; create a new invitation")
    if body.active and body.role != "admin" and user.expires_at and user.expires_at <= utcnow():
        raise HTTPException(409, "Expired temporary memberships require a new invitation")
    if (
        user.role == "admin"
        and user.active
        and len(admins) <= 1
        and (not body.active or body.role != "admin")
    ):
        raise HTTPException(409, "The last administrator cannot be removed")
    if not set(body.permissions) <= DELEGABLE:
        raise HTTPException(422, "Unsupported permission")
    user.active, user.role, user.permissions = body.active, body.role, body.permissions
    if body.role == "admin":
        user.expires_at = None
    db.execute(delete(SessionToken).where(SessionToken.user_id == user_id))
    emit(db, "audit.user_updated", {"id": user_id, "active": body.active, "role": body.role}, actor.id)
    db.commit()
    return {"status": "completed", "sessions_revoked": True}


@router.post("/admin/users/{user_id}/sign-out")
def sign_out_user(user_id: str, actor=Depends(require_admin), db=Depends(get_db)):
    """End every session of one person (lost phone, shared computer): they sign in again."""
    if user_id == actor.id:
        raise HTTPException(409, "Sign yourself out from Me → Security")
    if not db.get(User, user_id):
        raise HTTPException(404, "User not found")
    ended = db.execute(delete(SessionToken).where(SessionToken.user_id == user_id)).rowcount
    PRESENT.pop(user_id, None)
    emit(db, "audit.user_signed_out", {"id": user_id, "sessions": ended}, actor.id)
    db.commit()
    return {"status": "completed", "sessions_revoked": ended}


@router.get("/usage")
def usage(
    days: int = 7,
    start: str | None = None,
    end: str | None = None,
    user_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    actor=Depends(require_actor),
    db=Depends(get_db),
):
    if actor.role != "admin":
        require_permission(actor, "assistant.use")
        if user_id and user_id != actor.id:
            raise HTTPException(403, "Own usage only")
        user_id = actor.id
    if days not in {1, 7, 30} and not start:
        raise HTTPException(422, "Choose today, 7 days, 30 days or a custom range")
    from .house_settings import get_house_settings

    zone = ZoneInfo(get_house_settings(db)["timezone"])
    try:
        now = datetime.now(zone)
        lo = (
            datetime.fromisoformat(start).replace(tzinfo=zone)
            if start
            else (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
        hi = datetime.fromisoformat(end).replace(tzinfo=zone) + timedelta(days=1) if end else now
        if hi <= lo or (hi - lo).days > 366:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Invalid date range (maximum 366 days)")
    q = select(Usage).where(
        Usage.created_at >= lo.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        Usage.created_at < hi.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
    )
    if user_id:
        q = q.where(Usage.user_id == user_id)
    if provider:
        q = q.where(Usage.provider == provider)
    if model:
        q = q.where(Usage.model == model)
    records = db.scalars(q).all()
    evidence = (
        {
            row.id: row.data
            for row in db.scalars(
                select(Record).where(Record.kind == "usage.evidence", Record.id.in_([r.id for r in records]))
            )
        }
        if records
        else {}
    )

    def blank():
        return dict(
            requests=0,
            input_tokens=0,
            output_tokens=0,
            cached_tokens=0,
            cost_microusd=0,
            unpriced_requests=0,
            subscription_requests=0,
            unknown_token_requests=0,
            failures=0,
            tool_calls=0,
            latency_ms=0,
            reserved_microusd=0,
            provider_reported_microusd=0,
            estimated_microusd=0,
            looked_up_microusd=0,
            looked_up_requests=0,
        )

    from .usage_prices import estimate, saved

    price_list = saved(db)
    prices = price_list.get("prices", {})

    totals, by_day, groups, kinds = blank(), {}, {}, set()
    for row in records:
        day = row.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date().isoformat()
        bucket = by_day.setdefault(day, blank())
        group = groups.setdefault((row.user_id, row.provider, row.model), blank())
        kind = evidence.get(row.id, {}).get(
            "cost_kind", "estimated" if row.cost_microusd is not None else "unknown"
        )
        kinds.add(kind)
        for target in (totals, bucket, group):
            target["requests"] += 1
            for name in ("input_tokens", "output_tokens", "cached_tokens", "tool_calls", "latency_ms"):
                target[name] += getattr(row, name)
            target["cost_microusd"] += row.cost_microusd or 0
            target["unpriced_requests"] += row.cost_microusd is None and kind != "subscription"
            target["subscription_requests"] += kind == "subscription"
            target["unknown_token_requests"] += not evidence.get(row.id, {}).get(
                "tokens_reported", row.status == "completed"
            )
            target["failures"] += row.status == "failed"
            target["reserved_microusd"] += row.reserved_microusd if row.cost_microusd is None else 0
            if kind == "provider_reported":
                target["provider_reported_microusd"] += row.cost_microusd or 0
            elif kind == "estimated":
                target["estimated_microusd"] += row.cost_microusd or 0
            # No cost recorded, not a subscription: what it would cost at today's looked-up price.
            guess = estimate(row, prices) if row.cost_microusd is None and kind != "subscription" else None
            if guess is not None:
                target["looked_up_microusd"] += guess
                target["looked_up_requests"] += 1
    return {
        "totals": totals,
        "series": [{"date": d, **v} for d, v in sorted(by_day.items())],
        "breakdown": [
            {"user_id": key[0], "provider": key[1], "model": key[2], **value} for key, value in groups.items()
        ],
        "timezone": zone.key,
        "cost_kind": next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "unknown",
        "prices_as_of": price_list.get("as_of"),
        "content_included": False,
    }


@router.get("/operations/{operation_id}")
def get_operation(operation_id: str, actor=Depends(require_actor), db=Depends(get_db)):
    row = db.scalar(select(Operation).where(Operation.id == operation_id, Operation.actor_id == actor.id))
    if not row:
        raise HTTPException(404, "Operation not found")
    return {
        "id": row.id,
        "kind": row.kind,
        "state": row.state,
        "revision": row.revision,
        "result": row.result,
        "updated_at": row.updated_at,
    }


# Work a resident started that is still in progress, for the activity tray. Plain codes;
# the interface words them. Old rows are ignored so a stale record never lingers.
ACTIVITY_JOBS = {
    "cinema.discover": "finding_sources",
    "cinema.validate": "checking_sources",
    "music.playlist_import": "importing_playlist",
}
ACTIVITY_WORKFLOWS = {"preparing": ("preparing_film", 6 * 3600), "command_sent": ("sending_to_tv", 600)}


@router.get("/activity")
def activity(actor=Depends(require_actor), db=Depends(get_db)):
    from .cinema_models import CinemaTitle, CinemaWorkflow

    items = []
    jobs = db.scalars(
        select(Job)
        .where(Job.actor_id == actor.id, Job.state.in_(["pending", "running"]), Job.kind.in_(ACTIVITY_JOBS))
        .limit(20)
    ).all()
    for job in jobs:
        operation = (
            db.get(Operation, job.payload.get("operation_id")) if job.payload.get("operation_id") else None
        )
        if operation and operation.updated_at and operation.updated_at < utcnow() - timedelta(hours=1):
            continue
        media_id = (operation.data or {}).get("media_id") if operation else None
        title = db.get(CinemaTitle, media_id) if media_id else None
        result = (operation.result or {}) if operation else {}
        added, total = result.get("added"), result.get("total")
        items.append(
            {
                "id": job.id,
                "kind": ACTIVITY_JOBS[job.kind],
                "title": title.title if title else None,
                "operation_id": operation.id if operation else None,
                "progress": round(added / total, 3)
                if isinstance(added, int) and isinstance(total, int) and total
                else None,
                "detail": f"{added} / {total}" if job.kind == "music.playlist_import" and total else None,
                "href": "/listen" if job.kind.startswith("music.") else "/watch",
            }
        )
    for workflow in db.scalars(
        select(CinemaWorkflow)
        .where(CinemaWorkflow.owner_id == actor.id, CinemaWorkflow.state.in_(ACTIVITY_WORKFLOWS))
        .order_by(CinemaWorkflow.updated_at.desc())
        .limit(10)
    ):
        kind, max_age = ACTIVITY_WORKFLOWS[workflow.state]
        if workflow.updated_at < utcnow() - timedelta(seconds=max_age):
            continue
        title = db.get(CinemaTitle, workflow.media_id)
        download = workflow.data.get("download") or {}
        done, total = download.get("bytes"), download.get("total")
        items.append(
            {
                "id": workflow.id,
                "kind": "saving_film" if workflow.data.get("_kind") == "save_local" else kind,
                "title": title.title if title else None,
                "progress": round(done / total, 3)
                if isinstance(done, int) and isinstance(total, int) and total
                else None,
                "href": "/watch?workflow=" + workflow.id,
            }
        )
    return {"items": items}
