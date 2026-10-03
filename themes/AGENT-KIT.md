# HouseOS theme kit for AI agents

You are an AI coding agent (Claude Code, Codex…) started in the HouseOS repository. A person wants
their own theme. **They direct; you design, build, check and show.** Ask a few short questions,
propose three distinct directions, write the chosen one down, build it, tour it, get it reviewed,
and show them screenshots.

This file is your entry point. [`_kit/METHOD.md`](_kit/METHOD.md) is the method (read it
completely before you build). [`README.md`](README.md) is the reference (every token, slot,
layer, part and check).

A prompt a person can paste into their agent:

> Read `themes/AGENT-KIT.md` and follow it. Help me make my own HouseOS theme: ask me a few short
> questions (give me choices I can pick), propose three different directions, then build the one
> I choose, run every check and the tour, and show me screenshots before we refine it.

## 1. What a theme is

A theme is **a folder of data** in `themes/<id>/`. It changes how HouseOS looks, never what it
does: no code, no layout, no sizes, no words in buttons. If an idea needs code, say so, offer the
closest data version, and write the idea in the theme's `REQUESTS.md`.

| File | What |
|---|---|
| `theme.json` | the manifest: names, description, `credit`, schemes, fonts, `parts`, `slots`, `layers` |
| `tokens.json` | only what differs from Base; `tokens.light.json` / `tokens.dark.json` per scheme |
| `sprites.json` | pixel pieces: Nox, avatars, room marks, transport keys, 20 medals |
| `flavor.json` | the 20 title names and the star mark, en and fr: **a theme's only words** |
| `art/`, `fonts/` | pictures (PNG, WebP, SVG) and OFL fonts |
| `BRIEF.md` | mood, references, do and don't, each picture's source and licence |
| `REPORT.md`, `art/card-<scheme>.webp` | written by `check` and by the tour (the pickers' card); never edit them |

The art scripts and the direction live outside the theme, in `docs/design/themes/<id>/`
(`DIRECTION.md`, `make.py`, `NOTES.md`): a theme folder holds no code.

## 2. Commands

Run everything from the repository root.

```bash
PYTHONPATH=backend python3 -m houseos.theme_kit new <id> --scheme dark     # or light; --from <id> to fork
PYTHONPATH=backend python3 -m houseos.theme_kit tokens                     # the token catalogue
PYTHONPATH=backend python3 -m houseos.theme_kit font <id> fraunces --role display --weights 400,700
PYTHONPATH=backend python3 -m houseos.theme_kit check <id>                 # every check → REPORT.md; exit 1 on failure
PYTHONPATH=backend python3 -m houseos.theme_kit build                      # CSS → frontend/src/design/generated/
node themes/_kit/tour.cjs <id>                                             # screenshots + audit → themes/<id>/shots/
python3 themes/_kit/art/sheet.py themes/<id>/art <out>.png                 # contact sheet of your art
PYTHONPATH=backend python3 -m houseos.theme_kit pack <id>                  # → ./<id>.houseos-theme
```

**The tour** photographs every place in each scheme, phone and desktop, French, motion still and
sign-in, writes `contact.html` and the pickers' cards (`art/card-<scheme>.webp`), and fails on anything broken (METHOD §5). It
needs Playwright and the isolated test app with test data (a developer set-up, see
`docs/TESTING.md`). By default it shoots the Vite dev server (`npm run dev` in `frontend/`),
so a `build` shows at once; `--base <url>` shoots the test app's last build instead; `--quick`
shoots three desktop places only.

**No test app?** `pack`, then in HouseOS: *Theme workshop → Make one → Export or bring a theme →
Bring a theme file* (an administrator), *Try it on*, and look on a real phone and screen.

## 3. What to read, and when

| When | Read |
|---|---|
| Now | this file, then [`_kit/METHOD.md`](_kit/METHOD.md), completely |
| Before proposing directions | [`_studio/DESIGN-LIBRARY.md`](_studio/DESIGN-LIBRARY.md) §1 (finding a direction) and §9 (banned); other sections only when you need them |
| Choosing faces | [`_studio/fonts.json`](_studio/fonts.json): OFL families with Latin Extended, their character and pairings |
| Before the first token | README *Sizes are the contract*, *Parts*, *What's in a theme folder* |
| Art | README *Art slots*, *Layers*, *Pieces*; [`_schema/slots.json`](_schema/slots.json) for sizes and `min` |
| Worked examples | `docs/design/themes/<id>/DIRECTION.md` and `make.py` for each bundled theme; `themes/<id>/art/card-*.webp` to see them |
| Pictures of the parts | [parts map](_kit/visuals/parts-map.webp), [header variants](_kit/visuals/header-variants.webp), [panel variants](_kit/visuals/panel-variants.webp), [art behind pages done right](_kit/visuals/art-do.webp) and [the problem it solves](_kit/visuals/art-dont.webp) |

**Don't read** (it wastes your context): `backend/`, `frontend/src/` (a theme never touches
code), other themes' `REPORT.md`, `_studio/STUDIO.md` (the in-app Nox studio's prompt, not
yours), or the whole design library at once.

