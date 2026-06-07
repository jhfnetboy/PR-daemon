## PR Review: MushroomDAO/CometENS#6 — refactor: remove B2 plugin arch, D1 Durable Objects; disable plugin

**Verdict: REQUEST_CHANGES**

### Findings

**[PK-added] High** `workers/api/src/index.ts` — KV-only nonce consumption introduces replay race for write endpoints
- The Durable Object `NONCE_STORE` was removed; `consumeNonce()` now relies solely on KV
- KV is eventually consistent across Cloudflare PoPs (~1-2s window per documentation)
- Concurrent same-nonce requests to `/register`, `/set-text`, `/set-contenthash`, `/transfer-subnode` can both pass before KV converges
- This enables replay attacks on all state-changing endpoints
- Fix: either restore the Durable Object nonce path, or add a chain-level nonce check in the contract (e.g. incrementing on-chain nonce per signer)

**[PK-added] Medium** `workers/api/src/index.ts` — Replay protection fails open
- New `consumeNonce()` starts with `if (!kv) return` — skip replay protection entirely
- Old version failed closed when no storage was configured
- A misconfigured/local deployment silently disables nonce enforcement
- Fix: at minimum, log a warning; better: throw an error in production environments

**[Confirmed] Low** `contracts/src/L2RecordsV3.sol` — ReentrancyGuard removal
- `nonReentrant` stripped from `registerNode()` and `registerSubnode()`
- BUT the dangerous `withdrawFees()` (with `msg.sender.call`) was also removed
- Plugin system removed → no external calls to untrusted contracts remain
- ETH handling (payable, msg.value, excess refund) fully removed
- `_safeMint` from OZ ERC721 retains its own reentrancy guard
- Verdict: net security improvement — less code, fewer attack surfaces

### Rejected
- ReentrancyGuard removal overstated — Codex correctly noted the diff doesn't show `_registerNode` or `_safeMint` context; the actual call chain is safe

### Contract Changes Summary
- ✅ Plugin arch removed (IRegistrarPlugin, FreePlugin, WhitelistPlugin, FlatFeePlugin)
- ✅ `registerSubnode()` no longer payable — zero ETH handling surface
- ✅ `unruggable-gateways@v1.3.5` submodule added for OP fault proof verification
- ✅ DeployOPResolver upgraded to C3 architecture (FaultVerifier + GameFinder)

### PK Summary
| Finding | Result |
|---------|--------|
| ReentrancyGuard removal | Rejected — net security improvement |
| ETH/payable removal | Confirmed |
| unruggable-gateways submodule | Confirmed |
| KV nonce replay race | **PK-added** — critical |
| Replay protection fails open | **PK-added** — real |
