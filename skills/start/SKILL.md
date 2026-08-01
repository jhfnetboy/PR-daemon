---
name: start
description: Start (or reconfigure) a recurring background PR-patrol job. Default = every 10 min, dynamic top-8 most-pending-review repos across the 3 orgs. "$start all" = full 3-org scan + jhfnetboy/NextStop + jhfnetboy/AISalesMan. "$start Nm [all]" overrides the interval. Self-stops after 1h with nothing to review. Delegates every actual review to the unmodified pr-daemon-loop skill — this skill only schedules and scopes. Triggered by "start", "$start", "开始巡检", "巡检安排".
origin: pr-daemon
---

# Start — scheduled PR patrol launcher

This skill never reviews anything itself and never edits `pr-daemon-loop`. It only
manages a `CronCreate` job whose fired prompt narrows the repo scope for this cycle
and then hands each in-scope repo to the existing `pr-daemon-loop` skill, unmodified.

## Parse the invocation

- `$start` → interval=10, scope=`top8`
- `$start all` → interval=10, scope=`all`
- `$start 5m` / `$start 5` → interval=5, scope=`top8`
- `$start 5m all` / `$start all 5m` → interval=5, scope=`all`
- Interval token: integer, optional trailing `m`. **Snap to the nearest value in
  `{1,2,3,4,5,6,10,12,15,20,30}`** (these are the only minute counts that divide 60 evenly, so
  `N-59/N` spacing stays uniform all the way through the hour boundary — anything else creates
  an uneven gap once per hour and also breaks the `idle_rounds * N >= 60` self-stop math). Anything
  unparsable → default 10. If the requested number isn't in the set, silently use the closest one
  and mention the substitution in the Step 5 confirmation.

## Step 1 — Check for an existing patrol job (avoid duplicates)

```
CronList
```

- If a job's prompt contains the marker `[[start-loop]]` → tell the user its id / cron / scope, ask: **replace** (CronDelete it, then continue to Step 2) or **leave running** (stop here, do not create a second one).
- If some OTHER recurring job looks like it's already doing ad-hoc PR patrol (text like "PR review 巡检" / "有新PR就审") but has no `[[start-loop]]` marker — flag it by id and ask whether to fold it in (delete the old one) instead of running two patrols in parallel.

## Step 2 — Reset idle bookkeeping + clear any stale lock

```bash
mkdir -p /Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon
cat > /Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon/start-loop-idle.json <<'EOF'
{"idle_rounds": 0}
EOF
rm -f /Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon/start-loop.lock
```

Clearing the lock here matters because it's the one file a crashed/killed prior fire could have
left behind — a fresh `$start` invocation should never inherit a stale lock from a dead cycle.

## Step 3 — Cron expression

For interval `N` minutes (already snapped to `{1,2,3,4,5,6,10,12,15,20,30}` in Step "Parse the
invocation"): `4-59/N * * * *` (offset 4 avoids the `:00`/`:30` herd effect; since `N` divides 60,
spacing stays exactly `N` minutes across the hour boundary too).

## Step 4 — Create the job

`CronCreate(recurring: true, cron: "<expr from Step 3>", prompt: "<one of the two full templates below, with <N> substituted>")`.

The prompt text below is exactly what fires later, cold, with no memory of this conversation —
it must be fully self-contained. Pick **one** of the two complete templates by scope; do not
merge them, and do not paste any bracketed meta-text like `<N>` into the real call — substitute it.

Both templates share three fixes learned from an adversarial Codex pass on an earlier draft:

- **Env**: `PR_DAEMON_STATE_DIR` has no default outside `watch.sh` — export it explicitly, or
  pr-daemon-loop's own `$PR_DAEMON_STATE_DIR/pr-watch.sqlite` references silently resolve to
  `/pr-watch.sqlite` and every SQLite write in its Step 7 goes nowhere.
- **Overlap lock**: at `4-59/N` this job can fire again before a slow 4-round review finishes.
  Without a lock, two overlapping fires can double-post a review or race the SQLite/idle-JSON
  writes. A simple mtime-based lock file guards this.
