"""One authorized, seekable media input for a network-isolated parser."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import re
import socketserver
import threading
import tempfile

_HEADERS = {"content-length", "content-range", "accept-ranges", "content-type"}


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, address)

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.connection.settimeout(1)
        byte_range = self.headers.get("Range")
        if (
            self.path != "/source"
            or byte_range
            and (len(byte_range) > 80 or not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", byte_range))
        ):
            self.send_error(400)
            return
        chunks = None
        try:
            if self.server.stopping.is_set() or self.server.cancelled():
                self.send_error(410)
                return
            status, headers, chunks = self.server.opener(byte_range, self.command == "HEAD")
            if self.server.stopping.is_set() or self.server.cancelled():
                self.send_error(410)
                return
            self.send_response(status)
            for name, value in headers.items():
                if name.lower() in _HEADERS and "\r" not in str(value) and "\n" not in str(value):
                    self.send_header(name, str(value))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                for chunk in chunks:
                    if self.server.stopping.is_set() or self.server.cancelled():
                        break
                    self.wfile.write(chunk)
        except (OSError, ValueError):
            pass
        except Exception:
            # Provider errors must not reveal credentials or source URLs to the parser.
            if not self.wfile.closed:
                self.close_connection = True
        finally:
            if hasattr(chunks, "close"):
                chunks.close()


@contextmanager
def input_broker(directory: Path, opener, cancelled=lambda: False):
    """opener(range, head) returns status, headers, chunks; it owns URL validation.

    The caller supplies a thread-safe cancellation check and a bounded-time opener.
    No account credential or URL crosses the socket boundary.
    """
    # AF_UNIX paths are limited to 108 bytes; workflow UUID directories exceed it.
    temporary = tempfile.TemporaryDirectory(prefix="houseos-stream-")
    path = Path(temporary.name) / "input.sock"
    try:
        server = _Server(str(path), _Handler)
    except BaseException:
        temporary.cleanup()
        raise
    path.chmod(0o600)
    server.slots = threading.BoundedSemaphore(8)
    server.stopping = threading.Event()
    server.opener, server.cancelled = opener, cancelled
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        yield path
    finally:
        server.stopping.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        path.unlink(missing_ok=True)
        temporary.cleanup()


def streaming_media_command(args: list[str], socket_path: Path, output_directory: Path) -> list[str]:
    """Replace literal INPUT with an isolated loopback URL, never a provider URL."""
    import json

    output = str(output_directory.resolve())
    rewritten = [arg.replace(output, "/output") for arg in args]
    bridge = str(Path(__file__).with_name("stream_bridge.py").resolve())
    return [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind",
        "/etc/ld.so.cache",
        "/etc/ld.so.cache",
        "--dev",
        "/dev",
        "--dir",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(socket_path.resolve()),
        "/input.sock",
        "--ro-bind",
        bridge,
        "/bridge.py",
        "--bind",
        output,
        "/output",
        "/usr/bin/python3",
        "/bridge.py",
        json.dumps(rewritten),
    ]
