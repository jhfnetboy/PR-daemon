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

## Loop Entry

When the user starts the daemon, announce:

```text
PR Daemon starting. Reviewing open PRs by $PR_DAEMON_MAIN_USER.
Review account: $PR_DAEMON_REVIEW_USER. PK challenger: codex.
Will not merge any PR. Beginning scan...
```

## Step 1 — Discover Open PRs

Always use explicit `--author` (never `@me` — active account may be the review account):

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

**Use the Agent tool with `subagent_type: "codex:rescue"` — NOT `codex exec` CLI. The CLI spawns a fresh sandbox with 30–90s cold-start overhead; the Agent tool uses the shared runtime and is much faster.**

Invoke the Agent tool (not Bash) with this prompt:

```
Agent(
  subagent_type = "codex:rescue",
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

Read the critique. Accept valid challenges (mark Rejected). Verify Missed items independently. Max 2 rounds.

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

## Step 7 — Loop

After recording, move to the next queued PR immediately. When all queued PRs are done:

1. Re-scan GitHub for new or head-changed PRs (back to Step 1).
2. If nothing new: `sleep 300` (5 min), then scan again.
3. Log: `[LOOP] Cycle complete. Reviewed N PRs. Waiting...`

Continue until the user explicitly stops with Ctrl+C or says "stop the daemon".

## Hard Rules

- **PK challenge is MANDATORY** — every PR review MUST invoke Codex as adversarial challenger (Step 4) before any post. No exceptions.
- **Never merge** any PR, even after `APPROVE`.
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
