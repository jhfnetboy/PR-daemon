## Verdict: REQUEST_CHANGES (incremental re-review, head `f9209db`, round 3)

**「靠消灭第二条路径来关掉」这个判断是对的，而且我用变异证明了它是真的落地了，不是碰巧一致。**

上轮 3 条阻断项 + 4 条非阻塞**全部真修**：

| 上轮问题 | 现在 |
|---|---|
| `resolveAll` 与 `resolveSlot` 不一致（回归） | ✅ **结构性关闭**。15 组 brief × 4 槽，value 与 source 零不符；而且把 `resolveCore` 的 qty 兜底改掉，**两个入口同时跟着变**（`resolveSlot('qty',{})` 和 `resolveAll({}).qty` 一起变成 507）——`PRODUCT_KNOWLEDGE`/`DEFAULT_PROFILE` 现在只在 `:180` 一处被读，`resolveSlot` 是纯委托。已经没有第二份实现可以漂移了 |
| 非法 stated 值被静默覆盖 | ✅ `{qty:3}` 现在明示「**你说的 3 个**我这边先按 500 个算…要按哪个数报？」——点名了客户的数字并回问 |
| 空 brief 用虚构品类说「同类客户通常」 | ✅ 四条明示全是 `default`，措辞改成「我先随手给了…随时改」 |
| 种子表按引用返回 | ✅ 改返回值不再污染表（第二次调用仍是 `l=100`） |
| 原型链 | ✅ `productLabel('toString'/'__proto__'/'constructor')` 都返回字符串本身 |

变异得分也从上轮的 4 个存活降到「谓词全部被钉住」（上下界两侧、`typeof`、NaN 全部能杀）。

**但发散点又移了一层：值的路径现在可证明地一致了，而「话术」的路径不是。**

### 🔴 Blocking

1. **[High] `knowledge.ts:292` — 拒绝数量的理由被写死成「太小的量」，但它对**每一种**拒绝原因都照说。** 实测：
   ```
   qty=3                → 你说的 3 个…（太小的量算不出有意义的价）        ← 对
   qty=1000000000000    → 你说的 1000000000000 个…（太小的量…）          ← 反了
   qty=100000001        → 你说的 100000001 个…（太小的量…）              ← 反了
   qty=NaN              → 你说的 NaN 个…（太小的量…）                     ← 泄漏内部值
   qty=1e+21            → 你说的 1e+21 个…                                ← 裸 String()，而兜底值是 toLocaleString 过的
   qty='500'（字符串）  → 你说的 500 个我这边先按 500 个算（太小的量…）   ← 两边同一个数 + 假理由
   ```
   最后一条最刺眼：LLM 把数量返回成 JSON 字符串是这个文件注释自己说的「常事」，而客户读到的是「你说的 500 个我这边先按 500 个算」。
   上轮阻断项 2 是「别把客户的数字换成一句经验断言」；这轮把它换成了**一个假理由**，是同一个失败模式往下一层走。
   **修法**：理由按**哪个谓词失败**分支（低于下界 / 超过上界 / 没看懂你给的数量），并且当 `rejected` 与兜底值字面相等时，整句「先按 N 算」应当省掉。

2. **[Med] `knowledge.ts:194,288` — 尺寸的 `rejected` 是无条件模板插值，缺字段/垃圾值会把 JS 内部值直接写进客户话术。** 实测：
   ```
   {l:100,w:100}      → 「你给的尺寸（100×100×undefinedmm）我这边算不出来」
   {}                 → 「（undefined×undefined×undefinedmm）」
   {l:null,w:100,h:80}→ 「（NaN×100×80mm）」
   ```
   部分抽取（只拿到 l、w）是 LLM 抽参最常见的失败形态。
   **修法**：三边都是有限数才带值；否则用不带值的说法（「尺寸我没看全」）。

3. **[Med] `knowledge.ts:193,288` / `:198,292` — 字符串型数字被拒绝**并且被倒打一耙**。** 实测 `{size:{l:'100',w:'100',h:'80'}}` → 「你给的尺寸（**100×100×80mm**）我这边算不出来，先按 200×150×60mm 出，正确的是多少？」
   客户看到自己**完全合法**的尺寸被原样回显、还被说成算不出来。不信任类型是对的，但补救应该是**先转换再校验**（`Number(x)` + `Number.isFinite`），而不是拒绝加指责。`{qty:'20000'}` 同理。

4. **[Med] `knowledge.ts:157` — `validQty` 没有整数性检查。** `{qty:10.5}` 和 `{qty:500.7}` 以 `stated` 通过、**零明示**，`resolveAll` 直接把 `500.7` 交给报价路径。上下界现在都钉得很准，但小数个盒子仍然静默穿过 —— 和上轮那批阻断项同类，还开着。（`size` 同理但严重度更低。）

### 非阻塞

