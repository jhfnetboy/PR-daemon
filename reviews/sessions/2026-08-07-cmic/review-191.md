## ✅ APPROVE — 修得对，而且根因比「字段放错层级」更深一层；三条跟进项都不该卡这个 PR

4-round（DeepSeek R1a/R1b → Opus R2 独立读 → Codex R3 对抗 → Opus R4 终裁）。

### 我实跑验的

**契约断言 + 变异，静态复跑了一遍**（没有 node_modules，所以我把系统提示词从 `chat.ts` 里原样抽出来，用真串跑那三条断言的字符串逻辑）：

| | HEAD | 变异 R1（把 `- render_intent: set TRUE …` 那行原样塞回 `brief_patch` 清单 = 生产 bug 逐字复现） |
|---|---|---|
| ②b-1 模板里有 `"render_intent": boolean` | ✅ | ✅ |
| ②b-2 明说 `TOP-LEVEL field, NOT part of brief_patch` | ✅ | ✅ |
| ②b-3 `brief_patch` 段里没有它 | ✅ | **❌ 变红** |

**变异承重，且只红一条** —— 另外两条不跟着倒，说明三条断言分工干净、没有互相顶替。变异用的是字面替换 + `assert old in s` 命中检查，不是正则（正则会匹配到别的位置然后给你一个虚假的安心）。

另外核过：`sanitizePatch`（`:605+`）是逐字段白名单、正确地不含 `render_intent`；R2 把提示词里每个字段都和白名单对了一遍，**没有第二处同形状的 prompt↔白名单错配**。`bp` 的取值对 array / null / string / number 都不破（`typeof [] === 'object'` 但 `.render_intent` 是 undefined），两条分支上 `=== true` 的纪律都守住了。

### 授权面没有变宽 —— 只是触发面

`explicitAction` 依然不传，花钱仍然走 `photorealVerdict` / `canRenderPhotoreal`（`chat.ts:1204-1212` 那段注释写得很清楚：「`render_intent` 只能触发，不能授权」）。所以这个兜底是**频率**问题，不是**授权**问题。这一点我确认过再下的结论。

---

### 三条跟进项 —— 都不阻塞，理由写在下面

**FU-A [Medium] 这个 PR 让 `apps/web/src/chat.ts:1213` 的 `if (wantRender)` 块第一次真正活起来，而它没有任何次数上限。**

base 版 `chat.ts:995` 只读顶层，而说明在 `:524` 的 `brief_patch` 清单里 —— 这个 flag **永远不可能为 true**，所以那个块此前是死代码。现在它活了：

- 唯一的守卫是 `if (inflightFinishes.size > 0)`，挡的是**并发**的第二批，不是**串行**的下一批；上一批落地后 `inflightFinishes` 清空，下一个 `render_intent:true` 的回合再发 4 个。
- 去重键 `dir:${type}:${l}x${w}x${h}`（`:581`）只在途去重，**没有已完成渲染的缓存**。
- `renderL2`（`:578`）遍历 `BOX_TYPES` —— `funnel.ts:37-42` 正好 **4** 个。
- 服务端配额（`index.ts:851-862`）：10 分钟固定窗口 20 次（所有分桶），`role==='customer'` 再加 30/天。

→ **10 分钟内约 5 次模型自发触发就 429；约 7 次烧掉客户一整天。** Codex 核过 `photorealVerdict` 是纯当前状态、渲完不会翻（`render-gate.ts:337-354`），所以它不构成限流。放大器：系统提示词 `chat.ts:495` 本身就在教模型说「want me to show you something in that direction?」。

**但我认真试着推翻了这条，反例成立，所以不阻塞：**

1. 无上限**不是这个 PR 的设计**。`onCtaRender`（`:1026`）—— 已上线的、主要的、用户点的那个触发点 —— 守卫**一模一样**：`if (followUpBusy || inflightFinishes.size > 0) return;`，同样无上限、无冷却、无完成缓存。`enterThread`（`:1138`）第一轮也是无条件发一批。这个 PR 是给一栋本来就有两扇无锁门的房子加了第三扇。
2. **这个 diff 一行 `apps/web/src/` 都没碰**（2 个文件，都在 `apps/api/src/`）。要求在这里补限流 = 要求在另一个 app、在本 diff 不触碰的代码里，修一个上一个 PR 引入的设计缺陷。
3. 卡住它并不降低风险 —— 只是让一个**客户已经报障、100% 失效**的功能继续失效。

