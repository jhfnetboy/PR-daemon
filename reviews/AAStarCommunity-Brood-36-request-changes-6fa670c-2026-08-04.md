## Verdict: REQUEST_CHANGES (incremental re-review, head `6fa670c`, round 4)

Both blocking `[High]` findings from the last round are **genuinely fixed and mechanically verified** — I planted a completed task and ran the real build rather than reading the patch:

- Planted `backlog/completed/task-999 - Review fixture.md` → `npm run build` **succeeds**, `✅ Consistency check passed (50 tasks)`. Last round this path hard-crashed the build.
- The planted task's `filePath` in `dist/api/tasks.json` is `backlog/completed/task-999 - Review fixture.md` — repo-relative, and `lastModified` is gone. `grep -rl "/Users/jason\|/private/tmp" dist/` → **0 hits**.
- Two consecutive builds are byte-identical (`diff -rq` exit 0). The reproducibility guard still holds.

The `search.json` mirror is also the right fix rather than the tempting one: loosening the consistency assertion would have left the completed task unfindable in site search. Credit for fixing the cause instead of the symptom.

What blocks this round is **not** the export path — it is the new `reference/review-contract.md`. That doc is now the single normative source for how an unattended agent waits for a verdict, and as written the loop it prescribes cannot work. Three of the five blocking items below live in that one file, and the PR's own state demonstrates the first one.

### 🔴 Blocking

1. **[Medium] `reference/review-contract.md:27` + `scripts/pr-monitor.sh:34` — the documented wake condition cannot observe review round ≥ 2.** The contract says wake when `reviewDecision` is no longer `PENDING`. But GitHub keeps `reviewDecision=CHANGES_REQUESTED` across pushes — a push dismisses *approvals* at most, never a changes-requested review. `pr-monitor.sh` returns no head SHA and no review commit SHA, so a fresh verdict is indistinguishable from a stale one.
   **Live proof on this very PR, right now:** `gh pr view 36 --json reviewDecision` returns `CHANGES_REQUESTED` while the newest review is pinned to commit `31aa85b` — five commits behind head `6fa670c`. An agent following §"拿到裁决之后(反复循环)" would immediately re-triage a verdict about code it already replaced, and loop.
   **Fix:** add `headRefOid` + `latestReviews[].commit.oid` to `fields`, print `head_sha`/`review_sha`, and make the documented wake condition "裁决存在 **且** `review_sha == head_sha`".

2. **[Medium] `reference/review-contract.md:25` + `scripts/pr-monitor.sh:31` — the prescribed `Monitor` invocation cannot produce the documented cadence.** `pr-monitor.sh --pr <n>` is explicitly one-shot and *unconditionally* prints the PR line. A `Monitor` running it therefore fires on the first sample within seconds and terminates — so the "3–5 分钟一次" interval never happens, and the 30-minute cap the doc itself calls 防止无限等待的唯一机制 never engages.
   **Fix:** give the script a `--wait-for-verdict` mode that stays silent / exits non-zero while PENDING (so `Monitor` has something to actually wait on), or document the `Monitor` call with an explicit predicate on the printed `reviewDecision=` plus `timeout_ms: 1800000`.

3. **[Medium] `scripts/pr-monitor.sh:34` + `phases/run.md:141` — `age_min` is PR age, but it is consumed as "how long this round has waited".** It derives from `.createdAt`. On any re-review round `age_min` is already ≫ 30 the moment the wait starts, so the documented timeout rule fires instantly and tells the user 外部评审服务可能未覆盖本仓库 — for a PR that is being actively reviewed. **This PR, on round 4, is itself the failing case.**
   **Fix:** report `wait_min` from `latestReviews[].submittedAt` or the head commit's `committedDate`; keep `age_min` as informational only.

4. **[Medium] `.claude-plugin/marketplace.json:11` and `plugins/pilot/.claude-plugin/plugin.json:4` still advertise the integration this PR deletes.** Both descriptions end with `外部 PR 评审 daemon 集成(每日刷新 Top-N 活跃仓库扫描清单)` — while `ensure-pr-daemon.sh` and its daily refresh are removed by this very diff. This is the user-facing marketplace copy: an installer is promised a feature the plugin no longer has, which also regresses the wording PR #34 was merged to correct.
   **Fix:** replace that clause with contract wording, e.g. `PR 开出后按 reference/review-contract.md 盯外部评审裁决(不启动、不感知任何评审后端)`.

5. **[Medium] `templates/goal.md:16` — the one artifact that actually governs runtime is the one still missing the cap.** This PR edits that exact line, yet it still reads `5 分钟起退避，PENDING 就继续等不要瞎改` with no upper bound — directly contradicting `review-contract.md:29` (`不设上限会让 agent 永久睡死…上限不是可选优化`). `/goal` is the contract handed to the unattended loop, so the contradiction lands exactly where it does the most damage.
   **Fix:** `3–5 分钟一次并设 30 分钟硬上限；到点仍 PENDING 按 review-contract.md 的超时路径如实汇报后回主循环`.

