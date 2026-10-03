# Your machine, your hosting, your home

## Access

Nothing in this repository configures your hosting. With Docker, HouseOS opens an HTTPS door on
your network (see DOCKER.md); natively, start with the loopback URL in SETUP.md §2. To share locally,
choose your own hostname/HTTPS endpoint and certificate trust, explicitly configure allowed origins,
secure cookies and the host firewall for your household LAN. Do not expose the API or upload
transport indiscriminately. Use a dedicated hostname on a shared machine because cookies are
host-scoped across ports.

For private remote access, install/sign in to **your own Tailscale** (or another private VPN),
review its access policy and configure your own Serve endpoint to your loopback app. Check your
installed Tailscale documentation for the current command syntax. No Funnel, public internet
exposure or router forwarding is included or required. The repository contains no tailnet name,
certificates or network rules.

Ports:

| Port | Docker | Native (suggested) |
|---|---|---|
| 8443 | HTTPS door for phones and computers | an optional private HTTPS listener of your choice |
| 8990 | API, loopback only unless `HOUSEOS_BIND` says otherwise | API, loopback |
| 8991 | media relay TVs and speakers fetch from (LAN) | media relay (LAN) |
| 8992 | upload transport, internal | upload transport, loopback |

Verify conflicts first. Your receiver needs the scoped media relay via your LAN, not the private
provider API credentials. Restrict receiver access to approved destinations. Never make the relay
an arbitrary URL proxy.

## Native service adaptation

`docs/native/` preserves HouseOS service/backup/control implementation examples with
generic paths. An agent must map them to the recipient's directories, runtime users and approved
network. No scripts automatically perform this installation. Leave optional providers and physical
controls disabled until configured. Retain service isolation and resource bounds; the fetcher must
not gain DB/config access, and parser processes must not gain arbitrary network access. Include the
maintenance service (`houseos-maintenance.service`): reminders, song genres and the weekly film
index depend on it.

The Control Room allowlist names HouseOS-specific services and private sockets. If using a
different service namespace, update `control_room.py` and the matching broker together. Do not
point them at unrelated services. Its shutdown feature is only fully available after the matching
native broker/service installation. The local helper can be stopped using Ctrl+C.

## Backups and upgrades

**Docker.** `./houseos.sh backup` writes the database, the state volume (which holds the keys that
unlock saved passwords) and your files to `backups/<date>/`; `./houseos.sh update` pulls the new
version, rebuilds and restarts. With the optional helper (`./houseos.sh buttons on`), Control Room →
Services runs the same actions with a button. DOCKER.md §9 has the restore steps.

**Native.** Before migrations: back up your HouseOS schema, encrypted configuration keys and
settings. Retain a compatible code release. Test restore into a separate database and runtime,
never overwrite an unrelated database. Use separate migration/runtime credentials. Keep backups
encrypted and private; never put them into the repository. Retained uploads/media need their own
documented backup policy; temporary stream buffers do not.

Apply code updates to an isolated copy, install locked dependencies, build, migrate with a backup
and restart only affected services. A Cinema worker restart can interrupt its playback; a music
bridge restart cuts the current song, so restart it when nothing plays. Music should continue
through unrelated changes. No automatic reboot is needed or scheduled.

## Moving to another home

1. Stop your instance cleanly and back up your own data/configuration. Keep your keys private.
2. On the new machine, install platform dependencies and restore only your HouseOS data to a new
   isolated schema/runtime (Docker: restore the backup before the first start).
3. Native: reconfigure storage mount/UUID/import root and check quota/durable write behavior.
4. Remove old destinations/pairings in your copy. Set the new LAN CIDR/media relay address, enroll
   your new TV/Cast/Home Assistant entities and speaker output, and pair the TV remote again if you
   use its arrows.
5. Update your own HTTPS origins/certificates and VPN endpoint. Do not carry another home's private
   addresses or firewall rules forward.
6. Verify actual picture/audio/subtitles, seek, stop, disconnect recovery and music output. Keep the
   app honest about unverified capabilities.

Two independent HouseOS servers on one network can both send Cast commands to the same TV;
separate databases do not stop them interrupting one another. Agree who uses the TV. HouseOS
enrolls no device by itself and sends no test playback.

## Make your own version

HouseOS is a git repository: keep your changes under git; runtime data, secrets and dependency
caches stay ignored. You may rename/retheme/change HouseOS. Read ARCHITECTURE before altering
ownership, media or tool flows. The included original artwork is separate from the HTML controls
and can be replaced. Keep dependency notices/licenses when redistributing. Before sharing your fork,
run `python3 tools/privacy_scan.py . --git`; never share your `.env`, `backups/`, Docker volumes,
browser profile or live database.
