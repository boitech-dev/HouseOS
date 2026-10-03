# Shōwa Platform · brief

- **Idea, one sentence:** a small local-line station in the 1960s, 4 p.m. in August: cream-and-navy
  enamel signs, one signal red, a towering summer cloud, cicada heat, a railcar now and then.
- **Names:** Shōwa Platform · Quai Shōwa
- **Schemes:** light (4 p.m. in August) and dark (**dusk**, 7 p.m.: the same station with an indigo-to-apricot
  sky, lamps lit, the drinks machine glowing, fireflies). Every picture has its dusk twin, drawn by the
  same code through one colour map (`DUSK` in px.py) plus the lamps.
- **References (from memory):** enamel station-name boards (navy rim, the line's band, arrows to
  the neighbouring stations); Edmondson card tickets and the gate clipper's notch; cream-over-red
  diesel railcars on rural lines; nyūdōgumo, the summer cumulonimbus; red fire buckets on the
  platform; wooden pendulum clocks and ticket racks in the stationmaster's office; drinks machines
  glowing at dusk; the kids' summer stamp rally (◎).

## Tells

1. **Enamel plates**: cream with a navy line inset from the edge, a lip lit top-left, a screw in
   each corner (every panel and sheet).
2. **The line's band**: each room is a station on the house's line: its title sits on a name board
   whose band is the room's line colour, the badge in the middle, arrows to its neighbours.
3. **Card tickets**: the Now bar is a pale green card with a printed border and the clipper's V
   notch; chips are square-cornered like tickets; sliders are strips of tickets (a perforation
   every 13 px).
4. **Summer light**: a big sky, a lit cloud tower, sunflowers turned to the sun, heat on concrete.
5. **Signal red, once**: primary buttons and progress are the only red (plus the line bands).
6. **Wood and steel**: clapboard wall (the rail), telegraph poles, rails and ballast, brass.

## Spec

- **Palette** (`docs/design/themes/showa-platform/px.py`, every picture locked to it): navy enamel
  (ink, frames, cool shadows) · cream enamel/concrete (grounds) · signal red (the accent) · summer
  sky + cumulus · greens · sunflower yellow/brass · wood · steel. UI grounds are the cream steps;
  text is navy ramp 12; the one accent is signal red `oklch(0.555 0.175 33)`.
- **One light**: the afternoon sun high on the left; highlights top-left, shadows bottom-right in
  cool blue-violet (`s1`, `s2`); clouds and trees shaded from one height field by the same vector.
- **Medium**: pixel art, drawn at 1× and shown at 2× everywhere (slots pre-scaled ×2, layers
  `scale: 2`, sprites 16 × 16 in 32 px boxes). Never mixed.
- **Type**: Dela Gothic One (heavy, wide Shōwa shop-sign gothic) for titles only; Barlow (a
  rounded grotesk from road and rail signage, reads at 14 px) for everything read; Overpass Mono
  (timetable figures) for numbers and times.
- **Shape**: small radii (2–6 px); pixel-rounded plate corners; hard 1–2 px lip shadows, never
  soft glows; tickets square.
- **Motion**: mechanical and crisp: entrances `steps(4)` like a flap board turning; exits smooth.
  Layers: a railcar crosses Home's picture every 75 s, a red dragonfly every 47 s, the furin sways
  only while music plays. Nothing moves at "still".

## The house, part by part

| Place | What it gets | Why |
|---|---|---|
| Sign-in | `crest.png`: the line's emblem, a winged wheel on a navy enamel badge | the first thing a guest sees is the line itself |
| Status bar | `status.png` (clear sky) over `status-sky.png` drifting under it at 12 px/s (five uneven clouds; far flat clouds stay on the hills); the train `train-far.png` crosses every 45 s, swallows every 25 s, pantograph on the wire; at dusk fireflies | the line runs along the top of every page |
| Rail | cream clapboard (`clapboard.png` texture), navy edge; foot: `vending-foot.png` (a rail-foot layer, so it can answer a click), the drinks machine glowing | the station house's wall |
| Dock | `dock.png`: the platform edge's yellow tactile strip over concrete | where you stand to board |
| Page | sunlit concrete, faint staggered paving (`slab.png`), no scrim | the platform |
| Headers | `banner` variant, a name board per room (`board-<room>.png`): navy rim, thick line band, a 28 px badge with the room's pictogram, arrows to the neighbours; no wash (`banner-wash` 0) | every room a station |
| Home | `hero.png`: the platform, the far track, paddies, sunflowers, the level crossing, the canopy with its hanging board and clock, the sleeping cat; layers: `bench-end.png` (the sleeping cat and the turning sunflower, 12 frames); fade 28 % | the cover picture: moment 1 |
| Listen | the deck is the station's PA box (`pa-box.png`: navy enamel, speaker grille, a red 'on' lamp); `furin.png` hangs from its top-right, clear of the menu, and sways only while music plays; ticket-strip sliders | moment 2 |
| Now bar | `ticket.png` 9-slice: a pale green card ticket with the clipper's notch | a ticket for what's playing |
| Watch | `tv.png`: the waiting-room TV (the railcar on its screen); posters untouched | |
| Games | covers untouched; the empty state's bench | |
| My Space | `office.png`: the stationmaster's office (ticket rack, pendulum clock, fan, phone, dating press, calendar, cap) | moment 3, the surprise |
| Me | 5 avatars (night moon, dusk bat, crow on the wire, rose, lantern ghost), 20 medals as station objects | the stamp rally |
| Control Room | the same plates and boards, nothing moving, navy board | calm and dense |
| Sheets, dialogs | the same enamel plate (`plate.png`), a navy edge | |
| Empty states | `empty.png`: an empty bench, a straw hat left on it, a dragonfly on the brim | a smile |
| Controls | cream enamel buttons with a lip; signal-red primary with an inset bevel; square slider thumbs; ticket-strip meters | |
| Nox | the station cat in a navy cap with a brass badge, 6 moods | |
| Rooms | a line colour each (`LINES` in px.py = `color.room.*`) | the house's line map |

## Art (all drawn by code, `docs/design/themes/showa-platform/make.py`; MIT; no text in any picture)

Every file is regenerated by `python3 docs/design/themes/showa-platform/make.py`, tokens and the
manifest's slots/layers by `tokens_make.py`, pieces (sprites.json) by the `sprites` job.

## Pokes (desktop, a click; nothing shows they're there)

| Click | What happens |
|---|---|
| The station cat asleep on the bench (Home's picture, right) | it opens its eyes, sits up, stretches with its tail up, yawns, and curls up again (`bench-end-wake.png`, 10 frames, 1.25 s) |
| The drinks machine at the rail's foot | a selection button lights, the sign flickers, clunk: a red can drops and waits in the tray (`vending-can.png`, 10 frames, 1.1 s) |
| The level crossing in the status bar (middle of the strip) | its two red lamps blink left-right twice, as when a train is coming (`crossing-blink.png`, 6 frames, 1.2 s) |

At dusk the cat and the machine have their own sheets (`*-dusk.png`); the crossing's lamps are the same red.