### Confirmed, carried over

- **[Medium — open 4 consecutive rounds] `scripts/ci/check-task-yaml.py:25`** — `SCAN_DIRS` still omits `backlog/milestones`. Re-verified at this head: that directory holds 4 live frontmatter files and is exported via `export-backlog.js:510`, so a malformed milestone frontmatter ships to `/api/milestones.json` unchecked — the exact incident class this gate exists to prevent. It is a one-token diff and has now survived four rounds. Either land it, or state explicitly that milestone frontmatter is intentionally unvalidated so it stops re-surfacing.
- **[Medium] `phases/run.md:101,111`** — the `pr-create` gate at `git-guard.sh:121` remains unreachable from the documented workflow. Zero `.md` files anywhere under `plugins/` mention `pr-create`, `preflight.sh`, `grade-change.sh`, or `PILOT_SKIP_PREFLIGHT` (grep-verified); both PR-creation steps still say plain `gh pr create`. And `reference/pre-pr-review.md` — cited as normative by `grade-change.sh:7` and by the gate's own error message at `git-guard.sh:146` — still does not exist (`reference/` holds only followup-ledger, git-safety, pr-quality, review-contract, review-triage, task-schema). Last round's fail-open paths in those three scripts are untouched by this diff.

### Non-blocking

- **[Low] `scripts/export-backlog.js:531`** — `taskFiles` is never sorted, so completed tasks land in `tasksData` (and `search.json`) in raw `fs.readdir` order, which is filesystem-dependent. `dist/` is committed and byte-compared by the reproducibility guard, and this same hunk removes `new Date()` for precisely that reason. Same-machine rebuilds are stable (verified), so this is dormant exactly as long as the two bugs just fixed were — but with ≥2 completed tasks, a build on APFS and one on ext4 can emit different array order for identical content and fail the guard for a non-reason. One `.sort()` closes it.
- **[Low] `plugins/pilot/.claude-plugin/plugin.json:3`** — version stays `1.1.0` while this PR deletes a shipped script (`ensure-pr-daemon.sh`), a subcommand (`review-status`), a config key (`pr_daemon_root`) and a reference doc. Installed copies can't tell old from new.

### Rejected

- **All 4 DeepSeek R1 findings — refuted by measurement.** "`filePath` may be absolute": the built output for the planted fixture is `backlog/completed/task-999 - Review fixture.md`, and the absolute-path grep over `dist/` returns 0. "`sanitizeApiPayload` not defined": it is defined at `export-backlog.js:88`.
- **Codex R3's one new finding — refuted by two controlled builds.** Codex argued the completed-task merge never updates `statistics.totalTasks`, so the consistency check still fails. Measured: **without** the fixture all three counts are 49/49/49; **with** it, 50/50/50, and `assertExportConsistent` passes both times. The backlog CLI's `/api/statistics` already counts `backlog/completed/` while its `/api/tasks` list excludes it — the merge block closes exactly that gap rather than opening one. This is a property of the upstream CLI and not derivable from reading this file, so the reasoning was sound; the conclusion just doesn't survive execution.

### Note on the decoupling itself

Architecturally this is the right move, and `doctor` saying 本地就绪 ≠ PR 一定会被评审 is an honest touch. Two things worth saying out loud in the PR rather than leaving implicit:

- The deleted `pilot status` step was the daily cross-repo trigger that refreshed the review service's scan list. Pilot is right not to own that, but after this PR the responsibility has to live on the service side (cron / self-refresh) — otherwise "解耦" quietly converts a self-healing mechanism into a manual escalation path.
- Findings 1–3, plus the two carried-over items, are all the same failure mode: **normative text pointing at behavior the scripts don't provide.** This is round 4 and that class hasn't shrunk. One pass that mechanically checks every doc→script/tool claim under `reference/` would likely close more than fixing them one round at a time.

### Assumptions

- Reviewed in a dedicated worktree at this PR's exact head `6fa670c`, not the shared `~/Dev/aastar/Brood` checkout. The `backlog/completed/` fixture and the `dist/` from my builds were mine and have been removed; nothing in the PR branch was modified.
- Incremental scope is `31aa85b..6fa670c` (5 commits); earlier rounds' findings were each re-verified at this head rather than assumed.
- No linked issue in the PR body — Issue-compliance section skipped.

---
*Reviewed by clestons (`$pr` v4, 4-round, incremental `31aa85b`→`6fa670c`): DeepSeek R1a+R1b (dual-pass, `deepseek-v4-flash`; 4 findings, 0 survived verification) → Sonnet mechanical verification (planted a completed-task fixture, ran `npm run build` ×3 in an isolated worktree, absolute-path grep sweep, jq expression tests, two controlled builds to settle the Codex challenge) → Opus R2 (independent strategic read; 7 findings, all survived) → Codex R3 (`gpt-5.5`, ran in the same worktree; CONFIRMED all 7, zero challenges, 1 new finding refuted by measurement) → Opus R4 (final verdict + full-diff missed scan, +1 Low on `readdir` ordering).*