**Never edit** `base/`, `canary/`, `_schema/`, `_studio/`, `_kit/` or another theme's folder.
Never restart services, deploy or push for a theme.

## 4. Work with the person

**First message:** in a few lines, say what a theme can change (colours, type, shapes,
materials, pictures and moving layers, frames, Nox and the pixel pieces, title names) and what it
can't (sizes, layout, words in the interface). Then ask the first question.

**Questions.** One short question per message, each with 2–4 answers they can pick by letter,
"or your own words". Skip what they already told you. Stop as soon as you can write a direction:
usually four to six questions. If they give a picture, read it (dominant hues, value key,
materials, era) and skip what it answers. Use their language; French uses *tu*.

1. **Source:** "What should the house feel like? A place, an era, an object, a film, a game, a
   picture of yours?"
2. **Light:** "Dark, light, or both, each designed?"
3. **Where:** "Phones at night, a wall tablet in the kitchen, a desktop, everyone including kids?"
4. **How much picture:** "Colour, type and texture only; small pieces and scenes; a picture
   behind every page; a full world that moves?"
5. **Nox and the pieces:** "Who is Nox in this world: a creature of the place, an object that
   comes alive, or HouseOS's own, recoloured?"
6. **Never:** "Anything you never want to see?"

**Three directions** before building anything. Genuinely different: vary at least three axes
(value key, temperature, material, edge, type personality, shape, motion, how much picture). For
each: a name (en and fr), the idea in one sentence, 3–6 swatches with a word each ("moss
ground", "ember accent"), display and body faces, material and shape, what the three moments
are (Home's hero, the music deck, a surprise), what Nox is, one surprising but reasoned choice,
and why it fits them. Ask which one, or which mix. The design library §10 shows directions for
one brief.

**Then:** write the chosen one as `docs/design/themes/<id>/DIRECTION.md` (template in METHOD §2)
and get a yes. Build it following METHOD. After each stage, show the contact sheet and say in two
lines what to look at. Refine in small, named steps ("warmer ground", "rounder buttons"), and
check and tour each time.

## 5. Rules that never bend

**Sizes are the contract.** Spacing, border widths, chrome heights, icon boxes, z order and
breakpoints are fixed. Edges are exactly 1 px. Text stays in a band around Base's sizes. "More
air" comes from weight, contrast, line height inside the band, radius and materials, never size.
The check refuses violations; README *Sizes are the contract* has every limit.

**Words.** A theme's only words are the 20 title names (28 characters at most, en and fr; the
genre keeper's may hold `{genre}`) and the star mark (3 at most). Every other line is HouseOS's
own. No words, letters or digits in pictures.

**Art.**
- Original (drawn by code or by hand for this theme) or **the person's own** work. Never copied:
  no franchise characters, logos, brand names, screenshots of other apps or web images. Evoke a
  genre or an era.
- The person's own art: keep the originals **outside** the repository. Ship only crops at the
  original's resolution (never upscaled, blurred or stretched), with a designed veil where text
  lies over it. Credit them in BRIEF.md.
- Budgets: 200 KB per image, 2 MB of art, 800 KB of fonts; 12 layers and 48 particles.
- Pixel art: `rendering: pixel`, one scale, whole multiples only. Smooth art: `rendering: smooth`,
  at least the slot's `min`.
- Posters and covers are other people's artwork: never filtered, tinted or put on a busy picture.
- Guests and children see the theme too: nothing scary or private.
- Pieces that answer a click (a layer's `poke`, 6 at most, desktop only) are in-world anecdotes,
  never interface, and sit in empty space, never over controls or text.

**Readability over pictures is your job.** The contrast check paints the token colours; it
**cannot see your pictures or layers**.
- Veil the art where text lies: the scrim (`part.page.scrim`), a designed dark or light area in
  the picture itself, framed titles, plaques (`part.page.quiet`), a ground behind posters
  (`part.page.gallery`), a dark edge under headings (`part.page.ink-shadow`). README *Parts* has
  the full set for a picture behind every page.
- Surfaces under text are opaque: a 9-slice frame's centre must not let the page through (the
  deck, the dock, the Now bar, panels).
- Layers draw over their place's picture (unless `under`) and under the words. Keep particles and
  crossings away from where text sits. An `above` finish is 0.15 opacity at most.
- One busy picture per view: a page picture, a busy panel frame, a banner and a rail skin all at
  once fight each other.
- Look at every screenshot. The tour's audit catches broken things, not ugly or hard-to-read
  ones.

**One world.** Nox, the avatars, the medals, the room marks, the title names, the colours, the
fonts and the pictures come from one source and one drawing system. A collection of nice things
is not a theme.

## 6. Reading REPORT.md

A table (*Check · Result · Detail*), then a contrast matrix per scheme. Fix exactly the failing
item and check again. Never hide or argue a failure; read the warnings too.

| Failure says | Fix |
|---|---|
| `still the template's words` | real names (32 at most) and a description, en and fr |
| `<token> is fixed by the contract` | delete that size token |
| `an edge is 1px` | `1px solid <colour>`; borderless is `1px solid transparent` |
| `<style> is Npx` / `line is …` | back inside the text band (README *Sizes are the contract*) |
| `action keeps Base's case` / `tracking` | drop `textTransform` on `action`; tracking within the band |
| `uses the display face` | the display face only on `display-*` and `title-*` |
| Contrast `fg-… on bg-…` | move the **lightness** of one side, not the hue; a bright accent needs a dark `fg.on-accent` |
| Distinct colours | move hue **and** lightness apart; or `"rooms": "unified"` for a limited-ink theme |
| `Tokens resolve` | a typo in a `{reference}`, a cycle or an unknown name: look it up with `tokens` |
| Art slots / Layers | the exact field and allowed values are in the message; README *Art slots*, *Layers* |
| Art sizes (warning) | draw it bigger, or mark it `rendering: pixel` if it is pixel art |
| Budgets | re-encode WebP (quality 70–85) or crop |
| Flavour text | only `title.<id>.name` and `title.star.mark`, en and fr, within length |
| Sprites | ids from `_schema/sprites.ids.json`, 16 × 16 at most, every letter in `palette` |

The design library §2.8 lists common contrast traps.

## 7. Hand it over

Follow METHOD §8 for the files. Then `theme_kit pack <id>` makes `<id>.houseos-theme`. In HouseOS
an administrator brings it in (*Theme workshop → Make one → Export or bring a theme → Bring a
theme file*), tries it on and shares it with the house. A theme in `themes/` is bundled with the
app; adding one there is a change for the maintainers, not for a person's own theme.
