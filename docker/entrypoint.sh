#!/bin/sh
# Prepares /state once (keys, folders, permissions), then runs one HouseOS role as its own
# user. Roles: api, worker, maintenance, fetch, audio, relay, cinema-worker, cinema-observer,
# voice, codex-bridge, claude-bridge; `setup-code` prints the one-time setup code and
# `lan-suggest` the .env lines for compose.lan.yml.
set -eu
role="${1:-api}"
umask 0007

mkdir -p /state/run /state/audio /state/cinema /state/transcode /state/models /state/themes /data/houseos
chgrp houseos /state /state/run /state/audio /state/cinema /state/transcode /state/models /state/themes /data /data/houseos
chmod 2770 /state/run /state/audio /state/cinema /state/transcode /state/models /state/themes /data/houseos
chmod 0750 /state /data

# Private keys, made on first start and kept in the state volume (never in the image or git):
# the key that encrypts saved passwords/keys, the setup code, and the push-notification keys.
python - <<'PY'
import base64, os, secrets
path = "/state/keys.env"
known = open(path).read() if os.path.exists(path) else ""
lines = []
if "HOUSEOS_ENCRYPTION_KEY=" not in known:
    lines += ["HOUSEOS_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
              "HOUSEOS_BOOTSTRAP_TOKEN=" + secrets.token_urlsafe(24)]
if "HOUSEOS_VAPID_PRIVATE_KEY=" not in known:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    key = ec.generate_private_key(ec.SECP256R1())
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    lines += ["HOUSEOS_VAPID_PRIVATE_KEY=" + b64(key.private_numbers().private_value.to_bytes(32, "big")),
              "HOUSEOS_VAPID_PUBLIC_KEY=" + b64(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
              "HOUSEOS_VAPID_SUBJECT=mailto:houseos@localhost"]
if lines:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write("\n".join(lines) + "\n")
PY
set -a
. /state/keys.env
set +a
# Only database-backed services are given database settings.
if [ -n "${HOUSEOS_DB_USER:-}" ]; then
  export HOUSEOS_DATABASE_URL="mysql+pymysql://${HOUSEOS_DB_USER}:${HOUSEOS_DB_PASSWORD}@${HOUSEOS_DB_HOST:-db}:${HOUSEOS_DB_PORT:-3306}/${HOUSEOS_DB_NAME}"
fi
private() { unset HOUSEOS_DATABASE_URL HOUSEOS_DB_PASSWORD HOUSEOS_ENCRYPTION_KEY HOUSEOS_BOOTSTRAP_TOKEN HOUSEOS_VAPID_PRIVATE_KEY; }

# Service accounts live in the state volume, never in /root.
export HOME=/state/run XDG_CACHE_HOME=/state/run/.cache HF_HOME=/state/models/hf

run_as() { user="$1"; shift; exec setpriv --reuid="$user" --regid=houseos --clear-groups --inh-caps=-all "$@"; }
wait_db() {
  python - <<'PY'
import os, time
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["HOUSEOS_DATABASE_URL"])
for attempt in range(60):
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("The database did not answer in 2 minutes.")
PY
}

wait_schema() {
  # The api service applies migrations; everyone else starts once the schema is current.
  wait_db
  python - <<'PY'
import os, time
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
head = ScriptDirectory.from_config(Config("/opt/houseos/backend/alembic.ini")).get_current_head()
engine = create_engine(os.environ["HOUSEOS_DATABASE_URL"])
for attempt in range(150):
    try:
        with engine.connect() as c:
            if c.execute(text("SELECT version_num FROM alembic_version")).scalar() == head:
                break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit("The database schema is not ready; check the api service logs.")
PY
}

cli_update() {
  # New models need recent sign-in clients: install the latest beside the image's pinned copy,
  # swap it in whole, and keep the current one when offline or when npm fails.
  case "$1" in claude) pkg=@anthropic-ai/claude-code ;; *) pkg=@openai/codex ;; esac
  dir="/state/tools/$1"
  if HOME=/root timeout 600 npm install -g --prefix "$dir.new" --no-fund --no-audit "$pkg@latest" >/dev/null 2>&1; then
    rm -rf "$dir.old"; [ -e "$dir" ] && mv "$dir" "$dir.old"; mv "$dir.new" "$dir"; rm -rf "$dir.old"
  else
    rm -rf "$dir.new"; echo "houseos: could not update $pkg; keeping the current one" >&2
  fi
}

