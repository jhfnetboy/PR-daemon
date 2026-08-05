## Verdict: APPROVE（增量复审，head `e7cbbda9`，round 3）—— **阻断项按我说的修了，但我的药方开漏了一半，我先说这个**

上一轮我拦的是「CTA 没继承在途闸」，并写了「把 `#cta-render` 纳入 `setDockBusy` + 开头 `if (followUpBusy) return`」，还说**「这一条同时解决上面三点」**。

**那句话是错的。这个修法解决了 ① 和 ③，没有解决 ②。** 下面单开一节说，先记清楚该修的都修了：

| 上一轮的问题 | 现在 |
|---|---|
| 阻断项：CTA 不受在途闸约束 | ✅ `setDockBusy` 里加了 `if (cta) cta.disabled = busy`，`onCtaRender` 开头 `if (followUpBusy) return`。**e2e `:187` 那条用例还特意绕过 `disabled` 直接 `c.click()`，断言零付费请求** —— 两道闸各测各的，不是只测 UI 那层 |
| `??=` 写回不修复被拒绝的值 | ✅ 改成**四行无条件赋值**（`brief.product = r.product` …），正是我建议的那个更短也更正确的写法 |
| `restoreThread` 不恢复 `customerTurns` | ✅ 新增 `restoreTurns()`，`history.filter(m => m.role === 'user').length`，`:968` 在 `restoreThread` 里调用，e2e `:239` 钉住 |
| 两个默认尺寸不一致（`{100,100,80}` vs `{200,150,60}`） | ✅ 抽成 `FALLBACK_SIZE` 从 `knowledge.ts` 导出，`dims()` 和 `DEFAULT_PROFILE` 共用同一份 |
| `onCtaRender` 不往 `history` 推明示 | ✅ `history.push({ role:'assistant', content: said })` |
| 测试盲区：所有 mock 都是 `brief_patch: {}` | ✅ 新增 `:156` 那条**专门喂 `{boxType:'tuck-end', size:{l:100,w:100}}`**（都是 refused 那一类），断言「明示说换了什么，brief 里就得真是什么」——正是我说该补的那条 |

CI 两个 check 全绿；三方合并**无冲突**，而且我核过分支**没有动 `08-render-gate.spec.ts`**，所以合并不会丢掉 preview 上 #149 加的那 24 行。

---

### 我上一轮开漏的那一半（**不拦**，但要记进 follow-up）

闸是按 **`/chat` 在途**开合的：`enterThread` / `followUp` 在 `finally` 里释放 `followUpBusy`，而那时 `showBoxDirections` 只是**返回**了——里面的 `void renderFinishes(...)` 是 fire-and-forget，付费批次还要跑几十秒。

于是**渲染在途这个窗口没有被盖住**：

```
turn 完成 → followUpBusy=false、CTA 重新可点 → 但 inflightFinishes 里 4 个 key 还在
客户等了十几秒以为没反应 → 点 CTA
  → addCards(specs, true) 给【新的】4 张卡挂上 loading
  → for 循环里 inflightFinishes.has(bkey) 全部命中 → continue ×4，一个请求都不发
  → 而 .then/.catch/.finally 三个回调闭包捕获的是【第一次调用的】thumbMap
  → 没有任何东西会来摘第二组的 loading
```

这正是我上一轮描述的后果 ②，也正是 R2 说的「真实用户最可能碰到的那种，处理得最差」。

**但我把它降级为非阻断，理由是我实测了它的实际视觉后果，比我上轮描述的轻**：
- `addCards` 的 `.then` 仍然会把 WebGL 缩略图写进去（`:20`），所以第二组**不是四个空白转圈**，是**四张有图的卡**；
- 卡住的是 `.thumb.loading::after` 那条角标 —— `content: "✨ Generating preview…"` 的脉冲字条，会一直显示；
- **不烧钱**（`continue` 掉了，零付费请求）、**不丢数据**、页面其余部分正常。

