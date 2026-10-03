"""Opt-in generic Web Push. The inbox remains authoritative and private."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
import urllib3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, EllipticCurvePublicKey
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Actor, require_actor, require_permission
from .config import settings
from .db import Base, get_db, new_id, utcnow
from .household import HouseholdNotification
from .models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True)
    encrypted_payload: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PushDelivery(Base):
    __tablename__ = "push_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "subscription_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    notification_id: Mapped[str] = mapped_column(ForeignKey("household_notifications.id"), index=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("push_subscriptions.id"), index=True)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_error: Mapped[str | None] = mapped_column(String(40), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PushKeys(Strict):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class SubscriptionInput(Strict):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: PushKeys
    expirationTime: int | None = None


class NotificationPreferences(Strict):
    quiet_start: str = Field(default="23:00", pattern=r"^\d{2}:\d{2}$")
    quiet_end: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = "UTC"  # when omitted, the house setting is used (house_settings)
    muted_categories: list[str] = Field(default_factory=list, max_length=10)


def validate_endpoint(endpoint: str):
    try:
        u = urlparse(endpoint)
        host = u.hostname or ""
        allowed = (
            host in {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}
            or host.endswith(".push.apple.com")
            or host.endswith(".notify.windows.com")
        )
        if (
            u.scheme != "https"
            or not allowed
            or u.port not in (None, 443)
            or u.username
            or u.password
            or u.fragment
            or not u.path
            or any(ord(c) < 33 for c in endpoint)
        ):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Unsupported or unsafe browser push endpoint")
    return u


def validate_subscription(body: SubscriptionInput):
    validate_endpoint(body.endpoint)
    try:
        key = base64.urlsafe_b64decode(body.keys.p256dh + "=" * (-len(body.keys.p256dh) % 4))
        auth = base64.urlsafe_b64decode(body.keys.auth + "=" * (-len(body.keys.auth) % 4))
        EllipticCurvePublicKey.from_encoded_point(SECP256R1(), key)
        if len(auth) != 16:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid browser push encryption keys")


def cipher():
    if not settings.encryption_key:
        raise HTTPException(503, "Encrypted subscription storage is unavailable")
    return Fernet(settings.encryption_key.encode())


def configured():
    return bool(settings.vapid_private_key and settings.vapid_public_key and settings.vapid_subject)


@router.get("/push")
def push_status(actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "messages.read")
    rows = db.scalars(
        select(PushSubscription).where(
            PushSubscription.user_id == actor.id, PushSubscription.active.is_(True)
        )
    ).all()
    from .house_settings import notification_defaults

    user = db.get(User, actor.id)
    return {
        "configured": configured(),
        "application_server_key": settings.vapid_public_key if configured() else None,
        "subscriptions": [{"id": r.id, "created_at": r.created_at} for r in rows],
        "preferences": user.preferences.get("notification_settings")
        or {**NotificationPreferences().model_dump(), **notification_defaults(db)},
        "delivery_guarantee": "in_app_inbox",
        "privacy": "Push text is generic; provider acceptance does not prove display or reading",
    }


@router.post("/push", status_code=201)
def subscribe(body: SubscriptionInput, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "messages.read")
    if not configured():
        raise HTTPException(503, "Browser push has not been configured by the administrator")
    validate_subscription(body)
    endpoint_hash = hashlib.sha256(body.endpoint.encode()).hexdigest()
    row = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint_hash == endpoint_hash).with_for_update()
    )
    if row and row.user_id != actor.id:
        # Never transfer another account's subscription on browser account switch.
        raise HTTPException(409, "Unsubscribe this browser from its previous account first")
    if not row:
        count = len(
            db.scalars(
                select(PushSubscription.id).where(
                    PushSubscription.user_id == actor.id, PushSubscription.active.is_(True)
                )
            ).all()
        )
        if count >= 10:
            raise HTTPException(429, "Remove an unused device before adding another")
        row = PushSubscription(id=new_id(), user_id=actor.id, endpoint_hash=endpoint_hash)
        db.add(row)
    row.active = True
    row.encrypted_payload = cipher().encrypt(json.dumps(body.model_dump(exclude_none=True)).encode()).decode()
    db.commit()
    return {"id": row.id, "status": "subscribed", "delivery_status": "unverified"}


@router.delete("/push/{subscription_id}")
def unsubscribe(subscription_id: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    require_permission(actor, "messages.read")
    row = db.scalar(
        select(PushSubscription).where(
            PushSubscription.id == subscription_id, PushSubscription.user_id == actor.id
        )
    )
    if not row:
        raise HTTPException(404, "Subscription not found")
    row.active = False
    row.encrypted_payload = ""
    # Release endpoint hash so an explicitly unsubscribed browser can join a new account.
    row.endpoint_hash = hashlib.sha256(("revoked:" + row.id).encode()).hexdigest()
    db.commit()
    return {"unsubscribed": True}


@router.put("/preferences")
def preferences(
    body: NotificationPreferences, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    require_permission(actor, "messages.read")
    try:
        ZoneInfo(body.timezone)
        for value in (body.quiet_start, body.quiet_end):
            hour, minute = map(int, value.split(":"))
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ValueError()
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, "Invalid quiet hours or timezone")
    if not set(body.muted_categories) <= {"message", "assignment", "reminder", "reminder_catchup"}:
        raise HTTPException(422, "Unknown notification category")
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    from .house_settings import notification_defaults

    values = body.model_dump()
    if "timezone" not in body.model_fields_set:
        values["timezone"] = notification_defaults(db)["timezone"]
    user.preferences = {**user.preferences, "notification_settings": values}
    db.commit()
    return values


def quiet_now(preferences: dict, now: datetime) -> bool:
    values = {**NotificationPreferences().model_dump(), **preferences}
    try:
        local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(values["timezone"]))
        minute = local.hour * 60 + local.minute
        start_h, start_m = map(int, values["quiet_start"].split(":"))
        end_h, end_m = map(int, values["quiet_end"].split(":"))
        start, end = start_h * 60 + start_m, end_h * 60 + end_m
        if start == end:
            return False
        return start <= minute < end if start < end else minute >= start or minute < end
    except (ValueError, ZoneInfoNotFoundError):
        return True


class PinnedPushSession:
    """pywebpush's transport hook: pin public DNS, verify TLS hostname, no redirects."""

    def post(self, url, data, headers, timeout=10, **kwargs):
        u = validate_endpoint(url)
        ips = {item[4][0] for item in socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)}
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError("Unsafe push endpoint address")
        ip = sorted(ips)[0]
        pool = urllib3.HTTPSConnectionPool(
            ip,
            port=443,
            server_hostname=u.hostname,
            assert_hostname=u.hostname,
            cert_reqs="CERT_REQUIRED",
            timeout=urllib3.Timeout(connect=5, read=10),
            maxsize=1,
        )
        try:
            target = u.path + (("?" + u.query) if u.query else "")
            raw = pool.urlopen(
                "POST",
                target,
                body=data,
                headers={**headers, "Host": u.hostname},
                redirect=False,
                retries=False,
                preload_content=False,
            )
            response = requests.Response()
            response.status_code = raw.status
            response.headers.update({"Retry-After": raw.headers.get("Retry-After", "")})
            response._content = b""  # Never propagate provider bodies containing endpoint tokens.
            raw.close()
            return response
        finally:
            pool.close()


