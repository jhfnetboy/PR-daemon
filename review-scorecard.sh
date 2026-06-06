#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DB="${PR_DAEMON_MODEL_EVAL_DB:-$ROOT/reviews/model-evals/model-evals.sqlite}"

if [ "$#" -lt 3 ]; then
  cat >&2 <<'EOF'
usage: ./review-scorecard.sh OWNER REPO PR_NUMBER [--limit N]

example:
  ./review-scorecard.sh MushroomDAO CityOS 2
  ./review-scorecard.sh MushroomDAO whitelist 2 --limit 10
EOF
  exit 2
fi

OWNER="$1"
REPO="$2"
PR_NUMBER="$3"
shift 3

exec python3 scripts/model_eval_db.py scorecard --db "$DB" --owner "$OWNER" --repo "$REPO" --pr-number "$PR_NUMBER" "$@"
