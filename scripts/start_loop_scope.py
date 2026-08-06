#!/usr/bin/env python3
"""Scope helper for the ``$start`` patrol skill.

The ``$start`` skill only decides *when* and *for which repos* ``pr``
runs. This script owns the "which repos" half so the cron prompt stays short and
the logic stays testable.

Subcommands
-----------
``pins list``                 print pinned repos, one ``OWNER/REPO`` per line
``pins add <name|owner/repo>``   resolve a bare name (e.g. ``kms``) and pin it
``pins remove <name|owner/repo>`` unpin
``targets [--limit N]``       sync, then print this cycle's target repos

``targets`` prints, one per line:

1. every **pinned** repo that currently has pending-review PRs (pins never
   consume one of the N default slots — an explicit pin always gets scanned), then
2. the N (default 8) **most recently updated** repos with pending-review PRs
   across the three orgs.

"Pending review" is whatever ``poll_prs.py`` puts in its queue — it re-derives
that from a direct head-oid comparison, so it is never fooled by a spurious
``status`` flip in the SQLite row.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
POLL = REPO_ROOT / "scripts" / "poll_prs.py"

import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import scan_scope  # single source of truth: ~/.config/prbot/repos.conf
ORGS = scan_scope.orgs()
# Extra owners searched when resolving a bare repo name like "kms".
RESOLVE_OWNERS = ORGS + ["jhfnetboy"]

DEFAULT_LIMIT = 8

GOUTOU_DEPS = pathlib.Path("~/Dev/jhfnetboy/goutou/.goutou-deps.json").expanduser()

# Short names jason actually says out loud ("review kms 192"). Keyed by the REPO
# NAME ONLY, lowercased — never by OWNER/REPO — so an org rename (AuraAIHQ ->
# iDoris-ai already happened) can't silently break the mapping.
NICKNAMES = {
    "airaccount": "kms",
    "airaccount-contract": "account",
    "aastar-sdk": "sdk",
    "superpaymaster": "sp",
    "yetanotheraa-validator": "dvt",
    "yetanotheraa": "yaaa",
    "self-fde-workbench": "workbench",
    "hack5-net": "hack5",
    "auraai-packages": "aura-pkg",
    "agent-speaker": "speaker",
}


def nickname_map() -> dict[str, str]:
    """repo-name (lowercase) -> short name. Builtins win over the goutou file."""
    out: dict[str, str] = {}
    if GOUTOU_DEPS.exists():
        try:
            deps = json.loads(GOUTOU_DEPS.read_text()).get("repos", {})
            for repo_id, meta in deps.items():
                gh = (meta or {}).get("github", "")
                if "/" in gh:
                    out[gh.split("/", 1)[1].lower()] = repo_id
        except (json.JSONDecodeError, OSError, AttributeError):
            pass  # stale/absent goutou file must never break the patrol
    out.update(NICKNAMES)
    return out


def nick(repo: str) -> str:
    """Short name for OWNER/REPO, falling back to the lowercased repo name."""
    name = repo.split("/", 1)[1] if "/" in repo else repo
    return nickname_map().get(name.lower(), name.lower())


def state_dir() -> pathlib.Path:
    env = os.environ.get("PR_DAEMON_STATE_DIR")
    return pathlib.Path(env) if env else REPO_ROOT / ".state" / "pr-daemon"


def pins_path() -> pathlib.Path:
    """The ONE place a pin is written: `~/.config/prbot/focus-manual.conf`.

    Until 2026-08-05 pins lived in `.state/pr-daemon/start-loop-pinned.json`, which
    only this script read, while `focus-manual.conf` fed `repos.conf` which only the
    (not-running) `review_watch.py` read. "Pin a repo" therefore meant two edits in
    two files, and a repo could be in one and not the other — it happened. One file
    now, and `refresh-scan-focus.sh` folds it into `repos.conf` for every consumer.
    """
    return scan_scope.CFG / "focus-manual.conf"


def _legacy_pins_path() -> pathlib.Path:
    return state_dir() / "start-loop-pinned.json"


def load_pins() -> list[str]:
    """Pins from focus-manual.conf, with a one-way migration off the old JSON."""
    path = pins_path()
    out: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "/" in line and line not in out:
                out.append(line)
    except OSError:
        pass

    # Migrate anything still stranded in the retired JSON, then leave it alone —
    # silently dropping a pin the user set is worse than a redundant file.
    legacy = _legacy_pins_path()
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text())
            old = data.get("repos") if isinstance(data, dict) else data
            stranded = [r for r in (old or []) if isinstance(r, str) and "/" in r and r not in out]
            if stranded:
                print(
                    f"note: migrating {len(stranded)} pin(s) from the retired "
                    f"{legacy.name} into {path}: {', '.join(stranded)}",
                    file=sys.stderr,
                )
                out.extend(stranded)
                save_pins(out)
        except (json.JSONDecodeError, OSError):
            pass
    return out


def save_pins(repos: list[str]) -> None:
    """Write focus-manual.conf, then regenerate repos.conf so the change takes effect.

    Writing the pin file alone is not enough: `repos.conf` is the generated artifact
    every consumer reads, so a pin that never triggers a refresh is invisible.
    """
    path = pins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(set(repos))) + "\n")
    refresh = REPO_ROOT / "scripts" / "refresh-scan-focus.sh"
    if refresh.exists():
        try:
            subprocess.run(["bash", str(refresh)], capture_output=True, timeout=180)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(
                f"warn: pin saved to {path}, but regenerating repos.conf failed ({exc}). "
                f"Run `bash {refresh}` before relying on the new scope.",
                file=sys.stderr,
            )


# --------------------------------------------------------------------------
# name resolution
# --------------------------------------------------------------------------


def gh_json(args: list[str]) -> object | None:
    """Run a gh command expected to emit JSON. Returns None on any failure."""
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=60, check=True
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def candidate_repos() -> list[str]:
    """Every repo we might resolve a bare name against."""
    found: list[str] = []
    for owner in RESOLVE_OWNERS:
        data = gh_json(
            ["repo", "list", owner, "--limit", "200", "--json", "nameWithOwner"]
        )
        if not isinstance(data, list):
            print(f"warn: could not list repos for {owner}", file=sys.stderr)
            continue
        found.extend(
            item["nameWithOwner"]
            for item in data
            if isinstance(item, dict) and item.get("nameWithOwner")
        )
    return found


def resolve(token: str) -> str:
    """Resolve ``kms`` / ``OWNER/REPO`` to a canonical ``OWNER/REPO``.

    Exits non-zero with the candidate list when the name is ambiguous or unknown,
    so the caller never silently pins the wrong repo.
    """
    token = token.strip().strip("/")
    if not token:
        sys.exit("error: empty repo name")

    if "/" in token:
        data = gh_json(["repo", "view", token, "--json", "nameWithOwner"])
        if isinstance(data, dict) and data.get("nameWithOwner"):
            return data["nameWithOwner"]
        sys.exit(f"error: no such repo (or no access): {token}")

    needle = token.lower()
    repos = candidate_repos()
    exact = [r for r in repos if r.split("/", 1)[1].lower() == needle]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        sys.exit(
            "error: ambiguous name %r, matches:\n  %s\nPin the full OWNER/REPO instead."
            % (token, "\n  ".join(exact))
        )

    partial = [r for r in repos if needle in r.split("/", 1)[1].lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        sys.exit(
            "error: ambiguous name %r, matches:\n  %s\nPin the full OWNER/REPO instead."
            % (token, "\n  ".join(partial))
        )
    sys.exit(
        f"error: no repo matching {token!r} under {', '.join(RESOLVE_OWNERS)}. "
        "Pin the full OWNER/REPO if it lives elsewhere."
    )


# --------------------------------------------------------------------------
# targets
# --------------------------------------------------------------------------


def poll(args: list[str]) -> list[dict]:
    """Run poll_prs.py and return its queue. Raises on failure."""
    out = subprocess.run(
        [sys.executable, str(POLL), *args],
        capture_output=True,
        text=True,
        timeout=600,
        check=True,
    ).stdout
    data = json.loads(out)
    if data.get("fetch_failed"):
        raise RuntimeError("poll_prs.py reported fetch_failed")
    queue = data.get("queue")
    return queue if isinstance(queue, list) else []


# Standing, user-approved exceptions to pr's "3 orgs only" rule.
# Included in scope `all`; clestons already holds collaborator access on both.
ALL_SCOPE_EXTRA = ["jhfnetboy/NextStop", "jhfnetboy/AISalesMan"]


class Scope:
    """一轮巡检算出来的范围。cmd_targets(机器可读) 和 cmd_list(给人看) 共用同一次计算,
    免得两个命令各扫一遍 GitHub 还可能给出不一致的答案。"""

    def __init__(self, pins, pinned_hits, default_hits, ordered, pending):
        self.pins = pins                    # 全部 pin(含当前没有待审 PR 的)
        self.pinned_hits = pinned_hits      # 有待审 PR 的 pin —— 不占默认名额
        self.default_hits = default_hits    # 最近更新的前 N 个(pin 之外)
        self.ordered = ordered              # 所有有待审 PR 的仓库,按最近更新排序
        self.pending = pending              # repo -> [pr_number, ...]

    @property
    def targets(self) -> list[str]:
        return self.pinned_hits + self.default_hits

    def prs(self, repo: str) -> list[int]:
        return sorted(n for n in self.pending.get(repo, []) if n is not None)


def compute_scope(limit: int, scope_all: bool) -> Scope:
    pins = load_pins()
    if scope_all:
        pins = sorted(set(pins) | set(ALL_SCOPE_EXTRA))
        limit = 0  # no cap — scope `all` scans every repo with pending PRs

    try:
        queue = poll(["--sync", "--max", "200"])
    except Exception as exc:  # noqa: BLE001 - any failure here must not be fatal
        print(f"warn: org-wide sync failed: {exc}", file=sys.stderr)
        queue = []

    # Pins the org-wide pass genuinely cannot see need their own scoped sync.
    # Since the scope consolidation the org sweep already adds a `repo:` term for
    # every listed repo outside the swept orgs (scan_scope.extra_repos()), so a
    # second poll here would return the SAME PRs again — observed as
    # `nextstop #26,26,27,27`. Only poll a pin that is in neither set.
    already_swept = set(scan_scope.extra_repos())
    for repo in pins:
        if repo.split("/", 1)[0] in ORGS or repo in already_swept:
            continue
        try:
            queue.extend(poll(["--repo", repo, "--sync", "--max", "50"]))
        except Exception as exc:  # noqa: BLE001
            print(f"warn: sync failed for pinned {repo}: {exc}", file=sys.stderr)

    pin_set = set(pins)
    ordered: list[str] = []
    for item in sorted(queue, key=lambda p: p.get("updated_at") or "", reverse=True):
        repo = item.get("repo")
        if repo and repo not in ordered:
            ordered.append(repo)

    pinned_hits = [r for r in ordered if r in pin_set]
    rest = [r for r in ordered if r not in pin_set]
    default_hits = rest if limit <= 0 else rest[:limit]

    # Per-repo pending PR numbers, so the scope line can name what it will look at.
    pending: dict[str, list] = {}
    for item in queue:
        pending.setdefault(item.get("repo"), []).append(item.get("pr_number"))

    return Scope(pins, pinned_hits, default_hits, ordered, pending)


def resolve_only(only: str) -> list[str]:
    """Resolve a comma-separated --only list to canonical OWNER/REPO, same rules as `pins add`.

    Added 2026-08-06. Before this, narrowing a patrol to one repo meant hand-writing the repo name
    into the cron prompt — which is exactly the "second source of scope" the ONE-list consolidation
    exists to prevent: `$pr list` could not see it, and nothing kept it in sync with repos.conf.
    Narrowing now goes through this one command like everything else.
    """
    names = [n.strip() for n in only.split(",") if n.strip()]
    if not names:
        sys.exit("error: --only given but empty")
    return [resolve(n) for n in names]


def cmd_targets(limit: int, scope_all: bool, only: str = "") -> int:
    # Resolve BEFORE compute_scope: that call runs `poll_prs.py --sync --max 200` (up to 600s, and
    # --sync WRITES the queue DB) plus a scoped sync per out-of-org pin. A typo'd --only name used
    # to burn all of that before exiting.
    wanted = resolve_only(only) if only else []

    scope = compute_scope(limit, scope_all)
    pin_set = set(scope.pins)
    targets = scope.targets

    if only:
        # Filter `ordered` (every repo with pending PRs), NOT `targets` (already capped at the
        # top-N recency window). Filtering `targets` silently dropped a named repo that has
        # pending PRs but lost the top-8 race — and then printed "无待审" about it, which is a
        # lie the patrol acts on: it would scan nothing and self-stop after an idle hour while
        # that repo had PRs waiting. Masked whenever the repo happened to be pinned (pins bypass
        # the cap), so it failed intermittently. --only IS the cap; the limit has no job left.
        kept = [r for r in scope.ordered if r in wanted]
        idle = [r for r in wanted if r not in kept]
        print(
            "ONLY: narrowed to %s%s"
            % (
                ", ".join(nick(r) for r in wanted),
                "  (无待审: %s)" % ", ".join(nick(r) for r in idle) if idle else "",
            ),
            file=sys.stderr,
        )
        targets = kept

    # SCOPE line: what this cycle will actually watch, in the short names jason
    # uses. Printed to stderr so stdout stays a clean machine-readable target list.
    parts = []
    for repo in targets:
        nums = scope.prs(repo)
        pin_mark = "📌" if repo in pin_set else ""
        parts.append(f"{pin_mark}{nick(repo)}#{','.join(str(n) for n in nums)}")
    print("SCOPE: " + ("  ".join(parts) if parts else "(无待审 PR)"), file=sys.stderr)
    if only:
        # Derive the summary from the NARROWED list. The un-narrowed counts sat two lines above an
        # empty target list and contradicted the SCOPE line right above them.
        print(
            "targets: %d selected by --only (of %d repos with pending PRs)"
            % (len(targets), len(scope.ordered)),
            file=sys.stderr,
        )
    else:
        print(
            "targets: %d pinned + %d recent (of %d repos with pending PRs)"
            % (len(scope.pinned_hits), len(scope.default_hits), len(scope.ordered)),
            file=sys.stderr,
        )
    for repo in targets:
        print(repo)
    return 0


def cmd_list(limit: int, scope_all: bool, only: str = "") -> int:
    """`$pr list` —— 给人看的扫描范围:默认 N 个是哪些、额外 pin 进来的是哪些。

    和 targets 走同一个 compute_scope,所以这里显示什么,下一轮就真扫什么。
    """
    # Resolve before the sync, for the same reason as cmd_targets: compute_scope is a long,
    # DB-writing network sweep and a typo'd name should fail in a second, not after it.
    only_set = set(resolve_only(only)) if only else set()
    scope = compute_scope(limit, scope_all)

    def line(repo: str) -> str:
        nums = scope.prs(repo)
        prs = "#" + ",".join(str(n) for n in nums) if nums else "(无待审)"
        return f"  {nick(repo):<12} {prs:<16} {repo}"

    cap = "不限(scope=all)" if limit <= 0 else str(limit)
    print(f"默认扫描位({cap} 个,按最近更新排,只算有待审 PR 的仓库):")
    print("\n".join(line(r) for r in scope.default_hits) if scope.default_hits
          else "  (当前没有仓库有待审 PR)")

    print(f"\n额外 pin 进来的仓库({len(scope.pins)} 个,不占上面的名额):")
    if not scope.pins:
        print("  (无) —— 用 `$pr add kms` 添加")
    else:
        for repo in scope.pins:
            # pin 了但当前没待审 PR 的也要列出来:用户问的是"额外增加的是哪几个",
            # 只显示有 PR 的那些会让人以为 pin 掉了。
            mark = "📌" if repo in scope.pinned_hits else "📌(本轮无待审)"
            nums = scope.prs(repo)
            prs = "#" + ",".join(str(n) for n in nums) if nums else ""
            print(f"  {mark} {nick(repo):<12} {prs:<16} {repo}")

    if only_set:
        # Narrowing must be VISIBLE when you ask for it. NOTE what this does NOT do: --only is not
        # persisted anywhere, so a bare `$pr list` cannot know a running patrol is narrowed — this
        # warning only appears when you re-type --only yourself. Making bare `list` tell the truth
        # needs `$pr start` to record the active narrowing; until then this is a smaller claim than
        # "list can no longer disagree with the patrol".
        print(
            "\n⚠️  本轮巡检被 --only 收窄到: "
            + ", ".join(sorted(nick(r) for r in only_set))
            + "\n   (上面列出的其余仓库本轮不扫;去掉 --only 即恢复完整范围)"
        )
        # Under --only, `ordered` (all repos with pending PRs) is the right denominator and the
        # top-N cap is irrelevant, so the "没进前 N" clause would be meaningless here.
        scanned = [r for r in scope.ordered if r in only_set]
        print(f"\n本轮实扫 {len(scanned)} 个仓库(--only 收窄自 {len(scope.ordered)} 个有待审 PR 的仓库)")
        return 0

    dropped = len(scope.ordered) - len(scope.pinned_hits) - len(scope.default_hits)
    print(f"\n本轮实扫 {len(scope.targets)} 个仓库"
          + (f";另有 {dropped} 个有待审 PR 但没进前 {limit}(下轮它们更新了就会顶上来)"
             if dropped > 0 else ""))
    return 0


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pins = sub.add_parser("pins", help="manage the pinned-repo list")
    p_pins.add_argument("action", choices=["list", "add", "remove"])
    p_pins.add_argument("name", nargs="?", help="bare name (e.g. kms) or OWNER/REPO")

    p_targets = sub.add_parser("targets", help="print this cycle's target repos")
    p_targets.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="0 = no cap"
    )
    p_targets.add_argument(
        "--all",
        action="store_true",
        dest="scope_all",
        help="scope `all`: no cap, plus jhfnetboy/NextStop and jhfnetboy/AISalesMan",
    )
    p_targets.add_argument(
        "--only",
        default="",
        help="narrow this cycle to these repos only, comma-separated "
             "(bare names or OWNER/REPO, e.g. --only coliving,cmic). "
             "Use this instead of hand-writing repo names into a cron prompt.",
    )

    p_list = sub.add_parser("list", help="human-readable scan scope (default slots + pinned extras)")
    p_list.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="0 = no cap")
    p_list.add_argument("--all", action="store_true", dest="scope_all", help="scope `all`")
    p_list.add_argument("--only", default="", help="show the scope as narrowed by --only")

    p_nick = sub.add_parser("nick", help="print the short name for OWNER/REPO")
    p_nick.add_argument("repo")

    args = parser.parse_args()

    if args.cmd == "nick":
        print(nick(args.repo))
        return 0

    if args.cmd == "targets":
        return cmd_targets(args.limit, args.scope_all, args.only)

    if args.cmd == "list":
        return cmd_list(args.limit, args.scope_all, args.only)

    pins = load_pins()
    if args.action == "list":
        for repo in pins:
            print(repo)
        return 0

    if not args.name:
        sys.exit(f"error: `pins {args.action}` needs a repo name")

    if args.action == "add":
        repo = resolve(args.name)
        if repo in pins:
            print(f"already pinned: {repo}")
            return 0
        save_pins(pins + [repo])
        print(f"pinned: {repo}")
        return 0

    # remove — accept a bare name too, matched against what is already pinned
    needle = args.name.strip().strip("/").lower()
    matches = [
        r
        for r in pins
        if r.lower() == needle or r.split("/", 1)[1].lower() == needle
    ]
    if not matches:
        sys.exit(f"error: {args.name!r} is not pinned (pinned: {', '.join(pins) or 'none'})")
    if len(matches) > 1:
        sys.exit("error: ambiguous, matches:\n  " + "\n  ".join(matches))
    save_pins([r for r in pins if r != matches[0]])
    print(f"unpinned: {matches[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
