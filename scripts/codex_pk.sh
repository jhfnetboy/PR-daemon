#!/usr/bin/env bash
# Run a PK challenge through `codex exec` with hang detection, one retry, and an
# automatic DeepSeek fallback.
#
#   bash scripts/codex_pk.sh <prompt-file> [output-file]
#
# Why this exists: `codex exec` intermittently hangs producing ZERO output and
# never returns. A plain wall-clock timeout can't tell "hung" from "slow but
# working", so this watches the OUTPUT FILE's size instead: if it stops growing
# for CODEX_STALL_SECS, the process is stalled and gets killed. A run that is
# still streaming is left alone until the hard cap.
#
# Env knobs:
#   CODEX_STALL_SECS   no-new-output seconds before declaring a hang   (default 120)
#   CODEX_MAX_SECS     hard wall-clock cap per attempt                 (default 420)
#   CODEX_ATTEMPTS     codex attempts before falling back to DeepSeek  (default 2)
#
# Exit codes: 0 = a challenge was produced (by codex OR by the fallback),
#             1 = every challenger failed.
# The first line of the output names the challenger that actually ran, so the
# caller can label the review honestly instead of claiming "Codex" every time.
set -uo pipefail

PROMPT_FILE="${1:?usage: codex_pk.sh <prompt-file> [output-file]}"
OUT_FILE="${2:-/tmp/codex-pk-$$.out}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Tightened 2026-08-04: the `< /dev/null` fix below removed the stdin-EOF hang at its root, so a
# real run now streams within seconds. 1 attempt (no retry storm) + treat a hang as "Codex
# unavailable" and fall back fast, instead of burning ~14 min (was 2×420s). Stall/cap left roomy
# enough NOT to kill a legit run that emits early then spends time in a tool/reasoning phase on a
# large PR: 90s no-output = hung, 360s hard cap → worst case ~6 min. Override via env for slower runs.
STALL_SECS="${CODEX_STALL_SECS:-90}"
MAX_SECS="${CODEX_MAX_SECS:-360}"
ATTEMPTS="${CODEX_ATTEMPTS:-1}"

[ -f "$PROMPT_FILE" ] || { echo "ERROR: prompt file not found: $PROMPT_FILE" >&2; exit 1; }

# ── Short-term circuit breaker (added 2026-08-06) ────────────────────────────
# A hung `codex exec` costs a full stall+cap cycle before we learn anything. Measured on
# CoLivingOS#74: 366s of a 1159s review — 31.6% of the wall clock — spent waiting on a process
# that produced zero bytes. The stall detector caps ONE attempt; it does nothing about paying
# that tax again on the very next PR. So a hang trips a breaker: subsequent calls skip codex
# and go straight to DeepSeek until the breaker expires, then let exactly one probe through.
#
# The breaker is deliberately SHORT (30 min). Codex outages are usually transient; a long
# breaker would quietly downgrade every review of a session to the fallback challenger.
BREAKER_FILE="${CODEX_BREAKER_FILE:-${PR_DAEMON_STATE_DIR:-$HERE/../.state/pr-daemon}/codex-breaker.json}"
BREAKER_SECS="${CODEX_BREAKER_SECS:-1800}"

breaker_age() {   # seconds since the breaker tripped, or "" if not tripped
  [ -f "$BREAKER_FILE" ] || return 1
  local m; m="$(stat -f%m "$BREAKER_FILE" 2>/dev/null || echo 0)"
  [ "$m" -gt 0 ] || return 1
  echo $(( $(date +%s) - m ))
}

trip_breaker() {  # $1 = reason
  mkdir -p "$(dirname "$BREAKER_FILE")" 2>/dev/null
  printf '{"tripped_at":"%s","reason":"%s","breaker_secs":%s}\n' \
    "$(date -Iseconds)" "$1" "$BREAKER_SECS" > "$BREAKER_FILE" 2>/dev/null || true
}

BREAKER_OPEN=0
if age="$(breaker_age)"; then
  if [ "$age" -lt "$BREAKER_SECS" ]; then
    BREAKER_OPEN=1
    BREAKER_WHEN="$(sed -n 's/.*"tripped_at":"\([^"]*\)".*/\1/p' "$BREAKER_FILE" 2>/dev/null)"
    echo "[codex_pk] breaker OPEN (codex hung ${age}s ago at ${BREAKER_WHEN:-?}, expires in $(( BREAKER_SECS - age ))s) — skipping codex" >&2
  else
    echo "[codex_pk] breaker expired after ${age}s — letting one codex probe through" >&2
    rm -f "$BREAKER_FILE"
  fi
fi

filesize() { wc -c < "$1" 2>/dev/null | tr -d ' ' || echo 0; }

# Kill the whole process GROUP, not just the direct child. `codex exec` spawns
# helpers; killing only the parent leaves them running (verified: a plain
# `kill -9 $pid` on a wrapper left its `sleep` child alive indefinitely).
# macOS has no setsid, and `set -m` in a non-interactive script does not reliably
# give the job its own process group, so a group kill (`kill -- -$pid`) misses the
# grandchildren. Walk the descendant tree explicitly instead: children first, then
# the parent, so nothing gets reparented to init and survives.
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill -9 "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
}

run_codex_once() {
  local attempt="$1" raw="$OUT_FILE.raw"
  : > "$raw"

  # `< /dev/null` is THE fix, not a detail. Without it `codex exec` prints
  # "Reading additional input from stdin..." and blocks forever waiting for an
  # EOF that never arrives, because a non-TTY stdin makes it try to append piped
  # input to the prompt. That is the entire "codex hangs" phenomenon — it was
  # never quota, auth, or prompt size. Verified: the exact 8KB prompt that
  # stalled twice at 39 bytes completes in 19s once stdin is closed.
  #
  # `set -m` puts the background job in its own process group so kill_tree can
  # signal the entire group via the negative pid.
  set -m
  codex exec --skip-git-repo-check "$(cat "$PROMPT_FILE")" < /dev/null > "$raw" 2>&1 &
  local pid=$!
  set +m

  local start last_size last_change now size
  start=$(date +%s); last_size=0; last_change=$start

  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    now=$(date +%s)
    size=$(filesize "$raw")

    if [ "$size" -gt "$last_size" ]; then
      last_size=$size; last_change=$now
    fi

    if [ $(( now - last_change )) -ge "$STALL_SECS" ]; then
      echo "[codex_pk] attempt $attempt: no output for ${STALL_SECS}s (${size}B total) — killing stalled codex" >&2
      kill_tree "$pid"
      return 2
    fi
    if [ $(( now - start )) -ge "$MAX_SECS" ]; then
      echo "[codex_pk] attempt $attempt: hard cap ${MAX_SECS}s reached — killing codex" >&2
      kill_tree "$pid"
      return 3
    fi
  done

  wait "$pid"; local rc=$?
  if [ "$rc" -ne 0 ] || [ "$(filesize "$raw")" -lt 20 ]; then
    echo "[codex_pk] attempt $attempt: codex exited rc=$rc with $(filesize "$raw")B output" >&2
    return 4
  fi

  { echo "CHALLENGER: codex"; cat "$raw"; } > "$OUT_FILE"
  return 0
}

CODEX_RC=0
if [ "$BREAKER_OPEN" -eq 0 ]; then
  for i in $(seq 1 "$ATTEMPTS"); do
    echo "[codex_pk] codex attempt $i/$ATTEMPTS (stall=${STALL_SECS}s cap=${MAX_SECS}s)" >&2
    run_codex_once "$i"; CODEX_RC=$?
    if [ "$CODEX_RC" -eq 0 ]; then
      echo "[codex_pk] codex succeeded on attempt $i" >&2
      # A success clears a stale breaker file left by an earlier expired trip.
      rm -f "$BREAKER_FILE"
      cat "$OUT_FILE"
      exit 0
    fi
  done
  # rc 2 = stalled (no output), rc 3 = hard cap. Both are "codex is hung", which is what the
  # breaker exists for. rc 4 (exited non-zero / too little output) is a normal failure — it
  # costs seconds, not minutes, so it does NOT trip the breaker.
  if [ "$CODEX_RC" -eq 2 ] || [ "$CODEX_RC" -eq 3 ]; then
    trip_breaker "$([ "$CODEX_RC" -eq 2 ] && echo stalled || echo hard_cap)"
    echo "[codex_pk] breaker TRIPPED — next ${BREAKER_SECS}s of calls skip codex" >&2
  fi
  echo "[codex_pk] all $ATTEMPTS codex attempts failed — falling back to DeepSeek PK" >&2
fi

# The first line names who ACTUALLY answered, so the caller labels the review honestly instead
# of writing "R3=codex" over a round codex never ran. Breaker-skips say so explicitly.
if [ "$BREAKER_OPEN" -eq 1 ]; then
  FALLBACK_LABEL="deepseek-fallback (codex breaker open — hung ${age}s ago, not retried)"
else
  FALLBACK_LABEL="deepseek-fallback (codex hung/failed ${ATTEMPTS}x)"
fi
# Overridable so the breaker test can exercise the full path without spending a real DeepSeek
# call. Production never sets it.
FALLBACK_SH="${CODEX_PK_FALLBACK:-$HERE/deepseek_pk_challenge.sh}"
if bash "$FALLBACK_SH" "$PROMPT_FILE" > "$OUT_FILE.ds" 2>"$OUT_FILE.dserr"; then
  {
    echo "CHALLENGER: $FALLBACK_LABEL"
    cat "$OUT_FILE.ds"
  } > "$OUT_FILE"
  cat "$OUT_FILE"
  exit 0
fi

echo "[codex_pk] DeepSeek fallback also failed:" >&2
cat "$OUT_FILE.dserr" >&2
exit 1
