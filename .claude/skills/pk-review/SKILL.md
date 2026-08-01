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

### 4. PK Challenge via Codex (fallbacks: DeepSeek, then Opus) — MANDATORY, NEVER SKIP

**This step is required for every review. Do not skip even if you are confident in the findings.**

**Primary: use the Agent tool with `subagent_type: "codex:codex-rescue"` — do NOT use `codex exec` CLI (it spawns a fresh sandbox and is 30–90s slower).** Always run it in the foreground (`run_in_background: false` / do not background it) — a backgrounded PK task whose result can't be retrieved must not be silently waited on.

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

**Fallback — Codex quota exhausted / auth failure / unavailable:** the PK prompt has no tool access when sent to this fallback (unlike codex:codex-rescue, which can run `gh pr diff` itself) — embed the actual diff content directly in the prompt (e.g. `gh pr diff N --repo OWNER/REPO --patch` appended after the instructions), not an instruction to go fetch it. Write the combined prompt to a temp file and run:

```bash
bash PR_DAEMON_ROOT/scripts/deepseek_pk_challenge.sh /tmp/pk-prompt.txt
```

This calls DeepSeek (`deepseek-v4-flash`, non-thinking mode — fast, no chain-of-thought overhead; `DEEPSEEK_API_KEY` in `PR_DAEMON_ROOT/.env`) and prints only the model's answer in the same `[CHALLENGE]/[CONFIRM]/[MISSED]` structured critique format (the prompt asks for it explicitly). Treat its output exactly like Codex's: parse the same three tags, apply the same accept/reject rules below — but weigh its challenges critically, same as any reviewer: DeepSeek can push back with speculative or incorrect counter-arguments (e.g. asserting a downstream size/validation limit that doesn't actually exist), so verify a [CHALLENGE] against your finding before accepting it, don't just defer to it.

(A prior Kimi K3 fallback via hilinkup.com was tried and dropped: non-streaming responses get killed by that host's ~100s Cloudflare edge timeout, and even streamed responses took 5+ minutes without finishing on a normal-sized PR diff before hitting rate limits. DeepSeek answers in single-digit seconds on the same prompt size — use it, not Kimi.)

**Second fallback — DeepSeek also fails/unavailable (network down, key missing, bad/empty response):** use the Agent tool with `model: "opus"` (a full Claude agent, not a bare completion call — it can run `gh pr diff` itself like Codex, no need to embed the diff in the prompt). Same PK-challenge prompt template as the Codex call in step 4's primary path:

```
Agent(
  model = "opus",
  subagent_type = "general-purpose",
  prompt = """
PK CHALLENGE for OWNER/REPO#N (Codex and DeepSeek both unavailable this round):

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

Run this in the foreground (do not background it), same reasoning as the Codex primary path.

**Never silently skip this step and self-finalize** just because Codex is unavailable — DeepSeek and Opus exist specifically so a real adversarial pass still happens even without Codex. Only if *all three* (Codex, DeepSeek, Opus) fail may you fall back to self-verification with tool-based empirical proof, and the resulting review must say explicitly which challenger was actually used ("PK via Codex" / "PK via DeepSeek (Codex quota exhausted)" / "PK via Opus (Codex + DeepSeek both unavailable)" / "PK via self-verification (Codex + DeepSeek + Opus all unavailable)") — never claim a Codex round that didn't happen.

After receiving the critique:
- Accept valid challenges → mark finding as **Rejected** (do not include in final review)
- For each **[MISSED]**: independently verify before including
- Run a second round only if the challenger raised critical Missed items. Max 2 rounds total.

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
Challenger (Codex, DeepSeek, or Opus) raised and orchestrator verified.

Rejected: finding — reason.

PK Summary | Verification
```

## Hard Rules

- **NEVER MERGE** any PR — not even after APPROVE. `gh pr merge` is forbidden. Merging belongs to the PR author/maintainer only.
- **PK challenge round is MANDATORY** — every review must invoke Codex, or DeepSeek/Opus fallback when Codex quota is exhausted, to challenge findings before posting.
- **Never modify** business repo source, config, tests, or lock files.
- **Only review and comment** — the only allowed GitHub write operations are: post review comment, request changes, approve. Nothing else.
- Always use `post_pr_review.sh` for posting. Never call `gh pr review` directly.
- Always verify `gh api user -q .login` equals `$PR_DAEMON_MAIN_USER` after posting.
- Max 2 PK challenge rounds per review.
