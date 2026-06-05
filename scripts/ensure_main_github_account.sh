#!/usr/bin/env bash
# Restore the default GitHub CLI account used for discovery/fetching.

set -euo pipefail

MAIN_USER="${PR_DAEMON_MAIN_USER:-jhfnetboy}"
HOST="${PR_DAEMON_GH_HOST:-github.com}"

get_active_user() {
  for _ in 1 2 3; do
    gh api user -q .login 2>/dev/null && return 0
    sleep 1
  done
  return 1
}

ACTIVE_USER="$(get_active_user || true)"
if [ "$ACTIVE_USER" != "$MAIN_USER" ]; then
  gh auth switch --hostname "$HOST" --user "$MAIN_USER" >/dev/null
  ACTIVE_USER="$(get_active_user)"
fi

if [ "$ACTIVE_USER" != "$MAIN_USER" ]; then
  echo "Failed to restore main GitHub account. Active=$ACTIVE_USER expected=$MAIN_USER" >&2
  exit 1
fi

echo "Active GitHub account: $ACTIVE_USER"
