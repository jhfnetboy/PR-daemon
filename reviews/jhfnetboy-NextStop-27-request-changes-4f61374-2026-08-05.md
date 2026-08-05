## Verdict: REQUEST_CHANGES（首轮，head `4f61374e`）—— **不是这段代码写得不好，是它拆掉的那道闸【前面那道现在是开的】**

先说这个 PR 本身做得细的地方：

- **`phone` / `wechat` 不再拷进公开目录行** —— 注释写明「它们留在 submission 记录上供管理员用」。这是**顺手修掉的一个真实隐私问题**，值得单独记一笔。
- **只有 `community` / `event` 两类自动发布**，`join/stay/contact/apply` 这些 lead 类仍然 `pending` 进管理员收件箱 —— 分界画得对（前者有公开面，后者没有）。
- **先发布、成功了才翻 `approved`** —— `publishSubmission` 抛异常时 catch 住并留在 pending，不会出现「标了 approved 但目录里没有」。
- **确定性 id (`sub-community-${submissionId}`) + `INSERT OR IGNORE`** 挡住同一份 submission 重复发布，注释也如实说了名字去重只是 best-effort。

### 🔴 Blocking：自动发布 + Turnstile 当前**未配置**，两道闸同时是开的

`verifyTurnstile`（`functions/_shared/turnstile.ts`）在没有密钥时**fail-open**：

```ts
if (!secret) {
  return requireTurnstile
    ? { ok:false, status:503, ... }        // 只有 REQUIRE_TURNSTILE==='true' 才拒
    : { ok:true, configured:false };       // ← 否则直接放行
}
```

而生产上它**没有配**。我查了实际的 secret 列表：

```
$ wrangler pages secret list --project-name nextstop
The "production" environment ... has access to the following secrets:
  - ADMIN_API_TOKEN
  - EMAIL_FROM
  - RESEND_API_KEY
                          ← 没有 TURNSTILE_SECRET_KEY
```
`docs/backend-plan.md:96` 那个 checkbox 也还没打勾：`- [ ] Create Turnstile widget and configure TURNSTILE_SECRET_KEY …`。`README.md:54` 明写「`REQUIRE_TURNSTILE=true` 只有在密钥配好之后才设」。

**所以今天合并这个 PR 之后，一个匿名脚本到公开目录之间只剩一样东西：IP 限流 10 次 / 60 秒**（`submissions` bucket）。也就是**单 IP 每天 14,400 条**直接进公开目录，换 IP 无上限，全程零人工、零人机验证。

**关键在于这是【组合】风险，不是这个 PR 单独的错。** Turnstile fail-open 是既有的、有文档的、故意的（「配好之前不挡人」）；免审自动发布本身也是个合理的产品决定。**但前一道闸是开的时候，后一道闸就是唯一的那道** —— 而这个 PR 把它拆了。

**我建议二选一，都很小：**

1. **把自动发布挂在 Turnstile 真的生效之上**（推荐）：
   ```ts
   const autoApprove = autoPublishTypes.has(type) && turnstile.configured;
   ```
   `verifyTurnstile` 已经返回了 `configured: boolean`，**现在就有这个信息，没用上**。配好密钥之前自动发布不生效、提交照旧进管理员队列；配好之后自动生效，不需要再改代码。
2. 或者**先配 `TURNSTILE_SECRET_KEY` + `REQUIRE_TURNSTILE=true` 再合这个 PR** —— 顺序换一下就行。

### 非阻塞

