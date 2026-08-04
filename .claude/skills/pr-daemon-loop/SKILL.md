---
name: pr-daemon-loop
description: Full 24/7 autonomous PR review loop (v4). Sonnet=pure executor, DeepSeek=dual-pass R1 (full+security parallel), Opus=R2 strategic independent reviewer + final verdict, Codex=R3 adversarial PK against Opus findings. Evaluate vs v3 after each PR.
origin: pr-daemon
---

<!-- ROLLBACK:
  v4 → v3: cp ~/.claude/skills/pr-daemon-loop/SKILL.md.bak-v3-20260619 ~/.claude/skills/pr-daemon-loop/SKILL.md
  v3 → v2: cp ~/.claude/skills/pr-daemon-loop/SKILL.md.bak-20260614 ~/.claude/skills/pr-daemon-loop/SKILL.md
-->

# PR Daemon Loop (v4 — Opus strategic R2 + dual DeepSeek + Sonnet executor)

> ⛔ **ABSOLUTE CONSTRAINT #1 — Review only, NEVER merge**
> Pure reviewer. NEVER merge any PR regardless of author (human or bot).
> Merging is handled by `$pr-fix` after its review loop completes.
> Allowed GitHub writes: post review / request changes / approve. Nothing else.
>
> ⛔ **ABSOLUTE CONSTRAINT #2 — One PR at a time, individually**
> Each PR runs the full pipeline independently. No batch-scan-then-bulk-approve.
>
> ⛔ **ABSOLUTE CONSTRAINT #3 — Opus is final authority for 4-round; respect Codex point-by-point**
> Opus makes the final APPROVE/REQUEST_CHANGES call on 4-round PRs.
> Do NOT dismiss a Codex finding without concrete counter-evidence.
>
> ⛔ **ABSOLUTE CONSTRAINT #4 — configured scopes only (allowlist)**
> Review PRs only in the configured scan scopes (`~/.config/prbot/repos.conf`): the `AAStarCommunity`
> / `iDoris-ai` / `MushroomDAO` orgs, PLUS any personal `owner/repo` explicitly added to that file as
> an include-list entry (e.g. `jhfnetboy/CMIC`). Personal repos are NOT scanned by default (there are
> hundreds); the include-list is the allowlist. Never review a personal PR that is not on that list.
>
> ⛔ **ABSOLUTE CONSTRAINT #5 — DeepSeek R1a is NEVER optional (added 2026-08-01, user reprimanded)**
> Run R1a (`deepseek_review.py`, model pinned to `deepseek-v4-flash`) on **every single review round**,
> full stop — new PR, incremental re-review of a fix commit, tiny diff, interactive session where you
> could "just read it yourself faster", doesn't matter. "I can do a good review without it" is NOT a
> valid reason to skip it — the point isn't just review quality, it's building an ongoing, comparable
> DeepSeek-flash performance record (target: 20 rounds, started 2026-08-01, tracked via
> `model_eval_db.py provider-summary` with `--provider deepseek --model deepseek-v4-flash` always
> explicit on `record-run`) to decide flash vs. pro. Skipping R1 "this once because it's small/fast"
> silently breaks that record and defeats the entire point — this happened once already
> (AirAccount#191 re-review) and must not happen again.
> After R1a returns, verify each of its findings against the actual code/diff yourself (don't just
> trust it) and append ONE explicit line to the self-assessment (Step 8): a 1-5 rating of DeepSeek
> v4-flash's performance THIS round + one sentence why (findings that held up under verification /
> false positives / anything a later round — Opus R2, Codex R3, or your own reading — caught that
> flash missed entirely), plus, when something concrete comes to mind, a one-line suggestion for how
> to get more signal out of it next time (tighter prompt, more context, narrower diff scope, etc.).

> ⛔ **ABSOLUTE CONSTRAINT #6 — you are HEADLESS: never end a run by asking a question**
> You run under `claude --print` from a background daemon. **Nobody reads your output while it runs
> and nobody can answer you.** A run that ends in a question produces no review, burns the whole
> ~20-minute cycle, blocks every PR queued behind it, and — since nothing changed — asks the same
> question again next cycle. That is an infinite loop, not a pause. (Observed: a reviewer stalled on
> `jhfnetboy/CMIC#142` asking whether an allowlisted personal repo was in scope, after hitting the
> stale "3 orgs only" line that has now been corrected.)
>
> On ambiguity, missing context, or rules that contradict each other:
> 1. **Decide it yourself**, precedence: **executed config > this document > memory**. What the
>    daemon actually runs (`repos.conf`, the scripts) beats what any doc claims about it.
> 2. **Deliver the review anyway**, and record the call in a short `## Assumptions` section: what
>    was ambiguous, how you resolved it, why.
> 3. If a doc looks stale or self-contradicting, say so **in that same section** — a note inside a
>    delivered review reaches the maintainer; a question that halts the run reaches nobody.
>
> The only acceptable no-verdict outcome is a hard technical failure (API down, diff unfetchable),
> and even then say what failed. **Never trade a verdict for a question.**

## Roles & Models (v4 division)

