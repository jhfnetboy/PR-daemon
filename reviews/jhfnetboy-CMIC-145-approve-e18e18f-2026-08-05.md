## Verdict: APPROVE（增量复审，head `e18e18f1`，round 6）—— **假绿全清，而且没有换回假红**

上一轮我拦的是「循环反转」：8 条假红修好了，换来 15 条假绿，全落在 A4 这条唯一 100% 硬闸上。**这一轮把假绿清干净了，而且方向没有再翻回去。**

新旧两版对跑：

| 上轮的 15 条假绿 | 现在 |
|---|---|
| `months` 从无上下文臂被删（8 条：`It will take 3 months.` / `Production takes 3 months.` / `We need 4 months for this run.` / `Mass production window is 3 months from PO.` / `Bulk order timeline: 3 months.` / `Ships in 3 months.` / `It ships in 3 months.` / `Shipment is 3 months out.`） | ✅ **8/8 全拦** |
| 小数月（`Delivery in 2.5 months.`） | ✅ **2/2 全拦** |
| 中文行业交期词（`大货三个月。` / `打样一周，大货三十天。` / `生产周期三个月。` / `要三十天左右。`） | ✅ **4/4 全拦** |
| 句末价格（`大概三块五。` / `一个盒子三块。`） | ✅ **2/2 全拦** |

上轮四条 Med 也全修：

- `minimum` 臂的 `\b`-vs-CJK 死分支 → `minimum 500 个` / `minimum 500 个。` / `The minimum is 500 box.` / `The minimum run is 500.` **4/4 从逃逸变拦截**
- CJK 句末符：`Delivery is TBD。 We did 5 days of testing on the coating.` **从误红变放行**
- A6 的 `ADVICE_STRONG` 语序旁路：`你推荐哪个盒型？` / `推荐哪个盒型？` / `最适合你的是哪个盒型？` / `更适合你的是哪种？` / `先按什么方向走，你说？` **5/5 从放绿变抓到**（连同原本就抓到的那条，现在 6/6）
- 裸数量下限：新加了一臂，`最少 500 个` / `至少 500 个。` / `500 个以上才做。` / `We start at 500 pieces.` **4/6 从逃逸变拦截**

**关键是这次没有把假红换回来。** 我按类展开跑了一遍（不是回放上轮的具体字符串——那是我上一轮自己踩的坑）：

```
规格/材质/工艺 12/12 放行   300g coated board · 350gsm kraft · 4-color offset · 2mm thickness
                            A4 size · 5cm window · 1.5mm rigid board · Pantone 185C · FSC 100% …
数量不是 MOQ    切成三块 · 裁成四块 · 分成三块 · 三块板 · 500 pcs per carton  全放行
上上轮那 8 条假红                                                            8/8 仍放行
真价格 8/8 · 真 MOQ 7/7 · 真交期 9/9                                          全部拦住
```

`golden.json` 从 66 涨到 100+ 条，**全绿**，而且新加的用例带反向保护（`a4-anniversary-not-leadtime`：「10 周年」不是交期、`a4-kuai-as-quantifier`：「块」是量词）——把两个方向都钉住了，不只钉修好的那一侧。

**CI 守卫也真收了。** 我把上轮报的绕过手法逐个重跑：

