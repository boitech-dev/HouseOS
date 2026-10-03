"""More languages than English and French: Nox's AI translates the interface once, in the
background, and the translation lives in the database like any house data.

The strings to translate come from the built page (`ui-strings.json`, English keys with the
French wording as context, written by the frontend build). Batches are small and saved as
they finish, so a restart or a failed call resumes where it stopped. Budgets and daily limits
apply to every call, as for a chat with Nox."""

import json
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .auth import Actor, Input, require_actor, require_admin
from .config import settings
from .db import SessionLocal, get_db, utcnow
from .events import emit
from .models import Record

router = APIRouter(tags=["languages"])
BUILT_IN = {"en": "English", "fr": "Français"}
BATCH_CHARACTERS = 3500  # about 100 short strings per request
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
state = {"thread": None}


class NewLanguage(Input):
    code: str = Field(pattern="^[a-z]{2,3}$", description="ISO 639-1 code, e.g. pl, de, pt.")
    name: str = Field(min_length=1, max_length=40, description="The language's own name, e.g. Polski.")


def key(code):
    return "language:" + code


def source_strings():
    """English → French pairs from the built page; empty when not built here."""
    try:
        return json.loads((settings.frontend_dist / "ui-strings.json").read_text())
    except (OSError, ValueError):
        return {}


def public(row):
    data = row.data
    return {
        "code": data["code"],
        "name": data["name"],
        "state": data["state"],
        "done": len(data.get("strings", {})),
        "total": data.get("total", 0),
        "error": data.get("error"),
    }


def added(db):
    from sqlalchemy import select

    return list(
        db.scalars(select(Record).where(Record.kind == "house.language", Record.deleted_at.is_(None)))
    )


def ready(db):
    """Every language the interface can show now: code → its own name."""
    return {**BUILT_IN, **{r.data["code"]: r.data["name"] for r in added(db) if r.data["state"] == "ready"}}


def ensure_ready(db, code):
    if code not in ready(db):
        raise HTTPException(422, "This language isn't ready in the house yet")


@router.get("/languages")
def languages(actor=Depends(require_actor), db=Depends(get_db)):
    built = [{"code": c, "name": n, "state": "ready", "built_in": True} for c, n in BUILT_IN.items()]
    return {"items": built + [public(r) for r in added(db)]}


@router.get("/languages/{code}/strings")
def strings(code: str, actor=Depends(require_actor), db=Depends(get_db)):
    row = db.get(Record, key(code))
    if not row or row.deleted_at or row.kind != "house.language":
        raise HTTPException(404, "No such language")
    return row.data.get("strings", {})


def start(db, actor, body: NewLanguage):
    """Create (or resume) a translation; the maintenance service does the work."""
    if body.code in BUILT_IN:
        raise HTTPException(409, "This language is built in")
    total = len(source_strings())
    if not total:
        raise HTTPException(503, "The interface texts aren't available on this server; rebuild the page")
    row = db.get(Record, key(body.code))
    data = {"code": body.code, "name": body.name, "state": "translating", "total": total, "by": actor.id}
    if row:
        row.data, row.deleted_at, row.updated_at = {**row.data, **data, "error": None}, None, utcnow()
    else:
        row = Record(
            id=key(body.code), kind="house.language", owner_id=actor.id, visibility="house", data=data
        )
        db.add(row)
    emit(db, "audit.language_translation_started", {"name": body.name})
    db.commit()
    return public(row)


@router.post("/admin/languages")
def add_language(body: NewLanguage, actor=Depends(require_admin), db=Depends(get_db)):
    return start(db, actor, body)


@router.delete("/admin/languages/{code}")
def remove_language(code: str, actor=Depends(require_admin), db=Depends(get_db)):
    row = db.get(Record, key(code))
    if not row or row.kind != "house.language":
        raise HTTPException(404, "No such language")
    row.deleted_at = utcnow()
    db.commit()
    return {"status": "removed"}


# ---------- the work, in the maintenance service ----------
POLICY = (
    "You translate the interface of HouseOS, a warm, playful self-hosted app for a shared home "
    "(music jukebox, films, groceries, tasks, a pixel-art bat assistant called Nox). Translate each "
    "English string into {name} ({code}). Keep it short, natural and friendly, as a native app would. "
    "Keep every {{placeholder}} exactly, keep emoji, arrows and punctuation marks, keep product names "
    "(HouseOS, Nox, Jellyfin, YouTube, Cast). The French is only a hint for tone. Answer "
    'with one JSON object only: {{"<number>": "<translation>"}} for every number given.'
)


def batch(pending, source, limit=None):
    chosen, size = [], 0
    for text in pending:
        if chosen and size + len(text) + len(source.get(text, "")) > (limit or BATCH_CHARACTERS):
            break
        chosen.append(text)
        size += len(text) + len(source.get(text, ""))
    return chosen


