## Verdict: REQUEST_CHANGES（增量复审，head `42e3cfa2`，round 5）—— **两条，都是「这套处理只落在部分槽上」再往外一格**

**上一轮两条 Blocking 和四条 Low 全部真修，而且 `refused` 这个结构建议你实现得很干净。**

| round-4 的问题 | 现在 |
|---|---|
| `boxType` 不 trim/不折大小写，对我们【有】的盒型说假话 | ✅ `' drawer '`/`'Drawer'`/`'DRAWER'`/`' magnet'`/`'MAGNET'`/`'  LIDBASE  '` 全部 `source=stated` 且**返回规范枚举值**；`'Book '` 正确拒绝并带 `rejected='Book'` |
| stated-but-unrenderable 与「客户没说」字节相同 | ✅ `{k:1}`/`['drawer']`/`true`/`'  '`/`'nope'`/`0` 全部 `refused=true`，与「没说」（无 `refused`）可区分 |
| 三边都给了但都解析不出仍说「没看全」 | ✅ 改说「没看懂」；镜像的 `{l:0,w:0,h:0}` 改说「我这边用不了」 |
| 话术回显裸 JS 数字 `1e+21` | ✅ 改成「你说的这个量超出我们能报的范围了」，不回显 |
| size 没有真正的下限 | ✅ 加了 `x < 1 → too-small`，话术「太小了，做不出实体盒子」 |

我按上一个 PR 的教训**重验了上轮验过的不变式**：`deepFreeze` 仍是三层真深、`productLabel('toString'/'__proto__'/'constructor')` 仍返回字符串本身。

新的 `refused` 不变式我在 **32 组 brief** 上跑过：**凡是 brief 带了非 null 值而 `source !== 'stated'` 的槽，`refused` 一律为 true，零违反**；且 `refused` 的槽话术里**零**「通常/最常/一般」。变异 22 个，`normalizeBoxType` 的 trim / 折大小写 / `missingSide` 四种改法 / `x<1` / `>=2000` / `>=10` / 整数检查 / `deepFreeze` / tier / 种子拷贝 / 截断 / `toNum` 形状检查，全部杀掉。

**另外一件我得先认的事**：上一轮我把「`toNum` 放松成裸 `Number(x)` 仍绿」当作证据，举的例子是「变异下 `{qty:''}` 会变成 0 → 『你说的 0 个太少了』」。**你的注释是对的，我是错的。** 我在两个 head 上、带与不带形状检查四种组合都跑过：`{qty:''}` 输出**逐字相同**（`数量我没看懂，先按 500 个算`），因为 `showRaw('')` 返回 null，两条路都落到 `:430` 的兜底。而你换上的例子严格更好——**没有形状检查时 `'1e3'` 会被当成 1000、`'0x10'` 被当成 16 静默收下，零明示**。这个变异现在被杀掉了。

---

**卡住的两条，是同一个形状再往外一格。**

### 🔴 Blocking

1. **[High] `knowledge.ts:143`/`:255`/`:265` — `product` 是唯一既没拿到类型守卫、也没有 `refused` 路径的槽，而且它是【抛异常】而不是拒绝。**
   实测（其余三个槽在同样输入下**一个都不抛**）：
   ```
   ❌抛  product=123            → TypeError: p.trim is not a function
   ❌抛  product={}             → 同上
   ❌抛  product=["Watch"]      → 同上
   ❌抛  product=true           → 同上
   ❌抛  product={name:'Watch'} → 同上
   ❌抛  product=0              → TypeError: brief.product?.trim is not a function   ← `?.` 不对 0 短路
   ```
   `normalizeProduct` 只在 `!p` 后面直接 `p.trim()`。异常穿透 `resolveAll`，打破这个模块自己的核心不变式（**永远返回值**）。
   这正是 round-4 的模式挪到下一个槽：`boxType` 拿到了 `typeof b !== 'string'`、`size` 拿到了 `typeof !== 'object'`、`qty` 拿到了 `toNum` 的形状检查——**`product` 什么都没拿到**。
   而 `:201` 你自己的注释写着调用方（`chat.ts:76` 的 `applyPatch`）把 LLM 输出**原样拷进 brief 不做检查**，`FU-8` 提的两种收口方式（校验整个移进 `knowledge.ts` / 让 `sanitizePatch` 原样透传）**任何一种都会让这条变成线上 500**。
   **修法**：`typeof brief.product !== 'string'` → `{ value: FALLBACK_PRODUCT, source: 'default', refused: true }`。

