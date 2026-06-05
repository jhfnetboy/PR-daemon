#!/usr/bin/env python3
"""Resolve an OWNER/REPO GitHub repository to the configured local root."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


CONFIG = Path(__file__).resolve().parents[1] / "config" / "repo-roots.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def remote_matches(repo_dir: Path, owner: str, repo: str) -> bool:
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return False
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return False
    url = result.stdout.strip().lower().removesuffix(".git")
    suffix = f"{owner}/{repo}".lower()
    return url.endswith(suffix)


def resolve(owner: str, repo: str) -> tuple[Path, Path | None]:
    config = load_config()
    owner_key = owner.lower()
    for item in config["roots"]:
        names = [item["owner"], *item.get("aliases", [])]
        if owner_key not in {name.lower() for name in names}:
            continue
        root = expand(item["path"])
        direct = root / repo
        if direct.exists():
            return root, direct
        if root.exists():
            for child in root.iterdir():
                if child.is_dir() and child.name.lower() == repo.lower():
                    return root, child
            for child in root.iterdir():
                if child.is_dir() and remote_matches(child, owner, repo):
                    return root, child
        return root, None
    raise RuntimeError(f"no local root configured for owner {owner!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve OWNER/REPO to a local checkout path.")
    parser.add_argument("repository", help="OWNER/REPO")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if "/" not in args.repository:
        raise RuntimeError("repository must be OWNER/REPO")
    owner, repo = args.repository.split("/", 1)
    root, path = resolve(owner, repo)
    clone_target = root / repo
    payload = {
        "repository": args.repository,
        "root": str(root),
        "path": str(path) if path else None,
        "exists": path is not None,
        "clone_target": str(clone_target),
        "clone_command": f"git clone https://github.com/{args.repository}.git {clone_target}",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"repository: {args.repository}")
        print(f"root: {root}")
        if path:
            print(f"path: {path}")
        else:
            print("path: <missing>")
            print(f"clone: {payload['clone_command']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
