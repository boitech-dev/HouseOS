"""Personal unmodified Claude Code, native sign-in; no OAuth token/API proxy.

The user signs in through the CLI itself: `claude setup-token` runs in a private terminal,
HouseOS shows its sign-in link and passes back the code, and the resulting token stays in
the bridge profile (or the CLI's own login from a desktop terminal is used). Built-ins and
customizations are disabled; JSON tool proposals return to HouseOS's authorization and
confirmation dispatcher.
"""

import asyncio
import contextlib
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import termios
from urllib.parse import urlsplit
import uuid

from .codex_bridge import BridgeError, MAX_BYTES, STUDIO_BYTES, serve
from .assistant_prompt import BRIDGE_SUFFIX
from .config import settings

PROFILE = settings.runtime_root / "claude"
ALIASES = ("default", "sonnet", "opus", "haiku")
# The current family by full id, so a picker can offer "Claude Opus 5.5"; the account decides access.
MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-opus-5": "Claude Opus 5",
    "claude-sonnet-5": "Claude Sonnet 5",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "claude-fable-5-1": "Claude Fable 5.1",
}
SIGN_IN_HOSTS = ("claude.com", "claude.ai", "anthropic.com")
TOKEN = re.compile(r"sk-ant-oat[\w-]{20,400}")


def masked(text):
    """For the journal: never a token or a pasted code."""
    return re.sub(r"sk-ant-[\w-]+|[\w-]{16,}#[\w-]+", "…", text)


def plain(raw):
    """Terminal output as text: cursor-forward moves become spaces, other escapes vanish."""
    text = re.sub(r"\x1b\[(\d*)C", lambda m: " " * int(m.group(1) or 1), raw.decode(errors="replace"))
    return re.sub(r"\x1b(\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[()][0-9A-Za-z]|.)", "", text)


def output_schema(schemas):
    """Scope each tool's local JSON refs before nesting it in the result schema."""
    variants = []
    for index, tool in enumerate(schemas):
        name = tool.get("name", "")
        if not re.fullmatch(r"[A-Za-z_][\w-]{0,63}", name):
            raise BridgeError("INVALID_TOOLS")
        prefix = f"#/properties/calls/items/anyOf/{index}/properties/args/"

        def relocate(value):
            if isinstance(value, dict):
                return {
                    key: prefix + item[2:]
                    if key == "$ref" and isinstance(item, str) and item.startswith("#/")
                    else relocate(item)
                    for key, item in value.items()
                }
            return [relocate(item) for item in value] if isinstance(value, list) else value

        variants.append(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "enum": [name]},
                    "args": relocate(tool["parameters"]),
                },
                "required": ["name", "args"],
                "description": tool.get("description", ""),
            }
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reply": {"type": "string"},
            "calls": {
                "type": "array",
                "maxItems": 1,
                "items": {"anyOf": variants} if variants else {"type": "null"},
                **({} if variants else {"maxItems": 0}),
            },
        },
        "required": ["reply", "calls"],
    }


OUTDATED = re.compile(r"does not support this model|version [\d.]+ or newer is required", re.I)


def failure(result) -> bool:
    """The CLI's own error line in the journal (never a token), so a failed round can be diagnosed.
    True when the model needs a newer Claude Code than this one."""
    if result.get("is_error") and result.get("result"):
        print(
            "claude round failed:",
            result.get("subtype"),
            TOKEN.sub("[token]", str(result["result"]))[:200],
            flush=True,
        )
    return bool(OUTDATED.search(str(result.get("result") or "")))


def effort(body):
    """The assistant's chosen reasoning effort; low unless the admin picked more."""
    return body.get("effort") if body.get("effort") in {"low", "medium", "high"} else "low"


def studio_images(images):
    """At most four images, already downscaled JPEG, PNG or WebP by HouseOS; anything else fails."""
    if images in (None, []):
        return []
    if not isinstance(images, list) or len(images) > 4:
        raise BridgeError("INVALID_IMAGES")
    checked = []
    for image in images:
        if (
            not isinstance(image, dict)
            or image.get("media_type") not in {"image/jpeg", "image/png", "image/webp"}
            or not isinstance(image.get("data"), str)
            or not 0 < len(image["data"]) <= 1_800_000
            or not re.fullmatch(r"[A-Za-z0-9+/=]+", image["data"])
        ):
            raise BridgeError("INVALID_IMAGES")
        checked.append({"media_type": image["media_type"], "data": image["data"]})
    return checked


