SECURITY_FINDINGS:
1. [Medium] scripts/deploy-review.sh:87-88 — SKIP_MIGRATIONS hardcodes 0003 migration skip; if table state diverges, data loss | fix: use schema_migrations ledger instead of hardcoded skip
2. [Low] scripts/deploy-review.sh:90-91 — grep pattern `index .* already exists` may miss other idempotent errors, causing false failures | fix: broaden pattern or use ledger

SECURITY_TRIAGE: low — deploy script migration handling has edge cases but no direct auth/crypto issue