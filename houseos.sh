#!/usr/bin/env bash
# HouseOS on this computer, in one script. Run it with no arguments for a menu.
#   ./houseos.sh install          first start: settings, build, start, your setup code
#   ./houseos.sh update           download the new version and restart HouseOS
#   ./houseos.sh backup           database + keys + files into ./backups/<date>
#   ./houseos.sh gpu on|off       voice typing on an NVIDIA graphics card
#   ./houseos.sh torrents on|off  the torrent player: a stream add-on without a debrid service (docs/INTEGRATIONS.md)
#   ./houseos.sh own-address [IP|off]   HouseOS as its own device on your network
#   ./houseos.sh buttons on|off   let Control Room run these from the app (the helper)
#   ./houseos.sh setup-code | status | logs [SERVICE…]
#   (the helper also runs `code apply|undo|keep ID`: a change applied in Control Room → Changes)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

say() { printf '%s\n' "$*"; }
fail() { printf 'HouseOS: %s\n' "$*" >&2; exit 1; }
result() { printf 'RESULT %s=%s\n' "$1" "$2"; }   # read back by Control Room
# COMPOSE_BAKE: Compose's faster build path (it otherwise prints a hint to set it; nothing to
# add to .env). Older Compose versions ignore it.
compose() { COMPOSE_BAKE=true docker compose ${HOUSEOS_PROJECT:+-p "$HOUSEOS_PROJECT"} "$@"; }
house_version() { sed -n 's/^__version__ = "\(.*\)".*/\1/p' backend/houseos/__init__.py 2>/dev/null; }

set_env() { # replace or add one line of .env
  touch .env
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
drop_env() { if [ -f .env ]; then sed -i "/^$1=/d" .env; fi; }

# The optional compose files this install uses live in COMPOSE_FILE (.env).
extras() { grep -s '^COMPOSE_FILE=' .env | cut -d= -f2 | tr ':' '\n' | grep -v -e '^docker-compose.yml$' -e '^$' || true; }
has() { extras | grep -qx "$1"; }
use() { # use FILE on|off
  local files=(docker-compose.yml) other
  for other in $(extras); do [ "$other" = "$1" ] || files+=("$other"); done
  [ "$2" = on ] && files+=("$1")
  if [ "${#files[@]}" -gt 1 ]; then set_env COMPOSE_FILE "$(IFS=:; echo "${files[*]}")"; else drop_env COMPOSE_FILE; fi
}

need_docker() {
  command -v docker >/dev/null || fail "Docker is not installed: https://docs.docker.com/engine/install/"
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 (the 'docker compose' command) is missing."
  local version
  version=$(docker compose version --short 2>/dev/null | sed 's/^v//')
  [ "$(printf '%s\n' 2.24 "$version" | sort -V | head -1)" = 2.24 ] \
    || fail "HouseOS needs Docker Compose 2.24 or newer (this computer has $version). Update Docker from Docker's own repository (https://docs.docker.com/engine/install/), then try again."
  docker info >/dev/null 2>&1 || fail "Docker is not running, or this user may not use it (sudo usermod -aG docker \$USER, then log in again)."
}
# First install only: the Docker setups HouseOS cannot run on (or not fully).
check_engine() {
  local engine=https://docs.docker.com/engine/install/
  [ "$(uname -s)" = Linux ] || fail "HouseOS runs on Linux. On Windows, run it inside WSL 2 (docs/WINDOWS.md); a Mac cannot host HouseOS."
  ! docker --version 2>&1 | grep -qi podman || fail "Podman is not supported: install Docker Engine ($engine)."
  ! docker info -f '{{json .SecurityOptions}}' 2>/dev/null | grep -q rootless \
    || fail "Rootless Docker cannot share this computer's network with HouseOS (TVs, speakers, houseos.local): install regular Docker Engine ($engine)."
  # The engine's own build, not the kernel's: 32-bit Raspberry Pi OS runs on a 64-bit kernel.
  case "$(docker version -f '{{.Server.Arch}}' 2>/dev/null)" in
    amd64 | arm64) ;;
    *) fail "HouseOS needs a 64-bit system (64-bit Raspberry Pi OS on a Pi 4/5)." ;;
  esac
  if docker info -f '{{.OperatingSystem}}' 2>/dev/null | grep -q 'Docker Desktop'; then
    say "Note: on Docker Desktop, casting to TVs and Find devices don't work (its network is separate). Docker Engine does: $engine"
  fi
  if readlink -f "$(command -v docker)" | grep -q '^/snap/'; then
    say "Note: Docker from snap may not reach folders outside your home or this computer's sound. Docker Engine is recommended: $engine"
  fi
}
wsl() { grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; }
gpu_available() { docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; }
ask() { # ask QUESTION → yes unless the person answers no (no when nobody is at a terminal)
  [ -t 0 ] || return 1
  local answer; read -r -p "$1 [Y/n] " answer; [[ ! "${answer:-y}" =~ ^[Nn] ]]
}

