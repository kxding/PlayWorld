#!/usr/bin/env bash
set -euo pipefail

CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
CDP_PORT="${CDP_PORT:-9222}"
PLAYWORLD_PROFILE_DIR="${PLAYWORLD_PROFILE_DIR:-/tmp/playworld-chrome-profile}"

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "Chrome executable not found: $CHROME_BIN" >&2
  exit 1
fi

exec "$CHROME_BIN" \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$PLAYWORLD_PROFILE_DIR"
