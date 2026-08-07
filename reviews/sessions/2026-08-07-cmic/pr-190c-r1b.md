SECURITY_FINDINGS:
1. [Medium] apps/api/src/share.ts:214 — COMMERCIAL_TEXT regex may miss pricing variants | expand regex or use structured price detection
2. [Low] apps/api/src/share.ts:214 — COMMERCIAL_TEXT regex may false-positive on base64 | exclude src from text scan (already done)

SECURITY_TRIAGE: low — input sanitization improved, minor regex coverage gaps remain