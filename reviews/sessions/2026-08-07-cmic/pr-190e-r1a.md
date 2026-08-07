FILES:
- apps/web/src/labels.ts — adds STOCK_LABEL map + stockLabel()
- apps/web/src/sample.ts — catch on buildShareBlocks, expiry check, shrink width
- apps/web/src/share.ts — Kind-typed LABELS, dedupe, stockLabel, title fix
- apps/web/test/labels.test.ts — STOCK_LABEL vs PAPER_SWATCHES consistency test
- scripts/deploy-review.sh — skip 0003, narrow error classification

FINDINGS:
1. [Medium] apps/web/src/sample.ts:512 — `sharePromise ??= createShareLink()` — if `sharePromise` is a rejected promise, `??=` keeps it, so the catch at :510 returns null, then `await sharePromise` at :513 re-throws the rejection (the `??=` does not reset it). The `catch(() => null)` at :510 only guards the `ready` branch; the later `const r = await sharePromise;` at :513 has no catch. | Reset sharePromise to null before rebuilding, or wrap the await in try/catch.

2. [Low] apps/web/src/share.ts:134 — `const title = fmt('text', design.typeName);` — if `typeName` is missing, title is now silently absent (no fallback to boxType), so the `<h1>` is empty instead of showing a fallback. The comment says the old fallback was wrong, but removing it entirely leaves no title for old snapshots. | Add a human-readable fallback for missing typeName.

3. [Low] apps/web/src/sample.ts:585 — shrink loop uses `[0.7, 0.8]` and `[0.55, 0.64]` — the width multiplier `w` is applied to both width and height, but the first iteration (q=0.7, w=0.8) may still exceed BLOCK_SRC_MAX if the original is very large; the second iteration (q=0.55, w=0.64) is the last chance, but if it still exceeds, the image is silently dropped (the `res(null)` path). The comment says "降质并降宽" but there's no third retry. | Add a third retry with lower width, or return the best-effort image instead of null.

TRIAGE: significant — core share logic, migration handling, and label translation fixes with new edge cases.

SKELETON:
The fixes address the prior review's findings well, but two new edge cases emerge: (1) the `??=` on `sharePromise` at sample.ts:512 preserves a rejected promise, so the `catch` at :510 doesn't protect the later `await sharePromise` at :513 — the button still dies; (2) the title fallback removal at share.ts:134 leaves an empty `<h1>` for old snapshots. The shrink loop's last retry can still silently drop an oversized image. The migration skip and error classification are correctly narrowed.