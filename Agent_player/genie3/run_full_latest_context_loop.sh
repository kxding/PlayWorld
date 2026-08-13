#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="${AGENT_PLAYER_KEYS_FILE:-${SCRIPT_DIR}/../api_keys.sh}"
if [[ -f "$KEY_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$KEY_FILE"
fi
ROOT="${WORLDMODELBENCH_ROOT:-$(cd "${SCRIPT_DIR}/../../../.." && pwd)}"
DATA_ROOT="${GENIE3_DATA_ROOT:-${ROOT}/worldplay_0622}"
OUT_ROOT="${GENIE3_OUT_ROOT:-${ROOT}/result-genie3}"
RUN_ID="${GENIE3_RUN_ID:-latest_context_full_20260710_1740}"
if [[ "${RUN_ID}" =~ (20[0-9]{6})_([0-9]{6})([^0-9]|$) ]]; then
  RUN_TIMESTAMP="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}"
elif [[ "${RUN_ID}" =~ (20[0-9]{6})_([0-9]{4})([^0-9]|$) ]]; then
  RUN_TIMESTAMP="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}00"
else
  RUN_TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
fi
LOG_ROOT="${GENIE3_RUN_LOG_ROOT:-${ROOT}/result-genie3-logs}"
RUN_LOG_DIR="${LOG_ROOT}/${RUN_ID}"
PYTHON_BIN="${GENIE3_PYTHON_BIN:-python3}"
TOTAL_TASKS=154
MAX_ROUNDS="${GENIE3_MAX_FULL_ROUNDS:-20}"

mkdir -p "${OUT_ROOT}" "${RUN_LOG_DIR}"

export GENIE3_CDP_URL="${GENIE3_CDP_URL:-http://127.0.0.1:9228}"
export GENIE3_RUN_ID="${RUN_ID}"
export GENIE3_DATA_ROOT="${DATA_ROOT}"
export GENIE3_OUT_ROOT="${OUT_ROOT}"
export GENIE3_RUN_LOG_ROOT="${LOG_ROOT}"
export GENIE3_DATA_FILES="GC:${DATA_ROOT}/GC.json,IF:${DATA_ROOT}/IF.json,OE:${DATA_ROOT}/OE.json"
export GENIE3_ALL_TASKS=1
unset TASK_IDS

export SKIP_EXISTING_SUCCESS=1
export SKIP_EXISTING_TERMINAL_FAILURE=0
export CREATE_WAIT_TIMEOUT_S="${CREATE_WAIT_TIMEOUT_S:-600}"
export POST_ACTION_WAIT_S="${POST_ACTION_WAIT_S:-300}"
export GENIE3_INITIAL_ACTION_DELAY_S="${GENIE3_INITIAL_ACTION_DELAY_S:-1}"
export GENIE3_AUTO_EXIT_AFTER_ACTIONS=0
export GENIE3_WAIT_AND_OBSERVE_S="${GENIE3_WAIT_AND_OBSERVE_S:-60}"
export GENIE3_ADAPTIVE_CORRECTION="${GENIE3_ADAPTIVE_CORRECTION:-1}"
export GENIE3_ADAPTIVE_PRETHINK=0
export GENIE3_ADAPTIVE_PHASE_DONE_CHECK="${GENIE3_ADAPTIVE_PHASE_DONE_CHECK:-1}"
export GENIE3_ADAPTIVE_PHASE_PROGRESS_CHECK="${GENIE3_ADAPTIVE_PHASE_PROGRESS_CHECK:-1}"
export GENIE3_ADAPTIVE_PHASE_CHECK_EVERY="${GENIE3_ADAPTIVE_PHASE_CHECK_EVERY:-3}"
export GENIE3_ADAPTIVE_EXTEND_HOLD="${GENIE3_ADAPTIVE_EXTEND_HOLD:-1}"
export GENIE3_ADAPTIVE_EXTEND_HOLD_MIN_MS="${GENIE3_ADAPTIVE_EXTEND_HOLD_MIN_MS:-2000}"
export GENIE3_LIVE_HOLD_STOP_CHECK="${GENIE3_LIVE_HOLD_STOP_CHECK:-1}"
export GENIE3_LIVE_HOLD_CHECK_INTERVAL_MS="${GENIE3_LIVE_HOLD_CHECK_INTERVAL_MS:-50}"
export GENIE3_LIVE_HOLD_MAX_CHECKS="${GENIE3_LIVE_HOLD_MAX_CHECKS:-20}"
export GENIE3_LIVE_HOLD_MIN_MS="${GENIE3_LIVE_HOLD_MIN_MS:-0}"
export GENIE3_LIVE_HOLD_MIN_APPLY_MS="${GENIE3_LIVE_HOLD_MIN_APPLY_MS:-600}"
export GENIE3_LIVE_HOLD_MIN_REMAINING_MS="${GENIE3_LIVE_HOLD_MIN_REMAINING_MS:-0}"
export GENIE3_ROTATION_LOOP_CHECK="${GENIE3_ROTATION_LOOP_CHECK:-1}"
export GENIE3_FINAL_ORIENTATION_CHECK="${GENIE3_FINAL_ORIENTATION_CHECK:-1}"
export GENIE3_ERROR_RETRIES="${GENIE3_ERROR_RETRIES:-3}"
export DOWNLOAD_EXPECT_TIMEOUT_MS="${DOWNLOAD_EXPECT_TIMEOUT_MS:-25000}"
export DOWNLOAD_JS_FALLBACK_TIMEOUT_MS="${DOWNLOAD_JS_FALLBACK_TIMEOUT_MS:-15000}"
export DOWNLOAD_SETTLE_MS="${DOWNLOAD_SETTLE_MS:-15000}"
export DOWNLOAD_CLICK_RETRIES="${DOWNLOAD_CLICK_RETRIES:-3}"
export PYTHONUNBUFFERED=1

valid_video_count() {
  local count=0
  local directory
  for directory in \
    "${OUT_ROOT}"/GC???_"${RUN_TIMESTAMP}" \
    "${OUT_ROOT}"/IF???_"${RUN_TIMESTAMP}" \
    "${OUT_ROOT}"/OE???_"${RUN_TIMESTAMP}"; do
    [[ -d "${directory}" ]] || continue
    if find "${directory}" -maxdepth 1 -type f -name '*_native.*' -size +1000c | read -r _; then
      count=$((count + 1))
    fi
  done
  echo "${count}"
}

for round in $(seq 1 "${MAX_ROUNDS}"); do
  started_at="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "round=${round} status=running started_at=${started_at}" > "${RUN_LOG_DIR}/loop_status.txt"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/../player_genie3.py" \
    >> "${RUN_LOG_DIR}/runner.log" 2>&1
  runner_exit=$?
  valid_count="$(valid_video_count)"
  finished_at="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "round=${round} status=finished runner_exit=${runner_exit} valid=${valid_count}/${TOTAL_TASKS} finished_at=${finished_at}" \
    > "${RUN_LOG_DIR}/loop_status.txt"
  if [[ "${valid_count}" -ge "${TOTAL_TASKS}" ]]; then
    touch "${RUN_LOG_DIR}/COMPLETE"
    exit 0
  fi
  sleep 30
done

valid_count="$(valid_video_count)"
echo "status=max_rounds_reached valid=${valid_count}/${TOTAL_TASKS}" > "${RUN_LOG_DIR}/loop_status.txt"
exit 1
