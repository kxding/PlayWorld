#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Editable VQA configuration. Keep real keys out of git.
# You can also set the matching uppercase environment variables instead.
# -----------------------------------------------------------------------------
api_key="${GEMINI_API_KEY:-xxx}"
model="${GEMINI_MODEL:-gemini-3.1-pro-preview}"
mode="${MODE:-score}"                         # score or gate
dataset="${DATASET:-/absolute/path/to/data.json}"
task_id="${TASK_ID:-GC001}"
video="${VIDEO:-/absolute/path/to/recording.mp4}"
reference_image="${REFERENCE_IMAGE:-}"       # optional; score mode only
world_model="${WORLD_MODEL:-unknown}"
output="${OUTPUT:-outputs/${task_id}_${mode}.json}"
context_output="${CONTEXT_OUTPUT:-outputs/${task_id}_${mode}_context.json}"

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

export GEMINI_API_KEY="$api_key"
export GEMINI_MODEL="$model"

# Advanced use: explicitly supplied CLI flags are forwarded unchanged.
# Example: ./run_vqa_score.sh --help
if (( $# > 0 )); then
  needs_api_key=1
  for argument in "$@"; do
    if [[ "$argument" == "--dry-run" || "$argument" == "--help" || "$argument" == "-h" ]]; then
      needs_api_key=0
    fi
  done
  if (( needs_api_key == 1 )) && [[ "$api_key" == "xxx" ]]; then
    echo "Replace api_key=\"xxx\" in run_vqa_score.sh or set GEMINI_API_KEY." >&2
    exit 2
  fi
  exec python3 -m metrics.vqa.score "$@"
fi

if [[ "$dataset" == /absolute/path/* || "$video" == /absolute/path/* ]]; then
  echo "Edit dataset/video in run_vqa_score.sh or set DATASET and VIDEO." >&2
  exit 2
fi
if [[ "${DRY_RUN:-0}" != "1" && "$api_key" == "xxx" ]]; then
  echo "Replace api_key=\"xxx\" in run_vqa_score.sh or set GEMINI_API_KEY." >&2
  exit 2
fi

args=(
  --mode "$mode"
  --dataset "$dataset"
  --task-id "$task_id"
  --video "$video"
  --world-model "$world_model"
  --model "$model"
  --context-output "$context_output"
  --output "$output"
)

if [[ -n "$reference_image" && "$mode" == "score" ]]; then
  args+=(--reference-image "$reference_image")
fi
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

python3 -m metrics.vqa.score "${args[@]}"
