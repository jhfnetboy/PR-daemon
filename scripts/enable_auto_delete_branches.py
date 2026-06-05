#!/usr/bin/env python3
"""Enable GitHub's delete_branch_on_merge setting for tracked repositories."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_PRBOT_CONFIG = Path.home() / ".config" / "prbot" / "repos.conf"


def run_gh_json(args: list[str]) -> object:
    last_error = ""
    for attempt in range(1, 4):
        result = subprocess.run(
            ["gh", *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "null")
        last_error = result.stderr.strip() or "gh command failed"
        if attempt < 3:
            time.sleep(attempt)
    raise RuntimeError(last_error)


def run_gh(args: list[str]) -> str:
    last_error = ""
    for attempt in range(1, 4):
        result = subprocess.run(
            ["gh", *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        last_error = result.stderr.strip() or "gh command failed"
        if attempt < 3:
            time.sleep(attempt)
    raise RuntimeError(last_error)


def read_scopes(path: Path) -> list[str]:
    scopes: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        scopes.append(value)
    return scopes


def repos_for_scope(scope: str) -> list[str]:
    if "/" in scope:
        return [scope]

    repos: list[str] = []
    page = 1
    while True:
        data = run_gh_json(
            [
                "api",
                "--method",
                "GET",
                f"orgs/{scope}/repos",
                "-f",
                "type=all",
                "-f",
                "per_page=100",
                "-f",
                f"page={page}",
            ]
        )
        if not isinstance(data, list):
            raise RuntimeError(f"unexpected repos response for {scope}: {data!r}")
        if not data:
            break
        for repo in data:
            full_name = repo.get("full_name")
            if isinstance(full_name, str):
                repos.append(full_name)
        if len(data) < 100:
            break
        page += 1
    return repos


def unique_repos(scopes: list[str]) -> list[str]:
    seen: set[str] = set()
    repos: list[str] = []
    for scope in scopes:
        for repo in repos_for_scope(scope):
            if repo not in seen:
                repos.append(repo)
                seen.add(repo)
    return repos


def repo_state(repo: str) -> tuple[bool, bool]:
    data = run_gh_json(["api", f"repos/{repo}"])
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected repo response for {repo}: {data!r}")
    permissions = data.get("permissions") or {}
    admin = bool(permissions.get("admin"))
    enabled = bool(data.get("delete_branch_on_merge"))
    return admin, enabled


def enable(repo: str) -> None:
    run_gh(["api", "--method", "PATCH", f"repos/{repo}", "-f", "delete_branch_on_merge=true"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable delete_branch_on_merge for repositories.")
    parser.add_argument("--config", default=str(DEFAULT_PRBOT_CONFIG), help="prbot repos.conf path")
    parser.add_argument("--scope", action="append", default=[], help="Org or owner/repo scope; repeatable")
    parser.add_argument("--repo", action="append", default=[], help="Specific owner/repo; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="Only report, do not patch")
    args = parser.parse_args()

    scopes = list(args.scope)
    scopes.extend(args.repo)
    if not scopes and Path(args.config).exists():
        scopes.extend(read_scopes(Path(args.config)))
    if not scopes:
        print("No scopes configured.", file=sys.stderr)
        return 2

    failures = 0
    repos = unique_repos(scopes)
    print(f"repositories: {len(repos)}")
    for repo in repos:
        try:
            admin, enabled = repo_state(repo)
            if not admin:
                print(f"SKIP no-admin {repo}")
                continue
            if enabled:
                print(f"OK already-enabled {repo}")
                continue
            if args.dry_run:
                print(f"WOULD_ENABLE {repo}")
            else:
                enable(repo)
                print(f"ENABLED {repo}")
        except RuntimeError as exc:
            failures += 1
            print(f"ERROR {repo}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
