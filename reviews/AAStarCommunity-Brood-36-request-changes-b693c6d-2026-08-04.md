## Verdict: REQUEST_CHANGES

This PR's stated goal is to turn three previously human-caught failure modes into CI-mechanical guards. Good instinct and well-documented intent — but the guards themselves have real, independently-verified gaps, and one of them ships a live instance of the exact bug class it's meant to prevent (a doc referenced in the search/docs index whose file was never committed). All findings below were reproduced with real commands in a worktree at this PR's head commit (`b693c6d5`), not inferred from reading alone.

### 🔴 Blocking

1. **[Critical] `.github/workflows/verify.yml` `dist-reproducible` job — `npx backlog` resolves to the WRONG npm package on any clean CI runner.**
   `scripts/export-backlog.js:94` runs `npx backlog browser --no-open -p <port>`. The actual CLI this repo builds with is published as **`backlog.md`** (confirmed: `npm view backlog.md` → v1.49.3, "Backlog.md"). The bare name **`backlog`** is a *different, unrelated* npm package (confirmed via `npm view backlog` → v1.4.56, "Orchestrator for AI coding agents"). Locally this is masked because `backlog.md` happens to be globally installed with its bin named `backlog` — but a fresh GitHub Actions runner has no such global install, so `npx backlog` fetches the wrong package from the registry. Verified: `npx --yes backlog@1.4.56 browser --no-open -p 8499` → `error: unknown option '--no-open'`. With `stdio:'ignore'` in the spawn call, this error is swallowed silently; the script waits 4s, then every subsequent `fetch('http://localhost:<port>/...')` throws.
   **Result: this job fails on 100% of CI runs**, for a reason that has nothing to do with whether dist/ is actually stale.
   Fix: pin `"backlog.md": "1.45.0"` as an explicit `devDependency`, add `npm ci` before build, and invoke the local bin (`./node_modules/.bin/backlog` or `npx --no-install backlog`) so a registry name-squat can never execute in its place.

2. **[High] `dist/api/docs.json` + `dist/api/search.json` reference `doc-8`, but `dist/api/docs/doc-8.json` was never committed.** Both index files in this PR's own diff add a `doc-8` entry, but `git ls-tree` on this PR's head shows only `dist/api/docs/{doc-1,doc-6,doc-7}.json` under `dist/api/docs/`. `deploy.yml` uploads `dist/` verbatim with no build step, and `dist/index.html` does `fetch(`…/api/docs/${id}`)` with `if (!res.ok) throw`. Merging as-is ships a docs index + search entry that hard-errors when clicked — this is exactly failure mode #1 from the PR description, shipped *inside* the PR that adds the guard against it.
   Fix: commit `dist/api/docs/doc-8.json`.

3. **[High] The new `dist-reproducible` gate is blind to newly-created (untracked) files — proven on this PR's own head commit.** `git diff --quiet -- dist/ ':(exclude)dist/api/version.json'` only compares files git already tracks; a file a fresh build *creates* is untracked and invisible to `git diff`. Reproduced independently three times (by two review rounds + Codex): running `npm run build` at this exact commit, then `git status --porcelain -uall -- dist/`, prints `?? dist/api/docs/doc-8.json` — yet the `git diff --quiet` check still reports clean (rc=0). So right now, on this PR's own commit, the flagship guard is green despite finding #2 above being real. It would not have caught its own PR's bug.
   Fix: `git add -AN -- dist/` (intent-to-add) before the diff check, or check `git status --porcelain -uall -- dist/` instead of `git diff --quiet`.

4. **[Medium] The `version.json` exclusion's stated rationale is factually wrong, and it silences the one canary for CLI drift.** The workflow comment says "the export writes a build timestamp into version.json on every run" — but `dist/api/version.json` contains only `{"version":"1.45.0"}` (the backlog.md CLI version), and a repo-wide grep for `version.json` writers finds nothing outside the workflow file itself; nothing writes a timestamp there. Excluding this file from the diff removes the only field that would flag "the CLI that built this dist ≠ the CLI running now" — i.e. the exact 2026-05-12 silent-patch-failure class the PR's own header cites as motivation.
   Fix: drop the exclusion (once the CLI is pinned per #1, this file is stable across builds).

5. **[Medium] `scripts/ci/check-task-yaml.py` `SCAN_DIRS` omits 3 directories the exporter actually reads frontmatter from**: `backlog/milestones` (**4 files with frontmatter today**, exported via `export-backlog.js`), `backlog/completed`, and `backlog/drafts` (both 0 files today but live code paths in the exporter — `export-backlog.js:333-336,353`). An unquoted-colon title in `backlog/milestones/*.md` corrupts that endpoint identically to the incident this PR fixes, and this new gate would not catch it.
   Fix: add all three to `SCAN_DIRS`.

### Confirmed but non-blocking

- **[Medium] `scripts/ci/check-docs-gate.sh:28-30`** — templates are copied into the test fixture conditionally (`[ -f ... ] && cp ...`) with no assertion any were actually found. If the templates directory is ever moved/renamed, the fixture silently stays empty and the "pristine templates rejected" assertions still pass — but only because they've degenerated into re-testing the already-covered empty-dir case, while the script still reports "the gate rejects... blank templates." Latent today (templates dir exists with all 7 files), not live.
- **[Low]** `check-task-yaml.py` has no floor on `checked` — rename a scan dir and it prints "Checked 0 files, all valid" and exits 0. Also: the frontmatter regex (`^---\n`) requires LF, so a CRLF-committed file silently falls into "no frontmatter, skip" instead of being validated; and it only validates that YAML *parses*, not that `title` is non-empty, so `title:` (blank) still ships the blank record this PR exists to prevent.
- **[Low]** `verify.yml`'s failure message says `pnpm run build` but the job itself runs `npm run build`. Harmless today (package.json has zero dependencies, so both produce identical output) — but once `backlog.md` is pinned per #1, the two package managers can diverge, so worth fixing in the same pass.
- **[Low]** The header comment "runs on... pushes to main so a direct push can't bypass it either" overstates: a push-triggered run fires *after* the push already landed on main — it detects, it doesn't prevent, without branch protection separately marking these as required checks.
- **[Low]** `on: pull_request` + `push: [main]` both fire for same-repo PR branches once merged, double-running all three jobs on the merge commit — minor CI-minutes waste, not correctness.

### Verified working (credit where due)

- `scripts/ci/check-task-yaml.py` runs clean at head: "Checked frontmatter in 58 file(s). All frontmatter parses as valid YAML." All 10 backlog task-title quoting fixes in this PR are correct, and the gate does catch the class of bug it targets (verified by re-running it for real).
- `scripts/ci/check-docs-gate.sh`'s 8 assertions against the actual `check-docs.sh` gate all pass and are logically sound against the real gate's threshold-validation code (`case`-based non-numeric/zero/empty handling) — read both sides and traced the bash semantics; they match.

### Assumptions
- Reviewed via `gh pr diff` + a git worktree checked out at the PR head commit (`b693c6d5`) rather than the shared local `~/Dev/aastar/Brood` checkout, which currently has ~60 unrelated staged files on `main` (pre-existing local WIP, untouched by this review).
- No linked issue in the PR body — skipped the Issue-compliance section.

---
*Reviewed by clestons (pr-daemon-loop v4, 4-round): DeepSeek R1a+R1b (dual-pass) → Opus R2 (independent strategic read) → Codex R3 (live PK challenge, ran commands itself in-worktree, confirmed all R2 findings + found one more) → Opus R4 (final verdict + full-diff missed-finding scan, found 2 additional High + 1 Medium not caught by R1-R3).*
