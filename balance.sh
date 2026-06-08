#!/usr/bin/env bash
# balance.sh — query provider usage/balance for DeepSeek + Codex + Claude
#
# Usage:
#   ./balance.sh                one-shot, human-readable
#   ./balance.sh --watch        refresh every 30 min (default)
#   ./balance.sh --watch 10     refresh every 10 min
#   ./balance.sh --compact      one-line per provider
#   ./balance.sh --json         raw JSON

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 -u "$ROOT/scripts/provider_balance.py" "$@"
