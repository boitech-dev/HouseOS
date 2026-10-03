"""Live assistant evaluation: real provider, prompt, schemas and chat loop; synthetic tools.

Tool handlers are replaced by canned results, so no device, media, network source or
production data is touched. Uses an in-memory database. Costs a few provider calls.

    agent-secret-run houseos-providers env PYTHONPATH=backend \
        /opt/houseos/state/venvs/app/bin/python backend/evals/live_assistant.py [name-filter]
"""

import json
import os
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import houseos.main  # noqa: F401 (registers every model)
from houseos import assistant as a
from houseos import assistant_profiles
from houseos.auth import Actor, RESIDENT
from houseos.db import Base, new_id
from houseos.models import User, Usage

MODEL = os.environ.get("EVAL_MODEL", "deepseek/deepseek-v4-flash")
BOB = "bob-0000-0000-0000-000000000000"


def fake_result(name, args):
    q = str(args.get("query") or "")
    if name == "music_search":
        n = int(args.get("limit") or 5)
        return {
            "status": "completed",
            "items": [
                {"id": f"cand-{i}", "title": f"{q} — result {i}", "uploader": "Official"}
                for i in range(1, n + 1)
            ],
        }
    if name in {"music_add_candidates", "music_add", "radio_queue"}:
        return {
            "status": "accepted",
            "operation_id": "op-music",
            "count": len(args.get("candidate_ids") or [1]),
        }
    if name == "music_control":
        return {"status": "completed", "action": args.get("action"), "value": args.get("value")}
    if name == "music_get_state":
        return {
            "state": "playing",
            "version": 7,
            "current": {
                "title": "Around the World",
                "uploader": "Daft Punk",
                "position": 42,
                "duration": 420,
            },
            "items": [{"title": "One More Time"}],
            "volume": 60,
        }
    if name == "household_list":
        return {"items": [{"id": "g1", "kind": "groceries", "version": 1, "summary": {"label": "Bread"}}]}
    if name == "household_create":
        item = args.get("item") or {}
        return {
            "status": "completed",
            "id": new_id(),
            "kind": item.get("kind"),
            "version": 1,
            "summary": item.get("data"),
        }
    if name == "calendar_digest":
        return {
            "today": "2026-09-23",
            "week": [{"title": "Dentist", "start": "2026-09-25T10:00:00", "all_day": False, "for_you": True}],
            "later": [],
            "tasks": [],
        }
    if name == "calendar_agenda":
        return {
            "items": [
                {
                    "id": "e1",
                    "title": "Dentist",
                    "start": "2026-09-25T10:00:00+02:00",
                    "end": "2026-09-25T11:00:00+02:00",
                }
            ]
        }
    if name == "users_lookup":
        return {"items": [{"id": BOB, "name": "Bob"}]}
    if name == "messages_send":
        return {
            "status": "needs_confirmation",
            "confirmation_id": "conf-msg",
            "confirmation_path": "/assistant/confirmations/conf-msg",
            "preview": {"recipient_ids": [BOB], "body": args.get("body")},
        }
    if name == "memory_save":
        return {"status": "completed", "id": "mem-1", "text": args.get("text")}
    if name == "cinema_search":
        return {"items": [{"id": "title-dune2", "title": "Dune: Part Two", "year": 2024, "kind": "movie"}]}
    if name == "devices_list":
        return {
            "items": [
                {"id": "dev-cast", "name": "Living room TV (Chromecast)", "adapter": "cast", "state": "idle"}
            ]
        }
    if name == "cinema_discover":
        return {"status": "accepted", "operation_id": "op-discover", "state": "running", "workflow_id": None}
    if name == "tv_control":
        return {
            "status": "needs_confirmation",
            "confirmation_id": "tv-conf",
            "confirmation_path": "/cinema/device-confirmations/tv-conf",
            "preview": {"action": args.get("action"), "value": args.get("value")},
        }
    if name == "files_search":
        return {"items": [{"id": "f1", "name": "Taxes 2025.pdf", "version": 1, "scope": "personal"}]}
    return {"status": "completed"}


TV = {
    "items": [
        {
            "id": "tv-1",
            "name": "Hisense TV",
            "state": "on",
            "version": 3,
            "input": "HDMI1",
            "inputs": ["HDMI1", "HDMI2", "HDMI3"],
            "volume": 20,
        }
    ]
}


# (name, message, check(calls) -> bool). calls = [(tool, args), ...] in order.
def names(calls):
    return [c[0] for c in calls if c[0] != "switch_context"]


