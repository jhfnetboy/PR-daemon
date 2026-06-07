---
name: pr-daemon-loop
description: Full 24/7 autonomous PR review loop. Discovers all open PRs for the configured author across configured orgs, deep-reviews as the primary model, calls Codex as PK challenger, posts findings via the review account, and loops continuously. Use when the user says "run PR daemon", "start 24/7 review", "keep reviewing PRs", or "start the review loop".
origin: pr-daemon
---

<!-- INSTALL NOTE
When installed globally via install-skills.sh --global, PR_DAEMON_ROOT is patched to the absolute
path of the PR-Daemon repo. When used directly in the project, run from the PR-Daemon root directory.
-->

# PR Daemon Loop

> ⛔ **ABSOLUTE CONSTRAINT #1 — No Merge**
> PR-Daemon is a **review-only** system. It MUST NEVER merge any PR under any circumstances.
> Even if the verdict is APPROVE, merging is the PR author's or maintainer's sole decision.
> Do not run `gh pr merge`, do not click merge, do not trigger any merge operation — ever.
> Allowed GitHub write operations: post review comment / request changes / approve. Nothing else.
>
> ⛔ **ABSOLUTE CONSTRAINT #2 — PR must be reviewed individually, one at a time**
> Each PR goes through the FULL 7-step loop independently. Do NOT batch-scan many PRs and
> produce bulk APPROVEs. Even a trivial PR (typo fix, readme edit) gets individual treatment:
> read the diff → form findings → PK challenge → post → record. A trivial PR's PK round can be
> quick, but it MUST exist.
>
> ⛔ **ABSOLUTE CONSTRAINT #3 — PK is NEVER optional**
> Every single PR review MUST go through Step 4 (PK Challenge via Codex) before posting.
> No exceptions based on confidence, triviality, volume, or the number of remaining PRs.
> If Codex is unavailable, retry or wait — do not proceed without PK.
>
> ⛔ **ABSOLUTE CONSTRAINT #4 — Double Review for PRs >100 lines changed**
> If a PR's total diff exceeds **100 lines** (additions + deletions), run a **second PK round**
> after the first round is complete and findings are adjudicated. Round 2 sends the ADJUDICATED
> findings (with what was confirmed/rejected/added) back to Codex for a final adversarial pass.
> This catches mistakes in the first round's adjudication. Round 2 report is included in the final review.
> Count lines: `gh pr diff N --repo OWNER/REPO | wc -l`

## Configuration

Read these values at the start of every session:

```bash
# Load env vars (accounts, API keys, org roots)
source PR_DAEMON_ROOT/.env 2>/dev/null || true
source PR_DAEMON_ROOT/scripts/load_pr_daemon_env.sh 2>/dev/null || true

PR_DAEMON_MAIN_USER="${PR_DAEMON_MAIN_USER:-jhfnetboy}"
PR_DAEMON_REVIEW_USER="${PR_DAEMON_REVIEW_USER:-clestons}"
PR_DAEMON_STATE_DIR="${PR_DAEMON_STATE_DIR:-PR_DAEMON_ROOT/.state/pr-daemon}"

# Org roots come from config/repo-roots.json
python3 PR_DAEMON_ROOT/scripts/resolve_repo.py --list 2>/dev/null || true
```

## What This Skill Does

You (Claude Code as primary reviewer) run a closed autonomous loop:

1. Discover all open PRs authored by `$PR_DAEMON_MAIN_USER`.
2. Pick the next un-reviewed (or head-changed) PR.
3. Deep-review the diff independently.
4. Challenge findings via `codex exec` (PK round).
5. Post the final verdict as `$PR_DAEMON_REVIEW_USER`.
6. Record results in SQLite + Markdown.
7. Repeat. When all done, wait and check for new/changed PRs.

Never modify business code. Never merge. Post only after approval or in autonomous mode.

## Mandatory Per-PR Completion Checklist

Before posting ANY review, you MUST answer YES to ALL of these:

