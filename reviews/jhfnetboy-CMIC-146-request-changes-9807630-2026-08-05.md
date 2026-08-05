## Verdict: REQUEST_CHANGES（增量复审，head `9807630`，round 4）—— **两条，都是同一个修法再往 `boxType` 挪一格**

**上一轮那条 High 和三条 Med 全部真修，而且修得比我要求的更多。**

| round-3 的问题 | 现在 |
|---|---|
| 拒绝数量的理由写死成「太小」 | ✅ **按哪个谓词失败分支**：`3`→「太少了」/ `1e12`·`100000001`·`1e21`→「超出我们能报的范围」/ `NaN`→「数量我没看懂」/ `10.5`→「盒子得按整个算」/ `null`→普通兜底话术 |
| 字符串型数字被拒绝**并倒打一耙** | ✅ 改成**先转换再校验**：`{qty:'500'}`、`{l:'100',w:'100',h:'80'}` 都被当 `stated` 接受，零拒绝话术 |
| 尺寸拒绝话术漏 `undefined`/`NaN` | ✅ `{l:100,w:100}`/`{}`/`{l:null,…}` 现在都是「尺寸我没看全，先按 200×150×60mm 出」 |
| 非整数 qty 静默通过 | ✅ 现在被拒并给出「盒子得按整个算」 |

按上一个 PR 的教训，我**重验了上轮验过的不变式**（不假设它们在重写后还成立）：

- `resolveAll` vs 单独 `resolveSlot`：**12 组 brief × 4 槽，value 与 source 零不符**
- `deepFreeze` **是真深的**：`PRODUCT_KNOWLEDGE` / `.Watch` / `.Watch.size` 三层全 frozen，写入抛错，改后再取仍是原值
- `productLabel('toString'/'__proto__'/'constructor')` 都返回字符串本身
- 上轮作为证据的两个变异（明示尺寸倒序、数量翻倍）**仍然变红**

边界也是精确的：qty `9/10` 与 `100000000/100000001`、size `1999/1999.9/2000` 两侧都对。

**卡住的两条是同一件事：`boxType` 是唯一没拿到本轮这套处理的槽。**

### 🔴 Blocking

1. **[Med] `knowledge.ts:188` — `validBoxType` 既不 `trim()` 也不折大小写，于是对一个我们【有】的盒型说假话。**
   实测：
   ```
   ' drawer '  → 「你说的「drawer」我这边没有这个盒型，先按天地盒出，你要的是哪种？」
   'Drawer'    → 同上   'DRAWER' → 同上   ' magnet' → 同上
   ```
   `drawer` 就在 `BOX_TYPE_ENUM` 里。**而你自己的测试 `resolve-slot.test.ts:204-205` 明确禁止这句话**（当时只为数组形态关掉了）。`normalizeProduct`（`:141`）给 `product` 做了 trim + lowercase，`boxType` 两样都没有。
   可达性：`apps/web/src/chat.ts:76` 的 `applyPatch` 把 `p.boxType` 原样拷进 brief，不做枚举/trim/大小写检查 —— 而 LLM 返回 `"Drawer"` 是很常见的。
   **修法**：校验前先归一 —— `const b = typeof raw === 'string' ? raw.trim().toLowerCase() : null`，匹配上就把**规范枚举值**作为 `stated` 返回。这一条同时把「我们没有这个盒型」的假话和「白扔掉一个客户真给了的值」一起解决。

2. **[Med] `knowledge.ts:234` + `:373` — 渲染不出来的 stated boxType，与「客户什么都没说」字节相同，于是话术编出经验。**
   实测 `{product:'watch', boxType:{k:1} | ['drawer'] | true | '  '}`：
   ```
   source=knowledge   reason=(无)   →  「做手表的客户最常用天地盒，我先按这个」
   ```
   客户**明明说了**一个盒型，我们不但丢掉了它，还盖上一句虚构的同类经验 —— 正是 round-2 阻断项 2 那个模式，也正是这个模块存在要关掉的东西。
   对比之下 `size`/`qty` 在同样形态下**保住了** `reason`（`{"source":"knowledge","reason":"unparseable"}`）并经 `:373` 的新循环给出诚实话术 —— 但那个循环只遍历 `[['size',size],['qty',qty]]`。
   **修法**：`brief.boxType != null` 时**无条件**挂上 `reason`（不要放在 `shown ? …` 的展开里），并把 `'boxType'` 加进 `:373` 的兜底循环，话术如「盒型我没看懂，先按天地盒出，你要的是哪种？」。否则一个「说了但渲染不出」的盒型，对**每一个下游消费者**都与「没说」不可区分，不只是话术层。

### 非阻塞

