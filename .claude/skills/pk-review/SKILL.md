---
name: pk-review
description: Single-PR PK review. The orchestrating model (Claude Code on DeepSeek, or Codex) deep-reviews one PR independently, calls the other CLI as adversarial PK challenger, posts the final verdict via the review account. Use when asked to review a specific PR, or when pr-daemon-loop delegates a single review.
origin: pr-daemon
---

<!-- INSTALL NOTE
When installed globally via install-skills.sh --global, PR_DAEMON_ROOT is patched to the absolute
path of the PR-Daemon repo. When used directly in the project, run from the PR-Daemon root.
-->

# PK Review (Single PR)

## Configuration

```bash
PR_DAEMON_MAIN_USER="${PR_DAEMON_MAIN_USER:-jhfnetboy}"
PR_DAEMON_REVIEW_USER="${PR_DAEMON_REVIEW_USER:-clestons}"
```

## Workflow

### 1. Resolve Diff

```bash
python3 PR_DAEMON_ROOT/scripts/resolve_repo.py OWNER/REPO
gh pr diff N --repo OWNER/REPO --patch > /tmp/pr-diff.patch
```

### 2. Optional Breadth Pass

```bash
python3 PR_DAEMON_ROOT/skills/pk-review/scripts/local_review.py \
  --repo ~/Dev/ORG/REPO \
  --diff-file /tmp/pr-diff.patch \
  --eval-db PR_DAEMON_ROOT/reviews/model-evals/model-evals.sqlite \
  --owner OWNER --repo-name REPO --pr-number N \
  --output /tmp/breadth.md
```

### 3. Deep Review (Independent)

Read diff and changed file context. Focus on: correctness bugs, security, concurrency, data loss, API contract breaks, missing tests, CI config. Form findings **before** reading breadth-pass output.

### 4. PK Challenge via Codex — MANDATORY, NEVER SKIP

**This step is required for every review. Do not skip even if you are confident in the findings.**

**Use the Agent tool with `subagent_type: "codex:rescue"` — do NOT use `codex exec` CLI (it spawns a fresh sandbox and is 30–90s slower).**

Invoke the Agent tool like this (pseudocode — use it as the Agent tool call, not Bash):

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
<YOUR_FINDINGS_HERE>

Do NOT post anything to GitHub. Return ONLY the structured critique.
"""
)
```

After receiving the critique:
- Accept valid challenges → mark finding as **Rejected** (do not include in final review)
- For each **[MISSED]**: independently verify before including
- Run a second round only if Codex raised critical Missed items. Max 2 rounds total.

### 5. Post

```bash
bash PR_DAEMON_ROOT/scripts/post_pr_review.sh \
  --repo OWNER/REPO --pr N \
  --body-file /tmp/review.md \
  --request-changes  # or --approve or --comment
```

### 6. Record

```bash
python3 PR_DAEMON_ROOT/scripts/model_eval_db.py record-run \
  --owner OWNER --repo REPO --pr-number N \
  --head-oid HEAD --score SCORE --verdict VERDICT \
  --useful-findings "..." --false-positives "..." --misses "..."
```

## Output Format

```text
[Confirmed] Severity - file:line - Title
Evidence and fix.

[PK-added] Severity - file:line - Title
Codex raised and orchestrator verified.

Rejected: finding — reason.

PK Summary | Verification
```

## Hard Rules

- **PK challenge round is MANDATORY** — every review must invoke Codex to challenge findings before posting.
- Never merge, never modify business code.
- Always use `post_pr_review.sh` for posting.
- Always verify `gh api user -q .login` equals `$PR_DAEMON_MAIN_USER` after posting.
- Max 2 PK challenge rounds per review.