wait_ready() {
  local start=$SECONDS told=
  until compose exec -T api python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8990/api/v1/health', timeout=2)" \
    >/dev/null 2>&1; do
    [ $((SECONDS - start)) -lt 600 ] || fail "HouseOS did not answer within 10 minutes. See: docker compose logs api"
    if [ -z "$told" ] && [ $((SECONDS - start)) -ge 120 ]; then
      say "Still starting… (the first start takes longer on a Raspberry Pi or a slow disk)"; told=1
    fi
    sleep 2
  done
}

https_port() { # the HTTPS door's port; at its own address (compose.lan.yml) it is always 8443
  local port=
  has compose.lan.yml || port=$(grep -s '^HOUSEOS_HTTPS_PORT=' .env | cut -d= -f2 || true)
  echo "${port:-8443}"
}
# ss lists listening ports; without it, nothing counts as taken and Docker says so if one is.
port_taken() { ss -Hltn "( sport = :$1 )" 2>/dev/null | grep -q .; }
check_ports() { # before the first start: a port another program holds stops HouseOS
  [ -z "$(compose ps -q 2>/dev/null)" ] || return 0   # running: HouseOS holds them itself
  local port free
  port=$(https_port)
  if ! has compose.lan.yml && port_taken "$port"; then
    for free in 9443 9444 9445 10443 ""; do [ -n "$free" ] && ! port_taken "$free" && break; done
    [ -n "$free" ] || fail "Port $port is in use by another program: put a free one in .env (HOUSEOS_HTTPS_PORT=…), then run ./houseos.sh install again."
    set_env HOUSEOS_HTTPS_PORT "$free"
    say "Port $port is used by another program, so HouseOS opens on port $free instead (allow it in your firewall if you run one)."
  fi
  for port in 8990 8991; do
    [ "$port" = 8991 ] && has compose.lan.yml && continue   # the relay is at its own address then
    if port_taken "$port"; then
      fail "Port $port is used by another program on this computer, and HouseOS needs it. Find it with: sudo ss -ltnp 'sport = :$port', stop it, then run ./houseos.sh install again."
    fi
  done
}

addresses() {
  local port ip
  port=$(https_port)
  ip=$(grep -s '^HOUSEOS_LAN_IP=' .env | cut -d= -f2 || true)
  say "Open HouseOS from a phone or computer on this network:"
  say "  https://houseos.local:$port"
  if has compose.lan.yml && [ -n "$ip" ]; then
    say "  https://$ip:$port"
  else
    for ip in $(hostname -I 2>/dev/null); do
      case "$ip" in *:* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) ;; *) say "  https://$ip:$port" ;; esac
    done
  fi
  say "Your browser warns once about the certificate HouseOS made for itself: accept it."
  if wsl; then
    say "On Windows, phones reach HouseOS only with WSL's mirrored networking and a firewall rule:"
    say "  see docs/WINDOWS.md (two settings, once)."
  fi
}

