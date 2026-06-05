#!/usr/bin/env bash
# Post a PR review with the review GitHub account, then switch back to main.

set -euo pipefail

ENV_FILE="${PR_DAEMON_ENV_FILE:-.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

usage() {
  cat <<EOF
Usage:
  $0 --repo OWNER/REPO --pr NUMBER --body-file FILE [--comment|--request-changes|--approve]

Environment:
  PR_DAEMON_MAIN_USER     Default GitHub login to restore. Default: jhfnetboy
  PR_DAEMON_REVIEW_USER   Review GitHub login. Default: clestons
  PR_DAEMON_REVIEW_TOKEN  Optional token used only for this review command
EOF
}

REPO=""
PR=""
BODY_FILE=""
MODE=""
EXPECTED_USER="${PR_DAEMON_REVIEW_USER:-clestons}"
MAIN_USER="${PR_DAEMON_MAIN_USER:-jhfnetboy}"
HOST="${PR_DAEMON_GH_HOST:-github.com}"
REVIEW_TOKEN="${PR_DAEMON_REVIEW_TOKEN:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --pr) PR="${2:-}"; shift 2 ;;
    --body-file) BODY_FILE="${2:-}"; shift 2 ;;
    --comment|--request-changes|--approve) MODE="$1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$REPO" ] || [ -z "$PR" ] || [ -z "$MODE" ]; then
  usage >&2
  exit 2
fi
if [ "$MODE" != "--approve" ] && [ ! -s "$BODY_FILE" ]; then
  echo "body file missing or empty: $BODY_FILE" >&2
  exit 2
fi

restore_main() {
  if [ "${PR_DAEMON_RESTORE_MAIN:-1}" = "1" ]; then
    active=""
    for _ in 1 2 3; do
      active="$(gh api user -q .login 2>/dev/null || true)"
      [ -n "$active" ] && break
      sleep 1
    done
    if [ "$active" != "$MAIN_USER" ]; then
      gh auth switch --hostname "$HOST" --user "$MAIN_USER" >/dev/null 2>&1 || true
    fi
  fi
}
trap restore_main EXIT

run_gh() {
  if [ -n "$REVIEW_TOKEN" ]; then
    GH_TOKEN="$REVIEW_TOKEN" gh "$@"
  else
    gh "$@"
  fi
}

if [ -n "$REVIEW_TOKEN" ]; then
  ACTIVE_USER="$(GH_TOKEN="$REVIEW_TOKEN" gh api user -q .login)"
  if [ "$ACTIVE_USER" != "$EXPECTED_USER" ]; then
    echo "Review token belongs to $ACTIVE_USER, expected $EXPECTED_USER." >&2
    exit 1
  fi
elif ! gh auth switch --hostname "$HOST" --user "$EXPECTED_USER" >/dev/null 2>&1; then
  cat >&2 <<EOF
Review account is not available in gh credential store.
Expected review user: $EXPECTED_USER

Log it in from a normal Terminal:
  gh auth login --hostname $HOST --web --git-protocol https
  gh auth switch --hostname $HOST --user $EXPECTED_USER
  gh api user -q .login

Or put a token in .env:
  PR_DAEMON_REVIEW_TOKEN=...

After login, re-run this command. The script will switch back to $MAIN_USER automatically.
EOF
  exit 1
else
  ACTIVE_USER="$(gh api user -q .login)"
  if [ "$ACTIVE_USER" != "$EXPECTED_USER" ]; then
    echo "Refusing to post review. Active user is $ACTIVE_USER, expected $EXPECTED_USER." >&2
    exit 1
  fi
fi

case "$MODE" in
  --comment)
    EVENT="COMMENT"
    ;;
  --request-changes)
    EVENT="REQUEST_CHANGES"
    ;;
  --approve)
    EVENT="APPROVE"
    ;;
esac

PAYLOAD="$(mktemp "${TMPDIR:-/tmp}/pr-review.XXXXXX")"
if [ "$MODE" = "--approve" ] && [ -z "$BODY_FILE" ]; then
  jq -n --arg event "$EVENT" '{event:$event}' > "$PAYLOAD"
else
  jq -n --rawfile body "$BODY_FILE" --arg event "$EVENT" '{body:$body,event:$event}' > "$PAYLOAD"
fi
run_gh api --method POST "repos/$REPO/pulls/$PR/reviews" --input "$PAYLOAD" >/dev/null

echo "Posted PR review as $EXPECTED_USER. Restoring default account $MAIN_USER..."
