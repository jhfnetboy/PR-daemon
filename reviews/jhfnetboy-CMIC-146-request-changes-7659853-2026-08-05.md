## Verdict: REQUEST_CHANGES (incremental re-review, head `7659853`, round 2)

**上一轮 5 条阻断项全部真修了**，我逐条实跑验证：

| 上轮问题 | 现在 |
|---|---|
| 内部英文键漏进中文话术 | ✅ 「按一只常规**「Gift set」**假设的」→「我先按一只常规**礼盒**假设的，装的不是这个就告诉我」 |
| 同 brief 连调 6 次出 4 种盒型 | ✅ 6 次调用 **1 个结果**，随机层整个拿掉了 |
| stated 值零校验 | ✅ `{0,0,0}` / `{l:-10}` / `PYRAMID` / `1e12` 全部落到 `default` |
| 未知品类的 size/qty 标成 knowledge | ✅ 现在标 `default` |
| 明示话术不随 source 变 | ✅ `knowledge` →「做礼盒的客户最常用天地盒」；`default` →「盒型我先随手给了天地盒，随时改」 |

而且**测试真的变锋利了**：上轮活下来的三个变异（明示尺寸倒序、数量翻倍、把 `default` 全标成 `knowledge`）**现在全部变红**。加第四种 source + 让话术随 source 变，正是该走的路。

**但这次重写引入了一条回归，另有一条新的诚实性问题 —— 恰好是这个 PR 自己要解决的那一类。**

### 🔴 Blocking

1. **[Med] 回归：`resolveAll` 与单独 `resolveSlot` 在「没说品类」时不再一致。** 实测 head `7659853`：
   ```
   brief={}        resolveAll → size 250×180×70 / qty 300 (knowledge)
                   resolveSlot → size 200×150×60 / qty 500 (default)   ❌
   brief={qty:3}   同样不一致
   ```
   上一轮我用 26 组 brief 验过、四个槽全一致；旧代码在 `boxType` 分支里有一段显式对账，注释写着「**同一件事两条路径两个结果，是个陷阱**。（这条不一致是本 Task 自己的单测抓出来的。）」—— 重写把 size/qty 的对账删掉了，现在只有 `boxType` 还一致，而那是巧合（两边都是 `lidbase`）。
   顺带：`:217-219` 说 `eff` 那行「严格来说是【空操作】」也不再成立 —— 删掉它测试会红，它现在是承重的。
   **修法**：让两条路径**按构造**一致 —— `resolveSlot` 接收已解析的 product，或者两者都走同一个内部 `resolveWith(known)`；并补一条「四个槽 × 无品类 brief」的 value + source 双重断言，也就是旧注释说曾经抓到过这个 bug 的那条断言。

2. **[Med] 客户说了非法值，被静默改掉且不告诉他。** 实测 `{qty:3}`（3 个的打样单，能过 `chat.ts:88` 的 `sanitizePatch`，它只要求 `qty>0`）：
   ```
   明示 → 「礼盒这类通常做 300 个，先按这个算」
   ```
   客户明确说的 3 消失了，取而代之的是一句**声称行业经验**的话。`boxType:'PYRAMID'`、只给了 `l,w` 的 size 同理。
   校验本身是上轮要求的，但它的用户可见后果，是比原来那个 bug **更严重**的一类不诚实 —— 而这正是这个 PR 存在要关掉的那一类。
   **修法**：加第四种明示语义 `overridden`：「你说的 3 个低于我们 10 个起订，我先按 300 个算，可以吗」；至少在 `Disclosure` 上带一个 `overrode: <原值>`。

3. **[Med] 空 brief（生产里最高频的入口）三条明示都在用一个**我们自己编出来的品类**说「同类客户通常」。**
   `product` 标 `default`（「我先按一只常规礼盒假设的」），然后另外三条基于这个虚构的品类标 `knowledge`：「做礼盒的客户最常用天地盒」/「礼盒的常见内腔是 250×180×70mm」/「礼盒这类通常做 300 个」。客户什么都没说，「同类客户通常」是我们单方面指派的细分。这是上轮阻断项 4 那句「伪装成推断的常量」在最高频路径上的残留，而测试 `:77-82` 现在把它固化成了期望输出。
   **修法**：`product.source !== 'stated'` 时，那三条也降级成 `default`；或者干脆不要从一个 `default` 的品类推导 `knowledge`。

