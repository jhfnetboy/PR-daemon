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

    # other runners: {file} and {name} are substituted, and selection is judged by exit code
    ... --test-cmd 'npx jest {file} -t {name}'

## Scope: JS/TS only

Test discovery only understands JS/TS `it(...)` / `test(...)` declarations. A Rust `#[test] fn`,
a pytest `def test_x`, or a Go `func TestX` yields NO cases — and reporting "all clear" for a
language it cannot read would be a lie, so a repo whose changed test files are not JS/TS exits 1.

Exit codes: 0 = every added test is load-bearing (or genuinely nothing to check)
            2 = at least one added test passes without the fix  ← the finding
            1 = could not run the check — unsupported language, a test red at PR head, or a
                name that did not select exactly one test. NEVER a silent all-clear.
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
# Matches simple modifiers (it.only, it.skip). NOT matched, deliberately: `it.each([...])("…")`,
# whose name follows a second call, and whose `%i`/`%s` placeholders are resolved at runtime — a
# pattern built from the literal could never match. Template literals containing `${…}` are
# captured but then rejected below for the same reason.
ADDED_TEST_RE = re.compile(
    r"""^\+\s*(?:it|test)(?:\.\w+)*\s*\(\s*(['"`])(?P<name>(?:(?!\1).)+)\1""",
    re.MULTILINE,
)

# Bare substring matching ("test" in path) misclassified `src/latest.sh`, `src/inspector.ts`,
# `attest`, `contest`, `spectrum`… as test files — and a misclassified SOURCE file never gets
# reverted, which turns a load-bearing test into a false "not load-bearing" finding. Anchor on
# real conventions instead.
TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|e2e|cypress)/"
    r"|\.(?:test|spec|cy|e2e)\.[jt]sx?$"
    r"|_test\.[a-z]+$",
    re.IGNORECASE,
)
JS_TEST_FILE_RE = re.compile(r"\.[cm]?[jt]sx?$", re.IGNORECASE)
# Files whose reversion cannot change behaviour — reverting them adds noise, not signal.
NON_SOURCE_SUFFIXES = (".md", ".txt", ".json", ".lock", ".yaml", ".yml", ".toml", ".snap")


