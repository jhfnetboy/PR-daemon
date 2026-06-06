#!/usr/bin/env bash
# Start the PR-Daemon review watcher loop.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PR_DAEMON_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi
STATE_DIR="${PR_DAEMON_STATE_DIR:-$HOME/.local/state/pr-daemon}"
mkdir -p "$STATE_DIR"

INTERVAL="${PR_DAEMON_WATCH_INTERVAL:-900}"
REFRESH_INTERVAL="${PR_DAEMON_REVIEW_REFRESH_INTERVAL:-3600}"
MAX_REVIEWS="${PR_DAEMON_MAX_REVIEWS_PER_CYCLE:-1}"
LOG_FILE="${PR_DAEMON_REVIEW_WATCH_LOG:-$STATE_DIR/review-watch.log}"
PID_FILE="${PR_DAEMON_REVIEW_WATCH_PID:-$STATE_DIR/review-watch.pid}"
META_FILE="${PR_DAEMON_REVIEW_WATCH_META:-$STATE_DIR/review-watch.meta}"
WATCH_DB="${PR_DAEMON_REVIEW_WATCH_DB:-$STATE_DIR/pr-watch.sqlite}"
ACTION="${1:-start}"
CURRENT_REVIEW_FILE="$STATE_DIR/current-review.json"
WATCHER_STATE_FILE="$STATE_DIR/watcher-state.json"

print_meta() {
  if [ -f "$META_FILE" ]; then
    cat "$META_FILE"
  else
    echo "meta: missing"
  fi
}

print_runtime_state() {
  if [ -f "$CURRENT_REVIEW_FILE" ]; then
    echo "active_review_file=$CURRENT_REVIEW_FILE"
    python3 - "$CURRENT_REVIEW_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
repo = payload.get("repo", "")
pr_number = payload.get("pr_number", "")
head_oid = str(payload.get("head_oid", ""))[:7]
print(f"active_review={repo}#{pr_number} head={head_oid}")
PY
  else
    echo "active_review=none"
  fi

  if [ -f "$WATCHER_STATE_FILE" ]; then
    echo "watcher_state_file=$WATCHER_STATE_FILE"
    python3 - "$WATCHER_STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
for key in ("loop_state", "seen_open_prs", "processed_reviews", "updated_at"):
    if key in payload:
        print(f"{key}={payload[key]}")
PY
  fi
}

stop_watcher() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")"
    rm -f "$PID_FILE" "$META_FILE" 2>/dev/null || true
    echo "stopped review watcher"
  else
    rm -f "$PID_FILE" "$META_FILE" 2>/dev/null || true
    echo "review watcher not running"
  fi
}

case "$ACTION" in
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "review watcher running: pid $(cat "$PID_FILE")"
    elif [ -f "$CURRENT_REVIEW_FILE" ]; then
      echo "review watcher not running (orphaned active review present)"
    else
      echo "review watcher not running"
    fi
    print_meta
    print_runtime_state
    exit 0
    ;;
  stop)
    stop_watcher
    exit 0
    ;;
  restart)
    stop_watcher
    ;;
  start)
    ;;
  *)
    echo "usage: $0 [start|stop|restart|status]" >&2
    exit 2
    ;;
esac

ARGS=(
  "$ROOT/scripts/review_watch.py"
  --loop
  --interval "$INTERVAL"
  --refresh-interval "$REFRESH_INTERVAL"
  --max-reviews-per-cycle "$MAX_REVIEWS"
  --db "$WATCH_DB"
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
  print_meta
  exit 0
fi

cd "$ROOT"
{
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') start_review_watch.sh ===="
  echo "auto_review=${PR_DAEMON_AUTO_REVIEW:-0} dry_run=${PR_DAEMON_DRY_RUN:-0} interval=${INTERVAL} refresh_interval=${REFRESH_INTERVAL} max_reviews=${MAX_REVIEWS} db=${WATCH_DB}"
} >>"$LOG_FILE"
nohup python3 -u "${ARGS[@]}" >>"$LOG_FILE" 2>&1 &
echo "$!" >"$PID_FILE"
cat >"$META_FILE" <<EOF
pid=$(cat "$PID_FILE")
log=$LOG_FILE
db=$WATCH_DB
auto_review=${PR_DAEMON_AUTO_REVIEW:-0}
dry_run=${PR_DAEMON_DRY_RUN:-0}
interval=$INTERVAL
refresh_interval=$REFRESH_INTERVAL
max_reviews=$MAX_REVIEWS
started_at=$(date '+%Y-%m-%d %H:%M:%S')
EOF

echo "started review watcher pid $(cat "$PID_FILE")"
echo "log: $LOG_FILE"
echo "auto_review: ${PR_DAEMON_AUTO_REVIEW:-0}"
echo "dry_run: ${PR_DAEMON_DRY_RUN:-0}"
