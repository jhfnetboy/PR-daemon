## Verdict: REQUEST_CHANGES（首轮，head `d9b7bb95`）—— **卡的是那句声称，不是那个重构**

**先说这个 PR 最好的部分：新加的 e2e 用例是真的，而且比它旁边那条更强，应该原样保留。**

我把它的两条断言逐个推了一遍判别力（静态推，没跑 Playwright——这台机器上 5173/5174 的服务器来路不明）：

| 变异 | 结果 | 靠哪条断言抓住 |
|---|---|---|
| `addCards` 恒挂 `loading`（去掉 `&& photorealPending`） | **红** | `.thumb.loading` 计数。`photoreal=false` 时 L2 整块不跑，而两处 `classList.remove('loading')`（`:346` 成功回调、`:350` catch）**都在 `if (RENDER_AVAILABLE && photoreal)` 里面**；另外两处一个是 `:783` 改分离克隆、一个是 `:811` 的 rehydrate，都不在这条路上。没有东西会去掉这个类 |
| `showBoxDirections` 忽略 `photoreal`（改成 `if (RENDER_AVAILABLE)`） | **红** | `expect(calls()).toHaveLength(0)`，**不是** loading 那条——503 stub 下 `:350` 会剥掉 loading 加上 failed，两条分支的 loading 都是 0 |
| `renderThumb` 解析出 null | **红** | `.thumb img` 计数（写成 `<span class="ph">Preview</span>`） |

**两条断言的变异集是不相交的，都承重。** 而且旁边 `:52` 那条既有用例**从来没断言过 `calls()`**（只 record 了计数，用 `.thumb.failed` 当代理），新用例补上了直接断言——净增强。

**行为侧也是对的。** 我读了整条路径确认验收项成立：`enterThread:661` 无条件调 `showBoxDirections(v.allow)`，`:329` 传 `addCards(specs, photoreal)`，`:274` 是 `if (s.finishKey) { …; if (RENDER_AVAILABLE && photorealPending) add('loading') }`。所以 `done:false` 且闸拒绝时：4 张卡、4 个 `<img>`、0 个 `.thumb.loading`、0 次 `/render-finishes`。

---

**但 `apps/web/src/chat.ts` 在这个 PR 里【零行为改动】。**

`git diff origin/preview d9b7bb95 -- apps/web/src/chat.ts` 滤掉注释行之后是**空的**——新增的 18 行全是注释。（对 `f2e7eb6` 和 `origin/preview` 两个基准都验过；`#145`/`#146` 没碰 `chat.ts`，所以这个结论对活的 preview 也成立。）

### 🔴 Blocking

1. **[Med] `chat.ts:299-313` — 注释以现在时断言 `renderL1()` 和 `renderL2()` 存在，而它们不存在。**
   ```
   * 现在是两段:
   *   - `renderL1()` —— **无条件**。四张结构卡 + WebGL 灰模,零成本,永远即时出。
   *   - `renderL2()` —— 只在 `photoreal` 为真时发付费 batch,且只在这时才挂 loading。
   ```
   全仓 grep（`apps/web/src` + `e2e/` + `docs/`）这两个标识符**只有两处命中，都在这段注释里**。`showBoxDirections` 仍是一个函数，本 PR 加的是两条 `// ── L1 / L2` 分节标记。PR body 用的是同样的措辞。

   **为什么这条要拦**：纯文档 PR 的宽松线豁免的是**精度瑕疵**（措辞不严、少个限定词），不豁免**对具名 API 的虚假存在声明**。「现在是两段 `renderL1()`」不是不严谨，是不成立——而且不成立的方向正是这个仓库代价最大的那个：它告诉下一个读者重构已经做完了。一个想扩 L2 的人 grep `renderL2()`，只会搜到「它存在」这句话本身。这和 #142 第 4 轮拦的、以及 #145–#148 反复出现的，是同一类缺陷。

   **修法（不要求做重构，见下）**：把注释改成描述**真实存在的那两个分节**（`// ── L1` / `// ── L2` 标记确实建立了它们），并同步改 PR body 的「## 现在」。

2. **[Low，但是机械缺陷] `chat.ts:295-313` — 叠了两个 `/** */` 块，`@param photoreal` 悬空了。**
   ```
   /**
    * @param photoreal 允不允许发【付费】的照片级 batch。…      ← 原有块
    */
   /**
    * ## 两个显式的层  …                                       ← 本 PR 新增
    */
   function showBoxDirections(photoreal: boolean) {
   ```
   **只有最后一个 doc 注释会绑定到符号上。** 于是编辑器悬停和任何 tsdoc/typedoc 抽取看到的是新块——而新块没有记录任何参数，`@param` 文档挂在了空处。应该把旧块**折进**新块，而不是叠在上面。

### 非阻塞

