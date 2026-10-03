# Pure: notes

Architecture made of light. Dark: black concrete, white light, hairlines. Light: its negative,
cream paper and black ink, like the monograph that photographs the building.
Brief and house table: `themes/pure/BRIEF.md`. Direction: `DIRECTION.md`.

## Regenerate

```bash
python3 docs/design/themes/pure/tokens.py     # tokens.json + tokens.light.json
python3 docs/design/themes/pure/sprites.py    # sprites.json + flavor.json
python3 docs/design/themes/pure/make.py       # every picture (Blender renders, then finishing)
python3 docs/design/themes/pure/manifest.py   # theme.json (slots and layers of the art present)
```

Scenes: `scenes/concrete.py` holds the one light (a low warm sun through openings only), the one
concrete (mottle, pores, 1.8 × 0.9 m shuttering seams, 3 × 2 form-tie holes per panel) and the
opening screens (invisible to the camera: they only shape the sun). Contact sheets: `sheets/`.

## What's in it

- **Tokens:** no hue; #000 / near-black surfaces split by hairlines, warm white ink, the sun's
  cream as the one room light (rooms unified). Light scheme: cream #eee8db, ink, black primary
  buttons. Radius 0 (avatars round). Archivo Light display, Instrument Sans body, Fragment Mono
  numbers; labels in tracked capitals. Motion 90/120/140/200 ms, no bounce. Status colours sage,
  ochre, clay, slate.
- **Parts:** header banner, panels outlined, dock flush, Now bar docked; quiet buttons get a solid
  plaque over art; galleries sit on the plain ground.
- **Per scheme:** every picture has a night print and a paper print (see BRIEF: two prints).
- **Slots:** hero (sun blade across a cantilevered stair, with haze), page backdrop (béton wall and
  one square window's patch, strong scrim), header banners per room (each room its own opening:
  slits, slot, six squares, louvres, checker, oculus, a single line for the Control Room, a
  letterbox, a perforated screen, a lamp's square), crest (a square of light through a concrete
  block), empty state, rail foot (a slit at the end of a corridor), TV (a screen set deep in
  concrete), My Space (a small room, a window, sun on a bench), the music deck and the sheets (a drawing
  frame whose hairlines overshoot at the corners, a light line and an ink line).
- **Layers:** dust motes floating over the page (light over the black, ink over the paper), concrete grain (`above`,
  5 %), the roof slit (status), a seam of light down the rail's edge, dust turning in the hero's
  blade (dark only), sun blades walking across the music deck while music plays.
- **Pieces:** Nox as a square of light with its cast shadow (6 moods; error dims the light),
  5 avatars (a square rose spiral, a stepped bat, a ghost of squares...), 9 room marks as openings,
  5 transport keys, 20 medals as plaques; title names for light, stairs and concrete; ■ as the star.

## Round 2 (after review)

- The negative selection is the tell: `bg.current`/`fg.current` make the rail's room and the
  settings page solid blocks; `bg.selected` raised to a clear step.
- Every picture has its own paper print: daylight renders (no bounce, crisp sun, denoised) for
  the hero, the rail foot and My Space; ink drawings of the light for the page, the banners and
  the empty state (no more grey polka dots or blurred halos).
- Banners: the patches moved to 60 % of the width and 16–72 px from the top (a phone crop holds
  them, clear of the words), half the mottle, a few crisp tie holes where the light falls.
- The sun window that crossed the house (three big panes) is gone: it read as moving boxes. Dust
  motes float over the page instead, in both schemes.
- Crest: a night render that throws its square of light, a day render with one ink void.
- People without hue; success desaturated. Room marks redrawn as each room's opening, thin, with
  a ground-coloured shadow; medals as geometric marks (no key, basket or envelope).
- One poke: the rail foot's cloud. By day it now softens toward paper white (not a
  black dim), and the paper print fades into the page with no visible box.

## Discoveries

1. Dust turns slowly over the page: specks of light over the black, specks of ink over the
   paper (its negative).
2. The empty state's patch of sun has a small bird's shadow on its edge: someone sits in the
   window, out of sight.
3. Each room has its own opening in its header: the Control Room's is a single line of light.
4. Pictures are split into light and shadow, so each scheme prints the same negative: the dark
   hero is only the blade of sun; the light hero is the whole stair in daylight.
5. While music plays, sun blades walk across the deck; stop the music and the light holds still.
6. The roof slit: a hairline of light along the top of the house, brightest where the sun is.
8. Dust turns in the hero's blade of sun, at night only.
9. Touch the slit at the rail's foot: a cloud passes over the sun.
7. Nox casts a shadow to the lower right, the same way as every render's sun.

## Iterations (hero)

1. Blade in the middle of the frame, stair lost in black: the fade on wide screens ate it.
2. Camera moved so the blade sits at two thirds and the left stays quiet wall; the low tones
   lifted (light gamma 0.85) so the stair reads in the dark print.
3. Haze near the wall so the blade glows in the air; a floor on the light alpha removes the grey
   veil that showed as an edge in the hero box. Kept: the best balance of drama (dark) and a
   complete, calm photograph (light).
4. Round 2: the paper print got its own render (no haze, no bounced light, a crisper sun, a
   bright sky, 512 samples, denoised): the stair's shadows are the sun's, crisp, no smudge.
Crest: a flat lit tile (1), a lit window in a mid-grey block (2), a darker block with a long lens
(3), then two renders (4, kept): at night the opening glows and throws its square of light on the
floor; by day a cream block, one ink void, its shadow.
Rail foot: a white needle (1), an aquatint (2), then a night print and a clean daylight plate,
with a cloud to pass over it (3, kept).

## Next

- A poke on the hero's blade (REQUESTS 2).
- Posters and covers are untouched by design; a Watch "screening room" banner could come later.

## Known limits

- Night prints show the wall only where light falls (on purpose).
- The rail foot's cloud is its only poke; the hero's blade inversion waits for REQUESTS 2.
- Room marks are pixel squares at 2 px strokes, heavier than the 1.25 px line icons beside them.
- The crossing sun and the deck blades are not in the tour's screenshots (they wait or need music).
- Hero dust motes drift over the whole hero, words included (few, small, 60 %).
