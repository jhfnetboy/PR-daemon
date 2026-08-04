## Verdict: APPROVE (incremental re-review, head `1fb4c25`, round 2)

上一轮的 `[High]` 已修，而且**用变异测试证明了修复和它的回归测试都是真的**，不是纸面上的：

- 在独立 worktree 里跑新增的 `brief: 晚回来的第一轮不许把客户刚改对的参数覆盖回去` → **绿**
- 把 `:545` 的 `myTurn === turnSeq` 守卫删掉，退回修复前的写法 → **红**（`07-chips.spec.ts:230` 的 `2,000 units` 断言失败）
- 守卫加回来 → 再次**绿**

这个测试选的断言点也对：`showBoxDirections()` 开场白里那句用户真看得见的 `Four directions that fit N units`，而不是内部状态。上一轮六条findings（含五条 Low）逐条核对都真落地了，`followUpBusy` 挪进 `try`、`unspendChips` 补退路、rehydrate 补白名单、`restoreThread` 显式置 `started`——尤其把那条不可达的守卫**保留并注明「防御性对称」**，比悄悄删掉诚实。

⚠️ **但跑这个测试的过程里发现一件比本 PR 更要紧的事，见下面「环境」一节——这个仓库的 e2e 在本机上可能一直在测别的代码。**

以下全部是 Low，不阻塞合并。

### 建议修复（Low）

1. **`apps/web/src/chat.ts:545` — 守卫站在了 `await` 的错误一侧。**
   ```ts
   if (r.ok && myTurn === turnSeq) { const d = await r.json() as ChatReply; applyPatch(d.brief_patch); ... }
   ```
   判断在 `await r.json()` **之前**求值。而 `followUp` 入口的 `const myTurn = ++turnSeq`（:562）和 `supplementFromText(t)`（:572）都是**同步**执行、发生在它自己 `await fetch` 之前。所以：守卫通过 → `r.json()` 让出 → 客户排队的那次回车派发 → `brief.qty` 被同步改成 2000 → `enterThread` 的续体恢复、`applyPatch({qty:500})` 把它悄悄改回去。
   **和本 PR 修掉的那个 bug 是同一种用户可见损害**，只是窗口从几秒缩到了一个微任务。
   佐证是同一函数里的不对称：`firstChips` 在 `:554` 是在 await **之后**复查的，`applyPatch` 不是。
   ```ts
   const d = await r.json() as ChatReply;
   if (myTurn === turnSeq) { applyPatch(d.brief_patch); firstChips = d.chips; }
   ```
   顺带把过期轮次的响应体也读掉（当前写法留着不读）。

2. **`apps/web/src/chat.ts:571`（配合 :183/:585/:590）— `unspendChips` 缺的是「归属」判断，不是「轮次」判断。**
   `addChips` 在 `items.length === 0` 时于 `:183` 提前返回，**没有重新赋值 `liveChips`**。而 `chips: []` 是正常形态——模型漏给/给坏时后端就是这个结果，`done:true` 的收尾轮也是。于是：某一轮成功且 `chips` 为空 → 它正确地把 `liveChips` 那一组置为 spent，但 `liveChips` 仍指着它 → 下一次 `followUp` 取 `spent = liveChips`（已 spent）→ `spendChips` 因幂等守卫空转 → 一旦网络抖动走到错误分支，`unspendChips(spent)` 三个检查全过，**把一组过期两轮的方向复活成可点**。点下去就等于把两轮前的方向当作客户刚说的话重新发一遍，和 `:137` 那句「一组 chips 只属于它所在的那一轮」自相矛盾。
   ```ts
   spent = liveChips;
   const spentByMe = !!spent && !spent.classList.contains('spent');
   spendChips(spent);
   // …错误/非 ok 分支:
   if (spentByMe) unspendChips(spent);
   ```
   **别改成在 `addChips` 的空数组分支里把 `liveChips` 置 null** —— 那条路和 `enterThread` 离线时的 `addChips(undefined)`（:554）共用，会误杀一组本该活着的方向。

3. **`e2e/tests/07-chips.spec.ts:225-230` — 新测试和 followups 里的 FU-2 互相拆台。**
   它断言的正是 `showBoxDirections()` 的开场白，而同一个 PR 记进 ledger 的 FU-2 计划就是给这个渲染上闸。FU-2 一落地，正确行为变成「开场白根本不渲染」，这个测试会**超时**而不是给出有意义的失败。建议在 FU-2 那条 ledger 里交叉引用本测试，让落地的人去改断言而不是删掉一个红测试。

4. **[Nit] `apps/web/src/chat.ts:698-703`** — rehydrate 先 `slice(MAX_CHIPS)` 再规范化、且不过滤空串，而 `addChips` 是先 `filter(Boolean)` 再 slice。被改过的存档里 4 个空 + 2 个真，会留下 4 个空的、删掉真的。只影响自己的 localStorage，但这正是本 hunk 注释说要消灭的「同一条不变式两条路径不一致」。

### 环境（不属于本 PR，但会让整套 e2e 失效）

`e2e/playwright.config.ts` 用固定端口 5173 + `reuseExistingServer: true`。本机 5173 **从 7 月 31 日起**就被另一个 vite 占着，服务的是 `/Users/jason/Dev/auraai/AuraAI/CMIC/apps/web` ——**另一个 checkout**。

后果是实测出来的：我最初两次变异测试（守卫已删）**都是绿的**，因为浏览器加载的根本不是被测代码。换成独立端口 + `reuseExistingServer: false` 之后，变异才如实变红。

也就是说，只要本机上 5173 被任何东西占着，这个仓库的**全部** e2e 都会静默地测另一份代码并报绿。建议记一条 ledger：`global-setup.ts` 里断言所服务构建的身份（比如注入一个 build id 并核对），或者每次跑用随机端口。

### 驳回的findings

- **R1a「`unspendChips` 需要 `myTurn === turnSeq` 守卫」** —— 它已经有等价且更强的保护：`row !== liveChips` 是按身份比的，中途渲染了新一组就自动让旧的保持 spent，与轮号无关。真正的缺口是「归属」不是「新鲜度」，见上面第 2 条。
- **R1b「rehydrate 未转义地重新渲染 chip 文本」/「dataset 未消毒」** —— `textContent` 不解析 HTML（:702），属性值在序列化时转义，且还原路径上已重新截断（:701）。
- **R1b「applyPatch 应校验 patch 字段类型」** —— 不可信来源（localStorage）由 `sanitizeBrief` 覆盖；`/chat` 是本应用自己的后端，且 `applyPatch` 对 `qty` 已有类型检查。

### Assumptions

- 在独立 worktree（head `1fb4c25`）里跑测试，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异只发生在 worktree 里且已还原。
- 增量范围 `f27b65f..1fb4c25`（1 个 commit）。
- PR body 未关联 issue，跳过 Issue-compliance 小节。

---
*Reviewed by clestons (`$pr` v4, 2-round + 全量核对, incremental `f27b65f`→`1fb4c25`): DeepSeek R1a+R1b（`deepseek-v4-flash`;4 条findings 0 条成立）→ Sonnet 机械验证（独立 worktree 跑 e2e、对 `:545` 守卫做变异测试并双向确认红/绿、查出 5173 端口被外部陈旧 vite 占用导致前两次测试无效）→ Opus R2（独立评审，未看我的笔记就挖出 chips 复活那条 Low）→ **Codex R3 按 post-R2 严重度闸门跳过（R2 无 Medium 及以上）** → Opus R4（终裁 + 全量补扫,发现 `:545` 守卫在 await 错误一侧那条）。*
