# Kinari · brief

- **Idea, in one sentence:** a quiet Japanese room in the morning — unbleached cotton, washi,
  kraft, dark walnut and sumi ink, everything in its place, and one small red seal.
- **Names:** Kinari · Kinari (kinari is the colour of unbleached cotton; the id stays
  `linen-morning`, the theme it grew from).
- **Scheme:** light only. It is not a "white theme": the ground is kinari beige (L 0.925), the
  structure is brown and black (walnut edges, sumi buttons, the tatami heri).
- **Three moments:** Home's ink-wash mountains in drifting mist (with geese and a falling leaf
  now and then, and bamboo shadows on the wall); the music deck as a kraft card with its seal and
  a thread of incense that burns only while music plays; the sign-in crest, an ensō and a seal.

## The tells

1. **Ma** — empty space that means something: one object per room banner, the hero's left half
   empty, a crest with nothing inside its circle.
2. **Sumi on washi** — ink washes that are dark at the ridge and fade into mist, bled edges,
   dry-brush tails; paper with long kozo fibres, never a flat fill.
3. **The Muji label** — a black button with washi text, kraft card, hairline brown edges, small
   radii (2–6 px): paper, not pills.
4. **The hanko** — one vermilion, always small and square: the focus ring, the slider's seal,
   the seal on the crest, the deck, the scroll and the hero; nothing else is red.
5. **Tatami and its heri** — the status bar is a strip of mat with its dark indigo cloth edge;
   the phone dock carries the same heri on top: the room is framed by its mats.
6. **Shoji light** — the rail is the alcove's paper wall lit from the top left, with a walnut
   post; the morning sun comes from the top left in every picture.
7. **Mincho titles** — Shippori Mincho with calligraphic contrast for titles and the brand
   (tracked 0.12em), a calm gothic (Zen Kaku Gothic New) for everything read and touched.
8. **Stamps, not drawings** — the pieces (avatars, Nox, medals) are carved stamps: kamon discs.

## Spec

- **Palette (OKLCH):** kinari ground 0.925/0.021/80 · washi surfaces 0.958/0.013/84 · kraft
  edges and meter track (0.78–0.8, hue 68–70) · walnut 0.37/0.04/52 (links, hover of the ink
  button, the rail post) · sumi 0.25/0.014/55 (text, the "accent": primary buttons, chosen chips,
  tabs, switches, progress) · hanko 0.55/0.175/33 (focus ring, slider thumbs, sprite red, seals).
  States from natural dyes: matcha success, kuchiba-ochre warning, bengara danger, ai indigo
  info, fuji private. Rooms: natural dyes at L ≈ 0.47–0.53, C 0.025–0.11.
- **One light:** morning sun from the top left through shoji: warm, soft; shadows fall down and
  to the right (the scroll, the cushion, the TV, the tatami under the heri).
- **Medium:** sumi ink washes on washi (numpy: periodic noise, bleed, dry brush), a few flat
  objects in walnut and kraft, pieces as 16 × 16 stamps drawn at 2×.
- **Type:** Shippori Mincho 500/700 (display, brand), Zen Kaku Gothic New 400/500/700 (body,
  titles, controls), M PLUS 1 Code (numbers). Labels tracked 0.08em, mixed case.
- **Shape:** radius xs 1 · s 2 (controls, chips) · m 4 (cards) · l 6 (sheets); hairline edges in
  kraft; shadows a 1 px step plus a soft warm drop only on overlays.
- **Motion:** drifting and slow: 150 · 300 · 460 · 760 ms, ease [0.4, 0, 0.2, 1]. Ambient:
  mist (6 px/s), bamboo shadows (2 px/s), geese every 200 s, a leaf every 150 s, incense
  frames while music plays.

## The house

| Place | What it gets | Why |
|---|---|---|
| Sign-in | `crest.webp`: an ensō and the seal | the house's first gesture: one breath of ink |
| Status bar | `status-heri.webp`: tatami with its indigo heri; border in heri indigo | the mat's edge frames the room at the top |
| Rail | `rail-shoji.webp` (paper lit from the top left, walnut post) over the washi texture; `scroll-foot.webp` at the rail's foot (a hanging scroll with bamboo and a seal, a layer so it can sway); washi halo under names | the alcove wall; no bars behind the names |
| Dock | `dock-heri.webp`: the heri along its top; washi texture | the same mat edge closes the phone at the bottom |
| Page | kinari + `washi.webp` fibres; scrim off; on Home only, `leaf-shadow.webp` (bamboo shadows, drifting, parallax) | the wall is shoji paper; shadows stay where text is not |
| Headers | variant banner; `banner-<room>.webp`: plain kinari with one small ink object top right per room | a single thing per room, above the buttons, gone on phones |
| Home | `hero-mountains.webp` + mist, geese, falling leaf layers | the cover picture: sansui in morning mist |
| Listen | deck: `deck-kraft.webp` 9-slice (kraft card, seal in the corner) + `incense.webp` while playing; sumi transport, hanko seal thumbs | the Muji card; music lights the incense |
| Watch | `tv-walnut.webp` walnut cabinet; posters untouched | wood and dark glass |
| Games | covers untouched; banner: two go stones | the game is the art |
| My Space | `space-tatami.webp`: shoji, alcove with a scroll and one red bud, a cushion | the person's own room |
| Me | 5 kamon avatars, 20 kamon medals, titles named in flavor.json | stamps |
| Control Room | the same tokens, no layer, a banner of raked gravel | calm, dense, readable |
| Sheets, menus, toasts | washi overlay, kraft edge, radius 6; toasts sumi | paper laid on paper |
| Empty states | `empty-stone.webp`: a stone in raked gravel, a leaf resting on it | the smile is the leaf |
| Controls | ink primary, raised washi secondary, kraft hairlines, hanko seal slider thumb (square, radius 2), hanko focus ring | the label and the seal |
| Nox | an ink cat, six moods; blush of seal red when happy | a brush mark with ears |
| Rooms | distinct natural dyes | wayfinding in the rail and kickers |
| Room marks, transport | HouseOS's pen-line icons at stroke 1.4, on purpose | pen for the interface, stamps for the pieces |

## Art sources

Every picture is drawn by code in `docs/design/themes/linen-morning/` (`make.py` with `ink.py`,
`pieces.py` for sprites, `tokens.py`, `manifest.py`, `flavor.py`), original, MIT like the theme.
No text, letters or characters in any picture; the seal carvings are a plum blossom.

## Do / Don't

- **Do:** leave space; keep red for seals; keep text on paper, never on ink.
- **Don't:** kanji or kana in pictures; cherry blossom everywhere; pure white; a pink palette.

## Pokes (desktop, with a mouse; found, never announced)

- **The hanging scroll** at the rail's foot: click it and it sways once on its nail and settles (1.1 s).
- **The incense bowl** in the music deck's lower right corner: click the bowl and the ember
  brightens, breathing out one slow puff that curls up and fades (1.4 s).
