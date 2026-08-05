---
name: start
description: "ALIAS — the documented command is now `$pr start [Nm] [all]` / `$pr stop`. This file holds only the cron scheduling mechanics that `$pr start` reads (Steps 1-5). Scope/pin management moved to the `pr` skill and to ONE file, ~/.config/prbot/repos.conf. Still triggered by \"start\", \"$start\", \"开始巡检\" for muscle memory."
origin: pr-daemon
---

# Start — cron mechanics for `$pr start` (not a separate entry point)

> ⚠️ **Consolidated 2026-08-05.** The user-facing command is **`$pr start [Nm] [all]`** /
> **`$pr stop`**. This file is the implementation `$pr start` reads for Steps 1-5.
>
> **Path A (pin management) below is RETIRED** — pins now live in exactly one place,
> `~/.config/prbot/focus-manual.conf` → `repos.conf`, managed by `$pr add` / `$pr remove`.
> Do not use the `start-loop-pinned.json` flow it describes; that file is archived as
> `.retired-20260805` and its contents were migrated. If an invocation starts with
> `add`/`remove`/`pins`, hand it to the `pr` skill instead of following Path A.

This skill never reviews anything itself and never edits `pr`. It only
manages a `CronCreate` job whose fired prompt narrows the repo scope for this cycle
and then hands each in-scope repo to the existing `pr` skill, unmodified.

All "which repos" logic lives in `scripts/start_loop_scope.py`, so the cron prompt
stays short and the selection stays testable outside a fired cycle.

## Parse the invocation

Two families of invocation — **pin management** (Path A) and **scheduling** (Path B).

**Path A — pin management** (the invocation starts with `add` / `remove` / `pins`):

- `$start add kms` / `$start add OWNER/REPO` → pin a repo, then go to Step 0 below.
- `$start remove kms` / `$start unpin kms` → unpin, then Step 0.
- `$start pins` / `$start list` → just print the current pins and stop.

**Path B — scheduling** (everything else):

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

## Step 0 — Pin management (Path A only)

```bash
cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon
python3 scripts/start_loop_scope.py pins add kms       # or: remove kms / list
```

The script resolves a bare name (`kms`) against every repo under `AAStarCommunity`,
`iDoris-ai`, `MushroomDAO`, and `jhfnetboy`; an exact repo-name match wins over a
substring match. **Ambiguous or unknown names exit non-zero and print the candidates
rather than pinning a guess** — relay that to the user and stop; do not pick for them.
A repo outside those four owners must be pinned by its full `OWNER/REPO`.

Pins persist in `.state/pr-daemon/start-loop-pinned.json` and survive `$start`
re-invocations, session restarts, and the 1h auto-stop. They are **never** cleared by
Step 2 — only `$start remove` clears them.

Then:

- If a `[[start-loop]]` cron job already exists → **nothing else to do.** The fired
  prompt recomputes targets from scratch every cycle, so the new pin is picked up on the
  next fire. Confirm the pin plus the existing job's id/interval and stop.
- If no patrol job exists → continue into Path B with the defaults (interval=10,
  scope=`top8`) so the pin actually gets patrolled.

## Step 1 — Check for an existing patrol job (avoid duplicates)

```
CronList
```

- If a job's prompt contains the marker `[[start-loop]]` → tell the user its id / cron / scope, ask: **replace** (CronDelete it, then continue to Step 2) or **leave running** (stop here, do not create a second one).
- If some OTHER recurring job looks like it's already doing ad-hoc PR patrol (text like "PR review 巡检" / "有新PR就审") but has no `[[start-loop]]` marker — flag it by id and ask whether to fold it in (delete the old one) instead of running two patrols in parallel.

Also check for the **legacy Python watcher**, which is not a cron job and so never shows
up in `CronList`:

```bash
pgrep -f "scripts/review_watch.py" || echo "no legacy watcher"
```

If it is running it holds an exclusive lock on `pr-watch.sqlite` — every sync in the patrol
then dies with `database is locked` — *and* it posts its own reviews, so two patrols in
parallel can double-post. Ask the user whether to stop it (`./watch.sh stop`) before
continuing. `./watch.sh stop` kills only the watcher; a `claude -p` review subprocess it
already launched keeps running to completion. Let that one finish rather than leaving
half-written state, and say so.

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
**Do not touch `start-loop-pinned.json`** — pins are intentionally sticky.

