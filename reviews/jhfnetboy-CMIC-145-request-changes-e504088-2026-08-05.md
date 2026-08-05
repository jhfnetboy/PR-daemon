## Verdict: REQUEST_CHANGES (head `e504088`)

「给『像优秀销售』造一把能跑的尺子」这个方向完全对，而且实现上有几点比今晚另外两个 PR 好得多：

- **离线可跑、确定性、不联网不要 key** —— 我实跑确认，所以放进根 `check` 链是安全的
- **两条反向保护用例是真的**：`quantity-is-not-price`（「500 units」不许触发 A4）和 `recovers-after-one-silent-round`（只有一轮没建议不算 A5），这种「不许误伤」的用例通常没人写
- **六条规则的 ID 都被 golden 钉住了** —— 我逐条删掉每条规则的 `v.push`，六条**全部变红**

**但这是一把量别人的尺子，所以标准得更高。三条 High 让它现在量不准。**

### 🔴 Blocking

1. **[High] `run.ts:88-94,116,148-150` — live 模式下，基础设施故障会静默变成 PASS。**
   `oneTurn` 在 fetch 抛错和非 2xx 时都返回 `null`，`runLive` 里 `if (!t) continue`，于是零个 turn 被评测、`tally.A4.fail === 0`、进程 **exit 0**。
   实测：`--api http://127.0.0.1:9`（不可达）→ 打印 `A4 0% (0/0) （🔴 必须 100%）`，**exit=0，通过**。
   URL 写错、Worker 挂了、401、部署坏了 —— 和「模型完美」无法区分。而这个工具自述的用途是「改 prompt 前后各跑一次做对照」，那么一个从没连上过的 Worker 会给出两份一模一样的干净报告。
   **修法**：统计 `null` 的轮次，`if (unreachable > 0) return unreachable`，或者 `pass + fail === 0` 直接判失败。

2. **[High] `checks.ts:87-100` — A4（唯一要求 100% 的硬闸）两个方向都错了。**
   实测，它**拦住了提示词明确要求模型说的推辞话术**（`apps/api/src/chat.ts:64` 写着「NEVER quote prices, MOQ, lead time… If asked, warmly say the real quote appears on the next step」）：
   ```
   拦 lead-time   「交期这块我给不了准数，得等报价引擎出。」
   拦 moq         「起订量我这边不方便说，下一步会有真实报价。」
   拦 price       「单价不由我给，下一步系统会出真实报价。」
   拦 lead-time   "I can't give you a lead time — the real quote comes on the next step."
   ```
   而**真正的报价它全部放行**：
   ```
   放行  "USD 3.50 per box"    放行  "RMB 12 each"      放行  "Around 1.20 each"
   放行  「大概 3 块 5 一个」    放行  「开模费大概 800」
   ```
   根因：`/交期/`、`/起订量?/`、`/单价/` 匹配的是**话题词**不是**被报出来的值**；而货币模式要求数字在**前**（`\b\d[\d,.]*\s?(?:usd|rmb…)`），所以「词在前」这种最常见的写法全部逃逸，`yuan`/`块`/`毛`/`cents`/`/pc`/开模费更是完全没有。
   在 live 模式下这是硬失败，所以第一次真跑就会因为**正确行为**而 A4 不及格；而唯一能「提分」的办法，是训练模型别再提这些话题词 —— 也就是不再优雅推辞。
   **修法**：话题词要求邻近有数字/货币才算；或者对含推辞标记的句子豁免。同时把 `USD 3.50`、`1.20 each`、`3块5`、开模费补进模式和 golden。

3. **[High] `run.ts:46-47` — `keys()` 用 `Set` 存 `check@turn`，重复期望会被折叠，导致 A3 两个谓词互相掩护。**
   `bad-chips` 故意同时期望 `A3@0` 两次（数量超上限 + chip 过长），但 Set 里只留一条，**任一半满足即通过**。
   我做了谓词级变异，全部**仍然全绿**：
   ```
   chipTooLong → 永远 false      仍全绿 ⚠️
   chips 上限 4 → 8              仍全绿 ⚠️
   中文 chip 长度上限 12 → 999    仍全绿 ⚠️
   ```
   **这条也修正了我自己上面那句「六条规则都被钉住」** —— 钉住的是规则 **ID**，不是规则内部的**谓词**。同样地，`ADVICE` 从 12 条缩到 2 条、`PRICE` 从 5 条缩到 1 条、`MOQ` 从 4 条缩到 1 条，测试都不会红。对一个自述「尺子本身错了，后面量出来的所有数字都是废的」的模块，golden 需要**每个谓词一条用例**，而不是每个规则 ID 一条。
   **修法**：改成多重集比较（`check@turn#n`），或者把 `bad-chips` 拆成两条（5 个短 chip / 2 个 chip 其中一个超长）。

### 非阻塞

