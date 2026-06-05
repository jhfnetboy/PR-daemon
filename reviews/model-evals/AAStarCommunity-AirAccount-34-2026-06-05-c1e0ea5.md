# Local Model Review Evaluation: AAStarCommunity/AirAccount#34

- Date: 2026-06-05
- PR head: `c1e0ea57c59baf20dae992f57ffbf8e677cde62a`
- Model: `qwen3.6-a3b`
- Local review: `reviews/AAStarCommunity-AirAccount-34-local-review-c1e0ea5-2026-06-05.md`
- Final GitHub review: `REQUEST_CHANGES`
- Score: 6/10

## What Helped

The local model found a deterministic quickstart blocker: the guide creates
`/opt/dk2-ta-dev-kit` with `sudo mkdir`, then runs `scp` as the normal macOS
user into that root-owned directory. This became one of the posted request
changes.

## What It Missed

The model did not verify the documented CreateKey command against the actual
KMS server route and tests. The guide used `/kms/CreateKey` without the required
`x-amz-target: TrentService.CreateKey` header, while the current implementation
exposes `POST /CreateKey` and requires that exact header.

## False Positives / Calibration

The HTTP warning and MX93/MX95 wording were reasonable hardening/cleanup notes,
but not blocking. They should remain lower priority than commands that fail when
copied exactly from the guide.

## Prompt Improvement

For documentation PRs, require the local model to validate every copied shell
command, endpoint, path, header, and sample response against repository source,
tests, or existing docs before deciding severity.

## Codex Adjudication

Useful as a first-pass batch reviewer, but not sufficient for final PR review.
Codex verification added the missing API-route blocker and turned the result into
a precise `REQUEST_CHANGES` review.
