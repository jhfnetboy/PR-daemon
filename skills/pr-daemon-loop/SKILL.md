---
name: pr-daemon-loop
description: Full 24/7 autonomous PR review loop (v2). Claude Code (Max subscription) orchestrates a 3-round PK review with smart 2/4-round triage. DeepSeek does cheap grunt work + initial review, Claude challenges, Codex PKs, Opus makes the final verdict. Use when the user says "run PR daemon", "start 24/7 review", "用 $pr-daemon-loop 开始", "/pr-daemon-loop", or "start the review loop".
origin: pr-daemon
---

<!-- INSTALL NOTE
When installed globally via install-skills.sh --global, PR_DAEMON_ROOT is patched to the absolute
path of the PR-Daemon repo. When used directly in the project, run from the PR-Daemon root directory.
Full architecture rationale: see PR_DAEMON_ROOT/DESIGN.md
-->

# PR Daemon Loop (v2 — Max-subscription driven, 3-round PK + 2/4 triage)

> ⛔ **ABSOLUTE CONSTRAINT #1 — No Merge**
> Review-only system. NEVER merge any PR. Even after APPROVE, merging is the author's/maintainer's call.
> Allowed GitHub writes: post review / request changes / approve. Nothing else. No `gh pr merge`.
>
> ⛔ **ABSOLUTE CONSTRAINT #2 — One PR at a time, individually**
> Each PR runs the full pipeline independently. No batch-scan-then-bulk-approve.
>
> ⛔ **ABSOLUTE CONSTRAINT #3 — Final verdict is yours (Claude Code), but respect the panel**
> YOU make the final APPROVE/REQUEST_CHANGES call. But you MUST respect DeepSeek's and especially
> Codex's feedback — address Codex's points one by one; do not dismiss a Codex finding without
> concrete counter-evidence. Codex is the senior adversary.
>
> ⛔ **ABSOLUTE CONSTRAINT #4 — 3 orgs only**
> Only review PRs in `AAStarCommunity`, `AuraAIHQ`, `MushroomDAO`. Never review personal (jhfnetboy) PRs.

## Roles & Models

| Role | Model | Cost | Decides verdict? |
|------|-------|------|------------------|
| Grunt work + initial review | DeepSeek API | ~$0.001/PR | ❌ |
| Challenge / orchestration | Sonnet (this session) | subscription | ❌ |
| PK adversary | Codex (Agent tool) | Plus $20/mo | ❌ |
| **Final verdict** | **Opus subagent** (4-round) or Sonnet (2-round) | subscription | ✅ |

**Sonnet→Opus**: run the loop on Sonnet for cost. For 4-round PRs, spawn an Opus subagent
(`Agent(model="opus")`) for the final high-stakes verdict. 2-round PRs: Sonnet decides directly.

## The Loop

```
poll_prs.py → for each PR:
  R1  DeepSeek initial review + triage proposal
  ▼   triage confirm (2-round vs 4-round)
  ├─ 2-round: Sonnet verdict
  └─ 4-round: R2 Sonnet challenge → R3 Codex PK → Opus verdict
  ▼   score DeepSeek, record triage, post, next PR
```

## Token discipline (read first)

To save tokens: **DeepSeek does the heavy lifting, Claude only does hard judgment.**
- Read/compress the diff **ONCE**. Pass the SAME compressed diff forward to every round.
- Subagents (Codex R3, Opus verdict) get the diff + prior findings **inline in the prompt** —
  never tell them to re-fetch `gh pr diff`.
- Use the concise templates in `config/review_templates.md`. No preamble, no postamble, no praise.
- Each round outputs **deltas only** (confirm/reject/add), not a full re-derivation.

## Step 1 — Sync + discover PRs

**At the start of every loop cycle, run with `--sync`** to mirror ALL open PRs into SQLite
(every author, including bots — the goal is to clear every PR). This keeps `pr-watch.sqlite`
an accurate live snapshot: new→`needs_review`, head-moved→`needs_review`, gone→`closed`.

**Org-scan mode** (all 3 orgs, ALL authors incl. dependabot):
```bash
python3 PR_DAEMON_ROOT/scripts/poll_prs.py --sync --max 200
```
**Single-repo mode** (one repo, all its open PRs):
```bash
python3 PR_DAEMON_ROOT/scripts/poll_prs.py --repo OWNER/REPO --sync --max 50
```
Output: `total_open`, `sync` counts (inserted/updated/closed), and the review `queue`
(new / head-changed only). The DB stores author + reviewer + status for every PR.
The user may pass a repo via `/pr-daemon-loop OWNER/REPO` or extra instructions — honor them.

