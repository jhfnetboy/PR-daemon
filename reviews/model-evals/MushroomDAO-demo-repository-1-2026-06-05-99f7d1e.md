# Local Model Evaluation - MushroomDAO/demo-repository PR #1 99f7d1e

Date: 2026-06-05
Model: qwen3.6-a3b via Rapid-MLX
PR: https://github.com/MushroomDAO/demo-repository/pull/1
Head reviewed: 99f7d1ee03a2a2f069b8b9193ae5f1e34229d283
SQL run id: 6
GitHub review: APPROVE posted as clestons

## Score

4.0 / 10

## Prior Improvements Applied

- None. No prior model-eval runs or carried-forward improvement items existed for this PR.

## Did The Prior Improvements Actually Improve Output?

Not applicable. There were no prior improvement items to evaluate on this run.

## Useful Contribution

- Kept the broad pass appropriately narrow and non-blocking for a documentation-only diff.
- Prompted the one check that mattered: verify the referenced workflow files exist before approving.

## False Positives

- Treated missing workflow files as a live risk without checking the repository tree first.

## Misses

- Failed the challenge/comment-draft step twice by emitting hidden reasoning instead of a usable final review body.
- Did not explain that external badge URL `404` responses are expected in this private-repository context, so Codex had to resolve that separately.

## Prompt Gaps

- The challenge and comment-draft prompts still allow process-text leakage.
- The local model needs a stronger rule to separate repository-verifiable facts from speculation.

## Next Prompt Improvements

- When asked for a GitHub comment draft, return only the final review body and final conclusion line with no preamble, analysis, or labels.
- Do not speculate that referenced files may be missing when the repository tree can verify them; mark that case uncertain until checked.

## Codex Adjudication

No confirmed findings. Codex verified that the only diff is the two badge lines in `README.md`, that the referenced workflow files exist on `main`, and that the badge path format matches GitHub's documented workflow badge pattern. The repo is private, which explains why direct unauthenticated badge fetches returned `404` outside the GitHub UI context. Final decision: `APPROVE`.

## Verification

- Used local repo: `/Users/jason/Dev/mycelium/demo-repository`
- Ran `git diff --unified=20 origin/main...99f7d1ee03a2a2f069b8b9193ae5f1e34229d283 -- README.md`
- Ran `git ls-tree -r --name-only` on both `origin/main` and `99f7d1e` for `.github/workflows`
- Ran `gh api repos/MushroomDAO/demo-repository/actions/workflows`
- Ran `gh repo view MushroomDAO/demo-repository --json isPrivate,defaultBranchRef`
- Ran `curl -I` against both badge URLs to confirm the observed external `404`
- Ran `gh pr view 1 --repo MushroomDAO/demo-repository --json latestReviews,reviewDecision`
