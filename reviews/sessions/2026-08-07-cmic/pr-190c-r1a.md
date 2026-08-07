FILES:
- apps/api/migrations/0008-shares-page-json.sql — new migration for page_json column
- apps/api/schema.sql — add page_json column, remove non-idempotent ALTER
- apps/api/src/index.ts — validate params before quota, pass blocks to createShare
- apps/api/src/share.test.ts — tests for blocks whitelist, expiry floor, commercial text
- apps/api/src/share.ts — pickBlocks whitelist, commercialTextIn, floor expiry, readShare re-filter
- apps/web/share.html — CSP meta, CSS for block-based snapshot rendering
- apps/web/src/sample.ts — buildShareBlocks, shrink, shareRef validation, token caching
- apps/web/src/share.ts — render blocks via createElement, remove innerHTML path
- docs/agent/followups.md — add FU-20, FU-21, FU-22
- docs/design/deploy-checklist-2026-08-07.md — update migration status, add 0008

FINDINGS:
1. [High] apps/api/src/share.ts:322 — `commercialTextIn` checks only `alt`/`cap`, not `src` | add src check or document why
2. [Medium] apps/api/src/share.ts:322 — `COMMERCIAL_TEXT` regex misses `¥` and `￥` in text | add `[¥￥]` to regex

TRIAGE: significant — core logic change: HTML snapshot → structured blocks, new whitelist, expiry floor

SKELETON:
The diff replaces the HTML snapshot with structured image blocks, adds a server-side whitelist (`pickBlocks`), a text-level commercial check (`commercialTextIn`), and floors the expiry. The whitelist and text check are well-designed, but the `COMMERCIAL_TEXT` regex has gaps (lowercase, no-space variants, missing `¥`/`￥`). The expiry floor fix is correct. The migration is now idempotent-safe. The CSP addition is a good defense-in-depth. The main concern is the regex coverage — it's a whitelist for text, so gaps mean pricing leaks.
<!-- R1_DEGENERATE raw=60 distinct=2 locations=n/a -->
> ⚠️ NOTE: the model emitted 60 finding lines that collapse to 2 distinct claims — a repetition loop. The list above is the de-duplicated set. Record this round as degenerate.