- **[Med] `package.json:16` vs `.github/workflows/ci.yml` — `eval:chat` 进了 `check` 却没进 ci.yml，这是 #147 刚修好的同一个缺口。** `ci.yml` 逐条列举了 `check` 链里其余 12 步，唯独 `eval:chat` 没有对应步骤。更尖锐的是 `ci.yml:41-43` 那句「CI 跑的命令和本地【完全一样】…如果 CI 有一套、本地有另一套，绿了红了没人信它」——这个 PR 在同一个文件上把它又变成了假的。这也印证我在 #147 里提的建议：加一条守卫测试断言 `package.json` 里每个脚本都出现在 `ci.yml`，否则这条 finding 会一轮一轮地来。
- **[Med] `checks.ts:45-54` — A1 是 12 条短语白名单，量的是措辞不是「有没有给建议」。** 实测误红（A1 触发）于这些明确的推荐：`The matte black rigid box … is the strongest fit for a watch brand like yours.` /「磁扣盒最适合你这个品类，开箱体验最好。」/「手表类我一般都做天地盒，最稳。」；同时误绿于纯索取：「我建议你先告诉我产品尺寸、数量和预算。」甚至裸的「我建议。」
  这是典型的 Goodhart 风险：提高 A1 分数最便宜的办法是把魔法短语塞进系统提示词，数字上去了行为反而退化 —— 正是文件头声称这把尺子要防的那件事。
- **[Med] `checks.ts:58` — A2 数的是 `?` 字符不是问句。** 误绿：「我建议先定盒型。告诉我你的产品尺寸，还有数量，还有预算，还有交付城市。」→ 0 个问句，整轮干净；误红：回复里带一个含 query string 的 URL → 2。
- **[Med] `checks.ts:66,73-81` — A6 的「打招呼」豁免只认单词招呼，恰好漏掉它自己注释里说要抓的形状**（`:63-65` 写的是「招呼 + 立刻提问」）。`Hi! What are we packaging today?` 抓得到，但 `Hi there! …` / `Hey Jason! …` / `Welcome to CMIC! …` /「你好呀！你想做什么盒型？」/ `Hi!! …` **全部漏掉** —— `GREETING` 用 `^…$` 锚定整句，任何修饰词都能绕开。
- **[Med] `checks.ts:112-118` — 一个 CJK 字符就能让英文词数上限失效。** `if (cjk > 0) return cjk > 12;` 提前返回，于是 `Matte black with gold foil stamping and spot UV 盒`（9 个英文词 + 1 个汉字）判为不超长。
- **[Med] 尺子与线上守卫已经漂移，而且是双向的。** (a) 线上只中和**价格**，MOQ 和交期原样返回客户 —— A4 三类里有两类**线上零防线**，这个 eval 是唯一一层，而它不在 CI 里；(b) 反过来，线上是**就地改写** `reply` 之后才返回，所以 live 模式读到的是过滤后的文本：一个让模型吐 `$2.80` 的提示词回归会被改写成「(I'll show the real quote on the next step)」，A4 报 100%。**A4 的价格这一臂在 live 模式下恰恰看不见它要检测的那个回归。**(c) `chat.ts:162` 已经 `.slice(0, 4)`，所以 A3 的 `chips.length > 4` 分支在真数据上永不触发。
- **[Low] `golden.json:2` 把参数写成 `--ai`，而代码读的是 `--api`。** 实测 `--ai <url>`、`--api=<url>`、`--api` 放在 argv 末尾，三种都**静默跳过 live 并 exit 0**。叠加第 1 条，等于有四条路径让人以为自己量了真模型、其实什么都没量。建议拒绝未知的 `--*` 参数。
- **[Low] `checks.ts:155-157` — A5 被 A1 严格支配，没有独立信号。** 它只在 i-1 和 i 两轮都 `!advice` 时触发，而那时 A1 已经报了两次，它永远不可能是唯一的红；`run.ts:120,130` 在 live 模式里还直接跳过 A5。「六条」实际是五个检测器 + 一个严重度标记，值得说明，免得有人把 A5 的通过率当证据。
- **[Low] `run.ts:97-104`** — 注释说「用 golden 里每段对话的客户侧开场真跑一遍」，但 `LIVE_OPENERS` 是与 `golden.json` 无关的硬编码字面量。golden 加再多用例，live 探针也永远覆盖不到。

### 驳回的 findings

- **R1a「`t.reply ?? ''` 是死代码」** —— 不是。`golden.json` 在 `run.ts:38` 是 `JSON.parse` + `as` 断言，`Turn` 在运行时没有校验；缺 `reply` 的 fixture 会在 `hasAdvice` 里抛。这是 JSON 边界上的防御，只在类型层面是 no-op。
- **R1a「`LIVE_OPENERS` 类型不一致」** —— 不成立。推断出来就是 `string[][]`，`opener.map()`（`:114`）和 `opener.join()`（`:122,125`）在它上面都合法。

### Assumptions

- 在独立 worktree（head `e504088`）里跑 eval、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— 三条 High 都有我自己实跑的
  双向证据（不可达 URL exit 0、A4 四拦五放、三个谓词变异存活），再跑一轮是重复取证。
  所以本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons (`$pr` v4, **2-round + 机械验证**, head `e504088`): DeepSeek R1a+R1b
（`deepseek-v4-flash`;2 条 findings 均不成立）→ Sonnet 机械验证（离线实跑 eval、六条规则 ID 逐条变异
全部变红、谓词级变异三条存活、A4 推辞话术与真实报价双向探针、不可达 URL 的 live 模式退出码、
grep 证实 ci.yml 未接 eval:chat）→ Opus R2（独立评审，挖出 live 静默通过、Set 折叠导致 A3 双谓词
互相掩护、A4 方向性错误、A1 措辞白名单的 Goodhart 风险、尺子与线上守卫双向漂移）→
**Codex R3 挂起未跑；R4 未跑（证据已双向闭合）**。*
