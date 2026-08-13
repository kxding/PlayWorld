#!/usr/bin/env bash
# Copy to Agent_player/api_keys.sh and keep the real file untracked.
export KIGRESS_BASE_URL="https://gateway.example.com/v1"
export KIGRESS_API_KEY="xxx"
export KIGRESS_USER_KEY="xxx"
export KIGRESS_MODEL="claude-haiku-4-5-20251001"
export KIGRESS_BIZ_SCENE="offline"
export KIGRESS_TRUST_ENV="0"

# Optional Gemini agent controller.
export GEMINI_API_KEY="xxx"
export GEMINI_MODEL="gemini-3.1-pro-preview"
