## Brood#30 — REQUEST_CHANGES(第 3 轮,增量复审 @3493929)

**4-round pipeline(增量复审)** · 纯 docs(backlog)PR。修复 commit `3493929`(fix #30 r2 precision nits)已正确解决上一轮 3 项,但**上一轮唯一的 blocking(F1:doc-8:10 目标标记 over-claim)仍未处理** —— 这是同类 defect 连续第 3 次出现(digest 的 blanket 声明 ≠ 文件实际),恰好违背本 PR 自己立的 TASK-47("doc 必须对真实文件验证")。

### Blocking(Med)

**doc-8:10** — 「各 task 描述首行标注『目标仓库』」**与文件实际不符**。已逐一核对 10 个 task 文件的 description 首行:
- task-39/40/41/42/43/44/45(共 7 个)描述首行**均无**目标标记;
- 仅 task-46(「目标仓库:PR-Daemon」)、task-47(「目标:Brood」)、task-48(「目标:Brood」)有,且 47/48 用的是「目标」而非「目标仓库」。

该声明上一轮(f8399d5)已列为唯一 blocking,本轮 fix commit 未触碰。**fix(二选一)**:给 task-39..45 描述首行补 `**目标仓库:…**` 标记(对齐声明),**或**改写 doc-8:10 如实描述(仅 task-46/47/48 首行带标记);顺手统一 47/48 的「目标:」为「目标仓库:」,避免一个约定三种写法。

### Confirmed(Low — 本轮一并打包,避免再走一轮)

1. **doc-8:8 + doc-8:39 "91 个 reviews" 不可复现**:`reviews/` 目录现共 99 个 .md,其中 20 个是 `*local-review*`(未 post),**已 post 记录实为 79 个**。若按撰写时点计数,请标注时点;当前数字请对齐为 79。**注意 doc 标题第 3 行 "digestfrom 91 reviews" 也是同一计数**,改要一起改。
2. **doc-8:22 "#194 … 6 个 request-changes 文件"**:磁盘实为 **5 个 request-changes + 1 个 approve**(6 个文件总计)。改为 "5 个 request-changes(+1 approve)"。
3. **doc-8:8 "已把可执行项立成 TASK-39 ~ TASK-48" 仍略过度**:digest item 1(R1a/R1b 非对称处理)、item 3(别省 token 跳过 R4)是**流程策略**(已内嵌 SKILL.md v4),既无 TASK 也无数「保留为策略」的说明。补一句 "items 1/3 为 pipeline 内嵌策略,不立 task" 即收敛。

### 上一轮已解决(本轮机械验证通过 ✅)

- **计数 213→56**:doc-8:22 与 task-46 对齐为 56,实测 review-watch.log 恰为 **56 次** "database is locked" → 修正确。
- **codex stdin-EOF 修复补入「已完成」**:`scripts/codex_pk.sh:66` 确为 `codex exec … < /dev/null` → 引用准确。
- **task-46 "item 5"→"item 4"**:doc-8 item 4 确为 SQLite 锁项 → 编号修正。

### 自动化兼容性(机械证据 ✅)

PR head worktree 实跑 `node scripts/export-backlog.js`:**0 错误**,`dist/api/tasks.json` 47 个 task,TASK-39..48 全部进入,ID 无冲突;8 个新文件 frontmatter / SECTION 标记 / ordinal 均合法。R1b 安全轮 0 发现(纯 .md 无安全面,正确)。

### Suggestions(非 blocking)

1. 本 PR 正是 TASK-47 的活教材:一份声称"doc 必须对真实文件验证"的 digest,自身两处计数不可复现、一处 cross-file 声明与文件不符——修好它就是 TASK-47 自检的验收样例。
2. 目标标记统一为一种写法(如 `**目标仓库:…**`)并覆盖全部 10 个 task,否则 sync-progress 这类消费者按标记读取时 7/10 静默忽略。
3. task-48「目标:Brood」却按"不挂 Brood milestone"处理,与 note 的 blanket 理由矛盾——要么在 Brood 下挂 milestone,要么归为跨仓库 infra。

---

**Rounds:** R1a(DeepSeek v4-flash): 10 条 finding 全为噪音(「task 引用了 X 但 diff 无代码」——backlog task 文件本就不含代码,Opus R2 + Codex R3 一致 REJECT),且**未独立发现真 blocker** · R1b(DeepSeek v4-flash,security): 0(正确) · R2(Opus strategic): 独立确认 marker-absence + 新加 3 条 Low(91 计数 / #194 5+1 / items 1·3 无 task) · R3(Codex PK gpt-5.5): **CONFIRM F1 + F2,0 CHALLENGE** · R4(Opus final): REQUEST_CHANGES,missed-scan 补抓 doc 标题同款 91 计数。