**最锋利的形式（三轮都没点出来，R4 挖到的）**：`chat.ts:1256-1260` 有一条白纸黑字的产品决策 ——「改色/换 logo 一律**只重渲免费的 WebGL 缩略图，绝不自动触发照片级**：客户会连点五个颜色找感觉，自动重渲就是五次 GPU」，照片级交给 T2.1.3 的漂移标记 + 手动重出。换色处理器（`:1488`）老老实实遵守了。但 `render_intent` 一旦生效，客户下一句话就能让模型说「我给你看看藏青的」→ 每个颜色 4 批照片级 —— **绕过了这条决策本身**。建议跟进项直接引用这两行，别只写「加个上限」。

**FU-B [Low-Medium] 兜底那条分支的松紧没人守。** 这个文件自己写着存在理由是「别让这个开关变松」，但 `truthyTraps`（`:44-51`）和 `falsy`（`:52-56`）两张表都只走 `intentOf()`，而它把值放在**顶层**（`:26`，`brief_patch: {}`）。新加的第二个读取点 `bp.render_intent` 只有 ②c 一条、只喂字面 `true`。把 `bp.render_intent === true` 改成 `!!bp.render_intent`，**全文件断言照样全绿**。修法约 3 行：给 `intentOf` 加一个位置参数，让那两张表也跑一遍 `brief_patch` 位。

**FU-C [Medium] `:93` 那条断言可能空转变绿 —— 而它正是全组里唯一能抓到生产 bug 的那条。**

```ts
const bpSection = sys.slice(sys.indexOf('capture any concrete fact'), sys.indexOf('CHIPS:'));
```

我按 JS 的 slice 语义原样复跑过：起始锚点哪天被改了措辞 → `indexOf` 返回 -1 → 负数起点被钳到 `len-1`，大于终点 → slice 返回 `''` → `!''.includes('render_intent')` **恒真**。

⚠️ 这和这个 PR 要修的 bug 是**同一个属**：一条绿着但没在测它声称在测的东西的断言。两行就能钉住：切片前先 `ok('锚点还在', a >= 0 && b > a)`。

顺带两条 Low：
- `chat.ts:999` 注释写「顶层优先」，但 `:1007` 是个平凡的 `||` —— 显式的顶层 `render_intent: false` 否决不掉一个跑偏的 `brief_patch.render_intent: true`。在一个自己写着「松一点就等于模型说一声就能花钱」的文件里，文档承诺的优先级没有实现。②c 抓不到（它压根不带顶层字段）。
- api↔路由这一段是唯一没测到的接缝：单测断的是 `r.data.render_intent`，而 e2e（`e2e/tests/26-render-intent.spec.ts:31`）用 `page.route('**/chat', …)` 把整个 `/chat` mock 掉、直接 fulfill 一个顶层 `render_intent` —— **它绕开的正是坏掉的那一层**。这就是为什么 TC-R1..R4 四条在整个生产故障期间全程是绿的。

---

### 写得比我会开的方子更好的地方

一个被告知「这个 flag 恒为 false」的 reviewer，开出来的方子会是「把提示词那行挪到顶层 + 修解析」。作者多做了三件我不会想到的：

1. **找到了更深一层的根因** —— 那个字段**压根没出现在 JSON 输出模板里**，所以模型连「要返回它」都不知道。只挪位置修不好。
2. **兜底防的是模型的习惯，不是模型的服从** —— `|| bp.render_intent === true`。
3. **测试钉的是提示词文本本身**，而不是又写一个 mock 形状的断言 —— 并且报了变异结果。这直接回应了他自己诊断出的病根：「上一版测试全绿，是因为 mock 里我自己把它放在顶层 —— 测试和真实模型收到的是两份不同的契约」。

顺带说一句：这是今晚同形状错误的第五次变体（他自己在 PR 里列了前四次），而**这一次他是在写修复的同时把判据也换掉了** —— 从「验我想象的机制」换成「验真实路径的契约」。FU-C 说明这个转换还差最后一步（锚点本身也是想象出来的稳定），但方向是对的。

<sub>Rounds — R1a/R1b DeepSeek(v4-flash)：R1a 一条 finding，判为假阳性（它说兜底应该把 flag 写进 output patch；实际 flag 走顶层 `data` → `index.ts:780` 的展开 → web `chat.ts:1176`，一路都在。按它的方子改会把一个瞬时信号写进会被每轮 POST 回来的持久 brief，flag 会永久锁死）。R1b 判无安全面，合理。R2 Opus：独立发现 FU-A/B/C 三条。R3 Codex(gpt-5.5)：三条全 CONFIRM，并确认 `photorealVerdict` 渲完不翻。R4 Opus：被要求先证伪最强 finding，**反例成立**（落点在本 diff 未触碰的既有代码），据此判 APPROVE，并挖出 `:1256-1260` 的产品决策冲突和 e2e mock 掉坏掉那层这两条。</sub>
