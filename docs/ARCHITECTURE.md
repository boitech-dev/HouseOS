# Architecture and change guide

<img src="readme/arch.webp" alt="One computer runs the house: your devices open it, your TV and speakers play from it; what stays at home, what goes online, and where your AI is used." width="100%">

- **Backend**: Python 3.13, FastAPI, SQLAlchemy, Alembic, MariaDB. Durable jobs, leases and
  confirmations.
- **Frontend**: React 19, TypeScript, Vite, one design system whose look is a theme (tokens made by
  a Python theme kit, checked for contrast; a canary theme proves nothing escapes them). Pixel
  sprites and dithered scenes in code, English and French built in (other languages translated
  once by Nox), phone-first.
- **Media**: mpv for the speakers, ffmpeg/ffprobe in a bubblewrap sandbox, Chromecast and DLNA.

## One modular application

React/TypeScript/Vite renders semantic HTML over independent original pixel-art layers. FastAPI/Pydantic owns validated versioned HTTP contracts. MariaDB/SQLAlchemy stores accounts, state, operations and jobs; Alembic owns schema migrations. No frontend is trusted to grant access. Most modules expose a router and domain services; assistant tools reuse these services instead of a parallel AI implementation.

`backend/houseos/main.py` registers routers below `/api/v1`, middleware enforces allowed origins, trusted hosts and response security headers, and serves `frontend/dist`. `config.py` reads `HOUSEOS_` environment variables. `db.py` creates a secret-redacted SQLAlchemy engine and sessions. The local helper loads private settings into its children's environment; live credentials are never baked into a build.

## Ownership and persistence

`auth.py`, `account.py`, `models.py`: invite-only accounts, admin/resident/guest permissions, passwords, opaque sessions, revocation, CSRF and invitation ceilings. Membership lifetime is separate from invite redemption lifetime. Last-admin protection is a domain rule.

`household.py`, `house_settings.py`, `notifications.py`: house wall, chores/tasks/occurrences, groceries, events/calendar and recipient-scoped inbox/notifications. Task and grocery lists have views (`?state=open|done|recurring|bought`): a finished task moves to Done and `reopen` brings it back; To do shows a repeating task's copies for the next week only. Messages group into conversations by their participants (`GET /household/conversations`, and `/conversations/{key}?before=` pages back through one thread and marks it read). Dates use the house timezone (House setting, default UTC) unless a feature's explicit setting overrides it; review recurrence/DST tests when changing time behavior.

`files.py`, `storage_admin.py`, `backup_policy.py`: personal/shared storage, upload reservations, quota accounting, grants, trash/restore and usage. tusd is only transport. Finalization validates mount identity, file boundaries and durable metadata. An upload isn't stored until finalization succeeds. Do not read arbitrary paths or follow untrusted symlinks. UI drafts are account-scoped and are not durable server content until synchronized.

`events.py`, `worker.py`: transactional event/outbox and durable jobs, leases and retries. Events must be filtered by actor ownership. External calls are outside long DB locks. Generation/revision checks prevent stale workers committing over newer actions. No synthetic status should impersonate observed playback.

`models.py` and module-local ORM models are both important: not all tables live in one file. Alembic's environment imports the domain modules before migration. `docs/CODE-INDEX.md` (regenerate with `python3 tools/code_index.py`) lists every module, function, model and route with line links; do not create tables ad hoc at production startup.

## Music path

UI or `music_*` tool → permission-checked music service → canonical source/queue row → metadata + bounded download preparation → isolated fetch resolver → durable cached track → private audio bridge → mpv → selected output.

