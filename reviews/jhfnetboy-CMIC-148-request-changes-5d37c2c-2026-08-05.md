## Verdict: REQUEST_CHANGES（首轮，head `5d37c2c8`）—— **一条，改法不是调正则**

**先说这个 PR 做对的事**：合并前每一个首轮**无条件**烧四次 GPU，客户打句 "Hi" 也烧。这是净改进，而且改得很扎实——`photorealVerdict` 把「模型自报 done」定成**只能否决不能授权**、`enterThread` 也占 busy 闸（FU-2 的根治而不是丢弃）、`submitFromDock` 保留客户打的字、`onChipClick` 那段「作废不能放在这里」的推理是对的，`e2e/08` 七条用例覆盖了拒绝和放行两个方向。`07-chips` 那条竞态用例被换掉时你还写了诚实的说明。

**但闸的最高权限输入，是另一个文件里一句没人审过的 `String.includes`。**

### 🔴 Blocking

**[High] `apps/web/src/chat.ts:60` — `directionConfirmed` 由子串匹配置位，而它是授权付费出图的两个条件之一。**

```js
if (!brief.boxType) for (const k in BOX_HINT) if (low.includes(k)) { brief.boxType = BOX_HINT[k]; directionConfirmed = true; break; }
```
`BOX_HINT` 的键是 `lid / rigid / magnet / book / drawer / slide / mailer / ship / corrug`，`low.includes(k)` 是裸子串。实测 16 条**根本不是在说盒型**的话会置位：

```
命中「lid」  : solid black box / a solid color / holiday gift box / valid until friday / slides for the deck / no lid needed
命中「ship」 : what is the shipping cost? / ship to Germany / before the shipment / our relationship with the factory
命中「book」 : a booklet insert / post it on facebook / notebook style / booking a call / I do NOT want a book box
命中「rigid」: make it rigid? maybe not
```

端到端跑真实的 `canRenderPhotoreal`，`supplementFromText` 会从**同一句话**里把其它槽也填满（`candle` → product **且** size 自动取 `PRODUCTS['Candle']`，`500 pcs` → qty）：

```
"solid black box for a candle, 500 pcs"          directionConfirmed=true  → allow=true (slots-complete)  ← 出图
                                                  directionConfirmed=false → allow=false (slots-incomplete)
"what is the shipping cost for 500 candle boxes?" 一句纯物流提问                → allow=true              ← 出图
"I do NOT want a book box, 500 candles"           客户用大写否定了盒型          → allow=true              ← 出图
```

R2 用逐字提取的接线搭了台，按 `enterThread` 的真实首轮顺序跑 17 条现实首句：**9 条放行，其中 7 条是子串意外授权的**，包括两条客户**明确否认**了盒型的。

为什么这条要拦：`render-gate.ts` 开篇自己声明了成本不对称——**漏判便宜、误判烧 GPU**，并且花了三轮建 `NEGATORS`/`MODIFIERS`/分句作用域，全部建立在「拿不准一律不算指令」上。**这套东西一点没用在打开同一道闸的那个信号上。** 一个裸 `String.includes` 比这个 PR 存在理由所不信任的「模型推断」还要弱，却拿到了**严格更高**的权限：它直接满足 `slots-complete`，而 `modelDone` 那道否决救不了它（模型通常会同意子串的判断）。

**改法不是调正则——我实测过三种，都不行：**

| 候选 | 17 条里放行 | 问题 |
|---|---|---|
| 现状 | 9（7 条是意外） | — |
| `\bKEY` 前缀边界 | 6 | 杀掉 solid/holiday，`booklet`/`ship`/否定句仍在 |
| `\bKEY\b` 全词 | 4 | **打断 `magnetic closure box for perfume`**——真客户 |
| 只认点 chip | 0 | 首轮全灭 |

关键的一次变异：把 `directionConfirmed = true` 从 `supplementFromText` 删掉，放行从 9/17 掉到 **0/17**——**目前每一次首轮放行（包括那 2 条正当的）都走这条子串路径**，所以它不能简单删掉。

**建议的切分**：`brief.boxType = BOX_HINT[k]` **原样保留**（填错一张卡是便宜且可逆的，客户点另一张就是了），`directionConfirmed` 只由两处置位——(1) chip 点击（`:595`，你自己注释里说的「点了盒型 = 明确选了方向」，这个是对的）；(2) 一个**专门的方向匹配器**，走 `render-gate.ts` 已有的 `NEGATORS` + 分句作用域，并在 `render-gate.test.ts` 里给它自己的用例。这样「客户确认了方向」这个判断和「客户下了出图指令」这个判断用同一套严格度。

### 非阻塞

