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
# A genuinely hung `codex exec` — one that produces NOTHING and never returns — costs a full
# stall timeout before we learn anything, and the stall detector only caps that ONE attempt. It
# does nothing about paying the same tax again on the very next PR. So a real stall trips a
# breaker: subsequent calls skip codex and go straight to DeepSeek until it expires, then let one
# probe through.
#
# ⚠️ CORRECTION (adversarial review of this very change). The CoLivingOS#74 incident that
# motivated this was NOT a hang. The preserved artifact of that run is 99,590 bytes of real
# streaming analysis — codex banner, tool calls, a node repro printing comparison tables —
# killed at ~352s by the HARD CAP while it was still working. So:
#   * rc=3 (hard cap) means codex was ALIVE and streaming for the whole run: by construction it
#     emitted output at least once every STALL_SECS. Tripping the breaker on it disables the
#     strongest challenger for 30 minutes because one PR was slow. It must NOT trip.
#   * rc=2 (stall) only counts as a hang when almost nothing was produced. A run that streamed
#     90KB and then went quiet for 90s is a slow tool call, not a dead process.
# The real remedy for #74 was a bigger CODEX_MAX_SECS, not a breaker. The breaker is for the
# separate, real failure mode: codex that never says anything at all.
#
# The breaker is deliberately SHORT (30 min). Codex outages are usually transient; a long
# breaker would quietly downgrade every review of a session to the fallback challenger.
BREAKER_FILE="${CODEX_BREAKER_FILE:-${PR_DAEMON_STATE_DIR:-$HERE/../.state/pr-daemon}/codex-breaker.json}"
BREAKER_SECS="${CODEX_BREAKER_SECS:-1800}"

breaker_age() {   # seconds since the breaker tripped, or "" if not tripped / unusable
  [ -f "$BREAKER_FILE" ] || return 1
  # `stat -f%m` is BSD; on GNU coreutils -f means *filesystem* and %m prints a mount point.
  local m; m="$(stat -f%m "$BREAKER_FILE" 2>/dev/null || stat -c%Y "$BREAKER_FILE" 2>/dev/null || echo 0)"
  case "$m" in ''|*[!0-9]*) return 1 ;; esac
  local a=$(( $(date +%s) - m ))
  # A future mtime (clock skew, or a restored/copied file) gave "expires in 12703951s" — codex
  # disabled for ~147 days. Treat it as unusable so the caller expires the file instead.
  [ "$a" -ge 0 ] || return 1
  echo "$a"
}

trip_breaker() {  # $1 = reason
  mkdir -p "$(dirname "$BREAKER_FILE")" 2>/dev/null
  printf '{"tripped_at":"%s","reason":"%s","breaker_secs":%s}\n' \
    "$(date -Iseconds)" "$1" "$BREAKER_SECS" > "$BREAKER_FILE" 2>/dev/null || true
}

BREAKER_OPEN=0
if age="$(breaker_age)" && [ -n "$age" ]; then
  if [ "$age" -lt "$BREAKER_SECS" ]; then
    BREAKER_OPEN=1
    BREAKER_WHEN="$(sed -n 's/.*"tripped_at":"\([^"]*\)".*/\1/p' "$BREAKER_FILE" 2>/dev/null)"
    echo "[codex_pk] breaker OPEN (codex hung ${age}s ago at ${BREAKER_WHEN:-?}, expires in $(( BREAKER_SECS - age ))s) — skipping codex" >&2
  else
    echo "[codex_pk] breaker expired after ${age}s — letting one codex probe through" >&2
    rm -f "$BREAKER_FILE"
  fi
elif [ -f "$BREAKER_FILE" ]; then
  echo "[codex_pk] breaker file unusable (bad or future mtime) — discarding it" >&2
  rm -f "$BREAKER_FILE"
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

# Bytes below which a stalled run counts as "produced nothing". A real codex run emits its
# banner and version within seconds, so anything under a couple of KB means it never got going.
SILENT_BYTES="${CODEX_SILENT_BYTES:-2048}"

CODEX_RC=0
HUNG=0        # sticky across attempts: with ATTEMPTS>1, only the LAST rc used to decide
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
    # ONLY a silent stall counts as a hang — see the CORRECTION at the top of this file.
    # rc=3 (hard cap) means it streamed the whole time; rc=4 (fast non-zero exit) costs seconds;
    # rc=2 after real output is a slow tool call, not a dead process.
    if [ "$CODEX_RC" -eq 2 ]; then
      produced="$(filesize "$OUT_FILE.raw")"
      if [ "$produced" -lt "$SILENT_BYTES" ]; then
        HUNG=1
      else
        echo "[codex_pk] attempt $i stalled AFTER producing ${produced}B — slow, not hung; breaker not tripped" >&2
      fi
    elif [ "$CODEX_RC" -eq 3 ]; then
      echo "[codex_pk] attempt $i hit the hard cap while still streaming ($(filesize "$OUT_FILE.raw")B) — codex was working, not hung." >&2
      echo "[codex_pk] breaker NOT tripped; raise CODEX_MAX_SECS if this repeats." >&2
    fi
  done
  if [ "$HUNG" -eq 1 ]; then
    trip_breaker "silent_stall"
    # Only claim a trip if the write actually landed — a read-only state dir used to print
    # "breaker TRIPPED" with no file behind it.
    if [ -f "$BREAKER_FILE" ]; then
      echo "[codex_pk] breaker TRIPPED — next ${BREAKER_SECS}s of calls skip codex" >&2
    else
      echo "[codex_pk] warn: could not write $BREAKER_FILE — breaker NOT armed" >&2
    fi
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
