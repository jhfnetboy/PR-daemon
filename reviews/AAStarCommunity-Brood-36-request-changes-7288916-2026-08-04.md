## Verdict: REQUEST_CHANGES (incremental re-review, head `72889168`)

Good progress — 4 of the 5 blocking findings from the last round are genuinely fixed (verified by rebuilding the project twice in a clean worktree at this exact commit). But the flagship guard this PR exists to add — "`dist/` is reproducible from source" — is **structurally guaranteed to never pass**, on this PR's own head commit or any future one, for a reason none of the fix commits touched. There's also a real (if minor) information-disclosure bug shipped in the same `dist/`.

All findings below were reproduced with real commands (`npm install backlog.md@1.49.3`, `npm run build` ×2, `git show`/`git diff` against the actual committed tree) in a clean git worktree at this PR's head, not inferred from reading. Confirmed independently by Opus (strategic read) and Codex (live `gpt-5.5`, ran its own read-only commands in the same worktree) — zero disagreement across all three passes.

### 🔴 Blocking

1. **[Critical] The `dist-reproducible` guard can never pass — proven on this PR's own head commit.** `dist/api/tasks.json`, `search.json`, `statistics.json`, and `status.json` embed an **absolute filesystem path** (`filePath`, `projectPath`, `rootConfigPath` — e.g. committed `status.json` literally contains `"/Users/jason/Dev/Brood"`) and a wall-clock/source-mtime `lastModified`, sourced verbatim from the `backlog.md` CLI's local REST API. These fields can never match between whatever machine built the committed `dist/` and a GitHub Actions runner's checkout path (`/home/runner/work/Brood/Brood/...`) — or even the author's own machine today, which is now `~/Dev/aastar/Brood`, not `/Users/jason/Dev/Brood`. Reproduced: installed the exact pinned CLI (`backlog.md@1.49.3`), ran `npm run build` twice (deterministic across runs), diffed against what's committed — **49/49 tasks differ**, isolated via field-level JSON diff to exactly `filePath`+`lastModified`(+`comments`). The job will report "stale" on every PR forever, including ones that touch nothing dist-related — permanently red, and the team will learn to bypass it, which is worse than not having the guard.
   Fix: relativize `filePath`/`projectPath`/`rootConfigPath` to repo root and drop (or tree-derive) `lastModified` before writing `dist/api/*.json`, then rebuild + recommit `dist/` with the pinned CLI. **Do not** "fix" this by excluding more files from the diff check the way `version.json` is excluded — all 4 remaining diffed API files are path/mtime-contaminated, so excluding them would leave the guard watching only `index.html` + hashed assets and go green while shipping exactly the stale/foreign-server data this PR exists to prevent.

2. **[High] The same data leaks the maintainer's home-directory path to the live public site.** `deploy.yml` uploads `dist/` verbatim. Committed `dist/api/status.json` contains `"projectPath":"/Users/jason/Dev/Brood"` and `"rootConfigPath":"/Users/jason/Dev/Brood/backlog.config.yml"`; `tasks.json`/`search.json` carry 49 absolute `filePath` values. Real content/info-disclosure bug, independent of the CI-guard framing above — same fix (relativize before write) resolves both at once.