- **[Med] `.github/workflows/ci.yml` — `pnpm test:gate` 不在 CI 里。** 我实测：`check` 串 13 条，ci.yml 逐条列了 **12 条，独独漏掉 `test:gate`**；ci.yml 也不跑 `pnpm check`。而它自己的开篇写着「CI 跑的命令和本地**完全一样**」。ci.yml 自 `d8b03eb`（PR #58）没动过，那时闸还不存在。
  后果用变异量出来了——7 个接线变异（`directionConfirmed` 初值设 true / 删掉 `modelDone` 否决 / `photorealVerdict` 恒 allow / `size` 恒 true / `qty` 恒 true / `confirmedDirection` 恒 true / 删掉子串置位）**全部存活 `pnpm test:gate` + `pnpm check` + 整个 CI**，因为 CI 跑的东西没有一个 import `chat.ts` 或 `render-gate.ts`。其中「`photorealVerdict` 恒 allow」把放行从 9/17 变成 **17/17**，也就是把整道闸拆掉，CI 全绿。`e2e/08` 能杀掉其中 4 个，但它不在 CI 里。
  **合并后这段接线的实际变异得分是 0/7。** 建议这一行（`- run: pnpm test:gate`）在**本 PR** 里加上，而不是留给 FU-6——不然上面那条 High 的修复没有地方落。这也正是 ci.yml 自己开篇的论证：「一个只在人想起来的时候才运行的检查，等于没有检查」。
- **[Med] `e2e/playwright.config.ts:41` — `reuseExistingServer: true` 会让 5174 那条注释的保证失效。** Playwright **只在自己启动**那条命令时才注入 `VITE_API_URL`；复用已有服务器时环境变量不会被应用 → `RENDER_AVAILABLE=false` → 7 条里有 **4 条拒绝用例空转通过**（正是你注释里警告的「量的是后台没配，不是闸生效了」），2 条放行用例失败并打出指向闸的错误信息（「闸关死了」）而不是指向服务器配置。
  这台机器上此刻就是这个状态：5174 由 `~/Dev/auraai/AuraAI/CMIC`（停在 `docs/agent-plan-v2`）的实例占着，它的 `chat.ts` 里 `photorealVerdict`/`directionConfirmed`/`canRenderPhotoreal`/`setDockBusy` **一个都没有**。（那个方向会**响亮地失败**，不是静默绿；静默绿的是环境变量那条路。）建议 5174 这条改 `reuseExistingServer: false`——`--strictPort` 已经在了，端口被占会直接报错。
- **[Low] `chat.ts:559` — `modelDone === false` 太窄。** `null`/`0`/`""`/`"false"` 都会跳过否决并放行。今天有后端 `apps/api/src/chat.ts:163` 的 `obj.done === true` 兜着，所以只是防御性问题——但前端在断言一个它不拥有的跨部署不变式。而且槽位齐备时返回的 `reason` 被改写成 `'slots-incomplete'`，把这个字段本来要支持的日志记错。建议 `modelDone !== true` + 一个 `'model-not-ready'` 的 reason。
- **[Low] `chat.ts:624-625` 的注释「这几句是纯 DOM」不准确。** 两个赋值之间夹着 `priceBoxEst`（报价引擎）、`boxFaces`（几何）、`renderThumb`（three.js）。今天安全，但 `followUp:634-636` 对一个**更小**的窗口给出了相反论证。这里抛异常会让 `dock-input` 卡在 disabled——是整页哑掉，不只是标志位卡住。建议 `try/finally` 包住 617-627 并删掉那句注释，免得它招后来人往窗口里加代码。
- **[Low] `e2e/08:57` 的 `expect('.thumb.loading').toHaveCount(0)` 在 503 stub 下是空断言。** `apiPost` 在 `!r.ok` 时立刻抛（`render.ts:183`），`showBoxDirections` 的 `.catch`（`chat.ts:315-317`）会剥掉 `loading` 并加上 `failed`——**两条分支下计数都是 0**。改成断言 `.thumb.failed` 计数为 0，那个才有判别力。
- **[Low] `qty >= 10` 硬编码在三处**（`supplementFromText:77`、`qty():113`、`photorealVerdict:553`），没有共享常量，而报价引擎自己的门槛是 `smallQtyMax` 500/1000，两边对不上。
- **[Low] `awaitingAnswer: false` 写死**（`:557`，全文件唯一出现），使 `render-gate.ts:299` 的 `awaiting-answer` 分支在生产里**永不可达**。今天这个判断是对的——`photorealVerdict` 只能从 `enterThread` 到达，而 `enterThread` 每页只跑一次（`started` 守卫，`restoreThread:837` 也置 `started`），首轮确实不存在「刚问了客户一个问题」的状态。所以这是一条未测的不可达分支，不是错误决策。

### 驳回

