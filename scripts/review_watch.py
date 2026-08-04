#!/usr/bin/env python3
"""Track PRs from prbot scopes and enqueue Codex/local-model reviews."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import time
import traceback
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

CREATE TABLE IF NOT EXISTS pr_watch_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute(
        "SELECT value FROM pr_watch_meta WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row else ""


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO pr_watch_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


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
    review_user = os.environ.get("PR_DAEMON_REVIEW_USER", "clestons")
    latest_reviews = pr.get("latestReviews")
    if not isinstance(latest_reviews, list):
        return ""
    for review in latest_reviews:
        if not isinstance(review, dict):
            continue
        author = review.get("author") or {}
        if isinstance(author, dict) and author.get("login") == review_user:
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
        Use $pr (the canonical v4 pipeline — do not substitute a different review flow)
        to review {row['repo']}#{row['pr_number']} in PR-Daemon autonomous watch mode.

        Requirements (on top of everything pr's own SKILL.md already mandates):
        - Use the local repository if available (see config/repo-roots.json); never clone to /tmp unless no local checkout exists.
        - Every review must end with a clear conclusion: APPROVE, REQUEST_CHANGES, or COMMENT.
        - Post the corresponding GitHub review/comment as clestons using scripts/post_pr_review.sh.
        - Never merge the PR, even after approval. Leave merge decisions to the PR author/maintainer.
        - Update PR-Daemon SQLite/Markdown records: reviews/, model_eval_db.py record-run.
          Always pass --provider deepseek --model deepseek-v4-flash explicitly on record-run
          (past runs were mostly logged with provider left blank -> "unknown" in provider-summary,
          which makes flash-specific stats unqueryable — do not repeat that gap).
        - Do NOT modify business repo source, config, tests, or lock files.
        - DeepSeek model is pinned to deepseek-v4-flash (PR_DAEMON_FIRST_PASS_MODEL) — do not override it.
        - In the mandatory self-assessment block, add one explicit line rating DeepSeek v4-flash's
          performance on THIS PR (1-5 + one sentence: did R1a/R1b surface anything Opus R2/Codex R3
          later confirmed as real, any false positives, anything they caught that flash missed
          entirely). This feeds an ongoing flash-vs-pro evaluation (target: 20 rounds, started
          2026-08-01) — jason will aggregate via model_eval_db.py provider-summary once enough
          rounds land, so just record honestly each time, no extra action needed here.

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


def mark_reviewing(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    conn.execute(
        """
        UPDATE pr_watch_targets
        SET status = 'reviewing'
        WHERE repo = ? AND pr_number = ?
        """,
        (row["repo"], row["pr_number"]),
    )


def latest_clestons_review_commit(repo: str, number: int) -> str | None:
    """Commit SHA the latest clestons review was ACTUALLY posted on, via the REST reviews API
    (unlike gh's `latestReviews.commit.oid`, which comes back empty).

    Returns:
      "<sha>" — a clestons review exists, posted on that commit,
      ""      — VERIFIED: no clestons review exists (a real 'phantom' non-posting run),
      None    — verification FAILED (gh api errored / rate-limited / bad JSON). MUST NOT be
                treated as 'no review' — the caller falls back to the old behavior so a transient
                API failure can't re-review an already-verdicted PR into an infinite loop.
    """
    review_user = os.environ.get("PR_DAEMON_REVIEW_USER", "clestons")
    try:
        data = run_json(
            ["gh", "api", f"repos/{repo}/pulls/{number}/reviews", "--paginate", "--per-page", "100"],
            retries=2,
        )
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    commit = ""
    for review in data:  # REST returns chronological order → keep the LAST clestons review
        if isinstance(review, dict):
            user = review.get("user") or {}
            if isinstance(user, dict) and user.get("login") == review_user:
                commit = str(review.get("commit_id") or "")
    return commit


def refresh_review_state(conn: sqlite3.Connection, repo: str, pr_number: int) -> None:
    viewed = view_pr(repo, pr_number)
    clestons_state = latest_clestons_state(viewed)
    state = str(viewed.get("state") or "")
    review_decision = str(viewed.get("reviewDecision") or "")
    head_oid = str(viewed.get("headRefOid") or "")
    # Record the head the review was ACTUALLY posted on — NOT blindly the current PR head — so a
    # phantom rc=0 run (didn't post) leaves last_reviewed at the old SHA → PR stays needs_review.
    review_commit = latest_clestons_review_commit(repo, pr_number)
    # ONLY write this column when we have positive evidence of the commit a review landed on.
    # Stamping the CURRENT head as a fallback is what caused a permanent stall: after the author
    # pushes a fix, this function runs again; a transient REST failure (or lag) then records the
    # NEW head as "already reviewed", so upsert_pr's `last_reviewed != head → needs_review` test
    # can never fire again and the PR is never re-reviewed. (Real case: Brood#34 — review posted
    # on 24da4fc, fix pushed as c0d25e7, DB claimed c0d25e7 was reviewed.)
    #
    # Preserving the previous value is strictly safer than either alternative: it cannot create
    # the old re-review loop (if the PR really was reviewed at an unchanged head, the preserved
    # SHA still equals head → no re-review), and it cannot fake coverage of a head nobody read.
    # Cost: during the brief REST-lag window right after a review posts, the stale SHA may trigger
    # one duplicate review. A duplicate is recoverable; a silent permanent stall is not.
    reviewed_head: str | None
    if review_commit:
        reviewed_head = review_commit            # verified SHA — the only case we record
    elif review_commit == "":
        reviewed_head = None                     # VERIFIED no review yet → leave column untouched
    else:
        reviewed_head = None                     # verification failed → leave column untouched

    if state != "OPEN":
        status = state.lower() or "closed"
    elif clestons_state == "APPROVED":
        status = "approved"
    elif clestons_state == "CHANGES_REQUESTED":
        status = "changes_requested"
    elif clestons_state == "COMMENTED":
        status = "commented"
    else:
        status = "prompt_ready"

    # COALESCE(?, last_reviewed_head_oid): passing NULL keeps whatever is already recorded, so an
    # unverifiable cycle is a no-op on this column instead of overwriting it with the current head.
    conn.execute(
        """
        UPDATE pr_watch_targets
        SET head_oid = ?,
            review_decision = ?,
            last_reviewed_head_oid = COALESCE(?, last_reviewed_head_oid),
            last_review_event = ?,
            last_reviewed_at = CURRENT_TIMESTAMP,
            last_seen_at = CURRENT_TIMESTAMP,
            status = ?
        WHERE repo = ? AND pr_number = ?
        """,
        (head_oid, review_decision, reviewed_head, clestons_state, status, repo, pr_number),
    )


def write_current_review(path: Path, row: sqlite3.Row, prompt_path: Path) -> None:
    payload = {
        "repo": row["repo"],
        "pr_number": row["pr_number"],
        "title": row["title"],
        "head_oid": row["head_oid"],
        "prompt_path": str(prompt_path),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def clear_current_review(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def current_review_age_seconds(path: Path) -> float:
    return max(0.0, time.time() - path.stat().st_mtime)


def write_watcher_state(state_path: Path, **payload: object) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, object] = {}
    if state_path.is_file():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except json.JSONDecodeError:
            current = {}
    current.update(payload)
    current["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state_path.write_text(json.dumps(current, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def read_workspace_roots(config_path: Path = Path("config/workspace-roots.txt")) -> list[str]:
    if not config_path.exists():
        return []
    roots = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            roots.append(stripped)
    return roots


def _add_dir_flags(roots: list[str]) -> list[str]:
    flags: list[str] = []
    for root in roots:
        flags += ["--add-dir", root]
    return flags


# --- Cost gate: pick the review backend by changed-files risk --------------
# The pr skill routes R1=DeepSeek-flash (own API), executor=session
# model, and R2/R4=Opus + R3=Codex via Agent() sub-agents. Because ANTHROPIC_*
# overrides are process-global, a session launched through run-dpsk-claude.sh
# resolves those "opus" sub-agents to DeepSeek too. So we pick the backend PER PR:
#   trivial (pure docs/deps/chore) -> DeepSeek shell (cheap, ~free)
#   everything else / any uncertainty -> real Anthropic (real Opus + Codex)
# The gate is coarse and CONSERVATIVE (default 'real'); the skill's own Step-4
# triage still assigns the accurate 2/4-round label inside the chosen session.
_TRIVIAL_SUFFIXES = (
    ".md", ".mdx", ".markdown", ".rst", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
)
_TRIVIAL_BASENAMES = frozenset({
    "license", "license.md", "notice", "notice.md", "contributing.md",
    "codeowners", "readme", "readme.md", ".gitignore", ".editorconfig",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "cargo.toml", "cargo.lock", "go.mod", "go.sum", "requirements.txt",
    "poetry.lock", "gemfile.lock",
})


# Automation-consumed ledgers/config: look like docs/markdown but are parsed & executed by
# CI / pilot / scripts, so a bad value has real consequences — NOT trivial (route to real backend).
_LEDGER_PATH_HINTS = ("docs/agent/", ".pilot.yml", ".pilot.yaml")
_LEDGER_BASENAMES = frozenset({"tasks.md", "roadmap.md", "progress.md"})


def _is_trivial_path(path: str) -> bool:
    p = path.strip().lower()
    if not p:
        return False
    base = p.rsplit("/", 1)[-1]
    # automation-consumed ledgers/config are NOT trivial, even under docs/ (YAA#450)
    if any(h in p for h in _LEDGER_PATH_HINTS) or base in _LEDGER_BASENAMES:
        return False
    if p.startswith("docs/"):
        return True
    if base in _TRIVIAL_BASENAMES:
        return True
    return p.endswith(_TRIVIAL_SUFFIXES)


def pr_changed_files(repo: str, pr_number: int) -> list[str] | None:
    """Changed file paths for a PR via gh. None on any failure (caller = safe side)."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo,
             "--json", "files", "--jq", ".files[].path"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def triage_gate(row: sqlite3.Row) -> str:
    """Return 'deepseek' (cheap) or 'real' (Anthropic). Conservative: default 'real'.

    Only a PR whose EVERY changed file is provably trivial gets the cheap backend.
    PR_DAEMON_FORCE_BACKEND=deepseek|real overrides the gate (for tests/spikes).
    """
    forced = os.environ.get("PR_DAEMON_FORCE_BACKEND", "").strip().lower()
    if forced in ("deepseek", "real"):
        return forced
    files = pr_changed_files(row["repo"], int(row["pr_number"]))
    if not files:
        return "real"  # gh failed or empty -> real (safe side)
    return "deepseek" if all(_is_trivial_path(f) for f in files) else "real"


def _build_claude_cmd(roots: list[str], backend: str = "deepseek") -> list[str]:
    # The prompt is NOT embedded here — it is fed via stdin by launch_reviewer using
    # `--print`. A `-p <prompt>` positional is unreliable when claude runs detached
    # (it waits on / errors reading stdin: "Input must be provided…"); stdin-fed is robust.
    max_turns = os.environ.get("PR_DAEMON_REVIEWER_MAX_TURNS", "80")
    skill_file = str(Path.cwd() / ".claude/skills/pr/SKILL.md")
    if backend == "real":
        # Real Anthropic (Max OAuth): executor = real Sonnet, R2/R4 spawn real Opus,
        # R3 real Codex. `env -u` strips any ambient DeepSeek override so the CLI hits
        # api.anthropic.com, never the DeepSeek endpoint.
        model = os.environ.get("PR_DAEMON_REAL_MODEL", "sonnet")
        launch = [
            "env",
            "-u", "ANTHROPIC_BASE_URL",
            "-u", "ANTHROPIC_AUTH_TOKEN",
            "-u", "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "-u", "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "-u", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "claude",
        ]
    else:
        # Cheap DeepSeek backend (all model aliases -> deepseek-v4-flash via the shell).
        model = os.environ.get("PR_DAEMON_DEEPSEEK_MODEL", "sonnet")
        launch = ["bash", str(Path.cwd() / "run-dpsk-claude.sh")]
    cmd = [
        *launch,
        "--print",
        "--model",
        model,
        # Autonomous headless reviewer: skip the permission layer so R3's
        # codex:codex-rescue sub-agent (and its internal Bash) runs natively instead of
        # being denied and forced into a turn-wasting fallback (observed on Brood#13).
        # No-post during tests is enforced by post_pr_review.sh's PR_DAEMON_NO_POST
        # guard, not by tool allow-listing.
        "--dangerously-skip-permissions",
        "--append-system-prompt-file",
        skill_file,
        "--max-turns",
        max_turns,
    ]
    cmd += _add_dir_flags(roots)
    return cmd


def _build_codex_cmd(prompt_text: str, roots: list[str]) -> list[str]:
    cmd = [
        "codex",
        "exec",
        "-s",
        "workspace-write",
        "-c",
        "sandbox_workspace_write.network_access=true",
        "--cd",
        str(Path.cwd()),
    ]
    cmd += _add_dir_flags(roots)
    cmd.append(prompt_text)
    return cmd


def _log_review_eval(row: sqlite3.Row, backend_label: str, duration_sec: float, returncode: int) -> None:
    """Append one line to reviews/review-eval.tsv for periodic speed/cost analysis.
    Columns: timestamp \t repo#pr \t backend \t duration \t rc. Never raises."""
    try:
        line = "\t".join([
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            f"{row['repo']}#{row['pr_number']}",
            backend_label,
            f"{duration_sec:.0f}s",
            f"rc={returncode}",
        ])
        eval_path = Path("reviews") / "review-eval.tsv"
        eval_path.parent.mkdir(parents=True, exist_ok=True)
        with eval_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def launch_reviewer(row: sqlite3.Row, prompt_path: Path, dry_run: bool) -> int:
    prompt_text = prompt_path.read_text(encoding="utf-8")
    roots = read_workspace_roots()

    primary_cli = os.environ.get("PR_DAEMON_REVIEWER_CLI", "claude")
    fallback_cli = os.environ.get("PR_DAEMON_REVIEWER_FALLBACK", "codex")
    # Codex fallback is OFF by default: a failed claude review would otherwise be re-run
    # with codex, which produces low-quality/garbage output that could get posted.
    allow_codex_fallback = os.environ.get("PR_DAEMON_ALLOW_CODEX_FALLBACK", "0") == "1"

    # Determine which CLI to use based on binary availability
    use_claude = primary_cli == "claude" and shutil.which("claude") is not None
    use_claude = use_claude and Path("run-dpsk-claude.sh").exists()

    if use_claude:
        backend = triage_gate(row)
        cmd = _build_claude_cmd(roots, backend=backend)
        cli_label = "claude(real-anthropic)" if backend == "real" else "claude(deepseek)"
    elif allow_codex_fallback and shutil.which(fallback_cli):
        cmd = _build_codex_cmd(prompt_text, roots)
        cli_label = fallback_cli
    else:
        # Codex fallback disabled -> fail loudly instead of reviewing with (and posting) codex.
        raise RuntimeError(
            "claude reviewer unavailable and codex fallback is disabled "
            "(set PR_DAEMON_ALLOW_CODEX_FALLBACK=1 to re-enable)"
        )

    print("LAUNCH", row["repo"], f"#{row['pr_number']}", f"[{cli_label}]", shlex.join(cmd[:8]), "...")
    if not dry_run:
        review_started = time.time()
        # claude runs with `--print` and reads the prompt from stdin — robust when
        # detached (a `-p <arg>` positional errors "Input must be provided…" there).
        # codex takes the prompt as a positional arg and gets EOF on stdin instead.
        if use_claude:
            result = subprocess.run(cmd, check=False, input=prompt_text, text=True)
        else:
            result = subprocess.run(cmd, check=False, stdin=subprocess.DEVNULL)
        # On non-zero exit: retry with codex ONLY if the fallback is explicitly enabled.
        # Disabled by default -> a failed review propagates so the daemon requeues the PR
        # (prompt_ready) and logs launch_error, instead of posting garbage from codex.
        if result.returncode != 0 and use_claude and allow_codex_fallback and shutil.which(fallback_cli):
            print(
                f"FALLBACK {row['repo']}#{row['pr_number']} {cli_label} exited {result.returncode};"
                f" retrying with {fallback_cli}",
                file=sys.stderr,
            )
            fallback_cmd = _build_codex_cmd(prompt_text, roots)
            result = subprocess.run(fallback_cmd, check=False, stdin=subprocess.DEVNULL)
        _log_review_eval(row, cli_label, time.time() - review_started, result.returncode)
        return result.returncode
    return 0


def queue_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM pr_watch_targets
        WHERE status IN ('needs_review', 'prompt_ready', 'reviewing')
          AND is_draft = 0
          AND title NOT LIKE '%WIP%'
          AND title NOT LIKE '%PAUSED%'
          AND (last_reviewed_head_oid IS NULL OR last_reviewed_head_oid != head_oid)
        """
    ).fetchone()
    return int(row["count"]) if row else 0


def next_queue_item(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM pr_watch_targets
        WHERE status IN ('prompt_ready', 'needs_review')
          AND is_draft = 0
          AND title NOT LIKE '%WIP%'
          AND title NOT LIKE '%PAUSED%'
          AND (last_reviewed_head_oid IS NULL OR last_reviewed_head_oid != head_oid)
        ORDER BY
          CASE status
            WHEN 'prompt_ready' THEN 0
            WHEN 'needs_review' THEN 1
            ELSE 2
          END,
          last_seen_at DESC
        LIMIT 1
        """
    ).fetchone()


