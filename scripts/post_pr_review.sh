#!/usr/bin/env bash
# Post a PR review with the review GitHub account.
# PAT mode (PR_DAEMON_REVIEW_TOKEN set): uses GH_TOKEN env, no account switching.
# Auth-switch mode (no token): switches to review user, restores main user on exit.

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

# Dry-run guard: with PR_DAEMON_NO_POST=1 this never touches GitHub (no account
# switch, no POST). Used for validation runs; the review body is echoed to stderr.
if [ "${PR_DAEMON_NO_POST:-0}" = "1" ]; then
  echo "PR_DAEMON_NO_POST=1 — dry run: NOT posting. Would $MODE to $REPO#$PR. Body:" >&2
  [ -f "$BODY_FILE" ] && cat "$BODY_FILE" >&2 || true
  exit 0
fi

TMP_FILES=""
cleanup_tmp() { [ -n "$TMP_FILES" ] && rm -f $TMP_FILES; return 0; }

restore_main() {
  cleanup_tmp
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
  # Identity preflight: FATAL on a mismatch, ADVISORY when the call itself fails.
  #
  # Why the split (2026-08-07 and 2026-08-18): GET /user has now twice returned 503 while
  # POST /repos/.../reviews was perfectly healthy. The old fatal form killed the script in
  # preflight, so a review that would have posted did not — and the failure looked like
  # "GitHub is down for writes", which it was not. A preflight that cannot reach the API
  # has learned NOTHING about the token's identity; treating "unknown" as "wrong" converts
  # someone else's partial outage into a lost review.
  #
  # The wrong-account guard is not weakened: the POST response carries .user.login, which
  # is the authoritative answer to "who did this get attributed to", and it is checked
  # below. Failure modes trade in the right direction — worst case becomes "posted by the
  # wrong account and told about it loudly", instead of "correct review silently not
  # posted, on an endpoint that was never even asked".
  ACTIVE_USER="$(GH_TOKEN="$REVIEW_TOKEN" gh api user -q .login 2>/dev/null || true)"
  if [ -n "$ACTIVE_USER" ] && [ "$ACTIVE_USER" != "$EXPECTED_USER" ]; then
    echo "Review token belongs to $ACTIVE_USER, expected $EXPECTED_USER." >&2
    exit 1
  fi
  if [ -z "$ACTIVE_USER" ]; then
    echo "⚠️  identity preflight unreachable (GET /user failed) — proceeding; the POST response's .user.login is verified instead." >&2
  fi
  # PAT mode: no account switching occurred, so drop restore_main — but keep temp cleanup.
  trap cleanup_tmp EXIT
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
RESPONSE="$(mktemp "${TMPDIR:-/tmp}/pr-review-resp.XXXXXX")"
TMP_FILES="$PAYLOAD $RESPONSE"
if [ "$MODE" = "--approve" ] && [ -z "$BODY_FILE" ]; then
  jq -n --arg event "$EVENT" '{event:$event}' > "$PAYLOAD"
else
  jq -n --rawfile body "$BODY_FILE" --arg event "$EVENT" '{body:$body,event:$event}' > "$PAYLOAD"
fi
run_gh api --method POST "repos/$REPO/pulls/$PR/reviews" --input "$PAYLOAD" > "$RESPONSE"

# Authoritative identity check: who GitHub actually attributed this review to. This is the
# check the preflight above only approximates — it runs on the same request that did the
# write, so it cannot disagree with reality the way a separate GET can.
POSTED_AS="$(jq -r '.user.login // empty' "$RESPONSE" 2>/dev/null || true)"
REVIEW_ID="$(jq -r '.id // empty' "$RESPONSE" 2>/dev/null || true)"
if [ -n "$POSTED_AS" ] && [ "$POSTED_AS" != "$EXPECTED_USER" ]; then
  echo "❌ REVIEW ALREADY POSTED, BUT AS THE WRONG ACCOUNT: $POSTED_AS (expected $EXPECTED_USER)." >&2
  echo "   $REPO#$PR review id=$REVIEW_ID — it is live on GitHub; dismiss or delete it manually." >&2
  exit 1
fi

if [ -n "$REVIEW_TOKEN" ]; then
  echo "Posted PR review as ${POSTED_AS:-$EXPECTED_USER} (via PAT, no account switch). review id=${REVIEW_ID:-?}"
else
  echo "Posted PR review as ${POSTED_AS:-$EXPECTED_USER}. review id=${REVIEW_ID:-?}  Restoring default account $MAIN_USER..."
fi
