Use $rapid-mlx-review to review AAStarCommunity/AirAccount#2 in PR-Daemon autonomous watch mode.

Requirements:
- Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
- Use qwen3.6-a3b through Rapid-MLX for broad pass, prior-finding verification, adversarial cases, and comment draft.
- Codex must independently verify findings with code, diff, and commands.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons.
- Never merge the PR, even after approval. Leave merge decisions to the PR author/maintainer.
- Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
- Continue to treat local-model output as hypotheses, not final authority.

PR metadata:
- title: chore: Apache 2.0 license compliance — bilingual five-file set
- url: https://github.com/AAStarCommunity/AirAccount/pull/2
- base: main
- head: chore/license-compliance
- head_oid: eeeb08030f23ea2cc25a348e197041c1bd423e74
- current_review_decision: REVIEW_REQUIRED
- latest_clestons_review:
