# Y2K skin: direction (the agent picks the final name)

**Idea:** the house as a millennium media-player skin. It mixes the Winamp and Windows Media
Player skin culture, the iMac G3's translucent Bondi plastic, chrome, and the cool-kid Y2K of
keychains, flip phones, clear consoles and glitter gel pens: those old MP3 player UIs and their
transparent things were already a UI aesthetic.
Transparency, bevels, gloss and LCDs are the point, and they must stay readable.

**References and their tells:**
- **Winamp 2.x skins:** a brushed or charcoal metal window, 1px bevel highlights top-left and
  shadows bottom-right, a title bar with grip lines, a small pixel LCD in green or amber on black,
  a spectrum analyser, tiny chunky transport buttons.
- **WMP 9 and 10 skins, Sonique:** blobby chrome shapes, aqua glass pills.
- **iMac G3 and the clear GameBoy Color, N64 and PS1 editions:** translucent candy plastic
  showing the insides, with speckle.
- **Early-2000s web:** matrix grids, lens flares, iridescent gradients, star sparkles (✦ drawn as
  art, never emoji), a lilac sky with clouds. A poster of a short phrase on lilac clouds.
- **Flip phones, keychain pets, frosted-plastic MP3 players.**

**Two schemes, two skins:**
- **Dark, "classic skin":**
  - charcoal and gunmetal surfaces with bevels
  - an LCD-green ink for numbers and small labels
  - an orange-yellow hot accent (think a volume bar)
  - a deep night-blue page with a faint matrix grid
- **Light, "Bondi":**
  - translucent ice and Bondi-blue surfaces (use `material.*.blur` and alpha for real
    transparency over a lilac cloud sky)
  - chrome edges
  - glossy aqua primary pills

**Type:** a wide techno display (Michroma, Orbitron, Audiowide, Syncopate, Krona One…), a clear
body (Lexend or similar), and a pixel LCD mono for numbers and times (VT323, Silkscreen): check it
reads in the Control Room.

**Controls** (`part.control`, `part.meter`, new for you):
- Primary buttons: glossy pills, a gradient with a bright top half over the colour.
- Secondary buttons: brushed metal with bevel shadows.
- Sliders and progress: LCD segments or a gloss tube (`part.meter.pattern`).
- Hover and press stay glossy: only the colour under the gloss changes.

**Art** (Blender for chrome and translucent plastic, with the chrome, translucent and plastic
presets; SVG for skies, grids, sparkles and skins):
- **Music deck** (`deck.surface`, 9-slice): **the skin window**, with title-bar grips, rivets
  and bevels. The middle stays a calm dark or frosted panel so the text reads.
- **Deck layer:** a small spectrum analyser (frames, `playing: true`) at a corner, never behind
  the song title.
- **Home hero:** chrome blobs and translucent plastic objects in a sky (light) or on a matrix
  grid (dark), rendered in Blender.
- **Page:**
  - light: the lilac cloud sky, clouds drifting slowly, sparkles twinkling (`particles`)
  - dark: a perspective matrix grid and a far lens-flare glow
- **Rail surface:** a playlist-window skin. **Now bar:** a mini-player skin.
- **Crest:** a chrome star or orb. **Empty state:** a translucent keychain toy. **TV bezel:** a
  translucent CRT.
- **Status strip:** a thin chrome bar with a tiny LCD feel.

**Pieces:**
- **Nox:** a translucent keychain pet or chrome blob with an LCD face (6 moods, animated idle).
- **Medals:** Y2K icons: a CD, a flip phone, a star, a heart gem, a controller, a floppy…
- **Transport keys:** Winamp-like chunky glyphs.

**Discoveries:** a lens flare crossing now and then; a sparkle on the crest; the spectrum
dancing only while music plays.

**Never:** brand logos (no Winamp, Apple, Nintendo or Sony marks or names), unreadable text on
glass (keep a frosted base under text), words in pictures, scrolling text.
