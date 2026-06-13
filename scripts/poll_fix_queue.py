#!/usr/bin/env python3
"""
poll_fix_queue.py — Discover jhfnetboy's PRs needing fixes.

Scans all 3 orgs for open PRs authored by jhfnetboy (or PR_DAEMON_MAIN_USER)
that have REQUEST_CHANGES or unresolved review comments. Fetches the full
review + comment text so the pr-fix skill can classify and queue them.

Usage:
  python3 scripts/poll_fix_queue.py                        # scan all 3 orgs
  python3 scripts/poll_fix_queue.py --repo OWNER/REPO      # single repo
  python3 scripts/poll_fix_queue.py --pr N --repo OWNER/REPO  # single PR
  python3 scripts/poll_fix_queue.py --output json          # JSON for piping

Output (text, default):
  Lists PRs with status, then per-PR prints review bodies + inline comments.
"""

import sys, os, json, subprocess, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
ORGS = ["AAStarCommunity", "AuraAIHQ", "MushroomDAO"]


# ──────────────────────────────────────────────────────────────
# Config helpers
# ──────────────────────────────────────────────────────────────

def load_env():
    env = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env

ENV = load_env()
MAIN_USER = ENV.get("PR_DAEMON_MAIN_USER", "jhfnetboy")

# Accounts whose comments are never fix candidates (CI bots, automation)
BOT_LOGINS = {
    "github-actions[bot]", "dependabot[bot]", "renovate[bot]",
    "codecov[bot]", "stale[bot]", "chatgpt-codex-connector[bot]",
    MAIN_USER,  # author's own comments are not fix requests
    # NOTE: "clestons" is the primary reviewer account — its comments ARE fix requests
}


# ──────────────────────────────────────────────────────────────
# gh CLI helpers
# ──────────────────────────────────────────────────────────────

def gh(*args, token=None):
    """Run gh CLI, return parsed JSON. Raises on non-zero exit."""
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    cmd = ["gh"] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:4])} failed: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}

def gh_api(path, token=None):
    return gh("api", path, token=token)

def gh_text(*args, token=None):
    """Run gh CLI, return raw stdout text."""
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    r = subprocess.run(["gh"] + list(args), capture_output=True, text=True, env=env)
    return r.stdout if r.returncode == 0 else ""


# ──────────────────────────────────────────────────────────────
# PR discovery
# ──────────────────────────────────────────────────────────────

def find_prs(repo=None, pr_number=None):
    """Return list of open PRs authored by MAIN_USER."""
    if pr_number and repo:
        data = gh_api(f"repos/{repo}/pulls/{pr_number}")
        if data.get("user", {}).get("login") != MAIN_USER:
            return []
        data["repository"] = {"nameWithOwner": repo}
        return [data]

    if repo:
        repos = [repo]
    else:
        repos = []
        for org in ORGS:
            try:
                page = gh_api(f"orgs/{org}/repos?type=all&per_page=100")
                repos += [r["full_name"] for r in page]
            except RuntimeError:
                pass

    prs = []
    for r in repos:
        try:
            page = gh_api(f"repos/{r}/pulls?state=open&per_page=100")
            for pr in page:
                if pr.get("user", {}).get("login") == MAIN_USER:
                    pr["_repo"] = r
                    prs.append(pr)
        except RuntimeError:
            pass

    return prs


# ──────────────────────────────────────────────────────────────
# Review + comment fetching
# ──────────────────────────────────────────────────────────────

def fetch_reviews(repo, pr_number):
    """Return list of reviews, newest first. Ignore DISMISSED."""
    try:
        reviews = gh_api(f"repos/{repo}/pulls/{pr_number}/reviews")
        return [r for r in reviews if r.get("state") != "DISMISSED"]
    except RuntimeError:
        return []

def fetch_inline_comments(repo, pr_number):
    """Return inline diff comments (review threads)."""
    try:
        return gh_api(f"repos/{repo}/pulls/{pr_number}/comments")
    except RuntimeError:
        return []

def fetch_issue_comments(repo, pr_number):
    """Return PR-level (non-review) comments."""
    try:
        return gh_api(f"repos/{repo}/issues/{pr_number}/comments")
    except RuntimeError:
        return []


# ──────────────────────────────────────────────────────────────
# Fix-need detection
# ──────────────────────────────────────────────────────────────

def latest_review_decision(reviews):
    """Return the most impactful recent review state."""
    # Priority: CHANGES_REQUESTED > APPROVED > COMMENTED
    states = {r["state"] for r in reviews}
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in states:
        return "APPROVED"
    if "COMMENTED" in states:
        return "COMMENTED"
    return "NONE"

def has_unresolved_inline(inline_comments):
    """
    Heuristic: inline comments that are not replies and not from MAIN_USER
    are likely unresolved reviewer notes.
    """
    roots = [c for c in inline_comments
             if not c.get("in_reply_to_id")
             and c.get("user", {}).get("login") != MAIN_USER]
    return len(roots) > 0