- **[Low] `docs/agent/tasks.md:56`** —— 开发范围第 1 条「抽出 `showBoxDirections()` 里的两段逻辑：`renderThumb` = L1、`renderFinishes` = L2」未完成，而 PR 标题写的是「L1/L2 分成两个显式的层」。
  **但我不要求你做这个抽取。** T1.2.1 的**目标**原文是「不是靠 `RENDER_AVAILABLE` 一个开关混在一起」——而这件事 **#148 已经达成了**：它引入了 `canRenderPhotoreal()` 和独立的 `photoreal` 参数，`RENDER_AVAILABLE` 和 `photoreal` 现在就是两个各说各事的布尔量。剩下的把 30 行函数拆成两个具名半截，是纯粹的结构装饰。
  同理开发范围第 3 条「只有 L1 时不转圈」也**已经在 #148 里发货了**——`git log -S photorealPending -- apps/web/src/chat.ts` 只返回 `f2e7eb6`（#148），也就是本 PR 的 merge-base。
  **更诚实的做法是改口径**：把第 1、3 条标成「已由 #148 达成」，让 T1.2.1 的交付物就是**验收用例 + 准确的文档**。这样 `tasks.md` 记的是真发生的事。
  ⚠️ 如果就这么合了，T1.2.1 以后会翻成 `DONE` 并把 #149 写进「证据」，为一次**没发生的抽取**背书。要么现在改口径，要么现在做抽取——拖下去这个漂移就固化了。

### 驳回

- **R1a「`mockAll` 可能没有 track `/render-finishes`，`calls()` 的 0 可能是空断言」** —— 实测证伪：`mockAll:29-33` 确实 `page.route('**/render-finishes')`、把 URL push 进 `renderCalls`、并 fulfill 503。`calls()` 不是空的。
- **「`tasks.md` 把 T1.2.1 标成 DONE 会过度声称」（我自己的初步担心）** —— 不成立，diff 是 `BACKLOG` → `PR_OPEN`。台账本身是诚实的，虚假声称只在代码注释和 PR body 里。
- **「本分支相对 preview 显示删了 `knowledge.ts` / `packages/extract/eval` / `ci-covers-check.test.ts`」** —— 那是分支落后于 preview 造成的假象，不是 PR 内容，且当前无冲突。不算发现。

### 一句总结

**卡的是那句声称，不是那个重构。** 三处编辑就能合：(i) 注释改成描述真实存在的两个分节；(ii) 把悬空的 `@param photoreal` 折进同一个块；(iii) 改 PR body 的「## 现在」。可选：按上面把开发范围第 1、3 条改口径。

**别让注释的问题连累掉那条用例**——它是这个 PR 里最有价值的东西，我建议原样保留。

### Assumptions

- 在两个独立 worktree（`origin/preview` 与 `d9b7bb95`）里读代码、跑 `render-gate.test.ts`、静态推变异，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- **没有跑 Playwright** —— 这台机器上 5173/5174 的服务器来路不明（#148 首轮我查出 5174 是另一个 checkout 在跑）。e2e 的判别力是**静态**推的：我逐个追了所有会加/删 `loading` 类的位置，并区分了哪条断言抓哪个变异。
- `compress_diff` 丢了 7 个文件，**全是 `.png` 截图**，评审覆盖无损失。
- 每条 finding 都标了它是「本 PR 引入」还是「既有」；验收项 3 我用 `git log -S` 确认是 #148 带进来的，没算到这个 PR 头上。
- **R3(Codex PK) 未跑、R4 未跑** —— 两条阻断项都有我自己的 grep / `sed` 直接输出。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `d9b7bb95`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；1 条实测证伪）→ Sonnet 机械验证（`git diff` 滤注释确认 chat.ts 零行为改动、
全仓 grep 确认 `renderL1`/`renderL2` 只在注释里、读全路径确认验收项行为成立、`git log -S` 定位验收项 3
的真实来源、静态推三个变异的判别力）→ Opus R2（独立评审，对两个基准重新推导确认「只有注释」这一结论
对活的 preview 也成立、挖出叠加 JSDoc 导致 `@param` 悬空、论证 T1.2.1 的目标已由 #148 达成因而应
改口径而非强做抽取、并逐处追证两条断言的变异集不相交）→ **Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 唯一一条 finding 实测证伪（`mockAll` 确实 route 了 `render-finishes`），但它**问对了问题类型**——「这个断言会不会空转」正是评审这类 e2e 该问的，只是它没往下读 12 行去看 `mockAll` 的实现。它完全没注意到本 PR 的 `chat.ts` 是零行为改动，也没注意到注释声称了两个不存在的函数——而后者只需要一次 grep。
- **下次怎么榨出更多信号**：这类 PR 的核心风险是「声称与实际不符」。下次在 prompt 里加一条硬要求：「列出 diff 里出现的每一个函数名/标识符，逐个标注它在本仓库中是否真实存在（存在/仅出现在注释里/不存在）」。这是纯 grep 比对，flash 做得可靠；本轮的阻断项 1 单靠这一条就能自己抓出来。
