# Local Model Review Evaluation: MushroomDAO/CometENS#4

- Date: 2026-06-05
- PR head: `45a0dcfdf74cc630384a6fdfe1f63a203889de46`
- Model: `qwen3.6-a3b`
- Local review: `reviews/MushroomDAO-CometENS-4-local-review-45a0dcf-2026-06-05.md`
- SQL run id: `7`
- Final GitHub review: `REQUEST_CHANGES` posted as `clestons`
- Score: `2.5 / 10`

## What Helped

The local model completed a full five-chunk broad pass and did eventually
re-verify several fixes that are genuinely present in the final head: server-side
`verifyingContract` pinning, moving `consumeNonce(...)` after auth checks,
`badReq(...)`-based bigint validation, deadline capping, normalized-label
enforcement, and rejecting missing gateway `sender`.

## False Positives

It kept reporting already-fixed issues from earlier commits as if they were still
live on `45a0dcf`: client-controlled `verifyingContract`, missing nonce replay
checks, signer-vs-owner `primaryNode` validation, 500s on malformed bigint
input, unbounded deadline windows, and missing sender handling in the gateway.

## What It Missed

It missed the blockers that actually matter in the final merged code:

- The gateway now mis-encodes multicoin `addr(node, coinType)` results because
  `encodeFunctionResult(...)` is called through the full overloaded ABI instead
  of an unambiguous `bytes` ABI item.
- The new KV resolver cache is not scoped to contract or network, so old values
  can survive a contract redeploy and still be signed as current resolver truth.
- The exported SDK still posts writes to removed `/api/manage/*` routes and has
  no `apiUrl` option, so existing SDK consumers break under the new split-worker
  architecture.

## Prior Improvement Assessment

Not applicable. There were no prior model-eval runs or carried-forward
improvement items for this PR.

## Prompt Improvement

- When a PR touches the same file multiple times across a patch series, the model
  must reconcile everything into the final head state instead of treating early
  hunks as still authoritative.
- For ABI refactors, the model must explicitly check overloaded encode/decode
  paths and not assume `functionName` lookups remain safe after deduplication.
- When asked for structured output or a comment draft, the model must return only
  the requested sections and never emit hidden-reasoning markers or process text.

## Codex Adjudication

Codex independently verified three blockers on `45a0dcf` and posted a
`REQUEST_CHANGES` review:

- multicoin `addr(node, coinType)` encoding is broken after the gateway switched
  to the full overloaded ABI,
- the KV cache can serve stale signed resolver answers across contract redeploys
  because keys are not scoped to contract or network and cache hits are not
  revalidated, and
- the public SDK write surface still targets removed `/api/manage/*` routes.

## Verification

- Used local repo: `/Users/jason/Dev/mycelium/CometENS`
- Ran `git diff --stat origin/main...45a0dcfdf74cc630384a6fdfe1f63a203889de46`
- Ran `git show` on the reviewed head for `workers/gateway/src/index.ts`,
  `workers/api/src/index.ts`, `workers/*/wrangler.toml`, `sdk/CometENS.ts`, and
  `sdk/types.ts`
- Reproduced the overloaded `addr` encoding mismatch with a local `node` script
  using the repo's installed `viem`
- Ran `pnpm typecheck`
- Tried `pnpm build`, which failed because this checkout is missing Rollup's
  optional native package `@rollup/rollup-darwin-arm64`
