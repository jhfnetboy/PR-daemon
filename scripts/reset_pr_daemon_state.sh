#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PR_DAEMON_ROOT="$ROOT"
# shellcheck disable=SC1091
. "$ROOT/scripts/load_pr_daemon_env.sh"

WIPE_MODEL_EVAL_DB=0
if [ "${1:-}" = "--wipe-model-eval-db" ]; then
  WIPE_MODEL_EVAL_DB=1
fi

STATE_DIR="${PR_DAEMON_STATE_DIR:-$ROOT/.state/pr-daemon}"
WATCH_DB="${PR_DAEMON_REVIEW_WATCH_DB:-$STATE_DIR/pr-watch.sqlite}"
MODEL_EVAL_DB="${PR_DAEMON_MODEL_EVAL_DB:-$ROOT/reviews/model-evals/model-evals.sqlite}"

./scripts/start_review_watch.sh stop >/dev/null || true

rm -f \
  "$STATE_DIR/current-review.json" \
  "$STATE_DIR/watcher-state.json" \
  "$STATE_DIR/review-watch.pid" \
  "$STATE_DIR/review-watch.meta" \
  "$WATCH_DB" \
  "$WATCH_DB-shm" \
  "$WATCH_DB-wal"

if [ "$WIPE_MODEL_EVAL_DB" = "1" ]; then
  rm -f "$MODEL_EVAL_DB" "$MODEL_EVAL_DB-shm" "$MODEL_EVAL_DB-wal"
fi

./scripts/bootstrap_pr_daemon.sh

echo "reset_complete=1"
echo "wiped_model_eval_db=$WIPE_MODEL_EVAL_DB"
