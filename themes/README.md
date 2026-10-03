# HouseOS themes: the reference

A theme is a folder of **data**: colours, type, shapes, materials, motion timing, art, moving
layers, pixel pieces and the house titles' names. It can't change what the app does or where
things are. The theme kit turns it into CSS and checks it; code judges contrast and
completeness, so your eyes are free for taste.

This page is the complete reference, accurate to the kit's checks. For **how** to make a good
theme, read [`_kit/METHOD.md`](_kit/METHOD.md). **AI agents start with
[AGENT-KIT.md](AGENT-KIT.md)** (orientation, working with the person, commands).

## Quick start

```bash
PYTHONPATH=backend python3 -m houseos.theme_kit new my-theme --scheme dark   # from the templates
# write the direction (METHOD §2), then the seeds in themes/my-theme/tokens.json
PYTHONPATH=backend python3 -m houseos.theme_kit check my-theme               # every check → REPORT.md
PYTHONPATH=backend python3 -m houseos.theme_kit build                        # CSS for the app
node themes/_kit/tour.cjs my-theme                                           # screenshots + audit
```

`new --scheme light` starts from Base's light seeds (dark and light need different lightness);
`new <id> --from <other>` forks a theme. Other commands: `tokens` (the catalogue: every token,
its Base value, its purpose), `font` (see *Fonts*), `pack` (see *Sharing and installing*),
`check --all`.

**In the app, no terminal:** *Your preferences → Appearance → Make it yours*, or the **theme workshop**
(`/workshop`): a tour of every part on a live copy of the app, ideas, every piece, and **Remix**,
an editor for colours, type, corners, parts, pictures, pixel pieces and title names with a live
preview and these same checks. Or ask Nox (*Make one with Nox*): the studio follows this guide.

## Sizes are the contract: a theme is a skin on the same blocks

Every screen is built from the same blocks (`frontend/src/design/`: buttons, rows, panels, sheets,
the shell), laid out on the same spacing, with the same control, chrome and icon sizes. **A theme
changes how the blocks look, never how big they are.** That is why a theme can't break a screen
that fits in Base.

**Fixed in every theme** (the kit refuses them): spacing (`space.*`), border widths (`border.*`),
chrome heights (`chrome.*`), icon boxes (`icon.s/m/l`), z order (`z.*`) and breakpoints (`bp.*`).
`density` in theme.json is only a word for the brief: it scales nothing. Glyphs and Nox draw in
fixed boxes (glyphs 32 or 48 px, Nox 32, 48 or 64 px), whether the identity is pixel or line.

**Kept within limits:**

- A material's or part's edge (`material.*.border`, `part.*.border`) is exactly **1 px**,
  `solid`, `dashed` or `dotted`, in any colour. A borderless look is `1px solid transparent`,
  never `none`. Fields keep a visible edge (`material.sunken.border` is never transparent).
- Paper tilts (`material.paper.rotate`) 2deg at most.
- Text stays in a band. Component styles (`title-*`, `body-*`, `action`, `label`, `caption`,
  `numeric`) may be at most **1 px** larger than Base, with a line (size × lineHeight) within
  **±2 px** of Base's: enough for a face with small letters to read the same. `action` (buttons,
  tabs, chips) keeps Base's case and at most +0.02em of tracking; `label` and `caption` are tracked
  0.1em at most. Display styles may be at most **10 %** larger; the `brand` line is 32 px at most
  (it sits in the status bar). No text under 11 px; body styles never use the display face.
- Durations 1 s at most; easings are a cubic-bezier list or `steps(1–12)`; `icon.stroke` 1–3.
- Posters and covers (`material.media`) are never filtered.

**Free**: colours (seeds and meanings), faces and weights, radius, shadows and elevation, what
materials and parts look like (colour, edge colour and style, texture, blur, glow, gradients),
motion style, icon stroke, identity (line or pixel), art slots, layers, pieces, title names. Want
a calmer or denser feel? Use weight, contrast, line height inside the band, materials and radius:
not size.

**What still varies, on purpose** (layouts are built to take it):

- **Text widths.** Two faces at the same size are not the same width (roughly ±15 %), so a word
  that fits on one line in Base may wrap in another theme. Check with the tour, which shoots
  French (the longest).
- **Filled art slots** add their slot's own box and nothing else (a filled `home.hero.backdrop`
  adds the hero's band). Every layout is right with every slot empty and every slot filled.
- **Words** are HouseOS's own (a tip under each title, the same in every theme). A theme's only
  words are the house titles' names (see *Words*).

**See it.** The Workbench (`/workbench`, for everyone who lives here, not guests; linked from
*Your preferences → Appearance* and *Control Room → Themes*) lays out every block. *Draw it in* draws the page
in any theme without changing yours; *Compare themes* puts themes side by side on wide screens.
The tour (`node themes/_kit/tour.cjs <id>`) shoots the real rooms.

### The blocks

Sizes in px; `space.1–8` are 4, 8, 12, 16, 24, 32, 48, 64. Every edge is 1 px.

