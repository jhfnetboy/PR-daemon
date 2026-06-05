Use $rapid-mlx-review to review MushroomDAO/demo-repository#1 in PR-Daemon autonomous watch mode.

Requirements:
- Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
- Use qwen3.6-a3b through Rapid-MLX for broad pass, prior-finding verification, adversarial cases, and comment draft.
- Codex must independently verify findings with code, diff, and commands.
- Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
- Post the corresponding GitHub review/comment as clestons.
- Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
- Continue to treat local-model output as hypotheses, not final authority.

PR metadata:
- title: Add workflow badges to README
- url: https://github.com/MushroomDAO/demo-repository/pull/1
- base: main
- head: add-badges-to-readme
- head_oid: 99f7d1ee03a2a2f069b8b9193ae5f1e34229d283
- current_review_decision: 
- latest_clestons_review:
