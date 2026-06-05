#!/usr/bin/env python3
"""Track PRs from prbot scopes and enqueue Codex/local-model reviews."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path


DEFAULT_PRBOT_CONFIG = Path.home() / ".config" / "prbot" / "repos.conf"
DEFAULT_DB = Path("reviews/pr-watch.sqlite")
SEARCH_FIELDS = "repository,number,title,url,author,updatedAt,isDraft,state"
VIEW_FIELDS = (
    "number,title,url,author,headRefOid,headRefName,baseRefName,isDraft,"
    "state,reviewDecision,updatedAt,latestReviews"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_watch_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    title TEXT,
    url TEXT,
    author TEXT,
    base_ref TEXT,
    head_ref TEXT,
    head_oid TEXT,
    state TEXT,
    review_decision TEXT,
    is_draft INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_reviewed_head_oid TEXT,
    last_review_event TEXT,
    last_reviewed_at TEXT,
    last_prompt_path TEXT,
    status TEXT NOT NULL DEFAULT 'seen',
    UNIQUE(repo, pr_number)
);

CREATE INDEX IF NOT EXISTS idx_pr_watch_status
ON pr_watch_targets(status, last_seen_at);

CREATE TABLE IF NOT EXISTS pr_watch_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    head_oid TEXT,
    event_type TEXT NOT NULL,
    details TEXT
);
"""


def run_json(args: list[str], retries: int = 3) -> object:
    last_error = ""
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "null")
        last_error = result.stderr.strip() or "command failed"
        if attempt < retries:
            time.sleep(attempt)
    raise RuntimeError(last_error)


def run_text(args: list[str], retries: int = 3) -> str:
    last_error = ""
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        last_error = result.stderr.strip() or "command failed"
        if attempt < retries:
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


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def search_scope(scope: str, limit: int) -> list[dict[str, object]]:
    args = ["gh", "search", "prs", "--state", "open", "--archived=false", "--limit", str(limit), "--json", SEARCH_FIELDS]
    if "/" in scope:
        args.extend(["--repo", scope])
    else:
        args.extend(["--owner", scope])
    data = run_json(args)
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected search response: {data!r}")
    return [item for item in data if isinstance(item, dict)]


def view_pr(repo: str, number: int) -> dict[str, object]:
    data = run_json(["gh", "pr", "view", str(number), "--repo", repo, "--json", VIEW_FIELDS])
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected PR view response: {data!r}")
    return data


def latest_clestons_state(pr: dict[str, object]) -> str:
    latest_reviews = pr.get("latestReviews")
    if not isinstance(latest_reviews, list):
        return ""
    for review in latest_reviews:
        if not isinstance(review, dict):
            continue
        author = review.get("author") or {}
        if isinstance(author, dict) and author.get("login") == "clestons":
            state = review.get("state")
            return str(state or "")
    return ""


