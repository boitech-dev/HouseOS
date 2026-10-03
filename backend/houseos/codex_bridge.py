"""Private Codex app-server adapter. Never executes a HouseOS/model-selected tool.

Native OAuth stays in a dedicated CODEX_HOME. Dynamic tool requests cross back to
HouseOS's existing permission/confirmation dispatcher; Codex threads are ephemeral.
"""

import asyncio
import json
import os
from pathlib import Path
import pwd
import re
import socket
import struct
from urllib.parse import urlsplit
from .assistant_prompt import BRIDGE_SUFFIX
from .config import settings

PROFILE = settings.runtime_root / "codex"
MAX_BYTES = 262144
# The theme studio's lane (Claude only): its own lock, so a long studio round never makes
# everyday Nox busy, a longer round, and room for a few downscaled images.
STUDIO_BYTES, STUDIO_SECONDS = 8_000_000, 605
# Explicitly disable host abilities; empty turn environments remove environment tools.
CONFIG = {
    "approval_policy": "never",
    "sandbox_mode": "read-only",
    "cli_auth_credentials_store": "file",
    "web_search": "disabled",
    "agents.enabled": False,
    "apps._default.enabled": False,
    "analytics.enabled": False,
    "history.persistence": "none",
    "project_doc_max_bytes": 0,
    "shell_environment_policy.inherit": "none",
    **{
        "features." + name: False
        for name in (
            "shell_tool",
            "unified_exec",
            "apply_patch_freeform",
            "apps",
            "plugins",
            "memories",
            "memory_tool",
            "multi_agent",
            "multi_agent_v2",
            "js_repl",
            "code_mode",
            "browser_use",
            "computer_use",
            "image_generation",
            "view_image",
            "goals",
            "hooks",
            "codex_hooks",
            "plugin_hooks",
            "request_permissions",
            "request_permissions_tool",
            "tool_search",
            "workspace_dependencies",
            "shell_snapshot",
            "shell_snapshot_v2",
        )
    },
    "features.skip_host_skill_discovery": True,
}


def effort(body):
    """The assistant's chosen reasoning effort; low unless the admin picked more."""
    return body.get("effort") if body.get("effort") in {"low", "medium", "high"} else "low"


class BridgeError(Exception):
    pass