- **[Low] `:377`** — 「尺寸我没看全」在三边**都给了但都解析不出**时也会说（`{l:'abc',w:'def',h:'ghi'}`、`size:'100x100x80'`、`size:[100,100,80]`），此时「没看全」是错的。镜像问题在 `:351`：`{l:0,w:0,h:0}`/`{l:-100,…}` 说「我这边没看懂」，其实我们看懂了，只是它非法。
- **[Low] `:363-365`** — 客户话术里回显了原始 JS 数字格式：`qty:1e21` → 「你说的 **1e+21** 个」；超长数字串会在中间被省略号截断。`rej` 没过 `toLocaleString`，而兜底值 `fb` 过了 —— 同一句话里两个数字两种格式。建议 `rej` 也走 `toLocaleString`，并优先用「太大了」而不是回显 `1e+21`。
- **[Low] `:184`** — `size` 只有 `<=0` 的下界检查，没有真正的下限，而 `qty` 有 `>=10`。`{l:0.5,w:0.5,h:0.5}`、`{l:0.001,…}` 会以 `stated` 通过且**零明示**，直接流进报价/几何。
- **[Low] 4 个变异存活，全在本轮新加的代码里**：(1) 把 size 的 `reason` 强制成 `'unparseable'`、(2) 把 `reason === 'too-large'` 三元写死成 `false`，两者都存活 → **size 的「太大」话术分支没有任何断言**；(3) 把 `:377` 那句「尺寸我没看全」换成任意字符串仍绿 → **本轮的招牌话术修复只被 `!/undefined|NaN|null/` 和 `length > 0` 两个否定式断言守着，从没按内容断言过**；(4) 把 `toNum` 放松成裸 `Number(x)` 仍绿 → `:159` 注释称为承重的那个形状检查没被钉住（变异下 `{qty:''}` 变成 `0` → 「你说的 0 个太少了」，一个客户从没说过的数字）。另外 `!= null` → `!== undefined` 在 size 和 qty 上都存活：`:217` 断言的是 `overrode === undefined`，变异下也成立 —— 该断言应该落在 `what` 上（`{qty:null}` 必须读作「数量我先按 500 个算的」而不是「数量我没看懂」）。

### 驳回

- **R1a「`:239` 的 `brief.size!` 非空断言」** —— 它在 `sr === null` 之后，而那只在 `brief.size != null` 时可达。不可达，不是缺陷。
- **R1a「用 `toNum` 重新解析而不复用数组」** —— `toNum` 是纯函数，两个调用点在互斥分支里，零行为差异，纯文体。

### 一条给接线 PR 的重要提醒（不属于本 PR，但影响很大）

我把 `sanitizePatch`（`apps/api/src/chat.ts:88`）→ `resolveAll` 端到端跑了一遍：

- `{qty:1e12}` 在到达 `knowledge.ts` **之前**就被静默 clamp 成 `100000000`，`{qty:10.5}` 被静默四舍五入成 `11` —— 两者都以合法 `stated` 抵达，**零明示**。客户说了 1e12，被报了 1 亿个盒子，而且没人告诉他。
- `{size:{l:'100',…}}` 和 `{boxType:' drawer '}` 在上游被丢成 `{}`，所以本轮的字符串转换工作在那条路径上**完全不可见**。
- 本轮新加的四个 `RejectReason` 里有两个（`too-large`、`not-integer`）**经 API 不可达**。

写第一个 importer 的人必须二选一：要么把校验整个移进 `knowledge.ts`，要么让 `sanitizePatch` 原样透传 —— 否则这个 commit 修好的话术路径，恰恰在最需要它的地方被绕过去了。

### 一条结构建议

`boxType` 这个缺口之所以存在，是因为「客户说了但被拒」这件事是**隐式编码**的（有时是 `rejected != null`，有时是 `reason != null`，有时两者都没有），而不是在「拒绝一个 stated 值」这个唯一的点上显式置一个字段。

在 `Resolved2` 上加一个 `refused: true`，再配一条覆盖 brief 矩阵的不变式测试（「凡是 brief 带了非 null 值而 `source !== 'stated'` 的槽，其话术不得包含『通常』『最常』」），这一类三轮里出现三次的问题就会被一次性关掉。

### Assumptions

- 在独立 worktree（head `9807630`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- 模块仍零 import 方，`tsc --noEmit` 干净，套件全绿 —— 所以以上都是接线前的问题，现在改最便宜。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— R2 独立判定 2-round，
  两条阻断项都有我自己实跑的输出。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `f9209db`→`9807630`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；2 条均为文体、实测不成立）→ Sonnet 机械验证（拒绝理由按谓词分支的 9 种输入、
尺寸话术 5 种畸形输入、非整数 qty、并按前一个 PR 的教训重验双路径一致性/deepFreeze/原型链/两个历史变异）→
Opus R2（独立评审，定位到 `boxType` 是唯一没拿到本轮处理的槽——trim/大小写缺失导致对存在的盒型说假话、
以及 stated-but-unrenderable 与「没说」不可区分；并端到端发现 `sanitizePatch` 会在上游静默 clamp，
使本轮两个新 reason 分支经 API 不可达）→ **Codex R3 挂起未跑；R4 未跑**。*
