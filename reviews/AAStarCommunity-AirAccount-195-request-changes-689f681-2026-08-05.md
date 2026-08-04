## Verdict: REQUEST_CHANGES (incremental re-review, head `689f681`, round 3)

**All 8 items from the last round are genuinely fixed** — I re-read each in the checked-out tree rather than trusting the commit message:

| Prior item | Status |
|---|---|
| [High] fresh deploy 226/NAMESPACE | ✅ README step 6 now `install -d -m0755 -o root -g root /var/lib/airaccount/updater` before the systemd step — and the note explaining why **not** to use `StateDirectory=` is exactly right |
| [Med] STUCK latch check-before-acquire race | ✅ re-checked after `mut_sem().acquire()`; `store(true)` happens before the permit drops, so there is no window |
| [Med] login-lockout race | ✅ `login_sem`→1 and the permit is taken **before** the lockout check, so the counter actually gates |
| [Low] read verbs queue behind a 180s apply | ✅ separate `read_sem(3)` |
| [Low] pubkey asserted for every verb | ✅ `case "$verb" in check\|apply)` |
| [Low] STUCK latch silent | ✅ `eprintln` added |
| [Low] tailscale probe hang / serve false-positive | ✅ `run_with_timeout(3s)`, funnel-only |
| [Low] `assert_secure` missing STATE_DIR/releases | ✅ added (but see Blocking 3) |

This is a careful fix pass and the security posture of the boundary itself is strong — `env -i`, fixed absolute paths, strict argv whitelist, exact Host/Origin, PHC + constant-time compare, fail-closed asserts. What blocks the round is **verb classification**: two places where the panel's idea of what a verb does disagrees with what the updater actually does.

### 🔴 Blocking

1. **[High] `kms/deploy/admin/src/helper.rs:36-37` — `check` is classified read-only, but it installs.** `is_mutating` matches only `apply|rollback`. Yet `kms/deploy/updater/aastar-node-updater.sh:704` — inside `cmd_check` — calls `download_verify_apply()`: a real root install (symlink swap + `restart_service` + state write). **This commit makes the misclassification structurally worse**, because it splits the old single permit into `mut_sem(1)` + `read_sem(3)`:
   - `check` now runs **concurrently with an in-flight `apply`** instead of serializing behind it;
   - `check` skips the STUCK latch on entry **and never sets it on timeout** — so after a timed-out check-triggered install (root updater possibly still alive and unkillable, which is the whole reason the latch exists), a subsequent `apply` passes its own latch check and starts a second root mutation. Two defense layers collapse to one, the updater's `flock`.
   - `main.rs:339-342` — `GET /api/candidates` calls `helper::run(&["check"])` behind session + Origin only: no CSRF, no 2FA, while `README:93` states apply/rollback require Telegram second-factor confirmation.

   Your own code already says this twice: `main.rs:178`'s route comment admits `有副作用(触发 helper check)`, and **this very commit** makes the shell assert the signing pubkey for `check|apply` — i.e. the shell layer treats `check` as signature-sensitive precisely *because it installs*, while the Rust layer treats it as read-only. Two layers, one verb, opposite classifications.
   Caveat, stated fairly: `cmd_check` only installs when a candidate is `auto_apply_allowed` and passes the policy gates — conditional, not unconditional. That bounds the exposure; it does not change the classification being wrong.
   **Fix:** add `check` to `is_mutating` (route it through `mut_sem` + the latch, and set the latch on its timeout), or split a genuinely read-only `list-candidates` verb out of the updater for the panel and keep every install path behind 2FA.

2. **[High] `kms/deploy/admin/airaccount-admin-helper:76-79` — the panel's rollback button is a silent no-op in the normal case.** `rollback` maps to `run_updater recovery`. But `cmd_recovery` is the *boot* recovery path, and `aastar-node-updater.sh:468` reads:
   ```bash
   if [ -z "$pending" ]; then log "无 pending,无需恢复"; return 0; fi
   ```
   After a **successful** apply, `:415` does `state_set previous "$prev" current "$ver" pending ""` — pending is empty. So the post-apply state, which is exactly when an operator wants to roll a bad release back, hits that early `return 0`. The helper exits 0, the panel reports success, and nothing happened — after the user burned a one-time Telegram 2FA code to get there. (`pending` is non-empty only mid-apply or after a power cut, which is what `recovery` was written for.)
   Second half of the same problem: even on the path where it *does* roll back, `cmd_recovery:465` pins `AU_RESTART_CMD="true"`. That is correct for the boot unit (`Before=kms-api`, restarting there would self-deadlock the boot transaction) but wrong for a panel-initiated rollback — the symlink flips while the bad `kms-api` process keeps serving.
   **Fix:** give the updater a real interactive `rollback` verb that rolls back to `state.previous` unconditionally and performs a normal restart, and point the helper at that. Keep `recovery` for the boot unit only.