3. **[High] `npx backlog` (the wrong-package bug from the last round's finding #1) is still live in the script itself.** `scripts/export-backlog.js:193` still does `spawn('npx', ['backlog', 'browser', ...])`. Only `verify.yml` was hardened around it (`npm install --no-save backlog.md@1.49.3` + PATH prepend, CI-only); any developer running `npm run build` locally without that exact install still resolves the bare `backlog` package (a different, unrelated npm package) exactly as before, and `stdio:'ignore'` still swallows the resulting error.
   Fix: add `backlog.md@1.49.3` as a real `devDependency` (+ lockfile, `npm ci` in CI) and spawn the resolved bin path directly — never bare `npx`.

4. **[Medium — carried over from the first review round, still unfixed] `scripts/ci/check-task-yaml.py` `SCAN_DIRS` still omits `backlog/milestones`, `backlog/data`, `backlog/completed`, `backlog/drafts`.** Re-verified independently by all three rounds: `backlog/milestones/` has 4 files with live YAML frontmatter today (`m-1`…`m-3`, `m-r`), actively read by the exporter for the milestones API. An unquoted `:` in a milestone title breaks the exporter identically to the incident this PR fixes, and this gate would not catch it there.
   Fix: add those four dirs to `SCAN_DIRS`.

### Confirmed but non-blocking

- **[Medium]** `package.json` has zero dependencies and no lockfile — the `backlog.md@1.49.3` pin exists only as an inline string in one CI step, so nothing else (local dev, any other workflow) is pinned. Fixing this the same way resolves #3 above and the version skew below in one pass.
- **[Medium]** Committed `dist/api/version.json` says `"1.45.0"` while CI now pins `1.49.3` — the committed `dist/` was never rebuilt with the pinned CLI. Subsumed by finding #1 but must be fixed in the same rebuild.
- **[Medium]** `withDeterministicConfig`'s regex (`^check_active_branches:[ \t]*true[ \t]*$`) silently no-ops — no warning — if the key is absent, differently indented, or commented; determinism is then assumed but not actually achieved.
- **[Low]** `serverExited` is checked once at the 4s startup mark and never re-checked during the later fetch-retry loop, so a mid-export server death surfaces only as a generic fetch failure, not the intended hard error.
- **[Low]** The "this is a BUILD FAILURE, not stale" guidance in `verify.yml` is now effectively unreachable: with `set -euo pipefail` + the script's `process.exitCode = 1`, a thrown export aborts the step before that branch runs. Harmless (defense-in-depth), but not the safety net the comment describes — consider `npm run build || build_failed=1` so the message actually reaches a developer whose build fails.
- **[Low]** `withDeterministicConfig` mutates the tracked `backlog/config.yml` in place and restores it only in a `finally` — a hard crash/SIGTERM mid-export leaves `check_active_branches: false` committed into the working tree as a silent side effect.
- **[Low]** `assertPortFree`'s 1500ms socket-timeout treats "no response yet" as "port free" — a hung/stale `backlog browser` (the exact 2026-07-07 incident this function exists to catch) could be misclassified as absent.

### Verified working (credit where due)

- Prior findings #1 (CI path only), #2, #3, #4 from the last review round are genuinely fixed: `npm install backlog.md@1.49.3` + PATH prepend verified via `which backlog` → pinned bin, `backlog --version` → `1.49.3`, full `npm run build` succeeded end-to-end; `git add -AN -- dist/` correctly makes new files visible to `git diff --quiet` (git intent-to-add semantics verified); `dist/api/docs/doc-8.json` is now committed; the `version.json` exclusion comment is now factually accurate.
- The separately-noted "guard erases the live site" fix (`fetchFromLocal('/')` proving the local server answers *before* `fs.rm(distDir)`) is correctly ordered and was exercised successfully during the build run above.
- `scripts/ci/check-task-yaml.py` still runs clean; not touched this round, no regression.

### Assumptions
- Reviewed via a git worktree at this PR's exact head commit (`728891689de25656e506051efe479a301870f99e`), not the shared local `~/Dev/aastar/Brood` checkout (which has unrelated local WIP on `main`).
- The incremental diff reviewed excludes ~30 files that arrived via `git merge origin/main` and were not authored by this PR (docs/org/protocol content already on `main`); only the two PR-authored commits (`0c27123`, `7288916`) were treated as in-scope changes.
- No linked issue in the PR body — skipped the Issue-compliance section.

---
*Reviewed by clestons (pr-daemon-loop v4, 4-round, incremental re-review of commit `b693c6d5`→`72889168`): DeepSeek R1a+R1b (dual-pass, low signal this round — see self-assessment) → Sonnet mechanical verification (real `npm install`/`npm run build` ×2 in a clean worktree, field-level JSON diff) → Opus R2 (independent strategic read, isolated the exact root cause and added 4 more findings) → Codex R3 (live `gpt-5.5`, ran its own read-only commands in-worktree, CONFIRMED all 6 findings, zero challenges) → Opus R4 (final verdict, full-diff missed-finding scan, +3 additional Low findings).*
