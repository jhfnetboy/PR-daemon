---
name: rapid-mlx-review
description: Local-first code review workflow that uses a resident Rapid-MLX OpenAI-compatible server, exposed as qwen3.6-a3b, to perform broad first-pass review, summaries, challenge rounds, and comment drafting before Codex performs independent deep review, senior-risk analysis, adjudication, and final accountability. Use when the user asks for review, code review, PR review, repository review, diff review, or says to use local Rapid-MLX/local MLX/local A3B/local model first and then have Codex verify, compare, PK, challenge, or synthesize findings.
---

# Rapid-MLX Review

## Overview

Use local Rapid-MLX as a cheap, broad, always-on reviewer, then use Codex as the verifier and final reviewer. The local model should do as much volume work as possible: queue summaries, diff triage, first-pass findings, file summaries, reverse challenges, fix suggestions, and comment drafts. Codex must reserve attention for independent deep review, security and senior-risk analysis, final adjudication, and accountability. Treat local-model output as hypotheses only; never report a finding as final unless Codex can ground it in code paths, diffs, tests, or reproducible reasoning.

## Workflow

1. Resolve the review target.
   - If the user names a repository path, work there.
   - If the user names a PR, branch, commit, or goal, inspect the relevant git state and derive the diff.
   - For GitHub PRs, resolve local checkouts before cloning. In PR-Daemon, use `config/repo-roots.json` and `scripts/resolve_repo.py`. Known roots:
     - `AAStarCommunity` / `aastar` → `~/Dev/aastar`
     - `AuraAI` / `auraai` → `~/Dev/auraai`
     - `mycelium` → `~/Dev/mycelium`
   - If a repo is missing under its configured root, clone it into that root. Do not use `/tmp` for normal PR review checkouts.
   - External business repos are review context only. Never modify their source, config, tests, lock files, or PR branch code. Write access, when available, is only for git metadata operations like fetch/checkout and explicit temporary review artifacts.
   - If the user asks for the PR-Daemon default queue, discover open PRs authored by `jhfnetboy` explicitly; do not rely on `@me` because the active GitHub account may be the review account.
   - If the target is ambiguous, make the most conservative discoverable assumption from the current repo; ask only when the target cannot be inferred.

2. For GitHub PR queue mode, separate discovery identity from review identity.
   - Discovery owner/author is normally `jhfnetboy`.
   - Review/posting account is normally `clestons` for `clestons@gmail.com`.
   - Keep `jhfnetboy` as the default active GitHub account. Switch to `clestons` only for posting a review, then switch back immediately.
   - In PR-Daemon, use `scripts/post_pr_review.sh` for posting because it switches to the review account and restores the main account.
   - `gh auth switch --user` expects a GitHub login, not necessarily an email address.
   - Use explicit PR search when discovering authored PRs:

```bash
gh search prs --author jhfnetboy --state open --json number,title,repository,url,updatedAt,isDraft,author --limit 50
```

   - In the PR-Daemon repository, prefer `scripts/list_open_prs.py` when available:

```bash
python3 scripts/list_open_prs.py --author jhfnetboy
```

   - If `prbot` is installed, it may be used as an interactive dashboard, but do not use its `@me`-based categories as the source of truth when the active account is not `jhfnetboy`.

3. Start or verify the resident Rapid-MLX server.
   - Prefer an existing OpenAI-compatible server at `http://localhost:8000/v1`.
   - Correct default is to reuse an already-running server first. Codex/headless sessions may not have Metal access and can fail with `No Metal device available`; if that happens, start Rapid-MLX from a normal macOS Terminal/user session and reuse the API.
   - In PR-Daemon, prefer the daemon helper:

```bash
scripts/rapid_mlx_daemon.sh ensure
scripts/rapid_mlx_daemon.sh status
```

   - API model name should be `qwen3.6-a3b`.
   - Default loader is the Rapid-MLX alias `qwen3.6-35b-6bit`, which uses Rapid-MLX/Hugging Face cache resolution.
   - `RAPID_MLX_LOAD_MODEL` may override the loader with either a Rapid-MLX alias/HF repo or a local OMLX path such as `~/.omlx/models/Qwen3.6-35B-A3B-MLX-6bit`.
   - If no server is reachable and `rapid-mlx` is installed, manual fallback:

```bash
rapid-mlx serve qwen3.6-35b-6bit --host 127.0.0.1 --port 8000 --served-model-name qwen3.6-a3b --prefill-step-size 4096 --gpu-memory-utilization 0.85 --enable-prefix-cache
```

   - Use a user-specified model, port, or base URL when provided.
   - If the model fails under memory pressure, lower `--prefill-step-size` before switching away from the requested qwen3.6 A3B-class model.

4. Run local first-pass review.
   - Use `scripts/local_review.py` from this skill when possible.
   - Default comparison is merge-base against `origin/main`; override when the user specifies a base.
   - If the local repo cannot be written/fetched from the Codex sandbox, use `gh pr diff` into `/tmp` and pass `--diff-file`.
   - When re-reviewing a PR, pass prior findings or adversarial cases with `--context-file` so the local model verifies whether known issues were fixed.
   - In PR-Daemon, also load SQL model-eval history from `reviews/model-evals/model-evals.sqlite` with `--eval-db`, `--owner`, `--repo-name`, and `--pr-number` so prior prompt improvements are applied on the next run.

```bash
python3 /path/to/rapid-mlx-review/scripts/local_review.py --repo . --base origin/main --target HEAD --model qwen3.6-a3b --output /tmp/rapid-mlx-local-review.md
```

