## REQUEST_CHANGES — 增量复审 `a1b1fb8` → `56b168e`

先说好消息：上一轮的 **Blocking 1 真修好了**——`readWorksetBackup` 改成纯读内存，`commitRestore` 只在 present/lost/restored 判定**之后**才落盘，`lost` 分支现在一个字节都不写，重复调用保持幂等（e2e 场景 6 验证）。并发锁（`withProjectLock`）也补上了，`/api/chat` 与 `/api/commit` 的 state 读-改-写临界区都串行化了。CC-77 的账本半边（把 `writeProjectState` 挪到 `snapshotWorkset` 之前）确实解决了「备份抖一下就把已花的钱丢了」这个原始病根，hack5 结算不再依赖这次修的这几个 bug。

但 **Blocking 2 没有修**，而且我又多挖出两个 High——都验证过（真跑 `grep`/`git check-ignore`，Codex R3 独立复现确认，不是读出来的猜测）。

---

### 🔴 Blocking（沿用上一轮，仍未修）—— `worksetLostAt` 是个只写不读的死字段，manual commit 完全没有 reset 门禁

`chat/route.ts:149-150` 在 reset 轮把 `worksetLostAt`/`worksetLostAtRound` 写进 state，但**全仓库 grep 只有这一处写、types.ts 一处声明，零读者**。而 `chat/route.ts:176` 的门禁仍是 `if (ws.kind !== "reset" && AUTO_COMMIT)`——只在**当次请求**成立；`commit/route.ts` 的 `doCommit` 更彻底，**只挡 `ws.kind==="lost"`，reset 相关一律不挡**。

具体场景：项目 `rounds=12`，冷启动无备份 → chat 第一次调用 409 `lost` → 带 `acceptWorksetLoss:true` 重发 → `reset`，铺 7 个空模板，**这一次**正确跳过了 commit，`worksetLostAt` 写进去但没人读 → 用户点「手动提交」→ `POST /api/commit` → `ensureProjectWorkset` 这时看到 `conversation.jsonl` 已存在 → 返回 `present`（不是 `lost`）→ 直接把 7 个近乎空的模板 commit+push，覆盖仓库里已交付的 12 轮 spec。这正是这次改动声称要挡住的结果，只是晚了一步。

**修法**：`doCommit` 与 `AUTO_COMMIT` 分支都改成读持久化的 `state.worksetLostAt`/`worksetLostAtRound`，而不是当次请求的 `ws.kind`；只有用户显式确认（或已有一轮非-reset 的真实提交）之后才清掉该字段。

（旁支线索：本地 `git check-ignore -v` 证实 `fde-copilot/.gitignore:14 /clients/*` 连带忽略了嵌套的 `clients/<c>/projects/<p>/SPEC.md`，`git add`（未带 `-f`）在无 `repo` 参数的旧路径下大概率直接失败/空提交——即 `/api/chat` 的 `AUTO_COMMIT`（未传 `repo`）今天很可能本来就是空跑。但 `POST /api/commit` 手动路径若带 `repo`（走 `pushSpecToRepo`，独立 clone）不受这条 gitignore 影响，上面这条 Blocking 在该路径下依然成立、依然会真推空模板覆盖交付仓库。)

---

### 🔴 High（新发现）—— 项目详情 GET 不进锁却会删文件，跟持锁的 chat 竞态

`ensureProjectWorkset` 的脏标记分支会**无条件** `fs.rm(convPath, {force:true})`（`clients.ts:551`），但这个函数同时被**不进锁**的项目详情 GET 调用（`route.ts:20-24` 注释说"最坏两边各恢复一次，幂等无害"——这个论证只覆盖 `wx` 恢复写，不覆盖这里的无条件删除）。

竞态：脏标记已存在（上一次回滚失败留下的）→ chat（持锁）清掉标记、恢复、追加了新客户消息 → 并发的 GET（无锁）在标记被清之前读到 `exists(dirtyMark)===true`，执行自己的 `fs.rm(convPath)`——删掉 chat 刚写好的内容——然后从（更旧的）备份重新恢复；chat 轮末的 `snapshotWorkset(full=true)` 随后把这份倒退的历史写回 D1，永久丢掉刚追加的那条消息。哪怕没有并发，单纯一次页面刷新命中脏项目也会从只读端点悄悄删文件。

