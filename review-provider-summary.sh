#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DB="${PR_DAEMON_MODEL_EVAL_DB:-$ROOT/reviews/model-evals/model-evals.sqlite}"

exec python3 scripts/model_eval_db.py provider-summary --db "$DB" "$@"