- **R1a「`followUpBusy = true` 在 await 前置位、缺 try/finally，fetch 抛异常会永久锁死 dock」** —— 逐句追过 `chat.ts:591`→`:626` 没有抛出路径：`followUp` 自己有 `finally`；`enterThread` 的 fetch 在独立 `try/catch` 里；`addChips` 有 `if (!Array.isArray(chips)) return`；`rawQuote`(funnel.ts:92) 和 `boxFaces`(box-preview.ts:40) 都 `try/catch → null`；`renderThumb` 是 async 所以同步抛会变成 rejection 被 `addCards` 接住；`applyPatch` 的输入在服务端有边界（`apps/api/src/chat.ts:78-93`）。方向值得警惕，代码不成立——降级成上面那条 Low。
- **R1b「`directionConfirmed` 从用户文本置位」** —— 方向对，就是上面那条 High，已并入。

### 两条关于范围的话（不影响结论）

- **省下的量按实测说更好**：17 条现实首句从 17/17 放行降到 9/17，约 **47%**，而不是「Hi 不再烧 GPU」。而且这是**只管首轮**的——`showBoxDirections` 只有一个调用点，被拒的客户没法靠继续聊天重新触发它；他们回到出图的路是 Vary / Sample，那两个付费调用点**没有闸**。按「明确指令压过一切禁止条件」这是站得住的，但值得写清楚：闸覆盖了 3 个付费调用点里的 1 个。
- **FU-6 的描述可以收紧**：它写「要么把闸的核心判定再补一层不依赖浏览器的单测」，但 `apps/web/test/render-gate.test.ts` 已经是那层了（17 处引用 `canRenderPhotoreal`）。真正缺的是**接线层**的覆盖——而那正好是上面那条 High 所在的层。

### Assumptions

- 在独立 worktree（head `5d37c2c8`）里读代码、跑 `pnpm test:gate`、用逐字提取的接线搭台跑对抗语料与变异，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原，`git status` 干净。
- **没有跑 Playwright**：这台机器上 5173/5174 的服务器来路不明（见上），跑出来的结果不可信；`e2e` 的判别力是**静态**分析的，我明确标出来。
- `compress_diff` 丢了 15 个文件，**全是 `.png` 截图**，评审覆盖无损失。
- 本 PR 对 `preview` **MERGEABLE / CLEAN**，CI 两个 check 都绿。但注意 `docs/agent/followups.md` 是 append-only 账本，**#145/#146/#147/#148 四个分支都在文件尾部各自追加**——我用 `git merge-tree` 实测 #146 与 #147 之间已经有真冲突。解错方向会**静默丢掉 follow-up 条目**，比 `package.json` 那个危险，建议一并写进合并须知。
- **R3(Codex PK) 未跑、R4 未跑** —— 阻断项有我自己实跑的端到端输出（子串命中 16 条 + `canRenderPhotoreal` 真实放行判定），CI 缺 `test:gate` 是我用 `yaml.safe_load` 解析 ci.yml 与 `package.json` 的 `check` 串逐条比对得到的。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `5d37c2c8`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；R1a 的 High 逐句追证不成立、R1b 方向对已并入阻断项）→ Sonnet 机械验证
（BOX_HINT 子串 16 条实测、端到端跑真实 `canRenderPhotoreal` 确认一句话即 allow、`yaml.safe_load`
解析 ci.yml 与 check 串比对发现独漏 `test:gate`、查出 5174 上是另一个 checkout 在跑且不含本 PR 任何符号）→
Opus R2（独立评审，用逐字提取的接线搭台按 `enterThread` 真实顺序跑 17 条首句得出 9 放行/7 条是意外授权、
7 个接线变异全部存活整个 CI、量出三种候选正则修法都不行、并指出 `reuseExistingServer` 真正的静默绿方向
是环境变量而非外来代码）→ **Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 唯一一条 High（`followUpBusy` 缺 try/finally）**指对了函数、指错了结论**——它没看到 `followUp` 有 `finally`、`enterThread` 的 fetch 有独立 `try/catch`、`addChips` 有数组守卫。而且它把同一条 finding 输出了两遍（一条标 High 一条标 Medium，文字完全相同），这是格式缺陷。R1b 那条方向是对的（`directionConfirmed` 从用户文本置位），但它只说「limit to explicit selection」，没意识到 `low.includes` 是**子串**匹配，也没往下追这个标志位授权的是付费出图——差一步就是本轮唯一的阻断项。
- **下次怎么榨出更多信号**：这个 PR 的核心风险是「一个宽松的启发式喂给了一道严格的闸」，而 diff 里看不到 `BOX_HINT` 的定义（它在未改动的行上）。下次对**接线类** PR，把被接线的两端（这里是 `BOX_HINT` 表 + `canRenderPhotoreal` 的判定链）连同 diff 一起喂给 R1，并明确问「diff 里每一个新的布尔标志位，它的取值来源有多可靠、它授权了什么」。flash 已经嗅到了这个标志位，缺的是两端的上下文。
