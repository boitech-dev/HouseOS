# Installing HouseOS: guide for an AI agent

You are installing **HouseOS** for a person, on their computer, and then walking them through
its setup. Work autonomously; talk to them only to welcome them, ask what only they can answer,
and show progress. Keep your messages short, warm and in their language (HouseOS speaks English,
French, and any language Nox adds; match whichever they write in).

> Changing HouseOS's code is a different job: that starts at [AGENTS.md](AGENTS.md).

## 0. Rules

- **Check, don't assume.** Every step below ends with a check; run it before moving on.
- **Ask before** installing system packages, using `sudo`, restarting the computer or WSL, or
  changing Windows settings. One clear question, with why.
- **Secrets stay secret.** Never repeat the setup code, API keys or passwords in logs, files or
  commits. The person types their own keys into HouseOS's Control Room, not into this chat.
- **Stay on the home network.** Never open HouseOS to the internet, touch the router or weaken a
  firewall beyond the ports named here, from the home network only: TCP 8443 and 8991, UDP 5353
  (mDNS) and 1900 (SSDP) for Find devices.
- **Honest status.** Say what really happened ("the build finished", "the page opens"), not
  what should have.
- **The person decides** what to connect. Everything after the first account is optional except
  the six essentials in §5.

## 1. Welcome them

Send this (adapt the language, keep the tone):

> 👋 Hello! I'm going to set up **HouseOS** for you: your home's own app, with a fair jukebox
> everyone takes turns on, films sent to the TV in one tap, the groceries, the chores, and Nox,
> the house assistant who runs the place.
>
> Here's the plan: I check this computer, install what's missing, start the house (10 to 20
> minutes the first time), then we open it together and I show you the essentials. I'll only
> ask you questions when I really need you. Shall we begin? 🕯️

## 2. Check the computer

HouseOS runs on **one computer that stays on at home**. Everyone else just opens a browser.

| Needs | Minimum | Check |
|---|---|---|
| OS | 64-bit Linux (x86_64 or arm64), or Windows 11 with WSL 2 (on Windows 10, HouseOS works only from the PC itself: phones and TVs can't reach it) | `uname -sm`, or `winver` on Windows |
| Memory | 4 GB, 8 GB comfortable (Windows: 8 GB, 16 GB comfortable) | `free -g` |
| Disk | 30 GB free, plus room for songs and films | `df -h ~` |
| Docker | Docker Engine (not Podman, rootless Docker or Docker Desktop) with Compose v2 (2.24+) | `docker compose version` |
| git | any | `git --version` |
| Network | same home network as the phones (not a guest Wi-Fi) | — |

Choose the path:

- **Linux** (PC, mini-PC, NAS, laptop): §3A.
- **Windows**: §3B.
- **Raspberry Pi 4/5** with 4 GB+ and a 64-bit OS: §3A, then add `HOUSEOS_VOICE_MODEL=base` to `.env`.
- **macOS**: HouseOS cannot be *hosted* on a Mac (it needs Linux host networking and sound). Tell
  them kindly, and offer another computer at home (an old laptop or a mini-PC is perfect); the
  Mac can still use HouseOS in its browser.

## 3A. Install on Linux

1. **Docker**, if `docker compose version` fails. Ask first, then (Debian/Ubuntu and most distros):

   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker "$USER"
   ```

   The group change needs a new login: use `newgrp docker` in this shell, or ask them to log out
   and in. **Check:** `docker run --rm hello-world` prints "Hello from Docker!".

2. **Get HouseOS:**

   ```bash
   git clone https://github.com/boitech-dev/HouseOS.git ~/HouseOS && cd ~/HouseOS
   ```

   **Check:** `ls houseos.sh docker-compose.yml`.

3. **Ask two questions**, because the script's own prompts answer *no* by themselves when no one
   is at a terminal (as with you):
   - "Should Control Room be able to update and back up HouseOS with a button?" (the *helper*:
     it holds Docker's socket, restricted to signed HouseOS actions). If **yes**, run
     `./houseos.sh buttons on` after the install.
   - Only if `nvidia-smi` works: "Use the graphics card for voice typing?" If **yes**, run
     `./houseos.sh gpu on` after the install.

4. **Install:**

   ```bash
   ./houseos.sh install
   ```

   It makes a private database password, builds and starts everything (10–20 minutes the first
   time, 20–40 on a Raspberry Pi), then prints the **one-time setup code** and the addresses.
   **Check:** the output ends with `https://…:8443` lines, and `./houseos.sh status` shows the
   services `running`.

## 3B. Install on Windows

Follow **[docs/WINDOWS.md](docs/WINDOWS.md)** in order; it is written for you, with a check after
each step. In short:

1. PowerShell **as administrator**: `wsl --install -d Ubuntu-24.04`, then restart (ask first).
2. `C:\Users\<them>\.wslconfig` with mirrored networking (Windows 11 22H2+), `wsl --shutdown`,
   and the firewall rule for ports 8443 and 8991. Their network must be set to **Private**.
3. Inside Ubuntu: systemd on, Docker Engine from Docker's repository.
4. HouseOS in the Linux home folder (never on `C:`), then §3A steps 2–4.
5. Music plays on the PC's own speakers automatically (WSLg).

## 4. First visit together

Tell them, in these words or close:

> The house is up! 🏠 On this computer or your phone (same Wi-Fi), open
> **https://houseos.local:8443** (or the other address I showed you). Your browser will warn you
> about the certificate once: that's HouseOS's own, so choose *Advanced → Continue*. Then enter
> the **setup code** and create your account; you'll be the house's admin.

- The code is printed by `./houseos.sh setup-code` any time until the first account exists.
- The address they sign up at becomes trusted. Other addresses are added later in Control Room → Access.
- **Check:** they see the Home page with their name.

## 5. Walk through the setup

In HouseOS: **avatar menu → Control Room → Setup**. It checks each part for real and links to the
right tab. Go through it together, one item at a time, and skip what they don't want. HouseOS
ships with none of this: every account, key and device is theirs.

| Item | Essential | What they need / do |
|---|---|---|
| House | ✓ | Name, language, time zone (Control Room → House). Until then: "MIDNIGHT HOUSE", UTC, English. |
| Access | ✓ | Done once they use the `https://` address. To lose the certificate warning: *Control Room → Access → Download the certificate* on each device, or a reverse proxy / Tailscale ([docs/DOCKER.md §3](docs/DOCKER.md#3-behind-your-own-reverse-proxy)). |
| AI for Nox | ✓ | Control Room → AI: sign in with ChatGPT or Claude, or paste an OpenRouter / OpenAI / Anthropic key, or their own model (Ollama…). Without it, Nox's ready-made buttons still work. |
| Speakers | ✓ | Control Room → Speakers: the computer's own output (Bluetooth included), a Cast or DLNA speaker, or phones with *Play on this device*. |
| Sources | ✓ | Automatic (the `fetch` service): YouTube, SoundCloud, radio. |
| Invite | ✓ | Control Room → People → Invites: a link per housemate; guests get a party pass. |
| Films | | Sources they choose: their own files (Files, or imports), their **Jellyfin**, or a Stremio add-on they add themselves (Control Room → Integrations → Stream add-on: *Browse add-ons* opens a community catalogue, they pick one, paste their own debrid API token on its page and paste its link back). HouseOS names and includes no add-on: let them choose. No debrid service: `./houseos.sh torrents on`, then tick *Play torrents from this computer* ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)). |
| TV | | Control Room → Devices → Find devices (Chromecast, Google TV, DLNA), or add one by address. The host firewall must let the home network in on TCP 8991 and UDP 5353 and 1900. |
| Smart home | | Control Room → Integrations → Home Assistant: its address and a long-lived token. |
| Voice | | Downloads by itself; works on `https://` addresses. |
| Backups | | Control Room → Recovery, or `./houseos.sh backup`; copy the backups to another disk. |
| Extras | | Jellyfin, OpenSubtitles, push notifications: their own servers or keys ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)). |

