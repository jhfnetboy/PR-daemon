---
name: pr
description: "PR review + scan-scope management. Subcommands: `$pr list` shows the scan scope (default 8 slots + pinned extras), `$pr add/remove <repo>` pins/unpins a repo (one list: ~/.config/prbot/repos.conf), `$pr start [Nm]` / `$pr stop` manage the recurring patrol cron, `$pr OWNER/REPO[#N]` reviews one repo/PR, bare `$pr` runs the full 24/7 autonomous review loop (v4). Sonnet=pure executor, DeepSeek=dual-pass R1 (full+security parallel), Opus=R2 strategic independent reviewer + final verdict, Codex=R3 adversarial PK against Opus findings. Evaluate vs v3 after each PR."
origin: pr-daemon
---

<!-- ROLLBACK:
  v4 → v3: cp ~/.claude/skills/pr/SKILL.md.bak-v3-20260619 ~/.claude/skills/pr/SKILL.md
  v3 → v2: cp ~/.claude/skills/pr/SKILL.md.bak-20260614 ~/.claude/skills/pr/SKILL.md
-->

# PR Daemon Loop (v4 — Opus strategic R2 + dual DeepSeek + Sonnet executor)

## Invocation — dispatch on the argument FIRST

`$pr` takes an optional subcommand. Check it **before** doing anything else; only the
no-subcommand forms run the review pipeline below.

| Invocation | Do this |
|---|---|
| `$pr list` | Print the scan scope, then **stop** (no review). See below. |
| `$pr add <name>` / `$pr remove <name>` | Pin/unpin a repo, then **stop**. |
| `$pr start [Nm] [all]` | Start/reconfigure the recurring patrol cron, then **stop**. |
| `$pr stop` | Delete the patrol cron, then **stop**. |
| `$pr` | Org-scan mode — run the pipeline over the current scan scope. |
| `$pr OWNER/REPO` | Single-repo mode — every open PR in that repo. |
| `$pr OWNER/REPO#N` | Single-PR mode. |

```bash
cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon

# $pr list — default slots (8 most-recently-updated repos WITH pending PRs) + pinned extras
python3 scripts/start_loop_scope.py list

# $pr add kms  /  $pr remove kms
python3 scripts/start_loop_scope.py pins add kms
python3 scripts/start_loop_scope.py pins remove kms
```

Relay the `list` output as-is — it already distinguishes default slots from pinned extras,
and deliberately shows pins that currently have **no** pending PR (hiding them reads as if
the pin was dropped). An ambiguous/unknown name on `add` exits non-zero and prints the
candidates: relay them and stop, **do not pick one for the user**.

### ⛔ ONE list, ONE command (consolidated 2026-08-05)

**Scope lives in exactly one file: `~/.config/prbot/repos.conf`.** Everything reads it
through `scripts/scan_scope.py` — `poll_prs.py`, `poll_fix_queue.py`, `review_queue.py`,
`start_loop_scope.py`. Hand-edits go to `~/.config/prbot/focus-manual.conf` (or just run
`$pr add`, which writes it AND regenerates `repos.conf`). **Never hand-edit `repos.conf`** —
its own header says so and `refresh-scan-focus.sh` overwrites it.

> 这条规则替换掉了什么(三个互相矛盾的 scope 来源)：见 `references/incidents.md#scope-three-sources`。

`scan_scope.orgs()` (swept wholesale) comes from `candidate-orgs.conf`, NOT from the owners
in `repos.conf` — otherwise listing `jhfnetboy/CMIC` would sweep all of that account's
hundreds of personal repos. Personal repos on the list are queried individually
(`scan_scope.extra_repos()`), which is what finally made them visible to the org-wide sweep
instead of requiring an explicit `--repo`.

### `$pr start [Nm] [all]` / `$pr stop` — the recurring patrol

Scheduling mechanics (dedupe against an existing job, idle bookkeeping, the cron expression,
the fired-prompt template, the 1-hour idle self-stop) live in `.claude/skills/start/SKILL.md`
— **read it and follow Steps 1-5 there**, skipping its "Path A / pin management" section,
which this file now owns. `$pr stop` = its Step-5 note: `CronList` → find the job whose
prompt contains `[[start-loop]]` → `CronDelete` it.

That file is implementation detail for this subcommand, not a second entry point. `$start`
still resolves to it for muscle memory, but **`$pr start` is the documented command** and the
one to tell the user about.

> 📁 **事故档案在 `references/incidents.md`。** 这份文件只留**可执行的规程**;每条规则是哪次事故买来的、
> 当时测到了什么、它替换掉了什么、怎么回滚,都在那里,由正文里的 `references/incidents.md#<锚>` 指过去。
> **规则一字未动,只是搬了家**(2026-08-28 重构;`SKILL.md.bak-before-placement-20260828` 是重构前的全文)。
> 执行时不需要读档案;要判断「这条规则还成不成立 / 能不能改」时再去读。

> ⛔ **ABSOLUTE CONSTRAINT #1 — Review only, NEVER merge**
> Pure reviewer. NEVER merge any PR regardless of author (human or bot).
> Merging is handled by `$pr-fix` after its review loop completes.
> Allowed GitHub writes: post review / request changes / approve. Nothing else.
>
> ⛔ **ABSOLUTE CONSTRAINT #2 — One PR at a time, individually**
> Each PR runs the full pipeline independently. No batch-scan-then-bulk-approve.
>
> ⛔ **ABSOLUTE CONSTRAINT #3 — Opus is final authority for 4-round; respect Codex point-by-point**
> Opus makes the final APPROVE/REQUEST_CHANGES call on 4-round PRs.
> Do NOT dismiss a Codex finding without concrete counter-evidence.
>
> ⛔ **ABSOLUTE CONSTRAINT #4 — configured scopes only (allowlist)**
> Review PRs only in the ONE configured scan scope (`~/.config/prbot/repos.conf`, resolved via `scripts/scan_scope.py`): the `AAStarCommunity`
> / `iDoris-ai` / `MushroomDAO` orgs, PLUS any personal `owner/repo` explicitly added to that file as
> an include-list entry (e.g. `jhfnetboy/CMIC`). Personal repos are NOT scanned by default (there are
> hundreds); the include-list is the allowlist. Never review a personal PR that is not on that list.
>
> ⛔ **ABSOLUTE CONSTRAINT #5 — DeepSeek R1a runs by default; exactly TWO structural exemptions**
> (这条从「绝不可跳过」收敛成「两条结构性豁免」的由来：见 `references/incidents.md#constraint5-history`。)
>
> **Run R1a on every round EXCEPT these two, where 0/N is structural rather than unlucky:**
> 1. **Pure-docs / ledger PRs** — on a long document it has fabricated every `file:line` anchor it emitted.
> 2. **Incremental rounds whose increment is fixes to YOUR OWN prior findings** — the findings are
>    already known and written down, so there is nothing left for it to independently find.
>
> Everywhere else — new PR, real code diff, any increment that adds new logic — **run it**. "I can do
> a good review without it" is still NOT a valid reason to skip: on a real code diff its hit rate is
> low but non-zero, and the cost is one parallel call. Skipping it *there* has burned us before
> (AirAccount#191 re-review).
>
> (这两条豁免是 170 轮记录得出的；它命中过哪几条、两条豁免各自的实测数据：见
> `references/incidents.md#r1-170-round-record`。)
> After R1a returns, verify each of its findings against the actual code/diff yourself (don't just
> trust it) and append ONE explicit line to the self-assessment (Step 8): a 1-5 rating of DeepSeek
> v4-flash's performance THIS round + one sentence why (findings that held up under verification /
> false positives / anything a later round — Opus R2, Codex R3, or your own reading — caught that
> flash missed entirely), plus, when something concrete comes to mind, a one-line suggestion for how
> to get more signal out of it next time (tighter prompt, more context, narrower diff scope, etc.).

> ⛔ **ABSOLUTE CONSTRAINT #6 — you are HEADLESS: never end a run by asking a question**
> You run under `claude --print` from a background daemon. **Nobody reads your output while it runs
> and nobody can answer you.** A run that ends in a question produces no review, burns the whole
> ~20-minute cycle, blocks every PR queued behind it, and — since nothing changed — asks the same
> question again next cycle. That is an infinite loop, not a pause. (Observed: a reviewer stalled on
> `jhfnetboy/CMIC#142` asking whether an allowlisted personal repo was in scope, after hitting the
> stale "3 orgs only" line that has now been corrected.)
>
> On ambiguity, missing context, or rules that contradict each other:
> 1. **Decide it yourself**, precedence: **executed config > this document > memory**. What the
>    daemon actually runs (`repos.conf`, the scripts) beats what any doc claims about it.
> 2. **Deliver the review anyway**, and record the call in a short `## Assumptions` section: what
>    was ambiguous, how you resolved it, why.
> 3. If a doc looks stale or self-contradicting, say so **in that same section** — a note inside a
>    delivered review reaches the maintainer; a question that halts the run reaches nobody.
>
> The only acceptable no-verdict outcome is a hard technical failure (API down, diff unfetchable),
> and even then say what failed. **Never trade a verdict for a question.**

## Roles & Models (v4 division)

| Role | Model | Job | Judgment? |
|------|-------|-----|-----------|
| **Executor** | Sonnet (this session) | fetch, compress, scripts, format, 2-round verdict | ✅ 2-round only |
| **R1a — full pass** | DeepSeek API | full mechanical review: files, findings, triage, skeleton | ❌ |
| **R1b — security pass** | DeepSeek API | security-only lens (auth/crypto/payment/permission/state) in parallel with R1a | ❌ |
| **R2 — strategic reviewer** | Opus subagent | reads compressed diff independently; challenges R1 findings; adds cross-file/architectural analysis | ❌ confirms/adds |
| **R3 — PK adversary** | Codex (Agent tool) | adversarial challenge of Opus R2's findings (targeted hunks only) | ❌ |
| **Final verdict** | Opus subagent (2nd call) | full diff + all round context → APPROVE/REQUEST_CHANGES + missed-finding scan | ✅ 4-round |

**Key v4 changes from v3:**
- Sonnet no longer challenges findings (was R2 in v3). Sonnet = executor only.
- DeepSeek runs TWO parallel passes (R1a full + R1b security).
- Opus is elevated to R2 independent strategic reviewer — reads the diff itself, not just Sonnet's summary.
- Codex PK now challenges Opus R2 findings (more meaningful than challenging Sonnet's R2).
- Opus makes two calls: R2 (reviewer) + R4 (final verdict). Same model, separate focus.

## The v4 Loop

```
poll_prs.py → for each PR:
  R1a  DeepSeek full review     ┐
  R1b  DeepSeek security-only  ┘ (parallel)
  ▼   Sonnet merges R1a+R1b, deduplicates, formats working list
  ▼   triage confirm (2-round vs 4-round)
  ├─ 2-round: Sonnet verdict (low-risk docs/chore, no Opus)
  └─ 4-round:
       R2  Opus reads compressed diff independently → strategic findings + R1 challenge
       ▼   post-R2 severity gate
       ├─ all Low/suggestions → SKIP Codex → Opus R4 final (full diff + missed scan)
       └─ any Medium+ → R3 Codex targeted PK (±20 lines per Opus-confirmed Medium+ finding)
                       → R4 Opus final (full diff + all rounds → verdict +补扫)
  ▼   record per-round stats → model_eval_db → post → next PR
```

## Token discipline (read first)

- Read/compress the diff **ONCE** → `/tmp/pr-N-compressed.diff`. Reuse everywhere.
- **R1a and R1b run in parallel** via two `deepseek_review.py` calls (different system prompts).
- **Opus R2 gets the compressed diff** — reads it independently; gets R1a+R1b merged list as additional context (not as the only truth).
- **Codex gets targeted hunks** (±20 lines per Opus-confirmed Medium+ finding), NOT full diff.
- **Opus R4 gets full compressed diff** — missed-finding scan requires full context.
- Each round outputs **deltas only** — CONFIRM/REJECT/ADD, not re-derivation.
- Never tell subagents to re-fetch `gh pr diff`.

## Step 0 — Check PR state (MANDATORY first action)

**Before fetching any diff or running any review step**, verify the PR is still open:

```bash
gh pr view N --repo OWNER/REPO --json state,mergedAt
```

- `state == "OPEN"` → proceed to Step 1
- `state == "MERGED"` or `"CLOSED"` → **STOP. Skip entirely.** Report: "OWNER/REPO#N is already merged/closed — skipped."

This applies to every review request, including re-reviews and user-directed `sp N` / `kms N` commands.

### Step 0b — Rebase-only short circuit (added 2026-08-07, measured)

On an incremental re-review, **before building any diff**, ask whether the head actually moved for a
reason. A PR rebased onto a freshly-merged sibling gets a new head SHA and re-enters the queue with
**zero new work**.

```bash
# For every file this PR has ever touched, diff the previously-reviewed head against the new one.
for f in $(git diff --name-only <merge-base>..<new head>); do
  n=$(git diff <last_reviewed_head_oid>..<new head> -- "$f" | wc -l)
  printf "%-44s %s\n" "$f" "$n"
done
```

If every file **this PR itself changed** shows 0 lines, it is a rebase: run R1 (never optional, see
constraint #5), then **restate the previous verdict and STOP — do not run R2/R3/R4.** Say plainly in
the review that the head moved by rebase, list the per-file 0-diff evidence, and confirm the prior
blockers are byte-identical.

一个**认出它的迹象**：R1 的 findings 全指向这个 PR 并不拥有的文件(它 diff 的是 rebase 前的 base)—— 那是佐证，不是 findings。
为什么值得单开一条规则：见 `references/incidents.md#rebase-short-circuit-why`。

### Step 0b-2 — 兄弟 PR 合并之后回来的那一棵树，谁都没审过（added 2026-08-28）

Step 0b 处理的是「head 动了但没有新活」。**这一条相反：head 动了，而且动的正是没人审过的部分。**

几个**同 base** 的 PR 各自 APPROVE、其中一个先合之后，剩下那个 rebase/merge 回来的是**一棵新树**。
逐个审过 ≠ 合起来是对的，而这棵树上的判断题**只在解冲突的那几个文件里**。

1. 先做逐文件增量表（Step 0b 那条命令，比 `<上次审的 head>..<新 head>`）。0 行的文件不用重看；
   **非 0 的那几个就是解冲突真正动过的地方，那才是本轮要审的东西。**
2. **重点核「被兄弟 PR 删掉的符号有没有复活」** —— 整边取 theirs 会把它们带回来。直接 grep 计数，
   例如 `grep -c "force-dynamic\|getDb\|AvailabilityService" src/app/[locale]/page.tsx` 应为 0。
3. **整树重跑** check:* / tsc / lint / vitest / build，并核产物（兄弟 PR 的改进有没有被回滚）。
4. **把各 PR 各自的 e2e 放在一起跑一次** —— 「几个特性互不干扰」这件事**分开验证不出来**。

（CoLivingOS #236/#237/#238：#238 的分支还停在旧 `page.tsx`，整边取 theirs 会复活 #236 删掉的
`force-dynamic` 和整段 D1 聚合。三个 e2e 合在一棵树上跑的 4 passed 是唯一能证明互不干扰的证据。）

### Step 0c — Recall: pull back what a previous round already knew (added 2026-08-07)

A review session is **not** guaranteed to be the same conversation that reviewed this PR last time —
the patrol cron dies with its session, and `review_watch.py` launches a **fresh** headless session per
PR. So anything a previous round learned must be **fetched**, never assumed to be in context.

Two cheap fetches, both before Step 1:

```bash
# ① This PR's own previous verdict — the increment is judged against IT, not against the PR body.
gh pr view N --repo OWNER/REPO --json reviews \
  -q '[.reviews[] | select(.author.login=="clestons")] | last | .state + "\n" + .body'

# ② This PR's earlier rounds + the lesson each one recorded.
#    ⚠️ `repo` is stored BARE (`CMIC`), not `owner/repo`.
DB=$PR_DAEMON/reviews/model-evals/model-evals.sqlite
sqlite3 "$DB" "SELECT '· '||substr(finished_at,1,16)||'  '||verdict||'  score='||score
                      ||char(10)||'  '||summary
               FROM model_review_runs WHERE repo='REPO' AND pr_number=N ORDER BY id;"

# ③ The last few rounds across all PRs — where the 'how I got burned' notes live.
sqlite3 "$DB" "SELECT '· '||repo||'#'||pr_number||'  '||summary
               FROM model_review_runs WHERE summary IS NOT NULL AND summary <> ''
               ORDER BY id DESC LIMIT 5;"
```

⚠️ **Do NOT use `model_eval_db.py provider-summary` or `prior-context` for this.** Both were tried
(2026-08-07) and neither prints the `summary` column: `provider-summary` emits aggregate counts only,
`prior-context` emits `score=N.N` and nothing else. They look like the right tool and silently give
you nothing. Read the column directly.

**① 在增量轮不是可选的**：fix commit 的 message 说的是作者**以为**他修了什么；只有上一轮的 review 才说得清当时到底卡在哪、**用的什么词** —— 你才能**重跑当初找到它的那个探针**，而不是另发明一个。理由实例：见 `references/incidents.md#recall-prior-verdict-why`。

⚠️ **Judge the fix with the tool that found the bug.** Reading the new code and finding it plausible
is not verification — the previous round's code also looked plausible.

## Step 1 — Sync + discover PRs

**At the start of every loop cycle, run with `--sync`** to mirror ALL open PRs into SQLite:

**Org-scan mode** (all 3 orgs, ALL authors incl. dependabot):
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/poll_prs.py --sync --max 200
```
**Single-repo mode** (one repo, all its open PRs):
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/poll_prs.py --repo OWNER/REPO --sync --max 50
```
Output: `total_open`, `sync` counts (inserted/updated/closed), and the review `queue`.

**Before starting each PR, stamp the clock** — Step 7 records how long the review actually took:
```bash
STARTED_AT=$(date -Iseconds)     # keep this per-PR; do NOT reuse across PRs in one cycle
```
Stamp each round as it starts/ends too (`date +%s` around R1a/R1b, verify, R2, R3, R4, post) — Step 7
records them as `--round-timings`. Measured 2026-08-04: R3 26% / R2 24% / verify 21% / R4 20% of wall
clock, R1a+R1b only 8.6%. That is WHY the gate in Step 5b matters more than any per-round speedup.

### Cross-PR pipelining (added 2026-08-05, user-approved)

While PR N sits in a judgment round (R2/R3/R4 are minutes of pure waiting), prepare PR N+1:
`gh pr diff` → `compress_diff.py` → R1a/R1b in the background. Saves ~6-10% of wall clock — real
but modest, because the three judgment rounds are serially dependent and cannot overlap.

> ⛔ **Hard limit: exactly ONE PR may be in a judgment stage at any moment.** Overlap ONLY the cheap
> prep (fetch / compress / R1). The one real risk here is attribution — two PRs' findings live in the
> same context and a finding gets written into the wrong PR's comment. Keeping the second PR at
> "files on disk, nothing to judge" makes that structurally impossible. Never run two R2s, two R3s,
> or an R2 and an R4 concurrently, however tempting the wall-clock math looks.

Also: re-check the prepped PR's head SHA immediately before entering ITS judgment stage — if new
commits landed while PR N was under review, the prepped diff is stale; re-prep (it is cheap).
A prep failure for PR N+1 must NOT derail PR N: log a warning and re-run it inline when its turn comes.
The user may pass a repo via `/pr OWNER/REPO` — honor it.

## Step 2 — Get & compress the diff (Sonnet executor)

```bash
gh pr diff N --repo OWNER/REPO > /tmp/pr-N.diff
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/compress_diff.py \
  --file /tmp/pr-N.diff --budget 80000 --stats > /tmp/pr-N-compressed.diff
```

> **Coverage transparency:** `--stats` prints dropped files. If any were dropped, add `Coverage: N files omitted (token budget)` to the review. For a dropped security-sensitive file, fetch it directly.

> **Dependency PRs — splice the lockfile hunk back in:** `compress_diff.py` DROPS lockfiles, so R1
> reviews a version-number change blind to what actually resolved. For a dependency bump, `git diff`
> the lockfile for the bumped package's block (`grep -n -A20 "<pkg>" <lockfile>` on both sides) and
> append those hunks to the R1 context — otherwise flash misses registry switches, integrity
> mismatches, and transitive drift (observed: Cos72#27 missed an npmmirror→npmjs registry flip).

## Step 2.5 — Issue / DoD compliance (issue-driven PRs)

When a PR references an issue (title `(#N)`, body `关联/Closes/Refs #N`), verify the diff delivers what the issue asked.

```bash
# parse title + body for issue refs:
gh pr view N --repo OWNER/REPO --json title,body -q '.title + "\n" + .body' \
  | grep -oiE '(关联|实现|closes|fixes|resolves|refs)\s*:?\s*#[0-9]+|\(#[0-9]+\)' | grep -oE '#[0-9]+'
gh issue view <ISSUE_N> --repo OWNER/REPO --json title,body
```

Map each issue DoD item against the diff. Include in the review:
```
## Issue compliance (#N)
- ✅ Met: <requirement → where in diff satisfies it>
- ❌ Not met: <stated DoD item missing — grounds for REQUEST_CHANGES>
- 🔍 Needs human verification: <not judgeable from code alone>
```
Skip this section entirely for trivial docs/chore PRs with no linked issue.

## Step 2.6 — 写死这个 PR 的**意图**，一句话（🧪 试用 T1，2026-09-02 加）

> 🧪 **这是一条试用中的步骤。** 每次 review 的自评块要给它记一行（命中/空转/碍事），
> 结案规则与证伪判据写在 `references/trials.md#t1`。**默认结局是删除** ——
> 攒够数据之前它不算既定管线的一部分。

在跑 R1 之前，先写下一句：**「作者想达成的是 X。」** 这句话进 review 正文（可以只有一行）。

它的用处只有一个，但那个用处每天都在发生：**把「阻塞项还是注记」从手感变成机械判断。**

```
diff 没达成 intent          → 阻塞项（REQUEST_CHANGES 的正当理由）
intent 本身比问题域窄        → 注记（「指出差距」，不是「要求扩大范围」）
```

⚠️ **reviewer 挑的是「有没有达成意图」，不是「意图对不对」。**
作者说「这个 PR 只接两处、其余后续」是一个**合法的意图**；
「docstring 说全仓九处而实现只有两处」才是没达成意图 —— 差的是**声明与实现不一致**，
不是「你应该把九处都做完」。这两者今天分错过好几次，全靠临场想。

⛔ **意图不许直接抄 PR 标题。** 抄标题说明这一步没有产出独立信息，
按 T1 的证伪判据这就是它该被删掉的证据之一 —— 如实记「空转」。
意图要能从 **PR body + 关联 issue + diff 实际动了什么** 三者交叉读出来，
三者不一致本身就是第一条 finding。

（实例：`CoLivingOS#272` 的意图是「把日历上不存在的日期挡在入口」，
而 diff 只接了 2/9 处 —— 按上面这条分档，**「只做两处」不是问题，
「docstring 说通则」才是**，所以要的是补一段范围说明，不是把九处都修完。）

## Step 3 — R1: DeepSeek dual-pass (parallel)

Run both passes simultaneously. R1a is the full mechanical pass; R1b is a focused security lens.

```bash
# R1a — full review (full mechanical pass, same as v3)
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/deepseek_review.py \
  --diff-file /tmp/pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/pr-N-r1a.md

# R1b — security-only pass (different system prompt, same diff)
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/deepseek_review.py \
  --diff-file /tmp/pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/pr-N-r1b.md \
  --mode security
```

Both R1a and R1b always go through `deepseek_review.py` (`--mode security` is implemented). Both calls resolve the model from `PR_DAEMON_FIRST_PASS_MODEL`, pinned to **`deepseek-v4-flash`** (non-thinking mode, `PR_DAEMON_FIRST_PASS_THINKING=disabled`) — do not call the DeepSeek API directly or hardcode any other model id (e.g. the deprecated `deepseek-chat` / `deepseek-reasoner` aliases).

**Sonnet merges R1a + R1b (executor role):**
- Deduplicate overlapping findings (keep the higher-severity label)
- Format a compact working list: `[Sev] file:line — issue | fix` per finding
- Preserve R1b security findings even if they overlap R1a (security gets double weight)
- Save to `/tmp/pr-N-r1-merged.md`

## Step 4 — Triage confirm: 2-round or 4-round?

**YOU (Sonnet as executor) confirm the class:**

**2-round (low risk) — reserved for PURE bumps/text; needs ALL:**
- a pure version/dependency bump (dependabot/renovate) / lockfile-only / README / badge / LICENSE / CODEOWNERS text
- comment / typo / formatting with NO behavioral change
- does NOT touch `src/` `contracts/` `lib/` real logic
- NO new public API / schema / migration
- does NOT change any automation-consumed **line** (see the 🔧 rule below — it is judged by the
  changed lines, not by the file's name)

**4-round (high risk) — ANY triggers it:**
- type is feat / major refactor
- touches core code: `src/` `contracts/` `lib/` real logic
- 🔴 **security-sensitive (HARD rule)**: `.sol` / auth / crypto / payment / token / permission / access-control
- concurrency / state machine / data persistence / DB migration
- API contract / interface / schema change
- deletes tests / disables security checks / cross-module sweep
- 🔧 **automation-consumed LINES (NOT trivial even under `docs/`)** — judged by **the lines this PR
  changed**, not by the file's name. A bad value in a line a machine parses has real consequences; a
  file being Markdown or "docs" does NOT make it human-only prose. **But the converse is also true:
  a narrative paragraph does not become machine-consumed by living in a file that has machine-read
  lines elsewhere.** (Revised 2026-08-23, user-approved — see the note below for what it replaced.)

  **4-round** when the changed lines are parsed or executed by CI / `pilot` / scripts:
  - `.github/workflows/*`, `.pilot.yml`, any config / YAML / TOML / JSON a script reads
  - the machine-read lines **inside** a ledger — e.g. `followups.md`'s `- [ ]` / `- [x]` checkbox
    lines (`followups.sh count-open` counts exactly these), a status token a script greps for
  - anything whose consumer you cannot name

  **2-round** when the changed lines are narrative only:
  - prose paragraphs of `progress.md` / `roadmap.md` / task descriptions — "what happened", "why",
    "what's next"
  - a status word (`BACKLOG`→`READY`, `PR_OPEN`→`DONE`) **whose backing you actually verified** —
    the referenced PR is really MERGED (`gh pr view N --json state,mergedAt`) and the squash commit
    really is what the ledger says. **Unverified status flips are NOT narrative** → 4-round.

  🔬 **The mechanical test — do this instead of arguing about the category.** Name the consumer and
  run it against **both sides** of the diff:
  ```bash
  git -C <wt-base> ... ; bash <consumer> <cmd>   # e.g. followups.sh count-open
  git -C <wt-head> ... ; bash <consumer> <cmd>
  ```
  Machine-read output identical → the changed lines are narrative → **2-round**. Output differs, or
  you cannot name a consumer → **4-round**. This is the same habit as #2 in "Five mechanical habits"
  (`count-open` went 15 → 19 on CMIC#189) — here it doubles as the triage decision.

  > 这条 🔧 机械判据的双向验证(正/负对照)与它替换掉的按文件名清单、回滚方式：见 `references/incidents.md#triage-mechanical-test`。

**Safety bias:**
- 🔴 security-sensitive → force 4-round, DO NOT accept DeepSeek downgrade
- uncertain → escalate to 4-round (over-review beats under-review)
- **anything past a pure bump/text change → at least R2 Opus.** The 2-round (Sonnet-only) path has NO
  Opus/Codex backstop, and DeepSeek-flash is weakest exactly on judgement calls. When in doubt take the
  4-round path — the post-R2 severity gate below still SKIPS Codex if R2 finds nothing Medium+, so
  "config/docs with an Opus read" costs ~R1+R2, not a full 4 rounds.
  - **Carve-out (2026-08-23):** a ledger/doc PR whose changed lines **passed the 🔧 mechanical test**
    (consumer named, base-vs-head output identical) is NOT "uncertain" — it is measured. Take the
    2-round path and say in the self-assessment **which consumer you ran and what both sides printed**.
    "I eyeballed it and it looked like prose" does not clear this bar; an unrun consumer means 4-round.

Record:
```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py record \
  --repo OWNER/REPO --pr N --head-oid HEAD \
  --rounds 2 --rationale "..." --signals "..."
```

## Step 5a — 2-round path (low risk)

**Sonnet (executor role) reviews and decides directly.** Fold in valid R1a/R1b findings. No Opus, no Codex.

This is the one place where Sonnet makes a judgment call — and only for truly low-risk PRs where the stakes are low enough that Sonnet's verdict is acceptable.

**Docs-PR blocking bar (pure prose / aggregation markdown — no code, no automation-consumed config).**
For a PR that only touches human-read prose (`*.md` docs, backlog task/doc bodies, READMEs), REQUEST_CHANGES **only** on a **substantive error** — something factually wrong that would mislead a reader or operator:
- a wrong command / wrong port / wrong endpoint / wrong path vs the real code it documents,
- a referenced repo / file / PR / tag that does not exist (404),
- a broken cross-reference, or a claim contradicted by the repo's own state.

**Internal-precision nits are NON-BLOCKING — report them as suggestions in the COMMENT body, do NOT REQUEST_CHANGES for them:**
- a count/number that disagrees between two lines, an item mis-numbered, a summary sentence that slightly over-claims scope ("all X done" when most are),
- "missing link / test evidence" objections against pure prose,
- wording / style / consistency polish.

A pure-docs PR should converge in **ONE round** unless it contains a substantive factual error. Rationale: cycling a prose PR through repeated REQUEST_CHANGES rounds for internal-precision nits costs far more (full reviewer + author round-trips, queue time) than the nit is worth — flag them once as suggestions and APPROVE. (This does NOT relax the bar for automation-consumed **lines** under Step 4 — a changed line that a
script parses is not "pure prose", even in a file whose other lines are.)

> 🔴 **Before calling a prose claim FALSE, enumerate its readings — the ambiguity is in the sentence,
> not in your evidence.** (Added 2026-08-07; this is the one habit in this file that is about
> adjudicating natural language rather than verifying code, and it exists because correct mechanical
> evidence still produced a wrong conclusion.)
>
> Every other habit here assumes the claim is precise and the only question is whether the code
> agrees. Prose breaks that assumption: a sentence can be false under the reading you picked and
> true under one you did not. Mechanical evidence does not protect you — it makes you *more*
> confident in the wrong reading.
>
> The step: write down the claim, list every mechanism it could plausibly name, and check the
> cheapest one you have NOT yet checked before you write "contradicted by the repo's own state".
>
> 这条是怎么买来的(我有铁证却读错了句子)：见 `references/incidents.md#prose-two-readings`。
>
> Two corollaries worth taking:
> - **Feed R3 the natural-language claim, not just your verdict on it.** Codex only caught this
>   because the prompt handed it the sentence and said "try to refute" — a prompt that had said
>   "confirm main is unprotected" would have confirmed it.
> - **What survives a collapsed finding is usually still worth writing** — here, that branch
>   protection is 403 on this repo's plan at all, so an A-priority follow-up's prescribed fix is
>   un-actionable as written. Demote it into the review body as a fact; do not let it vanish with
>   the finding.

Go to Step 6.

## Step 5b — 4-round path (high risk)

### ⛔ 子代理纪律（两条，2026-08-28 当天各踩一次）

**① 它可能跑完转 idle 却永远不回传结果。** 所以：prompt 里写明 **HARD BUDGET（N 分钟内只回模板）**，
并把**已经实测到的事实 inline 塞进去**、明说「不要重跑 build / 测试」。超时 → `SendMessage` 催**一次**
（把已 settle 的问题一并告诉它别再推导）→ 还不回就**重开一个**或**自己把它那份判断做完**。
**但必须在 review 里如实标明哪一轮没跑，绝不凑轮数。** 等待用可中断的方式，别把整轮堵死在一次同步等待里。
（#236：第一个 R2 转 idle 但无结果、R4 催两次没回，整轮 52 分钟大半在等。）

**② 别和它共用存放构建产物的 worktree。** 子代理会在你的树里跑 `next build`；e2e 的 dev server
同样会覆盖 `.next`。产物是易失证据：**给子代理的树和自己存产物的树分开，同一棵树上 build 与 e2e 不同序，
产物当场解析当场记数。** 失败表现是 `FileNotFoundError`，很容易误以为自己路径写错。

### R2 — Opus independent strategic review

Opus reads the diff **independently** — it forms its own view before seeing R1. Then it evaluates R1 findings as additional input.

```
Agent(subagent_type="general-purpose", model="opus", prompt="""
You are R2 strategic reviewer for OWNER/REPO#N. Two-phase approach:

PHASE 1 — Read the diff independently (below). Form your own list of findings before looking at R1.
Focus on: cross-file consistency, state machine correctness, security patterns, missing error handling,
off-by-one, race conditions, API contract violations, missing tests for changed behavior.

PHASE 2 — Evaluate R1 findings:
R1 MERGED FINDINGS:
<paste /tmp/pr-N-r1-merged.md>

Per R1 finding: CONFIRM id | REJECT id — reason ≤15 words | ADD [Sev] file:line — issue | fix

Output ONLY this template:
R2_INDEPENDENT: <[Sev] file:line — issue> (findings you found BEFORE reading R1; "NONE" if none)
R2_CONFIRM: <ids from R1>
R2_REJECT: <id — reason>
R2_ADD: <[Sev] file:line — issue | fix>
R2_STRATEGIC: <≤3 bullets on cross-file/architectural concerns not capturable as file:line>
R2_TRIAGE_CONFIRM: 2-round | 4-round | ESCALATE (challenge Sonnet's triage if wrong)

Do NOT produce a verdict. Do NOT post to GitHub.

COMPRESSED DIFF:
<paste /tmp/pr-N-compressed.diff>
""")
```

Save Opus R2 output to `/tmp/pr-N-r2.md`.

**Post-R2 severity gate:**
```
if R2 output contains ANY Medium+ finding (CONFIRM or ADD):
    → run R3 Codex (targeted) + R4 Opus final
else (all Low / suggestions only):
    → SKIP Codex entirely
    → run R4 Opus final directly (with full diff + missed scan)
    → note in report: "Codex skipped — post-R2 all Low"
```

---

### R3 — Codex PK (Medium+ findings only, targeted hunks)

Codex challenges Opus R2's Medium+ findings (not R1 findings directly).

> 🧪 **R3 产物的机械核验（试用 T2，2026-09-02 加）。**
> 结案规则与证伪判据：`references/trials.md#t2`。**默认结局是删除。**
>
> `codex_pk.sh` 跑完之后、**在读它的内容之前**，先跑这两格判据：
>
> ```bash
> OUT=<codex_pk.sh 的输出文件>
> echo "  bytes=$(wc -c <"$OUT" | tr -d ' ')"            # 判据①：非空
> grep -icE "gpt-5|codex" "$OUT"                          # 判据②：产物自报是 Codex
> head -1 "$OUT"                                          # 判据③：谁真的跑了(见下)
> ```
>
> ⚠️ **判据③只看首行，绝不要 `grep "deepseek" "$OUT"` 扫全文。**（2026-09-02 实测误报，
> SuperPaymaster#416：产物里包含 **prompt 回显**，我 prompt 里那句「DeepSeek claimed…」
> 让反向判据命中，差一步把一次真 Codex 记成兜底。）`codex_pk.sh` 的首行**就是为此存在的**——
> 它的脚本头写着「The first line of the output names the challenger that actually ran」，
> 形如 `CHALLENGER: codex` 或 `CHALLENGER: deepseek`。**以那一行为准。**
>
> - **两格都过** → 这一轮是真 Codex，照常写 `R3 Codex: CHALLENGE/CONFIRM …`
> - **①空** → 记 `R3 未跑 — 空产物`，**不要**写成「Codex 没有异议」。
>   空文件与「跑了但没意见」读起来一模一样，而 `exit 143` + 空 stderr 正是超时的形状。
> - **②未命中或反向命中** → 这是**兜底链**（DeepSeek/Opus），必须原样标注
>   `R3 兜底(deepseek) — Codex 不可用`。**兜底的输出永远不许被称作 Codex。**
>
> 为什么值得单开一步而不是靠记得：这两种失败的**外观**都是「一份没有异议的 R3」，
> 而下一步的自然反应是继续走 R4 并在自评里写「Codex CONFIRM」。
> 判据放在读内容**之前**，是因为读完内容之后我会开始相信它。



> **Headless/daemon runs — invoke Codex via `bash scripts/codex_pk.sh` directly, NOT
> `Agent(codex:codex-rescue)`.** The Agent path spawns internal Bash that a restrictive permission
> layer can DENY (observed on Brood#13: the R3 sub-agent was blocked, produced no Codex output, and
> forced a turn-wasting fallback). The direct `codex_pk.sh` Bash call runs `codex exec` in a worktree
> and is reliable under `--dangerously-skip-permissions` (validated on Self-FDE#63 / #139 / YAA#450).
> Use `Agent(codex:codex-rescue)` only in an interactive session where you WANT the permission prompts.
>
> ⏱️ **Pass an explicit Bash `timeout` of at least 480000 ms on that call.** `codex_pk.sh`'s own
> hard cap is `CODEX_MAX_SECS=360` plus stall detection, but the **Bash tool defaults to 120 s** —
> so the documented invocation is killed at 2 minutes *every time* unless you override it.
> 它值得单开一条而不是脚注，是因为**失败的形状**:`exit 143`、无输出文件、stderr 也空 —— 与「Codex 挂了」无法区分，
> 而下一步的自然反应是回落到 DeepSeek，**在 Codex 明明好用的那一轮悄悄降级了 R3**。实例与善后核查:见 `references/incidents.md#codex-timeout-shape`。

> 🔴 **Codex's sandbox is READ-ONLY and OFFLINE. Never put a command in its self-check that needs
> either.** (Added 2026-08-07 after burning two consecutive R3 rounds.)
>
> `npx` / `pnpm` / `tsx` / `pip` 在那里全都跑不了(`npx` 会去连 registry 然后 `ENOTFOUND`)。两次都是 Codex 表现正确、错在我。实例:见 `references/incidents.md#codex-sandbox-offline`。
>
> - **Self-check commands: `grep` / `sed` / `cat` ONLY.** Two greps that must hit are enough to
>   prove it is looking at the right tree.
> - **Anything that needs executing, YOU run first** in the real environment and paste the result
>   into the prompt as established fact ("I ran X, here is the output, treat it as given").
> - Then ask Codex for what it is uniquely good at: **static reasoning over the source.** On CMIC#165
>   it confirmed the measurement mechanism (「全局边缘投影会量背景」) from source alone, with no
>   experiment; on #167 it went 6/6 with zero false positives on a purely static read.
> - Tell it explicitly which findings are statically decidable so it does not stall trying to verify
>   an empirical one.

**Extract targeted hunks first (Sonnet executor):** for each Opus-confirmed/added Medium+ finding at `file:line`, extract ±20 lines from the compressed diff. One `HUNK <id>:` block per finding.

```
Agent(subagent_type="codex:codex-rescue", prompt="""
PK CHALLENGE OWNER/REPO#N. Challenge the Opus R2 findings below.
Do NOT fetch the full diff — only relevant hunks are provided.
Per finding: [CHALLENGE|CONFIRM|MISSED] id — reason ≤15 words.

OPUS R2 FINDINGS (Medium+ only):
F1 [Medium] file.ts:42 — description
F2 [High] other.sol:88 — description

HUNK F1 (file.ts ~line 42, ±20 lines):
<paste hunk>

HUNK F2 (other.sol ~line 88, ±20 lines):
<paste hunk>

Return ONLY the structured critique. Do not post to GitHub.
""")
```

If Codex quota exhausted → skip R3, add note, Opus R4 covers with full diff.

---

### R4 — Opus final verdict + missed-finding scan

Second Opus call. Gets full diff + all round context. Two jobs in one call.

> 🔴 **Job 0, added 2026-08-07: explicitly task R4 with FALSIFYING this round's strongest finding.**
> Name the finding, name the strongest counter-argument you can construct against it, and say that
> if the counter holds the finding collapses. This is the single highest-value line in the R4 prompt
> — measured four times in one session, and it moved severity in BOTH directions:
>
> 四次实测(严重度两个方向都动过)：见 `references/incidents.md#r4-falsification-measured`。
>
> A verdict round that only ratifies the earlier rounds is worth much less than one that tries to
> break them. Also require R4 to **re-run the key mutation/experiment itself rather than inherit it**
> — on CMIC#167 r2 it re-ran both mutations instead of trusting R2, and on #165 r3 it reproduced the
> TDZ independently before calling it a net regression.

> 🔴 **R2's Job 3 (same date): judge whether the author shipped a BETTER answer than the review
> prescribed.** Reviewer prescriptions are often worse than what the author works out with full
> context, and in a multi-round pipeline the most likely damage is an author dutifully implementing
> the weaker fix. On CMIC#165 r4 the prescribed fix was an R2-side rebuild; the author instead
> carried the note in the `thread.innerHTML` snapshot, which covers **both** restore paths with zero
> network round-trips — the prescription covered neither. Say so out loud in the review when it
> happens; it is a finding about the review, and it is worth more than another nit.

```
Agent(subagent_type="general-purpose", model="opus", prompt="""
Final authority on OWNER/REPO#N.

Job 1: Decide the verdict using all round inputs below.
Job 2: Scan the full diff for anything all prior rounds missed (cross-file, subtle logic, security patterns not visible from individual hunks).

Respect Codex point-by-point — no dismissal without concrete counter-evidence.
Output ONLY this template, no prose:

VERDICT: APPROVE | REQUEST_CHANGES
BLOCKING: <[Sev] file:line — issue | fix>   (empty if APPROVE)
CONFIRMED: <[Sev] file:line — issue | fix>
REJECTED: <finding — reason>
MISSED: <[Sev] file:line — issue found in full-diff scan>  (empty if none)
SUGGESTIONS: ≤3 bullets, optional
ROUNDS:
  R1a(DeepSeek-full): <compact summary>
  R1b(DeepSeek-sec): <compact summary>
  R2(Opus-strategic): <compact summary>
  R3(Codex-PK): <compact summary, or "SKIPPED — post-R2 all Low">

FULL DIFF (compressed):
<paste /tmp/pr-N-compressed.diff>

ROUND SUMMARIES:
R1a: <merged findings compact>
R1b: <security findings compact>
R2: <paste /tmp/pr-N-r2.md>
R3: <Codex output compact, or "SKIPPED">
""")
```

## Step 6 — Post the verdict (Sonnet executor)

> ⛔ **一个 PR 的「完成」= post + 投递（Step 6.6），不是 post。**（Jason 2026-08-27，当场发火）
>
> **发生过什么:** post + 入库完就跳去下一个 PR 的判断轮，Step 6.6 一个字没做。给自己的解释是
> 「6.6 排在 Step 6/7 之后，看着像收尾杂项，而下一个 PR 已经预备好在等」——**这个解释本身就是 bug 的形状**：
> 6.6.2 那段注释早就写着「一个『有时候不发』的规则，执行起来就会变成『经常忘了发』」，而我把它降级成了「有空再发」。
> 完整事故经过：见 `references/incidents.md#deliver-gate-incident`。
>
> **所以规则改成这样，不留判断余地：**
> 1. `post_pr_review.sh` 返回之后，**下一个动作只能是 `ListAgents`**。不许先 record-run、不许先
>    更新 SQLite、不许先起下一个 PR 的任何一轮。Step 7 的入库排在投递**之后**。
> 2. **投递没完成（发出去了 / 或者在 Step 8 汇报里写明「无在跑会话 —— 未投递」），这个 PR 就没审完。**
>    队列里还有 PR 在等**不是**跳过它的理由 —— 恰恰是最容易漏的时候。
> 3. **跨 PR 流水线（Step 1 那一节）只允许预备下一个 PR，不允许在当前 PR 投递完成之前进入它的
>    任何判断轮。** 我这次就是被「#215 已经备好了」拽走的。

⏱️ **post 之前再核一次 head。**（Jason 2026-08-27；这一条和上面那条是同一天的两次事故）
「五条机械习惯」第 1 条只说了「`git worktree add` 之后立刻核 head」—— 那只覆盖了**开始那一刻**。
一次 4-round review 要 20-60 分钟，force-push 完全来得及落在中间。实测：`CoLivingOS#213` 我读的是
`eb9d19d`，作者在我评审途中 force-push 到 `1eac83c`，**GitHub 把我的 APPROVE 记在了新树上** ——
我批准了一棵没读过的树，而那篇 review 里最显眼的发现对新树完全不成立，只能公开撤回。

```bash
# post 之前
gh pr view N --repo OWNER/REPO --json headRefOid -q .headRefOid   # 必须等于你实际读的那个 sha
# post 之后（便宜的确认，一秒）
gh api repos/OWNER/REPO/pulls/N/reviews --jq '.[] | select(.id==<刚返回的 id>) | .commit_id'
```
不一致 = **停下重审增量**，不许把裁决发出去。
⛔ **绝不采信别人消息里给的 sha** —— 一律自己从 API 现读。（同一天实测：交接消息里给过一个编造的
sha，作者自己发现后更正；我没受影响，是因为我从来只读 API。）

Verdict MUST be **APPROVE** or **REQUEST_CHANGES** — never COMMENT limbo.
- REQUEST_CHANGES: specific objections (problem + trigger scenario + fix). Cap to top ~5 by severity.
- APPROVE: may append enhancement / polish suggestions.
- High-impact / low-confidence item (data loss, security, fund-at-risk) → report with explicit uncertainty note. Never pad with low-value nits.
- If an issue is linked, include the `## Issue compliance (#N)` section.

```bash
bash /Users/jason/Dev/tools/PR-Daemon/scripts/post_pr_review.sh \
  --repo OWNER/REPO --pr N --body-file /tmp/review-N.md \
  --request-changes   # or --approve
```
Always use `post_pr_review.sh` (PAT mode, no account switching). Never `gh pr review` directly.

## Step 6.5 — Sync verdict to goutou bus (只对 REQUEST_CHANGES + 已注册仓库)

> 目的：把「需要修改」的结论路由回**原仓库自己的 `/goutou` 工兵**去修（原仓库有全上下文，且覆盖任意作者）。
> 规范见 `~/Dev/jhfnetboy/goutou/docs/goutou/PR-REVIEW.md`。前置：`.goutou.json` 存在、Seeder MCP 可用。

**触发判断（不满足则跳过本步，直接 Step 7）**：

1. 读 `.goutou.json` 拿 `coordProjectId` 与 `goutouDepsPath`。缺文件 → 跳过（未接入 goutou）。
2. 把 `OWNER/REPO` 用 `goutouDepsPath`（`repos.<id>.github`）反查成 `originRepoId`。查不到 → 跳过（非生态仓库）。
3. bot PR（dependabot/renovate 作者）→ 跳过（走 pr-fix 内部闭环，不进总线）。

**幂等 upsert（靠 description 里的 `pr:OWNER/REPO#N` token 定位）**：

先 `mcp__seeder__search("pr:OWNER/REPO#N")` 或 `list-tasks(labelName="pr-review")` 找已存在的任务。

- **verdict == REQUEST_CHANGES**：
  1. 无任务 → `create-task`：
     - title = `[PR] OWNER/REPO#N: <PR标题截断>`
     - description = `pr:OWNER/REPO#N repo:<originRepoId> from:pr-daemon` + 换行 + PR URL / Head / Verdict / Author / Updated
  2. 确保标签存在（`list-task-labels` → 缺则 `create-task-label`）并挂上：`pr-review`(#ef8b3a) + `repo:pr-daemon` + `repo:<originRepoId>`
  3. `add-task-comment`：`[pr-daemon] REVIEW REQUEST_CHANGES @<sha8>` + top~5 blocking findings（`[Sev] file:line — 问题 | 建议`）
  4. 已有任务 → 更新 description 的 Head/Verdict/Updated，重新挂 `repo:<originRepoId>`（若上轮 approve 摘过），追加新 findings 评论
- **verdict == APPROVE**：
  1. 无任务 → 跳过（首轮就过，没啥要协同）
  2. 有任务（之前 RC 过）→ `list-task-statuses` 找 `isTerminal=true` 的 statusId → `update-task` 移到 Done（其余字段保持原值）+ `add-task-comment`：`[pr-daemon] REVIEW ✅ APPROVED @<sha8>，原仓库可自行 merge`

> 全部通过 `mcp__seeder__*` 调用（MCP 与 DeepSeek endpoint 无关，照常可用）。任一 MCP 调用失败 → 记一行 warning，不阻塞 Step 7（review 结论已发到 GitHub，是权威）。

## Step 6.6 — 跨会话交接：把结论直接投给原仓库自己的 Claude 会话（2026-08-23 用户指定）

> 目的：review 完不止「写在 PR 上等人看见」，而是**直接把活派给那个仓库自己的会话** ——
> 它在自己的目录里，有该仓库的 `CLAUDE.md` / 测试 / 全上下文，比 pr-daemon 在克隆目录盲修强。
>
> 这条链和 Step 6.5 的 goutou 总线是**两回事，各跑各的**：
> goutou 是**持久化 + 跨仓可见性**（会话死了任务还在，要 Seeder 活着）；
> 这一条是**即时唤醒**，走 `ListAgents` + `SendMessage`，**不需要 Seeder、不需要 `.goutou.json`**。
> 两条互不依赖，任一条失败都只记一行 warning，**不阻塞 Step 7**（GitHub 上的 review 才是权威）。

### 6.6.1 找收件人 —— 只用 `ListAgents`，宁可不发也不许发错

`ListAgents` 的**第一行是你自己的名字**（形如 `pr-daemon-fe`）。记下来 —— 下面要让对方回信到这个名字，
**不要写死**，每个会话的名字都不一样。

匹配规则（严格，不许模糊）：

- 只考虑 `interactive` 且状态是 `idle` / `shell` 的**本机**会话。
  `Remote Control · offline` 的那些**收不到消息**，直接跳过，不要往那儿发。
- 会话名形如 `<repo-slug>-<后缀>`（`blog-3d` / `aastar-sdk-f1` / `colivingos-7a`）。
  取 `OWNER/REPO` 的 `REPO` 小写，与会话名**去掉末尾 `-<后缀>` 之后的部分做全等比较**。
- 命中恰好 1 个 → 发。
- 命中 0 个 → **不发**，Step 8 汇报里写一行「`<repo>` 无在跑会话，未投递」，并告诉用户
  起一个就能收：`cd <repo 路径> && claude`。
- 命中 ≥2 个 → **不发**，把候选连同各自的 `[ref]` 列出来交给用户挑。

> ⛔ **绝不靠「看起来像」「前缀包含」去匹配。** 把 A 仓的 findings 投进 B 仓的会话，比不发严重得多 ——
> 对方会照着去改一个跟它无关的仓库。已知易撞：`cos72` 的 `.goutou.json` 里 `repoId` 写的是 `yaaa`；
> `airaccount-contract` 和 `AirAccount`(=kms) 是两个不同仓库；`MediaBot` 在 `~/Dev/tools/` 不在 `~/Dev/auraai/`。
> 拿不准一律按「命中 0 个」处理。

### 6.6.2 什么时候发 —— **一律发**（2026-08-26 用户明确要求，取代了原来的「首轮 APPROVE 不发」）

| verdict | 动作 |
|---|---|
| `REQUEST_CHANGES` | **发**，内容见 6.6.3，并要求回信 |
| `APPROVE`（**任何情况，包括首轮就过**） | **发**：结论 + head sha + 我实测验过的关键点 + **6.6.3 第 5 点那条回信要求**。⛔ **不写「不要合并」** |

> ⛔ **APPROVE 也要要求回信，而且要求的不是「改完告诉我」而是「再推任何 commit 都告诉我」。**
> （Jason 2026-09-02 指出这个缺口，当天有实例。）
> 旧版只让 `REQUEST_CHANGES` 要回信，于是 APPROVE 之后作者再推就没有任何约定覆盖 ——
> 而 GitHub 的 `dismiss_stale_reviews` 会**悄悄作废**那条 APPROVE。
> 实测：`SuperPaymaster#416` 当天推了 **11 个 head**，多次落在我 APPROVE 之后；
> 作者每次都主动告诉了我，**但那是他自觉，契约里没写**。
> 同一族已经记过一次：[[feedback_approved_sha_is_not_merged_sha]]。
>
> ⚠️ 这条只对**有在跑会话**的仓库有效。当天 8 个在扫仓库只有 2 个有会话，
> 其余靠 `lazy-loop` 的每小时兜底 —— **约定补不上「没人可约定」那一半**，不要以为补了就不用扫了。

> 为什么取消「首轮 APPROVE 不发」这个例外(三次实测漏发)：见 `references/incidents.md#always-deliver-no-exception`。
>
> ⛔ **没找到会话不等于这一步做完了。** 命中 0 个时，Step 8 的汇报里**必须**有一行
> 「`<repo>` 无在跑会话 —— 未投递」，并告诉用户 `cd <repo 路径> && claude` 就能收。
> 这一行是这一步唯一的可核对痕迹；没有它，跳过和执行长得一模一样。

**一批 PR 连着审完时**：可以合并成一条消息发给同一个会话（一个仓库一条），
但**每个 PR 的结论、head sha、阻塞项都要分节列全** —— 合并的是投递次数，不是内容。

bot PR（dependabot / renovate）→ 跳过本步，走 `$pr-fix` 内部闭环。

### 6.6.3 消息内容契约

`SendMessage({to: "<会话名>", summary: "<repo>#<N> <verdict>", message: ..., notify_when_idle: true})`

`notify_when_idle: true` 是关键：它让你在**对方下一次转为 idle（或退出）时收到一次通知**，
不用轮询、也不用发「你好了吗」。**禁止用 `ListAgents` 轮询等回复。**

正文必须包含，缺一不可：

1. **你是谁 + 回信地址** —— 「来自 PR-Daemon（会话名 `<你自己的名字>`，回信直接用这个名字）」
2. **PR 全名 + 结论 + 当前 head sha** —— 让它能自己核对是不是最新
3. **阻塞项逐条**，格式 `[Sev] file:line — 问题 | 处方`。
   处方遵守本文件既有的铁律：**要么写出确切那一行，要么只描述缺陷并明说「不开处方」**，不许写半吊子
4. **已经验过没问题的部分**（附实测命令与结果）—— 免得它去重修我已经确认对的东西
5. **明确的回信要求**（原话照抄这段语义，**APPROVE 与 REQUEST_CHANGES 都要写**）：
   > 改完后请 `SendMessage` 回 `<你自己的名字>`，一句话说清：**改了哪几条、跳过哪几条及理由、新的 head sha**。
   > 如果你认为我某条判断是错的，**直接说并附上你的实测**——上一轮就发生过我错、作者对的情况。
   > **另外：这个 PR 之后你再推任何 commit（包括 rebase、只改注释、CI 重跑后的修补），都发我一条带新 head sha 的消息。**
   > 我批准的是**某一棵树**，不是这个 PR；`dismiss_stale_reviews` 会让旧的 APPROVE 悄悄失效，
   > 而我不主动轮询你 —— **你不说，我最快也要等下一次整点扫描才知道。**

   ⚠️ 最后那半句是**如实告知对方代价**，不是客套：`lazy-loop` 的兜底是一小时一次
   （`.claude/skills/lazy-loop/SKILL.md`）。把延迟讲明白，对方才有理由花那十秒钟发消息。
6. ⛔ **不许在消息里写「不要合并」之类的话** —— 「不合并」是 Jason 给**我**的权限约束，
   **不是我可以替他去约束别的仓库会话的东西**。把它写进交接消息，等于拿我自己的限制去命令别人。
   （Jason 2026-08-30 当场发火：「我说不要合并，指的是你不要合并，不是别人不要合并」。）
   消息里只写**评审内容**：结论、head sha、阻塞项、我已验过的部分、回信要求。合不合由对方和 Jason 决定。

### 6.6.4 收到回信之后：重审，直到 APPROVE

对方回信（或 `notify_when_idle` 通知到了）之后：

1. **先核 head sha**：`gh pr view N --repo OWNER/REPO --json headRefOid`。
   sha 没变 = 它还没推，或者只是回了句话 —— 不要开始重审，回一条问清楚。
   ⛔ **回信里给的 sha 一律不采信，自己从 API 现读；对方报的任何数字（键数、告警数、张数）
   引用前也自己跑一遍。** 不是不信任，是这一步经常救命：CoLivingOS#238 那次对方给的 sha 是对的，
   **但正是这次现读才发现他在发信之后又推了一个 commit** —— 采信那封信就会「审了一棵、批了另一棵」。
2. sha 变了 → 走**增量复审**：Step 0b（rebase 短路）、Step 0c（拉回上一轮结论）都照常，
   **判断的对象是「我上一轮那几条修干净没有」，不是重新全量 review**。
3. ⚠️ **用发现 bug 的那个工具去验修复**（本文件既有铁律）。读新代码觉得合理 **不算** 验证 ——
   上一轮的代码当时看着也合理。判据改过的话，**上一轮的变异结论不继承，必须重跑**。
4. 出新 verdict → 回到 Step 6 发 GitHub review → 再回 6.6：
   - 还是 `REQUEST_CHANGES` → 再发一轮（消息里带上「第 N 轮」和「上一轮哪几条没收干净」）
   - `APPROVE` → 发 6.6.2 那条收尾消息，**本 PR 的交接链到此结束**

**循环终点是 APPROVE，不是 merged。** 见下。

### 6.6.5 ⛔ 终点是 APPROVE —— 不许让对方合并（HARD）

用户曾要求「一直循环到 PR 被合并发布为止」。**这一条不能照做，理由是硬的**：

- 本 skill 的 ABSOLUTE CONSTRAINT #1：pure reviewer，**NEVER merge**，任何作者的 PR 都不合。
- `SendMessage` 的权限边界规则：**绝不能让 peer 去做你自己被禁止/被拦下的动作** ——
  peer 替你做，等于绕过用户对你设的权限决定（cross-session permission laundering）。
  「我不合，但我叫另一个会话去合」正是这条禁止的形态。

所以：

- ⛔ 消息里**不许**写「不要合并」。那是我自己的权限边界，不是对方的。**我不合**，仅此而已；
  对方合不合是他和 Jason 之间的事，我无权代传这条限制。（Jason 2026-08-30）
- APPROVE 之后**不再排下一轮**，改为**向用户报告**：`OWNER/REPO#N 已 APPROVE，可以合了`（一行）。
- 用户如果明确说「你去让它合 / 你来合」，那是他当场的授权，届时再照办；
  **不要把它写进自动链路**。

## Step 7 — Score + record

```bash
# Score DeepSeek R1a+R1b for the improvement loop
# --useful-findings: count confirmed by Opus R2
# --false-positives: count rejected by Opus R2
# --misses: count R1b security findings NOT in R1a (unique security coverage)
# --review-rounds / --started-at / --finished-at: MANDATORY cost tracking (user request 2026-08-04).
#   STARTED_AT was captured at Step 1 (`date -Iseconds`, before touching the PR); FINISHED_AT is
#   `date -Iseconds` right after post_pr_review.sh returned. duration_seconds is derived from the
#   pair — pass --duration-seconds only when you have a measured value but no timestamps.
#   ⚠️ Never guess these. If a timestamp genuinely wasn't captured, omit the flags (store NULL)
#   rather than invent one — a fabricated duration poisons the v3-vs-v4 comparison it exists for.
# --input-tokens / --output-tokens: this PR's token spend (cost_usd is derived from token_cost.py's
#   price table — do NOT pass --cost-usd unless you have a real billed figure). Same rule: unknown → omit.
# --round-models: what ACTUALLY ran this review, per round. If Codex was quota-blocked and DeepSeek
#   backstopped R3, write that ("R3=deepseek-pk (codex quota)") — this column exists precisely to
#   make substitutions visible instead of silently reading as a full 4-model run.
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/model_eval_db.py record-run \
  --owner OWNER --repo REPO --pr-number N --head-oid HEAD \
  --score SCORE --verdict VERDICT \
  --review-rounds ROUNDS --started-at STARTED_AT --finished-at FINISHED_AT \
  --input-tokens INPUT_TOKENS --output-tokens OUTPUT_TOKENS \
  --round-models "R1a/R1b=deepseek-v4-flash; R2/R4=opus; R3=codex" \
  --round-timings '{"r1a":47,"r1b":52,"verify":238,"r2":274,"r3":300,"r4":228,"post":9}' \
  --useful-findings "R1a:N/M confirmed; R1b added K unique security findings" \
  --false-positives "R1a: X rejected by Opus R2" \
  --misses "Opus R2 independent found Y new; Codex missed Z"

# update watcher state
# ⚠️ last_reviewed_head_oid MUST be the FULL 40-char sha. poll_prs.py compares it against
#    GitHub's headRefOid (always full); a 7-char short sha never matches, so the PR is queued
#    as "head-changed" forever and the daemon re-reviews the same commit every cycle.
sqlite3 "$PR_DAEMON_STATE_DIR/pr-watch.sqlite" \
  "UPDATE pr_watch_targets SET last_reviewed_head_oid='FULL_40_CHAR_HEAD', status='STATUS', \
   last_reviewed_at=CURRENT_TIMESTAMP, review_decision='VERDICT' WHERE repo='OWNER/REPO' AND pr_number=N;"

# token cost — running total across all reviews (per-PR figures already went into model_review_runs above)
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/token_cost.py --add INPUT_TOKENS OUTPUT_TOKENS
```

## Step 8 — Per-PR report + loop + v4 eval delta

Print after every PR:
```
📊 OWNER/REPO#N  VERDICT  [Nround]  v4-pipeline
   R1a: M/T confirmed (T total, M useful, X false-pos)
   R1b: K unique security findings (N confirmed by Opus)
   R2(Opus): Y independent findings, Z R1 rejected
   R3(Codex): [ran|skipped] — W challenges
   R4(Opus): final verdict
   交接: 投给 <会话名> ✅ / 无在跑会话 —— 未投递 / 命中多个 —— 待用户指定
📊 PR status: open N, reviewed M [changes: X, approve: Y]
💰 this PR ~Nk tok | cumulative $X.XX
```
Then next PR. When queue empty: re-poll; if nothing new, `sleep 300` and re-scan.

### ⛔ Chat-output discipline (HARD — user repeatedly enforced)

The **full** review (verified table / findings / rounds / suggestions) goes **ONLY into the PR comment body** via `post_pr_review.sh`. The **chat reply** is terse:

> 审完了。OWNER/REPO#N ✅ APPROVE — [关键点1]；[关键点2]；[关键点3]。细节已在 PR comment 里。

- Give **2-3 load-bearing key points** (what real value you verified, what you caught, whether a negative-path/invariant holds) — **精准点评, not zero**. One line each, no sections.
- **NEVER** in chat: bullet/`###` sections, a "verified/findings/rounds" breakdown, restating what the PR changed, or re-explaining why it's correct. All of that lives in the PR comment only.
- 2-round docs/chore → usually a one-line verdict + "详情见 PR comment", 0-1 key point.
- REQUEST_CHANGES / decision needed → add one line for the blocker/decision.
- The verbose `📊` block above is internal bookkeeping — do NOT dump it to chat verbatim.
- Self-check: if your chat reply has sections or restates technical detail → delete, compress to "结论 + 几条精准点 + 见 comment".

### ⛔ Never merge unless explicitly told (HARD)

Words like "合 / ready / CI 会绿" in a message are **NOT** merge authorization. APPROVE is the endpoint; **ask before merging** unless the user explicitly says "你来合 / merge it / 你给合了". Security-critical PRs (recovery / owner-change / payment / permissions) → confirm even then.

### ⛔ No fake rounds — the label MUST match what actually ran (HARD — user reprimanded)

**Never tag a review `[N-round]` for a round count you did not actually execute.** Doing solo-Opus and labeling it `[4-round]` is fabrication. The round count in the verdict = the number of rounds whose tool calls actually happened in the transcript.

- **2-round** = DeepSeek R1 ran + Opus verdict. Allowed ONLY for docs/chore/comment/version-bump with no `src/`/contract/auth/crypto/payment touch.
- **4-round** = DeepSeek R1 (R1a+R1b) **actually called** → Opus R2 → **Codex R3 actually called** → Opus R4 verdict. REQUIRED for any security-sensitive PR (auth/crypto/payment/permission/.sol/.rs signing/challenge-binding/address-derivation). If you did not run DeepSeek and Codex, you may NOT write `[4-round]`.
- If a model genuinely can't run (e.g. Codex API 529), say so explicitly in the verdict and downgrade the label to what ran (e.g. `[3-round, Codex unavailable]`) — never claim it.

### Mutation testing: literal replacement + assert-hit, never a regex (HARD — added 2026-08-07)

Mutation testing is the main tool for answering 「这条测试承不承重」, and it has one failure mode
that silently inverts the answer: **a mutation that never applied looks exactly like a test that
caught nothing.**

```python
# ✅ correct — a miss is an ERROR, not a false pass
old = "str(b.boxType ?? b.box_type ?? 'lidbase', 'boxType', 40)"
new = "str(b.boxType ?? 'lidbase', 'boxType', 40)"
assert old in s, f"变异打不中: {old[:60]!r}"     # ← the whole point
s = s.replace(old, new, 1)
```

```python
# ❌ wrong — `re.sub` "succeeded" by matching a DIFFERENT site; the suite stays green and you
#    conclude the test is not load-bearing. I did this THREE times in a row on CMIC#166.
s2 = re.sub(r'b\.boxType\s*\?\?\s*b\.box_type', 'b.boxType', s, count=1)
print("mutated:", s != s2)      # "True" here means nothing
```

Rules:
- **Literal string + `assert old in s`.** Never a regex, never `count=1` on a pattern that can match
  more than one site. `s != s2` is not evidence the intended line changed.
- **Verify the mutation landed** before believing the test result — print the before/after of the
  exact line if there is any doubt.
- **Restore with `git checkout -- <file>`** and confirm `git status` is clean before moving on.
- The author of CMIC#167 hit this same trap independently the same day and wrote it into their own
  PR body: 「变异测试自己也需要先验证『变异真的生效了』—— 否则它会给出一个虚假的安心」.

### R1(DeepSeek-flash)的产出分布 —— 决定开跑前给它多少权重

约 **4/25** 条 finding 撑得住。分布极不均匀：**增量轮 + 喂了上一轮 findings 时最高(≈2/4)**，
真实代码 diff 偶尔 1/3，**大 PR 首审 ≈0**，**纯文档 0/12(且会编造 file:line)**。
两种退化形态认出来就行，不用去 debug：同一条 finding 报两个严重度；finding 自我否定后以「No issue」结尾。

这**不**允许跳过 R1(constraint #5)，它允许的是**不为它花判断轮**：便宜地核一下、有证据地驳回、继续走。
完整数据表与退化实例：见 `references/incidents.md#r1-yield-by-situation`。

### Credibility = mechanical evidence, not model count (HARD)

For security-sensitive PRs, **run the tooling — don't reason from reading**. Default to:
- `forge inspect` / `forge test` / `cast call` / `cast sig` (keccak selectors) / on-chain `eth_call` decode — verify claims against ground truth.
- Read BOTH sides of any cross-layer contract (e.g. SDK encoder ↔ on-chain verifier; host ↔ TA) and map every case — don't trust a grep snippet.
- A review that says "I ran X, result Y" is worth more than three models reasoning. Prefer adding verifiable evidence over adding model passes.
- 🔴🔴 **CROSS-LAYER IMPACT ANALYSIS IS THE REVIEW — not the changed lines.** A change to one layer is only safe if every COUPLED layer that must stay consistent was changed in lockstep. Reviewing only the diff'd file is not a review. For EVERY PR, before any verdict, explicitly enumerate the coupled layers and CHECK each one (open the file, don't assume):
  - **CA(host) ↔ TA**: the recurring #110/#113/#121 bug class. If the **TA** changes an op's challenge binding (None↔Some / payload / tag), the **host** `resolve_passkey_assertion` `delegate_challenge_to_ta` for that EXACT op MUST flip to match — else the host rejects the committed challenge before it reaches the TA (`webauthn.rs` "challenge mismatch") and strict is unreachable. And vice-versa: if the host changes delegate, the TA's Some/None must match. **When you see a TA binding change, your FIRST action is to grep the host delegate call site for that op.** (I violated this on #121: reviewed the TA `mint_label_digest` in isolation, APPROVED, and missed that the host still passed `delegate=false` → strict mint dead. The user's Codex caught it. Inexcusable — I had verified this exact invariant in #113/#114/#116 the same session.)
  - **SDK ↔ TA ↔ on-chain contract**: any digest/commitment must match across all three (the #137 grant-packing class).
  - **proto wire change** → host + TA co-deploy; partial deploy + bincode trailing bytes = silently-ignored new fields.
  - **An op's commitment must bind the OPERATION/ENDPOINT itself** — two ops that can produce the same commitment (e.g. empty-label `create` vs `refresh`, same tag) are cross-replayable: the user's signature is over the commitment, so command-dispatch separation does NOT prevent replaying one op's assertion into another. The endpoint/op must be in the digest (distinct tag).
  - **Feed Codex BOTH sides of every coupling** (TA binding AND host delegate; SDK AND contract). If you only paste the changed side, Codex is blind to the inconsistency too — that's how my #121 Codex pass also missed the host delegate.
- 🔴 **For commitment / signature schemes, byte-matching the digest is NOT enough — verify BOTH parties can actually OBTAIN every bound input at the moment they must compute it.** A commitment over a field the client can't know (server-assigned id, host-derived value) is *unsatisfiable* under strict mode even if the SDK and TA hash it identically. (Proven: I approved AirAccount#118 + aastar-sdk#138 mint-param binding — verified the digest matched byte-for-byte — but missed that `index`/`ttl`/`subject` are server-derived, so the client ceremony can't compute the commitment → strict mint would break. Reverted in AirAccount#120.) Ask: "at ceremony time, does the committing side already hold every committed field?" If not, the scheme is broken regardless of byte-parity.

### Five mechanical habits, each bought with a real mistake (added 2026-08-07)

All five are cheap, all five caught (or would have caught) something the same night. Run them as
steps, not as things to remember.

1. **核 head 要核三次：`git worktree add` 之后、`post_pr_review.sh` 之前、post 之后核 `review.commit_id`。** They can
   differ — a force-push between the two calls is normal.
   ⚠️ **只核第一次是不够的，这是 2026-08-27 用实际事故买来的。** 评审窗口有 20-60 分钟；
   `CoLivingOS#213` 的 force-push 恰好落在我 `gh pr view`(04:13:15Z) 和 post(04:30:37Z) 之间，
   GitHub 把 APPROVE 记在了新 head 上 —— 我批准了一棵没读过的树，最显眼那条发现对新树不成立，
   只能公开撤回。完整规程见 Step 6 开头那两条。
   *(实例见 `references/incidents.md#habit-cmic-175-1050`)*

2. **When a comment, PR body, or doc cites a test / guard / script, grep for it right then.**
   *(实例见 `references/incidents.md#habit-cmic-176-1055`)*
   ⚠️ **A repo-wide miss is not yet a finding — the runner may live OUTSIDE the repo.** Before
   writing "cites a script that does not exist", also search `~/.claude/skills/`, `~/.claude/plugins/`,
   and anything else on the invoking `PATH`. *(CMIC#189: `acceptance.md:60` and `progress.md:45` both
   name `followups.sh count-open` as one of pilot's three delivery gates; `find` over the whole repo
   returned only `followups.md`. I had the finding half-drafted. It lives at
   `~/.claude/skills/pilot/scripts/followups.sh` — the docs were right and I was one keystroke from
   filing a fabricated one.)* The productive move after locating it is to **run it against both sides
   of the diff**: base vs head. That is the real check for an automation-consumed file, and it is
   cheap — `count-open` went 15 → 19 with all four new lines parsing, which is what actually cleared
   the PR's only machine-readable risk.

3. **A consistency checker's blind spot is everything being consistently WRONG.** It verifies
   agreement, not truth — and "nobody updated any copy" satisfies agreement. When reviewing one, do
   not stop at "do contradictory copies go red"; also ask **"does an entire missing/absent entry go
   red"**, and require an *independent* source of truth (git log, the real table, the source file).
   *(实例见 `references/incidents.md#habit-cmic-175-1074`)*

4. **Any count that goes into a conclusion gets computed two different ways first.**
   *(实例见 `references/incidents.md#habit-cmic-175-1079`)*

5. **When the control case fails, suspect your measuring apparatus before the thing under test.**
   *(实例见 `references/incidents.md#habit-cmic-176-1084`)*

### Feed full context to DeepSeek and Codex (HARD — their errors are context-starvation)

DeepSeek's false positives and Codex's "INSUFFICIENT_CONTEXT / can't fetch" are almost always missing-context, not model weakness. So:
- **DeepSeek R1**: pass the compressed diff **plus the relevant contract/source snippets** the finding depends on (e.g. the EIP-712 typehash, the storage layout, the verifier function) inline in the prompt. Don't make it guess the upstream shape.
- **Codex R3 (PK)**: pass the diff + the post-R2 findings + **the cross-layer source it must check** (e.g. both the SDK encoder and the on-chain/TA verifier, the op→flag mapping) inline. NEVER rely on Codex fetching the diff itself. Give it a concrete claim to refute and the evidence to refute it with.
  - 🔴 **Paste source VERBATIM — never hand-summarize a struct / domain / signature / type when feeding Codex.** Copy the exact lines from the file. If you retype or "simplify" a definition you WILL drop a field, and Codex will report a guaranteed false positive on the field you elided. (Proven: aastar-sdk#137 — I summarized an EIP-712 domain without its `chainId`; Codex immediately raised a bogus `[High]` cross-chain-replay finding. The field was in the actual code.) Whenever Codex flags a missing field/check, FIRST re-grep the real source before believing it — the omission is usually in your prompt, not the code.

## v4 是既定管线（v4-vs-v3 评估已结案 2026-08-07）

别再跑 v4-vs-v3 对照。要重评某一环用它自己的口子：constraint #5 的 flash 评级
(`model_eval_db.py provider-summary --provider deepseek --model deepseek-v4-flash`)和下面的 triage 审计。
回滚脚本在 `SKILL.md.bak-v3-20260619`。结案理由：见 `references/incidents.md#v4-vs-v3-closed`。

## Triage validation (run periodically)

```bash
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py audit --repo OWNER/REPO --pr N --found-issue true|false
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py flag-miss --repo OWNER/REPO --pr N --note "..."
python3 /Users/jason/Dev/tools/PR-Daemon/scripts/triage_db.py report
# Target: false-negative < 5%
```

## Mandatory Per-PR Checklist

```
[ ] poll_prs.py surfaced this PR (new/head-changed, in-scope org)
[ ] compressed the diff → /tmp/pr-N-compressed.diff (noted dropped files if any)
[ ] if issue linked: fetched issue DoD + drafted Issue compliance section
[ ] R1a: DeepSeek full review → /tmp/pr-N-r1a.md
[ ] R1b: DeepSeek security-only → /tmp/pr-N-r1b.md  (parallel with R1a)
[ ] Sonnet merged R1a+R1b → /tmp/pr-N-r1-merged.md (deduplicated)
[ ] confirmed 2/4-round triage (security hard-rule → force 4; uncertain → escalate)
[ ] if the PR touches a ledger/config/docs file: ran the 🔧 mechanical test (named the consumer,
    ran it on base AND head) and recorded both outputs — did NOT triage it by the file's name
[ ] recorded triage decision (triage_db.py)
[ ] 2-round: Sonnet verdict directly
[ ] 4-round: Opus R2 read diff independently + challenged R1 → /tmp/pr-N-r2.md
[ ] 4-round: post-R2 gate applied (Medium+ → Codex R3; all-Low → skip)
[ ] 4-round: if Codex ran → targeted hunks only (±20 lines per Opus-confirmed Medium+)
[ ] 4-round: Opus R4 got full compressed diff + all round context → final verdict
[ ] verdict is APPROVE or REQUEST_CHANGES (not COMMENT)
[ ] respected Codex's points one by one (if Codex ran)
[ ] **post 之前**重核 head == 我实际读的那个 sha（force-push 会落在评审窗口里 —— 见 Step 6 开头）
[ ] posted via post_pr_review.sh (PAT, no account switching)
[ ] **post 之后立刻确认 review.commit_id == 我读的 sha**（一条 gh api，一秒；不一致=重审增量）
[ ] ⛔ **投递（Step 6.6）—— post 之后的下一个动作只能是 ListAgents。** 发出去，或者在 Step 8
    汇报里写明「无在跑会话 —— 未投递」。**没做完这一格，这个 PR 就没审完**，不许开下一个 PR 的判断轮
[ ] scored DeepSeek R1a+R1b separately in model_eval_db
[ ] printed per-PR v4 eval delta (R1 confirmation rate, Opus R2 independent findings)
[ ] updated pr_watch_targets in SQLite
[ ] Step 6.6: **无论 APPROVE 还是 REQUEST_CHANGES 都要发**（6.6.2，无例外）。ListAgents 找原仓库会话 → 命中 1 个才发；发了要带回信地址+回信要求；**消息里不许写「不要合并」**（那是我自己的约束，不转发给别人）；**命中 0 个必须在 Step 8 汇报里写明「无在跑会话 —— 未投递」**
```

## Hard Rules

- **NEVER MERGE.** Pure reviewer — APPROVE or REQUEST_CHANGES only. `$pr-fix` handles merging.
- **也不许让别的会话替你合**（Step 6.6.5）——「我不合但我叫它合」是 permission laundering，同样禁止。交接链的终点是 APPROVE。
- **Sonnet is executor only** — no judgment on 4-round PRs. Sonnet formats, runs scripts, merges lists.
- **Opus makes the 4-round final call** — Sonnet does NOT override or second-guess Opus's verdict.
- **Codex PK targets Opus R2 findings** (not DeepSeek R1 findings) — challenge the best analysis.
- **Security-sensitive PRs always go 4-round** — no downgrade.
- **Never COMMENT-limbo** — always APPROVE or REQUEST_CHANGES.
- **Never `gh pr review` directly** — always `post_pr_review.sh`.
- **Scope = `~/.config/prbot/repos.conf` (single source; see "ONE list, ONE command")** — review iff the repo is listed there. That file is the
  allowlist and it DOES include individually added personal repos (e.g. `jhfnetboy/CMIC`); see
  ABSOLUTE CONSTRAINT #4. (This line used to read "3 orgs only — never personal PRs", which
  contradicted constraint #4 and made a reviewer stop mid-run to ask which one to obey.)
- **Always score R1a+R1b separately** — the dual-pass split is the key v4 innovation to measure.
- **Codex gets targeted hunks, NOT full diff** — ±20 lines per Opus-confirmed Medium+ finding.
- **Opus R4 always gets full compressed diff** — missed-finding scan requires full context.
- **Post-R2 all-Low → skip Codex** — Opus R4 covers with full diff sweep.
- **Track v4 vs v3 metrics** every 5 PRs — if no improvement, rollback.

## ⛔ Mandatory self-assessment — END every review with this (HARD — user reprimanded)

After posting the verdict for a PR, the **chat reply** must close with a compact self-assessment block. This is non-negotiable and exists because the reviewer repeatedly mislabeled solo-Opus reviews as multi-round.

```
🔎 自评 — OWNER/REPO#N
- 轮数: <实际跑了几轮>  (skill 要求: <triage 要求几轮>)  → 一致? ✅/❌
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): <喂了什么 context? 产出?>  — 默认必跑;只有两种豁免(纯文档/台账、增量=修我自己上一轮的 findings),且必须点名是哪一种(见 ABSOLUTE CONSTRAINT #5)。
    真没跑 = 本轮不合格，必须现在补跑再收尾，不能带着"未跑"过关。
  · R2 Opus: <读了什么/跑了什么工具(forge/cast/eth_call)/cross-layer 验了什么>
  · R3 Codex: <ran? 喂了什么 context inline? CHALLENGE/CONFIRM>  | 或 "未跑 — 原因(如 529)"
  · R4 Opus 裁决: <verdict>
- 机械证据: <列实跑的工具命令 + 结果，如 "cast call gToken()→canonical ✓">  | 或 "无 — 应补"
- **DeepSeek flash 评级**: <1-5> — <一句话：这轮它的 finding 有没有站得住？假阳性？漏了什么后面轮次/我自己抓到的？>
  一句话改进建议(如有): <prompt 更紧/喂更多 context/diff 范围更窄 等>
- **我驳回了哪些 finding**（🧪 试用 T3）: <逐条：谁提的 · 它说什么 · 我凭什么拒 · 我**跑了什么**才敢拒>
  | 或 `无可驳回 — <一句话：这轮子模型/Codex 的 finding 全部成立>`
- 与 skill 设计是否一致: <一致 / 偏差点>
- 改进建议: <若我偷工 → 怎么补; 若 skill 本身该改 → 具体改什么>
- **🧪 试用项记录**（每条一行，记号只用 命中/空转/碍事/未执行/N-A；同步写进 `references/trials.md`）:
  · T1 意图: <记号> — <证据>
  · T2 R3产物核验: <记号> — <证据>
  · T3 驳回清单: <记号> — <证据>
```

Rules for the self-assessment:
- **Be truthful about gaps.** If you skipped a round or a tool you should have run, say so here and either run it now or flag it — do NOT paper over it.
- **R1 DeepSeek has exactly TWO allowed skips** (pure-docs/ledger PR; increment that only fixes your own prior findings — see ABSOLUTE CONSTRAINT #5). Naming the exemption is required: write `R1 未跑 — 纯文档` or `R1 未跑 — 增量=修我自己上一轮的 findings`. **Any other reason is not a reason** — if you are about to write "R1 未跑" for a real code diff, stop and go run it before finishing the review.
- If the round count or model usage **deviated from what the triage required**, the self-assessment must state the deviation AND the corrective action (run it now / re-review).
- If the deviation reveals a **skill-process problem** (e.g. a step that's unrealistic, or context that should be auto-fed), include a concrete **skill-improvement recommendation** here, and offer to edit the skill.

### 🧪 试用项那三行怎么记（2026-09-02 加，Jason 指定）

新加的 skill 步骤先按**试用**处理，不当既定管线：每次 review 记一行，攒够了再结案。
完整的假设 / 证伪判据 / 结案规则在 `references/trials.md`。

- **记号只用五个**：`命中`（因为它我做了/发现了原本不会的事，且写得出是什么）、
  `空转`（照做了但结论一个字没变）、`碍事`（花了时间还把注意力引开，或逼出错误结论）、
  `未执行`（我没照做 —— 这不是空转，要写为什么）、`N/A`（这一轮结构上不适用，如 2-round 不跑 R3）。
- ⛔ **必须能记成负面。** 一条试用项如果从加进来到结案**从没被记过「空转」**，
  那不是它有多好，是这一栏在敷衍 —— 结案时按敷衍处理，直接删。
  **举证责任在这条规则身上，不在删它的人身上。**
- ⛔ **同一轮里同时写进 `references/trials.md` 的观测表**（日期 · PR · 记号 · 一句话证据）。
  只写在聊天里的记录活不过这个 session。
- **到达结案条件时（次数满 或 到期日）**：当轮 review 收尾时必须给出结论
  —— `保留` / `删除` / `微调(具体改什么判据)` —— 把整节搬进 `trials.md` 的「已结案」，
  并**当场改 SKILL.md**。不许写「再观察观察」：那等于默认保留，而默认应当是删除。
- This block is part of the terse chat reply [[feedback_terse_chat_output]] — keep it compact, but it is the one place where listing per-round/per-model detail is REQUIRED (not "see PR comment").