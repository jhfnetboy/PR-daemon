Use $rapid-mlx-review to review MushroomDAO/MyNFT#3 in PR-Daemon autonomous watch mode.

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
- title: docs: 三大能力总体设计 + 生态集成规范 + 调研参考子模块
- url: https://github.com/MushroomDAO/MyNFT/pull/3
- base: main
- head: feat/design-docs-and-submodules
- head_oid: b10bd23c62a7c5b1995f8b1755d30cc32e7aed9d
- current_review_decision: 
- latest_clestons_review:
