# Installing your HouseOS (native, without Docker)

**Docker is the easier path**: see [DOCKER.md](DOCKER.md). This guide installs the same
services directly on Linux, for people who want full control or no Docker. On a Windows PC, use
Docker inside WSL 2: [WINDOWS.md](WINDOWS.md).

Target: **Ubuntu (or another Linux) x86-64, Python 3.13**, a computer that stays on at home. Phones
and computers use it from the browser. Developed with Python 3.13, Node 22, MariaDB 11.4,
PipeWire, FFmpeg, mpv and bubblewrap.

Install order that works: core app → storage → AI key → music → films → voice → phone access.
Each step is usable on its own; stop wherever the user is happy.

## 0. Prerequisites (system packages; ask the user first)

- Core: `python3.13` with venv, a MariaDB server.
- Music: `ffmpeg`, `mpv`, `bubblewrap`, `nftables`, PipeWire or PulseAudio (`pactl`), Node 22 (the
  YouTube resolver uses it for its JavaScript challenge).
- Uploads: `tusd` (upstream release binary).
- Frontend changes only: Node 22 + npm (the UI is already built in `frontend/dist`).

Not bundled on purpose: the OS packages above, MariaDB itself, provider accounts, browser engines
for browser tests, optional Jellyfin/Home Assistant, native Codex/Claude CLIs.

## 1. Database

Create a dedicated schema (for example `houseos`) and a password-protected user limited to it on
localhost, with your own MariaDB admin tools. Never give HouseOS root credentials.

## 2. Install, configure, start

From the HouseOS folder (`git clone https://github.com/boitech-dev/HouseOS.git`):

```bash
bash tools/install-python.sh          # from PyPI, pinned with exact hashes (dependencies/requirements.lock.txt)
.venv/bin/python tools/local.py init   # asks for the DB user/schema/password, creates keys
.venv/bin/python tools/local.py migrate
.venv/bin/python tools/local.py run    # http://127.0.0.1:8990 (Ctrl+C to stop)
```

In a second terminal, while it runs: `.venv/bin/python tools/local.py bootstrap` creates the first
administrator (username 3–80 characters, password 12+). Then sign in at http://127.0.0.1:8990.

`init` writes a private mode-600 file, `~/.local/share/houseos-personal/settings.json` (set
`HOUSEOS_PERSONAL_STATE` to choose another place). It holds your database URL, a fresh encryption
key and bootstrap token, and every `HOUSEOS_*` setting below. Back it up with the database; never
commit or share it. `run` starts the API and the background worker only; it installs no services.

`tools/install-python.sh` also installs `androidtvremote2` (it is in the lock) for the TV remote's
arrows on Google TV and Android TV; nothing else is needed for it.

**The maintenance service.** `python -m houseos.maintenance` (from `backend/`, with the same
`HOUSEOS_*` environment as the API) runs once a minute: household reminders and recurrences, file
and upload housekeeping, notifications, My Space refreshes, music genres and artwork, and the
weekly film index refresh (a ready index ships with HouseOS; the refresh comes from Wikidata).
`tools/local.py run` does not start it. Without it there are no reminders, no song genres and no
Watch filters or collections. Run it as a service like the others
(`docs/native/houseos-maintenance.service`).

## 3. Storage

Storage stays off until you choose a disk. Pick a mounted filesystem and a dedicated folder on it,
read its UUID with `findmnt -no UUID <mountpoint>`, then set in the settings file:

- `HOUSEOS_STORAGE_MOUNT` — the mountpoint, e.g. `/mnt/house-storage`
- `HOUSEOS_STORAGE_UUID` — that filesystem's UUID (HouseOS refuses to write if it changes)
- `HOUSEOS_DATA_ROOT` — the folder, e.g. `/mnt/house-storage/houseos`
- `HOUSEOS_IMPORT_ROOT` — optional folder admins may import existing films from

Keep the database, venvs and temporary buffers on the fast system disk; files, kept songs and saved
films go on the data root.

## 4. Your network (for the TV and phones)

- `HOUSEOS_LAN_URL` — how phones reach HouseOS on your Wi-Fi, e.g. `https://192.0.2.10:8545`
  (after you set up local HTTPS; see OPERATIONS-PERSONAL.md). Add it to `HOUSEOS_ALLOWED_ORIGINS`
  and set `HOUSEOS_COOKIE_SECURE=true` once you use HTTPS.
- `HOUSEOS_RECEIVER_BASE_URL` — the media relay the TV fetches from, e.g. `http://192.0.2.10:8991`
  (`houseos.relay:app`, see docs/native/houseos-media.service).
- `HOUSEOS_CAST_LAN_CIDR` — your LAN range, e.g. `192.0.2.0/24`; Cast devices outside it are refused.

192.0.2.x is a documentation range: replace it with your real addresses. Empty values keep TV
enrolment switched off.

## 5. Music

1. Resolver: `tools/install-python.sh` already put yt-dlp (`dependencies/resolver-requirements.txt`)
   in `.venv`; set `HOUSEOS_RESOLVER_BIN` to that `yt-dlp`, or to one in a separate venv.
2. Fetcher: `houseos.fetcher` runs as its own user (`houseos-fetch`) with the network policy in
   `docs/native/houseos-fetch.nft.example`; it is the only process that talks to
   YouTube/SoundCloud/radio. Keep that isolation.
3. Audio: `houseos.audio` runs as the desktop user (it needs the PipeWire/Pulse socket) and starts
   its own mpv.
4. Set `HOUSEOS_EXTERNAL_FETCH_ENABLED=true` and `HOUSEOS_AUDIO_ENABLED=true`, restart, choose the
   output in Control Room → Speakers, and play one song together with the user.

## 6. Voice (optional)

`houseos.voice` transcribes speech locally with faster-whisper: its own venv with
`pip install faster-whisper==1.2.1` (the version the Docker image uses), models in `<runtime>/models/whisper` (download
`large-v3-turbo` for a GPU and `small` for CPU once, then `HF_HUB_OFFLINE=1`). It loads on first use
and unloads after 10 idle minutes. Clear speech is sent to Nox directly; unsure words wait in the
box. Browsers only allow the microphone over HTTPS (or on 127.0.0.1).

## 7. Films

A stream add-on + a debrid service (docs/INTEGRATIONS.md), then `houseos.cinema_worker`,
`houseos.cinema_observer` and the relay (`houseos.relay:app` on your LAN address, port 8991,
firewalled to your TV/Chromecast). Enrol the Chromecast in Control Room → Devices.
Filters and collections in Watch need the maintenance service (§2) and its first film index build.

## 8. Running it for good

`docs/native/` has the systemd units, backup and control scripts this app runs with, with
generic paths (`/opt/houseos/...`, `YOUR_DESKTOP_USER`, `/run/user/YOUR_UID`, `YOUR_PRIVATE_DIRS`). They are references to
adapt, not files to copy blindly. Keep their isolation (separate users, private sockets, resource
limits).

## 9. Changing the interface

```bash
cd frontend
npm ci --ignore-scripts   # from the npm registry, exact versions from package-lock.json
npm run build            # checks French translations, types, then builds frontend/dist
```

`npm run dev` serves the UI on 127.0.0.1:5176 with the API proxied to 8990 (add that origin to
`HOUSEOS_ALLOWED_ORIGINS` while developing).
