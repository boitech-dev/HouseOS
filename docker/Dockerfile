# HouseOS — one image for every service; docker-compose.yml picks the role.
FROM python:3.13-slim-bookworm AS app

# ffmpeg/ffprobe: audio and film inspection · mpv: the speaker bridge · nodejs/npm: YouTube's
# challenge solver and the ChatGPT/Claude sign-in clients · bubblewrap: sandbox for media
# parsers · pulseaudio-utils: the host's PipeWire/PulseAudio · util-linux: findmnt/setpriv ·
# git: installing your own integrations from their repository (custom_admin.py).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg mpv nodejs npm bubblewrap pulseaudio-utils util-linux ca-certificates tini git \
 && rm -rf /var/lib/apt/lists/* \
 # The media sandbox exposes /usr only: resolve Debian's /etc/alternatives library links.
 && find /usr/lib -lname '/etc/alternatives/*' -exec sh -c 'ln -sfn "$(readlink -f "$1")" "$1"' _ {} \;

# The official ChatGPT (Codex) and Claude (Claude Code) command-line clients, pinned as a
# fallback: each bridge installs the latest into the state volume daily (entrypoint cli_update).
# HouseOS only talks to them through their private bridges; your sign-in stays in the volume.
RUN npm install -g --no-fund --no-audit @openai/codex@0.157.1 @anthropic-ai/claude-code@2.1.283 \
 && npm cache clean --force

# Service identities: the app, the only process that talks to YouTube/SoundCloud/radio, and
# one per AI sign-in client. They share the "houseos" group for the private sockets.
RUN groupadd --system --gid 61990 houseos \
 && useradd --system --uid 61990 --gid houseos --home-dir /state/run --shell /usr/sbin/nologin houseos \
 && useradd --system --uid 61991 --gid houseos --home-dir /state/run --shell /usr/sbin/nologin houseos-fetch \
 && useradd --system --uid 61992 --gid houseos --home-dir /state/codex --shell /usr/sbin/nologin houseos-codex \
 && useradd --system --uid 61993 --gid houseos --home-dir /state/claude --shell /usr/sbin/nologin houseos-claude

WORKDIR /opt/houseos
# Offline from the bundled wheelhouse when it was built for this processor (the release ZIP
# ships x86-64 wheels); otherwise from PyPI, pinned with hashes (a git checkout, or arm64 such
# as a Raspberry Pi: the lock holds every platform's wheel hashes, so the versions match).
COPY dependencies /tmp/dependencies
RUN if ls /tmp/dependencies/wheelhouse/*"$(uname -m)"*.whl >/dev/null 2>&1; then \
      pip install --no-cache-dir --no-index --find-links /tmp/dependencies/wheelhouse \
        -r /tmp/dependencies/bundled-linux-cp313.txt; \
    else \
      pip install --no-cache-dir --require-hashes -r /tmp/dependencies/requirements.lock.txt \
      && pip install --no-cache-dir -r /tmp/dependencies/resolver-requirements.txt; \
    fi \
 && rm -rf /tmp/dependencies

# Speech-to-text for Nox (faster-whisper); its model downloads on first start.
RUN pip install --no-cache-dir faster-whisper==1.2.1

COPY backend /opt/houseos/backend
# The theme kit checks installed themes against Base (themes/base) and the slot list.
COPY themes /opt/houseos/themes
COPY frontend/dist /opt/houseos/frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/houseos-entrypoint
RUN chmod 0755 /usr/local/bin/houseos-entrypoint \
 && python -m compileall -q /opt/houseos/backend/houseos

ENV PYTHONPATH=/opt/houseos/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOUSEOS_RUNTIME_ROOT=/state \
    HOUSEOS_FRONTEND_DIST=/opt/houseos/frontend/dist \
    HOUSEOS_STORAGE_CONTAINER=true \
    HOUSEOS_STORAGE_MOUNT=/data \
    HOUSEOS_DATA_ROOT=/data/houseos \
    HOUSEOS_IMPORT_ROOT=/import \
    HOUSEOS_RESOLVER_BIN=/usr/local/bin/yt-dlp \
    HOUSEOS_CODEX_SOCKET=/state/run/codex.sock \
    HOUSEOS_CLAUDE_SOCKET=/state/run/claude.sock \
    HOUSEOS_CODEX_BIN=/usr/local/bin/codex \
    HOUSEOS_CLAUDE_BIN=/usr/local/bin/claude
WORKDIR /opt/houseos/backend
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/houseos-entrypoint"]
CMD ["api"]

# Voice on an NVIDIA graphics card: the CUDA 12 libraries CTranslate2 needs (compose.gpu.yml).
FROM app AS voice-gpu
RUN pip install --no-cache-dir nvidia-cublas-cu12==12.* nvidia-cudnn-cu12==9.*
ENV HOUSEOS_VOICE_GPU=1 \
    LD_LIBRARY_PATH=/usr/local/lib/python3.13/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.13/site-packages/nvidia/cudnn/lib

# The optional helper behind Control Room's update/backup buttons (compose.helper.yml).
FROM docker:28-cli AS helper
RUN apk add --no-cache bash git jq openssl coreutils
COPY houseos.sh /usr/local/bin/houseos.sh
ENTRYPOINT ["bash", "/usr/local/bin/houseos.sh"]
CMD ["helper"]