def send_push(subscription: dict, payload: dict):
    from pywebpush import webpush

    return webpush(
        subscription_info=subscription,
        data=json.dumps(payload),
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
        ttl=3600,
        timeout=10,
        requests_session=PinnedPushSession(),
    )


def deliver_pending(db: Session, limit: int = 10):
    """Bounded worker entrypoint. Never calls an LLM or sends private message text."""
    from .house_settings import get_house_settings

    house_name = get_house_settings(db)["name"]
    if not configured():
        return {"state": "unconfigured", "accepted": 0}
    now = utcnow()
    created = 0
    # At most recent 100 unread inbox rows; old rows remain in-app without a push storm.
    notes = db.scalars(
        select(HouseholdNotification)
        .where(
            HouseholdNotification.created_at >= now - timedelta(hours=24),
            HouseholdNotification.read_at.is_(None),
        )
        .order_by(HouseholdNotification.created_at.desc())
        .limit(100)
    ).all()
    for note in notes:
        subscriptions = db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == note.user_id,
                PushSubscription.active.is_(True),
                PushSubscription.created_at <= note.created_at,
            )
        ).all()
        for sub in subscriptions:
            if db.scalar(
                select(PushDelivery.id).where(
                    PushDelivery.notification_id == note.id, PushDelivery.subscription_id == sub.id
                )
            ):
                continue
            try:
                with db.begin_nested():
                    db.add(PushDelivery(notification_id=note.id, subscription_id=sub.id))
                    db.flush()
                created += 1
            except IntegrityError:
                continue
    db.commit()
    now = utcnow()
    accepted = 0
    for _ in range(min(limit, 20)):
        delivery = db.scalar(
            select(PushDelivery)
            .where(PushDelivery.state.in_(["pending", "retry"]), PushDelivery.retry_at <= now)
            .order_by(PushDelivery.retry_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not delivery:
            break
        sub = db.get(PushSubscription, delivery.subscription_id)
        note = db.get(HouseholdNotification, delivery.notification_id)
        user = db.get(User, note.user_id)
        from .house_settings import notification_defaults

        prefs = {
            **notification_defaults(db),
            **(user.preferences.get("notification_settings", {}) if user else {}),
        }
        if (
            not sub.active
            or not user
            or not user.active
            or (user.expires_at and user.expires_at <= now)
            or note.read_at
            or note.category in prefs.get("muted_categories", [])
        ):
            delivery.state = "suppressed"
            db.commit()
            continue
        if note.created_at < now - timedelta(hours=24):
            delivery.state = "expired"
            db.commit()
            continue
        if quiet_now(prefs, now):
            delivery.retry_at = now + timedelta(minutes=15)
            db.commit()
            continue
        delivery.state = "sending"
        delivery.attempts += 1
        delivery.retry_at = now + timedelta(minutes=2)
        db.commit()
        try:
            subscription = json.loads(cipher().decrypt(sub.encrypted_payload.encode()))
            validate_endpoint(subscription["endpoint"])
            result = send_push(
                subscription,
                {
                    "title": house_name.upper(),
                    "body": "New house message",
                    "url": "/#household",
                    "tag": "house-inbox",
                },
            )
            delivery.state = "provider_accepted" if result.status_code <= 202 else "failed"
            delivery.accepted_at = utcnow() if delivery.state == "provider_accepted" else None
            if delivery.state == "provider_accepted":
                accepted += 1
        except Exception as exc:
            # Store categories only, never exception text containing subscription secrets.
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            if status in (404, 410):
                sub.active = False
                delivery.state, delivery.last_error = "failed", "SUBSCRIPTION_EXPIRED"
            elif status in (429, 503) and delivery.attempts < 3:
                delivery.state, delivery.last_error = "retry", "PROVIDER_RETRY"
                delivery.retry_at = utcnow() + timedelta(minutes=2**delivery.attempts)
            else:
                delivery.state, delivery.last_error = "unverified", "PUSH_NOT_CONFIRMED"
        db.commit()
    # A worker interrupted during network IO cannot assume whether push was accepted.
    for interrupted in db.scalars(
        select(PushDelivery).where(PushDelivery.state == "sending", PushDelivery.retry_at < now).limit(20)
    ).all():
        interrupted.state, interrupted.last_error = "unverified", "WORKER_INTERRUPTED"
    db.commit()
    return {"state": "processed", "created": created, "accepted": accepted}
