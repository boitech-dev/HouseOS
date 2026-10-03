# Legacy (carved-night): direction

**Idea:** HouseOS's first home, now fully haunted. A moonlit Victorian manor on a hill, carved in
stone, lit by embers and candles, where friendly ghosts keep house. Cosy-spooky, domestic and
warm inside, cold blue night outside. It is the default theme: the first impression of HouseOS.

**Tells:**
- **The house:** a manor silhouette with lit windows against a huge moon; dead trees; a wrought-
  iron fence; fog rolling at ground level.
- **Life around it:** bats; an owl; a ghost drifting behind a curtain; portraits whose eyes follow
  (or blink).
- **Inside:** a parlour with a gramophone, a dusty screening room, a library with ladders, a
  cellar, candelabras and a hearth.
- **The look:** carved stone bevels (the existing hard inset bevels are good: keep and refine);
  pixel lettering (Jacquard 12 display is its signature; keep it).

**Colour theory:** complementary.
- **Night:** moonlight violet-blue ramps (hue-shifted toward blue in shadows) for the night and
  stone.
- **Light:** ember orange and candle yellow for light and the accent.
- **Rooms:** colours harmonised as lamp colours in the same night (a gas-lamp green, a velvet
  red, a brass).

Dark scheme only. Improve the current hand-picked hex values rather than randomising.

**Keep:**
- the id
- the name "Legacy"
- Jacquard 12, Alegreya Sans, IBM Plex Mono (bundled already, no fonts/ needed)
- the live hall scene (`{"scene": "hall"}`) for the status strip if it still serves: it lights a
  window per person at home, which is a real feature

Replace the weak pictures (`/art/house-crest.png`, `/art/tv-bezel.png` references) with the
theme's own art in themes/carved-night/art/.

**Art** (pixel, one density):
- **Page:** a parallax night, a real layered scene:
  - sky gradient with the moon (cover)
  - clouds drifting across the moon
  - the manor on its hill (natural, bottom, small depth)
  - dead trees and the fence close (depth)
  - fog rolling along the bottom (repeat-x drift)
  - a bat crossing now and then

  Keep the scrim readable.
- **Home hero:** the manor at night, windows glowing. Consider leaving the hall scene generator
  in the hero if it's better than a static picture: the lit windows count the people at home.
  If so, add hero layers around it (a moving cloud, a bat).
- **Header banners per room:**
  - Listen: the parlour gramophone
  - Watch: the screening room
  - House: the kitchen hearth
  - Files: the library
  - Games: the attic toys
  - Control: the cellar's machinery
  - others: the hall
- **Music deck:** a gramophone or jukebox relic skin with a candle flicker.
- **Rail:** a carved stone column skin; at its foot, a candelabra (flicker frames).
- **Crest:** the manor's keyhole crest.
- **Empty state:** a friendly ghost.
- **TV bezel:** a carved wooden cabinet TV.
- **My Space:** a bedroom in the manor.
- **Status strip:** the roofline and chimneys.

**Pieces:**
- **Nox:** the black cat of the house, 6 moods, with an idle blink.
- **Avatars:** moon, bat, raven, rose, ghost, all redrawn carefully.
- **Medals:** 20 haunted-house objects (a key, a candle, a music box, a potion, a clock…).
- **Room marks.**

**Discoveries:**
- a portrait whose eyes blink
- a ghost passing behind a window now and then
- the owl on the fence
- a shooting star once in a while

**Never:** gore; jump scares; mixed pixel sizes; text in pictures; the Castle theme's
crimson-and-gold action look (another theme does that).
