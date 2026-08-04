## Verdict: REQUEST_CHANGES

Incremental re-review (previous round REQUEST_CHANGES at `b693c6d`; two fix commits since, current head `7288916`). Good progress — 3 of the 5 originally-blocking findings are genuinely fixed (npx wrong-package resolution, missing doc-8.json, wrong version.json comment wording). But the fixes for the flagship `dist-reproducible` guard introduced two new blockers, and one of them means the guard cannot pass on ANY machine but the author's, ever. All findings below were reproduced with real commands in isolated checkouts (a worktree + a fresh shallow clone mimicking a CI runner), independently by three passes (mechanical verification, an independent Opus strategic read, and a live Codex adversarial challenge that re-ran the verification commands itself) — not inferred from reading.

### 🔴 Blocking

1. **[Critical] The new "guard against missing new files" fix is blind to DELETED files — the exact mirror of the bug it was fixing.** `.github/workflows/verify.yml` now runs `git add -AN -- dist/` (intent-to-add) before `git diff --quiet -- dist/ ...`. `-AN` stages new AND deleted paths into the index, so the following `git diff` (worktree-vs-**index**, no `HEAD`) can no longer see anything the build removed — the index already reflects the deletion. Verified with an isolated 6-line repro: commit two files, delete one, `git add -AN -- dist/`, `git diff --quiet -- dist/` → exit 0 ("clean"); `git diff --quiet HEAD -- dist/` → exit 1 (correctly dirty). Net effect: if a rebuild legitimately drops a generated file (e.g. a task removed from `backlog/` so its exported json disappears), the guard now silently passes while the orphaned file stays committed and deployed — precisely the doc-8 "dangling reference shipped" failure mode this PR exists to prevent, inverted.
   Fix: keep `git add -AN`, but compare against `HEAD` instead of the index in all three diff invocations: `git diff --quiet HEAD -- dist/ ':(exclude)dist/api/version.json'` (catches new + deleted + modified in one check).

2. **[Critical] The committed, publicly-deployed `dist/` embeds the building machine's absolute filesystem path — pervasively — so it can never be reproduced by anyone else, regardless of any CLI-version pin.** `scripts/export-backlog.js` fetches `/api/status`, `/api/tasks`, etc. from the local `backlog browser` dev server verbatim, with zero sanitization, and writes the bytes straight into `dist/api/*.json`. Verified directly on the actual **committed** file at head `7288916`:
   ```
   $ git show 7288916:dist/api/tasks.json | grep -c '"filePath"'
   49
   $ git show 7288916:dist/api/tasks.json | grep -o '"filePath":"[^"]*"' | head -1
   "filePath":"/Users/jason/Dev/Brood/backlog/tasks/task-2 - ...md"
   $ git show 7288916:dist/api/status.json
   {"projectPath":"/Users/jason/Dev/Brood","rootConfigPath":"/Users/jason/Dev/Brood/backlog.config.yml",...}
   ```
   Rebuilding from a fresh clone elsewhere produced `/private/tmp/brood-pr36-shallow/...` instead — confirming the value is inherently machine-local, not stale content. Two consequences: (a) `deploy.yml` uploads `dist/` verbatim with no build step, so the author's home-directory path and local username are **live on the public site right now**; (b) the `dist-reproducible` guard is **unsatisfiable by construction** — it will report staleness on every single CI run forever, on any runner, no matter how correctly the CLI is pinned, because no other machine's absolute path will ever match the committed one.
   Fix: strip/normalize `filePath` / `projectPath` / `rootConfigPath` (and any other absolute-path field) to repo-relative — or drop them — before writing to `dist/`, then rebuild and recommit.

3. **[High] The pinned CLI version doesn't match the committed dist/ output, and the diff-exclusion for that field hides the mismatch instead of surfacing it.** CI pins `npm install --no-save backlog.md@1.49.3`; the committed `dist/api/version.json` (`git show 7288916:dist/api/version.json`) is `{"version":"1.45.0"}`. The exclusion comment claims "the pin above controls" this field staying in sync — it demonstrably doesn't, on this PR's own head.
   Fix: assert `version.json` equals the pinned version instead of excluding it from the diff; rebuild+recommit `dist/` with the pinned 1.49.3 output in this same PR.

