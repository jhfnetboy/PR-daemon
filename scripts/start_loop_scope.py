#!/usr/bin/env python3
"""Scope helper for the ``$start`` patrol skill.

The ``$start`` skill only decides *when* and *for which repos* ``pr-daemon-loop``
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

ORGS = ["AAStarCommunity", "iDoris-ai", "MushroomDAO"]
# Extra owners searched when resolving a bare repo name like "kms".
RESOLVE_OWNERS = ORGS + ["jhfnetboy"]

DEFAULT_LIMIT = 8


def state_dir() -> pathlib.Path:
    env = os.environ.get("PR_DAEMON_STATE_DIR")
    return pathlib.Path(env) if env else REPO_ROOT / ".state" / "pr-daemon"


def pins_path() -> pathlib.Path:
    return state_dir() / "start-loop-pinned.json"


def load_pins() -> list[str]:
    path = pins_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warn: unreadable {path}: {exc}", file=sys.stderr)
        return []
    repos = data.get("repos") if isinstance(data, dict) else data
    if not isinstance(repos, list):
        return []
    return [r for r in repos if isinstance(r, str) and "/" in r]


def save_pins(repos: list[str]) -> None:
    path = pins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"repos": sorted(set(repos))}, indent=2) + "\n")


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


# Standing, user-approved exceptions to pr-daemon-loop's "3 orgs only" rule.
# Included in scope `all`; clestons already holds collaborator access on both.
ALL_SCOPE_EXTRA = ["jhfnetboy/NextStop", "jhfnetboy/AISalesMan"]


def cmd_targets(limit: int, scope_all: bool) -> int:
    pins = load_pins()
    if scope_all:
        pins = sorted(set(pins) | set(ALL_SCOPE_EXTRA))
        limit = 0  # no cap — scope `all` scans every repo with pending PRs

    try:
        queue = poll(["--sync", "--max", "200"])
    except Exception as exc:  # noqa: BLE001 - any failure here must not be fatal
        print(f"warn: org-wide sync failed: {exc}", file=sys.stderr)
        queue = []

    # Pinned repos outside the three orgs need their own scoped sync — the
    # org-wide pass above never sees them. Failures are isolated per repo so one
    # dead/renamed pin cannot sink the whole cycle.
    for repo in pins:
        if repo.split("/", 1)[0] in ORGS:
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

    print(
        "targets: %d pinned + %d recent (of %d repos with pending PRs)"
        % (len(pinned_hits), len(default_hits), len(ordered)),
        file=sys.stderr,
    )
    for repo in pinned_hits + default_hits:
        print(repo)
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

    args = parser.parse_args()

    if args.cmd == "targets":
        return cmd_targets(args.limit, args.scope_all)

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