def should_refresh(conn: sqlite3.Connection, refresh_interval: int) -> bool:
    last_sync = get_meta(conn, "last_full_sync_epoch")
    if not last_sync:
        return True
    try:
        age = time.time() - int(last_sync)
    except ValueError:
        return True
    return age >= refresh_interval


# Statuses that mean "this PR still needs something from us". Anything else — approved,
# changes_requested (verdict already delivered), commented, merged, closed, draft, seen —
# is settled or not ours to act on.
ACTIONABLE_STATUSES = frozenset({"needs_review", "prompt_ready", "reviewing"})

# How many already-settled queue rows to skip past in one cycle before giving up. Each skip costs
# one `gh pr view`; the cap keeps a large backlog of stale rows from eating the whole cycle in
# verification calls. Whatever is left gets cleaned up on subsequent cycles.
MAX_STALE_SKIPS = 5

# Title markers the author uses to say "not ready, don't review" — same list the review
# queue filters on (see queue_count / next_queue_item). Kept in one place so the scan
# printout and the queue can never disagree about what counts as reviewable.
SKIP_TITLE_MARKERS = ("WIP", "PAUSED")


def is_actionable(status: str, item: dict) -> bool:
    """Should this PR appear in the per-cycle scan printout?

    The printout is a WORK LIST, not an inventory. Printing every tracked PR every cycle
    buried the few PRs that actually need review under dozens of already-approved / draft /
    WIP lines, and made settled PRs look like they were queued up to be re-reviewed. The DB
    still tracks everything (state transitions depend on it) — only the noise is suppressed.

    Conditions mirror queue_count()/next_queue_item() exactly, so if a line prints here it
    really is a candidate for review, and if it doesn't print it really won't be reviewed.
    """
    if status not in ACTIONABLE_STATUSES:
        return False
    if item.get("isDraft"):
        return False
    title = str(item.get("title") or "")
    return not any(marker in title for marker in SKIP_TITLE_MARKERS)