cmd_install() {
  need_docker
  check_engine
  if ! grep -qs '^HOUSEOS_DB_PASSWORD=' .env; then
    set_env HOUSEOS_DB_PASSWORD "$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 28 || true)"
    say "Made a private database password (in .env)."
  fi
  if wsl && [ -S /mnt/wslg/PulseServer ] && ! has compose.wsl.yml; then
    use compose.wsl.yml on   # music on the Windows PC's speakers
    say "Windows (WSL) found: music will play on this PC's speakers."
  fi
  if gpu_available && ! has compose.gpu.yml && ask "An NVIDIA graphics card is available. Use it for voice typing?"; then
    use compose.gpu.yml on
  fi
  if ! has compose.helper.yml && ask "Let Control Room update and back up HouseOS with a button (the helper; see docs/DOCKER.md)?"; then
    use compose.helper.yml on
  fi
  check_ports
  say "Building and starting HouseOS (10 to 20 minutes the first time)…"
  compose up -d --build --remove-orphans
  wait_ready
  say ""
  cmd_setup_code
  addresses
}

cmd_update() {
  need_docker
  local before
  before="$(house_version)"
  if [ -d .git ]; then
    say "Downloading the new version…"
    git fetch --quiet || fail "The new version could not be downloaded. Check this computer's internet connection, then run ./houseos.sh update again."
    [ -z "$(git tag -l 'houseos-backup/*')" ] \
      || fail "A change made in Control Room → Changes is waiting for Keep or Undo: choose there, then update."
    if git merge-base --is-ancestor HEAD '@{upstream}' 2>/dev/null; then
      git merge --quiet --ff-only '@{upstream}'
    elif [ -z "$(git status --porcelain --untracked-files=no)" ]; then
      # The published history moved on (or was rewritten). Follow it; changes made here with Nox
      # ("Nox: …" commits) go back on top. .env, backups and data are not tracked and stay.
      local was mine commit
      was=$(git rev-parse HEAD)
      mine=$(git log --reverse --format='%H %s' '@{upstream}..HEAD' | awk '$2 == "Nox:" {print $1}')
      git reset --quiet --hard '@{upstream}'
      for commit in $mine; do
        if ! git -c user.name=Nox -c user.email=nox@example.invalid cherry-pick "$commit" >/dev/null 2>&1; then
          git cherry-pick --abort 2>/dev/null || true
          git reset --quiet --hard "$was"
          fail "A change made with Nox ($(git log -1 --format=%s "$commit")) conflicts with the new version, so nothing was updated: see docs/CHANGING-HOUSEOS.md (Updates)."
        fi
      done
    else
      fail "Files in this folder were edited, so the new version was not applied. See them with: git status"
    fi
  else
    say "This copy did not come from git: copy the new version over this folder (your .env stays), then run ./houseos.sh update."
  fi
  if [ "$before" = "$(house_version)" ]; then
    say "You already have HouseOS $before; restarting it on the same version."
  else
    say "HouseOS $before → $(house_version). What's new: docs/CHANGELOG.md"
  fi
  # Music playing now pauses for the restart and comes back at the same second afterwards.
  compose exec -T -u 0 api touch /state/run/resume-music >/dev/null 2>&1 || true
  say "Rebuilding and restarting HouseOS (a few minutes; nothing to answer). Music pauses and comes back by itself…"
  compose up -d --build --remove-orphans
  wait_ready
  result version "$(git describe --always --tags 2>/dev/null || echo "")"
  say "HouseOS $(house_version) is up to date and running."
}

