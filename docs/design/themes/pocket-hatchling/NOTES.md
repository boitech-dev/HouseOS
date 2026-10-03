# Pocket Hatchling: notes

Rebuild everything: `python3 textures.py && python3 make.py && python3 tokens_src.py && python3 manifest.py`
(from this folder), then `theme_kit check pocket-hatchling` and the build. `python3 preview.py out.png`
draws every piece at 8 ×; `contact-sheet.png` and `pieces.png` are the last sheets.

## What's in it

- **Words:** DynaPuff titles, Nunito text, Pixelify Sans numbers; 20 title names en/fr
  (sticker-book voice, ≤ 28), ♥ as the star mark.
- **Frame:** pink status bar with a garland and lace; mint sticker-sheet rail (dot grid, stitched
  edge, a web-button shrine with the egg at its foot); floating pink glitter dock; Now bar as a
  mini LCD in a pink plastic ring; a candy awning over every room's title (13 variants).
- **Page:** lavender check tile with hearts and twinkles, drifting; cream cards with plum edges
  and hard plum drops; pink gallery grounds; lemon wall notes tilted 1.4°.
- **Controls:** white gloss rubber buttons, berry primary with a shine dot, LCD-segment sliders.
- **Pictures:** crest (the egg), hero (rainbow, clouds, stickers, sky layer, egg layer), Pip's
  room, toy TV, Pip asleep, shrine, sheet-corner sticker, status strip, awnings.
- **Pieces:** Pip in 6 moods, 5 avatars (moon, bat, raven, rose, ghost), 20 die-cut sticker
  medals, 9 LCD-toy room marks, 5 rubber keys.

## The three moments

1. **Home's hero:** the pet's world; Pip on the egg's screen blinks, and every 8 s nods off and
   blows a bubble.
2. **The music deck:** the player is the LCD set in the pink shell; while music plays hearts
   float up the screen and Pip dances in the corner beside Stop.
3. **The frame itself:** status garland, awnings and the web-button shrine.

## Discoveries

- Pip blinks and falls asleep on the hero's egg (frames).
- Once in a while Pip hops across the status bar, peeking between the garland and the lace.
- A shooting star with candy stripes crosses the top margin of the page every 70 s.
- Hearts and the dancing Pip appear only while music plays.
- Every sheet and dialog has a heart sticker stuck in its bottom-right corner, peeling.
- The Control Room keeps a plain ground and no motion.

## Pokes (desktop, with a mouse; never at motion "still")

| Click | What happens |
|---|---|
| The egg resting on its cloud, Home's hero (bottom right) | it hops twice, Pip beams on the screen, eight candy hearts burst out |
| The star sticker in the hero's sky (top right) | it turns round like a coin, sparkles fly |
| The shrine at the rail's foot | the six web buttons blink one after another round the ring, the egg sways on its chain |
| The sprout on the deck's shell (top middle) | it springs up and flops back, leaves fly |
| Pip on the deck's bottom-right corner (Listen; the part on the shell) | a jump and a twirl, notes fly |

## Round 2 (after review)

- Hero: sky under the picture; the egg now rests bottom right on a puffy cloud with no inner
  lines; while napping the egg sways, its LCD dims and a bubble swells outside the shell; a
  webring of web buttons, more hearts and sparkles; a bigger rainbow.
- Banners: each room its own homepage band (hearts; staff and notes; stars and moons on night
  blue; game pads and hearts; checkerboard; folders; airmail with envelopes; bows; clouds; bulbs;
  rainbow with gifts; candy construction stripes for the Control Room; speech bubbles), 12 art
  px tall, ending 8 px or more above the title. `banner-wash` 0.
- The deck is the egg: a 9-slice pearly shell (glitter corners, gloss, face-plate ring, bevelled
  LCD recess, three rubber buttons), a sprout on top that wiggles while music plays, Pip
  climbing out onto the bottom-right corner to dance, candy hearts floating.
- Page: calmer tile, scrim 40 %, 16 twinkling sparkles and 6 rising hearts (not in the Control
  Room).
- Cards: a 9-slice with a pinstripe, dotted lace fans in the corners and a heart stuck top left.
  Sliders fill with candy construction stripes. Web buttons also in the hero and My Space.
- Status: Pip rides the garland like a zip line (over the strip now).
- Nox: listening has a note, thinking a thought bubble, happy hops with hearts. Medals redrawn:
  task hero (a caped star), marathon (a stopwatch), genre guardian (a heart shield), romhacker
  (a cartridge and a screwdriver).
- Not done: the night scheme (optional). It needs its own tile, sky, hero and glowing LCD to
  be excellent; left for a later round rather than shipped half made.

## Iterations (hero pieces)

- **Crest:** v1 bare egg with a knob (read as a copy of a real toy); v2 printed care
  pictograms, sprout, chain (buttons came out as diamonds, chain across the shell); v3 hand-drawn
  round buttons, the chain outside the silhouette with a heart charm, a star sticker: kept, it
  reads as *this* pet's device.
- **Hero:** v1 sky + rainbow + flat cloud band (clip-art clouds); v2 ringed puff clouds with a
  lavender back row (volume); v3 clear sky with the sky as a layer so the animated egg shows,
  rainbow moved left so it never crosses the egg: kept.
- **Empty state:** v1 16 px Pip (too small in 96 px); v2 a large sleeping Pip drawn for the
  slot: kept.
- **Banners:** v1 thin awnings with hanging sticker charms (charms met header buttons and long
  titles at some widths); v2 bolder awnings only, clear of the status bar and the title: kept.
- **Rail:** v1 a sticker-sheet picture with peeled-sticker ghosts (the ghosts read as spinners,
  and a rail picture forces a faint selected state); v2 mint + printed dots by texture: kept.

## Next

- A night scheme only if layers could differ per scheme (the tile and sky are daylight).
- More per-room hero-style scenes (a room picture per banner) if the header got room.
- A tiny Pip reaction in the deck when a song is skipped (needs an event the theme can see).

## Known limits

- Phones: the resting egg sits behind the ask row's mic and send buttons (bottom-right anchor); Pip on the garland is only glimpsed between the status pills.
- Hero backdrop and slots scaled by `cover` are not at whole-number scales on every width
  (the strips and banners are: drawn wider than any screen).
- Cards are radius 10, not rounder, because of the gallery outline (REQUESTS.md 1).
- Light scheme only.