```
[ ] Did I read the actual diff for THIS PR?                (not from memory, not from the list scan)
[ ] Did I form independent findings from the diff?          (not copied from another PR)
[ ] Did I invoke Agent(codex:codex-rescue) PK challenge?    (MANDATORY — not skipped, not "obvious")
[ ] Did I read Codex's response and adjudicate each item?   (not just the summary)
[ ] Did I write a review with individual findings?          (not "looks good" / "LGTM")
[ ] Did I post via post_pr_review.sh?                       (not gh pr review or gh pr comment directly)
[ ] Did I record results via model_eval_db.py record-run?   (Mandatory — even for trivial APPROVEs)
[ ] Did I update pr_watch_targets status in SQLite?         (Mandatory — sets last_reviewed_head_oid)
[ ] Did I report the per-PR status counter?                 (open N, reviewed M [changes: X, approve: Y, else: Z])
[ ] Did I estimate and log the token cost for this PR?       (via python3 scripts/token_cost.py --add IN OUT)
```

If any box is unchecked → go back to that step and complete it. **No "bulk done" shortcuts.**

## Loop Entry

When the user starts the daemon, announce:

```text
PR Daemon starting. Reviewing open PRs by $PR_DAEMON_MAIN_USER.
Review account: $PR_DAEMON_REVIEW_USER. PK challenger: codex.
Will not merge any PR. Beginning scan...
```

## Step 1 — Discover Open PRs (3 Orgs Only)

**ONLY review PRs in these 3 orgs: `AAStarCommunity`, `AuraAIHQ`, `MushroomDAO`.**
Never review PRs from `jhfnetboy` (personal) or any other org — skip them immediately.

Use `prbot all` to discover the queue (it reads `~/.config/prbot/repos.conf`):

```bash
gh search prs --author "$PR_DAEMON_MAIN_USER" --state open \
  --json number,title,repository,url,updatedAt,isDraft,headRefOid,baseRefName \
  --limit 100
```

Or use the helper:

```bash
python3 PR_DAEMON_ROOT/scripts/list_open_prs.py --json
```

Skip `isDraft: true` PRs unless the user explicitly includes drafts.

Check if already reviewed at the current head:

```bash
sqlite3 "$PR_DAEMON_STATE_DIR/pr-watch.sqlite" \
  "SELECT status, last_reviewed_head_oid FROM pr_watch_targets WHERE repo='OWNER/REPO' AND pr_number=N;"
```

If `last_reviewed_head_oid` matches the current `headRefOid` → skip.

Priority: new PRs → head changed → `CHANGES_REQUESTED` with new commit → `updatedAt DESC`.

## Step 2 — Resolve Local Checkout

```bash
python3 PR_DAEMON_ROOT/scripts/resolve_repo.py OWNER/REPO
```

Org-to-local mappings are in `PR_DAEMON_ROOT/config/repo-roots.json`. If a local checkout exists, use it. Clone into the configured root otherwise. Never use `/tmp` for normal PR checkouts.

Fetch and get the diff:

```bash
cd ~/Dev/ORG/REPO
git fetch origin
git diff $(git merge-base origin/BASE_REF origin/HEAD_REF)..origin/HEAD_REF > /tmp/pr-diff.patch
# or
gh pr diff PR_NUMBER --repo OWNER/REPO --patch > /tmp/pr-diff.patch
```

## Step 3 — Deep Review

**One PR at a time. NEVER batch-review multiple PRs together. NEVER bulk-approve a list of PRs.**

Read the diff. Then read the changed functions and their immediate callers. Focus on:

- **Correctness bugs**: logic errors, wrong conditions, off-by-one
- **Security**: injection, broken auth, access control, supply chain
- **Concurrency / race conditions**: shared state, async misuse
- **Data loss**: missing rollbacks, wrong error handling
- **API contract breaks**: changed interfaces, missing migration
- **Missing tests**: especially for the changed code path
- **CI/config issues**: broken builds, misconfigured gates

Form findings independently **before** reading any prior review output.

Optional breadth pass after forming independent findings:

```bash
python3 PR_DAEMON_ROOT/skills/pk-review/scripts/local_review.py \
  --repo ~/Dev/ORG/REPO \
  --diff-file /tmp/pr-diff.patch \
  --eval-db PR_DAEMON_ROOT/reviews/model-evals/model-evals.sqlite \
  --owner OWNER --repo-name REPO --pr-number N \
  --output /tmp/breadth-pass.md
```

## Step 4 — PK Challenge (Codex as Adversarial Challenger) — MANDATORY, NEVER SKIP

**This step is required for every single PR review. Do not skip even if confident. No review may be posted without a completed PK challenge round.**

**Use the Agent tool with `subagent_type: "codex:codex-rescue"` — NOT `codex exec` CLI. The CLI spawns a fresh sandbox with 30–90s cold-start overhead; the Agent tool uses the shared runtime and is much faster.**