- **"Needs review" must be read off `last_reviewed_head_oid != head_oid`, not the `status`
  column, for repo-selection purposes.** `poll_prs.py`'s unscoped `--sync` marks every open row
  it didn't just see as `closed`, including rows outside the 3 orgs — so in scope `all`, the
  org-wide sync spuriously closes `jhfnetboy/NextStop` / `jhfnetboy/AISalesMan`, and the next
  single-repo sync "reopens" them, flipping `status` to `needs_review` regardless of whether
  anything actually changed. (Verified this is cosmetic, not a real re-review risk:
  `poll_prs.py`'s own `build_queue()` independently re-derives the actual review queue from a
  direct head-oid comparison every time it runs — including inside pr-daemon-loop's own Step 1 —
  so a spurious `status` flip alone never causes a real re-review. The fix here is still worth
  keeping: without it, Step B would list those two repos as targets on every cycle even when
  there's nothing to do, invoking pr-daemon-loop only for it to sync, find an empty queue, and
  return — comparing head oids up front skips that wasted round-trip.)

**Template — scope `top8` (default):**
```
[[start-loop]] PR-Daemon 定时巡检 (scope=top8-pending, interval=<N>m)

cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon

Step 0 — Overlap lock:
LOCK=.state/pr-daemon/start-loop.lock
if [ -f "$LOCK" ] && [ $(( $(date +%s) - $(stat -f%m "$LOCK" 2>/dev/null || echo 0) )) -lt $(( <N> * 60 * 3 )) ]; then
  echo "start-loop: previous cycle still running (lock < 3x interval old), skipping this fire."; exit 0
fi
touch "$LOCK"
(on ANY exit path below, including errors, run `rm -f "$LOCK"` before stopping)

Step A — Sync org-wide state:
python3 scripts/poll_prs.py --sync --max 200

Step B — Determine this cycle's target repos (dynamic, recompute every fire):
sqlite3 .state/pr-daemon/pr-watch.sqlite "
  SELECT repo FROM pr_watch_targets
  WHERE state='open' AND is_draft=0
    AND (last_reviewed_head_oid IS NULL OR last_reviewed_head_oid != head_oid)
    AND (repo LIKE 'AAStarCommunity/%' OR repo LIKE 'iDoris-ai/%' OR repo LIKE 'MushroomDAO/%')
  GROUP BY repo ORDER BY COUNT(*) DESC, MAX(pr_number) DESC LIMIT 8;"
Repos with the most pending-review (non-draft, head-moved-or-new) PRs right now win a slot.
Fewer than 8 such repos -> shorter list, that's fine -- never pad it out with idle repos.
Output is one repo per line (bare `OWNER/REPO`, nothing else) -- use each line verbatim.

Step C — Review each target repo, one at a time, not batched:
For each repo from Step B's output, in the order returned:
  invoke the pr-daemon-loop skill scoped to that repo (Skill tool, skill="pr-daemon-loop",
  args="<OWNER/REPO>"), which runs its full unmodified Steps 0-8 (R1a/R1b DeepSeek -> triage
  -> R2 Opus / R3 Codex if 4-round -> R4 verdict -> post -> record) for every PR in that
  repo's queue. Override ONLY pr-daemon-loop's Step 8 tail: once that repo's queue is empty,
  RETURN instead of "sleep 300 and re-scan" — this outer cron will wake the patrol again next
  cycle, so an inner infinite wait would just block forever for nothing.
  Keep a running total `k` of PRs actually reviewed (posted a verdict for) across all repos
  this cycle, then move to the next target repo.

Step D — Idle bookkeeping:
Read .state/pr-daemon/start-loop-idle.json ({"idle_rounds": N}).
  - k == 0 this cycle -> idle_rounds += 1
  - k >= 1 this cycle -> idle_rounds = 0
Write the updated value back to the same file. Remove the lock file (`rm -f "$LOCK"`).
If idle_rounds * <N> >= 60:
  CronList -> find the job whose prompt contains "[[start-loop]]" -> CronDelete it.
  Print: "start-loop: idle 1h+, auto-stopped." Then stop — do not schedule anything else.
Else print exactly one line: "start-loop: reviewed <k> PR(s), idle_rounds=<idle_rounds>/<60/N rounded>".
```