After this, work the queue. To see the full picture any time: `$pr-daemon-status`.

## Step 2 — Get & compress the diff

```bash
gh pr diff N --repo OWNER/REPO > /tmp/pr-N.diff
# compress large diffs to fit token budget (drops binary/lock/generated, ranks code first)
python3 PR_DAEMON_ROOT/scripts/compress_diff.py --file /tmp/pr-N.diff --budget 80000 --stats > /tmp/pr-N-compressed.diff
```

## Step 3 — R1: DeepSeek does the heavy lifting

DeepSeek (~$0.001/PR) produces ALL the mechanical work in one call: per-file summary,
candidate findings, triage class, AND a draft comment skeleton. Claude works FROM this,
not from scratch. Call DeepSeek directly with the R1 template (`config/review_templates.md`):

```bash
# DeepSeek R1 — pass the compressed diff, get FILES/FINDINGS/TRIAGE/SKELETON
python3 PR_DAEMON_ROOT/scripts/deepseek_review.py \
  --diff-file /tmp/pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/pr-N-r1.md
```
(If `deepseek_review.py` is absent, fall back to `skills/pk-review/scripts/local_review.py`.)

DeepSeek's output is the working base: `FILES`, `FINDINGS` (with severity+fix), `TRIAGE`
(trivial/significant), `SKELETON` (4-line draft comment). **Do not re-read the diff in full
afterward** — validate findings and spot-check only the hunks tied to high-sev/security items.

## Step 4 — Triage confirm: 2-round or 4-round?

YOU (Sonnet) confirm the class. **Criteria (see DESIGN.md §4):**

**2-round (low risk) — needs ALL:**
- type is docs / chore / style / typo / comments / formatting
- dependency bump (dependabot/renovate)
- License / CODEOWNERS / README / badge
- does NOT touch `src/` `contracts/` `lib/` real logic
- NO new public API / schema / migration

**4-round (high risk) — ANY triggers it:**
- type is feat (new feature) / major refactor
- touches core code: `src/` `contracts/` `lib/` real logic
- 🔴 **security-sensitive (HARD rule)**: `.sol` / auth / crypto / payment / token / permission / access-control
- concurrency / state machine / data persistence / DB migration
- API contract / interface / schema change
- deletes tests / disables security checks / cross-module sweep

**Safety bias:**
- 🔴 security-sensitive hard rule → force 4-round, DO NOT accept DeepSeek downgrade
- uncertain (can't tell if it's significant) → escalate to 4-round (over-review beats under-review)
- confirmed low risk → 2-round

Record the decision:
```bash
python3 PR_DAEMON_ROOT/scripts/triage_db.py record \
  --repo OWNER/REPO --pr N --head-oid HEAD \
  --rounds 2 --rationale "docs-only chore, no src touch" --signals "type:docs,no-core-code"
```

## Step 5a — 2-round path (low risk)

You (Sonnet) directly review the diff, fold in DeepSeek's valid findings, and decide the verdict.
No Codex, no Opus. Go to Step 6.

## Step 5b — 4-round path (high risk)

**R2 — Sonnet challenge (deltas only):** work FROM DeepSeek's FINDINGS, don't re-derive.
Spot-check only high-sev/security hunks. Output compactly: `CONFIRM <ids>` / `REJECT <id — why>` /
`ADD <[Sev] file:line — issue | fix>`. (Template: R2 in `config/review_templates.md`.)

**R3 — Codex PK (MANDATORY for 4-round):** pass the diff + R2 finding list **inline** so Codex
does NOT re-fetch. Use `codex:codex-rescue`:
```
Agent(subagent_type="codex:codex-rescue", prompt="""
PK CHALLENGE OWNER/REPO#N. Diff and findings are below — do NOT run gh pr diff.
Per finding return ONE: [CHALLENGE|CONFIRM|MISSED] id — reason <=20 words.
DIFF:
<paste compressed diff>
FINDINGS (post-R2):
<compact list>
Return ONLY the structured critique. Do not post to GitHub.
""")
```
If Codex quota is exhausted → it auto-falls-back to Tier-3; or Sonnet self-challenges once. Note which.

