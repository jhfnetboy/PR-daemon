Use $rapid-mlx-review to review AAStarCommunity/AirAccount#34 in PR-Daemon autonomous watch mode.

Requirements:
- Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
- Use qwen3.6-a3b through Rapid-MLX for broad pass, prior-finding verification, adversarial cases, and comment draft.
- Codex must independently verify findings with code, diff, and commands.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons.
- Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
- Continue to treat local-model output as hypotheses, not final authority.

PR metadata:
- title: docs: DK2 quickstart deployment guide
- url: https://github.com/AAStarCommunity/AirAccount/pull/34
- base: main
- head: docs/dk2-quickstart
- head_oid: c1e0ea57c59baf20dae992f57ffbf8e677cde62a
- current_review_decision: REVIEW_REQUIRED
- latest_clestons_review:
