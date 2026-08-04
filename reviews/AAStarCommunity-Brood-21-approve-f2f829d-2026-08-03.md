## ✅ APPROVE — [4-round] v4 pipeline

Re-review at `f2f829d` ("fix(progress-chart): make single-entry history render without crashing"). Both blockers from the prior REQUEST_CHANGES round (against `4919285`) are verified fixed — no re-flag.

**审查轮次**
- **R1a DeepSeek（full）**：3 findings，2 upheld
- **R1b DeepSeek（security）**："no security surface" — disproved by later rounds (innerHTML DOM-XSS vector)
- **R2 Opus（strategic）**：独立读 diff + 用 Playwright 实测两个历史 blocker（0/1/2-entry 场景），新增 Medium/Low findings
- **R3 Codex（PK, gpt-5.5）**：确认两个 Medium+ findings，独立发现 R2 遗漏的 innerHTML DOM-XSS 向量
- **R4 Opus（final）**：APPROVE

### Prior blockers — resolved
1. **[High] dead `<2 entries` guard** — fixed. `buildSummary()` now does `prev=HISTORY[HISTORY.length-2]||last`; `xOf`/`nearest` are guarded against `HISTORY.length<=1`. Verified in a real browser for 0/1/2-entry history: no crash, no console errors.
2. **[Medium] `dist/index.html` drift from generator** — fixed. Byte-compared: `generateProgressChartHtml()`'s output is identical to committed `dist/progress-chart.html` (11851/11851 chars), and the nav-link snippet in `dist/index.html` is byte-identical to the one in `scripts/export-backlog.js`. No cross-file drift.

### New findings (non-blocking — suggestions for a follow-up)

- **[Medium] `scripts/export-backlog.js:317-329` + `:544-556`** — the sidebar nav link is injected into `dist/index.html` unconditionally, on a code path independent of whether chart generation later succeeds. Chart generation is wrapped in a try/catch that only `console.warn`s (build exits 0 regardless), and `dist/` is fully wiped (`fs.rm`) at the start of every export. Net effect: a missing/malformed `backlog/data/progress-history.json` at build time ships a nav link pointing to a page that was never (re)written that run — a silent dead link on an apparently-successful build. `dist/api/progress-history.json` is written inside the same try block, so on failure it's fully absent (not stale). Fix: gate the nav-link injection on chart generation actually succeeding, or make the catch fail the build (`process.exitCode = 1` / rethrow).
- **[Low] `scripts/export-backlog.js:657`** — `const HISTORY=${JSON.stringify(history)};` is interpolated raw into an inline `<script>` tag with no escaping of `</script>` or U+2028/U+2029. Live-reproduced: a history entry with `"date":"</script><img src=x onerror=...>"` terminates the script context and materializes a live `onerror` element in the DOM. Currently low-risk since the data file is human-maintained (its own `description` field says "no automated writer yet" — implying one may land later, at which point this becomes load-bearing). Fix: `.replace(/</g,'\\u003c')` plus U+2028/U+2029 before interpolating.
- **[Low] `scripts/export-backlog.js:655`** — separate injection vector from the one above and survives fixing it in isolation: `row.innerHTML+=\`...${val}%...\`` where `val=last[p.key]` (the p1/p2/p3 field) is interpolated unescaped. Nothing enforces the field is numeric — if it were ever a string containing markup, it executes as DOM-based XSS on page load, no interaction required. Fix: build the chip via `textContent`/`createElement`, or coerce with `Number(val)`.
- **[Low] `scripts/export-backlog.js:544-547`** — no schema validation after `JSON.parse`. Not a crash: a malformed row (e.g. missing/null `p1`) renders `null%`/`NaN` in the chip and silently drops that series' segment from the canvas — wrong data displayed with no error surfaced. Fix: validate `date` + numeric `p1/p2/p3` per row.
- **[Low] `scripts/export-backlog.js:655` + generated CSS** — delta class is `diff>0?'up':'same'`; only `.chip-delta.up` is defined in the stylesheet, no `.down`. The committed data already contains a real regression (2026-04-26, p1 53→52), which renders in neutral grey, visually indistinguishable from "no change." Fix: add `diff<0?'down':'same'` and a `.chip-delta.down` CSS rule.
- **[Low] `scripts/export-backlog.js:648/641`** — the x-axis is index-spaced but tick labels are calendar dates; the committed data has 8–18 day gaps drawn at identical width, so slope reads as constant rate-of-change when it isn't. Fix: scale x by parsed date, or relabel the axis as scan index.
- **[Low] `scripts/export-backlog.js:566`** — `history` is drawn in array order with no sort/dedupe by date; an out-of-order hand-appended row (the file's own description implies manual maintenance) draws a backwards zigzag instead of being corrected.
- **[Nit]** dead `DONE` flag in the nav-link IIFE (read-after-`clearInterval` always fires first, so it's never observably true); no `#__prog_nav_link` existence guard against double-injection if the snippet runs twice.

**结论**：None of the above are crashes or exploitable via untrusted/user-facing input today — this is a build-time script over a repo-committed, human-edited JSON file with no runtime user input anywhere in the feature. Approving on that basis; recommend a fast follow-up for the Medium (silent-failure-ships-dead-link) and the two Low injection findings before an automated writer is added to `progress-history.json`, per the file's own "no automated writer yet" comment.

---
**Posted to GitHub**: 2026-08-03T09:13:59Z as clestons (APPROVED), commit `f2f829dcc0603d1bd0bf4d1f5d554c175cd1fa1a`.
**model_eval_db**: run #956, provider=deepseek, model=deepseek-v4-flash, score=7.0, verdict=APPROVE, codex_only_findings=1.

**Note (backfill 2026-08-03 16:15 +07)**: this review was fully executed and posted in a prior watcher cycle that was killed (SIGTERM, rc=143, `review-eval.tsv` row `2026-08-03T16:15:13 AAStarCommunity/Brood#21 claude(real-anthropic) 1140s rc=143`) after posting to GitHub and recording model_eval_db, but before writing this archive file or updating `pr_watch_targets`. This invocation only backfills those two records — no new review round was run, per feedback_incremental_diff_on_resubmit.md (head unchanged since the already-posted APPROVE).
