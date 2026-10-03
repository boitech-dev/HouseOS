# Legacy (id carved-night) · brief

The house default: the first thing a new house sees. HouseOS's first home, now fully haunted.

- **Idea, in one sentence:** a moonlit Victorian manor on a hill, carved in stone, lit by candles
  and embers, where friendly ghosts keep house: cold blue night outside, warm rooms inside.
- **Names:** Legacy · Legacy.
- **Scheme:** dark only.
- **Three moments:** Home's hero (the manor under a huge moon, Nox on the fence), Listen (the
  parlour's gramophone above the player dressed as a walnut wireless cabinet, its candle
  burning while music plays), the night behind every page (moon, drifting cloud, the manor on
  its hill with a ghost slipping out of the tower, the owl on the near fence, a bat).

## Tells

1. A manor silhouette with lit windows against a huge, cratered moon; a gnarled tree across it.
2. Wrought iron: spear-headed fence bars, iron studs on every panel's corners.
3. Carved stone: 1 px bevels (moonlit top-left, cut shadow bottom-right), cut corners, no radii.
4. Candlelight as the only warm light: windows, sconces, the candle at the rail's foot; it is also the accent.
5. Rooms of the house as banners: parlour, screening room, kitchen hearth, library, attic,
   cellar, bedroom, hall; damask wallpaper, dado rails, plank floors.
6. Pixel lettering: Jacquard 12 for titles only, at multiples of 12 px.
7. Life at the edges: fog, drifting cloud, a bat crossing, a shooting star, embers rising.

## Spec

- **Palette** (make.py `PAL`, locked on every picture): night (12 steps, violet-blue, shadows
  toward indigo), moon (cream to lilac), ember/candle (8 steps), wood, velvet, gas green, brass,
  ghost (pale blue), lilac, and a warm-night ramp for candlelight falling on dark walls.
  Ground `#0a0b1c`, surfaces `#11132b`/`#1a1d3c`, text cream `#efe7d6`, the one accent candle
  `#f2b45e`. Rooms are lamps in the same night: candle-cream Home, velvet-rose Listen,
  projector-blue Watch, gas-green House, brass Files, tin-toy teal Games, ghost-violet Ask,
  orchid Me, cellar-steel Control.
- **One light:** the moon, high on the left, cool; every picture's left edges are lit. Warm
  light only from flames, pooling on walls through the warm ramp.
- **Medium:** pixel art on one 3× grid. Slot pictures are drawn at native size and exported ×3;
  layers ship at native size with `"scale": 3`. Sprites are 16 × 16 grids in sprite tokens.
- **Type:** Jacquard 12 (display, 24/36/48), Alegreya Sans (body; bold labels), IBM Plex Mono.
- **Shape:** radius 0 everywhere, cut corners on surfaces, bevelled buttons (a gradient over the
  colour), segmented pixel meters, a square cream slider handle.
- **Motion:** candle-slow (200/320/560 ms). Ambient: clouds drift, a bat crosses the
  pages every ~61 s, a shooting star crosses Home every ~83 s, the candle at the rail's foot
  flickers in place, the roofline cat flicks its tail and two chimneys smoke, the sconces
  flicker in every room, the ancestor blinks, the deck's candle burns while music plays, the
  page manor's 32-frame loop (a ghost leaves the tower window). Still: first frames only.

## The house, part by part

| Place | Gets | Why |
|---|---|---|
| Status bar | `status.backdrop`: one long roofline (wing, turret cone, cresting, four chimneys with pots, lit dormers, far gable, weathervane, a cat); status layer: the cat's tail flick, chimney smoke | the manor's roof over every page |
| Rail | `rail.surface` stone column (9-slice); rail-foot layer: a little carved side table on the floorboards (a brass candlestick and its candle, two books, a teacup), just above Ask Nox, fitted to any screen | a carved pillar lit at its foot |
| Dock | tokens only (night bar, stone edge) | phones stay calm; the marks carry the theme |
| Page | `page.backdrop` sky with the moon high on the left; layers: drifting cloud, the manor on its hill (32 frames), the near garden (tree, fence, owl; parallax 0.12), a bat; scrim 64 %; `part.page.gallery` grounds lists | the night outside every room, dimmed under the content |
| Headers | `banner` variant, a room of the manor per room; subjects in the top 36 rows, the right quarter a quiet wall (two steps darker); header layers: two flickering sconces (all rooms), the blinking ancestor (Ask, My Space, Listen, Party, Files), a ghost behind the bedroom curtain (Me) | each room is a room of the house |
| Home | `home.hero.backdrop` manor + moon; hero layers: shooting star, the owl on its post at the picture's corner | the cover picture |
| Listen | parlour banner; `deck.surface` a walnut wireless cabinet (9-slice, brass corners, a candle in its pan); deck layer: the candle's flame while playing | the gramophone moment |
| Watch | screening-room banner; `watch.tv.bezel` a carved cabinet TV with a waving ghost; posters untouched | cinema in the manor |
| Games | attic banner (trunk, the manor as a dollhouse, rocking horse, toys) | the attic toys |
| My Space | `space.room.scene` a manor bedroom (a ghost peeks from under the cover); hall banner | your room in the house |
| Me | bedroom banner; five avatars, 20 medals, titles in `flavor.json` | the house's people and their keepsakes |
| Control Room | cellar banner kept calm (wine racks, barrels, gauges, the boiler) | recognisably the house, quiet |
| Sign-in | `auth.crest`: a symmetric brass escutcheon, the full moon through the keyhole | the door of the house |
| Panels / sheets / Now bar | 9-slice frames: carved groove + iron studs, moulding + brass brackets, groove + brass scrolls | stone, iron, brass |
| Empty states | `state.empty`: a friendly waving ghost | a smile in an empty room |
| Controls | bevelled gradients, candle primary, segmented meters, square thumb | carved and pixel |
| Nox | the black cat of the house: 6 moods, idle + blink | the familiar |
| Rooms | distinct lamps (`rooms: distinct`) | lamps in the same night |

## Pokes (desktop, a click; never at motion "still")

| Click | What happens |
|---|---|
| The candle on the side table at the rail's foot | it flares with a few sparks, gutters to a bead, goes out in a curl of smoke, relights |
| The owl on its post, bottom right of Home's picture | its eyes go wide, its head turns right round and back, it hoots; a few feathers drift off |
| The roofline cat (anywhere in the status bar's free space) | its eyes go wide, it gets up, arches its back, stretches long and sits down; the chimneys puff |
| The candle on the music player's bottom rail | it flares, gutters, goes out in a curl of smoke and relights |
| The ancestor's portrait (Listen, Files, My Space, Ask; its lower half, under the title's line) | it rolls its eyes up and round, then winks |
| The bedroom curtain (Me, the header's empty width by the window) | the ghost pops out, startled, ducks back behind it, the curtain swings |

## Do / Don't

- Do: keep text on quiet ground (objects to the right, dimmed behind buttons); candlelight = the accent.
- Do: keep real posters and covers in their own colours.
- Don't: gore, jump scares, flashing; mixed pixel sizes; words in pictures; crimson-and-gold action looks.

Art sources: `docs/design/themes/carved-night/` (make.py, pieces.py, tokens.py, manifest.py),
all drawn by code, MIT.
