# Your own connections

Every integration starts empty and disabled. Configure them in **Control Room** (admins). Keys are
stored encrypted in your database with your own encryption key; never put them in source, Git, chat
or docs. A setting that saves is not a tested feature: try the real thing once.

Something HouseOS doesn't know (a device only your house has, a helper on another computer)?
Add **your own integration** from a git repository: [CUSTOM-INTEGRATIONS.md](CUSTOM-INTEGRATIONS.md).

## Nox (the AI house manager)

**Not configured.** Control Room → **AI** shows five cards; each is one input or the official sign-in.
After connecting, HouseOS lists the models, picks a sensible one, runs a quick tool test and makes it
Nox's model if none was chosen:

| Card | You give it | Notes |
|---|---|---|
| ChatGPT subscription | Sign in on OpenAI's page with the code HouseOS shows | Runs the official Codex CLI in its own bridge; works on a headless server. |
| Claude subscription | Sign in on Claude's page, paste back the code (or a `claude setup-token` token) | Runs the official Claude Code CLI in its own bridge; the token only reaches that CLI. |
| OpenRouter | An API key | Many models; prices come from OpenRouter, so dollar budgets apply. |
| API key | An OpenAI or Anthropic key | Models without published prices count requests instead of dollars. |
| Self-hosted | The server address, e.g. `http://host.docker.internal:11434/v1` | Ollama, LM Studio, vLLM or anything OpenAI-compatible; counts requests. Ollama is spoken to through its own API so each request gets the context Nox needs; other servers that cut the prompt are told which setting to raise (16k tokens or more). |

"Advanced: assistant models" picks separate models for the house assistant and the My Space setup
chat, and "Advanced settings" on a card holds prices, limits and reasoning level.

What needs no model at all: the ready-made "Play our favourite songs", "What is planned this week?"
and "How does the house work?" (all code), every button in the app, queues, schedules, feeds, stats
and titles. "Help me find something to watch" and free conversation use the model. Nox knows when a
message was spoken (voice) and asks rather than guessing a misheard word.

Keep the house tour current: `backend/houseos/nox_presets.py` (`TOUR`) describes each room; a test
fails if a room is missing from it. Nox's system prompt is in `assistant_prompt.py`, its tools and
bundles in `assistant_tools.py`.

The Docker image includes both official CLIs (pinned); native installs set them up per
docs/NATIVE_ASSISTANT_BRIDGES.md. No login or profile is included: each house signs in itself.

## A stream add-on (films), with a debrid service or the torrent player

**None is included or preconfigured.** Like Stremio, HouseOS reads the Stremio add-on protocol
and reaches only the add-on you add: you paste its link, and HouseOS talks to that link's host and
nothing else. The add-on lists the versions of a film; HouseOS plays them either through **a debrid
service** (fast, cached, your own account) or with the **torrent player** on this computer (no
account; optional). The debrid service, when set up, is always tried first.

