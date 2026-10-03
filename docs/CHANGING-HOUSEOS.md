# Changing HouseOS

For agents and people changing HouseOS's code, and for Nox drafting a change in setup mode. It
says where things are, how a feature is built end to end, which checks must pass, how to deploy
and go back, and how a change drafted by Nox is reviewed and applied.

## Where things are

`docs/CODE-INDEX.md` lists every backend module, function, class and HTTP route, the frontend
files and the migrations, with line links. It is generated: run `python3 tools/code_index.py`
after adding or moving code. `docs/ARCHITECTURE.md` explains how the parts fit.

| Part | Where |
|---|---|
| HTTP API, one router per domain | `backend/houseos/<domain>.py` (music, cinema, household, files, games, home…), mounted in `main.py` |
| Sign-in, roles, CSRF | `backend/houseos/auth.py` (`require_actor`, `require_admin`, `Input`) |
| Tables | `backend/houseos/models.py` and module-local models; migrations in `backend/migrations/` |
| Background work | `worker.py` (music), `cinema_worker.py`, `maintenance.py` (timed chores), `fetcher.py` (the only process that talks to YouTube, SoundCloud and radio) |
| Nox | `assistant.py` (chat loop), `assistant_prompt.py` (instructions per tool bundle), `assistant_tools.py` (tool catalogue and bundles), `tool_*.py` (tools by domain) |
| Control Room | `control_room.py`, `house_setup.py`, `house_actions.py` (Docker buttons), `tool_code.py` (Changes) |
| Screens | `frontend/src/<room>.tsx` with its CSS; controls from `frontend/src/design/` |
| Words | `t("…")` in the screens; French in `frontend/src/locale_fr.ts` |
| Themes | `themes/` (the authoring guide is `themes/README.md`) |
| Deployment | Docker: `docker-compose.yml`, `docker/`, `houseos.sh`. Without Docker: `docs/native/` |

## How a feature is built

Code does the work; a model only decides what to ask for. If code can answer, code answers.

1. **Service and route.** A plain function does the work; a route in the domain's module calls
   it: `actor=Depends(require_actor)` (or `require_admin`), a body that subclasses `Input`, and
   an `HTTPException` with a sentence a person can act on when it can't. Changes that matter are
   recorded with `emit(db, "audit.…", {...}, actor.id)`.
2. **Nox tool.** The same function becomes a tool: an entry `name: (InputModel, description,
   handler)` in `assistant_tools.py` or a `tool_*.py`, added to the bundle it belongs to
   (`BUNDLES`). The handler returns a dict with `status`; a change people must approve returns a
   confirmation card instead of acting. Tools call the service with the person's own rights.
3. **Screen.** `api(path, method, body)` and `useData(path)` from `frontend/src/api.ts`; controls
   from the design system (`Button`, `Section`, `ConfirmSheet`…). Words are short and practical.
4. **French.** Every `t("…")` needs an entry in `locale_fr.ts`: "tu", never "vous"; the curly
   apostrophe (l’heure); a narrow no-break space (U+202F) before `:` `;` `?` `!`. The build fails
   on a missing or unused entry.
5. **Test.** One test that fails if the feature breaks: `backend/tests/` (pytest; the `client`
   fixture gives an app on a fresh SQLite database) or a browser scenario in `frontend/tests/`.
6. **Docs.** Regenerate `docs/CODE-INDEX.md`; say what's new in `docs/CHANGELOG.md`.

## Checks

From the repository root:

```bash
ruff check --config backend/pyproject.toml backend/houseos backend/tests backend/evals deploy
cd backend && python -m pytest -q        # SQLite by default; some tests need MariaDB (docs/TESTING.md)
cd frontend && npm run build             # translations, design guards, types, the build
python3 tools/privacy_scan.py .          # before sharing a copy
```

## Deploying and going back

**Docker.** `./houseos.sh update` downloads the new version, rebuilds and restarts; music pauses
and comes back at the same second. After editing code here yourself: `docker compose up -d
--build`. To go back, check out the previous commit and rebuild. The Docker image uses the
built screens in `frontend/dist`: after changing `frontend/src`, build them (`npm run build`)
before rebuilding the image.

**Without Docker.** `deploy/release.py` copies the source and the built screens into a new
folder under `<state>/releases/` and points `<state>/current` at it (`previous` keeps the one
before). Then restart the app services. Before restarting the worker, create
`<state>/run/resume-music`: the song playing pauses and resumes where it was. Never restart the
sound player (`houseos-audio`) while music plays. To go back, point `current` at the previous
release and restart the same services.

## Changes drafted by Nox

In setup mode an admin can ask Nox to change HouseOS itself. Nox never changes the code: it
drafts, and an admin applies.