**修法**：这个删除分支绝不能挂在无锁路径上——要么把脏清理单独拆出来强制走锁，要么把 `ensureProjectWorkset` 拆成只读的 `inspectWorkset()`（给 GET 用）和会破坏性写盘的版本（只给持锁的 chat/commit 用）。

---

### 🔴 High（新发现）—— 备份写入不校验、恢复时却一行坏就全军覆没

`capEntryForBackup`（`clients.ts:219-220`）只处理 >1MB 的行，≤1MB 的行**原样不解析地**写进 D1 备份；而 `readWorksetBackup`（`clients.ts:338-345`）恢复时只要**一行解析失败就判整份备份不可用**（文档+全部会话）。`readConversation`（本地正常读，`clients.ts:728-733`）对同样的坏行是**容忍跳过**的。

也就是说：容器崩溃中途写坏一行（这个 PR 好几处注释都点名过这个场景），本地读感知不到，但下一次全量 `snapshotWorkset` 会把这行坏数据原样镜像进备份——冷启动那一刻才发现整份备份全废，被迫 `lost`，即便只坏了一行。

**修法**：`capEntryForBackup` 对所有行都做校验（不只 >1MB 的），解析失败一律替换成占位符；恢复端也改成逐行容忍（记日志+跳过），和 `readConversation` 的语义对齐。

---

### 🟡 Medium

| 位置 | 问题 |
|---|---|
| `chat/route.ts:49` + `commit/route.ts:29` | `withProjectLock` 现在整段封住 ~800s 的 agent 轮次，且无排队上限/超时/公平性。手动提交点一下、或同项目突发几条并发 chat，都可能排队排到平台请求超时，而队列位置还占着 |
| `clients.ts:274-278`（R4 全量补扫新增） | 「先写块、后写 count」——崩溃卡在块和 count 之间，`readWorksetBackup` 会静默信任偏低的旧 count、判定 `restored` 成功，实际丢了最后一块（最多 ~192KB）历史，且不会被标脏 |

### ✅ Rejected（R1 DeepSeek 提的，站不住）

| finding | 驳回理由 |
|---|---|
| >1MB 占位符丢数据 | 代码注释里已明确写清楚是有意为之、占位文字本身就说明了丢失 |
| count=0 与"无备份"歧义 | `convOk = rounds===0 \|\| convChunks>0`，count=0 只在 rounds===0（没东西可丢）时才放行，unreachable |
| 本地脏标记清不掉会卡死 | 有意为之（`MIRROR_WORKSET` 门控），409 报文已明确告诉本地开发者删哪两个文件 |
| truncateConversation 并发写风险 | 所有写路径都在锁内，moot |
| withProjectLock 进程本地/非分布式（R1b 10 条同类） | 代码注释已明确写清是当前单实例部署形态下的接受限制，与 PR 描述的部署形态一致，不是新缺陷 |

---

<sub>🤖 4-round: R1a/R1b DeepSeek v4-flash 并行（4+10 条，全部低价值——3 条复述已知 tradeoff、1 条 moot、10 条重复同一个已文档化的单实例锁限制；两轮都没抓住仍未修的 Blocking 2 或任何新缺陷）→ R2 Opus 独立评审（确认 Blocking 1 真修好、重新证明 Blocking 2 仍破、新增 2 条 High）→ R3 Codex PK（真 Codex gpt-5.5，在 PR head checkout 上独立 grep 实证，3/3 全部 CONFIRM）→ R4 Opus 裁决 + 全量补扫（新增 count/chunk 写序竞态 + gitignore 使旧提交路径可能已经空跑的旁证）。机械证据：`grep -rn worksetLostAt` 全仓库仅 1 写 0 读；`git check-ignore -v` 证实 `/clients/*` 忽略嵌套 SPEC.md。</sub>
