# Castle of Night: direction (the agent picks the final name, no brand)

**Idea:** a 16-bit gothic vampire-hunter castle: SNES-era graphics, the classic, instantly
recognisable aesthetic of the genre and the lore of the vampire hunters and Dracula, in real pixel
art with attention to detail and mise en scène. Dracula and the gothic lore are public
domain; the game series' names, logos and characters are not: draw the genre, not the brand.

**Tells** (SNES era, 1991–1995):
- **Parallax:** a blood-red or violet night sky with a huge moon, a distant castle on a crag,
  mid-ground clock towers, near-ground stone arches and pillars.
- **Scenery:** candelabras and wall candles that flicker (frames). Gothic stained glass, gargoyles,
  iron gates, crumbling stone with moss.
- **HUD:** a red segmented health bar, a heart counter, a sub-weapon frame (dagger, axe, holy
  water, cross, stopwatch), gold-framed stat boxes.
- **Bats** flying across; clouds sliding over the moon.
- **Palette:** SNES 15-bit honest (each channel a multiple of 8). Night purple, crimson, bone,
  tarnished gold, stone blue-grey, candle orange.
- **Chapter art:** a dramatic staircase up to the keep.

**How it differs from Legacy** (the haunted-house theme, being reworked in parallel): Legacy is a
cosy moonlit manor in violet-blue and ember, warm and domestic. The castle is action-game gothic:
crimson and gold, ornament and HUD, drama and scale. Never reuse Legacy's fonts (Jacquard 12,
Alegreya Sans) or its palette.

**Palette:**
- **Ground:** deep night-purple and black.
- **Stone:** 3–4 blue-grey ramps.
- **Accent:** crimson.
- **Ornament:** gold.
- **Ink:** bone.
- **Candlelight:** orange-yellow.

Dark scheme only.

**Type:**
- **Display:** gothic; consider Grenze Gotisch, Pirata One, UnifrakturMaguntia, New Rocker, or a
  pixel gothic.
- **Body:** a sturdy face that reads at 14 px.
- **Mono:** a pixel HUD mono for numbers (Silkscreen, VT323, Press Start 2P is too wide for body use).

**Pixel scale:** choose one density. For example, draw the parallax pieces at native size and
show them at `scale: 3` or `4`; slots are drawn at their native box. Never mix sizes.

**Art** (pixel, `pixel.py`):
- **Page:** real parallax, the heart of the theme. Up to 5 page layers:
  - sky and moon (cover)
  - clouds drifting over the moon
  - the far castle (repeat-x or natural at the bottom, depth 0.15)
  - a clock tower (natural, depth 0.4)
  - near arches (natural, bottom corner, depth 0.8)
  - bats crossing now and then (frames + cross)

  Keep the scrim strong enough: panels are solid stone.
- **Panels:** a 9-slice stone-and-gold ornament frame (`panel.surface`, fit slice).
- **Sheets:** a larger ornate frame.
- **Music deck:** a relic chamber or stained-glass alcove skin with flickering candles as deck
  layers.
- **Home hero:** the staircase to the keep under the moon, a chapter-title picture without the
  title.
- **Header banners per room:** a gallery, a chapel, a library, a clock tower, the throne.
- **Rail:** a stone column skin with a candle sconce at its foot (flicker frames).
- **Status strip:** battlements.
- **Crest:** the castle's heraldry: a shield with bat wings and a cross.
- **Empty state:** a candle in a sconce.
- **TV bezel:** a gilded frame.
- **My Space:** a castle chamber.

**Controls:**
- Meters as a crimson segmented health bar (`part.meter.pattern`) with a bone track.
- Buttons with a stone bevel.
- The primary action in crimson with a gold edge.

**Pieces:**
- **Nox:** a small bat familiar, 6 moods, idle wing flap and a blink.
- **Avatars:** moon, bat, raven, rose, ghost, all redrawn in this style.
- **Medals:** sub-weapons and relics (dagger, axe, holy water, cross, stopwatch, rosary, heart,
  crystal…), one per title, legible at 16 × 16.
- **Room marks:** pixel icons.

**Discoveries:** a bat crossing the moon; candles flickering; the heart counter motif somewhere
smart; a stained-glass window where a colour glints.

**Never:** series names or logos, copied sprites, the Belmont or Alucard likenesses, mixed pixel
sizes, text in pictures.