`music.py` owns queue actions and attribution; `music_library.py` playlists, local-file sharing, skip votes and live-stream approval; `music_downloads.py` retained media and preparation/cancellation; `fetcher.py`, `fetcher_cache.py`, `fetcher_live.py` resolve/download safely; `audio.py` owns player IPC; `audio_admin.py` output configuration; `music_outputs.py` the other outputs (phones and computers in Speaker mode, one Cast or DLNA speaker/TV), which all follow mpv's clock. Tracks longer than 90 minutes and live radio stream through a fetcher-owned pipe instead of downloading (`fetcher_live.py`, lease renewed while playing); tracks over four hours are refused. `radio.py` owns station discovery and reads a station's ICY now-playing title.

**Queue order.** Fair turns decide only where a *new* song lands (`place_fairly`, using `fair_order`: each person's nth song in round n, starting after whoever played last). The House setting "Take turns" (`music_round_robin`, on by default) turns this off. After that, anyone with `music.queue` may move any waiting song (`PATCH /music/queue/{id}`); `POST /queue/{id}/next` makes your song your next one, and an admin can pin any song to play right after the current one. Everyone has one **veto**, back three hours after use (`POST /queue/{id}/veto`, `VETO_RELOAD`): it skips someone else's playing song or removes it from the queue. Removing a song (`DELETE`) is for its owner or an admin. `DELETE /music/queue/{id}/kept` deletes the song's kept file from the house (whoever kept it, shown as `kept_by`, or an admin): the playing song plays on from its own playback copy; a waiting one of yours leaves the queue. Every change bumps the queue version; stale writes get `409`.

**Levelling** (`audio.py`, House setting `music_normalize`, "Even out songs", on by default). Each downloaded file's loudness is measured once with ffmpeg's EBU R128 filter, in the background while the previous song plays, and one fixed gain is set before the song starts, never during it: below -13 LUFS gets +20 % (with a 0 dB limiter that only touches peaks that would clip), above -7 LUFS gets -15 %, anything else plays as released. Live radio is not measured and plays as is. Levelling applies to mpv (this computer's speakers); Cast, DLNA and Speaker mode play the file as is.

**Genres** (`music_genre.py`, no model). First match wins: the house's own genres (House setting `music_genres`, a name and the words that mean it), then what the source says (SoundCloud genre, station tags, words in the title such as "OST" or "OP 3"), then Deezer's public catalogue (no account or key; House setting `music_genre_lookup`, "Find each song's genre online"). `music_catalog.enrich` runs in the maintenance service, a few songs a minute: it keeps each song's evidence on its history record (so a house genre added later applies to past plays without new lookups) and fills missing artwork from the YouTube still or the Deezer cover.

Every play writes one `music.play` record (who, genre, time heard): play counts, history by person, the house favourites and the Home stats all read it.

Canonical URLs identify reusable media; playlist/radio parameters on a single-song link must not become an accidental playlist. Prefetch is bounded (next two) and serial; metadata should remain visible for later items. Full retained files may be reused, cancelled partial files must not leak. History, dedup, repeat and scheduling run in code; the LLM reads history only when needed.

## Cinema path

Catalog (`cinema.py`, `anime_catalog.py`) → exact movie/series/episode identity → source discovery (`cinema_sources.py`, `cinema_adapters.py`, `addon_http.cjs`) → frozen choices → source inspection → exact audio/subtitle/destination plan (`playback.py`) → authorized preparation/job → `cinema_worker.py` → delivery/Cast → fresh observation/checkpoints.

`cinema_jobs.py` owns durable workflow work. `cinema_progressive.py` prepares bounded progressive fMP4/HLS where needed; compatible video is copied, audio converted only when required. `cinema_stream_input.py` supplies authorized source bytes into a network-isolated parser. `cinema_delivery.py`, `relay.py` provide scoped opaque receiver URLs/ranges/CORS. `cinema_subtitles.py` extracts/normalizes tracks without pretending bitmap subtitles are text. `cinema_cast.py` verifies receiver sessions/tracks; `dlna.py` finds and drives UPnP/DLNA renderers (every URL pinned to the device's own private address); `cinema_observer.py` updates observed state. `cinema_tv.py` separates physical TV control (Home Assistant) from playback. `cinema_cleanup.py` owns stop/cancel/temp cleanup. `cinema_queue.py`, `cinema_sleep.py`, `cinema_library.py`, `cinema_watchlist.py`, `cinema_suggest.py` own queue/timer/local library/per-user media actions and source ranking.

Choosing a version (`cinema_suggest.py`): something the viewer can follow comes first, so audio or subtitles in one of their *languages* (a per-person list in the film preferences, default: their subtitle language, the house language, English) outweigh 4K; a film in none of them ranks last and a dub they understand is tried before it. A file without subtitles is ranked, never rejected. Opening a title probes the three most promising releases (Dolby Vision remuxes and 50 GB+ files last); when none plays on the chosen screen, or nobody would follow the best one, it checks the next three, up to four rounds, and reports why earlier ones were set aside (`suggestion_progress.setbacks`). A film saved on the house disk (Files → Films) is a source of its own (`saved_sources`), inspected once and served to the TV through the relay as `local:` bytes, never re-downloaded.

A source resolver link is a credential-bearing private resource, not a link to show the model. Preserve exact torrent hash, selected file index and episode mapping. A cached-source label is evidence from the provider, not proof that all downstream formats are playable. Surface distinct provider rejection, missing receiver, incompatible format, track failure and expired-source errors.

Streaming is temporary; explicit save/download goes to the retained local library. Continue Watching stores actual per-user position and last source/settings. Source refresh must retain identity; unknown outcomes require observation before retry. Stop Cinema cancels owned work, buffering and matching receiver activity; it must not close another application's playback or erase the saved library.

### Browsing: filters, collections, "More like this"

Watch's filters and collections read local indexes only, so they are instant and keep working when a remote catalogue is down. Nothing here uses a model.

- `film_index.py`: films and series from Wikidata (free, CC0, no account). HouseOS ships a ready copy (`houseos/data/film-index.json.gz`), so filters and collections work from the first start. The maintenance service refreshes it weekly in the background: Wikidata's own query service first, QLever (a public mirror) when it is down, one year per query for the busy decades; it resumes where it stopped, publishes only when the index grows, repairs missing directors and cast, and never replaces a bigger index with a smaller one. It keeps notable titles with an IMDb id: English and French title, year, genres, themes, directors, main cast, some awards, running time and how well known it is.
- `anime_offline.py`: the anime offline database (cedya77/anime-offline-database, derived from manami-project), downloaded and refreshed daily: tags, studios, seasons and franchise links. It is also the fallback when Jikan is down.
- `cinema_explore.py`: every filter at once (text, years, genre, theme tag, person or studio, award, maximum length or episodes, sort), facet lists, people search, similarity and franchise.
- `cinema_collections.py`: collections as data (one line each: title, kinds, filters, optional sort, months or pinned). The Watch home shows this month's seasonal ones, the pinned ones and six more that rotate weekly (the same six for everyone that week). A collection with too few titles is left out.
- Speed: an index loads once under a lock (and warms at startup) and is rebuilt only when its file changes; requests never download the anime catalogue (maintenance does). A kind with no local index yet (series before the first build) is served from Cinemeta's popular lists. The Watch page loads a row only when it nears the screen.
- Images (posters, song art, station logos) go through one sanitising cache on disk (`cinema/images`, 30 days; a failed image is not asked again for 6 h). Their routes are async and fetch misses on six threads of their own, so a page of posters never holds up other requests.
- Routes in `cinema.py`: `GET /cinema/explore`, `/cinema/explore/facets`, `/cinema/explore/people`, `/cinema/collections`, `/cinema/for-you` and `/cinema/titles/{id}/similar`. The Watch home shows, per tab: every title (endless, sideways), Recommended for you (like the last five watched), classic genre rows, then weekly niche collections; each row keeps loading sideways. For anime, "More like this" uses MyAnimeList members' recommendations through Jikan, falling back to similar themes and studio; for films and series it uses the same director, cast and themes from the film index.

### Web videos (Watch → Web)

`cinema_web.py` and `fetcher_web.py`. `POST /cinema/web {text, device_id, replace}` finds the link in what was pasted or shared and queues a `cinema.web_video` record (one per link and person; the same link again reuses its card and file). The cinema worker's own web lane (one at a time, beside the preparation lane) asks the fetcher for `web_info` (yt-dlp's reading: title, site, length, expected size; live, playlists, >4 h and >6 GB refused with their own codes) and then, when picture and sound are H.264/AAC readable as they arrive, `web_stream`: yt-dlp downloads each at full speed into a pipe and ffmpeg copies them into HLS pieces (EVENT playlist, fMP4) in `<runtime>/audio/web-video/<id>/`; as soon as the first pieces exist the lane writes `master.m3u8` (`cinema_progressive.write_master`) and launches with that folder as the workflow's `_prepared` stream, so the relay serves it like the films' progressive route while the rest arrives. Otherwise `web_video` downloads the best version up to 1080p merged to one MP4 first (the directory is shared by the fetcher, relay and workers). The fetcher keeps it in its sandbox: public internet only, no secrets, its own download slot so songs never wait behind a video. The file is then an ordinary house source (`resolve_media`'s `web_video` branch, `saved_path` allows that folder): a `web:` title (kind `web`, its own Watch tab, out of film stats) and a workflow launched on the chosen screen with the films' own `launch`, so compatibility, conversion, the relay, the Now bar and resume are the films'. `GET /cinema/web` lists your cards with progress (the growing download against the expected size); `POST /cinema/web/{id}/play` plays again or replaces what is on; `DELETE /cinema/web/{id}` forgets one. The observer deletes files 6 h after their last play (never while on a screen) and keeps the folder under 20 GB. Capture (the phone's share target) offers *Play this video on the TV* for a link.

### TV remote

`tv_remote.py` (`/api/v1/tv`) gives each Cast or DLNA screen up to two remotes, picked with a target: `tv`, the TV itself through Home Assistant when its media player is mapped to that device (power, input, volume, its own arrows), and `device`, the Cast/DLNA device (volume, mute, play/pause; arrows, OK, back and home once paired over the Android TV Remote protocol with `androidtvremote2`). Pairing is optional; its client identity is kept in `<runtime_root>/run/tv-remote` (0700/0600) and never returned. Keys are an allowlist. `tool_tv.py` lets Nox press a key on the remote that has it, the TV first.

## Games path

`games.py` keeps a `game.rom` record per file (an upload moved into `<data>/media/games/<console>/`,
a pasted link downloaded by the fetcher, or a file of an admin's games folder, read in place).
`games_catalog.py` names it from the libretro database (CRC32 by `zlib`, zip members read without
unpacking, copier headers skipped; else the file name) and `fetcher_games.py` fetches that data,
the covers, EmulatorJS files (`/emulator/4.2.3/…`, same origin) and RetroArch cores, each from a
fixed address list, only when first needed. **Here**: `games_player.tsx` loads EmulatorJS with
the game (`/games/<id>/file/<name>`) and syncs the in-game save to `<data>/game-saves/<user>/<game>/`.
**TV** (`games_tv.py`, native only): the API writes the pick to `run/next.json`; Sunshine's app,
`docs/native/houseos_game.py`, runs RetroArch with the same core and that person's save, and reports
`run/tv.json`. `docs/native/setup_games_host.py` installs and configures the host side once.
Details: [GAMES.md](GAMES.md).

## Home stats and house titles

`stats.py` builds "the house in numbers" (cached 60 s) from `music.play` rows, house records and Cinema state. The Home board has four tabs:

- **Music**: plays, hours heard (radio counts its listening time), top songs and DJs, genres, hours of the day.
- **House titles**: 20 titles over music, house life and games, in two periods: **this week** and **all time** (each title goes to whoever leads it; all time adds up to three stars). The viewer also gets a nudge ("3 more songs and you're Head DJ").
- **Films & series**: house totals only, this month and all time, split into films, series and anime and by genre. Each person's viewing stays private, so films never make a title.
- **Games**: hours played and the house's top games.

Add a title in `TITLES`, a board in `boards_for`/`house_counters`, and its label in `frontend/src/house_stats.tsx`.

## Smart home, network and background services

`home.py` is the Smart home room: the house's own Home Assistant behind an admin exposure policy (lights, plugs, blinds, heating, scenes, by room). Locks, alarms and similar devices always need a confirmed second step. Every command re-reads the device and reports the state Home Assistant shows. `tool_home.py` gives Nox the same actions; names such as "the living-room lights" resolve by fuzzy match, and several equally good matches are returned for the resident to choose. The room also holds the TV remote, so it appears when Home Assistant is connected or any Cast/DLNA screen is enrolled.

`discovery.py` finds TVs, speakers, Home Assistant and Jellyfin on the home network (mDNS, SSDP) and announces HouseOS as `houseos.local`. Multicast only works on the home network, so this runs in the media relay (host network in Docker, or HouseOS's own address with `compose.lan.yml`). Scan requests and results travel through one database row.

`maintenance.py` (`python -m houseos.maintenance`) runs once a minute, each step in its own transaction: history pruning, household reminders and recurrences, upload/file housekeeping, pending notifications, service-restart reconciliation, My Space refreshes, music genres and artwork (`music_catalog.enrich`) the weekly film index (`film_index.refresh`) and interface translations (`languages.refresh`). Without it there are no reminders, no genres and no Watch filters or collections.

Kept songs and saved films can be deleted from Files by whoever kept them or an admin (`storage_admin.delete_kept`, the same version-bound, path-checked deletion as Control Room → Storage).

`activity.py` is Control Room → Logs: the events the house already records told as sentence templates with a category (music, films, Nox, house, system) and a level (info, good, problem), filtered and paged newest first; plumbing events stay out and private content never appears. Background processes add their own lines with `activity.note` (a chore that failed, the film index rebuilt). Nox reads the same diary with the setup tool `house_activity`.

`languages.py` adds languages beyond English and French: the build writes every interface text to `ui-strings.json`; an admin (Control Room → House, or Nox with `language_add`) starts a translation that the maintenance service runs in batches through the setup assistant's model, under the usual budgets; each batch is saved, so it resumes after a restart, and a sentence that lost a `{placeholder}` stays English. A ready language can be the house default and anyone's own.

`house_setup.py` measures the first-run checklist and service health from real probes (heartbeats, socket pings, HTTP answers), never from configuration alone. `control_room.py` holds the fixed service actions. `house_actions.py` (Docker only) turns Control Room buttons into `houseos.sh` actions (update, backup, GPU voice on/off, own address on/off): the optional helper service (`compose.helper.yml`) holds the Docker socket and runs only those fixed actions, when the app asks with a note signed by the house key.

Small utilities: `atomic.py` (write a small JSON file atomically, mode 0600), `ipc.py` (JSON over a private Unix socket), `events.py` (events and service heartbeats).

## Assistants, tools, memory and cost

`nox_presets.py` answers the code presets (favourites, week digest, house tour) without any model and holds the `TOUR` text; `assistant_prompt.py` holds Nox's system text per tool bundle. `assistant.py` holds the system policy, tool registry, schemas, permission dispatcher, provider loop and usage reservations. `assistant_profiles.py` assigns separate profiles: everyday Nox, My Space, setup mode and the theme studio. `assistant_cinema_contract.py` validates media intent. `tool_household.py` exposes household/file operations. `provider_checks.py` validates model/provider setup. Optional native provider adapters live in `codex_*` / `claude_*`; API adapters are also in the assistant module.

Only a small relevant tool bundle is sent, with bounded context/tool loops and compact results. Conversations and explicit memories are user-owned. A new conversation keeps explicit saved preferences/memory but must not inject another user's history. Conversation data is not a shared vector index. Background jobs, queues and feed refreshes do not call an LLM for routine automation. Never load this whole documentation index into a runtime prompt.

Each assistant (everyday Nox, My Space, setup, the theme studio) has its own provider, model and effort (`assistant_profiles.py`); a ChatGPT or Claude sign-in passes the effort to its bridge (`--effort` / `effort`), and a medium or high effort gets a longer round (45 or 60 s) inside the 90-second turn. `usage_prices.py` looks up real per-token prices on demand from OpenRouter's free public model list, only for models used in the last 30 days or assigned, never for subscription sign-ins; the usage page then estimates API requests that reported no cost.

`personal_space.py` persists setup conversation/configuration and builds code-refreshed RSS/Reddit/illustration sections. User approval completes setup; later editing remains available. News collection and twelve-hour refresh work without recurring LLM selection calls.

## Voice

The browser records (MediaRecorder), `POST /assistant/voice` writes the file to a private folder and
asks `voice.py` over a Unix socket; faster-whisper transcribes locally, returns text plus a
`confident` flag, and the file is deleted. Confident speech is sent at once with `source="voice"`.

## Frontend and extending the app

`frontend/src` has one file per room with its CSS beside it (docs/CODE-INDEX.md lists them); `main.tsx` signs in and routes, `shell.tsx` is the frame. Every control, pattern and overlay comes from the design system in `src/design/` (`docs/design/SYSTEM.md`), coloured and shaped by the tokens a theme provides (`themes/`, compiled by the theme kit into `src/design/generated/`); pixel art is in `sprites.ts`/`pixel.ts`. The original look is the Legacy theme (`themes/carved-night`). All visible text goes through `t()` (`i18n.tsx`: English, French built in, other languages loaded from the house); `npm run build` fails if a French translation is missing (`locale_fr.ts`). See FRONTEND.md and CODE-INDEX. Keep mobile composers visible, use pending feedback, clear sent input correctly, truncate/wrap long titles and preserve keyboard/Enter behavior. Art is presentation; controls must remain accessible DOM elements with readable text. Use loading states instead of blocking navigation on a long provider call.

For a change: locate the domain service and all callers; update input/response schemas together; add a migration only if persistence changes; route both UI and tool actions through it; run the smallest relevant regression tests plus security/concurrency tests for changed boundaries. Update the docs that describe it.

## Operational boundary

Native services/Unix sockets/peer checks are part of the security model, in Docker (one image, one container per role: `docker/` and `docker-compose.yml`) as in a native install. The native service files in `docs/native/` are references to adapt, not a turnkey host installer. Paths, service users, mount UUIDs, network policy and own HTTPS access must match the recipient machine. Secrets remain external to source. Backup database + encryption/config keys together securely; media backup is separate. See OPERATIONS-PERSONAL.md.

## Themes and the theme studio

A theme is data in `themes/<id>/` (tokens in the DTCG format, a manifest, words, fonts, art).
`backend/houseos/theme_kit/` (standard library only) resolves tokens over Base, makes colour ramps
from seeds, checks everything (contrast matrix, distinct colours, fonts, art, words) and writes the
CSS the app imports (`frontend/src/design/generated/`). `themes.py` keeps installed themes (packs
and the studio's drafts) under `<runtime_root>/themes/`, re-checks them, builds their CSS there
and serves it behind the session (`/themes/<id>.css`); anyone who lives here makes them, an admin
shares them. The theme studio is an assistant purpose (`themes`) with its own limits
(`assistant.limits`: longer rounds and turns, run in the background), prompt
(`themes/_studio/STUDIO.md`) and tools (`tool_themes.py`: catalogue, library, fonts, save through
the checks, fonts from Fontsource, code-made textures, preview cards, wear, share, and
`web_read`/`web_image` through the sandboxed fetcher). People's pictures are downscaled and
stripped of metadata on arrival (`pictures.py`).

