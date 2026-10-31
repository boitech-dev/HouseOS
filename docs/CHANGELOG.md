# Changelog

## 1.1.0 — 2026-10-25

HouseOS has one branch, `master`, and no separate releases: everything here is in it, and fixes
keep landing there between version numbers. Control Room → Update (or `./houseos.sh update`)
brings them; Control Room says when changes are waiting, with *See what changed* to read them.
Newest first.

### 2026-10-31

- **Songs sorted into genres**: the house's songs list showed "other" for every kept song nobody
  had played yet (about 400 here) though its genre was known. Songs no catalogue knows now take
  the genre of the house's other songs by the same artist or channel (two at least, two thirds
  agreeing), and a cartoon's *générique* or *cabecera* is filed with anime. Residents can file
  any song themselves (My music → On this house, the bookmark button); that artist's other
  unsorted songs follow.
- **Agents from another network**: *Control Room → Agents* lists every address of the house,
  its Tailscale one first.

- **Connect your own assistant (MCP)**: `/mcp` serves Nox's tools to any MCP client (Streamable
  HTTP). *Control Room → Agents* makes a token per agent, acting as one person in the groups you
  pick (music, films and TV, smart home, the board, messages); it shows once and can be revoked.
  Every tool says whether it only reads, changes something or should ask first.
- **Auto play's next songs**: one list in play order, so a song moving into the queue keeps its
  place, and removing several quickly no longer fails; a removed song stays out.
- **Ideas** in Listen: four songs and one station, and a button for other ideas.
- **Search from a category** in Watch searches the whole tab, instead of showing nothing.
- **More versions to pick from**: up to eight cached versions in the picker; one not checked
  yet is checked when you pick it.
- **Nox plays films as asked**: "VO with French subtitles" sets the subtitles, subtitles are
  found online when the file has none, autoplay for a series, openings skipped when asked.

### 2026-10-26 to 2026-10-30

- **Switching films by hand** works on the Google TV Streamer: its player closes first, the new
  film is checked to really play, and a film whose screen another took is closed.
- **A film the Chromecast drops** (the cast logo on screen) is sent again a few seconds back.
- **A paused film stays** until you remove it: after a long pause, Play loads it fresh where it was.
- **The short reload** once a stream is complete stays where the film is.
- **The next episode keeps its subtitles** when its file has none in that language.
- **Versions that play only after a complete copy** rank below ones that stream at once.
- **Faster series and anime**, anime rankings and demographics; **song genres** for more songs,
  free (MusicBrainz).

### 2026-10-25

- **Skip openings and endings**: a switch on an episode's card, kept for the episodes that play
  after it. It follows each episode's own chapters (OP, ED), else AniSkip's times when they were
  measured on an episode as long as your file; nothing is skipped on a guess. Each is skipped once,
  and *Watch it* goes back.
- **The next episode starts on its own** (Linux install without Docker): the film service may now
  check the next file; before, every look failed and autoplay never started. If you installed by
  hand from `docs/native/`, add `AF_NETLINK` to `RestrictAddressFamilies` in your copy of
  `houseos-cinema-observer.service`.
- **A short loss of contact with the TV no longer ends the film** (30 s of grace), and Activity
  says "lost contact with the TV" rather than "no version plays on this screen" for a film that
  had played.
- **Pages heal after a dropped connection** (the computer slept, the network or the house
  restarted): what failed loads again on its own, and when the tab or the network comes back.
- **Update notices link to the changes**: Control Room's update line has *See what changed*.

### 2026-10-24

- **Next episode, as Stremio does it**: found five minutes before the end in the same release, with
  the same sound and subtitles, after a short countdown; it keeps trying until the episode ends.
- **New films and episodes load cleanly**: what the TV shows is stopped first, then the new one is
  sent (loading over a playing film went wrong on Chromecast).
- **Anime in Japanese with subtitles**, even when a dual-audio release marks its English dub as the
  default; a *Signs / Songs* track is never chosen as the subtitles.
- **Download first, then watch**: a heavy film is saved to the house disk while you do something
  else, plays from there without buffering, and is deleted once watched (or after a week).
- **Subtitles for a version that has none in your language**, in sync: found with the file's own
  fingerprint through the public OpenSubtitles add-on (no account); one that would drift is refused.
