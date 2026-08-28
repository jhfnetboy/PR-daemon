# PR skill — 事故档案

每条规则是哪次事故买来的、当时测到了什么、它替换掉了什么、怎么回滚。

`SKILL.md` 只留可执行的规程；这里是它的证据链。**规则本身一字未动，只是搬了家。**

从 SKILL.md 的一行指针跳过来读。


---

## scope-three-sources

What this replaced, so nobody rebuilds it: scope used to have *three* disagreeing sources —
a hardcoded `ORGS = [...]` copied into four scripts (the list that actually ran), a
`start-loop-pinned.json` read only by `start_loop_scope.py`, and `repos.conf` read only by
`review_watch.py`, **which is not running** — so pinning a repo there changed nothing.
`$start` is now an alias for `$pr start`; there is no second entry point.


---

## r1-170-round-record

> **The conclusion, from the 170-round record:** keep flash, but its job is **cheap hypothesis
> generation on real code diffs**, not being a findings source. It has genuinely hit — `#190`'s two
> Highs (non-idempotent ALTER; `page_html` missing `assertNoCommercial`), the pii-probe sweep deleting
> a concurrent sibling's live file, the `/isn.t supported/i` dot — and once it was *wrong but pointed
> the right way*, and following it up found the real bug. That is worth its ~40 seconds.
>
> **Run R1a on every round EXCEPT these two, where 0/N is structural rather than unlucky:**
> 1. **Pure-docs / ledger PRs** — measured 0/12 then, still 0/N now; on a long document it has
>    fabricated every `file:line` anchor it emitted.
> 2. **Incremental rounds whose increment is fixes to YOUR OWN prior findings** — the findings are
>    already known and written down, so there is nothing left for it to independently find. (Measured
>    repeatedly on `CMIC#190`/`#194`/`#196`/`#197`: `--prior-review` made it *worse*, not better.)
>
> Everywhere else — new PR, real code diff, any increment that adds new logic — **run it**. "I can do
> a good review without it" is still NOT a valid reason to skip: on a real code diff its hit rate is


---

