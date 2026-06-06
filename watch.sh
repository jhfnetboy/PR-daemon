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

ACTION="${1:-restart}"

export PR_DAEMON_STATE_DIR="${PR_DAEMON_STATE_DIR:-$ROOT/.state/pr-daemon}"
export PR_DAEMON_REVIEW_WATCH_DB="${PR_DAEMON_REVIEW_WATCH_DB:-$PR_DAEMON_STATE_DIR/pr-watch.sqlite}"
export PR_DAEMON_AUTO_REVIEW="${PR_DAEMON_AUTO_REVIEW:-1}"
export PR_DAEMON_DRY_RUN="${PR_DAEMON_DRY_RUN:-0}"
export PR_DAEMON_MAX_REVIEWS_PER_CYCLE="${PR_DAEMON_MAX_REVIEWS_PER_CYCLE:-3}"
export PR_DAEMON_WATCH_INTERVAL="${PR_DAEMON_WATCH_INTERVAL:-30}"
export PR_DAEMON_REVIEW_REFRESH_INTERVAL="${PR_DAEMON_REVIEW_REFRESH_INTERVAL:-3600}"
export PR_DAEMON_ACTIVE_REVIEW_STALE_SECONDS="${PR_DAEMON_ACTIVE_REVIEW_STALE_SECONDS:-14400}"

case "$ACTION" in
  queue)
    sqlite3 "$PR_DAEMON_REVIEW_WATCH_DB" '
      select "last_full_sync_epoch", coalesce(value, "")
      from pr_watch_meta
      where key = "last_full_sync_epoch";
    ' 2>/dev/null || true
    echo "---"
    sqlite3 "$PR_DAEMON_REVIEW_WATCH_DB" '
      select status, count(*)
      from pr_watch_targets
      group by status
      order by count(*) desc, status asc;
    ' 2>/dev/null || true
    echo "---"
    sqlite3 "$PR_DAEMON_REVIEW_WATCH_DB" '
      select repo, pr_number, status, substr(head_oid,1,7), coalesce(last_review_event, "")
      from pr_watch_targets
      where status in ("needs_review","prompt_ready","reviewing","changes_requested","approved","commented")
      order by
        case status
          when "reviewing" then 0
          when "prompt_ready" then 1
          when "needs_review" then 2
          else 3
        end,
        last_seen_at desc
      limit 20;
    ' 2>/dev/null || true
    ;;
  current)
    if [ -f "$PR_DAEMON_STATE_DIR/current-review.json" ]; then
      cat "$PR_DAEMON_STATE_DIR/current-review.json"
    else
      echo "no active codex review"
    fi
    ;;
  first-pass)
    python3 - "$PR_DAEMON_STATE_DIR" "$ROOT/reviews" "${2:-}" "${3:-}" <<'PY'
import json
import sys
from pathlib import Path

state_dir = Path(sys.argv[1])
reviews_dir = Path(sys.argv[2])
repo_arg = sys.argv[3].strip() if len(sys.argv) > 3 else ""
pr_arg = sys.argv[4].strip() if len(sys.argv) > 4 else ""

repo = repo_arg
pr_number = pr_arg

if not repo or not pr_number:
    current_path = state_dir / "current-review.json"
    if not current_path.is_file():
        print("no active codex review and no repo/pr specified")
        raise SystemExit(1)
    current = json.loads(current_path.read_text(encoding="utf-8"))
    repo = str(current["repo"])
    pr_number = str(current["pr_number"])

prefix = repo.replace("/", "-")
matches = sorted(
    reviews_dir.glob(f"{prefix}-{pr_number}-local-review-*.md"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)
if not matches:
    print(f"no first-pass review artifact found for {repo}#{pr_number}")
    raise SystemExit(1)

path = matches[0]
print(path)
wanted = (
    "Started:",
    "Repository:",
    "Base:",
    "Target:",
    "Provider:",
    "Model:",
    "Base URL:",
    "Thinking Mode:",
    "Reasoning Effort:",
    "Fallback Switched:",
    "Chunks:",
)
for line in path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if stripped.startswith(wanted):
        print(stripped)
PY
    ;;
  *)
    exec ./scripts/start_review_watch.sh "$ACTION"
    ;;
esac
