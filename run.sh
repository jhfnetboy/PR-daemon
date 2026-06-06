#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PR_DAEMON_ROOT="$ROOT"
# shellcheck disable=SC1091
. "$ROOT/scripts/load_pr_daemon_env.sh"

exec codex -a never \
  --sandbox workspace-write \
  -c 'sandbox_workspace_write.network_access=true' \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium \
  "$@"
