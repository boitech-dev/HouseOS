# Legacy (carved-night): notes

Regenerate everything from the repository root:

```bash
python3 docs/design/themes/carved-night/make.py       # every picture → themes/carved-night/art (PAL locked)
python3 docs/design/themes/carved-night/pieces.py     # sprites.json (Nox, avatars, room marks, medals)
python3 docs/design/themes/carved-night/tokens.py     # tokens.json
python3 docs/design/themes/carved-night/manifest.py   # theme.json (slots and layers for the art present)
```

## What's in the theme

- **Pictures (pixel, one 3× grid):** Home hero (manor, moon with two solid rings and three thin
  twigs, fence, graves, lamp post, an ember pool on the path, Nox on a post); the page night
  (`sky.png` backdrop with the moon high left, cloud tile, 32-frame manor sheet with a ghost
  leaving the tower, 8-frame near garden with the owl, fog tile, bat); the shooting star; the
  status roofline and its 16-frame life (tail flick, chimney smoke); the keyhole crest; the stone
  column and the rail-foot side table with its candle (8 frames); eight room banners and three header layers (sconces,
  the blinking ancestor, the bedroom curtain with its ghost); My Space bedroom; cabinet TV;
  empty-state ghost; 9-slice frames for panels, sheets, the Now bar and the deck (a walnut
  wireless cabinet) and the deck candle's flame. 32 files, about 110 KB.
- **Pieces:** Nox the black cat (6 moods: happy has ^^ eyes and a blush, thinking has a thought
  trail), five avatars, nine room marks (the manor's lit windows readable now), twenty medals,
  their names in `flavor.json` (en, fr).

## Pokes (desktop)

- **Candle on the side table** (rail foot, 62 × 72 at ×3 = 186 × 216, fitted smaller on short screens; its flame a teardrop changing height, fullness and heat in place): flare and four sparks → gutter to a bead → out in a curl of smoke → relight (6 frames, 0.6 s).
- **Owl** (Home's picture, bottom right, on its post): eyes wide → head turns round and back →
  hoot, three feathers (10 frames, 1 s).
- **Roofline cat** (the status bar's free space): wakes, stands, arches, stretches, sits
  (8 frames, 1 s); the chimneys puff harder.
- **Deck candle** (the music player's bottom rail, by the right corner): flare → gutter → out
  in smoke → relight (6 frames, 0.75 s).
- **Ancestor's portrait** (Listen, Files, My Space, Ask): rolls its eyes up, right, left, then
  winks (8 frames, 1 s). Its piece is only the portrait's width.
- **Bedroom curtain** (Me): the ghost pops out startled, ducks back, the curtain's hem swings
  (8 frames, 0.9 s).
- Tested with a throwaway Playwright script clicking each piece (every one receives the click).
  The header's title line (the h1) still spans the whole width, so the portrait and the curtain
  answer below it (the portrait's lower half, the curtain's tie-back and hem).

## Discoveries

1. The ancestor's portrait blinks (Listen, Files, My Space, Ask).
2. A ghost slips out of the manor's tower window behind the pages and drifts down the garden.
3. Someone hides behind the bedroom curtain (Me) and peeks out now and then.
4. The owl on the near fence blinks; the roofline cat flicks its tail; two chimneys smoke.
5. Nox sits on the fence in Home's picture; a dollhouse of the manor stands in the attic.
6. A shooting star over Home; a bat crossing the pages; a ghost waves from the TV; a ghost
   under the covers in My Space; the deck's candle lights only while music plays.

## What I'd do next

- Header fixtures anywhere in the banner once layers follow its crop (REQUESTS 2).
- A light scheme ("Legacy at dawn") is possible but not planned: the idea is night.

## Known limits

- Cover-fit slots (hero, banners, room scene) scale pixel art by a fraction on some screens
  (0.95–1.14 on desktops, ~0.5 on phones at 1× DPR); on real phones (DPR 2–3) the pixels stay
  sharp. Layers are exact (whole-number scale).
- Phones show the banners' middle third behind the title: the portrait, a sconce or the
  dollhouse can sit beside a long title; objects are kept off the title's row where possible.
- The hero no longer uses the live hall scene (lit windows per person at home); the drawn manor
  is far richer and the "who's home" line under the greeting still counts people.
- The page scene is deliberately dim (scrim 66 %): it is felt at the margins, never behind text.