- **[Med] 名字去重形同虚设，而它是唯一挡「同一个社区被灌 N 次」的东西。** `SELECT id FROM communities WHERE name = ?1` 精确匹配，`深圳数字游民` / `深圳数字游民 ` / `深圳数字游民社区` 是三条。注释诚实地标了 best-effort，但在**免审**语境下它的角色变重了——原来管理员会看见重复，现在没人看。至少归一化一下（trim + 折大小写 + 去空白）能挡住最常见的那类。
- **[Med] `reviewed_by = 'api-admin'`** —— 注释说这是「seeded 系统用户，满足 FK 约束，和 token-admin 路径同一个 actor」。理由成立，但**审计上「自动发布」和「管理员用 token 批准」现在长得一模一样**。事后想查「哪些是没人看过就上线的」查不出来。建议加一个可区分的值（`auto-publish`）或一列 `auto_published`——现在这个字段在说一件没发生的事。
- **[Low] 我没能建立 XSS 路径，如实说明。** 我查了 `scripts/assets/*.js` 里的 `innerHTML` 用法：`interactions.js:57` 那处对内容走了 `esc()`，`who-here.js:293` 是静态标记。`validateSubmission` 也对文本做了 `slice(maxLength)`。**所以我没有证据说提交内容能注入脚本**——但免审发布之后，任何一处将来新增的未转义渲染，影响面都从「管理员看到」变成「所有访客看到」。值得在 `publish-submission.ts` 上留一句注释说明这条不变式现在承重了。
- **[Low] 限流是按 IP 的**（`clientIp(request)`），Cloudflare 前面拿 `CF-Connecting-IP` 一般可信，但代理/移动网络下多用户共享 IP 会互相挤占 10/分钟的额度。免审之前这只是「提交失败重试一下」，之后它是唯一的量闸——值得复核这个数值是不是还合适。

### 驳回

- **R1b「auto-publish bypasses moderation, potential duplicate data races」定级 medium** —— 方向对，我把它升成了 Blocking，理由是它没看到 Turnstile 当前**未配置**这个外部事实（那需要查生产 secret）。至于 duplicate race：确定性 id + `INSERT OR IGNORE` 已经挡住了同一份 submission 的重复，注释也说清了；名字去重的松弛我另列为 Med。

### Assumptions

- 用 `gh repo clone` 拉了一份只读副本到 scratchpad 做评审上下文（本地 `~/Dev/auraai/NextStop` 也有一份，我没有碰它），未改动任何仓库文件。
- **生产 secret 是实查的**（`wrangler pages secret list --project-name nextstop`），不是照文档推的——这条是整个判断的基础，所以必须实查。
- **我没有向生产提交任何测试数据**：上面的结论都是读代码 + 查配置得出的，没有真的去打 `/api/submissions/community`。
- XSS 那条我**明确说明没能建立路径**，没有把「可能有」写成「有」。
- **R2/R3/R4 未跑** —— 阻断项的依据是一条可直接复核的外部事实（生产没配 Turnstile 密钥）加一段十行的代码路径。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `4f61374e`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；R1b 的 `medium — auto-publish bypasses moderation` 方向准确，缺的是生产配置这个外部事实）→
Sonnet 机械验证（读 `verifyTurnstile` 确认 fail-open 分支、`wrangler pages secret list` 实查生产
未配 `TURNSTILE_SECRET_KEY`、`backend-plan.md` 的未勾选项与 README 的启用顺序、限流参数 10/60s、
去重语句的精确匹配语义、`reviewed_by` 的取值、追 `innerHTML` 路径确认客户端有 `esc()` 因而未能建立 XSS）→
**Opus R2 未跑；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** R1b 的 triage **抓对了核心风险类别**（`medium — auto-publish bypasses moderation, potential duplicate data races`），而且它注意到了「dedup pre-checks are best-effort as documented」和「privacy fix properly removes phone/wechat」——两条都准。它够不到的是**生产配置**：Turnstile 是否真的在挡人，只有查 `wrangler pages secret list` 才知道，那是 diff 之外的事实。
- **下次怎么榨出更多信号**：这类「拆掉一道闸」的 diff，关键永远是**前后还剩几道闸、每道现在是开是关**。下次在 prompt 里写死：「列出这条请求路径上的全部前置校验（按代码顺序），并对每一道说明：它在什么条件下会放行，那个条件当前成立与否需要查什么」。它答不出最后半句，但**能把该查的清单列出来**——那我就知道要去查生产 secret，而不用靠自己想到。
