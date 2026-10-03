# The HouseOS design library

For whoever proposes a theme: a person with a designer's eye, an agent, or Nox's theme studio
acting as art director. It is the craft half of theming; the mechanics are in
`docs/design/SYSTEM.md`, the token catalogue (`PYTHONPATH=backend python3 -m houseos.theme_kit
tokens`) and `themes/base/tokens.json`. Fonts to choose from: `themes/_studio/fonts.json`.

A theme is **data**: seeds and token values, three font families, optional art and moving layers,
pixel pieces, the house titles' names.
Everything below is written as token moves. If an idea cannot be said in tokens, it is not
available to a theme; write it down as a proposal instead of hacking it in.

Every palette in this file was run through `theme_kit check` (contrast matrix, distinct colours,
colour-blind advice) on 2026-09-26 with system fonts and passed. If you change a value, run the
check again: passing here does not survive edits.

---

## 0. The levers, at a glance

| You want… | Move these |
|---|---|
| The whole value key (night, dusk, noon) | `seed.neutral` chroma and hue; for mid or unusual keys, `color.bg.*` and `color.fg.*` directly |
| The one thing that says "act here" | `seed.accent` (it becomes `accent.solid`, `focus-ring`, `bg.selected`, links) |
| States that belong to the world | `seed.success/warning/danger/info/private` |
| Each place's own light | `color.room.<home…control>` (indicators only: a line, a mark, the focus ring) |
| Voice of the letters | `theme.json` `fonts`, then `text.*` (weight, letterSpacing, textTransform; size and lineHeight only inside the text band) |
| What a surface is made of | `material.<canvas…screen>.*` (bg, border colour and style, shadow, radius, texture, blur, glow, rotate) |
| Corners | `radius.*` roles, `shape.cut` (a clip-path on surfaces) |
| Depth | `elev.0–4`, `color.shadow`, the `shadow` of each material |
| Tempo | `dur.*`, `ease.*` |
| What moves (steam, clouds, a crossing train) | `theme.json` `layers` (§7.1) |
| Identity | `theme.json` `identity` (`line` icons or `pixel` sprites), `sprites.json`, `slots` |
| The house titles' names | `flavor.json` (en + fr): the 20 title names and the star mark, a theme's only words |
| Icon weight | `icon.stroke` (1–3; 1.25 feels engraved, 2 feels stamped) |

Contract you cannot move: **sizes**. A theme changes how the blocks look, never how big they are.
Spacing (`space.*`), border widths (`border.*`), chrome heights (`chrome.*`), icon boxes
(`icon.s/m/l`), `z.*` and `bp.*` are fixed, and so is breathing room (`density` in theme.json is a
word for the brief; it scales nothing). A material's edge is always 1 px (`1px solid|dashed|dotted
<colour>`; borderless is `1px solid transparent`, never `none`); paper tilts 2deg at most. Text
stays in a band: component styles at most 1 px larger than Base with their line within ±2 px of
Base's, `action` in Base's case with at most +0.02em tracking, `label` and `caption` tracked 0.1em
at most, display styles at most 10 % larger, the `brand` line 32 px at most. Also: text under
11 px, body text in the display face, durations over 1 s, filters on posters and covers.

---

## 1. Finding a direction

### 1.1 Start from a thing, never from an adjective

"Modern", "clean", "minimal", "sleek", "premium" and "cosy" are not directions; they are what is
left when nobody chose. Start from something that exists and has a colour, a material and a
lettering of its own:

| Source | Example seed of an idea | What it hands you |
|---|---|---|
| A place | A jazz kissa in Kichijōji, 1976; a Lisbon kitchen tiled to the ceiling | Light, ground, one bright thing, signage |
| A material | Verdigris on a bronze door; oxblood leather; bone china; cork | Neutral, texture, edge, how light sits on it |
| An era | Interwar Central European civic print; 1970s Lyon living room | Type classification, colour chemistry, shapes |
| An object | A Braun radio, a loom's punched cards, a railway ticket, a seed packet | Proportions, shape language, a motif |
| A film or a film stock | Cinestill 800T at night; Kodachrome holiday slides | The key, the colour cast, where saturation lives |
| A print process | Risograph in two inks; cyanotype; letterpress; 2-colour newspaper | A strict ink budget, the paper, the texture |
| A person's photo | Their own shelf, their balcony at dusk | Colours sampled from their life (see 1.5) |

### 1.2 Interrogate the source (six questions)

Answer each in a few words before touching a token. The answers map one-to-one onto the levers.

1. **What is the light?** Noon, tungsten, a screen, candle, overcast. → value key, temperature
   (`seed.neutral` hue and chroma, `color.bg.*`).
2. **What is the ground made of?** Plaster, walnut, newsprint, slate, glaze. → `material.canvas`,
   `material.surface`, the neutral hue.
3. **What is the one bright thing?** The cobalt in the tile, the lamp, the stamp, the geranium.
   → `seed.accent`. There is one. If you name three, pick again.
4. **What lettering exists there?** Enamel signs, a typewritten label, a chalkboard, a book spine.
   → display face, `text.label` case and tracking.
5. **How do things move there?** A shuttle clacks, steam drifts, a page turns, nothing moves.
   → `dur.*`, `ease.*`, and the layers (§7.1).
6. **What is handled and worn?** Softened corners, chipped enamel, stitched edges, a punched hole.
   → `radius.*`, `shape.cut`, `material.*.border`, a motif.

### 1.3 The one-sentence mood

Formula: **a specific place or object + its light + its material + one telling detail**. It goes
in `BRIEF.md` and becomes `theme.json` `description`.

- Good: "A jazz kissa after closing: dark walnut, one amber lamp, the sleeve of the record still
  playing."
- Good: "A 1925 métro platform: white bevelled tile, navy enamel signs, Guimard's green iron."
- Bad: "A modern, clean, warm theme with a cosy feel." (no place, no light, no material)
- Bad: "Cyberpunk neon vibes." (a genre, not a place; see §9)

If the sentence would fit ten other themes, it is not yet a mood. Test: can someone who reads
only the sentence guess the accent hue and whether it is dark or light?

### 1.4 Three genuinely distinct directions

When a person asks for "a theme about X", show three. They must differ on **at least three**
of these axes, and never only in hue:

| Axis | Poles |
|---|---|
| Value key | night (canvas L ≈ 0.15) · dusk/mid (L 0.3 dark or 0.9 light) · noon (L ≈ 0.97) |
| Temperature | neutral hue warm (40–90) · cool (200–270) · green-grey (120–170) |
| Material | stone, paper, fabric, enamel, glass, screen, flat |
| Type personality | serif literary · grotesque civic · geometric period · pixel/blackletter · handwritten |
| Shape language | sharp · cut · soft · pill · ticket · arch |
| Edge | hairline · shadow · tonal step (§4.1) |
| Motion | still · crisp · springy · drifting · mechanical |
| Ornament | none · texture · scenes and crest art |

Write the three in a table with one row per axis before building any. If two columns match on
more than four rows, replace one direction. A common failure: three dark themes with a
different accent each. Another: three that are the same brief at three saturations.

Give each direction a name that is a noun from the source ("Kissa", "Herbier", "Ligne 1"), not
an adjective ("Warm Dark"). Names ≤ 32 characters, en and fr.

### 1.5 From a person's photo

1. Ask what in the photo they love (the lamp, the tiles, the plant), not only "use this photo".
2. Sample in OKLCH: the **largest calm area** (wall, floor, table) → `seed.neutral` hue; its
   chroma × 1.5 as the seed chroma (the ramps dilute chroma, see §2.1).
3. The **smallest saturated area** they named → `seed.accent`; move its lightness to the scheme's
   band (dark: L 0.72–0.82; light: L 0.40–0.56) and keep its hue and chroma.
4. The **darkest** and **lightest** points decide the scheme; a photo of a sunny room is not
   automatically a light theme if the person lives in the app at night.
5. Everything else in the photo becomes room hues, people colours, or nothing.
6. Never ship the photo as a texture. It can inspire an `auth.crest` or `home.hero.backdrop` art
   brief; the image itself stays private (no resident content in a theme pack).

---

## 2. Colour

### 2.1 How the kit turns seeds into colour (know this before choosing)

Each seed makes a 12-step ramp. Lightness is **fixed per step** and only chroma and hue come from
the seed, except steps 9–10 (the seed itself and its hover). Chroma is multiplied per step:

| Scheme | Step 1 (canvas) | 2 | 3 | 6–8 (lines) | 11 (muted text) | 12 (text) |
|---|---|---|---|---|---|---|
| dark: L | 0.17 | 0.20 | 0.235 | 0.335 / 0.41 / 0.535 | 0.83 | 0.95 |
| dark: chroma share | 15% | 20% | 30% | 45–60% | 70% | 25% |
| light: L | 0.99 | 0.975 | 0.955 | 0.875 / 0.80 / 0.62 | 0.47 | 0.24 |
| light: chroma share | 8% | 12% | 25% | 40–70% | 85% | 50% |

Consequences:

- **A neutral seed of chroma 0.02 gives a grey canvas.** `oklch(0.46 0.035 55)` yields
  `#110f0d` (barely warm); `oklch(0.46 0.08 55)` yields `#140e0a` (clearly walnut). For a neutral
  that feels chosen, use chroma **0.04–0.09** on the seed. The lightness of the neutral seed barely
  matters.
- **Light schemes start at L 0.99, almost white.** Paper, plaster and newsprint are not white.
  Override `color.bg.canvas` (and usually `surface`, `raised`, `overlay`, `sunken`, `hover`,
  `pressed`) for anything warmer or deeper than office paper. See the paper-on-table variant of palette 1 (§2.11) and the pitfalls in §2.8.
- **Dark schemes start at L 0.17.** For a mid-key dark (cyanotype blue, slate at dusk, a green
  chalkboard), override the `bg` set directly; see palette 13.
- **Seed lightness is the solid.** In dark themes put accents and states at **L 0.68–0.88**; in
  light themes at **L 0.40–0.62**. Outside those bands they fail 3:1 on the canvas.

### 2.2 Value first, hue second

Squint: a theme is a value structure before it is a palette. Decide the key and the steps between
canvas, surface and raised (dark: ≈ 0.03 L apart; light: surface may be *lighter* than canvas,
like sheets on a table). A theme where every ground is the same value has to draw borders on
everything (see §9); a theme with a clear value structure needs almost none.

### 2.3 Tinted neutrals

Never pure grey (chroma 0). The neutral takes its hue from one of:

- **The material**: walnut 50–60, terracotta 45–55, bone 85, slate 250, verdigris-stained bronze
  60, concrete 90 at very low chroma, blotting paper 110–140, cyanotype 255.
- **The accent's complement**, at low chroma, so the accent glows: a greenhouse (165) under a
  magenta lamp (340); slate blue (250) under signal orange (50); a walnut room (55) under a teal
  silk (200).
- **The accent's own hue**, at very low chroma, for monochrome, ink-on-paper themes (risograph blue
  ink on paper, cyanotype).

The neutral also colours text: `fg.default` is neutral 12, so a walnut neutral gives cream text in
the dark and dark brown ink in the light. That is the cheapest, most effective anti-generic move.

### 2.4 One fearless accent

