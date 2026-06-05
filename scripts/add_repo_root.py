#!/usr/bin/env python3
"""Add or update an owner -> local root mapping for PR-Daemon."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


CONFIG = Path(__file__).resolve().parents[1] / "config" / "repo-roots.json"


def load_config() -> dict[str, Any]:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"version": 1, "updated_at": "", "roots": [], "rule": ""}


def main() -> int:
    parser = argparse.ArgumentParser(description="Add/update a PR-Daemon repo root mapping.")
    parser.add_argument("owner", help="GitHub owner/org, e.g. AAStarCommunity")
    parser.add_argument("path", help="Local root path, e.g. ~/Dev/aastar")
    parser.add_argument("--alias", action="append", default=[], help="Additional alias; may be repeated")
    args = parser.parse_args()

    config = load_config()
    roots = config.setdefault("roots", [])
    owner_key = args.owner.lower()
    aliases = sorted({args.owner, *args.alias})
    path = str(Path(args.path).expanduser())

    for item in roots:
        names = [item.get("owner", ""), *item.get("aliases", [])]
        if owner_key in {name.lower() for name in names}:
            item["owner"] = args.owner
            item["aliases"] = aliases
            item["path"] = path
            break
    else:
        roots.append({"owner": args.owner, "aliases": aliases, "path": path})

    config["updated_at"] = date.today().isoformat()
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.owner} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