4. **[Medium — carried over from the FIRST review round at `b693c6d`, still unaddressed after 2 fix commits]** `scripts/ci/check-task-yaml.py`'s `SCAN_DIRS = ["backlog/tasks", "backlog/docs", "backlog/decisions", "backlog/archive"]` omits `backlog/milestones`, which exists today with 4 files carrying live YAML frontmatter (`m-1`/`m-2`/`m-3`/`m-r`, including colon-bearing titles like `title: "Phase 1: Genesis Launch"` — currently quoted, one careless edit away from the exact class this guard exists to catch) and is actively read by the exporter ("Fetching individual milestones..." in the build log). Zero CI coverage today.
   Fix: add `"backlog/milestones"` to `SCAN_DIRS`.

### Confirmed but non-blocking

- **[Medium]** `withDeterministicConfig`'s regex (`export-backlog.js`) only matches an exact, unindented, comment-free `check_active_branches: true` line; if the key is absent/indented/commented, it silently no-ops with no warning, losing the determinism guarantee with no signal. Live config matches today, so not actively broken — fragile.
- **[Low-Medium]** `assertPortFree` has a TOCTOU window between probe and spawn (negligible — single-purpose CI script, no adversary); the spawn-error flag is checked only once at t=4s; `lsof`-derived PIDs are SIGTERM'd without verifying they belong to the expected process; `assertExportConsistent`'s file reads have no try/catch (raw ENOENT on missing file); `t.id === 'TASK-'` is a brittle blank-id match; the `process.kill` try/catch wraps only the loop's first iteration, so one already-exited PID (ESRCH) aborts reaping the rest.

### Missed by rounds 1-3, caught in final full-diff scan

- **[Medium]** `deploy.yml` is not actually gated by `verify.yml` — it triggers independently on `push: branches:[main]` with no `needs:`/`workflow_run:` dependency, so on a push to main both race and a **failing** `dist-reproducible` job does not stop a stale `dist/` from going live; it's only reported after the fact. This is the PR's own stated failure mode ("the fix looks merged but never reaches users") still structurally unenforced. Fix: gate `deploy.yml` on `verify.yml`'s success via `workflow_run`, or fold deploy into verify.yml as a dependent job.
- **[Medium]** `check-task-yaml.py`: a file that opens `---` but never closes it fails the frontmatter regex, falls into the "no frontmatter — prose doc, skip" exemption, and is silently never checked, while the script still reports "All frontmatter parses as valid YAML." Probe-verified: adding one unterminated-frontmatter file to `backlog/tasks/` left the checked count unchanged and exit 0. This produces the same blank-id/title export this guard exists to prevent. Fix: treat a `---`-opened-but-unclosed file as an error, not prose, inside `backlog/tasks`.
- **[Low]** `check-docs-gate.sh`'s pristine-template fixture is built with a conditional `[ -f ... ] && cp ...`; if a template is ever renamed/removed the assertion silently degrades to the weaker "empty dir rejected" case while still printing `ok`. All 7 templates present today (verified: 8/8 assertions pass at head) — not live, but should fail loudly on a missing template instead of degrading quietly.

### Verified working (credit due)

- Both new guards genuinely pass at head when run cleanly: `check-docs-gate.sh` 8/8 assertions, rc=0; `check-task-yaml.py` 58 files, rc=0.
- The `npx backlog` → `backlog.md@1.49.3` pin fix is mechanically correct: a fresh clone + pinned install resolves the right package and builds to completion (previously it silently fetched an unrelated name-squatted package and hung on every clean runner).
- `doc-8.json` is now committed and `docs.json`/`search.json` ids resolve.
- `assertPortFree`, the build-failure-vs-stale-dist split (`[ ! -s dist/index.html ]`), the port-reaping cleanup, the export-count consistency check, and `withDeterministicConfig`'s restore-on-`finally` all function correctly in a live rebuild.

### Assumptions
- Reviewed at head `7288916` — this PR's head moved twice during this review session (`b693c6d` → `0c27123` → `7288916`); confirmed unchanged via `gh pr view` immediately before posting.
- Used a git worktree + a fresh `git clone --depth 1` shallow clone (mimicking `actions/checkout`) rather than the shared local checkout, to get a clean, uncached environment for the reproducibility tests.
- No linked issue in the PR body — skipped the Issue-compliance section.

---
*Reviewed by clestons (pr-daemon-loop v4, 4-round, incremental re-review): DeepSeek R1a+R1b (dual-pass on the delta since last review) → Opus R2 (independent strategic read, reproduced the build itself, found the deletion-blindness + absolute-path-leak regressions) → Codex R3 (live PK challenge, ran its own verification commands in the checkout, confirmed all 5 findings + surfaced a 6th) → Opus R4 (final verdict + full-diff missed-finding scan, added 3 more: deploy.yml not gated on verify, unterminated frontmatter silently skipped, conditional template fixture).*