- **[Low] `knowledge.ts:277-278`** — product 槽的 `knowledge` 话术「同类客户通常是做${pl}的」**不可达**：`resolveCore` 的 product 分支只会返回 `stated` 或 `default`（10 组输入实测，观察到的 source 恰好是这两种）。在一个以「话术即诚实机制」为论点的文件里留一段永远不会被读到的客户话术，建议删掉。
- **[Low] `knowledge.ts:190,283`** — boxType 的 `rejected` 是 `String(任意值)`，无长度上限也不转义，直接splice进「」里：`{boxType:{a:1}}` → 「你说的「[object Object]」」；`{boxType:'Z'.repeat(300)}` → 一条 339 字符的明示；`{boxType:['lidbase']}` → 「你说的「lidbase」我这边没有这个盒型」（而我们**有**这个盒型）。
- **[Low] `knowledge.ts:155,157` — 新加的 7 行注释为 `Number.isFinite` 辩护，但上一轮说它是死的是**对的**。** 给定 `typeof x === 'number'` 加上下界，`isFinite` 在 27 组探针上**零差异**（`NaN` 过不了任何比较，`±Inf` 过不了边界）。真正挡住 `'500'` 的是 `typeof`，不是 `isFinite` —— 注释里那个举例归因错了。变异确认：两处删掉 `isFinite` 测试都不红。留着当纵深防御没问题，但别在注释里把一条正确的评审意见判为错误。
- **[Low] `knowledge.ts:60` — `Object.freeze` 是浅冻结，实测买不到任何保护。** `Object.isFrozen(PRODUCT_KNOWLEDGE)` 为 `true`，但 `.Watch` 和 `.Watch.size` 都是 `false`；`PRODUCT_KNOWLEDGE.Watch.size.l = 1` 能成功，紧接着的 `resolveSlot` 就返回 `l:1`。删掉整个 `Object.freeze` 测试也不红。另外 `PRODUCT_LABEL`（`:113`）仍是导出的可变 `Record`，而它的值原样进客户话术。建议一个 `deepFreeze()` 覆盖两者 + 一条 `Object.isFrozen` 断言。
- **[Low] `test/resolve-slot.test.ts:148` — 尺寸顺序断言是瞎的，而且是第一轮已经抓过的同一个错误。** `z.overrode === '0×0×0mm'` 是回文，所以把插值倒成 `h×w×l` 测试照样绿。第一轮的原话是「断言只查形状，倒过来也能过」；现在断言查的是精确内容，但内容本身对称，是同一个洞。用 `{l:2500,w:180,h:70}` → `'2500×180×70mm'`。
- **[Low] 另有 3 条守卫今天正确但没被钉住**：`brief.qty != null` 改成 `!== undefined` 后 `{qty:null}`（LLM JSON 常见）会产出「你说的 **null** 个」而无人发现；stated product 路径去掉 `.trim()` 后 `{product:'   '}` 会变成三个空格的 stated 品类；以及「已知品类下被拒绝的值仍应保持 `source:'knowledge'`」这条没有断言。

### 驳回的 findings

- **R1a「`PRODUCT_KNOWLEDGE[known]!` 会 panic」** —— 实测不会。`normalizeProduct` 是对 `Object.keys` 匹配的，`toString` / `__proto__` / `陶瓷杯` 都干净地返回 `default`。
- **R1a「product 空串会被当 stated 返回」** —— 实测 `''` 和 `'   '` 都返回 `default` / `Gift set`。

### 一条观察

三轮下来是同一个形状：**两样必须一致的东西、手工维护**。第一轮和第二轮是「值的两条路径」，这轮结构性地关掉了（值路径现在可证明一致，不需要第四轮）。但发散点移到了**话术**：`add()` 按 source 标签在三条平行字符串里选一条，其中一条（`:292`）陈述的理由只对六种拒绝原因里的一种成立，另一条（`:277`）根本不可达。

如果有第四轮，目标应该是**让理由由「哪个谓词失败」生成，而不是由「哪一级兜底赢了」生成** —— 那是这个文件里最后一处手工维护的对应关系。

模块仍然零 import 方，现在改最便宜；但 `:292` 和 `:194` 恰恰是那种只会在客户对话记录里暴露的缺陷，而现在还没有消费者能替你发现它。

### Assumptions

- 在独立 worktree（head `f9209db`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— R2 独立判定 2-round，
  四条阻断项都有我自己实跑的输出。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons (`$pr` v4, **2-round + 机械验证**, incremental `7659853`→`f9209db`): DeepSeek
R1a+R1b（`deepseek-v4-flash`;2 条 findings 我实测均证伪）→ Sonnet 机械验证（6 组 brief × 4 槽的双路径
一致性、上轮 4 条非阻塞逐条复验、拒绝理由与尺寸插值的实际输出）→ Opus R2（独立评审,用变异证明
「消灭第二条路径」确实落地——改 `resolveCore` 两个入口同时变;并挖出拒绝理由写死、`undefined` 泄漏、
字符串型数字被倒打一耙、非整数 qty 静默通过,以及浅冻结无效与回文断言）→ **Codex R3 挂起未跑；R4 未跑**。*
