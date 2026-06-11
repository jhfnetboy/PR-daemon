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


GRAPHQL_QUERY = """
query($q: String!, $cursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number title url updatedAt isDraft headRefOid
        author { login }
        repository { nameWithOwner }
      }
    }
  }
}
"""


def gh_search_org_prs():
    """ALL open PRs across the 3 orgs — any author, incl bots — via ONE GraphQL call.

    Returns dicts shaped like gh search, PLUS headRefOid (so sync needs no per-PR
    head fetch). Paginates if >100. Goal: clear every PR, so no author filter.
    """
    q = " ".join(f"org:{o}" for o in ORGS) + " is:pr is:open"
    results = []
    cursor = None
    for _page in range(10):  # up to 1000 PRs
        cmd = ["gh", "api", "graphql", "-f", f"query={GRAPHQL_QUERY}", "-f", f"q={q}"]
        if cursor:
            cmd += ["-f", f"cursor={cursor}"]
        got = None
        for _ in range(3):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                if out.returncode == 0:
                    txt = out.stdout
                    s = txt.find("{")
                    got = json.loads(txt[s:txt.rfind("}") + 1])
                    break
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                pass
        if not got:
            break
        search = got.get("data", {}).get("search", {})
        for n in search.get("nodes", []):
            if not n:
                continue
            results.append({
                "number": n["number"], "title": n["title"], "url": n["url"],
                "updatedAt": n["updatedAt"], "isDraft": n["isDraft"],
                "headRefOid": n.get("headRefOid"),
                "author": n.get("author") or {},
                "repository": {"nameWithOwner": n["repository"]["nameWithOwner"]},
            })
        pi = search.get("pageInfo", {})
        if pi.get("hasNextPage"):
            cursor = pi.get("endCursor")
        else:
            break
    return results


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


def gh_list_repo_prs(repo, include_all_authors=False):
    """List open PRs in one specific repo. Returns list of dicts shaped like gh search."""
    cmd = ["gh", "pr", "list", "--repo", repo, "--state", "open",
           "--json", "number,title,url,updatedAt,isDraft,author", "--limit", "100"]
    for _ in range(3):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                txt = out.stdout
                start, end = txt.find("["), txt.rfind("]")
                if start >= 0 and end > start:
                    raw = json.loads(txt[start:end + 1])
                    # reshape to match gh search prs structure
                    return [{
                        "number": p["number"], "title": p["title"], "url": p["url"],
                        "updatedAt": p["updatedAt"], "isDraft": p["isDraft"],
                        "author": p.get("author", {}),
                        "repository": {"nameWithOwner": repo},
                    } for p in raw]
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
    return []


