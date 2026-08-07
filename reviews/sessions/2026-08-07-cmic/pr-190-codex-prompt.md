PK CHALLENGE — jhfnetboy/CMIC#190 `feat(share)`. Your job is to REFUTE the findings below, not agree with them.

WORKING TREE (read-only, checked out at PR head 4d51d7d9):
/private/tmp/claude-502/-Users-jason-Dev-tools-PR-Daemon/76b79141-505b-4469-bd90-4a90fffe7649/scratchpad/cmic-190

SELF-CHECK FIRST (grep/sed/cat ONLY — no network, no npx/pnpm/vitest/python; do not try):
  grep -n 'ALTER TABLE shares ADD COLUMN page_html' apps/api/schema.sql    # must hit ~495
  grep -n 'buildSharePage' apps/web/src/sample.ts                          # must hit
If either misses, say so and STOP.

WHAT THE PR DOES: public share link for the quote page. The image is now optional; instead the CLIENT uploads a price-stripped HTML snapshot of the confirmation page (`page_html`), which the public anonymous share page renders. Also pre-generates the link 1.2s after page load.

FINDINGS TO CHALLENGE — all statically decidable from the tree:

F1 [High] `apps/api/schema.sql:495` — a non-idempotent `ALTER TABLE shares ADD COLUMN page_html TEXT;` was added to a file that `scripts/deploy-review.sh:73` applies wholesale every deploy. I claim: base had ZERO executable ALTERs (only `--` comments at :216/:247/:326), deploy-review.sh is `set -euo pipefail` and the schema apply is step 1 of 3, so the SECOND deploy aborts with `duplicate column name`. The same statement already exists as `migrations/0008-shares-page-html.sql`, making the schema.sql copy redundant. REFUTE ME: is there anything that makes the re-apply safe (a flag on wrangler, an IF NOT EXISTS, error tolerance, the file never being re-applied)? Read deploy-review.sh fully.

F2 [High] `apps/api/src/share.ts` — `page_html` crosses the trust boundary with NO server-side validation. I claim `assertNoCommercial` runs on `design` at :245 and :294 but never on `input.pageHtml`; it is stored raw at :262 and returned raw at :292; the only server check is `typeof string && length <= SHARE_PAGE_MAX` at `index.ts:1204`; ALL real stripping is in `apps/web/src/sample.ts` `buildSharePage()` (clone `.quote-left`, remove `button/input/select/textarea/script`, currency regex). REFUTE ME: find any server-side sanitization, whitelist, or assertion applied to page_html anywhere in apps/api. Also state whether `POST /shares` can be called directly by any authenticated user with arbitrary page_html (read the route + auth in index.ts).

F3 [High] `apps/web/src/share.ts:81` — `host.innerHTML = data.pageHtml` on the public share page, no sanitization, no CSP. I claim the `<script>` removal lives only in the attacker's own browser, and `innerHTML` still allows `onerror`/`onload`/`<iframe>`. REFUTE ME: grep the whole tree for any CSP header or sanitizer reaching share.html.

F4 [High] `apps/web/src/sample.ts:139` — `new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })` has NO `preserveDrawingBuffer`, yet `buildSharePage()` (~:500) calls `live.toDataURL('image/png')` on that same canvas from a setTimeout. I claim the capture is a blank/transparent PNG that does not throw, so the `if (url)` guard passes and a blank image ships. Corroborating: `sample.ts:223-224`, `funnel.ts:228`, `customer.ts:534` ALL set `preserveDrawingBuffer: true`, and :223's own comment says "渲完立刻 toDataURL 取图(否则拿到空白)". REFUTE ME: is there any other mechanism (a render call immediately before the capture inside the same task, a different canvas being captured, `alpha` semantics) that makes the capture valid? Identify exactly WHICH canvases `left.querySelectorAll('canvas')` matches by reading `apps/web/sample.html`.

F5 [High] `apps/api/src/share.test.ts:487-490` — the loop `for (const bad of ['$','USD','MOQ','unitPrice','12.34']) ok(..., !got.text.includes(bad))`, labelled 「🔴 快照也不许带商务信息」, is VACUOUS: the `PAGE` fixture a few lines above contains none of those strings, and no server code strips them. Deleting all page_html handling leaves it green. REFUTE ME: is there any path by which that assertion could go red?

F6 [Medium] `apps/api/src/index.ts:1191-1197` — the daily create quota (`SHARE_CREATE_PER_DAY`) is incremented BEFORE `id(b.conversation_id, ...)` validation and before `createShare`, and is never refunded when either fails. Combined with an unconditional pre-generation `setTimeout(..., 1200)` in sample.ts, every page load spends a slot. REFUTE ME: is the quota refunded anywhere, or is validation actually earlier than I think?

Per finding output ONE line: [CHALLENGE|CONFIRM|MISSED] Fn — reason ≤25 words + the line numbers you actually read.
Then one final line: ANY OTHER REAL DEFECT you found that I did not list (or "NONE").
Return ONLY the structured critique.
