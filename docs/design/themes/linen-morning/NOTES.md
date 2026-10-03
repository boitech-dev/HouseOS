# Kinari · notes

Kinari replaces the plain "Linen Morning" (same id, `linen-morning`). Its brief is
`themes/linen-morning/BRIEF.md`; this page is what's in it, how it was made and what's next.

## Regenerate

```bash
python3 docs/design/themes/linen-morning/make.py      # every picture (≈30 s), or name pieces: hero crest …
python3 docs/design/themes/linen-morning/pieces.py    # sprites.json (avatars, Nox, medals)
python3 docs/design/themes/linen-morning/tokens.py    # tokens.json
python3 docs/design/themes/linen-morning/flavor.py    # flavor.json (title names)
python3 docs/design/themes/linen-morning/manifest.py  # theme.json (slots and layers for the art that exists)
```

`ink.py` is the painting kit (numpy + Pillow only): OKLCH colours, periodic noise, FFT blur,
ink bleed, dry brush, washi fibres, brush strokes. Every JSON is written atomically.

## What's in it

- **Tokens:** kinari ground, washi surfaces, kraft hairlines, walnut links, sumi as the
  "accent" (ink buttons with washi text, chosen chips, tabs, progress), hanko vermilion only for
  the focus ring and the square slider seal; natural-dye states and rooms; radii 1–6 px; slow
  drifting motion. Shippori Mincho / Zen Kaku Gothic New / M PLUS 1 Code (172 KB).
- **Pictures (30 files, 295 KB):** Home hero (sansui mountains in mist), crest (ensō + seal),
  status (tatami + heri), dock (heri), rail (lit paper wall + walnut post), rail scroll (bamboo),
  13 room banners (one ink object each: tea bowl, wind bell, round window, go stones, broom,
  paulownia box, sleeping cat, paper crane, raked gravel, stone lantern, tied letter, one branch,
  taiko), deck (kraft card, 9-slice), incense, empty state (stone, leaf), TV (walnut), My Space
  (tatami room), washi textures.
- **Layers (5):** bamboo leaf shadows on Home's wall (drift, parallax), hero mist (drift), geese
  (a rare crossing, wingbeat frames), a falling bamboo leaf (a rare crossing, tumbling frames),
  incense smoke in the deck (frames, only while music plays).
- **Pieces (31):** five kamon avatars (moon, bat, crow, camellia for rose, little ghost), Nox as an
  ink cat in six moods, twenty kamon medals. Room marks and transport keys stay pen-line icons.
- **Words:** the twenty title names, en and fr.

## Discoveries

0. Click the hanging scroll: it sways once. Click the incense bowl: one slow puff.
1. The bamboo shadows on Home move with the sun (2 px/s) and shift against the pointer.
2. Geese cross the hero's sky every few minutes; a single dry leaf tumbles down now and then.
3. The incense in the music deck smokes only while music plays.
4. Seals: a tiny one in the hero's sky, one on the crest, one on the scroll, one in the deck's
   corner, and the slider thumbs are seals too.
5. The one red in My Space's room is a bud on the alcove's branch.
6. Happy Nox blushes in seal red; the fisherman in the hero is a single dot in a boat.

## Iterations

- **Hero, four times:** v1 had pines of ruled lines that read like characters and rain-like
  texture strokes; v2 drew pines in dabs and curved hemp strokes but the peak was a dome; v3 made
  a craggy sansui peak, stronger values for the phone's small band, and a seal that read like a
  letter was re-carved as a plum blossom; v4 softened the far ranges into wet edges, added a last
  faint range for air and moved the seal from the corner to the sky beside the peak.
- **Crest, three times:** a peak and sun in a ring read as the "image" placeholder icon; three
  bamboo leaves in a ring read, small, like a car maker's star; the ensō with its seal is
  unmistakable and says the idea in one stroke. The ensō moved from the scroll to the crest, and
  the scroll now carries bamboo.
- **Banners, three times:** large objects collided with header buttons (Watch) and a transparent
  banner let the header's room tint through as a grey smudge; they are now small, top right,
  above the buttons, on plain kinari.
- **Leaf shadows:** fish-tail fans, then leaves that read as letters when blurred, then hanging
  fans on a drooping twig; limited to Home after the first tour showed them behind page text.

## Round 2 (after review)

- Banners redrawn in the hero's hand (`Brush`: washes that pool and bleed, bristle strokes that
  run dry, no outlines), ~110 px tall, right third, transparent with `banner-wash` 0, full ink
  above the header's buttons and faint beside them; My Space's banner is empty (its room picture
  sits beside a narrower header).
- Rail: a real shoji: fibred paper lit from the top left, a kumiko lattice of thin walnut bars
  (mullions between the marks and the names, and after the names).
- Deck: a kraft label with a deckled top edge and a printed walnut double rule; seal on its corner.
- Incense: a stick in an ash bowl, a hanko ember, smoke that widens, curls and fades, varying.
- My Space: a true-perspective tatami room: 2:1 mats with heri on the long edges, a rhombus of
  shoji light, a square zabuton with thickness and shadow, ink contours on posts and lintel.
- TV: three-step walnut grain, mitred corners, lit top-left bevels, a soft shoji reflection.
- Hero: the boat moved under the peak (clear of the Ask field), the seal small and low by the
  hut, the peak's hemp strokes in varied groups, some broken.
- Washi fibres: half the contrast, shorter, mostly lighter than the ground.
- People and rooms retuned to natural dyes at C ≤ 0.07; info asagi, private kon.
- Pieces: avatars are motifs on a washi field in a fine ring; large red fills on medals became
  walnut or sumi with a small red cluster.

## Round 3: pokes (minimal, zen)

- The scroll moved from the `rail.art` slot to a `rail-foot` layer (`scroll-foot.webp`) so it
  can answer a click: `scroll-sway.webp`, eleven frames turning a few degrees about the nail and
  back.
- The incense bowl (deck, bottom right; only the bowl sits in the deck's clear padding, so that
  is where the click lands): `incense-puff.webp`, ten frames: the ember glows, one curl of denser
  smoke rises, widens and fades.
- Tested with a throwaway Playwright script (clicks, mid-reaction screenshots); `rail-scroll.webp`
  removed (unused).

## What I'd do next

- Ink contours on the My Space room so it shares the banners' hand.
- A seasonal variant: the leaf that falls could follow the month (bamboo, maple, ginkgo).

## Open requests

Surface anchoring (horizontal) and a `part.status.radius` (see REQUESTS.md).

## Known limits

- Light scheme only.
- Banners are hidden on phones (the centre crop) by design; phones keep the plain paper.
- Room banners are drawn for a full-width header; a narrow header would crop them.
