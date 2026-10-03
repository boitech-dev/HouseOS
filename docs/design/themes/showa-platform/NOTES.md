# Shōwa Platform: notes

The theme's brief (idea, tells, spec, the house table) is `themes/showa-platform/BRIEF.md`.

## How to rebuild

```bash
python3 docs/design/themes/showa-platform/make.py            # every picture + sprites.json
python3 docs/design/themes/showa-platform/make.py hero boards # only some jobs
python3 docs/design/themes/showa-platform/tokens_make.py     # tokens.json, theme.json slots/layers/parts
```

Files: `px.py` (the palette, the line colours, the pixel kit, cloud shading from one height
field and one light), `scenes.py` (hero, status strip, far train, railcar, office), `pieces.py`
(dragonfly, furin, name boards, vending machine, crest, empty bench, TV, frames, textures),
`sprites.py` (Nox, avatars, room marks, transport, medals). `iterations/` keeps the hero's four
passes.

## What's in it

- **Home hero** (720 × 256, 2×): the platform at 4 p.m., the far track on its embankment,
  paddies, a farmhouse, sunflowers turned to the sun, a level crossing, telegraph poles, a
  cumulonimbus tower lit from the left, the canopy with its hanging name board and clock, red fire
  buckets, a bench with the station cat asleep and its cap beside it.
- **Status strip**: sky, far hills, catenary masts and wires, a crossing, sunflowers, one crow.
- **Name boards**: one per room (12), the room's line colour as the band, a badge with the room's
  pictogram, arrows to the neighbouring stations, screws, one enamel chip.
- **Plates**: every panel and sheet is a 9-slice enamel plate (navy inset line, lip, screws).
- **Ticket**: the Now bar is a 9-slice card ticket with the clipper's notch.
- **Dock**: the platform's yellow tactile strip. **Rail**: clapboard wall, the glowing drinks
  machine at its foot.
- **Crest** (winged wheel), **empty state** (bench, straw hat, dragonfly), **TV** (the railcar on
  its screen), **My Space** (the stationmaster's office).
- **Layers**: the railcar crossing Home's picture on the far track, a red dragonfly along its top,
  the furin at the player's corner (sways only while music plays).
- **Pieces**: Nox as the station cat in a cap with a brass badge (6 moods), 5 avatars, 9 room
  marks, 5 enamel transport keys, 20 medals as station objects, 20 title names (en/fr).

## Iterations (hero)

1. v1: one big round cloud made of balls, catenary masts crowding the sky, the board standing in
   front of the track. A layer train would have crossed over the board and the posts.
2. v2: the board moved up under the canopy (hanging, as on real platforms), a far track added for
   the railcar so nothing in front of it is ever crossed, telegraph poles instead of masts.
3. v3: the cloud shaded from one smoothed height field (lobes merge, one light), not per ball.
4. v4 (kept): tighter dithering so the clusters read clean; the best balance of calm sky where
   the fade meets the words and detail on the right.

## Round 2 (after review)

- The status train now runs (the platform fixed status layers), under a slowly drifting sky.
- The music deck is the station's PA box; the furin is bigger, its paper strip visible.
- Name boards redrawn: thick band, navy rim, 28 px colour badges, clear arrows; no banner wash.
- Hero: heat haze, the turning sunflower, a readable cat, fade 28 %. Nox moods each have a sign.
- Ticket notch moved to the right end; plate screws are 3 × 3 and slotted, a heavier lip.
- Selected door and Ask card on a warm cream step (no salmon).
- A second scheme, **dusk** (`dusk_tokens.py`, `*-dusk.png`).

## Round 3: pokes (desktop clicks)

- The sleeping cat (Home's picture, on the bench) wakes, sits, stretches, yawns, curls up again.
- The drinks machine (rail foot) takes a click: button, flicker, clunk, a can in the tray.
- The level crossing (status bar, middle) blinks its lamps twice.
- To fit the 12-layer budget: the cat left hero.png for a `bench-end` piece with the sunflower;
  the machine left the rail.art slot for a `rail-foot` layer; the hero's railcar went (the status
  train now crosses every page) and the heat haze went (it was barely visible).
- The furin can't take a click: in the deck, the player's rows lie over it (the layer box is the
  deck's inner box, not its frame). It still sways only while music plays.

## Round 4: a livelier day strip

- The near sky drifts at 12 px/s (dusk 6), far flat clouds rest on the hills (they stay: two depths).
- Swallows cross the strip every 25 s (both schemes); the train every 45 s. The hero's dragonfly
  gave its layer to the swallows.
- The vending machine at the rail's foot: 1× on a 1366 × 768 laptop (the platform steps it down
  by whole scales), 2× on 1920 × 1080.

## Discoveries

1. The train: every 70 s the cream-and-red local crosses the status strip, pantograph on the wire.
2. A red dragonfly skims the top of the picture every 47 s.
3. The furin only sways while music plays.
4. The station cat asleep on the bench in the hero, its cap beside it.
5. A crow on the telegraph wire; swallows in the sky; a crow on the status bar's wire.
6. The waiting-room TV shows the same railcar; the stationmaster's calendar has one day crossed
   in red; the ticket rack has an empty pigeonhole or two.
7. An enamel chip beside a screw on every name board.

## What I'd do next

- A bat crossing at dusk (the layer budget is 12; the dragonfly flies in both schemes).

## Known limits

- The furin stays 16 px wide so it keeps clear of the player's menu.
- On phones the turning sunflower stands at the hero card's bottom-right corner, beside the send key.
- Header boards are the same in both schemes (a room's picture wins over a scheme's), so they are
  drawn clear below the band.
- On phones the railcar crosses the hero card low, between the Ask row and its buttons.
- `space` has a plain board (no band) so it never covers the office picture above the title.
