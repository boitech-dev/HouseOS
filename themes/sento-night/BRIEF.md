# Bathhouse After Hours · brief

**Idea, in one sentence:** a Shōwa-era neighbourhood sentō ten minutes before closing: the great
Fuji mural over the baths seen through steam, wet teal mosaic, a vermilion noren in the doorway,
hinoki lockers and counters, the milk fridge humming, the bathhouse cat making its last round.

- **Names:** Bathhouse After Hours · Bains publics, après l’heure
- **Scheme:** dark only, on purpose: it is after hours (the lamps are low, the fridge glows).
- **Identity:** pixel. One art pixel = 4 screen pixels on a desktop, everywhere.

## The tells (what makes it read as a sentō at a glance)

1. **The mural (penki-e):** Fuji painted big on the back wall: flat stepped sky bands, a snow cap
   in long ridges lit on the left, a red sun, black pines on a rocky point, a sea of painted
   crests, a sail. Painted on big wall tiles, so a faint grout grid crosses it.
2. **Wet mosaic:** tiny square teal tiles, dark grout, the odd lighter chip; glaze lit on top.
3. **The noren:** a vermilion split curtain hanging under a hinoki lintel, the ♨ mark (a pictogram,
   never a letter) on its middle panel.
4. **Hinoki and brass:** lockers with wooden plank keys, the counter radio's wooden case, brass
   corner caps and a backlit tuning dial.
5. **The milk fridge:** a glowing glass door, three shelves of bottles with paper caps.
6. **Yellow basins and hinoki stools** on the wet floor; round fans, the dial scale, the massage chair.
7. **Steam:** always drifting, drawn as dithered wisps, never over words.
8. **The cat:** a calico who sleeps on warm things and walks the lintel at night.

**Three moments:** Home's hero (the bathing hall in one-point perspective under the mural, steam
gathering under the ceiling, a drop falling now and then); the music deck (the counter radio: a
wooden case, the dial with its needle drifting while music plays); the status bar (the noren in
the doorway, swaying, and the cat trotting past under it every minute and a half).

## Spec

- **Palette (make.py `PAL`, locked on every picture; the sprite tokens are the same colours):**
  - tile teal 0–9 `#061015 … #cfe8e0` (ground, grout, glaze, water);
  - mural blues A–H `#0d1433 … #e6eef6` (sky, sea, mountain, snow);
  - vermilion u–z `#3a0d0b … #ffb58f` (the noren, the sun, lacquer; the accent);
  - hinoki a–h `#1c0f09 … #f8e6bb` (wood, up to milk cream);
  - small ramps: basin yellow i–l, pine p–s, plum M–O, ginger o, white W.
  The **one accent** is vermilion: primary buttons, the noren, the dial's needle.
- **One light:** the lamps hang high on the left, warm. Tops and left faces catch it; shadows fall
  right and down toward teal. The fridge adds a cold glow where it stands.
- **Medium and scale:** pixel art drawn at 1 art px = 4 screen px (pictures sized so their slot
  shows them at about 4×; layers at `scale: 4`; 9-slice frames drawn at 4×). Outlines dark, hue-
  shifted ramps, dither only for steam and the sky's band edges.
- **Type:** Dela Gothic One (a heavy, wide shop-sign display face) for titles and the brand; Fira
  Sans for reading (sturdy, clear at 14 px); Overpass Mono (a timetable mono) for times and counts.
- **Shape:** square, tile-sharp (3 px radius on cards and controls, square sheets); chips round like
  bath tokens; hard pixel shadows (`elev.*`: a solid drop, then a soft one).
- **Materials:** surfaces are wet glaze (a 1 px lit top, a 2 px shaded bottom); buttons glazed tile
  (a gloss over the teal); the main button vermilion lacquer; sliders and progress bars a row of
  small tiles with grout (`part.meter.pattern`); sheets are wet tile under a noren's hem.
- **Motion:** drifting, like steam: 240/420 ms, a soft ease, nothing bounces. Layers: vapour drifting
  and puffs rising on the page (under the scrim), steam and a drop in the hero, the noren's sway and
  the cat in the status bar, the dial's needle in the deck (only while music plays).

## The house, part by part

