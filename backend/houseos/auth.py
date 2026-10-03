import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pwdlib import PasswordHash
from sqlalchemy import select, delete, func, String, DateTime, Integer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from .config import settings
from .db import Base, get_db, utcnow
from .models import User, SessionToken, Invite
from .events import emit

router = APIRouter(prefix="/auth", tags=["identity"])
passwords = PasswordHash.recommended()
COOKIE = "houseos_session"
RESIDENT = frozenset(
    {
        "household.read",
        "household.write",
        "messages.read",
        "messages.send",
        "files.read",
        "files.write",
        "files.shared.write",
        "music.read",
        "music.queue",
        "music.control",
        "cinema.use",
        "assistant.use",
        "diagnostics.read",
        "home.control",
        "games.play",
    }
)
DELEGABLE = RESIDENT | {"invites.create"}
PRESETS = {
    "roommate": RESIDENT,
    "guest": {"music.read", "music.queue"},
    "party": {"music.read", "music.queue", "games.play"},
    # A guest who may also pick a film for the TV (Watch → Guest code); no files, no account.
    "screen": {"music.read", "music.queue", "cinema.use"},
}


class BootstrapClaim(Base):
    __tablename__ = "bootstrap_claim"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    window_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Input):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class LoginCredentials(Credentials):
    # Authentication verifies an existing hash; creation policy belongs to enrollment.
    password: str = Field(min_length=1, max_length=256)


class Bootstrap(Credentials):
    name: str = Field(min_length=1, max_length=80)
    setup_token: str = Field(min_length=20, max_length=200)


class Redeem(Credentials):
    name: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=20, max_length=200)


class InviteInput(Input):
    preset: Literal["roommate", "guest", "party", "screen", "custom"] = "party"
    permissions: list[str] = Field(default_factory=list, max_length=30)
    expires_hours: int = Field(default=2, ge=1, le=168)
    membership_hours: int | None = Field(default=None, ge=1, le=720)


@dataclass(frozen=True)
class Actor:
    id: str
    name: str
    role: str
    permissions: frozenset[str]
    session_hash: str | None = None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def user_permissions(user):
    return frozenset(user.permissions or []) | (RESIDENT if user.role in {"resident", "admin"} else set())


def account_usable(user) -> bool:
    return bool(user and user.active and not (user.expires_at and user.expires_at <= utcnow()))


def delegated_user(db, user_id, session_hash=None, permission=None):
    """The user a background job acts for, if still usable, permitted and (for work started
    from a sign-in) that exact session is still valid; otherwise None."""
    user = db.get(User, user_id) if user_id else None
    if not account_usable(user) or (permission and permission not in user_permissions(user)):
        return None
    if session_hash:
        session = db.get(SessionToken, session_hash)
        if not session or session.user_id != user.id or session.expires_at <= utcnow():
            return None
    return user


def require_permission(actor, capability):
    if actor.role != "admin" and capability not in actor.permissions:
        raise HTTPException(403, "Permission denied")


def require_actor(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE)
    session = db.get(SessionToken, digest(token)) if token else None
    user = db.get(User, session.user_id) if session and session.expires_at > utcnow() else None
    if not account_usable(user):
        raise HTTPException(401, "Sign in required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token):
            raise HTTPException(403, "Refresh your session before retrying")
    request.state.session = session
    return Actor(user.id, user.name, user.role, user_permissions(user), session.token_hash)


def refresh_actor(db, actor):
    """Fresh authorization boundary after an external call or durable wait."""
    db.rollback()
    db.expire_all()
    user = delegated_user(db, actor.id, actor.session_hash)
    if not user:
        raise HTTPException(401, "Session was revoked or expired")
    return Actor(user.id, user.name, user.role, user_permissions(user), actor.session_hash)


def require_admin(actor=Depends(require_actor)):
    if actor.role != "admin":
        raise HTTPException(403, "Administrator required")
    return actor


def issue_session(db, user, response, request=None):
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(hours=settings.session_hours)
    if user.expires_at:
        expires = min(expires, user.expires_at)
    db.add(SessionToken(token_hash=digest(token), user_id=user.id, csrf_token=csrf, expires_at=expires))
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure or bool(request and request.url.scheme == "https"),
        samesite="strict",
        max_age=int((expires - utcnow()).total_seconds()),
        path="/",
    )
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role,
            "permissions": sorted(user_permissions(user)),
        },
        "csrf_token": csrf,
    }


