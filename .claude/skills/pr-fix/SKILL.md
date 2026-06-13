---
name: pr-fix
description: Fix and merge PRs across two categories — (1) jhfnetboy's own PRs with RC/comments: fix code, self-review, push, loop with pr-daemon-loop until APPROVE; (2) Bot PRs (dependabot/renovate): inline review, merge if clean, report to user if RC. Three-tier escalation for human PRs. Triggered by "$pr-fix", "$pr-fix OWNER/REPO", or "$pr-fix OWNER/REPO#N".
origin: pr-daemon
---

<!-- INSTALL NOTE
When installed globally via install-skills.sh --global, PR_DAEMON_ROOT is patched to the absolute
path of the PR-Daemon repo. When installed directly in the project, run from the PR-Daemon root.
-->

# PR Fix Skill — Autonomous self-fix for jhfnetboy's PRs

> ⛔ **ABSOLUTE CONSTRAINT #1 — Two categories only**
> Process only: (A) PRs authored by `jhfnetboy`, and (B) Bot PRs authored by `dependabot[bot]`, `app/dependabot`, `renovate[bot]`, `renovate`.
> Never touch PRs by other humans, even if RC'd.
>
> ⛔ **ABSOLUTE CONSTRAINT #2 — No force push, no --amend to published commits**
> Always add NEW commits on top of the existing branch. Never rewrite history that's already on the remote.
>
> ⛔ **ABSOLUTE CONSTRAINT #3 — Self-review MUST pass before pushing**
> Code fixes must clear the self-review pipeline before any `git push`. A failing self-review = iterate, not push.
>
> ⛔ **ABSOLUTE CONSTRAINT #4 — Never modify other people's business logic**
> You are fixing a specific reviewed issue. Do not refactor surrounding code, rename symbols, or make "while I'm here" changes outside the scope of the review comment.
>
> ⛔ **ABSOLUTE CONSTRAINT #5 — Skip ambiguous comments, report to user**
> If a review comment is subjective, architectural, or unclear — do NOT guess. Mark it `SKIP` and report it. The user decides.

## Three-Tier Escalation (CRITICAL — classify every PR before touching anything)

### Tier A — AUTO-FIX (execute autonomously)

ALL of the following must be true:
- Fix type: docs / typo / comment / style / parameter rename / dep bump / adding a comment
- OR: single-function code fix with a 1:1 mapping from review comment to code line
- Changed logic lines ≤ 30 (net insertions/deletions of non-blank, non-comment lines)
- Does NOT redesign a flow or change a public API contract
- Risk: Low — even if the fix is wrong, the blast radius is contained to one function

→ **Proceed directly** through Steps 1–8 without user confirmation.

### Tier B — PLAN-FIRST (show fix plan, wait for user approval)

ANY of the following triggers Tier B:
- Touches multiple files across different modules (>2 files in different dirs)
- Code fix involves logic restructuring, not just a parameter/key format change
- Changes a public API signature, auth flow, or data schema
- The review comment says "refactor", "redesign", "rethink", "move", "replace"
- 4-round triage (security-sensitive) AND changed logic lines > 30
- Fix requires understanding call chains beyond the immediate function

→ **STOP. Show the plan first:**

```
🔍 PLAN REQUIRED — MushroomDAO/CometENS#4  [Tier B: complex]

Review findings to address:
  [High] F1: nonce key missing chainId — consumeNonce() in workers/api/src/index.ts
  [Medium] F2: gateway singleton stale env — workers/gateway/src/index.ts

Proposed fix plan:
  1. consumeNonce(kv, from, nonce, deadline)
       → consumeNonce(kv, chainId, from, nonce, deadline)
       key: nonce:${from}:${nonce} → nonce:${chainId}:${from}:${nonce}
       Callers: 7 call sites in handleManage()
       Files: workers/api/src/index.ts only
       Risk: Low — key format change breaks no existing sessions (nonces are one-time-use)

  2. getGateway() singleton key
       Current: `${env.ETH_RPC_URL}|${env.OP_RPC_URL}|${env.NETWORK}`
       Proposal: add comment clarifying L2_RECORDS_ADDRESS is read per-request
       Files: workers/gateway/src/index.ts only
       Risk: Informational — no logic change

Self-review: 4-round (security-sensitive)
Estimated diff: ~25 lines

Approve this plan? (reply "yes" / "no" / "change X to Y")
```

