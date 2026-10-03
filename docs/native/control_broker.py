"""Privileged fixed service broker: no caller paths, shell, arguments or unit names."""

import grp
import json
import os
import pwd
import socket
import socketserver
import struct
import subprocess

UNITS = {
    name: "houseos-" + name + ".service"
    for name in (
        "api",
        "worker",
        "cinema-worker",
        "cinema-observer",
        "maintenance",
        "media",
        "upload",
        "fetch",
        "audio",
        "codex",
        "claude",
        "voice",
    )
}
SOCKET = "/run/houseos-control/control.sock"
APP = pwd.getpwnam("houseos").pw_uid
# The source checkout's owner (HOUSEOS_CODE_USER, set in this broker's unit): houseos-code.service,
# after an admin applied a change in Control Room → Changes, may only look at and restart the app
# services a change touches (deploy/code_change.py SERVICES): not the sound or TV path, no shutdown.
CODE = pwd.getpwnam(os.environ["HOUSEOS_CODE_USER"]).pw_uid if os.environ.get("HOUSEOS_CODE_USER") else APP
CODE_UNITS = {"api", "maintenance", "cinema-worker", "cinema-observer", "voice", "codex", "worker"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        _, uid, _ = struct.unpack("3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        result = {"status": "denied"}
        if uid not in {APP, CODE}:
            self.wfile.write(json.dumps(result).encode() + b"\n")
            return
        try:
            raw = self.rfile.readline(2049)
            if len(raw) > 2048:
                raise ValueError()
            data = json.loads(raw)
            if uid != APP and (
                data.get("action") not in {"restart", "status"} or data.get("service") not in CODE_UNITS
            ):
                self.wfile.write(json.dumps(result).encode() + b"\n")
                return
            if data.get("action") == "shutdown" and data.get("service") == "houseos":
                proc = subprocess.run(
                    ["/usr/bin/systemctl", "--no-block", "start", "houseos-shutdown.service"],
                    capture_output=True,
                    timeout=5,
                )
                self.wfile.write(
                    json.dumps({"status": "accepted" if proc.returncode == 0 else "failed"}).encode() + b"\n"
                )
                return
            unit = UNITS[data["service"]]
            if data["action"] == "restart":
                # --no-block avoids killing a worker before its durable acknowledgement.
                proc = subprocess.run(
                    ["/usr/bin/systemctl", "--no-block", "restart", unit], capture_output=True, timeout=5
                )
                result = {"status": "accepted" if proc.returncode == 0 else "failed"}
            elif data["action"] == "status":
                proc = subprocess.run(
                    [
                        "/usr/bin/systemctl",
                        "show",
                        unit,
                        "--property=ActiveState,SubState,ExecMainStatus,InvocationID",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                fields = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
                result = {
                    "status": "observed",
                    "active": fields.get("ActiveState"),
                    "substate": fields.get("SubState"),
                    "exit_code": fields.get("ExecMainStatus"),
                    "invocation_id": fields.get("InvocationID"),
                }
        except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
            result = {"status": "failed", "code": "SERVICE_ACTION_FAILED"}
        self.wfile.write(json.dumps(result).encode() + b"\n")


if __name__ == "__main__":
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    os.umask(0o007)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        os.chown(SOCKET, 0, grp.getgrnam("houseos").gr_gid)
        os.chmod(SOCKET, 0o660)
        server.serve_forever()