def throttle(db, request, username, limit=10):
    # Persistent window applies across workers. Do not trust caller X-Forwarded-For.
    key = digest((request.client.host if request.client else "local") + ":" + username.lower())
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.key == key).with_for_update())
    if row is None:
        row = LoginAttempt(key=key, count=0, window_at=utcnow())
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(429, "Please retry shortly")
    if row.window_at < utcnow() - timedelta(minutes=15):
        row.count, row.window_at = 0, utcnow()
    row.count += 1
    blocked = row.count > limit
    db.commit()
    if blocked:
        raise HTTPException(429, "Too many attempts; try again in 15 minutes")


@router.get("/status")
def status(db=Depends(get_db)):
    return {"setup_required": db.scalar(select(func.count()).select_from(User)) == 0}


@router.post("/bootstrap")
def bootstrap(body: Bootstrap, request: Request, response: Response, db=Depends(get_db)):
    throttle(db, request, "bootstrap")
    if not settings.bootstrap_token or not secrets.compare_digest(body.setup_token, settings.bootstrap_token):
        raise HTTPException(403, "Invalid local setup capability")
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(409, "HouseOS is already set up")
    db.add(BootstrapClaim(id=1))
    user = User(
        name=body.name.strip(),
        username=body.username.lower(),
        password_hash=passwords.hash(body.password),
        role="admin",
    )
    db.add(user)
    try:
        db.flush()
        result = issue_session(db, user, response, request)
        emit(db, "identity.bootstrap", {"user_id": user.id}, user.id)
        from .access import adopt, normalize

        # The setup code proves this is the owner: the address they used becomes trusted.
        if origin := normalize(request.headers.get("origin") or ""):
            adopt(db, origin, user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "HouseOS is already set up")
    return result


@router.post("/login")
def login(body: LoginCredentials, request: Request, response: Response, db=Depends(get_db)):
    throttle(db, request, "*", limit=100)
    throttle(db, request, body.username)
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    valid = (
        passwords.verify(body.password, user.password_hash)
        if user
        else passwords.verify(body.password, DUMMY_HASH)
    )
    if not user or not valid or not user.active or (user.expires_at and user.expires_at <= utcnow()):
        raise HTTPException(401, "Invalid credentials")
    attempt = db.get(
        LoginAttempt,
        digest((request.client.host if request.client else "local") + ":" + body.username.lower()),
    )
    attempt.count = 0
    result = issue_session(db, user, response, request)
    db.commit()
    return result


@router.get("/me")
def me(request: Request, actor=Depends(require_actor), db=Depends(get_db)):
    user = db.get(User, actor.id)
    return {
        "user": {
            "id": actor.id,
            "name": actor.name,
            "username": user.username if user else "",  # lets password managers pick the right login
            "role": actor.role,
            "permissions": sorted(actor.permissions),
        },
        "csrf_token": request.state.session.csrf_token,
    }


@router.post("/logout")
def logout(request: Request, response: Response, actor=Depends(require_actor), db=Depends(get_db)):
    db.delete(request.state.session)
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"status": "completed"}


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


