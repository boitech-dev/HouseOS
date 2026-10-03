"""Theme studio evaluation: Nox as the house's theme designer, end to end, with a real model.

Real studio prompt (themes/_studio/STUDIO.md), real theme tools (drafts are written to a
throwaway folder and really checked), scripted person replies, an in-memory database. Each
conversation is measured (words, questions and emojis per message; which tools ran and in what
order; whether the draft passed the checks) and then scored by a judge model on a rubric: does
Nox brainstorm across every aspect, raise the caveats the person didn't think of, keep it one
world, and walk the person through without flooding them.

    agent-secret-run houseos-providers env PYTHONPATH=backend \
        /opt/houseos/state/venvs/app/bin/python backend/evals/theme_studio.py [name-filter]

EVAL_MODEL (default anthropic/claude-opus-5.5, the studio's recommended model) and EVAL_JUDGE
(default anthropic/claude-sonnet-5) pick the OpenRouter models. A full run costs a few dollars.
Writes the transcripts and scores to EVAL_OUT (default /tmp/theme-studio-eval.json).
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import houseos.main  # noqa: F401 (registers every model)
from houseos import assistant as a
from houseos import assistant_profiles
from houseos.auth import Actor, RESIDENT
from houseos.config import settings
from houseos.db import Base, new_id
from houseos.models import User, Usage

MODEL = os.environ.get("EVAL_MODEL", "anthropic/claude-opus-5.5")
JUDGE = os.environ.get("EVAL_JUDGE", "anthropic/claude-sonnet-5")
OUT = Path(os.environ.get("EVAL_OUT", "/tmp/theme-studio-eval.json"))
KEY = os.environ["OPENROUTER_API_KEY"]

# (name, person's turns, checks) — a check is (label, fn(convo) -> bool); convo has "turns":
# [{"user", "reply", "calls": [(tool, args, result)], "cards"}].
EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐✨]")


def tools(convo, upto=None):
    turns = convo["turns"][:upto] if upto else convo["turns"]
    return [c[0] for t in turns for c in t["calls"]]


def saved_ok(convo):
    return any(
        name == "theme_save" and isinstance(result, dict) and result.get("status") == "saved"
        for t in convo["turns"]
        for name, _, result in t["calls"]
    )


def directions_count(convo):
    counts = [
        len(args.get("directions") or [])
        for t in convo["turns"]
        for name, args, _ in t["calls"]
        if name == "theme_directions"
    ]
    return max(counts, default=0)


def said(convo, *words, turn=None, least=1):
    text = " ".join(t["reply"] for t in convo["turns"]) if turn is None else convo["turns"][turn]["reply"]
    text = text.lower()
    return sum(w in text for w in words) >= least


SCENARIOS = [
    (
        "questions",
        [
            ("Start with 5 quick questions", "theme_questions"),
            "1. an old Japanese bathhouse at closing time 2. dark 3. phone at night 4. no pictures, just colours 5. nothing too cute",
        ],
        [
            (
                "the questions come from HouseOS, no model call",
                lambda c: (
                    not c["turns"][0]["calls"] and "five quick questions" in c["turns"][0]["reply"].lower()
                ),
            ),
            ("then three directions straight away", lambda c: directions_count(c) >= 3),
        ],
    ),
    (
        "cafe",
        [
            "I'd like our house to feel like a rainy Paris café at night.",
            "Dark, warm, a bit cosy. We mostly use it on phones in the evening, and a tablet in the kitchen.",
            "The second direction, but a little warmer.",
            "Can the buttons be rounder and the titles much bigger?",
        ],
        [
            (
                "three directions before building",
                lambda c: (
                    directions_count(c) >= 3
                    and tools(c).index("theme_directions")
                    < (tools(c).index("theme_save") if "theme_save" in tools(c) else 99)
                ),
            ),
            ("a draft that passes the checks", saved_ok),
            ("a preview card after saving", lambda c: "theme_preview" in tools(c)),
            (
                "honest about sizes (titles can't grow much)",
                lambda c: said(c, "size", "same size", "taille", turn=-1),
            ),
        ],
    ),
    (
        "photo-behind",
        [
            "Put a photo of my garden behind every page, and make all the panels see-through so we see it everywhere.",
            "It's a green garden with lots of flowers, quite busy. I love it.",
        ],
        [
            (
                "raises readability over a busy picture",
                lambda c: said(c, "contrast", "readab", "legib", "read", least=1),
            ),
            (
                "offers a veil / framed titles / grounds, not glass",
                lambda c: said(
                    c,
                    "veil",
                    "scrim",
                    "dim",
                    "frame",
                    "framed",
                    "ground",
                    "plaque",
                    "behind the posters",
                    least=1,
                ),
            ),
            (
                "keeps it short (≤ 2 questions per message)",
                lambda c: all(t["reply"].count("?") <= 2 for t in c["turns"]),
            ),
        ],
    ),
    (
        "surprise",
        ["Surprise me"],
        [
            ("three distinct directions as cards", lambda c: directions_count(c) >= 3),
            ("no build before the person chooses", lambda c: "theme_save" not in tools(c)),
        ],
    ),
    (
        "kid-fr",
        [
            "Je veux un thème pastel tout doux pour la chambre de ma fille de 8 ans, elle adore les licornes.",
            "Plutôt clair. Elle utilise surtout la tablette.",
        ],
        [
            (
                "answers in French, never vous",
                lambda c: said(c, " la ", " le ", " une ") and not said(c, " vous ", "votre"),
            ),
            (
                "pastel caveat: contrast / readability",
                lambda c: said(c, "contraste", "lisib", "lire", least=1),
            ),
            (
                "no copied characters (unicorns stay generic)",
                lambda c: not said(c, "my little pony", "disney"),
            ),
        ],
    ),
]

RUBRIC = """You are reviewing a conversation where "Nox", a home app's assistant, helps a person design
a visual theme for their home app. Score each criterion from 1 (poor) to 5 (excellent), strictly:
1. brainstorm: covers the aspects that matter (feeling/source, light/dark, colour, type, shapes and
   materials, pictures/art, the mascot and small pieces, words, motion), without asking about all
   of them at once — Nox decides the ones the person doesn't care about.
