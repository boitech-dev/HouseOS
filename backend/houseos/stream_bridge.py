"""Sandbox-only fixed-resource HTTP bridge. No provider URLs or credentials."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import signal
import socket
import subprocess
import sys
import threading


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect("/input.sock")


class Server(ThreadingHTTPServer):
    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.connection.settimeout(1)
        if self.path != "/source":
            self.send_error(404)
            return
        connection = UnixConnection("localhost", timeout=30)
        try:
            headers = {"Range": self.headers["Range"]} if self.headers.get("Range") else {}
            connection.request(self.command, "/source", headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() in {"content-length", "content-range", "accept-ranges", "content-type"}:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                while data := response.read(64 * 1024):
                    self.wfile.write(data)
        except (OSError, http.client.HTTPException):
            self.close_connection = True
        finally:
            connection.close()


def main():
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    args = json.loads(sys.argv[1])
    args = [f"http://127.0.0.1:{server.server_port}/source" if arg == "INPUT" else arg for arg in args]
    process = subprocess.Popen(args)

    def terminate(*_):
        process.terminate()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        return process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
