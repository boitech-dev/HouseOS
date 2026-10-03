# Modular: notes

Regenerate everything: `python3 docs/design/themes/modular/tokens.py` (tokens.json,
tokens.light.json, tokens.dark.json) and `python3 docs/design/themes/modular/make.py --preview`
(every picture in `themes/modular/art/`, `sprites.json`, previews on both papers and a contact
sheet at `/tmp/modular-sheet.png`). `flavor.json` and `theme.json` are written by hand.

## What's in it

- **Type:** Jersey 15 for titles and the house's name (a heavy grotesk on a square grid),
  Schibsted Grotesk for reading, Space Mono for numbers. Labels in tracked caps.
- **Colour:** paper `#F2EFE8`, ink `#141312`; every other tone is a mix of the two. The accent is
  the ink (chosen chips, switches, slider and progress segments). Red is rare: the main button
  (`#CC2812` with paper words by day, `#FF4F2E` with black words by night), the playing meter,
  one module per picture. Rooms unified (ink). People: ink discs in eight steps of the ink.
- **Shape:** radius 0 on boxes, full circles for chips, people and thumbs; 1 px rules, no
  shadows; panels carry an ink module in the corner, sheets a black band with a red module;
  segmented choices get an ink box; quiet buttons on the page stand on a faint module tile.
- **Pictures (SVG):** Home hero (a street on a canal: day, and its own night), crest (day/night),
  My Space room (day/night), TV bezel (day/night), empty face (and its negative), the deck's
  9-slice poster frame (and its negative), 13 room emblems as banner running heads (one file:
  a paper contour under the ink draws them in line by night), rail foot (now a rail-foot layer that turns when clicked), the page grid; room banners
  with a night negative each.
- **Layers:** page grid drifting a module a minute; status ruler of tick dots with a red module
  that walks it every three minutes; the deck's red dot-matrix meter along its foot, only while
  music plays.
- **Pieces:** Nox (6 moods), avatars (moon, bat, raven, rose as module glyphs; ghost), 9 room
  marks (smart home a bulb), 20 medals; title names in a print studio's voice.

## Discoveries

1. **The house goes to night with the scheme:** the street's windows light up and ripple in the
   canal, the sun becomes the moon's dark side, stars come out; the crest and the room follow.
2. **By day the lit windows are already in the water**, paper on paper: invisible until night.
3. **The emblems redraw themselves in line by night** (a paper contour hidden under the ink).
4. **The grid drifts one module a minute.**
5. **A red module walks the status bar's ruler** every three minutes.
6. **The red module steps** to a new place in each room's emblem.
7. **Nox's blink** flips its square eyes edge-on; listening turns an ear red.
8. **The deck's meter** runs only while music plays.

## Pokes

- Rail foot (layer `rail-foot`, `rail-foot-shuffle.svg`, 10 distinct arrangements at 16 fps,
  `stay: random`): a quick shuffle that lands on a random arrangement, one red quarter in each.
- Deck corner (layer `deck`, `deck-module-flip(-dark).svg`, 6 frames at 10 fps, `stay: random`):
  quarter → half → dot → quarter → half → square, landing on one of them. Tested by a throwaway Playwright click
  script (frames at 60/150/250 ms, both schemes).

## Iterations

- **Round 2 (art director review):** hero v5 (street raised above the phone fade, reflections
  below, a real night picture, nothing cut at the edges); space room redrawn as a room; deck
  skin; red made rare (ink sliders); display face Doto → Jersey 15 (Doto was one dot wide at
  48 px); initials on ink; chosen segments boxed in ink; banner wash off, emblems 14 px down
  with night contours; four avatars and the bulb redrawn; status ruler and walker.

- **Hero:** v1 concentric quarter rings (read as a radio sign, too literal for Home) → v2 a
  modular street, day/night by the two inks (the idea found, but cartoonish and cropped at the
  top) → v3 a tighter street on a 50 px grid, weight top right, sun moved clear of the fade →
  v4 (kept) gutters between the houses so each block reads as a module, more sky, tower lowered
  so nothing is cut at the top.
- **Rail foot:** v1 a quarter-circle fragment with a floating red dot (read as a blob) → v2 a
  4 × 4 permutation of quarters (strong but too black beside the bold room marks) → v3 (kept)
  alternate cells as bare quarter rings, drawn as single paths so no hairline seams show.
- **Banners:** v1 72 px emblems at the right (collided with header buttons such as Watch's
  Sources) → v2 (kept) 64 × 48 running heads above the buttons; the home emblem redrawn twice
  (a gable read as the letter M, then a dome as n; now a dome with a chimney).
- **Deck meter:** at the deck's foot it sat behind the Stop button; moved to the top edge.

## Next

- An ink tile for empty covers once the placeholder has a token (REQUESTS.md 3).

## Known limits

- The rail's current room and settings page are ink blocks; other selected rows keep an ink tint.
- Banners are cropped to their quiet middle on phones: phones see no emblem.
- Quiet buttons on the page all get the faint tile (the token is page-wide).
- The tour's phone Control Room shots waited 10 s for `main h1, main h2` in one run (the page
  was fine; a later run passed clean).