Invoke the Agent tool (not Bash) with this prompt:

```
Agent(
  subagent_type = "codex:codex-rescue",
  prompt = """
PK CHALLENGE for OWNER/REPO#N:

Read the diff with: gh pr diff N --repo OWNER/REPO --patch

Adversarially challenge each finding below. For each, return EXACTLY ONE of:
- [CHALLENGE] <finding> — counter-evidence or false-positive reason
- [CONFIRM] <finding> — independent supporting evidence
- [MISSED] <new finding> — real issue not in the list

Findings to challenge:
<YOUR_FINDING_LIST_HERE>

Do NOT post anything to GitHub. Return ONLY the structured critique.
"""
)
```

Read the critique. Accept valid challenges (mark Rejected). Verify Missed items independently.

**Double Review Rule — PRs with >100 lines changed:**
```bash
# Check diff size BEFORE review
LINES=$(gh pr diff N --repo OWNER/REPO | wc -l)
if [ "$LINES" -gt 100 ]; then
  echo "PR超过100行($LINES lines)，需要double review"
fi
```
If diff >100 lines, after adjudicating Round 1 findings, invoke a **second PK round** sending the adjudicated results back:
```
Agent(subagent_type="codex:codex-rescue", prompt="""
PK CHALLENGE ROUND 2 for OWNER/REPO#N:
Re-examine the adjudicated findings from Round 1. Challenge any CONFIRMED findings that may still be wrong. Look for new MISSED issues overlooked by Round 1.
ADJUDICATED FINDINGS: <paste adjudicated list with Confirmed/Rejected/PK-added>
""")
```
Incorporate Round 2 results into the final review. Mark Round 2 challenges/additions separately.
Normal PRs (≤100 lines): max 2 rounds total (one PK round). Double-review PRs (>100 lines): exactly 2 PK rounds required.

## Step 5 — Post as Review Account

Write the review and post using the account-switching script:

```bash
cat > /tmp/review-OWNER-REPO-N.md << 'EOF'
## Review: OWNER/REPO#N

Verdict: REQUEST_CHANGES | APPROVE | COMMENT

### Findings
...

### PK Summary
...
EOF

# This script switches to $PR_DAEMON_REVIEW_USER, posts, then restores $PR_DAEMON_MAIN_USER
bash PR_DAEMON_ROOT/scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr N \
  --body-file /tmp/review-OWNER-REPO-N.md \
  --request-changes   # or --approve or --comment

# Verify restored
gh api user -q .login
```

**Always use `post_pr_review.sh`** — never `gh pr review` directly (risks leaving the active account as the review account).

## Step 6 — Record Results

```bash
# Markdown artifact
cp /tmp/review-OWNER-REPO-N.md \
   PR_DAEMON_ROOT/reviews/OWNER-REPO-N-local-review-HEADOID-$(date +%Y-%m-%d).md

# SQLite
python3 PR_DAEMON_ROOT/scripts/model_eval_db.py record-run \
  --owner OWNER --repo REPO --pr-number N \
  --head-oid HEADOID --score SCORE --verdict REQUEST_CHANGES \
  --local-review-path PR_DAEMON_ROOT/reviews/OWNER-REPO-N-local-review-HEADOID-DATE.md \
  --useful-findings "..." --false-positives "..." --misses "..."

# Update watcher state
sqlite3 "$PR_DAEMON_STATE_DIR/pr-watch.sqlite" \
  "UPDATE pr_watch_targets SET last_reviewed_head_oid='HEADOID', status='changes_requested', last_reviewed_at=CURRENT_TIMESTAMP WHERE repo='OWNER/REPO' AND pr_number=N;"
```

## Step 6.5 — Per-PR Status Counter + Token Cost (MANDATORY after every PR)

After recording results for each PR, print BOTH:

### 6.5a — PR Status Counter

