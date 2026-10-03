# 🎮 Games

Your own games, on any screen. **Play here** runs in any browser (phone, tablet, laptop): nothing
to install. **Play on the TV** streams from the house's computer to Moonlight, with a controller.
Your saves follow you from one to the other.

> HouseOS never downloads a game. It plays the files you bring: uploads, a link you paste, or the
> folder where you already keep them. It only downloads open data (names, covers) and emulators.

## Add your games

| How | Where | Good for |
|---|---|---|
| **Upload** | Games → Add games → Upload | a few files, from any device; zips are fine |
| **A link** | Games → Add games → From a link | a file you keep online (your backup, homebrew) |
| **A folder** | Games → ⚙ Set up → Games folders (admin) | a whole collection: read where it is, never copied or changed |

- One subfolder per console helps (`SNES/`, `PS1/`…): discs and zips are placed by their folder.
- The same game twice is refused ("already in the house"); regions and revisions of one game
  become **one card with versions**.
- Covers, genre, year, players, publisher and series come from the open
  [libretro database](https://github.com/libretro/libretro-database), matched by the file's
  fingerprint (CRC) or its name. No account, no key.
- **Catalogue** shows every known game of a console, with what the house has marked. Romhacks
  link to their page, where you get the patch.

## Search online

A game of the **Catalogue** that isn't in the house has **Search online**: it opens a web search for
that game in a new tab. Found it? **Add your copy**: paste its download link, or upload the file.
The house matches it by its fingerprint and it shows up as "In the house". An admin can change
what it opens in **Set up → Search online** (a web address; `{title}`, `{console}`, `{system}`,
`{region}`, `{filename}` and `{crc32}` are filled in), or empty it to hide the button.

## Romhacks and translations

Open the original game → **Add a romhack patch** → pick the `.ips` or `.bps` file. The house
applies it and adds the hack as a game of its own, with the original's cover and facts. A patch
made for another version (region, revision) says so.

## Consoles

| Console | Here (browser) | TV | Needs a BIOS |
|---|---|---|---|
| NES, SNES, Game Boy (Color), GBA, Virtual Boy | ✅ | ✅ | — |
| Nintendo 64, Nintendo DS | ✅ (a good computer or phone) | ✅ | — |
| Master System, Mega Drive, Game Gear, 32X | ✅ | ✅ | — |
| Mega-CD | ✅ | ✅ | yes |
| PlayStation | ✅ | ✅ | optional |
| PC Engine, Neo Geo Pocket, WonderSwan, Atari 2600/7800, Jaguar | ✅ | ✅ | — |
| Lynx, ColecoVision | ✅ | ✅ | yes |
| Arcade (FBNeo sets) | ✅ | ✅ | `neogeo.zip` for Neo Geo |
| GameCube, Wii, PS2, PSP, Dreamcast, Saturn | — | ✅ | PS2, Saturn: yes |

A BIOS is a small file from the console itself: an admin adds it in **Set up → Console BIOS
files**. It is never downloaded.

## Saves

- The **in-game save** (the game's own memory card) is kept by the house, per person: the same
  on your phone, your laptop and the TV. It syncs every 30 seconds and when you leave.
- **Snapshots** ("save state") are per screen kind: the browser's list is in the game's page,
  with a picture each; the TV resumes exactly where you quit.
- Nobody else sees your saves, not even an admin. They are in the house's backup; game files are
  not (like films).

## On the TV

What you need: **Moonlight** on the TV (Google TV / Android TV, Apple TV, Fire TV, LG, Samsung,
or a laptop), free from its store, and a **controller paired to the TV** (Bluetooth), not to the
computer. The computer can be in another room.

1. Native Linux install only (the stream uses the computer's screen and graphics card): run once
   `sudo python3 docs/native/setup_games_host.py --user <desktop user>`. It installs Sunshine and
   RetroArch, opens their ports to the home network only, and never touches the music's
   speakers (games get their own sound output).
2. Open Moonlight on the TV: it shows a 4-digit code the first time. Type it in **Games → ⚙ Set
   up → Play on the TV**.
3. Pick a game on your phone → **Play on the TV** → on the TV, Moonlight → **HouseOS**. Picking
   another game switches it; **Stop** stops it from any phone. To leave from the controller:
   L1 + R1 + Start + Select, then Quit.

How it feels: at home, about 15–30 ms more than a console plugged into the TV (a TV that isn't in
game mode adds as much). Use Ethernet or strong 5 GHz Wi-Fi for the TV. Away from home, through
Tailscale, add your connection's own delay.

Docker and Windows installs: **Play here** works the same; TV play isn't available there.

## What is downloaded, and from where

| What | From | When |
|---|---|---|
| Game names and facts | libretro-database (GitHub) | the first game of a console |
| Covers, title screens, in-game pictures | thumbnails.libretro.com | per game, once |
| The in-browser emulator (EmulatorJS 4.2.3) | cdn.emulatorjs.org | a console's first play here |
| TV emulators (RetroArch cores) | buildbot.libretro.com | a console's first play on the TV |

Everything else stays in the house. EmulatorJS is GPL-3; each core keeps its own licence
(some are non-commercial): they are fetched by your house, not shipped with HouseOS.
