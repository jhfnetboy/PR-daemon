#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

ENV_FILE="${PR_DAEMON_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

exec codex -a never \
  --sandbox workspace-write \
  -c 'sandbox_workspace_write.network_access=true' \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium \
  "$@"
