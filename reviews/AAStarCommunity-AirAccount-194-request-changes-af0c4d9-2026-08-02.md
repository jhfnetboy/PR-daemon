## 🤖 Re-review of the fix commit (round 3) — DeepSeek R1 + Opus R2/R4 + Codex R3 PK

VERDICT: REQUEST_CHANGES

This is a re-review of commit `af0c4d9`, which claims to fix all 5 findings from the prior round's
CHANGES_REQUESTED review. **2 of 5 are genuinely fixed and verified; 2 of 5 are only half-fixed; 1 of 5
(TA version compat gate) fixed the symptom but reintroduced the same class of bug via a new source.**
One additional pre-existing issue (lock TOCTOU) was found and mechanically reproduced during this round.

### Genuinely fixed (verified — full 72-test suite passes, plus manual repro of each)
- ✅ **#1 lock leak** — `cleanup()` now does a pid-owned `rm -rf` instead of `rmdir`; verified across
  success/die/stale-lock paths.
- ✅ **#5 sha256 case-sensitivity** — both sides normalized to lowercase before compare; verified.

### Still blocking

1. **[Medium] `aastar-node-updater.sh:95` — TA_VERSION compat-gate source is coupled to the CA release
   lifecycle it's supposed to be independent of.** `ta_version()`'s file fallback reads
   `$AU_ROOT/current/TA_VERSION`, but `current` is a symlink into `releases/<ver>/` — the exact tree
   `download_verify_apply()` populates from the (content-untrusted) release tarball, and that
   `rollback()` repoints on every rollback. Two reproduced failure modes:
   - (a) Following the script's own comment ("installer/OOB 写"), placing `TA_VERSION` into
     `releases/<ver>/` makes it vanish the instant `current` repoints to a different release — the
     compat gate permanently fail-closes again after the very next `apply`.
   - (b) A CA-only bundle can itself carry a `TA_VERSION` file, letting the CA release self-attest a TA
     version that was never actually flashed — reintroducing the exact fail-open this commit exists to
     close, via a different door.
   Fix: read TA version from a location outside the release tree entirely (e.g.
   `$AU_STATE_DIR/ta-version` or an OOB/installer-owned `/etc/airaccount/ta-version`); never from
   anything under `current/`. Update the die message + `updater.env.example` to point there.

2. **[Medium] `aastar-node-updater.sh:586-588,666` — `cmd_apply`/`main()` still `die()` before
   `load_policy_env`.** `cmd_apply`'s two early `die`s (missing/invalid version arg) and 3 of `main()`'s
   own argv-validation `die`s fire before env is sourced — no Telegram creds, so those alerts are
   silent. Same root cause as round-2 finding #2, only closed for `cmd_check`. Fix: call
   `load_policy_env` as the first statement of `main()`, before dispatch/argv validation.

3. **[Medium] `aastar-node-updater.sh:345` + `airaccount-updater-recovery.service` +
   `notify-telegram.sh` — boot-recovery alert still structurally can't reach Telegram.**
   `cmd_recovery` now sources env (creds present), but the unit is `DefaultDependencies=no` /
   `After=local-fs.target` / `WantedBy=sysinit.target` — it runs before any network unit.
   `notify-telegram.sh` does a one-shot `curl` with no retry/queue, exits 3 on failure, and `notify()`'s
   `|| true` swallows it silently. The single most important alert ("board got bricked and
   auto-rolled-back") still can't be delivered — round-2 finding #3 is only half-fixed. Fix: persist the
   alert (e.g. write to `$AU_STATE_DIR/pending-notify`) and flush it from a unit that runs after
   `network-online.target`, or from the next `check` cycle.

### Additional finding — pre-existing, but directly relevant to this PR's own invariant

4. **[Medium] `acquire_lock()` (~line 158) — TOCTOU between `mkdir "$LOCK_DIR"` succeeding and the pid
   file being written.** If a second process runs `acquire_lock` in that gap, it sees the dir exists but
   the pid file is empty → treats it as an unowned stale lock → `rm -rf` + re-`mkdir`s it → both
   processes fall through believing they hold the exclusive lock. **Mechanically reproduced** (isolated
   repro of the exact gap): both racers logged "HOLDS LOCK" concurrently. This line isn't touched by
   this diff, but this PR is what makes the race consequential — it added the manual `apply` path with
   `LOCK_FATAL=1` racing against the periodic `check` timer, which is exactly the invariant round-2
   finding #2 was fixing ("apply must hard-fail on contention, not silently no-op"). Right now two
   concurrent invocations can both proceed past the guard instead of one blocking. Fix: reclaim
   atomically (`mv "$LOCK_DIR" "$LOCK_DIR.stale.$$" 2>/dev/null` — only one racer succeeds — then
   `mkdir`), and re-read `$LOCK_DIR/pid` after writing to confirm it's still `$$`.

### Low / suggestions
- `ta_version()`'s `tr -d '[:space:]v'` strips every `v` anywhere in the string, not just a leading
  prefix; combined with no whitespace-trim on the `AU_TA_VERSION` env branch, a trailing space in
  `updater.env` silently becomes a hard "TA 版本未知" reject.
- `AU_TA_VERSION` is now a hard prerequisite for any release declaring `requires_ta_version` — no board
  in the field currently has it set. Document this as a release prerequisite (README + release
  checklist), or the first such release will look like the updater broke fleet-wide.
- New tests (T40–T43) don't cover the `current/TA_VERSION` file-fallback path or `decide_action`'s auto
  (non-`apply`-command) path for the compat gate — only the `AU_TA_VERSION` env branch under explicit
  `apply`.
- `trap cleanup EXIT` doesn't fire on `SIGTERM` (systemd stop) — `WORK` tmpdirs can leak. `trap cleanup
  EXIT INT TERM` is a one-line fix (the lock itself already recovers via the stale-lock path).

## Issue compliance
No linked issue found in the PR title/body for this incremental commit; not applicable.

---
MODELS ACTUALLY RAN (round 3, incremental re-review of commit af0c4d9):
- R1 = deepseek-v4-flash (R1a full + R1b security, both real API calls, fed the incremental diff + a
  verbatim context appendix of the touched functions)
- R2 = REAL Opus (independent read of the diff before seeing R1; then ran the actual 72-test suite —
  72 PASS / 0 FAIL — plus 6 hand-built reproductions against the real script in a sandboxed tmp state
  dir)
- R3 = REAL Codex (`codex exec` gpt-5.5, run directly via `scripts/codex_pk.sh` against the actual
  PR-head checkout on disk, given verbatim source hunks for all 3 Medium+ findings; it independently
  pulled `airaccount-updater.service` and `README.md` beyond what was pasted to verify claims)
- R4 = REAL Opus (second call: full diff + all round context → verdict + missed-finding scan; found the
  `acquire_lock` TOCTOU, independently mechanically verified by the orchestrator afterward)

Coverage: no files omitted (3 changed files, all under token budget).
