## Verdict: REQUEST_CHANGES (incremental re-review, head `26d7bb4`, round 2)

**上一轮 3 条阻断项全部真修了，而且修得很对**：

1. **测试终于测的是守卫，不是判定函数** —— 我重跑了同一个变异测试：把 `chat.ts:269` 的 `.filter((c) => c && !chipLooksUnsafe(c))` 换成 `.filter((c) => !!c)`，套件现在**报错** `chips filter: 2 条断言失败`。上一轮同样的变异是全绿的。新测试真的驱动了 `chatTurn`（stub 掉 fetch），这是唯一能在有人删掉 `:269` 时变红的写法。
2. **CI 接上了** —— `ci.yml:103` `run: pnpm test:chips`、`:109` `run: pnpm test:api`。我把 `package.json` 的 `check` 里 14 条脚本逐条对了 `ci.yml` 的 `run:`，**全部在列**，所以 `ci.yml:41-43` 那句「CI 跑的命令和本地完全一样」现在重新成立了。顺带把 `apps/api/src/` 下 8 个从没在 CI 跑过的测试也接了进来，8/8 全绿。
3. **联系方式整类缺口封上了** —— 我上一轮公布的 9 条绕过**现在全部拦住**：`wx: abc123` / `vx: abc` / `加我 v 信` / `QQ 12345678` / `t.me/foo` / `wa.me/123` / `bit.ly/abc` / `13800138000` / `138 0013 8000`。上轮那条 Low（中英不对称）在交期/单价方向也closed：`15 天出货` / `0.85/pc` / `80 cents each` / `每个 8 毛` 全拦。

而且「把 D-3 的**带值断言**和 D-7 的**站外联系方式**拆成两类」这个设计动作，正面回答了我上轮提的那个问题（chips 是模型的断言还是客户的话术），也真的降低了「一整轮 chips 全被过滤 → `chips: []`」的概率。误伤我也查了：20 条真实合法 chip（`Matte lamination` / `Spot UV logo` / `Pantone 186C` / `350gsm board` / `A5 size` / `FSC certified board`…）**零误伤**。

**但放宽正则的代价出现了两处，其中一处是回归。**

### 🔴 Blocking

1. **[Med] `apps/api/src/chat.ts:163` — `企?微` 让「企」变成可选，于是任何含**裸「微」**的 chip 都被吃掉。**
   实测，6/6 全部误伤：
   ```
   误伤  "微调尺寸"    误伤  "稍微大一点"   误伤  "微压纹"
   误伤  "轻微磨砂"    误伤  "微光泽膜"     误伤  "细微烫金"
   ```
   这是面向中文市场的产品（系统提示要求用客户的语言回复，放行集里已经有 `磁扣盒`/`烫金 logo`/`天地盒`），而 **`微调尺寸` 恰恰是这个 agent 最会给的方向之一**。客户每被吃掉一条，就少一个可点入口。
   **修法**：`/微信|企业微信|whats\s*app/i` —— `加微` 已经由 `:165` 覆盖，不需要靠裸 `微` 兜。

2. **[Med] `apps/api/src/chat.ts:141,147` — 回归：英文的价格/MOQ 断言被删掉了，中英不对称没有 closed，而是**翻转**了。**
   旧版 `a37accc:113` 是 `/单价|\bunit\s*price\b/i`；新版换成了只认中文的 `(?:单价|售价|报价)\s?[:：]?\s?\d`。实测：
   ```
   拦截 ✅  "单价 2.8"   "售价 2.8"   "起订 500"   "交期 15 天"
   放行 ❌  "Unit price 2.8"   "Price 2.8"   "Quote 2.8"   "Min order 500"
   ```
   也就是说：`Unit price 2.8` 这种 chip 现在会直接摆到客户面前 —— 正是这个 PR 存在要挡的 D-3 违规，而且 `unit price` 这一条**旧版拦得住、新版拦不住**。
   **修法**：补 `/\b(?:unit\s*price|price|quote|unit\s*cost)\b[^\d]{0,4}\d/i` 和 `/\bmin(?:imum)?\.?\s+order\b[^\d]{0,8}\d/i`（`Minimum order 500` 目前能拦住，只是因为它匹配了完整的 `minimum order`；`Min order 500` 漏）。