**Do NOT write any code or touch any file until the user replies "yes" (or a variant).** If the user requests changes to the plan, update the plan and show it again. Only after explicit approval proceed to Steps 3–8.

### Tier C — SUGGEST ONLY (no code changes, no file edits)

ANY of the following triggers Tier C:
- Changed logic lines > 150 in the PR diff (very large PR)
- Touches core contract (`contracts/src/*.sol`) in non-trivial ways (not just adding a comment)
- Cross-cutting: fix requires coordinated changes across ≥ 3 modules or ≥ 2 repos
- Security critical involving token economics, upgrade proxies, access control role assignments, or fee/reward math
- The fix requires running tests you cannot run locally (e.g., real hardware, deployed testnet state)
- The review comment explicitly says "consider a different architecture" or "this needs a design discussion"
- Multiple prior RC rounds with no APPROVE → PR has a systemic issue, not a one-shot fix

→ **STOP. Report with suggestions, no code written:**

```
🚫 SUGGEST-ONLY — AAStarCommunity/SuperPaymaster#5  [Tier C: too large / too risky]
   PR URL: https://github.com/AAStarCommunity/SuperPaymaster/pull/5
   Branch: <headRefName>

Reason: <one sentence — e.g. "Core contract logic change + >200 logic lines, risk of
         unintended state machine effects">

Review findings:
  [High] F1: file:line — issue description
  [High] F2: file:line — issue description

Suggested approach:
  Option A: <description + risk>
  Option B: <description + risk>

Recommendation: <which option and why>

Suggested next step: Handle this directly in the business repo
  cd /Users/jason/Dev/aastar/SuperPaymaster
  git checkout <headRefName>
  # Start a Claude Code session there for full context
  # Or copy the PR URL above to share with the repo maintainer
```

**No files are created or modified in Tier C.** Only report and suggest.
Always include the PR URL prominently so the user can copy it to the relevant repo.

## What "self-review" means here

**Self-review = internal fix quality check, NOT the official clestons review.**

Before pushing, we run a mini-pipeline on the *fix diff* (not the original PR diff) to
catch mistakes in the fix itself:
- 2-round: DeepSeek R1 flags issues → Sonnet decides go/no-go
- 4-round: DeepSeek R1 → Sonnet R2 challenge → Codex PK → Opus final verdict

After self-review passes and the fix is pushed, we then add `clestons` as reviewer
(`gh pr edit --add-reviewer clestons`). That triggers the official `$pr-daemon-loop`
review cycle, which is a separate, independent review of the full updated PR.

```
fix diff self-review (jhfnetboy internal)     official PR review (clestons)
─────────────────────────────────────────     ──────────────────────────────
DeepSeek R1  →  Sonnet [→ Codex → Opus]   →  push  →  $pr-daemon-loop reviews full PR
"is the fix itself correct?"                  "is the whole PR ready to merge?"
```

## Roles

| Role | Model | When |
|------|-------|------|
| Triage + comment parsing + fix drafting | Sonnet (this session) | always |
| Mechanical review of **fix diff** | DeepSeek API | R1, both paths |
| Challenge (code/security changes) | Sonnet (this session) | R2, 4-round only |
| Final authority on fix quality | Opus subagent | 4-round only |
| PK adversary | Codex agent | 4-round only |
| Final authority (docs/simple) | Sonnet (this session) | 2-round |

## Review Rounds (Tier A auto-fix and Tier B post-approval)

**2-round** (DeepSeek R1 → Sonnet verdict): ALL of these must be true:
- Fix type is docs / typo / comment / style / formatting / dep version bump
- Does NOT touch `src/` `contracts/` `lib/` `kms/` real logic
- No new public API / schema / auth change

**4-round** (DeepSeek R1 → Sonnet R2 → Codex PK → Opus verdict): ANY of these:
- Touches source code (`*.rs`, `*.sol`, `*.ts`, `*.js` in `src/` `contracts/` `kms/`)
- Security-sensitive: auth, crypto, payment, token, permission
- Fixes a logical bug (not just formatting)
- Unclear risk → escalate to 4-round

## Step 1 — Discover PRs needing fixes

