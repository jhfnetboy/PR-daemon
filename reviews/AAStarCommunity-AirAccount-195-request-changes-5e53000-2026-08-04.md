## v4 pipeline review — AAStarCommunity/AirAccount#195 (4-round, incremental re-review)

Prior review (611d98d) gave **REQUEST_CHANGES** with 5 Blocking + 5 non-blocking findings. This
round reviews the single fix commit `5e53000` ("折入 pr-daemon v4 评审 —— 5 Blocking 全修 +
DoS/低危收口"), which claims to address all 10. It's a genuinely thorough, high-quality fix pass —
3 of 5 Blocking items are fully fixed and verified (including compiling/running the test suite),
4 of 6 non-blocking items fully fixed. But 2 issues remain: one prior Blocking item is only
partially closed (a fresh deployment can now fail to *start* the service at all — regression from
"apply fails" to "service won't boot"), and a new concurrency race in the fix itself lets the
exact scenario one of the other fixes targets slip through.

**Verdict: REQUEST_CHANGES**

### Blocking

1. **[High] `kms/deploy/admin/airaccount-admin.service:41`** — `ReadWritePaths=/opt/airaccount
   /var/lib/airaccount` has no `-` prefix, and `/var/lib/airaccount` does not exist on a fresh
   box: the README's deploy steps only `install -d /etc/airaccount`; `/opt/airaccount` gets
   created incidentally by step 2's `install -D`; nothing creates `/var/lib/airaccount`. The
   updater's own `mkdir -p "$AU_STATE_DIR"` only runs when the updater is actually invoked, which
   is *after* systemd has already validated the unit's sandbox at start time. `systemctl enable
   --now airaccount-admin` will fail with 226/NAMESPACE on a fresh deploy. This is a regression
   in kind, not degree — the prior fix (removing `/opt/airaccount` from `ReadOnlyPaths`, correctly
   closing the original EROFS-on-apply Blocking item) traded a "first apply fails" bug for a
   "service never starts" bug, and — like all 4 of the original directory/permission Blocking
   items — this is invisible to the in-process test suite; it only lives in README text + the
   systemd unit.
   Fix: add `install -d -m0755 -o root -g root /var/lib/airaccount/updater` to the README before
   the step that starts the service. **Do NOT** reach for `StateDirectory=` as a shortcut —
   systemd would create and `chown` that path to the service's own `User=`/`Group=`
   (`airaccount-admin`), which recreates exactly the "web-service-user owns a trust-relevant
   directory" class of bug this PR's original Critical finding was about (see REJECTED below for
   why that specific directory is *currently* safe only because it stays root-owned).

2. **[Medium] `kms/deploy/admin/src/helper.rs:47-51`** — the new `helper_stuck` latch (added to
   fix the prior "timeout releases permit → retry starts a second concurrent apply" Blocking
   item) is checked **before** `helper_sem().acquire().await`, not after. Sequence: request A
   holds the permit(1) and is mid-flight; request B (a second mutating call) passes the
   "not-stuck" check and then blocks waiting for the permit; A times out at 180s, sets the latch,
   and releases its permit; B — already past its stuck-check — immediately proceeds to
   `Command::new("sudo")` with a now-stale "not stuck" verdict. This is precisely the race the
   latch was introduced to close. Codex independently confirmed this by reading the checked-out
   file (see pipeline notes).
   Fix: re-check `helper_stuck()` immediately after `acquire()` succeeds, before spawning.

### Confirmed non-blocking (fix before increment 2)

- **[Medium]** `kms/deploy/admin/src/main.rs:280-295` — the same check-before-await-queue-point
  shape as Blocking#2: login lockout is checked under the state mutex, the mutex is dropped, and
  only *after* argon2 verification (gated by a width-2 semaphore) does the code re-acquire the
  mutex to update the failure counter. A concurrent burst of requests can all pass the initial
  "not locked" check before any of them increments the counter — the lockout mainly throttles
  requests that arrive *after* the lock is already set, not a genuine flood. Steady-state
  throughput is closer to the semaphore's raw argon2 throughput (~40 verifications/sec) than to
  "8 attempts per 60s". Also global (not per-source): any peer that can reach the bound port can
  keep the real admin locked out indefinitely by repeatedly failing. R1a and R1b both
  independently flagged this before R1b degenerated into repetition; Codex confirmed it with line
  citations and the sharper "attacker in-flight depth, not permit width" framing.
- **[Low]** `kms/deploy/admin/airaccount-admin-helper:44` — `assert_secure`'s directory whitelist
  still misses `STATE_DIR` (`/var/lib/airaccount/updater`) and `/opt/airaccount/releases` — the
  same two paths Blocking#1 above is about. Not currently exploitable (see REJECTED), but it's
  the safety net for Blocking#1's fix and should cover the same paths, especially since the fix
  for #1 touches exactly this trust boundary.
- **[Low]** `kms/deploy/admin/src/helper.rs:100` — permit reduced to 1 means read verbs
  (`status`/`candidates`) now also queue behind an in-flight `apply` (up to 180s), with no
  client-side timeout — the panel can appear to hang for the full duration with no visible cause.
  Consider a separate semaphore for read verbs.
- **[Low]** `kms/deploy/admin/airaccount-admin-helper:47` — `assert_secure "$PUBKEY"` now runs
  unconditionally for every verb including read-only `status`/`check`, but the README's deploy
  steps never install `updater-pubkey.pub` — a node that only ran the admin console setup (not
  the separate updater deploy docs) would have its entire panel fail, not just apply/rollback.
- **[Low]** `kms/deploy/admin/src/helper.rs:68-71` — setting the stuck latch produces no
  journal/stderr line; an operator only discovers it via the next apply's HTTP error message.
- **[Low]** `kms/deploy/admin/src/security.rs:86-96` — the new `tailscale serve/funnel` check has
  no timeout on the `tailscale` subprocess call (could hang the startup self-check if tailscaled
  is unresponsive), and matching on the `"funnel"` substring in `serve status` output could
  false-positive on a legitimate tailnet-only `serve` deployment. Also: as a non-root process, the
  command will likely just fail/return nothing on most distros and be silently skipped, same class
  of blind spot as the pre-existing `/root/.cloudflared` gap this fix was meant to help with.

### Confirmed as false positive after Codex challenge (raised by R2, refuted with concrete evidence)

- "The new `ReadWritePaths=/var/lib/airaccount` lets the web-service user write `state.json`
  directly, resetting the anti-rollback `seen_metadata_version` counter to replay an old
  legitimately-signed manifest" — **refuted**: `ReadWritePaths=` only controls the systemd mount
  namespace's RO/RW view: it does not override Unix DAC. The state directory and file are created
  by the *root*-run updater via plain `mkdir -p`/`mv -f` (default umask), so they end up
  root-owned and not group/other-writable — `airaccount-admin` cannot write there today despite
  the sandbox now permitting it at the mount level. The underlying risk (`state.json` is unsigned,
  and its `seen_metadata_version` is the sole anti-rollback gate per
  `aastar-node-updater.sh:527-534`) is real, but this commit does not make it reachable — the
  precondition would be a *separate* directory-ownership bug, which is exactly what Blocking#1's
  "don't use `StateDirectory=`" caveat above is warning against introducing.

### Non-blocking suggestions

- The same check-before-await-queue-point bug shape appears twice in this one commit (login
  lockout, helper stuck-latch). Worth a standing rule for this crate: any "reject if state X" gate
  followed by an `.await` queuing point must re-check state after the wait, not just before it.
  The new `login_lockout_after_repeated_fails` test is purely sequential and would not have caught
  either race — same lesson as this repo's prior singleton/concurrent-invocation postmortems.
- 4 of the 5 original Blocking items (directory ownership, `ReadWritePaths`, `assert_secure`
  coverage, helper serialization) are entirely invisible to the in-process test suite — they only
  live in README text, the systemd unit, and shell scripts, and Blocking#1 above is a direct
  consequence. A container-based smoke test that follows the README's deploy steps and does
  `systemctl start` would catch most of these for less cost than more in-process unit tests.
- `hash-password` has no minimum length/strength check, and this is the single highest-privilege
  credential in the system; combined with the login-lockout race above, a weak password is
  realistically enumerable within a tailnet. Consider enforcing a minimum length in `hash-password`
  itself.

## Assumptions

None — PR open, head matches `5e53000c5efa7abd60a4ab449c210d76c6c6e1f7`, confirmed against the
incremental diff since the prior review (611d98d). No linked issue to check DoD against.

---
**Pipeline: R1a(DeepSeek-v4-flash full) + R1b(DeepSeek-v4-flash security, parallel, on the
incremental diff since 611d98d) → R2(Opus, independent read + actually ran `cargo test` in a
clean worktree, 26/26 passed) → R3(Codex, isolated worktree checked out at PR head, targeted PK
on R2's 4 most severe new findings) → R4(Opus, full round context, missed-finding scan).**
R1b degenerated into a repetition loop on both the original full-diff pass and this incremental
pass (known flash reliability issue), but in both cases independently corroborated a real finding
before doing so. R3/Codex confirmed 3 of 4 challenged findings with line citations and refuted the
4th with concrete counter-evidence (DAC vs. systemd `ReadWritePaths`), which R4 independently
verified by reading the cited files before accepting — and in doing so caught that the "obvious"
fix for Blocking#1 (`StateDirectory=`) would silently reintroduce the exact precondition Codex's
refutation depends on.
