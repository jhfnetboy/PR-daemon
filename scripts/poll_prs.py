#!/usr/bin/env python3
"""
poll_prs.py — incremental PR discovery for the review loop.

Borrows robustness patterns from pr-agent's servers/github_polling.py:
  - `since` timestamp → only surface PRs changed since last poll (incremental)
  - dedup via last_reviewed_head_oid → never re-review the same head twice
  - parallel cap → bound how many PRs the loop takes per cycle
  - retry-safe → a transient gh failure doesn't crash the loop

Unlike pr-agent (event-driven via Notifications API), this is proactive-scan:
it lists open PRs by author across the configured orgs and emits the ones that
are new or head-changed since last review.

Usage:
  python3 scripts/poll_prs.py                 # emit queue as JSON
  python3 scripts/poll_prs.py --max 5         # cap to 5 PRs this cycle
  python3 scripts/poll_prs.py --since 3600    # only PRs updated in last hour
"""

import sys, os, json, subprocess, sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
STATE_DB = ROOT / ".state" / "pr-daemon" / "pr-watch.sqlite"

# 3 orgs only (per DESIGN.md). Never review personal jhfnetboy PRs.
ORGS = ["AAStarCommunity", "AuraAIHQ", "MushroomDAO"]


def load_main_user():
    """Read PR_DAEMON_MAIN_USER from env or .env."""
    u = os.environ.get("PR_DAEMON_MAIN_USER", "")
    if u:
        return u
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("PR_DAEMON_MAIN_USER="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "jhfnetboy"


def gh_search_prs(author, since_iso=None):
    """List open PRs by author. Returns list of dicts. Retry-safe."""
    cmd = [
        "gh", "search", "prs",
        "--author", author,
        "--state", "open",
        "--json", "number,title,repository,url,updatedAt,isDraft",
        "--limit", "100",
    ]
    for attempt in range(3):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                # gh prints non-JSON request log lines to stdout sometimes; find the array
                txt = out.stdout
                start = txt.find("[")
                end = txt.rfind("]")
                if start >= 0 and end > start:
                    return json.loads(txt[start:end + 1])
            # else retry
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
    return []


def get_reviewed_head(repo, pr_number):
    """Return last_reviewed_head_oid for a PR, or None."""
    if not STATE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(STATE_DB)
        row = conn.execute(
            "SELECT last_reviewed_head_oid, status FROM pr_watch_targets WHERE repo=? AND pr_number=?",
            (repo, pr_number),
        ).fetchone()
        conn.close()
        return row
    except sqlite3.Error:
        return None


def get_current_head(repo, pr_number):
    """Fetch current head OID via gh."""
    try:
        out = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "headRefOid"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            txt = out.stdout
            start = txt.find("{")
            end = txt.rfind("}")
            if start >= 0:
                return json.loads(txt[start:end + 1]).get("headRefOid")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def main():
    args = sys.argv[1:]
    max_prs = 100
    since_secs = None
    if "--max" in args:
        max_prs = int(args[args.index("--max") + 1])
    if "--since" in args:
        since_secs = int(args[args.index("--since") + 1])

    author = load_main_user()
    prs = gh_search_prs(author)

    # filter to the 3 orgs, skip drafts
    in_scope = []
    for pr in prs:
        owner = pr["repository"]["nameWithOwner"].split("/")[0]
        if owner not in ORGS:
            continue
        if pr.get("isDraft"):
            continue
        in_scope.append(pr)

    # incremental: filter by updatedAt if --since given
    if since_secs is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_secs)
        in_scope = [
            pr for pr in in_scope
            if datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00")) >= cutoff
        ]

    # dedup: only emit new or head-changed PRs
    queue = []
    for pr in in_scope:
        repo = pr["repository"]["nameWithOwner"]
        num = pr["number"]
        row = get_reviewed_head(repo, num)
        reason = "new"
        if row:
            last_head, status = row
            if status in ("approved", "changes_requested", "comment"):
                # already reviewed — check if head changed
                cur = get_current_head(repo, num)
                if cur and cur == last_head:
                    continue  # same head, skip
                reason = "head-changed"
        queue.append({
            "repo": repo,
            "pr_number": num,
            "title": pr["title"],
            "url": pr["url"],
            "updated_at": pr["updatedAt"],
            "reason": reason,
        })

    # cap parallel intake
    queue = queue[:max_prs]
    print(json.dumps({"count": len(queue), "queue": queue}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