**Template — scope `all`:**
```
[[start-loop]] PR-Daemon 定时巡检 (scope=all-3-orgs+extra, interval=<N>m)

cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon

Step 0 — Overlap lock: identical to the top8 template's Step 0 (same lock file).

Step A — Sync every scope:
python3 scripts/poll_prs.py --sync --max 200
python3 scripts/poll_prs.py --repo jhfnetboy/NextStop --sync --max 50
python3 scripts/poll_prs.py --repo jhfnetboy/AISalesMan --sync --max 50
(the org-wide sync above will spuriously flip jhfnetboy/NextStop and jhfnetboy/AISalesMan to
"closed" for a moment since they're outside its 3-org scope, then the two --repo syncs reopen
them — this is expected, harmless churn on the `status` column only; Step B below does not
read `status`, so it is unaffected.)

Step B — Determine this cycle's target repos:
sqlite3 .state/pr-daemon/pr-watch.sqlite "
  SELECT DISTINCT repo FROM pr_watch_targets
  WHERE state='open' AND is_draft=0
    AND (last_reviewed_head_oid IS NULL OR last_reviewed_head_oid != head_oid)
    AND (repo LIKE 'AAStarCommunity/%' OR repo LIKE 'iDoris-ai/%' OR repo LIKE 'MushroomDAO/%'
         OR repo IN ('jhfnetboy/NextStop','jhfnetboy/AISalesMan'));"
Output is one repo per line (bare `OWNER/REPO`) -- use each line verbatim.

Step C — Review each target repo, one at a time, not batched:
For each repo from Step B's output:
  invoke the pr-daemon-loop skill scoped to that repo (Skill tool, skill="pr-daemon-loop",
  args="<OWNER/REPO>"), which runs its full unmodified Steps 0-8 for every PR in that repo's
  queue. Override ONLY pr-daemon-loop's Step 8 tail: once that repo's queue is empty, RETURN
  instead of "sleep 300 and re-scan" — this outer cron will wake the patrol again next cycle.
  ⚠️ EXCEPTION for repo == jhfnetboy/NextStop or jhfnetboy/AISalesMan ONLY: pr-daemon-loop's
  own ABSOLUTE CONSTRAINT #4 says "3 orgs only, never jhfnetboy personal PRs" — that constraint
  does NOT apply to these two specific repos. They are a standing, user-approved exception
  (clestons already holds collaborator access on both; see the project's own memory record).
  When invoking pr-daemon-loop for exactly these two repos, explicitly state in the invocation
  that this is a pre-approved exception to constraint #4 for this repo only, so it proceeds
  instead of skipping. Every other jhfnetboy/* repo is still off-limits — do not generalize
  this exception.
  Keep a running total `k` of PRs actually reviewed (posted a verdict for) across all repos
  this cycle, then move to the next target repo.

Step D — Idle bookkeeping: identical to the top8 template's Step D.
```

## Step 5 — Confirm to the user

Report: interval, scope (list the 8 repos if `top8`, or "3 orgs + NextStop + AISalesMan" if `all`),
the cron job id, and remind them: **`CronCreate` jobs are session-only and auto-expire after 7 days** —
if this Claude Code session ends, the patrol stops; re-run `$start` in a fresh session to resume it.

## Notes

- This skill deliberately does not touch `scripts/review_watch.py` / `watch.sh` (the legacy Python
  watcher) — those remain independent, optional entry points. `$start` is the Claude-Code-native
  scheduler for the primary DeepSeek-executor pipeline.
- `pr-daemon-loop` itself is never edited by this skill, per standing project rule — `$start` only
  decides *when* and *for which repos* it gets invoked.
