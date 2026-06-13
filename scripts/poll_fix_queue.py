#!/usr/bin/env python3
"""
poll_fix_queue.py — Discover PRs needing attention for $pr-fix.

Scans two categories across all 3 orgs:
  1. jhfnetboy's own PRs with REQUEST_CHANGES or unresolved human review comments
  2. Bot PRs (dependabot / renovate) that are unreviewed or have RC findings

Usage:
  python3 scripts/poll_fix_queue.py                         # scan all 3 orgs, both categories
  python3 scripts/poll_fix_queue.py --repo OWNER/REPO       # single repo
  python3 scripts/poll_fix_queue.py --pr N --repo OWNER/REPO  # single PR
  python3 scripts/poll_fix_queue.py --human-only            # jhfnetboy PRs only
  python3 scripts/poll_fix_queue.py --bot-only              # bot PRs only
  python3 scripts/poll_fix_queue.py --needs-fix-only        # skip clean PRs
  python3 scripts/poll_fix_queue.py --output json           # JSON for piping

Output icons:
  🔴  CHANGES_REQUESTED (human PR)   — fix code, loop until APPROVE
  🟡  APPROVE + comments (human PR)  — address suggestions
  🤖  Bot PR needing review/action   — review + merge if clean, report if RC
  ✅  Clean, no action needed
"""

import sys, os, json, subprocess
from pathlib import Path

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

# Bot PR authors — PRs opened by these are handled with review+merge flow
BOT_PR_AUTHORS = {
    "dependabot[bot]", "app/dependabot",
    "renovate[bot]", "renovate",
}

# Review comment authors to ignore (CI automation, not real fix requests)
BOT_COMMENT_AUTHORS = {
    "github-actions[bot]", "dependabot[bot]", "renovate[bot]",
    "codecov[bot]", "stale[bot]", "chatgpt-codex-connector[bot]",
    MAIN_USER,  # author's own comments are not fix requests
    # NOTE: "clestons" is kept — its comments ARE fix requests
}


# ──────────────────────────────────────────────────────────────
# gh CLI helpers
# ──────────────────────────────────────────────────────────────

def gh(*args, token=None):
    """Run gh CLI, return parsed JSON. Raises on non-zero exit."""
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    r = subprocess.run(["gh"] + list(args), capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:4])} failed: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}

def gh_api(path, token=None):
    return gh("api", path, token=token)


# ──────────────────────────────────────────────────────────────
# PR discovery
# ──────────────────────────────────────────────────────────────

def _list_repos(repo_filter=None):
    if repo_filter:
        return [repo_filter]
    repos = []
    for org in ORGS:
        try:
            page = gh_api(f"orgs/{org}/repos?type=all&per_page=100")
            repos += [r["full_name"] for r in page]
        except RuntimeError:
            pass
    return repos

def find_prs(repo=None, pr_number=None, include_human=True, include_bots=True):
    """Return list of open PRs for the requested categories."""
    if pr_number and repo:
        data = gh_api(f"repos/{repo}/pulls/{pr_number}")
        author = data.get("user", {}).get("login", "")
        is_bot = author in BOT_PR_AUTHORS
        is_human = (author == MAIN_USER)
        if (is_bot and include_bots) or (is_human and include_human):
            data["_repo"] = repo
            data["_is_bot_pr"] = is_bot
            return [data]
        return []

    repos = _list_repos(repo)
    prs = []
    for r in repos:
        try:
            page = gh_api(f"repos/{r}/pulls?state=open&per_page=100")
            for pr in page:
                author = pr.get("user", {}).get("login", "")
                is_bot = author in BOT_PR_AUTHORS
                is_human = (author == MAIN_USER)
                if (is_bot and include_bots) or (is_human and include_human):
                    pr["_repo"] = r
                    pr["_is_bot_pr"] = is_bot
                    prs.append(pr)
        except RuntimeError:
            pass
    return prs


# ──────────────────────────────────────────────────────────────
# Review + comment fetching
# ──────────────────────────────────────────────────────────────

def fetch_reviews(repo, pr_number):
    try:
        reviews = gh_api(f"repos/{repo}/pulls/{pr_number}/reviews")
        return [r for r in reviews if r.get("state") != "DISMISSED"]
    except RuntimeError:
        return []

def fetch_inline_comments(repo, pr_number):
    try:
        return gh_api(f"repos/{repo}/pulls/{pr_number}/comments")
    except RuntimeError:
        return []

def fetch_issue_comments(repo, pr_number):
    try:
        return gh_api(f"repos/{repo}/issues/{pr_number}/comments")
    except RuntimeError:
        return []


# ──────────────────────────────────────────────────────────────
# Classification
# ──────────────────────────────────────────────────────────────

def latest_review_decision(reviews):
    states = {r["state"] for r in reviews}
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in states:
        return "APPROVED"
    if "COMMENTED" in states:
        return "COMMENTED"
    return "NONE"