```bash
# Scan all 3 orgs — both jhfnetboy PRs and bot PRs
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --needs-fix-only

# Only jhfnetboy's own PRs
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --human-only --needs-fix-only

# Only bot PRs (dependabot / renovate)
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --bot-only --needs-fix-only

# Single repo or PR
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --repo OWNER/REPO --needs-fix-only
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --repo OWNER/REPO --pr N

# JSON for programmatic use
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --needs-fix-only --output json
```

Output icons:
- `🔴` jhfnetboy PR — CHANGES_REQUESTED, needs code fix
- `🟡` jhfnetboy PR — APPROVED + reviewer comments, needs follow-up
- `🤖` Bot PR (dependabot/renovate) — unreviewed or RC, needs review+merge action
- `✅` clean, skip

**Queue priority:** 🔴 first → 🤖 second → 🟡 last

## Step 1b — Bot PR path (🤖 PRs, separate from human PR flow)

Bot PRs (dependabot / renovate) cannot push new commits — they follow a different path:

```
For each 🤖 bot PR:
  1. Run inline pr-daemon-loop review (same 2/4-round pipeline, clestons posts verdict)
  2. Check verdict:
     APPROVE (no blocking findings):
       → gh pr merge N --repo OWNER/REPO --squash --auto   # jhfnetboy account
       → verify: gh api user -q .login  # must be jhfnetboy
       → report: ✅ OWNER/REPO#N merged (bot PR, clean)
     CHANGES_REQUESTED (has blocking findings):
       → Tier C report to user — cannot auto-fix bot PR
       → Include PR URL + findings + suggestion
       → Do NOT merge, do NOT modify any files
```

Bot PR triage is always **2-round** (dependency bump = low risk by default) UNLESS:
- the diff touches non-trivial code (e.g. a major version bump with breaking API changes) → 4-round

After handling all 🤖 bot PRs, continue to Step 2 for 🔴/🟡 human PRs.

## Step 2 — Parse review comments → classify tier

For each open review comment or REQUEST_CHANGES body:

1. **Classify the comment**:
   - `MECHANICAL` — clear, code-level fix (add missing check, rename, format, fix bug per the description)
   - `DESIGN` — architectural question, requires user decision → SKIP, report
   - `QUESTION` — author asked something, not a change request → SKIP
   - `RESOLVED` — already addressed in a later commit → SKIP

2. **Classify the PR tier** (A / B / C) using the criteria above.

3. **Build a fix plan** for MECHANICAL items:
   ```
   Comment: "nonce key missing chainId"
   File: workers/api/src/index.ts
   Fix: Add chainId param to consumeNonce(); change key to nonce:${chainId}:${from}:${nonce}
   Callers affected: 7
   Risk: Low — one-time-use nonces, key change doesn't break existing sessions
   Triage: 4-round (security-sensitive)
   Tier: B (4-round + multi-callsite, show plan first)
   ```

4. If no MECHANICAL items → report to user, exit.

## Step 3 — Checkout local branch

```bash
# Resolve local path from config/repo-roots.json
python3 PR_DAEMON_ROOT/scripts/resolve_repo.py OWNER/REPO
# → /Users/jason/Dev/aastar/SuperPaymaster

# Verify git identity before touching anything
cd /path/to/repo
git config user.name    # should be jhfnetboy or Jason
git config user.email   # should match

# Fetch + checkout the PR branch
git fetch origin
git checkout -b fix/pr-N-review origin/<headRefName>
# Or if branch already exists locally:
git checkout <headRefName> && git pull --rebase origin <headRefName>

# Confirm we're on the right branch and it's clean
git status
git log --oneline -3
```

**NEVER work on main/master.** Always work on the PR's source branch.

## Step 4 — Apply fixes

For each MECHANICAL fix item:

1. Read the relevant file(s) in full before editing
2. Apply the minimal change that addresses the review comment — nothing more
3. Re-read the changed file to verify the edit is correct
4. If the fix requires running a test or build to verify:
   - **Rust**: `cargo build -p <crate>` or `cargo test -p <crate>` (in the repo root)
   - **Solidity**: `forge build` / `forge test`
   - **JS/TS**: `node <file>` for syntax check, or existing test scripts
   - If the test environment isn't available, document it and proceed to self-review anyway
5. After all fixes applied, do a final `git diff` to confirm exactly what changed

```bash
git diff HEAD    # always review before staging
```

If any fix produces unexpected side-effects or can't be isolated → SKIP that fix, report to user.

## Step 5 — Self-review pipeline

