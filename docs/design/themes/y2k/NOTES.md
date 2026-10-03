# Millennium Skin (y2k): notes

**Idea:** the house wears a millennium media-player skin. Dark is the "classic skin" (gunmetal
windows, bevels, LCD green, a hot amber gel, a matrix grid at night); light is "Bondi" (frosted ice
and clear blue plastic, chrome edges, aqua gel buttons, a lilac cloud sky).

## Regenerate

```bash
python3 docs/design/themes/y2k/tokens_src.py    # tokens.json, tokens.light.json
python3 docs/design/themes/y2k/manifest.py      # theme.json (slots, layers)
python3 docs/design/themes/y2k/sprites_src.py   # sprites.json (--preview out.png for a sheet)
python3 docs/design/themes/y2k/make.py          # every picture (skins pieces sky renders)
```

`studio.py` is the one Blender studio (the chrome environment, the key light top-left, the
materials, the keychain egg and the CRT); `scene_*.py` are the renders. `iterations/` keeps the
hero's versions (v1–v5 before the per-scheme split), the first renders and the final sheet.

## What's in it

- **Skins (pixel, 2×, 9-slice), gunmetal/chrome by night and Bondi plastic by day:** the deck as a
  Winamp-2-era main window (an 18 px title bar with paired grip ridges, a lit LED in a sunken
  socket, a rivet, a 2 px bevelled body, a sunken LCD well filled with opaque LCD glass: black by
  night, pale by day), the rail's playlist window, square panels and sheets with ridged title
  bands, the Now bar's mini player, the dock's lip, a grip-ridge seam under the status bar.
- **Renders (Blender):** Home's hero in two versions (chrome blob, the keychain egg with Nox's LCD
  smile, a rainbow disc, chrome stars, clear beads; over a glowing grid floor that they reflect by
  night, among puffy clouds by day), the sign-in crest (a chrome star in a clear Bondi orb,
  a chrome ring), the empty state (the keychain egg, its LCD lit inside the clear shell), Watch's TV
  (a clear CRT showing its tube, glowing neck and board, a pixel sunset on screen), My Space (a
  bedroom desk by night and by day: the CRT, a lava lamp, a CD tower, a clear flip phone, a speckled
  rug), the rail's foot (a clear flip phone, closed at rest: its board, chips and battery through the
  shell, a chrome barrel hinge; beside it the keychain egg).
- **Pages:** `page.backdrop` per scheme: a night grid (rays converging cleanly, the far ones fading)
  with a far lens-flare star (dark), a lilac cloud sky (light). Layers: white clouds drifting by day,
  8 twinkling sparkles (not in Home, Games or My Space), a lens flare, a gleam across Home's picture
  every 45 s, a blinking rail LED, the title-bar spectrum (Home and Listen, per scheme).
- **Controls:** brushed-metal bevel buttons, gel primary buttons (bright top half, hard middle
  line), LCD segment sliders (dark) and gel tubes (light), sunken LCD-glass fields.
- **Pieces:** Nox as a clear Bondi keychain egg with an LCD face (6 moods), 9 room marks (gel house,
  rainbow disc, clear CRT, clipboard, floppy, gel bulb, clear controller, chrome beads, gel buddy),
  gel transport keys, 5 avatars, 20 medals, title names in en and fr.

## Pokes (desktop)

- **Rail foot, the flip phone** (`scene_rail.py`, 12 frames): flips open, LCD lights, a pixel heart
  beats twice, 6 pixel hearts fly out, folds shut (0.9 s).
- **Rail foot, the keychain egg** (`scene_pokes.py`): swings on its ring and settles, 5 lit LCD
  pixels scatter (0.85 s).
- **Home's chrome star** (bottom right of the picture, clear of the words; `scene_pokes.py`): spins a
  full turn, 8 sparkles (0.75 s). The hero render no longer has its big star: this piece is it.
- **The deck's spectrum** (Home and Listen): every bar spikes to the red and falls (0.5 s).

`make.py pokes` renders the frames and stitches the sheets. Tested by clicking each piece in a
Playwright script (desktop, both schemes): each reaction plays, nothing else sits on top of them.

## Discoveries

1. The deck's **spectrum analyser is set into its title bar's grip ridges**, and moves only while
   music plays (on Home's Now playing deck too).
2. The rail's **power LED** blinks once every four seconds, over the playlist window's rivet.
3. A **lens flare** glides across the page every two and a half minutes.
4. The hero's keychain egg wears **Nox's own LCD smile**, pixel for pixel; the empty state is the
   same egg, and My Space's CRT and Watch's TV are the same set.
5. The rail's flip phone's strap ends in the chrome star that is also the crest's; open it (a click)
   and a **pixel heart** beats on its screen.
6. Sparkles twinkle between the windows; the Control Room has none of it.

## What I'd do next

- A dark-only layer for the grid (a slow pulse along the horizon) if it stays calm enough.
- Medals for a person holding titles were checked in the preview sheet only (the test account
  holds none): look at them on *Me* with a real title.
- The time in LCD green, once REQUESTS.md's `deck.time` lands.

## Known limits

- The sign-in page shows the crest on the plain ground (no page picture there).
- The deck's layers sit inside its 16 px side padding (measured), so the spectrum strip ends at the
  right cap's separator; if that padding rule changes, the strip moves by 16 px.
- The panel and sheet frame is one picture for both skins (translucent ridges that read on both).
- The tour sometimes photographs a blank page while another theme's build reloads the dev server;
  a second run is clean.
