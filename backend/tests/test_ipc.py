import socket
import threading
from houseos import ipc


def test_ipc_request_reply_eof_oversize_and_missing(tmp_path):
    path = str(tmp_path / "s.sock")
    server = socket.socket(socket.AF_UNIX)
    server.bind(path)
    server.listen()

    def serve():
        for reply in (b'{"ok":1}\n', b'{"ok":2}', b"x" * 100 + b"\n"):
            conn, _ = server.accept()
            conn.recv(100)
            conn.sendall(reply)
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    assert ipc.request(path, {"a": 1}, timeout=1, failure="F") == {"ok": 1}
    assert ipc.request(path, {"a": 1}, timeout=1, failure="F") == {"ok": 2}
    assert ipc.request(path, {"a": 1}, timeout=1, limit=50, failure="F") == "F"
    assert ipc.request(str(tmp_path / "missing"), {}, timeout=1, failure="F") == "F"
    server.close()


def test_fetcher_passes_a_search_limit_through(monkeypatch):
    # A search's `limit` (how many results) reaches the fetcher; it never caps the reply's bytes.
    from houseos.config import settings

    seen = {}
    monkeypatch.setattr(settings, "external_fetch_enabled", True)
    monkeypatch.setattr(ipc, "request", lambda path, payload, **kw: seen.update(payload=payload, **kw))
    ipc.fetcher("search", timeout=5, query="song", limit=5)
    assert seen["payload"]["limit"] == 5 and seen["limit"] == 128000
