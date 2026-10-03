# HouseOS interface: a working guide

React 19, TypeScript and Vite, in `frontend/`. The built interface is committed in `frontend/dist`,
so you only need Node 22 and npm to change it. There is no demo data and no fake success: empty,
unavailable and unconfigured states say so.

## Structure

- `src/main.tsx`: session bootstrap, sign-in, routing and which rooms a person may open.
- `src/shell.tsx`: the frame (status bar, rail or dock, the Now bar and sheet, the command
  palette). `src/nav.ts` holds routes and old-path aliases.
- One file per room, its CSS beside it (`music.tsx` is Listen, `watch.tsx` Watch, `control.tsx`
  the Control Room…). The full, always-current list of files, with what each exports, is in
  [CODE-INDEX.md](CODE-INDEX.md) (made by `python3 tools/code_index.py`).
- `src/design/`: the design system (`docs/design/SYSTEM.md`): cascade layers, controls, patterns,
  overlays, display pieces, icons, motion, art slots, the theme runtime (`theme.ts`) and the
  generated tokens (`generated/`, made from `themes/` by the theme kit). Rooms use these and style
  only their own layout, in `@layer rooms`, with tokens. `scripts/design-check.mjs` fails the build
  on a raw value, a raw control, an emoji or an undeclared layer. `src/sprites.ts` and `src/pixel.ts`
  hold the pixel art, drawn in the theme's colours.
- One interface. The original look is the **Legacy** theme (`themes/carved-night`).

## Shared pieces

Everything a room needs comes from `./design` (the full list, with the rules, is in
`docs/design/SYSTEM.md`): `Button`, `Field` and the inputs, `Sheet` and `ConfirmSheet` (never
`confirm()`), `Form` (busy submit, the failure in words), `List`/`ListRow`, `State` (empty, loading,
error, offline, not configured, no permission), `Notice`, `Problem` (an error with a retry),
`MoreBelow` (a list that grows as you scroll), `Slot` (the theme's art), `ReviewDetails`, `tone` (a
resident's colour), `PageGuard`.

`api.ts`:

- `api(path, method, body)`: same-origin authenticated requests with CSRF; errors become `ApiError`.
- `useData(path, {interval})`: a cached GET shared per path; polling pauses while the tab is hidden,
  and server events refetch only the paths mapped to their topic.
- `usePages(base, next)`: pages merged by id; `next` returns the query for the following page
  (for example `offset=24`, or a `before` cursor) or null at the end.
- Formatting helpers (`clock`, `time`, `bytes`…). The signed-in user comes from `useUser()`.

`messages.ts` turns server codes (errors, job states, probes) into sentences. No page shows a raw
code; an unknown code reads as a plain sentence.

## Text and translations

Every visible string goes through `t("English text")`. French lives in `locale_fr.ts`. `npm run build` runs `scripts/i18n-check.mjs` first and fails
when a literal `t("…")` string has no French translation, or when a French entry is no longer
used anywhere. Wording rules are in
`docs/design/COPY.md`; the visual direction is in `docs/design/BRIEF.md`.

## Build and develop

```bash
cd frontend
npm ci --ignore-scripts   # exact versions from package-lock.json
npm run build             # translations, design guards, TypeScript, Vite, the service worker
npm run dev               # 127.0.0.1:5176, /api proxied to 127.0.0.1:8990 (or $HOUSEOS_API)
```

Add the dev origin to `HOUSEOS_ALLOWED_ORIGINS` while developing.

## Offline and sharing

`public/sw.js` caches only the public shell, hashed JavaScript/CSS and decorative art on the same
origin. It never caches `/api/` responses, file downloads, media streams or conversations. Offline,
only Capture opens, for the last signed-in account; drafts and the file outbox are kept per account
in IndexedDB and upload only after reconnecting and a deliberate action. Logout clears them.

The manifest declares a share target at `/capture/share` (text, links, files). Shared items land in
the sharing account's outbox; uploading stays a separate manual step.

## Artwork

`assets/` holds the art sources, `assets/manifest.json` records every export, and exports live in
`frontend/public/art/`. `python3 assets/check.py` verifies them. Controls stay HTML over the art,
with readable text; motion respects `prefers-reduced-motion`.

## Browser tests

`frontend/tests/*.cjs` are Playwright scenarios. `npm run test:browser` (optionally with name
filters) runs them one by one against a disposable test API on `http://127.0.0.1:8893` and writes
screenshots and results to `frontend/evidence/latest` (ignored by git). They need test identities:
adapt `tests/session.cjs` first. They never start physical playback, restart services or change
real accounts. They do not prove that a speaker, TV or phone works; see TESTING.md.
