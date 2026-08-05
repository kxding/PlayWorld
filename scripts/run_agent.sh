#!/usr/bin/env bash
set -euo pipefail

exec python3 -m playworldbench.agent_cli "$@"
