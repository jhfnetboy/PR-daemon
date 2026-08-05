## Verdict: APPROVE（增量复审，head `3d7860ce`，round 2）—— **两条都修了，而且抽取真做了**

上一轮我拦的是**那句声称**，明说不要求做抽取。这轮你把两件事都办了：

| round-1 的问题 | 现在 |
|---|---|
| 注释声称 `renderL1()` / `renderL2()` 存在，而它们不存在 | ✅ **它们现在是真函数**：`:324 function renderL1(...)`、`:353 function renderL2(...)`，调用点 `:310-311` |
| 叠了两个 `/** */` 块，`@param photoreal` 悬空 | ✅ **合并成一个块**，`@param photoreal` 在里面，绑定到 `showBoxDirections` |
| `tasks.md` 开发范围第 1、3 条与实际不符 | ✅ 后两条划掉并标注「**已由 #148 达成**」，还附了我给的证据（`git log -S photorealPending` 只返回 `f2e7eb6`） |

而且注释现在**归因是准的**：「#148 把判定拆了出来（`canRenderPhotoreal()` + 独立的 `photoreal` 参数）；本函数把【执行】也拆成两个具名的半截，这样「L2 是什么」有一个可以 grep 的名字」。

**行为等价我逐处核过**：
```
拆前:  thumbMap = addCards(specs, photoreal);
       if (RENDER_AVAILABLE && photoreal) { …四个 batch… }
拆后:  const thumbMap = renderL1(d, q, photoreal);      ← 调用点判 photoreal
       if (photoreal) renderL2(d, thumbMap);
       function renderL2(...) { if (!RENDER_AVAILABLE) return; …四个 batch… }
```
`RENDER_AVAILABLE && photoreal` 这个合取原样保留，只是拆到了调用点和函数头两处。CI 两个 check 全绿。

**作用域没有回归**：`thumbMap` 在 `preview` 上**本来就是 `showBoxDirections` 的函数内局部变量**（`preview:304 let thumbMap`），不是模块级，所以拆成参数传递是安全的；`thumbSrc` 闭包仍留在 `renderL1` 内、和它捕获的 `specs` 同一作用域。顺带一个**净改善**：`renderL2` 里原来的 `thumbMap!` 非空断言（两处）现在是有类型的参数 `thumbMap: Map<string, HTMLElement>`。

上一轮我说要保留的那条 `L1 always renders` 用例**还在**。

**最值得说的一处**：`renderL2` 的 JSDoc 主动写了
> ⚠️ 如实记账:这一条【不是承重的守卫】—— `renderFinishes` 自己在 render.ts:267 就会抛。它只是提前返回…变异测试证明删掉它不会让任何用例变红…**别把它当成一道闸**。

这是**主动标注一个守卫其实不承重**，而且给了变异证据。上一轮的问题正好是反过来的（声称了一个不存在的东西）——这轮这条注释是同一个诚实度量表的另一端。

### 非阻塞

- **[Low] `renderL1` 内仍是 `let thumbMap: Map<...> | undefined` 然后 `thumbMap = addCards(...); return thumbMap;`。** 这是从原代码搬过来的形状，类型上没问题（`addCards` 返回非可选，赋值后 TS 会收窄），但既然现在是个独立函数、`thumbSrc` 闭包又必须在赋值前就捕获它，留个一行注释说明「为什么必须先声明再赋值」会省掉下一个人的困惑。
- **[Low]** `renderL2` 的注释说 e2e 跑在配了 `VITE_API_URL` 的实例上因而 `RENDER_AVAILABLE` 恒真——这个前提依赖 `playwright.config.ts` 里 5174 那条 `reuseExistingServer: false`（#148 加的）。两者是绑定的，值得在其中一处互相引一句。

### 驳回

- **R1a「`renderL1` 返回类型 `Map<string, HTMLElement>` 但 `thumbMap` 可能是 `undefined`，应改成可选返回」** —— 不成立。`addCards` 的返回类型是非可选的 `Map<string, HTMLElement>`，赋值之后 TS 就把 `thumbMap` 收窄了，`return thumbMap` 类型检查通过。而且 CI 的 `pnpm -r build`（含 `tsc`）**是绿的**——这条如果成立，构建会红。R1a 把同一条 finding 输出了两遍（一条 Medium 一条 Low，指向同一行）。
  ⚠️ 我自己没能在 worktree 里跑 `tsc`（没装 `node_modules`），所以这条我是靠 CI 的构建结果 + 类型收窄推理确认的，不是本地实跑，如实说明。

### Assumptions

- 在两个独立 worktree（`origin/preview` 与 `3d7860ce`）里读代码、逐处比对拆分前后的守卫合取，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- 增量里含一个 `Merge origin/preview`，我只审了 `3d7860c` 这一个真实改动 commit（`git diff 28afe57..3d7860ce`，2 个文件 +64/-42）——merge 带进来的 #145/#146/#150 的代码各自已经评审并 APPROVE 过，不构成新审查面。
- **没有跑 Playwright**（这台机器上 5173/5174 服务器来路不明）；**没有跑 `tsc`**（worktree 无 `node_modules`），类型结论依赖 CI 绿 + 收窄推理，已在驳回条目里标明。
- **R2/R3/R4 未跑** —— 两条阻断项的修复是可直接 grep / `sed` 证实的事实，无待判定的争议项。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `d9b7bb95`→`3d7860ce`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；1 条重复输出两遍且被 CI 构建证伪）→ Sonnet 机械验证（grep 确认 `renderL1`/
`renderL2` 现为真函数、`sed` 确认 JSDoc 合并且 `@param` 已绑定、逐处比对拆分前后守卫合取等价、
对 preview 核实 `thumbMap` 本就是函数内局部变量因而无作用域回归、确认 `tasks.md` 已按建议改口径、
确认那条 e2e 用例保留）→ **Opus R2 未跑（无争议项）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：1/5。** 唯一一条 finding 被 CI 的构建结果直接证伪（如果 `renderL1` 的返回类型真有问题，`pnpm -r build` 会红，而它是绿的），而且**同一条被输出了两遍**、只是severity 标签不同（Medium + Low 指向同一行 `:349`）——这是格式缺陷，不是两个发现。它完全没注意到本轮真正值得看的东西：抽取有没有改变 `RENDER_AVAILABLE && photoreal` 这个合取、`thumbMap` 的作用域有没有变。
- **下次怎么榨出更多信号**：这是一次**纯重构**（行为应等价），最该问的是「拆分前后哪些条件被移动了、合取/析取关系有没有变」。下次对含函数抽取的 diff，在 prompt 里写死：「列出被移动的每一个条件判断，标明它在拆分前后分别处于哪个函数、与哪些条件组合，并判断组合语义是否等价」。这是结构比对，flash 有机会做对；靠它自己想到该比对合取关系目前做不到。
