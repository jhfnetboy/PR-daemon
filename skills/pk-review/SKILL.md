---
name: pk-review
description: 3-tier PK-style PR review. When launched via run-dpsk-claude.sh, the orchestrating model runs on DeepSeek API — so DeepSeek IS the primary reviewer. Codex acts as PK challenger. Use when asked for review, code review, PR review, repository review, diff review, PK review, or when the user wants deep review with Codex challenge/adjudication.
---

# PK Review

## Overview

3-tier PK-style review driven by a Claude Code session.

- **Tier 1 — Claude Code session (orchestrator):** when launched via `./run-dpsk-claude.sh`, the session runs on DeepSeek API (via Anthropic-compatible endpoint). It reads diffs, forms findings independently, owns the verdict, and posts the GitHub review.
- **Tier 2 — Optional `local_review.py` breadth pass:** a separate DeepSeek HTTP call via `skills/pk-review/scripts/local_review.py` that provides a quick additional perspective before the main deep review. Useful for batch triage but optional — the Claude Code session is the authoritative reviewer.
- **Tier 3 — Codex (PK challenger):** called by the Claude Code session via `codex exec`. Its role is to adversarially challenge the orchestrator's finding list. The orchestrator makes the final call regardless of what Codex raises.

Treat first-pass and Codex-challenger output as input only. Never report a finding as final unless the orchestrating session can ground it in code, diffs, tests, or reproducible reasoning.

## Workflow

1. Resolve the review target.
   - If the user names a repository path, work there.
   - If the user names a PR, branch, commit, or goal, inspect the relevant git state and derive the diff.
   - For GitHub PRs, resolve local checkouts before cloning. In PR-Daemon, use `config/repo-roots.json` and `scripts/resolve_repo.py`. Known roots:
     - `AAStarCommunity` / `aastar` → `~/Dev/aastar`
     - `AuraAI` / `auraai` → `~/Dev/auraai`
     - `mycelium` → `~/Dev/mycelium`
   - If a repo is missing under its configured root, clone it into that root. Do not use `/tmp` for normal PR review checkouts.
   - External business repos are review context only. Never modify their source, config, tests, lock files, or PR branch code. Write access is only for git metadata operations and temporary review artifacts.
   - Discover open PRs authored by `jhfnetboy` explicitly — never rely on `@me` because the active GitHub account may be `clestons`.

2. Separate discovery identity from review identity.
   - Discovery owner/author: `jhfnetboy`.
   - Review/posting account: `clestons` (`clestons@gmail.com`).
   - Keep `jhfnetboy` as the default active GitHub account. Switch to `clestons` only for posting, then switch back immediately.
   - Use `scripts/post_pr_review.sh` for posting — it handles account switching automatically.

```bash
gh search prs --author jhfnetboy --state open --json number,title,repository,url,updatedAt,isDraft,author --limit 50
python3 scripts/list_open_prs.py --author jhfnetboy
```

3. (Optional) Run a quick `local_review.py` breadth pass before deep review.
   - Provides an extra angle without counting against the main session's budget.
   - Skip if the diff is small or time is constrained.

```bash
gh pr diff PR_NUMBER --repo OWNER/REPO --patch > /tmp/pr.diff
python3 skills/pk-review/scripts/local_review.py \
  --repo /path/to/local/repo \
  --diff-file /tmp/pr.diff \
  --eval-db reviews/model-evals/model-evals.sqlite \
  --owner OWNER --repo-name REPO --pr-number PR_NUMBER \
  --output /tmp/pk-breadth-pass.md
```

4. Perform the deep review (orchestrating session).
   - Read the diff and relevant surrounding files.
   - Prioritize bugs, regressions, security risks, concurrency problems, API contract breaks, data loss, and missing tests.
   - Run targeted tests or static checks when feasible.
   - Form findings independently BEFORE reading the breadth-pass output.
   - After forming an independent view, compare with the breadth-pass and note any additions.

5. PK / challenge round — invoke Codex as challenger.
   - Once the finding list is stable, invoke Codex to adversarially challenge it:

```bash
codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
  --cd . \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium \
  "You are the PK challenger. Read the diff at OWNER/REPO#PR_NUMBER and adversarially challenge this finding list. For each finding, argue whether the evidence actually supports it, whether it is a false positive, or whether there is a missed issue. Return a structured critique: Challenged (with counter-evidence), Confirmed (with independent evidence), and Missed findings. Do NOT post anything to GitHub."
```

   - Read Codex's critique. Incorporate confirmed additions; defend or discard challenged findings with code evidence.
   - Hard stop: two challenge rounds maximum unless the user explicitly requests more.
   - The orchestrating session owns the final verdict regardless of Codex's input.

6. Score and record contribution.
   - After every review, score the optional breadth-pass provider from 0-10 (skip if not run).
   - Record in `reviews/model-evals/` (Markdown) and `model_eval_db.py record-run` (SQLite).
   - Mark prior improvement items via `model_eval_db.py assess-item`.

## Final Output

Use the user's language. Lead with findings ordered by severity:

```text
Findings

[Confirmed] Severity - file:line - title
Evidence and recommended fix.

[Added by PK] Severity - file:line - title
Codex raised this; orchestrator verified independently.

Rejected or Defended
- Finding: reason challenged / reason defended.

PK Summary
What Codex challenged, what was accepted, what was rejected.

Verification
Commands/tests run, or why they were not run.
```

If no real issues are found, say so clearly and mention residual test gaps.

## Completion Contract

Every PR review must end with all of the following:

- A clear conclusion: `APPROVE`, `REQUEST_CHANGES`, or a non-blocking `COMMENT`.
- A posted GitHub review/comment matching that conclusion. If posting fails, record the failure and fix the posting flow.
- Updated local records: review body, Markdown evaluation, SQLite score, prior-improvement evaluation, next improvement items.
- Never merge the PR. The PR author or maintainer decides whether to merge.

## GitHub Posting

Do not post unless explicitly requested. Before posting, verify `gh auth status`, confirm the account is `clestons`, and confirm repo + PR number.

```bash
bash scripts/post_pr_review.sh --repo OWNER/REPO --pr PR_NUMBER --body-file /tmp/review.md --request-changes
bash scripts/post_pr_review.sh --repo OWNER/REPO --pr PR_NUMBER --body-file /tmp/review.md --comment
```