def sh(args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def git_bytes(cwd: Path, *args: str) -> bytes | None:
    """Raw bytes of a git object. `text=True` decoding blew up with UnicodeDecodeError on any
    binary file in the diff (a .png is not in NON_SOURCE_SUFFIXES, so it is treated as source to
    revert) and killed the whole run mid-way."""
    out = subprocess.run(["git", "-c", "core.quotePath=false", *args],
                         cwd=str(cwd), capture_output=True)
    return out.stdout if out.returncode == 0 else None


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
    return bool(TEST_PATH_RE.search(path))


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
    # Anchor on the QUOTED literal, not on "the line contains the name". A new test whose name is
    # a substring of an older one ("computes total" vs "computes total with discount") used to pick
    # up the older test's body, match it against base, and get silently skipped as a rename —
    # a false negative.
    quoted = [f'"{name}"', f"'{name}'", f"`{name}`"]
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(q in line for q in quoted) and re.search(r"\b(it|test)(\.\w+)*\s*\(", line):
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
            if "${" in name:
                # Resolved at runtime; any pattern we build from the literal matches nothing, and
                # "matches nothing" is indistinguishable from "the test is broken".
                print(f"skip (runtime-interpolated name): {f} :: {name}")
                continue
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


def run_one(cmd_tpl: str, wt: Path, file: str, name: str, json_out: bool) -> tuple[bool, int, str]:
    """-> (passed, tests_actually_run, detail).

    `-t` is a REGEX matched against the full test name, and EVERY match runs. Three ways that
    silently produced a wrong verdict before this was fixed:

      * a name that is a PREFIX of a sibling ("discount stays non-negative" vs "… with
        remainder") also selects the sibling; the sibling fails after the revert, so the inert
        test under examination is cleared as load-bearing — a false NEGATIVE, i.e. exactly the
        bug this tool exists to catch, silently missed;
      * metacharacters in a real name (`clamp(5) 返回 3`, `a|b`, `.`) compile to a pattern that
        matches NOTHING, which jest reports as success -> false accusation, vitest as failure ->
        "the test itself is broken";
      * `it("say \"hi\"")` produced a trailing backslash -> invalid regex, crash.

    So: escape the name, anchor it, and — for runners that can tell us — REQUIRE that exactly one
    test ran. A selection of 0 or >1 is not a verdict, it is a failed measurement.
    """
    # Escape+anchor ONLY for the runner we auto-detected and therefore know treats -t as a regex.
    # A custom --test-cmd owns its own matching semantics (`cargo test foo` is a substring, not a
    # pattern), so handing it `^foo$` would break it — the caller supplied the command and the
    # name-matching contract with it.
    # ESCAPE but do NOT anchor: `-t` matches the FULL name, which vitest/jest build by joining the
    # enclosing describe() blocks ("outer > inner > the name"), so `^name$` selects nothing at all.
    # Escaping alone kills the metacharacter and invalid-regex failures; the PREFIX-collision
    # problem is then solved downstream instead — the verdict is read from the JSON entry whose
    # title equals this name exactly, so a sibling that also matched cannot influence it.
    selector = re.escape(name) if json_out else name
    cmd = cmd_tpl.replace("{file}", shlex.quote(file)).replace("{name}", shlex.quote(selector))

    if not json_out:
        # Custom --test-cmd: we cannot count selections, so exit code is all we have.
        out = sh(["bash", "-lc", cmd], wt)
        return out.returncode == 0, -1, ""

    report = wt / ".verify-regr-report.json"
    report.unlink(missing_ok=True)
    cmd += f" --reporter=json --outputFile={shlex.quote(str(report))}"
    out = sh(["bash", "-lc", cmd], wt)
    if not report.exists():
        return out.returncode == 0, -1, "runner produced no JSON report"
    try:
        blob = json.loads(report.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return out.returncode == 0, -1, f"unparsable JSON report: {e}"

    results = [
        a for tr in blob.get("testResults", []) for a in tr.get("assertionResults", [])
        if a.get("status") not in ("skipped", "pending", "todo")
    ]
    # Judge ONLY the entry whose own title is this test. Other tests the regex happened to select
    # ran too, and their pass/fail is deliberately ignored — reading the command's exit code
    # instead is exactly how a failing prefix-sibling used to clear an inert test.
    matched = [a for a in results if (a.get("title") or "").strip() == name]
    if len(matched) != 1:
        return False, len(matched), (
            f"{len(results)} test(s) ran, {len(matched)} whose title is exactly this name"
        )
    return matched[0].get("status") == "passed", 1, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-path", required=True, help="local checkout of the repo under review")
    ap.add_argument("--base", required=True, help="commit BEFORE the fix (e.g. the PR's parent)")
    ap.add_argument("--head", required=True, help="PR head")
    ap.add_argument("--test-cmd", default="", help="template with {file} and {name}")
    ap.add_argument("--no-link-node-modules", dest="link_node_modules", action="store_false",
                    default=True,
                    help="do NOT symlink the real repo's node_modules into the worktree. The "
                         "symlink is a live write handle into the real checkout (vitest's default "
                         "cacheDir is node_modules/.vite), so turn it off if the user may be "
                         "running tests there concurrently.")
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

    non_js = [t for t in tests if not JS_TEST_FILE_RE.search(t)]
    if non_js and not args.test_cmd:
        # Discovery only reads JS/TS `it(`/`test(`. Reporting "all clear" for Rust/pytest/Go would
        # be an all-clear for a language this tool cannot read.
        print(f"❌ 不支持的测试语言: {', '.join(non_js)}")
        print("   本工具只认 JS/TS 的 it(...)/test(...) 声明。用 --test-cmd 显式指定运行器,"
              "或者别把它的沉默当成通过。")
        return 1

    cases = added_tests(repo, args.base, args.head, tests)
    if not cases:
        print(f"skip: {len(tests)} test file(s) changed but no NEW test declaration was added")
        return 0

    cmd_tpl = args.test_cmd or default_test_cmd(repo)
    # Only our own auto-detected vitest/jest command is known to accept the JSON reporter flags.
    json_out = not args.test_cmd and ("vitest" in cmd_tpl or "jest" in cmd_tpl)
    wt = Path(tempfile.mkdtemp(prefix="verify-regr-"))
    shutil.rmtree(wt, ignore_errors=True)   # git worktree add wants a non-existent path
    findings: list[dict] = []
    try:
        # A previous run killed with SIGKILL leaves a bogus admin entry in the REAL repo's
        # .git/worktrees forever, since `finally` never ran.
        git(repo, "worktree", "prune", check=False)
        git(repo, "worktree", "add", "--detach", str(wt), args.head)
        if args.link_node_modules and (repo / "node_modules").exists() \
                and not (wt / "node_modules").exists():
            (wt / "node_modules").symlink_to(repo / "node_modules")

        print(f"runner: {cmd_tpl}")
        if not json_out:
            # Without a JSON report we cannot count how many tests a name selected, and `-t`-style
            # selectors are regexes: a name that is a PREFIX of a sibling silently drags the
            # sibling in, and the sibling's post-revert failure then clears the inert test under
            # examination. Say so rather than presenting an unqualified verdict.
            print("⚠️  自定义 --test-cmd:无法确认「这个名字只选中了这一条测试」。"
                  "名字是另一条的前缀时,结论可能被兄弟测试掩盖 —— 结果按「未确认选择」看待。")
        print(f"source files to revert: {', '.join(src)}")
        print(f"new tests to check: {len(cases)}\n")

        for file, name in cases:
            print(f"· {file} :: {name}")
            ok_head, ran, detail = run_one(cmd_tpl, wt, file, name, json_out)
            if ran == 0 or (json_out and ran > 1):
                # Not a verdict — a failed measurement. Guessing here is how the prefix-collision
                # false negative happened.
                print(f"    ⚠️  selected {ran} tests, expected exactly 1 — cannot judge this case")
                findings.append({"file": file, "test": name, "status": "bad_selection",
                                 "selected": ran, "detail": detail})
                continue
            if not ok_head:
                # Red at head is a different (and louder) problem; do not call it "not load-bearing".
                print("    ⚠️  FAILS at PR head — the test itself is broken, skipping")
                findings.append({"file": file, "test": name, "status": "fails_at_head"})
                continue

            for s in src:
                exists_at_base = sh(
                    ["git", "-c", "core.quotePath=false", "cat-file", "-e", f"{args.base}:{s}"], repo
                ).returncode == 0
                if exists_at_base:
                    blob = git_bytes(repo, "show", f"{args.base}:{s}")
                    if blob is None:
                        print(f"    ⚠️  could not read {s} at base — aborting")
                        return 1
                    (wt / s).parent.mkdir(parents=True, exist_ok=True)
                    (wt / s).write_bytes(blob)
                    # Preserve the executable bit; a re-created file otherwise loses it.
                    mode = git(repo, "ls-tree", args.base, "--", s, check=False).split()
                    if mode and mode[0].endswith("755"):
                        (wt / s).chmod(0o755)
                elif (wt / s).exists():
                    # The PR ADDED this file. At base it did not exist, so the faithful revert is
                    # deletion — leaving it in place would let the new test import the very code
                    # the revert is meant to remove, and every test would look load-bearing.
                    (wt / s).unlink()
            still_green, _, _ = run_one(cmd_tpl, wt, file, name, json_out)
            # `checkout -- .` restores tracked files but CANNOT remove an untracked one — and
            # reverting a file the PR DELETED creates exactly that. Without the clean, every case
            # after the first ran against a tree that was not PR head.
            git(wt, "checkout", "--", ".")
            git(wt, "clean", "-fdq", check=False)

            if still_green:
                print("    ❌ PASSES without the fix — NOT load-bearing")
                findings.append({"file": file, "test": name, "status": "not_load_bearing"})
            else:
                print("    ✅ fails without the fix — load-bearing")
    finally:
        sh(["git", "worktree", "remove", "--force", str(wt)], repo)

    inert = [f for f in findings if f["status"] == "not_load_bearing"]
    unverified = [f for f in findings if f["status"] in ("fails_at_head", "bad_selection")]
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
    if unverified:
        # An all-clear here would be a lie: these cases were never measured. The caller reads the
        # exit code and the last line, so both must say "could not check", not "clean".
        for f in unverified:
            print(f"⚠️  未验证 {f['file']} :: {f['test']} — {f['status']}")
        print(f"\n❌ {len(unverified)}/{len(cases)} 条无法验证 —— 不是 all-clear。先修好它们再看结论。")
        return 1
    print(f"✅ all {len(cases)} new test(s) are load-bearing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
