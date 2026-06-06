PR-Daemon autonomous watch review context for MushroomDAO/CometENS#6.

Prior CometENS review context checked manually:

- PR #4 (`45a0dcf`): the overloaded multicoin `addr(node, coinType)` encoding issue still exists on this branch, but it is already present on the PR base branch `feat/milestone-bcd`, so I did not treat it as a PR #6 regression.
- PR #4 (`45a0dcf`): the earlier cache-namespace scoping concern remains architectural context, but this PR's new cache TTL change does not newly introduce that behavior relative to the base branch.
- PR #5 (`74ffe44`): the plugin/registrar gate blocker is intentionally removed in this PR by deleting the B2 plugin architecture; that prior finding is no longer applicable to head `b3bfb19`.
- PR #5 (`74ffe44`): the earlier API-worker auth/nonce/bigint fixes remain intact on this head. I rechecked the server-side `verifyingContract` pin, post-auth nonce consumption, and `asBigInt` 400 path; none regressed here.

New PR #6 regressions verified on this head:

- `GET /resolve-status` can incorrectly mark proof-mode names as immediately resolvable based only on global anchor lag, and the register page then overwrites the pending countdown with a green "ready" state.
- `GET /lookup` changed its response contract and ownership check in a way that breaks the frontend fallback path and allows stale reverse-lookup entries to survive transfers.
