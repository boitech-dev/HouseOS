# Millennium Skin (Skin an 2000)

**Idea, one sentence:** the house wears a millennium media-player skin: gunmetal windows with
bevels and title-bar grips, pixel LCDs in green, a hot amber gel, chrome, and clear Bondi plastic
over a lilac sky; every word sits on a calm frosted or dark glass so it always reads.

**Three moments:**
1. **The music deck** (Listen, and Home's Now playing): a Winamp-2-era main window: an 18 px title
   bar with paired grip ridges, a lit LED, a rivet, a bevelled body, a sunken LCD well, and a
   spectrum set into the ridges that dances only while music plays.
2. **Home's hero:** chrome blobs, a clear Bondi keychain egg, an iridescent disc and a chrome star,
   rendered in Blender, floating on the matrix grid (dark) or in the lilac sky (light).
3. **The sky itself:** a perspective grid with a far horizon glow (dark), or lilac clouds that
   drift (light); four-point sparkles twinkle, and now and then a lens flare glides across.

## Tells (what makes it recognisable)

1. **1 px bevels:** a light line top-left, a dark line bottom-right on every raised thing; sunken
   fields the other way round. A black outline around each skin window.
2. **Title bars with grip ridges:** paired light/dark hairlines in a band across the top of a
   window, with a rivet at each corner.
3. **Pixel LCDs:** green segments on black glass with the unlit segments faintly visible; square
   mono digits (Kode Mono) for times and counts.
4. **Spectrum analyser:** stacked segment bars, green to lemon to red, with a floating peak cap.
5. **Gel pills:** a saturated colour, a bright top half ending in a hard line at the middle, light
   pooling at the bottom rim. Hover changes only the colour under the gloss.
6. **Translucent candy plastic:** Bondi blue, grape, ice; the inside visible, a speckle, a lit rim.
7. **Chrome:** high-contrast reflections, a sky-blue top, a dark horizon band, a white floor.
8. **Early-web sky:** lilac, puffy clouds, four-point star sparkles, a lens flare, a perspective grid.

## Spec

**Palette (OKLCH), two skins:**

| Role | Dark, "classic skin" | Light, "Bondi" |
|---|---|---|
| Ground | night blue 0.155 0.04 270 + grid picture | lilac 0.90 0.045 295 + sky picture |
| Surfaces | gunmetal 0.235 0.022 258, bevelled, black outline | ice plastic 0.985 0.012 240 at 80 %, white rim |
| Ink | 0.95 0.01 250 | navy 0.24 0.05 265 |
| The one accent | amber gel 0.80 0.155 66 (dark ink on it) | aqua gel 0.76 0.12 212 (dark ink on it) |
| Light / LCD | LCD green 0.86 0.20 138 (focus ring, playing, screens) | the same green on the LCD screens; blueberry focus |
| Statuses | lemon, strawberry, ice-blue LEDs | tangerine, strawberry, blueberry, lime |
| Rooms | candy flavours: Bondi, tangerine, blueberry, lime, lemon, grape, strawberry, graphite, sage, ice, flower, ruby, clear green | the same flavours, deepened |

**One light:** a cool white key light from the top left (a window of sky). Chrome reflects a lilac
sky above and a dark horizon; shadows fall to the bottom right, tinted navy. Bevels obey it.

**Medium and scale:**
- Renders (Blender, one studio: key top-left, a lilac rim from behind, chrome / translucent /
  plastic presets) for the hero, the crest, the empty-state toy and the TV set.
- Vector (SVG) for skies, grids, clouds and the lens flare.
- Pixel art at **2×** everywhere pixels show (sprites 16 px in their 32 px box, the skin frames, the spectrum, the sparkle, the
  LED): never mixed.

**Type:** Michroma (a wide techno display: name plates, titles, the brand), Lexend (body; wide
spacing like the UI fonts of the era, reads at 14 px), Kode Mono (square LCD digits).

**Shape language:** square windows (the pixel frame is the corner), 9 px bevel lozenges for
controls, full pills for chips, 3 px knobs on sliders (dark) and clear beads (light).

**Motion:** crisp (90 / 160 / 260 ms), a small gel bounce on emphasis. Ambient: clouds drift
slowly, sparkles twinkle, a lens flare crosses every couple of minutes, the spectrum only while
music plays. All of it stops with motion off.

## The house (every part)

| Place | Gets | Why |
|---|---|---|
| Sign-in | `auth.crest`: a chrome four-point star inside a clear Bondi orb | the skin's badge |
| Status bar | brushed metal (dark) or chrome-white plastic (light) via `part.status.texture`; the clock in LCD mono | a thin chrome bar; plain on purpose (search and clock live there) |
| Rail | `rail.surface`: a playlist-window skin frame (title-bar ridges, rivets, bevels); a power LED layer that blinks every four seconds; scheme grounds; its foot (`rail-foot` layers): a clear Bondi flip phone (closed) and the keychain egg, both pokeable | the skin's playlist window |
| Dock | `dock.surface`: a chrome lip (Bondi plastic by day); scheme grounds | a player's button row |
| Page | `page.backdrop` per scheme (grid at night, lilac sky by day), white clouds drifting by day, twinkling sparkles, a lens flare every 150 s; none of it in the Control Room | the early-web sky |
| Headers | framed: a square name plate (gunmetal / frosted ice), `part.header.frame-texture`: two grip-ridge pairs across its top band and a 1 px bevel lit top-left | a skin's title plate |
| Home | the hero render per scheme (chrome blob, keychain egg with Nox's smile, rainbow disc, chrome stars; a reflecting grid floor by night, puffy clouds by day) | cover picture |
| Listen | the deck skin (`deck.surface`), the windowshade spectrum (`playing`, Listen only), LCD segment sliders (dark), gel tubes (light) | moment one |
| Now bar | `nowbar.surface`: a mini-player strip with end caps | the player shrunk |
| Watch | `watch.tv.bezel`: a clear-plastic CRT; posters untouched | the era's TV |
| Games | covers on the gallery ground, room light clear green | plain on purpose |
| My Space | `space.room.scene`: a bedroom desk at night: a clear CRT, a lava lamp, a disc stack, a chrome star, a window of stars, a grape beanbag | a room of its time |
| Me | 5 avatars redrawn (chrome moon, a gunmetal bat, a glossy raven, a gem rose, an ice ghost), 20 medals as Y2K objects (headphones, globe, floppy-era PDA, trophy, heart gem, chip…), title names | the pieces |
| Control Room | the same windows, calm: no page layers there, LCD mono for numbers | dense and readable |
| Sheets, dialogs | square skin windows with ridged title bands; dark: gunmetal; light: frosted ice with backdrop blur | the translucency |
| Empty states | `state.empty`: a translucent keychain egg pet | a smile |
| Controls | brushed-metal bevel buttons, gel primary buttons, LCD segment sliders (dark), gel tubes (light), sunken LCD fields | the tells |
| Nox | a translucent Bondi keychain egg with an LCD face, 6 moods | the familiar |
| Rooms | a candy flavour each | the candy flavours of clear electronics of the time, generic names |
| Schemes | dark classic skin first, light Bondi second: separate grounds, materials, controls, sprites' colours | two skins |

## Pokes (desktop, a click; nothing shows they're there)

| Click | What happens |
|---|---|
| The clear flip phone at the rail's foot | it flips open, its LCD lights, a pixel heart beats twice, pink pixel hearts fly out, it folds shut |
| The keychain egg beside it | it swings on its ring and settles; lit LCD pixels scatter |
| The chrome star at the bottom right of Home's picture | it spins a full turn and throws sparkles |
| The spectrum in the deck's title bar (Home, Listen) | every bar jumps to the red and falls back |

## Do / Don't

- **Do** keep a frosted or dark glass under every word; bevel every raised thing; keep chrome for
  edges and objects.
- **Don't** put brand marks, logos or names anywhere; words in pictures; scrolling text; a busy
  picture under text.

## Sources

Every picture is drawn by code in `docs/design/themes/y2k/` (`make.py`, Blender scenes), original,
CC-BY-4.0. Fonts: Michroma, Lexend, Kode Mono (OFL, via Fontsource).
