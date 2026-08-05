## Verdict: APPROVE（首轮，head `f37559c4`）—— **正是我上一轮填的那条 follow-up，而且选了我建议的那个方案**

上一轮我在 #151 里如实说了：我给的修法只盖住了 `/chat` 在途，没盖住渲染在途那几十秒，于是「第二组卡片饿死」仍可达。这个 PR 把窗口补上了：

```js
function syncCtaEnabled(): void {
  const cta = document.getElementById('cta-render') as HTMLButtonElement | null;
  if (cta) cta.disabled = followUpBusy || inflightFinishes.size > 0;
}
```
`onCtaRender` 的早退同步收宽成 `if (followUpBusy || inflightFinishes.size > 0) return;`，`syncCtaEnabled()` 在**入队时**（`:384`）和**两处 `.finally`**（`:395` / `:442`）都调用了——加和减两侧都盖住。

### 我重点查了三个「闸会不会永久卡死」的点，都没问题

| 风险 | 实测 |
|---|---|
| `renderFinishes` 同步抛 → `.finally` 挂不上 → key 永久留存 | ✅ 它是 `async function`，`:267` 的 `throw` 也变成 rejected promise，`.finally` 照常触发 |
| 轮询无上界 → promise 永不 settle → CTA 永久变灰 | ✅ **有上界**：`render.ts` 的两层轮询分别是 `i < 60`（~5 分钟）和 `i < 120`（~10 分钟），最坏情况也会 settle |
| 失败路径漏掉解锁 | ✅ 解锁在 `.finally` 里，`.catch` 之后，两条路都走得到 |

### e2e 钉得很准

- `:296` 渲染在途时 CTA **必须灰**（错误信息直接写「第二组卡片会饿死」）
- `:310` 渲染结束后 CTA **必须放开**
- `:295` **`dock-input` 不跟着延** —— 「渲染时客户仍能说话」。**这条最值得表扬**：它把「闸加宽」限定在 CTA 这一个控件上，而不是顺手把整个 dock 一起锁住。加宽一道闸最容易犯的错就是顺手多锁一点，这条断言把它挡住了。
- 用 `renderGate` 这个受控 promise 卡住 `**/render-finishes` 来制造窗口，比等真实时序稳。

### 非阻塞

- **[Low] `inflightFinishes` 是 `dir:` 和 `var:` 两类 key 共用的**（`:381` / `:430`），所以客户点 **Vary** 触发的付费渲染也会让 CTA 变灰。口径上说得通（任何付费渲染在途都不该再开一批），但它比这条 PR 声称的范围宽一点，值得在 `syncCtaEnabled` 上补一句注释说明这是有意的——否则下一个人可能会以为是 bug 而去拆开。
- **[Low] 最坏情况下 CTA 会灰约 10 分钟**（后端一直不返回、轮询走满 120 次）。有界、且那段时间渲染确实在途，可以接受；但如果以后想优化体感，给按钮加一句「出图中…」比单纯置灰更清楚——现在客户只看到它灰了，不知道要等什么。

### 驳回

- **R1a「在循环里先调 `syncCtaEnabled()` 可能在渲染其实已完成时短暂置灰，靠 `finally` 纠正」** —— 顺序是先 `inflightFinishes.add(bkey)` 再 `syncCtaEnabled()`，此刻这个 batch **确实**在途，置灰是正确状态不是瞬时错误；而 `.finally` 是在真正结束时才解锁。不存在它说的那个抖动窗口。

### Assumptions

- 在两个独立 worktree（`origin/preview` 与 `f37559c4`）里读代码、追 `inflightFinishes` 的加减两侧与 `renderFinishes` 的轮询上界，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- **没有跑 Playwright**（这台机器上 5173/5174 服务器来路不明）；e2e 的判别力是**静态**读的，我逐条对照了断言与它要防的那个失败模式。
- **R2/R3/R4 未跑** —— 单一职责的闸窗口加宽，无争议项，三个「永久卡死」风险点都有我自己的代码追证。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `f37559c4`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；1 条抖动质疑,追序后不成立）→ Sonnet 机械验证（`syncCtaEnabled` 的加减两侧
调用点、`renderFinishes` 的 async 性质与两层轮询上界、`.catch`/`.finally` 的解锁覆盖、
e2e 三条断言与失败模式的逐条对照）→ **Opus R2 未跑（单一职责，无争议项）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 它的 SKELETON 判断准确（「correctly widens the CTA gate… addressing the second card starvation issue」），唯一那条 finding 虽然不成立，但**问的是对的问题**——「先置灰再等 promise 会不会有瞬时错误状态」正是审查这类状态同步该问的。只是它没去看 `add` 和 `syncCtaEnabled` 的先后。
- **下次怎么榨出更多信号**：这类「加宽一道闸」的 diff，最该问的是**闸会不会卡死**。下次在 prompt 里写死：「对新的解锁条件，列出所有能让它永远不满足的路径（异常、超时、提前 return、promise 永不 settle），并逐个说明是否有兜底」。这是可枚举的路径追踪，flash 有机会做对——本轮三个风险点里有两个（同步抛、轮询上界）它只要顺着 `renderFinishes` 读 10 行就能自己排除。
