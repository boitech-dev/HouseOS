# Shōwa Platform · Quai Shōwa — concept (Sam)

**Idea.** The whole house is a small 1960s local-line railway station at 4 p.m. in August:
cream enamel signs with navy lettering, one vermilion signal arm, a timetable board, card
tickets clipped by the conductor, and the stamp desk where kids collect round ink stamps. Every
room is a *platform* or an *office* of the station; every room colour is a *line colour* on the
station map. Original art only: no real railway's logo, line name, train livery or mascot.

**Why it works for a family.** Kids get a game (collect stamps, the conductor-cat, "call the next
train"); adults get a calm, high-contrast light theme with one red that means "act here".

## Palette (light scheme, resolved)
| Role | Token | Value | Source |
|---|---|---|---|
| Ground | `color.bg.canvas` | #f2e9d2 | enamel cream |
| Plates | `color.bg.surface/raised` | #faf3e2 / #fcf8ea | fresh enamel |
| Lettering | `seed.neutral` oklch(0.45 0.06 255) → fg #15202d | station-sign navy |
| The one accent | `seed.accent` oklch(0.56 0.17 38) → #c34517 | signal vermilion |
| Statuses | success #2d7b48 · warning #b37903 · danger #a31b45 · info #1f689d | railway lamps |
| Private / Nox | #7f4995 | commemorative-stamp ink purple |
| Paper | #d4f1d8 | pale-green card ticket |
| Rooms (line colours) | home slate · listen orange · watch sky · house green · files mustard · ask purple · me rose · control navy | the line map |

**Type.** Dela Gothic One (heavy wide Shōwa shop-sign gothic) for titles only; Fira Sans for
everything read; Overpass Mono (timetable mono) for times and numbers.

**Motifs.** Enamel wall tile (canvas texture), overhead catenary, the station-name board (blank:
no words in images), split-flap board, ticket perforation, round ink stamps.

**Motion.** Mechanical and crisp, like flaps turning: 90/160/240 ms, `ease.standard` [0.6,0,0.1,1], no bounce.

## Composition plan (what each part becomes)
| Part | Becomes | Tie to the whole |
|---|---|---|
| Page background | cream enamel wall with faint tile grout | the station wall |
| Top status bar | sky with overhead catenary wires and poles (`status.backdrop`) | you are under the wires |
| Side rail / bottom dock | the line map: each door carries its line colour; the current door is the lit station | rooms = lines |
| Page header | kicker = platform announcement ("Platform 1 · the jukebox"), title in shop-sign gothic | station signage |
| Panels | enamel plates: tonal step + a 1 px "lip" shadow, 6 px corners | enamel signs |
| Lists and rows | timetable rows: mono times, dotted leaders | departure board |
| Buttons / switches / fields / chips | buttons = signal red plates; switches = signal levers; fields = white enamel insets; chips = card tickets (2 px corners, perforated edge) | tickets and signals |
| Now-playing bar | a split-flap departure board: dark board, amber flaps | "now departing" |
| Sheets and pop-ups | a ticket-window counter sliding up | the ticket office |
| Avatars (crest, moon, bat, raven, rose, ghost) | six round station stamps in stamp-ink purple | the stamp desk |
| Nox mascot | a conductor-cat in a navy cap with a red band | the station's familiar |
| House titles and medals | commemorative ink stamps, collected per week | stamp rally for kids |
| Empty / loading | "The platform is quiet. Call the next train." / loading = a flap board flipping | announcements |
| Fonts | see Type | |
| Motion | flap-turn: crisp, mechanical | |
| Words | platform/office kickers per room (flavor.json) | announcements |
| Sign-in crest | round stamp: sun over mountains, a train front (`auth.crest`) | the station's stamp |
| Home hero | pixel platform: canopy, blank name board, bench, clock, a cream-and-red train, signal arm | arriving at the station |
| Watch bezel | a 1960s waiting-room TV on legs | the waiting room |
