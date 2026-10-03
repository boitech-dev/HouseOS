# Zabiwa · brief

- **Mood, in one sentence:** a black gallery wall at night hung with details of Zabiwa's fresques (gothic saints
  in gilt, a space-opera armada, a pop Tokyo avenue), and a quiet, exact interface in white type
  that never competes with them.
- **Names:** Zabiwa · Zabiwa
- **Scheme(s):** dark
- **Author:** Zabiwa (the artist; the art is theirs).
- **References:** the artist's own work and site (zabiwa.com: black ground, the spaced ZA•BI•WA
  wordmark, "Building worlds at scale."); a museum's night hang with picture lights; gallery wall
  labels; gilt reliquaries and halos; fulldome projection.
- **Material feel:** flat black lacquer; hairlines; the art is the only texture.
- **Shape:** sharp (3 px controls and cards, 6 px sheets); chips stay pills.
- **Edge:** hairline, 1 px, neutral greys; no shadows on surfaces.
- **Type personality:** Instrument Serif (condensed high-contrast display serif, gallery walls) for
  titles only; Instrument Sans (crisp grotesque, a gallery-label face from the same family) for
  everything read; JetBrains Mono for times and numbers. The house's name in the status bar is
  tracked wide, like the ZA•BI•WA wordmark.
- **Colour story:** neutral is true black to bone white (a hint of warmth, hue 85). The one accent
  is bone white: primary buttons are white with black type. Rooms are unified (every room's light
  is bone), because colour belongs to the art. Statuses and people take the fresques' inks: jade,
  gilt, vermilion, ultramarine, violet.
- **Identity:** line icons, 1.25 stroke. Pieces redrawn in the fresques' inks: Nox as a porcelain
  saint's mask in a black hood under a gilt halo (six moods); avatars as a crescent on ultramarine,
  a bat across a gilt moon, a raven before the moon, the vermilion rose, the white mask with the red
  cross; the fifteen titles as gilt medallions with bone and vermilion emblems; star mark ✦.
- **Motion personality:** crisp and still (100 · 180 · 260 · 380 ms, no overshoot).
- **Do:** let the art fill the big spaces (banner, hero, rail); keep every control black,
  white and hairline; veil the art wherever type lies over it.
- **Don't:** publish a whole painting (only details ship); tint, blur, stretch or upscale the art; put colour in the chrome; add glass or glow.

## Parts
header **framed** (the title in a black wall label with a cream hairline, over the saints fresque behind every page) · panel **card** (black #050505, a faint cream hairline and cream corner marks) ·
dock **flush** (black, hairline) · now bar **docked** (black, a stronger hairline) · rail black with
the full-height fresque.

## Art (Zabiwa's artwork, © Zabiwa: not under the theme's MIT licence)
Cut by `docs/design/zabiwa/art-src/cut.py` from the four originals, which stay outside the
repository (with the artist, never in any copy of HouseOS) and are never published: every file here is a
detail, none a whole work. Every crop is at the original's own resolution,
never upscaled, blurred or stretched; the only processing is a designed light map (multiply) where
type lies over the art, and WebP compression (quality ≥ 70) to stay within 200 KB per image.

| File | Slot | Size | From |
|---|---|---|---|
| `art/banner-spires.webp` | header.banner | 1500 × 210 | the cathedral fresque's top band: storm, spires, moon, gilt sun; veiled 30–55 % |
| `art/hero-panorama-full.webp` | home.hero.backdrop | 2000 × 469 | the whole gothic panorama, mirrored (the owner's choice): the hooded woman, the white-haired face and the red-eyed mask at the right, the cathedral fading under the words |
| `art/rail-nyc.webp` | rail.surface | 464 × 2400 | the owner's own rail picture (NYC, masked), given for the rail as a whole; anchored at the bottom, so a short window crops its top first |
| `art/crest-cross.webp` | auth.crest, state.empty | 250 × 250 | the crowned woman with the cross, gothic fresque; a round cameo in a gilt hairline ring (sign-in, opening the house, and every empty moment: the owner preferred it to the moon) |
| `art/tv-helmet.webp` | watch.tv.bezel | 480 × 360 | the boy in the bubble helmet |
| `sprites.json` | pieces | 16 × 16 | drawn by code, `docs/design/zabiwa/art-src/sprites.py` (MIT) |

The fresques carry some invented lettering on their signs (the Tokyo avenue): it is part of the
paintings, not information, and never needed to use the app.
