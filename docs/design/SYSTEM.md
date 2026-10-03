# The HouseOS design system

How the interface is built so that its look is a **theme**: data a person can change without
touching a component. Read this before changing any style.

## Where things are

| Path | What |
|---|---|
| `themes/` | The theme packs (data only): `base` (every token, neutral), `carved-night` (the default), `linen-morning` (warm and light), `canary` (debug). How to make one: `themes/README.md`. |
| `backend/houseos/theme_kit/` | The pipeline (Python standard library): colour maths, ramps, tokens, checks, CSS, packs. `PYTHONPATH=backend python3 -m houseos.theme_kit --help` |
| `frontend/src/design/generated/` | `themes.css` and `themes.ts`, made by `theme_kit build` from `themes/` (committed; a backend test fails when stale). |
| `frontend/src/design/layers.css` | The cascade order. |
| `frontend/src/design/theme.ts` | The runtime: which theme and scheme, applied on `<html>`; `useTheme()`, `token()`, `palette()`, `qrColours()`. |
| `frontend/scripts/design-check.mjs` | The guards (run by `npm run build`); `npm run census` prints the counts. |
| `frontend/tests/theme-canary.cjs` | The canary diff (see below). |
| `frontend/tools/` | `screens.cjs` (screenshots of every place, any UI, theme, language, size), `pixel-diff.mjs`. |

## Cascade layers

```
@layer reset, tokens, theme, base, layout, components, patterns, rooms, utilities, overrides;
```

`tokens`: Base on `:root` · `theme`: every other theme on `[data-theme="<id>"]` (installed themes
too) · then the design system's own layers; a room's CSS is in `rooms`. A later layer wins whatever the selectors, so nothing fights specificity. Every CSS file
declares its layer (a guard checks).

## Tokens

Four tiers. A theme sets **seeds** (and any semantic value it wants to pick itself); the kit makes a
12-step **ramp** per seed and maps meanings onto steps, so contrast is right by construction and
checked anyway. Components read **semantic**, **material** or **component** tokens, never ramps and
never literal values.

| Tier | Names | Example |
|---|---|---|
| inputs | `seed.*` → `ramp.<seed>.1–12` | `seed.accent: oklch(0.64 0.085 195)` |
| semantic | `--c-*`, `--text-*`, `--radius-*`, `--elev-*`, `--dur-*`, `--ease-*`, `--icon-stroke` | `--c-fg-muted`, `--text-title-m` |
| material | `--mat-<name>-*` (canvas, surface, raised, overlay, sunken, inverse, paper, media, screen) | `--mat-sunken-shadow` |
| part | `--part-<name>-*` (page, status, rail, dock, nowbar, header, panel, sheet; each defaults to a material) and `data-part-<name>` variants | `--part-dock-bg`, `data-part-panel="flat"` |
| contract | `--space-*`, `--border-*`, `--chrome-*`, `--icon-s/m/l`, `--z-*`, `--bp-*` (the same in every theme) | `--space-4`, `--z-dock` |

The full catalogue with Base values: `python3 -m houseos.theme_kit tokens`.

**Sizes are the contract: a theme changes how blocks look, never how big they are.** Spacing,
border widths, chrome heights, icon boxes, z order and breakpoints are fixed; `density` in
`theme.json` is a word for the brief and scales nothing. Material edges (`--mat-*-border`) are
always 1 px, any colour or style. Glyphs and Nox draw in fixed boxes (glyphs 32 / 48 px, Nox
32 / 48 / 64 px), pixel or line. Text keeps to a band (see the checks). What still varies, on
purpose: a face's own widths (roughly ±15 %, so layouts must take wrapping), a filled art slot's
own box (e.g. the hero band of `home.hero.backdrop`). Under a title, `PageHeader` shows a tip
about the room (`tips.ts`), the same in every theme: themes add no sentences. Check layouts with slots empty and filled, in French.

Every theme compiles to **final values** (no `var()` chains), complete per scheme, so a `data-theme`
preview inside another theme shows exactly that theme. Rooms: the shell sets `data-room` on
`<html>`; each theme has `--c-room`, `--c-room-fg`, `--c-room-soft`, `--c-room-line` per room.

**Parts, pieces and words**. The shell and the page's big blocks read `--part-*`, never a
material directly, so a theme styles each alone. Size-neutral variants (`theme.json` `parts`) set
`data-part-<name>` on `<html>` and on any scoped preview; their CSS sets inherited custom properties
(`--pv-*`), so the nearest choice wins. Pieces a theme redraws (`sprites.json`, ids in
`themes/_schema/sprites.ids.json`) are read by `Glyph`, `Mascot`, `AvatarPicture` and the house
titles through `usePiece()` / `themeGrid()`. Words (`flavor.json`) are only the titles' names (`useTitleLook`).
`useThemeInfo()` gives the theme drawing a part of the page: a draft's (`PreviewInfo`), a scoped
preview's (`ThemeScope`), else the one worn.

