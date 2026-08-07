## ❌ REQUEST_CHANGES —— `owner`/`kind` 拆分是对的，但新的 `*/5` 扫描会**永久堵死**成本账本那条路

诊断和分解我都认：一个可空列同时承载「谁拥有」和「要不要在画廊里露面」两件独立的事，本来就该拆。拆完之后 `COALESCE(kind,'') <> 'finishes'` 对老行的处理也是对的。

### 我核过的（全部成立）

- **迁移这次是干净的**：`kind TEXT` 在 `render_jobs` 的 `CREATE TABLE` 里（`schema.sql:237`，块从 `:212` 起），ALTER 只在 `migrations/0009` 里，`grep -nE '^\s*ALTER' schema.sql` = **0**，而且 `0009` 不在 `deploy-review.sh` 的 `SKIP_MIGRATIONS` 里 —— review 部署会自动跑到它。今晚这条链路栽过两次，这次是对的。
- `finOwner = me.id && me.id !== 'public-render' ? me.id : null`（`:1036`）和既有 `/render` 路径的 owner 判据（`:942`）**逐字相同**，`me` 来自鉴权层不是请求体。匿名照旧 NULL。
- **归属变更的爆炸半径我逐个查过**：`/my-renders` 过滤了；`getConversationAsset` 的两道 owner 闸都还在（这正是这个 PR 要修好的那条回显路）；配额算的是 `render_quota_windows` 不是 `COUNT(render_jobs)`；`/render-result` 的归属校验是 `call_id + result_token`，不受影响；`COALESCE(owner_user_id, user_id)` 的幂等命名空间对登录用户前后一致，`idx_render_jobs_idem` 不会新增碰撞。**没有任何一条查询因此获得跨用户的可达性。**
- `cleanupRenderHistory` 只看 `delivered_at`、对 `kind` 无感 —— finishes 行以前**永远不会被删**（从不 delivered），现在会跟着 30 天保留期正常老化。这是改善不是回归。
- 两条 cron 都注册了（`wrangler.jsonc:44` 生产、`:78` review），`c.cron === '*/5 * * * *'` 的字面比较对得上，`10 3 * * *` 正确落到重活分支。
- **测试自己钉了反空真的前提断言**（`:93` 「下面两条不能【空真】」→ `:95` `ok('(前提)缩略图那一行确实落库了', cnt === 1)`）。三条变异确实各自会红。这一点写得好。

---

### 🔴 1 [Med-High] 扫描不写成本账本，而它顺手设的 `delivered_at` 会让浏览器**再也走不到**写账本那一步

`sweepUndelivered` 的注释里写着：

> · **不扣配额、不记成本** —— 钱在提交那一刻就花掉了,这里只是把已经买到的东西取回来。

**这个理由是错的。** 成本账本不是在提交时写的，是在 `done` 时从 `result.usage` 写的 —— `index.ts:1078-1086`：

```ts
if (result && result.status === 'done' && Array.isArray(result.usage)) {
  for (const item of result.usage as ...) {
    const event_id = `${callId}:${item.slot ?? item.kind}`;
    await writeCostEvent(env, { ...item, event_id, call_id: callId, user_id: job.user_id, ... })
```

而 `/render-result` 的执行顺序是：

```
:1060  if (job.delivered_at && env.RENDERS) {
:1061    const cached = await loadRenderFromR2(env, job);
:1062    if (cached) return cached;          ← 在这里就返回了
:1063  }
:1064  const result = await proxyRender(...)
:1073  ...persistRender...
:1078  ...writeCostEvent...                  ← 永远到不了
```

所以这不只是「扫描自己不记账」，而是**扫描先把 `delivered_at` 设上，浏览器之后再来轮询就命中 R2 缓存直接 return，账本那一段被彻底跳过**。

⚠️ 这是这个 PR **引入的回归**，不是原有缺口：改之前，客户把标签页放后台 5 分钟再回来，轮询走的是完整路径、账还是记上的；改之后 `*/5` 的扫描抢在他前面，那笔账就没了。而且**是不确定的** —— 浏览器和扫描抢同一个 job 时，浏览器赢了就有账、扫描赢了就没账。