### 非阻塞

- **[Low] `chat.ts:139`** — `\b\d[\d,.]*\s?(?:each|…)\b` 会吃掉 `Order 500 each` / `about 3.5 each`。裸整数 + `each` 是数量档位不是单价。建议要求小数或货币上下文。
- **[Low] 8 个变异存活。** 逐条注释掉 26 个正则子句再跑测试：`each` / `每个 N` / `单价 N` / 反序的 `N MOQ` / `minimum order N` / `lead time N` / `交期 N` / `企?微` 这 8 条**删掉测试都不会红** —— 没有任何断言走到它们。新测试正确地删掉了旧的 `'Unit price'`/`'单价更低'`/`'Lead time'` 用例（因为改成了只拦带值的），但没有补上它们的**带值版本**。
  加 `单价 2.8`、`交期 15 天`、`Lead time 15`、`Minimum order 500` 到拦截集，`Order 500 each` 到放行集，能一次杀掉 8 条里的 6 条。
- **[Low] `chat.ts:182`** — 新加的 `redact` 注入参数**零消费者**：`:269` 用默认值，也没有测试传 stub。我验证过它不会削弱结果（传 noop stub，四张表先跑，`redact` 是纯增量），所以今天没有分叉风险；但这是一段没有测试的导出 API，它唯一的保证（「单向增强」）只写在注释里。要么等有第二个调用点再加，要么补一条 `chipLooksUnsafe(x, s => s)` 仍然拦住的断言。
- **[Low] `package.json:12`** — `test:api` 用 `&&` 串了 8 个文件，`auth.test.ts` 一挂就短路，另外 7 套的结果在那一个 CI 步骤里全看不到。

### 一条方法建议

两轮下来，这张黑名单已经是 **26 条手工维护的正则**，其中 8 条没有测试。它和 `redactContact` 已经漂移过一次，现在英文/中文两侧又漂移了一次。

建议在 FU-4（把它抽进 `packages/`）时顺手改成**表驱动的中英成对规格** —— 一条英文规则没有中文孪生（或反之）就直接测试失败。否则这类「补了一半」的 finding 会一轮一轮地来。

同理，`ci.yml:41-43` 那句话今天成立，是因为有人手工枚举了 14 个步骤。加一条 3 行的守卫测试（断言 `package.json` 里每个 `test:*` 都出现在 `ci.yml` 里）就能让这句话自我维持，否则这条 finding 的第 3 轮已经排好队了。

### Assumptions

- 在独立 worktree（head `26d7bb4`）里跑测试、变异实验与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- 增量范围 `a37accc..26d7bb4`（1 个 commit）。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— R2 独立判定本轮为 2-round
  （它已直接执行完对抗语料，再跑一轮是重复取证）。所以本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。
  上面两条阻断项都有我自己实跑的证据（6/6 误伤、新旧两版 `unit price` 对比）。

---
*Reviewed by clestons (`$pr` v4, **2-round + 机械验证**, incremental `a37accc`→`26d7bb4`): DeepSeek
R1a+R1b（`deepseek-v4-flash`）→ Sonnet 机械验证（重跑守卫变异测试确认现在会红、9 条绕过语料全部转为拦截、
20 条合法 chip 零误伤、逐条对齐 `check` 与 `ci.yml` 的 14 个步骤）→ Opus R2（独立评审，挖出裸「微」误伤
与英文价格断言回归，并用逐子句变异找出 8 条无测试覆盖的规则）→ **Codex R3 挂起未跑；R4 按 R2 的
2-round 判定未跑**。*