2. **[High] `knowledge.ts:441` vs `:379` — `refused` 从来没离开 `resolveCore`，round-4 的 B2 在【输出层】原封不动地活着。**
   `resolveAll` 才是这个模块的输出契约，而它把 `refused` 丢了。实测「客户说了但渲染不出」与「客户从没说」两种 Disclosure：
   ```
   boxType {k:1}（说了，我们丢了）  resolveSlot: source=knowledge refused=true
                                    Disclosure: keys=[slot,source,what]  source=knowledge
   boxType 没说                     resolveSlot: source=knowledge refused=-
                                    Disclosure: keys=[slot,source,what]  source=knowledge
   ```
   **键集完全相同，`source` 也完全相同，只有散文不同。** size 同样。（能渲染出来的那种拒绝还有个结构化标记 `overrode`，渲染不出的那种连这个都没有。）
   于是一个**按 `source` 渲染**的下游消费者——而 `source` 存在的意义就是给人按它分支——**仍然分不出「客户说了、我们丢了」和「客户没说」**。这就是 B2 那条判别性问题，整体上移了一层。
   **修法**：`:429` 那个循环里也把 `refused`（或 `overrode`）带上。

### 非阻塞

- **[Med] `refused` 目前是【装饰性】的，这也是那 1 个存活变异真正暴露的东西。** 22 个变异里存活 7 个：`:298`（size 那条同时设 `rejected` 和 `refused` 的分支，删掉 `refused` 仍绿）、`:430` 的条件改成 `r.reason != null` 仍绿、改成 `reason || refused` 仍绿、`add()` 的 key 从 `refused` 换成 `rejected` 仍绿，加三条纯测试空档。
  在测试文件里 grep `refused`，**只在两条注释里出现**（`test:315`/`:317`）——那个标着「refused 不变式」的块断言的是「有 disclosure」和「没有『通常/最常』」，也就是**症状**，从来没断言过这个字段本身。`:430` 是它唯一的读取点，而变异证明在那里 `refused` 与 `reason != null` **完全可互换**。
  所以：**这条不变式只在它本来就冗余的地方成立。** 把 `resolveAll` 变成这个字段的消费者（阻断项 2），再让不变式测试在现有 48 组矩阵上**直接断言这个字段**，M1/M5/M6/M11 四个变异一起被杀，大约 15 行。
- **[Med] `:192-193` `x<1` 修好了 round-4 的字面例子，没修它的现实形态。** `Dims` 没有单位字段，每边 `[1, 2000)mm` 静默接受。一份按 **cm** 写的 brief `{20,15,8}` 和按 **inch** 写的 `{8,6,3}` 都以 `stated` 通过、**零明示**——一个 2 厘米的盒子直接进报价引擎。`PRODUCT_KNOWLEDGE` 里最小的种子尺寸是 45mm。建议下限提到 ~10mm，或对「远小于同品类种子」的尺寸给一条明示。
- **[Low] `:276` vs `:265`** —— `{boxType:'  '}` → `refused:true`，`{product:'  '}` → 静默丢弃、无 `refused`。同样的输入，两个槽相反的待遇。
- **[Low] `:388`** —— `add('product', …, '', …)` 的 `knowledgeWhat` 是空串。今天不可达（注释也这么说），但一旦可达，客户会收到一个空句子。建议改成 throw。
- **[Low] 三条一行的测试空档**：`[100,100,80]` → 「没看懂」没被钉住、`{l:0,w:0,h:0}` → 「用不了」没被钉住、`boxType` 精确枚举匹配没被钉住（`product` 在 `test:253` 恰好有这条测试，可以照抄）。

### 驳回