后果是静默的：`reconcile()` 会把这些 `call_id` 一直列成缺口，而 `replayOutbox` 补不回来 —— 因为压根没有东西入过队。

**修法约 6 行**：扫描的 SELECT 加上 `user_id`，把 `:1078-1086` 那个循环复制过来。安全的：`writeCostEvent` 是 `INSERT … ON CONFLICT(event_id) DO NOTHING`（`cost.ts:215`），`event_id` 又是 `${callId}:${slot}` 确定性生成的，和抢跑的浏览器撞上也不会重复计费。

（更耐久的做法是把 `/render-result` 里 `done` 之后那一段抽成一个 `deliver(env, job, result)`，两个调用方共用 —— 现在这个「复制半个 handler」的形状，下次在 `done` 后面加任何东西都会再漂一次。）

### 🔴 2 [Low-Med] `ORDER BY created_at DESC` 对一个补扫来说是反的

```sql
WHERE delivered_at IS NULL AND owner_user_id IS NOT NULL AND created_at > ?1
ORDER BY created_at DESC LIMIT 20
```

补扫应该 `ASC`。`DESC` 有两重坏处：

1. **最新的那批「未交付」恰恰是还在跑的**（出图要 60–120 秒），所以 20 个名额优先花在**保证还不是 `done`** 的任务上 —— 最不紧急、也最不可能成功的那些。
2. 而真正快要掉出 `created_at > now-2h` 窗口、掉出去就永久丢失的老任务，排在最后，backlog 一超过 20 就永远轮不到。

我原本猜 `DESC` 是为了「客户正在看」，R2 把这条也否了：**客户要是在看，他的浏览器就在轮询，这个扫描根本没必要存在** —— 扫描的全部前提就是没人在看。

**修法**：`ORDER BY created_at ASC`。

### 两条 Low

- **打不出图的任务会在窗口里被重试 24 次。** `persistRender` 在 `done` 但没有图片键时返回 0 且不写 `delivered_at`（`render-store.ts:47`），Modal 的 `error`/`failed` 也永远不满足 `status === 'done'`。两种情况下这一行都留在扫描集合里，每 5 分钟一次、整整 2 小时。有界，但它在啃第 2 条那个 20 名额的预算。
- **整个 `scheduled()` 路径零测试覆盖。** 新测试里 `env.RENDERS` 是 `undefined`，`sweepUndelivered` 第一行就 `return 0`，`persistRender` 根本没被跑到。也就是说 `'*/5 * * * *'` 这个字面量打错一个字符 —— 后果是那条重活的日常清理**每天跑 288 次**，正是注释里警告的那件事 —— 没有任何东西会红。

顺带一句关于测试的定位：它钉的是 INSERT 的列（有 owner、kind=finishes、不进画廊），那是「落库」这个结论的**代理指标**，不是结论本身 —— 它从没跑过 `/render-result` 或 `persistRender`。所以「有 owner ⇒ 会落库」这个因果目前只活在注释里；哪天有人改了 `/render-result` 的落库条件，这套测试会全绿，而灰色占位图会原样回来。

---

<sub>Rounds — R1a/R1b DeepSeek(v4-flash)：4 条，**全部不成立**。「扫描漏了匿名任务，应该把它们也捞上」—— 匿名本来就没有归属、没有历史，捞了等于往 R2 写一批没人能取的图；「0009 不幂等」—— 文件头自己写着，且部署循环把 `duplicate column name` 判为已跑过；「`finOwner` 用了 `me.id` 却没校验 session」×2 —— `me` 来自 `authenticate()`，而且这段逻辑和 `:942` 既有路径逐字相同。R2 Opus：独立发现上面第 1 条（我原本只探到「`persistRender` 的 UPDATE 没有 `AND delivered_at IS NULL`」这个良性方向，R2 指出真正的风险在**反方向**：不是重复记账，是记不上），并把第 2 条从「对老任务不公平」加强到「预算优先花在保证不会成功的任务上」。R3 Codex / R4 未跑：第 1 条由 `:1060-1063` 与 `:1078` 的**执行顺序**直接判定，第 2 条由一条 SQL 直接判定，都不是推理链。按实跑轮数标 **3-round**。</sub>
