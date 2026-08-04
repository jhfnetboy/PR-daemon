## 🤖 Re-review of the round-4 fix commit — DeepSeek R1a/R1b + Opus R2/R4 + Codex R3 PK

**Scope:** incremental diff `abe5c0ae..ca21e658` (this PR has been through 4 rounds already; each prior
round found real bugs in `kms/deploy/updater/aastar-node-updater.sh` and the author fixed them). This
round is a re-review of the round-4 fix commit's 4 findings + 4 Low items, focused on the new
symlink-based lock (`acquire_lock`/`cleanup`), `load_policy_env`, `rollback`'s dangling-`last-good`
check, and `cmd_recovery`.

**VERDICT: REQUEST_CHANGES**

The round-4 commit message claims the lock TOCTOU from round 3 is closed ("原子 symlink 锁...没有两步窗口
...并发也绝不会两个进程都以为持锁"). It is not. Mechanical, independently-reproduced testing (by me, by
an independent Opus reviewer with its own harness, and by Codex running its own shell commands) confirms
**two High-severity ways this lock can still grant simultaneous holders or be silently disabled**,
neither of which the new tests (T47-T50) exercise.

### 🔴 Blocking

1. **[High] `acquire_lock:195` — a pre-existing DIRECTORY at `$LOCK_LINK` makes the "atomic" lock a
   permanent no-op.** `$LOCK_LINK` is the exact same path the *old* `mkdir`-based lock (`LOCK_DIR`) used
   before this PR. Any node that crashed while holding the old-format lock — including via the round-1
   bug this repo already hit ("rmdir 失败→锁永不释放") — has a leftover directory sitting at that path
   the moment it receives this upgrade. `ln -s "$$" "$LOCK_LINK"` does **not** fail against an existing
   directory; standard `ln` semantics create `$LOCK_LINK/<pid>` *inside* it and return 0. The `while`
   loop exits immediately believing the lock is held. `rm -f` (used in both `cleanup` and
   `cmd_recovery`) cannot remove a non-empty directory, so there is no self-heal — mutual exclusion is
   disabled for that node **forever**, silently.
   ```
   $ mkdir -p /tmp/lock; ln -s "$$" /tmp/lock; echo exit=$?     # exit=0
   $ [ -d /tmp/lock ] && echo "still a directory"               # still a directory
   $ ln -s 99999 /tmp/lock; echo exit=$?                        # exit=0 — second "holder" too
   ```
   Reproduced independently 3 ways (me / Opus R2 / Codex R3 running its own `ln -s "$tmp/d"; ln -s $$`).
   Fix: before the loop, detect `[ -e "$LOCK_LINK" ] && [ ! -L "$LOCK_LINK" ]` and migrate/`rm -rf` the
   stale directory (one-time), or `die` for manual intervention rather than silently proceeding unlocked.

