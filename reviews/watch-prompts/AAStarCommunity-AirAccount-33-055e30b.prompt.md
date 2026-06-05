Use $rapid-mlx-review to review AAStarCommunity/AirAccount#33 in PR-Daemon autonomous watch mode.

Requirements:
- Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
- Use qwen3.6-a3b through Rapid-MLX for broad pass, prior-finding verification, adversarial cases, and comment draft.
- Codex must independently verify findings with code, diff, and commands.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons.
- Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
- Continue to treat local-model output as hypotheses, not final authority.

PR metadata:
- title: chore: fix README license badge to Apache 2.0
- url: https://github.com/AAStarCommunity/AirAccount/pull/33
- base: main
- head: chore/fix-readme-license
- head_oid: 055e30b20675a1abe2530529d05eaa80644b4f7a
- current_review_decision: REVIEW_REQUIRED
- latest_clestons_review:
