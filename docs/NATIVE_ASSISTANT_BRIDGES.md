# Native assistant connections

These adapters run the installed, unmodified native CLIs (OpenAI's Codex and Anthropic's Claude
Code) in dedicated OS identities. They do not implement subscription-token API proxies. Each native
connection belongs to the HouseOS user who signed in; other residents must not share it.

**Docker needs none of this.** The image includes both CLIs (pinned), and the `codex` and `claude`
containers run the bridges with their own identities and a private profile in the state volume.
Sign in from Control Room → AI. The rest of this page is for native installs.

## Codex

`codex_bridge.py` owns one `codex app-server` over stdio under its own identity (for example
`houseos-codex`), with a private `CODEX_HOME` at `<runtime_root>/codex` (for example
`/opt/houseos/state/codex`). Native device-code sign-in returns a verification URL/code only after
an explicit UI action. Account status strips email/identity details. Model refresh uses the native
paginated model catalog.

Each conversation round creates an ephemeral thread with empty environments, read-only sandbox and
shell, apps, plugins, multi-agent, memory and other host tools disabled. Only current HouseOS
dynamic tools are supplied. The bridge interrupts on the first tool request and returns it for
HouseOS validation/execution. Thread unsubscribe removes the ephemeral context. It never reports
tool execution itself.

The protocol does not expose `max_output_tokens`; response bytes/characters and the caller's
deadline are bounded. Missing native token usage remains unknown. This is not a promise of an exact
generation-token cap.

## Claude Code

`claude_bridge.py` runs the unmodified Claude Code binary (`HOUSEOS_CLAUDE_BIN`, default
`/usr/local/lib/houseos/claude`) under its own identity (for example `houseos-claude`); its private
HOME and `CLAUDE_CONFIG_DIR` are `<runtime_root>/claude` (for example `/opt/houseos/state/claude`).
Sign-in stays entirely in that CLI: either its own `claude auth login` run as that identity from a
desktop terminal, or Control Room → AI → Claude subscription, which runs the CLI's own
`claude setup-token` in a private terminal. HouseOS shows its official sign-in link, the owner
pastes back the code from Anthropic's page, and the resulting one-year token is kept 0600 as
`oauth-token` in the bridge profile and passed to the CLI only as `CLAUDE_CODE_OAUTH_TOKEN`. A token
made by `claude setup-token` elsewhere can be pasted instead. Signing out deletes it.

Inference uses `--safe-mode`, which disables customizations but retains native authentication. It
also sets no built-in tools, strict empty MCP configuration, no settings sources, no session
persistence, and a schema derived from the current HouseOS tool bundle. A structured tool proposal
is validated by HouseOS before execution. Native output tokens, output bytes and time are bounded.
The model selector exposes documented native aliases, explicitly not a live account entitlement
catalog.

**Two lanes.** Everyday Nox and the theme studio each have their own lane with its own lock, so a
long studio round (up to 10 minutes) never makes Nox answer "busy". Only the studio lane may carry
pictures (at most four, already downscaled by HouseOS; up to 8 MB per request), uses
`--input-format stream-json --output-format stream-json` (the bridge keeps only the final
`result` line) and may enable one built-in tool, `WebSearch` (run on Anthropic's side; nothing is
fetched from the bridge's identity). `WebFetch` and every other built-in tool stay off in both
lanes. Deadlines are per request, so the lanes never share a timer.

Anthropic's published terms permit an end user to sign into an unmodified hosted Claude Code binary
with their own subscription, while separately restricting subscription-token proxies and
third-party Claude.ai login. This implementation relies on the personal native-CLI route and must
not be turned into a shared household subscription relay.

## Provisioning and checks (native)

Create one system identity per bridge, a private 0700 profile folder for each, and install the
pinned CLIs (Codex 0.153.4, Claude Code 2.1.263, as in the Docker image). Run the bridges as
services (`docs/native/houseos-codex.service`, `houseos-claude.service`); adapt their
paths. Nothing signs in by itself. Changing a pinned CLI version means retesting.

Clients use Unix sockets, by default `/run/houseos-{codex,claude}/bridge.sock`
(`HOUSEOS_CODEX_SOCKET`, `HOUSEOS_CLAUDE_SOCKET`; the CLIs are `HOUSEOS_CODEX_BIN`, default
`/usr/bin/codex`, and `HOUSEOS_CLAUDE_BIN`). Socket permissions and peer UID restrict callers to
HouseOS/root. Child processes receive a clean environment, no database secrets and no host
profile. The socket interface has fixed actions, request size limits and single-request
concurrency. `round.timeout_seconds` bounds setup plus generation; deadline expiration kills
outstanding native work, with no automatic retry.

Tests cover the stub protocol and structured output, refusal of unknown tools, timeout, identity
redaction, split subprocess output and the clean environment. They do not sign in or run a live
model turn: check that once with your own account. Native dollar cost stays unknown (subscription
usage), never invented API pricing. Credentials refresh through the native clients; expired or
revoked sessions may need their native sign-in again.

Sources: [Codex app-server](https://developers.openai.com/codex/app-server), [Codex config schema](https://developers.openai.com/codex/config-schema.json), [Claude CLI reference](https://code.claude.com/docs/en/cli-reference), [Claude model aliases](https://code.claude.com/docs/en/model-config), [Claude native hosting/authentication terms](https://code.claude.com/docs/en/legal-and-compliance). Checked 2026-09-20 against Codex 0.153.4 and Claude Code 2.1.263.
