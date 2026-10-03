# Pocket Hatchling · brief

**Idea, in one sentence:** the house is a 90s keychain pet living on its own handmade personal
homepage: tiled checks, lace, stickers, web buttons and a reflective LCD, held together by plum
ink outlines and calm cream cards.

- **Names:** Pocket Hatchling · Éclosion de poche
- **Scheme:** light only (the page tile, the sky and the stickers are daylight art; layers cannot
  change per scheme, so a night scheme would still show a lavender page).
- **Pet:** Pip, a lemon hatchling still sitting in the bottom of its cracked eggshell, a sprout
  on its head. Pip is Nox, lives on every LCD, hops across the status bar and sleeps in empty
  states.

## Tells

1. **The egg device:** candy-pink pearly plastic with glitter flecks, a lavender face plate with
   care pictograms printed round a recessed grey-green LCD, three rubber buttons (lemon, berry,
   mint), a sprout on top, a ball chain and a heart charm.
2. **The LCD:** grey-green face, dark segment pixels, a faint ghost grid, 1-bit Pip.
3. **The homepage:** a tiled lavender check with hearts and twinkles; a lace trim and pennant
   garland; candy-shop awnings over each room; 88 × 31-style web buttons (pictogram + pattern,
   never words); a shooting star with candy stripes.
4. **Kawaii rules:** round faces, wide-set dot eyes, pink blush, a consistent plum outline on
   every drawing and every card.
5. **Stickers:** die-cut white border + plum outline (every medal, the charms, the hero's
   stickers, a heart peeling in the corner of every sheet).
6. **Rubber buttons:** white gloss buttons with a hard plum bottom edge; the berry primary
   carries a round shine dot top left.
7. **Sticker sheet:** the rail is mint backing with a printed dot grid and a stitched edge.

## Spec

- **Palette** (`docs/design/themes/pocket-hatchling/pal.py`, every picture locked to it):
  bubblegum (#b03a78 → #ffe6f1), mint (#2d8c79 → #dcf8ec), lavender (#6653ad → #f2edfe),
  lemon (#c4880f → #fff5c6), baby blue (#3c74b8 → #ddeefe), LCD (#27311f → #cbd6ad); plum ink
  #2b1638 for outlines and text; **one accent: berry #bd1860** for primary actions, focus and
  progress. Page lavender #efe8fd, cards cream #fffaf4.
- **Light:** top left, white-ish; highlight rims top left, shadow rims bottom right, in the
  material's own darker ramp (never grey). Hard offset shadows in plum (sticker drop).
- **Medium:** pixel art on one 2 × grid (slots saved at 2 ×, layers drawn at 1 × with scale 2).
  Strips and banners are drawn wider than any screen so `cover` shows them at exactly 1 : 1.
- **Type:** DynaPuff 600 (puffy, round, legible) for display and the brand; Nunito 400–800
  (rounded, reads at 14 px) for everything read; Pixelify Sans for times and counts (LCD
  counters).
- **Shape:** 1 px plum edges everywhere, radius 10 on cards (the gallery outline clips corners
  above that, see REQUESTS.md), 14 on controls, pills for chips, 24 on sheets.
- **Motion:** quick and bouncy (110–380 ms, overshoot on enter). Ambient: the page tile drifts
  slowly; everything else moves rarely or only while music plays.

## The house

| Place | What it gets | Why |
|---|---|---|
| Sign-in | `auth.crest`: the egg device with Pip awake, ball chain and heart charm, a star sticker | the first thing a guest sees is the pet |
| Status bar | pink bar, strip: heart garland on top, lace hem below; now and then Pip rides the garland like a zip line | a homepage header; a peek of the pet |
| Rail | mint sticker-sheet backing, printed dot grid (`dots.svg`), stitched dashed edge; selected door a pink pill; foot: a shrine of six web buttons on a lace board with the egg on its chain (a rail-foot layer) | sticker sheet + 88 × 31 wall, calm behind the names |
| Dock | floating pink plastic with glitter, plum edge; Ask's plate holds Pip | the device's button row |
| Page | soft lavender check tile (layer, drifts), 16 twinkling sparkles and 6 rising hearts, scrim 40 %; the Control Room keeps a plain ground | the homepage background, calm enough for text |
| Headers | `banner` variant, `banner-wash` 0: a homepage band per room (hearts, staff and notes, stars and moons, game pads, checkerboard, folders, airmail, bows, clouds, bulbs, rainbow and gifts, construction stripes, speech bubbles), ending 8 px+ above the title | a different tiled band per room |
| Home | hero: rainbow over a cloud floor, stickers, hearts, a webring of web buttons (picture, clear sky) + a dithered sky layer under it + the egg resting bottom right on a puffy cloud (16 frames: Pip blinks; naps: the egg sways, the LCD dims, a bubble swells) | moment 1 |
| Listen | the deck is the egg: `deck.surface` 9-slice pearly shell with glitter, face-plate ring, LCD recess and rubber buttons; a sprout on top that wiggles, candy hearts and Pip dancing on the shell's corner, only while music plays | moment 2 |
| Now bar | a mini LCD in a pink plastic ring (shadow rings) | the device, everywhere |
| Watch | posters on pink gallery grounds (never filtered); `watch.tv.bezel`: a lavender toy TV with Pip on its screen | |
| Games | the empty state: Pip asleep; mint awning with controllers | |
| My Space | Pip's room: heart wallpaper, bunting, window, eggshell bed, shelf of treasures, rug | |
| Me | 5 kawaii avatars; 20 die-cut sticker medals and their title names | |
| Control Room | plain lavender ground (no tile), pink gallery, a lavender awning with cogs; no motion | calm, still this theme |
| Sheets & dialogs | cream with glitter, plum edge, a heart sticker peeling in the bottom-right corner | discovery |
| Empty states | Pip asleep in its shell on a cloud pillow, a bubble, the moon | a smile |
| Panels | 9-slice: pink pinstripe, dotted lace fans in the corners, a heart stuck top left | homepage boxes |
| Controls | white gloss rubber buttons with a hard plum edge; berry primary with a shine dot; sliders filled with candy construction stripes | rubber buttons |
| Nox | Pip, 6 moods | |
| Rooms | a candy colour per room | |

## Pokes (desktop, with a mouse; never at motion "still")

| Click | What happens |
|---|---|
| The egg resting on its cloud, Home's hero (bottom right) | it hops twice, Pip beams on the screen, eight candy hearts burst out |
| The star sticker in the hero's sky (top right) | it turns round like a coin, sparkles fly |
| The shrine at the rail's foot | the six web buttons blink one after another round the ring, the egg sways on its chain |
| The sprout on the deck's shell (top middle) | it springs up and flops back, leaves fly |
| Pip on the deck's bottom-right corner (Listen; the part on the shell) | a jump and a twirl, notes fly |

## Art: sources and credits

All pictures and pieces are original, drawn by code in `docs/design/themes/pocket-hatchling/`
(`make.py` regenerates every picture; `sprites_src.py` holds the pieces; `tokens_src.py` writes
tokens.json; `manifest.py` writes theme.json, sprites.json and flavor.json). No real toy's shell,
character, logo or name; no words in any picture. Fonts: DynaPuff, Nunito, Pixelify Sans (SIL
OFL 1.1 via Fontsource, licences in `fonts/`). MIT.