cmd_backup() {
  need_docker
  local dir running keep="${1:-0}" names
  [[ "$keep" =~ ^[0-9]+$ ]] || keep=0   # 0 keeps every backup (Control Room → Recovery)
  dir="$PWD/backups/$(date +%Y-%m-%d_%H%M%S)"
  mkdir -p "$dir"
  # The settings too: the database password lives only in .env.
  [ ! -f .env ] || install -m 600 .env "$dir/houseos.env"
  # Everything but the helper pauses for a minute so the copy is consistent.
  running=$(compose ps --services --status running | grep -vx helper || true)
  [ -z "$running" ] || compose stop $running
  compose run --rm --no-deps -u 0 -v "$dir":/b --entrypoint tar db czf /b/houseos-db.tgz -C /var/lib/mysql .
  # The speech model downloads again by itself; sockets and caches are rebuilt at start.
  compose run --rm --no-deps -u 0 -v "$dir":/b --entrypoint tar api czf /b/houseos-files.tgz \
    --exclude=state/models --exclude=state/run/.cache --exclude='*.sock' -C / state data
  [ -z "$running" ] || compose start $running
  # Only the admin's "keep the last N" removes older backups: whole folders HouseOS made.
  if [ "$keep" -gt 0 ]; then
    ls -1d "$PWD"/backups/20*/ 2>/dev/null | sort | head -n -"$keep" | while read -r old; do
      [ -f "$old/houseos-db.tgz" ] && rm -rf -- "$old"
    done
  fi
  names=$(ls -1d "$PWD"/backups/20*/ 2>/dev/null | sort | tail -n 20 | xargs -r -n1 basename | sed 's/.*/{"name": "&"}/' | paste -sd, -)
  compose exec -T -u 0 api sh -c "printf '{\"created_at\": \"%s\", \"location\": \"%s\", \"keep\": %s, \"backups\": [%s]}' \"\$(date -u +%Y-%m-%dT%H:%M:%SZ)\" '$dir' '$keep' '$names' > /state/run/backup-status.json" || true
  result backup "$dir"
  say "Backup saved in $dir. It holds your keys: copy it to another disk and keep it private."
}

cmd_torrents() {
  case "${1:-}" in
    on) use compose.p2p.yml on ;;
    off) use compose.p2p.yml off ;;
    *) fail "Use: ./houseos.sh torrents on|off" ;;
  esac
  compose up -d
  say "The torrent player is $1. $([ "$1" = on ] && echo "Now tick \"Play torrents from this computer\" in Control Room → Integrations → Stream add-on.")"
}

cmd_gpu() {
  case "${1:-}" in
    on) gpu_available || fail "Docker cannot use an NVIDIA card here yet. Voice typing already works on the processor.
  For the graphics card: install the NVIDIA driver and the NVIDIA Container Toolkit
  (https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
  run: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
  then run ./houseos.sh gpu on again."
        use compose.gpu.yml on ;;
    off) use compose.gpu.yml off ;;
    *) fail "Use: ./houseos.sh gpu on|off" ;;
  esac
  compose up -d --build voice
  say "Voice typing now runs on the $([ "$1" = on ] && echo "graphics card" || echo "processor")."
}

cmd_own_address() {
  need_docker
  local ip="${1:-}" suggested answer
  if [ "$ip" = off ]; then
    use compose.lan.yml off
    compose up -d --remove-orphans
    say "HouseOS uses this computer's address again."
    return
  fi
  wsl && fail "Windows (WSL) cannot give HouseOS its own network address. Use the PC's address instead (docs/WINDOWS.md)."
  local version port
  version=$(docker compose version --short 2>/dev/null | sed 's/^v//')
  [ "$(printf '%s\n' 2.33 "$version" | sort -V | head -1)" = 2.33 ] \
    || fail "An own address needs Docker Compose 2.33 or newer (this computer has $version). Update Docker, then try again."
  if [ -t 0 ] && [ "$ip" = "" ]; then
    say "Optional. On Linux, HouseOS already finds TVs and speakers without it (it shares this"
    say "computer's network). Use it only on Docker Desktop, or to reach HouseOS at an address of its own."
  fi
  # lan-suggest reads the network from the relay, which must be on this computer's network.
  if has compose.lan.yml; then use compose.lan.yml off; compose up -d --remove-orphans relay; fi
  suggested=$(compose run --rm --no-deps relay lan-suggest | grep '^HOUSEOS_LAN_') \
    || fail "Could not read this computer's network (docs/DOCKER.md, own address)."
  if [ -z "$ip" ]; then
    ip=$(printf '%s\n' "$suggested" | sed -n 's/^HOUSEOS_LAN_IP=//p')
    if [ -t 0 ]; then read -r -p "Address for HouseOS (free, outside your router's automatic range) [$ip]: " answer; ip=${answer:-$ip}; fi
  fi
  [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || fail "Give an address such as 192.168.1.250."
  while IFS='=' read -r key value; do
    [ "$key" = HOUSEOS_LAN_IP ] || set_env "$key" "$value"
  done <<< "$suggested"
  set_env HOUSEOS_LAN_IP "$ip"
  use compose.lan.yml on
  if ! compose up -d --remove-orphans; then
    use compose.lan.yml off   # never leave the house stuck on a setting that does not start
    compose up -d --remove-orphans
    fail "The own address did not start, so HouseOS went back to this computer's address."
  fi
  result address "$ip"
  port=$(https_port)
  say "HouseOS now has its own address: https://$ip:$port (and https://houseos.local:$port)."
}

cmd_buttons() {
  case "${1:-}" in on | off) use compose.helper.yml "$1" ;; *) fail "Use: ./houseos.sh buttons on|off" ;; esac
  compose up -d --build --remove-orphans
  say "Control Room buttons are $1."
}

