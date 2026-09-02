#!/usr/bin/env python3
"""One command, one compact answer: what is there to review right now?

Replaces the per-repo `gh pr list` fan-out the loop ticks used to do (8 calls per
tick). `poll_prs.py --sync` already mirrors every open PR in scope into SQLite, so
one subprocess plus one query is enough — and the scope comes from the same single
source (`scan_scope.py`) that everything else reads.

## The pending criterion is TWO conditions, not one

    head_oid != last_reviewed_head_oid          -> new PR, or the author pushed a fix
    OR last_reviewed_at IS NULL/''              -> a head was recorded without a review

The second one is not theoretical: on 2026-09-02 the table had 85 rows with a
recorded head and no `last_reviewed_at`. Only checking the head silently reports
"nothing to do" for a PR nobody ever reviewed. Every one of those 85 turned out to
be closed/draft/actually-reviewed, so nothing was missed — but the path is real and
it fails in the direction that produces silence.

## Drafts

`is_draft` PRs are listed separately and are NOT work: the author marked them as not
ready. They are printed so the skip is auditable, never silently dropped. Do not
write `last_reviewed_at` for them — that would claim a review happened.

## Control line

`open=` is printed even when nothing is pending. A scan that finds 0 pending and a
scan whose `gh` call failed produce the same empty list otherwise, and the second
one must not read as "all clear".
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(
    os.environ.get("PR_DAEMON_STATE_DIR", os.path.join(ROOT, ".state/pr-daemon")),
    "pr-watch.sqlite",
)


def sync(max_prs: int) -> bool:
    """Mirror every open PR in scope into SQLite. Returns False if the fetch failed."""
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "poll_prs.py"), "--sync", "--max", str(max_prs)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    # poll_prs prints JSON; we only need to know whether the remote fetch worked.
    # A failed fetch leaves SQLite holding yesterday's picture, which would read as
    # "nothing new" — exactly the silence this script exists to avoid.
    return '"fetch_failed": false' in r.stdout


def pending(con: sqlite3.Connection):
    rows = con.execute(
        """
        SELECT repo, pr_number, head_oid, COALESCE(last_reviewed_head_oid,''),
               COALESCE(last_reviewed_at,''), COALESCE(title,''), is_draft
        FROM pr_watch_targets
        -- `state` is stored lower-case ('open'); two legacy rows hold 'MERGED'.
        -- Writing 'OPEN' here matched zero rows and the scan reported "nothing to
        -- review" — caught only because the `open=` control line printed 0.
        WHERE lower(COALESCE(state,'')) = 'open'
        ORDER BY repo, pr_number
        """
    ).fetchall()
    work, drafts, done = [], [], 0
    for repo, n, head, rev, at, title, draft in rows:
        if head and head == rev and at:
            done += 1
            continue
        why = "head 不同" if head != rev else "head 相同但 last_reviewed_at 空"
        (drafts if draft else work).append((repo, n, head, rev, why, title))
    return rows, work, drafts, done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sync", action="store_true", help="只查 SQLite,不去 GitHub 拉")
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="只把匹配的仓库算作待审(可重复)。被滤掉的仍然计数并打印出来 —— "
        "一个把结果藏起来的过滤器和一个「真没活」的扫描不能长得一样。",
    )
    a = ap.parse_args()

    ok = True if a.no_sync else sync(a.max)
    con = sqlite3.connect(DB)
    rows, work, drafts, done = pending(con)

    if not ok:
        print("FETCH_FAILED — 下面这份是上一次同步的快照,不代表现在。不要据此判定「无待审」。")

    def keep(repo: str) -> bool:
        return not a.only or any(s.lower() in repo.lower() for s in a.only)

    shown = [w for w in work if keep(w[0])]
    filtered = [w for w in work if not keep(w[0])]

    for repo, n, head, rev, why, title in shown:
        print(f"★ {repo}#{n}  {why}  cur={head[:12]} rev={rev[:12] or '<无>'}  {title[:44]}")
    for repo, n, head, rev, why, title in drafts:
        if keep(repo):
            print(f"· (draft,跳过) {repo}#{n}  {title[:44]}")

    # A filter that hides rows must still say how many it hid. Otherwise "待审=0"
    # under --only and "待审=0" with nothing to do print the same thing, and the
    # scope restriction silently becomes a coverage gap.
    if filtered:
        print(f"· (--only 之外,今晚不管) {len(filtered)} 个: "
              + ", ".join(f"{r}#{n}" for r, n, *_ in filtered[:6])
              + (" …" if len(filtered) > 6 else ""))

    print(f"open={len(rows)} 已完成={done} 待审={len(shown)}"
          f"{f'(+{len(filtered)} 被 --only 滤掉)' if filtered else ''}"
          f" draft={sum(1 for d in drafts if keep(d[0]))}"
          f"{'' if ok else '  ⚠️ FETCH_FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