3. **[Medium] `kms/deploy/admin/airaccount-admin-helper:39-41` — the `$STATE_DIR` guard doesn't match its own comment, and bricks every verb on already-deployed nodes.** The comment says `STATE_DIR/releases 存在才查(fresh box 首次 apply 前 releases 尚不存在)`, but only `/opt/airaccount/releases` gets the `[ -e ] &&` guard — `"$STATE_DIR"` sits in the unguarded `for` loop, and `assert_secure` exits 3 on a missing path (line 30).
   Reproduced both halves in a shell: the `[ -e X ] && cmd` pattern is safe under `set -euo pipefail` (does not exit), and the unguarded loop exits 3 with `helper: 缺文件/目录 /var/lib/airaccount/updater`.
   Impact is on the **upgrade** path, not fresh deploys: the updater's own `state_init` does `mkdir -p "$AU_STATE_DIR"`, so its contract is "this may not exist yet", and the systemd unit binds the **parent** (`ReadWritePaths=… /var/lib/airaccount`) — so the service starts cleanly and *then* every verb, including read-only `status`, dies with exit 3 until an operator manually creates the directory. This is the same failure class as the pubkey item this commit just fixed (`别因缺 pubkey 让整个面板挂`).
   **Fix:** move `"$STATE_DIR"` behind the same `[ -e ] &&` guard, and add `/var/lib/airaccount` to the unguarded loop instead (the parent is guaranteed to exist because `ReadWritePaths` binds it) — that closes the item below at the same time.

### Confirmed non-blocking

- **[Low] `airaccount-admin-helper:40`** — the trust-root loop asserts `$STATE_DIR` but not its parent `/var/lib/airaccount`, even though the same loop asserts `/opt/airaccount` precisely because it is the parent of `updater/`. A group/other-writable parent would let a non-root user rename or replace `updater/` wholesale and thereby control `state.json`, which is the rollback target.
- **[Low] `src/security.rs:90`** — `s.contains(&format!(":{needle_port}"))` is a substring match, so checking port 80 false-positives on a funnel listing that mentions `:8080` and refuses startup. Same pattern pre-exists at `:69` and `:80`. Match the port as a whole field.
- **[Low] `src/security.rs:99-111`** — `run_with_timeout`'s detached thread is never joined; on timeout it and its `tailscale` child outlive the call. Startup-only and at most one call, so acceptable as-is — a comment noting the deliberate leak would close it.

### Rejected

- **DeepSeek R1b: "the STUCK re-check after permit acquisition may still miss a concurrent apply"** — the post-acquire re-check *is* the fix, and `mut_sem` permit=1 makes a second in-flight mutating call impossible.
- **DeepSeek R1b: "the latch should be set on all error paths, not just timeout"** — by design. The latch means *a root child may still be alive and unkillable*, which only the timeout path implies; non-timeout errors mean the child already exited, and latching there would wedge the panel on transient failures.
- **My own open question, "rollback should assert the pubkey"** — no. `cmd_recovery` only swaps the symlink to an already-present `releases/$target` and never calls `verify_sig`; `cmd_status` is `state_init; cat "$STATE_FILE"`. The `case "$verb" in check|apply)` split is correct.
- **My own open question, "login_sem=1 is a new DoS"** — no. After 8 failures the lockout arms and queued requests return 429 before reaching argon2, so the queue self-drains.
- **My own hypothesis, "CSRF-on-GET reaches /api/candidates cross-site"** — no. The session cookie is `SameSite=Strict` (`main.rs:314`) and `host_allowed("")` returns false. Finding 1 is an authorization-design gap, not a cross-site one.

### Suggestions

- Once `check` is reclassified as mutating, the `read_sem(3)` split actually achieves its stated goal. As written, `status` shares `read_sem` with the 180s network+install `check`, so three concurrent `/api/candidates` still hang the panel — the exact failure the split was introduced to prevent.
- The new README step fixes fresh deploys but not nodes already in the field; one line telling existing operators to run the same `install -d` before upgrading would prevent Blocking 3 from biting in production.
- `is_mutating` keying off argv strings in two independent places (Rust `matches!` and the shell `case`) is what let the two layers disagree in the first place. A single shared verb table carrying an explicit `mutating: bool` would turn the next divergence into a compile error.

### Assumptions

- Reviewed in a dedicated worktree at this PR's exact head `689f681`; nothing in the PR branch was modified.
- Incremental scope is `5e53000..689f681` (1 commit), but Blocking 2 was found by following `rollback` out of that range into `cmd_recovery` — cross-layer semantics are in scope even when the file isn't in the diff.
- No linked issue in the PR body — Issue-compliance section skipped.

---
*Reviewed by clestons (`$pr` v4, 4-round, incremental `5e53000`→`689f681`): DeepSeek R1a+R1b (`deepseek-v4-flash`; 4 findings → 1 Low survived, 2 rejected with reasons above) → Sonnet mechanical verification (re-read all 8 prior items in the checked-out tree; reproduced the `set -euo pipefail` / `assert_secure` behaviour in a shell; traced `check`→`cmd_check`→`download_verify_apply` and `rollback`→`cmd_recovery` across the Rust/shell/updater layers) → Opus R2 (independent; found the `is_mutating` High and the missing-parent Low before seeing my notes, and refuted two of my own hypotheses with file evidence) → Codex R3 (`gpt-5.5`, in the same worktree; CONFIRMED all 5, zero challenges, no additional issue in range) → Opus R4 (final verdict + full-tree scan; found the rollback-no-op High that every earlier round missed by staying inside the incremental range).*
