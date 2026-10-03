# Making a theme that is authored, not generated

This is the method for making a HouseOS theme worth wearing, for a person with an AI agent or an
agent working alone. [README.md](../README.md) is the reference (every token, slot, layer, part
and check). This page is how to use it well. Read it once, completely, before you start.

A theme is **a world the house lives in for a while**. It is not a colour swap, and it is not one
big picture with defaults everywhere else. A good theme has one clear idea, carried into every
corner of the house, with things to discover. Every screen stays as readable and quick to use as
in Base.

The loop: **study → direction → plan → art → build and tour → self-critique → review round →
fix → tour → review again → hand over.** The review round is not optional: in every theme made so
far, the first review asked for another round, and the second round was clearly better.

## 0. What you can use

| Lever | Where | For |
|---|---|---|
| Colours, type, radius, shadows, materials, motion timing | `tokens.json` (`theme_kit tokens` lists all) | the whole feel |
| Buttons and sliders | `part.control.*`, `part.meter.*` tokens | gloss, bevels, segmented bars, square thumbs |
| Home's picture box, the banner's room tint | `part.hero.width`, `part.hero.fade`, `part.header.banner-wash` | how the hero and banners sit |
| Part variants: header, panel, dock, Now bar | `theme.json` `parts` | how the frame is built |
| Art slots: crest, status strip, Home hero, page backdrop, header banner, empty state, rail foot, TV bezel, My Space | `theme.json` `slots` | pictures in fixed places |
| Surfaces: rail, dock, Now bar, panels, sheets, **the music deck** | `slots` `<part>.surface`: cover, contain, stretch or a 9-slice frame | a part's own skin |
| "Where you are" (the rail's current room, the settings menu's page) | `color.bg.current`, `color.fg.current` | an inverted block, a stamped tab |
| A picture **per room** or **per scheme** | a slot fill's `"rooms": {"listen": "art/…"}` (or `{"listen": {"dark": "art/…", "light": "art/…"}}`) or `"schemes": {"light": "art/…"}` | a banner for each room, a day and a night picture |
| **Layers**: pictures the app moves | `theme.json` `layers` | steam, bats, clouds, a train, grain |
| Pieces that answer a click | a layer's `poke` (6 at most) | the cat stretches, the candle flares |
| Who made it | `theme.json` `credit` (en, fr, 40 characters, plain text) | a small line at the rail's foot |
| Pixel pieces: Nox's 6 moods, 5 avatars, room marks, transport keys, 20 medals | `sprites.json` | the house's small drawings |
| Title names and the star mark | `flavor.json` | the only words a theme writes |

**Layers, in short.** A layer is `{"image": "art/…", "where": "page"}` plus how it sits and
moves. `where` is page, hero, header, rail, rail-foot (a box above the Ask Nox card), status or
deck. Each layer has one way of moving:
`drift` (a seamless tile that pans), `cross` (a piece that crosses now and then) or `particles`
(the image repeated as steam, snow, sparkles). `frames` animates a sprite sheet. `depth` adds
parallax. `playing` moves it only while music plays. A layer draws **over its place's picture**
unless it is `"under": true`. `"above": true` puts a faint finish (0.15 at most) over the whole
page. `poke` makes a natural piece answer a click once (a reaction sheet, maybe a small burst):
desktop with a mouse only, never at motion still, 6 at most, placed in empty space, never over
controls or text. At most 12 layers and 48 particles. Every field and limit: README *Layers*.

The person's motion level decides how much moves: **still** shows first frames only (no
crossings, no particles), **subtle** (the default) adds drift, frames, crossings and half the
particles, **full** adds all the particles and parallax.

## 1. Study: find the tells

Before any colour, write down the **five to eight tells** of the aesthetic: the details that make
someone recognise it at a glance. Name real references from memory: artists, objects, places,
games, software, printed matter. For each, say what exactly makes it work: palette, light,
materials, shapes, type, surface texture, rhythm. Vague words ("modern", "clean", "cozy") are not
tells. "A 1 px highlight top-left and a 1 px shadow bottom-right on every control" is a tell.

