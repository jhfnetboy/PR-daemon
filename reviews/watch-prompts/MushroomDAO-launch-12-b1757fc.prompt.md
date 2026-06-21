Use $rapid-mlx-review to review MushroomDAO/launch#12 in PR-Daemon autonomous watch mode.

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
- title: feat(site): AAStar + AuraAI landing pages + nav links + label fixes
- url: https://github.com/MushroomDAO/launch/pull/12
- base: main
- head: feat/aastar-auraai-pages
- head_oid: b1757fcef1550925a119faddf96ef1d0b252d5a7
- current_review_decision: 
- latest_clestons_review: APPROVED