- **Chromecast streams**: a stream the Chromecast took for a live one is loaded again once complete,
  so seeks land where asked and it ends cleanly; a stream no longer fails to start while its
  manifest is still being written.
- **Admins hear of every new batch of fixes**, not only a new version number.
- The film card's notes are in plain words.

### 2026-10-22

- A streamed film is limited by free disk space, not a fixed 80 GB, and a refusal says how much
  room it needs. Subtitles that are pictures say clearly why they can't show on this screen.

### 2026-10-18

- **Film controls show the truth**: the Now bar follows the film through buffering and seeks, goes
  to a typed time (1:23:45, 83:20 or minutes), and its volume is the TV's own when Home Assistant
  reaches it. Going to a time ahead works on Chromecast streams.
- **TV remote and Chromecast**: Power turns a TV on from standby, buttons a TV lacks are hidden, and
  a paired Chromecast can be turned on from the Smart home remote.
- **Music**: fast taps skip several songs (but a late tap or a second phone skips nothing extra);
  Previous stops the playing song; a radio's turn counts the time it is heard.
- **Nox's panel fits the screen** and grows on wide ones; everyday requests get more rounds.
- **Faster**: built files are compressed and cached for good.
- Many small fixes: buttons stay busy while their action runs, offline changes survive a restart,
  private event reminders reach their author only, uploads stuck after a restart are released.
- **Install**: an update never drops this copy's own commits, a failed backup starts the house
  again, and the example settings no longer ship a fixed database password.

### 2026-10-04

- **Music**: the house's sleep timer waits five hours with nobody touching the music.

### 2026-10-03

- **Your own integrations**: code for your house's own devices and habits, installed from a git
  repository in Control Room → Integrations (checked before it runs, pinned to a commit, off until
  turned on, updated in one step). It can add routes with their own keys for shortcuts and
  helpers, Nox tools with confirmation cards, share buttons on Capture and a Control Room card.
  docs/CUSTOM-INTEGRATIONS.md, with a tested example. The Docker image now includes `git`.

## 1.0.0 — first release

HouseOS is your home's own app: one computer at home runs it, and everyone opens it in a browser,
on a phone or a computer, at home or away through Tailscale or your own proxy. No cloud account,
no subscription. What it does from the first evening:

- **Listen**: a fair jukebox. Search, paste a YouTube or SoundCloud link or a playlist, pick one
  of 50,000 radios, or ask Nox. New songs take turns; anyone can move a waiting song; everyone has
  one veto every three hours. Songs are kept on the house disk after their first play, with one
  fixed loudness level each. Auto play carries on when the queue runs dry. Music plays on the
  computer's speakers, Cast and DLNA speakers and TVs, or phones in Speaker mode.
- **Watch**: films, series and anime from your own sources (files on the house disk, Jellyfin, or
  a Stremio-style add-on with your own debrid account or the optional torrent player). It picks a
  version you can follow and your TV plays, sends it to the TV in one tap, and resumes where you
  stopped. Filters and collections run on a local film index that ships with HouseOS.
- **Watch → Web**: any video link (YouTube, TikTok, Instagram…) plays on the TV, without ads.
- **Games**: your own games, from a folder, an upload or a link; play in the browser, or on the TV
  with Moonlight on a native Linux install. Saves follow each person.
- **The house board**: tasks, groceries, a shared calendar with private events, and messages.
- **Files**, **Smart home** (with Home Assistant, and a TV remote) and a **party mode** for guests.
- **Nox**, the house assistant: the same actions as the buttons, with the same permissions, typed
  or spoken (speech runs on your computer). Bring your own AI: a ChatGPT or Claude sign-in, an
  API key (OpenRouter, OpenAI, Anthropic), or your own model. Its ready-made requests work with
  no AI at all.
- **The house in numbers**: hours, genres, top songs and games, and twenty house titles.
- **Themes**: ten bundled looks; make your own by hand or with Nox's theme studio. *Hand it to
  Nox* in the hand editor, or *Ask Nox* next to a theme in your list: Nox reads what you made,
  keeps what works and finishes it with you.
- **English and French** built in; Nox translates the app into any other language.
- **Install**: `git clone` and `./houseos.sh install` on Linux (or Windows through WSL 2), then
  *Control Room → Setup* walks you through the rest.
