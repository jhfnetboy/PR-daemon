## PR Review: MushroomDAO/CometENS#4 — feat: production API server (Phase 1-3) + security hardening

**Verdict: REQUEST_CHANGES** (1 critical missed finding)

### Findings

**[PK-added] High** `workers/api/wrangler.toml` + `workers/api/src/index.ts:510` — Production replay protection effectively disabled
- `consumeNonce()` silently no-ops when no KV binding exists: `if (!kv) return`
- `workers/api/wrangler.toml` has `REGISTRY` and `RECORD_CACHE` bindings **commented out** under `[env.production]`
- `scripts/deploy-production.sh` only pushes secrets, no KV-binding preflight check
- Result: ALL production write endpoints have ZERO replay protection
- Fix: bind real KV namespaces under `[env.production]`, make `consumeNonce` fail closed in prod, add deploy preflight

**[PK-added] Low** `workers/api/src/index.ts:103` — Error messages leak internal details
- Top-level catch returns raw `e.message` to clients
- Exposes viem/RPC/internal failure details from production endpoints
- Fix: return generic 500 for unexpected errors, log details server-side only

### Confirmed Safe
- admin.html client-side security ✅
- Deployment secret fallback handling ✅
- Auth enforcement & input validation bypasses ✅

### PK Summary
| Finding | Result |
|---------|--------|
| Production nonce disabled | **PK-added** High — KV bindings commented out |
| Error message leak | **PK-added** Low |
| admin.html / deployment / auth | Confirmed safe |
