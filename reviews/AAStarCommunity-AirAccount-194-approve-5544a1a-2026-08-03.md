## PR-Daemon v4 review — incremental (head `485fd30` → `5544a1a`)

**Verdict: APPROVE**

This commit is the author's response to the prior 8-round review's 2 Blocking + 5 Should/Low findings on the flock lock-migration work. Both Blocking fixes were mechanically re-verified, not just read:

- **Blocking #1 (stderr永久重定向)**: confirmed with an isolated bash repro that `{ exec 9>"$f"; } 2>/dev/null` (braced) scopes the suppression to just that exec call, while the old unbraced `exec 9>"$f" 2>/dev/null` permanently kills all subsequent `stderr` in the shell. Reproduced both forms directly.
- **Blocking #2 (跨版本迁移防护)**: manually simulated end-to-end against the real script — a legacy symlink lock held by a genuinely-alive PID correctly makes a flock-acquiring new instance defer; a legacy lock pointing at a dead PID correctly does **not** block. Both edge cases work as claimed.
- **Test suite**: ran locally. Without a real `flock` binary: 102 PASS / 0 FAIL / 3 SKIP (matches the commit message). After `brew install flock`: **105 PASS / 0 FAIL / 0 SKIP** — T57/T58 now exercise the real flock path (not skip) and pass.

### Confirmed findings (non-blocking)

- **[Should]** `aastar-node-updater.sh:246-255` — the migration guard is one-directional: a flock-holding new instance defers to a *live* legacy lock, but never stakes its own claim on the legacy lock face. If the new-version instance starts first and an old-version instance starts later, the old instance won't see the flock and could still double-hold. Real-world reachability is low (release tarballs don't ship the updater script itself, so an old-version script reappearing while a new-version instance is running isn't a normal path) — but closing it is a one-liner: after acquiring flock, also `ln -s "$$" "$LOCK_LINK" 2>/dev/null || true`. `cleanup()` already handles releasing it (`readlink==$$ → rm -f`), no further change needed there.
- **[Low]** `aastar-node-updater.sh:248-255` — the flock branch only *checks* the legacy lock face, never reclaims a stale one (the symlink-CAS fallback path has `reclaim_stale_lock`; flock path doesn't). If a crashed old-version instance leaves a dead-PID-adjacent symlink whose PID gets reused by an unrelated process, `lock_holder_alive` reads it as alive → every check silently `exit 0`s (systemd sees success) → the node stops receiving updates for up to `LOCK_STALE_SECS` (default 24h) with nothing but a `warn` line in the journal.
- **[Low]** `test-updater.sh:1046` — T57 syncs with the lock-holding subshell via a fixed `sleep 0.5` rather than confirming the holder actually has the flock; under load this could flake (failure direction is a false FAIL, not a false PASS/vacuous-pass, so Low not Should).
- **[Low]** `test-updater.sh` (whole suite, 106 cases) — not referenced by any `.github/workflows/*.yml`. Combined with this commit's new SKIP semantics, the flock production path currently has **zero automated coverage** — this lock has been fixed across 8 review rounds purely by manual review catching bash semantics gotchas (permanent stderr redirect, `kill -0 0`, `ln` landing in a directory, `mv` preemption windows). Wiring this suite into CI (a Linux runner has `flock` natively, so T57/T58 stop skipping) would likely prevent more regressions than any remaining line-level finding here.

### Rejected (R1 DeepSeek false positives, verified)

- Suggestion to revert `{ exec 9>&-; } 2>/dev/null` to the unbraced form — that's re-introducing the exact bug this commit fixes (mechanically confirmed above).
- Two "unvalidated pid" findings — `lock_holder_alive()`'s first line (`case "$1" in ''|*[!0-9]*|0*) return 1 ;; esac`) already rejects empty/non-numeric/leading-zero input; no gap at the call sites.

### Suggestions (non-blocking)

- Add the one-line `ln -s "$$" "$LOCK_LINK"` to fully close the migration-guard direction, rather than leaving it for "a few rounds until the old version disappears."
- Longer term: the flock/symlink-CAS dual-backend (plus the split-brain die + `AU_TEST_MODE` escape hatch + migration guard) is accumulating debt to bridge a transition. Production is all Linux — consider eventually dropping the symlink-CAS fallback and having tests use real `flock` directly.

---
**Pipeline: 4-round** (concurrency/lock-migration code — security-sensitive hard rule, no downgrade despite the small 128-line diff)
- R1a (DeepSeek v4-flash, full): 2 Low findings, both false positives on independent verification.
- R1b (DeepSeek v4-flash, security): 1 Medium + 1 Low; the Medium (migration TOCTOU) pointed at something real but the suggested "fix" was already the current code — R2 reframed it more precisely as the one-directional gap above; the Low was a false positive (same as R1a's).
- R2 (Opus, independent strategic read): found the one-directional migration gap independently before seeing R1, rejected all 4 R1 findings with reasoning, flagged CI-coverage gap.
- R3 (Codex PK): **skipped** — post-R2 gate found no Medium+ findings surviving (all Should/Low).
- R4 (Opus, final verdict + full-diff missed-scan): confirmed R2's findings, additionally caught the stale-reclaim gap in the flock branch that R2 missed, and re-verified R2's own "T57 lacks a positive control" Low finding was actually wrong (added a positive-control assertion in a scratch worktree, got 106/106 PASS, then removed the worktree).
