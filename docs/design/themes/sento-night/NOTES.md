# Bathhouse After Hours (sento-night): notes

Regenerate every picture and piece: `python3 docs/design/themes/sento-night/make.py`
(one piece: `make.py hero`, `make.py banners`, `make.py sprites`…). `pieces.py` holds the pixel
pieces (sprites.json). One palette (`PAL`), locked on every picture; one light (lamps up left);
one density (an art pixel is 4 screen pixels on a desktop).

## What's in it

- **Page:** the Fuji mural up close (penki-e on big wall tiles, a faint grout grid), the mosaic wall
  and the bath below; vapour drifting and puffs rising over it, under a 78 % scrim.
- **Status bar:** a hinoki lintel over the wave-scale tile; the vermilion noren (♨ on the middle
  panel) sways in six frames; the calico trots past under it every 95 s.
- **Home hero:** the bathing hall in one-point perspective: the mural in its frame, the tub and its
  water, taps and mirrors down the left wall, stools and yellow basins on the wet tile floor, the
  pendant lamp, the cat asleep on the rim. Layers: drawn wisps of steam drifting under the ceiling
  (over the sun), a drop falling through the hall every 23 s.
- **Headers:** a tiled wall under a picture rail; each room its own corner of the bathhouse (13
  scenes), placed past the lead text and above the header's buttons, outside a phone's view.
- **Rail:** dim hinoki lockers with plank keys (one missing); at its foot the milk fridge on a bench
  with the cat asleep on top. **Dock:** the shoe lockers by the door.
- **Music deck:** the counter radio: a wooden 9-slice case with brass corners, a backlit dial
  window in its top edge whose vermilion needle drifts while music plays.
- **Now bar:** vermilion lacquer with a dark brass rim. **Sheets:** a noren's hem on top, faint wet
  tile grout, square corners.
- **Controls:** glazed tile buttons, a vermilion lacquer main button, tile-segmented sliders and
  progress bars with a milk-cream square thumb.
- **Pieces:** Nox as a milk bottle in six moods; five night-bath avatars; nine room marks; transport
  keys in milk cream; twenty sentō medals and their names (en/fr).
- **Slots:** the ♨ crest in a tile medallion, an empty basin smiling, the changing-room TV, the
  changing room for My Space.

## Round 2 (the review asked for more detail where the house is seen most)

- **The noren** is now a header layer, 48 × 24 art px, eight frames: a bamboo rod, three split
  panels with sleeves, two soft folds each (light and dark), a shaded hem, each panel swinging out
  of step, and the ♨ redrawn as an open bowl under three S lines. It hangs past the room's words
  (the piece carries 140 px of air on its left, so on a phone it is out of view) in the rooms
  whose header has no buttons. The status bar keeps the lintel and the cat.
- **13 composed header corners** (banners.py): each stands on a counter, a shelf or the hinoki
  wainscot, a main object 20–32 px tall, two or three props, and the pool of its pendant lamp. A
  frieze runs along every banner's top 8 rows (tile band, picture rail, things on the ledge,
  wind chimes): the part a phone shows above the title.
- **The radio deck**: rounded case, grain along each side, louvred speaker band and a knob in
  each bottom corner; a dark-glass dial backlit amber with two tick rows and a long needle; a
  wisp of warmth off its top corner while music plays.
- **The hero**, rebuilt with the vanishing point on the left: the wall of mirrors and taps (hot
  and cold) is on the right where a desktop sees it, Fuji right of centre, a thick lit rim, water
  that reflects the mural, a towel and a pail on the rim, bigger stools and basins, a basin
  pyramid, one pendant lamp and its pool. Cream steam curls drift below the peak; under the
  picture, the hall's dark tile continues (a layer), so a phone's greeting sits on the bathhouse
  wall, not on the mural's big pixels.
- **Rail**: smaller, more numerous lockers with grain, vents, brass plates and plank keys on
  strings (one lock empty); the fridge's glow hums (a layer); the cat sleeps on the rail's floor
  by the fold button, flicking its tail now and then.
- **My Space**: your locker door swung open with the red towel over its edge, a folded crane,
  the coin massage chair (headrest, control box, footrest), a bench in front, the lamp's pool.
- **Vapour** is a pale mist in three large soft clusters at 0.3. **Crest**: the new ♨.

## Round 3: pokes (desktop, a mouse; click the thing, nothing tells you it's there)

| Where | Click | What happens |
|---|---|---|
| Rail foot, left | the milk fridge | its glass door swings open, a bottle clinks, a few paper caps pop out, it closes |
| Rail foot, right | the cat asleep on the bench | it wakes, stretches with its rear in the air, sits up for a big yawn, curls up again |
| Header (rooms without buttons) | the noren | it parts as if someone walked through: side panels pushed apart, the middle one lifted, then swinging back |
| Listen / Home deck | the radio's dial | the needle swings across the band and back, a few little notes fly out |
| Home hero, top right | the steam under the ceiling | it billows, and condensation drops scatter |

The fridge and the cat moved from rail.art into two `rail-foot` pieces (the fridge anchored
bottom-left, the cat on its bench bottom-right), so they stay put above Ask Nox on any screen
and their boxes never overlap (each takes its own clicks). The status bar's cat, the page's
steam and the hero's drop stay ambient.

## Discoveries

1. The bathhouse cat: asleep on its bench by the milk fridge at the rail's foot, flicking its
   tail (click it), asleep on the tub's rim
   (hero), on the fridge in the House header, trotting under the lintel now and then (status
   bar), and painted, tiny, on the mural's rocky point (hero).
2. The fridge has one bottle missing on its lowest shelf: Nox is that bottle.
3. A drop gathers under the steamy ceiling and falls through the hall; in the picture, one is
   caught mid-air over its ring on the water.
4. One locker key is out on the rail: someone is still in the bath. Yours is the open locker with
   the red towel in My Space, a paper crane folded from a receipt on top.
5. The radio's needle only wanders while music plays.
6. A summer wind chime hangs from the picture rail in rooms without their own corner.

## Iterations (hero)

1. A flat elevation: sky, mountain, sea, then a band of tile and stools. Convex mountain, noisy
   dithered sky, a muddle at the bottom: rejected.
2. One-point perspective: a framed mural on the back wall, the tub, side walls, a floor. Read as a
   place for the first time; floor grid too fine, steam as noise.
3. Perspective floor with real tile sizes, flat sky bands dithered only where they meet, a proper
   concave Fuji with snow ridges, sprite pines.
4. Steam as drawn wisps instead of dither, a calmer water band, the drop and its ring, the hidden
   cat on the mural's point. Kept: it reads at a glance, holds up at 4 ×, and keeps its detail on a
   phone at 2 ×.

## What I'd do next

- A light scheme: the same bathhouse at opening time (morning light through the high windows,
  the noren just hung, the tile dry).
- A deeper Games room (a claw machine by the door) and more per-room hero variants.
- Animate the fridge's hum (a slow flicker) as a rail layer if the rail foot moves to the bottom.

## Known limits

- Pixel pictures under `cover` scale by whatever the box asks: exactly 4 × at 1440 × 900 (page,
  banner, status), a little more or less elsewhere, 2 × for the hero on phones.
- Header scenes sit past the lead text and above the buttons at desktop widths; on a tablet a
  scene can peek from behind the header's buttons.
- Header layers can't follow a banner's objects at every width (the banner is `cover`-scaled,
  a layer is not), so the radio's glow and the TV's flicker stay painted, not animated.
- Pokes are for a mouse only (the platform's rule); on phones the pieces just live.