### 非阻塞

- **[Med] `knowledge.ts:177-178` — 解析出来的 `size` 是模块常量的**引用**。** `resolveAll({product:'Watch'}).size === PRODUCT_KNOWLEDGE.Watch.size` 为 `true`，改一次就把种子表改了：`a1.size.l = 9999` 之后，下一个客户会读到「手表的常见内腔是 **9999**×100×80mm」。在 Workers isolate 里这是跨请求污染。目前只是潜在（模块还没有任何 import 方），但等某个渲染器开始原地归一化尺寸就很难查了。`stated` 的 size 同理，直接把调用方的对象还回去了。
  **修法**：返回副本（`{ ...profile.size }`），种子表 `Object.freeze`。
- **[Low] `knowledge.ts:119`** — `PRODUCT_LABEL[p] ?? p` 会读原型链：`productLabel('toString')` 返回一个**函数**，`'__proto__'` 返回 `Object.prototype`，插值进话术就是「做function toString() { [native code] }的客户最常用天地盒」。今天从 `resolveAll` 走不到（带 `${pl}` 的话术只在 `knowledge` 分支，需要真表键），但 `productLabel` 是导出的，而 `product` 是自由的 LLM 文本。用 `Object.prototype.hasOwnProperty.call` 或 `Object.create(null)`。
- **[Low] 新加的校验谓词是全文件覆盖最差的代码。** 4 个变异存活：`x < 2000` → `x < 20000` 存活（没有任何用例用过 ≥2000 的尺寸 —— 也就是上轮阻断项 3 要的那个上界完全没测）；`q <= 1e8` → `q <= 1e9` 存活；删掉 `typeof q === 'number'` 和 `typeof x === 'number'` 都存活 —— 而它们是承重的：没有它们，`{qty:'500'}` / `{size:{l:'100',…}}`（LLM 返回 JSON 字符串是常事）会被强制转换后当 `stated` 通过。
  建议：每个新谓词都带**边界两侧**的用例（`2000`/`1999`、`9`/`10`/`1e8`/`1e8+1`、字符串型数字）。
- **[Nit] `knowledge.ts:142,144`** — 两处 `Number.isFinite` 是死的（`x>0 && x<2000`、`q>=10 && q<=1e8` 本身已排除 NaN/±Infinity），删掉行为和全部测试都不变。测试 `:31` 的注释把 NaN 用例归功于它，是误导。另外 `add('product',…)` 的 `knowledgeWhat`（`:237`）不可达 —— product 只会是 `stated` 或 `default`。

### 驳回的 findings

- **R1a「`validQty` 上界 1e8 可能拒掉合法大单」** —— `chat.ts:88` 上游已经 clamp 到 1e8，更大的值根本到不了这个模块。
- **R1a「`validSize` 的 2000mm 没注释」** —— 注释在，且引用了 `chat.ts:88`，值也和 `chat.ts:89` 完全一致。真正（更小的）问题是这个重复值没有测试，已另记在上面。

### Assumptions

- 在独立 worktree（head `7659853`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- 模块仍然零 import 方，所以以上全部是接线前的问题，现在改最便宜。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— R2 独立判定 2-round。
  所以本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

**一条我自己的检讨**：上一轮我用 26 组 brief 验过两条路径一致，这一轮验修复时**没有重验它** —— 回归是 R2 独立读出来的，我只是事后确认。以后凡是「上轮验过的不变式」，在重写之后都要重跑一遍，不能只验被点名的那几条。

---
*Reviewed by clestons (`$pr` v4, **2-round + 机械验证**, incremental `6709e67`→`7659853`): DeepSeek
R1a+R1b（`deepseek-v4-flash`;2 条 findings 均不成立）→ Sonnet 机械验证（逐条实跑上轮 5 条阻断项、
三个上轮存活的变异现在全部变红、双路径一致性探针）→ Opus R2（独立评审，挖出双路径一致性回归、
非法 stated 值被静默覆盖、空 brief 用虚构品类说「同类客户通常」、种子表按引用返回、
以及新校验谓词的 4 个存活变异）→ **Codex R3 挂起未跑；R4 按 R2 的 2-round 判定未跑**。*
