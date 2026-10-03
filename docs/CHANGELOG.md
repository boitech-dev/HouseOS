# Changelog

## Unreleased

- **Show on the TV**: a YouTube link from a phone's share sheet, a button on YouTube or Nox plays
  full screen on the house computer, and the TV turns on and opens Moonlight straight on it (LG
  webOS through Home Assistant). A desktop helper (`docs/native/houseos_screen.py`), a screen key
  for shortcuts, and the Tampermonkey button. docs/DEVICES.md → Show on the TV.

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
