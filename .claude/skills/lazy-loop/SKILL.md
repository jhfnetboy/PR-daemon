---
name: lazy-loop
description: 懒巡检 —— 推送为主、每小时兜底一次。启动时扫一遍当前 open 的 PR(含作者已推修复的),审完就等;之后只在收到仓库会话的消息、或每小时那一枚兜底 cron 时干活。取代 `loop` 那条 10 分钟起步的自收敛梯子。触发词:`lazy-loop` / `懒巡检` / 「切被动」。
---

# lazy-loop —— 推送为主,每小时兜底

Jason 2026-09-02 定的。**取代 `loop` skill 那条梯子**(10→20→…→60 分钟自收敛),
理由是那条梯子把大量 tick 花在空转上,而真正的复审几乎全是被推送触发的。

## 为什么是这个形状 —— 当天的实测

| 触发方式 | 数量 |
|---|---|
| **轮询发现的新 PR** | **7 / 10 个** |
| 推送发现的新 PR | 3 / 10 个 |
| **推送触发的复审** | **14 / 14 轮** |

而 8 个在扫仓库里**只有 2 个有在跑的会话**(其余 6 个没有人能给我发消息),
加上 dependabot 的 PR 永远不会发消息、会话也可能死掉 ——
**所以推送包不住「发现」,轮询包不住「及时」。两者各管一半。**

- **推送管复审**:不需要任何机制。会话活着就能收消息,收到就立刻审 —— **不要等下一枚 cron**。
- **轮询管发现**:一小时一次足够,因为它只需要覆盖「没会话的仓库 / bot PR / 新开的 PR」。

## Step 1 — 扫一次(一条命令)

```bash
cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon
python3 scripts/lazy_scan.py
```

输出形如:

```
★ OWNER/REPO#N  head 不同  cur=abc123456789 rev=def123456789  标题
· (draft,跳过) OWNER/REPO#M  标题
open=53 已完成=50 待审=1 draft=3
```

`lazy_scan.py` 内部先跑 `poll_prs.py --sync`(**一次**,覆盖全部 scope 的 53 个 open PR),
再按下面这条判据查 SQLite。**这一条命令取代了以前每轮 8 次 `gh pr list`。**

### 判据是两条,不是一条

```
head_oid != last_reviewed_head_oid      → 新 PR,或作者推了修复
或 last_reviewed_at 为空                 → head 被记下过但从未真评审
```

第二条不是假想:2026-09-02 实测全表 **85 行**处于这个状态。只看 head 会让这些
**从未被评审的 PR 静默算作已完成**。(那 85 行逐条核过,没有真漏,但那条路径是真的。)

### ⛔ `open=` 那一行是承重的,不许省

「待审=0」和「`gh` 调用失败」在其余输出上**一模一样**。
写这个脚本时第一版把 `state='OPEN'` 写成了大写(库里存的是小写 `open`),
查到 0 行、报「待审=0」—— **就是那行 `open=0` 把它和「真的没活」分开的**。
`FETCH_FAILED` 时脚本会额外打一行警告并 `exit 1`,**那种情况下不许判定「无待审」**。

## Step 2 — 有活就审,排空为止

对每个 `★` 的 PR:`Skill(skill="pr", args="OWNER/REPO#N")`,走它未经修改的 Steps 0-8。

审完一个就**重新跑一次 Step 1**(不是复用上一份名单):审的过程中对方会推新 commit、
开新 PR、把 REQUEST_CHANGES 改完再来 —— 那些恰恰是最该马上接着看的。
**扫描扫空才算排空。**

⛔ `(draft,跳过)` 的**不审**,但要在汇报里点名。**不许给它写 `last_reviewed_at`** ——
那等于声称审过。它会每轮出现直到脱离 draft,这是判据变严的正确代价。

⛔ **没活的那一轮不要加载 `pr` skill。** 一条 `lazy_scan.py` + 一行汇报就结束,
这是这个模式省 token 的主要来源。

## Step 3 — 排下一枚兜底

```
CronCreate(cron="<下一个整点后的某分钟>", recurring=false, prompt=<下面那段>)
```

**固定一小时,没有梯子、没有状态文件。** 分钟数不要取 :00 / :30。
要改频率就改这一个数。

## Step 4 — 推送来的活(这才是主路径)

仓库会话修完会主动 `SendMessage` 回来。收到就:

1. **从 API 现读 head**,绝不采信消息里给的 sha ——
   2026-09-02 实测:`superpaymaster-b6` **两次在发完消息之后又推了新 commit**。
   不是不配合,是「发消息」和「push」天然不同步。
2. head 变了 → 走 `pr` skill 的增量复审(Step 0b / 0c 照常)。
3. head 没变 → 回一条问清楚,不要开始重审。
4. **不要等下一枚 cron。** 推送来的活立刻做完,做完之后原来那枚 cron 照旧有效。

## 停止

`lazy-loop stop` → `CronList` 找 prompt 含 `[[lazy-loop]]` 的那枚 → `CronDelete`。

## 一次性 cron 的 prompt 模板(原样用)

```
[[lazy-loop]] PR-Daemon 懒巡检 —— 扫一次,有活就审到排空,然后再排一枚一小时后的

cd /Users/jason/Dev/tools/PR-Daemon
export PR_DAEMON_STATE_DIR=/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon
python3 scripts/lazy_scan.py

- 有 ★ → 逐个 Skill(skill="pr", args="OWNER/REPO#N"),审完重新扫,排空为止
- (draft,跳过) 的不审,但在汇报里点名;不许给它写 last_reviewed_at
- ⛔ 末行 open=0 或出现 FETCH_FAILED → 那是 gh 出错,不是「没活」,如实报出来,不要判定无待审
- ⛔ 没活的那一轮不要加载 pr skill:一条命令 + 一行汇报就结束

排空之后排下一枚一小时后的一次性 cron(recurring=false),prompt 就是这一整段(原样)。
⛔ 审查逻辑一律走 pr skill,这条链只管节奏。
```

## 已知边界,如实说

- **cron 是 session-only**:这个会话结束,待发的那枚就没了,收消息的能力也一起没。
- **推送依赖对方主动**:我在每封交接消息里都要求回信,四个会话当天都照做了,
  但这是约定不是机制 —— 兜底轮询存在的理由正是它可能不发生。
- **一小时是个选择,不是结论**:它假设「新 PR 晚一小时看到没关系」。
  如果哪天需要更快,改 Step 3 那一个数;不要改回梯子。
