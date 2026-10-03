"""Use the same bounded private transport for the personal Claude Code bridge."""

from .codex_client import request as _request
from .config import settings


def request(action, **fields):
    result = _request(action, _socket_path=settings.claude_socket, **fields)
    if result.get("error", "").startswith("CODEX_"):
        result["error"] = result["error"].replace("CODEX_", "CLAUDE_", 1)
    return result
