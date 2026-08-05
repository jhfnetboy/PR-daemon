## Verdict: APPROVE（增量复审，head `a20c4481`，round 6）—— **两条阻断项都修好了，而且是把处理补齐到最后一个槽**

| round-5 的问题 | 现在 |
|---|---|
| `product` 是唯一没有类型守卫、且【抛异常】而不是拒绝的槽 | ✅ **15 种输入零抛出**：`123` / `{}` / `['Watch']` / `true` / `{name:'Watch'}` / `0` / `NaN` / `Symbol` / 函数 全部 → `value='Gift set' source=default refused=true`；`null` / `undefined` 正确**不带** `refused`（那是「没说」）；`'Watch'` / `'watch'` / `'zzz'` 仍是 `stated` |
| `refused` 从来没离开 `resolveCore`，B2 在输出层原样存活 | ✅ **`refused` 现在进了 `Disclosure` 的键集**，四个槽一致：说了但渲染不出 → `keys=[slot,source,what,refused] refused=true`；完全没说 → `keys=[slot,source,what]` 无 `refused` |

我把不变式提到**输出层**重跑：**18 组 brief 上，凡是 brief 带了非 null 值而 `source !== 'stated'` 的槽，它的 `Disclosure` 一律带 `refused===true`，零违反。** 变异确认它真被断言钉住了——把 `refused` 从 Disclosure 层去掉，套件红。

上轮那条 Low 也修了：`{product:'  '}` 现在和 `{boxType:'  '}` 一个口径（都 `refused=true`），代码注释还写明了「纯空白字符串也算『说了』—— 和 boxType 的 `'  '` 同一口径」。

### 非阻塞

- **[Low] 上轮那个存活变异还在**：`:320`（size 那条同时设 `rejected` 和 `refused` 的分支）删掉 `refused` 后套件仍绿。我验过它**不是等价变异**——`{l:0,w:0,h:0}` / `{l:0.5,…}` / `{l:3000,…}` 三种情况下 `Disclosure.refused` 会消失。但危害比上轮小得多：那三种情况的 Disclosure 里仍有 `overrode` 这个结构化标记，下游按 `overrode` 分支仍然分得出来。补一条断言即可（现有 48 组矩阵里加一行）。
- **[Med] 单位假设仍未处理**（上轮就列的）：`Dims` 没有单位字段，`{l:20,w:15,h:8}`（cm 形状）和 `{l:8,w:6,h:3}`（inch 形状）都以 `stated` 通过、零明示，而 `PRODUCT_KNOWLEDGE` 里最小的种子尺寸是 45mm。建议下限提到 ~10mm，或对「远小于同品类种子」的尺寸给一条明示。
- **[Low] 上轮列的三条测试空档**（`[100,100,80]` → 「没看懂」、`{l:0,w:0,h:0}` → 「用不了」、`boxType` 精确枚举匹配）仍无断言钉住，各一行。

### 驳回

- **R1a「`normalizeProduct` 现在对非字符串返回 undefined，而 `resolveCore` 另外处理，需确保一致」** —— 实测两条路径给出同一结果（`source=default refused=true`），15 种输入零不一致。分层是有意的：`normalizeProduct` 只管归一，「说了但用不了」的语义由 `resolveCore` 统一置 `refused`——和另外三个槽同一形状。
- **R1a「`raw != null` 把 `0` 当成『说了』，而 `normalizeProduct` 对 `0` 返回 undefined，null/undefined 与 falsy 语义要对齐」** —— **`0` 就该算「说了」**：客户传了一个值，只是我们用不了。实测 `{product:0}` → `refused=true`，而 `{product:null}` → 无 `refused`。这正是 round-4 B2 要求的区分，语义是对的。

### 一条结构上的肯定

连续三轮，缺陷都是同一个形状——**「这套处理只落在部分槽上」**（round-3 是 `size`/`qty` 双路径、round-4 是 `boxType` 没拿到 trim/大小写、round-5 是 `product` 没拿到类型守卫）。这一轮把最后一个槽补齐了，四个槽现在**形状一致**：类型守卫 → 归一 → 拒绝时置 `refused` → 传到 Disclosure。

我上轮建议的 `guardStated(slot, raw)` 没有做成一个共享函数，但**行为上已经收敛了**，而且不变式测试现在直接断言 `refused` 字段本身（不再只断言症状）。如果以后要加第五个槽，抽成共享函数仍然值得——那时「漏掉一个」才会在结构上不可能，而不是靠这四处各自写对。

### Assumptions

- 在两个独立 worktree（`42e3cfa2` 与 `a20c4481`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原，`git status` 干净。
- **零生产 import 方**（仍然成立），所以剩下的非阻塞项现在改仍然最便宜。
- 本 PR 对 `preview` 冲突。注意 **#146 分支的 `check` 串里没有 `pnpm test:gate`**（它在 #144 合入前开的分支）——`#142` 已经用「合一次 preview」解决了同样的问题，建议照做。
- **R3(Codex PK) 未跑、R4 未跑** —— 本轮是 APPROVE，两条阻断项的修复有我自己实跑的输出（15 种输入零抛出、Disclosure 键集对比、18 组不变式扫描、变异确认已钉住）。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `42e3cfa2`→`a20c4481`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；2 条实测均证伪，其中一条把正确的语义区分当成了不一致）→ Sonnet 机械验证
（15 种畸形 product 输入确认零抛出、四个槽的 Disclosure 键集逐个对比确认可区分、18 组 brief 上重跑
不变式于输出层、三个变异确认 refused 已被直接断言、复测上轮存活变异并验证它非等价）→
**Opus R2 未跑（本轮无待判定的争议项，两条阻断项的修复我自己就能证）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 两条都实测证伪，但**都落在本轮真正改动的两行上**，不像早几轮那样在无关代码里找 TypeScript 语法问题。第二条尤其可惜：它注意到了 `raw != null` 把 `0` 当「说了」而 `normalizeProduct` 对 `0` 返回 undefined——这个观察是准的，只是它把**有意的语义分层**读成了不一致。差一步就是「这个分层对不对」的正确提问。
- **下次怎么榨出更多信号**：这个文件三轮的评审结论都写在代码注释里（「和 boxType 的 `'  '` 同一口径」「四轮 Blocking-1」这种）。下次要求 R1「对每条 finding，先在附近注释里找有没有已经解释过这个设计选择的句子；找到就复述它并说明你的 finding 与它是否矛盾」——它这两条如果先做这一步，自己就会撤回。
