## Brood#17 — docs(research): paper topics proposal + roadmap (2026-07)

**Verdict: ✅ APPROVE** · 2-round pipeline (DeepSeek R1a+R1b) · pure docs PR

### What this PR adds

3 new Markdown files under `research/paper-topics/`, all human-readable research planning docs:

- `master-paper-roadmap-2026-07.md` — canonical 6-paper thesis map (Onion/Weighted/DVT/AOA/RepCredit/AgentPay), PhD thesis framework, anti-salami-slicing differentiation matrix, journal distribution, RepCredit v16 resubmit brief, Q3'26–Q1'27 timeline.
- `paper-title-keywords-abstract-2026-07.md` — titles/keywords/abstracts for 4 thesis papers (Ch3/4/5/8).
- `paper-topics-proposal-2026-07.md` — historical exploratory proposal, explicitly superseded for naming/structuring but retains valid analysis + timeline.

No code, no config, no CI workflow, no automation-consumed file touched. R1b security pass: no security-relevant surface.

### Verified (mechanical evidence)

| Check | Result |
|---|---|
| Cross-doc consistency: 6-paper naming / chapter mapping / `canonical` cross-refs between the 3 docs | ✅ consistent (roadmap §0 ↔ proposal header ↔ abstract header) |
| Code anchor `AAStarAirAccountBase.sol:1089-1160` (bitmap weighted multi-factor, P256/ECDSA/BLS/3 guardians) | ✅ verified at `src/core/AAStarAirAccountBase.sol:1089` `_validateWeightedSignature` |
| Code anchor `AirAccountExtension.sol:744` (fixed-count 2-of-3 recovery) | ✅ verified at `src/core/AirAccountExtension.sol` (`RECOVERY_THRESHOLD=2`, `RECOVERY_TIMELOCK=2 days`) |
| DVT gas figures: abstract `~450k` 3-signer vs roadmap §4 `~112k` | ✅ **no conflict** — ~112k is RepCredit's already-published "EIP-2537 aggregation saving" claim that the roadmap explicitly forbids DVT from re-claiming (baseline only); ~450k is DVT's own measured on-chain verification cost (the dynamic-gas-model claim the roadmap *does* require). Two metrics, different meanings. |
| Timeline consistency: proposal 执行建议 vs roadmap §7 | ✅ consistent (Onion→ACM DLT Q3; DVT→FC'27; AgentPay→Financial Innovation Q4–Q1) |

### Minor (non-blocking) suggestions

- **`paper-topics-proposal-2026-07.md` test-count nit**: it states WeightedSignature.t.sol has "49 用例"; current `test/WeightedSignature.t.sol` contains 43 test functions. Fix the number if the doc is meant to be referenced again — or leave as-is since the doc is flagged historical.
- **Historical doc carries an actionable-looking Q3–Q4 timeline** ("执行建议" + journal allocation). The header already says "下方分析仍有效，仅标签作废", which resolves the ambiguity, but consider adding one line pointing to `master-paper-roadmap-2026-07.md` §7 as the *live* timeline.

### Note

- `arXiv:2605.05774` (AOA) cited in the proposal is the author's own submission — **needs human verification** of the identifier before any paper cites it externally.
- Noted internally: no issue-linked DoD to check (PR body references #13 as branch provenance only).
