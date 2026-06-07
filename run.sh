#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PR_DAEMON_ROOT="$ROOT"
# shellcheck disable=SC1091
. "$ROOT/scripts/load_pr_daemon_env.sh"

ROOTS_FILE="$ROOT/config/workspace-roots.txt"
ADD_DIRS=()
if [ -f "$ROOTS_FILE" ]; then
  while IFS= read -r line; do
    line="${line%%#*}"
    line="${line//[[:space:]]/}"
    [ -n "$line" ] && ADD_DIRS+=(--add-dir "$line")
  done < "$ROOTS_FILE"
fi

exec codex -a never \
  --sandbox workspace-write \
  -c 'sandbox_workspace_write.network_access=true' \
  "${ADD_DIRS[@]}" \
  "$@"