def upsert_pr(conn: sqlite3.Connection, pr: dict[str, object]) -> tuple[str, sqlite3.Row | None]:
    repo_info = pr.get("repository")
    if isinstance(repo_info, dict):
        repo = str(repo_info.get("nameWithOwner") or "")
    else:
        repo = str(pr.get("repo") or "")
    number = int(pr["number"])
    viewed = view_pr(repo, number)
    head_oid = str(viewed.get("headRefOid") or "")
    existing = conn.execute(
        "SELECT * FROM pr_watch_targets WHERE repo = ? AND pr_number = ?",
        (repo, number),
    ).fetchone()

    author = viewed.get("author") or {}
    author_login = author.get("login") if isinstance(author, dict) else ""
    clestons_state = latest_clestons_state(viewed)
    status = "draft" if viewed.get("isDraft") else "seen"
    if viewed.get("state") != "OPEN":
        status = str(viewed.get("state") or "closed").lower()
    elif existing is None or existing["last_reviewed_head_oid"] != head_oid:
        status = "needs_review"
    elif clestons_state == "APPROVED":
        status = "approved"
    elif clestons_state == "CHANGES_REQUESTED":
        status = "changes_requested"

    values = (
        repo,
        number,
        viewed.get("title"),
        viewed.get("url"),
        author_login,
        viewed.get("baseRefName"),
        viewed.get("headRefName"),
        head_oid,
        viewed.get("state"),
        viewed.get("reviewDecision"),
        1 if viewed.get("isDraft") else 0,
        clestons_state,
        status,
    )
    conn.execute(
        """
        INSERT INTO pr_watch_targets (
            repo, pr_number, title, url, author, base_ref, head_ref, head_oid,
            state, review_decision, is_draft, last_review_event, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo, pr_number) DO UPDATE SET
            title = excluded.title,
            url = excluded.url,
            author = excluded.author,
            base_ref = excluded.base_ref,
            head_ref = excluded.head_ref,
            head_oid = excluded.head_oid,
            state = excluded.state,
            review_decision = excluded.review_decision,
            is_draft = excluded.is_draft,
            last_review_event = excluded.last_review_event,
            status = excluded.status,
            last_seen_at = CURRENT_TIMESTAMP
        """,
        values,
    )
    event_type = ""
    if existing is None:
        event_type = "discovered"
    elif existing["head_oid"] != head_oid:
        event_type = "head_changed"
    elif existing["status"] != status:
        event_type = f"status:{status}"
    if event_type:
        conn.execute(
            """
            INSERT INTO pr_watch_events (repo, pr_number, head_oid, event_type, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (repo, number, head_oid, event_type, viewed.get("title") or ""),
        )
    return status, existing


def build_prompt(row: sqlite3.Row) -> str:
    return textwrap.dedent(
        f"""
        Use $rapid-mlx-review to review {row['repo']}#{row['pr_number']} in PR-Daemon autonomous watch mode.

        Requirements:
        - Use the local repository if available; never clone to /tmp unless no configured local checkout exists.
        - Use qwen3.6-a3b through Rapid-MLX for broad pass, prior-finding verification, adversarial cases, and comment draft.
        - Codex must independently verify findings with code, diff, and commands.
        - Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
        - Post the corresponding GitHub review/comment as clestons.
        - Update PR-Daemon SQLite/Markdown records, including model score and improvement-item assessment.
        - Continue to treat local-model output as hypotheses, not final authority.

        PR metadata:
        - title: {row['title']}
        - url: {row['url']}
        - base: {row['base_ref']}
        - head: {row['head_ref']}
        - head_oid: {row['head_oid']}
        - current_review_decision: {row['review_decision']}
        - latest_clestons_review: {row['last_review_event']}
        """
    ).strip()


def write_prompt(row: sqlite3.Row, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_repo = row["repo"].replace("/", "-")
    path = out_dir / f"{safe_repo}-{row['pr_number']}-{row['head_oid'][:7]}.prompt.md"
    path.write_text(build_prompt(row) + "\n", encoding="utf-8")
    return path


def mark_prompt(conn: sqlite3.Connection, row: sqlite3.Row, path: Path) -> None:
    conn.execute(
        """
        UPDATE pr_watch_targets
        SET last_prompt_path = ?, status = 'prompt_ready'
        WHERE repo = ? AND pr_number = ?
        """,
        (str(path), row["repo"], row["pr_number"]),
    )


def launch_codex(row: sqlite3.Row, prompt_path: Path, dry_run: bool) -> None:
    cmd = [
        "codex",
        "exec",
        "-a",
        "never",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(Path.cwd()),
        "--add-dir",
        "/Users/jason/Dev/aastar",
        "--add-dir",
        "/Users/jason/Dev/auraai",
        "--add-dir",
        "/Users/jason/Dev/mycelium",
        prompt_path.read_text(encoding="utf-8"),
    ]
    print("LAUNCH", row["repo"], f"#{row['pr_number']}", shlex.join(cmd[:12]), "...")
    if not dry_run:
        subprocess.run(cmd, check=False)


def scan(args: argparse.Namespace) -> int:
    scopes = list(args.scope)
    if not scopes and Path(args.config).exists():
        scopes = read_scopes(Path(args.config))
    if not scopes:
        print("No scopes configured.", file=sys.stderr)
        return 2

    seen = 0
    with connect(Path(args.db)) as conn:
        for scope in scopes:
            for item in search_scope(scope, args.limit_per_scope):
                repo_info = item.get("repository") or {}
                repo = repo_info.get("nameWithOwner") if isinstance(repo_info, dict) else ""
                number = int(item.get("number") or 0)
                try:
                    status, _ = upsert_pr(conn, item)
                    seen += 1
                    print(f"{status:16} {repo}#{number} {item.get('title')}")
                except RuntimeError as exc:
                    conn.execute(
                        """
                        INSERT INTO pr_watch_events (repo, pr_number, event_type, details)
                        VALUES (?, ?, 'scan_error', ?)
                        """,
                        (repo, number, str(exc)),
                    )
                    print(f"{'scan_error':16} {repo}#{number} {exc}", file=sys.stderr)

        queue = conn.execute(
            """
            SELECT * FROM pr_watch_targets
            WHERE status = 'needs_review'
              AND is_draft = 0
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (args.max_reviews_per_cycle,),
        ).fetchall()
        for row in queue:
            if args.write_prompts_dir:
                path = write_prompt(row, Path(args.write_prompts_dir))
                mark_prompt(conn, row, path)
                print(f"PROMPT {path}")
                if args.auto_review:
                    launch_codex(row, path, args.dry_run)

    print(f"seen_open_prs: {seen}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PR-Daemon watch loop for autonomous reviews.")
    parser.add_argument("--config", default=str(DEFAULT_PRBOT_CONFIG), help="prbot repos.conf path")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite watch DB path")
    parser.add_argument("--scope", action="append", default=[], help="Org or owner/repo; repeatable")
    parser.add_argument("--limit-per-scope", type=int, default=200)
    parser.add_argument("--max-reviews-per-cycle", type=int, default=3)
    parser.add_argument("--write-prompts-dir", default="reviews/watch-prompts")
    parser.add_argument("--auto-review", action="store_true", help="Launch codex exec for queued PRs")
    parser.add_argument("--dry-run", action="store_true", help="Print codex command without launching")
    parser.add_argument("--loop", action="store_true", help="Run forever")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval seconds")
    args = parser.parse_args()

    while True:
        try:
            scan(args)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