def classify_pr(pr, reviews, inline_comments, issue_comments):
    """
    Return (needs_action: bool, decision: str, candidates: list[dict])

    For bot PRs: needs_action=True when unreviewed (NONE) or has RC.
    For human PRs: needs_action=True when RC or has human reviewer comments.
    """
    is_bot_pr = pr.get("_is_bot_pr", False)
    decision = latest_review_decision(reviews)
    candidates = []

    # RC review bodies (both human and bot PRs)
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

    # Inline comments from human reviewers only
    for c in inline_comments:
        if c.get("in_reply_to_id"):
            continue
        if c.get("user", {}).get("login") in BOT_COMMENT_AUTHORS:
            continue
        candidates.append({
            "source": "inline_comment",
            "author": c["user"]["login"],
            "file": c.get("path", ""),
            "line": c.get("line") or c.get("original_line"),
            "body": (c.get("body") or "").strip(),
            "created_at": c.get("created_at", ""),
            "comment_id": c["id"],
        })

    # PR-level comments from human reviewers only
    for c in issue_comments:
        if c.get("user", {}).get("login") in BOT_COMMENT_AUTHORS:
            continue
        body = (c.get("body") or "").strip()
        if body and len(body) > 20:
            candidates.append({
                "source": "pr_comment",
                "author": c["user"]["login"],
                "file": None,
                "line": None,
                "body": body,
                "created_at": c.get("created_at", ""),
                "comment_id": c["id"],
            })

    if is_bot_pr:
        # Bot PRs need action when: never reviewed (NONE) or RC found
        needs_action = decision in ("NONE", "CHANGES_REQUESTED")
    else:
        # Human PRs need action when: RC or unresolved human reviewer comments
        needs_action = (decision == "CHANGES_REQUESTED") or (len(candidates) > 0)

    return needs_action, decision, candidates


# ──────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────

def process_pr(pr, output_mode="text"):
    repo = pr.get("_repo") or pr.get("repository", {}).get("nameWithOwner", "")
    number = pr["number"]
    title = pr.get("title", "")
    branch = pr.get("head", {}).get("ref", "")
    head_oid = pr.get("head", {}).get("sha", "")
    is_bot_pr = pr.get("_is_bot_pr", False)
    author = pr.get("user", {}).get("login", "")

    reviews = fetch_reviews(repo, number)
    inline = fetch_inline_comments(repo, number)
    issue_comments = fetch_issue_comments(repo, number)

    needs_action, decision, candidates = classify_pr(pr, reviews, inline, issue_comments)

    result = {
        "repo": repo,
        "pr": number,
        "title": title,
        "branch": branch,
        "head_oid": head_oid[:12] if head_oid else "",
        "author": author,
        "is_bot_pr": is_bot_pr,
        "review_decision": decision,
        "needs_action": needs_action,
        "fix_candidates": candidates,
        "candidate_count": len(candidates),
        # convenience: what $pr-fix should do
        "action": "review+merge" if is_bot_pr else "fix+review",
    }

    if output_mode == "json":
        return result

    # Text output
    if is_bot_pr:
        icon = "🤖" if needs_action else "✅"
        kind = f"[bot:{author}]"
    else:
        icon = "🔴" if decision == "CHANGES_REQUESTED" else "🟡" if candidates else "✅"
        kind = f"[{decision}]"

    print(f"\n{icon} {repo}#{number}  {kind}  {title[:55]}")
    print(f"   branch: {branch}  head: {head_oid[:10]}  author: {author}")

    if not needs_action:
        if is_bot_pr:
            print(f"   → already reviewed ({decision}), no action needed")
        else:
            print("   → no fix needed")
        return result

    if is_bot_pr:
        if decision == "NONE":
            print("   → 🤖 unreviewed bot PR — needs inline review then merge")
        elif decision == "CHANGES_REQUESTED":
            print(f"   → 🤖 bot PR has RC ({len(candidates)} finding(s)) — report to user, cannot auto-fix")
            for i, c in enumerate(candidates, 1):
                print(f"   [{i}] {c['source']} by {c['author']}: {c['body'][:100].replace(chr(10), ' ')}")
    else:
        print(f"   → {len(candidates)} comment(s) to address:")
        for i, c in enumerate(candidates, 1):
            file_info = f" @ {c['file']}:{c['line']}" if c.get("file") else ""
            body_preview = c["body"][:120].replace("\n", " ")
            print(f"   [{i}] {c['source']}{file_info} by {c['author']}:")
            print(f"       {body_preview}")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Find PRs needing fixes ($pr-fix queue)")
    parser.add_argument("--repo", help="OWNER/REPO to scan (default: all 3 orgs)")
    parser.add_argument("--pr", type=int, help="Specific PR number (requires --repo)")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument("--needs-fix-only", action="store_true",
                        help="Only output PRs that actually need action")
    parser.add_argument("--human-only", action="store_true",
                        help="Only scan jhfnetboy's own PRs")
    parser.add_argument("--bot-only", action="store_true",
                        help="Only scan bot PRs (dependabot/renovate)")
    args = parser.parse_args()

    include_human = not args.bot_only
    include_bots = not args.human_only

    print(f"Scanning PRs (human={include_human}, bots={include_bots})...", file=sys.stderr)

    prs = find_prs(repo=args.repo, pr_number=args.pr,
                   include_human=include_human, include_bots=include_bots)
    print(f"Found {len(prs)} open PR(s)", file=sys.stderr)

    results = []
    for pr in prs:
        r = process_pr(pr, output_mode=args.output)
        if args.needs_fix_only and not r["needs_action"]:
            continue
        results.append(r)

    if args.output == "json":
        print(json.dumps(results, indent=2))
    else:
        human_fix = sum(1 for r in results if not r["is_bot_pr"] and r["needs_action"])
        bot_action = sum(1 for r in results if r["is_bot_pr"] and r["needs_action"])
        total = len(results)
        print(f"\n── Summary: {human_fix} human PR(s) need fixes | {bot_action} bot PR(s) need action | {total} total ──")
        if human_fix or bot_action:
            print(f"\nNext step: $pr-fix  (or: python3 scripts/poll_fix_queue.py --output json)")


if __name__ == "__main__":
    main()