Get the fix diff:
```bash
git diff HEAD > /tmp/fix-pr-N.diff
# Compress if large
python3 PR_DAEMON_ROOT/scripts/compress_diff.py --file /tmp/fix-pr-N.diff --budget 60000 > /tmp/fix-pr-N-compressed.diff
```

### 2-round path (docs/simple)

**R1 — DeepSeek:**
```bash
python3 PR_DAEMON_ROOT/scripts/deepseek_review.py \
  --diff-file /tmp/fix-pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/fix-r1-N.md
```

**Sonnet verdict (you):** Read DeepSeek's findings. If no blockers → PROCEED. If blockers → fix them and re-run R1.

### 4-round path (code/security)

**R1 — DeepSeek** (same as above)

**R2 — Sonnet challenge (you):** Work from DeepSeek's findings. Spot-check security hunks.
Output compactly: `CONFIRM <ids>` / `REJECT <id — why>` / `ADD <[Sev] file:line — issue | fix>`

**R3 — Codex PK (MANDATORY):**
```
Agent(subagent_type="codex:codex-rescue", prompt="""
PK CHALLENGE: fix for OWNER/REPO#N. Diff + R2 findings inline — do NOT re-fetch.
Per finding: [CHALLENGE|CONFIRM|MISSED] id — reason ≤20 words.
DIFF:
<paste compressed diff>
FINDINGS (post-R2):
<compact list>
Return ONLY the structured critique.
""")
```

**Opus verdict (MANDATORY for 4-round):**
```
Agent(subagent_type="general-purpose", model="opus", prompt="""
Final authority on fix for OWNER/REPO#N.
Is this fix correct, complete, and safe to push? Respect Codex point-by-point.
Output ONLY:
VERDICT: PUSH | DO_NOT_PUSH
BLOCKING: <issues if DO_NOT_PUSH>
CONFIRMED_SAFE: <items>
REJECTED_CONCERN: <concern — reason>
ROUNDS — R1(DeepSeek): <summary>  R2(Sonnet): <summary>  R3(Codex): <summary>
""")
```

**If self-review → DO_NOT_PUSH:** go back to Step 4, fix the blocking issues, re-run pipeline.
**Max 3 iterations.** If still failing after 3 → report to user, do NOT push.

## Step 6 — Commit and push

Self-review passed. Commit using the fix description:

```bash
cd /path/to/repo
git add -p    # stage only the intended changes (prefer selective staging)
git commit -m "fix: address review comments on PR #N — <summary>"

# Verify what we're about to push
git log --oneline origin/<branch>..HEAD
git diff origin/<branch>..HEAD

# Push
git push origin <branch>
```

**Commit message format:**
- `fix(scope): address review — <what was fixed>` for bug/code fixes
- `docs: address review — <what was fixed>` for docs-only
- Always reference the original PR in the body if multi-item

## Step 7 — Inline review cycle (fix → review → loop)

This is the core loop. After pushing, run the pr-daemon-loop pipeline inline for this
single PR (as clestons), check the verdict, then decide whether to loop again.

### 7a — Post fix comment + request review

```bash
gh pr comment N --repo OWNER/REPO --body "$(cat <<'EOF'
Addressed review comments (Round <N>):
- [list each fix applied]

Self-review passed (DeepSeek R1 + Sonnet [+ Opus + Codex] — no blockers).
Ready for re-review.
EOF
)"
gh pr edit N --repo OWNER/REPO --add-reviewer clestons
```

### 7b — Run pr-daemon-loop pipeline for this PR (inline, as clestons)

Execute the full pr-daemon-loop review pipeline for OWNER/REPO#N:

1. `gh pr diff N --repo OWNER/REPO > /tmp/pr-N-recheck.diff`
2. `python3 PR_DAEMON_ROOT/scripts/compress_diff.py ...`
3. R1 DeepSeek review
4. Triage confirm (2-round or 4-round) — use same triage rules as pr-daemon-loop
5. [2-round] Sonnet verdict directly
   [4-round] Sonnet R2 → Codex PK → Opus verdict
6. Write verdict to `/tmp/review-N-roundN.md`
7. Post via `bash PR_DAEMON_ROOT/scripts/post_pr_review.sh --repo OWNER/REPO --pr N --body-file /tmp/review-N-roundN.md [--approve | --request-changes]`
8. Verify account restored: `gh api user -q .login`

