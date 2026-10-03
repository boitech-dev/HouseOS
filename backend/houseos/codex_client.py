"""Bounded transport to the private Codex bridge; no provider credentials."""

import json
from . import ipc
from .config import settings


def request(action, *, _socket_path=None, **fields):
    studio = fields.get("lane") == "studio"  # the theme studio's lane: longer rounds, images
    raw = json.dumps({"action": action, **fields}, separators=(",", ":")).encode() + b"\n"
    if len(raw) > (8_000_000 if studio else 262144):
        return {"error": "CODEX_CONTEXT_TOO_LARGE"}
    timeout = (
        min(600.0 if studio else 60.0, max(1.0, float(fields.get("timeout_seconds", 20)))) + 0.5
        if action == "round"
        # Exchanging a sign-in code can take Claude's servers well over 25 s; the bridge
        # gives up at 55 s and each bridge request ends at 65 s.
        else 62
        if action == "login_code"
        else 25
    )
    return ipc.request(
        _socket_path or settings.codex_socket,
        {"action": action, **fields},
        timeout=timeout,
        limit=262144,
        failure={"error": "CODEX_UNAVAILABLE"},
    )