```
✅ 抓住  viaCheck 一行注释毒化（删掉一步 + `run: pnpm -v # remember: pnpm check covers this`）
✅ 抓住  if: false + 行尾注释      ✅ 抓住  continue-on-error: true + 注释
✅ 抓住  if: 'false' 带引号        ✅ 抓住  run: pnpm regress || true
❌ 混过  if: github.event_name == 'never'
```
上轮那条 **High（一行注释关掉整个守卫）已经关掉了**，8 种手法里 7 种被抓。

### 非阻塞

- **[Low] `if:` 里的恒假【表达式】仍能混过去**（`if: github.event_name == 'never'`）。字面量 `false`、带引号的 `'false'`、`${{ false }}` 都抓得住，剩下的是「写一个永远不成立的表达式」——这需要刻意为之，不再是救火时顺手写的形状。彻底解法是：对**满足某条覆盖断言的步骤**，任何 `if:` 都要求出现在一张白名单里（而不是去枚举哪些表达式是假的）。
- **[Med] 三条误红，两版皆有、非本轮引入**：
  ```
  红 ❌ [lead-time]  "5 weeks ago" / "3 weeks ago" / "5 days ago"     ← 过去时间不是交期
  红 ❌ [lead-time]  "open 7 days a week" / "7 days a week"           ← 营业时间不是交期
  红 ❌ [price]      "12 per box" / "6 per box"                       ← 而 "12 per carton" 放行
  ```
  最后一条最刺眼：`per box` 打红而 `per carton` 放行，同一个意思两种判定。`ago` / `a week` 加进否定前瞻，`per box` 与 `per carton` 取同一口径即可。
- **[Low] 裸数量下限还剩两条逃逸**（两版皆有）：`一次要订 500 个。` / `Min order quantity is 1000`。新加的那一臂覆盖了最常见的四种，这两种可以下一轮补。

### 驳回

- **R1a「`(?<!分成)` 只排除了 4 个动词，带空格或其它动词的变体可能漏」** —— 实测 `分成三块` / `切成三块` / `裁成四块` 全部正确放行，`大概三块五。` / `一个盒子三块。` 正确拦截。它举的三个「变体」是同一个字符串。
- **R1a「`min\.?\s*(?:order\s*)?(?:qty|quantity)` 漏掉单独的 `min order`」** —— 实测 `Minimum order 500 pieces` 拦得住；`Min order quantity is 1000` 确实逃逸，但原因不是它说的这条正则，已按实测列在上面的 Low 里。
- **R1a「`(?=[.。!！?？]|$)` 要求句末，`minimum 500 pieces needed` 会漏」** —— 实测 `We start at 500 pieces.` 拦得住；这条前瞻是**故意**的（避免 `minimum 500 pieces per carton` 这类量词语境误红），属设计口径不是缺陷。

### 一条方法上的肯定

这一轮和上一轮的差别，不在于「又修了几条」，而在于**修法从「删掉/收窄那一臂」变成了「加一条精准的排除项」**——`months` 回到了无上下文臂而排除项挂在后面、中文交期不再靠关键词白名单、句末价格分支恢复并改用动词否定后顾。而且 `golden.json` 这次同时钉了**两个方向**（该拦的和该放的），所以下一次改动如果再往任一方向过冲，套件会自己红。

上轮我说「A4 需要一次 normalize-then-classify，不是第 23 条臂」——这仍然是长期方向，但按目前的钉住程度，这个 PR 已经不该再拦着了。

### Assumptions

- 在两个独立 worktree（`0900faa2` 与 `e18e18f1`）里对跑，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；`ci.yml` 的 8 次攻击实验都在 worktree 内做并已还原，`git status` 干净。
- **本轮我按类而不是按字符串验回归**（上一轮我只回放具体字符串、漏了 15 条同类，这是那次的教训）：语料按「价格/MOQ/交期 × 中英 × 关键词在前/在后/无关键词 × 规格-材质-工艺-时间-数量五类干扰项」展开。
- 每条 finding 都标了 REGRESSION / PRE-EXISTING；三条误红经两版对跑确认**非本轮引入**。
- 本 PR 对 `preview` 冲突。注意 **#145 分支的 `check` 串里没有 `pnpm test:gate`**（它在 #144 合入前开的分支）——`#142` 已经用「合一次 preview」解决了同样的问题，建议照做，否则合并时一次 take-theirs 会把唯一护着 GPU 花费的断言静默删掉。
- **R3(Codex PK) 未跑、R4 未跑** —— 本轮是 APPROVE，结论有我自己在新旧两版实跑的矩阵语料、golden 套件与 8 次 CI 攻击实验。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `0900faa2`→`e18e18f1`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；3 条实测均证伪，其中一条把同一个字符串举成三个变体）→ Sonnet 机械验证
（新旧两 worktree 按类展开对跑确认 15 条假绿全清且 8 条假红未复发、golden 100+ 条全绿含反向保护用例、
8 种 CI 禁用手法逐个实跑确认 viaCheck 毒化已关闭）→ **Opus R2 未跑（本轮无待判定的争议项，
15 条假绿的修复我用两版对跑自己就能证）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：1/5。** 三条全部实测证伪。第一条把 `分成三块` 一个字符串写成「三个变体」（`分成三块` 变体如带空格的 `分成三块` 或其它动词的 `分成三块`）——这是复读，不是分析。第三条把一个**故意的**设计口径（句末前瞻避免量词语境误红）当成缺陷。它对着一个刚清掉 15 条假绿的 diff，一条真实的行为变化都没碰。
- **下次怎么榨出更多信号**：这个文件每一轮的评审结论都写在 `golden.json` 的用例名和注释里（`a4-anniversary-not-leadtime` / `a4-kuai-as-quantifier` 这种）。下次把 **golden.json 的用例名清单**连同 diff 一起喂进去，要求「先说明这次改动可能破坏哪几条既有用例，再给 findings」——它会被迫先建立「这个文件已经踩过哪些坑」的上下文，而不是从零开始猜正则。