## triage-mechanical-test

  **The test was validated in both directions before this clause shipped** (a rule that only ever
  answers "2-round" is worse than no rule — see habit #5 on suspecting your own apparatus):

  | control | PR | changed lines | `count-open` base → head | verdict |
  |---|---|---|---|---|
  | positive | `blog#57` | flipped FU-16/FU-19 `- [ ]` → `- [x]` | **14 → 12, differs** | 4-round ✅ |
  | negative | `blog#58` | prose + status words backed by merged PRs | **12 → 12, identical** | 2-round ✅ |

  > **What this replaced, and how to roll it back.** Until 2026-08-23 this clause listed
  > `docs/agent/tasks.md|roadmap.md|progress.md` **by filename**, so any touch of those files forced
  > 4 rounds. Measured failure: `MushroomDAO/blog#58` — a pure ledger-sync PR (prose + status words
  > already backed by merged PRs #54/#55/#56/#57) was triaged 4-round, while **both** of its blocking
  > findings came from mechanical checks alone (grep the ledger; copy `searchVectorRanked` verbatim
  > into node and run four failure scenarios; `count-open` on base vs head → 12/12, unchanged). Two
  > Opus rounds would have bought nothing. Rollback = restore the filename list above; the old text is
  > in `git log -S "automation-consumed files (NOT trivial"`.


---

## prose-two-readings

> *(CMIC#189, FU-20's 「而不是只保护 main」. I queried as repo owner: `branches/main` →
> `protected: false`, `preview` likewise, owner `.type == "User"` so no org ruleset, `/protection`
> and `/rulesets` both 403. Airtight — for the GitHub-branch-protection reading. R3 Codex then
> pointed at `.github/workflows/ci.yml`: `on: push: branches: [main]` + `on: pull_request`, so a
> direct push to `preview` runs NO CI while a push to `main` does. The mechanical asymmetry is real
> and the sentence is literally true under that reading. My finding died; the author was right.)*


---

## r4-falsification-measured

> | PR | What R4 was told to attack | Result |
> |---|---|---|
> | CMIC#165 | 「my composite box is a flat rectangle; a real box has shadows/reflections so it may carry far more energy」 | **Refuted the counter** (real box = 11.2% of pixels, 15.6% of edge energy) and then found the decisive fact nobody had: the positive control was invalid |
> | CMIC#166 | 「how likely is a client-chosen id to match a phone pattern in practice?」 | **Downgraded** the finding: 200k samples of the real generator, 0 redactions — and redirected it to `product`, which does bite |
> | CMIC#167 | 「is `sample.ts` a demo path? if so the High drops」 | **Ruled the counter out** — it is the customer's own download |
> | CMIC#165 r3 | 「look for an outer `en`, hoisting, or a path where the callback fires later」 | **Ruled all out**, then escalated a sibling Low → High |


---

## deliver-gate-incident

> **发生了什么：** `CoLivingOS#214` post 完 + 入库完，我立刻跳去下一个 PR 的 R2 —— Step 6.6 一个字
> 没做。#211/#212/#213 都发了，唯独这个漏了。我给自己的解释是「Step 6.6 排在 Step 6/7 之后，看着
> 像收尾杂项，而下一个 PR 已经预备好在等」。**这个解释本身就是 bug 的形状**：6.6.2 那段注释早就


---

## always-deliver-no-exception

> **这一步不是可选的，也不是「有必要才发」。** 原来的规则给首轮 APPROVE 开了个「省噪音」的口子，
> 而实际效果是**投递这一步整个被跳过而没人发现** —— 2026-08-26 实测：`CoLivingOS#185`
> RC 了没发、`SuperPaymaster#375` RC 了没发、`DevLoop#2` APPROVE 了没发也没在汇报里
> 写「无在跑会话」。三次里两次是**明确违反当时已有的规则**，一次是钻了那个口子。
> 一个「有时候不发」的规则，执行起来就会变成「经常忘了发」。所以取消例外。


---

## r1-yield-by-situation

#### Where R1 (DeepSeek-flash) actually pays (measured over ~10 rounds, 2026-08-06/07)

Roughly **4/25 findings** survived across a full session. The distribution is not uniform, and it
tells you how much weight to give R1 before you start:

| Situation | R1 yield | Note |
|---|---|---|
| **Incremental round, `--prior-review` fed, prior findings ARE the subject** | best (≈2/4) | This is the one place it earns its slot — checking 「上一轮那条改干净没有」 |
| Real code diff with new logic | occasional 1/3 | It hit a real `--write` anchor bug once |
| First review of a large PR | ~0 | Missed a Critical, a High, and three Mediums across three PRs |
| Pure-docs / long-document PRs | 0/12 | Worse: on a 1000-line doc **all three file:line anchors were fabricated** |

Two recurring degradation shapes to recognize rather than debug:
- **The same finding filed twice at two severities** (identical text at Medium and Low) — seen on
  two consecutive PRs.
- **A "finding" that self-refutes mid-sentence** and ends with 「No issue」 — it emitted its reasoning
  as the finding.
- On an incremental round, if R1's findings all name files the PR does not own, it diffed a
  pre-rebase base — see the Step 0b short circuit.

None of this licenses skipping R1 (constraint #5 is absolute). It licenses **not spending judgement
rounds chasing it**: verify its findings cheaply, reject them with evidence, and move on.


---

## v4-vs-v3-closed

### v4 是既定管线 —— 别再跑 v4-vs-v3 评估（结案 2026-08-07）

这里原本挂着一张 v4-vs-v3 对照表、一条「跑够 10 个 v4 PR 再评」的指令，和一条回滚扳机。
**实测 v4 自 2026-06-19 起已经跑了 155 个 PR** —— 是它自己那个决策点的 15 倍，回滚从未发生。
一个 15 倍过期的决策点不是待办事项，是每轮 review 都要读一遍的噪音，所以删掉。

v4 就是当前管线。真要重新评估某一环，用它自己的口子：constraint #5 的 flash 评级
（`model_eval_db.py provider-summary --provider deepseek --model deepseek-v4-flash`）和
下面的 triage 审计。回滚脚本仍在 `SKILL.md.bak-v3-20260619`，需要时自己 `cp`。


---

## habit-cmic-175-1050

   *(CMIC#175: I recorded a review against `1421fe0e` while my worktree held `ffde325`. The findings
   happened to still hold, so it cost nothing — this time. If the push had landed after my fetch I'd
   have reviewed stale content and reported it as current.)*


---

## habit-cmic-176-1055

   *(CMIC#176: the justification for narrowing a **PII guard** was "`test:pii-guard` has a
   counter-control". Whole-repo grep: one hit — the sentence itself. Narrowing a security guard on a
   test that does not exist. This is the same shape as a pointer into something the consumer cannot
   see.)*


---

## habit-cmic-175-1074

   *(CMIC#175: I approved a 3-way ledger checker after 4/4 mutations went red — all of them
   contradiction mutations. #176 then merged without updating any of the three, and it stayed green.
   The author found it, not me.)*


---

## habit-cmic-175-1079

   *(CMIC#175: my first pass counted backtick-quoted table names as statuses and produced
   `DONE=19/READY=1`; tightened to the valid status words it was `21/2`. Those numbers were going
   into the review. Same night I rejected a subagent's "213 multi-line templates" — it was 0.)*


---

## habit-cmic-176-1084

   *(CMIC#176: my first PII counter-control had all six cases pass, including the positive control —
   which reads as "the guard is completely blind". Actual cause: `scan_files` uses `git ls-files` and
   my probe was untracked, plus `ARCHIVE` is hardcoded. The PR author independently hit the other half
   of the same trap — his probe email was filtered by the gate's own `*example*` rule. **A result that
   says "everything is broken" is far more often a broken harness.**)*


---

## constraint5-history

> (originally 2026-08-01 "never optional"; **the record it demanded is now complete — 170 rounds over
> 80 PRs by 2026-08-08, 8.5× its own 20-round target — so the decision it was collecting for is made,
> and the blanket rule is replaced by the conclusion.** Same shape as the v4-vs-v3 eval section deleted
> the same day: an expired decision point that kept costing a round.)

---

## rebase-short-circuit-why

Why this is worth a rule: on CoLivingOS/CMIC#165 a rebase re-queued the PR and a full 4-round pass
would have spent three judgement rounds re-deriving conclusions that could not have changed. The
increment vs. the last-reviewed head is NOT empty in that case — it contains the merged sibling's
code — so the diff size alone will not tell you. A tell: **R1's findings all point at files the PR
does not own** (it diffed a pre-rebase base). Treat that as corroboration, not as findings.

---

## recall-prior-verdict-why

**Why ① is not optional on an incremental round:** the fix commit's message tells you what the author
*believes* he fixed. Only the previous review tells you what was actually blocking, and **in what
words** — so you can re-run *the same probe that found it* instead of inventing a new one. On
CoLivingOS#74 that is exactly what settled it: the mutation that was green last round went red this
round, and that comparison is only possible if you still have last round's mutation.

---

## codex-timeout-shape

> makes this worth a rule rather than a footnote is the failure's SHAPE: `exit 143`, no output
> file, nothing on stderr. That is indistinguishable from "Codex is down", and the natural next
> move is to fall back to DeepSeek — silently downgrading R3 on a run where Codex was working
> fine. (CMIC#189: killed at 120 s, re-run with `timeout: 480000` returned a clean 4/4 in ~5 min
> and CHALLENGED the round's strongest finding. Falling back would have lost that.)
> The outer kill leaves no orphan and does not trip the circuit breaker — verified after the fact
> with `pgrep -fl "codex exec"` and by reading `codex-breaker.json` — so the only cost is the
> wasted attempt, provided you do not misread it as an outage.

---

## codex-sandbox-offline

> `npx` / `pnpm` / `tsx` / `pip` all fail there — `npx` tries the registry and dies with
> `ENOTFOUND`. Both times Codex behaved correctly: the prompt said 「不对就说出来并停下」 and it
> stopped. The fault was mine, twice.
