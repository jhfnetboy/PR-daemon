Findings

[Confirmed] High - `workers/gateway/src/index.ts:96` - The ABI dedup refactor breaks multicoin `addr(node, coinType)` responses. The two-argument branch now calls `encodeFunctionResult({ abi: L2RecordsV2ABI, functionName: 'addr', ... })` against an overloaded ABI, and the repo's `viem` resolves that to the single-argument `addr(bytes32) -> address` shape instead of `addr(bytes32,uint256) -> bytes`. I reproduced this locally: for the same 20-byte payload, the correct bytes result is dynamic-bytes ABI data, while the current code returns a padded address encoding, and non-20-byte multicoin payloads throw `InvalidAddressError`. This breaks ENSIP-11 / multicoin resolution for any client calling `addr(node, coinType)`. Use an unambiguous ABI item or a single-purpose ABI for the two-argument branch.

[Confirmed] High - `workers/gateway/src/index.ts:57` - The new KV resolver cache can sign stale records after contract redeploys or any out-of-band write. Cache keys are only `addr60:{node}`, `text:{node}:{key}`, and `ch:{node}`, the gateway serves cache hits without chain revalidation, and both workers reuse the same `RECORD_CACHE` namespace in `workers/gateway/wrangler.toml:24` and `workers/api/wrangler.toml:15` while this PR also moves `L2_RECORDS_ADDRESS` to a new contract. That means values cached for the previous deployment remain valid hits for the new contract and get signed as if they were current truth. Prefix cache keys with network plus contract address, or flush/revalidate the namespace on contract changes.

[Confirmed] Medium - `sdk/CometENS.ts:135` - The API split breaks existing SDK write flows. This PR removes the local `/api/manage/*` implementation from `vite.config.ts` and the gateway worker no longer serves compatibility routes, but the exported SDK in `sdk/index.ts:1` still derives its write base from `gatewayUrl` and POSTs to `/api/manage/register` and `/api/manage/set-addr`, while `sdk/types.ts:13` still exposes no `apiUrl`. Existing SDK consumers now 404 on writes unless you keep compatibility routes or ship the SDK update in the same PR.

Rejected Local Findings

Rapid-MLX repeatedly flagged earlier security issues that are already fixed in this head: `workers/api/src/index.ts` now hardcodes `env.L2_RECORDS_ADDRESS` for EIP-712 verification, moves `consumeNonce(...)` after auth/ownership checks, and throws `badReq(...)` from `asBigInt(...)`. Those are no longer blockers on `45a0dcf`.

Local Model Summary

Rapid-MLX was useful for broad triage, but it overfit to the PR description's old review history and missed the two regressions introduced by the gateway/ABI/cache refactor. I treated its output as hypotheses only and re-verified everything against the current code and local reproductions.

Verification

- `git diff --stat origin/main...45a0dcfdf74cc630384a6fdfe1f63a203889de46`
- `git show 45a0dcfdf74cc630384a6fdfe1f63a203889de46:workers/gateway/src/index.ts`
- `git show 45a0dcfdf74cc630384a6fdfe1f63a203889de46:workers/api/src/index.ts`
- `git show 45a0dcfdf74cc630384a6fdfe1f63a203889de46:sdk/CometENS.ts`
- Local `node` reproduction with the repo's `viem` showing the overloaded `addr` encoding mismatch
- `pnpm typecheck`
- `pnpm build` could not complete in this checkout because Rollup's optional native package `@rollup/rollup-darwin-arm64` is missing locally

Conclusion: REQUEST_CHANGES
