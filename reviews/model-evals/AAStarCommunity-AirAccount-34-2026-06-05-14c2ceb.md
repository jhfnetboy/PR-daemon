# Local Model Review Evaluation: AAStarCommunity/AirAccount#34

- Date: 2026-06-05
- PR head: `14c2cebbd3e8d11eab33a55c8869c7bc1bde0977`
- Model: `qwen3.6-a3b`
- Local review: `reviews/AAStarCommunity-AirAccount-34-local-review-14c2ceb-2026-06-05.md`
- Final GitHub review: `REQUEST_CHANGES`
- Score: 3/10

## What Helped

The local model correctly saw that the previous `/opt/dk2-ta-dev-kit` ownership
issue and direct `/kms/CreateKey` curl were no longer present in the quickstart.

## What It Missed

The model missed that the replacement instruction points users to
`scripts/test-kms-api-simple.sh`, which is a QEMU Guest VM helper. That script
posts KMS operations to `http://localhost:3000/`, starts `./kms-api-server` from
the current directory, and does not match the DK2 deployment flow. The current
server routes are path-specific, such as `POST /CreateKey`, and the existing DK2
guide already points to `DK2_KMS_URL=http://192.168.7.2:3000
./kms/test/run-api-tests.sh`.

## Prior Improvement Assessment

Prior improvement item #11 said documentation PRs must validate copied commands,
endpoints, headers, paths, and sample responses against source, tests, or
existing docs. This was ineffective in this run: the model claimed the scripts
matched repository layout but did not inspect the referenced script closely
enough to catch the wrong API path and wrong runtime context.

## Prompt Improvement

For documentation PRs, every referenced script must be opened and checked at the
line level. It is not enough that the path exists. The model must verify that the
script is intended for the documented environment and that its commands match
current routes, headers, deployment paths, and prerequisite flow.

## Codex Adjudication

Codex rejected the local model's "no blockers" conclusion, verified the script
against the implemented KMS routes and DK2 deployment guide, and posted a fresh
`REQUEST_CHANGES` review on the new PR head.
