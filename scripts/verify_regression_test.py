#!/usr/bin/env python3
"""
verify_regression_test.py — does this PR's new regression test actually fail without the fix?

## Why this exists

A regression test that passes against the pre-fix code is worse than no test at all: on the diff
it looks like the bug has been nailed shut, so nobody looks again — and nothing stops the bug
coming back.

Found by hand on jhfnetboy/CoLivingOS#74 (2026-08-06). The PR fixed a real discount-proration bug
and shipped a test named "有一单欠额为 0 时，折扣不会把它压成负数". Swapping the changed source file
back to its parent-commit version and re-running the suite: **45/45 still green**. The test used
2 allocations and zeroed the last one, so `floor(discount·a₀/a₀) == discount` exactly — the
remainder was always 0 and the buggy "remainder → last row" branch never executed. Reproducing it
needed ≥3 rows AND an indivisible remainder AND the zero-owed row last.

That check is mechanical, so it should not depend on a reviewer thinking of it.

## What it does

    for each test added by this PR:
        run it at PR head                      -> must PASS (else the PR is just broken)
        revert this PR's source files to base  -> run it again
        still passes  ->  [Medium] the test is not load-bearing

## Usage

    python3 scripts/verify_regression_test.py --repo-path ~/Dev/jhfnetboy/CoLivingOS \\
        --base 0a633af --head 5f7aa04

    # non-vitest projects: {file} and {name} are substituted
    ... --test-cmd 'npx jest {file} -t {name}'
    ... --test-cmd 'cargo test {name}'

Exit codes: 0 = every added test is load-bearing (or nothing to check)
            2 = at least one added test passes without the fix  ← the finding
            1 = could not run the check (bad range, no runner, tests red at head)
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# A test declaration as it appears on an ADDED diff line:  + it("name", ... / + test('name'
# Also matches vitest/jest modifiers (it.only, test.each) so a renamed-but-real test is not missed.
ADDED_TEST_RE = re.compile(
    r"""^\+\s*(?:it|test)(?:\.\w+)*\s*\(\s*(['"`])(?P<name>(?:(?!\1).)+)\1""",
    re.MULTILINE,
)

TEST_PATH_HINTS = ("test", "spec", "__tests__")
# Files whose reversion cannot change behaviour — reverting them adds noise, not signal.
NON_SOURCE_SUFFIXES = (".md", ".txt", ".json", ".lock", ".yaml", ".yml", ".toml", ".snap")


def sh(args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def git(cwd: Path, *args: str, check: bool = True) -> str:
    # `-c core.quotePath=false` is NOT cosmetic: by default git C-quotes any path with a non-ASCII
    # byte (`"docs/16-\346\270\240..."`), and that quoted string is not a usable path — `git show`
    # rejects it and the suffix test sees `.md"` instead of `.md`. Caught by the first negative
    # control run, on a repo whose docs are named in Chinese.
    out = sh(["git", "-c", "core.quotePath=false", *args], cwd)
    if out.returncode != 0:
        if not check:
            return ""
        sys.exit(f"❌ git {' '.join(args)} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def is_test_file(path: str) -> bool:
    low = path.lower()
    return any(h in low for h in TEST_PATH_HINTS)


def classify(repo: Path, base: str, head: str) -> tuple[list[str], list[str]]:
    """-> (test files changed, source files changed)"""
    changed = [p for p in git(repo, "diff", "--name-only", f"{base}..{head}").splitlines() if p]
    tests = [p for p in changed if is_test_file(p)]
    src = [
        p for p in changed
        if p not in tests and not p.lower().endswith(NON_SOURCE_SUFFIXES)
    ]
    return tests, src


def _test_body(text: str, name: str) -> str:
    """The body of the test declaring `name`, from its `it(` line to the matching close.

    Approximate but adequate: JS/TS test files close a test with `});` at the declaration's own
    indentation, and a nested block is always indented further.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if name in line and re.search(r"\b(it|test)(\.\w+)*\s*\(", line):
            indent = len(line) - len(line.lstrip())
            out = []
            for nxt in lines[i + 1:]:
                if nxt.strip().startswith("})") and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                out.append(nxt)
            return re.sub(r"\s+", " ", "\n".join(out)).strip()
    return ""


def added_tests(repo: Path, base: str, head: str, test_files: list[str]) -> list[tuple[str, str]]:
    """-> [(test file, test name)] for every test declaration this PR genuinely ADDED.

    A RENAMED test looks added (its `it("…")` line is a `+` line) but is not new: its body is
    unchanged, so of course it still passes without the fix, and reporting it as
    "not load-bearing" is noise. Observed on CoLivingOS#74, where a pre-existing remainder test
    was retitled in the same commit and got flagged alongside the genuinely inert new one.
    So: if the body is byte-identical (whitespace-normalised) to a test body already present in
    the base version of the file, treat it as a rename and skip it.
    """
    found: list[tuple[str, str]] = []
    for f in test_files:
        diff = git(repo, "diff", f"{base}..{head}", "--", f)
        names = [m.group("name") for m in ADDED_TEST_RE.finditer(diff)]
        if not names:
            continue
        head_text = git(repo, "show", f"{head}:{f}")
        try:
            base_text = git(repo, "show", f"{base}:{f}")
        except SystemExit:
            base_text = ""      # brand-new test file: every test in it is genuinely new
        base_bodies = {
            b for b in (
                _test_body(base_text, n)
                for n in {m.group("name") for m in ADDED_TEST_RE.finditer(
                    "\n".join("+" + l for l in base_text.splitlines()))}
            ) if b
        }
        for name in names:
            body = _test_body(head_text, name)
            if body and body in base_bodies:
                print(f"skip (renamed, body unchanged): {f} :: {name}")
                continue
            found.append((f, name))
    return found


def default_test_cmd(repo: Path) -> str:
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            blob = json.loads(pkg.read_text())
            deps = {**blob.get("devDependencies", {}), **blob.get("dependencies", {})}
            if "vitest" in deps:
                return "npx vitest run {file} -t {name}"
            if "jest" in deps:
                return "npx jest {file} -t {name}"
        except (json.JSONDecodeError, OSError):
            pass
    if (repo / "Cargo.toml").exists():
        return "cargo test {name}"
    sys.exit(
        "❌ could not detect a test runner — pass --test-cmd 'npx vitest run {file} -t {name}'"
    )


def run_one(cmd_tpl: str, wt: Path, file: str, name: str) -> bool:
    """True if the named test PASSES."""
    cmd = cmd_tpl.replace("{file}", shlex.quote(file)).replace("{name}", shlex.quote(name))
    out = sh(["bash", "-lc", cmd], wt)
    return out.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-path", required=True, help="local checkout of the repo under review")
    ap.add_argument("--base", required=True, help="commit BEFORE the fix (e.g. the PR's parent)")
    ap.add_argument("--head", required=True, help="PR head")
    ap.add_argument("--test-cmd", default="", help="template with {file} and {name}")
    ap.add_argument("--link-node-modules", action="store_true", default=True,
                    help="symlink node_modules into the worktree (default on)")
    ap.add_argument("--json", action="store_true", help="machine-readable result on stdout")
    args = ap.parse_args()

    repo = Path(args.repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        sys.exit(f"❌ not a git checkout: {repo}")

    tests, src = classify(repo, args.base, args.head)
    if not tests:
        print("skip: this PR changes no test file — nothing to verify")
        return 0
    if not src:
        # Reverting nothing would make every test trivially pass and report a false finding.
        print("skip: this PR changes tests but no source file — reverting would be a no-op")
        return 0

    cases = added_tests(repo, args.base, args.head, tests)
    if not cases:
        print(f"skip: {len(tests)} test file(s) changed but no NEW test declaration was added")
        return 0

    cmd_tpl = args.test_cmd or default_test_cmd(repo)
    wt = Path(tempfile.mkdtemp(prefix="verify-regr-"))
    shutil.rmtree(wt, ignore_errors=True)   # git worktree add wants a non-existent path
    findings: list[dict] = []
    try:
        git(repo, "worktree", "add", "--detach", str(wt), args.head)
        if args.link_node_modules and (repo / "node_modules").exists() \
                and not (wt / "node_modules").exists():
            (wt / "node_modules").symlink_to(repo / "node_modules")

        print(f"runner: {cmd_tpl}")
        print(f"source files to revert: {', '.join(src)}")
        print(f"new tests to check: {len(cases)}\n")

        for file, name in cases:
            print(f"· {file} :: {name}")
            if not run_one(cmd_tpl, wt, file, name):
                # Red at head is a different (and louder) problem; do not call it "not load-bearing".
                print("    ⚠️  FAILS at PR head — the test itself is broken, skipping")
                findings.append({"file": file, "test": name, "status": "fails_at_head"})
                continue

            for s in src:
                exists_at_base = sh(
                    ["git", "-c", "core.quotePath=false", "cat-file", "-e", f"{args.base}:{s}"], repo
                ).returncode == 0
                if exists_at_base:
                    blob = git(repo, "show", f"{args.base}:{s}")
                    (wt / s).parent.mkdir(parents=True, exist_ok=True)
                    (wt / s).write_text(blob)
                elif (wt / s).exists():
                    # The PR ADDED this file. At base it did not exist, so the faithful revert is
                    # deletion — leaving it in place would let the new test import the very code
                    # the revert is meant to remove, and every test would look load-bearing.
                    (wt / s).unlink()
            still_green = run_one(cmd_tpl, wt, file, name)
            git(wt, "checkout", "--", ".")   # restore head for the next case

            if still_green:
                print("    ❌ PASSES without the fix — NOT load-bearing")
                findings.append({"file": file, "test": name, "status": "not_load_bearing"})
            else:
                print("    ✅ fails without the fix — load-bearing")
    finally:
        sh(["git", "worktree", "remove", "--force", str(wt)], repo)

    inert = [f for f in findings if f["status"] == "not_load_bearing"]
    if args.json:
        print(json.dumps({"findings": findings, "checked": len(cases)}, ensure_ascii=False))
    print()
    if inert:
        for f in inert:
            print(
                f"[Medium] {f['file']} — 回归测试不承重: 「{f['test']}」对着修复前的代码也是绿的 "
                f"| 让它先在 {args.base} 上失败,再合"
            )
        # Not every green-on-old test is a defect: a PR often adds a happy-path assertion
        # ALONGSIDE its guard test ("本来就是 X 的单照样通过"), and that one is supposed to pass
        # before and after. Measured on CoLivingOS f5ef4e87..e973c46f: 10/12 correctly
        # load-bearing, 2 flagged, and both flagged ones were companion assertions. So this is a
        # finding to JUDGE, not to auto-block — the reviewer decides which kind each one is.
        print(
            "\n⚠️  判断题,不是自动结论:如果这条是为某个 fix 配的**回归测试**,它挡不住回归,该改;"
            "\n   如果它只是给既有行为补的一条断言(happy-path 陪跑),本来就该前后都绿,忽略即可。"
        )
        return 2
    print(f"✅ all {len(cases)} new test(s) are load-bearing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
