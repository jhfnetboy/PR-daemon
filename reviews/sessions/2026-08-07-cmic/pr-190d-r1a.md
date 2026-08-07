FILES:
- apps/api/src/share.ts — drop blocks from tail until under limit
- apps/web/share.html — add swatch CSS for color display
- apps/web/src/chat.ts — clear shareToken/shareRef in newChat
- apps/web/src/sample.ts — cache with ref, wait views, revoke clears state
- apps/web/src/share.ts — label mapping, hex swatches
- docs/agent/followups.md — add FU-23 watermark finding
- scripts/deploy-review.sh — apply migrations after schema

FINDINGS:
1. [High] apps/web/src/sample.ts:480 — cached token reused without checking expiry | add `expiresAt > Date.now()` to reuse condition
2. [Med] apps/web/src/sample.ts:483 — `shareRef()` may throw if called before init | wrap in try/catch or check null
3. [Low] apps/web/src/share.ts:55 — `paperLabel`/`laminationLabel` may return undefined for unknown keys | fallback to raw value if undefined

TRIAGE: significant — fixes prior review findings, adds migration runner

<4-line draft review comment>
The prior review's five blocking findings are all addressed: cache now includes ref, newChat clears share keys, revoke clears state, views are awaited, and migrations run in review deploy. The tail-drop and quality-retry fixes address the Low findings. One new issue: cached token reuse doesn't check expiry — a stale token could be served after expiration. Also, `shareRef()` is called at module scope before initialization, which could throw. The migration runner correctly handles non-idempotent ALTERs by swallowing duplicate-column errors.
</4-line draft review comment>