**Final verdict — Opus subagent (fixed template, no essay):** pass COMPACT round summaries, not
full re-explanations. Demand the fixed template:
```
Agent(subagent_type="general-purpose", model="opus", prompt="""
Final authority on OWNER/REPO#N. Decide from these compact rounds. Respect Codex point-by-point
(no dismissal without concrete counter-evidence). Output ONLY this template, no prose:
VERDICT: APPROVE | REQUEST_CHANGES
BLOCKING: <[Sev] file:line — issue | fix>   (empty if APPROVE)
CONFIRMED: <[Sev] file:line — issue | fix>
REJECTED: <finding — reason>
SUGGESTIONS: <=3 bullets, optional
ROUNDS — R1(DeepSeek): <...>  R2(Sonnet): <...>  R3(Codex): <...>
""")
```

## Step 6 — Post the verdict

Verdict MUST be **APPROVE** or **REQUEST_CHANGES** — never COMMENT limbo.
- REQUEST_CHANGES: include challenging, specific objections (problem + trigger scenario + fix).
- APPROVE: may still append enhancement / polish suggestions.

```bash
bash PR_DAEMON_ROOT/scripts/post_pr_review.sh \
  --repo OWNER/REPO --pr N --body-file /tmp/review-N.md \
  --request-changes   # or --approve
gh api user -q .login   # verify restored to main account
```
Always use `post_pr_review.sh` (account switch). Never `gh pr review` directly.

## Step 7 — Score DeepSeek + record

```bash
# score DeepSeek's R1 work for the improvement loop
python3 PR_DAEMON_ROOT/scripts/model_eval_db.py record-run \
  --owner OWNER --repo REPO --pr-number N --head-oid HEAD \
  --score SCORE --verdict VERDICT \
  --useful-findings "..." --false-positives "..." --misses "..."

# update watcher state
sqlite3 "$PR_DAEMON_STATE_DIR/pr-watch.sqlite" \
  "UPDATE pr_watch_targets SET last_reviewed_head_oid='HEAD', status='STATUS', \
   last_reviewed_at=CURRENT_TIMESTAMP, review_decision='VERDICT' WHERE repo='OWNER/REPO' AND pr_number=N;"

# token cost
python3 PR_DAEMON_ROOT/scripts/token_cost.py --add INPUT_TOKENS OUTPUT_TOKENS
```

## Step 8 — Per-PR report + loop

Print after every PR:
```
📊 OWNER/REPO#N  VERDICT  [Nround]  PK: <summary>
📊 PR status: open N, reviewed M [changes: X, approve: Y]
💰 this PR ~Nk tok | cumulative $X.XX
```
Then next PR. When queue empty: re-poll; if nothing new, `sleep 300` and re-scan.

## Triage validation (run periodically)

```bash
# audit a past 2-round PR by running full 4-round retroactively
python3 PR_DAEMON_ROOT/scripts/triage_db.py audit --repo OWNER/REPO --pr N --found-issue true|false
# if a 2-round APPROVE later gets human RC / bug:
python3 PR_DAEMON_ROOT/scripts/triage_db.py flag-miss --repo OWNER/REPO --pr N --note "..."
# check effectiveness (target false-negative < 5%)
python3 PR_DAEMON_ROOT/scripts/triage_db.py report
```
If false-negative rate ≥ 5% → tighten 2-round criteria, push more PRs to 4-round.

## Mandatory Per-PR Checklist

```
[ ] poll_prs.py surfaced this PR (new/head-changed, in-scope org)
[ ] compressed the diff if large
[ ] R1: DeepSeek initial review + triage proposal
[ ] confirmed 2/4-round (security hard-rule → force 4; uncertain → escalate)
[ ] recorded triage decision (triage_db.py)
[ ] 4-round: ran R2 Sonnet challenge + R3 Codex PK + Opus verdict
[ ] verdict is APPROVE or REQUEST_CHANGES (not COMMENT)
[ ] respected Codex's points one by one
[ ] posted via post_pr_review.sh, verified account restored
[ ] scored DeepSeek (model_eval_db) + updated pr_watch_targets
[ ] printed per-PR report (status counter + token cost)
```

## Hard Rules

- **NEVER MERGE.** `gh pr merge` forbidden.
- **Final verdict is Claude Code's**, but respect DeepSeek + Codex (especially Codex) feedback.
- **Security-sensitive PRs always go 4-round** — no downgrade.
- **Never COMMENT-limbo** — always APPROVE or REQUEST_CHANGES.
- **Never `gh pr review` directly** — always `post_pr_review.sh`.
- **3 orgs only** — never personal PRs.
- **Always score DeepSeek + record triage** for the improvement & validation loops.
