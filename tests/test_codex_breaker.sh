#!/usr/bin/env bash
# Test the codex_pk.sh hang breaker. No network, no real codex, no DeepSeek spend:
# `codex` and the DeepSeek fallback are both stubbed on PATH / via CODEX_PK_FALLBACK.
#
#   bash tests/test_codex_breaker.sh
#
# What it pins down:
#   1. a hung codex trips the breaker and writes the state file
#   2. the NEXT call skips codex entirely (proved by the stub's invocation counter) and
#      returns fast, instead of paying the stall timeout again
#   3. the fallback output says codex never ran, so a review cannot be labelled "R3=codex"
#   4. an EXPIRED breaker lets exactly one probe through again
#   5. a fast non-zero codex exit (rc=4) does NOT trip the breaker — it costs seconds,
#      and breaking on it would downgrade every later PR for a transient blip
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../scripts/codex_pk.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
ok()   { echo "  ✅ $1"; PASS=$((PASS + 1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$3', got '$2')"; fi; }

# ── stubs ───────────────────────────────────────────────────────────────────
mkdir -p "$TMP/bin"
CALLS="$TMP/codex-calls"
: > "$CALLS"

# Hangs forever emitting nothing — exactly the failure mode the breaker exists for.
cat > "$TMP/bin/codex" <<EOF
#!/usr/bin/env bash
echo call >> "$CALLS"
sleep 600
EOF
chmod +x "$TMP/bin/codex"

cat > "$TMP/fallback.sh" <<'EOF'
#!/usr/bin/env bash
echo "STUB FALLBACK VERDICT"
EOF
chmod +x "$TMP/fallback.sh"

echo "probe prompt" > "$TMP/prompt.txt"

export PATH="$TMP/bin:$PATH"
export CODEX_PK_FALLBACK="$TMP/fallback.sh"
export CODEX_BREAKER_FILE="$TMP/codex-breaker.json"
export CODEX_STALL_SECS=6 CODEX_MAX_SECS=30 CODEX_ATTEMPTS=1 CODEX_BREAKER_SECS=1800

calls() { wc -l < "$CALLS" | tr -d ' '; }

# ── 1. hung codex trips the breaker ─────────────────────────────────────────
echo "[1] hung codex trips the breaker"
t0=$(date +%s)
out1="$(bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out1.txt" 2>"$TMP/err1.txt")"
d1=$(( $(date +%s) - t0 ))
check "codex was invoked" "$(calls)" "1"
[ -f "$CODEX_BREAKER_FILE" ] && ok "breaker file written" || bad "breaker file missing"
grep -q '"reason":"silent_stall"' "$CODEX_BREAKER_FILE" && ok "reason recorded as silent_stall" \
  || bad "reason not recorded (got: $(cat "$CODEX_BREAKER_FILE" 2>/dev/null))"
echo "$out1" | grep -q "STUB FALLBACK VERDICT" && ok "fell back to the challenger stub" \
  || bad "no fallback output"
[ "$d1" -ge 6 ] && ok "first call paid the stall timeout (${d1}s)" \
  || bad "first call too fast (${d1}s) — did it really wait for the stall?"

# ── 2 + 3. next call skips codex, and says so ───────────────────────────────
echo "[2] breaker open -> next call skips codex"
t0=$(date +%s)
out2="$(bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out2.txt" 2>"$TMP/err2.txt")"
d2=$(( $(date +%s) - t0 ))
check "codex NOT invoked again" "$(calls)" "1"
[ "$d2" -le 3 ] && ok "returned fast (${d2}s vs ${d1}s) — stall tax not paid twice" \
  || bad "second call still slow (${d2}s)"
grep -q "breaker OPEN" "$TMP/err2.txt" && ok "breaker skip is logged" || bad "no breaker log line"
echo "$out2" | head -1 | grep -q "breaker open" \
  && ok "output line 1 says codex never ran (honest R3 label)" \
  || bad "challenger label does not disclose the skip: $(echo "$out2" | head -1)"

# ── 4. expired breaker lets one probe through ───────────────────────────────
echo "[3] expired breaker -> one probe allowed"
touch -t 202001010000 "$CODEX_BREAKER_FILE"   # far in the past = long expired
t0=$(date +%s)
bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out3.txt" >/dev/null 2>"$TMP/err3.txt"
d3=$(( $(date +%s) - t0 ))
check "codex probed again" "$(calls)" "2"
grep -q "breaker expired" "$TMP/err3.txt" && ok "expiry is logged" || bad "no expiry log line"
[ "$d3" -ge 6 ] && ok "probe really ran (${d3}s)" || bad "probe did not run (${d3}s)"

# ── 5. a fast failure must NOT trip the breaker ─────────────────────────────
echo "[4] fast non-zero exit does NOT trip the breaker"
rm -f "$CODEX_BREAKER_FILE"
cat > "$TMP/bin/codex" <<EOF
#!/usr/bin/env bash
echo call >> "$CALLS"
echo "boom" >&2
exit 1
EOF
chmod +x "$TMP/bin/codex"
bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out4.txt" >/dev/null 2>"$TMP/err4.txt"
check "codex was invoked" "$(calls)" "3"
[ -f "$CODEX_BREAKER_FILE" ] && bad "breaker tripped on a fast failure (it should not)" \
  || ok "breaker NOT tripped on a fast failure"

# ── 6. hard cap on a STREAMING run must NOT trip ────────────────────────────
# The incident that motivated this whole feature was NOT a hang: the preserved artifact is
# 99,590 bytes of real streaming analysis, killed at the hard cap while still working. Tripping
# on rc=3 would disable the strongest challenger for 30 minutes because one PR was slow.
echo "[5] hard cap while streaming does NOT trip the breaker"
rm -f "$CODEX_BREAKER_FILE"
cat > "$TMP/bin/codex" <<EOF
#!/usr/bin/env bash
echo call >> "$CALLS"
# Emit steadily so the stall detector never fires; only the hard cap can stop this.
while :; do echo "streaming real analysis output ................................"; sleep 1; done
EOF
chmod +x "$TMP/bin/codex"
before=$(calls)
CODEX_MAX_SECS=8 CODEX_STALL_SECS=6 bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out5.txt" >/dev/null 2>"$TMP/err5.txt"
check "codex was invoked" "$(calls)" "$((before + 1))"
[ -f "$CODEX_BREAKER_FILE" ] && bad "breaker tripped on a hard cap (codex was streaming, not hung)" \
  || ok "breaker NOT tripped on a hard cap"
grep -q "was working, not hung" "$TMP/err5.txt" && ok "log says codex was working" \
  || bad "no explanatory log line: $(tail -2 "$TMP/err5.txt")"

# ── 7. a stall AFTER substantial output is slow, not hung ───────────────────
echo "[6] stalling after real output does NOT trip the breaker"
rm -f "$CODEX_BREAKER_FILE"
cat > "$TMP/bin/codex" <<EOF
#!/usr/bin/env bash
echo call >> "$CALLS"
# ~4KB up front (over CODEX_SILENT_BYTES), then go quiet -> stall detector fires.
for i in \$(seq 1 60); do echo "real analysis line ................................................"; done
sleep 600
EOF
chmod +x "$TMP/bin/codex"
before=$(calls)
bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out6.txt" >/dev/null 2>"$TMP/err6.txt"
check "codex was invoked" "$(calls)" "$((before + 1))"
[ -f "$CODEX_BREAKER_FILE" ] && bad "breaker tripped after codex produced real output" \
  || ok "breaker NOT tripped after real output"
grep -q "slow, not hung" "$TMP/err6.txt" && ok "log distinguishes slow from hung" \
  || bad "no slow-not-hung log: $(tail -2 "$TMP/err6.txt")"

# ── 8. a future mtime must not disable codex for months ─────────────────────
echo "[7] a future-dated breaker file is discarded, not honored"
printf '{"tripped_at":"?","reason":"?"}\n' > "$CODEX_BREAKER_FILE"
touch -t 202801010000 "$CODEX_BREAKER_FILE"
cat > "$TMP/bin/codex" <<EOF
#!/usr/bin/env bash
echo call >> "$CALLS"
echo "boom" >&2
exit 1
EOF
chmod +x "$TMP/bin/codex"
before=$(calls)
bash "$SCRIPT" "$TMP/prompt.txt" "$TMP/out7.txt" >/dev/null 2>"$TMP/err7.txt"
check "codex was probed, not skipped" "$(calls)" "$((before + 1))"
grep -q "unusable" "$TMP/err7.txt" && ok "future mtime is called out" \
  || bad "future mtime not handled: $(tail -2 "$TMP/err7.txt")"

echo
echo "passed: $PASS   failed: $FAIL"
[ "$FAIL" -eq 0 ]
