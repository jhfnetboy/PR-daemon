---
description: Start the PR review loop (3-round PK + Opus verdict, 2/4 triage). Optional args: a repo (OWNER/REPO) and/or extra instructions.
argument-hint: "[OWNER/REPO] [extra instructions]"
---

Start the PR-Daemon review loop by loading the `pr-daemon-loop` skill.

User arguments: $ARGUMENTS

Interpret the arguments:
- If an argument looks like `OWNER/REPO` → **single-repo mode**: review ALL open PRs in that
  one repo. Discover with `python3 scripts/poll_prs.py --repo OWNER/REPO`.
- If no repo is given → **org-scan mode**: review the 3 orgs (AAStarCommunity, AuraAIHQ, MushroomDAO)
  via `python3 scripts/poll_prs.py`.
- Any remaining text is extra instructions (e.g. "only security review", "max 3 PRs", "skip drafts")
  — honor them on top of the skill's defaults.

Then run the skill's pipeline per PR. Print the per-PR report after each
(verdict, status counter, token cost) so the user sees intermediate progress.

See DESIGN.md for the architecture. Begin now.
