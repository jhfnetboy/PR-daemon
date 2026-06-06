# Local Model Review Evaluation: MushroomDAO/CometENS#5

- Date: 2026-06-05
- PR head: `74ffe4409435c27016d6ae4633469548d2141abc`
- Model: `qwen3.6-a3b`
- Local review: `reviews/MushroomDAO-CometENS-5-local-review-74ffe44-2026-06-05.md`
- Final GitHub review: `REQUEST_CHANGES` to be posted as `clestons`
- Score: `1.5 / 10`

## What Helped

The local model was mildly useful for broad triage and for reminding the review
loop to re-check the old CometENS blockers instead of assuming they were fixed.
Its challenge pass also treated the transfer/lookup concern as weaker than the
core contract/API blockers, which matched Codex's final prioritization.

## False Positives / Compliance Failures

- It repeatedly violated the required output contract by emitting hidden
  reasoning / process narration instead of only the requested sections.
- The challenge/comment-draft prompt did not return a usable GitHub review body
  because it prefaced the draft with internal reasoning text.
- The long-form broad-pass run over the full diff stalled after partial chunk
  progress and did not produce a final machine-generated review artifact.

## What It Missed

Codex had to independently verify the actual blockers:

- the gateway still mis-encodes multicoin `addr(node, coinType)` responses when
  `encodeFunctionResult(...)` is called through the overloaded ABI,
- the plugin architecture still preserves the old owner/registrar gate instead
  of enabling the advertised permissionless / whitelist / fee registration flow,
- the shared KV resolver cache is still unscoped by network/contract address, so
  stale signed resolver answers survive redeploys or worker retargets, and
- the public SDK write surface still points at removed `/api/manage/*` routes.

## Prior Improvement Assessment

The carried-forward improvement item from CometENS #4 was ineffective. Even with
explicit instructions to return only structured sections, the model still
emitted hidden reasoning/process narration in both the chunked broad pass and
the challenge/comment-draft pass.

## Prompt Improvement

- For structured review and comment-draft prompts, return only the requested
  sections; never emit hidden reasoning, planning text, or a "thinking process"
  preamble.
- When prior findings are provided, explicitly separate "still broken" from
  "fixed on this head" instead of mixing old context into the live finding list.
- For contract feature reviews, check whether access-control modifiers still gate
  the advertised path before trusting changelog language or passing tests.

## Codex Adjudication

Codex independently verified four blockers on `74ffe44` and prepared a
`REQUEST_CHANGES` review:

- multicoin `addr(node, coinType)` encoding is still broken in the gateway,
- plugin-backed registration is still gated by contract-owner/registrar auth,
- resolver cache keys are still not scoped by network/contract identity, and
- the public SDK still writes to removed `/api/manage/*` routes.

## Verification

- Used local repo worktree: `/Users/jason/Dev/mycelium/CometENS-pr5-review`
- Ran `git diff --stat origin/main...74ffe4409435c27016d6ae4633469548d2141abc`
- Ran `gh pr view 5 --repo MushroomDAO/CometENS --json title,body,commits,files,latestReviews,reviewDecision`
- Ran `pnpm install --frozen-lockfile`
- Ran `pnpm typecheck`
- Ran local `node` repros with installed `viem` showing:
  - non-20-byte multicoin bytes throw `InvalidAddressError` through the
    overloaded `addr` ABI path, and
  - 20-byte multicoin bytes encode differently from the explicit two-argument ABI
- Attempted `pnpm test -- --run test/unit/nonce-store.test.ts test/unit/transfer-subnode.test.ts test/unit/schemas.test.ts`, but Vitest could not start because this environment is missing the optional native package `@esbuild/darwin-arm64`
