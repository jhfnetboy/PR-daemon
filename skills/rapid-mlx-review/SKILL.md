---
name: rapid-mlx-review
description: Local-first code review workflow that uses a running Rapid-MLX OpenAI-compatible server, normally qwen3.6-35b-6bit or another A3B MLX model, to perform an initial broad review before Codex performs an independent deep review and adjudicates the results. Use when the user asks for review, code review, PR review, repository review, diff review, or says to use local Rapid-MLX/local MLX/local A3B/local model first and then have Codex verify, compare, PK, or synthesize findings.
---

# Rapid-MLX Review

## Overview

Use local Rapid-MLX as a cheap, broad first-pass reviewer, then use Codex as the verifier and final reviewer. Treat local-model output as hypotheses only; never report a finding as final unless Codex can ground it in code paths, diffs, tests, or reproducible reasoning.

## Workflow

1. Resolve the review target.
   - If the user names a repository path, work there.
   - If the user names a PR, branch, commit, or goal, inspect the relevant git state and derive the diff.
   - If the target is ambiguous, make the most conservative discoverable assumption from the current repo; ask only when the target cannot be inferred.

2. Start or verify Rapid-MLX.
   - Prefer an existing OpenAI-compatible server at `http://localhost:8000/v1`.
   - If no server is reachable and `rapid-mlx` is installed, start:

```bash
rapid-mlx serve qwen3.6-35b-6bit --port 8000 --prefill-step-size 4096 --gpu-memory-utilization 0.85
```

   - Use a user-specified model, port, or base URL when provided.
   - If the model fails under memory pressure, lower `--prefill-step-size` before switching away from `qwen3.6-35b-6bit`.

3. Run local first-pass review.
   - Use `scripts/local_review.py` from this skill when possible.
   - Default comparison is merge-base against `origin/main`; override when the user specifies a base.

```bash
python3 /path/to/rapid-mlx-review/scripts/local_review.py --repo . --base origin/main --target HEAD --output /tmp/rapid-mlx-local-review.md
```

   - Add `--worktree` when the user asks to review current uncommitted changes.

4. Perform Codex deep review independently.
   - Read the diff and relevant surrounding files. Include unstaged or staged changes when `--worktree` was used.
   - Prioritize bugs, regressions, security risks, performance risks, concurrency problems, API contract breaks, data loss, and missing tests.
   - Run targeted tests or static checks when feasible.
   - Do not rely on the local model's reasoning until after forming an independent view.

5. Adjudicate local findings.
   - Mark each local finding `Confirmed` only if Codex verifies it.
   - Mark it `Rejected` when it is a false positive, unsupported, merely stylistic, or contradicted by code.
   - Add `Codex-only` findings when Codex finds issues the local model missed.

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

## GitHub Posting

Do not post PR comments or use a different GitHub account unless the user explicitly asks for posting. If posting is requested, verify `gh auth status`, selected account, repository, and target PR before creating comments.
