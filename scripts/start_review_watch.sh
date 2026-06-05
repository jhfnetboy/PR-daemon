#!/usr/bin/env bash
# Start the PR-Daemon review watcher loop.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${PR_DAEMON_STATE_DIR:-$HOME/.local/state/pr-daemon}"
mkdir -p "$STATE_DIR"

INTERVAL="${PR_DAEMON_WATCH_INTERVAL:-900}"
MAX_REVIEWS="${PR_DAEMON_MAX_REVIEWS_PER_CYCLE:-1}"
LOG_FILE="${PR_DAEMON_REVIEW_WATCH_LOG:-$STATE_DIR/review-watch.log}"
PID_FILE="${PR_DAEMON_REVIEW_WATCH_PID:-$STATE_DIR/review-watch.pid}"

ARGS=(
  "$ROOT/scripts/review_watch.py"
  --loop
  --interval "$INTERVAL"
  --max-reviews-per-cycle "$MAX_REVIEWS"
  --write-prompts-dir "$ROOT/reviews/watch-prompts"
)

if [ "${PR_DAEMON_AUTO_REVIEW:-0}" = "1" ]; then
  ARGS+=(--auto-review)
fi

if [ "${PR_DAEMON_DRY_RUN:-0}" = "1" ]; then
  ARGS+=(--dry-run)
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "review watcher already running: pid $(cat "$PID_FILE")"
  exit 0
fi

cd "$ROOT"
nohup python3 "${ARGS[@]}" >>"$LOG_FILE" 2>&1 &
echo "$!" >"$PID_FILE"

echo "started review watcher pid $(cat "$PID_FILE")"
echo "log: $LOG_FILE"
echo "auto_review: ${PR_DAEMON_AUTO_REVIEW:-0}"
echo "dry_run: ${PR_DAEMON_DRY_RUN:-0}"