One hue carries "act here / this is on" (`accent.solid`, `focus-ring`, `bg.selected`, links,
progress). Make it **specific and a little brave**: a Majorelle blue, a geranium, a grow-lamp
magenta, a tram-ticket orange; not "a nice blue". Keep everything else quiet so it can be loud.

Collisions to resolve **before** building (the kit fails states closer than ΔE 0.04, and people
confuse them long before that):

| Accent in | Then move | How |
|---|---|---|
| green (120–180) | `success` | toward yellow-green 115–125 or blue-green 160–170, and ≥ 0.05 L away |
| red, vermilion, terracotta (15–45) | `danger` | ≥ 25° cooler (0–15 crimson or 350–355 rose) **and** ≥ 0.08 L darker (light) / brighter (dark) |
| amber, ochre (60–90) | `warning` | toward lemon 95–105 and lighter (dark scheme), or darker ochre (light) |
| blue (230–270) | `info` | toward teal 200–215 or slate violet 275, lower chroma |
| violet, plum (290–340) | `private` | toward rose 350–355 or lavender 285 at lower chroma |

Status colours appear **only** for state, never as decoration. Rooms never carry state.

### 2.5 States that stay distinct, including for colour blindness

- Separate the four states by **lightness as well as hue**. Hue alone collapses for deuteranopia
  (the most common colour-vision deficiency, ≈ 5% of men): green and red become the same ochre.
- In **light** themes, put `success` at L ≈ 0.58–0.60 and toward 150–170, and `danger` at
  L ≈ 0.46–0.48. The kit's colour-blind advice (a deuteranopia simulation, Machado 2009) warned on
  every light palette here until that split was made (e.g. success 0.52/145 with danger 0.52/30).
- In **dark** themes, `warning` is the brightest (L 0.84–0.88), `success` 0.78–0.80, `danger`
  0.68–0.72. The ladder itself is information.
- Words and marks always accompany state colours (`<Status>` does this); colour is the second
  channel, never the only one.

### 2.6 Rooms (eight related lights)

Rooms are `home, listen, watch, house, files, ask, me, control`. Each is an indicator (a line, a
mark, the focus ring on the room's soft fill), never a fill of the page. The kit derives
`--c-room-fg` (the better of `fg.default` and `fg.inverse` on it), `--c-room-soft` (16% of it) and
`--c-room-line`.

Recipe that passes first time:

1. **Home is the house itself**: the neutral hue at chroma 0.025, a step brighter (dark) or darker
   (light) than the other rooms. Every palette below failed "rooms look the same" (home vs files
   or listen) until home was made low-chroma.
2. The other seven share **one lightness and one chroma** (dark: L 0.78–0.84, C 0.08–0.10;
   light: L 0.48–0.53, C 0.08–0.12) and differ in hue.
3. Hue spacing: ≥ 30° between neighbours in the 50–120 band (orange, amber, ochre, olive are
   perceptually crowded; 85 vs 105 at C 0.08 failed ΔE 0.04), ≥ 25° elsewhere.
4. Tie them to the source: `listen` often takes the accent's hue (music is the house's heart),
   `watch` the screen's colour, `house` the plants, `files` the paper or brass, `ask` Nox's hue,
   `me` the private hue, `control` a cool technical hue.
5. Rooms are ≥ 3:1 on canvas and surface and the text on them ≥ 4.5:1 (checked).

### 2.7 People and data

`color.person.1–8` mark residents (avatar ring, their songs); `color.data.1–8` are chart series
(by default a reordering of people). Base values usually survive a palette change; override when
the theme's canvas moves (a mid-key light canvas made Base's yellow `person.6` fail 3:1 at 2.97:
set it to `oklch(0.56–0.58 0.12 90)`). Keep them at the rooms' lightness band, spread over the full
hue circle, and never reuse the accent's exact hue for person 1.

### 2.8 Contrast pitfalls (what failed while writing this)

- **Light accent, light text**: a bright accent (dark themes, L ≥ 0.7) needs dark
  `fg.on-accent`; the default `contrast({color.accent.solid})` picks it for you. Don't override it
  with white "because buttons are white text".
- **Mid-lightness accents** (L 0.58–0.64, like fluorescent pink or a saturated orange) are the
  trap: neither end of the neutral reaches 4.5:1. Riso pink at L 0.60 gave 4.34 on-accent; 0.58
  passed at 4.7. Move the accent's L, not the text.
- **Yellow on light grounds**: `warning` above L 0.62 fails 3:1 on a light canvas. Ochre (0.60,
  hue 65–72) is the light-scheme warning; lemon only lives in the dark.
- **Mid-key light canvas** (L ≈ 0.93, a tan table): `border.strong` (neutral 8 at L 0.62) fell to
  2.97:1. When you darken a light canvas, set `color.border.strong` to ≈ L 0.55–0.56 and check
  `person.6`.
- **Translucent grounds** (`alpha(...)`) are checked as painted on the canvas; over a poster they
  are not. Keep translucent overlays for the scrim and the selected tint.
- **Paper inside a dark theme**: `color.paper.bg/fg/muted` is its own light world with its own
  checked pairs (`paper-fg` and `paper-muted` on `paper-bg`, 4.5:1). Set all three together; a
  muted ink needs roughly L ≤ 0.5 on paper at L 0.9.
- **APCA** is reported next to WCAG. Body text below Lc 60 reads thin even when WCAG passes;
  thin display faces (Poiret One, Cormorant at 300) need Lc ≥ 75.

### 2.9 Hue compass (OKLCH hue angles, for writing seeds by hand)

`0–10` rose-crimson · `20–30` red, tomato, oxblood (low C) · `35–50` vermilion, terracotta,
burnt orange · `55–70` amber, walnut (low C), saffron · `75–95` ochre, brass, mustard, bone (low
C) · `100–110` lemon, blotting paper (low C) · `115–135` olive, moss, avocado · `140–160` leaf,
fern, Guimard green (low C) · `165–185` verdigris, jade, teal · `195–215` cyan, petrol, lake ·
`220–245` sky, slate (low C), denim · `250–270` cobalt, ultramarine, Majorelle, navy (low L) ·
`275–300` violet, encre violette · `305–340` plum, magenta, grow-lamp · `345–359` rose, pink.

Chroma: 0.02 barely tinted · 0.05 a clear tint · 0.10 a colour · 0.15 strong · 0.20+ fearless
(check gamut; the kit maps to sRGB).

### 2.10 Where palettes come from

**Material-derived.** Photograph or imagine the material under one light; its body colour is
the neutral, its accident is the accent.

| Material | Neutral | Accent / accident | Notes |
|---|---|---|---|
| Terracotta | 55 · C 0.03–0.05 | the fired orange 38, or glaze green 150 | Light schemes: unglazed tile is a mid-key canvas |
| Verdigris on bronze | bronze 60 · C 0.035 | patina 175–180 | The accent is green: move success (§2.4) |
| Slate | 250 · C 0.02 | chalk 95 (low C) or a signal orange 50 | Cold, flat, no gloss |
| Oxblood leather | 25 · C 0.045 | brass 85 | Danger must be brighter and oranger than the leather |
| Bone, ivory | 85 · C 0.015–0.02 | ink indigo 268 | A ground that is nearly white but never white |
| Walnut | 55 · C 0.06–0.08 | lamp amber 68, or a teal textile 200 | Dark walnut wants cream text, not white |
| Cork | 70 · C 0.06 (mid-key) | a pin colour: red 25 or blue 250 | Notes on cork: `material.paper.rotate` |
| Zinc, pewter | 230 · C 0.01 | bistro red 25 | Enamel-like, cool, tiny radii |
| Concrete | 90 · C 0.008 | a single safety yellow (dark) or cobalt (light) | Brutalist: zero radius, no shadow |
| Linen | 90 · C 0.02 | a woad blue 245 | Weave texture at very low contrast |

**Place and era.**

- *Lisbon azulejo kitchen*: tin-glazed white, cobalt 262 at high chroma, a little yellow and
  manganese violet. Light, glossy (enamel), tile motif.
- *1970s Japanese jazz kissa*: roasted walnut 55, one amber lamp 68, red velvet 22, smoke blue
  230. Dark, lacquer or wood, crisp, still.
- *Nordic sauna*: aspen and spruce 75, cold lake 215, birch bark (a near-white with dark
  flecks), smoke. Light or mid-key; soft corners; drifting motion.
- *Moroccan riad at noon*: warm plaster 50, Majorelle blue 268 at C 0.2, zellige green 150,
  saffron 70, pomegranate 22, hard shade. Light, high key, arch shapes, tile motif.
- *1920s Paris métro*: white bevelled tile 95 at C 0.015, navy enamel 262, Guimard green 160, a
  signal red. Light, enamel, grotesque or Art Nouveau display.
- *Greenhouse at dusk*: glass-green neutral 165, magenta grow lamp 340, geranium 32, dusk blue
  225. Dark, glass allowed (it is literally glass), drifting.

**Film stocks.**

- *Kodachrome*: deep sky blue and saturated reds and yellows, dense blacks, warm neutral. Put
  the stock's saturation in the rooms and people, keep one blue or red as the accent.
- *Portra 400*: soft pastel, peachy neutral 60, teal 200, low contrast highlights. Light, low
  chroma everywhere, generous line height.
- *Cinestill 800T*: tungsten night: teal-blue shadows 225, red halation around lights 33. Dark,
  the accent is the halo; `material.screen.glow` can carry a halation ring.
- *Velvia*: saturated greens 140 and magenta 340, deep blacks. Dark, high chroma rooms, one
  magenta accent.

**Print processes.**

- *Risograph two-ink*: paper + two inks (fluorescent pink 0 and blue 262). Text in the blue ink
  (`color.fg.default`), accent in pink, the overprint (their mix, a purple) as `private`. Grain
  texture; misregistration only in art, never in text.
- *Letterpress*: cotton paper 85, black ink with a hint of warmth, one vermilion 33. Accent is
  red: danger goes crimson and darker. Impression = `material.sunken` inset shadow.
- *Cyanotype*: Prussian blue ground 255, white image, tea-toned brown 60 as the one warm thing.
  Mid-key dark with a directly set `bg` family.
- *Screen print*: flat opaque inks, no gradients, chunky halftone, one fluorescent. Zero
  shadows, hard ink edges (`material.*.border` 1 px in the ink, doubled inside with an `inset 0 0 0
  1px` shadow if it must look heavier), overprint colours as rooms.
- *2-colour newspaper*: newsprint 95 at C 0.012 (mid-key light), black, one spot red 27 or blue
  250. Condensed grotesque headlines, a text serif, column rules as `border.subtle`.

**Limited-ink palettes.** Choose the inks first (2–4), then express every token as an ink, a
paper, or a mix: neutral = paper + ink-1 ramp, accent = ink-2, states = ink mixes where possible,
rooms = tints of the inks at the rooms' lightness. It is the fastest way to a coherent,
non-generic theme, and it tolerates the most daring accent.

### 2.11 Mini-palettes (all passed `theme_kit check` colour checks, 2026-09-26)

Rooms: `home` is written as L C H; the other seven share one L and C, hues in the order
listen · watch · house · files · ask · me · control.