| Block | Fixed (every theme) | The theme decides |
|---|---|---|
| Button | height 40 · 44 · 52 (s · m · l), at least as wide as high; padding 12 · 16 · 24; gap 8; label on one line, ellipsised | `part.control.*` (ground, shadow, the primary's ground and shadow), variant colours, `radius.control`, `text.action` face and weight |
| Icon button | a square of 40 · 44 · 52; icon 16 (20 at l), or a glyph's 32 box (48 at l) | as Button; `icon.stroke` |
| Input / Select | at least 44 high; padding 8 × 12; room for the arrow or clear button 48; textarea at least 88 | the sunken material (bg, edge colour, radius, shadow), `text.body-m`, placeholder colour, `label` and `caption` for the field |
| Chip | 36 high (40 when it's a button); padding 0 × 12; remove button 36 wide; 8 between chips | `radius.chip`, colours for selected, tag, person and count, `text.action` |
| Segmented | choices 40 high, padding 0 × 12; track padding and gaps 4; wraps rather than hides a choice | sunken track, raised material for the chosen one, `radius.control`, colours |
| Switch / Checkbox | row at least 44 high, gap 12; switch 44 × 26 with an 18 knob; checkbox 22 | colours (the accent when on), edge colour |
| Slider / progress bar | the control's size | `part.meter.*` (track, a pattern over the bar, the thumb and its radius) |
| List row | at least 56 high; padding 8 × 4, gap 12; title and detail one line each, ellipsised | divider, hover and selected colours, `radius.control`, `body-s` and `numeric` |
| Panel | padding 16, gap 12; head at least 32 high | `part.panel.*`, variant `parts.panel`, `panel.surface`, `title-s`, link colour |
| Tile | at least 104 high; padding 16, gap 8 | the surface material, `label`, `title-l`, `body-s` |
| Section | no box; gap 12; head at least 40 high | `title-m` / `title-s`, lead colour |
| Sheet | from the bottom on phones (up to the screen less 24); from 900 px centred 560 (860 wide) or at the side 480 (720 wide); head padding 8 (24 at the start), body padding 24 (8 at the top); grip 44 × 20 | `part.sheet.*`, `sheet.surface`, blur, scrim, `title-l`, motion |
| Notice / Hint | hint: two lines at most then *More*, its close button 40; notice: padding 12 × 16, its action beside it from 900 px | surface colour, edge colour, `radius.control`, tone colours, `body-s` |
| Status bar | 48 high (`chrome.status`) | `part.status.*`, `text.brand`, the `status.backdrop` slot, status layers |
| Rail | from 900 px: 232 wide with names, 88 with icons only (`chrome.rail`); padding 12 | `part.rail.*`, `rail.surface`, the `rail.art` slot, rail layers, `color.bg.current` / `fg.current` for the current room |
| Dock | 64 high (`chrome.dock`) plus the phone's safe area; five doors (Home, Listen, Ask, Watch, More), their marks in a 32 row; Ask's plate 44 × 32 | `part.dock.*`, `dock.surface`, variant `parts.dock`, `caption`, the room's light on the current door |
| Now bar | 56 high (`chrome.nowbar`), 8 above the dock | `part.nowbar.*`, `nowbar.surface`, variant `parts.nowbar` |
| Music deck | the player on Listen, up to 480 × 560 | `deck.surface` (a skinned deck gets a 16 px padding, so a frame never runs under the cover and buttons), deck layers |
| Page header | the title's text style; its banner never adds height | `part.header.*`, variant `parts.header`, the `header.banner` slot, header layers (the tip under the title is HouseOS's) |
| Home hero | the greeting's band | `home.hero.backdrop`, `part.hero.*`, hero layers |
| Page | the window | `part.page.*`, the `page.backdrop` slot, page layers |
| Glyph | a 32 box (48 at l), pixel or line | identity, colours, `icon.stroke` |
| Mascot | a 32 · 48 · 64 box, pixel or line | identity, colours, `nox.*` pieces |
| Avatar | 28 · 40 · 64; a 2 ring (`border.strong`) | `radius.avatar`, people's colours, the initials' text style, `avatar.*` pieces |

## Parts: each block its own

The shell and the page's big pieces are **parts**, each with its own tokens (`part.<name>.*` in
`tokens.json`). In Base each part takes a material (the dock is the overlay, the panels the
surface…), so a theme that sets only materials still looks whole; set a part's tokens to style it
alone: a dock of lacquered wood while sheets stay paper. Edges are `1px solid|dashed|dotted
<colour>`; sizes never change.