Then decide **one idea** the whole theme serves, in one sentence, and **three moments**: the
places where the theme shows off most (usually Home's hero, the music deck and one surprise).

## 2. Write the direction

The direction is the most important document. Agents did far better work from a concrete
direction than from a mood word. Write it in `docs/design/themes/<id>/DIRECTION.md` before you
draw anything, and get the person's yes. It is also what the reviewer reads (step 7).

```markdown
# <Name> (<id>): direction

**The person's words:** what they asked for, quoted, if they said something specific.

**Idea:** one sentence (a place or object, its light, its material, one telling detail),
then two or three lines on what the house feels like.

**Tells:** 5–8 concrete details that make the aesthetic recognisable.

**How it differs:** from the nearest existing theme (palette, fonts, material).

**Palette:** 3–5 ramps, each colour's role (ground, surface, ink, the one accent, light,
shadow). Schemes: dark, light or both; the second scheme is its own design.

**Light:** where it comes from, its colour, how shadows fall.

**Type:** display, body (reads at 14 px), mono. Candidates from _studio/fonts.json.

**Medium and scale:** pixel art at one scale (say which), or vector at one stroke weight,
or renders with one camera and one set of materials.

**Shape and motion:** corners, edges, depth; timing and easing; what moves at first sight
and what is a rare surprise.

**Art, part by part:** page, Home hero, header banners (per room), rail, dock, the music deck,
Now bar, panels and sheets, status strip, crest, empty state, TV bezel, My Space.

**Controls:** buttons (part.control), sliders and bars (part.meter), focus ring.

**Pieces:** Nox (6 moods), the 5 avatars, the 20 medals, room marks, transport keys.

**Discoveries:** three or more small things that reward a second look.

**Never:** what this theme must not do (words in pictures, brand names, mixed pixel sizes…).
```

Short is fine. Concrete is what matters: "a noren curtain swaying in the banner, with a radio on
the counter in Listen's" beats "a Japanese feel".

## 3. Plan the house: nothing left to defaults by accident

The direction's part-by-part plan must cover **every place below**. A place may stay plain on
purpose (the Control Room should be calm), but only on purpose.

| Place | Think about |
|---|---|
| Sign-in | the crest (`auth.crest`): the first thing a guest sees |
| Status bar | its strip (`status.backdrop`), status layers |
| Rail (wide screens) | its surface, its foot (`rail.art`, a `rail-foot` layer), rail layers, the current room's look, the `credit` |
| Dock (phones) | its surface, the room marks, a surface that doesn't let the page through |
| Page | ground, texture, backdrop picture, scrim, page layers, an `above` finish |
| Headers | the part variant; banners per room (`header.banner` with `rooms`); `banner-wash` |
| Home | the hero (`home.hero.backdrop` + hero layers): the theme's cover picture |
| Listen | **the music deck** (`deck.surface`, deck layers, `playing`), the queue, the Now bar |
| Watch | the TV bezel; posters stay untouched (never filter other people's artwork) |
| Games | the covers grid, the catalogue |
| My Space | the room scene (`space.room.scene`) |
| Me | the 5 avatars, the 20 medals and their title names |
| Control Room | dense forms and tables: calm, readable, still recognisably this theme |
| Sheets, dialogs, toasts, menus | their material and frame |
| Empty and loading states | `state.empty`: a small picture with a smile in it |
| Controls | buttons (`part.control`), fields, switches, sliders and bars (`part.meter`), focus rings |
| Nox | 6 moods at 16 × 16, each different at a glance; idle and blink make its animation |
| Pokes | small things that answer a click, in character (`poke`): anecdotes from the world, never interface |
| Rooms | a colour per room (`color.room.*`), or one for all (`"rooms": "unified"`) |
| Schemes | dark, light or both: a second scheme is a second design, not an inversion |

## 4. Make the art

Draw with code, in `docs/design/themes/<id>/`: one `make.py` (and scene files) that regenerates
every picture into `themes/<id>/art/`. Then iterations are cheap, and a reviewer's fixes are
edits, not redraws from scratch. The toolkit is in `themes/_kit/art/`:

- **`pixel.py`:** `ramp()` for hue-shifted ramps, `Palette().lock()`, `grid()` sprites from text,
  `outline()`, `dither()`, `bands()`, `speckle()`, `sheet()` for frames, `nine()` for 9-slice
  boxes, `scale()` and `save()`.
- **`svg.py`:** write an SVG and `render()` it to PNG or WebP at the exact size. Gradients,
  `feTurbulence` paper and grain, and blur all work. `add_grain()` and `limit()` too.
- **`blender.py`:** headless 3D scenes with presets for chrome, brushed metal, plastic,
  translucent, glass, concrete and paper, plus a camera, lights and `finish()`.
- **`sheet.py`:** a contact sheet of your art at 1× and zoomed. **Look at it** after every change.

**Craft rules**

- **Pixel art:**
  - One pixel scale for the whole theme. Draw at native size and scale by whole numbers only.
  - `cover` scales a picture by fractions: draw pixel art at the box's real height where you
    can, and never mix a 2× hero with a 4× page.
  - Clusters, not noise. Readable silhouettes first, then shading.
  - Hue-shifted ramps, 2–4 shades per material. Lock every picture to the palette.
  - Anti-alias by hand, on curves only. Dither only for gradients and textures.
  - Outlines dark, selective where light hits.
- **Vector:** optical alignment, one stroke weight, consistent corner radii. Add grain or paper
  so flat fills don't look plastic.
- **Renders:** one light setup, believable roughness, composed for the box and its anchor.
- **Size of details:** if it can't be seen at 1×, it doesn't exist. No 1–2 px screws, no Nox
  moods that differ by one pixel, no discovery hidden on a 10 px screen.
- **Phone crops:** banners crop to their middle on phones. Keep a banner's subject in the band
  that survives (about 45–75 % of the width, the top 60 % of the height) and the far right calm,
  where the header's buttons sit. Nothing may touch the title or sit under a button.
- **Every picture:**
  - Original, drawn for this theme, or the person's own work. No logos, brands or characters
    from anywhere.
  - **No words, letters or digits in pictures.** Names come from the interface, in the person's
    language.
  - Within budgets: 200 KB per file, 2 MB of art, 800 KB of fonts.
  - Smooth art at least the slot's `min` size, never upscaled.
- **Iterate:** draw the hero piece at least three times. Keep the best, and say why it is better.

## 5. Build and tour

```bash
PYTHONPATH=backend python3 -m houseos.theme_kit check <id>     # REPORT.md: must PASS
PYTHONPATH=backend python3 -m houseos.theme_kit build          # the app's CSS
node themes/_kit/tour.cjs <id>                                 # screenshots + audit
```

The tour photographs every place (Home, Listen, Watch, Games, House, My Space, Me, Inbox, Files,
three Control Room tabs) in each scheme, on a phone and a desktop; Home, Listen and the Control
Room in French on a phone; Home with motion still; and the sign-in page. It writes
`themes/<id>/shots/` (with `contact.html`) and the theme's cards, `art/card-<scheme>.webp`. It fails on anything
broken: the page scrolling sideways, text cut off, a control off screen, a layer covering a
control, contrast problems, a missing focus ring, a page error. `--quick` shoots only desktop
Home, Listen and the Control Room, for fast iterations.

**Open the screenshots and look at every one**, at full size where detail matters. Passing the
checks is not the same as being good. Show the person the contact sheet after each stage, and
take their notes before going on.

A theme never needs a service restart, a deploy or a push. Stop only processes you started.

## 6. Self-critique

Judge the tour against the rubric below as a demanding art director would. Then go through the
common failures. Write down what is weakest, fix it, and tour again.

**Rubric** (score each 1–10):

1. **Readability:** every text comfortable at a glance. No text on busy pictures (scrims, solid
   surfaces, plaques). Contrast passes with room to spare.
2. **Usability:** controls look like controls; selected, hover, focus and disabled are obvious.
   Nothing cut off or crowded. French fits. The Control Room is calm.
3. **Cohesion:** one palette, one light, one pixel scale or stroke, one voice across every part.
   Nothing looks borrowed from another theme.
4. **Craft:** pictures that hold up zoomed: clean clusters, intentional edges, believable
   materials, compositions made for their box.
5. **Depth:** every part considered; three or more discoveries (a detail that rewards a second
   look, a layer that surprises once in a while).
6. **Restraint:** motion gentle and optional, effects that serve the idea, budgets kept.
7. **Would the person love it:** does it look like what they asked for, done better than they
   imagined?

**Common first-round failures** (check each one):

- [ ] **One great Home picture, everything else thin.** Banners, the music deck, My Space, the
      TV, the rail get far less craft and read as placeholders.
- [ ] **Details too small to see** at 1× (see *Size of details*).
- [ ] **Text touching or sitting on art:** banner props under header buttons or touching the
      title; sparkles over words; page art showing behind text on phones.
- [ ] **Phone crops:** banner subjects cut off or orphaned on a phone.
- [ ] **Pixel scale drift:** fractional `cover` scaling, or two pixel sizes side by side.
- [ ] **Surfaces that let the page through:** a transparent 9-slice centre under text (the deck,
      the dock, the Now bar).
- [ ] **Layer stacking assumed wrong:** layers draw over their place's picture unless
      `"under": true`.
- [ ] **The room tint behind banners** left on by accident (`part.header.banner-wash`: 0 for
      none).
- [ ] **Off-palette leftovers:** default avatars, a selected or current state in the accent's
      soft tint (`color.bg.selected`, `color.bg.current`), a fourth hue from a status seed.
- [ ] **Two drawing systems:** Nox and the pieces must be drawn like the pictures (not a bottle
      when the hero shows an egg).
- [ ] **Motion nobody sees:** a crossing every 150 s is a fine surprise, but with motion on,
      something should also be alive at first sight.
- [ ] **A maximalist idea gone timid:** use the budget (2 MB of art, 12 layers, 48 particles)
      when the idea asks for it. A minimal theme does the opposite, on purpose.

**Generic signs to hunt down:** one big picture with defaults everywhere else; default font
pairings (Inter with Inter); muddy mid-tones and grey-on-grey; random gradients and glassy blur;
emoji or clip art as art; mixed pixel sizes; decoration with no reason in the idea; words baked
into pictures; everything at full saturation; the same radius and shadow as every other app.

## 7. Review round

Self-review is not enough: you see what you meant to draw. After your own pass, get a
**fresh-eyed review**. The reviewer is another agent (a sub-agent, a new session) or a person, who
has not seen your work in progress.

**Give the reviewer only:** the direction, the rubric and the common failures above, and the
tour's screenshots (the contact sheet, and the images at full size). Not your notes, not your
reasoning, not the code.

**Ask the reviewer for:**

1. A score from 1 to 10 for each of the seven rubric criteria, with one line of reason each.
2. **Keep these:** what works and must survive the next round.
3. **Fixes, in priority order:** concrete and located. "The Listen banner's radio sits under the
   search button on a phone: move it left of 75 %" — not "improve the banners".
4. A verdict: **ship**, or **another round**.

**Then:** fix in priority order (edit `make.py` and the tokens; don't redraw from scratch), tour
again, and send the new screenshots to a reviewer for the next round. Do at least one review
round; expect the first to say "another round". Stop when the verdict is ship and the person
agrees.

## 8. Hand over

- **`docs/design/themes/<id>/`:**
  - `DIRECTION.md`, kept up to date with what changed.
  - `make.py` (and its scene files): regenerates every picture.
  - `NOTES.md`: what's in the theme, the discoveries, what you'd do next, known limits.
- **`themes/<id>/`:**
  - `BRIEF.md`: the mood, references, do and don't, and every picture's source and licence.
  - `REPORT.md`: written by `check`, PASS.
  - `art/card-<scheme>.webp`: the picker's card, written by the tour.
  - `REQUESTS.md` (optional): what the theme wanted that needs code, with the part and why.
- **The picker card:** `names` in en and fr, 32 characters at most. A `description` in en and fr
  that says the idea plainly in one sentence (keep it under about 90 characters; French uses
  *tu* if it addresses anyone). A `credit` (en and fr, 40 characters) if the person wants their
  name at the rail's foot.
