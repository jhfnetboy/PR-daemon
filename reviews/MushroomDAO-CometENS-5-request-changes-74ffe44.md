Findings

[Confirmed] High - `workers/gateway/src/index.ts:111` - Multicoin `addr(node, coinType)` is still encoded against the overloaded ABI, so the gateway signs the wrong payload shape for 20-byte values and throws for non-20-byte values. The two-argument branch calls `encodeFunctionResult({ abi: L2RecordsV2ABI, functionName: 'addr', ... })` against both `addr` overloads. I re-ran this with the repo's installed `viem` on this head: a bytes result like `0x123456` throws `InvalidAddressError`, and a 20-byte result is encoded as a padded `address` instead of dynamic `bytes`. Use a single-purpose ABI item for the two-argument `addr` path.

[Confirmed] High - `contracts/src/L2RecordsV3.sol:86` and `workers/api/src/index.ts:339` - Milestone B2's plugin model never enables the advertised permissionless / whitelist / fee registration flow. Both the contract and `/register` still require the caller to be the contract owner or an explicit registrar before any plugin check runs, so `FreePlugin`, `WhitelistPlugin`, and `FlatFeePlugin` are only extra checks layered on top of the old registrar gate. The tests mask this by always adding a registrar or calling through the contract owner. If plugins are meant to replace registrar auth when attached, remove the owner/registrar precondition for plugin-backed registration and add API coverage for that path.

[Confirmed] High - `workers/gateway/src/index.ts:80` and `workers/api/wrangler.toml:30` - The resolver KV cache is still not scoped by network or contract address, so the gateway can sign stale records after contract redeploys or worker retargeting. Cache keys are only `addr60:{node}`, `text:{node}:{key}`, and `ch:{node}`; the gateway serves KV hits without chain revalidation; and both workers bind the same `RECORD_CACHE` namespace. Prefix keys with network plus contract address, or flush/revalidate the namespace whenever `L2_RECORDS_ADDRESS` changes.

[Confirmed] Medium - `sdk/CometENS.ts:135` - The public SDK write surface is still incompatible with the split API worker. It derives writes from `gatewayUrl` and still POSTs to `/api/manage/register` and `/api/manage/set-addr`, while the current frontend/API worker use `/register` and `/set-addr` on `apiUrl`, and `sdk/types.ts:13` still exposes no `apiUrl`. Existing SDK write calls will 404 unless you keep compatibility routes or update the SDK in the same PR.

Rejected Local Findings

The earlier API-worker security issues from the previous review do look fixed on this head: server-side `verifyingContract` pinning is in place, nonce consumption now happens after auth checks, malformed bigint input returns 400, deadline TTL is capped, and missing gateway `sender` is rejected instead of defaulting to zero.

Local Model Summary

Rapid-MLX was useful for broad triage and for re-checking the old CometENS review context, but it kept violating the output contract by emitting hidden process text instead of just the requested sections. I treated all local-model output as hypotheses only and independently re-verified the final findings in code and commands.

Verification

- Used local repo worktree: `/Users/jason/Dev/mycelium/CometENS-pr5-review`
- `git diff --stat origin/main...74ffe4409435c27016d6ae4633469548d2141abc`
- `gh pr view 5 --repo MushroomDAO/CometENS --json title,body,commits,files,latestReviews,reviewDecision`
- `pnpm install --frozen-lockfile`
- `pnpm typecheck`
- Local `node` reproduction with installed `viem` showing the overloaded `addr` encoding mismatch:
  - non-20-byte bytes result throws `InvalidAddressError`
  - 20-byte bytes result encodes differently from the explicit two-argument ABI
- `pnpm test -- --run test/unit/nonce-store.test.ts test/unit/transfer-subnode.test.ts test/unit/schemas.test.ts` could not start because this environment is missing the optional native package `@esbuild/darwin-arm64`

Conclusion: REQUEST_CHANGES
