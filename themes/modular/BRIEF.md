# Modular: brief

**Idea, one sentence:** Swiss modular typography as a house: every letter, picture and piece is
built from one grid of modules (squares, quarter circles, dots) in black and white, with one
signal red, like a poster system you live in.

**Names:** Modular / Modulaire. **Schemes:** light (its own: warm paper, black ink) and dark (the
inverse duality: black paper, white ink, the same red).

## The tells (what makes it read as Swiss modular at a glance)

1. **A visible grid that everything obeys.** Wim Crouwel's New Alphabet and his Stedelijk
   posters: the grid is printed, letters are drawn inside its cells. Here: a faint dot at every
   grid crossing on the page, and every picture drawn cell by cell on the same 24 px module.
2. **Letters made of modules.** Crouwel's grid-built letters: a heavy grotesk drawn on a square
   grid (Jersey 15) for titles and the house's name, never for small text.
3. **Four shapes only.** Square, quarter circle, half circle, dot: Ben Bos and Total Design's
   fat modular numerals. No triangles (the play keys keep the house's line icons).
4. **Duality.** Black on white, then white on black; the negative is as designed as the positive.
5. **One red module per composition.** Müller-Brockmann's red: loud, rare, placed asymmetrically.
6. **Rules, not shadows.** 1 px black rules and black blocks make the hierarchy; zero radius on
   boxes, full circles for chips and people.
7. **Variation by rule.** Karl Gerstner's programmes: the room emblems are one programme, the red
   module steps to a new corner in each room.
8. **Captions in tracked caps.** Small labels uppercase with 0.09em tracking; titles big and tight.

## Three moments

- **Home's hero:** a street poster built from blocks, quarter and half circles, with gutters
  between the houses and one red door: by day a black sun, by night a crescent and lit windows.
- **The music deck:** a dot-matrix level meter in red along its top edge that runs only while
  music plays, over segmented red bars and a round black thumb.
- **The surprise:** switch the scheme and the house goes to night: the street's lights come on
  under a crescent, the crest and the room follow, and the emblems redraw themselves in line.

## Spec

- **Palette:** paper `#F2EFE8` (ground, warm), ink `#141312` (text, blocks, selected marks),
  signal red (`#CC2812` by day, `#FF4F2E` by night, so the button's words pass: the main
  button, the playing meter, one module per picture). Tones between paper and ink are mixes of the two (never a new hue). Status colours are
  kept for meaning only (a deep green, an ochre, a crimson, a Swiss blue), never decoration. In the
  dark scheme paper and ink swap; the red stays.
- **Light:** none. Flat print: no shading, no shadows, no gloss. Depth is only overprint order.
  The hero's 'light' is the scheme itself: light is day (a black sun), dark is night (a moon).
- **Medium and scale:** vector (SVG), crisp, no grain. One module: 24 px on the page grid; each
  picture uses its own grid of equal cells. Pixel pieces (sprites) on the 16 × 16 grid, 1 px = one
  module unit.
- **Type:** Jersey 15 (a grotesk built on a square grid, heavy, tight) for titles and the brand;
  Schibsted Grotesk (a clean grotesk, reads at 14 px) for everything read; Space Mono for numbers.
- **Shape language:** radius 0 on every box; chips, avatars and slider thumbs fully round. 1 px
  rules. The panel's top-left corner carries a small ink module; sheets carry a black band with a
  red module on top.
- **Motion:** snappy (80–280 ms), things enter in steps (`steps(4)`), like a module flipping. The
  page grid drifts one module a minute; the spectrum moves only while music plays.

## The house, part by part

| Place | What it gets | Why |
|---|---|---|
| Sign-in | crest: a house built from modules, red dot door | the first poster a guest sees |
| Status bar | paper, black rule, a ruler of tick dots along its foot; now and then a red module walks the ruler | the bar is a ruler of the grid |
| Rail | paper with a black rule; bold module room marks with a paper contour; the current room an ink block with paper words; foot (a rail-foot layer): a 4 × 4 Gerstner permutation of quarters that turns when clicked | the grid reaches the edge |
| Dock (phones) | paper, black rule on top; the bold room marks, an ink mark on the current door; Nox on the Ask plate | calm: it's a tool |
| Page | paper, drifting dot grid (a module a minute) | the visible grid (Crouwel) |
| Headers | banner variant, no wash: a running-head emblem per room at the top right (64 × 48 on a 16 px module), one programme, the red module steps to a new place in each room; by night each room's own negative | Gerstner's variation by rule |
| Home | the hero poster | moment one |
| Listen | the deck as a poster: 9-slice frame, 1 px rule, black head band, one red square (negative by night); a red dot-matrix meter along its foot only while music plays; ink segmented progress and volume; the red play key | moment two |
| Watch | TV bezel: a black frame on the grid, a red standby dot; posters untouched | frame, never filter |
| Games | covers untouched on the paper ground | never picture on picture |
| My Space | a room drawn in modules: window, lamp, chair, red rug | same programme |
| Me | 5 avatars and 20 medals drawn in modules; initials on ink discs (eight steps of the ink); titles named in the type-shop voice | one world |
| Control Room | same rules, no pictures, tables on paper with hairlines | calm on purpose |
| Sheets, dialogs, menus | paper, black rule, black band with a red module on top of sheets | a poster's head |
| Empty state | a module face with a quarter-circle smile | a small smile |
| Controls | the red main button (paper words by day, black by night); outlined secondary; quiet buttons on a faint module tile; chosen chips and switches in ink; segmented ink meters on a paper-mix track, round thumb | controls look like controls |
| Nox | square body, quarter-circle ears, square eyes; blink flips the eye modules | built from the grid |
| Rooms | unified: every room's light is the ink (selected marks, tabs, progress are black blocks; red stays for acting) | a two-ink print |

## Art sources

All pictures are drawn by code for this theme (`docs/design/themes/modular/make.py`), original,
CC-BY-4.0 with the theme. No text, letters or numerals in any picture. Fonts: Doto, Schibsted
Grotesk and Space Mono, each under the SIL Open Font License (files in `fonts/`).

## Do / don't

- Do: keep to squares, quarter circles and dots; one red module per picture; black rules.
- Do: design the dark scheme as the negative, not a dimmer copy.
- Do: leave space: asymmetric, with a lot of paper.
- Don't: soft shadows, blur, gradients for their own sake, rounded rectangles.
- Don't: extra colours, letters in pictures, grey on grey.
- Don't: filter posters or covers.

## Pokes (desktop, a mouse; nothing announces them)

- **The rail's foot:** click the module grid and it shuffles through ten arrangements of its
  sixteen quarters (the red one moving too) and stays on one at random: Gerstner's programme,
  a new permutation each click.
- **The deck's red module** (the red square hanging from the player's head band): click it and
  it runs through the programme (quarter, half, dot, quarter, half, square) and stays as one of
  those modules at random.