Text is styled only by **text styles**: `font: var(--text-body-m)` plus
`letter-spacing: var(--text-body-m-tracking)` and `text-transform: var(--text-body-m-case)`.

## Runtime

`<html data-theme data-scheme data-room data-motion data-motion-effective>`. The person's theme
(`Preferences.theme`, `""` = the house's) over the house's (`HouseSettings.theme`, default
`carved-night`); an unknown id falls back to the house's, then the default. `scheme`: the theme's
own, `dark`, `light`, or `device` (follows the device when the theme has both). The last theme is
kept in `localStorage` and applied before the first paint; `index.html` starts in the default so
nothing flashes. JS-drawn things (sprites, scenes, placeholders, QR codes) read tokens and cache by
the theme (`useTheme()`); charts and people's colours use `var(--c-data-N)` / `var(--c-person-N)`.

**Installed themes** (made in the studio or imported as `.houseos-theme` packs) live beside the
house's data (`<runtime_root>/themes/<id>/`), are checked again and compiled by the server, and
join the bundled ones through `GET /api/v1/themes` → `setInstalled()`: each one's stylesheet
(`/themes/<id>.css?v=<hash>`, only its `[data-theme]` custom properties and its fonts) is linked
once. Administrators make and share themes (the authoring guide is `themes/README.md`).

**Surfaces**: a part with a picture (`<part>.surface` slot) gets `data-surface-<part>` on
`<html>` and its `--surface-<part>`, `-size`, `-border` (9-slice) and `-render` properties; one
block in `patterns.css` draws them on the part's `::before`, behind its content. Scoped previews
get the same properties (`surfaceVars`), "none" for the parts their theme leaves bare.

**Offline-safe actions** (`outbox.ts`): a grocery's tick, a new grocery, a new or finished
task and a new note wait on the device when the house can't be reached ("N changes waiting" in
the top bar) and are sent once it can: `sendOrKeep()` for exactly these, `api()` for the rest.

## Guards (fail the build)