- **R1a「`x < 1` 拒绝合法的亚毫米尺寸、缺配置项」** —— `x<1` 正是对我 round-4 那条「size 没有真正下限」的修复，`{l:1,w:1,h:1}` 通过。真正的问题在单位假设，已改列为上面那条 Med。
- **R1a「`missingSide` 对 string/array 返回 false 处理不了非对象 size」** —— 返回 false 是**正确的**：`size:'100x100x80'` 应该说「没看懂」而不是「没看全」，这正是我 round-4 要的。（作为**测试**空档它成立，已列在上面。）
- **R1a「`shownQty` 只遮 `too-large`，`1e21` 也会走 `not-integer`」** —— 实测 `1e21` 走的是 `too-large` 且话术不回显；`10.5`/`'1e3'` 回显的是客户自己打的字面量，包在「没看懂」/「按整个算」的句子里，是恰当的。

### 一条结构建议

连续第三轮，缺陷都是**「这套处理只落在部分槽上」**：round-3 是 `size`/`qty` 的双路径、round-4 是 `boxType` 没拿到 trim/大小写、这一轮是 `product` 没拿到类型守卫。修法一直是「把落下的那个补上」，于是下一轮换一个槽落下。

结构上关掉它：**一个 `guardStated(slot, raw)`，四个槽全部从它走**——形状检查、归一、拒绝、置 `refused` 都在里面完成。这样**新加一个槽就不可能跳过这套处理**，而不是靠每轮评审去找哪个槽被落下了。

配套的不变式测试也从「每个槽各写一遍」改成在槽名列表上循环，`SlotName` 加一个成员时测试自动覆盖它。

### Assumptions

- 在两个独立 worktree（`98076304` 与 `42e3cfa2`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原，两个 worktree `git status` 干净。
- **零生产 import 方**（确认仍然成立，只有我和 R2 的探针，都已删除），所以以上全部是接线前的问题，现在改最便宜。接上 T1.5.1 之后，`product` 那条就是一次真实聊天轮次上的 500。
- 每条 finding 都标了严重度依据；`refused` 那条我特意区分了「不变式不成立」（不是）和「不变式只在冗余处被验证」（是）。
- 本 PR 对 `preview` **CONFLICTING**，冲突在 `package.json` 与 `docs/agent/followups.md`（#144 已合入 preview）。`followups.md` 是 append-only 账本，**#145/#146/#147/#148 四个分支都在尾部各自追加**，我用 `git merge-tree` 实测 #146 与 #147 之间就有真冲突——解错方向会**静默丢掉条目**，比 `package.json` 那个危险。
- **R3(Codex PK) 未跑、R4 未跑** —— 两条阻断项都有我自己实跑的输出（6/6 抛异常的对照、两种 Disclosure 的键集与 `source` 逐字对比）。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `98076304`→`42e3cfa2`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；3 条实测全部证伪，其中 1 条作为测试空档成立）→ Sonnet 机械验证（新旧两 worktree
对跑确认两条 Blocking 与四条 Low 全修、32 组 brief 上验 `refused` 不变式、重验 deepFreeze/原型链、
12 个变异）→ Opus R2（独立评审，挖出 `product` 槽 6/6 抛异常、`refused` 从未离开 `resolveCore`
使 B2 在输出层原样存活、单位假设、以及论证那个存活变异真正暴露的是「`refused` 从未被直接断言」）→
**Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 三条 findings 全部实测证伪。但要给它记一分：第 2 条（`missingSide` 对非对象 size）**作为行为判断是错的、作为测试空档是对的**——它指的那个分支确实没有断言钉住（变异 M15 存活）。这是 flash 这几轮里第一次「结论错但指对了一个真空档」。第 1 条（`x<1` 缺配置）正好指反了：那是对上一轮评审的修复，而它旁边真正的问题（`Dims` 无单位字段，cm/inch 的 brief 静默通过）它没看到。
- **下次怎么榨出更多信号**：这个模块的缺陷模式三轮都是「同一套处理只落在部分槽上」。下次直接把这个模式写进 R1 的 prompt：「列出这个文件里所有的 slot / 分支 / 对称结构，逐个检查本次新增的处理是否每一个都拿到了，把没拿到的列出来」。这是纯枚举比对，flash 做得可靠；靠它自己从 diff 里悟出「谁被落下了」目前做不到——这三轮都是 Opus 挖出来的。
