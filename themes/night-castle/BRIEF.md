# The Vampire's Keep · brief

- **Mood, in one sentence:** the title screen of a 16-bit gothic action game at midnight: a huge
  moon behind the count's castle, candlelit stone, crimson and tarnished gold, a HUD in the corner.
- **Names:** The Vampire's Keep · Le donjon du vampire
- **Scheme(s):** dark only (a castle at night; a day version would be another theme).
- **References, in words:** Super Nintendo gothic platformers of 1991–1995 (parallax night skies,
  segmented health bars, sub-weapon frames); Bram Stoker's Dracula and the Universal horror sets;
  the stained glass and rib vaults of a Rayonnant chapel; illuminated manuscript blackletter;
  a candelabrum on a stone sill.
- **Material feel:** stone (blue-grey ashlar), tarnished gold, crimson velvet.
- **Shape:** sharp. Every corner square; gold bosses with a ruby on the frames' corners.
- **Edge:** 1 px night-black edges, the 9-slice gold frames drawn inside them; bevels lit
  top-left→ down-right like SNES buttons (1 px highlight, 1 px shadow).
- **Type personality:** Grenze Gotisch (a blackletter that still reads) for titles, the brand
  and chapter-like headings; Vollkorn (sturdy old-style serif, dark colour) for everything read;
  DotGothic16 (a 16-bit role-playing game's pixel type) for numbers, times and the HUD. Blackletter against old-style:
  contrast of structure, one family of the book.
- **Colour story:** SNES 15-bit honest (every channel a multiple of 8). Ground: night violet to
  black. Stone: a blue-grey ramp, violet in shadow. One accent: crimson (act here, on). Gold is
  ornament and the focus ring (the game's cursor). Ink: bone. Candle orange only where a flame is.
  Room lights: a jewel per wing, lifted so they read as tints on the night ground.
- **Identity:** pixel. Nox is a small violet bat familiar with candle eyes; room marks are castle
  objects (the keep, organ pipes, a gilded frame, a key, a tome, a lantern, a chest, a cameo, a
  studded door); medals are the hunter's relics (dagger, axe, holy water, cross, stopwatch,
  heart, crystal, the roast in the wall…).
- **Motion personality:** slow and nocturnal: clouds sliding over the moon, bats crossing now and
  then, embers rising from the deck while music plays. Interface timing crisp (100/160/260 ms).
- **Do:** one light (the moon, up-right) in every picture; one pixel size (× 3); dark walls
  behind every title; gold only as ornament, crimson only as action.
- **Don't:** series names, logos or characters (no hunter or count likenesses); text in pictures;
  bright art behind text; Legacy's fonts (Jacquard 12, Alegreya Sans) or its violet-and-ember palette.

## The idea and the tells

**One idea:** HouseOS as a castle's HUD: every room a wing of the keep, every panel a gold-framed
stat box, the night outside moving in parallax.

**Tells:** (1) parallax night: a sky, a huge moon, the castle on its crag, a balustrade in front;
(2) gold-framed HUD boxes with corner bosses; (3) crimson segmented health bars; (4) sub-weapons
and relics; (5) candles and candelabra, the only warm light; (6) stained glass and rib vaults;
(7) blackletter chapter titles; (8) bats crossing the moon.

**Three moments:** Home's hero (the flying staircase to the keep, the moon and its bats), the
page itself (the parallax night behind every room), the music deck (gold HUD keys, a crimson
key with a gold edge, health-bar meters, embers rising while it plays).

## Spec

- **Palette** (docs/design/themes/night-castle/palette.py): NIGHT 7 steps (ground), DUSK 5
  (horizon glow), STONE 10 (surfaces), MOSS 4, CRIMSON 7 (the accent), GOLD 7 (ornament),
  BONE 6 (ink), FLAME 6 (candles only), MOON 5 (moonlight), GLASS 8 (stained glass).
- **Light:** the moon, high on the right: rim light on right and top edges, shadows down-left
  and violet. Candles are local and warm, never lighting a whole picture.
- **Medium:** pixel art, one scale: every native pixel is 3 × 3 screen pixels (layers at scale 3,
  frames saved × 3 for 9-slice). The slots the app scales (hero, banners, chamber) are drawn at
  the density that shows about × 3 on a desktop.
- **Shape:** square; panels, sheets, the rail, the dock and the Now bar share one 9-slice family.
- **Motion:** dur 100/160/260 ms; ambient: clouds drift, bats cross (page every 45 s, hero every
  24 s), embers rise in the deck only while music plays.

## The house

| Place | What it gets | Why |
|---|---|---|
| Sign-in | `auth.crest`: a crimson shield, gold cross, bat wings, a crown of spikes | the castle's arms |
| Status bar | battlements texture, a torch flickering on the wall walk | the top of the wall |
| Rail | stone texture, the gold 9-slice frame, a rail-foot shrine: a candelabrum of three flickering candles on a draped altar, a heart reliquary | a HUD side panel, a chapel window |
| Dock | stone, the thin gold frame with ruby bosses | the HUD's bottom bar |
| Page | parallax layers: night sky (cover), far castle and moon (depth .15, not on Home or the Control Room), drifting clouds, the balustrade (depth .45), bats crossing; scrim 66 % | the heart of the theme, calm behind content |
| Headers | `banner` variant; a wing per room: hall (default), chapel (Listen), library (Files), clock tower (Control), throne (Me, My Space), armoury (Games), portrait gallery (Watch) | each room a wing; the title always on dark wall |
| Home | the flying staircase to the keep (hero), its sky and moon as a layer, bats crossing the moon | the chapter picture |
| Listen | the deck as a crimson-velvet reliquary (deck.surface), candles flickering in its corners, embers while playing, gold HUD keys, health-bar meters | the HUD |
| Watch | `watch.tv.bezel`: a gilded frame with the moon in it; posters untouched | a painting on the castle wall |
| Games | covers untouched; the armoury banner (the sub-weapons) | the relics |
| My Space | a bedchamber: canopy bed, fire, a window with the moon, a coffin in the corner | a castle room |
| Me | five avatars redrawn, 20 relic medals, titles as a hunter's feats, levels in hearts (♥) | the heart counter |
| Control Room | the same stone and frames, the clock-tower banner, no far moon behind it | calm and dense |
| Sheets | the thin gold + crimson velvet frame with ruby bosses | a reliquary lid |
| Empty states | a candle in an iron sconce with a little bat asleep under it | the smile |
| Controls | stone-bevel buttons, crimson primary with gold edge, gold focus ring, square slider thumb, segmented meters on a blood-dark track | a SNES menu |
| Nox | a violet bat familiar, six moods, idle and blink | the familiar |
| Rooms | a jewel light per wing | distinct, all lifted for the night ground |
| Pokes (desktop) | rail-foot shrine: candles whipped, a heart drops · hero gargoyle: eye kindles, wings, bats scatter · status torch: flares, sparks · deck votives: snuffed, smoke, relit | the genre's rituals, found by clicking |

## Art sources

Everything is drawn by code in `docs/design/themes/night-castle/` (make.py and its modules),
original, CC-BY-4.0. Fonts: Grenze Gotisch, Vollkorn, DotGothic16 (OFL, via Fontsource).
