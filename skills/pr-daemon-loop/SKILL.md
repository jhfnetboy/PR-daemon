---
name: pr-daemon-loop
description: Full 24/7 autonomous PR review loop. When invoked, continuously discovers all open PRs across the 3 orgs (aastar / auraai / mycelium), performs deep review as the primary model, calls Codex as PK challenger, posts findings as clestons, and records results. Loops until the user stops it. Use when the user says "run PR daemon", "start 24/7 review", "keep reviewing PRs", or "start the review loop".
---

# PR Daemon Loop

## What This Skill Does

You (Claude Code, running on DeepSeek via `run-dpsk-claude.sh`) are the **primary reviewer**. You run a closed loop:

1. Discover all open PRs authored by `jhfnetboy` across the 3 orgs.
2. Pick the next un-reviewed (or head-changed) PR.
3. Do a deep, thorough review.
4. Challenge your own findings with `codex exec` (PK round).
5. Post the final verdict as `clestons`.
6. Record results in SQLite + Markdown.
7. Repeat for the next PR. When all are done, wait and check for new/changed PRs.

You never modify business code. You never merge. You only post after explicit approval or in autonomous mode.

## Loop Entry Prompt

When the user says "run PR daemon" or similar, start with:

```text
Starting PR Daemon loop. I will continuously review all open PRs for jhfnetboy across aastar, auraai, and mycelium. I'll post findings as clestons and call Codex for each PK challenge round. I will not merge any PR.

Beginning scan...
```

## Step 1 — Discover Open PRs

Always query by explicit author to avoid `@me` issues (the active account may be `clestons`):

```bash
gh search prs --author jhfnetboy --state open \
  --json number,title,repository,url,updatedAt,isDraft,headRefOid,baseRefName \
  --limit 100
```

Or use the helper:

```bash
python3 scripts/list_open_prs.py --json
```

Filter out:
- `isDraft: true` PRs (skip unless user says to include drafts)
- PRs already reviewed by `clestons` at the current `headRefOid` — check:

```bash
sqlite3 .state/pr-daemon/pr-watch.sqlite \
  "SELECT status, last_reviewed_head_oid FROM pr_watch_targets WHERE repo='OWNER/REPO' AND pr_number=N;"
```

If `last_reviewed_head_oid` matches the current `headRefOid` → skip (already reviewed at this commit).

Priority order:
1. New PRs (never reviewed)
2. PRs with head changed since last review
3. PRs with `CHANGES_REQUESTED` that have a new commit
4. Others by `updatedAt DESC`

## Step 2 — Prepare Diff

Resolve local checkout first (no `/tmp` clones unless unavailable):

```bash
python3 scripts/resolve_repo.py OWNER/REPO
```

Known mappings (from `config/repo-roots.json`):
- `AAStarCommunity/*` → `~/Dev/aastar/*`
- `AuraAI/*` → `~/Dev/auraai/*`
- `mycelium/*` → `~/Dev/mycelium/*`

If local checkout exists, fetch and check out the PR branch:

```bash
cd ~/Dev/aastar/REPO
git fetch origin
git checkout origin/PR_HEAD_REF
```

Generate the diff:

```bash
git diff $(git merge-base origin/BASE_REF HEAD)..HEAD
# or
gh pr diff PR_NUMBER --repo OWNER/REPO --patch > /tmp/pr-OWNER-REPO-N.diff
```

## Step 3 — Deep Review (You are the Primary Reviewer)

Read the diff carefully. Then read the key files referenced by the diff (not every file — focus on changed functions and their callers). Focus on:

- **Correctness bugs**: logic errors, off-by-one, wrong conditions
- **Security issues**: injection, broken access control, auth bypass, supply chain
- **Concurrency / race conditions**: shared state, missing locks, async misuse
- **Data loss**: missing rollbacks, wrong error handling, missing idempotency
- **API contract breaks**: changed interfaces, missing migration, version skew
- **Missing or broken tests**: especially for the changed code path
- **CI/config issues**: broken builds, wrong env, misconfigured gates

For each finding, determine:
- Severity: Critical / High / Medium / Low
- File + line
- Root cause
- Recommended fix
- Whether a test can verify it

Do NOT look at any prior review or first-pass output yet. Form your view independently first.

Optional: after forming your independent view, run a quick breadth pass to catch what you might have missed:

```bash
gh pr diff PR_NUMBER --repo OWNER/REPO --patch > /tmp/pr.diff
python3 skills/pk-review/scripts/local_review.py \
  --repo ~/Dev/ORG/REPO \
  --diff-file /tmp/pr.diff \
  --eval-db reviews/model-evals/model-evals.sqlite \
  --owner OWNER --repo-name REPO --pr-number N \
  --output /tmp/breadth-pass.md
```

Merge any new findings from the breadth pass into your list.

## Step 4 — PK Challenge Round (Codex as Adversarial Challenger) — MANDATORY

**Use the Agent tool with `subagent_type: "codex:codex-rescue"` — NOT `codex exec` CLI.**  
`codex exec` spawns a fresh sandbox with 30–90s cold-start per call. The Agent tool uses the shared runtime and returns in seconds.