bridge() {
  # An AI sign-in client: its own user and profile folder; it never sees the database or keys.
  private
  user="houseos-$1"; profile="/state/$1"
  mkdir -p "$profile" && chown "$user":houseos "$profile" && chmod 0700 "$profile"
  export HOME="$profile"
  # The bridge runs this launcher: the updated client once there is one, else the image's.
  mkdir -p /state/tools && chmod 0755 /state/tools
  printf '#!/bin/sh\n[ -x /state/tools/%s/bin/%s ] && exec /state/tools/%s/bin/%s "$@"\nexec /usr/local/bin/%s "$@"\n' \
    "$1" "$1" "$1" "$1" "$1" > "/state/tools/$1-run" && chmod 0755 "/state/tools/$1-run"
  export "HOUSEOS_$(echo "$1" | tr a-z A-Z)_BIN=/state/tools/$1-run"
  # At start, then daily, or within a minute of an admin's "Update now" (Control Room → AI).
  (
    cli_update "$1"; last=$(date +%s)
    while sleep 60; do
      if [ -e "/state/run/bridge-update-$1" ] || [ $(( $(date +%s) - last )) -ge 86400 ]; then
        rm -f "/state/run/bridge-update-$1"; cli_update "$1"; last=$(date +%s)
      fi
    done
  ) &
  run_as "$user" python -m "houseos.$1_bridge"
}

case "$role" in
  api)
    wait_db
    (cd /opt/houseos/backend && setpriv --reuid=houseos --regid=houseos --clear-groups python -m alembic upgrade head)
    # Trust X-Forwarded-* only from this machine and Docker's own networks (the built-in
    # HTTPS proxy, or yours on the same host). Set HOUSEOS_FORWARDED_ALLOW_IPS for another one.
    run_as houseos python -m uvicorn houseos.main:app --host 0.0.0.0 --port 8990 --no-access-log \
      --proxy-headers --forwarded-allow-ips "${HOUSEOS_FORWARDED_ALLOW_IPS:-127.0.0.1,172.16.0.0/12}" ;;
  worker)          wait_schema; run_as houseos python -m houseos.worker ;;
  maintenance)     wait_schema; run_as houseos python -m houseos.maintenance ;;
  cinema-worker)   wait_schema; run_as houseos python -m houseos.cinema_worker ;;
  cinema-observer) wait_schema; run_as houseos python -m houseos.cinema_observer ;;
  relay)
    wait_schema
    unset HOUSEOS_BOOTSTRAP_TOKEN
    run_as houseos python -m uvicorn houseos.relay:app --host "${HOUSEOS_RELAY_BIND:-0.0.0.0}" --port 8991 \
      --no-access-log --log-level warning ;;
  fetch)
    # The fetcher never gets the database or the keys: it only resolves and downloads.
    private
    run_as houseos-fetch python -m houseos.fetcher ;;
  audio)
    # Plays through this computer's normal speakers: the desktop's PipeWire/PulseAudio when a
    # user is logged in (run as that user, who owns the socket), else the sound card directly,
    # else silently as the house clock for phones and Cast speakers (Listen says so).
    private
    sock=$(ls /run/host-user/*/pulse/native 2>/dev/null | head -n 1 || true)
    # Windows (WSL 2): WSLg's sound server plays on the PC's own speakers (compose.wsl.yml).
    if [ -S /run/wslg/PulseServer ]; then
      export PULSE_SERVER="unix:/run/wslg/PulseServer"
      run_as houseos python -m houseos.audio
    fi
    if [ -n "$sock" ] && [ -S "$sock" ]; then
      export PULSE_SERVER="unix:$sock"
      run_as "$(stat -c %u "$sock")" python -m houseos.audio
    fi
    if [ -e /dev/snd/controlC0 ]; then
      exec setpriv --reuid=houseos --regid=houseos --groups "$(stat -c %g /dev/snd/controlC0 2>/dev/null || echo 29)" \
        --inh-caps=-all python -m houseos.audio
    fi
    run_as houseos python -m houseos.audio ;;
  voice)
    # The speech model downloads in the background on first start (Services shows it).
    private
    run_as houseos python -m houseos.voice ;;
  codex-bridge)  bridge codex ;;
  claude-bridge) bridge claude ;;
  setup-code)
    echo "Your one-time setup code: ${HOUSEOS_BOOTSTRAP_TOKEN}" ;;
  lan-suggest)
    # The .env lines for compose.lan.yml, read from this computer's network: run it on a
    # host-network service, `docker compose run --rm --no-deps relay lan-suggest`.
    private
    exec python -c "from houseos.discovery import suggest_lan; suggest_lan()" ;;
  *) exec "$@" ;;
esac
