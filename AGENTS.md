# HouseOS: instructions for the AI agent working on this copy

You install, run, fix and change HouseOS for the person who owns this folder. Answer in their
language. Ask before installing system packages or services, using `sudo`, or touching their
TV, speakers, router or firewall. New to them? docs/START-HERE.md is a short introduction.

## Read first

1. **Installing:** follow **AGENT-INSTALL.md** (checks, questions, the welcome and tour messages,
   fixes). For more depth:
   - docs/START-HERE.md, then what they bring: AGENT-INSTALL.md §5.
   - Then the guide for their computer:
     - Linux with Docker: docs/DOCKER.md (`./houseos.sh`).
     - Windows: docs/WINDOWS.md (WSL 2, step by step with checks).
     - Linux without Docker: docs/SETUP.md.
   - Then docs/INTEGRATIONS.md, docs/DEVICES.md (their TVs, speakers and remotes, by brand), and .agent/STATE.md.
2. **Running it** (update, back up, find what's wrong): the next section.
3. **Changing code:**
   - docs/ARCHITECTURE.md (how the parts fit), then only the relevant section of
     docs/CODE-INDEX.md (every module, function and route, with line links).
   - docs/CHANGING-HOUSEOS.md: how a feature is built end to end, the checks, deploying and going
     back, and how changes Nox drafts are reviewed in Control Room → Changes.
   - The code and docs/ARCHITECTURE.md are the source of truth; docs/design/ has the product
     brief, the writing rules, the design system and each theme's direction.

## Running the house for them

Everything runs from this folder. Check with `./houseos.sh status` before and after.

| They ask | You do |
|---|---|
| "Update HouseOS" | `./houseos.sh update`. Music resumes at the same second; wait for a film to end. |
| "Back it up" | `./houseos.sh backup` → `backups/<date>/`. Private (keys, `.env`): suggest copying it to another disk. Restore: docs/DOCKER.md §9. |
| "Something's wrong" | `./houseos.sh status`, then `./houseos.sh logs [service…]`, then the table in docs/DOCKER.md → When something is off. *Control Room → Health* and *Logs* show the same from the app. |
| "A device doesn't work" | The section *When the user's device or setup doesn't work* below. |
| "The setup code" | `./houseos.sh setup-code` (only until the first account exists). |
| "Reach it from outside" | Tailscale (`tailscale serve --bg 8990`) or their reverse proxy: docs/DOCKER.md §3. Never a router port forward. |
| "Voice on the graphics card", "the torrent player", "buttons in Control Room" | `./houseos.sh gpu on`, `torrents on`, `buttons on` (each has `off`). |

- Settings, keys and accounts live in the app (*Control Room*), not in files: guide them there.
- `docker compose down` keeps everything; `down -v` deletes all data. Never run `-v` unless they
  ask for a fresh start, after a backup.
- Record what you did (never secret values) in .agent/STATE.md.

## What this is

A fresh, clean copy, with nothing from anyone else's house:
- no accounts or credentials;
- no configured stream add-on or debrid API token;
- no provider login, devices, history or hosting.

Everything the user needs to supply is listed in AGENT-INSTALL.md §5. Never ask the user to
paste secrets into chat. They enter keys in HouseOS's Control Room, where they are stored
encrypted.

## How it is put together (one minute)

- **Services** (Docker, one container per service):
  - `api` is FastAPI plus the built React UI.
  - `worker` runs music jobs.
  - `fetch` resolves YouTube, SoundCloud and radio, with no database and no keys.
  - `audio` is the mpv speaker bridge.
  - `maintenance` runs reminders, song genres and the weekly film index.
  - `cinema-worker` checks film versions in a sandbox; `cinema-observer` follows what the TV plays.
  - `tusd` takes uploads in pieces.
  - `relay` serves media to TVs.
  - `voice` is faster-whisper.
  - `codex` and `claude` are sign-in bridges.
  - `https` is the built-in door on :8443.
  - `db` is MariaDB.
  - `helper` (only after `./houseos.sh buttons on`) runs `houseos.sh`'s fixed actions for the Control Room.
- **Talking to each other:**
  - Services talk through the database (durable jobs, leases, confirmations) and small Unix
    sockets in the state volume.
  - The UI gets live updates from an event stream.
- **Backend:** `backend/houseos/`, one module per area.
  - Music: `music.py`, `audio.py`, `music_genre.py`.
  - Cinema: `cinema.py`, `cinema_explore.py`, `film_index.py`; Watch → Web (any video link): `cinema_web.py`, `fetcher_web.py`.
  - Home: `household.py`.
  - Assistant: `assistant*.py`.
  - Smart home: `home.py`.
- **Frontend:** `frontend/src/`, one file per room with its CSS beside it (`music.tsx`,
  `watch.tsx`, `household.tsx`, `me.tsx`, `control.tsx`…; the list is in docs/FRONTEND.md).
  - Product and writing rules: docs/design/BRIEF.md, docs/design/COPY.md.
  - **The design system** (`frontend/src/design/`, docs/design/SYSTEM.md): every control,
    pattern, overlay and state comes from `./design` (`Button`, `Field`, `Sheet`,
    `ConfirmSheet`, `Form`, `List`/`ListRow`, `State`, `Notice`, `Problem`…). A room's own CSS
    only lays things out, in `@layer rooms`, with tokens. `npm run build` fails on a raw
    `<button>`/`<input>`/`<dialog>`, an inline style, an emoji, a colour, font, radius, shadow or
    duration written by hand, a breakpoint other than 600/900/1232/1600, or an undeclared layer
    (`scripts/design-check.mjs`); `tests/theme-canary.cjs` fails on anything drawn outside the
    tokens. The token catalogue: `PYTHONPATH=backend python3 -m houseos.theme_kit tokens`.
  - **A new component** goes in `src/design/` (with its Workbench example at `/workbench`), not
    in a room. **A new theme** is data in `themes/`: read `themes/README.md` (the authoring
    guide), `themes/_kit/METHOD.md` (the method) and `themes/_studio/DESIGN-LIBRARY.md`;
    `theme_kit new|font|check|build`, then the tour: `node themes/_kit/tour.cjs <id>`. Installed
    themes (packs, the studio's drafts) live beside the house's data and are checked again there
    (`backend/houseos/themes.py`).
  - **Nox's theme studio** is an assistant purpose (`themes`) with its own model, prompt
    (`themes/_studio/STUDIO.md`), tools (`backend/houseos/tool_themes.py`) and limits
    (`assistant.limits`).
  - Every visible string goes through `t("English")`, with a French entry in
    `frontend/src/locale_fr.ts`. The build fails on a missing one.
  - There is one interface; themes only change its look (the default is Zabiwa, the original look
    is **Legacy**, `themes/carved-night`). Keep API changes additive (scripts use it).

## Rules that keep HouseOS good

- **If code can do it, code does it.** The AI model (Nox) is for real conversations only.
  Queues, schedules, feeds, stats, genres, filters and presets are plain code.
- **Every feature is also a tool Nox can call** (`assistant_tools.py`). It goes through the same
  permission-checked operations as the buttons.
- **Free and open data first.** Existing examples:
  - Wikidata for films;
  - the anime offline database and MyAnimeList;
  - Deezer's public catalogue for song genres;
  - radio-browser for stations.
  Anything that needs a paid key is optional and says so.
- **Honest status.** "Accepted" is not "playing"; a test double is not a physical check.
- **Never do these to "test"** without the user's go-ahead: start music or a film, control a TV,
  pair a device.
- **Preserve media exactly.** Keep the exact media, language, subtitles and saved position.
  Never silently drop subtitles. Music loudness is one fixed level per song, never changed
  during it.
- **No public exposure.** The Docker install serves the home network on :8443. No router port
  forwarding. Remote access goes through the user's own VPN (for example Tailscale).
- **Keep the fix small.** Before an edit, read the domain code and its callers, fix the cause
  where every caller goes through it, and keep the diff small.

## When the user's device or setup doesn't work

Compatibility problems are the most common request. Work in this order:
1. **What is it, exactly?** Brand, model, how it is connected (Cast, DLNA, Home Assistant
   integration, Bluetooth, HDMI), and the install (Docker Engine, WSL, Docker Desktop, native).
   docs/DEVICES.md says what should work.
2. **Look before changing:** *Find devices* results, the device's Home Assistant attributes
   (`supported_features`, `source_list`, `sound_output`…), `./houseos.sh logs relay worker api`,
   *Control Room → Logs*.
3. **Where the code is:**
   - Finding devices: `discovery.py` (Cast, mDNS, brand SSDP, brand names), `dlna.py`.
   - Playing on them: `cinema_cast.py` (films, Cast), `music_outputs.py` (music follower for
     Cast/DLNA, relay), `audio.py` (the server's own speakers).
   - Controlling them: `home.py` (Smart home; `REMOTES` maps each Home Assistant integration to
     its arrow/OK command names), `tv_remote.py` + `cinema_tv.py` (the TV remote).
4. **Fix it in the shared place** (a brand's remote names go in `home.REMOTES`, a new SSDP kind in
   `dlna.SCREENS`, a brand hint in `discovery.BRANDS` and `BRAND_HINTS` in `control.tsx`), with
   a test that uses the device's real answers (attributes, SSDP reply, SOAP response).
5. **Never test on their devices without asking**: no playing, casting, pairing or power.
6. Add the device to docs/DEVICES.md when it works.

## Changing it safely

1. Make the change, with its test: `backend/tests/` (pytest) or `frontend/tests/` (Playwright).
2. Run the checks in docs/TESTING.md. Never point tests at the live database: the fixtures
   refuse any schema other than `houseos_test`.
3. From `frontend/`, `npm run build` checks translations (missing and unused French), the design
   guards and types, and builds the interface. `npm run test:browser` runs its scenarios.
4. Rebuild and restart with `docker compose up -d --build`. From git, `./houseos.sh update`
   pulls first. Restarting `audio` stops the song that is playing, so do it between songs.
5. After adding or moving code, run `python3 tools/code_index.py` to regenerate
   docs/CODE-INDEX.md.
6. Before sharing a copy, run `python3 tools/privacy_scan.py .`. Add `--git` for the history.
   Both must print PASS.
7. Update .agent/STATE.md and .agent/TASKS.md as you go. Never commit or share `.env`,
   `backups/`, Docker volumes, databases, logs or keys.
