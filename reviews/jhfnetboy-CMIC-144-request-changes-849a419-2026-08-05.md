## Verdict: REQUEST_CHANGES (incremental re-review, head `849a419`, round 3)

**上一轮 4 条阻断项全部真修了**，我拿同一组探针在新旧两个 head 上对跑，**26/26 全对**（旧 head 在这 26 条里错 20 条）：

| 上轮问题 | 旧 `bb29657` → 新 `849a419` |
|---|---|
| 中文触发词 + 标点/emoji | `出图吧。`/`就这个吧！`/`直接出图。`/`好的，出图吧。`/`出图。`/`就这个吧👍`/`出图吧🙏` **false → true** ✅ |
| `will` 被从疑问词表删掉 | `Will you go ahead and render it` 等 **true → false** ✅ |
| 同句反悔只在逗号分隔时生效 | `go ahead. no wait.`/`go ahead — no wait`/`go ahead no wait` 等 **true → false** ✅ |
| 英文动词无边界 | `make it cheaper`/`take this into account` 等 **true → false** ✅ |

而且我按上一个 PR 的教训**重跑了第一轮那 18 个字符串**，全部没有回归；6 条正向用例仍正常触发。

**但这是同一个 200 行检测器的第三次重写，而且第三次出现同样的形状：修好被点名的字符串，修复本身的机制在上一层开出新洞。这轮的新洞全在「绝不能错」的那个方向。**

### 🔴 Blocking

1. **[High] `render-gate.ts:110` — 新回归：转述别人的话现在会真出图。**
   `TRAILING_DECOR` 为了让 `就这个吧👍` 能过而剥掉尾部装饰字符，连带把中文引号 `”』」` 也剥了，于是引述内容顶到了 `$` 锚点上。两边对跑：
   ```
   他说“出图吧”        false → true ❌
   老板说“直接出图吧”   false → true ❌
   同事说“做张图”      false → true ❌
   ```
   （`he said "go ahead"` 新旧都 true，属既有洞。）emoji 修复和这个洞是**同一行**造成的。
   **修法**：剥装饰字符前先判断整句是否含引述结构（`说`/`said` + 引号），或者只剥真正的表情/空白，不剥引号。

2. **[High] `render-gate.ts:157` — 中文的推迟词是**前置**的，末尾锚定结构上看不见它们。**
   两边对跑，6/6 全 true：
   ```
   以后再做图  下次做图吧  回头出图吧  晚点出图吧  下周再出图  等确认了再出图吧
   ```
   这正是上一轮 High-4（`go with this approach later maybe`）的镜像 —— **英文推迟词后置**（被 `$` 挡住，上轮修好了），**中文推迟词前置**（锚点看不见）。同一个双语类别只修了英文那一半，而语料只采样了英文那一半。烧钱方向。

3. **[High] `render-gate.ts:206-222` — 条件句 / 征求许可会误触发，因为分句把「条件」切成了独立分句，而只有触发词**之后**的分句才被检查。**
   两边对跑，8/8 全 true：
   ```
   if the price is ok, go ahead        once you get the specs, go ahead
   let me know if I should go ahead    tell me before you go ahead
   I wonder if we should go ahead      ok to go ahead
   so should I go ahead                maybe go ahead
   ```
   （`so should I go ahead` 能逃是因为 `INTERROGATIVE_LEAD` 用 `^` 锚定，前面加一个虚词就失效。）
   这是「取最后一个指令分句 + 只往右看」这个结构的固有缺陷，不是漏了哪个词。

### 非阻塞