def sync_to_sqlite(prs):
    """Upsert every open PR into pr_watch_targets — the live mirror of all open PRs.

    Stores author + reviewer + status. Marks PRs no longer open as 'closed'.
    - new PR                       → status='needs_review'
    - already reviewed, head same  → keep status (approved/changes_requested)
    - already reviewed, head moved  → status='needs_review' (re-review)
    Returns (inserted, updated, closed) counts.
    """
    review_user = os.environ.get("PR_DAEMON_REVIEW_USER", "clestons")
    conn = sqlite3.connect(STATE_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS pr_watch_targets ("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT, pr_number INTEGER, title TEXT, "
                 "url TEXT, author TEXT, head_oid TEXT, state TEXT, review_decision TEXT, "
                 "is_draft INTEGER DEFAULT 0, first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP, "
                 "last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP, last_reviewed_head_oid TEXT, "
                 "last_reviewed_at TEXT, status TEXT DEFAULT 'seen', reviewer TEXT, "
                 "UNIQUE(repo, pr_number))")
    # ensure reviewer column exists (older DBs)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pr_watch_targets)").fetchall()]
    if "reviewer" not in cols:
        conn.execute("ALTER TABLE pr_watch_targets ADD COLUMN reviewer TEXT")

    seen_keys = set()
    inserted = updated = 0
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        num = pr["number"]
        author = (pr.get("author") or {}).get("login", "?")
        seen_keys.add((repo, num))
        row = conn.execute(
            "SELECT status, last_reviewed_head_oid, last_reviewed_at FROM pr_watch_targets "
            "WHERE repo=? AND pr_number=?", (repo, num)).fetchone()
        is_draft = 1 if pr.get("isDraft") else 0
        cur_head = pr.get("headRefOid")  # from GraphQL — no extra gh call needed
        if row is None:
            conn.execute(
                "INSERT INTO pr_watch_targets (repo, pr_number, title, url, author, head_oid, "
                "state, is_draft, status, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (repo, num, pr["title"], pr["url"], author, cur_head, "open", is_draft, "needs_review"))
            inserted += 1
        else:
            status, last_head, last_reviewed_at = row
            new_status = status
            if status in ("approved", "changes_requested", "comment"):
                if cur_head and cur_head != last_head:
                    new_status = "needs_review"   # head moved → re-review
            elif status == "closed":
                new_status = "needs_review"       # reopened
            conn.execute(
                "UPDATE pr_watch_targets SET title=?, url=?, author=?, head_oid=?, is_draft=?, "
                "state='open', status=?, last_seen_at=CURRENT_TIMESTAMP WHERE repo=? AND pr_number=?",
                (pr["title"], pr["url"], author, cur_head, is_draft, new_status, repo, num))
            updated += 1

    # mark PRs that are tracked but no longer open as closed
    closed = 0
    for r in conn.execute("SELECT repo, pr_number FROM pr_watch_targets WHERE state='open' OR state IS NULL").fetchall():
        if (r[0], r[1]) not in seen_keys:
            conn.execute("UPDATE pr_watch_targets SET state='closed', status='closed' WHERE repo=? AND pr_number=?", r)
            closed += 1
    conn.commit()
    conn.close()
    return inserted, updated, closed


def build_queue(prs, max_prs, since_secs):
    """From open PRs, build the review queue (new / head-changed only)."""
    in_scope = [pr for pr in prs if not pr.get("isDraft")]
    if since_secs is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_secs)
        in_scope = [pr for pr in in_scope
                    if datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00")) >= cutoff]
    queue = []
    for pr in in_scope:
        repo = pr["repository"]["nameWithOwner"]
        num = pr["number"]
        row = get_reviewed_head(repo, num)
        reason = "new"
        if row:
            last_head, status = row
            if status in ("approved", "changes_requested", "comment"):
                cur = pr.get("headRefOid")  # inline from GraphQL — no extra gh call
                if cur and cur == last_head:
                    continue
                reason = "head-changed"
        queue.append({
            "repo": repo, "pr_number": num, "title": pr["title"], "url": pr["url"],
            "author": (pr.get("author") or {}).get("login", "?"),
            "updated_at": pr["updatedAt"], "reason": reason,
        })
    return queue[:max_prs]


def main():
    args = sys.argv[1:]
    max_prs = 200
    since_secs = None
    target_repo = None
    do_sync = "--sync" in args
    if "--max" in args:
        max_prs = int(args[args.index("--max") + 1])
    if "--since" in args:
        since_secs = int(args[args.index("--since") + 1])
    if "--repo" in args:
        target_repo = args[args.index("--repo") + 1]

    # Fetch: single repo (all authors) OR all 3 orgs (all authors, incl bots)
    if target_repo:
        prs = gh_list_repo_prs(target_repo)
    else:
        prs = gh_search_org_prs()

    result = {"total_open": len(prs)}

    if do_sync:
        ins, upd, clo = sync_to_sqlite(prs)
        result["sync"] = {"inserted": ins, "updated": upd, "closed": clo}

    queue = build_queue(prs, max_prs, since_secs)
    result["count"] = len(queue)
    result["queue"] = queue
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
