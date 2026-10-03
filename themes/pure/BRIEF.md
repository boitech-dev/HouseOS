# Pure · brief

**The idea, in one sentence:** architecture made of light: a house of black concrete where the
sun is the only ornament, and its negative, the same house printed in black ink on cream paper.

- **Names:** Pure · Pur
- **Scheme(s):** both. Dark first (black concrete, white light); light is its negative (cream
  paper, black ink), designed as the monograph that photographs the building.
- **References, in words:** Tadao Ando's béton brut (form-tie holes on the shuttering grid, a slit
  of light, a square window's patch sliding across a wall); Swiss posters and grids (flush-left,
  big voids, one grotesk); architectural drawings (1 px hairlines that overshoot at the corners);
  black-and-white architecture monographs on cream stock; a late afternoon sun in an empty room.
- **Material feel:** concrete and light (renders), paper (the light scheme).
- **Shape:** sharp. Radius 0 everywhere; only the person (avatar ring, the oculus) is round.
- **Edge:** hairline, 1 px, grey on black / warm grey on cream. Surfaces part by lines, not fills.
- **Type:** Archivo Light for display (large, tight, -0.025em: a calm architectural voice),
  Instrument Sans for body and controls (crisp, slightly condensed neo-grotesk that reads at
  14 px), Fragment Mono for numbers and times (a Swiss mono, the dimension text of a drawing).
  Labels are small capitals tracked 0.1em, like drawing annotations.
- **Colour story:** no hue. Dark: #000 canvas, near-black surfaces (#070707, #0e0e0d) split by
  hairlines, warm white ink #f3f1eb, and the sun's cream (#e3d6bb) as the rare second tone: the
  one room light (rooms unified), the kicker above titles. Light: cream paper #eee8db, ink
  #12110f, black primary buttons, a deep umber (#5f5544) as the second tone. Statuses are
  desaturated and dignified (sage, ochre, clay, slate); no red, it belongs to Modular.
- **Identity:** line icons for the interface; pixel pieces made of squares: Nox is a square of
  light with two square eyes and its own cast shadow (the negative of a shadow); the room marks
  are openings; the medals are plaques with geometric marks. Pieces paint in the light (white in
  the dark, ink on the paper).
- **Motion:** crisp and brief (90/120/140/200 ms, no bounce). Ambient life is only the sun: a
  window's light crossing the house every four minutes, blades of sun walking across the music
  deck while music plays, and one poke: touch the slit at the rail's foot and a cloud passes.
- **The negative selection:** where you are is a solid block: the rail's current room and the
  settings page are light on black (ink on paper), chips and primary buttons too. The room marks
  throw a one-pixel shadow of the ground's colour, so they are drawn on the block.
- **Do:** let light carry every picture; square corners and hairlines; big quiet voids.
- **Don't:** any hue, grey-on-grey, glass or blur, gradients for their own sake, words in pictures.

## One light

A single low sun, warm white (1.0, 0.95, 0.86), from the upper left and in front, reaching the
concrete only through openings. The world light is almost nothing, so shadows are near black.
Every render (Blender, `docs/design/themes/pure/scenes/`) uses it and the same concrete material
(mottled béton, pores, shuttering seams on a 1.8 × 0.9 m grid, form-tie holes 3 × 2 per panel).

## One building, two prints

Every picture has a print per scheme (`schemes`, and per room for the banners):
- **Night print (dark):** the render's light only, on black: only what the sun touches exists.
- **Paper print (light):** either a clean daylight photograph (hero, rail foot, My Space: their
  own renders without bounced light, crisp sun, denoised), or a **drawing** of the light (page,
  banners, empty state): the patches of sun filled with light, outlined by a crisp 1 px ink line,
  the form-tie holes they fall on as ink dots, and nothing else on the paper.
- The crest has two renders: at night a dark block whose opening glows and throws its square of
  light on the floor; by day a cream block whose opening is the one ink void.
Hairline art (the drawing frame, the seams) is a light line with an ink line beside it: one is
seen in each scheme.

## The house

| Place | What it gets | Why |
|---|---|---|
| Sign-in | `auth.crest`: night, a dark block whose opening glows and throws its square of light on the floor; day, a cream block and one ink void | a square within a square: the theme's emblem |
| Status bar | a `status` layer: a hairline of light along the top of the house | the roof slit |
| Rail | a `rail` layer: a seam of light down its edge; a `rail-foot` piece: a slit at the end of a corridor, its line of sun on the floor (touch it: a cloud passes); the current room a solid block of light | the rail meets the page along light |
| Dock (phones) | black (cream) bar, hairline top; the room marks | calm; the marks carry it |
| Page | `page.backdrop`: one square window's patch of sun on the wall (night), the patch and its six tie holes on clean paper (day), under a strong scrim; `above` grain (concrete pores, 5 %); `above` sun window crossing every four minutes | the wall every room stands against |
| Headers | `banner` variant, no wash: every room its own opening, its patch of light at 60 % of the width, 16–72 px from the top (slits for Listen, a wide slot for Watch, six squares for House, louvres for Files, an oculus for Me and My Space, a single line for the Control Room...); drawn in ink outline on paper | each room of the house has its own window |
| Home | `home.hero.backdrop`: a blade of sun through a roof slit across a cantilevered stair, a night and a paper print; dust motes turning (dark) | the cover picture |
| Listen | `deck.surface`: a drawing frame (overshooting hairlines, 9-slice); a `deck` layer, `playing`: blades of sun walking across it | the music deck as a drawing, alive only with music |
| Watch | `watch.tv.bezel`: a screen set deep in concrete, its glow on the reveals; posters untouched | |
| Games | covers on the plain ground (`part.page.gallery`), square corners | never picture on picture |
| My Space | `space.room.scene`: a small room, one square window, sun on a bench | a place to sit in the light |
| Me | 5 avatars and 20 medals as geometric marks (stairs, slits, nested squares, a meander, a plumb line); titles named for light, stairs and concrete; people's colours without hue, told apart by lightness and warm/cool | |
| Control Room | the single line of light in its header; forms and tables plain: hairlines, square fields | calm on purpose |
| Sheets, dialogs | `sheet.surface`: the same drawing frame; flat, hairline, no blur | |
| Toasts, menus | inverse: white block (dark), ink block (light) | the negative selection |
| Empty states | `state.empty`: a sharp patch of sun on the floor, a small bird's shadow (a quarter of its width) on its edge | the smile |
| Controls | primary: a solid block of light (dark) or ink (light); secondary: hairline; square slider thumbs; selected chips invert; selected rows a clear step | inverted selection |
| Nox | a square of light, two square eyes, its shadow on the floor; 6 moods | the negative of a shadow |
| Rooms | unified: the sun's cream | one light |

## Art sources

Every picture is drawn by code in this repository: renders by `docs/design/themes/pure/scenes/*.py`
(Blender, Cycles), finished and drawn by `docs/design/themes/pure/make.py`; pieces by
`docs/design/themes/pure/sprites.py`. Original, CC-BY-4.0 with the theme. No text in any picture.

## Pokes (desktop)

| Touch | What happens |
|---|---|
| The slit at the rail's foot | a cloud passes over the sun (0.9 s). At night the slit and its line of light dim and come back; by day the corridor's shade pales toward the paper and returns (each scheme has its own piece; the paper print fades into the page, no box) |