**1. Terracotta courtyard · light**. Unglazed tile and lime-washed walls; terracotta is the
accent, so danger goes cool crimson and much darker.
```
neutral oklch(0.58 0.03 55)   accent  oklch(0.54 0.14 38)   success oklch(0.52 0.1 128)
warning oklch(0.6 0.13 72)    danger  oklch(0.46 0.16 12)   info    oklch(0.52 0.07 235)
private oklch(0.5 0.09 330)
rooms   home 0.48 0.025 60 · others L0.52 C0.1 at 38 · 220 · 128 · 85 · 12 · 330 · 255
```
Paper-on-table variant (mid-key): `bg.canvas oklch(0.93 0.025 65)`, `surface 0.965/0.015/70`,
`raised 0.985/0.01/70`, `overlay 0.975/0.012/70`, `sunken 0.9/0.025/65`, `hover 0.9/0.03/65`,
`pressed 0.87/0.03/65`, then `border.strong oklch(0.56 0.03 60)` and `person.6 oklch(0.58 0.12 90)`.

**2. Verdigris & bronze · dark**. The patina is the accent; the bronze under it is the neutral;
success moves to yellow-green so it doesn't read as "the accent".
```
neutral oklch(0.5 0.035 60)   accent  oklch(0.76 0.1 178)   success oklch(0.8 0.14 118)
warning oklch(0.82 0.13 85)   danger  oklch(0.7 0.15 25)    info    oklch(0.74 0.08 245)
private oklch(0.74 0.09 320)
rooms   home 0.86 0.025 70 · others L0.8 C0.08 at 178 · 230 · 125 · 90 · 25 · 320 · 270
```

**3. Oxblood library · dark**. Leather-bound shelves and a brass reading lamp; danger is a
brighter vermilion so it doesn't vanish into the leather.
```
neutral oklch(0.48 0.045 25)  accent  oklch(0.8 0.11 85)    success oklch(0.78 0.11 150)
warning oklch(0.84 0.14 100)  danger  oklch(0.72 0.17 35)   info    oklch(0.76 0.07 230)
private oklch(0.76 0.08 310)
rooms   home 0.86 0.025 60 · others L0.8 C0.09 at 85 · 215 · 150 · 118 · 30 · 320 · 260
```

**4. Bone & indigo ink · light**. Bone china and a fountain pen; almost monochrome, the ink is
the only colour; success lifted and teal-shifted for deuteranopia.
```
neutral oklch(0.58 0.018 85)  accent  oklch(0.42 0.12 268)  success oklch(0.58 0.1 170)
warning oklch(0.6 0.12 70)    danger  oklch(0.47 0.17 22)   info    oklch(0.52 0.07 215)
private oklch(0.5 0.1 320)
rooms   home 0.46 0.025 80 · others L0.5 C0.09 at 268 · 195 · 150 · 95 · 25 · 320 · 232
```

**5. Azulejo kitchen, Lisbon · light**. Cobalt on tin glaze; a warm white neutral so the cobalt
sings; olive-oil success, tomato danger kept darker than success.
```
neutral oklch(0.6 0.02 95)    accent  oklch(0.45 0.16 262)  success oklch(0.6 0.11 150)
warning oklch(0.62 0.14 68)   danger  oklch(0.47 0.18 28)   info    oklch(0.55 0.08 200)
private oklch(0.5 0.12 312)
rooms   home 0.48 0.025 75 · others L0.52 C0.11 at 262 · 200 · 132 · 95 · 30 · 312 · 235
```

**6. Kissa, 1976 · dark**. Walnut, an amber lamp, a red velvet banquette; the lamp is the
accent, so warning becomes a paler lemon above it. Raise neutral chroma to 0.08 for a truly
brown room.
```
neutral oklch(0.46 0.035 55)  accent  oklch(0.78 0.13 68)   success oklch(0.78 0.11 140)
warning oklch(0.88 0.14 102)  danger  oklch(0.68 0.17 22)   info    oklch(0.74 0.06 230)
private oklch(0.72 0.09 335)
rooms   home 0.86 0.025 55 · others L0.8 C0.09 at 68 · 220 · 140 · 100 · 22 · 335 · 265
```

**7. Sauna by the lake · light**. Aspen benches and cold water; the lake is the accent, info
moves to a slate violet to stay apart from it.
```
neutral oklch(0.6 0.03 75)    accent  oklch(0.48 0.08 215)  success oklch(0.58 0.1 160)
warning oklch(0.6 0.13 65)    danger  oklch(0.47 0.17 28)   info    oklch(0.5 0.07 275)
private oklch(0.5 0.09 340)
rooms   home 0.46 0.025 70 · others L0.5 C0.08 at 215 · 250 · 145 · 90 · 30 · 340 · 280
```

**8. Riad at noon · light**. Pink plaster in hard sun and one fearless Majorelle blue at
C 0.20; everything else steps back.
```
neutral oklch(0.62 0.03 50)   accent  oklch(0.47 0.2 268)   success oklch(0.6 0.12 155)
warning oklch(0.62 0.15 70)   danger  oklch(0.47 0.19 22)   info    oklch(0.54 0.09 205)
private oklch(0.52 0.14 350)
rooms   home 0.48 0.025 55 · others L0.52 C0.12 at 268 · 205 · 145 · 85 · 22 · 350 · 300
```

**9. Ligne 1, 1925 · light**. Bevelled white tile, navy enamel signs as the accent, Guimard's
green iron as success, a signal red.
```
neutral oklch(0.6 0.015 95)   accent  oklch(0.4 0.11 262)   success oklch(0.5 0.09 160)
warning oklch(0.62 0.14 72)   danger  oklch(0.54 0.2 27)    info    oklch(0.56 0.08 210)
private oklch(0.5 0.11 320)
rooms   home 0.46 0.025 90 · others L0.5 C0.09 at 262 · 210 · 160 · 75 · 27 · 320 · 290
```

**10. Greenhouse at dusk · dark**. Condensation-green glass and a magenta grow lamp (the
complement of the leaves); private moves to lavender away from the magenta.
```
neutral oklch(0.48 0.035 165) accent  oklch(0.72 0.18 340)  success oklch(0.8 0.14 135)
warning oklch(0.84 0.13 85)   danger  oklch(0.7 0.17 32)    info    oklch(0.76 0.08 225)
private oklch(0.74 0.1 290)
rooms   home 0.86 0.025 95 · others L0.8 C0.09 at 340 · 220 · 135 · 80 · 32 · 290 · 255
```

**11. Cinestill 800T · dark**. Tungsten night: teal-blue shadows, red halation as the accent;
danger becomes a cool rose so it is not the halo.
```
neutral oklch(0.47 0.045 225) accent  oklch(0.7 0.18 33)    success oklch(0.8 0.12 160)
warning oklch(0.86 0.14 90)   danger  oklch(0.72 0.17 355)  info    oklch(0.78 0.08 215)
private oklch(0.74 0.1 300)
rooms   home 0.86 0.025 70 · others L0.8 C0.09 at 33 · 215 · 160 · 95 · 355 · 300 · 255
```

**12. Risograph, pink & blue · light**. Two inks on cream stock: the text is the blue ink, the
accent the fluorescent pink (L 0.58: at 0.60 on-accent text fails).
```
neutral oklch(0.55 0.05 262)  accent  oklch(0.58 0.22 0)    success oklch(0.52 0.11 155)
warning oklch(0.62 0.14 70)   danger  oklch(0.5 0.18 30)    info    oklch(0.5 0.12 250)
private oklch(0.5 0.13 305)
color   bg.canvas oklch(0.97 0.012 95)   fg.default oklch(0.38 0.14 262)
rooms   home 0.48 0.025 262 · others L0.52 C0.13 at 0 · 230 · 155 · 80 · 30 · 305 · 280
```

**13. Cyanotype · dark, mid-key**. The Prussian-blue print itself as the ground (L 0.30, not
0.17), white image as text, tea-toned brown as the one warm accent. Needs the `bg`/`fg` family
set directly.
```
neutral oklch(0.55 0.09 255)  accent  oklch(0.8 0.11 60)    success oklch(0.84 0.12 150)
warning oklch(0.88 0.13 95)   danger  oklch(0.76 0.14 25)   info    oklch(0.86 0.06 220)
private oklch(0.8 0.08 320)
color   bg.canvas 0.30/0.085/258  surface 0.34/0.09/258  raised 0.39/0.09/258
        overlay 0.34/0.09/258  sunken 0.26/0.075/258  hover 0.42/0.09/258  pressed 0.36/0.09/258
        fg.default 0.97/0.012/250  muted 0.88/0.03/250  subtle 0.86/0.04/250
        placeholder 0.84/0.04/250  border.strong 0.70/0.07/255
rooms   home 0.9 0.025 60 · others L0.84 C0.09 at 70 · 210 · 150 · 110 · 25 · 330 · 280
```

**14. Slate & signal orange · dark**. Wet slate roof, one safety-orange buoy; cold neutral,
hot accent, nothing else saturated.
```
neutral oklch(0.5 0.02 250)   accent  oklch(0.72 0.17 50)   success oklch(0.78 0.12 150)
warning oklch(0.86 0.14 95)   danger  oklch(0.7 0.17 20)    info    oklch(0.76 0.08 225)
private oklch(0.74 0.09 305)
rooms   home 0.86 0.025 80 · others L0.8 C0.08 at 50 · 220 · 150 · 100 · 20 · 305 · 265
```

**15. Portra afternoon · light**. Peach-skin neutral, pastel teal accent, low chroma everywhere;
the calmest palette here. Pair with the most generous line heights the band allows (Base + 2 px)
and quiet, tonal materials.
```
neutral oklch(0.6 0.025 60)   accent  oklch(0.5 0.08 200)   success oklch(0.58 0.1 155)
warning oklch(0.62 0.12 70)   danger  oklch(0.47 0.16 25)   info    oklch(0.52 0.08 245)
private oklch(0.52 0.1 330)
rooms   home 0.49 0.025 55 · others L0.53 C0.09 at 200 · 245 · 140 · 85 · 28 · 330 · 285
```

---

## 3. Type

### 3.1 Where each face is allowed

| Styles | Face | Rule |
|---|---|---|
| `display-xl`, `display-l`, `display-m`, `brand` | display | Page titles, hero moments, the house's name. Expressive faces live here only. |
| `title-l`, `title-m`, `title-s` | body by default | May use the display face if it stays legible at 16–22 px (a text serif, a grotesque); never a pixel, blackletter, hairline or script face. |
| `body-l/m/s`, `action`, `caption` | body | Never the display face (the kit fails it). Controls and paragraphs must read at a glance. |
| `label` | body or mono | Field labels and small headings; case and tracking give it character. |
| `numeric` | mono (or body with tabular figures) | Times, counts, codes; must align. |

A display face may appear on at most **one line per view** at display sizes. If a theme's
personality depends on the display face appearing everywhere, the personality is in the wrong
place: move it to material, colour and shape.

### 3.2 Pairing principles

1. **One expressive, one legible.** The display face carries the era; the body face carries
   the reading. Two expressive faces fight; two neutral faces are Base.
2. **Contrast in structure, not only weight.** Pair a serif with a sans, a condensed with a
   normal width, a geometric with a humanist. Two humanist sans at different weights read as a
   mistake.