def refresh_from_remote(conn: sqlite3.Connection, args: argparse.Namespace, scopes: list[str]) -> int:
    seen = 0
    actionable = 0
    for scope in scopes:
        # Isolate each scope: a bad org (renamed/invalid/no-permission) or a transient
        # gh failure must not starve the remaining scopes this cycle. Log and continue.
        try:
            scope_items = search_scope(scope, args.limit_per_scope)
        except Exception as exc:
            print(f"scope_scan_failed scope={scope}: {exc}", file=sys.stderr)
            continue
        for item in scope_items:
            repo_info = item.get("repository") or {}
            repo = repo_info.get("nameWithOwner") if isinstance(repo_info, dict) else ""
            number = int(item.get("number") or 0)
            try:
                status, _ = upsert_pr(conn, item)
                seen += 1
                if is_actionable(status, item):
                    actionable += 1
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
    set_meta(conn, "last_full_sync_epoch", str(int(time.time())))
    # Say plainly how many were hidden, so an empty work list reads as "nothing to do"
    # rather than "the scan broke" — and so suppression is never silent.
    hidden = seen - actionable
    if hidden > 0:
        print(f"scan: {actionable} actionable / {seen} open (hidden {hidden}: approved/draft/WIP/settled)")
    return seen


def repair_false_reviewed(conn: sqlite3.Connection) -> int:
    """Un-stick PRs the DB believes were reviewed at their current head but never actually were.

    `last_reviewed_head_oid == head_oid` is what keeps a PR out of the queue. If that value was
    ever written without a real review behind it (the old refresh_review_state stamped the CURRENT
    head whenever REST verification was inconclusive), the PR silently drops out of the queue
    FOREVER — no error, no log line, it simply never gets reviewed. Found in the wild:
    AirAccount#195/#196 sat "reviewed" with zero reviews on GitHub.

    A row is suspect when it claims a reviewed head but has no recorded review event. Confirm
    against GitHub before touching anything — a review that exists but wasn't recorded locally must
    NOT be re-run — then clear the false stamp so the normal queue logic picks it up again.

    Returns how many rows were repaired. Cheap: the suspect set is normally empty.
    """
    suspects = conn.execute(
        """
        SELECT repo, pr_number FROM pr_watch_targets
        WHERE state = 'OPEN' AND is_draft = 0
          AND last_reviewed_head_oid IS NOT NULL
          AND last_reviewed_head_oid = head_oid
          AND (last_review_event IS NULL OR last_review_event = '')
          AND title NOT LIKE '%WIP%' AND title NOT LIKE '%PAUSED%'
        """
    ).fetchall()

    repaired = 0
    for s in suspects:
        repo, number = s["repo"], s["pr_number"]
        commit = latest_clestons_review_commit(repo, number)
        if commit is None:
            continue                      # couldn't verify — leave it alone, retry next cycle
        if commit != "":
            # A review DOES exist; the local record was merely missing. Write the truth instead of
            # re-reviewing, so this repair can never cause duplicate reviews.
            conn.execute(
                "UPDATE pr_watch_targets SET last_reviewed_head_oid = ? WHERE repo = ? AND pr_number = ?",
                (commit, repo, number),
            )
            continue
        conn.execute(
            "UPDATE pr_watch_targets SET last_reviewed_head_oid = NULL, status = 'needs_review' "
            "WHERE repo = ? AND pr_number = ?",
            (repo, number),
        )
        repaired += 1
        print(f"repaired_false_reviewed {repo}#{number} (marked reviewed but GitHub has no review)")
    if suspects:
        conn.commit()
    return repaired