def ask(db, row, texts, source):
    """One model call for a batch; returns {english: translation} for the ones that are sound."""
    from .assistant import audit_request, provider_round, record_usage_evidence, reserve
    from .assistant_profiles import apply_assignment, assignment
    from .integrations import integration_config
    from .models import Usage, User

    owner = db.get(User, row.data["by"])
    actor = Actor(owner.id, owner.name, owner.role, frozenset())
    selected = assignment(db, "setup")
    provider = selected["provider"]
    cfg = integration_config(db, provider)
    apply_assignment(db, cfg, selected)
    cfg["_purpose"], cfg["_assignment"] = "setup", selected
    cfg["_policy"] = POLICY.format(name=row.data["name"], code=row.data["code"])
    numbered = {str(i + 1): {"en": text, "fr": source.get(text, "")} for i, text in enumerate(texts)}
    messages = [{"role": "user", "content": json.dumps(numbered, ensure_ascii=False)}]
    usage_id = reserve(db, actor, provider, cfg, messages, [])
    # ponytail: the reservation counts the provider's usual reply size; the real cost of this
    # longer reply is recorded right after, so budgets stay exact from then on.
    # 60 s is the sign-in bridges' cap per round; a batch that runs out of time is halved.
    cfg["max_output_tokens"], cfg["_timeout_seconds"] = 4000, 60
    # The setup model, thinking briefly: translating strings is mechanical, and at medium effort
    # 100 strings of JSON can outlast a round. Only lowered where one is set (a model without a
    # configurable effort refuses the parameter), after reserve(), which reapplies the assignment.
    if cfg.get("reasoning_effort"):
        cfg["reasoning_effort"] = "low"
    record = db.get(Usage, usage_id)
    try:
        reply, _, _, reported = provider_round(provider, cfg, messages, [])
    except Exception:
        record.status = "failed"
        record_usage_evidence(db, record, cfg)
        audit_request(db, record)
        db.commit()
        raise
    record_usage_evidence(db, record, cfg, reported)
    audit_request(db, record)
    db.commit()
    return read_answer(reply, texts)


def read_answer(reply, texts):
    """{english: translation} from the model's JSON, only where every {placeholder} survived."""
    found = re.search(r"\{.*\}", reply or "", re.S)
    answer = json.loads(found.group(0)) if found else {}
    result = {}
    for number, text in enumerate(texts, start=1):
        said = answer.get(str(number))
        # A translation that lost a {placeholder} would break the sentence: keep English there.
        if (
            isinstance(said, str)
            and said.strip()
            and set(PLACEHOLDER.findall(said)) == set(PLACEHOLDER.findall(text))
        ):
            result[text] = said.strip()
    return result


def work(code):
    """Translate batch after batch until done; stops on three failures in a row (Retry resumes)."""
    source = source_strings()
    failures, limit = 0, None
    while True:
        with SessionLocal() as db:
            row = db.get(Record, key(code))
            if not row or row.deleted_at or row.data.get("state") != "translating":
                return
            done = row.data.get("strings", {})
            pending = [text for text in source if text not in done]
            if not pending:
                row.data = {**row.data, "state": "ready", "total": len(source), "error": None}
                emit(
                    db,
                    "system.note",
                    {"text": "{name} is ready for everyone", "level": "good", "name": row.data["name"]},
                )
                db.commit()
                return
            texts = batch(pending, source, limit)
            try:
                translated = ask(db, row, texts, source)
                failures = 0 if translated else failures + 1
                limit = limit if translated else (limit or BATCH_CHARACTERS) // 2
            except Exception as error:  # noqa: BLE001 - a failed batch is retried, then reported
                db.rollback()
                translated, failures = {}, failures + 1
                limit = (limit or BATCH_CHARACTERS) // 2  # a smaller batch answers sooner
                detail = getattr(error, "detail", None)
                message = detail if isinstance(detail, str) else type(error).__name__
            else:
                message = "The AI's answers could not be read"
            row = db.get(Record, key(code))
            if not row or row.deleted_at:
                return
            # Strings it could not translate stay English for now, so the work always moves on.
            skipped = {text: text for text in texts if text not in translated} if failures == 0 else {}
            row.data = {**row.data, "strings": {**row.data.get("strings", {}), **skipped, **translated}}
            if failures >= 3:
                row.data = {**row.data, "state": "failed", "error": message}
                emit(
                    db,
                    "system.note",
                    {
                        "text": "{name} translation stopped: {error}",
                        "level": "problem",
                        "name": row.data["name"],
                        "error": message,
                    },
                )
            db.commit()
            if failures >= 3:
                return
        time.sleep(1 if not failures else 20)


def refresh(db=None):
    """Maintenance step: one translation at a time, in its own thread."""
    if state["thread"] and state["thread"].is_alive():
        return
    with SessionLocal() as session:
        waiting = [r.data["code"] for r in added(session) if r.data.get("state") == "translating"]
    if waiting:
        state["thread"] = threading.Thread(target=work, args=(waiting[0],), name="translate", daemon=True)
        state["thread"].start()