def classify_pr(pr, reviews, inline_comments, issue_comments):
    """
    Return (needs_fix: bool, status: str, fix_candidates: list[dict])

    fix_candidates: list of {source, author, file, line, body, created_at}
    """
    repo = pr.get("_repo") or pr.get("repository", {}).get("nameWithOwner", "")
    number = pr["number"]
    decision = latest_review_decision(reviews)

    candidates = []

    # Collect RC review bodies
    rc_reviews = [r for r in reviews if r["state"] == "CHANGES_REQUESTED"]
    for r in rc_reviews:
        body = (r.get("body") or "").strip()
        if body:
            candidates.append({
                "source": "review_body",
                "author": r["user"]["login"],
                "file": None,
                "line": None,
                "body": body,
                "created_at": r.get("submitted_at", ""),
                "review_id": r["id"],
            })

    # Collect inline comments from human reviewers only
    root_inline = [c for c in inline_comments
                   if not c.get("in_reply_to_id")
                   and c.get("user", {}).get("login") not in BOT_LOGINS]
    for c in root_inline:
        candidates.append({
            "source": "inline_comment",
            "author": c["user"]["login"],
            "file": c.get("path", ""),
            "line": c.get("line") or c.get("original_line"),
            "body": (c.get("body") or "").strip(),
            "created_at": c.get("created_at", ""),
            "comment_id": c["id"],
        })

    # Collect issue comments from human reviewers only (no bots)
    reviewer_issue_comments = [c for c in issue_comments
                                if c.get("user", {}).get("login") not in BOT_LOGINS]
    for c in reviewer_issue_comments:
        body = (c.get("body") or "").strip()
        if body and len(body) > 20:  # skip trivial pings
            candidates.append({
                "source": "pr_comment",
                "author": c["user"]["login"],
                "file": None,
                "line": None,
                "body": body,
                "created_at": c.get("created_at", ""),
                "comment_id": c["id"],
            })

    needs_fix = (decision == "CHANGES_REQUESTED") or (len(candidates) > 0)

    return needs_fix, decision, candidates


# ──────────────────────────────────────────────────────────────
# Main output
# ──────────────────────────────────────────────────────────────

def process_pr(pr, output_mode="text"):
    repo = pr.get("_repo") or pr.get("repository", {}).get("nameWithOwner", "")
    number = pr["number"]
    title = pr.get("title", "")
    branch = pr.get("head", {}).get("ref", "")
    head_oid = pr.get("head", {}).get("sha", "") or pr.get("headRefOid", "")

    reviews = fetch_reviews(repo, number)
    inline = fetch_inline_comments(repo, number)
    issue_comments = fetch_issue_comments(repo, number)

    needs_fix, decision, candidates = classify_pr(pr, reviews, inline, issue_comments)

    result = {
        "repo": repo,
        "pr": number,
        "title": title,
        "branch": branch,
        "head_oid": head_oid[:12] if head_oid else "",
        "review_decision": decision,
        "needs_fix": needs_fix,
        "fix_candidates": candidates,
        "candidate_count": len(candidates),
    }

    if output_mode == "json":
        return result

    # Text output
    icon = "🔴" if decision == "CHANGES_REQUESTED" else "🟡" if candidates else "✅"
    print(f"\n{icon} {repo}#{number}  [{decision}]  {title[:60]}")
    print(f"   branch: {branch}  head: {head_oid[:10]}")

    if not needs_fix:
        print("   → no fix needed")
        return result

    print(f"   → {len(candidates)} comment(s) to address:")
    for i, c in enumerate(candidates, 1):
        src = c["source"]
        author = c["author"]
        file_info = f" @ {c['file']}:{c['line']}" if c.get("file") else ""
        body_preview = c["body"][:120].replace("\n", " ")
        print(f"   [{i}] {src}{file_info} by {author}:")
        print(f"       {body_preview}")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Find jhfnetboy PRs needing fixes")
    parser.add_argument("--repo", help="OWNER/REPO to scan (default: all 3 orgs)")
    parser.add_argument("--pr", type=int, help="Specific PR number (requires --repo)")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument("--needs-fix-only", action="store_true",
                        help="Only output PRs that actually need fixes")
    args = parser.parse_args()

    print(f"Scanning for {MAIN_USER}'s PRs needing fixes...", file=sys.stderr)

    prs = find_prs(repo=args.repo, pr_number=args.pr)
    print(f"Found {len(prs)} open PR(s) by {MAIN_USER}", file=sys.stderr)

    results = []
    for pr in prs:
        r = process_pr(pr, output_mode=args.output)
        if args.needs_fix_only and not r["needs_fix"]:
            continue
        results.append(r)

    if args.output == "json":
        print(json.dumps(results, indent=2))
    else:
        fix_count = sum(1 for r in results if r["needs_fix"])
        print(f"\n── Summary: {fix_count}/{len(results)} PR(s) need fixes ──")
        if fix_count:
            print(f"\nNext step: $pr-fix  (or: python3 scripts/poll_fix_queue.py --output json)")


if __name__ == "__main__":
    main()