cmd_check() { # what Control Room shows next to the buttons
  if [ -d .git ]; then
    result version "$(git describe --always --tags 2>/dev/null || echo "")"
    result current "$(house_version)"
    if timeout 60 git fetch --quiet 2>/dev/null; then
      result behind "$(git rev-list --count 'HEAD..@{upstream}' 2>/dev/null || echo "")"
      result latest "$(git show '@{upstream}:backend/houseos/__init__.py' 2>/dev/null \
        | sed -n 's/^__version__ = "\(.*\)".*/\1/p')"
    fi
  else
    result version zip
  fi
  result gpu_available "$(gpu_available && echo yes || echo no)"
  result gpu "$(has compose.gpu.yml && echo on || echo off)"
  result own_address "$(has compose.lan.yml && grep -s '^HOUSEOS_LAN_IP=' .env | cut -d= -f2 || true)"
}

cmd_setup_code() { compose exec -T api houseos-entrypoint setup-code; }

# A change Nox drafted and an admin applied in Control Room → Changes (docs/CHANGING-HOUSEOS.md);
# the helper runs it, since the change is in the state volume. First a backup (the tag
# houseos-backup/ID, the images re-tagged :backup-ID); a failed check or a HouseOS that doesn't
# come back returns to it. Keep deletes the backup, undo returns to it.
own_images() { compose config --images | grep '^houseos' | sort -u; }
# What Nox may change: backend/houseos/code_rules.py in bash, without frontend/ and themes/ (they
# come prebuilt here); tests/test_code_changes.py keeps the two equal. Case-insensitive, like it.
nox_may_change() { local LC_ALL=C; local s='[a-z0-9_-][a-z0-9_.-]*' p="${1,,}"; local re="^(backend/houseos/($s/)*$s\.py|backend/tests/($s/)*$s\.(py|json)|docs/$s\.md)$"; [[ "$p" =~ $re && ! "$p" =~ (^|/)conftest\.py$ && ! "$p" =~ ^backend/houseos/(code_rules|__init__)\.py$ ]]; }
# No film on a screen (house_actions.house_busy, asked in the running app), or no answer: wait.
no_film() { compose exec -T api python -c 'import sys
from houseos.db import SessionLocal
from houseos.house_actions import house_busy
with SessionLocal() as db: sys.exit(house_busy(db, music=False))' >/dev/null 2>&1; }
sha() { sha256sum | cut -c1-64; }
code_digest() { # CHANGE PATH…: code_rules.digest, the diff the admin approved
  local path
  for path in "${@:2}"; do
    printf '%s %s %s\n' "$path" "$(jq -j --arg p "$path" '.before[$p] // ""' "$1" | sha)" "$(jq -j --arg p "$path" '.files[$p]' "$1" | sha)"
  done | sha
}
code_restore() { # back to the backup of change $1, which then goes
  local image
  git reset --quiet --keep "houseos-backup/$1"
  for image in $(own_images); do
    docker tag "${image%:*}:backup-$1" "$image" 2>/dev/null && docker rmi "${image%:*}:backup-$1" >/dev/null
  done
  git tag -d "houseos-backup/$1" >/dev/null
}
code_write() { # CHANGE PATH…: the drafted files, committed as "Nox: <summary>"
  local change="$1" path
  for path in "${@:2}"; do
    # shellcheck disable=SC2094  # $path is the key read from $change and the file written
    mkdir -p "$(dirname "$path")" && jq -j --arg p "$path" '.files[$p]' "$change" > "$path" || return 1
  done
  git add -- "${@:2}" \
    && git -c user.name=Nox -c user.email=nox@example.invalid commit --quiet -m "Nox: $(jq -r '.summary // ""' "$change")"
}
cmd_code() {
  local action="${1:-}" id="${2:-}" reviewed="${3:-}" change tag image path paths=()
  [[ "$id" =~ ^[0-9a-f]{12}$ ]] || fail "Use: ./houseos.sh code apply ID DIGEST | undo ID | keep ID (Control Room → Changes)"
  change="/state/run/code/$id.json" tag="houseos-backup/$id"
  need_docker
  [ -d .git ] || fail "This copy did not come from git, so it cannot take changes."
  case "$action" in
    apply)
      [ -r "$change" ] || fail "This change is not here: apply it from Control Room → Changes."
      # Read once: everything below checks and writes this copy (it goes with the task's container).
      path=$(mktemp) && cp -- "$change" "$path" && change="$path" || fail "This change could not be read."
      [ -z "$(git status --porcelain --untracked-files=no)" ] \
        || fail "Files in this folder were edited, so the change was not applied. See them with: git status"
      [ "$(git rev-parse HEAD)" = "$(jq -r .base "$change")" ] \
        || fail "HouseOS changed since this was drafted: ask Nox to draft it again."
      mapfile -t paths < <(jq -r '.files | keys[]' "$change")
      for path in "${paths[@]}"; do   # the app checked them; checked again here, not through a link
        nox_may_change "$path" && [ "$(realpath -m -- "$path")" = "$PWD/$path" ] \
          || fail "Refused a file Nox may not change: $path"
      done
      [ "$(code_digest "$change" "${paths[@]}")" = "$reviewed" ] \
        || fail "This change was edited after it was reviewed: look at it again in Control Room → Changes."
      for path in "${paths[@]}"; do
        [ "$({ cat -- "$path" 2>/dev/null || true; } | sha)" = "$(jq -j --arg p "$path" '.before[$p] // ""' "$change" | sha)" ] \
          || fail "A file is not as the reviewed diff showed it: ask Nox to draft it again."
      done
      [ -z "$(git ls-files --others -- "${paths[@]}")" ] \
        || fail "A new file would replace one that isn't part of HouseOS: ask Nox to draft it again."
      git tag "$tag"
      for image in $(own_images); do docker tag "$image" "${image%:*}:backup-$id"; done
      if ! code_write "$change" "${paths[@]}"; then
        git reset --quiet --hard "$tag"   # clean a moment ago: only this change's files
        code_restore "$id"
        fail "The change could not be written, so nothing changed."
      fi
      result commit "$(git rev-parse --short HEAD)"
      say "Checking the change: HouseOS is built with it (a few minutes)…"
      if ! compose build || ! compose run --rm --no-deps -T --entrypoint python api -c \
        'import houseos.main, houseos.worker, houseos.maintenance, houseos.cinema_worker, houseos.relay'; then
        code_restore "$id"
        fail "The change did not pass its checks, so nothing changed (the lines above say why)."
      fi
      if ! no_film; then   # the build takes minutes: a film may have started since the app looked
        code_restore "$id"
        fail "A film is playing, so nothing changed: apply it again when it's over."
      fi
      compose exec -T -u 0 api touch /state/run/resume-music >/dev/null 2>&1 || true
      compose up -d --build --remove-orphans
      if ! (wait_ready); then
        code_restore "$id"
        compose up -d --build --remove-orphans
        fail "HouseOS did not come back with the change, so it went back to how it was."
      fi
      say "Changed and running. Keep it or undo it in Control Room → Changes." ;;
    undo)
      git rev-parse -q --verify "refs/tags/$tag" >/dev/null || fail "This change has no backup."
      [ "$(git rev-parse HEAD^)" = "$(git rev-parse "$tag^{commit}")" ] \
        || fail "Something changed after this change: undo it by hand (git revert)."
      no_film || fail "A film is playing, so nothing changed: undo it again when it's over."
      code_restore "$id"
      compose exec -T -u 0 api touch /state/run/resume-music >/dev/null 2>&1 || true
      compose up -d --build --remove-orphans
      wait_ready
      say "Back to how it was before the change." ;;
    keep)
      git rev-parse -q --verify "refs/tags/$tag" >/dev/null || fail "This change has no backup."
      git tag -d "$tag" >/dev/null
      for image in $(own_images); do docker rmi "${image%:*}:backup-$id" >/dev/null 2>&1 || true; done
      say "Kept; its backup is deleted." ;;
    *) fail "Use: ./houseos.sh code apply ID DIGEST | undo ID | keep ID (Control Room → Changes)" ;;
  esac
}

