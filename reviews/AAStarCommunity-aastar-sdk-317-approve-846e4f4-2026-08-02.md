## [2-round] APPROVE ✅

**AAStarCommunity/aastar-sdk#317** — `ci(gates): promote check:addresses + check:stubs to hard gates, kill the vacuous ABI pass (T3.1.1)`

### Summary

This PR delivers the scope-corrected T3.1.1: promotes `check:addresses` from advisory to hard gate, adds `check:stubs` as a new hard gate, and retrofits three ABI scripts with `REQUIRE_UPSTREAM=1` to prevent the vacuous-pass class of bug (comparing against zero upstream artifacts and printing PASS). The ABI gates are deliberately left out of CI — the comment block in ci.yml thoroughly documents why (runner has no sibling upstream repos) and what would be needed to add them later.

### Verified

| File | Change | Assessment |
|:-----|:-------|:-----------|
| `.github/workflows/ci.yml` | Removes `continue-on-error: true` from check:addresses; adds check:stubs step; adds comprehensive comment on ABI gates | ✅ Correct. Address drift is documented as resolved; stubs check is self-contained. Comment block is thorough and accurate. |
| `scripts/abi-sync.ts` | Adds `REQUIRE_UPSTREAM` env guard + `scannedLevels` counter | ✅ Correct. Guard fires before `--json`/`--fix` early exits. |
| `scripts/check-abi-completeness.ts` | Adds `REQUIRE_UPSTREAM` env guard + `scannedUpstreams` counter | ✅ Correct. Same pattern, consistent. |
| `scripts/check-abi-drift.ts` | Adds `REQUIRE_UPSTREAM` env guard on `OUT_DIRS.length === 0` | ✅ Correct. Already had the length check; now fails hard under the flag. |
| `docs/RELEASE-CHECKLIST.md` | Adds `REQUIRE_UPSTREAM=1` instructions for §3 | ✅ Correct. Clear rationale, correct bash snippet. |
| `docs/agent/*.md` | Progress/task/followup updates | ✅ Correct. Reflects T3.1.1 scope change and T4.1.1 completion. |

### R1a (DeepSeek v4-flash) findings assessed

1. **[Low] `abi-sync.ts` — partial scan with `REQUIRE_UPSTREAM=1` passes if some (not zero) levels present** — Technically true: the guard is `scannedLevels === 0`, not `< LEVELS.length`. A developer with only 1 of 3 upstream repos checked out would still get a PASS under `REQUIRE_UPSTREAM=1`. However, this is a local release-checklist gate where the engineer is expected to have all siblings checked out (per the checklist itself). The primary threat — comparing against zero artifacts and printing PASS — is properly caught. Tightening to `< LEVELS.length` would be a nice follow-up but is not blocking: the documentation already covers the expectation, and the zero-artifact case (the truly dangerous one) is eliminated.

2. **[Low] `check-abi-completeness.ts` — same partial-scan pattern** — Same analysis as above. Not blocking.

### R1b (DeepSeek v4-flash security) — Clean. No security-relevant code in this diff.

### Suggestions (non-blocking)

- **Consider `scannedLevels < LEVELS.length` instead of `=== 0`** in `abi-sync.ts` and `check-abi-completeness.ts` — catches the partial-checkout case. Low priority since these are local release-checklist gates with documented expectations.
- **FU-6 is well-captured** — the followup item correctly defers "put ABI gates in CI" to a separate task that evaluates cost and private-repo access.
