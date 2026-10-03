"""Durable slow catalog/probe work. Interrupted remote mutations never auto-replay."""

from datetime import timedelta
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import Actor, require_actor, user_permissions, delegated_user
from .db import get_db, utcnow, new_id
from .models import Job, Operation
from .events import emit
from .cinema import (
    router,
    Discover,
    allowed,
    discover,
    own_workflow,
    validate_rd,
    save_workflow,
    public_workflow,
    CinemaWorkflow,
)
from .playback import MediaError


def public_operation(row):
    return {"operation_id": row.id, "status": row.state, **row.result}


@router.get("/operations/{identity}")
def get_operation(identity: str, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    row = db.scalar(
        select(Operation).where(
            Operation.id == identity,
            Operation.actor_id == actor.id,
            Operation.kind.in_(["cinema.discover", "cinema.validate"]),
        )
    )
    if not row:
        raise HTTPException(404, "Cinema operation not found")
    return public_operation(row)


@router.post("/operations/discover")
def enqueue_discovery(body: Discover, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)):
    allowed(actor)
    payload = body.model_dump()
    existing = db.scalar(
        select(Operation).where(
            Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
        )
    )
    if existing:
        if existing.kind != "cinema.discover" or existing.data != payload:
            raise HTTPException(409, "Idempotency key already used for another request")
        return public_operation(existing)
    row = Operation(
        id=new_id(),
        actor_id=actor.id,
        kind="cinema.discover",
        state="accepted",
        data=payload,
        idempotency_key=body.idempotency_key,
    )
    db.add(row)
    db.add(
        Job(
            logical_key="cinema:" + row.id,
            kind="cinema.discover",
            actor_id=actor.id,
            payload={"operation_id": row.id, "session_hash": actor.session_hash},
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # A concurrent request with the same key won; return its operation.
        existing = db.scalar(
            select(Operation).where(
                Operation.actor_id == actor.id, Operation.idempotency_key == body.idempotency_key
            )
        )
        if not existing or existing.kind != "cinema.discover" or existing.data != payload:
            raise HTTPException(409, "Idempotency key already used for another request")
        return public_operation(existing)
    return public_operation(row)


def enqueue_validation(db, workflow, source_ids, session_hash):
    row = Operation(
        id=new_id(),
        actor_id=workflow.owner_id,
        kind="cinema.validate",
        state="accepted",
        data={"workflow_id": workflow.id, "version": workflow.version, "source_ids": source_ids},
        result={"workflow_id": workflow.id},
    )
    db.add(row)
    db.add(
        Job(
            logical_key="cinema:" + row.id,
            kind="cinema.validate",
            actor_id=workflow.owner_id,
            payload={"operation_id": row.id, "session_hash": session_hash},
        )
    )
    workflow.data = {**workflow.data, "operation_id": row.id}
    db.commit()
    return public_workflow(workflow)


def start_suggestion(db, workflow_id, session_hash, more=False):
    """Probe the three most promising releases now, so one tap can play the best of them.
    Only cached releases are checked (16 MB each); nothing plays or downloads. `more` looks
    again after the first rounds found nothing (Check other versions)."""
    from .cinema_suggest import rank_provisional

    workflow = db.get(CinemaWorkflow, workflow_id)
    states = {"discovered", "awaiting_choice"} | ({"recovery_required"} if more else set())
    if not workflow or workflow.state not in states:
        return None
    if not more and workflow.data.get("choice_set", {}).get("candidates"):
        return None  # a local or already-checked release is ready
    request = workflow.data.get("request", {})
    maximum = request.get("maximum_resolution") or 2160
    top = rank_provisional(workflow.data.get("_sources", []), maximum)
    if not top:
        return None
    ids = [source["id"] for source in top]
    workflow.state, workflow.version, workflow.updated_at = "preparing", workflow.version + 1, utcnow()
    workflow.data = {
        **workflow.data,
        "_validation_selection": ids,
        "_suggestion": True,
        "_rounds": 1,
        "error": None,
    }
    return enqueue_validation(db, workflow, ids, session_hash)


class More(BaseModel):
    version: int = Field(ge=1)


@router.post("/workflows/{identity}/suggest-more")
def suggest_more(
    identity: str, body: More, actor: Actor = Depends(require_actor), db: Session = Depends(get_db)
):
    """Check the next most promising versions, best first (not simply the next in the list)."""
    own_workflow(db, actor, identity, body.version)
    result = start_suggestion(db, identity, actor.session_hash, more=True)
    if not result:
        raise HTTPException(409, "No other versions to check.")
    return result


def job_actor(db, job):
    # Independent transaction avoids a MariaDB repeatable-read authorization snapshot.
    with Session(db.get_bind()) as fresh:
        token_hash = job.payload.get("session_hash")
        user = delegated_user(fresh, job.actor_id, token_hash, "cinema.use")
        if not user:
            raise MediaError(
                "PERMISSION_REVOKED", "Cinema authorization expired or was revoked.", "authorization"
            )
        return Actor(user.id, user.name, user.role, frozenset(user_permissions(user)), token_hash)


def process_one_operation(db):
    now = utcnow()
    job = db.scalar(
        select(Job)
        .where(
            Job.kind.in_(["cinema.discover", "cinema.validate"]),
            Job.next_run <= now,
            or_(Job.state == "pending", and_(Job.state == "running", Job.lease_until < now)),
        )
        .order_by(Job.next_run)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not job:
        db.rollback()
        return False
    op = db.get(Operation, job.payload["operation_id"])
    if job.state == "running":
        job.state, job.error_code = "unverified", "INTERRUPTED_RECONCILE_BEFORE_RETRY"
        op.state, op.result = (
            "unverified",
            {
                **op.result,
                "error": {
                    "code": job.error_code,
                    "message": "The worker was interrupted. Inspect the saved workflow before preparing another action.",
                },
            },
        )
        workflow = (
            db.get(CinemaWorkflow, op.data.get("workflow_id")) if op.kind == "cinema.validate" else None
        )
        if workflow and workflow.state == "preparing":
            save_workflow(db, workflow, "recovery_required", {"error": op.result["error"]})
        db.commit()
        return True
    job.state, job.lease_owner, job.lease_until = "running", new_id(), now + timedelta(minutes=20)
    job.generation += 1
    job.attempts += 1
    generation, job_id, operation_id = job.generation, job.id, op.id
    op.state = "running"
    db.commit()
    result = None
    error = None
    try:
        actor = job_actor(db, job)
        if op.kind == "cinema.discover":
            result = discover(Discover(**op.data), actor, db)
            if op.data.get("suggest"):
                result = start_suggestion(db, result["id"], actor.session_hash) or result
        else:
            workflow = own_workflow(db, actor, op.data["workflow_id"], op.data["version"])
            if workflow.state != "preparing":
                raise MediaError("PLAN_STALE", "Source validation was cancelled or superseded.", "validation")
            db.commit()  # release revision lock before provider calls
            result = validate_rd(db, workflow, op.data["source_ids"])
        job_actor(db, job)
    except MediaError as exc:
        error = exc.public()
    except HTTPException as exc:
        error = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "CINEMA_REQUEST_FAILED", "message": str(exc.detail)[:240]}
        )
    except Exception:
        # Unknown outcome stays unverified; do not store raw exception/provider URLs.
        error = {
            "code": "CINEMA_OPERATION_UNVERIFIED",
            "message": "The operation stopped unexpectedly. Inspect its workflow before retrying.",
        }
    db.rollback()
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not job or job.generation != generation or job.state != "running":
        # Discovery may finish its bounded provider request after Stop Cinema.
        # Retire its result too; never resurrect a cancelled operation in the UI.
        if job and job.state == "cancelled" and result:
            workflow = db.get(CinemaWorkflow, result["id"])
            if workflow and workflow.state in {"discovered", "awaiting_choice", "preparing"}:
                save_workflow(db, workflow, "cancelled", {"confirmation_id": None})
        db.rollback()
        return True
    op = db.get(Operation, operation_id)
    if error:
        job.state = op.state = (
            "unverified" if error.get("code") == "CINEMA_OPERATION_UNVERIFIED" else "failed"
        )
        job.error_code = error.get("code")
        op.result = {**op.result, "error": error}
        if op.kind == "cinema.validate":
            stuck = db.get(CinemaWorkflow, op.data.get("workflow_id"))
            if stuck and stuck.state == "preparing" and stuck.version == op.data.get("version"):
                save_workflow(db, stuck, "recovery_required", {"error": error})
    else:
        job.state = op.state = "completed"
        op.result = {"workflow_id": result["id"], "workflow": result}
    emit(db, "cinema.operation", public_operation(op), user_id=op.actor_id)
    db.commit()
    return True
