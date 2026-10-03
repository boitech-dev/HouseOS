# HouseOS on a Windows PC

This guide is written so that you, or an AI agent working for you, can install HouseOS on a
Windows PC and keep it running as the house's server. Every step has a check. Do them in order.

HouseOS runs in Linux containers. On Windows they run inside **WSL 2** (Windows' built-in
Linux), with **Docker Engine installed inside Ubuntu**. This behaves like a Linux server:
casting to TVs, finding devices on the network and playing music on the PC's own speakers all
work. Docker Desktop also runs HouseOS, but its network is separated from your home network,
so casting and device discovery don't work there. Use it only to try the app.

## What you need

- Windows 11 22H2 or later. **Windows 10: HouseOS works only from the PC itself (phones and TVs
  can't reach it)**, because Windows 10 has no mirrored networking.
- Virtualisation turned on in the BIOS. Task Manager → Performance → CPU says "Virtualization: Enabled".
- 8 GB of memory (16 GB is more comfortable) and 30 GB of free disk.
- An administrator account, for the setup steps only.
- Optional: an NVIDIA graphics card with current drivers, for faster voice typing.

## 1. Install WSL and Ubuntu

In **PowerShell as administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart when asked. Ubuntu then opens and asks you to create a Linux user name and password.

Check it in PowerShell with `wsl -l -v`: `Ubuntu-24.04` shows `VERSION 2`.

## 2. Put WSL on your home network and keep it running

Create or edit `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
vmIdleTimeout=-1

[experimental]
hostAddressLoopback=true
```

- **Mirrored networking** gives HouseOS the PC's own address on your network, so phones can
  reach it and TVs can fetch films from it. It needs Windows 11 22H2 or later.
- **`vmIdleTimeout=-1`** stops Windows from shutting Linux down when no window is open.

Then, in **PowerShell as administrator**:

```powershell
wsl --shutdown
# Let other devices on the network reach WSL (the WSL firewall's own switch):
Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
# The two HouseOS doors: the app (8443) and the media relay TVs fetch from (8991).
New-NetFirewallRule -DisplayName "HouseOS" -Direction Inbound -Protocol TCP -LocalPort 8443,8991 -Action Allow -Profile Private
```

Your home network must be set to **Private** in Windows (Settings → Network → your
connection → Private network), or the rule above does not apply.

Check it: open Ubuntu and run `hostname -I`. It shows the same address as `ipconfig` in
Windows (for example `192.168.1.50`).

## 3. Turn on systemd and install Docker Engine inside Ubuntu

Recent Ubuntu images already have systemd. Check with `cat /etc/wsl.conf`. If it doesn't
contain `systemd=true`, add it:

```bash
printf '[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf
```

Then run `wsl --shutdown` in PowerShell and reopen Ubuntu.

Install Docker Engine from Docker's own repository (steps from
https://docs.docker.com/engine/install/ubuntu/):

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Close Ubuntu, open it again, and check with `docker run --rm hello-world`, which prints
"Hello from Docker!".

## 4. Get HouseOS in Linux (not onto C:)

Keep HouseOS in the Linux file system. It is many times faster than `/mnt/c`, and the
scripts keep their permissions there. In Ubuntu:

```bash
cd ~ && git clone https://github.com/boitech-dev/HouseOS.git && cd HouseOS
```

## 5. Install

```bash
./houseos.sh install
```

It makes a private database password, sees that it runs on Windows (WSL), plays music on this
PC's speakers, offers the graphics card if there is one, builds everything (10–20 minutes the
first time), then prints **your one-time setup code** and the addresses to open.

Check it: in a browser, open `https://<the PC's address>:8443` (the address the phones will use;
`ip -4 addr` inside Ubuntu shows it, the same as Windows'). Accept the certificate warning once,
enter the setup code, and create the first (administrator) account: HouseOS trusts the address
you sign up at. Then open the same address from a phone on the same Wi-Fi. `https://localhost:8443`
on the PC works too, but only once you add it (or any other address) in *Control Room → Access →
Addresses → Another address*.

## 6. Music on the PC's speakers

`houseos.sh` adds `compose.wsl.yml` by itself when Windows' Linux sound bridge (WSLg) is
there. Check it: Control Room → Speakers lists "This computer" as the output → "Test tone" →
you hear it. If there is no sound, `ls /mnt/wslg/PulseServer` inside Ubuntu must show a file.
If it doesn't, update WSL with `wsl --update` in PowerShell, then run `wsl --shutdown`. Phones
(Speaker mode) and Cast speakers work either way.

Games: **Play here** works on every phone and computer; **Play on the TV** needs HouseOS on
Linux itself, not in WSL ([GAMES.md](GAMES.md)).

## 7. Start with Windows

The containers restart whenever Docker starts, and Docker starts with Ubuntu. Ubuntu must start
when you sign in: in **Task Scheduler → Create Task**, set the trigger "At log on", and add the
action `wsl.exe` with the arguments `-d Ubuntu-24.04 --exec sleep infinity`. Tick "Run whether
user is logged on or not" if the PC runs without anyone signed in.

Check it: restart Windows, wait two minutes, and open `https://<the PC's address>:8443`.

## 8. Optional: voice typing on the graphics card

Install the current NVIDIA driver in Windows (not inside Ubuntu), then follow "Installing with
Apt" at https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
inside Ubuntu. Then run `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl
restart docker`, then `./houseos.sh gpu on`.

## What works differently on Windows

- `./houseos.sh own-address` (HouseOS as its own device on the network) is Linux-only. On
  Windows, HouseOS uses the PC's address.
- `houseos.local` may not resolve from every phone. The PC's address always works.
- If casting can't find a TV by itself, add it by address in Control Room → Devices.

## Final checklist (all must pass)

1. `https://<PC address>:8443` opens HouseOS on the PC and on a phone.
2. Control Room → Setup shows every step as done or optional.
3. Listen: search a song, it plays and is heard from the PC's speakers.
4. Watch: a film's page opens. If a TV and a film source are set up, it plays on the TV.
5. Ask (with an AI connected): the microphone button works over `https://`.
6. After a Windows restart, all of the above still works without opening anything.

## Changing HouseOS with an agent

- Read `AGENTS.md`, then `docs/ARCHITECTURE.md`. `docs/CODE-INDEX.md` maps every function and
  route, and `docs/TESTING.md` explains the checks.
- After changing code: `docker compose up -d --build` in the HouseOS folder rebuilds and
  restarts. With git, `./houseos.sh update` also pulls the new version first.
- Before sharing your copy: `python3 tools/privacy_scan.py .` must print PASS.
- Never commit or share `.env`, `backups/` or Docker's volumes: they hold your keys, accounts
  and household data.