SCENARIOS = [
    (
        "play-song",
        "Play Bohemian Rhapsody by Queen",
        lambda c: names(c)[:1] == ["music_search"] and {"music_add_candidates", "music_add"} & set(names(c)),
    ),
    (
        "three-songs-fr",
        "Mets 3 chansons de Daft Punk",
        lambda c: any(t == "music_add_candidates" and len(x.get("candidate_ids", [])) == 3 for t, x in c),
    ),
    (
        "pause",
        "Pause the music",
        lambda c: names(c) == ["music_control"] and c[-1][1].get("action") == "pause",
    ),
    (
        "volume",
        "Set the music volume to 40%",
        lambda c: names(c)[-1:] == ["music_control"] and c[-1][1].get("value") in (40, 40.0),
    ),
    ("now-playing", "What's playing right now?", lambda c: names(c) == ["music_get_state"]),
    ("groceries", "Add milk and eggs to the groceries", lambda c: set(names(c)) == {"household_create"}),
    (
        "agenda",
        "What's on the house calendar this week?",
        lambda c: names(c) in (["calendar_digest"], ["calendar_agenda"]),
    ),
    (
        "task-bob",
        "Create a task for Bob to take out the trash tomorrow",
        lambda c: "household_create" in names(c) and "users_lookup" in names(c),
    ),
    ("message-bob", "Send Bob a message: dinner is ready", lambda c: names(c)[-1:] == ["messages_send"]),
    ("remember", "Remember that my favourite colour is green", lambda c: names(c) == ["memory_save"]),
    (
        "hdmi",
        "Switch the TV to HDMI 2",
        lambda c: names(c) == ["tv_control"] and c[-1][1].get("action") == "input",
    ),
    (
        "tv-volume-fr",
        "Baisse le son de la télé à 15",
        lambda c: names(c) == ["tv_control"] and c[-1][1].get("value") in (15, 15.0, "15"),
    ),
    (
        "movie",
        "Watch Dune Part Two on the living room TV in French",
        lambda c: names(c)[:1] == ["cinema_search"] and "cinema_discover" in names(c),
    ),
    ("reboot", "Reboot the Chromecast", lambda c: not c),
    ("hello", "Hi! How are you?", lambda c: not c),
    ("files", "Find my tax documents", lambda c: names(c) == ["files_search"]),
]


def run(selected):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    alice = User(
        id=new_id(),
        name="Alice",
        username="alice",
        password_hash="eval",
        role="resident",
        permissions=list(RESIDENT),
    )
    db.add_all(
        [
            alice,
            User(
                id=BOB,
                name="Bob",
                username="bob",
                password_hash="eval",
                role="resident",
                permissions=list(RESIDENT),
            ),
        ]
    )
    db.commit()
    actor = Actor(alice.id, "Alice", "resident", RESIDENT)
    cfg = {
        "api_key": os.environ["OPENROUTER_API_KEY"],
        "model": MODEL,
        "reasoning_effort": "low",
        "max_output_tokens": 800,
        "input_microusd_per_million": 1,
        "output_microusd_per_million": 1,
    }
    selected_role = {"provider": "openrouter", "model": MODEL, "reasoning_effort": "low"}
    a.integration_config = lambda db, name: dict(cfg)
    assistant_profiles.assignment = lambda db, purpose: dict(selected_role)
    assistant_profiles.apply_assignment = lambda db, cfg, selected: None

    def reserve(db, actor, provider, config, messages, schemas):
        row = Usage(user_id=actor.id, provider="openrouter", model=MODEL, reserved_microusd=1)
        db.add(row)
        db.commit()
        return row.id

    a.reserve = reserve
    a.assistant_devices = lambda actor, db, tv=False: TV if tv else fake_result("devices_list", {})
    original_registry, original_round = a.tool_registry, a.provider_round
    calls, rounds = [], []

    def registry(context):
        tools = original_registry(context)

        def fake(name, handler):
            if name == "switch_context":
                return lambda b, ac, d: (calls.append((name, b.model_dump())), handler(b, ac, d))[1]
            return lambda b, ac, d: (
                calls.append((name, b.model_dump(mode="json", exclude={"idempotency_key"}))),
                fake_result(name, b.model_dump(mode="json")),
            )[1]

        return {name: (model, desc, fake(name, handler)) for name, (model, desc, handler) in tools.items()}

    def timed_round(*args):
        start = time.monotonic()
        result = original_round(*args)
        rounds.append(
            {
                "seconds": round(time.monotonic() - start, 2),
                "calls": [c["name"] for c in result[1]],
                "usage": result[3],
            }
        )
        return result

    a.tool_registry, a.provider_round = registry, timed_round

    results = []
    for name, message, check in SCENARIOS:
        if selected and selected not in name:
            continue
        calls.clear()
        rounds.clear()
        start = time.monotonic()
        try:
            out = a.chat(a.Chat(message=message, idempotency_key=new_id()), actor, db)
            reply, cards, error = out["reply"], out["cards"], None
        except Exception as exc:  # report, keep evaluating
            reply, cards, error = "", [], f"{type(exc).__name__}: {getattr(exc, 'detail', exc)}"
        ok = bool(check(list(calls))) and not error
        results.append(
            {
                "name": name,
                "ok": ok,
                "rounds": len(rounds),
                "seconds": round(time.monotonic() - start, 1),
                "input_tokens": sum((r["usage"] or {}).get("input_tokens") or 0 for r in rounds),
                "tools": [c[0] for c in calls],
                "reply": reply[:160],
                "cards": len(cards),
                "error": error,
            }
        )
        r = results[-1]
        print(
            f"{'PASS' if ok else 'FAIL'} {name:15} rounds={r['rounds']} {r['seconds']:5}s in={r['input_tokens']:6} tools={r['tools']} :: {r['reply']!r}"
            + (f" ERROR {error}" if error else ""),
            flush=True,
        )
    passed = sum(r["ok"] for r in results)
    print(
        json.dumps(
            {
                "passed": passed,
                "total": len(results),
                "rounds": sum(r["rounds"] for r in results),
                "seconds": round(sum(r["seconds"] for r in results), 1),
                "input_tokens": sum(r["input_tokens"] for r in results),
            }
        )
    )


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
