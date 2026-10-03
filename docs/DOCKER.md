# HouseOS with Docker

You need **Docker with Compose v2** (2.24 or newer) on a Linux computer that stays on and is on
your home network (Wi-Fi or cable): a mini-PC, a NAS, an old laptop, a Raspberry Pi (§8) or a
Windows PC through WSL 2 (§10). It
needs no speakers or screen of its own. Nothing else: no `.env` to fill in, no ports to open in
advance. Everything else is set up inside the app, which walks you through it. Installing needs an
internet connection; a network with IPv6 only (no IPv4 addresses) is not supported. Other
systems (Unraid, Proxmox, Fedora, Mint, Arch): §11.

## 1. Start the house

```bash
git clone https://github.com/boitech-dev/HouseOS.git && cd HouseOS && ./houseos.sh install
```

`houseos.sh` checks Docker, makes a private database password, asks two questions (use an NVIDIA
card for voice if there is one; turn on the Control Room buttons, §9; with no one at a terminal
both answers are *no*), builds and starts HouseOS (10–20 minutes the first time), then prints **your one-time setup code** and the addresses to open.
If port 8443 is already used by another program, it picks 9443 (or the next free one) and says so.
Run it again later for a menu. Prefer plain Docker? `docker compose up -d --build`, then
`docker compose exec api houseos-entrypoint setup-code` for the code: the result is the same.

Then open HouseOS in a browser, from any device on your network:

| You open… | When |
|---|---|
| `https://houseos.local:8443` | The usual way, from a phone or computer on the same network: HouseOS announces itself under this name. Your browser warns **once** about the certificate (it is made by this server); accept it. |
| `https://<server-ip>:8443` | The same door by address, if `houseos.local` does not open (some Android versions and older Windows do not look up `.local` names). Trusted once you sign up at it or add it (below). |
| `https://your.domain` | You already have a reverse proxy (Caddy, Traefik, nginx, Tailscale Serve…): point it at `http://<server>:8990`, see §3. |
| `http://localhost:8990` | Only on the server itself, if it has a screen. |

Fill in your name, a username, a password (12+ characters) and the setup code. You are the admin,
and **only the address you used is trusted from then on** (plus `houseos.local`, which HouseOS
announces), so sign up at the address the phones will use. Add others in *Control Room → Access →
Addresses → Another address*; until then HouseOS says it "does not answer to the name" there.

## 2. The Setup checklist

*Control Room → Setup* opens first. Each line is measured (it tests the real thing), says what it
gives you and has a button to do it: house name, the secure address, Nox's AI, speakers, music
sources, films, your TV, voice typing, invitations and backups. **Everything is already running**:
films, voice and music are part of the one stack, and if a part stops answering, *Control Room →
Services* has a Restart button for it. You never need to start Docker a different way.

## 3. Behind your own reverse proxy

HouseOS listens on `8990` (plain HTTP, this computer only by default). The proxy just forwards to
it; HouseOS trusts the address you set up with and explains anything it refuses.

**Caddy**
```
house.example.lan {
    reverse_proxy 127.0.0.1:8990
}
```

**nginx**
```nginx
server {
    listen 443 ssl;
    server_name house.example.lan;
    client_max_body_size 16m;          # uploads are sent in 8 MB pieces
    location / {
        proxy_pass http://127.0.0.1:8990;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;           # live updates
    }
}
```

**Apache** (`sudo a2enmod ssl proxy proxy_http headers`; a certificate with `sudo certbot --apache -d house.example.com`)
```apache
<VirtualHost *:443>
    ServerName house.example.com
    SSLEngine on
    SSLCertificateFile    /etc/letsencrypt/live/house.example.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/house.example.com/privkey.pem
    LimitRequestBody 16777216              # uploads are sent in 8 MB pieces
    ProxyPreserveHost On                   # HouseOS checks the address you opened
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass        / http://127.0.0.1:8990/ flushpackets=on   # live updates
    ProxyPassReverse / http://127.0.0.1:8990/
</VirtualHost>
```

**Tailscale** (a real certificate with nothing to configure): `tailscale serve --bg 8990`, then open
`https://<server>.<tailnet>.ts.net`.

**Then, once:** open HouseOS at an address it already trusts and add the new one in *Control Room →
Access*; until then it explains that the address is "not one of its trusted addresses".

**Certificates.** A public certificate (Let's Encrypt) needs a real domain name: a public one, or a
private name with your DNS provider's DNS challenge (`certbot --preferred-challenges dns`, Caddy's
DNS modules) when the house must stay off the internet. Without a domain, keep the built-in door and
trust its certificate on each device: *Control Room → Access → Download the certificate*.