```
Agent(
  subagent_type = "codex:codex-rescue",
  prompt = """
PK CHALLENGE: You are the adversarial reviewer for OWNER/REPO#PR_NUMBER.

Read the diff with: gh pr diff PR_NUMBER --repo OWNER/REPO --patch

Then adversarially challenge this finding list:

<paste_your_finding_list_here>

For each finding, return EXACTLY ONE of:
- [CHALLENGE] <finding> — reason the evidence does NOT support it, or it is a false positive
- [CONFIRM] <finding> — independent evidence confirms this is real
- [MISSED] <new finding> — something the primary reviewer missed

Do NOT post anything to GitHub. Return ONLY your structured critique.
"""
)
```

Read Codex's response. For each item:
- `[CHALLENGE]`: examine the counter-evidence. If it's valid, mark the finding `Rejected`. If not, defend it with additional code evidence.
- `[CONFIRM]`: keep the finding as `Confirmed`.
- `[MISSED]`: verify independently. If valid, add as `Codex-added` finding.

Maximum 2 challenge rounds. After 2 rounds, make your final call regardless.

## Step 5 — Final Verdict and Output

Structure the review as:

```text
## PR Review: OWNER/REPO#N — TITLE

Verdict: REQUEST_CHANGES | APPROVE | COMMENT

### Findings

**[Critical/High/Medium/Low]** `file:line` — Title
Evidence: ...
Fix: ...

### PK Summary
- Codex challenged: ...
- Outcome: ...

### Verification
Commands run / tests checked

### Records
- Local review: reviews/OWNER-REPO-N-local-review-HEADOID-DATE.md
- Model eval: recorded via model_eval_db.py
```

## Step 6 — Post as clestons

Only post after forming the final verdict. Use `scripts/post_pr_review.sh` which handles account switching:

```bash
# Check current account first
gh api user -q .login

# Write review to file
cat > /tmp/review-OWNER-REPO-N.md << 'EOF'
(paste final review text)
EOF

# Post (script switches to clestons, posts, switches back to jhfnetboy)
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /tmp/review-OWNER-REPO-N.md \
  --request-changes   # or --approve or --comment

# Verify account returned to main
gh api user -q .login
```

**Never post without running `scripts/post_pr_review.sh`** — direct `gh pr review` risks leaving the active account as `clestons`.

## Step 7 — Record Results

Write the review artifact:

```bash
# Markdown record
cp /tmp/review-OWNER-REPO-N.md reviews/OWNER-REPO-N-local-review-HEADOID-DATE.md
```

Record in SQLite:

```bash
python3 scripts/model_eval_db.py record-run \
  --owner OWNER \
  --repo REPO \
  --pr-number N \
  --head-oid HEADOID \
  --score SCORE \
  --verdict REQUEST_CHANGES \
  --local-review-path reviews/OWNER-REPO-N-local-review-HEADOID-DATE.md \
  --useful-findings "..." \
  --false-positives "..." \
  --misses "..." \
  --next-prompt-improvements "..."
```

Update the watcher DB:

```bash
sqlite3 .state/pr-daemon/pr-watch.sqlite \
  "UPDATE pr_watch_targets SET last_reviewed_head_oid='HEADOID', status='changes_requested', last_reviewed_at=CURRENT_TIMESTAMP WHERE repo='OWNER/REPO' AND pr_number=N;"
```

## Step 8 — Loop

After recording, immediately move to the next queued PR. When all queued PRs are processed:

1. Re-scan GitHub for new/updated PRs (repeat Step 1).
2. If nothing new, wait ~5 minutes then scan again:

```bash
sleep 300
```

3. If a previously-reviewed PR has a new commit (author responded to `REQUEST_CHANGES`), re-queue it.
4. Log progress:

```text
[LOOP] Cycle complete. Reviewed N PRs. Waiting for new activity...
```

Continue looping until the user explicitly stops with Ctrl+C or says "stop".

## Hard Rules (never violate)

- **Never merge** any PR, even if verdict is `APPROVE`.
- **Never modify** business repo source, config, tests, or lock files.
- **Never post** using direct `gh pr review` — always use `scripts/post_pr_review.sh`.
- **Never rely on `@me`** for PR discovery — always use `--author jhfnetboy`.
- **Always verify** `gh api user -q .login` equals `jhfnetboy` after every GitHub operation.
- **Always record** both Markdown and SQLite for every completed review.
- **Maximum 2 PK rounds** per PR per head commit.

## Quick-Start Commands

```bash
# Launch Claude Code on DeepSeek
./run-dpsk-claude.sh

# Then tell Claude:
# "Use $pr-daemon-loop to start the 24/7 review loop"

# Or one-liner (headless):
./run-dpsk-claude.sh -p "Use pr-daemon-loop. Start the continuous PR review daemon for jhfnetboy's open PRs across aastar, auraai, and mycelium. Post reviews as clestons. Run until I stop you."

# Check watcher state while running
./watch.sh queue
./watch.sh current
tail -f .state/pr-daemon/review-watch.log
```
