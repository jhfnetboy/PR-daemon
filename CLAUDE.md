# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

PR-Daemon is a **3-tier PK-style automated PR review system** for open-source repositories (aastar / auraai / mycelium).

**Primary mode — Claude Code on DeepSeek:**
1. `./run-dpsk-claude.sh` starts Claude Code with `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`, routing all LLM calls to DeepSeek (cheap). Claude Code IS the primary reviewer.
2. Claude Code discovers PRs, does deep review, invokes `codex exec` for the PK challenge round, posts findings as `clestons`, and records results.
3. The loop runs autonomously until stopped.

**Tiers:**
- **Tier 1 — Claude Code (DeepSeek):** primary reviewer, orchestrator, final authority.
- **Tier 2 — Codex:** PK challenger — called by Claude Code to adversarially challenge findings.
- **Tier 3 — Optional breadth pass:** `skills/pk-review/scripts/local_review.py` via DeepSeek HTTP API for additional coverage.

**Key constraint:** Claude Code's CLI speaks only the Anthropic API format. `run-dpsk-claude.sh` works because DeepSeek provides an Anthropic-compatible endpoint (`https://api.deepseek.com/anthropic`). Codex is a separate process called via `Bash(codex *)`.

All review artifacts go to `reviews/`. Watcher state is in `.state/pr-daemon/`. No PR branch code is ever modified.

## Primary Entry Point — Claude Code on DeepSeek

```bash
# One-line launch: Claude Code session running on DeepSeek
./run-dpsk-claude.sh

# Then tell Claude Code:
# "Use $pr-daemon-loop to start the 24/7 review loop"

# Headless / non-interactive:
./run-dpsk-claude.sh -p "Use pr-daemon-loop. Start the continuous PR review daemon for jhfnetboy's open PRs across aastar, auraai, and mycelium. Post reviews as clestons. Run until stopped."

# Check status while running:
./watch.sh queue && ./watch.sh current
tail -f .state/pr-daemon/review-watch.log
```

## Startup Commands (helpers and legacy watcher)

```bash
# First-time initialization
./scripts/bootstrap_pr_daemon.sh

# Start the Python watcher (optional — Claude Code can also run the loop itself)
./watch.sh restart
# Or with explicit env:
PR_DAEMON_AUTO_REVIEW=1 PR_DAEMON_MAX_REVIEWS_PER_CYCLE=3 PR_DAEMON_WATCH_INTERVAL=30 ./watch.sh restart
# When watcher launches a reviewer, it now calls run-dpsk-claude.sh -p (falls back to codex)

# Start Codex session with all workspace roots (alternative entry point)
./run.sh

# Start resident local model (optional offline fallback — Metal unavailable in headless/Codex)
scripts/start_rapid_mlx_resident.sh
```

## Daily Observability Commands

```bash
./watch.sh status        # watcher PID, active review, loop state
./watch.sh queue         # SQLite queue by status
./watch.sh current       # currently-running Codex review (JSON)
./watch.sh first-pass    # provider/model/fallback info for active review
tail -f .state/pr-daemon/review-watch.log

./review-status.sh
./review-current.sh
./review-provider-summary.sh
./review-scorecard.sh OWNER REPO PR_NUMBER
```

## PR Discovery

**Never use `@me`** — the active GitHub account may be `clestons` (the posting account).

```bash
python3 scripts/list_open_prs.py
python3 scripts/list_open_prs.py --repo OWNER/REPO
# Underlying command:
gh search prs --author jhfnetboy --state open --json number,title,repository,url,updatedAt,isDraft,author --limit 50
```

## Posting a Review

Only after explicit user approval. `scripts/post_pr_review.sh` switches to `clestons`, posts, then switches back to `jhfnetboy`:

```bash
bash scripts/post_pr_review.sh --repo OWNER/REPO --pr PR_NUMBER --body-file FILE --request-changes
bash scripts/post_pr_review.sh --repo OWNER/REPO --pr PR_NUMBER --body-file FILE --comment
```

Always verify the active GitHub account before and after posting:

```bash
gh api user -q .login
bash scripts/ensure_main_github_account.sh   # restore to jhfnetboy
```

## Model Evaluation

```bash
python3 scripts/model_eval_db.py scorecard --owner OWNER --repo REPO --pr-number N --limit 5
python3 scripts/model_eval_db.py provider-summary --limit 50
python3 scripts/model_eval_db.py record-run ...
python3 scripts/model_eval_db.py assess-item --item-id N --status effective|ineffective|needs_followup|retired
```

## Architecture

### Two Databases

- **`.state/pr-daemon/pr-watch.sqlite`** — runtime watcher state (`pr_watch_targets`, `pr_watch_events`, `pr_watch_meta`). Tracks which PRs need review, their `status` column (`seen` → `needs_review` → `prompt_ready` → `reviewing` → `approved`/`changes_requested`).
- **`reviews/model-evals/model-evals.sqlite`** — persistent scoring history for local model improvement feedback loop (scores, improvement items, `carried_to_next` flag).

### Data Flow

**Primary (Claude Code on DeepSeek):**
```
./run-dpsk-claude.sh  →  claude -p (DeepSeek API via Anthropic-compatible endpoint)
  Claude Code session (primary reviewer, running on DeepSeek)
    → gh search prs --author jhfnetboy   (discover PRs)
    → git fetch / gh pr diff              (get diff)
    → reads diff + files independently    (deep review)
    → skills/pk-review/scripts/local_review.py  (optional breadth pass)
    → codex exec "PK CHALLENGE: ..."      (Tier 3 PK challenger)
    → scripts/post_pr_review.sh           (post as clestons)
    → scripts/model_eval_db.py record-run (record score)
    → loop to next PR
```

