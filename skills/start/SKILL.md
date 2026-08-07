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

- `$start` → interval=20, scope=`top8`
- `$start all` → interval=20, scope=`all`
- `$start 5m` / `$start 5` → interval=5, scope=`top8`
- `$start 5m all` / `$start all 5m` → interval=5, scope=`all`
- Interval token: integer, optional trailing `m`. **Snap to the nearest value in
  `{1,2,3,4,5,6,10,12,15,20,30}`** (these are the only minute counts that divide 60 evenly, so
  `N-59/N` spacing stays uniform all the way through the hour boundary — anything else creates
  an uneven gap once per hour). Anything
  unparsable → default 20. If the requested number isn't in the set, silently use the closest one
  and mention the substitution in the Step 5 confirmation.

> **Why the default is 20, not 10** (measured 2026-08-06 over an 11-PR patrol): one 4-round review runs
> **18–26 minutes** wall-clock, and a cycle with several queued PRs ran **70 minutes**. At a 10-minute
> interval every fire that landed during a review was a wasted no-op skip, and the lock — refreshed only
> at cycle start — went stale mid-cycle, so a second cycle could have started concurrently (it had to be
> hand-touched to prevent that). 20 minutes matches one review, so a fire normally lands *between*
> reviews rather than inside one. See the Step 4 lock-refresh rule, which fixes the stale-lock half.

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
- If no patrol job exists → continue into Path B with the defaults (interval=20,
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

## Step 2 — Record the start baseline + clear any stale lock

```bash
mkdir -p /Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/idle_state.py baseline
rm -f /Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon/start-loop.lock
```

The baseline exists for one case: a state dir with **no** recorded runs at all. Without it the
Step-D idle check has no timestamp to measure from, and a brand-new patrol would read as
"idle since the epoch" and stop itself on its first tick.

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
  ⚠️ **The lock must be REFRESHED after every PR, not only at cycle start** (added 2026-08-06 after
  a 70-minute cycle). Its mtime has to mean "time since the last sign of progress"; if it only ever
  means "time since the cycle began", any cycle longer than `3 × interval` lets the lock go stale and
  a second cycle starts *on top of a running one* — exactly what the lock exists to prevent. Today
  that had to be worked around by hand-`touch`ing the lock mid-cycle. The template's Step C now
  touches it after each PR.
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

  🔒 **After EACH PR's verdict is posted, refresh the lock: `touch "$LOCK"`.** Its mtime must mean
  "time since the last sign of progress", not "time since this cycle started" — a cycle with several
  queued PRs runs far longer than `3 × interval` (measured: 70 minutes), and without this the lock
  goes stale mid-cycle and the next fire starts a SECOND cycle on top of the running one.

Step D — Cycle report + idle bookkeeping:

📣 **Report the whole cycle in ONE line**, short names, verdict per PR, nothing else:
  `本轮: kms 193 ❌RC · workbench 85 ❌RC · aura-pkg 34 ✅ — 细节见各 PR comment`
  Use `✅` for APPROVE and `❌RC` for REQUEST_CHANGES. Group PRs under one short name
  when a repo had several (`kms 192 ✅ 193 ❌RC`). Reviewed nothing -> `本轮: 无待审 PR`.
  ⛔ Do NOT restate findings, list rounds, or add sections — the full review already
  lives in the GitHub comment. The ONE exception is the mandatory per-PR self-assessment
  block that pr itself requires; that still applies.

Idle check — ask "how long since the last sign of progress?", NOT "how many cycles reviewed nothing".
Run (NO nested code fence here — this whole template is one fenced block, and an inner fence would
close it early and cut off everything below, including the auto-stop and the lock removal):
  python3 scripts/idle_state.py check --window-minutes 60
  exit 0 -> still active, continue
  exit 3 -> idle for over an hour: apply the DEGRADE LADDER below (default) or auto-stop, per how
            the patrol was started.
  any other exit -> treat as undecidable: do NOT stop the patrol, print the script's stderr.
Remove the lock file (`rm -f "$LOCK"`) on EVERY path above, then append exactly one line:
"start-loop: reviewed <k> PR(s), <minutes_since_progress from idle_state.py> min since last post".
```

### The degrade ladder — idle should slow the patrol down, not kill it (added 2026-08-07)

An hour of quiet usually means "nobody is pushing right now", not "stop watching". Auto-stop then
costs a manual restart the moment work resumes. Default behaviour is therefore to **step the
interval up one rung and keep going**:

```
5m → 10m → 15m → 20m → 30m → (stay at 30m forever)
```

Only these values are usable — they are the minute counts that divide 60 evenly, so `4-59/N`
spacing stays uniform across the hour boundary (see "Parse the invocation").

On `exit 3`:

```
CronList → find the job whose prompt contains "[[start-loop]]" → read its cron expression
  · already `4-59/30 * * * *` → do NOTHING. Print "start-loop: idle 1h+, 已在 30 分钟档，保持。"
  · otherwise → CronDelete it, then CronCreate:
        cron      = `4-59/<next rung> * * * *`
        recurring = true
        prompt    = THE FIRED PROMPT'S OWN FULL TEXT, verbatim (you are holding it)
    Print "start-loop: idle 1h+, 降频到 <next rung> 分钟一次（不停止）。"
```

⛔ **Never `CronDelete` without recreating.** A delete-without-create silently ends a patrol the user
asked to keep running — and because cron jobs are session-only, there is nothing to notice it by.

The fired prompt must carry this ladder inside itself, because `CronCreate` bakes the prompt at
creation time: the job that recreates itself one rung slower has to hand its successor the same
instructions. Keep the ladder text identical across rungs so the only thing that changes is the cron
expression.

**Auto-stop is still available** when the user asks for it ("跑一小时没动静就停"): keep the old
behaviour — `CronDelete` and print `"start-loop: idle 1h+, auto-stopped."` — and say in the Step 5
confirmation which of the two the job is carrying, since the two are indistinguishable from outside.

### The lock: fixed threshold, and ALWAYS remove it on the way out

Two rules learned the hard way on 2026-08-06/07:

- **The staleness threshold is a fixed 3600s — do NOT scale it with the interval.** The old
  "3 × interval" rule is fine at 20m but breaks below it: one 4-round review runs 15–25 minutes, so
  at a 5-minute interval the 900s window expires *mid-review* and the next fire starts a second
  cycle on top of the running one — exactly what the lock exists to prevent. The lock is refreshed
  after every posted PR anyway, so its mtime already means "time since the last sign of progress".
- **`rm -f "$LOCK"` on EVERY exit path, including the one where you stop early with PRs still
  queued.** Observed 2026-08-06: a cycle ended after posting one review with a second PR still in
  the queue, touched the lock as its progress refresh, and returned without removing it — the next
  fire then skipped, and the queued PR waited a full extra cycle for no reason.

> **Why this replaced the `idle_rounds` counter (2026-08-06).** The counter measured *cycles that
> reviewed nothing*, which is not the same thing. That day two PRs were reviewed and posted **at
> the user's direct request**, outside any cron cycle; every cycle still saw `k == 0`, so
> `idle_rounds` climbed 0→3 and the patrol stopped itself an hour after a session that had just
> done real work. `idle_state.py` reads the newest `finished_at` in `model_review_runs` — a review
> that actually posted, whoever triggered it. Same correction as the Step 4 lock: the number has
> to mean "time since the last sign of progress", not "time since some counter was last reset".
> `start-loop-idle.json` is retired. Note the caveat: `CronCreate` bakes the prompt at creation
> time, so a patrol job scheduled BEFORE this change still carries the old `idle_rounds` block and
> keeps writing that file. Nothing changes until `$pr start` is re-run and the job recreated.

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
