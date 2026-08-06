#!/usr/bin/env python3
"""Test idle_state.py — "time since the last posted review", not "cycles that reviewed nothing".

    python3 tests/test_idle_state.py

Offline: builds its own model-evals.sqlite in a temp dir and drives `--now` explicitly, so the
result never depends on the wall clock or on the real database.

What it pins down:
  1. a review posted inside the window  -> active (exit 0)
  2. nothing posted for longer          -> idle (exit 3)
  3. THE BUG THIS EXISTS FOR: a review posted outside any cron cycle still counts as progress
  4. a fresh state dir with no runs does NOT read as "idle since the epoch"
  5. naive UTC timestamps are read as UTC, not as local time (a 7h local offset is longer than
     the default 60-minute window, so getting this wrong silently stops the patrol)
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "idle_state.py"

PASS = 0
FAIL = 0


def ok(m: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {m}")


def bad(m: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  ❌ {m}")


def want(m: str, cond: bool, detail: str = "") -> None:
    ok(m) if cond else bad(f"{m}{' — ' + detail if detail else ''}")


tmp = pathlib.Path(tempfile.mkdtemp(prefix="idle-"))
db_dir = tmp / "reviews" / "model-evals"
db_dir.mkdir(parents=True)
DB = db_dir / "model-evals.sqlite"


def seed(rows: list[tuple[str | None, str]]) -> None:
    """rows = [(finished_at, created_at)] oldest first."""
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.execute(
        "CREATE TABLE model_review_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at TEXT, owner TEXT, repo TEXT, pr_number INTEGER, finished_at TEXT)"
    )
    for finished, created in rows:
        con.execute(
            "INSERT INTO model_review_runs (created_at, owner, repo, pr_number, finished_at) "
            "VALUES (?,?,?,?,?)", (created, "jhfnetboy", "CoLivingOS", 74, finished))
    con.commit()
    con.close()


def run(*args: str, state: pathlib.Path | None = None):
    env = dict(os.environ, PR_DAEMON_STATE_DIR=str(state or (tmp / "state")))
    # Point the script at the temp DB by running a copy rooted in tmp.
    return subprocess.run([sys.executable, str(tmp / "scripts" / "idle_state.py"), *args],
                          capture_output=True, text=True, env=env)


(tmp / "scripts").mkdir()
(tmp / "scripts" / "idle_state.py").write_text(SCRIPT.read_text())

NOW = "2026-08-06T22:00:00+07:00"

print("[1] a review posted inside the window -> active")
seed([("2026-08-06T21:40:00+07:00", "2026-08-06T21:39:00+07:00")])
r = run("check", "--window-minutes", "60", "--now", NOW)
want("exit 0", r.returncode == 0, f"rc={r.returncode} {r.stdout}")
out = json.loads(r.stdout)
want("reports not idle", out["idle"] is False)
want("reports ~20 minutes since progress", 19 <= out["minutes_since_progress"] <= 21,
     str(out.get("minutes_since_progress")))
want("names the PR as the source", "CoLivingOS#74" in out["source"], out["source"])

print("[2] nothing posted for longer than the window -> idle")
seed([("2026-08-06T19:00:00+07:00", "2026-08-06T19:00:00+07:00")])
r = run("check", "--window-minutes", "60", "--now", NOW)
want("exit 3 (stop the patrol)", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
want("reports idle", json.loads(r.stdout)["idle"] is True)

print("[3] the actual bug: a review posted OUTSIDE a cron cycle still counts")
# Exactly 2026-08-06: two PRs reviewed on user request, every cron cycle then saw k==0.
# The round counter climbed to 3 and stopped the patrol; the timestamp must not.
seed([("2026-08-06T21:10:27+07:00", "2026-08-06T21:10:00+07:00"),
      ("2026-08-06T21:19:59+07:00", "2026-08-06T21:19:00+07:00")])
r = run("check", "--window-minutes", "60", "--now", NOW)
want("still active after 3 empty cron cycles", r.returncode == 0,
     f"rc={r.returncode} {r.stdout}")

print("[4] a fresh state dir does not read as idle-since-epoch")
seed([])
fresh = tmp / "fresh-state"
r = run("check", "--window-minutes", "60", "--now", NOW, state=fresh)
want("no runs + no baseline -> refuses to stop", r.returncode == 0, f"rc={r.returncode} {r.stdout}")
want("says why", "refusing to stop" in r.stdout)

r = run("baseline", state=fresh)
want("baseline is recorded", r.returncode == 0 and (fresh / "start-loop-baseline.json").exists())
r = run("check", "--window-minutes", "60", "--now", NOW, state=fresh)
want("just-started patrol is active", r.returncode == 0, r.stdout)
want("source is the baseline", json.loads(r.stdout)["source"] == "baseline", r.stdout)

print("[5] naive timestamps are UTC, not local")
# NOW is 22:00 +07:00 == 15:00 UTC. A naive "14:50:00" is 14:50 UTC == 21:50 +07:00,
# i.e. 10 minutes ago. Reading it as LOCAL time would make it 14:50+07 == 07:50 UTC,
# 7h10m old — past the 60-minute window, so the patrol would stop for no reason.
seed([(None, "2026-08-06 14:50:00")])
r = run("check", "--window-minutes", "60", "--now", NOW)
want("naive UTC row keeps the patrol active", r.returncode == 0, f"rc={r.returncode} {r.stdout}")
want("~10 minutes, not ~430", 9 <= json.loads(r.stdout)["minutes_since_progress"] <= 11,
     r.stdout)

print("[6] NULL finished_at falls back to created_at instead of counting as no-progress")
seed([(None, "2026-08-06 13:00:00")])
r = run("check", "--window-minutes", "60", "--now", NOW)
want("historical NULL row still yields a timestamp", "last_progress_at" in r.stdout, r.stdout)

print("[7] THE PRODUCTION SHAPE: old DB rows + a fresh baseline")
# model-evals.sqlite is git-tracked with 1000+ rows, so "a fresh state dir" in this deployment
# never means an empty DB — it means OLD rows plus a NEW baseline. `max()` must pick the baseline.
# Test [4] only covered the empty-DB case, so mutating `max(marks)` -> `marks[0]` survived it.
seed([("2026-08-01T09:00:00+07:00", "2026-08-01T09:00:00+07:00")])
fresh2 = tmp / "fresh-state-2"
run("baseline", state=fresh2)
r = run("check", "--window-minutes", "60", "--now", NOW, state=fresh2)
want("old rows + new baseline -> active", r.returncode == 0, f"rc={r.returncode} {r.stdout}")
want("the baseline wins over the old row", json.loads(r.stdout)["source"] == "baseline", r.stdout)

print("[8] the newest timestamp wins regardless of insert order")
# `ORDER BY id DESC LIMIT 50` used to assume insert order tracks finished_at. Newest row FIRST
# by id, then 60 old ones, is the shape that broke it.
rows = [("2026-08-06T21:50:00+07:00", "2026-08-06T21:50:00+07:00")]
rows += [("2026-08-01T09:00:00+07:00", "2026-08-01T09:00:00+07:00")] * 60
seed(rows)
r = run("check", "--window-minutes", "60", "--now", NOW)
want("newest row at the LOWEST id is still found", r.returncode == 0, f"rc={r.returncode} {r.stdout}")
want("~10 minutes, not 5 days", json.loads(r.stdout)["minutes_since_progress"] <= 11, r.stdout)

print("[9] an unreadable DB fails OPEN, and says so")
DB.unlink()
lonely = tmp / "db-gone-state"
run("baseline", state=lonely)
# Age the baseline well past the window so the ONLY thing that could keep it active is the
# refusal to act on a failed read.
(lonely / "start-loop-baseline.json").write_text(
    json.dumps({"started_at": "2026-08-06T10:00:00+00:00"}) + "\n")
r = run("check", "--window-minutes", "60", "--now", NOW, state=lonely)
want("does NOT stop the patrol on a failed DB read", r.returncode == 0, f"rc={r.returncode} {r.stdout}")
want("distinguishable from a healthy idle answer", "unreadable" in r.stdout, r.stdout)
want("names the DB problem", "no eval db" in r.stdout, r.stdout)

print("[10] a malformed baseline file does not crash")
for junk in ("[]", '"a string"', '{"started_at": 123}', "not json at all"):
    bad_state = tmp / ("junk-" + str(abs(hash(junk)))[:6])
    bad_state.mkdir(parents=True, exist_ok=True)
    (bad_state / "start-loop-baseline.json").write_text(junk)
    seed([("2026-08-06T21:40:00+07:00", "2026-08-06T21:40:00+07:00")])
    r = run("check", "--window-minutes", "60", "--now", NOW, state=bad_state)
    want(f"baseline {junk[:18]!r} -> no traceback",
         r.returncode in (0, 3) and "Traceback" not in r.stderr, r.stderr[-200:])

print("[11] the window boundary is inclusive (>=), as documented")
seed([("2026-08-06T21:00:00+07:00", "2026-08-06T21:00:00+07:00")])   # exactly 60 min before NOW
r = run("check", "--window-minutes", "60", "--now", NOW)
want("exactly at the window counts as idle", r.returncode == 3, f"rc={r.returncode} {r.stdout}")

print("[12] a FUTURE timestamp is clamped and flagged, not printed as negative")
seed([("2026-08-06T23:00:00+07:00", "2026-08-06T23:00:00+07:00")])
r = run("check", "--window-minutes", "60", "--now", NOW)
out = json.loads(r.stdout)
want("no negative minutes", out["minutes_since_progress"] >= 0, r.stdout)
want("clock skew is flagged", "clock_skew" in out, r.stdout)

print(f"\npassed: {PASS}   failed: {FAIL}")
sys.exit(1 if FAIL else 0)
