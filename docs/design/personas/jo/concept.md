# Bathhouse After Hours (`sento-night`) · concept, by Jo

**The idea.** A Shōwa-era neighbourhood bathhouse ten minutes before closing. Wet night-teal
mosaic tile on the walls, the vermilion curtain at the door, hinoki pails, a mountain mural
fading into the steam, milk bottles humming in the fridge by the lockers.
**The rule for all art: every picture is a tile mosaic, one pixel = one glazed tile.** This makes
HouseOS's forced `image-rendering: pixelated` part of the idea instead of a limit.

## Palette (dark only)
| Role | Source | Value |
|---|---|---|
| Neutral / grounds | night tile, teal-slate | seed `oklch(0.52 0.035 215)`; canvas `oklch(0.19 0.032 222)` → surface 0.23 → raised 0.285 |
| Accent (the only call to act) | the noren curtain | vermilion `oklch(0.66 0.17 33)` |
| Success | bath-water jade | `oklch(0.74 0.11 170)` |
| Warning | hinoki gold | `oklch(0.83 0.12 85)` |
| Danger | camellia crimson, far from the vermilion | `oklch(0.62 0.2 355)` |
| Info / private | mural mountain blue / yukata plum | 250 / 310 |
| Paper | milk-cream notice card | `oklch(0.93 0.025 85)`, tilted 1deg |
| Rooms | the mural's tile colours | sea teal, jade, hinoki gold, mountain blue, plum, vermilion-peach |

## Type
Dela Gothic One (heavy, wide Japanese-gothic shop-sign display, weight 400) for titles and the
brand; Fira Sans (sturdy, a little technical) for reading; Overpass Mono (timetable) for numbers.

## Motifs
Seigaiha wave scales; 2×2 glazed tiles with grout; a split three-panel curtain; hinoki wood
grain; three rising steam lines; milk-bottle caps; lockers with brass key plates.

## Composition plan, part by part
| Part | What it becomes | How it ties in |
|---|---|---|
| Page background | wet mosaic wall: 24 px tile of 2×2 glazed tiles + grout (`art/tile.svg`) | the wall of the bath |
| Top status bar | a band of wave-scale tile with three short vermilion curtains and a hinoki trim at the bottom (`art/status-waves.png`) | the entrance lintel |
| Side rail / bottom dock | hinoki wood panel with a grain, the current room marked by a vermilion curtain tab | the front desk (bandai) / the shoe-locker row |
| Page header | Dela Gothic title, kicker in the room colour, like an enamel shop sign | enamel signage |
| Panels | tonal-step tile panels with a 1 px grout edge and a wet inner highlight | wall sections |
| Lists and rows | grout lines as dividers | tile courses |
| Buttons | primary = vermilion curtain; secondary = hinoki raised with a bottom lip; chips = round bath tokens | door, wood, tokens |
| Switches / fields | sunken = the tub (inset shadow) | the bath |
| Now-playing bar | the radio on the fridge: hinoki case, dial | Listen's "radio by the fridge" |
| Sheets | overlay with steam blur; a split noren hanging from the sheet's head | walking through the curtain |
| Avatars | bath token, moon-in-water, paper fan, geta, camellia, steam puff | things in a bathhouse |
| Nox | a milk bottle with a paper cap: blinks; fogs up when thinking | the fridge |
| Titles & medals | milk-bottle caps: gold / silver / bronze | "king of the milk fridge" |
| Empty / loading | an empty wash basin with one drop; loading = steam rising | quiet after hours |
| Home hero | original tile mural: a big mountain, seigaiha sea, pine island, sail, low sun, steam | the mural above the bath |
| My space | changing room: lockers (yours open, a red towel inside), milk fridge, fan, basket | your locker |
| Watch | hinoki-cased CRT with a lace doily as the frame around the picture | changing-room TV |
| Sign-in crest | a hinoki pail with three steam lines in a vermilion ring | the house's mark |
| Fonts | shop-sign gothic + sturdy sans + timetable mono | signage |
| Motion | drifting like steam: 240/420 ms, soft ease, nothing bounces; ambient: steam drift | steam |
| Words | "The radio by the fridge", "Changing-room television", "The notice board", "Shoe lockers — Your key, your locker.", "Only the drip of the tap. Put a song on." (en + fr) | the sentō's voice |
