#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${PR_DAEMON_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

STATE_DIR="${PR_DAEMON_STATE_DIR:-$ROOT/.state/pr-daemon}"
WATCH_DB="${PR_DAEMON_REVIEW_WATCH_DB:-$STATE_DIR/pr-watch.sqlite}"
MODEL_EVAL_DB="${PR_DAEMON_MODEL_EVAL_DB:-$ROOT/reviews/model-evals/model-evals.sqlite}"
PROMPT_DIR="${PR_DAEMON_PROMPT_DIR:-$ROOT/reviews/watch-prompts}"
MODEL_EVAL_DIR="${ROOT}/reviews/model-evals"

mkdir -p "$STATE_DIR" "$PROMPT_DIR" "$MODEL_EVAL_DIR"

python3 scripts/review_watch.py --db "$WATCH_DB" --init-db >/dev/null
python3 scripts/model_eval_db.py init --db "$MODEL_EVAL_DB" >/dev/null

echo "state_dir=$STATE_DIR"
echo "watch_db=$WATCH_DB"
echo "model_eval_db=$MODEL_EVAL_DB"
echo "prompt_dir=$PROMPT_DIR"