Already there by default: the fair queue, *Even out songs*, the online genre lookup, a 5 h music
sleep timer, quotas of 20 GiB per person and 200 GiB of shared media (all in Control Room →
House), Nox's prompts, tools and ready-made requests, translations, art and the built interface.
The film index ships with HouseOS and refreshes weekly from Wikidata; the anime database daily.
Without Docker, [docs/SETUP.md](docs/SETUP.md) lists what to provide by hand (database, keys,
storage, audio bridge, fetcher).

## 6. Show them around

When the essentials are green, send:

> ✨ Your house is ready! A quick tour:
> - 🎶 **Listen**: paste a link or search. Songs take turns, one each per round; anyone can move
>   a waiting song, and everyone has one veto every 3 hours. **Auto play** keeps the music going.
> - 🍿 **Watch**: films, series and anime. Pick one, confirm once, it plays on the TV.
> - 📋 **House**: groceries, tasks (tick, confirm, done), the calendar and messages.
> - 🐾 **Nox**: ask anything, typed or by voice: "put some jazz on", "what's on this week?".
> - 🏠 **Home** shows today at a glance; **Files** keeps your files and the house's music and films.
>
> Invite your housemates from Control Room → People → Invites, and enjoy! 🕯️

Offer the in-app tour too: in Nox, the button **"How does the house work?"**.

## 7. When something is off

Run `./houseos.sh logs` (last lines, live), then use the table in
[docs/DOCKER.md → When something is off](docs/DOCKER.md#when-something-is-off). Ask before
touching their web server, DNS, router or firewall.

## 8. Reference

- **Commands** (in the HouseOS folder): `./houseos.sh` (menu) · `install` · `update` · `backup` ·
  `status` · `logs [SERVICE…]` · `setup-code` · `gpu on|off` · `torrents on|off` · `own-address [IP|off]` ·
  `buttons on|off`.
- **Ports**: TCP 8443 (the app, HTTPS), TCP 8991 (media to TVs and speakers), UDP 5353 and 1900
  (Find devices, `houseos.local`). 8990 is local-only plain HTTP for a reverse proxy.
- **Data**: Docker volumes `houseos-state` (keys: back them up, keep them private), `houseos-data`
  (files, songs, films) and the database volume. `./houseos.sh backup` saves all three.
- **Updates**: `./houseos.sh update`, or Control Room → Services when the helper is on.
- **Deeper**: [docs/DOCKER.md](docs/DOCKER.md) (every Docker option), [docs/WINDOWS.md](docs/WINDOWS.md),
  [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md), [docs/TESTING.md](docs/TESTING.md) (what to check on their devices).
