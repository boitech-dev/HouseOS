# TVs, speakers and remotes

What plays where, and how HouseOS controls it, by kind of device and by brand. **Control Room →
Devices → Find devices** lists what is on your network and gives each one a line saying how to
use it.

## What plays where

| Device | Films | Music | Controlled from HouseOS |
|---|---|---|---|
| Chromecast, Google TV, Android TV, TVs with Chromecast built in (Sony, Philips, TCL, Hisense, Xiaomi…) | ✓ Cast | ✓ Cast | Volume and playback over Cast; arrows once paired in the TV remote (Google TV / Android TV) |
| Nest and other Cast speakers, Cast speaker groups | – | ✓ Cast | Volume, pause |
| Smart TVs without Chromecast (LG webOS, Samsung Tizen, most others) | Jellyfin app on the TV | ✓ DLNA | Power, sources, volume and arrows through Home Assistant (below) |
| Sonos | – | ✓ DLNA (choose a group's main speaker) | Volume, pause |
| Denon / Marantz (HEOS), Yamaha MusicCast, most hi-fi network players, Kodi | – | ✓ DLNA | Volume, pause |
| The server's own speakers: jack, HDMI, USB DAC, Bluetooth | – | ✓ | Everything |
| Phones and computers | – | ✓ Listen → Speaker mode | Their own volume |
| Apple TV, HomePod, AirPlay speakers | – | Not yet (see below) | Power and arrows through Home Assistant |
| Roku, Fire TV | Jellyfin app on the device | – | Power, apps and arrows through Home Assistant |

Films need Cast because HouseOS hands the TV a stream it can seek, pause and report on. DLNA
TVs get the music; for films on them, a Jellyfin library with the Jellyfin app on the TV works.

## Remotes through Home Assistant

HouseOS uses the integration Home Assistant already has for your TV. Add it in Home Assistant
(*Settings → Devices & services → Add integration*), connect Home Assistant in *Control Room →
Integrations*, and the TV shows in **Smart home** with the controls it really has: power,
play/pause, previous/next, its sources and apps, volume and a remote with arrows, OK, back and
home. Link it to a screen in *Devices* and the **TV remote** uses it too.

| Brand | Home Assistant integration | Arrows, OK, back, home |
|---|---|---|
| LG webOS | LG webOS TV | ✓ |
| Samsung (Tizen) | Samsung Smart TV | ✓ |
| Sony Bravia | Sony Bravia TV | ✓ |
| Philips | Philips TV | ✓ |
| Roku | Roku | ✓ |
| Apple TV | Apple TV | ✓ |
| Android TV, Google TV | Android TV Remote (or Android Debug Bridge) | ✓ (or pair directly in HouseOS) |
| Fire TV | Android Debug Bridge | ✓ |
| Hisense VIDAA | VIDAA (community integration) | ✓ with its remote buttons |
| Panasonic Viera | Panasonic Viera | power and volume |

**Sound on a soundbar or amplifier** (HDMI ARC, optical): the TV's own volume level no longer
changes what you hear, so HouseOS shows volume **− / +** instead of a slider. The TV passes those
keys to the soundbar over HDMI-CEC.

**Turning an LG TV on**: webOS TVs switch their network off when asleep, so Home Assistant needs
Wake on LAN to wake them:
1. On the TV: *Settings → General → Devices → TV Management* (or *Network*, by model) → turn on
   **Turn on via Wi-Fi**. Note the TV's MAC address (*About this TV*, or your router's list).
2. In Home Assistant: *Settings → Automations & scenes → Create automation → Create new
   automation*.
3. **Add trigger → Device** → the TV → **Device is requested to turn on**.
4. **Add action** → **Wake on LAN: Send magic packet** → the TV's MAC address. Save. (No Wake on
   LAN action? Add the line `wake_on_lan:` to `configuration.yaml` and restart Home Assistant.)

The power button then appears in HouseOS. Other brands that sleep the same way (some Sony and
Philips) work the same.

## Show on the TV (the computer's screen, through Moonlight)

A YouTube link plays full screen on the house computer, and the TV shows that computer through
Moonlight: your browser, your extensions, your YouTube account. One press from a phone's share
sheet, a button on YouTube, or Nox ("show this on the TV"):

1. HouseOS turns the TV on through Home Assistant (LG: Wake on LAN, above).
2. It opens Moonlight on the TV straight on the computer's **Desktop** app. On LG webOS this uses
   Moonlight TV's launch parameters (`host_uuid`, `host_app_id`), so nothing is pressed on the
   TV. Other TVs get Moonlight through their input list; pick the computer there.
3. The computer's helper waits for the stream, opens the video in a window of its own, brings it
   to the front and puts it full screen, from where you were in it.