@router.post("/password")
def change_password(body: PasswordChange, actor=Depends(require_actor), db=Depends(get_db)):
    user = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if not passwords.verify(body.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    user.password_hash = passwords.hash(body.new_password)
    db.execute(delete(SessionToken).where(SessionToken.user_id == actor.id))
    emit(db, "audit.password_changed", {"user_id": actor.id}, actor.id)
    db.commit()
    return {"status": "completed", "sessions_revoked": True}


@router.get("/sessions")
def sessions(actor=Depends(require_actor), db=Depends(get_db)):
    return [
        {"id": x.token_hash[:16], "created_at": x.created_at, "expires_at": x.expires_at}
        for x in db.scalars(select(SessionToken).where(SessionToken.user_id == actor.id))
    ]


@router.delete("/sessions")
def revoke_sessions(actor=Depends(require_actor), db=Depends(get_db)):
    db.execute(delete(SessionToken).where(SessionToken.user_id == actor.id))
    db.commit()
    return {"status": "completed"}


@router.post("/invites")
def create_invite(body: InviteInput, actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "invites.create")
    grants = set(body.permissions) if body.preset == "custom" else set(PRESETS[body.preset])
    if not grants <= DELEGABLE or (actor.role != "admin" and not grants <= actor.permissions):
        raise HTTPException(403, "Invitation exceeds delegated permissions")
    role = "resident" if body.preset == "roommate" else "guest"
    if role == "resident" and actor.role != "admin":
        raise HTTPException(403, "Only administrators can create roommate memberships")
    token = secrets.token_urlsafe(32)
    invite = Invite(
        token_hash=digest(token),
        creator_id=actor.id,
        preset=body.preset,
        role=role,
        permissions=sorted(grants),
        expires_at=utcnow() + timedelta(hours=body.expires_hours),
        membership_hours=body.membership_hours if role == "resident" else (body.membership_hours or 2),
    )
    db.add(invite)
    db.flush()
    emit(db, "invite.created", {"id": invite.id}, actor.id)
    db.commit()
    return {
        "id": invite.id,
        "token": token,
        "path": "/join#" + token,
        "expires_at": invite.expires_at,
        "permissions": invite.permissions,
    }


@router.get("/invites")
def invitations(actor=Depends(require_actor), db=Depends(get_db)):
    require_permission(actor, "invites.create")
    q = select(Invite)
    if actor.role != "admin":
        q = q.where(Invite.creator_id == actor.id)
    return [
        {
            "id": x.id,
            "preset": x.preset,
            "permissions": x.permissions,
            "expires_at": x.expires_at,
            "redeemed": bool(x.redeemed_by),
            "revoked": x.revoked,
        }
        for x in db.scalars(q.order_by(Invite.created_at.desc()).limit(100))
    ]


@router.post("/redeem")
def redeem(body: Redeem, request: Request, response: Response, db=Depends(get_db)):
    throttle(db, request, "redeem")
    invite = db.scalar(select(Invite).where(Invite.token_hash == digest(body.token)).with_for_update())
    if not invite or invite.revoked or invite.redeemed_by or invite.expires_at <= utcnow():
        raise HTTPException(410, "Invitation expired, revoked or already used")
    issuer = db.get(User, invite.creator_id)
    if not account_usable(issuer):
        raise HTTPException(410, "Invitation issuer is no longer authorized")
    if issuer.role != "admin" and (
        "invites.create" not in user_permissions(issuer)
        or not set(invite.permissions) <= user_permissions(issuer)
    ):
        raise HTTPException(410, "Invitation permissions have been revoked")
    user = User(
        name=body.name.strip(),
        username=body.username.lower(),
        password_hash=passwords.hash(body.password),
        role=invite.role,
        permissions=invite.permissions,
        expires_at=utcnow() + timedelta(hours=invite.membership_hours) if invite.membership_hours else None,
    )
    db.add(user)
    try:
        db.flush()
        invite.redeemed_by = user.id
        result = issue_session(db, user, response, request)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username unavailable")
    return result


@router.delete("/invites/{invite_id}")
def revoke_invite(
    invite_id: str, revoke_membership: bool = False, actor=Depends(require_actor), db=Depends(get_db)
):
    require_permission(actor, "invites.create")
    row = db.scalar(select(Invite).where(Invite.id == invite_id).with_for_update())
    if not row or (actor.role != "admin" and row.creator_id != actor.id):
        raise HTTPException(404, "Invitation not found")
    row.revoked = True
    if revoke_membership and row.redeemed_by:
        user = db.get(User, row.redeemed_by)
        if user.role == "admin":
            raise HTTPException(409, "Use administrator account controls")
        user.active = False
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    emit(db, "invite.revoked", {"id": row.id}, actor.id)
    db.commit()
    return {"status": "completed"}


DUMMY_HASH = passwords.hash("houseos-dummy-verification-password")