class AppServer:
    def __init__(self, profile=PROFILE):
        self.profile = Path(profile)
        self.pending = {}
        self.events = asyncio.Queue(maxsize=512)
        self.serial = 0
        self.process = None
        self.reader_task = None

    async def start(self):
        self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        workspace = self.profile / "empty"
        workspace.mkdir(exist_ok=True, mode=0o700)
        command = [settings.codex_bin, "app-server", "--listen", "stdio://"]
        for key, value in CONFIG.items():
            command += ["-c", key + "=" + json.dumps(value)]
        # A clean child environment prevents workstation credentials/config inheritance.
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self.profile),
            "CODEX_HOME": str(self.profile),
            "LANG": "C.UTF-8",
        }
        self.process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=2 * 1024 * 1024,
        )
        self.reader_task = asyncio.create_task(self.read())
        await self.rpc(
            "initialize",
            {"clientInfo": {"name": "houseos", "version": "1.0"}, "capabilities": {"experimentalApi": True}},
        )
        await self.write({"method": "initialized", "params": {}})

    async def write(self, value):
        self.process.stdin.write(json.dumps(value, separators=(",", ":")).encode() + b"\n")
        await self.process.stdin.drain()

    async def read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" not in message:
                    future = self.pending.pop(message.get("id"), None)
                    if future is not None and not future.done():
                        if "error" in message:
                            future.set_exception(BridgeError("CODEX_REQUEST_FAILED"))
                        else:
                            future.set_result(message.get("result", {}))
                else:
                    self.events.put_nowait(message)
        except (ValueError, asyncio.QueueFull, OSError):
            pass
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(BridgeError("CODEX_DISCONNECTED"))
            self.pending.clear()

    async def rpc(self, method, params=None, timeout=20):
        self.serial += 1
        identity = self.serial
        future = asyncio.get_running_loop().create_future()
        self.pending[identity] = future
        await self.write({"id": identity, "method": method, "params": params or {}})
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(identity, None)

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader_task:
            self.reader_task.cancel()

    async def round(self, body):
        budget = min(60.0, max(0.1, float(body.get("timeout_seconds", 20))))
        try:
            async with asyncio.timeout(max(0.05, budget - min(0.75, budget / 2))):
                return await self._round(body)
        except TimeoutError:
            # Abort the native turn, not just its caller's socket. Nothing is replayed.
            if self.process and self.process.returncode is None:
                self.process.kill()
                try:
                    await asyncio.wait_for(self.process.wait(), min(0.5, budget / 2))
                except TimeoutError:
                    pass
            if self.reader_task:
                self.reader_task.cancel()
            raise BridgeError("CODEX_TIMEOUT")

    async def _round(self, body):
        model, messages, schemas = body.get("model"), body.get("messages"), body.get("schemas", [])
        policy = body.get("policy", "")
        if not isinstance(model, str) or not re.fullmatch(r"[\w./:-]{1,128}", model):
            raise BridgeError("INVALID_MODEL")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 100 or not isinstance(policy, str):
            raise BridgeError("INVALID_CONTEXT")
        if not isinstance(schemas, list) or len(schemas) > 32:
            raise BridgeError("INVALID_TOOLS")
        tools = []
        for schema in schemas:
            if not isinstance(schema, dict) or not re.fullmatch(
                r"[A-Za-z_][\w-]{0,63}", schema.get("name", "")
            ):
                raise BridgeError("INVALID_TOOLS")
            tools.append(
                {
                    "type": "function",
                    "name": schema["name"],
                    "description": schema.get("description", ""),
                    "inputSchema": schema.get("parameters", schema.get("input_schema", {})),
                }
            )
        allowed = {tool["name"] for tool in tools}
        account = await self.rpc("account/read", {"refreshToken": False})
        if (account.get("account") or {}).get("type") != "chatgpt":
            raise BridgeError("CODEX_SIGN_IN_REQUIRED")
        while not self.events.empty():
            self.events.get_nowait()
        thread = await self.rpc(
            "thread/start",
            {
                "model": model,
                "ephemeral": True,
                "cwd": str(self.profile / "empty"),
                "environments": [],
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "dynamicTools": tools,
                "baseInstructions": policy + BRIDGE_SUFFIX,
                "config": CONFIG,
            },
        )
        thread_id = thread["thread"]["id"]
        turn_id = None
        reply, calls, usage = "", [], {}
        try:
            turn = await self.rpc(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [
                        {
                            "type": "text",
                            "text": json.dumps(messages, ensure_ascii=False, separators=(",", ":")),
                        }
                    ],
                    "environments": [],
                    "effort": effort(body),
                    "summary": "none",
                },
            )
            turn_id = turn["turn"]["id"]
            async with asyncio.timeout(50):
                while True:
                    event = await self.events.get()
                    params = event.get("params", {})
                    method = event.get("method", "")
                    if params.get("threadId") not in {None, thread_id}:
                        continue
                    if method == "item/tool/call":
                        name = params.get("tool")
                        args = params.get("arguments")
                        if name not in allowed or not isinstance(args, dict):
                            raise BridgeError("CODEX_INVALID_TOOL_CALL")
                        calls = [{"id": str(params.get("callId", event["id"])), "name": name, "args": args}]
                        # Interrupt while the dynamic tool is suspended: no tool output,
                        # success claim, extra model turn, or side effect is fabricated.
                        await self.rpc(
                            "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=5
                        )
                        break
                    if method == "item/started" and params.get("item", {}).get("type") in {
                        "commandExecution",
                        "fileChange",
                        "mcpToolCall",
                        "webSearch",
                        "imageGeneration",
                    }:
                        raise BridgeError("CODEX_UNEXPECTED_CAPABILITY")
                    if "id" in event:
                        await self.write(
                            {
                                "id": event["id"],
                                "error": {"code": -32601, "message": "Not supported by HouseOS"},
                            }
                        )
                        raise BridgeError("CODEX_UNEXPECTED_CAPABILITY")
                    if method == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
                        reply = params["item"].get("text", "")
                        if len(reply) > min(32768, max(1024, int(body.get("max_output_tokens", 4096)) * 8)):
                            raise BridgeError("CODEX_OUTPUT_LIMIT")
                    if method == "thread/tokenUsage/updated":
                        total = params.get("tokenUsage", {}).get("total", {})
                        usage = {
                            "input_tokens": total.get("inputTokens"),
                            "output_tokens": total.get("outputTokens"),
                            "cached_tokens": total.get("cachedInputTokens"),
                        }
                    if method == "turn/completed":
                        if params.get("turn", {}).get("status") != "completed":
                            raise BridgeError("CODEX_TURN_FAILED")
                        break
            wire = [
                {
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": call["name"],
                    "arguments": json.dumps(call["args"]),
                }
                for call in calls
            ]
            if reply:
                wire.append({"role": "assistant", "content": [{"type": "output_text", "text": reply}]})
            return {"reply": reply, "calls": calls, "wire": wire, "usage": usage}
        finally:
            if asyncio.current_task().cancelling():
                if self.process and self.process.returncode is None:
                    self.process.kill()
                raise asyncio.CancelledError
            if turn_id:
                try:
                    await self.rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=3)
                except (BridgeError, TimeoutError):
                    pass
            # Never retain another resident's ephemeral thread in the app-server.
            try:
                await self.rpc("thread/unsubscribe", {"threadId": thread_id}, timeout=3)
            except (BridgeError, TimeoutError):
                pass

    async def action(self, body):
        if self.reader_task and self.reader_task.done():
            await self.close()
            await self.start()
        action = body.get("action")
        if action == "status":
            result = await self.rpc("account/read", {"refreshToken": False})
            mode = (result.get("account") or {}).get("type")
            return {"status": "ok", "logged_in": mode == "chatgpt", "auth_mode": mode}
        if action == "login_start":
            result = await self.rpc("account/login/start", {"type": "chatgptDeviceCode"})
            url = urlsplit(str(result.get("verificationUrl", "")))
            if url.scheme != "https" or url.hostname != "auth.openai.com":
                raise BridgeError("CODEX_LOGIN_URL_REJECTED")
            return {
                "status": "pending",
                "login_id": result["loginId"],
                "verification_url": result["verificationUrl"],
                "user_code": result["userCode"],
            }
        if action == "login_cancel":
            await self.rpc("account/login/cancel", {"loginId": str(body.get("login_id", ""))[:128]})
            return {"status": "cancelled"}
        if action == "logout":
            await self.rpc("account/logout")
            return {"status": "signed_out"}
        if action == "models":
            items, cursor = [], None
            for _ in range(5):
                result = await self.rpc(
                    "model/list", {"limit": 100, "cursor": cursor, "includeHidden": False}
                )
                items += [
                    {
                        "id": row["model"],
                        "name": row["displayName"],
                        "description": row.get("description", "")[:500],
                    }
                    for row in result.get("data", [])
                ]
                cursor = result.get("nextCursor")
                if not cursor:
                    break
            return {"status": "ok", "items": items[:500], "truncated": bool(cursor)}
        if action == "round":
            return await self.round(body)
        raise BridgeError("UNKNOWN_ACTION")


