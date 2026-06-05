Use $rapid-mlx-review to review MushroomDAO/CometENS#4 in PR-Daemon autonomous watch mode.

Requirements:
- Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
- Use qwen3.6-a3b through Rapid-MLX for broad pass, prior-finding verification, adversarial cases, and comment draft.
- Codex must independently verify findings with code, diff, and commands.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons.
- Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
- Continue to treat local-model output as hypotheses, not final authority.

PR metadata:
- title: feat: production API server (Phase 1-3) + security hardening
- url: https://github.com/MushroomDAO/CometENS/pull/4
- base: main
- head: feat/production-api-server
- head_oid: 45a0dcfdf74cc630384a6fdfe1f63a203889de46
- current_review_decision: 
- latest_clestons_review:
