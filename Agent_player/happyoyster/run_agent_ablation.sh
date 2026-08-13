#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORLDPLAY_DIR="${HAPPYOYSTER_DATA_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
PROJECT_ROOT="$(cd "${WORLDPLAY_DIR}/.." && pwd)"

MODE="${1:-}"
TASK_IDS_VALUE="${2:-${TASK_IDS:-}}"
AGENT_LABEL="${3:-haiku}"
if [[ "$MODE" != "preset_only" && "$MODE" != "agent_only" && "$MODE" != "preset_agent" ]]; then
  echo "Usage: ./run_agent_ablation.sh preset_only|agent_only|preset_agent TASK_IDS [haiku|sonnet|gemini31pro]" >&2
  exit 2
fi
if [[ -z "$TASK_IDS_VALUE" ]]; then
  echo "TASK_IDS is required" >&2
  exit 2
fi

case "$AGENT_LABEL" in
  haiku)
    export AGENT_PROVIDER=claude
    if [[ "${AGENT_TRANSPORT:-openai}" == "anthropic" ]]; then
      export AGENT_MODEL="${AGENT_MODEL:-${WQ_MODEL:-ep-hizen2-1786024970943139465}}"
    else
      export AGENT_MODEL="${AGENT_MODEL:-claude-haiku-4-5-20251001}"
    fi
    ;;
  sonnet)
    export AGENT_PROVIDER=claude
    export AGENT_TRANSPORT="${AGENT_TRANSPORT:-anthropic}"
    if [[ "$AGENT_TRANSPORT" == "anthropic" ]]; then
      export AGENT_MODEL="${AGENT_MODEL:-${WQ_MODEL:-ep-hizen2-1786024970943139465}}"
    else
      export AGENT_MODEL="${AGENT_MODEL:-claude-sonnet-4-5}"
    fi
    ;;
  gemini31pro)
    export AGENT_PROVIDER=gemini
    export AGENT_TRANSPORT="${AGENT_TRANSPORT:-gemini_generate_content}"
    export AGENT_MODEL="${AGENT_MODEL:-gemini-3.1-pro-preview}"
    ;;
  *) echo "Unknown agent label: $AGENT_LABEL" >&2; exit 2 ;;
esac

KEY_FILE="${AGENT_PLAYER_KEYS_FILE:-${SCRIPT_DIR}/../api_keys.sh}"
if [[ "$MODE" != "preset_only" && -f "$KEY_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$KEY_FILE"
fi

if [[ "$MODE" == "preset_only" ]]; then
  CONDITION="preset_only"
else
  CONDITION="${MODE}_${AGENT_LABEL}"
fi

OUT_ROOT="${PROJECT_ROOT}/final-result/agentablation/happyoyster"
LOG_DIR="${OUT_ROOT}/_logs"
mkdir -p "$LOG_DIR"

export AGENT_ABLATION_MODE="$MODE"
export HAPPYOYSTER_CDP_URL="${HAPPYOYSTER_CDP_URL:-http://127.0.0.1:9225}"
export HAPPYOYSTER_CREATE_URL="${HAPPYOYSTER_CREATE_URL:-https://www.happyoyster.com/create}"
export HAPPYOYSTER_HOST_FRAGMENT="${HAPPYOYSTER_HOST_FRAGMENT:-happyoyster.com}"
export HAPPYOYSTER_RUN_ID="$CONDITION"
export HAPPYOYSTER_CONDITION_VIDEO_NAME="${CONDITION}.mp4"
export HAPPYOYSTER_DATA_ROOT="$WORLDPLAY_DIR"
export HAPPYOYSTER_OUT_ROOT="$OUT_ROOT"
export HAPPYOYSTER_DATA_FILES="${HAPPYOYSTER_DATA_FILES:-GC:GC.json,IF:IF.json,OE:OE.json}"
export TASK_IDS="$TASK_IDS_VALUE"
export SPLIT_BY_PERSPECTIVE=0
export SKIP_EXISTING_SUCCESS="${SKIP_EXISTING_SUCCESS:-1}"
export CREATE_WAIT_TIMEOUT_S="${CREATE_WAIT_TIMEOUT_S:-600}"
export CREATE_ATTEMPTS="${CREATE_ATTEMPTS:-4}"
export DOWNLOAD_ATTEMPTS="${DOWNLOAD_ATTEMPTS:-3}"
export DOWNLOAD_MODAL_WAIT_S="${DOWNLOAD_MODAL_WAIT_S:-120}"
export DOWNLOAD_FILE_WAIT_S="${DOWNLOAD_FILE_WAIT_S:-90}"

if [[ "$MODE" == "preset_agent" ]]; then
  export HAPPYOYSTER_ADAPTIVE_CORRECTION="${HAPPYOYSTER_ADAPTIVE_CORRECTION:-1}"
  export HAPPYOYSTER_LIVE_HOLD_STOP_CHECK="${HAPPYOYSTER_LIVE_HOLD_STOP_CHECK:-1}"
  export HAPPYOYSTER_LIVE_HOLD_REQUEST_MIN_MS="${HAPPYOYSTER_LIVE_HOLD_REQUEST_MIN_MS:-0}"
  export HAPPYOYSTER_LIVE_HOLD_STOP_MIN_MS="${HAPPYOYSTER_LIVE_HOLD_STOP_MIN_MS:-600}"
  export HAPPYOYSTER_LIVE_HOLD_MIN_REMAINING_MS="${HAPPYOYSTER_LIVE_HOLD_MIN_REMAINING_MS:-0}"
  export HAPPYOYSTER_ADAPTIVE_PHASE_PROGRESS_CHECK="${HAPPYOYSTER_ADAPTIVE_PHASE_PROGRESS_CHECK:-1}"
  export HAPPYOYSTER_ROTATION_LOOP_CHECK="${HAPPYOYSTER_ROTATION_LOOP_CHECK:-1}"
  export HAPPYOYSTER_ROTATION_LOOP_MAX_ACTIONS="${HAPPYOYSTER_ROTATION_LOOP_MAX_ACTIONS:-4}"
  export HAPPYOYSTER_ROTATION_LOOP_MAX_CHECKS="${HAPPYOYSTER_ROTATION_LOOP_MAX_CHECKS:-2}"
  export HAPPYOYSTER_FINAL_ORIENTATION_CHECK="${HAPPYOYSTER_FINAL_ORIENTATION_CHECK:-1}"
  export HAPPYOYSTER_FINAL_ORIENTATION_MAX_ACTIONS="${HAPPYOYSTER_FINAL_ORIENTATION_MAX_ACTIONS:-4}"
  export HAPPYOYSTER_FINAL_ORIENTATION_MAX_CHECKS="${HAPPYOYSTER_FINAL_ORIENTATION_MAX_CHECKS:-2}"
fi

LOG_PATH="${LOG_DIR}/${CONDITION}_$(date +%Y%m%d_%H%M%S).log"
echo "Condition: $CONDITION"
echo "Tasks: $TASK_IDS"
echo "Output: ${OUT_ROOT}/${CONDITION}"
echo "CDP: $HAPPYOYSTER_CDP_URL"
python3 "${SCRIPT_DIR}/../player_happyoyster.py" 2>&1 | tee "$LOG_PATH"
