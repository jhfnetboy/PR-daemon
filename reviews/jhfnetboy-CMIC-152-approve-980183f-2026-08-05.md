## Verdict: APPROVE（首轮，head `980183f7`）—— **sanitizer 扎实，而且你自己把没跑的验收如实写出来了**

### `sanitizeOpenQuestion` 我逐类探过，形状校验 14/14 正确

```
null / undefined / 0 / "" / [] / "str" / {} / {text:1} / {text:""} / {text:"  "}  → 全部 null
{text:'ok'}                        → {"text":"ok","category":"other"}
{text:'ok',category:'BOGUS'}       → category 落回 "other"          ← 白名单外不透传
{text:'ok',category:'  Regulation  '} → "regulation"                ← trim + 折大小写
{text:'ok',category:123}           → "other"
```
类别是**闭合白名单 + `other` 兜底**，没有任何未知值能穿过去。截断 500 我也验了：600 个中文字 → 500；300 个 emoji（600 code unit）→ 500 且**没有切出孤立代理**（500 是偶数，成对字符不会被劈开）。`redact` 在 `slice` **之前**跑，所以占位符不会被截一半——`480 个 x + call 13800138000` 实测输出末尾是完整的 `call [phone] now`。

`chat.test.ts` 28 条通过，其中 9 条断言直接打在 `open_question` 上，含「超长要截断」。

### 新 SYSTEM 不会绕过 #148 的付费闸 —— 这是我最担心的一处，实测过了

新 prompt 给了 AI **「STANDING AUTHORITY to preset any of them… you do NOT need permission first」**。我查了它和出图闸的交界：
```
directionConfirmed 的两个赋值点:  supplementFromText 里的 statedDirection(t)  ·  点盒型 chip
applyPatch(模型给的 brief_patch)  → 对 directionConfirmed 的引用数: 0
端到端: AI 预设四槽、客户没说过盒型 → {"allow":false,"reason":"slots-incomplete"}
        客户真说了盒型             → {"allow":true,"reason":"slots-complete"}
```
**模型自己预设的槽位填得满 `slots`，但填不了「方向已确认」**，所以 #148 那道闸仍然要求客户真说过盒型。这个分层是对的，值得在 prompt 或 `render-gate.ts` 里互相引一句，免得以后有人给 `applyPatch` 加上 `directionConfirmed`。

### 规则重写本身：约束的确实是 AI 自己

第 8 条从「NEVER RUSH」改成「DON'T RUSH THE CUSTOMER — but **don't stall either**… It does NOT mean you may circle the same ground twice」，第 9 条「PACE **YOURSELF**, NOT THEM… never ask about something already recorded in `brief_patch`, and never re-ask a question they declined」。这是**对 AI 行为的约束**，不是让 AI 去催客户——和 Task 标题一致，也和评审当初否掉「第 7 轮 AI 收口」的理由一致（收敛靠界面，见 #151）。

### 我要特别记一笔的：你自己把没跑的验收写出来了

`progress.md` 里那段：
> **T1.5.1 的 live 基线：没有跑** …… 要对比就得先把新 prompt 发上生产 —— 那是一次生产部署，不在这个 Task 的授权范围内 …… 在这之前，本 Task 的 prompt 改动**只有离线保证**：语义约束进了 prompt，但没有实测证明模型照做了。

**这正是我这几轮反复在挑的那件事的反面。** 一个「验收命令没跑、原因、两种补法、以及现在的保证边界」的诚实交代，比一个跑了但量错了的数字有价值得多。而且你连「即使跑了 A4 那一项的数字也不可信」（FU-5 那条：线上 chat.ts 就地改写 reply 之后才返回）都点出来了。

**我的建议是选补法 1（staging worker）**，理由是补法 2 的风险描述本身就说明了问题：「prompt 变差但离线尺子看不出来」——而 #145 建的那把尺子（A1–A6）恰恰是为了度量 prompt 改动的，如果第一次真正的 prompt 改动就绕过它，尺子的价值会打折。不过这是要你拍板的事，不是评审能替你定的。

### 非阻塞

