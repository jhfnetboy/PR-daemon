## Brood#30 — REQUEST_CHANGES

**4-round pipeline** · 纯 docs(backlog) PR:7 个 TASK 文件 + 1 个 digest 文档,全新增,无代码/配置/CI 改动。`backlog/tasks/*.md` 被 `scripts/export-backlog.js` 构建解析(automation-consumed),已实跑完整构建验证。

### 结论:digest 的 task-ification 声明过度(F1,唯一 blocking)

`backlog/docs/doc-8:14` 声称 **"已把可执行项立成 TASK-39 ~ TASK-45"**,但同文档内 ≥3 个写了**明确修法的可执行项**没有任何 TASK 文件覆盖:

| digest 项 | 描述的具体修法 | 对应 TASK |
|---|---|---|
| SQLite 单写锁 (doc-8:20) | "post 后 finalize(UPDATE+归档)做成不可被 SIGTERM 打断的短事务;手动单-PR review 前先查 current-review.json 防自撞" | **无** |
| docs-refresh 断言失真 (doc-8:26) | "doc PR 必须对真实代码验证;curl body 过 JSON-lint;arch 图从真实路由重画" | **无** |
| `dist/` 无 CI 复现 gate (doc-8:28) | "该做成 CI gate" | **无** |

Opus R2 独立发现 → Codex R3 (gpt-5.5) PK **CONFIRM**(无反驳证据)。已核实这 3 项确实没有对应的 TASK-39..45 文件。

**建议修法(二选一):**
- 为这 3 项补立 **TASK-46/47/48**(SQLite finalize 事务、docs-refresh 真实代码验证、dist/ CI 复现 gate),或
- 把 digest 开头改为 **"已将大部分可执行项立成 TASK-39 ~ TASK-45"**,并把这 3 项显式标为 deferred。

作者自己的 digest 就在主张"doc PR 必须对真实代码验证"——一份声明过度、与实际文件不符的 digest 恰好违背了这条自身原则。

### 已验证无问题(R1 两条 finding 均被机械证据驳回)

- **task-39 引用的 404 repo**:`iDoris-ai/AI_Beginner_Courses`、`AAStarCommunity/MyTask` 经 `gh api` 核实**均不存在**——引用的是真实铁证,非缺陷。
- **task-41 声称"代理已修"**:修复已在 PR-Daemon commit `0692299` 落地(`load_pr_daemon_env.sh` 空 `PR_DAEMON_*_PROXY` 强制 unset 继承代理)——跨仓库记录,非缺陷。
- **R1b 安全轮**:0 发现(正确,diff 纯 .md 无安全面)。

### 自动化兼容性(机械证据)

- 8 个新文件 frontmatter 全部合法 YAML;`TASK-39..45` + `doc-8` ID 唯一,与现有(`TASK-38`、doc-1/6/7)无冲突。
- 在 PR head worktree 实跑 `node scripts/export-backlog.js`:**0 错误**,TASK-39..45 全部进入 `dist/api/tasks.json`,doc-8 正常保存,里程碑进度正常计算。

### Suggestions(非 blocking)

1. **7 个新 task 全无 `milestone:` 字段**(现有 37/37 都有)——milestone-less task 被排除在里程碑进度/kanban 里程碑 lane 之外。若 TASK-39/40 是 Brood 自身 skill/plugin 改进、应上板,建议加 `milestone: m-r` 或明确决策。
2. 跨 repo 的 task(40/41/42/43/44/45 实际改 pilot/PR-Daemon/AirAccount,非 Brood)没有 target-repo/owner 字段,Brood 侧无法验收——建议加字段或注明推到所属仓库。
3. TASK-43 AC#1 引用的"涉钱任务模板"无文件路径,指名模板位置后 AC 才可验证。

---

**Rounds:** R1a(DeepSeek-full): 2 findings,均被机械证据驳回 · R1b(DeepSeek-sec): 0 · R2(Opus-strategic): 1 [Med] F1 + 2 [Low] ADD · R3(Codex PK gpt-5.5): CONFIRM F1 · R4(Opus final): REQUEST_CHANGES
