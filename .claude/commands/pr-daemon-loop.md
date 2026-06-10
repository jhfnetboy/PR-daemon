---
description: Start the 24/7 PR review loop (3-round PK + Opus verdict, 2/4-round triage)
---

Start the PR-Daemon review loop by invoking the `pr-daemon-loop` skill.

Follow the skill's instructions exactly. Key points:
- You (Claude Code on the Max subscription) are the orchestrator and final authority.
- Run the main loop on the current session model (Sonnet recommended for cost).
- For each PR: R1 DeepSeek initial review + triage proposal → confirm 2-round vs 4-round.
- 2-round (low risk): DeepSeek → Sonnet verdict.
- 4-round (high risk): DeepSeek → Sonnet challenge → Codex PK → Opus subagent verdict.
- Final verdict must be APPROVE or REQUEST_CHANGES (never COMMENT limbo). Respect Codex feedback point-by-point.
- Score DeepSeek's work each PR, record triage decision, never merge.

See DESIGN.md for the full architecture.

Begin now: load the `pr-daemon-loop` skill and start scanning.