```bash
STATE_DB="PR_DAEMON_ROOT/.state/pr-daemon/pr-watch.sqlite"

# Count total PRs in 3 orgs
TOTAL=$(sqlite3 "$STATE_DB" "
  SELECT COUNT(*) FROM pr_watch_targets
  WHERE repo LIKE 'AAStarCommunity/%' OR repo LIKE 'AuraAIHQ/%' OR repo LIKE 'MushroomDAO/%';")

# Count reviewed by verdict
REVIEWED=$(sqlite3 "$STATE_DB" "
  SELECT COUNT(*) FROM pr_watch_targets
  WHERE status IN ('approved','changes_requested','comment')
  AND (repo LIKE 'AAStarCommunity/%' OR repo LIKE 'AuraAIHQ/%' OR repo LIKE 'MushroomDAO/%');")

CHANGES=$(sqlite3 "$STATE_DB" "
  SELECT COUNT(*) FROM pr_watch_targets
  WHERE status='changes_requested'
  AND (repo LIKE 'AAStarCommunity/%' OR repo LIKE 'AuraAIHQ/%' OR repo LIKE 'MushroomDAO/%');")

APPROVED=$(sqlite3 "$STATE_DB" "
  SELECT COUNT(*) FROM pr_watch_targets
  WHERE status='approved'
  AND (repo LIKE 'AAStarCommunity/%' OR repo LIKE 'AuraAIHQ/%' OR repo LIKE 'MushroomDAO/%');")

ELSE_COUNT=$((REVIEWED - CHANGES - APPROVED))
echo "📊 PR status: open $TOTAL, reviewed $REVIEWED [request changes: $CHANGES, approve: $APPROVED, else: $ELSE_COUNT]"
```

### 6.5b — Token Cost (local tokenizer, 0 API cost)

Estimate this PR's token usage and add it to cumulative tracking:

```bash
# Input tokens: estimate from the diff + conversation context for this PR
# Output tokens: estimate from the review + PK challenge response
# Rough estimate: 10K-50K input + 2K-10K output per trivial PR
#                 50K-200K input + 10K-50K output per complex PR

python3 PR_DAEMON_ROOT/scripts/token_cost.py --add INPUT_TOKENS OUTPUT_TOKENS

# Print cumulative
python3 PR_DAEMON_ROOT/scripts/token_cost.py --status
```

**Pricing reference (DeepSeek V4 Pro):** Input $0.435/M · Cache-hit $0.003625/M · Output $0.87/M

**Output format after each PR:**
```
📊 MushroomDAO/Sin90#2 COMMENT | PK: 1r (1 challenged, 1 confirmed, 1 added)
📊 PR status: open 54, reviewed 2 [request changes: 0, approve: 0, else: 2]
💰 Estimated this PR: ~45K tokens ≈ $0.02 | Cumulative: 100K tokens ≈ $0.05
```

## Step 7 — Loop

**After recording, move to the next queued PR — one at a time.** Do not skip to "finish off" remaining PRs without review. Each PR gets its own individual Step 3 → Step 4 → Step 5 → Step 6, in order.

When all queued PRs are done:

1. Re-scan GitHub for new or head-changed PRs (back to Step 1).
2. If nothing new: `sleep 300` (5 min), then scan again.
3. Log: `[LOOP] Cycle complete. Reviewed N PRs. Waiting...`

Continue until the user explicitly stops with Ctrl+C or says "stop the daemon".

## Hard Rules

- **NEVER MERGE** any PR — not even after APPROVE. `gh pr merge` is forbidden. Merging belongs to the PR author/maintainer only.
- **PK challenge is MANDATORY** — every PR review MUST invoke Codex as adversarial challenger (Step 4) before any post. No exceptions.
- **NO BATCH REVIEWS** — each PR goes through the full 7-step loop individually. Do not scan multiple PRs and bulk-approve them.
- **NO SKIPPING PK** — not for trivial PRs, not for confidence, not for volume. If Codex is down, retry or wait.
- **DOUBLE REVIEW for PRs >100 lines** — two mandatory PK rounds for large PRs. Check `gh pr diff N --repo OWNER/REPO | wc -l` before review.
- **Never modify** business repo source, config, tests, or lock files.
- **Never post** via `gh pr review` directly — always use `post_pr_review.sh`.
- **Never rely on `@me`** — always use `--author $PR_DAEMON_MAIN_USER`.
- **Verify `gh api user -q .login` equals `$PR_DAEMON_MAIN_USER`** after every GitHub operation.
- **Always record** both Markdown and SQLite for every completed review.
- **Maximum 2 PK rounds** per PR per head commit.

## Output Format

```text
Findings

[Confirmed] Severity - file:line - title
Evidence and fix.

[PK-added] Severity - file:line - title
Codex raised and orchestrator verified.

Rejected
- Finding: reason.

PK Summary
What Codex challenged / confirmed / added.

Verification
Commands run.
```