## Step 3 — Cron expression

For interval `N` minutes (already snapped to `{1,2,3,4,5,6,10,12,15,20,30}` in Step "Parse the
invocation"): `4-59/N * * * *` (offset 4 avoids the `:00`/`:30` herd effect; since `N` divides 60,
spacing stays exactly `N` minutes across the hour boundary too).

## Step 4 — Create the job

`CronCreate(recurring: true, cron: "<expr from Step 3>", prompt: "<the template below, with <N> substituted and the right Step A+B line kept>")`.

The prompt text below is exactly what fires later, cold, with no memory of this conversation —
it must be fully self-contained. Do not paste any bracketed meta-text like `<N>` into the real
call — substitute it.

Three fixes learned from an adversarial Codex pass on an earlier draft are baked in:

- **Env**: `PR_DAEMON_STATE_DIR` has no default outside `watch.sh` — export it explicitly, or
  pr's own `$PR_DAEMON_STATE_DIR/pr-watch.sqlite` references silently resolve to
  `/pr-watch.sqlite` and every SQLite write in its Step 7 goes nowhere.
- **Overlap lock**: at `4-59/N` this job can fire again before a slow 4-round review finishes.
  Without a lock, two overlapping fires can double-post a review or race the SQLite/idle-JSON
  writes. A simple mtime-based lock file guards this.
- **"Needs review" is read off `last_reviewed_head_oid != head_oid`, never the `status`
  column.** `poll_prs.py`'s unscoped `--sync` marks every open row it didn't just see as
  `closed`, including rows outside the 3 orgs — so a pinned out-of-org repo gets spuriously
  closed by the org-wide sync and "reopened" by its own scoped sync, flipping `status`
  regardless of whether anything actually changed. `start_loop_scope.py targets` reads
  `poll_prs.py`'s queue, which re-derives review-needed from a direct head-oid comparison,
  so it is immune to that churn.

**Template** (substitute `<N>`; keep exactly one Step A+B command, per the scope):
```
[[start-loop]] PR-Daemon 定时巡检 (scope=<top8-recent | all-3-orgs+extra>, interval=<N>m)

cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon

Step 0 — Overlap lock:
LOCK=.state/pr-daemon/start-loop.lock
if [ -f "$LOCK" ] && [ $(( $(date +%s) - $(stat -f%m "$LOCK" 2>/dev/null || echo 0) )) -lt $(( <N> * 60 * 3 )) ]; then
  echo "start-loop: previous cycle still running (lock < 3x interval old), skipping this fire."; exit 0
fi
touch "$LOCK"
(on ANY exit path below, including errors, run `rm -f "$LOCK"` before stopping)

Step A+B — Sync every scope and determine this cycle's target repos (dynamic, recomputed every fire):
  scope top8 ->  python3 scripts/start_loop_scope.py targets --limit 8
  scope all  ->  python3 scripts/start_loop_scope.py targets --all
That one command does the org-wide sync, plus a scoped sync for every pinned /
out-of-org repo (failures isolated per repo — one dead pin never sinks the cycle), and
prints the target list on stdout, one bare `OWNER/REPO` per line, in review order:
  1. every PINNED repo that has pending-review PRs right now (pins never consume a
     default slot — an explicit pin is always scanned), then
  2. the 8 MOST RECENTLY UPDATED repos with pending-review PRs across
     AAStarCommunity / iDoris-ai / MushroomDAO (scope `all`: no cap, plus
     jhfnetboy/NextStop and jhfnetboy/AISalesMan).
Repos with nothing pending never appear — a short list, or an empty one, is correct.
Never pad it out. Use each printed line verbatim; the stderr lines are summaries, not targets.

📣 **Announce the scope before reviewing anything.** The command prints a
`SCOPE: kms#193  📌workbench#85  sdk#315,317` line to stderr, using the short names
jason actually says (`kms` = AirAccount, `sp` = SuperPaymaster, `dvt` =
YetAnotherAA-Validator, …; `📌` marks a pinned repo). Echo that as ONE line to the
user, e.g. `本轮盯: kms#193  📌workbench#85`. Do not expand it into a table or restate
the full OWNER/REPO paths.

