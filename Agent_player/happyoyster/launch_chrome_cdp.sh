#!/usr/bin/env bash
set -euo pipefail

PORT="${HAPPYOYSTER_CDP_PORT:-9222}"
PROFILE_DIR="${HAPPYOYSTER_CHROME_PROFILE:-$HOME/.happyoyster_chrome_dev_profile}"
URL="${HAPPYOYSTER_CREATE_URL:-https://www.happyoyster.cn/create}"

if [[ -x "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev" ]]; then
  APP="/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev"
elif [[ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
  APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
else
  echo "Google Chrome or Google Chrome Dev was not found under /Applications." >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"

"$APP" \
  --user-data-dir="$PROFILE_DIR" \
  --remote-debugging-port="$PORT" \
  --no-first-run \
  --no-default-browser-check \
  --no-sandbox \
  --disable-blink-features=AutomationControlled \
  "$URL" &

echo "Chrome launched with CDP: http://127.0.0.1:${PORT}"
echo "Profile: ${PROFILE_DIR}"
