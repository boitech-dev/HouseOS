# Modular: direction

**Idea:** Swiss modular typography as a house. Letters and shapes built from one grid of modules
(squares, quarter circles, dots), set in a strict black and white duality with one signal red.
Structural, dynamic, playful, super clean: a poster system you live in.

**References and their tells:**
- Wim Crouwel's New Alphabet and his Stedelijk posters: the grid is visible and letters obey it.
- Ben Bos, and Total Design: fat modular numerals, blocks.
- Karl Gerstner's programmes: variation by rule.
- The Nothing phone's dot-matrix type and glyph lights.
- Josef Müller-Brockmann: asymmetric grids, big numbers, red accents.
- MIT Tech Review's modular covers.

**Palette:**
- **Light scheme (first):** paper white (warm, not blue), ink black, signal red (a true vermilion
  red, used rarely and loud: the primary action, the selected mark, one module per composition).
- **Dark scheme (second):** its inverse duality: black paper, white ink, the same red.

**Type:** the display face is grid-built. Consider Handjet, a modular variable face (its element
axes let you pick squares or dots), or Doto (dot-matrix), Bungee, Big Shoulders, Unbounded,
Sixtyfour; find the most "modular" OFL face that still reads. The body is a clean grotesk that
reads at 14 px (Space Grotesk, Schibsted Grotesk, Inter Tight…); the mono is Space Mono or similar.
Titles large and tight, labels in caps with tracking inside the band.

**Shape and motion:**
- Radius 0 for boxes; full circles for chips and avatars. Modules are squares and circles, nothing
  in between.
- Panels flat with a thick rule feel (1px edges; hierarchy from black blocks and red squares, not
  shadows).
- Motion snappy, maybe `steps()` for a mechanical feel on small things.

**Art (SVG, rendered by `svg.py`, crisp, no grain or very little):**
- **Home hero:** a composition of modules: a big quarter-circle and square system with one red
  module. It must feel like a poster.
- **Header banners, one per room** (`header.banner` with `rooms`): each room its own module
  composition, an emblem built from the same grid: the music room's quarter circles like sound,
  the watch room's frame, and so on. No letters, no numerals: the room's name comes from the font.
- **Page:** a very faint module grid (dots at grid crossings) as a slow `drift` layer, or static.
- **Deck skin:** a poster frame with a red square module where the music plays.
- **Crest, empty state, rail foot, status strip:** module compositions.

**Pieces:** Nox made of modules (a square body, quarter-circle ears), 6 moods; the medals are
geometric modular glyphs; the room marks are modular.

**Discoveries:** the red module moves to a different corner in each room's banner; the grid
drifts by one module when you look long enough; Nox's blink is a module flipping.

**Never:** letters or digits baked in pictures, extra colours, soft shadows, blur, rounded rectangles.