| Part | Tokens (Base value → what it is) |
|---|---|
| `page` | `bg`, `texture` (a tiling `url(art/…)` over the whole page), `scrim` (over the `page.backdrop` picture and the page layers, under the content; Base `alpha(canvas, 82%)`), `quiet` (a plaque behind quiet buttons, tabs and chips when art shows behind the page), `ink-shadow` (under the page's headings), `gallery` (behind rows and grids of posters and covers) |
| `status` | `bg`, `border`, `texture`, `art-opacity` (how much `status.backdrop` shows, 0–1) |
| `rail` | `bg`, `border`, `texture`, `ink-shadow` (under the rail's words when `rail.surface` is behind them) |
| `dock` | `bg`, `border`, `texture` |
| `nowbar` | `bg`, `fg` (its text: a dark bar in a light theme needs light text), `border`, `radius`, `shadow`, `texture` |
| `header` | `fg` (the title), `kicker` (the words above the title in unified rooms), `banner-fade` (where the banner fades out), `banner-wash` (0–1: how strongly the room's light tints a banner; 0 for none; Base 1), `frame-bg`, `frame-border` (the framed variant's box) |
| `panel` | `bg`, `border`, `radius`, `shadow`, `texture`, `head` (a panel's icon and link line) |
| `sheet` | `bg`, `border`, `radius`, `shadow`, `texture` |
| `hero` | `width` (Home's picture on wide screens: how much of the greeting's box it takes, from the right; Base 60%), `fade` (how far into the picture it fades in from the words' side; Base 40%) |
| `control` | `bg` (buttons' ground: a colour, or a gradient over one), `shadow` (an outlined button's shadow), `primary-bg`, `primary-shadow` (the main button: a gradient, an inset bevel, a glow) |
| `meter` | `track` (the empty part of a slider), `pattern` (drawn over sliders and progress bars: segments, stripes or gloss, as a gradient or `url(art/…)`), `thumb` (a slider's handle), `thumb-radius` (0 for a square handle) |

Two colour tokens style **where you are** (the rail's current room, the settings menu's current
page, the picker's mini rail): `color.bg.current` (Base: `bg.selected`) and `color.fg.current`
(Base: `fg.default`). They are checked as a contrast pair, so a theme can make "current" a solid,
inverted block.

Some parts also have **variants**: a different treatment in the same boxes, chosen in
`theme.json` → `"parts": {"panel": "flat", "header": "banner"}` ([`_schema/parts.json`](_schema/parts.json)):

| Part | Variants |
|---|---|
| `header` | **plain** (default): the title on the page · **banner**: the `header.banner` art behind the title, fading into the page · **ribbon**: a page's kicker (Home's date) as a small ribbon in the room's light · **framed**: the title in a box of its own (`part.header.frame-bg`, `frame-border`), for a picture behind every page |
| `panel` | **card** (default): a filled card with an edge · **flat**: no card, a hairline above each panel · **outlined**: an edge only, the page showing through |
| `dock` | **flush** (default): a bar along the bottom (phones) · **floating**: a rounded bar floating above the bottom edge |
| `nowbar` | **floating** (default): a rounded bar over the page · **docked**: a flat bar across the width, above the dock |

**A picture behind every page** (`page.backdrop`) needs the page's own pieces to stand clear of
it. Three page tokens do it, all off in Base: `part.page.quiet` puts quiet buttons, tabs and chips
on a plaque; `part.page.gallery` puts lists and rows of posters and covers on a ground of their
own (never picture on picture); `part.page.ink-shadow` gives the page's headings a dark edge.
Inside panels and sheets they switch off. Pair them with the **framed** header, a visible panel
edge (`part.panel.border`) and a `part.page.scrim` that still lets the art through (Zabiwa's
settings are an example).

## What's in a theme folder

| File | Needed | What |
|---|---|---|
| `theme.json` | yes | The manifest: id, names, description, schemes, fonts, identity, `parts`, `slots`, `layers`, `rooms` ([schema](_schema/theme.schema.json)) |
| `tokens.json` | yes | Design tokens in the W3C DTCG format, **only what differs from Base** ([schema](_schema/tokens.schema.json); catalogue: `theme_kit tokens`) |
| `tokens.dark.json`, `tokens.light.json` | no | What changes for one scheme, when the theme has both |
| `BRIEF.md` | yes | The mood, references, do and don't, each picture's source and licence (template in `_studio/templates/`) |
| `flavor.json` | no | The house titles' names and their star mark, in English and French ([schema](_schema/flavor.schema.json)) |
| `sprites.json` | no | The pieces the theme redraws by id ([schema](_schema/sprites.schema.json), [ids](_schema/sprites.ids.json)) |
| `fonts/` | no | woff2 files and their licence, added by `theme_kit font` |
| `art/` | no | SVG, PNG or WebP for slots, layers and textures |
| `REQUESTS.md` | no | What the theme wanted that needs code: the part, what and why |
| `REPORT.md`, `art/card-<scheme>.webp` | made | Written by `check`, and by the tour (the card each picker shows); never edit them |
| `shots/` | made | The tour's screenshots; local only (ignored by git, never checked or shipped) |

A theme folder holds no code: the check fails on `.js`, `.ts`, `.html`, `.py`, `.sh` or `.css`
files (outside `shots/`). Scripts that draw the art live elsewhere (for the bundled themes,
`docs/design/themes/<id>/`).

`theme.json` fields: `id` (the folder's name, lowercase words and hyphens), `schema` (1),
`version` (a whole number; raise it with each change you share), `names` and `description` (en
and fr; names 32 characters at most), `schemes` (`dark`, `light` or both; the first is its own),
`fonts` (`display`, `body`, `mono`), `identity` (`line` icons or `pixel` sprites), `density` (a
word only), `rooms` (`distinct` or `unified`), `parts`, `slots`, `layers`, and optionally
`credit`, `author`, `license`, `hidden` (kept out of the pickers) and `debug`.

`credit` is `{"en": …, "fr": …}`: who made the theme, plain text, 40 characters at most in each
language. It shows small at the rail's foot (wide screens, not with the icons-only rail) and is
never a link.

**Tokens: seeds → ramps → meanings.** Each colour seed (`seed.neutral`, `accent`, `success`,
`warning`, `danger`, `info`, `private`) becomes a 12-step ramp, lightest to darkest in the
scheme's direction (step 9 is the seed itself). Base's meanings (`color.bg.canvas`,
`color.fg.muted`, `color.border.strong`, …) point at ramp steps, so **a theme made of seeds alone
is already complete and legible.** Set a meaning yourself only where the theme needs a signature.
Values can be hex, `oklch(…)`, a `{reference.to.another.token}`, or one of three functions:
`mix(a, b, 40%)` (40 % of `a`, 60 % of `b`, like CSS `color-mix`), `alpha(a, 16%)`, `contrast(bg)`
(the more legible end of the neutral ramp on `bg`).

## The brief and the direction

Before any colour, write the **direction** (`docs/design/themes/<id>/DIRECTION.md`; template and
method in [METHOD §2](_kit/METHOD.md)): the idea, its tells, palette roles, light, type, medium,
a plan for every part, the pieces, discoveries and a never-list. The theme's `BRIEF.md` ships with
it and is shorter:

- **Mood, in one sentence.** Specific enough to argue with: "a warm Lisbon kitchen at 8 a.m.,
  tiles, bread, radio", not "modern and clean".
- **Names**: English and French (32 characters at most).
- **Scheme(s)**: dark, light, or both (then both must be designed, not one inverted). A light
  scheme needs darker accents and statuses than a dark one (see `base/tokens.light.json`).
- **Three to five references, in words**: places, eras, objects, films, prints. Not other apps.
- **Material, shape, edge, type, colour story, identity, motion**: a line each.
- **Do / Don't**: three each.
- **Art**: each picture's source and licence.

For ideas that don't look like every other app, read `_studio/DESIGN-LIBRARY.md`: palette
strategies, type pairings, material recipes, shape languages, motifs, motion and a banned list.

## The order of work

1. **Seeds.** Neutral first (it is 80 % of the screen), then the one accent, then the status
   colours inside the palette's world.
2. **Typography.** Choose the families (`theme_kit font`), then shape three key styles:
   `text.display-l`, `text.title-m`, `text.body-m`. The rest follow from Base.
3. **Shape, depth, materials.** Radii (`radius.*`), elevation (`elev.*`) and the material recipes
   (`material.canvas`, `surface`, `raised`, `overlay`, `sunken`, `inverse`, `paper`, `screen`;
   `media` holds posters and covers and is never filtered).
4. **Rooms, people, data.** `color.room.*`, `color.person.1–8` (residents' colours),
   `color.data.1–8` (charts). A room colour mostly shows as a 16 % tint on the ground: a hue
   opposite the ground's greys out there, so give it more chroma or pull it toward the ground's
   temperature. A limited-ink theme may light every room the same: `"rooms": "unified"` in
   theme.json, and the checks stop asking for distinct room lights.
5. **Motion.** `dur.*` and `ease.*`: the personality from the direction.
6. **Parts.** `part.*` tokens and variants (see *Parts*), controls and meters.
7. **Art, layers and pieces.** Slots, surfaces, layers, `sprites.json`. Plan them together: one
   world, not a collection.
8. **Title names** in `flavor.json`.
9. **`check` → `build` → tour → critique → review round** ([METHOD §5–7](_kit/METHOD.md)).

## Decisions for non-designers

- **Neutral seed**: never a pure grey. Lean it slightly toward the accent's complement, or toward
  the material (warm paper, cool slate). Chroma 0.01–0.03 in OKLCH is plenty.
- **One accent.** It means "act here" or "this is on". If two colours both shout, one of them is a
  room colour or a mistake.
- **Status colours**: success, warning, danger and info far apart in hue *and* lightness (the
  checks measure it, colour-blind simulation included). Make them belong: a terracotta theme's
  danger is a brick red, not a stock #ff0000.
- **Fonts**: one expressive display face (titles only) and one highly legible body face. Match
  x-heights; contrast in structure (serif vs sans), not just weight.
- **Texture or a tonal step?** A tonal step (surface one ramp step above the canvas) separates
  areas. Texture is for a material that *is* the theme (paper, felt, stone) and stays so faint
  that text on it reads as on flat colour.
- **Breathing room** is the same in every theme. For calm, use lighter weights, quieter edges and
  the band's longer line heights; for a dense feel, stronger weights and edges.

## Art slots

Decoration lives in named slots ([`_schema/slots.json`](_schema/slots.json)); every layout is
right with every slot empty and with every slot filled, and Base leaves them empty. A slot takes
an image in `art/` (`"art/x.webp"`) or an object; the scene slots can instead take a scene
generator (`{"scene": "hall" | "room"}`, painted in the theme's colours):

```json
"slots": {
  "home.hero.backdrop": { "image": "art/hero.webp", "rendering": "smooth",
                          "schemes": { "light": "art/hero-day.webp" } },
  "header.banner": { "image": "art/banner.png", "anchor": "bottom",
                     "rooms": { "listen": "art/banner-listen.png",
                                "watch": { "dark": "art/tv-night.png", "light": "art/tv-day.png" } } },
  "state.empty": { "image": "art/basin.png", "fit": "contain" }
}
```

| Field | Values | Default |
|---|---|---|
| `image` | `art/<file>` (SVG, PNG or WebP in the theme's folder) | required |
| `rendering` | `pixel` (hard edges: pixel art stays crisp) or `smooth` (painted or photographic art) | pixel |
| `fit` | `cover` (fills the box, cropped), `contain` (whole, letterboxed), `stretch` (whole, stretched), `slice` (surfaces only: a 9-slice frame) | cover |
| `slice` | with `fit: slice` only: the frame's corner size, 1–400 px | – |
| `anchor` | `top`, `center` or `bottom`: the part kept whole when a tall picture is cropped (`bottom` crops the top first) | center |
| `rooms` | `{room: "art/<file>"}` or `{room: {"dark": "art/…", "light": "art/…"}}`: another picture in those rooms | – |
| `schemes` | `{"dark"\|"light": "art/<file>"}`: another picture in that scheme (only the theme's schemes) | – |

A room's own picture wins over `schemes`. Rooms: home, listen, watch, house, files, ask, me,
control, smart-home, inbox, space, party, games.

Draw at the size below, or a whole multiple for pixel art. `cover` crops the edges on phones:
keep what matters in the middle, and for banners in the band that survives on a phone (METHOD
§4). The check warns when smooth art is smaller than its `min` (it would be upscaled and blur):
draw it bigger, or mark it pixel.

**Surfaces: a picture for every part.** The rail, the dock, the Now bar, every panel, every sheet
and the music deck take a picture of their own (`<part>.surface`), drawn behind their content in
any fit, never changing a size. PNG and WebP keep their **transparency**: transparent pixels show
the part's own ground, and a theme that sets that part's `bg` to `transparent` gets a **shaped
box** (a torn ticket, a cloud) drawn entirely by its picture. Under text, keep a frame's centre
opaque. A 9-slice frame's corners stay whole and sharp; its edges and middle stretch, so one
small drawing frames a box of any size:

```json
"panel.surface": { "image": "art/panel-frame.png", "rendering": "pixel", "fit": "slice", "slice": 16 }
```

| Slot | Kind | Size on screen | `min` | Purpose |
|---|---|---|---|---|
| `status.backdrop` | scene | 320 × 16 strip, the bar's full width | – | a strip behind the house's name and the bar (strength: `part.status.art-opacity`) |
| `home.hero.backdrop` | scene | 240 × 72, scaled | – | the house at the real time of day, on Home |
| `space.room.scene` | scene | 160 × 72, scaled | – | the person's room in My Space |
| `auth.crest` | image | square, 160 | 160 × 160 | the house's emblem on the sign-in page |
| `watch.tv.bezel` | image | 4:3, 480 wide | 480 × 360 | the frame around the TV picture |
| `page.backdrop` | image | the whole window, cover | 1600 × 900 | a picture behind every page, under `part.page.scrim` |
| `header.banner` | image | the header's width × 160, fades into the page | 1200 × 160 | a banner behind each room's title (with `parts.header: banner`) |
| `state.empty` | image | square, 96 | 96 × 96 | the picture of an empty state (instead of Nox) |
| `rail.art` | image | the rail's width × up to 240, at its foot | 232 × 240 | a decoration at the bottom of the rail (wide screens) |
| `rail.surface` | surface | the rail, full height (232 wide) | 232 × 600 | the rail's own picture |
| `dock.surface` | surface | the phone's width × 64 | 390 × 64 | the dock's own picture (phones) |
| `nowbar.surface` | surface | up to 960 × 56 | 960 × 56 | the Now bar's own picture |
| `panel.surface` | surface | any panel (a 9-slice frame fits all) | 320 × 200 | every panel's picture or frame |
| `sheet.surface` | surface | a sheet, up to 720 wide | 720 × 400 | every sheet's picture or frame |
| `deck.surface` | surface | the music player on Listen, up to 480 × 560 | 320 × 320 | the deck's skin (a 16 px padding keeps the frame clear of the cover and buttons) |

**Textures.** A material's or part's `texture` token is `url(art/<file>.svg)` (or PNG, WebP): a
small tile in the theme's `art/`, repeated at its own size. The check fails if the file is missing
or the URL leads anywhere else. `part.meter.pattern` may also be `url(art/…)`.

**Budgets and safety.** Each image ≤ 200 KB, all art ≤ 2 MB. SVG without scripts, event handlers,
`foreignObject`, entities or outside links. No text in images. Write where each picture came from
(drawn by code, the person's own, its licence) in BRIEF.md; a bundled theme's art is also
recorded in the repository's `assets/manifest.json`.

## Layers: pictures the app moves

`theme.json` `"layers"` is a list of pictures drawn in a place and moved as far as the person's
motion level allows. Layers never catch a click, except pieces that answer one (`poke`). At
most **12 layers**, **48 particles** in all and **6 pokes**.

```json
"layers": [
  { "image": "art/steam.png", "where": "page", "fit": "natural", "particles": { "count": 10, "motion": "rise", "seconds": 14 }, "opacity": 0.5 },
  { "image": "art/clouds.png", "where": "hero", "fit": "repeat-x", "anchor": "top", "drift": [6, 0] },
  { "image": "art/bat.png", "where": "page", "fit": "natural", "scale": 3, "frames": { "count": 4, "fps": 8 },
    "cross": { "seconds": 9, "every": 60, "from": "right" }, "schemes": ["dark"] },
  { "image": "art/grain.png", "where": "page", "fit": "repeat", "above": true, "opacity": 0.08, "blend": "overlay" }
]
```

| Field | Values | Default | Notes |
|---|---|---|---|
| `image` | `art/<file>` | required | |
| `where` | `page`, `hero` (Home's picture), `header` (the page header), `rail`, `rail-foot`, `status`, `deck` (the music player) | required | `rail-foot`: a box of its own just above the Ask Nox card at the rail's foot, up to 240 px high (a quarter of the screen's height at most), hidden when the rail shows icons only |
| `fit` | `cover`, `contain`, `repeat`, `repeat-x`, `natural` | cover | `natural`: the picture at its own size × `scale`, placed at `anchor` |
| `anchor` | `center`, `top`, `bottom`, `left`, `right`, `top-left`, `top-right`, `bottom-left`, `bottom-right` | center | |
| `scale` | whole number 1–8 | 1 | tiles and natural pieces drawn bigger (pixel art) |
| `rendering` | `pixel`, `smooth` | pixel | |
| `opacity` | 0.05–1 | 1 | |
| `blend` | `normal`, `screen`, `multiply`, `overlay`, `soft-light` | normal | |
| `rooms` | a list of rooms | all | only in those rooms |
| `schemes` | a list of the theme's schemes | all | e.g. a night-only moon |
| `under` | `true` | – | behind the place's own picture (a sky seen through its clear parts); `page`, `hero`, `status` or `header` only; not with `above` |
| `above` | `true` | – | over the page's content: a finish (grain, scanlines, a vignette); `where: page` only, opacity 0.15 at most |
| `depth` | 0–1 | 0 | parallax: follows the pointer (up to 24 px) and a little the scroll; full motion only |
| `playing` | `true` or `false` | false | moves only while music plays; only the deck knows, so use it on `deck` layers |

**One way of moving** (at most one of these per layer):

| Field | Values | Needs | What |
|---|---|---|---|
| `drift` | `[x, y]` px a second, each −200 to 200 | `fit: repeat` or `repeat-x` | a seamless tile that pans (clouds, fog, a grid); it moves one tile per loop |
| `cross` | `{"seconds": 2–120, "every": seconds–600, "from": "left"\|"right"\|"top"\|"bottom"}` | `fit: natural` | a piece crossing the place now and then (a train, a bat); `every` defaults to `seconds`, `from` to left; the first crossing starts after a third of `every` |
| `particles` | `{"count": 1–24, "motion": "rise"\|"fall"\|"float"\|"twinkle", "seconds": 2–60}` | – | the image is one particle, repeated (steam, snow, sparkles, petals); `seconds` defaults to 8; placed the same way every time |

**Can be added:** `frames: {"count": 2–32, "fps": 1–24}` (fps defaults to 6) on a `natural`
picture: a sprite sheet, frames side by side, its width a multiple of `count` (a candle, a
curtain, a blinking LCD, a flapping bat that also crosses).

**A piece that answers a click:** `poke` on a `natural` layer (not `above`), at most 6 per theme.

| Field | Values | Default | What |
|---|---|---|---|
| `frames` | `{"count": 2–32, "fps": 1–24}` | fps 10 | the reaction, played once on a click |
| `image` | `art/<file>` | the layer's own image | the reaction sheet: `count` frames of the piece's own frame size, side by side |
| `burst` | `{"image": "art/<file>", "count": 1–12}` | – | small bits flying out of the piece (sparks, petals, a puff) |
| `stay` | `"random"` | – | after the reaction, the piece keeps one of its frames at random: a new arrangement each click |

```json
{ "image": "art/cat.png", "where": "page", "fit": "natural", "anchor": "bottom-right", "scale": 3,
  "poke": { "image": "art/cat-stretch.png", "frames": { "count": 6, "fps": 10 },
            "burst": { "image": "art/hair.png", "count": 5 } } }
```

A poke plays only on a desktop with a mouse, and never at the still motion level. It is an
anecdote from the theme's world (the cat stretches, the candle flares, a bell swings), never
interface: nothing depends on it and nothing tells you to click. Place poke pieces in empty space,
never over controls or text: a layer over a control fails the tour's audit.

**What each motion level shows** (the person's choice; a device asking for reduced motion means
still unless they chose full):

| Level | Shows |
|---|---|
| still | first frames only; nothing drifts; no crossings and no particles |
| subtle (the default) | drift, frames, crossings, and half the particles (rounded up) |
| full | all the particles, and parallax (`depth`) |

Previews (the pickers, the Workbench) always show layers still.

**Stacking, per place** (back to front):

| Place | Order |
|---|---|
| page | `under` layers → `page.backdrop` → page layers → `part.page.scrim` → content → `above` layers |
| hero | `under` layers → `home.hero.backdrop` → hero layers → the greeting |
| header | `under` layers → `header.banner` (with its room tint, `part.header.banner-wash`) → header layers → the title |
| status | `under` layers → `status.backdrop` → status layers → the bar's words and controls |
| rail | `rail.surface` → rail layers → the rail's foot (`rail.art`) and doors |
| rail-foot | a box of its own in the rail, just above the Ask Nox card |
| deck | `deck.surface` → deck layers → the cover, words and buttons |

Layers are drawn behind words, but a particle or a crossing over a picture still competes with
text near it: keep moving things away from where text sits. The contrast check can't see
layers; look at the tour.

## Pieces: avatars, Nox, room marks, medals

`sprites.json` redraws the app's pieces **by id** ([`_schema/sprites.ids.json`](_schema/sprites.ids.json)).
Anything the theme leaves out keeps HouseOS's own drawing (a line icon for medals). A redrawn
piece is drawn in every theme, whatever its `identity`, and always fits the box of the piece it
replaces, so sizes never move.

| Pieces | Ids | Draw at |
|---|---|---|
| `avatar.*` | moon, bat, raven, rose, ghost | 12 × 11 (16 × 16 fills the ring) |
| `nox.*` | idle, blink, listening, thinking, happy, error | 16 × 16 |
| `room.*` | home, listen, watch, house, files, smart-home, games, more, me | 16 × 16 |
| `transport.*` | play, pause, next, previous, stop | 9 × 9 |
| `title.*` (20 medals) | dj, explorer, night_owl, early_bird, weekend, genre_guardian, broken_record, marathon, radio_host, task_hero, grocery_runner, planner, wall_poet, courier, curator, high_scorer, collector, game_hopper, console_hopper, romhacker | 16 × 16 |

Each piece is rows of letters, one letter per pixel (`.` is empty), **16 × 16 at most**; the
file's `palette` maps each letter to a `color.sprite.*` token, so the theme's colours paint it
(and a scheme change repaints it):

```json
{
  "palette": { "k": "outline", "e": "accent", "c": "light" },
  "glyphs": {
    "nox.idle": ["....kkkk....", "...keeeek...", "..kecceceek.."],
    "title.dj": ["..kkk..", ".keeek.", "..kkk.."]
  }
}
```

People keep their choice of avatar (moon, bat, raven, rose, ghost, or their initials): a theme
redraws those five pictures, so a person's picture changes with the theme and never disappears;
initials stay letters in every theme. Pieces are scaled by whole pixels to fill their box
(avatars their ring, medals 32 px). Avatars must still read at 28 px, medals at 32 px, and Nox's
six moods must differ at a glance. `check` refuses an unknown id, a piece larger than 16 × 16 and
a letter missing from the palette.

## Words

A theme's look is pictures, shapes and type, not sentences: every line of text in HouseOS is its
own and practical (what's here, what to do; under each title, a tip about the room), the same in
every theme. `flavor.json` (optional, English **and** French, *tu*) holds a theme's only words:

| Key | Where | At most |
|---|---|---|
| `title.<title>.name` | a house title's name (the 20 titles in *Pieces*); the genre keeper's may hold `{genre}` (the genre, or "a genre" while nobody holds it: word it so both read well) | 28 |
| `title.star.mark` | the star mark of a title's level (★ in HouseOS) | 3 |

```json
{ "title.dj.name": { "en": "The radio on the counter", "fr": "La radio du comptoir" } }
```

Any other key fails the check. No words, letters or digits in pictures.

Rooms (their lights `color.room.*`): home, listen, watch, games, house, inbox, files, smart-home,
ask, space, me, control, party. `games` has its own light in Base (a theme without one keeps it);
the phone dock's fifth door is **More** (`room.more`), which opens the rooms past the dock.

## Motion

`dur.*` (1 s at most) and `ease.*` (a cubic-bezier list, or `steps(n)` with n 1–12 for mechanical
themes: a flap board, an LCD) give the theme's motion style. Moving pictures are layers (see
*Layers*). People choose how much motion they want; every animation stops at the still level.

## Art by code

No drawing program needed: write the picture as code and render it. The kit's toolkit is in
`themes/_kit/art/`: `pixel.py` (palettes, sprites from text, outlines, dither, 9-slice boxes,
sprite sheets), `svg.py` (SVG rendered to PNG or WebP at an exact size, with grain and paper),
`blender.py` (headless 3D renders with material presets) and `sheet.py` (a contact sheet of your
art at 1× and zoomed). Keep one script that regenerates every picture, so changes are edits.
[METHOD §4](_kit/METHOD.md) has the craft rules. Worked examples: `docs/design/themes/<id>/`.

## Fonts

```bash
PYTHONPATH=backend python3 -m houseos.theme_kit font my-theme fraunces --role display --weights 400,700
```

It takes an **OFL** family from Fontsource (Latin and Latin Extended, so French works), copies its
licence, and sets `theme.json` `fonts.<role>` and `tokens.json` `font.<role>`; `--italic` adds
italics. A catalogue of families with character notes and pairings: `_studio/fonts.json`. Bundled
faces need no files: Jacquard 12, Alegreya Sans, IBM Plex Mono, and `system`. Fonts ≤ 800 KB in
all.

## The tour

```bash
node themes/_kit/tour.cjs <id> [--base <url>] [--quick]
```

It needs Playwright and the isolated test app with test data (a developer set-up: see
`docs/TESTING.md`). By default it shoots the Vite dev server (`npm run dev` in `frontend/`),
so a `theme_kit build` shows at once; `--base` points it at the test app's last build instead.

- **Shoots**, for each scheme, on a phone (390 × 844) and a desktop (1440 × 900): Home, Listen,
  Watch, Games, House, My Space, Me, Inbox, Files and three Control Room tabs (themes, setup,
  users); on the phone in French too, for Home, Listen and the Control Room's setup; Home with
  motion still; and the sign-in page on a phone. `--quick`: desktop Home, Listen and the Control
  Room only.
- **Writes** `themes/<id>/shots/` (`<scheme>-<size>-<place>.png`, `contact.html` to look at,
  `audit.json`) and, on a full tour (or `--cards` alone), `art/card-<scheme>.webp`: Home on a
  desktop in each scheme, tidy and still, at 560 × 350, the card the pickers show (a theme
  without one is drawn live). `shots/` is never committed, checked or shipped.
- **Audits** and exits 1 on: the page scrolling sideways, text cut off without an ellipsis, a
  control outside the screen, a layer covering a control, colour-contrast problems found by axe
  (Home and the Control Room), a focused control without a visible ring, a page error.

The audit finds broken things, not ugly or hard-to-read ones: look at every screenshot.

## What the checks do (all code)

`theme_kit check <id>` writes `REPORT.md` and exits non-zero on any failure:

- **Manifest**: id = folder, whole-number versions, names and description in en and fr (not the
  template's), names ≤ 32, `credit` (en and fr, ≤ 40), schemes, density, identity, the three
  font roles, known part variants, `rooms` distinct or unified.
- **Contract**: no size token overridden; material and part edges exactly 1 px (solid, dashed or
  dotted); fields keep a visible edge; easings a cubic-bezier or `steps(1–12)`; art opacities 0–1;
  paper tilted 2deg at most; no filters on media.
- **Tokens resolve**: every reference and function resolves, no cycles, no unknown names, every
  colour a colour.
- **Text sizes fit the layout** and **type, motion and icon bounds**: the text band, text ≥ 11 px,
  body never in the display face, durations ≤ 1 s, icon stroke 1–3.
- **Contrast matrix** per scheme (WCAG gate, APCA shown): text on every ground and material, on
  the accent, on paper, inverse and screen; each status on its soft ground and the canvas; the Now
  bar's text; the current place (`fg.current` on `bg.current`); control borders, the focus ring,
  room lights, people's and data colours and sprite colours ≥ 3:1.
- **Distinct colours**: statuses and accent far apart (OKLab ΔE), rooms distinct (unless
  unified), people distinct; a deuteranopia simulation for success, warning and danger (advice).
- **Fonts, art and files**: font files and licence, Latin Extended, budgets, SVG safety, no code.
- **Images in tokens**: `url()` only to files in the theme's `art/`.
- **Art slots**, **Layers** (every field and limit above), **flavour text** (only title names
  and the star mark, en and fr, within length) and **sprites** (known ids, 16 × 16, palette
  letters).
- **Art sizes** (a warning): smooth art smaller than its slot's `min`.

A shared or imported theme passes the same checks again on the server; its CSS is always
regenerated there, never taken from a pack, and every value must stay a plain value (no `;`,
braces, quotes, comments or outside images). When its owner changes a shared theme, it goes back
to an administrator before the house sees the change.

## Before you show it

The checks judge what code can. For the rest, use METHOD's rubric (readability, usability,
cohesion, craft, depth, restraint, would the person love it), its **common first-round
failures**, and a **fresh-eyed review round** ([METHOD §6–7](_kit/METHOD.md)). Also: both schemes
designed, if it has both; nothing from the design library's banned list (§9).

## What not to do

- Edit components, add selectors, hard-code values or ship code or CSS: a theme is data only,
  and the checks refuse anything else.
- Change the layout, the order of things, words in buttons, or hide a control.
- Put text in images; use art as the only way to show information.
- Override a meaning just to "tweak": each override is a promise the checks must keep.

## Sharing and installing

- `theme_kit pack <id>` makes `<id>.houseos-theme` (a zip of the data with checksums).
- In HouseOS: *Your preferences → Appearance → Your themes → Bring a theme file* installs one as your draft.
  Wear it yourself; *Ask to share it with the house*, and an administrator shares it in
  *Control Room → Themes*. Anyone who lives here designs; an administrator shares.
- A bundled theme lives in this folder, is built into the app, and is tested with the rest.

## Themes in this folder

| Folder | Name | What |
|---|---|---|
| `pure` | Pure | Architecture made of light: black concrete, white light, square openings. Dark and light. Takes Base's place in the pickers. |
| `carved-night` | Legacy | The original candlelit manor look: a haunted manor under the moon, stone carved by candlelight, friendly ghosts. |
| `linen-morning` | Kinari | A quiet Japanese room at dawn: washi, kraft, walnut and sumi ink, one small red seal. |
| `modular` | Modular | Swiss modular type as a house: one grid of squares and circles, black and white, one red. |
| `night-castle` | The Vampire's Keep | A 16-bit gothic castle by night: candlelit stone, crimson and gold, bats across the moon. |
| `pocket-hatchling` | Pocket Hatchling | A keychain pet on a handmade homepage: stickers, glitter, an LCD and plum ink. |
| `sento-night` | Bathhouse After Hours | A Shōwa bathhouse at closing: the Fuji mural in steam, wet tile, a noren, a sleepy cat. |
| `showa-platform` | Shōwa Platform | A 1960s country station in August: enamel signs, signal red, a big sky, a railcar. |
| `y2k` | Millennium Skin | The house as a Y2K media-player skin: chrome bevels, LCD green, clear Bondi plastic. |
| `zabiwa` | Zabiwa | A black gallery wall for the artist Zabiwa's fresques: white type, hairlines, the art cut at its own resolution and veiled where type lies over it. |

Each bundled theme's direction, notes and art scripts are in `docs/design/themes/<id>/` (Zabiwa's
crop script: `docs/design/zabiwa/art-src/`).

Not in the pickers:

- `base`: hidden. The root every theme inherits: every token, nothing added. A stored "base"
  choice wears Pure.
- `canary`: debug only. Every token a loud, different value, so anything drawn outside the
  tokens shows (`frontend/tests/theme-canary.cjs`).

Also here: `_schema/` (the JSON Schemas), `_kit/` (the method, the tour, the art toolkit and
pictures of the parts), `_studio/` (the design library, the font catalogue, the studio's prompt
`STUDIO.md` and the templates).