`design-check.mjs`: CSS colour, font, radius, shadow, z-index and duration values come from tokens;
every stylesheet declares its layer; `@media` uses 600 / 900 / 1232 / 1600 px; no colour literals in
TypeScript; outside `src/design/`, no raw `<button>`, `<input>`, `<select>`, `<textarea>`,
`<dialog>` and inline styles only set custom properties; no emoji as icons; no `em`, `lh` or `ex`
lengths in sizes (widths, heights, gaps, padding, margins, insets), so no size follows a theme's
face (`html` keeps the browser's 16 px, so `rem` doesn't either; the one exception centres a
hint's first line on its 40 px close button). Any problem fails the
build (the allow-list used during the migration is gone with the legacy stylesheets).

## The canary

`themes/canary` gives every colour token its own loud value (and odd corners and a typewriter face).
`tests/theme-canary.cjs` draws each place in Base then in Canary: an element whose colour, font,
corners or shadow don't change is drawn outside the tokens. Every place must have none.

## Checks a theme must pass (all code)

`theme_kit check <id>`: manifest · contract (spacing, border widths, chrome, icon boxes, z order
and breakpoints fixed; material edges exactly 1 px, solid, dashed or dotted, any colour; paper tilt
±2deg; media never filtered) · text band (component styles ≤ Base + 1 px and their line within
±2 px of Base's; `action` in Base's case, tracking ≤ Base + 0.02em; `label` and `caption` tracking
≤ 0.1em; display ≤ Base + 10 %; the brand's line ≤ 32 px) · tokens resolve (no unknown names,
no loops) · text ≥ 11 px, body never in the display face, motion and icon bounds · the contrast
matrix (WCAG: 4.5 for text, 3 for marks, edges and the focus ring, on every ground, material and
room; APCA reported) · distinct colours (states, rooms, people; a
colour-blind note) · fonts (licence, latin-ext for French), art (size, safe SVG), data only ·
flavour text (en + fr, lengths) · sprites. It writes the theme's `REPORT.md`.

## Components (`frontend/src/design/`, import from `./design`)

Rooms compose these; they never style raw elements (the guards forbid raw `<button>`, `<input>`,
`<select>`, `<textarea>`, `<dialog>` outside `src/design/`). Text passed in is already translated.
Every piece, in every state and theme: **the theme workshop, `/workshop`** (everyone who lives
here, not guests; `/workbench` and `/design` lead there): a tour of the parts on `ThemePreview`
(the app in miniature, scoped to any theme), ideas, *Every piece* (the catalogue of parts, slots and
pieces, then the full specimen with *Draw it in* and *Compare themes*) and three ways to make one.
**Remix** (`/workshop/remix?id=`) edits a draft by hand with a live preview.

| Kind | Components |
|---|---|
| Layout | `Page` (width, rhythm), `Stack`, `Cluster`, `Grid` (`space` = a step of the scale) |
| Controls | `ColorInput` (a theme colour: swatch + the browser's picker; `toHex()` for any CSS colour), `ColorField` (a light's colour: common hues + any), `SwatchPicker` (one of a few colours, a radio group), `Button` (primary · secondary · quiet · danger · link; s · m · l; `busy`, `pressed`), `IconButton` (label required), `LinkButton` (a link that looks like a button: downloads, exports), `FileButton` (choose files: the browser's own field can't be themed or translated), `Field` (label, hint, error), `Input`, `Textarea`, `Select`, `Combobox`, `SearchInput`, `SecretInput` (a key or token, masked with a Show button; not a password field), `Switch` (applies at once), `Checkbox`, `Radio`, `Segmented`, `Slider` (`onCommit` once on release), `Chip` (filter · tag · person · count, removable) and `ChipGroup` |
| Display | `Text` (a text style), `Status` (mark + word), `Badge`, `Avatar`, `Progress` (bar, stepped, busy), `Spinner`, `Skeleton`, `Divider`, `Kbd`, `Tooltip`, `Surface` (a material), `Media` (poster or cover over a placeholder) |
| Identity | `Icon` (line icons by name), `Glyph` (rooms, transport: pixel or line, per theme, or the theme's own piece), `Mascot` (Nox), `AvatarPicture`, `PieceFill` (a piece scaled by whole pixels to a box), `Sprite` |
| Patterns | `PageHeader` (title, a tip about the room, one primary action, a `Hint` of two lines at most, *More* for the rest), `SubNav`, `Toolbar`, `Section` (no box; `aside` puts its title beside its controls in settings), `Panel` (a dashboard module: icon, title, *Open* link, content — Home's board), `List` + `ListRow` (with a `control` beside it for selection), `MediaCard`, `Shelf`, `Tile`, `State` (empty · loading · error · offline · not configured · no permission), `Notice`, `QuickAdd`, `Disclosure` (folded detail), `MoreBelow` (a list that grows as you scroll), `Form` (fields, busy submit, the failure in words), `EmojiTray` (emoji as message content), `SettingsLayout` (sections parted by a hairline, short fields in pairs, level-3 and `aside` sections with the title beside the controls from 1232 px) |
| Overlays | `Sheet` (bottom · side · center; the only modal), `ConfirmSheet`, `Menu`, `Popover` (a small window by its button, not modal: who's home), `toast()` + `ToastRegion`, `CommandPalette` (ranked search; numbered quick actions with modes: `Command.mode`) |
| Art | `Slot` (decoration only where a theme fills a slot: `themes/_schema/slots.json`; an image's `rendering` and `fit` as the theme says), `Scene` (the "hall" generator) |

States are `data-*` attributes (`data-variant`, `data-selected`, `data-busy`…). Spacing props are
steps of the scale, never pixels.

## The shell (`frontend/src/shell.tsx`)

- **Status bar** (48 px): the house's name (and the theme's `status.backdrop` art), the palette
  button (⌘K / Ctrl K), connection, clock, work in progress, inbox, the person's menu.
- **Places**: a rail on wide screens (names or icons only, remembered per device); on phones a dock
  of five with Ask in the middle (Home, Listen, Ask, Watch, House). Files, Smart home, My space, Me
  and Control Room are in the person's menu and the palette.
- **Now bar** (56 px, only while something plays): the TV first when a film plays, a switch for the
  music; it opens the Now sheet (both, full controls, what's next). What the TV answered (a truthful
  stop) shows on it. It leaves out what the page already shows (music on Home and Listen, the film
  on Home). Any page opens the Now sheet with `dispatchEvent(new Event("houseos:now"))`.
- **Command palette** (⌘K): places, common actions, and "Ask Nox: …" as the last row. Nox also
  opens from Ask and from any page with `houseos:ask`.
- **Toasts** above the Now bar; **In progress** sheet for background work.
- Phone chrome: at most 168 px with music and a film playing (`tests/shell-budget.cjs`).
- Pages that fill the screen use `--shell-top`, `--shell-bottom` and `--shell-pad-top`.
