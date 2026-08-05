## Verdict: REQUEST_CHANGES（增量复审，head `2de0925c`，round 2）—— **一条，约 3 行：CTA 没继承在途闸**

上一轮 PR 里只有 4 张截图（`git add` 漏了源文件）。这轮代码补齐了，**设计本身是对的，我先说清楚**：

- **轮次只驱动按钮样式，不驱动 prompt** —— `customerTurns` 的唯一消费点是 `cta.classList.add('primary')`，`bumpTurn()` 只有两个调用点（`enterThread:669` / `followUp:723`），都在 `started` / busy 守卫之后，**推不动**。点 CTA 自身不 `bumpTurn`（0 次引用），这是对的——点按钮不是一轮客户消息。
- **阈值两侧都钉住了**：`09-cta.spec.ts:79` 断言第 6 轮 `not.toHaveClass(/primary/)`、`:82` 断言第 7 轮 `toHaveClass(/primary/)`。「恒亮」和「恒不亮」都过不了。
- **常态可点而非 disabled** —— 和 render-gate「明确指令压过一切」一致。
- **新 prompt 的「预设槽位标准授权」不会绕过付费闸**（我在 #152 里实测过：`applyPatch` 对 `directionConfirmed` 零引用）。

**你自己抓的那两条空转断言，我复核了，是真的修好了**：`先按` / `先随手给了` 这两个串**只出现在 `knowledge.ts` 的明示话术里**（`:419-450`），mock 的回复是英文，不会误命中；而「点两次、第二次不该再有明示」是这个文件里最强的一条断言——它通过**可观察后果**去测写回，而不是测一个本来就有默认值的数字。

我静态推了五个变异，**全部被抓**：删写回（`:141-144`）、第 1 轮就点亮（`:60` + `:79`，抓两次）、永不点亮（`:82`）、删明示（`:111` + `:139`，抓两次）、`onCtaRender` 不调 `showBoxDirections`（`:104` + `:137`，抓两次）。

---

### 关于「重复点击重复烧 GPU」—— 我原本想拦，结论是**不拦**

我先确认了机制：`explicitAction: true` 在 `render-gate.ts:344` **短路返回** `{allow:true, reason:'explicit-instruction'}`（在 `awaitingAnswer` 和 `confirmedDirection` 之前），`inflightFinishes` 只去重在途（`.finally` 里 delete），全仓无「这组参数已出过图」的记忆。所以每次点击都发 4 个付费 batch。

**但这是对的，不该拦**：点击**就是**这套教条里优先级最高的信号，拦它等于让这个 PR 和它依赖的那个文件自相矛盾。每次点击也确实产出一组新的可见卡片，客户有反馈，不是静默燃烧。

**而且我原本设想的「按解析后的 brief 做去重」是个坏答案**：任何 key 都是在猜客户认为什么算「变了」——`color`/`innerColor`/`finish`/`logoText` 都喂给渲染却不在 brief 的四槽里，客户改了烫金再点，会得到一个**死按钮**，而这个仓库的文档反复论证死按钮比多烧一次更糟。而且它对真正的误点场景（第一批还没回来所以再点一次）完全无效——那时 brief 恰恰没变。

**正确的方向是按「在途」而不是按「参数」上闸** —— 这正好也是下面那条阻断项的修法。

### 🔴 Blocking（1 条，约 3 行）

**[Med] `chat.ts:780` / `setDockBusy` — CTA 没有继承在途闸，于是它绕过了 `#144` 以来建立的整套串行化。**

```js
function setDockBusy(busy: boolean): void {
  const go  = document.getElementById('dock-go');      // ← 只管这两个
  const inp = document.getElementById('dock-input');
  if (go) go.disabled = busy;  if (inp) inp.disabled = busy;
}
```
`submitFromDock` 遇到 `followUpBusy` 提前返回、`enterThread` 有 `started` 守卫，而 **`onCtaRender` 里 `followUpBusy` 出现 0 次**，`setDockBusy` 也不碰 `#cta-render`。所以**一轮在途时 dock 明明是灰的，CTA 仍然是活的**。

三个后果，都是普通使用就会碰到的：