2. **[High] `acquire_lock:197-202` — TOCTOU between the `kill -0` liveness check and the unconditional
   `rm -f` two lines later reintroduces exactly the double-holder bug class round 3 already found.**
   A racer that read a stale dead-pid can execute its `rm -f` *after* a different process has already
   legitimately re-acquired the lock with a fresh, live pid — deleting that live lock — then win the
   now-empty slot itself. Two processes end up simultaneously believing they hold the mutex. Raw `ln -s`
   atomicity is sound (verified separately: 20-way single-shot race → exactly 1 winner); the defect is
   the gap between "check" and "act", not `ln -s` itself.
   Reproduced independently 2 ways: I extracted the loop byte-for-byte into an isolated harness (8
   concurrent racers over a pre-seeded dead-pid symlink) and got genuinely overlapping acquire→release
   windows in 3/5 rounds (e.g. P2 holds `.5367→.850`, P4 *also* acquires at `.5388`, well inside P2's
   window). Opus R2 independently reproduced the same overlap with its own 6-8 process harness. Codex
   confirmed from the code that no compare-before-delete/rename-claim/inode check exists anywhere in the
   reclaim path.
   Fix (production is Linux/systemd): use `flock -n 9` on an fd (kernel releases it automatically on
   process death — no pid-liveness heuristic, no stale-reclaim TOCTOU at all), falling back to the
   symlink scheme only where `flock(1)` is unavailable (macOS test env). If keeping the symlink scheme,
   at minimum change reclaim to atomic-steal: re-confirm the link still equals the pid you read before
   deleting (`mv "$LOCK_LINK" "$LOCK_LINK.stale.$$"`, only one racer's rename can win), never blind
   `rm -f`.

### 🟡 Should fix

3. **[Medium] `acquire_lock:197` — dead-holder detection is pid-only via `kill -0`, no age/mtime
   fallback, and `oldpid` isn't validated as a positive decimal PID before being passed to `kill -0`.**
   A recycled pid makes `check` read an unrelated live process as "another instance running" and
   silently `exit 0` forever — the node stops receiving updates with zero alerting until reboot (`apply`
   at least hard-fails via `LOCK_FATAL=1`; `check` does not). Separately (Codex's finding, verified):
   `kill -0 0` and `kill -0 -1` both return success (own process group / broadcast) — a corrupted or
   `0`/`-1` symlink target would be misread as "alive", causing the same permanent false contention.
   Fix: reject non-positive-decimal `oldpid` before `kill -0`; add an mtime/age bound as a staleness
   fallback independent of pid liveness.

4. **[Low] `cmd_recovery:381` — unconditionally `rm -f`s the lock without checking ownership.** If a
   `check`/`apply` instance is genuinely running at boot when recovery fires (unit ordering guarantees
   start sequence, not that the other process has exited), recovery can delete its live lock, compounding
   finding #2 into a guaranteed double-holder. Fix: reuse the same "only remove if target is a dead pid"
   check as `acquire_lock`.

5. **[Low] `cmd_recovery:393` (F5) — `if rollback "$target"; then ...; fi` with no `else` swallows the
   "board is unrecoverable" failure signal.** `rollback` returns 1 on that branch, but a false `if` with
   no `else` still makes the enclosing function return 0 in bash — `airaccount-updater-recovery.service`
   reports **success** to systemd even when the board has zero valid releases and only a best-effort
   Telegram notify (into a single-slot queue, on a box with no network yet) fired. T50 asserts on
   state/symlink but not on the recovery unit's actual exit code. Fix: add `else warn ...; return 1; fi`
   (or `exit 1`) so unit status reflects reality and `OnFailure=` (if configured) can trigger.

6. **[Low] `acquire_lock:205` (F4) — the function's return value is held together by accident.** The
   `while` loop's last body statement is `[ "$tries" -ge 5 ] && lock_contended ...`, which itself
   evaluates false (and thus returns 1) whenever `tries<5`; it's only saved because `trap cleanup EXIT`
   is the next (and actually last) statement in the function. Reordering those two lines, or anyone
   adding a line after the loop, would silently make `acquire_lock` return non-zero under `set -e` right
   after successfully taking the lock. Add an explicit `return 0` at the end (same pattern this PR
   already applied to `load_policy_env`).

### 🆕 Missed by all 5 prior rounds — full-diff scan (Opus R4)

7. **[Low] `flush_pending_notify:87` — this diff's own level-whitelist fix dropped the `|| echo warn`
   fallback, turning a benign race into a `set -e` abort of the whole `check` run.** Old code:
   `lvl="$(head -1 "$f" 2>/dev/null || echo warn)"` — always succeeds. New code:
   `lvl="$(head -1 "$f" 2>/dev/null | tr -d '[:space:]')"` — no `|| ...` fallback. Under
   `set -euo pipefail`, if `head` fails (e.g. `$f` is deleted between the earlier `[ -f "$f" ]` check and
   this read — a real race, since `flush_pending_notify` runs at `cmd_check:563`, *before*
   `acquire_lock` at `:565`, so two concurrent `check` invocations have zero mutual exclusion across this
   exact window), the pipe fails under `pipefail`, the bare assignment fails, and `set -e` kills the
   entire script right there — `acquire_lock` and everything after it never runs. Verified directly:
   `bash -c 'set -euo pipefail; lvl="$(false | tr -d "[:space:]")"; echo reached'` never prints
   `reached`, exits 1. The very next line (`msg="$(tail ... || true)"`) kept its `|| true` — that
   asymmetry is itself evidence this is an unintentional regression, not a deliberate change. Fix: restore
   a fallback, e.g. `lvl="$(head -1 "$f" 2>/dev/null | tr -d '[:space:]' || true)"`.

### Confirmed correct in this diff (no objection)

- `load_policy_env`'s explicit `return 0` — genuinely fixes `[ -f ] && {...}` returning 1 as `main`'s
  first statement under `set -e` (verified `main()` does call it first).
- `ta_version` dropping the `AU_TA_VERSION_FILE` env override — real closure of the release-tree coupling
  round-3 flagged (though `updater.env`'s `set -a`-sourced `AU_TA_VERSION` itself remains an
  operator-trusted declaration path — worth a comment so it isn't mistaken for fully sealed).
- `rollback`'s `[ -L ... ] && [ -d .../last-good/ ]` dangling-symlink check — correctly forces resolution
  via the trailing slash.
- `queue_notify`'s added `sync` — reasonable for the power-loss path.

### Tests

`kms/tests/updater/test-updater.sh`: **87/87 assertions PASS**, ran locally. But none of the new tests
(T47-T50) actually exercise either High finding: T47 seeds only a *single* process against a stale link
(no concurrent racers, so the TOCTOU window in #2 is never opened); T49's second process contends against
an already-live (never-stale) lock, so it never enters the reclaim branch where #2 lives; no test seeds a
pre-existing *directory* at `$LOCK_LINK` for #1. Suggest adding: (a) `mkdir -p "$NS/lock"` before `check`,
assert it doesn't silently "succeed" past the lock; (b) ≥4 concurrent racers against a pre-seeded dead-pid
symlink, asserting acquire/release windows never overlap.

### Coverage

Full diff reviewed (2 files, 91+/45-, no dropped hunks — small enough to review in full).

---
🔎 自评 — AAStarCommunity/AirAccount#194
- 轮数: 实跑 4 轮(R1a+R1b DeepSeek 并行 → R2 Opus 独立读+并发 harness → R3 Codex PK,自己跑 shell 命令验证
  而非纯推理 → R4 Opus 终裁+全量扫)。triage: 安全敏感(锁/回滚/recovery)→ 铁律强制 4-round → 一致 ✅。
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 喂了增量 diff(244 行,含完整函数上下文的 hunk)。R1a 定位到 acquire_lock:196
    的 stale 回收 `rm -f` 可能删活锁(方向对、机制描述不够精确,没点出"读的是陈旧数据"这个根因),另一条
    tries 计数器顾虑被 Opus R2 否了(边界正确)。R1b 判定"无安全相关面"——**假阴性**,这是一个动了互斥锁+
    回滚逻辑的安全关键 updater diff,不应该 fast-exit。
  · R2 Opus: 独立通读全部改动后,先自建一个逐字节照抄 acquire_lock 循环的隔离 harness,8 并发 racer 打预置
    死 pid 软链,3/5 轮复现出真实重叠的 ACQUIRE 窗口;又单独验证了目录旁路(`mkdir` 一个 lock 目录后
    `ln -s` 仍 exit=0)。产出 2 个 High + 1 Medium + 2 Low,并复核确认了本 diff 里 4 处改得对的地方。
  · R3 Codex: 直接 Bash(scripts/codex_pk.sh)前台同步跑,喂了 5 条 R2 findings + 两段函数完整源码 + 我的
    机械复现记录。Codex 没有停在"读代码判断",自己跑了 `ln -s "$tmp/d"; ln -s $$` 复现目录旁路、跑了
    `kill -0 0`/`kill -0 -1` 验证误判、跑了 `trap`+`set -e` 组合验证返回值遮蔽——5/5 CONFIRM,外加两条独有
    发现(oldpid 未做数字校验、cmd_recovery 无主删锁)。
  · R4 Opus 裁决: REQUEST_CHANGES。全量扫又抓到一条前 5 轮都没人发现的回归(flush_pending_notify 丢了
    `|| echo warn` 兜底,在 pipefail 下会让并发竞态直接 set -e 杀掉整个 check)。
- 机械证据: 本地跑 `kms/tests/updater/test-updater.sh` → 87/87 全绿(命令+完整输出见上方 Tests 节);
  自建 8-并发 stale-lock-race harness(round1-5,3/5 复现重叠持锁,时间线贴在 PR comment 正文);
  独立验证目录旁路(`mkdir+ln -s` → exit=0);独立验证 `set -e`+`pipefail` 会杀掉 `lvl=$(head|tr)` 空
  fallback 的赋值链。
- **DeepSeek flash 评级: 3/5** — R1a 精准定位到了本轮最终成为 High 的那一行代码(acquire_lock:196 的
  `rm -f`),这在一个 244 行的纯 shell diff 里不算容易,值得肯定;但它把根因说成"another process holds
  lock, this deletes it"而没抓住真正的 TOCTOU 机制(读的是陈旧数据,不是当前状态),也完全没提到更严重
  的目录旁路(F1,反而是本轮最该抓的 High)。R1b 在一个改锁+回滚的安全关键文件上判"无安全面"是明确假
  阴性,拖了后腿。改进建议:security-mode 的 fast-exit 启发式对"改了锁/并发原语"这类信号应该更敏感一些,
  不能只看 diff 里有没有 auth/crypto/payment 关键词。
- 与 skill 设计是否一致: 一致。增量 diff(非全量)符合"已 review PR 再次提交拉增量"的规则;安全敏感强制
  4-round;Codex 直接 Bash 前台同步(未走 Agent codex-rescue);R2/R3/R4 都拿到了完整函数源码而非只有 diff
  hunk,避免了"没喂全 context 导致假阳性/假阴性"的已知坑。
- 改进建议: 无偷工之处需要补;可考虑的 skill 改进——对"改并发原语/锁"类 diff,把"要求 reviewer 自建一个
  逐字节复刻的隔离 harness 实测,而非只读代码判断"写成硬规则(不止是最佳实践),因为这轮如果只靠三个模型
  读代码判断,大概率会像前四轮一样被"看起来修对了"的注释和新增测试说服,而实际上新增的 T47/T49 恰好都没
  覆盖到这两个 High 真正所在的窗口。