What it needs:
- The TV in Home Assistant, shown to HouseOS (Smart home), with **Moonlight** among its sources.
- Sunshine on the computer (its **Desktop** app) and Moonlight paired with it once.
- A Linux X11 desktop with a browser and `xdotool`, and someone signed in to it.

Set up in **Control Room → Devices → Show on the TV**:
- **The screen key.** Create it there (shown once). Phones, the YouTube button and the helper
  send it; it reaches only the Show on the TV routes and acts as the administrator who made it.
  Replacing it stops the old one everywhere.
- **The computer:** from the HouseOS folder, as the desktop user,
  `python3 docs/native/houseos_screen.py --setup` (asks for the address, `http://127.0.0.1:8990`
  when HouseOS runs there, and the key; starts with the desktop from then on).
  `--check` shows what it reports: Sunshine's host id, the Desktop app's id, whether a stream is on.
- **iPhone, iPad:** a Shortcut in the share sheet, *Get Contents of URL*, POST to
  `<HouseOS address>/api/v1/tv/screen/show`, header `Authorization: Bearer <key>`, JSON body
  `{"url": Shortcut Input}`. The steps are on the Control Room card.
- **Android:** install HouseOS from the browser, then in YouTube *Share → HouseOS → Show on the
  TV from the computer*. For a single tap, the HTTP Shortcuts app can send the iPhone request.
- **A computer:** the Tampermonkey script `/houseos-show-on-tv.user.js` (served by HouseOS) adds a
  **Show on TV** button and Alt+T on YouTube; it asks for the address and the key once.

Honest status: "sent" means the computer took the video; the Control Room card then shows whether
it opened full screen. While a stream is on, the helper keeps the screen from blanking.

## Speakers on the server

HouseOS plays through the computer's sound server (PipeWire or PulseAudio) when someone is logged
in, else straight to the sound card.

- **Bluetooth** needs PipeWire: on a server without a desktop, install `pipewire-pulse
  wireplumber`, run `sudo loginctl enable-linger $USER`, pair the speaker, then restart the audio
  service in *Control Room → Services*.
- **HDMI not listed**: pick the HDMI profile in the computer's sound settings; it then appears in
  *Control Room → Speakers*.
- **AirPlay speakers** on a PipeWire computer: `pactl load-module module-raop-discover` makes them
  appear as outputs of the computer.
- **Several rooms at once**: Snapcast can be added as a PipeWire output on the computer.

## Setting up your devices, step by step

1. **Find them**: *Control Room → Devices → Find devices*. Each line says what the device is and
   how it works with HouseOS. Press **Add** on the ones HouseOS plays on.
2. **Choose where music plays**: *Control Room → Speakers*. Films ask which screen each time.
3. **Control TVs** (power, sources, arrows): add the TV's integration in Home Assistant (table
   above), connect Home Assistant in *Control Room → Integrations*, then pick what shows in
   **Smart home** (*Choose what shows*).
4. **Link a TV to its Chromecast** (optional): in *Devices*, so films turn the TV on and switch
   it to the right input, and the TV remote shows both.

## Fix it with an agent

Every home is different. When a device doesn't work, a coding agent (Claude Code, Codex…) can
usually find out why and fix it, in your copy of HouseOS. Open the HouseOS folder in the agent
and paste, filling in the brackets:

```text
Read AGENTS.md and docs/DEVICES.md. My [brand and model, e.g. "LG OLED C5 TV"] [what happens,
e.g. "is found but the volume does nothing"]. I use [Docker on Linux / Windows WSL / …] and
[Home Assistant with the "LG webOS TV" integration / no Home Assistant]. Find the cause, fix it
in HouseOS with a test, then tell me what to do on my side. Don't play anything on my devices
without asking me first.
```

Useful things to give it: what *Find devices* shows, the device's details in Home Assistant
(*Settings → Devices → the device → Attributes*), and `./houseos.sh logs`. A fix that would help
everyone can be shared back with the project.

## When a device isn't found

- Same network as the server, **not a guest Wi-Fi** (guest networks keep devices apart).
- The server's firewall lets the home network in: mDNS (UDP 5353), SSDP (UDP 1900), the app
  (TCP 8443) and the media relay TVs fetch from (TCP 8991). For example with ufw:
  `sudo ufw allow from 192.168.1.0/24` (your network).
- Docker: the relay shares the computer's network on Linux (Docker Engine). Docker Desktop keeps
  containers in a virtual machine, so discovery and casting need Linux or WSL2 (see
  [WINDOWS.md](WINDOWS.md)).
- Kodi answers only with *Settings → Services → UPnP/DLNA → Allow remote control via UPnP* on.
- A device HouseOS doesn't find can be added by its address: *Devices → Add by address*.
- Something special at your place? Ask Nox in setup mode, or your coding agent with
  [AGENTS.md](../AGENTS.md): most devices are a small addition away.
