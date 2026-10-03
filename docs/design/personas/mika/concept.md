# Pocket Hatchling · Éclosion de poche

**The idea:** the house is a 90s keychain virtual pet. You're holding a bubblegum plastic egg with glitter in it. Every panel is a small reflective LCD window set into that shell, with grey-green glass, a visible pixel grid and segment-black ink. There's one berry-red rubber button. Nox is the pet that lives in there: it hatched, it gets hungry, it beeps. The house titles are the care chart. It's original: no real toy's shell, characters, logo or name.

## Palette (light scheme)
| Role | Value | Where from |
|---|---|---|
| Shell (canvas) | `oklch(0.87 0.065 352)` bubblegum + glitter tile | translucent candy plastic |
| LCD (surfaces, fields) | `oklch(0.905 0.045 118)` + 4 px pixel-grid tile | reflective LCD glass |
| Ink (text, outlines) | `oklch(0.27 0.035 145)` | LCD segments |
| Accent | `oklch(0.52 0.2 358)` berry | the rubber A/B/C buttons |
| Rooms / people | L 0.46–0.47, C 0.12, eight hues (tangerine, sky, lime, grape…) | the other shell colours of the line |
| Status | success leaf 150, warning mustard 65, danger brick 32, info 235 | all dark enough for the LCD and the shell |

## Type
- **Display:** Doto 900 (dot-matrix). It's the LCD's own lettering and only goes on titles.
- **Body:** Lexend 400/500/600, rounded and very legible, like the printed manual.
- **Mono / numbers:** VT323, like the LCD counters.

## Motifs
The egg; the 7×7 care icons (food, light, ball, heart, bath, Zz); the LCD pixel grid; glitter; the zig-zag crack of hatching; the three round buttons.

## Composition: every part
| Part | Becomes | Ties in because |
|---|---|---|
| Page background | the pink glitter shell (`material.canvas.texture` glitter.svg) | you're holding the toy |
| Top status bar | a strip of shell with tiny embossed eggs (`status.backdrop` → status.png); the brand in Doto | the top edge of the egg |
| Side rail / bottom dock | the button row under the screen: LCD rail on desktop, pale shell dock on phone; the room glyphs should be the 7×7 care icons | the device's controls |
| Page header | Doto title plus a kicker in the pet's voice ("The beep speaker", "The care chart") | the LCD's menu screen |
| Panels | LCD windows: 1 px ink edge, inset bevel, pixel-grid texture | screens set into the shell |
| Lists and rows | ink dividers on the LCD, like the lines of the care menu | the same |
| Buttons | rubber buttons: raised, a 3 px drop in darker shell, primary in berry | the A/B/C buttons |
| Switches, fields, chips | fields are sunken LCD; chips are pill "stickers"; switches are berry when on | the same |
| Now-playing bar | a mini LCD with a dancing pet (wished for) | the pet listens with you |
| Sheets / pop-ups | the back of the egg: pale shell, rounded top, 1 px ink edge | turn the toy over |
| Avatars (crest, moon, bat, raven, rose, ghost) | six hatchlings: a spotted egg, a sleepy moon-blob, a winged blob, a little bird, a flower sprout, a ghost pet (art/pixel) | everybody in the house is a pet |
| Nox mascot | a round pink hatchling in its cracked shell, with a berry antenna; idle / blink / listening (ears up) / thinking (dots) / happy (hearts) / error (dizzy X eyes) | Nox is the pet |
| House titles and medals | care-chart awards: Head DJ → "Loudest beeper", Task hero → "Clean pet", Night owl → "Up past lights-out", each with a pixel ribbon medal | the care chart |
| Empty / loading | an unhatched egg with Zz ("Silence. The pet is asleep. Feed it a song."); loading = the egg wobbling | waiting for it to hatch |
| Fonts | Doto / Lexend / VT323 | above |
| Motion | springy enter (the pet hops in), snappy mechanical everything else; ideally `steps()` like LCD frames | toy firmware |
| Words | kickers and taglines in the pet's voice, en + fr (tu) | above |
