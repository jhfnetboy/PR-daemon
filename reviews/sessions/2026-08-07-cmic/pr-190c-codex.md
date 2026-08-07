PK CHALLENGE — jhfnetboy/CMIC#190, incremental round on commit 621181a. REFUTE the two findings below.

WORKING TREE (read-only, head 621181ae):
/private/tmp/claude-502/-Users-jason-Dev-tools-PR-Daemon/76b79141-505b-4469-bd90-4a90fffe7649/scratchpad/cmic-190c

SELF-CHECK (grep/sed/cat ONLY — no network, no node_modules, do not run tests):
  grep -n "cmic.shareToken" apps/web/src/sample.ts       # must hit ~460 and ~475
  grep -n "page_json" apps/api/schema.sql                # must hit ~480
If either misses, say so and STOP.

CONTEXT: this commit reworked the share snapshot from raw HTML to structured image blocks, in response to 5 blocking findings. Those 5 are verified fixed. These are the two NEW findings.

F1 [High] `apps/web/src/sample.ts:460,475` — STALE / DEAD share token handed to the sender.
`cmic.shareToken` is written at :460 and read at :475 (which sets `sharePromise`, so the 1200 ms timer never rebuilds). I claim there is NO `removeItem` for that key anywhere in `apps/web`, and therefore three reachable paths all silently serve a wrong token:
  (a) go back to chat, change colour/logo, return to the confirm page → recipient sees the OLD design;
  (b) start a new conversation ("+ New") → same old token;
  (c) click "Turn off this link" (revoke succeeds at ~:616) then click Share again → the modal serves the REVOKED token together with the text "Anyone with this link can see the design", and the recipient gets a 404.
REFUTE ME: find any `removeItem`/overwrite/expiry that clears `cmic.shareToken`; check `newChat()` in `apps/web/src/chat.ts` and `goToQuote()` for whether they clear it; check whether returning to `/sample.html` is a same-tab navigation that preserves sessionStorage; and check whether the revoke handler resets `sharePromise` or the storage. If any path is actually covered, say so.

F2 [Med-High] `scripts/deploy-review.sh:73` — the REVIEW environment never gets the `page_json` column.
I claim: `CREATE TABLE IF NOT EXISTS shares` already existed in `origin/preview`'s schema.sql (so the `cmic-review` D1 already has the table, and this commit's addition of `page_json` INSIDE that CREATE TABLE is a no-op there); `deploy-review.sh` applies ONLY `apps/api/schema.sql` at :73 with no migrations step at all; and the new column's ALTER lives only in `apps/api/migrations/0008-shares-page-json.sql`, which nothing in `scripts/` or `apps/api/package.json` ever executes. Net: every `POST /shares` in the review environment fails with `no such column: page_json` — reproducing the exact customer-reported symptom this PR set out to fix. REFUTE ME: find any step in `scripts/deploy-review.sh`, `apps/api/package.json`, `.github/workflows/`, or the deploy checklist under `docs/design/` that applies migrations to the review DB, or any reason the review DB would be recreated fresh.

Also answer briefly:
F3 — is `pickBlocks` (`apps/api/src/share.ts:234-249`) + `DATA_IMG` really airtight against a script-bearing payload reaching `<img src>` on the public share page? Consider MIME/content mismatch and webp.
F4 — `apps/api/src/share.ts:398` `readShare` re-runs `pickBlocks` and `assertNoCommercial(design)` but NOT `commercialTextIn(blocks)`. Does that matter, given the write path rejects on a hit?

Per finding output ONE line: [CHALLENGE|CONFIRM|MISSED] Fn — reason ≤25 words + the line numbers you actually read.
Then one final line: ANY OTHER REAL DEFECT you found that I did not list (or "NONE").
Return ONLY the structured critique.
