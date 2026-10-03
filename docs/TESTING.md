# Tests and what they prove

## What every release runs

- Backend: pytest on an isolated MariaDB test schema, including the theme kit, installed themes
  (malicious and malformed packs), the theme studio and the bridge lanes.
- Browser scenarios (`frontend/tests`, `npm run test:browser`), among them `theme-canary` (every
  place drawn from the tokens), `theme-runtime` (switching without a reload), `theme-studio`,
  `legacy-theme`, `phone-fit` (every room at 360 and 390 px) and `accessibility` (axe-core).
- Themes: `PYTHONPATH=backend python3 -m houseos.theme_kit check --all`: every bundled theme passes.
- Privacy scan: `python3 tools/privacy_scan.py .` and `python3 tools/privacy_scan.py . --git` (the
  whole history): no names, host names, addresses, home folders, disk ids or secrets.
- Code index regenerated with `python3 tools/code_index.py` (`docs/CODE-INDEX.md` matches the source).
- The fresh install gate below.

## The release gate: a stranger's first evening

`docker/tests/first-evening.cjs` runs before a release on a fresh clone: empty volumes, no `.env`,
HouseOS reached only by name through HTTPS. The admin is created through that address, which is
then trusted; every room and Control Room page reads in words (no raw codes); the microphone
explains itself; no page errors.

Checked by hand in a Docker install: YouTube search and download, radio (with its song
title), music following the house clock on a phone-sized browser in Speaker mode (within 0.2 s,
pause followed), radio replacing radio, Stop and Clear queue on the player, ChatGPT and Claude
sign-in links (not completed), Jellyfin at a hostname with a real API key and user choice, GPU voice
transcribing a recording on an NVIDIA card, the fetcher unable to reach the database or the app.
Self-hosted AI: Ollama with qwen3:8b connected in one step and Nox added a grocery with its tool.

## Run the checks yourself

Dependencies install online: Python from PyPI with the hash-pinned lock
(`bash tools/install-python.sh`), the frontend from the npm registry with exact versions from
`package-lock.json`.

```bash
.venv/bin/python tools/check-export.py          # built UI, origin boundary, blank secrets, outputs off
cd frontend && npm ci --ignore-scripts && npm run build
python3 tools/privacy_scan.py .                 # add --git to scan the whole history
```

Full backend suite: create a **separate** schema named `houseos_test`, put its URL in
`DATABASE_URL` (in the environment, never on the command line), then from `backend/`:
`HOUSEOS_TEST_MARIADB=1 PYTHONPATH=. ../.venv/bin/python -m pytest -q tests`. The fixtures refuse
any other schema name and clean up their own random test users. Never point tests at your live
database.

Browser scenarios need Playwright, a disposable test API on `127.0.0.1:8893` and test identities;
adapt `frontend/tests/session.cjs` first. `npm run test:browser` (optionally with name filters)
runs every `frontend/tests/*.cjs` in turn and writes screenshots and results to
`frontend/evidence/latest` (ignored by git).

## What only your own home can prove

Software checks are not a real speaker, TV, provider or phone. Check once each, on your equipment:

- Sign-in, invites, a guest's limits, private messages and files.
- Your disk: upload, quota, trash and restore, backups.
- Nox with your provider key and budget; a preset of each kind; voice on a phone over HTTPS.
- A song from YouTube and SoundCloud, a radio (with and without its song title), pause/seek/skip.
- A veto: someone else's playing song skips, a waiting one leaves the queue, and yours comes back
  three hours later.
- "Even out songs": a quiet upload and a loud master play at a similar level, with no pumping
  inside a song.
- A film through your stream add-on + debrid service: picture, sound, subtitles, seek, lip-sync, stop.
- Watch's filters, collections and rows (they work from the first start, with the film index
  HouseOS ships), Recommended for you after a few films, and "More like this" on a film and an anime.
- Your TV remote: power/input/volume through Home Assistant if you use it, and the Chromecast's
  arrows after pairing.

Providers can change or rate-limit at any time; a torrent, codec or HDR profile may not play on
every receiver. HouseOS reports those honestly instead of pretending.