- **[Med] `render-gate.ts:151` — `\b(?:i['’]?ll|i\s+will)\s+take\b` 没有末尾锚点。** `I'll take this into account` / `I'll take a look first` / `I'll take my time` / `I'll take the cheaper one` 新旧**都是 true**（不是回归，但方向是烧钱的）。讽刺的是文件 `:140` 自己就把 `take this into account` 列为不该触发的例子 —— 这轮给裸 `take this` 加了边界，漏了 `I'll take`。R1a 这次抓对了这条。
- **[Med] `render-gate.ts:146` — TAIL 回归比 R1a 说的更宽，而且结果取决于用户打没打逗号。** `go ahead thanks` / `go ahead ok` / `go ahead now please` **true → false**；但 `go ahead, thanks`（带逗号）仍然 true。同一个意思，有没有逗号给出相反结论。便宜方向，但一致性问题值得一并修。
- **[Med] `render-gate.ts:218,210` — 本轮的招牌结构改动（`matchEnd` + 尾部复查）几乎是死代码。** 除了 `\bi'll take\b`，每个 GO_PATTERN 都以 `$` 结尾，所以 `core.slice(matchEnd)` 恒为空串。3400 条输入的差分：把 `matchEnd` 换成 `0`，结果**零变化**；删掉整个尾部复查，只有 72 条变化，**全部是 `i'll take` 系列**。代码注释写的「`go ahead no wait` 完全没有标点，只能这样抓」与事实不符 —— 那个串被拒是因为锚点根本不匹配，压根走不到尾部复查。
- **[Med] `render-gate.ts:122,171` — 上一轮 High-3 的修复（补 ASCII `.`、`—…:` 分隔符）实际是装饰性的。** 3696 条输入差分为 0：`go ahead. no wait.`、`go ahead — no wait` 之所以被拒，是靠末尾锚定，不是靠新分隔符。`CANCEL_ACTION` 整块同样零影响。
- **[Med] `render-gate.ts:203` — `raw.slice(-2000)` 会把疑问词开头砍掉。** `'Should we ' + 'x'×2500 + ' go ahead'` 新旧都 true。粘一段长规格再问一句是很平常的操作。建议截断后若头部被砍就直接判 false。
- **[Low] `render-gate.ts:110,122` — 全角 `．`(U+FF0E) 和 `～`(U+FF5E) 既不在分隔符、也不在 `end` 正则、也不在 TRAILING_DECOR 里**：`出图吧．` / `出图吧～` 新旧都 false。便宜方向，但产生 `。！？` 的那个输入法同样会产生它们。
- **[Low] `render-gate.ts:209`** — `GO_PATTERNS.map(exec).find(Boolean)` 命中后仍跑完全部 11 个正则，且取的是**数组顺序**的第一个而非最左/最右匹配，`matchEnd` 因此来自一个任意模式。今天无害只是因为 `matchEnd` 本身是惰性的。

### 测试判别力：21 个变异存活 8 个

- **M10 删掉整个 TAIL** → 210 条输入结果变化，测试**全绿**（没有任何用例测 `go ahead now` / `render it please`）
- **M12 去掉 `go ahead` 的 `$` 锚点** → 30 条变化，全绿；而且每一条差异都是「不锚定反而更对」（`go ahead thanks` false→true）—— **套件分不清这个回归和它的修复**
- **M21 同时去掉锚点并删掉两个新分隔符** → 仍全绿，两个机制互相掩护，谁都没被钉住
- M1/M6/M8/M9/M13 存活是因为它们本来就是死代码

### 一条结构性建议（第三轮了，值得认真考虑）

三轮下来是同一个循环：修好被点名的字符串 → 修复本身的机制在上一层开新洞。本轮的 emoji 剥离造出了引述误判，本轮的末尾锚定造出了 `thanks`/`ok` 漏判**并且**让本轮自己的分隔符变成死代码。

真正的信号不是**位置**，而是一小组**修饰语类别**，它们独立于动词地前置或后置：
- **条件**：`if` / `once` / `等` / `如果`
- **推迟**：`later` / `以后` / `回头` / `下次` / `晚点`
- **转述**：`X said` / `说` + 引号
- **征求许可**：`should I` / `ok to` / `let me know if`
- **否定/反悔**：现有的 NEGATORS / REVERSAL

把它们做成围绕触发词的**显式作用域检查**，而不是试图用触发词上的 `^`/`$` 锚点去表达 —— 后者的附带伤害（`thanks`、`ok`、全角标点）正是每轮都被重新打破的东西。

按这个文件自己声明的成本不对称，最省事的即时降险不是加更多正则，而是：**要求同时满足「有触发词」且「整句不含任何修饰语类别的词」，长句/多分句一律默认 false**。我上面确认的 15 条误触发会全部消失，代价只是多按一次按钮。

### Assumptions

- 在两个独立 worktree（`bb29657` 与 `849a419`）里对跑同一组探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- 每条 finding 都标注了「新回归」还是「新旧皆有」，以免把既有洞算到这个 commit 头上。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— 三条阻断项都有新旧两版对跑的
  直接证据。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons (`$pr` v4, **2-round + 机械验证**, incremental `bb29657`→`849a419`): DeepSeek
R1a+R1b（`deepseek-v4-flash`;3 条 findings 中 2 条成立,其中 `i'll take` 无锚点是烧钱方向的真发现）→
Sonnet 机械验证（新旧两 worktree 对跑上轮 4 条 26/26、重跑第一轮 18 条确认无回归、`i'll take` 与
`go ahead thanks` 的新旧归属判定）→ Opus R2（独立评审，挖出引述回归、中文推迟词前置、条件句误触发，
并用 3400+ 输入的差分证明本轮的 `matchEnd` 与上轮的分隔符都是死代码，21 个变异存活 8 个）→
**Codex R3 挂起未跑；R4 未跑**。*