- **[Med] `redactContact` 的缺口现在有了一个更宽的入口（缺口本身是既有的，不是本 PR 引入）。** 两版对跑，两边**完全相同**：
  ```
  ✅ 抹掉  +8613800138000 · 13800138000 · a@b.com · WhatsApp +1 555 0100 · QQ 123456789
  ❌ 未抹  call 138-0013-8000（带连字符的手机号）· 微信 abc123 · 加我微信 abc · wx: seller01 · tg @seller
  ```
  今天不构成 D-7 泄漏：`open_question` **只到 API 返回、没有落库**（全仓无 `open_questions` 表、无写入点），而返回的是客户自己的话回给客户自己。但 `chat.test.ts` 里那句「这段**会进 DB**」说明落库是计划中的——落库那一刻，这些缺口就变成了持久化的联系方式。建议在接落库的那个 PR 之前先补 `redactContact`（连字符手机号 + 微信/wx/tg 这类带 handle 的），或者至少把这条写进 FU 账本，和已有的 FU-3（reply 出站零过滤）合并处理。
- **[Low] `sanitizeOpenQuestion(q, redact = redactContact)` 的默认参数对 `null` 不生效**（R1a 提的，方向对）。JS 的默认参数只在实参为 `undefined` 时生效，显式传 `null` 会直接把 `null` 当函数调用。当前唯一调用点 `:392` 只传一个实参，所以不可达；但这是个导出函数，将来别人显式传 `null` 就会炸。改成 `const r = redact ?? redactContact` 更稳。
- **[Low] `.slice(0, 500)` 在奇数偏移下仍可能切开代理对。** 我测的 300 个 emoji 正好 600 code unit、切在 500 是成对边界；但 `1 个 ASCII + 250 个 emoji` = 501 unit，切到 499 就会留一个孤立高位代理。存进 DB 是一个坏码点。用 `[...text].slice(0,500).join('')` 按码点截即可。

### 驳回

- **R1a「类别校验用 `includes` 打在 readonly 数组的 cast 上，应改用带类型守卫的 `OQ_CATEGORIES.includes(cat)`」** —— `(OQ_CATEGORIES as readonly string[]).includes(cat)` 是**必要的**：`OQ_CATEGORIES` 是 `as const` 元组，`Array.includes` 的形参类型会被推成联合字面量，直接传 `string` 通不过类型检查。这个 cast 是标准写法，不是缺陷。实测行为正确（14/14）。

### Assumptions

- 在两个独立 worktree（`origin/preview` 与 `980183f7`）里跑 sanitizer 探针、`chat.test.ts`、以及 prompt-vs-闸 的端到端判定，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- `redactContact` 的缺口经**两版对跑**确认是既有的，我明确没有算到这个 PR 头上——但说明了为什么它在这个 PR 之后更要紧。
- **live A/B 我没有代跑**，也不建议我代跑：它需要一次生产或 staging 部署，超出评审的范围。作者自己的记录我逐条读了并同意其判断。
- **R2/R3/R4 未跑** —— 唯一需要判断力的交界（新 prompt 的「标准授权预设」是否绕过付费闸）我用端到端实测确定了，无剩余争议项。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `980183f7`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；2 条,1 条方向对已列为 Low、1 条把必要的 cast 当缺陷）→ Sonnet 机械验证
（14 类畸形输入探 sanitizer、截断与代理对边界、redact-before-slice 顺序、`chat.test.ts` 28 条、
两版对跑定性 `redactContact` 缺口为既有、grep 确认 `open_question` 尚未落库、端到端确认
`applyPatch` 碰不到 `directionConfirmed` 因而新 prompt 的预设授权不绕过 #148 的闸）→
**Opus R2 未跑（唯一交界已实测定论）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 两条 findings **都落在本轮新增的那个函数上**，没有在无关代码里找问题。第一条（默认参数对 `null` 不生效）**方向是对的**，我把它保留成了 Low——这是它这几轮里第一次给出一条我原样采纳的技术判断。第二条把一个**必要的** `as readonly string[]` cast 当成缺陷，是对 TypeScript `as const` 元组与 `Array.includes` 形参推断的误解。R1b 的 triage（「new untrusted input sanitized, minor gaps in category handling」）方向准确。
- **下次怎么榨出更多信号**：这个 PR 的核心是一个新的**不可信输入入口**。对这类 diff，最有价值的指令是「对新增的每一个 sanitize/validate 函数，列出它拒绝的输入类别和它**放行**的输入类别，并指出放行集合里有没有本该拒绝的」——它已经会看「拒绝了什么」，缺的是系统性地问「放行了什么」。本轮 `redactContact` 的那几个缺口就在放行集合里。
