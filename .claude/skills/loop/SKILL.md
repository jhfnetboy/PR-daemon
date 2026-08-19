---
name: loop
description: "自收敛巡检梯子 —— Jason 说「开始」/「loop」/「review」任意一个就启动:立刻跑一次,然后 10 分钟档 3 次 → 20 → 30 → 40 → 50 → 60 分钟跑最后一次,自动停止。节奏由 scripts/loop_ladder.py 定,审查逻辑全部委托给未经修改的 pr skill。"
origin: pr-daemon
---

# Loop — 自己会停的巡检梯子

Jason 2026-08-19 定的:**触发词 `开始` / `loop` / `review` 任意一个**(单独说,或者
「开始吧」「loop 一下」这种明显是这个意思的)就启动一轮**会自己收敛并停止**的巡检。

和旧的 `$pr start` 那条 recurring cron **不是一回事**:那条按「闲置 1 小时降一档」调节、
而且**永不停止**;这条按**已跑次数**升档,跑满就**自动停**,不需要谁记得去关。

## 梯子(共 16 次,跨度 500 分钟 ≈ 8h20m)

| 档位 | 次数 | 说明 |
|---|---|---|
| 立刻 | 1 | **算 10 分钟档的第 1 次** |
| 10 分钟 | 2 | 补齐这一档的 3 次 |
| 20 分钟 | 3 | |
| 30 分钟 | 3 | |
| 40 分钟 | 3 | |
| 50 分钟 | 3 | |
| 60 分钟 | 1 | 跑完 → **停** |

⚠️ 别用 recurring cron 去做这件事。`4-59/N` 那套要求 N 整除 60,40 和 50 做不出均匀
间隔(`*/40` 实际是 40,40,20 的循环)。这里用**一次性 cron**(`recurring:false`,分/时/日/月
全钉死),每跑完一次再排下一枚 —— 间隔任意,而且**「不再排下一枚」天然就是停止**,
不需要 `CronDelete`,也就没有「删了忘了建、巡检悄悄没了」那个风险。

## Step 1 — 启动(收到触发词时)

```bash
cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon
python3 scripts/loop_ladder.py status                      # 已经在跑?先告诉 Jason,别叠一层
python3 scripts/loop_ladder.py start --trigger "<原话>"
```

⚠️ **先查 `status`。** 已经有一条活着的梯子就不要再起一条 —— 报告当前进度
(`runs_done` / `next_at`),问要不要重开。

⚠️ **旧的 recurring 巡检要先收掉**,否则两套并行:`CronList` → 找 prompt 含
`[[start-loop]]` 的那条 → `CronDelete`。这是**唯一**允许删它而不重建的场合,
因为这条梯子接管了它的职责;删完要在回复里明说。

然后**立刻执行 Step 2 的巡检一次**(这就是 run#1)。

## Step 2 — 一次巡检 = 原样调用 `pr`

这个 skill **不做任何审查**。一次巡检就是:

1. 锁:`.state/pr-daemon/start-loop.lock`,超过 3600 秒才算过期(一次 4-round review 要 15-25 分钟)
2. `python3 scripts/start_loop_scope.py targets --limit 8` → 得到本轮目标仓库,把 `SCOPE:` 那行压成一行报给 Jason
3. 对每个目标仓库,`Skill(skill="pr", args="<OWNER/REPO>")`,跑它未经修改的 Steps 0-8;
   队列空就 RETURN,**不要**用它 Step 8 那个 `sleep 300` 内层等待
4. 每 post 完一个 PR 的结论就 `touch "$LOCK"` 刷新
5. 一行汇报:`本轮: kms 193 ❌RC · sdk 328 ✅ — 细节见各 PR comment`;没活干就 `本轮: 无待审 PR`
6. `rm -f "$LOCK"`

⛔ 仓库名**只能**来自 Step 2 那条命令的 stdout,不许写死在这个文件里 ——
写死的名单永远比来源先过期。

## Step 3 — 排下一枚,或者停

```bash
python3 scripts/loop_ladder.py next
```

- `action: "schedule"` → 用它给的 `cron` 字段 `CronCreate(cron=<cron>, recurring=false, prompt=<下面的模板>)`,
  然后回一行 `loop: 第 N/16 次跑完,下次 <fires_at>(等 <wait_min> 分钟)`
- `action: "stop"` → **什么都不排**,回一行
  `loop: 梯子跑完了(共 16 次 / 500 分钟),已自动停止。要再来一轮就说「开始」。`

## 一次性 cron 的 prompt 模板

原样用这一段(它自带 Step 2 + Step 3,所以链条能自己接下去):

```
[[loop-ladder]] PR-Daemon 自收敛巡检 —— 跑一次,然后按梯子排下一枚(或停止)

cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon

按 `.claude/skills/loop/SKILL.md` 的 Step 2 跑一次巡检(锁 → start_loop_scope.py targets
→ 逐个仓库交给未经修改的 pr skill → 一行汇报 → 解锁),然后执行 Step 3:

  python3 scripts/loop_ladder.py next

- 返回 action=schedule → 用返回的 cron 字段再排一枚一次性 cron(recurring=false),
  prompt 就是这一整段(原样,包括这一行)
- 返回 action=stop → 不再排,回一行「loop: 梯子跑完了,已自动停止」

⛔ 仓库名只能来自 start_loop_scope.py 的 stdout,不许写死。
⛔ 审查逻辑一律走 pr skill,这条链只管节奏。
```

## 中途停

Jason 说「停」「stop」「别 loop 了」:

```bash
python3 scripts/loop_ladder.py stop
```

再 `CronList` → 删掉 prompt 含 `[[loop-ladder]]` 的那枚待发一次性 cron。
(这里**可以**删而不重建 —— 这正是他要的停止。)

## 已知边界,如实说

- **cron 是 session-only 的**:这个 Claude session 结束,待发的那枚就没了,梯子会停在半路。
  跨越 8 小时的梯子大概率会碰到这件事 —— 启动时就要跟 Jason 讲明。
- 一次性 cron 落在 :00 / :30 会被调度器提前至多 90 秒;梯子的时刻是算出来的,不去凑整。
- 一次 4-round review 要 15-25 分钟,排了几个 PR 的 cycle 实测跑到过 70 分钟。所以
  10 分钟档那几次很可能撞上正在跑的 cycle 而被锁挡掉 —— **这是设计,不是故障**:
  锁的 mtime 表示「距上次有进展多久」,被挡掉的那次不占梯子的次数(次数只在
  Step 3 真跑完时才 +1)。