Step C — Review each target repo, one at a time, not batched:
For each repo from Step A+B's stdout, in the order printed:
  📣 **Before starting each PR, print exactly one line naming it**, using the short name:
  `▶ review kms#193`. Nothing else — no plan, no preamble, no restating the PR title.
  Get the short name with `python3 scripts/start_loop_scope.py nick <OWNER/REPO>`
  (it also appears in the SCOPE line).

  invoke the pr skill scoped to that repo (Skill tool, skill="pr",
  args="<OWNER/REPO>"), which runs its full unmodified Steps 0-8 (R1a/R1b DeepSeek -> triage
  -> R2 Opus / R3 Codex if 4-round -> R4 verdict -> post -> record) for every PR in that
  repo's queue. Override ONLY pr's Step 8 tail: once that repo's queue is empty,
  RETURN instead of "sleep 300 and re-scan" — this outer cron will wake the patrol again next
  cycle, so an inner infinite wait would just block forever for nothing.
  ⚠️ EXCEPTION for any target repo NOT under AAStarCommunity / iDoris-ai / MushroomDAO:
  pr's own ABSOLUTE CONSTRAINT #4 says "3 orgs only, never jhfnetboy personal
  PRs" — that constraint does NOT apply to a repo that reached this list, because a repo
  only gets here by being explicitly pinned by the user (`$start add`) or by being one of
  the two standing scope-`all` exceptions (jhfnetboy/NextStop, jhfnetboy/AISalesMan, where
  clestons already holds collaborator access). When invoking pr for such a repo,
  explicitly state in the invocation that this is a pre-approved exception to constraint #4
  for this repo only, so it proceeds instead of skipping. Do not generalize the exception to
  any repo that is not on this cycle's printed target list.
  Keep a running total `k` of PRs actually reviewed (posted a verdict for) across all repos
  this cycle, then move to the next target repo.

Step D — Cycle report + idle bookkeeping:

📣 **Report the whole cycle in ONE line**, short names, verdict per PR, nothing else:
  `本轮: kms 193 ❌RC · workbench 85 ❌RC · aura-pkg 34 ✅ — 细节见各 PR comment`
  Use `✅` for APPROVE and `❌RC` for REQUEST_CHANGES. Group PRs under one short name
  when a repo had several (`kms 192 ✅ 193 ❌RC`). Reviewed nothing -> `本轮: 无待审 PR`.
  ⛔ Do NOT restate findings, list rounds, or add sections — the full review already
  lives in the GitHub comment. The ONE exception is the mandatory per-PR self-assessment
  block that pr itself requires; that still applies.

Read .state/pr-daemon/start-loop-idle.json ({"idle_rounds": N}).
  - k == 0 this cycle -> idle_rounds += 1
  - k >= 1 this cycle -> idle_rounds = 0
Write the updated value back to the same file. Remove the lock file (`rm -f "$LOCK"`).
If idle_rounds * <N> >= 60:
  CronList -> find the job whose prompt contains "[[start-loop]]" -> CronDelete it.
  Print: "start-loop: idle 1h+, auto-stopped." Then stop — do not schedule anything else.
Else append exactly one line: "start-loop: reviewed <k> PR(s), idle_rounds=<idle_rounds>/<60/N rounded>".
```

## Step 5 — Confirm to the user

Report: interval, scope, the current pins (`python3 scripts/start_loop_scope.py pins list`),
this cycle's resolved target repos **by short name** (run `targets` once and echo its
`SCOPE:` line), and the cron job id. Remind them: **`CronCreate` jobs are
session-only and auto-expire after 7 days** — if this Claude Code session ends the patrol stops;
re-run `$start` in a fresh session to resume it. Pins, unlike the job, survive on disk.

## Notes

- This skill deliberately does not touch `scripts/review_watch.py` / `watch.sh` (the legacy Python
  watcher) — those remain independent, optional entry points, and Step 1 only asks about stopping
  one that is already running. `$start` is the Claude-Code-native scheduler for the primary
  DeepSeek-executor pipeline.
- `pr` itself is never edited by this skill, per standing project rule — `$start` only
  decides *when* and *for which repos* it gets invoked.
- `pr` is globally `"off"` in `~/.claude/settings.json`; this repo opts back in via a
  tracked `.claude/settings.json`. If Step C ever fails with "disabled for model invocation in
  skillOverrides settings", that opt-in is missing or a session-local override shadows it.
