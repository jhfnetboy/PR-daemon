## Verdict: REQUEST_CHANGES (head `6709e67`)

三级默认值链这个设计是对的，而且我实测确认它声称的三条不变式**真的成立**：

- 四个槽任何输入下都能解析出可用值，没有 undefined
- `resolveAll()` 的 `disclosures` 与逐个 `resolveSlot()` 的 `source` 在 26 组 brief 上**零遗漏、零重复**
- `resolveAll` 与单独调 `resolveSlot` **四个槽全部一致**（注释说这是自己单测抓出来的 bug，确实修住了）

`normalizeProduct` 的 `trim()` 也正确处理了全角空格 U+3000，大小写折叠正常。作者自己的测试全绿。而且这个模块**还没被任何地方 import**（grep 确认零消费者），所以线上目前没有任何东西被影响 —— 下面几条都是合并前该修的，不是线上事故。

**但「诚实明示」这一层没有做完，而且测试看不住它。**

### 🔴 Blocking

1. **[Med] `knowledge.ts:199` — 内部英文表键漏进了给客户看的中文话术。**
   空 brief（最常见的入口）实测输出：
   ```
   {"slot":"product","source":"knowledge","what":"按一只常规「Gift set」假设的"}
   ```
   而这个文件 `:71` 自己写的期望是「我先按一只常规**礼盒**假设的」。盒型有 `BOX_LABEL` 映射，品类没有。
   **修法**：加一张 `PRODUCT_LABEL`（礼盒 / 手表 / 香水 …），明示里用它。

2. **[Med] `knowledge.ts:121,144` — 同一个 brief 连调 6 次，客户看到 4 种不同的盒型。**
   `rng` 默认 `Math.random`，所以「说了但表里没有的品类」每次调用都换一个盒型。实测 6 次：
   ```
   磁扣书型盒 / 磁扣书型盒 / 磁扣书型盒 / 抽屉盒 / 天地盒 / 飞机盒   ← 不同结果数 4
   ```
   一旦接进去，聊天消息、重新渲染、报价页可能各自明示一个不同的盒型。这也和这个文件 `:24-27` 自己反对「把推断放进模型运行时」的理由（「慢、不可复现」）直接冲突。
   **修法**：要么在调用点按 session/brief 播种并把这写进契约，要么按下面第 4 条改成确定性的通用档。

3. **[Med] `knowledge.ts:132,147,154` — 客户给的值零校验，而这正是「保证每个参数都有可用值」的那个模块。**
   实测全部原样通过、且**不产生任何明示**：
   ```
   size {l:0,w:0,h:0}     → stated       size {l:-10,w:5,h:5}  → stated
   boxType "PYRAMID"      → stated（不在 BOX_TYPE_ENUM 里）   qty 1e12 → stated
   ```
   兄弟文件 `apps/api/src/chat.ts:87-88` 明确写着「qty 加上界（PR#130 建议）：防荒谬值流入 packages/quote」并 clamp 到 1e8。这个模块抄了下界（`>=10`）却把上界丢了。
   **修法**：stated 的 `size` 要求三边有限且 > 0、`boxType` 过 `BOX_TYPE_ENUM.includes`、`qty` 要求有限整数且 ≤ 1e8；不合法就落到下一级。

4. **[Med] `knowledge.ts:150,157` — 未知品类的 `size`/`qty` 被标成 `knowledge`，是「伪装成推断的常量」。**
   实测「陶瓷杯」（表里没有）：`size` 和 `qty` 返回的值与「客户什么都没说」**完全相同**（250×180×70、300），却标 `knowledge`；只有 `boxType` 诚实地标了 `random`。
   而 `:141-142` 的注释正好论证了这一点：「那会让所有未知品类都拿到同一个盒型，看起来像「经验」其实是伪装成推断的常量。随机至少诚实」—— 这个论证一字不改地适用于三行之下的 `size` 和 `qty`。
   **但「让 size/qty 也随机」不是对的解法**：随机尺寸会流进几何和报价，比一个合理的通用值更糟，而且尺寸没有可采样的枚举。
   **修法（同时解掉第 2 条）**：给 `SlotSource` 加第四种 `'default'`；`size`/`qty` 的通用分支和 `boxType` 的未知品类分支都返回它（`boxType` 那里改成确定性通用档，非骰子）；然后**让 `what` 随 source 变**——`knowledge` → 「同类客户通常是…」，`default` → 「先随手给了一个，随时改」。
   现在 `source` 算得很仔细、注释里争论了很久，最后**没有改变客户读到的任何一个字** —— `盒型先按抽屉盒` 无论来自经验还是掷骰子都长一样。