Record the verdict: **APPROVE** or **CHANGES_REQUESTED**.

### 7c — Loop decision

```
if verdict == APPROVE:
    → go to Step 8 (done ✅)

if verdict == CHANGES_REQUESTED:
    loop_round += 1
    if loop_round >= 3:
        → ESCALATE: report to user — "3 fix rounds exhausted, same issues persist"
        → show remaining findings, ask user how to proceed
        → STOP loop
    
    # Check for no-progress: same finding IDs recur after fix
    if new_findings ∩ prev_round_findings is substantial (>50% overlap):
        → ESCALATE: report to user — "no progress after round N, findings unchanged"
        → STOP loop
    
    # New findings or different issues — continue
    → go back to Step 2 (parse new RC comments), next round
```

**Loop termination summary:**

| Condition | Action |
|-----------|--------|
| APPROVE received | ✅ Done — report to user, ready to merge |
| Tier C detected in any round | 🚫 Stop — suggest only, report |
| Tier B plan rejected by user | ⏸ Stop — await user decision |
| 3 rounds exhausted | ⚠️ Escalate — report to user, stop |
| Same findings recur (no progress) | ⚠️ Escalate — report to user, stop |
| Self-review DO_NOT_PUSH × 3 | ⚠️ Escalate — don't push, report |

**NEVER merge.** When APPROVE is reached, report to user and stop. Merging is the author's call.

## Step 8 — Final report

```
✅ OWNER/REPO#N  APPROVED after N fix round(s)
   PR URL: https://github.com/OWNER/REPO/pull/N
   Rounds: [Round 1: fixed X, Y → RC] [Round 2: fixed Z → APPROVE]
   Total self-review rounds: N (2-round/4-round)
   Ready to merge — this is your call.

🔧 OWNER/REPO#N  [TIER A|B] ROUND N PUSHED — awaiting clestons review
   Fixed: <list of MECHANICAL items addressed>
   Skipped: <DESIGN/QUESTION items>
   Self-review: PASS
   Pushed: <branch> @ <commit>

⚠️  OWNER/REPO#N  ESCALATED — <reason>
   PR URL: https://github.com/OWNER/REPO/pull/N
   <details for user>

⚠️  OWNER/REPO#N  [TIER B] PENDING YOUR APPROVAL
   <plan text>

🚫 OWNER/REPO#N  [TIER C] SUGGEST-ONLY
   PR URL: https://github.com/OWNER/REPO/pull/N
   Branch: <headRefName>
   <reason + option A/B + recommendation>
```

## What to SKIP (report to user instead of fixing)

| Comment type | Action |
|---|---|
| "Consider using X instead of Y" without clear correctness reason | SKIP — design choice |
| "Why did you do this?" | SKIP — question, not a fix request |
| "This could be improved by..." | SKIP — suggestion, not RC |
| Multi-file architectural restructuring | SKIP — scope too large |
| Requires running tests you can't run (e.g., real hardware) | SKIP — report required test |
| Comment on someone else's code (not jhfnetboy's PR) | Never process |

## Hard Rules

- **Two categories only** — jhfnetboy's PRs (fix+review loop) and bot PRs (review+merge). Never touch other human PRs.
- **Bot PRs: merge only after APPROVE with no blocking findings** — use `gh pr merge --squash --auto` as jhfnetboy
- **Bot PRs with RC: Tier C report, never merge** — cannot auto-fix; report to user with PR URL
- **Human PRs: NEVER merge** — APPROVE is the endpoint; merging is the author's call
- **No force push** — new commits only
- **Self-review MUST pass** before push — no exceptions
- **Minimal diff** — fix only what the review comment says
- **Max 3 fix rounds in the loop** — escalate to user if still RC after 3 rounds
- **No-progress detection** — if >50% of findings recur unchanged, escalate immediately
- **NEVER MERGE** — loop ends on APPROVE; merging is always the author's call
- **Tier B: NO CODE before user says yes** — show plan, wait, only proceed after explicit approval
- **Tier C: NO CODE, NO FILES** — only report and suggest
- **NEVER use `gh pr review`** directly — always use `post_pr_review.sh`
- **Always verify git identity** before committing: `git config user.name` should be jhfnetboy
- **Always verify account restored** after each clestons post: `gh api user -q .login`
- **Skip + report** is always safer than a wrong fix