def process_queue(conn: sqlite3.Connection, args: argparse.Namespace, current_review: Path) -> int:
    # Confirm the PR is still open before spending a review on it. The scan only ever returns OPEN
    # PRs, so a row whose PR was merged or closed afterwards is never updated again and sits in the
    # queue forever at its last-known state — and this function used to go straight from "row" to
    # "launch reviewer", burning a full ~20-minute review on a PR that no longer exists, and
    # delaying every real PR behind it. Verifying costs one `gh pr view`.
    #
    # Skip past stale rows rather than returning: one merged PR at the head of the queue must not
    # cost the whole cycle. Bounded so a burst of stale rows can't spin here indefinitely.
    row = None
    for _ in range(MAX_STALE_SKIPS):
        candidate = next_queue_item(conn)
        if candidate is None:
            return 0
        repo, number = candidate["repo"], candidate["pr_number"]
        try:
            viewed = view_pr(repo, number)
        except Exception as exc:
            # Can't verify (transient API failure) — proceed rather than stall the queue. A wasted
            # review is recoverable; refusing to review anything until GitHub answers is not.
            print(f"queue_state_check_failed {repo}#{number}: {exc}", file=sys.stderr)
            row = candidate
            break
        state = str(viewed.get("state") or "")
        if state == "OPEN":
            # Also make sure the recorded head is still the real one. The queue row is written by
            # the periodic scan, which may be several minutes stale — and `refresh_from_remote`
            # is skipped entirely while the queue is non-empty. Reviewing an outdated head burns a
            # full cycle producing findings the author already fixed, and posts a misleading
            # CHANGES_REQUESTED against code that no longer exists. Observed on Brood#36: the
            # reviewer launched on b693c6d minutes after 7288916 was pushed.
            live_head = str(viewed.get("headRefOid") or "")
            if live_head and live_head != str(candidate["head_oid"] or ""):
                print(
                    f"head_moved {repo}#{number} {str(candidate['head_oid'])[:7]} → {live_head[:7]}; "
                    "re-syncing before review"
                )
                # Re-upsert from the live view so head_oid, status and the prompt all describe the
                # same commit, then take the refreshed row.
                upsert_pr(conn, {"repo": repo, "number": number})
                conn.commit()
                refreshed = conn.execute(
                    "SELECT * FROM pr_watch_targets WHERE repo = ? AND pr_number = ?",
                    (repo, number),
                ).fetchone()
                if refreshed is not None:
                    candidate = refreshed
            row = candidate
            break
        # Settled since we last saw it — record the real state so it drops out of the queue for good.
        conn.execute(
            "UPDATE pr_watch_targets SET state = ?, status = ?, last_seen_at = CURRENT_TIMESTAMP "
            "WHERE repo = ? AND pr_number = ?",
            (state, state.lower() or "closed", repo, number),
        )
        conn.commit()
        print(f"skip_settled {repo}#{number} state={state} (no longer open; dropped from queue)")

    if row is None:
        return 0

    if not args.write_prompts_dir:
        return 0

    path = Path(row["last_prompt_path"]) if row["status"] == "prompt_ready" and row["last_prompt_path"] else None
    if path is None or not path.exists():
        path = write_prompt(row, Path(args.write_prompts_dir))
        mark_prompt(conn, row, path)
        print(f"PROMPT {path}")

    if args.auto_review:
        if args.dry_run:
            launch_reviewer(row, path, True)
        else:
            returncode = -1
            mark_reviewing(conn, row)
            write_current_review(current_review, row, path)
            try:
                returncode = launch_reviewer(row, path, False)
            except Exception as exc:
                mark_prompt(conn, row, path)
                conn.execute(
                    """
                    INSERT INTO pr_watch_events (repo, pr_number, head_oid, event_type, details)
                    VALUES (?, ?, ?, 'launch_error', ?)
                    """,
                    (row["repo"], row["pr_number"], row["head_oid"], f"launch exception: {exc}"),
                )
                print(f"launch_error     {row['repo']}#{row['pr_number']} {exc}", file=sys.stderr)
            finally:
                clear_current_review(current_review)
            if returncode == 0:
                refresh_review_state(conn, row["repo"], row["pr_number"])
            elif returncode != -1:
                mark_prompt(conn, row, path)
                conn.execute(
                    """
                    INSERT INTO pr_watch_events (repo, pr_number, head_oid, event_type, details)
                    VALUES (?, ?, ?, 'launch_error', ?)
                    """,
                    (row["repo"], row["pr_number"], row["head_oid"], f"reviewer exit code {returncode}"),
                )
    return 1


