# HouseOS original artwork

Generated2026-09-20 with the built-in OpenAI imagegen tool. Original sources are in
`sources/`, including retained generation provenance metadata. Production exports are
in `frontend/public/art/`; `manifest.json` indexes dimensions, purpose and source.
No third-party game art, screenshots, remote hotlinks or embedded interface controls.

Prompt set:
- Panorama: original16-bit pixel environment, shallow moonlit rooftop/courtyard,
  inhabited dark stone house at left, amber windows, quiet navy center, moon at right;
  no words, brands, interface or recognizable franchise.
- Objects: transparent3×3 atlas of house/moon crest, bat/envelope, cassette/record relic,
  blank CRT, archive tray, gothic window, sleeping-bat mailbox, idle record player,
  moonlit paper tray; consistent navy/plum/cream/amber palette.
- Icons: transparent5×2 atlas, music/TV/folder/note/grocery/calendar/inbox/settings/moon/
  warning,24px logical silhouettes, no words or logos.
- Courier: six consistent transparent poses, open/blink/open/raised wings/out/lowered,
  identical body scale/baseline, lilac bat and cream envelope, no scenery.
- Mobile panorama: independent shallow composition, small house/window at far left,
  low gate along bottom, moon upper right, quiet navy center,390×88 logical export.

Exports use nearest-neighbor scaling, fixed transparent canvases and lossless PNG/WebP.
Courier has6×32px fixed-grid frames with common baseline (one-pixel final-frame variance),
used for a single successful-message action only. Window glow is a four-frame fixed-grid
brightness variation of the original window. Still/reduced-motion disables both;
hidden pages pause CSS animation. Static equivalents are available. App maskable icon
keeps the crest inside the safe circle. A10 paper edge is optional and omitted: semantic
paper surfaces use CSS borders. A08 generated glyphs are available; small functional
control symbols use Lucide ISC-licensed SVGs (license in frontend/licenses).

Reviewed exported desktop/mobile artwork in the actual interface, plus source atlas and
courier poses. Built-in imagegen produced the artwork; no paid API credential was read.
Source
retention and hashes permit reproducible identification; generation itself is not bit-
reproducible. No human art-approval claim is made.
