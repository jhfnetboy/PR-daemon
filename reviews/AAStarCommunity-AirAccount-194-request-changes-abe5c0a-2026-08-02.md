## 🤖 Re-review of the fix commit (round 4) — DeepSeek R1 + Opus R2/R4 + Codex R3 PK

VERDICT: REQUEST_CHANGES

This is a re-review of commit `abe5c0a`, which claims to fix all 4 Medium findings from round 3
(`af0c4d9`). **All 4 fixes were checked; 1 is solid with no residual gap (TA_VERSION source), and 3
introduce or leave open real problems — one of them a genuine regression this exact commit introduces.**
80/80 assertions (T1-T47) pass, but the passing suite doesn't cover any of the 3 issues below — each
requires either a missing env file, real concurrency, or a specific failure branch the existing tests
don't exercise. One additional pre-existing (out-of-diff) issue was found during the full-scan pass.

Every finding below converged across 3 independent lines of evidence: mechanical repro run by the
orchestrator against the actual PR-head file, an independent Opus read of the diff (before seeing any
of the others' findings), and a real `codex exec` pass re-reading the actual file in a clean worktree
checked out at `abe5c0a`. Zero disagreement across all three on any of the 3 blocking items.

### Genuinely fixed and verified (no residual gap)
- ✅ **round-3 #1, TA_VERSION source** — now reads `AU_TA_VERSION` env or `$AU_STATE_DIR/ta-version`,
  never `current/TA_VERSION`. Correctly decoupled from the untrusted, rollback-mutable release tree.
  Both failure modes from round 3 (rollback erases it / CA-only bundle self-attests it) are closed.
  Verified via T44 + independent read.

### Still blocking

1. **[High] `aastar-node-updater.sh:100` (call site `:706`) — this commit's own fix for round-3 #2
   introduces a silent total-failure regression.** `load_policy_env()`'s last statement is
   `[ -f "$AU_ENV_FILE" ] && { set -a; . "$AU_ENV_FILE"; set +a; }` — with no env file present, the
   function returns 1. This commit hoists the call to be `main()`'s very first statement, unconditionally,
   before dispatch (previously only `cmd_check`/`cmd_apply`/`cmd_recovery` called it; `cmd_status` never
   did). Under the script's `set -euo pipefail`, that turns "no env file yet" into a silent `exit 1`
   before ANY subcommand runs — `check`, `apply`, `recovery`, and `status` alike. Not even a `die()`
   message; zero output.

   Mechanically reproduced (both before/after comparison and the `recovery` path specifically):
   ```
   $ env AU_ENV_FILE=<missing> bash <af0c4d9 script> status  → EXIT=0, prints state JSON
   $ env AU_ENV_FILE=<missing> bash <abe5c0a script> status  → EXIT=1, zero output
   ```
   Since `load_policy_env` pre-sets sane defaults (`AUTO_UPDATE="notify-only"`, etc.) *before* the
   conditional source, "no env file yet" is clearly an anticipated, supported state — not a
   misconfiguration. On any freshly-provisioned node without `updater.env` deployed yet, this means the
   periodic `check` timer silently no-ops forever, and **`recovery` — the boot-time crash-safety net this
   entire PR series exists to build — never runs**: it exits before reaching its own `rm -rf "$LOCK_DIR"`
   or `state_init` calls. The 80-test suite doesn't catch this because every test setup block
   pre-creates `$ROOT/updater.env`.
   Fix: end `load_policy_env` with an explicit `return 0`. Add a test that does NOT pre-create
   `updater.env` and asserts `status`/`check`/`recovery` still exit 0.

2. **[Medium] `aastar-node-updater.sh:206-209` — round-3 #4's lock TOCTOU is narrowed, not closed.**
   The new `mv "$LOCK_DIR" "$LOCK_DIR.stale.$$"` reclaim step only provides mutual exclusion *among
   racers that hit the reclaim branch*. It does not protect the original top-level `mkdir` winner: that
   process's final ownership check (`echo $$ > "$LOCK_DIR/pid"` then read back) is a plain write-then-read
   against a *path*, not a compare-and-swap against the specific directory *instance* it created. If a
   second process reclaims (mv's away) that directory in the window between the first process's `mkdir`
   and its `echo`, the first process ends up writing/reading against the second process's fresh
   directory — and depending on interleaving, both can independently observe their own pid on read-back.

   Mechanically reproduced: extracted `acquire_lock()`/`cleanup()`/`lock_contended()` verbatim into a
   standalone harness, raced two processes (role A = mkdir winner with an injected scheduling delay
   before its pid-write; role B = a late racer hitting the reclaim branch during that window) — **5/5
   runs, both A and B logged "HOLDS-LOCK" simultaneously.** This is exactly the invariant this PR's own
   manual `apply` (`LOCK_FATAL=1`) racing the periodic `check` timer depends on. T47 (this commit's new
   lock test) is sequential/single-process — it tests a pre-existing empty lock dir, not two live
   acquirers racing — and structurally cannot catch this class.
   Fix: replace the mkdir/stale/mv heuristic with a real mutex — `exec 9>"$AU_STATE_DIR/lock.f"; flock -n
   9 || lock_contended ...` (kernel-guaranteed atomic, tied to an fd/inode, released automatically on
   crash/SIGKILL, immune to rename). Add a genuinely concurrent test (two backgrounded acquirers with an
   injected delay), not another sequential one.

3. **[Medium] `aastar-node-updater.sh:363-367` (call site `:390`) — the alert-queue upgrade skips the
   single worst recovery outcome.** `rollback()`'s "no `last-good` available" branch (board effectively
   unrecoverable, "转 OOB 人工救板") still calls the old lossy `notify()` (`notify_send "$@" || true`,
   fire-and-forget) and then `return 1`. Because `cmd_recovery` calls `rollback "$target"` as a bare
   statement under `set -e`, that `return 1` aborts `cmd_recovery` immediately — before reaching this
   commit's own new `queue_notify` logic a few lines below (which is for the *different*,
   successful-rollback message anyway). Net effect: this commit fixed alert delivery for "board got
   bricked and auto-rolled-back successfully" but left "board is unrecoverable, needs OOB rescue" —
   arguably the more urgent case — on the exact lossy delivery path this whole PR series exists to
   eliminate. Reproduced: notify hook forced to fail (simulating no network at boot) → `EXIT=1`, no
   `pending-notify` file created, alert permanently lost.
   Fix: `notify_send error "$msg" || queue_notify error "$msg"` in the failure branch, and change
   `cmd_recovery`'s call to `rollback "$target" || true` (or handle the return code explicitly) so
   execution reaches the alert-delivery logic regardless of which branch `rollback` took.