| Role | Model | Job | Judgment? |
|------|-------|-----|-----------|
| **Executor** | Sonnet (this session) | fetch, compress, scripts, format, 2-round verdict | ✅ 2-round only |
| **R1a — full pass** | DeepSeek API | full mechanical review: files, findings, triage, skeleton | ❌ |
| **R1b — security pass** | DeepSeek API | security-only lens (auth/crypto/payment/permission/state) in parallel with R1a | ❌ |
| **R2 — strategic reviewer** | Opus subagent | reads compressed diff independently; challenges R1 findings; adds cross-file/architectural analysis | ❌ confirms/adds |
| **R3 — PK adversary** | Codex (Agent tool) | adversarial challenge of Opus R2's findings (targeted hunks only) | ❌ |
| **Final verdict** | Opus subagent (2nd call) | full diff + all round context → APPROVE/REQUEST_CHANGES + missed-finding scan | ✅ 4-round |

**Key v4 changes from v3:**
- Sonnet no longer challenges findings (was R2 in v3). Sonnet = executor only.
- DeepSeek runs TWO parallel passes (R1a full + R1b security).
- Opus is elevated to R2 independent strategic reviewer — reads the diff itself, not just Sonnet's summary.
- Codex PK now challenges Opus R2 findings (more meaningful than challenging Sonnet's R2).
- Opus makes two calls: R2 (reviewer) + R4 (final verdict). Same model, separate focus.

## The v4 Loop

```
poll_prs.py → for each PR:
  R1a  DeepSeek full review     ┐
  R1b  DeepSeek security-only  ┘ (parallel)
  ▼   Sonnet merges R1a+R1b, deduplicates, formats working list
  ▼   triage confirm (2-round vs 4-round)
  ├─ 2-round: Sonnet verdict (low-risk docs/chore, no Opus)
  └─ 4-round:
       R2  Opus reads compressed diff independently → strategic findings + R1 challenge
       ▼   post-R2 severity gate
       ├─ all Low/suggestions → SKIP Codex → Opus R4 final (full diff + missed scan)
       └─ any Medium+ → R3 Codex targeted PK (±20 lines per Opus-confirmed Medium+ finding)
                       → R4 Opus final (full diff + all rounds → verdict +补扫)
  ▼   record per-round stats → model_eval_db → post → next PR
```

## Token discipline (read first)

- Read/compress the diff **ONCE** → `/tmp/pr-N-compressed.diff`. Reuse everywhere.
- **R1a and R1b run in parallel** via two `deepseek_review.py` calls (different system prompts).
- **Opus R2 gets the compressed diff** — reads it independently; gets R1a+R1b merged list as additional context (not as the only truth).
- **Codex gets targeted hunks** (±20 lines per Opus-confirmed Medium+ finding), NOT full diff.
- **Opus R4 gets full compressed diff** — missed-finding scan requires full context.
- Each round outputs **deltas only** — CONFIRM/REJECT/ADD, not re-derivation.
- Never tell subagents to re-fetch `gh pr diff`.

## Step 0 — Check PR state (MANDATORY first action)

**Before fetching any diff or running any review step**, verify the PR is still open:

```bash
gh pr view N --repo OWNER/REPO --json state,mergedAt
```

- `state == "OPEN"` → proceed to Step 1
- `state == "MERGED"` or `"CLOSED"` → **STOP. Skip entirely.** Report: "OWNER/REPO#N is already merged/closed — skipped."

This applies to every review request, including re-reviews and user-directed `sp N` / `kms N` commands.

## Step 1 — Sync + discover PRs

**At the start of every loop cycle, run with `--sync`** to mirror ALL open PRs into SQLite:

**Org-scan mode** (all 3 orgs, ALL authors incl. dependabot):
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/poll_prs.py --sync --max 200
```
**Single-repo mode** (one repo, all its open PRs):
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/poll_prs.py --repo OWNER/REPO --sync --max 50
```
Output: `total_open`, `sync` counts (inserted/updated/closed), and the review `queue`.
The user may pass a repo via `/pr-daemon-loop OWNER/REPO` — honor it.

## Step 2 — Get & compress the diff (Sonnet executor)

```bash
gh pr diff N --repo OWNER/REPO > /tmp/pr-N.diff
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/compress_diff.py \
  --file /tmp/pr-N.diff --budget 80000 --stats > /tmp/pr-N-compressed.diff
```

> **Coverage transparency:** `--stats` prints dropped files. If any were dropped, add `Coverage: N files omitted (token budget)` to the review. For a dropped security-sensitive file, fetch it directly.

> **Dependency PRs — splice the lockfile hunk back in:** `compress_diff.py` DROPS lockfiles, so R1
> reviews a version-number change blind to what actually resolved. For a dependency bump, `git diff`
> the lockfile for the bumped package's block (`grep -n -A20 "<pkg>" <lockfile>` on both sides) and
> append those hunks to the R1 context — otherwise flash misses registry switches, integrity
> mismatches, and transitive drift (observed: Cos72#27 missed an npmmirror→npmjs registry flip).

## Step 2.5 — Issue / DoD compliance (issue-driven PRs)

When a PR references an issue (title `(#N)`, body `关联/Closes/Refs #N`), verify the diff delivers what the issue asked.

```bash
# parse title + body for issue refs:
gh pr view N --repo OWNER/REPO --json title,body -q '.title + "\n" + .body' \
  | grep -oiE '(关联|实现|closes|fixes|resolves|refs)\s*:?\s*#[0-9]+|\(#[0-9]+\)' | grep -oE '#[0-9]+'
gh issue view <ISSUE_N> --repo OWNER/REPO --json title,body
```

Map each issue DoD item against the diff. Include in the review:
```
## Issue compliance (#N)
- ✅ Met: <requirement → where in diff satisfies it>
- ❌ Not met: <stated DoD item missing — grounds for REQUEST_CHANGES>
- 🔍 Needs human verification: <not judgeable from code alone>
```
Skip this section entirely for trivial docs/chore PRs with no linked issue.

## Step 3 — R1: DeepSeek dual-pass (parallel)

Run both passes simultaneously. R1a is the full mechanical pass; R1b is a focused security lens.

```bash
# R1a — full review (full mechanical pass, same as v3)
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/deepseek_review.py \
  --diff-file /tmp/pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/pr-N-r1a.md

# R1b — security-only pass (different system prompt, same diff)
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/deepseek_review.py \
  --diff-file /tmp/pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/pr-N-r1b.md \
  --mode security
```

Both R1a and R1b always go through `deepseek_review.py` (`--mode security` is implemented). Both calls resolve the model from `PR_DAEMON_FIRST_PASS_MODEL`, pinned to **`deepseek-v4-flash`** (non-thinking mode, `PR_DAEMON_FIRST_PASS_THINKING=disabled`) — do not call the DeepSeek API directly or hardcode any other model id (e.g. the deprecated `deepseek-chat` / `deepseek-reasoner` aliases).

**Sonnet merges R1a + R1b (executor role):**
- Deduplicate overlapping findings (keep the higher-severity label)
- Format a compact working list: `[Sev] file:line — issue | fix` per finding
- Preserve R1b security findings even if they overlap R1a (security gets double weight)
- Save to `/tmp/pr-N-r1-merged.md`

## Step 4 — Triage confirm: 2-round or 4-round?

**YOU (Sonnet as executor) confirm the class:**

**2-round (low risk) — reserved for PURE bumps/text; needs ALL:**
- a pure version/dependency bump (dependabot/renovate) / lockfile-only / README / badge / LICENSE / CODEOWNERS text
- comment / typo / formatting with NO behavioral change
- does NOT touch `src/` `contracts/` `lib/` real logic
- NO new public API / schema / migration
- does NOT touch any automation-consumed file (see the 🔧 rule below)

**4-round (high risk) — ANY triggers it:**
- type is feat / major refactor
- touches core code: `src/` `contracts/` `lib/` real logic
- 🔴 **security-sensitive (HARD rule)**: `.sol` / auth / crypto / payment / token / permission / access-control
- concurrency / state machine / data persistence / DB migration
- API contract / interface / schema change
- deletes tests / disables security checks / cross-module sweep
- 🔧 **automation-consumed files (NOT trivial even under `docs/`)**: CI workflows (`.github/workflows/*`),
  `.pilot.yml`, task/plan ledgers (`docs/agent/tasks.md|roadmap.md|progress.md`), or any config/YAML/TOML
  parsed & executed by CI / `pilot` / scripts. A bad value here has real consequences — a file being
  Markdown or "docs" does NOT make it human-only prose.

**Safety bias:**
- 🔴 security-sensitive → force 4-round, DO NOT accept DeepSeek downgrade
- uncertain → escalate to 4-round (over-review beats under-review)
- **anything past a pure bump/text change → at least R2 Opus.** The 2-round (Sonnet-only) path has NO
  Opus/Codex backstop, and DeepSeek-flash is weakest exactly on judgement calls. When in doubt take the
  4-round path — the post-R2 severity gate below still SKIPS Codex if R2 finds nothing Medium+, so
  "config/docs with an Opus read" costs ~R1+R2, not a full 4 rounds.

Record:
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py record \
  --repo OWNER/REPO --pr N --head-oid HEAD \
  --rounds 2 --rationale "..." --signals "..."
```

## Step 5a — 2-round path (low risk)

**Sonnet (executor role) reviews and decides directly.** Fold in valid R1a/R1b findings. No Opus, no Codex.

This is the one place where Sonnet makes a judgment call — and only for truly low-risk PRs where the stakes are low enough that Sonnet's verdict is acceptable.

**Docs-PR blocking bar (pure prose / aggregation markdown — no code, no automation-consumed config).**
For a PR that only touches human-read prose (`*.md` docs, backlog task/doc bodies, READMEs), REQUEST_CHANGES **only** on a **substantive error** — something factually wrong that would mislead a reader or operator:
- a wrong command / wrong port / wrong endpoint / wrong path vs the real code it documents,
- a referenced repo / file / PR / tag that does not exist (404),
- a broken cross-reference, or a claim contradicted by the repo's own state.

**Internal-precision nits are NON-BLOCKING — report them as suggestions in the COMMENT body, do NOT REQUEST_CHANGES for them:**
- a count/number that disagrees between two lines, an item mis-numbered, a summary sentence that slightly over-claims scope ("all X done" when most are),
- "missing link / test evidence" objections against pure prose,
- wording / style / consistency polish.

A pure-docs PR should converge in **ONE round** unless it contains a substantive factual error. Rationale: cycling a prose PR through repeated REQUEST_CHANGES rounds for internal-precision nits costs far more (full reviewer + author round-trips, queue time) than the nit is worth — flag them once as suggestions and APPROVE. (This does NOT relax the bar for automation-consumed files under Step 4 — those are not "pure prose".)

Go to Step 6.

## Step 5b — 4-round path (high risk)

### R2 — Opus independent strategic review

Opus reads the diff **independently** — it forms its own view before seeing R1. Then it evaluates R1 findings as additional input.

```
Agent(subagent_type="general-purpose", model="opus", prompt="""
You are R2 strategic reviewer for OWNER/REPO#N. Two-phase approach:

PHASE 1 — Read the diff independently (below). Form your own list of findings before looking at R1.
Focus on: cross-file consistency, state machine correctness, security patterns, missing error handling,
off-by-one, race conditions, API contract violations, missing tests for changed behavior.

PHASE 2 — Evaluate R1 findings:
R1 MERGED FINDINGS:
<paste /tmp/pr-N-r1-merged.md>

Per R1 finding: CONFIRM id | REJECT id — reason ≤15 words | ADD [Sev] file:line — issue | fix

Output ONLY this template:
R2_INDEPENDENT: <[Sev] file:line — issue> (findings you found BEFORE reading R1; "NONE" if none)
R2_CONFIRM: <ids from R1>
R2_REJECT: <id — reason>
R2_ADD: <[Sev] file:line — issue | fix>
R2_STRATEGIC: <≤3 bullets on cross-file/architectural concerns not capturable as file:line>
R2_TRIAGE_CONFIRM: 2-round | 4-round | ESCALATE (challenge Sonnet's triage if wrong)

Do NOT produce a verdict. Do NOT post to GitHub.

COMPRESSED DIFF:
<paste /tmp/pr-N-compressed.diff>
""")
```

Save Opus R2 output to `/tmp/pr-N-r2.md`.

**Post-R2 severity gate:**
```
if R2 output contains ANY Medium+ finding (CONFIRM or ADD):
    → run R3 Codex (targeted) + R4 Opus final
else (all Low / suggestions only):
    → SKIP Codex entirely
    → run R4 Opus final directly (with full diff + missed scan)
    → note in report: "Codex skipped — post-R2 all Low"
```

---

### R3 — Codex PK (Medium+ findings only, targeted hunks)

Codex challenges Opus R2's Medium+ findings (not R1 findings directly).

> **Headless/daemon runs — invoke Codex via `bash scripts/codex_pk.sh` directly, NOT
> `Agent(codex:codex-rescue)`.** The Agent path spawns internal Bash that a restrictive permission
> layer can DENY (observed on Brood#13: the R3 sub-agent was blocked, produced no Codex output, and
> forced a turn-wasting fallback). The direct `codex_pk.sh` Bash call runs `codex exec` in a worktree
> and is reliable under `--dangerously-skip-permissions` (validated on Self-FDE#63 / #139 / YAA#450).
> Use `Agent(codex:codex-rescue)` only in an interactive session where you WANT the permission prompts.

**Extract targeted hunks first (Sonnet executor):** for each Opus-confirmed/added Medium+ finding at `file:line`, extract ±20 lines from the compressed diff. One `HUNK <id>:` block per finding.

```
Agent(subagent_type="codex:codex-rescue", prompt="""
PK CHALLENGE OWNER/REPO#N. Challenge the Opus R2 findings below.
Do NOT fetch the full diff — only relevant hunks are provided.
Per finding: [CHALLENGE|CONFIRM|MISSED] id — reason ≤15 words.

OPUS R2 FINDINGS (Medium+ only):
F1 [Medium] file.ts:42 — description
F2 [High] other.sol:88 — description

HUNK F1 (file.ts ~line 42, ±20 lines):
<paste hunk>

HUNK F2 (other.sol ~line 88, ±20 lines):
<paste hunk>

Return ONLY the structured critique. Do not post to GitHub.
""")
```

If Codex quota exhausted → skip R3, add note, Opus R4 covers with full diff.

---

### R4 — Opus final verdict + missed-finding scan

Second Opus call. Gets full diff + all round context. Two jobs in one call.

```
Agent(subagent_type="general-purpose", model="opus", prompt="""
Final authority on OWNER/REPO#N.

Job 1: Decide the verdict using all round inputs below.
Job 2: Scan the full diff for anything all prior rounds missed (cross-file, subtle logic, security patterns not visible from individual hunks).

Respect Codex point-by-point — no dismissal without concrete counter-evidence.
Output ONLY this template, no prose:

VERDICT: APPROVE | REQUEST_CHANGES
BLOCKING: <[Sev] file:line — issue | fix>   (empty if APPROVE)
CONFIRMED: <[Sev] file:line — issue | fix>
REJECTED: <finding — reason>
MISSED: <[Sev] file:line — issue found in full-diff scan>  (empty if none)
SUGGESTIONS: ≤3 bullets, optional
ROUNDS:
  R1a(DeepSeek-full): <compact summary>
  R1b(DeepSeek-sec): <compact summary>
  R2(Opus-strategic): <compact summary>
  R3(Codex-PK): <compact summary, or "SKIPPED — post-R2 all Low">

FULL DIFF (compressed):
<paste /tmp/pr-N-compressed.diff>

ROUND SUMMARIES:
R1a: <merged findings compact>
R1b: <security findings compact>
R2: <paste /tmp/pr-N-r2.md>
R3: <Codex output compact, or "SKIPPED">
""")
```

## Step 6 — Post the verdict (Sonnet executor)

Verdict MUST be **APPROVE** or **REQUEST_CHANGES** — never COMMENT limbo.
- REQUEST_CHANGES: specific objections (problem + trigger scenario + fix). Cap to top ~5 by severity.
- APPROVE: may append enhancement / polish suggestions.
- High-impact / low-confidence item (data loss, security, fund-at-risk) → report with explicit uncertainty note. Never pad with low-value nits.
- If an issue is linked, include the `## Issue compliance (#N)` section.

```bash
bash /Users/jason/Dev/tools/PR-Daemon/scripts/post_pr_review.sh \
  --repo OWNER/REPO --pr N --body-file /tmp/review-N.md \
  --request-changes   # or --approve
```
Always use `post_pr_review.sh` (PAT mode, no account switching). Never `gh pr review` directly.

## Step 6.5 — Sync verdict to goutou bus (只对 REQUEST_CHANGES + 已注册仓库)

> 目的：把「需要修改」的结论路由回**原仓库自己的 `/goutou` 工兵**去修（原仓库有全上下文，且覆盖任意作者）。
> 规范见 `~/Dev/jhfnetboy/goutou/docs/goutou/PR-REVIEW.md`。前置：`.goutou.json` 存在、Seeder MCP 可用。

**触发判断（不满足则跳过本步，直接 Step 7）**：

1. 读 `.goutou.json` 拿 `coordProjectId` 与 `goutouDepsPath`。缺文件 → 跳过（未接入 goutou）。
2. 把 `OWNER/REPO` 用 `goutouDepsPath`（`repos.<id>.github`）反查成 `originRepoId`。查不到 → 跳过（非生态仓库）。
3. bot PR（dependabot/renovate 作者）→ 跳过（走 pr-fix 内部闭环，不进总线）。

**幂等 upsert（靠 description 里的 `pr:OWNER/REPO#N` token 定位）**：

先 `mcp__seeder__search("pr:OWNER/REPO#N")` 或 `list-tasks(labelName="pr-review")` 找已存在的任务。

- **verdict == REQUEST_CHANGES**：
  1. 无任务 → `create-task`：
     - title = `[PR] OWNER/REPO#N: <PR标题截断>`
     - description = `pr:OWNER/REPO#N repo:<originRepoId> from:pr-daemon` + 换行 + PR URL / Head / Verdict / Author / Updated
  2. 确保标签存在（`list-task-labels` → 缺则 `create-task-label`）并挂上：`pr-review`(#ef8b3a) + `repo:pr-daemon` + `repo:<originRepoId>`
  3. `add-task-comment`：`[pr-daemon] REVIEW REQUEST_CHANGES @<sha8>` + top~5 blocking findings（`[Sev] file:line — 问题 | 建议`）
  4. 已有任务 → 更新 description 的 Head/Verdict/Updated，重新挂 `repo:<originRepoId>`（若上轮 approve 摘过），追加新 findings 评论
- **verdict == APPROVE**：
  1. 无任务 → 跳过（首轮就过，没啥要协同）
  2. 有任务（之前 RC 过）→ `list-task-statuses` 找 `isTerminal=true` 的 statusId → `update-task` 移到 Done（其余字段保持原值）+ `add-task-comment`：`[pr-daemon] REVIEW ✅ APPROVED @<sha8>，原仓库可自行 merge`

> 全部通过 `mcp__seeder__*` 调用（MCP 与 DeepSeek endpoint 无关，照常可用）。任一 MCP 调用失败 → 记一行 warning，不阻塞 Step 7（review 结论已发到 GitHub，是权威）。

## Step 7 — Score + record

```bash
# Score DeepSeek R1a+R1b for the improvement loop
# --useful-findings: count confirmed by Opus R2
# --false-positives: count rejected by Opus R2
# --misses: count R1b security findings NOT in R1a (unique security coverage)
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/model_eval_db.py record-run \
  --owner OWNER --repo REPO --pr-number N --head-oid HEAD \
  --score SCORE --verdict VERDICT \
  --useful-findings "R1a:N/M confirmed; R1b added K unique security findings" \
  --false-positives "R1a: X rejected by Opus R2" \
  --misses "Opus R2 independent found Y new; Codex missed Z"

# update watcher state
sqlite3 "$PR_DAEMON_STATE_DIR/pr-watch.sqlite" \
  "UPDATE pr_watch_targets SET last_reviewed_head_oid='HEAD', status='STATUS', \
   last_reviewed_at=CURRENT_TIMESTAMP, review_decision='VERDICT' WHERE repo='OWNER/REPO' AND pr_number=N;"

# token cost
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/token_cost.py --add INPUT_TOKENS OUTPUT_TOKENS
```

## Step 8 — Per-PR report + loop + v4 eval delta

Print after every PR:
```
📊 OWNER/REPO#N  VERDICT  [Nround]  v4-pipeline
   R1a: M/T confirmed (T total, M useful, X false-pos)
   R1b: K unique security findings (N confirmed by Opus)
   R2(Opus): Y independent findings, Z R1 rejected
   R3(Codex): [ran|skipped] — W challenges
   R4(Opus): final verdict
📊 PR status: open N, reviewed M [changes: X, approve: Y]
💰 this PR ~Nk tok | cumulative $X.XX
```
Then next PR. When queue empty: re-poll; if nothing new, `sleep 300` and re-scan.

### ⛔ Chat-output discipline (HARD — user repeatedly enforced)

The **full** review (verified table / findings / rounds / suggestions) goes **ONLY into the PR comment body** via `post_pr_review.sh`. The **chat reply** is terse:

> 审完了。OWNER/REPO#N ✅ APPROVE — [关键点1]；[关键点2]；[关键点3]。细节已在 PR comment 里。

- Give **2-3 load-bearing key points** (what real value you verified, what you caught, whether a negative-path/invariant holds) — **精准点评, not zero**. One line each, no sections.
- **NEVER** in chat: bullet/`###` sections, a "verified/findings/rounds" breakdown, restating what the PR changed, or re-explaining why it's correct. All of that lives in the PR comment only.
- 2-round docs/chore → usually a one-line verdict + "详情见 PR comment", 0-1 key point.
- REQUEST_CHANGES / decision needed → add one line for the blocker/decision.
- The verbose `📊` block above is internal bookkeeping — do NOT dump it to chat verbatim.
- Self-check: if your chat reply has sections or restates technical detail → delete, compress to "结论 + 几条精准点 + 见 comment".

### ⛔ Never merge unless explicitly told (HARD)

Words like "合 / ready / CI 会绿" in a message are **NOT** merge authorization. APPROVE is the endpoint; **ask before merging** unless the user explicitly says "你来合 / merge it / 你给合了". Security-critical PRs (recovery / owner-change / payment / permissions) → confirm even then.

### ⛔ No fake rounds — the label MUST match what actually ran (HARD — user reprimanded)

**Never tag a review `[N-round]` for a round count you did not actually execute.** Doing solo-Opus and labeling it `[4-round]` is fabrication. The round count in the verdict = the number of rounds whose tool calls actually happened in the transcript.

- **2-round** = DeepSeek R1 ran + Opus verdict. Allowed ONLY for docs/chore/comment/version-bump with no `src/`/contract/auth/crypto/payment touch.
- **4-round** = DeepSeek R1 (R1a+R1b) **actually called** → Opus R2 → **Codex R3 actually called** → Opus R4 verdict. REQUIRED for any security-sensitive PR (auth/crypto/payment/permission/.sol/.rs signing/challenge-binding/address-derivation). If you did not run DeepSeek and Codex, you may NOT write `[4-round]`.
- If a model genuinely can't run (e.g. Codex API 529), say so explicitly in the verdict and downgrade the label to what ran (e.g. `[3-round, Codex unavailable]`) — never claim it.

### Credibility = mechanical evidence, not model count (HARD)

For security-sensitive PRs, **run the tooling — don't reason from reading**. Default to:
- `forge inspect` / `forge test` / `cast call` / `cast sig` (keccak selectors) / on-chain `eth_call` decode — verify claims against ground truth.
- Read BOTH sides of any cross-layer contract (e.g. SDK encoder ↔ on-chain verifier; host ↔ TA) and map every case — don't trust a grep snippet.
- A review that says "I ran X, result Y" is worth more than three models reasoning. Prefer adding verifiable evidence over adding model passes.
- 🔴🔴 **CROSS-LAYER IMPACT ANALYSIS IS THE REVIEW — not the changed lines.** A change to one layer is only safe if every COUPLED layer that must stay consistent was changed in lockstep. Reviewing only the diff'd file is not a review. For EVERY PR, before any verdict, explicitly enumerate the coupled layers and CHECK each one (open the file, don't assume):
  - **CA(host) ↔ TA**: the recurring #110/#113/#121 bug class. If the **TA** changes an op's challenge binding (None↔Some / payload / tag), the **host** `resolve_passkey_assertion` `delegate_challenge_to_ta` for that EXACT op MUST flip to match — else the host rejects the committed challenge before it reaches the TA (`webauthn.rs` "challenge mismatch") and strict is unreachable. And vice-versa: if the host changes delegate, the TA's Some/None must match. **When you see a TA binding change, your FIRST action is to grep the host delegate call site for that op.** (I violated this on #121: reviewed the TA `mint_label_digest` in isolation, APPROVED, and missed that the host still passed `delegate=false` → strict mint dead. The user's Codex caught it. Inexcusable — I had verified this exact invariant in #113/#114/#116 the same session.)
  - **SDK ↔ TA ↔ on-chain contract**: any digest/commitment must match across all three (the #137 grant-packing class).
  - **proto wire change** → host + TA co-deploy; partial deploy + bincode trailing bytes = silently-ignored new fields.
  - **An op's commitment must bind the OPERATION/ENDPOINT itself** — two ops that can produce the same commitment (e.g. empty-label `create` vs `refresh`, same tag) are cross-replayable: the user's signature is over the commitment, so command-dispatch separation does NOT prevent replaying one op's assertion into another. The endpoint/op must be in the digest (distinct tag).
  - **Feed Codex BOTH sides of every coupling** (TA binding AND host delegate; SDK AND contract). If you only paste the changed side, Codex is blind to the inconsistency too — that's how my #121 Codex pass also missed the host delegate.
- 🔴 **For commitment / signature schemes, byte-matching the digest is NOT enough — verify BOTH parties can actually OBTAIN every bound input at the moment they must compute it.** A commitment over a field the client can't know (server-assigned id, host-derived value) is *unsatisfiable* under strict mode even if the SDK and TA hash it identically. (Proven: I approved AirAccount#118 + aastar-sdk#138 mint-param binding — verified the digest matched byte-for-byte — but missed that `index`/`ttl`/`subject` are server-derived, so the client ceremony can't compute the commitment → strict mint would break. Reverted in AirAccount#120.) Ask: "at ceremony time, does the committing side already hold every committed field?" If not, the scheme is broken regardless of byte-parity.

### Feed full context to DeepSeek and Codex (HARD — their errors are context-starvation)

DeepSeek's false positives and Codex's "INSUFFICIENT_CONTEXT / can't fetch" are almost always missing-context, not model weakness. So:
- **DeepSeek R1**: pass the compressed diff **plus the relevant contract/source snippets** the finding depends on (e.g. the EIP-712 typehash, the storage layout, the verifier function) inline in the prompt. Don't make it guess the upstream shape.
- **Codex R3 (PK)**: pass the diff + the post-R2 findings + **the cross-layer source it must check** (e.g. both the SDK encoder and the on-chain/TA verifier, the op→flag mapping) inline. NEVER rely on Codex fetching the diff itself. Give it a concrete claim to refute and the evidence to refute it with.
  - 🔴 **Paste source VERBATIM — never hand-summarize a struct / domain / signature / type when feeding Codex.** Copy the exact lines from the file. If you retype or "simplify" a definition you WILL drop a field, and Codex will report a guaranteed false positive on the field you elided. (Proven: aastar-sdk#137 — I summarized an EIP-712 domain without its `chainId`; Codex immediately raised a bogus `[High]` cross-chain-replay finding. The field was in the actual code.) Whenever Codex flags a missing field/check, FIRST re-grep the real source before believing it — the omission is usually in your prompt, not the code.

## v4 vs v3 Evaluation

After every 5 PRs (or on demand), compare v4 vs v3 pipeline quality:

**Metrics to track in model_eval_db:**
| Metric | v3 baseline | v4 target | How to measure |
|--------|-------------|-----------|----------------|
| DeepSeek R1 false-positive rate | ~60% (this session) | < 40% | R1 rejected by Opus R2 / R1 total |
| Unique security findings from R1b | 0 (no R1b in v3) | > 0 per security PR | count R1b-only confirmed findings |
| Opus R2 independent findings | 0 (no Opus R2 in v3) | > 0 on non-trivial PRs | count R2_INDEPENDENT non-empty |
| Codex challenge rate | ~20% of findings | stable | Codex CHALLENGE / total Codex input |
| Final verdict quality | subjective | fewer RC-to-APPROVE flips | track post-review author feedback |

**Run after 10+ v4 PRs:**
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/model_eval_db.py provider-summary --limit 50
# Filter by date > v4 launch (2026-06-19) to isolate v4 results
```

**Rollback trigger:** if DeepSeek false-positive rate doesn't improve after 10 PRs, OR Opus R2 costs make the loop prohibitive, revert:
```bash
cp ~/.claude/skills/pr-daemon-loop/SKILL.md.bak-v3-20260619 ~/.claude/skills/pr-daemon-loop/SKILL.md
```

## Triage validation (run periodically)

```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py audit --repo OWNER/REPO --pr N --found-issue true|false
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py flag-miss --repo OWNER/REPO --pr N --note "..."
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py report
# Target: false-negative < 5%
```

## Mandatory Per-PR Checklist

```
[ ] poll_prs.py surfaced this PR (new/head-changed, in-scope org)
[ ] compressed the diff → /tmp/pr-N-compressed.diff (noted dropped files if any)
[ ] if issue linked: fetched issue DoD + drafted Issue compliance section
[ ] R1a: DeepSeek full review → /tmp/pr-N-r1a.md
[ ] R1b: DeepSeek security-only → /tmp/pr-N-r1b.md  (parallel with R1a)
[ ] Sonnet merged R1a+R1b → /tmp/pr-N-r1-merged.md (deduplicated)
[ ] confirmed 2/4-round triage (security hard-rule → force 4; uncertain → escalate)
[ ] recorded triage decision (triage_db.py)
[ ] 2-round: Sonnet verdict directly
[ ] 4-round: Opus R2 read diff independently + challenged R1 → /tmp/pr-N-r2.md
[ ] 4-round: post-R2 gate applied (Medium+ → Codex R3; all-Low → skip)
[ ] 4-round: if Codex ran → targeted hunks only (±20 lines per Opus-confirmed Medium+)
[ ] 4-round: Opus R4 got full compressed diff + all round context → final verdict
[ ] verdict is APPROVE or REQUEST_CHANGES (not COMMENT)
[ ] respected Codex's points one by one (if Codex ran)
[ ] posted via post_pr_review.sh (PAT, no account switching)
[ ] scored DeepSeek R1a+R1b separately in model_eval_db
[ ] printed per-PR v4 eval delta (R1 confirmation rate, Opus R2 independent findings)
[ ] updated pr_watch_targets in SQLite
```

## Hard Rules

- **NEVER MERGE.** Pure reviewer — APPROVE or REQUEST_CHANGES only. `$pr-fix` handles merging.
- **Sonnet is executor only** — no judgment on 4-round PRs. Sonnet formats, runs scripts, merges lists.
- **Opus makes the 4-round final call** — Sonnet does NOT override or second-guess Opus's verdict.
- **Codex PK targets Opus R2 findings** (not DeepSeek R1 findings) — challenge the best analysis.
- **Security-sensitive PRs always go 4-round** — no downgrade.
- **Never COMMENT-limbo** — always APPROVE or REQUEST_CHANGES.
- **Never `gh pr review` directly** — always `post_pr_review.sh`.
- **Scope = `~/.config/prbot/repos.conf`** — review iff the repo is listed there. That file is the
  allowlist and it DOES include individually added personal repos (e.g. `jhfnetboy/CMIC`); see
  ABSOLUTE CONSTRAINT #4. (This line used to read "3 orgs only — never personal PRs", which
  contradicted constraint #4 and made a reviewer stop mid-run to ask which one to obey.)
- **Always score R1a+R1b separately** — the dual-pass split is the key v4 innovation to measure.
- **Codex gets targeted hunks, NOT full diff** — ±20 lines per Opus-confirmed Medium+ finding.
- **Opus R4 always gets full compressed diff** — missed-finding scan requires full context.
- **Post-R2 all-Low → skip Codex** — Opus R4 covers with full diff sweep.
- **Track v4 vs v3 metrics** every 5 PRs — if no improvement, rollback.

## ⛔ Mandatory self-assessment — END every review with this (HARD — user reprimanded)

After posting the verdict for a PR, the **chat reply** must close with a compact self-assessment block. This is non-negotiable and exists because the reviewer repeatedly mislabeled solo-Opus reviews as multi-round.

```
🔎 自评 — OWNER/REPO#N
- 轮数: <实际跑了几轮>  (skill 要求: <triage 要求几轮>)  → 一致? ✅/❌
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): <喂了什么 context? 产出?>  — NOT OPTIONAL, no "未跑—原因" escape (见 ABSOLUTE CONSTRAINT #5)。
    真没跑 = 本轮不合格，必须现在补跑再收尾，不能带着"未跑"过关。
  · R2 Opus: <读了什么/跑了什么工具(forge/cast/eth_call)/cross-layer 验了什么>
  · R3 Codex: <ran? 喂了什么 context inline? CHALLENGE/CONFIRM>  | 或 "未跑 — 原因(如 529)"
  · R4 Opus 裁决: <verdict>
- 机械证据: <列实跑的工具命令 + 结果，如 "cast call gToken()→canonical ✓">  | 或 "无 — 应补"
- **DeepSeek flash 评级**: <1-5> — <一句话：这轮它的 finding 有没有站得住？假阳性？漏了什么后面轮次/我自己抓到的？>
  一句话改进建议(如有): <prompt 更紧/喂更多 context/diff 范围更窄 等>
- 与 skill 设计是否一致: <一致 / 偏差点>
- 改进建议: <若我偷工 → 怎么补; 若 skill 本身该改 → 具体改什么>
```

Rules for the self-assessment:
- **Be truthful about gaps.** If you skipped a round or a tool you should have run, say so here and either run it now or flag it — do NOT paper over it.
- **R1 DeepSeek is the one exception with no "skip" escape hatch** — every other round (R2/R3/R4) may legitimately be "未跑 — 原因" per triage, but R1 must always have actually run (see ABSOLUTE CONSTRAINT #5). If you find yourself about to write "R1 未跑" here, stop and go run it before finishing the review.
- If the round count or model usage **deviated from what the triage required**, the self-assessment must state the deviation AND the corrective action (run it now / re-review).
- If the deviation reveals a **skill-process problem** (e.g. a step that's unrealistic, or context that should be auto-fed), include a concrete **skill-improvement recommendation** here, and offer to edit the skill.
- This block is part of the terse chat reply [[feedback_terse_chat_output]] — keep it compact, but it is the one place where listing per-round/per-model detail is REQUIRED (not "see PR comment").