1. Control Room → Integrations → Stream add-on → **Configure** (or the welcome's films step) →
   **"Browse add-ons ↗"** opens the Stremio community's add-on catalogue in a new tab. Pick an
   add-on that finds films and series.
2. On the add-on's page, choose your options; with a debrid service, paste **your own API token**
   from that service there.
3. Press **Install**, copy the link (it ends with `/manifest.json`), paste it into HouseOS and
   save. It is stored like a password and never shown again.

Debrid versions play when the add-on uses the common Stremio debrid link format (`realdebrid=` in
its link, `[RD+]` versions resolved on the add-on's own host); versions that carry a torrent
(`infoHash`) play with the torrent player, whatever the add-on.

**Without a debrid service: the torrent player.** Install it once: Docker `./houseos.sh torrents on`;
native Linux `sudo python3 docs/native/setup_torrent_engine.py` (behind a password kept in the
house's secrets). It is TorrServer (GPL-3), listening on this computer only. Ticking the box below
checks it's there and sets it quiet (no UPnP, sharing back capped at 50 KB/s, memory only). Then paste an add-on link without debrid and tick **Play torrents from
this computer** in Control Room → Integrations → Stream add-on. The film starts while it downloads from other people:
they see your internet address and it shares pieces back; depending on where you live and what you
play, that can be illegal, and your provider may send notices. It stays off until you tick it.

Films you own always work without either: upload or import them (Files, Watch → save locally) or
use your own Jellyfin.

How versions are chosen: HouseOS ranks what your sources offer (a copy on the house disk first, then
what the add-on reports as cached on your debrid service): something you can follow comes first (sound or
**embedded** subtitles in the languages set in your film preferences), then the original audio,
then the resolution, at most your screen's. It checks the top three in parallel (ffprobe), carries
on with the next three when none plays on your TV (up to twelve), and remembers each check for a
week. You confirm once before anything plays.

## Watch: catalogue data (free, no account)

- **Cinemeta**: search, posters, cast and synopsis for films and series.
- **MyAnimeList through Jikan**: anime search and details, and "More like this" for anime (what
  MyAnimeList members recommend).
- **The local film index**: films and series from Wikidata (CC0). HouseOS ships a ready copy, so
  it works from the first start; the maintenance service refreshes it once a week in the
  background (it resumes if interrupted and never replaces a bigger index with a smaller one). It
  powers Watch's filters (genre, theme, person, award, length, years), rows and collections,
  Recommended for you, and "More like this" for films and series (same director, cast, themes).
- **The anime offline database** (cedya77/anime-offline-database, derived from the
  manami-project database), downloaded and refreshed daily: anime filters, studios, seasons,
  franchise links, and the fallback when Jikan is down.

None of this uses a model. "More like this" shows its source (MyAnimeList or similar themes).

## Cinema: Cast, audio and subtitles

TVs and Cast devices fetch media from the **media relay** on your host (port 8991; in Docker it is
part of the core stack). It finds its own LAN address; set `HOUSEOS_RECEIVER_BASE_URL` only to force
another one. **Control Room → Devices → Find devices** lists Chromecasts, Google TV and Android TV
(Chromecast built in), Nest and Cast speakers on your network; one tap adds one. Devices can also be
added by IP address; any private LAN address
is accepted unless you narrow it with `HOUSEOS_CAST_LAN_CIDR`. Allow port 8991 from your LAN in the
host firewall if you run one. A TV controlled through Home Assistant and a separate Chromecast plugged into it are distinct: HouseOS casts to the Chromecast, and Home Assistant's TV power/input controls are not proof of a native movie player on the TV.

Run `houseos.cinema_worker`, `houseos.cinema_observer` and the `houseos.relay:app` service in their own isolated native setup. The ordinary worker alone is not the Cinema engine. The receiver must be able to reach your relay; the private API may remain loopback-only behind your own HTTPS proxy. Preserve URL/peer allowlists, opaque session resources, range/CORS handling and parser network isolation.

Discover/enroll your own receiver, record supported codecs/HDR modes from evidence and test a known legal clip with picture, sound and a text subtitle. Test pause, seek, volume and "Stop and remove". Coordinate first with anyone else using that TV.

Embedded text subtitles are extracted/normalized to WebVTT for Cast, with their original timing and language labels. External supplied SRT is separate and should be labeled. Bitmap subtitles cannot be converted to text by renaming a file; they need a compatible route or approved burn-in. There is no promised flawless automatic subtitle/dialogue retiming. OpenSubtitles is optional, needs your own provider setup and quotas, and is unnecessary when embedded/supplied tracks work.

Video is copied where compatible; unsupported audio may be converted while buffering. Some HDR/Dolby Vision profiles or bitmap tracks need another source/client or a disclosed transformation. Never suppress compatibility errors just to show success. The most recent sync/seek fix needs a real-device retest on your equipment.

Home Assistant (optional) can also turn a TV on and off, set its volume and switch its HDMI input before a film; pick that TV when you connect Home Assistant (below).

## TV remote

The Smart home room has a **TV remote** for each enrolled Cast or DLNA screen, with a target picker
(remembered per browser):

- **The TV itself**, through Home Assistant, when its media player is mapped to that device: power,
  input, volume and mute (as far as Home Assistant reports the TV supports them), and its own arrows.
- **Only the Chromecast** (or the DLNA TV): volume, mute and play/pause over Cast or DLNA. Arrows,
  OK, back and home need a one-time pairing over the Android TV Remote protocol (Google TV,
  Chromecast with Google TV and most Android TVs): the TV shows a code and you type it. Pairing is
  optional. A DLNA TV offers volume only.

Only the buttons a target really has are shown. Nox can press them too ("turn the TV volume down").

## Home Assistant: the Smart home room

If you already run Home Assistant, HouseOS joins it: *Control Room → Integrations → Home Assistant*.
The address is filled in when HouseOS finds it on your network. Press **Open Home Assistant's token
page**, create a long-lived token named HouseOS (at the bottom of your profile's Security page), paste
it, **Save and test**, then choose what HouseOS may control. Everyone then gets a **Smart home** room
(lights, plugs, blinds, heating, scenes, by room, plus the TV remote above) and can ask Nox (*"turn off the living-room
lights"*). Locks, alarms, sirens and valves are off unless you allow them, and always ask to confirm.
Every command re-reads the device, so HouseOS only says "done" when Home Assistant shows it.

## Jellyfin and Home Assistant addresses

Both accept **any address this server can reach**: a LAN IP, a hostname or an `https://` URL. Inside
Docker, a service on the same computer is `http://host.docker.internal:<port>` (not 127.0.0.1).
Jellyfin: its address and an API key (Jellyfin → Dashboard → API Keys), then **Save and test**: the
key is checked for real and you pick the Jellyfin user whose library HouseOS shows. Home Assistant:
its address and a long-lived token, tested the same way. Addresses with a user/password, a query or
a link-local IP are refused; certificate checks stay on.

## Voice

Local and private: `houseos.voice` (faster-whisper) transcribes on your own computer and deletes
each recording right after. Docker runs it always; it downloads its `small` model once in the
background and runs on the processor. With an NVIDIA card, the `compose.gpu.yml` line in `.env` uses
`large-v3-turbo` on the card (~1.2 GB of video memory while loaded); if the card fails it falls back
to the processor by itself, and Control Room → Services says which one runs.
Native: docs/SETUP.md §6. The microphone needs an `https://` address; when it cannot listen it says why.

## Music, radio and uploads

**Where music plays.** Control Room → Speakers: any output of this computer, picked at any time,
even mid-song (its default output, HDMI, USB, or a Bluetooth speaker paired with it, which appears by
itself; without a desktop sound server, Docker uses the sound card directly), a **Cast** or
**DLNA** device, and any phone or computer in **Speaker mode** (`/speaker`: it follows the house clock, so a
phone paired with a Bluetooth speaker becomes the house speaker). https radio plays on phones too;
http-only stations stay on the server's speakers.

**Even out songs** (Control Room → House, on by default). Each downloaded song gets one fixed
gain, measured once with ffmpeg (EBU R128) before it plays, never changed during the song: very
quiet files (below -13 LUFS) +20 %, very loud ones (above -7 LUFS) -15 %, the rest as released. A
limiter at 0 dB touches only peaks that would clip after a boost. Live radio is not changed. It
applies to this computer's speakers; Cast, DLNA and Speaker mode play the file as is.

**Genres** (for stats and favourites) come from code and free data, never a model: your own house
genres (Control Room → House: a name and the words that mean it), what the source says (SoundCloud
genre, station tags, words in the title), then **Deezer's public API** (no account or key, one
lookup per song by the maintenance service, plus a cover for songs without artwork). Switch the
Deezer lookup off with Control Room → House → **Find each song's genre online**.

**Native installs** keep the stricter host setup below.

Music uses the dedicated `houseos.audio` bridge running with access to your desktop user's PipeWire/PulseAudio socket and a chosen sink. It starts its own mpv; do not share another application's mpv IPC socket. `houseos.fetcher` must run as isolated **houseos-fetch** with the protected network policy; the bridge checks peer identity. Adapt service users/paths carefully; do not remove that check. `HOUSEOS_AUDIO_ENABLED` and `HOUSEOS_EXTERNAL_FETCH_ENABLED` remain false until this is configured and tested.

The resolver dependencies are pinned in `dependencies/resolver-requirements.txt`. Point `HOUSEOS_RESOLVER_BIN` to your resolver's `yt-dlp`. The optional bgutil PO-token helper source and lockfile are included under `vendor/` with their GPL license. It is a separate upstream service, not login state; install its platform/native dependencies, configure your own instance and set `HOUSEOS_YOUTUBE_POT_URL`. Its README describes operation; do not enable it just by copying an old service template. YouTube cookies/Chromium sessions are not included. Music supports SoundCloud and YouTube, reuses canonical downloaded tracks, bounds preparation and cleans partial downloads; providers can still rate-limit or withdraw media. A free provider cannot be guaranteed unlimited or permanently available.

For uploads install tusd from its upstream release and adapt the loopback upload service to port 8992 and your data-root staging directory. HouseOS authenticates every proxied upload/status/resume request and finalizes it; never expose tusd directly to the LAN or bypass the reservation/finalization path.

Radio stations come from Radio Browser, a free community directory of about 50,000 stations: browse
by Popular, Trending, Most liked, New or Surprise me, by genre, country and language, keep only the
stations phones can play, or tap a collection (SomaFM, Radio Paradise, FIP, KEXP…). Streams on the
high ports Icecast/Shoutcast use are accepted; the fetcher still refuses every private address. HouseOS shows the song a station is playing when the station
publishes it (its ICY "StreamTitle"); many music stations do, most talk stations do not. "Find this
song" searches it for you.

## My Space and other household features

My Space starts with a setup chat. The resident chooses news, up to five subreddits and illustration tags/counts within provider limits, then confirms setup. Configuration and the setup conversation persist. Feed refreshes every 12 hours run in code, not paid AI polling. Reddit/RSS/image sites can be unavailable; show last-refresh/error states honestly. Push notifications are optional; generate your own VAPID keys and configure HTTPS. The private durable inbox remains authoritative.