async def serve(app=None, socket_path=None, lanes=("default",)):
    app = app or AppServer()
    # Only HouseOS, root and this bridge's own identity may call it.
    callers = {0, os.getuid()}
    try:
        callers.add(pwd.getpwnam("houseos").pw_uid)
    except KeyError:
        pass
    locks = {lane: asyncio.Lock() for lane in lanes}
    largest = STUDIO_BYTES if "studio" in locks else MAX_BYTES
    await app.start()

    async def client(reader, writer):
        try:
            # Socket ACL limits to the HouseOS service group. Disallow root? Root is
            # the host's administrator and can already control the process; no remote RPC.
            peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            _, uid, _ = struct.unpack("3i", peer)
            if uid not in callers:
                raise BridgeError("FORBIDDEN")
            raw = await asyncio.wait_for(reader.readline(), 5)
            if len(raw) > largest or not raw.endswith(b"\n"):
                raise BridgeError("REQUEST_TOO_LARGE")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise BridgeError("INVALID_REQUEST")
            lane = body.get("lane") if body.get("lane") in locks else "default"
            if lane != "studio":
                body.pop("lane", None)
                if len(raw) > MAX_BYTES:
                    raise BridgeError("REQUEST_TOO_LARGE")
            lock = locks[lane]
            try:  # a quick status check may be running: wait a moment for our turn
                await asyncio.wait_for(lock.acquire(), 10)
            except TimeoutError:
                raise BridgeError("CODEX_BUSY") from None
            try:
                async with asyncio.timeout(STUDIO_SECONDS if lane == "studio" else 65):
                    result = await app.action(body)
            finally:
                lock.release()
        except BridgeError as exc:
            result = {"error": str(exc)}
        except Exception:
            result = {"error": "CODEX_UNAVAILABLE"}
        try:
            writer.write(json.dumps(result, separators=(",", ":")).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except ConnectionError:
            pass  # the caller left (a health ping only checks that the socket answers)

    path = Path(socket_path or settings.codex_socket)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.unlink(missing_ok=True)
    server = await asyncio.start_unix_server(client, path=path, limit=largest + 1)
    os.chmod(path, 0o660)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await app.close()


if __name__ == "__main__":
    from .events import restart_on_request

    restart_on_request("codex")
    asyncio.run(serve())