3. **Shared proportion.** Match x-heights (or compensate with size): Josefin Sans has a tiny
   x-height, so set a body under it 1 px up (the band's limit), never beside it on one line.
   Atkinson and Lexend are large; faces with small x-heights next to them look shrunken.
4. **Shared era or deliberate clash.** Libre Franklin + Libre Caslon (American print, same
   century) is harmony; Bodoni Moda + Martian Mono (1800 and a spacecraft) is a clash that must
   be meant.
5. **The mono is a third voice, not a second body.** Choose it for times, codes and the label
   style; a typewriter (Courier Prime) says bureau, a wide mono (Martian) says instrument, a
   serif mono (Xanh) says library card.
6. **French first.** Check « Paramètres », « Télécharger », « Écouter », œ in « cœur », ’ in
   « l’atelier » at `display-l` and `label` size. Capital accents (É, À) collide with tight
   `lineHeight` in display styles: display lineHeight ≥ 1.05 for faces with tall caps.

### 3.3 Tracking and case (text-style tokens)

`letterSpacing` is in em; `textTransform` is `none`, `uppercase` or `lowercase`.

| Situation | letterSpacing | textTransform |
|---|---|---|
| Display grotesque ≥ 34 px | −0.01 to −0.02 | none |
| Display serif, didone | 0 to −0.01 | none |
| Condensed display caps (League Gothic, Six Caps, Big Shoulders) | +0.01 to +0.03 | uppercase |
| Wide display (Unbounded, Krona One) | 0 | none (caps make it a billboard) |
| Pixel faces | 0 (never negative; pixels collide) | as drawn |
| Blackletter | 0 | **never** uppercase |
| `label` in caps | +0.06 to +0.10 | uppercase, sizes 12–13 |
| `label` in small caps mood | +0.02 | none, weight 600 |
| Body | 0 (±0.005 at most) | none |
| `action` (buttons, tabs, chips) | Base's + 0.02 at most | none, as Base (caps widen buttons) |
| `caption` | +0.01 | none |

Only one style in a theme should be uppercase + tracked (usually `label`); a caps-mono `label`
on every section is the "mono eyebrow above every title" anti-pattern (§9). Carved Night avoids
it: a mixed-case Alegreya Sans `label`, 14/600, +0.02; IBM Plex Mono for `numeric` only.

### 3.4 Special faces

- **Pixel faces** (Jacquard 12, Silkscreen, VT323, Doto, Handjet): sizes on their grid, within
  Base + 10 % (`display-m/l/xl` 29/37/48 px; `brand` line ≤ 32): Jacquard 12 at 24/36/48,
  Silkscreen 24/32/40, VT323 24/36/48; weight as drawn; `lineHeight` 1–1.1. Carved Night: `display-*`
  and `brand` in Jacquard 12, reading text and `label` in Alegreya Sans, `numeric` in IBM Plex Mono.
- **Blackletter** (Jacquard 12, Grenze Gotisch): titles only, mixed case, never tracked.
- **Hairline and high-contrast display** (Poiret One, Cormorant Garamond, Bodoni Moda, Gloock):
  `display-xl`/`display-l` only, ≥ 28 px, and on dark themes prefer weight 500+; hairlines break
  on low-DPI screens.
- **Handwritten** (Caveat, Caveat Brush, Klee One): kickers, empty-state lines and wall notes
  are the handwriting's place; not titles of forms, never buttons. Shantell Sans is the only one
  that can also be a body face (its Informal axis at 0).
- **Variable axes** (`axes` in fonts.json): the kit loads the file; the token system has no axis
  settings yet. Pick faces whose default instance is the look you want (Fraunces' default is
  already soft; Bricolage's opsz follows size automatically).

### 3.5 Budget

Install with `PYTHONPATH=backend python3 -m houseos.theme_kit font <id> <fontsource-id> --role
display|body|mono --weights 400,700 [--italic]` (it fetches the woff2 files and the licence).
`fonts/` ≤ 800 KB, woff2 with latin **and** latin-ext files, plus the licence. `kb_400` in
fonts.json is one weight (latin + latin-ext). A typical theme: display 1–2 weights, body 400,
400 italic, 600 or 700, mono 400 = 6–8 files, 180–400 KB. Heavy families: Andika, Caveat Brush
(≈ 100 KB/weight), EB Garamond (81), Fira Sans (70), Shantell Sans (68), Unbounded (66).

### 3.6 Pairings

| # | Display | Body | Mono | Character | Style notes |
|---|---|---|---|---|---|
| 1 | Jacquard 12 | Alegreya Sans | IBM Plex Mono | Carved Night: woven gothic pixel over a bookish humanist | display 24/36/48 only |
| 2 | Fraunces | Atkinson Hyperlegible Next | Courier Prime | 1970s book jacket over the most honest text face | display weight 600–700, `lineHeight` 1.05 |
| 3 | Bodoni Moda | Jost | IBM Plex Mono | Paris 1925: opera poster over métro geometry | display ≥ 34 px; `label` Jost caps +0.08 |
| 4 | Big Shoulders Display | Spectral | Overpass Mono | Railway yard signage over a quiet catalogue serif | display uppercase +0.02, weight 800 |
| 5 | Young Serif | Inclusive Sans | Courier Prime | A cookbook on the counter, a warm kitchen | titles in Inclusive Sans 700 |
| 6 | Instrument Serif | Instrument Sans | Martian Mono | Gallery wall label, restrained, precise | display italic for one word only; no bold serif exists |
| 7 | Libre Franklin (900) | Libre Caslon Text | Courier Prime | American broadsheet, 1900s | display tight −0.02; body 17 px, `lineHeight` 1.5 |
| 8 | League Gothic | Newsreader | JetBrains Mono | Cinema listings and a Sunday paper | display caps +0.02 |
| 9 | Grenze Gotisch | Lexend | IBM Plex Mono | A Rhine town's beer label, readable gothic | display mixed case, never tracked |
| 10 | Shrikhand | Atkinson Hyperlegible | Space Mono | 1970s diner sign, candy wrapper, disco | display-m and up only, one line |
| 11 | Cinzel | EB Garamond | IBM Plex Mono | Museum plaque and a French book | titles in EB Garamond 600; Cinzel is caps only |
| 12 | Unbounded | Fira Sans | JetBrains Mono | Sports poster, contemporary, loud and legible | display 600, French titles run wide: check `display-xl` |
| 13 | Doto | Instrument Sans | IBM Plex Mono | Departure board at a small station | display ≥ 24 px; `numeric` mono |
| 14 | Cormorant Garamond | Source Sans 3 | Victor Mono | Perfume counter, cold luxury, cursive italics in labels | display ≥ 34 px, weight 600 in dark |
| 15 | Bricolage Grotesque | Newsreader | Martian Mono | A contemporary arts magazine | display 700 −0.02; body serif 17/1.5 |
| 16 | Besley | Archivo | Space Mono | Victorian seed packet and a municipal notice | titles Besley 700; `label` Archivo caps |
| 17 | Klee One | Zilla Slab | IBM Plex Mono | A kissa menu written at the counter | Klee for kickers and display-m only |
| 18 | Dela Gothic One | Inclusive Sans | IBM Plex Mono | Shōwa shop signs, manga covers | display short words only, `display-m` 24 |
| 19 | Syne (800) | Inclusive Sans | Space Mono | An art-centre poster, avant-garde but kind | Syne only at `display-xl/l` |
| 20 | Brygada 1918 | Brygada 1918 | Overpass Mono | Interwar civic print: stamps, forms, a post office | one family: display 700, body 400; `label` Overpass caps |
| 21 | Caveat | Familjen Grotesk | Courier Prime | Fridge door notes over a friendly household sans | Caveat in kickers and wall notes, never `display-xl` |
| 22 | Limelight | Josefin Sans (titles) + Source Sans 3 (body) | Courier Prime | Art Deco cinema lobby | Josefin as `title-*` only; three families max |

Never pair two of: Fraunces, Young Serif, Shrikhand (same 1970s voice). Never pair Bodoni Moda
with Abril Fatface, DM Serif Display or Cormorant Garamond (two high-contrast serifs). Never pair Atkinson with
Lexend (two legibility faces).

---

## 4. Materials and depth

### 4.1 The edge rule

Each material gets **one** edge strategy: a hairline (`border`), a shadow (`shadow`), or a tonal
step (`bg` differs from what is behind). Never all three. Base uses hairlines; dark themes read
best with tonal steps plus an inner highlight; light themes with a tinted shadow and no visible
border.

Every material edge is **1 px** in every theme, so a block is the same size whatever its look.
Choose its colour and style (`solid`, `dashed`, `dotted`); "no border" is `1px solid transparent`
(the kit refuses `none` and any other width). A heavier rim is colour, or a second pixel drawn
inside with an `inset 0 0 0 1px <colour>` shadow, which takes no room.

### 4.2 Depth by scheme

- **Dark**: shadows are nearly invisible on dark grounds; depth is **lighter = nearer**
  (`canvas` < `surface` < `raised` < `overlay`), with an optional 1 px inner highlight on top
  (`inset 0 1px 0 alpha(#ffffff, 6–10%)`). `elev.*` only for overlays and the Now bar.
- **Light**: depth is a shadow tinted with the neutral (`color.shadow` = neutral hue at L 0.3,
  C 0.02–0.04, not black), small offset, low opacity (8–14%). Surfaces may be lighter than the
  canvas (sheets on a table).
- `shape.cut` is a `clip-path` on every Surface except paper: it **cuts off outer shadows**. With
  cut corners use inset shadows and tonal steps, as Carved Night does.

### 4.3 Recipes

Values are token paths. `{…}` are references; colours in `oklch(L C H)` or hex.

**Paper** (light; notes, gazette, a whole theme of stationery)
```
color.shadow               oklch(0.32 0.03 60)
material.canvas.bg         {color.bg.canvas}                 # the table, L 0.93
material.surface.bg        oklch(0.975 0.01 85)             # the sheet, lighter than the table
material.surface.border    1px solid transparent
material.surface.shadow    0 1px 0 alpha({color.shadow}, 10%), 0 3px 8px alpha({color.shadow}, 8%)
material.surface.texture   url(art/fibre.svg)               # §6 paper fibre, ΔL ≤ 0.02
material.paper.rotate      0.8deg
material.sunken.shadow     inset 0 1px 2px alpha({color.shadow}, 14%)   # letterpress impression
```

**Stone** (dark; carved, heavy, Carved Night)
```
radius.card / control      {radius.none}
shape.cut                  polygon(4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px),
                           calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px), 0 4px)
material.surface.border    1px solid {color.border.subtle}
material.surface.shadow    inset 1px 1px 0 #ffffff12, inset -1px -1px 0 #00000070
material.sunken.shadow     inset 2px 2px 0 #00000080, inset -1px -1px 0 #ffffff0d
material.canvas.texture    url(art/grain.svg)               # optional: speckle, ΔL 0.03
```

**Glass** (only when the source *is* glass: a greenhouse, a vitrine, a TV. Never by default)
```
material.overlay.bg        alpha({ramp.neutral.2}, 82%)
material.overlay.blur      blur(14px) saturate(120%)
material.overlay.border    1px solid alpha(#ffffff, 12%)
material.overlay.shadow    {elev.4}
color.scrim                alpha({ramp.neutral.1}, 60%)
```
Only `overlay` (sheets, menus) is glass; surfaces stay solid. Text contrast is checked against
the canvas, so keep the alpha ≥ 80% or the sheet is illegible over a poster.

**Fabric / felt** (soft, warm, quiet; a textile shop, a card table)
```
radius.card                {radius.l}      radius.control {radius.m}
material.surface.border    1px solid transparent
material.surface.shadow    none                             # tonal step only
material.surface.texture   url(art/weave.svg)               # plain weave, ΔL ≤ 0.015
material.sunken.shadow     inset 0 1px 3px alpha({color.shadow}, 35%)
icon.stroke                2
```

**Enamel** (signs, cookware, métro plaques: glossy, saturated, rimmed)
```
radius.card                {radius.s}      radius.chip {radius.xs}
material.surface.border    1px solid {color.border.strong}
material.surface.shadow    inset 0 0 0 1px {color.border.strong},      # the rim, doubled inside
                           inset 0 2px 0 alpha(#ffffff, 35%)           # the glaze highlight (light)
material.raised.border     1px solid {color.accent.border}
material.raised.shadow     inset 0 0 0 1px {color.accent.border}
material.inverse.bg        {color.accent.solid}                        # toasts as enamel plaques
material.inverse.fg        {color.fg.on-accent}
```
The rim is 2 px to the eye and 1 px to the layout: the second pixel is an inset shadow.

**Lacquer** (dark, deep, glossy; a kissa counter, a Japanese box)
```
material.surface.bg        oklch(0.22 0.04 25)              # oxblood-black
material.surface.border    1px solid transparent
material.surface.shadow    inset 0 1px 0 alpha(#ffffff, 8%)
material.raised.shadow     inset 0 1px 0 alpha(#ffffff, 12%), 0 1px 0 #00000080
radius.card                {radius.xs}
```

**CRT / phosphor** (only on `material.screen`: the TV and deck displays, never the page)
```
material.screen.bg         oklch(0.16 0.03 150)
material.screen.texture    url(art/scanlines.svg)           # §6 scanlines, period 3 px
material.screen.glow       inset 0 0 0 1px alpha({color.accent.solid}, 25%),
                           inset 0 0 32px alpha({color.accent.solid}, 12%)
```
The glow is `inset` so it survives `shape.cut`. Media inside is never filtered or tinted.

**Wood** (walnut, aspen, spruce)
Do not photograph wood. Use a tonal ground in the wood's hue (neutral chroma 0.06–0.08) and, if
anything, a code-drawn grain on `material.canvas.texture` only: long, slightly wavy lines, ΔL ≤
0.015, never on surfaces that carry text lists. Wood reads from colour and warmth far more than
from grain.

**Concrete** (brutalist, civic)
```
seed.neutral               oklch(0.55 0.008 90)
radius.control/card/sheet/chip/media   {radius.none}
material.surface.border    1px solid transparent            material.surface.shadow none
material.canvas.texture    url(art/aggregate.svg)           # sparse speckle, ΔL 0.02
elev.1  none   elev.2  none   elev.3  0 2px 0 alpha({color.shadow}, 40%)
```

**Cork** (a household board; House room notes)
```
material.canvas.bg         oklch(0.62 0.07 65)  # only if every text pair still passes; usually
                                                # cork is paper.bg's backdrop in art, not the canvas
material.paper.bg          oklch(0.97 0.02 95)
material.paper.shadow      0 2px 0 alpha({color.shadow}, 25%), 0 6px 12px alpha({color.shadow}, 12%)
material.paper.rotate      1.2deg
```
A cork canvas at L 0.62 fails text contrast for anything but paper; prefer cork as a texture on
a mid-key light canvas (L ≥ 0.9) with the speckle at ΔL 0.03.

### 4.4 Texture or tonal step?

Use a **tonal step** when the job is separation (almost always). Use a **texture** only when the
material is the idea (paper, felt, concrete, a screen) and the texture is invisible at arm's
length. Budget: at most **two** textures per theme; never on `sunken` (inputs), `overlay`
(sheets full of text) or `inverse`; each tile ≤ 4 KB SVG or ≤ 20 KB PNG/WebP; luminance deviation
from the ground ≤ 0.02 OKLab L (≤ 0.03 for canvas only). The contrast check cannot see textures:
this budget is what keeps its numbers true.

---

## 5. Shape languages

A shape language is radius roles + edge colour + shadow + cut, all agreeing (edges are always
1 px: the column below says whether they show). Pick one; apply it
to control, card, sheet, chip, media and avatar together.

| Language | radius roles (control · card · sheet · chip · media · avatar) | edge (1 px) | shadow / cut | Feels like |
|---|---|---|---|---|
| Sharp | 0 · 0 · 0 · 0 · 0 · 0 | hairline | none | print, newspaper, concrete |
| Cut | 0 everywhere | hairline | `shape.cut` 4–6 px chamfer, inset shadows | stone, stamped metal, pixel games |
| Soft | 6 · 10 · 14 · 6 · 6 · full | transparent or hairline | tinted light shadow | paper, kitchens, felt |
| Pill | full · 14 · 20 · full · 10 · full | transparent | tonal | toys, 1970s, rubber |
| Ticket | 2 · 2 · 6 · 2 · 0 · 2 | solid | `shape.cut` side notches | transit, cinema, cloakroom |
| Arch | 6 · 10 · 20 · 999 · 0 · full | transparent | `shape.cut` rounded top on surfaces | riad, chapel, greenhouse |

Cut shapes (values for `shape.cut`):

- **Chamfer 4 px**: `polygon(4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px),
  calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px), 0 4px)`
- **Ticket notches (6 px, mid-height)**: `polygon(0 0, 100% 0, 100% calc(50% - 6px),
  calc(100% - 6px) 50%, 100% calc(50% + 6px), 100% 100%, 0 100%, 0 calc(50% + 6px), 6px 50%,
  0 calc(50% - 6px))`
- **Arch top**: `inset(0 round 40px 40px 0 0)`; keep ≤ 48 px or wide cards lose their first line.
- **One clipped corner (tab or file card)**: `polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100%
  100%, 0 100%)`

Consistency rules:

1. Chips and controls share a family: if controls are 0, chips are 0 or 2, not pills.
2. Media (posters, covers) take the least radius in the theme; art is never rounded more than
   its frame.
3. Avatars may be the exception (round people in a square house is fine; say so in the brief).
4. With `shape.cut`, never rely on an outer shadow or outer focus effect on surfaces.
5. The edge is part of the shape, but its width never changes (1 px): enamel and screen print
   want a dark solid edge, doubled inside with an inset shadow if it must look heavier; paper
   wants a transparent one; everything else a hairline.
6. `icon.stroke` follows: sharp/cut 1.5–2, soft 1.75, pill 2–2.25, engraved serif themes 1.25.

---

## 6. Motifs and textures made by code

Generate these as small tiling SVGs in the theme's `art/` (no scripts, no external links, no
`data:` hrefs: the kit rejects them) and reference them from `material.*.texture` as
`url(art/<name>.svg)` (the kit points it at wherever the theme's art is served, and the check
fails if the file is missing or the URL leaves the theme's `art/`). Colours are the **resolved**
token values of the ground they sit on, lightened or darkened by the stated ΔL; store the seed and parameters in the theme's `BRIEF.md`
so the tile can be regenerated when the palette changes. Use a seeded PRNG (e.g. mulberry32 with
a fixed seed) so builds are reproducible.

| Motif | Tile | Construction | Colour / opacity | Good on |
|---|---|---|---|---|
| Grain (speckle) | 128×128 | 220 `rect` 1×1 at seeded positions; half at +ΔL, half at −ΔL | ΔL 0.02–0.03, opacity 1 | canvas (stone, concrete, riso) |
| Paper fibre | 160×160 | 40 `path` quadratic curves, length 6–18 px, random angle, stroke 0.6 | ΔL 0.015 darker, opacity 0.6 | paper surfaces |
| Halftone | 8×8 (fine) or 12×12 | one `circle` r = 1.2 at centre + four quarter circles at corners (offset rows) | ink colour at 5–8% opacity | canvas of newspaper, riso, screen print; never under body text lists |
| Plain weave | 8×8 | two horizontal `rect` 8×3 and two vertical 3×8 alternating over/under (draw over-threads last) | warp +ΔL 0.012, weft −ΔL 0.012 | fabric/felt surfaces |
| Twill | 12×12 | a 3×3 grid of 4 px cells with the three diagonal cells filled (a stepped 45° line) | ΔL 0.015 | canvas of textile themes (Canut) |
| Tile (azulejo) | 48×48 | `circle` r = 12 at the centre + a `circle` r = 12 on each edge midpoint (clipped; they join into rings across tiles), stroke 1, no fill | accent at 6% opacity | canvas only, light themes |
| Zellige star | 64×64 | 8-point star from two squares rotated 45°, stroke 1, no fill | accent or room colour at 5% | canvas, `auth.crest` art |
| Dots | 16×16 | one `circle` r = 1 | ΔL 0.03 | canvas, screen |
| Hatching | 6×6 | `line` (0,6)→(6,0) plus stubs (−1,1)→(1,−1) and (5,7)→(7,5) so it tiles without seams, stroke 0.75 | ΔL 0.02 | canvas of engraving themes (Herbier) |
| Cross-hatch | 6×6 | hatching plus its mirror (same stubs), stroke 0.5 | ΔL 0.015 | the same, darker materials |
| Scanlines | 1×3 | `rect` 1×1 at y=0 | black at 18–25% | `material.screen.texture` only |
| Awning stripes | 24×24 | one `rect` 12×24 | ΔL 0.02 | canvas of market/seaside themes; never with another pattern |
| Terrazzo | 96×96 | 30 irregular `polygon`s (4–6 points, 2–5 px across), seeded | 3 room colours at 12% opacity | canvas of kitchen themes |
| Punched card | 24×32 | a 3×4 grid of 2×4 `rect` holes, seeded ~40% present | ΔL −0.02 | canvas of the Canut direction |

Subtlety rules:

1. **Never under running text** at a contrast the eye can pick out: a list over a visible
   pattern loses half its legibility while the contrast check still says it passes.
2. **One pattern per theme** at most on the canvas, plus optionally one material texture
   (paper fibre, weave). Never two geometric patterns.
3. **Tiles must not beat**: 1 px features on non-integer device pixels shimmer. Keep tile sizes
   integers and features ≥ 1 px; avoid fine diagonals below 6 px period on phones.
4. **Pattern is the motif, not the logo**: repeated room glyphs or the mascot as wallpaper is
   sprinkling (§9).
5. **Measure it**: render the tile over its ground and check the largest ΔL against the budget in
   §4.4 before shipping.
6. A texture token never moves. A moving background is a layer (§7.1): a `drift` on a repeat
   tile, slow, faint where text sits, and it stops at the still motion level.

---

## 7. Motion personalities

The person's motion level always wins: **still** (also what a device asking for reduced motion
gets) stops movement whatever the theme says, **subtle** is the default, **full** adds the most.
Durations ≤ 1000 ms (checked); keep `dur.fast` ≤ 150 so presses feel immediate in any
personality. The last column says how much the theme's layers (§7.1) might move.

| Personality | dur fast · base · slow · slower | ease standard | enter | exit | emphasized | layers | Fits |
|---|---|---|---|---|---|---|---|
| Still | 80 · 120 · 160 · 200 | [0.2, 0, 0, 1] | [0, 0, 0, 1] | [0.3, 0, 1, 1] | [0.2, 0, 0, 1] | none, or still ones | print, concrete, library |
| Crisp | 100 · 160 · 220 · 320 | [0.3, 0, 0, 1] | [0.1, 0.8, 0.2, 1] | [0.4, 0, 1, 1] | [0.2, 0.9, 0.1, 1] | a rare crossing | civic, métro, newspaper |
| Springy | 120 · 220 · 320 · 480 | [0.3, 1.3, 0.5, 1] | [0.34, 1.56, 0.64, 1] | [0.4, 0, 1, 1] | [0.5, 1.6, 0.4, 1] | twinkles, frames | 1970s, toys, pill shapes |
| Drifting | 160 · 280 · 420 · 700 | [0.4, 0, 0.2, 1] | [0.2, 0, 0, 1] | [0.4, 0, 0.6, 1] | [0.3, 0.2, 0, 1] | drift, rising particles | sauna steam, greenhouse, dusk |
| Mechanical | 90 · 140 · 200 · 280 | [0.6, 0, 0.4, 1] | [0.8, 0, 0.2, 1] | [0.6, 0, 1, 1] | [0.9, 0, 0.1, 1] | stepped frames, crossings | looms, typewriters, departure boards |
| Weighty | 140 · 240 · 360 · 520 | [0.5, 0, 0.1, 1] | [0.2, 0, 0, 1] | [0.5, 0, 0.9, 1] | [0.6, 0, 0, 1] | slow drift, a flicker | stone, lacquer, oxblood |

Notes:

- Springy curves have y values > 1 (overshoot; the kit accepts them and emits
  `cubic-bezier(0.34, 1.56, 0.64, 1)`). Use them on `enter` and `emphasized` only; a sheet that
  overshoots on exit looks broken.
- Mechanical wants steps: `ease.*` may be `steps(n)` (n 1–12), or short durations with a hard
  ease-in-out: things arrive decisively, like a shuttle.
- Motion in the interface explains where things come from; the personality only colours it.
  Never add interface motion to make a theme feel "alive": that is what layers are for, and the
  person decides how much of them moves.

### 7.1 Layers: pictures that move

`theme.json` `"layers"` (at most 12, and 48 particles in all) draws pictures in a place and moves
them as far as the person's motion level allows. They never catch a click, except `poke` pieces.

- **Where:** `page`, `hero` (Home's picture), `header`, `rail`, `rail-foot` (a box of its own
  just above the Ask Nox card, up to 240 px, hidden with the icons-only rail), `status`, `deck`
  (the music player). A layer draws **over its place's picture** (under the page scrim, under the words)
  unless `"under": true` (behind the picture: a sky through its clear parts; page, hero, status
  or header). `"above": true` puts a finish over the whole page (grain, scanlines, a vignette):
  `where: page`, opacity 0.15 at most.
- **How it sits:** `fit` cover, contain, repeat, repeat-x or natural (its own size × `scale`
  1–8, at `anchor`); `opacity` 0.05–1; `blend` normal, screen, multiply, overlay, soft-light;
  `rendering` pixel or smooth; `rooms` and `schemes` limit where it shows.
- **One way of moving:** `drift: [x, y]` px a second (±200) on a repeat or repeat-x tile, which
  pans seamlessly; `cross: {seconds 2–120, every up to 600, from left|right|top|bottom}` on a
  natural piece (a train, a bat); `particles: {count 1–24, motion rise|fall|float|twinkle,
  seconds 2–60}`, the image as one particle (steam, snow, petals, sparkles).
- **Can add:** `frames: {count 2–32, fps 1–24}` on a natural sprite sheet (frames side by side);
  `depth` 0–1 for parallax; `playing: true` on deck layers, to move only while music plays.
- **A piece that answers a click:** `poke: {frames: {count 2–32, fps 1–24 (default 10)}, image?,
  burst?: {image, count 1–12}}` on a natural piece (not `above`), at most 6 per theme. On a click
  it plays the reaction once: `image` is `count` frames of the piece's own frame size side by side
  (the piece's own image by default), and `burst` throws a few small bits out. Desktop with a
  mouse only, never at the still level. It is an anecdote from the world (the cat stretches, the
  candle flares), never interface; put poke pieces in empty space, never over controls or text.
- **Motion levels:** still shows first frames only (no crossings, no particles); subtle, the
  default, adds drift, frames, crossings and half the particles; full adds all particles and
  parallax.

Good use: one thing alive at first sight (steam, a slow cloud, a flickering candle) and one rare
surprise (a crossing every minute or two). Keep particles and crossings away from where text
sits, and every layer on the theme's palette and pixel scale.

---

## 8. Title names: a theme's only words

A theme's look is pictures, shapes and type, not sentences. Every line of text in HouseOS is its
own and practical (what's here, what to do), the same in every theme. A theme names only the 20
house titles and their star mark, in `flavor.json`, English and French:

| Key | At most | Where it shows |
|---|---|---|
| `title.<title>.name` | 28 | a house title's name on Me and in the house's titles (the genre keeper's may hold `{genre}`: the genre, or "a genre" while nobody holds it) |
| `title.star.mark` | 3 | the mark of a title's level (★ in HouseOS) |

Any other key fails the check. Pictures carry no words, letters or digits either.

Rules:

1. **Name the thing from the world**, not the feat: a bathhouse's early bird is "First in the
   bath", not "Early riser award".
2. **Tu in French**, warm and direct, never cute.
3. Write **French as its own name**, not a translation: a pun that only works in one language is
   replaced by a different good name in the other.
4. Use ’ and « » with narrow no-break spaces (U+202F) inside guillemets; no straight quotes.
5. No emoji, no exclamation marks.
6. The medal (`title.*` in `sprites.json`) and the name are one idea: a lute medal and "The
   minstrel", not a lute and "Top DJ".
7. **Leaving the names out is a choice**: HouseOS's own names stay. Bad names are worse than
   none.

---

## 9. Banned: auto-reject, with the reason

| Pattern | Why it fails | How it shows up in tokens | Instead |
|---|---|---|---|
| Blue→purple (or teal→violet) gradients | The signature of template SaaS and AI landing pages; says "no one chose" | gradient strings in `material.*.bg` or `texture`, accent 250–290 + private next to it | One flat accent from a real source; gradients only in scene art |
| Glassmorphism by default | Blur is expensive, lowers contrast over posters, and is a 2021 trend, not a material | `material.overlay.blur` ≠ none without glass in the brief; translucent `surface.bg` | Solid overlays; glass only when the source is glass (§4.3) |
| Inter/Roboto/system on white with a blue accent | That is Base plus a hue: a theme must change voice, not only colour | `font.*` unchanged, `seed.accent` hue 240–265, canvas L 0.99 | Choose faces from fonts.json; move canvas and neutral hue |
| Rainbow status soup | Seven saturated colours at equal weight destroys "colour is information" | states, rooms, people all at C ≥ 0.15 | Rooms and people at C 0.08–0.12; one accent at full strength |
| Bordered-everything cards | Boxes instead of hierarchy; noisy, bureaucratic | visible edges on surface, raised, sunken and media, plus shadows | One edge strategy per material (§4.1); hierarchy by type and space |
| Drop shadows on everything | Muddy, dated, and invisible in dark themes | `material.surface.shadow` = `elev.2+`, black `color.shadow` on light | Tonal steps; tinted shadows only on raised and overlay |
| Neon on black "cyber" | Genre cliché; fails the six questions (§1.2) and is hard to read for hours | canvas L < 0.12, accent C > 0.25 at hue 150/320/200, glow on everything | A real night place: a kissa, Cinestill, a sodium-lit street |
| Pastel everything | No value contrast: nothing is primary, states vanish, fails WCAG | rooms, accent and grounds all at L 0.85–0.95 (light) | A dark ink and one saturated accent; pastels only as tints |
| Emoji as decoration | Platform-dependent, childish in chrome, and forbidden by the guards | emoji in title names or art | Words; `Glyph`s and sprites |
| Centred everything | Breaks scanning and the left-edge grid; reads as a landing page | (layout is contract; art composed around a centred subject on every picture) | Left-aligned; centre only a single empty-state line |
| Stock "hero" illustrations | Generic people-with-laptops art; interchangeable | `home.hero.backdrop` filled with flat vector people | Scenes from the source (a room, a window), or nothing |
| Over-rounded pills everywhere | Toy-like, wastes space, erases shape hierarchy | `radius.control` and `radius.card` = full or xl | A shape language (§5); pills only for chips in a pill theme |
| Grey-on-grey "minimal" | Low contrast masquerading as taste; fails real rooms and eyes | `fg.muted` near `fg.disabled`, neutral C < 0.01 | Tinted neutrals, a proper ladder from 12 to 11 to 8 |
| All-caps mono eyebrow above every title | The 2023 "technical" template tic | `text.label` uppercase in the mono face (kickers use `label`) | Mixed-case `label` in the body face (§3.3) |
| Warm-minimal startup (oat ground + soft serif + one blue) | 2024's default "calm" product look: a beige canvas, a soft display serif (Fraunces, Young Serif, Instrument Serif) and one blue button reads as a template, not a house | canvas L 0.93–0.97 at hue 60–90, a soft serif in `font.display`, `seed.accent` hue 240–265, nothing else changed | A ground and an ink from a real source, a material that is not only colour. Linen Morning sits on this edge and escapes it only through its weave texture, walnut ink and its own pieces; a theme with less than that is the template |
| Epic fantasy default (gold Cinzel on black) | Genre costume, not a house | Cinzel + accent 85 + canvas L < 0.15 | Cinzel on stone or plaster, with a daylight palette |

---

## 10. Three directions for one brief

**Brief:** "A warm family flat in Lyon, lots of books and plants." Lyon offers more than "warm":
the silk weavers' workshops of the Croix-Rousse (the Jacquard loom was built for them), the
botanical tradition of the Parc de la Tête d’Or's greenhouses, and the apartments themselves,
many furnished in the 1970s. Three directions, differing on every axis:

| Axis | A. Canut | B. Herbier | C. Salon 74 |
|---|---|---|---|
| Key | night (L 0.17) | noon (L 0.965) | mid-key light (L 0.93) |
| Temperature | warm walnut | cool green-grey | warm oat and orange |
| Material | fabric, woven | paper, engraved | cork and felt |
| Type | pixel blackletter + sturdy humanist + narrow mono | garalde display + humanist + typewriter | 1970s heavy serif + legible sans |
| Shape | sharp, cut | ticket labels | soft to pill |
| Motion | mechanical | still | springy |
| Motif | twill / punched card | hatching | none (cork speckle) |

### A. Canut · « Canut »

*A silk-weaver's workshop in the Croix-Rousse at night: walnut looms, a skein of peacock-teal
silk under the lamp, punched cards stacked by the window.*

`theme.json`: `"schemes": ["dark"]`, `"identity": "line"`,
`"fonts": {"display": "Jacquard 12", "body": "Fira Sans", "mono": "Victor Mono"}`.

```json
"seed": {
  "neutral": {"$value": "oklch(0.45 0.06 45)"},  "accent":  {"$value": "oklch(0.76 0.1 200)"},
  "success": {"$value": "oklch(0.8 0.13 130)"},  "warning": {"$value": "oklch(0.85 0.13 88)"},
  "danger":  {"$value": "oklch(0.7 0.16 22)"},   "info":    {"$value": "oklch(0.78 0.07 250)"},
  "private": {"$value": "oklch(0.74 0.1 330)"}
},
"color": {
  "accent": {"border": {"$value": "oklch(0.55 0.08 200)"}},
  "room": {
    "home": {"$value": "oklch(0.87 0.03 70)"},    "listen": {"$value": "oklch(0.72 0.14 15)"},
    "watch": {"$value": "oklch(0.8 0.09 200)"},   "house": {"$value": "oklch(0.8 0.1 130)"},
    "files": {"$value": "oklch(0.84 0.11 88)"},   "ask": {"$value": "oklch(0.76 0.11 350)"},
    "me": {"$value": "oklch(0.78 0.09 300)"},     "control": {"$value": "oklch(0.78 0.08 250)"}
  }
}
```
The rooms are silk skeins: crimson, teal, moss, gold thread, rose, violet. (Listen's crimson and
danger's red sit near each other; rooms never carry state and danger always has its word.)

- **Type**: Jacquard 12 at 24/36/48 for `display-m/l/xl` and 24/1.1 for `brand` (a jacquard-woven
  face for the city of the Jacquard loom), Fira Sans body 16/1.45 (compact, sturdy) and `label`
  13/600 mixed case +0.02 (it carries the kickers), Victor Mono `numeric` 14 (narrow, like a card's columns).
  It shares only the display face with Carved Night; palette, material and body all differ.
- **Material**: fabric. `material.surface.border 1px solid transparent`, tonal steps,
  `material.canvas.texture url(art/twill.svg)` (twill, ΔL 0.015); `material.sunken.shadow inset 0 1px 3px
  alpha({color.shadow}, 40%)`.
- **Shape**: `radius.* 0`, `shape.cut` chamfer 4 px; `icon.stroke 2`.
- **Motion**: mechanical (§7), with `steps()` on small things. `home.hero.backdrop`: a loom by
  the window at night, drawn from the theme's ramps, no text; a hero layer of the shuttle
  crossing now and then (`cross`, `frames`).
- **Motif**: punched card in `auth.crest` art; twill on canvas.

### B. Herbier · « Herbier »

*A herbarium on the desk by the window: blotting paper, pressed ferns, labels typed in violet
school ink.*

`theme.json`: `"schemes": ["light"]`, `"identity": "line"`,
`"fonts": {"display": "Cormorant Garamond", "body": "Source Sans 3", "mono": "Courier Prime"}`.

```json
"seed": {
  "neutral": {"$value": "oklch(0.58 0.03 140)"}, "accent":  {"$value": "oklch(0.45 0.16 300)"},
  "success": {"$value": "oklch(0.58 0.1 165)"},  "warning": {"$value": "oklch(0.6 0.13 70)"},
  "danger":  {"$value": "oklch(0.48 0.17 25)"},  "info":    {"$value": "oklch(0.52 0.08 230)"},
  "private": {"$value": "oklch(0.5 0.1 355)"}
},
"color": {
  "bg": {
    "canvas":  {"$value": "oklch(0.965 0.012 110)"}, "surface": {"$value": "oklch(0.985 0.006 110)"},
    "raised":  {"$value": "oklch(0.99 0.004 110)"},  "overlay": {"$value": "oklch(0.985 0.006 110)"},
    "sunken":  {"$value": "oklch(0.94 0.015 115)"}
  },
  "room": {
    "home": {"$value": "oklch(0.46 0.03 120)"},   "listen": {"$value": "oklch(0.5 0.12 300)"},
    "watch": {"$value": "oklch(0.5 0.08 230)"},   "house": {"$value": "oklch(0.5 0.1 150)"},
    "files": {"$value": "oklch(0.52 0.1 85)"},    "ask": {"$value": "oklch(0.5 0.13 25)"},
    "me": {"$value": "oklch(0.5 0.1 350)"},       "control": {"$value": "oklch(0.5 0.08 265)"}
  }
}
```
The accent is *encre violette*, the violet ink of French school exercise books; private moves to
a faded rose to stay apart from it.

- **Type**: Cormorant Garamond 600 for `display-l` and `display-xl` only (Base's 34 and 44 px;
  `display-m` stays in Source Sans 3), italic reserved for Latin plant names in art; Source Sans 3
  body 17/1.5, titles 600; Courier Prime `label` 13, no caps (typed
  specimen labels), `numeric` Courier Prime.
- **Material**: paper recipe (§4.3) with `color.shadow oklch(0.35 0.03 140)`, `material.paper.rotate
  0.6deg`, `material.surface.texture url(art/fibre.svg)`.
- **Shape**: ticket: `radius.control 2`, `radius.card 2`, `radius.chip 2`, `shape.cut` ticket
  notches (labels tied to specimens); `icon.stroke 1.25` (engraved).
- **Motion**: still.
- **Motif**: hatching at 6 px, ΔL 0.02, on canvas only; `auth.crest` a hatched fern.

### C. Salon 74 · « Salon 74 »

*The family living room, 1974: oat carpet, a burnt-orange armchair, a cork board by the phone,
the record deck always open.*

`theme.json`: `"schemes": ["light"]`, `"identity": "line"`,
`"fonts": {"display": "Young Serif", "body": "Inclusive Sans", "mono": "Courier Prime"}`.

```json
"seed": {
  "neutral": {"$value": "oklch(0.55 0.05 60)"},  "accent":  {"$value": "oklch(0.55 0.16 45)"},
  "success": {"$value": "oklch(0.52 0.1 150)"},  "warning": {"$value": "oklch(0.56 0.12 85)"},
  "danger":  {"$value": "oklch(0.44 0.16 18)"},  "info":    {"$value": "oklch(0.5 0.08 230)"},
  "private": {"$value": "oklch(0.48 0.1 330)"}
},
"color": {
  "bg": {
    "canvas":  {"$value": "oklch(0.93 0.03 80)"},  "surface": {"$value": "oklch(0.955 0.022 80)"},
    "raised":  {"$value": "oklch(0.975 0.015 80)"}, "overlay": {"$value": "oklch(0.965 0.02 80)"},
    "sunken":  {"$value": "oklch(0.9 0.035 75)"},  "hover":   {"$value": "oklch(0.9 0.035 75)"},
    "pressed": {"$value": "oklch(0.87 0.04 75)"}
  },
  "fg": {"default": {"$value": "oklch(0.28 0.04 50)"}},
  "border": {"strong": {"$value": "oklch(0.55 0.05 60)"}},
  "person": {"6": {"$value": "oklch(0.56 0.12 90)"}},
  "room": {
    "home": {"$value": "oklch(0.44 0.03 60)"},    "listen": {"$value": "oklch(0.52 0.15 45)"},
    "watch": {"$value": "oklch(0.48 0.08 220)"},  "house": {"$value": "oklch(0.48 0.1 135)"},
    "files": {"$value": "oklch(0.54 0.11 85)"},   "ask": {"$value": "oklch(0.46 0.14 15)"},
    "me": {"$value": "oklch(0.46 0.1 330)"},      "control": {"$value": "oklch(0.46 0.08 270)"}
  }
}
```
Mid-key: the canvas is the carpet, surfaces are lighter (felt cushions), text is dark brown, not
black. Danger is a deep brick, darker and redder than the orange accent.

- **Type**: Young Serif for `display-*` and `brand`, `lineHeight` 1.1; Inclusive Sans body 17/1.5,
  titles 700; Courier Prime `numeric`; `label` Inclusive Sans 13/600, no caps.
- **Material**: felt: `material.surface.border 1px solid transparent`, `material.surface.shadow 0 1px 0
  alpha({color.shadow}, 10%)`, `color.shadow oklch(0.3 0.04 55)`; paper notes on the House room
  with `material.paper.rotate 1.2deg`.
- **Shape**: soft to pill: `radius.control {radius.full}`, `radius.card {radius.xl}`, `radius.sheet
  {radius.xl}`, `radius.chip {radius.full}`, `radius.media {radius.m}`; `icon.stroke 2.25`.
- **Motion**: springy on enter; `ease.exit` plain.
- **Motif**: none on grounds; the cork speckle only behind paper notes if the House board is
  given art.

### Two more poles for the same brief

The three above are all historical. Two directions people ask for that none of them covers: a
**contemporary** one and a **high-contrast** one. They differ from A–C and from each other on key,
material, type and ornament.

### D. Presqu’île · « Presqu’île » (contemporary)

*A new flat at the Confluence: pale poured concrete, white oak, big glass, and the red of a tram
passing the window.*

`theme.json`: `"schemes": ["light"]`, `"identity": "line"`,
`"fonts": {"display": "Bricolage Grotesque", "body": "Inclusive Sans", "mono": "Martian Mono"}`.

```json
"seed": {
  "neutral": {"$value": "oklch(0.56 0.012 90)"}, "accent":  {"$value": "oklch(0.56 0.19 30)"},
  "success": {"$value": "oklch(0.52 0.11 155)"}, "warning": {"$value": "oklch(0.6 0.13 75)"},
  "danger":  {"$value": "oklch(0.48 0.17 20)"},  "info":    {"$value": "oklch(0.5 0.09 240)"},
  "private": {"$value": "oklch(0.5 0.1 320)"}
},
"color": {
  "bg": {
    "canvas": {"$value": "oklch(0.975 0.003 90)"}, "surface": {"$value": "oklch(0.99 0.002 90)"},
    "raised": {"$value": "oklch(1 0 0)"},          "sunken":  {"$value": "oklch(0.955 0.004 90)"}
  },
  "fg": {"default": {"$value": "oklch(0.2 0.01 90)"}},
  "room": {
    "home": {"$value": "oklch(0.45 0.015 90)"},  "listen": {"$value": "oklch(0.5 0.07 60)"},
    "watch": {"$value": "oklch(0.5 0.06 230)"},  "house": {"$value": "oklch(0.5 0.07 150)"},
    "files": {"$value": "oklch(0.54 0.08 95)"},  "ask": {"$value": "oklch(0.48 0.07 350)"},
    "me": {"$value": "oklch(0.48 0.06 300)"},    "control": {"$value": "oklch(0.44 0.06 260)"}
  }
}
```
Concrete, not paper: the neutral is almost grey (C 0.012, warm), surfaces are lighter than the
canvas, and the tram red is the only saturated thing on a page (rooms stay at C ≤ 0.08).

- **Type**: Bricolage Grotesque 700 for `display-*`, −0.02 (its optical size follows the size);
  Inclusive Sans body 16/1.5 and titles 700; `label` Inclusive Sans 13/600 mixed case, +0.01;
  Martian Mono `numeric` only (it is wide: times and counts, never labels).
- **Material**: flat. `material.surface.border 1px solid {color.border.subtle}`, no shadows,
  `material.raised.shadow {elev.1}` only for the Now bar and menus; no texture anywhere.
- **Shape**: sharp but not cut: `radius.control {radius.xs}`, `radius.card {radius.s}`,
  `radius.chip {radius.full}`; `icon.stroke 1.5`.
- **Motion**: crisp: `dur.fast 100`, `dur.base 160`, `ease.standard [0.2, 0, 0, 1]`.
- **Ornament**: none. The house's name in `brand` is the only display moment in the chrome.

### E. Affiche · « Affiche » (high contrast, AAA)

*A Lyon poster column in full sun: black ink on white paper, one printer's blue, nothing faint.*
For someone with low vision, a bright room, or a tablet on the fridge read from across the
kitchen: every text colour reaches **7:1 (WCAG AAA)** on every ground, not only the kit's 4.5.
It gets there with ink, weight and hard edges, not size: text stays in the band like any theme's.

`theme.json`: `"schemes": ["light"]`, `"identity": "line"`,
`"fonts": {"display": "Libre Franklin", "body": "Atkinson Hyperlegible Next", "mono": "JetBrains
Mono"}`.

```json
"seed": {
  "neutral": {"$value": "oklch(0.5 0.01 260)"},  "accent":  {"$value": "oklch(0.4 0.19 265)"},
  "success": {"$value": "oklch(0.42 0.12 150)"}, "warning": {"$value": "oklch(0.45 0.11 65)"},
  "danger":  {"$value": "oklch(0.42 0.17 25)"},  "info":    {"$value": "oklch(0.42 0.1 235)"},
  "private": {"$value": "oklch(0.42 0.13 315)"}
},
"color": {
  "bg": {
    "canvas": {"$value": "oklch(1 0 0)"},            "surface": {"$value": "oklch(0.975 0.003 260)"},
    "raised": {"$value": "oklch(1 0 0)"},            "sunken":  {"$value": "oklch(1 0 0)"},
    "hover": {"$value": "oklch(0.94 0.006 260)"},    "pressed": {"$value": "oklch(0.9 0.008 260)"},
    "selected": {"$value": "oklch(0.93 0.03 265)"}
  },
  "fg": {
    "default": {"$value": "oklch(0.15 0.01 260)"},   "muted": {"$value": "oklch(0.3 0.01 260)"},
    "subtle": {"$value": "oklch(0.34 0.01 260)"},    "placeholder": {"$value": "oklch(0.36 0.01 260)"},
    "link": {"$value": "oklch(0.4 0.19 265)"}
  },
  "border": {
    "subtle": {"$value": "oklch(0.55 0.01 260)"},    "default": {"$value": "oklch(0.45 0.01 260)"},
    "strong": {"$value": "oklch(0.2 0.01 260)"}
  },
  "paper":   {"muted": {"$value": "oklch(0.3 0.01 260)"}},
  "accent":  {"fg": {"$value": "oklch(0.4 0.19 265)"}},
  "success": {"fg": {"$value": "oklch(0.36 0.1 150)"}},  "warning": {"fg": {"$value": "oklch(0.37 0.09 65)"}},
  "danger":  {"fg": {"$value": "oklch(0.37 0.15 25)"}},  "info":    {"fg": {"$value": "oklch(0.36 0.09 235)"}},
  "private": {"fg": {"$value": "oklch(0.36 0.12 315)"}},
  "room": {
    "home": {"$value": "oklch(0.3 0.02 260)"},   "listen": {"$value": "oklch(0.4 0.12 50)"},
    "watch": {"$value": "oklch(0.4 0.09 220)"},  "house": {"$value": "oklch(0.4 0.1 145)"},
    "files": {"$value": "oklch(0.42 0.09 90)"},  "ask": {"$value": "oklch(0.4 0.13 10)"},
    "me": {"$value": "oklch(0.4 0.12 320)"},     "control": {"$value": "oklch(0.38 0.11 285)"}
  }
},
"text": {
  "display-xl": {"$value": {"fontFamily": "{font.display}", "fontSize": 48, "fontWeight": 800, "lineHeight": 1.05, "letterSpacing": -0.01}},
  "display-l":  {"$value": {"fontFamily": "{font.display}", "fontSize": 37, "fontWeight": 800, "lineHeight": 1.1, "letterSpacing": -0.01}},
  "display-m":  {"$value": {"fontFamily": "{font.display}", "fontSize": 29, "fontWeight": 800, "lineHeight": 1.15}},
  "title-l": {"$value": {"fontFamily": "{font.body}", "fontSize": 23, "fontWeight": 700, "lineHeight": 1.2}},
  "title-m": {"$value": {"fontFamily": "{font.body}", "fontSize": 19, "fontWeight": 700, "lineHeight": 1.25}},
  "title-s": {"$value": {"fontFamily": "{font.body}", "fontSize": 17, "fontWeight": 700, "lineHeight": 1.3}},
  "body-l":  {"$value": {"fontFamily": "{font.body}", "fontSize": 19, "fontWeight": 400, "lineHeight": 1.45}},
  "body-m":  {"$value": {"fontFamily": "{font.body}", "fontSize": 17, "fontWeight": 400, "lineHeight": 1.5}},
  "body-s":  {"$value": {"fontFamily": "{font.body}", "fontSize": 15, "fontWeight": 400, "lineHeight": 1.4}},
  "action":  {"$value": {"fontFamily": "{font.body}", "fontSize": 16, "fontWeight": 700, "lineHeight": 1.15}},
  "label":   {"$value": {"fontFamily": "{font.body}", "fontSize": 14, "fontWeight": 700, "lineHeight": 1.15}},
  "caption": {"$value": {"fontFamily": "{font.body}", "fontSize": 13, "fontWeight": 500, "lineHeight": 1.3}},
  "numeric": {"$value": {"fontFamily": "{font.mono}", "fontSize": 15, "fontWeight": 500, "lineHeight": 1.15}}
}
```
The ramps' state text (step 11) stops near 5:1, and the paper's muted text near 6:1, so every
`*.fg` and `paper.muted` is set by hand. The lowest text pair the kit measures is 8.2:1 (a
room's text on its own light); white on the accent is 9.5:1.

- **Type**: the poster is in the weight. Libre Franklin 800 for `display-*`, each at Base + 10 %
  (48, 37, 29), −0.01, never caps. Atkinson Hyperlegible Next everywhere else, every component
  style at Base + 1 px with its line kept within 2 px (`body-m` 17/1.5, `body-s` 15, `caption` 13),
  titles 700, buttons 700, `label` 14/700 mixed case; JetBrains Mono `numeric` 15/500.
- **Material**: paper-white and ink, hard edges. Surfaces take a 1 px `border.default` edge and no
  shadow; controls and raised things a near-black edge doubled inside, so they read as 2 px
  without growing:
  ```
  material.surface.border    1px solid {color.border.default}
  material.surface.shadow    none
  material.raised.border     1px solid {color.border.strong}
  material.raised.shadow     inset 0 0 0 1px {color.border.strong}
  material.sunken.border     1px solid {color.border.strong}
  material.sunken.shadow     inset 0 0 0 1px {color.border.strong}
  material.overlay.border    1px solid {color.border.strong}
  ```
  `elev.4` stays on sheets (Base's), no texture, `material.overlay.blur none`.
- **Shape**: square as a poster: `radius.control`, `card`, `sheet`, `chip` and `media` all
  `{radius.none}`; `icon.stroke 2.25`; the focus ring is the accent.
- **Motion**: still: short, plain fades, no layers.
- **Ornament**: none, no layers, no title names: nothing on the page is there to be looked at.

All five passed `theme_kit check` as written here, colours, text band and contract included
(2026-09-26, with system fonts; font files and textures were not part of those runs).
E's lowest text pair in the kit's contrast matrix is 8.2:1, above AAA's 7:1.

---

## 11. Review: the rubric and the common failures

Run `theme_kit check <id>` first; everything below is what code cannot judge. Judge the theme on
its screenshots (the tour, `themes/_kit/tour.cjs`) or its preview, as a demanding art director
who did not make it. Then get a fresh-eyed review: someone who sees only the direction, this
rubric and the screenshots (the method: `themes/_kit/METHOD.md` §7). A first round nearly always
ends in "another round".

**Rubric** (score each 1–10, with one line of reason):

1. **Readability:** every text comfortable at a glance. No text on busy pictures (scrims, solid
   surfaces, plaques). Contrast passes with room to spare.
2. **Usability:** controls look like controls; selected, current, hover, focus and disabled are
   obvious. Nothing cut off or crowded. French fits. The Control Room is calm.
3. **Cohesion:** one palette, one light, one pixel scale or stroke, one voice across every part.
   Nothing looks borrowed from another theme.
4. **Craft:** pictures that hold up zoomed: clean clusters, intentional edges, believable
   materials, compositions made for their box.
5. **Depth:** every part considered; three or more discoveries (a detail that rewards a second
   look, a layer that surprises once in a while).
6. **Restraint:** motion gentle and optional; effects serve the idea; budgets kept.
7. **Would the person love it:** what they asked for, done better than they imagined.

A review ends with **keep these** (what must survive), **fixes in priority order** (concrete and
located: "the Listen banner's radio sits under the search button on a phone"), and a verdict:
ship, or another round.

**Common first-round failures**

- [ ] **One great Home picture, everything else thin:** banners, the music deck, My Space, the
      TV, the rail get far less craft and read as placeholders.
- [ ] **Details too small to see:** 1–2 px screws, 8 px wind bells, a discovery on a 10 px
      screen, Nox moods that differ by one pixel. If it can't be seen at 1×, it doesn't exist.
- [ ] **Text touching or sitting on art:** banner props under header buttons or touching the
      title's cap line; sparkles over words; page art showing behind text on phones.
- [ ] **Phone crops:** banners crop to their middle on phones. Keep subjects in the band that
      survives (about 45–75 % of the width, the top 60 % of the height), the far right calm.
- [ ] **Pixel scale drift:** `cover` scales pixel pictures by fractions; draw at the box's real
      height where possible; never a 2× hero beside a 4× page.
- [ ] **Surfaces that let the page through:** a transparent 9-slice centre under text (the deck,
      the dock, the Now bar).
- [ ] **Layer stacking assumed wrong:** layers draw over their place's picture unless `under`.
- [ ] **The room tint behind banners** left on by accident (`part.header.banner-wash`: 0 for
      none).
- [ ] **Off-palette leftovers:** default avatars, a selected or current state in the accent's
      soft tint, a fourth hue from a status seed.
- [ ] **Two drawing systems:** Nox and the pieces drawn unlike the pictures (a bottle when the
      hero shows an egg).
- [ ] **Motion nobody sees:** a crossing every 150 s is a fine surprise, but with motion on,
      something should be alive at first sight.
- [ ] **A maximalist idea gone timid:** use the budget (2 MB of art, 12 layers, 48 particles)
      when the idea asks for it; a minimal theme does the opposite, on purpose.

**Also check**

- [ ] The one-sentence mood names a place, object, era or process, and predicts the scheme and
      the accent hue. Not Base with a new accent. Nothing from §9.
- [ ] Squint and greyscale: a clear value ladder (canvas → surface → raised), the primary
      action still the most prominent thing, states apart by lightness.
- [ ] One accent: count the saturated hues on Home. Neutrals tinted.
- [ ] The display face only in `display-*`, `brand` and titles; body reads for a paragraph of
      Nox's answer on a phone; French (« Paramètres de la maison », « cœur », « l’atelier »)
      fits at `display-l`, `title-m` and `label`.
- [ ] Every slot empty and filled: the layout still right. Posters and covers untouched.
- [ ] Both schemes, if two, reviewed page by page; the light one with darker marks.
- [ ] Motion at the still level: nothing essential disappears.
- [ ] Title names, if any: en and fr as their own names, *tu*, ≤ 28 characters, no emoji.
