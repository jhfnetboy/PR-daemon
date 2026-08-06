#!/usr/bin/env python3
"""Test `start_loop_scope.py targets/list --only` — narrowing a patrol to named repos.

    python3 tests/test_scope_only.py

Offline: `resolve` (which shells out to `gh repo list`) and `compute_scope` (which shells out
to `poll_prs.py`) are both stubbed, so this pins the narrowing LOGIC without touching GitHub.

What it pins down:
  1. --only narrows the printed target list, and nothing else leaks through
  2. bare short names resolve the same way `pins add` resolves them
  3. a named repo with nothing pending is reported as idle, not as an error
  4. no --only  ==  unchanged behaviour (the regression that matters most)
  5. `list --only` VISIBLY says the patrol is narrowed — the whole point of routing
     narrowing through this command instead of hand-writing repos into a cron prompt
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import start_loop_scope as sls  # noqa: E402

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


def check(msg: str, got, want) -> None:
    ok(msg) if got == want else bad(f"{msg} (want {want!r}, got {got!r})")


def want_true(msg: str, cond: bool, detail: str = "") -> None:
    """`cond and ok(...) or bad(...)` is a TRAP: ok() returns None, so `or bad(...)` always
    fires and every assertion reports both pass and fail. Caught by this file's own first run."""
    if cond:
        ok(msg)
    else:
        bad(f"{msg}{' — ' + detail if detail else ''}")


# ── stubs ───────────────────────────────────────────────────────────────────
ALL_TARGETS = [
    "jhfnetboy/CoLivingOS",
    "jhfnetboy/CMIC",
    "AAStarCommunity/Brood",
    "AAStarCommunity/AirAccount",
]
PENDING = {
    "jhfnetboy/CoLivingOS": [74, 75],
    "jhfnetboy/CMIC": [161],
    "AAStarCommunity/Brood": [44],
    "AAStarCommunity/AirAccount": [191],
}
SHORT = {
    "coliving": "jhfnetboy/CoLivingOS",
    "colivingos": "jhfnetboy/CoLivingOS",
    "cmic": "jhfnetboy/CMIC",
    "brood": "AAStarCommunity/Brood",
    "kms": "AAStarCommunity/AirAccount",
}


def fake_resolve(token: str) -> str:
    if "/" in token:
        return token
    hit = SHORT.get(token.lower())
    if not hit:
        sys.exit(f"error: no repo matching {token!r}")
    return hit


def fake_scope(targets=None, pins=None, limit=8):
    """Mirror the real compute_scope, INCLUDING the top-N cap.

    The first version of this stub set `scope.targets = ordered` and ignored `limit`, so no
    assertion could ever exercise --only against the cap — which is exactly where the real bug
    was (a named repo with pending PRs that lost the top-N recency race was dropped and then
    reported as 无待审). A stub that cannot express the bug cannot catch it.
    """
    ordered = ALL_TARGETS if targets is None else list(targets)
    scope = types.SimpleNamespace()
    scope.pins = pins if pins is not None else ["jhfnetboy/CoLivingOS", "jhfnetboy/CMIC"]
    scope.ordered = ordered
    scope.pinned_hits = [r for r in ordered if r in scope.pins]
    rest = [r for r in ordered if r not in scope.pins]
    scope.default_hits = rest if limit <= 0 else rest[:limit]
    scope.targets = scope.pinned_hits + scope.default_hits
    scope.prs = lambda repo: PENDING.get(repo, [])
    return scope