# ---------------------------------------------------------------------------------------
# The helper (compose.helper.yml). It holds the Docker socket, so it trusts nothing but
# notes signed with the house's key, and runs nothing but the actions above. Each action
# runs in its own container outside the stack, so an update can rebuild HouseOS (the
# helper included) without cutting itself off. Results go to /state/run/helper-out.
cmd_helper() {
  local inbox=/state/run/helper-in out=/state/run/helper-out self image workdir project owner key state
  mkdir -p "$out" && chmod 0755 "$out"
  self=$(hostname)
  image=$(docker inspect "$self" --format '{{.Config.Image}}')
  workdir=$(docker inspect "$self" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')
  project=$(docker inspect "$self" --format '{{index .Config.Labels "com.docker.compose.project"}}')
  owner=$(docker run --rm -v "$workdir:/w:ro" --entrypoint stat "$image" -c '%u:%g' /w)
  # Tasks read the state volume (a change to apply), as the app's group (61990, docker/Dockerfile).
  state=$(docker inspect "$self" --format '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}')
  until grep -qs '^HOUSEOS_ENCRYPTION_KEY=' /state/keys.env; do sleep 2; done   # the app makes it on its first start
  key=$(printf 'houseos-helper:%s' "$(sed -n 's/^HOUSEOS_ENCRYPTION_KEY=//p' /state/keys.env)" | sha256sum | cut -d' ' -f1)
  task() { # task ID ACTION ARGS…: one detached run of this script, as the folder's owner
    docker run -d --name "houseos-task-$1" --label "houseos.task=$1" --label "houseos.action=$2" \
      --user "$owner" --group-add "$(stat -c %g /var/run/docker.sock)" -e HOME=/tmp -e HOUSEOS_PROJECT="$project" \
      -v /var/run/docker.sock:/var/run/docker.sock -v /etc/localtime:/etc/localtime:ro \
      -v "$workdir:$workdir" -w "$workdir" -v "$state:/state:ro" --group-add 61990 \
      --entrypoint bash "$image" "$workdir/houseos.sh" "${@:3}" >/dev/null
  }
  say "HouseOS helper: watching Control Room for $workdir"
  while true; do
    date +%s > "$out/alive"
    collect "$out"
    if [ -z "$(find "$out" -name check.json -mmin -360)" ] && ! docker inspect houseos-task-check >/dev/null 2>&1; then
      task check check check || true
    fi
    for note in "$inbox"/*.json; do
      [ -e "$note" ] || continue
      local body sig id action arg ts args=()
      body=$(jq -r '.body // ""' "$note" 2>/dev/null || true)
      sig=$(jq -r '.sig // ""' "$note" 2>/dev/null || true)
      rm -f "$note"
      [ "$(printf '%s' "$body" | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$key" -r | cut -d' ' -f1)" = "$sig" ] || continue
      id=$(jq -r .id <<< "$body"); action=$(jq -r .action <<< "$body")
      arg=$(jq -r '.arg // ""' <<< "$body"); ts=$(jq -r '.ts // 0' <<< "$body")
      [[ "$id" =~ ^[0-9a-f-]{36}$ && "$ts" =~ ^[0-9]+$ ]] && ts=$(($(date +%s) - ts)) && [ "${ts#-}" -lt 300 ] || continue
      if [ "$action" = check ]; then rm -f "$out/check.json"; continue; fi   # look again now
      case "$action" in
        update) args=("$action") ;;
        backup) [[ "$arg" =~ ^[0-9]{0,2}$ ]] && args=(backup "${arg:-0}") ;;
        gpu-on) args=(gpu on) ;;
        gpu-off) args=(gpu off) ;;
        own-address) [[ "$arg" =~ ^(off|[0-9.]{7,15})$ ]] && args=(own-address "$arg") ;;
        code-apply) [[ "$arg" =~ ^([0-9a-f]{12}):([0-9a-f]{64})$ ]] && args=(code apply "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}") ;;
        code-undo | code-keep) [[ "$arg" =~ ^[0-9a-f]{12}$ ]] && args=(code "${action#code-}" "$arg") ;;
      esac
      if [ "${#args[@]}" -gt 0 ] && task "$id" "$action" "${args[@]}"; then
        jq -n --arg id "$id" --arg action "$action" '{id: $id, action: $action, state: "running"}' > "$out/$id.json"
      else
        jq -n --arg id "$id" --arg action "$action" '{id: $id, action: $action, state: "failed", message: "Could not start"}' > "$out/$id.json"
      fi
    done
    sleep 2
  done
}
collect() { # finished runs → their result and the end of their log
  local out="$1" container id action code log
  for container in $(docker ps -aq --filter label=houseos.task --filter status=exited); do
    id=$(docker inspect "$container" --format '{{index .Config.Labels "houseos.task"}}')
    action=$(docker inspect "$container" --format '{{index .Config.Labels "houseos.action"}}')
    code=$(docker inspect "$container" --format '{{.State.ExitCode}}')
    log=$(docker logs "$container" 2>&1 | tail -n 60)
    docker rm "$container" >/dev/null
    grep -v '^RESULT ' <<< "$log" > "$out/$id.log" || true
    { grep '^RESULT ' <<< "$log" || true; } | sed 's/^RESULT //' \
      | jq -R 'capture("^(?<k>[^=]+)=(?<v>.*)$") | {(.k): .v}' \
      | jq -s --arg id "$id" --arg action "$action" --argjson code "$code" \
        --arg message "$(grep -v '^RESULT ' <<< "$log" | tail -n 1)" \
        '{id: $id, action: $action, state: (if $code == 0 then "done" else "failed" end), message: $message, results: (add // {})}' \
      > "$out/$id.json"
    case "$action" in update | gpu-*) rm -f "$out/check.json" ;; esac   # look again
  done
  find "$out" \( -name '*-*.json' -o -name '*-*.log' \) -mtime +30 -delete 2>/dev/null || true
}

menu() {
  PS3="Choose a number: "
  select _ in "Update HouseOS" "Back up now" "Show the setup code" "Status" "Voice on the graphics card (NVIDIA)" \
    "Voice on the processor" "Own address on the network (optional)" "Control Room buttons on" "Quit"; do
    case "$REPLY" in
      1) cmd_update ;; 2) cmd_backup ;; 3) cmd_setup_code ;; 4) compose ps ;; 5) cmd_gpu on ;;
      6) cmd_gpu off ;; 7) cmd_own_address ;; 8) cmd_buttons on ;;
    esac
    break
  done
}

case "${1:-}" in
  install) cmd_install ;;
  update) cmd_update ;;
  backup) cmd_backup "${2:-0}" ;;
  gpu) cmd_gpu "${2:-}" ;;
  torrents) cmd_torrents "${2:-}" ;;
  own-address) cmd_own_address "${2:-}" ;;
  buttons) cmd_buttons "${2:-}" ;;
  check) cmd_check ;;
  setup-code) cmd_setup_code ;;
  status) compose ps ;;
  logs) compose logs --tail 100 -f "${@:2}" ;;
  helper) cmd_helper ;;
  "") if grep -qs '^HOUSEOS_DB_PASSWORD=' .env; then menu; else cmd_install; fi ;;
  code) cmd_code "${2:-}" "${3:-}" "${4:-}" ;;
  *) sed -n '2,11p' "$0"; exit 1 ;;
esac