1. **Drafting.** `code_search` and `code_read` read the source; `code_edit` replaces one exact
   piece of text (it must be found exactly once); `code_write` writes a new or whole file;
   `code_diff` shows the draft; `code_discard` drops a file or the draft; `code_list` lists
   changes and backups. Drafts are files under `<state>/run/code/`; nothing writes the source.
   Nox reads the whole source (not `.git`, dependencies, builds, keys or settings files), but
   drafts only in the app itself (`backend/houseos/code_rules.py`):

   | Nox may change | Never (by hand only) |
   |---|---|
   | `backend/houseos/**/*.py`, `backend/tests/**/*.py` and test data (`.json`) | `conftest.py`: it sets up every test, so a change there could hide failures |
   | `frontend/src/**/*.ts(x)` and `.css` (not in Docker: the screens come prebuilt) | what builds, checks, deploys and undoes a change: `deploy/`, `packaging/`, `houseos.sh`, `docker/`, `tools/`, `frontend/scripts/`, `vite.config.ts`, `themes/_kit/`, `code_rules.py` and `backend/houseos/__init__.py` (loading the rules must never run app code) |
   | bundled themes' data: `themes/<id>/**/*.json` and `.md` (not in Docker) | dependencies (`pyproject.toml`, `uv.lock`, `package*.json`): new code from the internet |
   | `docs/*.md` | database migrations: Undo can't take a database back |

   The checks run the drafted code, so everything that decides what runs and how it is checked
   stays out of Nox's reach. The rule ignores case, so `CONFTEST.py` is `conftest.py`. Also
   refused: a path through a link to another file, and text with characters that would make the
   diff read differently from what the code does (controls but tab and newline, a lone carriage
   return, line separators, text direction, zero-width, tags). Nox's `code_list` shows each
   change's state, not what the checks printed: that is on the Changes page.
2. **Reviewing.** Control Room → Changes shows each change with its full diff, file by file.
   **Apply** asks for a confirmation that repeats the files. It sends back a digest of the diff
   on the screen; a draft Nox changed since is refused ("look at it again"). From then on the
   change is frozen: Nox's tools start a new draft. Apply and Undo wait while a film plays (a
   song resumes where it was after the restart). Then the house computer:
   - refuses unless the draft still has the digest the admin approved, every file is one Nox may
     change (checked again, with its own copy of the rule), the source has no uncommitted edits,
     is at the draft's commit and each file is exactly the diff's "before" (draft it again);
   - makes the backup: the git tag `houseos-backup/<id>`, plus the running release (without
     Docker) or the running images re-tagged `:backup-<id>` (Docker);
   - writes the files and commits them as `Nox: <summary>`;
   - runs the checks: without Docker ruff, the SQLite tests (compared with the same tests before
     the change) and the screens' build, in a jail (bubblewrap: only the system, the checkout, the
     app's Python and `node_modules`, read-only; nothing writable but the build's output; no
     `/mnt/house-storage`, home, HouseOS state, sockets, network or other processes); with Docker the image
     build and an import check in the new image. A failed check goes back to the backup and
     deploys nothing;
   - looks again for a film (the checks take minutes): one playing puts everything back, and Undo
     waits the same way;
   - deploys and restarts (music resumes where it was), then checks the health: if HouseOS
     doesn't come back, it returns to the backup by itself.
3. **Keep or Undo.** After an apply, the backup stays listed until **Keep** (which deletes it).
   **Undo** returns to it (only while nothing else was committed on top; otherwise `git revert`).
   Updates wait while a backup is waiting. `./houseos.sh update` puts your `Nox:` commits back on
   top of the new version; if one conflicts, nothing is updated: revert it (`git revert <commit>`)
   or redo it by hand, then update. A backup tag without its change on the page (its draft file
   was deleted) goes by hand: `git tag -d houseos-backup/<id>`.

**Setting it up.** The app reads the source at `HOUSEOS_SOURCE_ROOT`. Docker does it for you: the
HouseOS folder is mounted read-only at `/source`, and the Control Room buttons (`./houseos.sh
buttons on`) run the apply. Without Docker: set `HOUSEOS_SOURCE_ROOT` to the git checkout in the
app's environment file, install bubblewrap (`apt install bubblewrap`), `houseos-code.path` and
`houseos-code.service` (they run `deploy/code_change.py` as the checkout's owner), and set
`HOUSEOS_CODE_USER` to that owner in `houseos-control.service`. Without it, Nox answers that code
changes aren't set up.

The checkout's owner is often an admin account (sudo, Docker), and the checks run drafted code,
so `houseos-code.service` is fenced in: no privilege gain (`NoNewPrivileges`, so no sudo), a
read-only system, the owner's home hidden except HouseOS's state folder and the Python it runs
on, `HOME` a private `/tmp`, network only to this computer (the health check), no socket that
gives root back (Docker, containerd, LXD, snapd, hwctl, D-Bus and polkit, systemd, Tailscale,
SSH), and the checks in their jail. It loads `code_rules.py` as one file, never the `houseos`
package, so no drafted code runs outside the jail. The control broker lets that owner look at and restart the app services only (API,
worker, maintenance, cinema, voice, codex): not the sound or TV path, and no shutdown.

## Rules

- Code over model: when code can decide, code decides; the model picks among real options.
- Secrets never enter chat, logs, docs or git: keys go into the app's secret fields.
- Never cut the music: restarts between songs or with `resume-music`; never the sound player.
- Never test on someone's devices (TV, speakers) without asking.
- Words on screen are short and useful; French uses "tu".
- One change, one test; the checks pass before anything is deployed.
