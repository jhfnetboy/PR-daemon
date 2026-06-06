Use $rapid-mlx-review to review MushroomDAO/Sin90#2 in PR-Daemon autonomous watch mode.

Requirements:
- Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
- Use the configured first-pass reviewer for broad pass, prior-finding verification, adversarial cases, and comment draft. Prefer DeepSeek via the repo .env when configured; otherwise use Rapid-MLX. If the primary provider fails, fall back to Rapid-MLX.
- Codex must independently verify findings with code, diff, and commands.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons.
- Never merge the PR, even after approval. Leave merge decisions to the PR author/maintainer.
- Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
- Continue to treat local-model output as hypotheses, not final authority.

PR metadata:
- title: chore: Apache 2.0 license compliance
- url: https://github.com/MushroomDAO/Sin90/pull/2
- base: main
- head: chore/license-compliance
- head_oid: ef4303f2bbbbad273ea2ea4bcfa906ae00125c7b
- current_review_decision: CHANGES_REQUESTED
- latest_clestons_review: CHANGES_REQUESTED
