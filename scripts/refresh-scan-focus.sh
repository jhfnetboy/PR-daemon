#!/usr/bin/env bash
# refresh-scan-focus.sh — regenerate the PR-daemon scan list (~/.config/prbot/repos.conf)
# as "the N repos whose DEFAULT BRANCH was committed to most recently" PLUS pinned repos.
#
# Why: watching whole orgs meant scanning hundreds of dormant repos every cycle. The daemon
# should focus on where work is actually happening — top-N by last default-branch commit —
# while still letting you PIN specific repos that must always be watched regardless of recency.
# NOTE the metric is committedDate on the default branch, NOT repo.pushedAt: pushedAt counts
# any ref push, so dependabot/renovate PR branches keep dormant repos looking active.
#
#   refresh-scan-focus.sh                 # (default) recompute top-N + pinned → write repos.conf
#   refresh-scan-focus.sh refresh         # same as above (FORCE — always recomputes)
#   refresh-scan-focus.sh daily           # once-per-day IDEMPOTENT refresh (skips if already
#                                         #   done today); the entry point daemon-start & pilot
#                                         #   status call — many callers/day, GitHub hit once
#   refresh-scan-focus.sh add o/r [o/r…]  # pin repo(s) (always watched), then recompute
#   refresh-scan-focus.sh rm  o/r [o/r…]  # unpin repo(s), then recompute
#   refresh-scan-focus.sh list            # show what repos.conf currently resolves to
#
# Daily gate: $CFG/.focus-last-refresh holds the YYYY-MM-DD of the last real refresh; a same-day
# `daily` is a no-op. $CFG/focus-history.log records "<date>\t<resolved repo list>" per refresh.
#
# Config files under $CFG (auto-created with sane defaults on first run):
#   candidate-orgs.conf       orgs whose repos form the top-N candidate pool (one per line)
#   candidate-personal.conf   individual personal repos ALSO eligible for the top-N pool
#   focus-manual.conf         PINNED repos — always in repos.conf, on top of the N (the "追加" list)
#
# Env knobs:
#   FOCUS_TOP_N   how many recent repos to auto-include   (default 8)
#   PRBOT_CFG     config dir                              (default ~/.config/prbot)
set -uo pipefail

CFG="${PRBOT_CFG:-$HOME/.config/prbot}"
TOP_N="${FOCUS_TOP_N:-8}"
OUT="$CFG/repos.conf"
ORGS_F="$CFG/candidate-orgs.conf"
PERS_F="$CFG/candidate-personal.conf"
PIN_F="$CFG/focus-manual.conf"

mkdir -p "$CFG"
[ -f "$ORGS_F" ] || printf 'AAStarCommunity\niDoris-ai\nMushroomDAO\n' > "$ORGS_F"
[ -f "$PERS_F" ] || printf 'jhfnetboy/CMIC\njhfnetboy/goutou\njhfnetboy/PowerSalesMan\n' > "$PERS_F"
[ -f "$PIN_F" ]  || : > "$PIN_F"

# read a conf file: strip comments + blanks, trim, drop empties
readconf() { sed 's/#.*//' "$1" 2>/dev/null | awk 'NF{$1=$1;print $1}'; }

pin_add() {
  local r
  for r in "$@"; do
    case "$r" in */*) ;; *) echo "skip (not owner/repo): $r" >&2; continue ;; esac
    grep -qxF "$r" "$PIN_F" 2>/dev/null || echo "$r" >> "$PIN_F"
  done
}
pin_rm() {
  local r tmp; tmp="$(mktemp)"
  cp "$PIN_F" "$tmp"
  # NOTE: do NOT gate `mv` on grep's exit status. grep -v returns 1 when it emits
  # ZERO lines (i.e. removing the only pinned repo empties the file) — `&& mv` would
  # then skip the update and silently keep the repo. Always take grep's output.
  for r in "$@"; do grep -vxF "$r" "$tmp" > "$tmp.2" || true; mv "$tmp.2" "$tmp"; done
  mv "$tmp" "$PIN_F"
}

refresh() {
  local scan; scan="$(mktemp)"   # tab-separated: <default-branch last commit date> \t owner/repo
  local org r ts

  # RANKING METRIC = last commit on the DEFAULT BRANCH, *not* repo.pushedAt.
  # pushedAt is bumped by a push to ANY ref — including dependabot/renovate pushing PR
  # branches. A repo whose trunk has been dormant for a month still looks "active" by
  # pushedAt (real case: SuperPaymaster, pushedAt=08-03 but main's last commit=07-09,
  # inflated purely by bot dependency PRs) and would crowd a genuinely active repo out
  # of the top-N. committedDate on defaultBranchRef tracks where work actually lands.
  local gq='query($org:String!, $cursor:String){organization(login:$org){repositories(first:100, after:$cursor, isArchived:false, orderBy:{field:PUSHED_AT,direction:DESC}){pageInfo{hasNextPage endCursor} nodes{nameWithOwner pushedAt defaultBranchRef{target{... on Commit{committedDate}}}}}}}'

  # org repos (non-archived) → candidate pool
  while IFS= read -r org; do
    [ -z "$org" ] && continue
    # Fall back to pushedAt when committedDate is missing (empty repo / odd default ref),
    # so such a repo still sorts rather than silently vanishing from the pool.
    gh api graphql -f query="$gq" -f org="$org" --paginate \
      --jq '.data.organization.repositories.nodes[] | [(.defaultBranchRef.target.committedDate // .pushedAt), .nameWithOwner] | @tsv' \
      2>/dev/null >> "$scan"
  done < <(readconf "$ORGS_F")

  # personal candidates → also eligible for the top-N (same metric: default-branch HEAD date)
  while IFS= read -r r; do
    [ -z "$r" ] && continue
    ts="$(gh api "repos/$r/commits?per_page=1" 2>/dev/null \
      | python3 -c "import json,sys
d=json.load(sys.stdin)
print(d[0]['commit']['author']['date'] if isinstance(d,list) and d else '')" 2>/dev/null)"
    [ -z "$ts" ] && ts="$(gh repo view "$r" --json pushedAt 2>/dev/null \
      | python3 -c "import json,sys;print(json.load(sys.stdin).get('pushedAt',''))" 2>/dev/null)"
    [ -n "$ts" ] && printf '%s\t%s\n' "$ts" "$r" >> "$scan"
  done < <(readconf "$PERS_F")

  # top-N by pushedAt desc
  local topn; topn="$(mktemp)"
  sort -r "$scan" | awk -F'\t' '!seen[$2]++{print $2}' | head -n "$TOP_N" > "$topn"

  # pinned repos (always included), minus any already in top-N
  local pins; pins="$(mktemp)"
  readconf "$PIN_F" | awk 'NF' | while IFS= read -r r; do
    grep -qxF "$r" "$topn" || echo "$r"
  done > "$pins"

  # emit repos.conf
  {
    echo "# GENERATED by refresh-scan-focus.sh — DO NOT hand-edit."
    echo "# Default scan scope = top-$TOP_N most-recently-pushed repos + pinned repos."
    echo "# 改候选池: candidate-orgs.conf / candidate-personal.conf"
    echo "# 加/减常驻: refresh-scan-focus.sh add|rm <owner/repo>  (写入 focus-manual.conf)"
    echo "# 重新计算:  refresh-scan-focus.sh   (repos 有新提交后跑一次，Top-$TOP_N 会变)"
    echo
    echo "# --- top-$TOP_N by recent push (auto) ---"
    cat "$topn"
    if [ -s "$pins" ]; then
      echo
      echo "# --- pinned / 手动追加 (focus-manual.conf, 恒扫) ---"
      cat "$pins"
    fi
  } > "$OUT"

  echo "wrote $OUT:"
  grep -vE '^\s*#|^\s*$' "$OUT" | nl -w2 -s'. '
  rm -f "$scan" "$topn" "$pins"
}

daily() {
  local stamp="$CFG/.focus-last-refresh" hist="$CFG/focus-history.log" today
  today="$(date +%F)"
  if [ -f "$stamp" ] && [ "$(cat "$stamp" 2>/dev/null)" = "$today" ]; then
    echo "scan focus already refreshed today ($today) — idempotent no-op ($(grep -vcE '^\s*#|^\s*$' "$OUT" 2>/dev/null) repos)"
    return 0
  fi
  refresh
  echo "$today" > "$stamp"
  printf '%s\t%s\n' "$today" "$(grep -vE '^\s*#|^\s*$' "$OUT" 2>/dev/null | paste -sd, -)" >> "$hist"
  echo "recorded $today → $hist"
}

case "${1:-refresh}" in
  refresh) refresh ;;
  daily) daily ;;
  add) shift; [ $# -ge 1 ] || { echo "usage: add <owner/repo>..." >&2; exit 2; }; pin_add "$@"; refresh ;;
  rm)  shift; [ $# -ge 1 ] || { echo "usage: rm <owner/repo>..."  >&2; exit 2; }; pin_rm  "$@"; refresh ;;
  list) echo "repos.conf resolves to:"; grep -vE '^\s*#|^\s*$' "$OUT" | nl -w2 -s'. ' ;;
  *) echo "usage: refresh-scan-focus.sh [refresh|daily|add <o/r>|rm <o/r>|list]" >&2; exit 2 ;;
esac
