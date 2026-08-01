#!/usr/bin/env python3
"""Discovery for the auto-review loop: open PRs across the 3 orgs (author jhfnetboy)
that clestons hasn't APPROVED/reviewed at the CURRENT head. Outputs the review queue.

A PR is "needs review" if no clestons review exists whose commit == the PR head
(i.e. new PR, or head moved since clestons last reviewed). Drafts are skipped.
`pr-fix` label is surfaced so the loop knows merge is authorized.
"""
import json, subprocess, sys

# AuraAIHQ was renamed to iDoris-ai (old name now 404s -> "Invalid search query").
ORGS = ["AAStarCommunity", "iDoris-ai", "MushroomDAO"]
REVIEWER = "clestons"

def gh(args):
    r = subprocess.run(["gh"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return r.stdout.strip()

def search_open():
    out = gh(["search", "prs", "--author", "jhfnetboy", "--state", "open",
              "--json", "number,title,repository,isDraft,url", "--limit", "100"])
    try:
        prs = json.loads(out) if out else []
    except Exception:
        return []
    res = []
    for p in prs:
        repo = p["repository"]["nameWithOwner"] if isinstance(p["repository"], dict) and "nameWithOwner" in p["repository"] else None
        if not repo:
            r = p["repository"]; repo = (r.get("owner",{}).get("login","") + "/" + r.get("name","")) if isinstance(r,dict) else str(r)
        if repo.split("/")[0] not in ORGS:  # 3-orgs only, never personal
            continue
        if p.get("isDraft"):
            continue
        res.append({"repo": repo, "number": p["number"], "title": p["title"], "url": p["url"]})
    return res

def needs_review(repo, num):
    """True if clestons has NO review at the current head."""
    head = gh(["pr", "view", str(num), "--repo", repo, "--json", "headRefOid", "-q", ".headRefOid"])
    revs = gh(["api", f"repos/{repo}/pulls/{num}/reviews", "-q",
               f'[.[] | select(.user.login=="{REVIEWER}") | .commit_id] | @json'])
    try:
        reviewed_commits = json.loads(revs) if revs else []
    except Exception:
        reviewed_commits = []
    return head not in reviewed_commits, head

def has_prfix_label(repo, num):
    labels = gh(["pr", "view", str(num), "--repo", repo, "--json", "labels", "-q",
                 "[.labels[].name] | @json"])
    try:
        names = [n.lower() for n in (json.loads(labels) if labels else [])]
    except Exception:
        names = []
    return any(n in ("pr-fix", "auto-merge", "merge-ok") for n in names)

def main():
    queue = []
    for pr in search_open():
        nr, head = needs_review(pr["repo"], pr["number"])
        if nr:
            pr["head"] = head[:8]
            pr["prfix"] = has_prfix_label(pr["repo"], pr["number"])
            queue.append(pr)
    if "--json" in sys.argv:
        print(json.dumps(queue))
    else:
        if not queue:
            print("queue empty — all open PRs reviewed at head ✓")
        for q in queue:
            print(f"  {q['repo']}#{q['number']} head={q['head']} {'[pr-fix]' if q['prfix'] else ''} {q['title'][:50]}")
    print(f"\n待审: {len(queue)}", file=sys.stderr)

if __name__ == "__main__":
    main()
