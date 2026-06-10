#!/usr/bin/env python3
"""
triage_db.py — track 2-round vs 4-round triage decisions and validate criteria.

Per DESIGN.md §4: every PR is classified 2-round (low risk) or 4-round (high
risk). This records each decision + rationale, and computes the triage
false-negative rate (how often a 2-round PR should have been 4-round).

Usage:
  # record a triage decision
  python3 scripts/triage_db.py record \
    --repo OWNER/REPO --pr N --head-oid HEAD \
    --rounds 2 --rationale "docs-only chore, no src/ touch" \
    --signals "type:docs,no-core-code"

  # flag a 2-round PR as a triage miss (human later requested changes / bug found)
  python3 scripts/triage_db.py flag-miss --repo OWNER/REPO --pr N --note "human RC'd it"

  # record a retroactive 4-round audit result on a 2-round PR
  python3 scripts/triage_db.py audit --repo OWNER/REPO --pr N --found-issue true|false

  # show the validation report (false-negative rate)
  python3 scripts/triage_db.py report
"""

import sys, argparse, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "reviews" / "model-evals" / "triage.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS triage_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    head_oid TEXT,
    rounds INTEGER NOT NULL,          -- 2 or 4
    rationale TEXT,
    signals TEXT,                     -- comma list of triggered signals
    -- validation fields (filled later):
    flagged_miss INTEGER DEFAULT 0,   -- 1 = a 2-round PR that should've been 4-round
    miss_note TEXT,
    audited INTEGER DEFAULT 0,        -- 1 = retroactively run full 4-round
    audit_found_issue INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_triage_target ON triage_decisions(repo, pr_number, created_at);
"""


def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def cmd_record(a):
    c = conn()
    c.execute(
        "INSERT INTO triage_decisions (repo, pr_number, head_oid, rounds, rationale, signals) "
        "VALUES (?,?,?,?,?,?)",
        (a.repo, a.pr, a.head_oid, a.rounds, a.rationale, a.signals),
    )
    c.commit()
    print(f"recorded triage: {a.repo}#{a.pr} → {a.rounds}-round  ({a.rationale})")
    return 0


def cmd_flag_miss(a):
    c = conn()
    c.execute(
        "UPDATE triage_decisions SET flagged_miss=1, miss_note=? "
        "WHERE repo=? AND pr_number=? AND id=(SELECT MAX(id) FROM triage_decisions WHERE repo=? AND pr_number=?)",
        (a.note, a.repo, a.pr, a.repo, a.pr),
    )
    c.commit()
    print(f"⚠️  flagged triage miss: {a.repo}#{a.pr}  ({a.note})")
    return 0


def cmd_audit(a):
    c = conn()
    found = 1 if a.found_issue.lower() in ("true", "1", "yes") else 0
    c.execute(
        "UPDATE triage_decisions SET audited=1, audit_found_issue=? "
        "WHERE repo=? AND pr_number=? AND id=(SELECT MAX(id) FROM triage_decisions WHERE repo=? AND pr_number=?)",
        (found, a.repo, a.pr, a.repo, a.pr),
    )
    c.commit()
    verdict = "FOUND issue (triage miss!)" if found else "clean (triage correct)"
    print(f"audit {a.repo}#{a.pr}: 4-round retro → {verdict}")
    return 0


def cmd_report(a):
    c = conn()
    total = c.execute("SELECT COUNT(*) FROM triage_decisions").fetchone()[0]
    if total == 0:
        print("No triage decisions recorded yet.")
        return 0
    two = c.execute("SELECT COUNT(*) FROM triage_decisions WHERE rounds=2").fetchone()[0]
    four = c.execute("SELECT COUNT(*) FROM triage_decisions WHERE rounds=4").fetchone()[0]
    misses = c.execute("SELECT COUNT(*) FROM triage_decisions WHERE rounds=2 AND flagged_miss=1").fetchone()[0]
    audited = c.execute("SELECT COUNT(*) FROM triage_decisions WHERE rounds=2 AND audited=1").fetchone()[0]
    audit_found = c.execute("SELECT COUNT(*) FROM triage_decisions WHERE rounds=2 AND audited=1 AND audit_found_issue=1").fetchone()[0]

    # false-negative rate = (flagged misses + audit-found issues) / 2-round total
    fn = misses + audit_found
    fn_rate = (fn / two * 100) if two else 0.0

    print("═══════════  Triage Validation Report  ═══════════")
    print(f"  Total triaged   : {total}")
    print(f"  2-round (low)   : {two}")
    print(f"  4-round (high)  : {four}")
    print(f"  ─────────────────────────────────")
    print(f"  2-round misses  : {misses} (human flagged)")
    print(f"  2-round audited : {audited}  → {audit_found} found issues")
    print(f"  ─────────────────────────────────")
    print(f"  🎯 False-negative rate: {fn_rate:.1f}%  (target < 5%)")
    if fn_rate >= 5:
        print(f"  ⚠️  ABOVE TARGET — tighten 2-round criteria, push more PRs to 4-round")
    else:
        print(f"  ✅ Within target — triage criteria effective")
    print("═" * 50)
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="Track and validate 2/4-round triage decisions.")
    sub = p.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--repo", required=True)
    rec.add_argument("--pr", type=int, required=True)
    rec.add_argument("--head-oid", default=None)
    rec.add_argument("--rounds", type=int, choices=[2, 4], required=True)
    rec.add_argument("--rationale", default="")
    rec.add_argument("--signals", default="")
    rec.set_defaults(func=cmd_record)

    fm = sub.add_parser("flag-miss")
    fm.add_argument("--repo", required=True)
    fm.add_argument("--pr", type=int, required=True)
    fm.add_argument("--note", default="")
    fm.set_defaults(func=cmd_flag_miss)

    au = sub.add_parser("audit")
    au.add_argument("--repo", required=True)
    au.add_argument("--pr", type=int, required=True)
    au.add_argument("--found-issue", required=True)
    au.set_defaults(func=cmd_audit)

    rp = sub.add_parser("report")
    rp.set_defaults(func=cmd_report)

    return p


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
