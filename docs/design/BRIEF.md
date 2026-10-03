# Midnight House — design brief

The reference for the UI/UX overhaul (approved 2026-09-23). When a screen is designed or
reviewed, check it against this file.

## 1. What we are making

HouseOS is a private app for a shared house: a few roommates, mostly on phones, some on
desktop, opened in the browser (not installed). It works; it does not yet feel designed.
The overhaul turns a pile of features into **one coherent, premium-feeling product with
a world of its own**.

> Not a modern dashboard wearing a pixel-art costume: a **fictional household operating
> system** that secretly has extremely modern, premium UX.

- "Premium" is not minimalist SaaS. "Retro" is not inconvenient retro software.
- Interaction is contemporary and polished; the art direction is strange and authored.
- Netflix-level immediacy does not require Netflix aesthetics.

## 2. Priorities (in order)

1. Functionality, clarity, speed and first-day onboarding.
2. A coherent product: one structure, one visual language, one way to show state.
3. Personality, lore and small moments of delight — never slowing or confusing anyone.

Someone who had nothing to do with building it must understand it on day one.

## 3. The two jobs that matter most

1. **Keep the house music queue fair between everyone.** Everyone can add songs, see
   whose turn is next, and trust that nobody takes over the evening.
2. **Get any film or series onto the TV from a phone**, without the TV remote. Choosing
   a title gives a ready, sensible setup that you confirm in one tap or change quickly.

Every other area should be good; these two should be excellent.

## 4. Places and layers

| Place | For | In the world |
|---|---|---|
| **Home** | What is happening at home right now; glanceable, every tile opens its area | The hall at night: the house, windows lit for residents who are around |
| **Listen** | Now playing, the fair queue, search/links/playlists/radio, library, history | The parlour and its jukebox |
| **Watch** | Continue watching, search and shelves, the title sheet, what is on the TV | The screening room, a glowing CRT alcove |
| **House** | Today; wall notes, groceries, tasks, calendar, messages | The kitchen notice board |
| **Files** | Personal, house and drop files; uploads | The archive cellar |
| **Me** | Profile, preferences, memories, My Space settings; security tucked away | Your own room |
| **My Space** | A small personal room to visit: daily news, communities, illustrations | Your bedroom desk and window |
| **Control Room** | Administration (admins only), behind the profile menu | The house's workshop |

Layers present everywhere:

- **Player** — one bar for music and the TV; expands to a full now-playing sheet.
- **Ask** — the house familiar (a small bat, "Nox", renamable) one tap away: side
  panel on desktop, full sheet on phone, ⌘K, voice mode.
- **Activity** — one tray for work in progress (a film preparing, a playlist
  importing, uploads) with honest steps, failures and retry.
- **Connection** — a quiet indicator when live updates drop, and recovery when back.

Phone: dock **Home · Listen · Watch · House · Ask**; Files, Me and Control Room behind
the avatar. Sheets instead of new pages; the composer is never hidden by the keyboard.
Desktop: the same places in a left rail; the Player and Ask stay reachable.

Party mode (occasional): a tablet view for guests — search, fair queue, Player — on an
expiring party invite.

## 5. Visual direction

HouseOS is themable: how things look is a theme (`themes/`, the authoring guide is
`themes/README.md`). **Carved Night** is the house default and the original direction; its brief
(palette, type, materials, art) is `themes/carved-night/BRIEF.md`. What holds in every theme:

- Colour is logic, not decoration: one accent means light, active or the primary action; state
  always has a shape or a word as well as a colour.
- **Real media stays real.** Posters, series art and album covers keep their true colours.
- Titles may be expressive; reading text and controls are always a legible face.
- Decoration lives only in the theme's art slots, empty and loading states, and flavour words;
  every screen is right with none of them (Base shows none).

## 6. Motion and micro-life

| Level | What moves |
|---|---|
| Still | Nothing; instant state changes. Default when the device asks for reduced motion. |
| Subtle (default) | Feedback, transitions, playback indicators. No ambient loops. |
| Full | Ambient life: dither shimmer, windows, candle, residents, the familiar idling. |

Loops pause when the tab is hidden or offscreen. Nothing flashes. Motion never delays an
action: the interface responds first, the flourish follows.

## 7. States

Every area designs: first use, loading, loaded, in progress, success, empty, error,
offline/disconnected, not configured, no permission. Waiting always says what is
happening now and what comes next. Errors say what happened and what to do.
"Started" is never shown as "done"; "sent to the TV" is never "playing" until observed.

## 8. Language and copy

French by default for residents, English for the administrator; switch in Me. See
`COPY.md`. Plain functional labels ("Musique", "Courses"); lore lives in headers, empty
states, loading and success moments — never inside the words of an action.

## 9. Listen — specifics

- Fair rotation is on by default and visible ("tour de table"): rounds with avatars.
- One field accepts a search, a song link, a playlist link or a radio station.
- Playlists import in the background with progress; no arbitrary 50-song cap.
- Starting a radio station from the app plays it (no hidden approval step).
- Real artwork, real titles in history; play next, reorder your own songs, shuffle yours.

## 10. Watch — specifics

- Opening a title shows **a ready suggestion**: source · quality · audio · subtitles ·
  screen · start time. One button launches it; every line can be changed. Nothing ever
  starts without that tap (the TV is slow; a wrong choice is costly).
- Default preference: debrid-cached → up to 4K → original-language audio (VO) → embedded
  French or English subtitles. A source with suitable embedded subtitles can beat an
  otherwise better one; external subtitles are a fallback.
- Choose where to start: resume, from the beginning, or a precise time (e.g. 1:13:36).
- Continue watching is series-aware (next episode), and history is useful.
- No technical words; honest progress: finding → checking → sending → playing.

## 11. Ask — specifics

The assistant is a layer, not the home page. It knows which screen you are on, answers
briefly, shows real results as receipts, and asks for confirmation only where the app
requires it. Voice: tap the mic, the familiar appears and listens, the transcript lands
in the composer to send with one tap. Speech is transcribed locally and never stored.

## 12. My Space

Rarely visited, so it is not in the dock — but when you visit, it should delight: a cute,
personal room whose layout changes with the time of day, a desk with the daily
"gazette", a window with the day's illustrations, letters from chosen communities, small
interactions and details that change.