### Found during full-diff scan — pre-existing, out of this diff's scope, but adjacent and real

- **[Medium] `aastar-node-updater.sh:360` — `rollback()`'s `last-good` fallback only checks
  `[ -L "$AU_ROOT/last-good" ]` (is-a-symlink), never that its target actually exists.** If `last-good`
  is dangling (its target release dir was removed — plausible in the exact scenario that lands here:
  filesystem damage/incomplete extraction after power loss), `rollback()` repoints `current` to the
  dangling target, clears `pending`, sets `state.current` to that version, and reports success via both
  `notify` calls — while the board now has **zero valid release on disk**. Mechanically reproduced:
  `last-good -> releases/0.1.0` with that directory missing → `recovery` exits 0, logs "已回滚到
  0.1.0" / "boot recovery:掉电中断已回滚到 0.1.0", state.json shows `current: "0.1.0"` — but
  `releases/0.1.0` doesn't exist. This is the exact scenario that should trigger the "转 OOB 人工救板"
  alert instead; right now it fires a false-positive success report. Not caused by this commit, but
  worth fixing in the same pass since #3 above already touches this function.
  Fix: `if [ -L "$AU_ROOT/last-good" ] && [ -d "$AU_ROOT/last-good/" ]; then` (trailing slash forces
  symlink resolution).

### Low / suggestions
- `queue_notify` (:79-80) writes tmp + `mv -f` with no `fsync`; if another power loss hits shortly after
  a recovery event (plausible — this *is* the crash-recovery path), the just-queued alert can be lost
  before `check` ever flushes it. `state_set` already does an explicit sync for durability — worth the
  same treatment here for consistency.
- The new `AU_TA_VERSION_FILE` override (`ta_version()`, :119) is undocumented anywhere
  (`updater.env.example`, README, tests) and, since `updater.env` is fully `set -a`-sourced, an operator
  could point it right back under `$AU_ROOT/`, silently reintroducing the exact release-tree coupling
  finding #1 (from round 3) closes. Either drop the override or reject paths under `$AU_ROOT/` inside
  `ta_version()`.
- `flush_pending_notify`'s `head -1 ... || echo warn` (:86) is dead code (the file was just `[ -f ]`
  tested); the real risk is an *empty* first line producing `lvl=""` passed straight to the notify hook.
  Worth a small whitelist check on `lvl` (R1b's instinct here was right, just under-justified).
- `acquire_lock`'s reclaim leaves `$LOCK_DIR.stale.$$` behind permanently if the process is killed
  between the `mv` and the `rm -rf`; `cmd_recovery`'s existing stale-lock cleanup could sweep
  `"$LOCK_DIR".stale.*` too.

## Issue compliance
No linked issue for this incremental commit; not applicable.

---
MODELS ACTUALLY RAN (round 4, incremental re-review of commit abe5c0a):
- R1 = deepseek-v4-flash (R1a full + R1b security, both real API calls against the incremental diff)
- R2 = REAL Opus (independent read of the diff, formed its own findings before seeing R1 or the
  orchestrator's lock-race evidence — independently arrived at the same TOCTOU, plus found the
  `load_policy_env`/`set -e` regression and the `rollback` failure-branch alert gap nobody else had yet)
- R3 = REAL Codex (`codex exec`, run directly via `scripts/codex_pk.sh` — not the Agent path — inside a
  fresh git worktree checked out at `abe5c0a`, given the 3 Medium+ claims and told to re-read the actual
  file rather than trust the prompt; independently re-derived all 3 from the real source, 0 misses)
- R4 = REAL Opus (second call: full round context → verdict + its own full-diff scan, which surfaced
  the dangling-`last-good` false-positive-success bug via its own mechanical repro)
- Orchestrator (this session, mechanical, not a model): ran the full 80-assertion suite (80/80 PASS);
  independently reproduced the `load_policy_env` regression, the lock TOCTOU (5/5 races), the
  `rollback` failure-branch alert loss, and the dangling-`last-good` false success — all 4 confirmed
  against the actual PR-head checkout at `~/Dev/aastar/AirAccount`, not simulated.

Coverage: no files omitted (3 changed files, all under token budget).