def scan(args: argparse.Namespace) -> int:
    scopes = list(args.scope)
    if not scopes and Path(args.config).exists():
        scopes = read_scopes(Path(args.config))
    if not scopes:
        print("No scopes configured.", file=sys.stderr)
        return 2

    seen = 0
    with connect(Path(args.db)) as conn:
        current_review = Path(args.db).parent / "current-review.json"
        watcher_state = Path(args.db).parent / "watcher-state.json"
        write_watcher_state(watcher_state, loop_state="scan_start")
        if current_review.exists():
            age_seconds = current_review_age_seconds(current_review)
            if age_seconds < args.active_review_stale_seconds:
                write_watcher_state(
                    watcher_state,
                    loop_state="blocked_active_review",
                    active_review_age_seconds=round(age_seconds, 1),
                    seen_open_prs=0,
                    processed_reviews=0,
                )
                print(
                    f"active_review_block {current_review} age_seconds={age_seconds:.1f}; "
                    "skipping new queue work until it clears",
                    file=sys.stderr,
                )
                print("seen_open_prs: 0")
                return 0
            print(
                f"stale_active_review {current_review} age_seconds={age_seconds:.1f}; clearing stale marker",
                file=sys.stderr,
            )
            clear_current_review(current_review)
            write_watcher_state(
                watcher_state,
                loop_state="cleared_stale_active_review",
                active_review_age_seconds=round(age_seconds, 1),
            )
        # Self-heal falsely-"reviewed" rows before deciding there is nothing to do. Without this,
        # a single bad stamp removes a PR from the queue permanently and silently — the failure
        # looks exactly like "no work pending", which is why it went unnoticed for days.
        repair_false_reviewed(conn)

        if queue_count(conn) == 0 or should_refresh(conn, args.refresh_interval):
            seen = refresh_from_remote(conn, args, scopes)
            write_watcher_state(watcher_state, loop_state="refreshed", seen_open_prs=seen)

        processed = 0
        for _ in range(args.max_reviews_per_cycle):
            processed += process_queue(conn, args, current_review)
            if processed == 0:
                break
        write_watcher_state(
            watcher_state,
            loop_state="idle" if processed == 0 else "cycle_complete",
            seen_open_prs=seen,
            processed_reviews=processed,
        )

    print(f"seen_open_prs: {seen}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PR-Daemon watch loop for autonomous reviews.")
    parser.add_argument("--config", default=str(DEFAULT_PRBOT_CONFIG), help="prbot repos.conf path")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite watch DB path")
    parser.add_argument("--init-db", action="store_true", help="Initialize the watch SQLite schema and exit")
    parser.add_argument("--scope", action="append", default=[], help="Org or owner/repo; repeatable")
    parser.add_argument("--limit-per-scope", type=int, default=200)
    parser.add_argument("--max-reviews-per-cycle", type=int, default=3)
    parser.add_argument("--refresh-interval", type=int, default=3600, help="Seconds between full remote refresh scans")
    parser.add_argument("--write-prompts-dir", default="reviews/watch-prompts")
    parser.add_argument("--auto-review", action="store_true", help="Launch codex exec for queued PRs")
    parser.add_argument("--dry-run", action="store_true", help="Print codex command without launching")
    parser.add_argument("--loop", action="store_true", help="Run forever")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval seconds")
    parser.add_argument(
        "--active-review-stale-seconds",
        type=int,
        # 1h, was 4h. This is the backstop for a review whose process died WITHOUT the start-time
        # lock cleanup catching it (i.e. the watcher itself kept running). A real 4-round review
        # tops out well under this: codex_pk caps R3 at 360s and the other rounds are minutes, so
        # ~15-25min is the realistic worst case. At 4h a single orphaned lock silently parked the
        # whole daemon for half a day — printing `seen_open_prs: 0` while reviewing nothing.
        default=int(os.environ.get("PR_DAEMON_ACTIVE_REVIEW_STALE_SECONDS", "3600")),
        help="Treat current-review.json older than this as stale and clear it",
    )
    args = parser.parse_args()

    if args.init_db:
        with connect(Path(args.db)):
            pass
        print(args.db)
        return 0

    while True:
        try:
            scan(args)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            traceback.print_exc()
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
