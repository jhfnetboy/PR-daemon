#!/usr/bin/env python3
"""Test the incremental-re-review inputs: fetch_prior_review.py + `deepseek_review.py --prior-review`.

    python3 tests/test_prior_review.py

Offline: `gh` is stubbed on PATH and the DeepSeek call is bypassed via `--print-prompt`,
so nothing here touches the network or spends a token.

What it pins down:
  1. fetch_prior_review picks OUR latest SUBSTANTIVE review, not someone else's and not a
     bare-approval stub (an empty body would silently read as "nothing was raised last round")
  2. no prior review -> exit 3, so the caller can tell "first review" from "failure"
  3. --prior-review injects the follow-up block AHEAD of the diff, and does not disturb the
     prompt when absent (the regression that matters)
  4. an over-long prior review is truncated head-first (findings live at the top of our bodies)
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

PASS = 0
FAIL = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


def want(msg: str, cond: bool, detail: str = "") -> None:
    ok(msg) if cond else bad(f"{msg}{' — ' + detail if detail else ''}")


def check(msg: str, got, expected) -> None:
    want(msg, got == expected, f"want {expected!r}, got {got!r}")


tmp = pathlib.Path(tempfile.mkdtemp())
bindir = tmp / "bin"
bindir.mkdir()


ARGV_LOG = tmp / "gh-argv.txt"


def stub_gh(reviews: list[dict], rc: int = 0) -> None:
    """Install a `gh` stub returning `reviews`, and RECORD its argv.

    Recording argv is not decoration: with a stub that ignored its arguments, mutating the real
    call to query the wrong repo AND the wrong PR number still passed 24/24. A stub that cannot
    see the query cannot pin the query.
    """
    payload = json.dumps({"reviews": reviews})
    (bindir / "gh").write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" > {ARGV_LOG}\n'
        f"[ {rc} -eq 0 ] || {{ echo 'gh: boom' >&2; exit {rc}; }}\n"
        "cat <<'JSON'\n" + payload + "\nJSON\n"
    )
    (bindir / "gh").chmod(0o755)


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
    return subprocess.run(args, capture_output=True, text=True, env=env, **kw)


def review(login: str, body: str, state: str = "CHANGES_REQUESTED", when: str | None = "2026-08-06T11:00:00Z"):
    return {"author": {"login": login}, "body": body, "state": state, "submittedAt": when}


# ── 1. picks our latest substantive review ──────────────────────────────────
print("[1] fetch_prior_review picks OUR latest substantive review")
stub_gh([
    review("clestons", "OLD REVIEW BODY — first round finding A" + " x" * 40,
           when="2026-08-06T10:00:00Z"),
    review("someone-else", "a human reviewer's comment" + " y" * 40, when="2026-08-06T12:00:00Z"),
    review("clestons", "NEWEST REVIEW BODY — second round finding B" + " z" * 40,
           when="2026-08-06T13:00:00Z"),
    review("clestons", "LGTM", state="APPROVED", when="2026-08-06T14:00:00Z"),  # too short
])
out = run([sys.executable, str(SCRIPTS / "fetch_prior_review.py"),
           "--repo", "o/r", "--pr", "7", "--output", str(tmp / "prior.md")])
check("exit 0", out.returncode, 0)
body = (tmp / "prior.md").read_text()
want("picked the NEWEST clestons review", "NEWEST REVIEW BODY" in body)
want("skipped the older one", "OLD REVIEW BODY" not in body)
want("skipped the other author's review", "a human reviewer" not in body)
want("skipped the too-short bare approval", "LGTM" not in body)
want("header carries verdict + timestamp", "CHANGES_REQUESTED" in body and "2026-08-06T13" in body)
want("queried the right PR and repo",
     "pr view 7" in ARGV_LOG.read_text() and "--repo o/r" in ARGV_LOG.read_text(),
     ARGV_LOG.read_text().strip())

print("[1b] ordering comes from submittedAt, not from array order")
stub_gh([
    review("clestons", "NEWEST BY SUBMITTED TIME" + " z" * 40, when="2026-08-06T13:00:00Z"),
    review("clestons", "OLDER BUT LAST IN ARRAY" + " x" * 40, when="2026-08-06T10:00:00Z"),
])
out = run([sys.executable, str(SCRIPTS / "fetch_prior_review.py"),
           "--repo", "o/r", "--pr", "7", "--output", str(tmp / "ord.md")])
want("newest-by-time wins even when it is first in the array",
     "NEWEST BY SUBMITTED TIME" in (tmp / "ord.md").read_text(),
     (tmp / "ord.md").read_text()[:200])

print("[1c] unsubmitted drafts and dismissed reviews are not 'what we posted'")
stub_gh([
    review("clestons", "THE REAL SUBMITTED REVIEW" + " z" * 40, when="2026-08-06T10:00:00Z"),
    review("clestons", "PENDING SCRATCH NOTES" + " y" * 40, state="PENDING", when=None),
    review("clestons", "DISMISSED OLD TAKE" + " y" * 40, state="DISMISSED",
           when="2026-08-06T12:00:00Z"),
])
out = run([sys.executable, str(SCRIPTS / "fetch_prior_review.py"),
           "--repo", "o/r", "--pr", "7", "--output", str(tmp / "st.md")])
got = (tmp / "st.md").read_text()
want("PENDING draft is skipped", "PENDING SCRATCH NOTES" not in got)
want("DISMISSED is skipped", "DISMISSED OLD TAKE" not in got)
want("the real submitted review is used", "THE REAL SUBMITTED REVIEW" in got)

print("[1d] gh failure is exit 1, not exit 3")
stub_gh([], rc=1)
out = run([sys.executable, str(SCRIPTS / "fetch_prior_review.py"),
           "--repo", "o/r", "--pr", "7", "--output", str(tmp / "fail.md")])
want("hard failure exits 1 (distinct from 'no prior review')", out.returncode == 1,
     f"rc={out.returncode}")

# ── 2. no prior review -> exit 3 ────────────────────────────────────────────
print("[2] no prior review is exit 3, not a crash and not a false empty")
stub_gh([review("someone-else", "not ours" + " y" * 40)])
out = run([sys.executable, str(SCRIPTS / "fetch_prior_review.py"),
           "--repo", "o/r", "--pr", "7", "--output", str(tmp / "none.md")])
check("exit 3 (first-time review)", out.returncode, 3)
want("says it is a first-time review", "first-time review" in out.stderr)
want("wrote no file", not (tmp / "none.md").exists())

# A caller reusing a fixed path (/tmp/prior.md) across PRs must not inherit the previous PR's
# review — that would feed R1 another PR's findings as this PR's prior round.
stale = tmp / "stale.md"
stale.write_text("A DIFFERENT PR'S REVIEW")
out = run([sys.executable, str(SCRIPTS / "fetch_prior_review.py"),
           "--repo", "o/r", "--pr", "7", "--output", str(stale)])
want("a stale --output from an earlier PR is removed on exit 3", not stale.exists(),
     stale.read_text() if stale.exists() else "")

# ── 3. prompt assembly ──────────────────────────────────────────────────────
print("[3] --prior-review injects the follow-up block ahead of the diff")
diff_file = tmp / "d.diff"
diff_file.write_text("--- a/x.ts\n+++ b/x.ts\n@@\n+const MARKER_IN_DIFF = 1;\n")
prior_file = tmp / "prior.md"

base = [sys.executable, str(SCRIPTS / "deepseek_review.py"),
        "--diff-file", str(diff_file), "--repo", "o/r", "--pr", "7", "--print-prompt"]

plain = run(base)
check("plain run exits 0", plain.returncode, 0)
want("plain prompt has the diff", "MARKER_IN_DIFF" in plain.stdout)
want("plain prompt has NO incremental block", "INCREMENTAL RE-REVIEW" not in plain.stdout)

incr = run(base + ["--prior-review", str(prior_file)])
check("incremental run exits 0", incr.returncode, 0)
want("incremental prompt announces the mode", "INCREMENTAL RE-REVIEW" in incr.stdout)
want("carries the prior review text", "NEWEST REVIEW BODY" in incr.stdout)
want("still carries the diff", "MARKER_IN_DIFF" in incr.stdout)
want("asks for FIXED/PARTIAL/NOT FIXED", "PARTIAL" in incr.stdout and "NOT FIXED" in incr.stdout)
want(
    "block comes BEFORE the diff (a long diff must not bury the instructions)",
    incr.stdout.index("INCREMENTAL RE-REVIEW") < incr.stdout.index("MARKER_IN_DIFF"),
)
want("stderr reports incremental mode", "incremental mode" in incr.stderr)

# an empty prior file must degrade to a normal review, not emit an empty "nothing was raised" block
empty = tmp / "empty.md"
empty.write_text("   \n")
deg = run(base + ["--prior-review", str(empty)])
want("empty prior file falls back to a fresh review", "INCREMENTAL RE-REVIEW" not in deg.stdout)
want("and says so", "empty" in deg.stderr)

# ── 4. truncation keeps the head ────────────────────────────────────────────
print("[3b] a MISSING prior file degrades instead of killing the round")
missing = run(base + ["--prior-review", str(tmp / "does-not-exist.md")])
check("still exits 0", missing.returncode, 0)
want("no traceback", "Traceback" not in missing.stderr, missing.stderr[-300:])
want("falls back to a fresh review", "INCREMENTAL RE-REVIEW" not in missing.stdout)
want("warns on stderr", "unreadable" in missing.stderr, missing.stderr.strip())

print("[3c] security mode (R1b) does not get the follow-up block")
sec = run(base + ["--mode", "security", "--prior-review", str(prior_file)])
check("exits 0", sec.returncode, 0)
want("R1b keeps its own contract", "SECURITY_FINDINGS" in sec.stdout)
want("no follow-up block in R1b", "INCREMENTAL RE-REVIEW" not in sec.stdout)
want("says why", "ignored in security mode" in sec.stderr, sec.stderr.strip())

print("[3d] --print-prompt honors --output")
po = tmp / "printed.txt"
run(base + ["--output", str(po)])
want("--output is written in print-prompt mode", po.exists() and "MARKER_IN_DIFF" in po.read_text())

print("[4] an over-long prior review is truncated head-first")
long_prior = tmp / "long.md"
long_prior.write_text("FINDING_AT_TOP\n" + ("filler line\n" * 4000) + "TAIL_MARKER\n")
cut = run(base + ["--prior-review", str(long_prior)])
want("kept the head (findings live there)", "FINDING_AT_TOP" in cut.stdout)
want("dropped the tail", "TAIL_MARKER" not in cut.stdout)
want("said it truncated", "truncated" in cut.stdout)

print(f"\npassed: {PASS}   failed: {FAIL}")
sys.exit(1 if FAIL else 0)