1. **翻倍花钱 + D-1 分歧**：点击用**打补丁前**的 `brief` 发 4 个 batch；在途的 `/chat` 随后落地，`applyPatch`（`:94-100`）**无条件**覆写 `brief.product`/`size`/`qty`；然后 `enterThread`/`followUp` 继续走到它自己的 `showBoxDirections`。净结果 8 张卡、8 个付费 batch，而**前 4 张的价格算自 `brief` 已经不再持有的参数**。
2. **饿死的第二组卡片**（我按代码顺序推的，最刺眼的一个）：`showBoxDirections` 先跑 `renderL1`（`addCards` 已经把 4 张卡挂上 `loading`），再跑 `renderL2` —— 而 `renderL2` 看到 `inflightFinishes` 里已有 `dir:${type}:${l}x${w}x${h}` 就对四个盒型全部 `continue`。**没有任何东西会来摘第二组的 `loading`**：`.then`/`.catch`/`.finally` 三个回调闭包捕获的是**第一次调用的 `thumbMap`**（`:328`/`:332` 的 `thumbMap!`）。三种重复点击场景里，**真实用户最可能碰到的那种（渲染要几十秒、以为没反应再点一次）处理得最差：点击被吞、一张图都不发、四个转圈永远停不下来**。
3. 它绕过的正是 `followUpBusy` + `turnSeq` 那套序列化 —— 那套东西是 #144 那轮专门为「晚回来的补丁覆盖新补丁」建的。

**修法（约 3 行）**：把 `#cta-render` 纳入 `setDockBusy`，并在 `onCtaRender` 开头 `if (followUpBusy) return;`。这一条同时解决上面三点，也顺带解决了「误点两次」的浪费——**而且没有死按钮问题**，因为禁用窗口由渲染本身界定，客户看得见它为什么灰。

### 非阻塞（建议一并做，都是一两行）

- **[Med] `chat.ts:618-620` 的 `??=` 写回不修复【被拒绝的值】，于是明示话术会陈述一次没有发生的替换。**
  `??=` 只在 `null`/`undefined` 时赋值，而 #146 建立的 `refused` 恰恰是「**给了但用不了**」这一类——那时 `brief.X` 是真值，`??=` 是空操作。我实跑了 7 组：
  ```
  {product:'watch', boxType:'nope'}   明示=[boxType,size,qty]
      brief 留下 : {"product":"watch","boxType":"nope",...}
      该用的     : {"product":"Watch","boxType":"lidbase",...}     ❌ 不同参
  {product:'watch', size:{l:0,w:0,h:0}}  →  brief 留下 0×0×0,该用 100×100×80  ❌
  ```
  **7 组里 6 组打破了这段代码自己注释声称的 D-1/D-2 同参不变式。**
  ⚠️ **但我要如实说明可达性比它看起来窄**：API 侧的 `sanitizePatch` 我实测过，8 种畸形 size **全部拒绝**，`boxType` 也过 `BOX_ENUM.has()`。所以模型注入不进来。真正的敞口是客户端的 `sanitizeBrief`（`:798`，localStorage 还原）——它对 `boxType` **完全不做枚举校验**，size 用 `+b.size.l || 0` 强转（`{l:100,w:100}` → `h:0`）。也就是说：**今天不出事，靠的是上游校验，而写回这段代码并不知道自己依赖这个前提。**
  修法反而更简单：`resolveAll` 对合法的 stated 值会**原样回显并顺带归一**（`'Drawer'`→`'drawer'`、`'500'`→`500`），所以四行无条件赋值 `brief.product = r.product;` … 比现在的条件写法更短且严格更正确。`qty` 那行同理——它现在漏掉 `10.5`（`typeof number && >= 10` 通过）、`1e9`、`NaN`（`NaN < 10` 为 false）。
- **[Low] `chat.ts:902-923` `restoreThread` 不恢复 `customerTurns`**（0 次引用），于是**回访客户的 CTA 会重新变暗**。一个走「回到历史对话」回来的 15 轮客户，要再聊 7 轮才能重新点亮——而这恰恰是这个 Task 要防的「客户会迷失」，还偏偏打在漏斗最深的那个人身上。一行：`customerTurns = history.filter(m => m.role === 'user').length`。
- **[Low] 两个默认尺寸不一致**：`dims()`（`:124`）兜底 `{100,100,80}`，而 `DEFAULT_PROFILE.size` 是 `{200,150,60}`。空 brief 的客户打「go ahead」拿到 100×100×80，点 CTA 拿到 200×150×60。`knowledge.ts:136` 显示你为了同样的理由把 `qty` 在两处对齐到了 500，`size` 没有。
- **[Low] `chat.ts:625-626` 的 `confirmedDirection` / `awaitingAnswer` 在这条路上provably 读不到**（`explicitAction` 先短路）。不是缺陷，但读起来像闸会参考它们。加一句注释即可。
  （顺带回答我在 #148 里的预言：**它没有应验**。`showBoxDirections` 确实多了第二个调用点，但新调用点走的是无条件放行的 `explicitAction` 分支，两个字段都没被读到。它们仍是 Low。）
