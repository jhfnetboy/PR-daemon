Use $pr-daemon-loop (the canonical v4 pipeline — do not substitute a different review flow)
to review jhfnetboy/CMIC#142 in PR-Daemon autonomous watch mode.

Requirements (on top of everything pr-daemon-loop's own SKILL.md already mandates):
- Use the local repository if available (see config/repo-roots.json); never clone to /tmp unless no local checkout exists.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons using scripts/post_pr_review.sh.
- Never merge the PR, even after approval. Leave merge decisions to the PR author/maintainer.
- Update PR-Daemon SQLite/Markdown records: reviews/, model_eval_db.py record-run.
  Always pass --provider deepseek --model deepseek-v4-flash explicitly on record-run
  (past runs were mostly logged with provider left blank -> "unknown" in provider-summary,
  which makes flash-specific stats unqueryable — do not repeat that gap).
- Do NOT modify business repo source, config, tests, or lock files.
- DeepSeek model is pinned to deepseek-v4-flash (PR_DAEMON_FIRST_PASS_MODEL) — do not override it.
- In the mandatory self-assessment block, add one explicit line rating DeepSeek v4-flash's
  performance on THIS PR (1-5 + one sentence: did R1a/R1b surface anything Opus R2/Codex R3
  later confirmed as real, any false positives, anything they caught that flash missed
  entirely). This feeds an ongoing flash-vs-pro evaluation (target: 20 rounds, started
  2026-08-01) — jason will aggregate via model_eval_db.py provider-summary once enough
  rounds land, so just record honestly each time, no extra action needed here.

PR metadata:
- title: docs: CMIC Agent v2 交互设计 + M→F→T 规划（含 Codex 复审修复）
- url: https://github.com/jhfnetboy/CMIC/pull/142
- base: preview
- head: docs/agent-plan-v2
- head_oid: 806239e3df2a770f64c21f4ae51f83c5f7da9490
- current_review_decision: CHANGES_REQUESTED
- latest_clestons_review: CHANGES_REQUESTED