The proxy runs on **another machine**? In `.env`: `HOUSEOS_BIND=0.0.0.0` and
`HOUSEOS_FORWARDED_ALLOW_IPS=<that machine's IP>`. Never expose HouseOS to the whole internet;
use your network or a private VPN such as Tailscale.

The proxy runs **in a container** (Nginx Proxy Manager, Traefik, SWAG)? Attach it to HouseOS's
network, `<folder>_default` (e.g. `houseos_default`; `docker network ls` shows it):
`docker network connect houseos_default <proxy container>`, or list that network as `external` in
the proxy's compose file. Then forward to `http://api:8990`. HouseOS already trusts proxies on
Docker's networks (`HOUSEOS_FORWARDED_ALLOW_IPS` defaults to `127.0.0.1,172.16.0.0/12`); if
`docker network inspect` shows another range, add it there.

### HouseOS on your network

The computer running HouseOS *is* the device on your Wi-Fi: HouseOS announces itself on it as
`houseos.local` (mDNS, like a printer or a Chromecast) and finds the speakers, TVs and services
around it. That is why the few parts that talk to the network (the media relay, the film
worker and observer) use the computer's own network (`network_mode: host`) while the rest stays
in Docker's private network behind the HTTPS door: discovery and announcements are multicast,
which does not cross into Docker's private network. Two HouseOS on one network? Give one
another name with `HOUSEOS_MDNS_NAME=` in `.env` (empty turns the announcement off).

### HouseOS as its own device on the network (optional)

HouseOS can also have **its own address** on your network, like any other device, instead of
sharing this computer's. The HTTPS door and the media relay (the announcement, Find devices and
the media for TVs) then live at that address; everything else stays in Docker's private network.
Not needed to find TVs and speakers on Linux: the relay already shares this computer's
network. It needs Docker Compose 2.33 or newer; if it does not start, HouseOS goes back to this
computer's address by itself.

Turn it on with *Control Room → Services → Give HouseOS its own address*, or on the server:

```bash
./houseos.sh own-address            # suggests a free address; ./houseos.sh own-address off undoes it
```

It reads this computer's network card, subnet and router, suggests a free address (check it is
outside your router's automatic, DHCP, range) and writes these lines to `.env`:

```
COMPOSE_FILE=docker-compose.yml:compose.lan.yml
HOUSEOS_LAN_PARENT=wlan0          # this computer's network card (Wi-Fi or cable)
HOUSEOS_LAN_SUBNET=192.168.1.0/24
HOUSEOS_LAN_GATEWAY=192.168.1.1   # your router
HOUSEOS_LAN_IP=192.168.1.250      # the address
```

Phones then open `https://houseos.local:8443`, or `https://<HOUSEOS_LAN_IP>:8443`. It uses **ipvlan**, which shares this computer's network card and
MAC address, so it works on Wi-Fi as well as cable (macvlan, which invents a new MAC address,
is refused by most Wi-Fi access points). Its known limit: **this computer itself cannot reach
that address** (phones, TVs and other computers can); on this computer, use
`http://localhost:8990`.

## 4. Music: where it plays

*Control Room → Speakers*, at any time, even mid-song:
- **This computer's outputs**: its speakers, HDMI, USB, or a Bluetooth speaker paired with this
  computer (it appears by itself). HouseOS uses the logged-in desktop's sound if there is one,
  otherwise the sound card directly: nothing to set up.
- **A phone or a computer (Speaker mode)**: open *Listen → Play on this device* and tap *Play here*.
  A phone paired with a Bluetooth speaker turns that speaker into the house speaker.
