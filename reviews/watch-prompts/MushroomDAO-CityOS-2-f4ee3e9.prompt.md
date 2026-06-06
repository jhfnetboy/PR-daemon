Use $rapid-mlx-review to review MushroomDAO/CityOS#2 in PR-Daemon autonomous watch mode.

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
- title: fix: README badge formatting — add missing newline
- url: https://github.com/MushroomDAO/CityOS/pull/2
- base: main
- head: chore/fix-badge-newline
- head_oid: f4ee3e9b061ad7144ea5f3b6264e3638317c4521
- current_review_decision: 
- latest_clestons_review: APPROVED
