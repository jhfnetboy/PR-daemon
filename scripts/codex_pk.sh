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
# real run now streams within seconds. Treat a hang as "Codex unavailable" and fall back FAST
# rather than burning the review budget: 1 attempt (no retry storm), 60s no-output = hung, 300s
# hard cap. Worst case ~5 min (was ~14: 2×420s). Override via env for a deliberately slow run.
STALL_SECS="${CODEX_STALL_SECS:-60}"
MAX_SECS="${CODEX_MAX_SECS:-300}"
ATTEMPTS="${CODEX_ATTEMPTS:-1}"

[ -f "$PROMPT_FILE" ] || { echo "ERROR: prompt file not found: $PROMPT_FILE" >&2; exit 1; }

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

for i in $(seq 1 "$ATTEMPTS"); do
  echo "[codex_pk] codex attempt $i/$ATTEMPTS (stall=${STALL_SECS}s cap=${MAX_SECS}s)" >&2
  if run_codex_once "$i"; then
    echo "[codex_pk] codex succeeded on attempt $i" >&2
    cat "$OUT_FILE"
    exit 0
  fi
done

echo "[codex_pk] all $ATTEMPTS codex attempts failed — falling back to DeepSeek PK" >&2
if bash "$HERE/deepseek_pk_challenge.sh" "$PROMPT_FILE" > "$OUT_FILE.ds" 2>"$OUT_FILE.dserr"; then
  {
    echo "CHALLENGER: deepseek-fallback (codex hung/failed ${ATTEMPTS}x)"
    cat "$OUT_FILE.ds"
  } > "$OUT_FILE"
  cat "$OUT_FILE"
  exit 0
fi

echo "[codex_pk] DeepSeek fallback also failed:" >&2
cat "$OUT_FILE.dserr" >&2
exit 1
