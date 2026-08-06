#!/usr/bin/env python3
"""
fetch_prior_review.py — pull the last review WE posted on a PR, for incremental re-review.

## Why this exists

On an incremental re-review (the PR moved on since we last looked), the blocking findings are
almost always **漏改点** — the previous round's finding was fixed in one place and missed in
another. By definition the missed place is NOT in the new diff, so a reviewer that only sees the
diff cannot find it. Measured 2026-08-06 on CoLivingOS#74 and #75: DeepSeek R1 scored 0/4 and 0/1
on two consecutive incremental rounds, and both rounds' real blocking findings were residue of the
PREVIOUS round's findings. Neither was reachable from the diff alone.

So: feed the previous review back in, and ask R1 to check each of its findings for a complete fix.

Usage:
  python3 scripts/fetch_prior_review.py --repo OWNER/REPO --pr N [--output FILE] [--user clestons]

Exit codes:
  0  a prior review was found and written
  3  no prior review by that user (first-time review — caller should skip --prior-review)
  1  hard failure (gh unavailable / API error)
"""

# The system python3 here is 3.9, where `tuple[...] | None` in a signature is evaluated at
# def-time and raises TypeError. Deferring annotation evaluation keeps the modern syntax readable
# without pinning a newer interpreter.
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# We want the most recent SUBMITTED, SUBSTANTIVE review. A bare APPROVE with an empty body
# carries no findings to re-check, and picking it would silently produce an empty prior-review
# block that reads as "nothing was raised last time". Ordering is taken from `submittedAt`, never
# from the array order — see the sort in fetch().
MIN_BODY_CHARS = 40

# States that are not "a review we posted": PENDING is an unsubmitted draft, DISMISSED was
# explicitly retracted.
SKIP_STATES = {"PENDING", "DISMISSED"}


def fetch(repo: str, pr: int, user: str) -> tuple[str, str, str] | None:
    try:
        out = subprocess.run(
            ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "reviews"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        sys.stderr.write(f"❌ gh failed: {e}\n")
        sys.exit(1)
    if out.returncode != 0:
        sys.stderr.write(f"❌ gh pr view failed: {out.stderr.strip()[:300]}\n")
        sys.exit(1)

    try:
        reviews = json.loads(out.stdout).get("reviews", [])
    except json.JSONDecodeError as e:
        sys.stderr.write(f"❌ could not parse gh output: {e}\n")
        sys.exit(1)

    mine = [
        r for r in reviews
        if (r.get("author") or {}).get("login", "").lower() == user.lower()
        and len(r.get("body") or "") >= MIN_BODY_CHARS
        # A PENDING review is an UNSUBMITTED draft — `gh` returns the viewer's own drafts, and
        # feeding scratch notes to R1 as "the review WE posted last round" is worse than feeding
        # nothing. DISMISSED reviews were explicitly retracted, so they are not "what we said"
        # either. Both were reproduced beating the real review before this filter existed.
        and (r.get("state") or "").upper() not in SKIP_STATES
        and r.get("submittedAt")
    ]
    if not mine:
        return None
    # Sort by submittedAt rather than trusting array order. GraphQL orders reviews by database id
    # (creation), not submission, so a review drafted earlier but submitted later sorts wrong —
    # and the failure is SILENT: you get an older round's body labelled as the prior round, which
    # is precisely the one thing this script must never get wrong.
    mine.sort(key=lambda r: r.get("submittedAt") or "")
    last = mine[-1]
    return last.get("body", ""), last.get("state", "?"), last.get("submittedAt", "?")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="OWNER/REPO")
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--user", default="clestons", help="review account whose review to fetch")
    ap.add_argument("--output", help="write here instead of stdout")
    args = ap.parse_args()

    got = fetch(args.repo, args.pr, args.user)
    if got is None:
        # Remove a stale --output from an earlier PR. Callers reuse fixed paths like
        # /tmp/prior.md; leaving the previous PR's review there would let R1 silently ingest
        # a DIFFERENT PR's findings as this PR's prior round.
        if args.output:
            Path(args.output).unlink(missing_ok=True)
        sys.stderr.write(
            f"[prior-review] no prior review by {args.user} on {args.repo}#{args.pr} — "
            f"this is a first-time review, run R1 without --prior-review\n"
        )
        sys.exit(3)

    body, state, when = got
    text = (
        f"PRIOR REVIEW by {args.user} on {args.repo}#{args.pr}\n"
        f"verdict: {state}   submitted: {when}\n"
        f"{'-' * 70}\n{body}\n"
    )
    if args.output:
        Path(args.output).write_text(text)
        sys.stderr.write(
            f"[prior-review] {args.repo}#{args.pr}: {state} @ {when}, "
            f"{len(body)} chars -> {args.output}\n"
        )
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
