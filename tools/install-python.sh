#!/usr/bin/env bash
# Installs HouseOS's Python dependencies: offline from dependencies/wheelhouse when present,
# otherwise from PyPI with the hash-locked requirements.
# Needs CPython 3.13. If your system has another version: `uv python install 3.13`, then run
#   PYTHON="$(uv python find 3.13)" bash tools/install-python.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3.13}"
if ! command -v "$PYTHON" >/dev/null || ! "$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 13)' 2>/dev/null; then
  echo "CPython 3.13 is required (found: $("$PYTHON" --version 2>&1 || echo none))." >&2
  echo 'Install it, e.g. `uv python install 3.13`, then: PYTHON="$(uv python find 3.13)" bash tools/install-python.sh' >&2
  exit 1
fi
"$PYTHON" -m venv .venv
if [ -d dependencies/wheelhouse ]; then   # the release ZIP: fully offline
  .venv/bin/python -m pip install --no-index --find-links dependencies/wheelhouse -r dependencies/bundled-linux-cp313.txt
else                                      # a git checkout: from PyPI, pinned with hashes
  .venv/bin/python -m pip install --require-hashes -r dependencies/requirements.lock.txt
  .venv/bin/python -m pip install -r dependencies/resolver-requirements.txt
fi
printf '%s\n' 'Python dependencies installed. Read docs/START-HERE.md before configuring your instance.'