- **A speaker or TV on the Wi-Fi**: *Control Room → Devices → Find devices* lists what is on your
  network; tap *Add*, then choose it in Speakers. Music follows the house (pause, skip, seek,
  volume) on:
  - **Cast**: Chromecast, Google TV and Android TV, Nest and Cast speakers, speaker groups;
  - **DLNA/UPnP**: Sonos, most smart TVs (Samsung, LG, Sony, Philips, Hisense…), many hi-fi
    speakers and Kodi (in Kodi: *Settings → Services → UPnP/DLNA → Allow remote control*). Songs
    in a format the device may not play (YouTube's WebM) are sent as an MP3 copy made on the fly.

  Find devices also shows AirPlay speakers (listed, not playable yet: AirPlay 2 needs Apple's
  pairing), Home Assistant and Jellyfin servers with their address, ready for *Integrations*.

A computer without any speakers is fine: music then plays on these devices and phones only.

- **A server with no desktop and a Bluetooth speaker**: install `pipewire-pulse wireplumber`, run
  `sudo loginctl enable-linger $USER` (so the sound server runs without anyone logged in), pair
  the speaker, then restart the `audio` service (*Control Room → Services*).
- **AirPlay speakers**, on a computer with PipeWire: `pactl load-module module-raop-discover`
  makes them appear under *This computer*.
- **Snapcast**: expose it as a PipeWire output on this computer; it then appears under *This computer*.

If music would play with no speaker at all, Listen says so and offers these choices.

**Even out songs** (*Control Room → House*, on by default): each downloaded song gets one fixed
volume correction, measured before it plays and never changed during it (very quiet uploads +20 %,
very loud masters -15 %, the rest as released). Live radio is left as is. It applies to this
computer's outputs; Cast, DLNA and phones play the file as is.

**Genres** for the stats come from the song's source and, by default, **Deezer's public catalogue**
(no account; one lookup per song, in the background). Turn that off with *Control Room → House →
Find each song's genre online*.

## 5. Nox's AI

*Control Room → AI* has five cards. Keys and sign-ins are stored encrypted on the server; nothing
is in files.

| Card | You need |
|---|---|
| ChatGPT subscription | A ChatGPT account: open the link HouseOS shows and enter the code (Google sign-in is fine). |
| Claude subscription | A Claude account: open the link, sign in, paste back the code it gives you. |
| OpenRouter | An OpenRouter API key: many models, one bill. |
| API key | An OpenAI or Anthropic API key. |
| Self-hosted | Your own model server, e.g. **Ollama** at `http://host.docker.internal:11434/v1`, LM Studio (`:1234/v1`), vLLM (`:8000/v1`). Ollama must listen beyond localhost: `OLLAMA_HOST=0.0.0.0`. |

Without any AI, the ready-made requests on Nox's welcome screen still work.

## 6. Films and series

Film preparation is already running. In *Control Room → Integrations* (each card says what it is for):
- **Stream add-on**: *Browse add-ons ↗* opens the Stremio community's catalogue; pick a Stremio
  add-on, set it up there (with a debrid service, paste **your** API token on its page), *Install*,
  copy the link and paste it back. HouseOS includes none and reaches only the one you add.
- **Jellyfin**: its address (`http://host.docker.internal:8096` if it runs on this computer, or
  any `https://` address) and a Jellyfin API key, then pick whose library to show.
- **Home Assistant** (optional): its address and a long-lived token, then pick the TV and what
  HouseOS may control. Everyone gets a **Smart home** room (lights, plugs, blinds, heating,
  scenes) and HouseOS can turn the TV on and off, set its volume and switch its HDMI input before
  a film.

**TV remote** (Smart home room): for each TV, choose what the remote controls: **the TV itself**
through Home Assistant (power, input, volume, its menus), or **only the Chromecast** or DLNA TV
(volume and playback; a DLNA TV has volume only). The Chromecast's arrows, OK, back and home work
after an optional one-time pairing: the TV shows a code and you type it. Without Home Assistant,
the room still appears once a Cast or DLNA screen is added.

**Filters and collections** in Watch come from a local film index that ships with HouseOS
(works at once) and is refreshed from Wikidata once a week in the background (the `maintenance`
service). Anime filters use the anime offline database, refreshed daily.

Your TV and speakers fetch films and songs from this computer on port **8991**: allow it from your
network in the host firewall if you run one, with mDNS (UDP 5353) and SSDP (UDP 1900) for Find
devices and `houseos.local`. Media parsers run in a bubblewrap sandbox, which is why `api`,
`worker` and `cinema-worker` have `seccomp=unconfined` (it drops every capability inside the sandbox).

### Films without a debrid service

A stream add-on without a debrid account needs **the torrent player**: `./houseos.sh torrents on`,
then tick **Play torrents from this computer** in Control Room → Integrations → Stream add-on (it says what that means;
ticking it sets the player quiet: no UPnP, sharing back capped, memory only).

### Games

**Games → Play here** works in Docker as everywhere (the emulator runs in the browser). **Play on
the TV** needs HouseOS installed directly on Linux (it streams the computer's screen with its
graphics card): see [GAMES.md](GAMES.md). A games folder is any folder under your import mount.

## 7. Voice for Nox

Voice typing is already part of the stack: it downloads its speech model once in the background (a
few minutes; Services shows it) and then runs on the processor. With an **NVIDIA** card and the
NVIDIA Container Toolkit, press *Control Room → Services → Move voice to the graphics card* (or run
`./houseos.sh gpu on`): Services then says *running on the graphics card*, and HouseOS
falls back to the processor by itself if the card fails. The microphone needs an `https://`
address (§1).

## 8. On a Raspberry Pi

A **Raspberry Pi 4 or 5 with 4 GB of memory or more**, a **64-bit** OS (Raspberry Pi OS 64-bit,
Ubuntu Server arm64) and an SSD or a good USB drive rather than the SD card. The same
`./houseos.sh install` builds HouseOS for the Pi (allow 20–40 minutes the first time):
Python packages come from PyPI, pinned with hashes, as on any other computer.
What is slower: the first build, voice typing (HouseOS picks the smaller `base` speech model on
ARM boards and computers with under 6 GB of memory; `HOUSEOS_VOICE_MODEL=small` in `.env`
chooses the other one) and film preparation when a film must be converted for the TV (direct
playback is unaffected). Music, Cast and DLNA speakers, phones and the rest run as usual.
From an SD card, the first start can take 10 minutes or more. HDMI sound: if nothing plays,
choose the HDMI output in *Control Room → Speakers*.

## 9. Updates, backups and the Control Room buttons

```bash
./houseos.sh update        # download the new version, rebuild, restart
./houseos.sh backup        # database + state (keys) + files into backups/<date>
./houseos.sh gpu on|off    # voice typing on the NVIDIA card, or the processor
./houseos.sh torrents on|off  # the torrent player: a stream add-on without a debrid service (§6)
./houseos.sh buttons on|off   # the Control Room buttons (the helper, below)
./houseos.sh own-address   # HouseOS as its own device on the network (§3)
./houseos.sh setup-code    # the one-time setup code again
./houseos.sh status        # what runs;   ./houseos.sh logs [api worker…]   what it says
```

**Knowing when there is a new version.** With the Control Room buttons on (below), HouseOS looks
for a new version every 6 hours (or at once: *Control Room → Services → Check for updates*).
When one is out, every admin gets a note from Nox in their inbox. Then either:

- press **Update HouseOS** in *Control Room → Services*;
- ask Nox: *"update HouseOS"* (it shows a card to confirm);
- or tick **Update by itself at night**: it updates between 3 and 5 am (the house's time), only
  when nothing is playing.

Music that was playing comes back at the same second after an update.

**Control Room buttons.** `./houseos.sh buttons on` (or *yes* when installing) adds a small
**helper** service, so *Control Room → Services* can run update, backup, GPU voice and own
address with a button, showing progress and the result. HouseOS may disappear for a few minutes
during an update; the page comes back by itself. `./houseos.sh buttons off` removes it.

Know what it means: the helper holds **the Docker socket**, which is as powerful as being this
computer's administrator. It is kept narrow: it has no network, it only runs the fixed actions
of `houseos.sh`, and only when the app asks with a note signed by the house's own key. The parts
of HouseOS that touch the internet (downloads, sound, the AI clients) never hold that key.

**Backups** land in `backups/<date>/` next to HouseOS: `houseos-db.tgz` (the database),
`houseos-files.tgz` (the state, which holds the keys that unlock saved passwords, and your files)
and `houseos.env` (your settings, with the database password). Everything pauses for about a
minute. Keep them private, and copy them to another disk or computer. To restore on a fresh
clone, before the first start, put the settings back first, then the data:

```bash
cp backups/<date>/houseos.env .env && chmod 600 .env
docker compose create
docker compose run --rm --no-deps -u 0 -v "$PWD/backups/<date>":/b --entrypoint tar db  xzf /b/houseos-db.tgz -C /var/lib/mysql
docker compose run --rm --no-deps -u 0 -v "$PWD/backups/<date>":/b --entrypoint tar api xzf /b/houseos-files.tgz -C /
docker compose up -d
```

`docker compose down` stops HouseOS and keeps everything; `docker compose down -v` **deletes**
the volumes: only for a real fresh start.

## 10. On a Windows PC

HouseOS runs in **WSL 2** with Docker Engine installed inside Ubuntu; follow
[docs/WINDOWS.md](WINDOWS.md) step by step. In short: WSL's **mirrored networking** gives
HouseOS the PC's own address on your network (Windows 11 22H2 or later), a Windows firewall rule
opens ports 8443 and 8991, and `./houseos.sh` sees it runs in WSL and adds `compose.wsl.yml` so
music plays on the PC's speakers. `./houseos.sh own-address` is refused on WSL: HouseOS uses the
PC's address. Docker Desktop also starts HouseOS, but its network is separated from your home
network, so casting and Find devices don't work there.

## 11. Other systems

- **Unraid**: keep the HouseOS folder under `/mnt/user/appdata`.
- **Proxmox**: run HouseOS in a VM, or in an LXC container with `nesting=1,keyctl=1`.
- **Linux Mint, Arch**: install Docker from the distribution's packages (Docker's `get.docker.com`
  script refuses them), with its Compose plugin (2.24 or newer).
- **SELinux** (Fedora, RHEL with `moby-engine` or Docker CE): the import folder is labelled for
  Docker by itself. If `docker compose logs audio` (or `helper`, `worker`, `cinema-worker`) shows
  "permission denied", give that service `security_opt: ["label=disable"]` in a
  `compose.selinux.yml` next to `docker-compose.yml`, and add it to `COMPOSE_FILE` in `.env`
  (`COMPOSE_FILE=docker-compose.yml:compose.selinux.yml`, keeping any files already listed).
- **Not supported**: Podman, rootless Docker and 32-bit systems (`./houseos.sh` says so). Docker
  from snap works with limits; Docker Engine is recommended.

## When something is off

First: `./houseos.sh logs` (the last lines, live) and *Control Room → Services*, which says in
plain words which part stopped. Nox in setup mode (admins) reads the same diary and checks.

| You see | Do |
|---|---|
| `permission denied` on `/var/run/docker.sock` | `sudo usermod -aG docker $USER`, then log in again (or `newgrp docker`). |
| `docker compose` not found | The Compose v2 plugin is missing: install `docker-compose-plugin` from Docker's repository. |
| The build fails while downloading | Run `./houseos.sh install` again (it resumes); check the internet and free disk (`df -h`). |
| Port 8443 already used | `./houseos.sh install` picks 9443 (or the next free one) and says so. For another: `HOUSEOS_HTTPS_PORT=…` in `.env`, then `./houseos.sh install` again. |
| Port 8990 or 8991 already used | Another program holds it; `sudo ss -ltnp 'sport = :8991'` names it. Stop it, then `./houseos.sh install` again. |
| Phones can't open it, or `houseos.local` does not open | Same Wi-Fi as the server, not a guest network. Use `https://<server-ip>:8443` (some phones don't look up `.local` names). On Windows, re-check [WINDOWS.md](WINDOWS.md) (mirrored networking, the firewall rule, a **Private** network). Away from home: §3. |
| "HouseOS was opened at … not one of its trusted addresses", or "does not answer to the name …" | Only the address you signed up at (and `houseos.local`) is trusted. Open HouseOS at that address and add the new one in *Control Room → Access → Addresses → Another address*. |
| "Not secure" or a certificate warning | The connection is encrypted; the certificate is the house's own. Per device: *Control Room → Access → Download the certificate* and install it as a trusted certificate authority (iPhone: then *Settings → General → About → Certificate Trust Settings*). For a real certificate: `tailscale serve --bg 8990`, or your own domain (§3). |
| The microphone explains it needs a secure address | Use an `https://` address: `https://houseos.local:8443`, `https://<server-ip>:8443` or your proxy. |
| A service is *Not answering* in *Control Room → Services* | Press its Restart button; if it stays red, `docker compose logs <service>` shows why. |
| No sound, or Listen says no speaker is playing | Choose one in *Control Room → Speakers*, or *Play on this device* on a phone (§4). |
| Find devices lists nothing, or a TV can only be turned off | [DEVICES.md](DEVICES.md#when-a-device-isnt-found): same network, firewall ports, which brand needs Home Assistant. A TV that is neither Cast nor DLNA can open HouseOS in its web browser. |
| TVs or speakers can't play, and this computer uses a VPN or a Tailscale exit node | HouseOS gives them the VPN's address. Put this computer's home address in `.env` (`HOUSEOS_LAN_ADDRESS=…`), then `docker compose up -d`. |
| Anime rows are empty | The anime list downloads on the first start (a minute). *Control Room → Services* shows whether `maintenance` runs. |
| Anything else | Open the HouseOS folder in a coding agent (Claude Code, Codex…): [DEVICES.md → Fix it with an agent](DEVICES.md#fix-it-with-an-agent) has a ready-made request. |
