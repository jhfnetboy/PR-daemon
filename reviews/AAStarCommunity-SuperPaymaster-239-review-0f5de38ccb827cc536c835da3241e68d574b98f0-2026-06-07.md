## PR Review: AAStarCommunity/SuperPaymaster#239 — Dependabot auto-merge CI

**Verdict: COMMENT** (1 improvement suggestion)

### Findings

**[PK-added] Medium** `.github/workflows/dependabot-auto-merge.yml:40-46` — Auto-merge not pinned to head commit SHA
- `gh pr merge --auto --squash "$PR_URL"` queues auto-merge without `--match-head-commit`
- If PR head changes between approval and merge execution, new un-reviewed code auto-merges
- Fix: add `--match-head-commit "$HEAD_SHA"` binding to `${{ github.event.pull_request.head.sha }}`
- Bonus: add `concurrency: { group: dependabot-auto-merge-${{ github.event.pull_request.number }}, cancel-in-progress: true }` to prevent stale-run races

### Confirmed Safe
- No `actions/checkout` — pull_request_target safe from pwn-request ✅
- Triple guard (actor + author + repo) ✅
- Action pinned to commit SHA ✅
- Major bumps label-only, never auto-merge ✅
- Branch protection gates actual merge ✅

### PK Summary
| Finding | Result |
|---------|--------|
| Auto-merge not head-pinned | **PK-added** Medium — improvement, not blocker |
| pull_request_target safety | Confirmed safe |
| Triple guard + major exclusion | Confirmed safe |