| Place | What it gets | Why |
|---|---|---|
| Sign-in | `auth.crest`: the ♨ in a medallion of twelve vermilion tiles around teal mosaic | the first thing a guest sees: the bathhouse's mark |
| Status bar | `status.backdrop`: the hinoki lintel; `part.status.texture`: the wave-scale tile; layer: the cat (a crossing, 4-frame walk) | the lintel over the doorway |
| Rail | `rail.surface`: one composed locker wall, 58 × 270, cover anchored bottom (calm doors under the names; on the right the clock, a key out, a painted Fuji poster, an open locker with a yukata and basket, a towel over a door, a shelf of basins); rail-foot layers: the milk fridge with its basins, its light humming, and the cat asleep on a bench beside it, flicking its tail (both answer a click) | the wall you walk along |
| Dock (phones) | `dock.surface`: the shoe lockers by the door with their plank keys | the doors of the house |
| Page | `page.backdrop`: the mural up close on big tiles, the mosaic wall and the bath below; scrim 78 %; layers: drifting vapour, rising puffs | every room happens in front of the mural, through steam |
| Page pieces | `part.page.quiet` plaques, `part.page.gallery` ground, a hard pixel shadow under headings | nothing sits on the picture without its own ground |
| Headers | `banner` variant; a frieze on every banner's top 8 rows (tile band, picture rail, its ledge, wind chimes) that phones see; a header layer: the noren swaying past the words (rooms without header buttons); per room, its corner (standing on a counter, shelf or wainscot, under a pendant lamp): a radio (Listen), a TV hung high (Watch), the game corner's lit sign and paddles (Games), the fridge, scale and cat (House), lockers and the crane (My Space), a key board (Files), boiler pipes and gauge (Control Room), mirror and hood dryer (Me), notice board and letter box (Inbox), fan, switches and lamp (Smart home), the attendant's bell and abacus (Ask), lanterns and fans (Party); default: clock, towels and a wind chime | each room is a corner of the bathhouse; set past the words and above the buttons, outside a phone's view |
| Home | `home.hero.backdrop`: the bathing hall (mural, tub with its reflection, the wall of mirrors and taps, stools, a basin pyramid, the lamp, the cat on the rim); hero layers: cream steam curls, a falling drop, and under the picture the hall's tile (a phone's greeting sits on it) | the cover picture |
| Listen | `deck.surface`: the counter radio's case (9-slice: rounded top, grain, louvred speaker band, two knobs); deck layers: the amber dial and its needle, a wisp of warmth (both while playing) | the music comes from the radio on the counter |
| Now bar | `nowbar.surface`: a strip of vermilion lacquer with a darker brass rim | the radio's travelling cousin, always at hand |
| Watch | `watch.tv.bezel`: the changing-room TV on its cabinet, a doily, a camellia in a milk bottle | posters stay untouched |
| Games | the game-corner banner; covers stay untouched | |
| My Space | `space.room.scene`: the changing room: your locker open (a red towel), the crane, the massage chair, fan, scale, a yukata in a basket | your own corner |
| Me | 5 avatars (moon on the water, a bat across the moon, a crow on the chimney, a camellia, the steam ghost); 20 medals (sentō objects) and their names | |
| Control Room | tokens only (plain glaze panels) and the calm boiler banner | dense and quiet on purpose |
| Sheets, dialogs, menus | `sheet.surface`: a noren's hem along the top; faint wet-tile grout (`tile.svg`); square corners | stepping through a curtain |
| Empty states | `state.empty`: an empty basin, one drop about to land, the ripple smiling | a smile in it |
| Controls | glazed tile buttons, vermilion lacquer primary, tile-segmented meters, milk-cream square thumbs | |
| Nox | the milk bottle, 6 moods (blink, listening rings, fogged glass thinking, happy cheeks, its cap fallen off on an error) | Nox is the bottle missing from the fridge |
| Rooms | a light each: milk cream, the radio's dial, the CRT's glow, jade tile, hinoki, plum… | |

## Pokes (desktop, a mouse; click the thing, nothing tells you it's there)

| Where | Click | What happens |
|---|---|---|
| Rail foot, left | the milk fridge | its glass door swings open, a bottle clinks, a few paper caps pop out, it closes |
| Rail foot, right | the cat asleep on the bench | it wakes, stretches with its rear in the air, sits up for a big yawn, curls up again |
| Header (rooms without buttons) | the noren | it parts as if someone walked through: side panels pushed apart, the middle one lifted, then swinging back |
| Listen / Home deck | the radio's dial | the needle swings across the band and back, a few little notes fly out |
| Home hero, top right | the steam under the ceiling | it billows, and condensation drops scatter |

## Art (all original, drawn by code; licence CC-BY-4.0)

Every picture: `python3 docs/design/themes/sento-night/make.py` (pieces: `pieces.py` beside it).
No words, letters or numerals in any picture (the ♨ is a pictogram; the clocks have ticks only).
No brands: the basins, bottles and radio are generic. The mural is an original composition.

| Use | File | Drawn at | Notes |
|---|---|---|---|
| `page.backdrop` | page-mural.png | 400 × 225 (4 × at 1440 × 900) | pixel, cover |
| `home.hero.backdrop` | hero-hall.png | 180 × 64 (≈4 × desktop, 2 × phone) | pixel, cover |
| `status.backdrop` | status-beam.png | 302 × 12 | only the lintel is painted |
| `header.banner` (+12 rooms) | banner*.png | 286 × 40 | pixel, cover, top |
| `rail.surface`; rail-foot layers | rail-wall.png (a plain night-tile wall; low down the painted Fuji mural behind the fridge and the cat, a hinoki ledge and wainscot); foot-fridge.png, foot-cat.png (+ their poke sheets) | 58 × 270 (cover, bottom); 29 × 32, 22 × 20 | pokes: foot-fridge-open, foot-cat-wakes |
| `dock.surface` | dock-shelf.png | 98 × 16 | |
| `deck.surface` / `nowbar.surface` / `sheet.surface` | deck-radio / nowbar-frame / sheet-hem.png | 12, 12, 9 px squares × 4 | 9-slice, slice 16, 16, 12 |
| `auth.crest`, `state.empty`, `watch.tv.bezel`, `space.room.scene` | crest, empty-basin, tv, changing-room.png | 40², 24², 40 × 30, 100 × 45 | 4 × in their boxes |
| layers | noren, cat-walk, hero-steam, hero-drop, deck-dial, deck-needle, vapour, steam-puff | natural, scale 4 | frames, crossings, drift, particles |
| textures | status-waves.svg, tile.svg, scanlines.svg | pixel-exact SVG | |
