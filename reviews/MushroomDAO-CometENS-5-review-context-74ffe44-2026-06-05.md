PR-Daemon autonomous watch review context for MushroomDAO/CometENS#5.

Review target:
- Repository: MushroomDAO/CometENS
- PR: #5
- Base: main
- Head: feat/milestone-bcd
- Head OID: 74ffe4409435c27016d6ae4633469548d2141abc

Constraints:
- Treat local-model output as hypotheses only.
- Focus on bugs, regressions, security issues, cache invalidation, API contract breaks, plugin architecture risks, proof-path correctness, and missing tests.
- Avoid style-only feedback.

Prior blockers from the earlier review on this branch family that must be explicitly re-verified:
- Gateway multicoin `addr(node, coinType)` ABI encoding broke because the overloaded `addr` ABI resolved to the single-argument address variant.
- Resolver KV cache keys were not scoped by network or contract address, allowing stale signed answers after redeploys or out-of-band writes.
- Public SDK write methods still posted to removed `/api/manage/*` routes and had no separate `apiUrl`.

Adversarial checks to verify on this head:
- Does any gateway proof/signature branching mis-handle overloaded ABI encoding, contenthash bytes, or multicoin address bytes?
- Can cache reads survive contract upgrades, proof-mode toggles, or resolver writes with stale data because keys or invalidation are incomplete?
- Do plugin add/remove/execute paths preserve authorization boundaries and avoid silently bricking registrations or transfers?
- Do transfer and registration flows keep owner, signer, registrar, and primary-node semantics consistent after the plugin refactor?
- Does the split frontend/API/gateway deployment still preserve public SDK compatibility and expected routes?
- Do production/testnet deployment scripts update the right worker/config targets without leaking stale contract addresses?
- If the prior blockers are fixed, say that clearly instead of repeating them.

Reminder:
- Report only issues grounded in the final head state.
- Include concrete fixes.