2. caveats: raises what the person didn't think of (legibility and contrast, pictures behind text,
   transparency, sizes that never change, phones vs tablets, colour-blind safe statuses) kindly and
   with a better version.
3. cohesion: the proposal feels like one world (colours, type, shapes, pieces and words from one
   source), with a reason for each choice.
4. walkthrough: one step at a time, at most one or two questions per message, never a wall of
   text; the person always knows where they are and what comes next.
5. formatting: easy to scan (short paragraphs or bullets, bold for key words, a few emojis as
   markers at most), ADHD-friendly, in the person's language.
6. honesty: never claims something is saved, passing or looks a certain way without a tool result.
Reply with JSON only: {"brainstorm": n, "caveats": n, "cohesion": n, "walkthrough": n,
"formatting": n, "honesty": n, "notes": "two or three sentences: the most important fix"}"""


def metrics(reply):
    words = len(reply.split())
    return {
        "words": words,
        "questions": reply.count("?"),
        "emojis": len(EMOJI.findall(reply)),
        "bullets": sum(1 for line in reply.splitlines() if line.strip().startswith(("-", "•", "*", "1."))),
    }


def judge(convo):
    transcript = "\n\n".join(
        f"PERSON: {t['user']}\nNOX: {t['reply']}\n[tools: {', '.join(c[0] for c in t['calls']) or 'none'}]"
        for t in convo["turns"]
    )
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + KEY},
        json={
            "model": JUDGE,
            "messages": [
                {"role": "system", "content": RUBRIC},
                {
                    "role": "user",
                    "content": f"The conversation so far ({len(convo['turns'])} turns of a longer one: judge what "
                    "should be there by this point):\n\n" + transcript,
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 1500,
        },
        timeout=120,
    )
    text = response.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(text[text.index("{") : text.rindex("}") + 1])
    except ValueError:
        return {"notes": "judge answer unreadable: " + text[:200]}


def setup():
    settings.runtime_root = Path(tempfile.mkdtemp(prefix="theme-studio-eval-"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    owner = User(
        id=new_id(),
        name="Ada",
        username="ada",
        password_hash="eval",
        role="admin",
        permissions=list(RESIDENT),
    )
    db.add(owner)
    db.commit()
    cfg = {
        "api_key": KEY,
        "model": MODEL,
        "reasoning_effort": "medium",
        "max_output_tokens": 6000,
        "input_microusd_per_million": 1,
        "output_microusd_per_million": 1,
    }
    a.integration_config = lambda db, name: dict(cfg)
    assistant_profiles.assignment = lambda db, purpose: {
        "provider": "openrouter",
        "model": MODEL,
        "reasoning_effort": "medium",
    }
    assistant_profiles.apply_assignment = lambda db, cfg, selected: None

    def reserve(db, actor, provider, config, messages, schemas):
        row = Usage(user_id=actor.id, provider="openrouter", model=MODEL, reserved_microusd=1)
        db.add(row)
        db.commit()
        return row.id

    a.reserve = reserve
    return db, Actor(owner.id, owner.name, "admin", RESIDENT)


def run(selected):
    db, actor = setup()
    calls = []
    original = a.tool_registry

    def registry(context):
        found = original(context)

        def watched(name, handler):
            def call(body, who, session):
                result = handler(body, who, session)
                calls.append((name, body.model_dump(mode="json") if body is not None else {}, result))
                return result

            return call

        return {name: (model, desc, watched(name, handler)) for name, (model, desc, handler) in found.items()}

    a.tool_registry = registry
    report = []
    for name, turns, checks in SCENARIOS:
        if selected and selected not in name:
            continue
        convo, conversation, start = {"name": name, "turns": []}, None, time.monotonic()
        for message in turns:
            calls.clear()
            message, preset = message if isinstance(message, tuple) else (message, None)
            body = a.Chat(
                message=message,
                conversation_id=conversation,
                purpose="themes",
                preset=preset,
                idempotency_key=new_id(),
            )
            try:
                turn = a.open_turn(body, actor, db)
                out = a.finish_turn(turn, db)
                conversation = out["conversation_id"]
                reply, cards = out.get("reply") or "", out.get("cards") or []
            except Exception as exc:  # noqa: BLE001 - a failed turn is a result
                reply, cards = f"[turn failed: {type(exc).__name__}: {exc}]", []
            convo["turns"].append(
                {
                    "user": message,
                    "reply": reply,
                    "cards": [c.get("kind") or c.get("type") for c in cards if isinstance(c, dict)],
                    "calls": [(n, args, result) for n, args, result in calls],
                    "metrics": metrics(reply),
                }
            )
        convo["checks"] = {label: bool(fn(convo)) for label, fn in checks}
        # A provider failure (no credit, an outage) measures nothing: say so instead of judging it.
        failed = [
            t["reply"]
            for t in convo["turns"]
            if "PROVIDER_" in t["reply"] or t["reply"].startswith("[turn failed")
        ]
        convo["judge"] = {"notes": "not measured: " + failed[0][:160]} if failed else judge(convo)
        convo["seconds"] = round(time.monotonic() - start)
        report.append(convo)
        passed = sum(convo["checks"].values())
        scores = {k: v for k, v in convo["judge"].items() if k != "notes"}
        worst = max((t["metrics"]["words"] for t in convo["turns"]), default=0)
        print(
            f"{name:14} checks {passed}/{len(checks)}  judge {scores}  longest {worst} words  {convo['seconds']} s"
        )
        for label, ok in convo["checks"].items():
            if not ok:
                print("   ✗", label)
        print("   note:", convo["judge"].get("notes", ""))
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print("transcripts:", OUT)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