所以它是「四张卡角上挂着一条永远不消失的『生成中』」，不是页面死掉。**是缺陷，但不到拦第三轮的程度**——尤其考虑到它是我上一轮**明确说过会被这个修法解决**的东西，作者是照着我的话做的。

**修法（留给 follow-up，两条任选）**：
1. 闸的窗口延到渲染结束：`showBoxDirections` 返回一个 `Promise.allSettled(batches)`，`finally` 等它；或者单独维护一个 `renderBusy`，`inflightFinishes` 非空即为真，`setDockBusy` 一并看它。
2. 或者让 `continue` 那一支**自己收尾**：命中在途 key 时，把这一组对应的 `thumbBox` 也登记进第一次调用的回调将要更新的映射里（或直接 `thumbBox.classList.remove('loading')`），别让它挂着。

我建议 1 —— 它同时消除了「点了没反应」这个体感本身，而不只是收拾它的残留。

### 其余非阻塞（都还开着，都不急）

- **[Low] `chat.ts:625-626` 的 `confirmedDirection` / `awaitingAnswer` 在这条路上读不到**（`explicitAction` 先短路）。加一句注释即可。
- **[Low] 分支落后 `preview` 3 个 commit**（#149 / #152 / #153）。无冲突，但 #149 已经把 `showBoxDirections` 拆成了 `renderL1` / `renderL2`，合并后上面那条 follow-up 会落在 `renderL2` 里——先 merge 一次 preview 再动它更省事。

### 驳回

- **R1a「`onCtaRender`（`:622`）引用了声明在 `:667` 的 `followUpBusy`，要确认提升行为」** —— 不成立。函数声明会提升，但**函数体只在调用时执行**；唯一的调用点是 `:819` 的 `$('cta-render').onclick = onCtaRender`，那时 `:667` 早已执行完。模块顶层代码按序执行，客户的点击只可能发生在模块跑完之后，不存在 TDZ 窗口。

### Assumptions

- 在两个独立 worktree（`2de0925c` 与 `e7cbbda9`）里读代码、追时序、核对 CSS 与 `addCards` 的 `.then` 分支，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- **没有跑 Playwright**（这台机器上 5173/5174 服务器来路不明）；上面那个「渲染在途」的时序是**静态**追的，我逐处给了依据（`finally` 的位置、`void renderFinishes` 的 fire-and-forget、`continue` 分支无收尾、回调闭包捕获的是第一次的 `thumbMap`）。
- **合并安全性实查**：`git diff --name-only <base> <head>` 确认分支未触碰 `08-render-gate.spec.ts`，`git merge-tree` 无冲突标记，GitHub 报 MERGEABLE/CLEAN。
- **R2/R3/R4 未跑** —— 本轮是 APPROVE，且核心结论是我自己上一轮的药方开漏了，判断依据都是我自己实跑/实追的。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `2de0925c`→`e7cbbda9`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；1 条 TDZ 质疑不成立）→ Sonnet 机械验证（逐条核对上一轮 6 项的修复、
追 `followUpBusy` 释放时机与 `void renderFinishes` 的 fire-and-forget 时序、读 CSS 与 `addCards`
的 `.then` 分支给「卡住的转圈」精确定级、`git diff --name-only` + `git merge-tree` 确认合并不丢
#149 的用例）→ **Opus R2 未跑（本轮无争议项，核心结论是我自己上轮的疏漏）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 唯一一条 finding（`followUpBusy` 声明在后、担心提升）**指对了一个真实的代码事实**——变量确实声明在函数之后——但没往下追一步看唯一调用点在 `:819`，那时声明早已执行。这是它这几轮的固定形态：能看见事实，判不了可达性。
- **本轮更该记的是我自己的问题**：我上一轮写「这一条同时解决上面三点」，而那个修法只盖了 `/chat` 在途、没盖渲染在途——**后果 ② 是我自己列的，也是我自己漏掉的**。教训是：**给修法的时候要把它的作用窗口和每一条后果的发生窗口逐条对齐**，别因为三条后果同源就默认一个闸能全收。下次给修法前，我会把「这个闸从什么时候开、到什么时候关」和「每条后果发生在哪个时刻」并排列一次。
