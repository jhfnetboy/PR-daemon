---
name: pr-daemon-status
description: Show a live progress dashboard for the PR review daemon. Displays total PRs queued, in-progress, completed, and a verdict breakdown (REQUEST_CHANGES / APPROVE / COMMENT). Use when the user says "status", "show progress", "how many done", "$pr-daemon-status", or asks for a review summary.
origin: pr-daemon
---

# PR Daemon Status Dashboard

Run the queries below and format the output as a clean dashboard. Call this any time the user asks for status, or print it automatically after every completed review cycle.

## Step 1 — Queue State (pr_watch_targets)

```bash
STATE_DB="PR_DAEMON_ROOT/.state/pr-daemon/pr-watch.sqlite"

# Total discovered
sqlite3 "$STATE_DB" "SELECT COUNT(*) FROM pr_watch_targets;"

# By status
sqlite3 "$STATE_DB" "
SELECT status, COUNT(*) as n
FROM pr_watch_targets
GROUP BY status
ORDER BY CASE status
  WHEN 'reviewing'          THEN 1
  WHEN 'needs_review'       THEN 2
  WHEN 'prompt_ready'       THEN 3
  WHEN 'seen'               THEN 4
  WHEN 'changes_requested'  THEN 5
  WHEN 'approved'           THEN 6
  ELSE 7 END;"

# Currently being reviewed
sqlite3 "$STATE_DB" "
SELECT repo, pr_number, title
FROM pr_watch_targets WHERE status='reviewing';"
```

## Step 2 — Verdict Breakdown (model_review_runs)

```bash
EVAL_DB="PR_DAEMON_ROOT/reviews/model-evals/model-evals.sqlite"

# Total reviews posted
sqlite3 "$EVAL_DB" "SELECT COUNT(*) FROM model_review_runs;"

# By verdict
sqlite3 "$EVAL_DB" "
SELECT verdict, COUNT(*) as n, ROUND(AVG(score),2) as avg_score
FROM model_review_runs
GROUP BY verdict
ORDER BY n DESC;"

# Recent 10 reviews
sqlite3 "$EVAL_DB" "
SELECT datetime(created_at,'localtime') as at,
       owner||'/'||repo as repo, pr_number,
       verdict, score
FROM model_review_runs
ORDER BY created_at DESC LIMIT 10;"
```

## Step 3 — Format and Print

Output a dashboard in this format:

```
═══════════════════════════════════════
  PR Daemon Status  •  <current time>
═══════════════════════════════════════

Queue
  Total discovered : N
  🔄 Reviewing now : N  (repo/PR#)
  ⏳ Pending       : N  (needs_review + prompt_ready)
  👁  Seen only     : N  (not yet queued for review)

Completed Reviews
  Total posted     : N
  ❌ REQUEST_CHANGES : N  (avg score: X.X)
  ✅ APPROVE          : N  (avg score: X.X)
  💬 COMMENT          : N  (avg score: X.X)

Recent
  <repo>#<pr>  <verdict>  score=X.X  <time>
  ...

═══════════════════════════════════════
```

If no reviews have been posted yet, say: "No reviews recorded yet — daemon may still be on its first PR."

## When to auto-print

During `$pr-daemon-loop`, print this dashboard:
- At the start of each new loop cycle (after all PRs in a batch are done)
- When the user asks for it explicitly
- Before entering idle sleep (`sleep 300`)

## Hard Rules

- Read-only. Never write to either database in this skill.
- If a database file is missing, print: "DB not found at <path> — run ./scripts/bootstrap_pr_daemon.sh first"
