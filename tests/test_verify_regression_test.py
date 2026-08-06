#!/usr/bin/env python3
"""Test verify_regression_test.py against a synthetic git repo.

    python3 tests/test_verify_regression_test.py

Fully offline and deterministic: builds a throwaway git repo with a trivial shell "test runner",
so no node_modules, no network, no vitest. The runner is injected via --test-cmd, which is the
same seam a non-JS project would use.

What it pins down:
  1. an INERT new test (green with the fix reverted) is reported, exit 2
  2. a LOAD-BEARING new test (red with the fix reverted) is not reported, exit 0
  3. a RENAMED pre-existing test is skipped, not mistaken for a new inert one
  4. tests-only and source-only PRs are skipped rather than mis-reported
  5. a source file the PR ADDED is deleted (not left in place) when reverting — otherwise the
     new test would import the very code the revert is meant to remove
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify_regression_test.py"

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


# A "test runner": each test file is a shell script; `run <name>` exits non-zero if that test
# fails. `impl.sh` is the source under test — reverting it is what the tool does.
RUNNER = """#!/usr/bin/env bash
# usage: runner.sh <testfile> <testname>
set -uo pipefail
[ -f ./src/impl.sh ] || exit 1        # source deleted = every test fails, as it should
source ./src/impl.sh
# `eval`, not `| bash`: a pipe spawns a fresh shell that has never seen the sourced function,
# so every assertion dies with "clamp: command not found" and the tool honestly reports
# "FAILS at PR head". (This test file's own first run did exactly that.)
eval "$(grep -A2 "TESTBODY:$2" "$1" | tail -1)"
"""


def repo_with(commits: list[dict]) -> pathlib.Path:
    """Build a git repo, applying each commit's {path: content} then committing."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="vrt-repo-"))
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    (d / "runner.sh").write_text(RUNNER)
    (d / "runner.sh").chmod(0o755)
    for c in commits:
        for path, content in c.items():
            p = d / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=d, check=True, env=env)
    return d


def shas(d: pathlib.Path) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%H", "--reverse"], cwd=d,
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def run_tool(d: pathlib.Path, base: str, head: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-path", str(d), "--base", base, "--head", head,
         "--test-cmd", "bash ./runner.sh {file} {name}"],
        capture_output=True, text=True,
    )


# `clamp` returns 0 on the buggy version for the value the new test uses, so a test asserting
# clamp(5)==3 passes BEFORE and AFTER — inert. A test asserting clamp(9)==3 only passes after.
BUGGY = 'clamp() { if [ "$1" -ge 9 ]; then echo 0; else echo 3; fi; }\n'
FIXED = 'clamp() { echo 3; }\n'

TESTS_INERT = """# TESTBODY:inert-case
[ "$(clamp 5)" = "3" ]
"""
TESTS_LOADBEARING = """# TESTBODY:inert-case
[ "$(clamp 5)" = "3" ]
# TESTBODY:real-case
[ "$(clamp 9)" = "3" ]
"""

print("[1] an inert new test is reported")
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"src/impl.sh": FIXED, "tests/t.sh": "# TESTBODY:old\ntrue\n" + TESTS_INERT.replace(
        "# TESTBODY:inert-case", 'it("inert-case")\n# TESTBODY:inert-case')},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("exit 2 (finding)", r.returncode == 2, f"rc={r.returncode}\n{r.stdout}\n{r.stderr}")
want("names the inert test", "inert-case" in r.stdout and "NOT load-bearing" in r.stdout)
want("says it is a judgement call, not an auto-block", "判断题" in r.stdout)
shutil.rmtree(d, ignore_errors=True)

print("[2] a load-bearing new test is NOT reported")
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"src/impl.sh": FIXED, "tests/t.sh": 'it("real-case")\n' + TESTS_LOADBEARING},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("exit 0 (clean)", r.returncode == 0, f"rc={r.returncode}\n{r.stdout}")
want("says load-bearing", "load-bearing" in r.stdout and "NOT load-bearing" not in r.stdout)
shutil.rmtree(d, ignore_errors=True)

print("[3] a renamed pre-existing test is skipped, not flagged")
body = '\n  [ "$(clamp 5)" = "3" ]\n'
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": 'it("old name", () => {' + body + '});\n'},
    {"src/impl.sh": FIXED, "tests/t.sh": 'it("new name", () => {' + body + '});\n'},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("rename is detected and skipped", "skip (renamed" in r.stdout, r.stdout)
want("exit 0 — a rename is not a finding", r.returncode == 0, f"rc={r.returncode}")
shutil.rmtree(d, ignore_errors=True)

print("[4] tests-only / source-only PRs are skipped")
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"tests/t.sh": '# TESTBODY:old\ntrue\nit("added")\n# TESTBODY:added\ntrue\n'},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("tests-only PR is skipped (reverting nothing would fake a pass)",
     r.returncode == 0 and "no source file" in r.stdout, r.stdout)
shutil.rmtree(d, ignore_errors=True)

d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"src/impl.sh": FIXED},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("source-only PR is skipped", r.returncode == 0 and "no test file" in r.stdout, r.stdout)
shutil.rmtree(d, ignore_errors=True)