def run(fn, *args, targets=None, pins=None, **kw):
    """Call a cmd_* function with stubs in place; return (stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    orig_resolve, orig_compute = sls.resolve, sls.compute_scope
    sls.resolve = fake_resolve
    # `limit` reaches the stub the same way it reaches the real compute_scope: positionally.
    sls.compute_scope = lambda lim, *a, **k: fake_scope(targets, pins, limit=lim)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fn(*args, **kw)
    finally:
        sls.resolve, sls.compute_scope = orig_resolve, orig_compute
    return out.getvalue(), err.getvalue()


# ── 1. narrowing ────────────────────────────────────────────────────────────
print("[1] --only narrows the target list")
stdout, stderr = run(sls.cmd_targets, 8, False, "coliving,cmic")
lines = [l for l in stdout.splitlines() if l.strip()]
check("only the two named repos are emitted", lines, ["jhfnetboy/CoLivingOS", "jhfnetboy/CMIC"])
want_true("no other repo leaks into stdout", "Brood" not in stdout and "AirAccount" not in stdout)
want_true("narrowing is announced on stderr", "ONLY: narrowed to" in stderr, stderr.strip())

# ── 2. bare names + full OWNER/REPO both work ───────────────────────────────
print("[2] name resolution matches `pins add`")
stdout, _ = run(sls.cmd_targets, 8, False, "jhfnetboy/CMIC")
check("full OWNER/REPO accepted", [l for l in stdout.splitlines() if l.strip()], ["jhfnetboy/CMIC"])
stdout, _ = run(sls.cmd_targets, 8, False, " kms , brood ")
check(
    "bare names + whitespace tolerated",
    sorted(l for l in stdout.splitlines() if l.strip()),
    ["AAStarCommunity/AirAccount", "AAStarCommunity/Brood"],
)

# ── 3. named-but-idle repo is not an error ──────────────────────────────────
print("[3] a named repo with nothing pending is idle, not an error")
stdout, stderr = run(sls.cmd_targets, 8, False, "coliving,cmic", targets=["jhfnetboy/CMIC"])
check("idle repo produces no target line", [l for l in stdout.splitlines() if l.strip()],
      ["jhfnetboy/CMIC"])
want_true("idle repo named on stderr", "无待审" in stderr, stderr.strip())
stdout, stderr = run(sls.cmd_targets, 8, False, "coliving", targets=[])
check("all-idle -> empty stdout (a valid answer)", stdout.strip(), "")

# ── 4. no --only is unchanged ───────────────────────────────────────────────
print("[4] no --only == unchanged behaviour")
stdout, stderr = run(sls.cmd_targets, 8, False, "")
check("every target still printed", [l for l in stdout.splitlines() if l.strip()], ALL_TARGETS)
want_true("no ONLY line when not narrowing", "ONLY:" not in stderr, stderr.strip())

# ── 5. `list --only` makes the narrowing visible ────────────────────────────
print("[5] `$pr list --only` shows the patrol is narrowed")
stdout, _ = run(sls.cmd_list, 8, False, "coliving")
want_true("list warns that the patrol is narrowed", "--only 收窄" in stdout,
          "this is the whole point of the flag")
want_true("names the surviving repo", "colivingos" in stdout)

# ── 6. resolve_only rejects an empty list rather than scanning everything ───
print("[6] empty --only is an error, not 'scan everything'")
try:
    run(sls.cmd_targets, 8, False, " , ")
    bad("empty --only silently fell through")
except SystemExit as e:
    want_true("empty --only exits with a clear message", "empty" in str(e), str(e))

# ── 7. THE BUG THIS PR SHIPPED FIRST: --only must not intersect with the top-N cap ──
print("[7] a named repo outside the top-N window is still scanned")
# 3 repos with pending PRs, limit=2, and the wanted one is LAST by recency and NOT pinned —
# so it is absent from `targets` but present in `ordered`. Filtering `targets` drops it and
# then lies about why, and the patrol self-stops while that repo has PRs waiting.
stdout, stderr = run(sls.cmd_targets, 2, False, "kms", pins=[],
                     targets=["jhfnetboy/CoLivingOS", "jhfnetboy/CMIC",
                              "AAStarCommunity/Brood", "AAStarCommunity/AirAccount"])
check("the out-of-window repo is still emitted",
      [l for l in stdout.splitlines() if l.strip()], ["AAStarCommunity/AirAccount"])
want_true("and is NOT falsely reported as 无待审", "无待审" not in stderr, stderr.strip())

print("[8] the narrowed summary counts match the narrowed list")
stdout, stderr = run(sls.cmd_targets, 8, False, "coliving,cmic")
want_true("targets summary reflects --only, not the un-narrowed scope",
          "2 selected by --only" in stderr, stderr.strip())
stdout, _ = run(sls.cmd_list, 2, False, "kms", pins=[],
                targets=["jhfnetboy/CoLivingOS", "jhfnetboy/CMIC",
                         "AAStarCommunity/Brood", "AAStarCommunity/AirAccount"])
want_true("list counts the narrowed repo as scanned", "本轮实扫 1 个仓库" in stdout, stdout)
want_true("list drops the meaningless 「没进前 N」 clause under --only",
          "没进前" not in stdout, stdout)

print(f"\npassed: {PASS}   failed: {FAIL}")
sys.exit(1 if FAIL else 0)
