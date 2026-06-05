#!/usr/bin/env python3
"""List open PRs authored by the primary account for PR-Daemon."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


FIELDS = "number,title,repository,url,updatedAt,isDraft,author"


def run_gh(args: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["gh", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh command failed")
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"expected gh to return a JSON array, got {type(data).__name__}")
    return data


def rel_time(value: str) -> str:
    try:
        updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    seconds = int((datetime.now(timezone.utc) - updated).total_seconds())
    if seconds < 3600:
        return f"{max(seconds // 60, 0)}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def repo_name(pr: dict[str, Any]) -> str:
    repo = pr.get("repository") or {}
    return str(repo.get("nameWithOwner") or "")


def render_table(prs: list[dict[str, Any]]) -> str:
    rows = []
    for pr in prs:
        draft = " draft" if pr.get("isDraft") else ""
        rows.append(
            [
                repo_name(pr),
                f"#{pr.get('number')}{draft}",
                str(pr.get("title") or "").replace("\n", " ")[:80],
                rel_time(str(pr.get("updatedAt") or "")),
                str(pr.get("url") or ""),
            ]
        )

    headers = ["repo", "pr", "title", "updated", "url"]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    lines = ["  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="List open PRs authored by the primary account.")
    parser.add_argument("--author", default="jhfnetboy", help="GitHub login that authored the PRs")
    parser.add_argument("--repo", action="append", default=[], help="Limit to OWNER/REPO; may be repeated")
    parser.add_argument("--owner", action="append", default=[], help="Limit to owner/org; may be repeated")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--include-drafts", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    gh_args = [
        "search",
        "prs",
        "--author",
        args.author,
        "--state",
        "open",
        "--json",
        FIELDS,
        "--limit",
        str(args.limit),
        "--sort",
        "updated",
        "--order",
        "desc",
    ]
    for repo in args.repo:
        gh_args.extend(["--repo", repo])
    for owner in args.owner:
        gh_args.extend(["--owner", owner])

    prs = run_gh(gh_args)
    if not args.include_drafts:
        prs = [pr for pr in prs if not pr.get("isDraft")]

    if args.json:
        print(json.dumps(prs, ensure_ascii=False, indent=2))
    elif prs:
        print(render_table(prs))
    else:
        print(f"No open non-draft PRs found for author {args.author}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
