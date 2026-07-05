---
name: pk-review
description: Single-PR PK review. The orchestrating model (Claude Code on DeepSeek, or Codex) deep-reviews one PR independently, calls the other CLI as adversarial PK challenger, posts the final verdict via the review account. Use when asked to review a specific PR, or when pr-daemon-loop delegates a single review.
origin: pr-daemon
---

<!-- INSTALL NOTE
When installed globally via install-skills.sh --global, /Users/jason/Dev/tools/PR-Daemon is patched to the absolute
path of the PR-Daemon repo. When used directly in the project, run from the PR-Daemon root.
-->

# PK Review (Single PR)

> ⛔ **ABSOLUTE CONSTRAINT — READ FIRST**
> PR-Daemon is a **review-only** system. It MUST NEVER merge any PR under any circumstances.
> Even if the verdict is APPROVE, merging is the PR author's or maintainer's sole decision.
> Do not run `gh pr merge`, do not click merge, do not trigger any merge operation — ever.

## Configuration

```bash
PR_DAEMON_MAIN_USER="${PR_DAEMON_MAIN_USER:-jhfnetboy}"
PR_DAEMON_REVIEW_USER="${PR_DAEMON_REVIEW_USER:-clestons}"
```

## Workflow

### 0. PR Type Gate — decide track BEFORE doing anything else

Read the diff file list (from `gh pr view N --repo OWNER/REPO --json files` or the patch header).
Classify into exactly one track:

| Track | Condition | PK |
|---|---|---|
| **BUMP** | Every changed file is one of: `package.json` (version field only), `Cargo.toml` (version only), `CHANGELOG.md`, `*.md`, `openapi.yaml`, `foundry.toml` (version only) | **SKIP PK → go straight to Post** |
| **CODE** | Any file is: `.sol`, `.ts`, `.js`, `.py`, `.rs`, `.go`, `.sh`, config, CI, scripts, lock files, contracts | **PK MANDATORY** |

If unsure, treat as CODE.

**For BUMP-track PRs:** skip Steps 2–4 entirely. Write a one-line review body ("Pure version bump / release chore. No production code changes.") and go to Step 5.

---

### 1. Resolve Diff

**If this PR has been reviewed before in this session or recently, always check for new commits first:**

```bash
# Get current head OID and compare with last reviewed OID from eval DB
gh pr view N --repo OWNER/REPO --json headRefOid,commits
# If new commits exist, get only the incremental diff:
git -C <local-repo-path> diff <old-oid>..<new-oid>
# Otherwise full diff:
gh pr diff N --repo OWNER/REPO --patch > /tmp/pr-diff.patch
```

```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/resolve_repo.py OWNER/REPO
gh pr diff N --repo OWNER/REPO --patch > /tmp/pr-diff.patch
```

### 2. Optional Breadth Pass

```bash
python3 /Users/jason/Dev/tools/PR-Daemon/skills/pk-review/scripts/local_review.py \
  --repo ~/Dev/ORG/REPO \
  --diff-file /tmp/pr-diff.patch \
  --eval-db /Users/jason/Dev/tools/PR-Daemon/reviews/model-evals/model-evals.sqlite \
  --owner OWNER --repo-name REPO --pr-number N \
  --output /tmp/breadth.md
```

### 3. Deep Review (Independent)

Read diff and changed file context. Focus on: correctness bugs, security, concurrency, data loss, API contract breaks, missing tests, CI config. Form findings **before** reading breadth-pass output.

### 4. PK Challenge via Codex

**Pure-docs PRs** (only `.md`, `.yaml`, `CHANGELOG`, version bumps, `openapi.yaml`, `package.json` version-only, `Cargo.toml` version-only): **PK is OPTIONAL — default SKIP.** Post directly after Step 3.

**All other PRs** (any code, config, CI, scripts, lock files, contract): **PK is MANDATORY, NEVER SKIP.**

**Use the Agent tool with `subagent_type: "codex:codex-rescue"` — do NOT use `codex exec` CLI (it spawns a fresh sandbox and is 30–90s slower).**

Invoke the Agent tool like this (pseudocode — use it as the Agent tool call, not Bash):

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
bash /Users/jason/Dev/tools/PR-Daemon/scripts/post_pr_review.sh \
  --repo OWNER/REPO --pr N \
  --body-file /tmp/review.md \
  --request-changes  # or --approve or --comment
```

### 6. Record

```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/model_eval_db.py record-run \
  --owner OWNER --repo REPO --pr-number N \
  --head-oid HEAD --score SCORE --verdict VERDICT \
  --useful-findings "..." --false-positives "..." --misses "..."
```

## Output Format (Chat — shown to user AFTER posting)

**First line MUST be the verdict sentence:**
```
OWNER/REPO#N — APPROVED | REQUEST CHANGES | COMMENT
```
Then ≤3 bullet points (core findings only). No section headers, no process recap.

Example:
```
AAStarCommunity/YetAnotherAA-Validator#132 — COMMENT
- Medium: X402AuthGuard 无启动 secret 缺失警告，运营人员只在第一个 settle 请求时才知道
- Low: rawBody fallback 触发时只返回 403 无诊断信息
见 PR comment。
```

**PR Comment body format (written to /tmp/review.md):**
```text
[Confirmed] Severity - file:line - Title
Evidence and fix.

[PK-added] Severity - file:line - Title
Codex raised and orchestrator verified.

Rejected: finding — reason.

PK Summary | Verification
```

## Hard Rules

- **NEVER MERGE** any PR — not even after APPROVE. `gh pr merge` is forbidden. Merging belongs to the PR author/maintainer only.
- **PK challenge round**: classified at §0 (PR Type Gate). BUMP-track → skip PK entirely. CODE-track → MANDATORY, never skip.
- **Never modify** business repo source, config, tests, or lock files.
- **Only review and comment** — the only allowed GitHub write operations are: post review comment, request changes, approve. Nothing else.
- Always use `post_pr_review.sh` for posting. Never call `gh pr review` directly.
- Always verify `gh api user -q .login` equals `$PR_DAEMON_MAIN_USER` after posting.
- Max 2 PK challenge rounds per review.
