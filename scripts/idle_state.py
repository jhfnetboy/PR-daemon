#!/usr/bin/env python3
"""
idle_state.py — has the patrol actually made progress lately?

## Why this replaces the round counter

The `$pr start` patrol used to auto-stop after N consecutive cycles that reviewed nothing
(`idle_rounds`), which is a proxy for "nothing is happening" — and a wrong one. On 2026-08-06 two
PRs were reviewed and posted **at the user's direct request**, outside a cron cycle; every cron
cycle still saw `k == 0`, so `idle_rounds` climbed 0→3 and the patrol stopped itself an hour
after a session that had just done real work.

The counter said "cycles that reviewed nothing". What it was *meant* to say is "time since the
last sign of progress" — which is the same correction already applied to the overlap lock's mtime
(refresh after every PR, not only at cycle start). So measure it directly: the most recent
`finished_at` in `model_review_runs` is a review that actually posted, whoever triggered it.

A fresh state dir has no runs at all, which must not read as "idle since the epoch" and stop the
patrol on its first tick. `baseline` records a start time for exactly that case.

## Usage

    python3 scripts/idle_state.py baseline                 # at `$pr start`
    python3 scripts/idle_state.py check --window-minutes 60
        -> prints JSON; exit 0 = progress within the window, exit 3 = idle, stop the patrol

Exit codes: 0 = active, 3 = idle for longer than the window, 1 = could not tell.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVAL_DB = ROOT / "reviews" / "model-evals" / "model-evals.sqlite"


def state_dir() -> pathlib.Path:
    env = os.environ.get("PR_DAEMON_STATE_DIR")
    return pathlib.Path(env) if env else ROOT / ".state" / "pr-daemon"


def baseline_path() -> pathlib.Path:
    return state_dir() / "start-loop-baseline.json"


def parse_ts(raw: str) -> datetime | None:
    """Parse the timestamp shapes this repo actually stores.

    `record-run --finished-at` writes ISO-8601 with an offset (`...+07:00`), while the table's
    DEFAULT CURRENT_TIMESTAMP writes naive UTC (`2026-08-06 15:10:27`). Both appear in the same
    column, so both must parse — and a naive one must be READ AS UTC, not as local time, or the
    comparison silently shifts by the local offset (7 hours here, which is longer than the
    default idle window).
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def last_post() -> tuple[datetime | None, str]:
    """(timestamp of the most recent posted review, human label)."""
    if not EVAL_DB.exists():
        return None, "no eval db"
    try:
        con = sqlite3.connect(f"file:{EVAL_DB}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT finished_at, created_at, owner, repo, pr_number FROM model_review_runs "
            "ORDER BY id DESC LIMIT 50"
        ).fetchall()
        con.close()
    except sqlite3.Error as e:
        return None, f"db error: {e}"

    best: tuple[datetime, str] | None = None
    for finished, created, owner, repo, pr in rows:
        # finished_at is NULL on historical rows (never backfilled — see ROADMAP §4), so fall
        # back to created_at rather than treating those rows as "no progress ever".
        ts = parse_ts(finished) or parse_ts(created)
        if ts and (best is None or ts > best[0]):
            best = (ts, f"{owner}/{repo}#{pr}")
    return (best[0], best[1]) if best else (None, "no runs recorded")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline", help="record 'the patrol started now'")
    p_check = sub.add_parser("check", help="idle for longer than the window?")
    p_check.add_argument("--window-minutes", type=int, default=60)
    p_check.add_argument("--now", default="", help="override 'now' (testing only)")
    args = ap.parse_args()

    if args.cmd == "baseline":
        p = baseline_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        p.write_text(json.dumps({"started_at": now}) + "\n")
        print(f"baseline recorded: {now}")
        return 0

    now = parse_ts(args.now) or datetime.now(timezone.utc)
    ts, label = last_post()

    base_ts = None
    if baseline_path().exists():
        try:
            base_ts = parse_ts(json.loads(baseline_path().read_text()).get("started_at", ""))
        except (json.JSONDecodeError, OSError):
            base_ts = None

    # The patrol is "active" if EITHER a review posted recently OR it only just started. Taking
    # the max is what keeps a fresh state dir (no runs at all) from reading as idle-since-epoch.
    marks = [t for t in (ts, base_ts) if t is not None]
    if not marks:
        print(json.dumps({"idle": False, "reason": "no timestamp available — refusing to stop",
                          "detail": label}, ensure_ascii=False))
        return 0

    newest = max(marks)
    minutes = (now - newest).total_seconds() / 60.0
    idle = minutes >= args.window_minutes
    print(json.dumps({
        "idle": idle,
        "minutes_since_progress": round(minutes, 1),
        "window_minutes": args.window_minutes,
        "last_progress_at": newest.isoformat(),
        "source": "baseline" if base_ts and newest == base_ts else label,
    }, ensure_ascii=False))
    return 3 if idle else 0


if __name__ == "__main__":
    sys.exit(main())
