"""Newline-delimited JSON request/response over a private local Unix socket."""

import json
import socket


def request(path, payload, *, timeout, limit=65536, failure):
    """Return the decoded reply, or `failure` when the peer is absent, slow, silent or oversized."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            client.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
            with client.makefile("rb") as stream:
                line = stream.readline(limit + 1)
        return failure if len(line) > limit else json.loads(line)
    except (OSError, ValueError):
        return failure


def fetcher(action, *, timeout, reply_limit=128000, **payload):
    """One request to the house's fetcher, refused while outside fetching is switched off.
    `reply_limit` caps the reply in bytes; anything else (a search's `limit`…) goes to the fetcher."""
    from .config import settings

    if not settings.external_fetch_enabled:
        return {"status": "blocked", "code": "FETCH_SANDBOX_NOT_VERIFIED"}
    return request(
        settings.runtime_root / "run/fetch.sock",
        {"action": action, **payload},
        timeout=timeout,
        limit=reply_limit,
        failure={"status": "failed", "code": "FETCH_UNAVAILABLE"},
    )
