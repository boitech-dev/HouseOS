# The Vampire's Keep (night-castle): notes

Regenerate everything: `python3 docs/design/themes/night-castle/make.py` (palette.py, lib.py,
hero.py, page.py, frames.py, banners.py, slots.py, pieces.py, data.py). All art is pixel art
drawn by code, native size, one scale (× 3), locked to a 15-bit SNES palette. 25 files, ~33 KB.

## What's in it

- **Page (parallax):** night sky with stars and a dusk horizon (cover layer); the far castle on
  its crag before a huge veiled moon (natural, bottom-right, depth .15, 75 %, not on Home or the
  Control Room); flat SNES clouds drifting; a ruined balustrade with an urn and ivy (depth .45);
  three bats crossing every 45 s. Scrim 66 %.
- **Home hero:** a flying staircase on pointed arches climbing out of the mist to the keep's
  open gate, braziers on the newels, a dead tree, a far watchtower; the sky, moon and cloud
  streaks are a hero layer, and bats cross the moon every 24 s.
- **Frames:** one 9-slice family (gold, groove, stone or crimson velvet, ruby bosses) for panels,
  the rail, sheets, the Now bar and the dock; stone ashlar texture; battlements on the status bar.
- **Banners (a wing per room):** great hall with leaded windows (default), chapel with organ and
  rose window (Listen), library (Files), clock-tower gears (Control), throne room (Me, My
  Space), armoury of sub-weapons (Games), portrait gallery (Watch). Every title sits on dark wall.
- **Slots:** crest (crimson shield, gold cross, bat wings, crown of spikes); empty state (a
  candle in a sconce, a bat asleep under it); the TV as a gilded frame with the moon; My Space
  as a bedchamber; a candelabrum shrine at the rail's foot.
- **Pieces:** Nox as a violet bat familiar (6 moods); moon, bat, raven, rose, ghost avatars;
  room marks (keep, organ pipes, gilded frame, key, tome, lantern, chest, cameo, studded door);
  gold HUD transport keys; 20 relic medals (lute, torch, crescent, sun, chalice, shield,
  stopwatch, hourglass, bell, axe, the wall roast, grimoire, quill, dagger, key ring, crown,
  heart, holy water, cross, crystal orb).
- **Controls:** stone-bevel buttons, crimson primary with a gold edge, gold focus ring (the
  game cursor), segmented health-bar meters on a blood-dark track, square slider thumb.
- **Type:** Grenze Gotisch (titles), Vollkorn (reading), DotGothic16 (numbers, the HUD).
- **Words:** titles as a hunter's feats; levels counted in hearts (♥).

## Discoveries

1. Bats cross the hero's moon every 24 s (and the page's sky every 45 s).
2. A gargoyle with one red eye crouches on the stair's first newel.
3. Far on the ridge, a ruined watchtower still has one window lit.
4. My Space has a coffin in the corner, lid ajar.
5. The grocery runner's medal is the roast found in the wall.
6. The empty state's bat is asleep under the candle, smiling.
7. Embers rise from the music deck only while something plays.
8. The keep's crimson pennant blows away from the moon; the relic's heart glows after the whip.

## Iterations

The hero was drawn four times (`iterations/` keeps v3 and the final v4; v1 and v2 were judged in the session and overwritten): (1) stair as a blob, red checker glows, no read;
(2) balustrade and arches, but a flat mass under the stair and a boxy gate; (3) ashlar courses,
a pointed gate, a spire with a pennant, cracks in the crag; (4) the sky layer made shorter with a
smaller, higher moon so phones keep it inside their 112 px band. Banners were moved right of
the phone's centre third after the first tour; the far moon was veiled after the first tour
(it sat behind text on phones); VT323 was replaced by DotGothic16 (VT323 read too small at 15 px).

## Round 2 (after review)

Banners rebuilt on one wall: rib vaults with cobwebs, a tapestry and two hanging banners behind
the title (each wing its own colours), torches on the pilasters, props moved to 46–76 % of the
width with their lower half in cast shadow (phone subtitles cross them), and a dark velvet
curtain over the right quarter where header buttons sit; `banner-wash` 0.2. My Space has its
own quiet banner and a redrawn chamber (whole coffin with the lid ajar, banded firelight, a
pointed window with the moon). The rail foot is now a flickering layer: a two-light lancet with
a quatrefoil, 1 px leading, two-step panes, one glinting pane, candles on the sill. The deck is
a crimson-velvet reliquary (deck.surface) with a candle flickering in each bottom corner and
3 × 3 embers (screen blend) while playing; a torch flickers on the status bar's wall walk. The
far moon is at 42 %. Nox is a bat with ribbed wings; each mood's eyes differ. The sky moved to
page.backdrop. 11 layers.

## Pokes (desktop, a mouse; nothing hints at them)

| Click | What happens |
|---|---|
| The shrine at the rail's foot (a candelabrum on a draped altar) | the whip: the three candles flare and burst, a heart drops from the candelabrum onto the altar and bounces, the relic's heart brightens, a few hearts fly (the genre's classic) |
| The gargoyle perched at the hero's top-right corner, by the moon | its eye kindles red, it spreads its wings and hisses; five tiny bats scatter |
| The torch on the status bar's wall walk | it roars up and settles; sparks fly |
| Either votive in the music deck's bottom corners | a breath bends the flame, it dies to a red wick, smokes, and catches again |

The rail's foot is a compact shrine (70 × 68 native, × 3 = 210 × 204, whole-scaled down on short screens): a gold candelabrum of three flickering candles on a crimson-draped altar in a pointed niche, a heart reliquary at its foot (railfoot.py); the old stained-glass window was removed. The deck
candles became 5 × 5 votives so they sit inside the deck's 16 px padding, where a click reaches
them. 12 layers, 5 pokes.

## Next

- Particles can't take frames, so the embers don't twinkle.
- A light scheme would be a second design (the castle by day, under storm light), not an inversion.

## Known limits

- The hero and banners are scaled by the app with `cover`, so their pixels land near × 3, not
  exactly (≈ 2.9 on a 1440 desktop, ≈ 1.5 for the hero on phones).
- Header action buttons (Watch, Games, Files) sit over the right end of their banners.
- The page moon shows through gaps between panels; it is veiled and scrimmed to stay quiet.
