## Review: AAStarCommunity/aastar-sdk#37 — feat(keeper): network-parameterized run-keeper.sh

**Date:** 2026-06-07 | **Reviewer:** Claude Code (DeepSeek) + Codex PK (skipped — 73-line script, low risk)
**Verdict: APPROVE** · **Score: 95/100**

Clean 73-line bash wrapper over existing `scripts/keeper.ts`. Network-parameterized with sensible defaults.

**[Confirmed] LOW — `grep -q -- '--superpaymaster'` pattern is fragile**
`printf '%s ' "$@" | grep -q -- '--superpaymaster'` — if any arg value contains `--superpaymaster` as substring, the baked address would be skipped. Practically unlikely (nobody passes that string as a value), but worth noting.

**[Confirmed] INFO — Well-structured script**
- `set -euo pipefail`, cd to script dir, auto-loads key from `.env.<network>`
- `--dry-run` exempt from key requirement (correct — no tx submission)
- Tunables via env: poll interval, safety margin, volatility thresholds

APPROVE — no blocking issues.