5. **[Med] `apps/web/test/resolve-slot.test.ts` — 测试对明示内容没有判别力，变异证明。**
   明示的断言只用正则查**形状**（`/\d+×\d+×\d+mm/`、`/\d/`），从不查**值**。我跑了两个变异，**都全绿**：
   ```
   把明示尺寸倒序:  内腔预设 250×180×70mm  →  70×180×250mm     ✅ 全部通过
   把明示数量翻倍:  数量按 300 个算         →  600 个算          ✅ 全部通过
   ```
   对一个信条是「含糊的明示等于没明示」的模块来说，**一条数字写错的明示能过 CI**。
   另外还有一批变异存活：把 `size`/`qty` 的 fallback source 从 `knowledge` 翻成 `random`（也就是第 4 条那个 finding 本身**两个方向都测不出来**）、把 `normalizeProduct` 的精确匹配换成 `startsWith`/`includes`（于是 `"W"` 会解析成 `Watch`）、删掉 `qty` 的按品类分支（所有品类都拿 300）。
   **修法**：对三组标准 brief（空 / 已知品类 / 未知品类）断言**精确的 `what` 字符串和精确的 `source`**；补一条敌意 rng 用例；补一条 `normalizeProduct('W') === undefined` 来钉死匹配语义。

### 非阻塞

- **[Low] `knowledge.ts:95`** — `pick` 对敌意 `Rng` 会破坏「永不 undefined」的不变式：`rng()` 返回 `-0.5` 或 `NaN` 时 `boxType` 是 `undefined`，明示会渲染成「盒型先按undefined」。`% xs.length` 只挡住了 `r >= 1`（JS 的 `%` 保留符号，`NaN % n` 还是 `NaN`）。`Rng` 是导出的公开类型，所以这是调用方可达的契约洞。
- **[Low] `knowledge.ts:19,38`** — 文件头两次引用 `render-gate.ts` 作为「已有的、负责出图决策的模块」（「同 render-gate.ts 的做法」），但 head `6709e67` 上**不存在这个文件**。对一个主要交付物就是「把意图写清楚」的 PR，它划的架构边界指向了空。（它在 PR#144 里，尚未合并 —— 建议改成明确的前向引用。）
- **[Low] `knowledge.ts:192`** — commit message 说 `eff` 品类透传是修了个真 bug 且「有专门断言钉住」，但它是**严格的空操作**：`brief.product` 为空时 `product.value` 按定义就是 `FALLBACK_PRODUCT`，它的 profile 恰好等于各槽自己 fallback 分支里的 `profileFor(undefined)`。删掉整行测试仍全绿。当防御性代码留着没问题，但「有断言钉住」这句不成立。
- **[Low] `knowledge.ts:76`** — `GENERIC` 不可达（`profileFor` 只在 `FALLBACK_PRODUCT` 不在表里时才用它，而它永远在）。它的值（200×150×60、qty 500）和实际服务的 Gift set 兜底（250×180×70、300）**不一样**，万一哪天激活，客户拿到的是另一组数字且无测试覆盖。
- **[Low] `knowledge.ts:44,51,84`** — `FINISH_ENUM` / `ProductProfile.finish` / `PartialBrief.finish` 声明并导出了，但 `finish` 从不解析、也不明示。要么注明是 T1.3.2 的接口面，要么先别导出。
- **[Low] 接进去时要先对齐两处冲突**：`qty` 默认值 `chat.ts:107` 是 500、这里是 300；以及 PR#130 给 `apps/api/src/chat.ts:88` 加的 qty 上界这里没有带上。另外 `chat.ts` 的 `PROD_HINT` 是**子串**归一（`luxury watch` → `Watch`）且键全是英文，而这里是精确匹配 —— `Watches`、`watch box`、`gift  set`（双空格）、`Ｗatch`（全角）以及**所有中文品类名**都会错过知识表、掉进随机/通用档。也就是说知识层在生产里触发的频率会远低于设计预期，这恰恰放大了第 4 条的标签问题。

### Assumptions

- 在独立 worktree（head `6709e67`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- 这个 PR 的实际改动是 3 个文件（`gh pr diff` 为准）；分支上其它 commit 属于叠在前面的 PR，不在本次范围。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— R2 独立判定 2-round。
  所以本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。上面五条阻断项都有我自己实跑的证据。

---
*Reviewed by clestons (`$pr` v4, **2-round + 机械验证**, head `6709e67`): DeepSeek R1a+R1b
（`deepseek-v4-flash`;挖到 size/qty 与 boxType 的 source 不一致 —— 本轮它第一条真发现）→ Sonnet 机械验证
（26 组 brief 验 resolveAll/resolveSlot 一致性与明示完整性、6 次连调证实同 brief 输出不确定、
非法 stated 值探针、两个明示变异证明测试查形状不查值）→ Opus R2（独立评审，挖出英文表键漏进中文话术、
非确定性、零校验、以及 17 个变异存活 10 个）→ **Codex R3 挂起未跑；R4 按 R2 的 2-round 判定未跑**。*