```bash
gh pr diff PR_NUMBER --repo OWNER/REPO --patch > /tmp/pr.diff
python3 /path/to/rapid-mlx-review/scripts/local_review.py --repo /path/to/local/repo --diff-file /tmp/pr.diff --model qwen3.6-a3b --output /tmp/rapid-mlx-local-review.md
```

```bash
python3 /path/to/rapid-mlx-review/scripts/local_review.py --repo /path/to/local/repo --diff-file /tmp/pr.diff --context-file /tmp/prior-findings.md --eval-db /path/to/PR-Daemon/reviews/model-evals/model-evals.sqlite --owner OWNER --repo-name REPO --pr-number PR_NUMBER --model qwen3.6-a3b --output /tmp/rapid-mlx-local-review.md
```

   - Add `--worktree` when the user asks to review current uncommitted changes.

5. Perform Codex deep review independently.
   - Read the diff and relevant surrounding files. Include unstaged or staged changes when `--worktree` was used.
   - Prioritize bugs, regressions, security risks, performance risks, concurrency problems, API contract breaks, data loss, and missing tests.
   - Run targeted tests or static checks when feasible.
   - Do not rely on the local model's reasoning until after forming an independent view.

6. Run PK/challenge adjudication.
   - Mark each local finding `Confirmed` only if Codex verifies it.
   - Mark it `Rejected` when it is a false positive, unsupported, merely stylistic, or contradicted by code.
   - Add `Codex-only` findings when Codex finds issues the local model missed.
   - For complex reviews, ask the local model to challenge the Codex finding list once, then Codex makes the final call.
   - Stop after findings are stable or after two challenge rounds unless the user asks for more.
   - Codex is responsible for the final answer even when the local model did most of the work.

7. Score and record local model contribution.
   - After every review, score local model contribution from 0-10.
   - Track useful findings, false positives, misses, prompt/context gaps, and next prompt improvements.
   - Save the narrative record in `reviews/model-evals/` when working in PR-Daemon.
   - Also record the run in SQL with `scripts/model_eval_db.py record-run`, including score, useful findings, false positives, misses, prompt gaps, prior-improvement evaluation, and next prompt improvements.
   - On re-review, evaluate whether the previous run's improvement items actually improved the model output; record that result in `prior_improvement_evaluation`.
   - Use `scripts/model_eval_db.py assess-item` to mark each carried-forward improvement item as `effective`, `ineffective`, `needs_followup`, or `retired`.
   - Use `scripts/model_eval_db.py scorecard` to check recent scores, open improvement items, and whether the local model is improving or repeating the same failure modes.
   - Update this skill when a repeated failure mode appears.

## Local Model Use Cases

The local model is useful for:

- Batch PR triage: summarize change scope, changed subsystems, obvious risk areas, and files Codex should inspect first.
- Repetitive verification: re-check prior findings, adversarial examples, test matrices, grep gates, and config invariants.
- Hypothesis generation: propose likely regressions, missing tests, and edge cases for Codex to verify or reject.
- Review recordkeeping: draft structured summaries, local findings, false positives, misses, and next prompt improvements.
- Comment drafting after Codex has already decided the final finding.

Do not trust the local model as final authority for security boundaries, concurrency, state machines, chain/TEE behavior, CI gates, data loss, or API contracts. Codex must independently verify final findings.

## Feedback Loop

For every review, keep the loop measurable:

1. Inject open SQL improvement items into the local-model prompt.
2. Run local broad pass.
3. Codex independently reviews and adjudicates local findings.
4. Score the local model from 0-10.
5. Record the run in SQLite and Markdown.
6. Mark prior improvement items:
   - `effective`: this item improved behavior; stop carrying it.
   - `ineffective`: no improvement; keep carrying it and make the constraint stronger.
   - `needs_followup`: partial improvement; verify again next run.
   - `retired`: no longer relevant.
7. Add only a small number of concrete next improvements.

Treat an improvement as real only if there is observable evidence: fewer repeated misses, fewer false positives, better required-section compliance, correct truth tables, fewer Codex-only blockers, or faster final GitHub review with less rework.

## Local Review Prompt Standard

The local model should be strict and concise:

- Report only issues that can plausibly cause bugs, regressions, security problems, performance problems, or meaningful test gaps.
- For every finding, include severity, file/function clue, why it matters, and a concrete fix.
- Avoid style-only feedback, praise, broad refactors, and unsupported guesses.
- Treat missing context as uncertainty instead of inventing facts.

## Final Output

Use the user's language. For code review, lead with findings ordered by severity. Use this structure:

```text
Findings

[Confirmed] Severity - file:line - title
Evidence and recommended fix.

[Codex-only] Severity - file:line - title
Evidence and recommended fix.

Rejected Local Findings
Short list of important false positives, if any.

Local Model Summary
What Rapid-MLX found, where it was useful, and where it missed or overreached.

Verification
Commands/tests run, or why they were not run.
```

If no real issues are found, say so clearly and mention residual test gaps.

## Completion Contract

Every PR review must end with all of the following:

- A clear conclusion: `APPROVE`, `REQUEST_CHANGES`, or a non-blocking `COMMENT`.
- A posted GitHub review/comment matching that conclusion. If posting fails, record the failure and fix or retry the posting flow.
- Updated local records in PR-Daemon: review body, local-model markdown evaluation, SQLite score, prior-improvement evaluation, and next improvement items.
- Never merge the PR after approval. The PR author or maintainer must read the review/comment and decide whether to merge.

## GitHub Posting

Do not post PR comments or use a different GitHub account unless the user explicitly asks for posting. If posting is requested, verify `gh auth status`, selected account, repository, and target PR before creating comments. For PR-Daemon's default posting flow, switch to `clestons` first and verify `gh api user -q .login` returns the intended review account.