- **[Low] `onCtaRender` 不往 `history` 里推任何东西**，模型不知道出过图、也不知道说过明示；而下一次 `/chat` 的 payload 带着的 `brief` 里，**猜出来的值和客户说的值不可区分**。模型会把 `Gift set`/`lidbase`/`200×150×60`/`500` 当成客户陈述的事实而不再追问。这和既有的 `addAgentSay` 不进 history 是同一个模式，不是本轮新增——但写回给了它牙齿。

### 测试的盲区（映射到上面的 finding）

**所有 mock 都返回 `brief_patch: {}`**，所以整个套件只走过「槽位缺失」这条路——而那正是 `??=` 恰好正确的那条。把 `??=` 改成 `=` 对套件是不可见的，这正是那条 Med 能活到评审的原因。同样未覆盖：在途时点 CTA、饿死的第二组卡片、`restoreThread` 后的点亮状态。补一条返回 `brief_patch: {size:{l:100,w:100}, boxType:'tuck-end'}` 并断言**渲染出的卡片尺寸/价格与明示的替换一致**的用例，能同时钉住第一类。

### 驳回

- **R1a「`enterThread` 重入会让 `customerTurns` 多计」** —— `:655` 的 `if (started) return; started = true` 让它每页一次，不可达。
- **R1a「`resolveAll` 在 `brief` 为 null 时会抛」** —— `brief` 是模块级对象字面量，永不为 null/undefined。
- **R1a「`disclosures` 含非字符串时 `join` 会失败」** —— `.map(d => d.what)` 取的是 `Disclosure.what`，类型是 `string`；而且 `join` 对任何值都不会抛。

### Assumptions

- 在两个独立 worktree（`origin/preview` 与 `2de0925c`）里读代码、复刻 `onCtaRender` 的写回逻辑跑 7 组 brief、静态推变异，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- **没有跑 Playwright**（这台机器上 5173/5174 服务器来路不明，#148 首轮查出过 5174 是另一个 checkout）；e2e 的判别力与「饿死的第二组卡片」都是**静态**推的，我逐处标了依据的行号。
- **可达性我如实标注了**：`??=` 那条今天靠上游校验兜着，我实测了 `sanitizePatch` 的 8 种拒绝，没有把它说成「现在就在漏」。
- `ci.yml` 那 6 行不是本 PR 的改动，是 merge `#150` 带进来的。
- **R3(Codex PK) 未跑、R4 未跑** —— 阻断项的三个后果都有我自己的代码追证（`grep -c followUpBusy` = 0、`setDockBusy` 全文、`renderL1`→`renderL2` 顺序、回调闭包捕获的 `thumbMap`）。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `10b0946e`→`2de0925c`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；3 条实测全部证伪）→ Sonnet 机械验证（复刻写回逻辑跑 7 组 brief 证明 6 组破坏
D-1/D-2、实测 `sanitizePatch` 拒绝 8 种畸形 size 以厘清可达性、端到端确认 `explicitAction` 短路、
`grep` 确认 CTA 无 busy 闸且 `setDockBusy` 不碰它、静态推五个变异全部被抓）→ Opus R2（独立评审，
论证重复点击**不该拦**且「按参数去重」是错答案、正确方向是按在途上闸；挖出饿死的第二组卡片、
`restoreThread` 不恢复轮次、两个默认尺寸不一致；并指出套件所有 mock 都是 `brief_patch: {}` 因而
`??=`↔`=` 对它不可见）→ **Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：1/5。** 三条 findings 全部证伪，而且三条都是**不看控制流就下的结论**：`enterThread` 有一行 `started` 守卫就在函数第一行、`brief` 是模块级字面量、`Disclosure.what` 有 string 类型。它对着一个新增了「第三条写 `brief` 的路径 + 第二个 `showBoxDirections` 调用点」的 diff，一条关于**新入口有没有继承既有不变式**的问题都没提。
- **下次怎么榨出更多信号**：这个 PR 的缺陷全部是同一个形状——**新入口没继承老入口积累的守卫**。下次对「新增一个用户可触发入口」的 diff，在 prompt 里写死：「找出已有的同类入口（这里是 `submitFromDock` / `enterThread`），逐条列出它们各自的前置守卫，并检查新入口是否每一条都有对应」。这是结构性枚举比对，flash 有机会做对；靠它自己想到该去对照现有入口，目前做不到。