**Legacy / fallback (Python watcher → Claude Code or Codex):**
```
review_watch.py (watcher loop)
  → scans GitHub open PRs by author=jhfnetboy
  → picks queued PR → writes prompt file to reviews/watch-prompts/
  → launches run-dpsk-claude.sh -p <prompt>   (primary)
    OR codex exec <prompt>                     (fallback)
  → reviewer posts GitHub review, writes records
```

### Skills

| Skill | Invocation | Purpose |
|-------|-----------|---------|
| `skills/pr-daemon-loop/SKILL.md` | `$pr-daemon-loop` | Full 24/7 autonomous review loop for Claude Code |
| `skills/pk-review/SKILL.md` | `$pk-review` | Single PR review with Codex PK challenge |
| `skills/pk-review/scripts/local_review.py` | CLI | Optional DeepSeek breadth pass, writes `reviews/*-local-review-*.md` |

### Key Scripts

| Script | Purpose |
|--------|---------|
| `run-dpsk-claude.sh` | Launch Claude Code on DeepSeek API (primary entry point) |
| `scripts/model_eval_db.py` | SQLite CRUD for per-PR scoring and improvement items |
| `scripts/resolve_repo.py` | Maps `OWNER/REPO` to local checkout path via `config/repo-roots.json` |
| `scripts/post_pr_review.sh` | Posts GitHub review with account switching (always use this) |
| `scripts/bootstrap_pr_daemon.sh` | One-time init: creates state dirs, initializes both SQLite DBs |
| `scripts/review_watch.py` | Python watcher daemon (optional — Claude Code can run its own loop) |
| `scripts/start_review_watch.sh` | Wraps watcher with nohup, PID file, metadata file |
| `scripts/reset_pr_daemon_state.sh` | Wipes runtime DB; `--wipe-model-eval-db` also wipes eval DB |

### Local Repo Mapping

Business repos are checked out locally, never cloned to `/tmp`:

| GitHub org | Local root |
|-----------|-----------|
| `AAStarCommunity` / `aastar` | `~/Dev/aastar` |
| `AuraAI` / `auraai` | `~/Dev/auraai` |
| `mycelium` | `~/Dev/mycelium` |

Configured in `config/repo-roots.json`. Even when these are writable roots, **never modify business source, config, tests, or lock files**.

## Environment Configuration

Copy `.env.example` → `.env`. Key variables:

```bash
PR_DAEMON_REVIEW_USER=clestons
PR_DAEMON_REVIEW_TOKEN=github_pat_xxx          # classic PAT: repo, read:org, gist

PR_DAEMON_FIRST_PASS_PROVIDER=deepseek
PR_DAEMON_FIRST_PASS_BASE_URL=https://api.deepseek.com/v1
PR_DAEMON_FIRST_PASS_MODEL=deepseek-v4-flash
PR_DAEMON_FIRST_PASS_API_KEY=sk-...
PR_DAEMON_FIRST_PASS_THINKING=disabled

PR_DAEMON_FALLBACK_PROVIDER=rapid-mlx
PR_DAEMON_FALLBACK_BASE_URL=http://127.0.0.1:8000/v1
PR_DAEMON_FALLBACK_MODEL=qwen3.6-a3b

# Proxy (PR-Daemon does not read macOS system proxy):
PR_DAEMON_HTTPS_PROXY=http://127.0.0.1:7890
PR_DAEMON_HTTP_PROXY=http://127.0.0.1:7890
```

## Watcher Env Knobs

| Variable | Default | Effect |
|----------|---------|--------|
| `PR_DAEMON_AUTO_REVIEW` | `1` | `0` = generate prompts only, no Codex launch |
| `PR_DAEMON_DRY_RUN` | `0` | `1` = print codex command, don't execute |
| `PR_DAEMON_MAX_REVIEWS_PER_CYCLE` | `3` | Max PRs processed before waiting |
| `PR_DAEMON_WATCH_INTERVAL` | `30` | Seconds between cycles |
| `PR_DAEMON_REVIEW_REFRESH_INTERVAL` | `3600` | Seconds between full remote PR re-scans |
| `PR_DAEMON_ACTIVE_REVIEW_STALE_SECONDS` | `14400` | Age at which orphaned `current-review.json` is cleared |

After editing `scripts/review_watch.py`, `scripts/start_review_watch.sh`, or `watch.sh`, run `./watch.sh restart`.

## Hard Rules

- **Never merge PRs**, even after `APPROVE`. The PR author decides.
- **Never modify business repo source, config, tests, or lock files** — local checkouts are read-only review context.
- **Never post to GitHub without explicit user approval** in the current turn.
- **Default active account must be `jhfnetboy`** — verify with `gh api user -q .login` before any GitHub operation.
- Rapid-MLX cannot start inside the Codex/headless sandbox (`No Metal device available`). Start it from a normal macOS Terminal and reuse `http://127.0.0.1:8000/v1`.
- Every completed review requires: explicit conclusion (`APPROVE`/`REQUEST_CHANGES`/`COMMENT`), GitHub comment posted, and both Markdown and SQLite records updated.
