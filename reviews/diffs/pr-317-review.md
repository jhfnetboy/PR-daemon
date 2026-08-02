## [2-round] APPROVE ✅

**AAStarCommunity/aastar-sdk#317 — ci(gates): promote check:addresses + check:stubs to hard gates, kill the vacuous ABI pass (T3.1.1)**

Clean CI hardening PR. The scope pivot from "four gates in CI" to "two self-contained gates + make the other three honest" is the right call — driven by actual measurement on a clean checkout, not assumption.

### What's good
- **`check:addresses` → hard gate**: Drift that motivated the `continue-on-error` is resolved; verified clean on chains 10/11155111/11155420. The original comment literally said "Flip to a hard gate once passes clean" — this delivers on that.
- **`check:stubs` → new hard gate**: Self-contained, guards the #169 class (shipped `roleData='0x'` → bare on-chain revert). No-op if no stubs exist; blocks if one appears.
- **`REQUIRE_UPSTREAM=1` in three ABI scripts**: The key fix. Without it, all three exit 0 after comparing against nothing on a clean runner — a green "verified" from a run that verified zero artifacts. With the flag, missing upstream becomes exit 1. The `abi-sync.ts` guard is correctly placed **before** `--json`/`--fix` early exits (the comment claiming this is accurate, unlike what the automated first-pass suggested).
- **`ci.yml` comment block**: Documents exactly why the three ABI gates are deliberately absent — measured output, clear rationale, prerequisites for future CI inclusion. Prevents rediscovery as an oversight.
- **Release checklist**: Now requires `REQUIRE_UPSTREAM=1` on all three ABI gates — a forgotten `forge build` or missing sibling checkout fails loudly instead of green-lighting a release.

### Verified
- All three `REQUIRE_UPSTREAM` guards are correctly placed in their respective scripts
- `abi-sync.ts` guard precedes `--json`/`--fix` exits (the comment is accurate)
- `check-abi-completeness.ts`: `scannedUpstreams` counter → `totalMissing > 0` check → `REQUIRE_UPSTREAM` gate → PASS
- `check-abi-drift.ts`: `OUT_DIRS.length === 0` + `REQUIRE_UPSTREAM` → exit 1
- Documentation updates (progress.md, tasks.md, followups.md, RELEASE-CHECKLIST.md) are consistent and accurate

### Not blocking
- YAML validation of `ci.yml` was reported as verified by the PR author; cannot independently validate here (business repo access restricted). The diff is structurally sound — a missing `check:stubs` script in package.json would be caught immediately by CI on merge.
- The `REQUIRE_UPSTREAM` env var pattern is standard CI tooling practice — not a security concern (these are build scripts, not runtime; an attacker who controls CI env vars already owns the pipeline).

### Suggestions
- Consider adding a one-liner in `ci.yml` noting that `check:stubs` was added as a companion to `check:addresses` — future readers scanning the gate list may wonder why these two specifically.
- FU-6 (recorded in followups.md) captures the real-CI-gate path well. When that task arrives, the `REQUIRE_UPSTREAM=1` flag is already wired — just needs the checkout+build step.