print("[5] a source file the PR ADDED is deleted when reverting")
d = repo_with([
    {"src/impl.sh": FIXED, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"src/impl.sh": FIXED, "src/added.sh": "extra() { echo hi; }\n",
     "tests/t.sh": 'it("uses-added")\n# TESTBODY:uses-added\n[ -f ./src/added.sh ]\n'},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("added file is removed on revert, so the test correctly fails without it",
     r.returncode == 0 and "load-bearing" in r.stdout, f"rc={r.returncode}\n{r.stdout}")
shutil.rmtree(d, ignore_errors=True)

print("[6] a prefix-colliding sibling must not clear an inert test (false NEGATIVE)")
# The bug: `-t "discount ok"` is a REGEX, so it also selects "discount ok with remainder".
# The sibling fails after the revert, the command exits non-zero, and the inert test under
# examination gets cleared as load-bearing — silently missing the exact defect this tool exists
# to find. The synthetic runner below models that: it runs EVERY test whose name contains the
# pattern, and fails if any of them fails.
GREEDY_RUNNER = """#!/usr/bin/env bash
set -uo pipefail
[ -f ./src/impl.sh ] || exit 1
source ./src/impl.sh
rc=0
while read -r n; do
  case "$n" in *"$2"*) eval "$(grep -A2 "TESTBODY:$n" "$1" | tail -1)" || rc=1 ;; esac
done < <(grep -o 'TESTBODY:[^ ]*' "$1" | sed 's/TESTBODY://' | sort -u)
exit $rc
"""
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"src/impl.sh": FIXED,
     "tests/t.sh": ('it("discount ok")\n# TESTBODY:discount ok\n[ "$(clamp 5)" = "3" ]\n'
                    'it("discount ok with remainder")\n'
                    '# TESTBODY:discount ok with remainder\n[ "$(clamp 9)" = "3" ]\n')},
])
(d / "runner.sh").write_text(GREEDY_RUNNER)
(d / "runner.sh").chmod(0o755)
base, head = shas(d)
r = run_tool(d, base, head)
# With a custom --test-cmd there is no JSON report, so selection COUNT is unknowable and the
# collision genuinely cannot be resolved — the tool must say so instead of presenting a clean
# verdict. (The auto-detected vitest/jest path does resolve it, via --reporter=json; that path is
# covered by the real-repo run documented in the PR body, since it needs node_modules.)
want("custom runners are flagged as unable to confirm selection",
     "无法确认" in r.stdout, r.stdout)
shutil.rmtree(d, ignore_errors=True)

print("[7] nothing verifiable is exit 1, never a green all-clear")
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    # The new test is red at PR head (asserts something false), so it can never be judged.
    {"src/impl.sh": FIXED, "tests/t.sh": 'it("broken")\n# TESTBODY:broken\nfalse\n'},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("exit 1, not 0", r.returncode == 1, f"rc={r.returncode}\n{r.stdout}")
want("does NOT claim all load-bearing", "all 1 new test" not in r.stdout, r.stdout)
want("says it could not verify", "无法验证" in r.stdout, r.stdout)
shutil.rmtree(d, ignore_errors=True)

print("[8] a substring-named sibling is not mistaken for a rename")
# base has "computes total with discount"; the PR adds a genuinely new, genuinely inert
# "computes total". Matching "the line contains the name" picked up the OLDER test's body,
# found it in base, and skipped the new one as a rename — a silent false negative.
old_body = '\n  [ "$(clamp 5)" = "3" ]\n# TESTBODY:computes total with discount\n[ "$(clamp 5)" = "3" ]\n'
d = repo_with([
    {"src/impl.sh": BUGGY,
     "tests/t.sh": 'it("computes total with discount", () => {' + old_body + '});\n'},
    {"src/impl.sh": FIXED,
     "tests/t.sh": ('it("computes total with discount", () => {' + old_body + '});\n'
                    'it("computes total")\n# TESTBODY:computes total\n[ "$(clamp 5)" = "3" ]\n')},
])
base, head = shas(d)
r = run_tool(d, base, head)
want("the new substring-named test is NOT skipped as a rename",
     "skip (renamed" not in r.stdout or "computes total\"" not in r.stdout, r.stdout)
want("it is judged and reported", r.returncode == 2, f"rc={r.returncode}\n{r.stdout}")
shutil.rmtree(d, ignore_errors=True)

print("[9] a non-JS test file is refused, not silently cleared")
d = repo_with([
    {"src/impl.sh": BUGGY, "tests/lib.rs": "// nothing\n"},
    {"src/impl.sh": FIXED, "tests/lib.rs": "#[test]\nfn clamps_nine() { assert_eq!(clamp(9), 3); }\n"},
])
base, head = shas(d)
r = subprocess.run(
    [sys.executable, str(SCRIPT), "--repo-path", str(d), "--base", base, "--head", head],
    capture_output=True, text=True)
want("exit 1 for a language it cannot read", r.returncode == 1, f"rc={r.returncode}\n{r.stdout}")
want("says so plainly", "不支持的测试语言" in r.stdout, r.stdout)
shutil.rmtree(d, ignore_errors=True)

print("[10] source files are not misclassified as tests by a bare substring")
d = repo_with([
    {"src/latest.sh": BUGGY, "tests/t.sh": "# TESTBODY:old\ntrue\n"},
    {"src/latest.sh": FIXED,
     "tests/t.sh": 'it("inert")\n# TESTBODY:inert\n[ "$(clamp 5)" = "3" ]\n'},
])
(d / "runner.sh").write_text(RUNNER.replace("./src/impl.sh", "./src/latest.sh"))
(d / "runner.sh").chmod(0o755)
base, head = shas(d)
r = run_tool(d, base, head)
want("src/latest.sh is treated as SOURCE (it contains 'test' as a substring)",
     "src/latest.sh" in r.stdout and "no source file" not in r.stdout, r.stdout)
shutil.rmtree(d, ignore_errors=True)

print(f"\npassed: {PASS}   failed: {FAIL}")
sys.exit(1 if FAIL else 0)