class Claude:
    def __init__(self, profile=PROFILE, binary=None):
        self.profile, self.binary = Path(profile), binary or settings.claude_bin
        self.token_file = self.profile / "oauth-token"
        self.login = None  # pending `claude setup-token`: (process, terminal, output so far)

    async def start(self):
        self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.profile / "empty").mkdir(exist_ok=True, mode=0o700)

    async def close(self):
        pass

    def environment(self, limit=4096):
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self.profile),
            "CLAUDE_CONFIG_DIR": str(self.profile),
            "LANG": "C.UTF-8",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(limit),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        if self.token_file.exists():
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self.token_file.read_text().strip()
        return env

    async def login_start(self):
        await self.login_cancel()
        env = {**self.environment(), "TERM": "xterm-256color"}
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        master, terminal = pty.openpty()
        # Wide enough that neither the sign-in link nor the token is wrapped.
        fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 1000, 0, 0))
        try:
            process = await asyncio.create_subprocess_exec(
                self.binary,
                "setup-token",
                cwd=self.profile / "empty",
                env=env,
                stdin=terminal,
                stdout=terminal,
                stderr=terminal,
                start_new_session=True,
            )
        except OSError:
            os.close(master)
            raise
        finally:
            os.close(terminal)
        self.login = (process, master, bytearray())
        link = (await self.expect(r"(https://\S+)\s[\s\S]*Paste\s*code")).group(1)
        host = urlsplit(link).hostname or ""
        if not link.startswith("https://") or not any(
            host == name or host.endswith("." + name) for name in SIGN_IN_HOSTS
        ):
            await self.login_cancel()
            raise BridgeError("CLAUDE_LOGIN_URL_REJECTED")
        return {"status": "pending", "verification_url": link, "needs_code": True}

    async def login_code(self, code):
        if not self.login:
            print(
                "claude sign-in: a code arrived but no sign-in is waiting (restarted, or cancelled)",
                flush=True,
            )
            raise BridgeError("CLAUDE_LOGIN_FAILED")
        if not re.fullmatch(r"[\w#.~-]{8,2048}", code):
            print(f"claude sign-in: the pasted code has an unexpected shape ({len(code)} chars)", flush=True)
            raise BridgeError("CLAUDE_LOGIN_FAILED")
        raw = self.login[2]
        start = len(raw)
        # Type the code, then press Enter on its own: the CLI takes a long burst ending in
        # Enter as a paste and keeps the Enter in the text, so a real (92-character) code was
        # never submitted.
        os.write(self.login[1], code.encode())
        await asyncio.sleep(0.5)
        os.write(self.login[1], b"\r")
        try:
            # The token, or Claude refusing the code (expired, or from an earlier sign-in page).
            found = await self.expect(r"sk-ant-oat[\w-]{20,400}|OAuth error[^\n]*", timeout=55, since=start)
        except BridgeError:
            print("claude sign-in did not finish:", masked(plain(raw[start:]))[-300:], flush=True)
            await self.login_cancel()
            raise
        print("claude sign-in: Claude answered the code", flush=True)
        if found.group(0).startswith("OAuth error"):
            print("claude sign-in:", masked(found.group(0))[:200], flush=True)
            # The CLI offers a retry with a fresh sign-in page: take it, so the resident only
            # opens the new page and pastes its code.
            again = len(raw)
            os.write(self.login[1], b"\r")
            try:
                link = (await self.expect(r"(https://\S+)\s[\s\S]*Paste\s*code", since=again)).group(1)
            except BridgeError:
                await self.login_cancel()
                raise BridgeError("CLAUDE_LOGIN_CODE_REJECTED") from None
            return {"status": "code_rejected", "verification_url": link, "needs_code": True}
        # Read from the raw terminal bytes: the token ends where an escape or line break begins.
        token = re.search(r"sk-ant-oat[\w-]{20,400}", bytes(raw[start:]).decode(errors="replace"))
        await self.login_cancel()
        return self.login_token(token.group(0) if token else found.group(0))

    def login_token(self, token):
        """Keep a token from `claude setup-token` (here or elsewhere); it reaches only the CLI's environment."""
        if not TOKEN.fullmatch(token):
            raise BridgeError("CLAUDE_TOKEN_INVALID")
        descriptor = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(token)
        return {"status": "signed_in"}

    async def login_cancel(self):
        if self.login:
            process, master, _ = self.login
            self.login = None
            os.close(master)
            with contextlib.suppress(ProcessLookupError):  # it may have exited already
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        return {"status": "cancelled"}

    async def expect(self, pattern, timeout=20, since=0):
        """Read the sign-in terminal until its text (from byte `since`) matches `pattern`; fail if
        it ends first."""
        _, master, raw = self.login
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while not (match := re.search(pattern, plain(raw[since:]))):
            ready, _, _ = await asyncio.to_thread(select.select, [master], [], [], 0.2)
            chunk = b""
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:  # EIO: the command exited and closed its terminal
                    pass
            if (ready and not chunk) or loop.time() > end or len(raw) > MAX_BYTES:
                raise BridgeError("CLAUDE_LOGIN_FAILED")
            raw.extend(chunk)
        return match

    async def invoke(self, arguments, content="", limit=4096, timeout=50, deadline=None, stream=False):
        process = await asyncio.create_subprocess_exec(
            self.binary,
            "--safe-mode",
            *arguments,
            cwd=self.profile / "empty",
            env=self.environment(limit),
            start_new_session=True,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=(STUDIO_BYTES if stream else MAX_BYTES) + 1,
        )
        try:
            async with asyncio.timeout(timeout):
                process.stdin.write(content.encode())
                await process.stdin.drain()
                process.stdin.close()
                if stream:  # stream-json: keep only the final result line
                    return await self.result_line(process)
                raw = bytearray()
                while chunk := await process.stdout.read(8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise BridgeError("CLAUDE_OUTPUT_LIMIT")
                await process.wait()
                # Native auth status returns nonzero when signed out, with valid JSON.
                result = json.loads(raw)
                if process.returncode and "loggedIn" not in result:
                    raise BridgeError(
                        "CLAUDE_UPDATE_REQUIRED" if failure(result) else "CLAUDE_REQUEST_FAILED"
                    )
                return result
        finally:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await asyncio.wait_for(
                    process.wait(),
                    max(0.01, min(0.5, deadline - asyncio.get_running_loop().time())) if deadline else 0.5,
                )

    async def result_line(self, process):
        """The stream's last `result` line (it carries structured_output and usage); search
        results and progress lines before it are read and dropped, each one bounded."""
        result = None
        try:
            while line := await process.stdout.readline():
                if b'"type":"result"' in line or b'"type": "result"' in line:
                    result = json.loads(line)
        except ValueError:  # one line over the lane's limit, or not JSON
            raise BridgeError("CLAUDE_OUTPUT_LIMIT") from None
        await process.wait()
        if result is None:
            raise BridgeError("CLAUDE_REQUEST_FAILED")
        return result

    async def status(self):
        result = await self.invoke(["auth", "status", "--json"], timeout=10)
        return {
            "status": "ok",
            "logged_in": bool(result.get("loggedIn")),
            "auth_mode": result.get("authMethod") if result.get("loggedIn") else None,
            "version": await self.version(),
        }

    async def version(self):
        """The client's version, e.g. "2.1.283" (new models need recent ones)."""
        try:
            process = await asyncio.create_subprocess_exec(
                self.binary, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            out, _ = await asyncio.wait_for(process.communicate(), 10)
        except (OSError, TimeoutError):
            return None
        return (out.decode().split() or [None])[0]

    async def action(self, body):
        action = body.get("action")
        if action == "status":
            return await self.status()
        if action == "models":
            return {
                "status": "ok",
                "items": [
                    {
                        "id": name,
                        "name": name.title(),
                        "description": "Native Claude Code alias; availability depends on your own account",
                    }
                    for name in ALIASES
                ]
                + [
                    {"id": name, "name": title, "description": "Availability depends on your own account"}
                    for name, title in MODELS.items()
                ],
                "catalog_kind": "documented_native_aliases",
                "availability_verified": False,
                "source": "https://code.claude.com/docs/en/model-config",
            }
        if action == "login_start":
            return await self.login_start()
        if action == "login_code":
            return await self.login_code(str(body.get("code", "")))
        if action == "login_token":
            return self.login_token(str(body.get("token", "")))
        if action == "login_cancel":
            return await self.login_cancel()
        if action == "logout":
            self.token_file.unlink(missing_ok=True)
            # Also sign out a login made with the CLI itself; it fails harmlessly when there is none.
            # Native logout may emit plain text; never return it as private content.
            try:
                await self.invoke_logout()
            except BridgeError:
                pass
            if (await self.status())["logged_in"]:
                raise BridgeError("CLAUDE_LOGOUT_FAILED")
            return {"status": "signed_out"}
        if action != "round":
            raise BridgeError("UNKNOWN_ACTION")
        studio = body.get("lane") == "studio"
        budget = min(600.0 if studio else 60.0, max(0.1, float(body.get("timeout_seconds", 20))))
        deadline = asyncio.get_running_loop().time() + budget
        try:
            async with asyncio.timeout(max(0.05, budget - min(0.75, budget / 2))):
                return await self.round(body, deadline)
        except TimeoutError:
            raise BridgeError("CLAUDE_TIMEOUT")

    async def round(self, body, deadline=None):
        model, messages, tools = body.get("model"), body.get("messages"), body.get("schemas", [])
        studio = body.get("lane") == "studio"
        images = studio_images(body.get("images")) if studio else []
        if not isinstance(model, str) or not re.fullmatch(r"[\w.\[\]:-]{1,128}", model):
            raise BridgeError("INVALID_MODEL")
        if (
            not isinstance(messages, list)
            or not 1 <= len(messages) <= 100
            or not isinstance(tools, list)
            or len(tools) > 32
        ):
            raise BridgeError("INVALID_CONTEXT")
        # No sign-in pre-check: it would start the CLI twice per round. A signed-out account
        # fails the call below, and the failure path then says CLAUDE_SIGN_IN_REQUIRED.
        limit = max(256, min(32000 if studio else 4096, int(body.get("max_output_tokens", 4096))))
        schema = output_schema(tools)
        # The theme studio may search the web (Anthropic runs the search; nothing is fetched
        # from here). Everything else has no host tools at all.
        searching = studio and body.get("web_search") is True
        arguments = [
            "--print",
            "--tools",
            "WebSearch" if searching else "",
            *(["--allowedTools", "WebSearch"] if searching else []),
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--permission-mode",
            "dontAsk",
            *(
                ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
                if studio
                else ["--output-format", "json"]
            ),
            "--json-schema",
            json.dumps(schema),
            "--model",
            model,
            "--effort",
            effort(body),
            "--system-prompt",
            body.get("policy", "") + BRIDGE_SUFFIX,
        ]
        conversation = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        if studio:  # one user message: the conversation as text, then the person's images
            conversation = (
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": conversation}]
                            + [{"type": "image", "source": {"type": "base64", **image}} for image in images],
                        },
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
        try:
            raw = await self.invoke(
                arguments,
                conversation,
                limit,
                timeout=max(1.0, deadline - asyncio.get_running_loop().time()) if deadline else 50,
                deadline=deadline,
                stream=studio,
            )
        except BridgeError as error:
            if str(error) != "CLAUDE_REQUEST_FAILED":
                raise
            raw = {"is_error": True}
        if raw.get("is_error") or raw.get("subtype") not in {None, "success"}:
            if failure(raw):
                raise BridgeError("CLAUDE_UPDATE_REQUIRED")
            # An expired or revoked sign-in fails here, and the CLI then forgets it: say so.
            if not (await self.status())["logged_in"]:
                raise BridgeError("CLAUDE_SIGN_IN_REQUIRED")
            raise BridgeError("CLAUDE_TURN_FAILED")
        result = raw.get("structured_output")
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("reply"), str)
            or not isinstance(result.get("calls"), list)
            or len(result["calls"]) > 1
        ):
            raise BridgeError("CLAUDE_INVALID_OUTPUT")
        allowed = {tool["name"] for tool in tools}
        calls = []
        for call in result["calls"]:
            if (
                not isinstance(call, dict)
                or call.get("name") not in allowed
                or not isinstance(call.get("args"), dict)
            ):
                raise BridgeError("CLAUDE_INVALID_TOOL_CALL")
            calls.append({"id": "houseos-" + str(uuid.uuid4()), "name": call["name"], "args": call["args"]})
        content = ([{"type": "text", "text": result["reply"]}] if result["reply"] else []) + [
            {"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]}
            for call in calls
        ]
        reported = raw.get("usage") or {}
        base = reported.get("input_tokens")
        cached = reported.get("cache_read_input_tokens")
        written = reported.get("cache_creation_input_tokens")
        return {
            "reply": result["reply"],
            "calls": calls,
            "wire": {"role": "assistant", "content": content},
            "usage": {
                "input_tokens": base + (cached or 0) + (written or 0) if isinstance(base, int) else None,
                "output_tokens": reported.get("output_tokens"),
                "cached_tokens": cached,
                "cache_write_tokens": written,
            },
        }

    async def invoke_logout(self):
        process = await asyncio.create_subprocess_exec(
            self.binary,
            "--safe-mode",
            "auth",
            "logout",
            env=self.environment(),
            cwd=self.profile / "empty",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.wait(), 10)
            if process.returncode:
                raise BridgeError("CLAUDE_LOGOUT_FAILED")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


if __name__ == "__main__":
    from .events import restart_on_request

    restart_on_request("claude")
    asyncio.run(serve(Claude(), settings.claude_socket, lanes=("default", "studio")))
