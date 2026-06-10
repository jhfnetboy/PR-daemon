Use $rapid-mlx-review to review MushroomDAO/CometENS#4 in PR-Daemon autonomous watch mode.

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
- title: feat: production API server (Phase 1-3) + security hardening
- url: https://github.com/MushroomDAO/CometENS/pull/4
- base: main
- head: feat/production-api-server
- head_oid: d8a283e1098183fd10e5bf40fe4e291b3f483848
- current_review_decision: CHANGES_REQUESTED
- latest_clestons_review: CHANGES_REQUESTED
