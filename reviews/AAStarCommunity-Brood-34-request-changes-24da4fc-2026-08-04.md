## PR-Daemon Review — AAStarCommunity/Brood#34 [2-round]

**结论: REQUEST_CHANGES**

纯文档/元数据 PR（`marketplace.json` 描述、`plugin.json`/`SKILL.md` 版本号、`status.md` 措辞），2-round：DeepSeek R1（全量 + 安全双通道）+ Sonnet 直接裁决，无 src/logic/自动化消费文件改动，未触发 4-round。

### ✅ 已核实为准确
- `status.md` 关于排序指标从 `pushedAt` 改为「默认分支最后提交时间」的描述，与 PR-Daemon 仓库已合并的 `76a659c fix(scan): rank by default-branch commit date, not repo.pushedAt` 完全吻合（commit message 里 SuperPaymaster 08-03/07-09 的例子逐字对应）。
- 文中提到的 `refresh-scan-focus.sh add <owner/repo>` 命令，在脚本里确实存在且用法一致（`case ... add) ... pin_add`）。
- `marketplace.json` 的新描述（git-guard best-effort + safe-cleanup + daemon 集成）与当前 `SKILL.md` 正文实际描述的行为一致（best-effort 措辞、无 auto-commit 相关内容，已确认 SKILL.md 全文搜不到"auto-commit"）。

### 🔴 Blocking — plugin.json 自身描述未同步修正
PR 标题/描述都在讲"marketplace 描述纠偏"（`auto-commit 安全网` 功能已移除，措辞需要改成 best-effort），但只改了 `.claude-plugin/marketplace.json` 里的描述，**`plugins/pilot/.claude-plugin/plugin.json` 自己的 `description` 字段一字未改**，仍然写着：

```
"仓库级开发操作系统:status→plan→run,git-guard 硬护栏 + PR 评审 daemon 集成 + auto-commit 安全网。"
```

这条描述同时有两个问题，正好是这个 PR 本该修的那一类错误：
1. `auto-commit 安全网` —— 该功能已按 PR 描述"按要求移除"，SKILL.md 正文也已确认无此内容，这里却还在对外宣称有。
2. `git-guard 硬护栏` —— 与本 PR 改好的新措辞矛盾：`marketplace.json` 新描述已经改成"best-effort"（防护而非硬拦截），SKILL.md 正文第 40 行也明确写"不承诺对抗式滴水不漏"。`plugin.json` 里仍然是"硬护栏"，两处描述现在互相矛盾。

`plugin.json` 是 marketplace 展示 pilot 插件时读取的**实际清单文件**，其 `description` 字段和 `marketplace.json` 里的描述是同一插件对外的两份文案，理应同步。建议把 `plugin.json` 的 `description` 也改成和 `marketplace.json` 一致（或至少去掉 `auto-commit 安全网` + `硬护栏` 这两处过时/矛盾的措辞）。

### 建议（non-blocking）
- 后续可以考虑把这类"插件描述"文案统一到一处（如从 `plugin.json` 派生 `marketplace.json`），避免同一份文案分散在两个文件里下次又漏改一个。

---
🔎 自评
- 轮数: 2-round（触发条件：纯文档/版本号/描述纠偏，无 src/contracts/lib 逻辑改动，无自动化消费文件改动）— 与判定一致 ✅
- R1 DeepSeek(flash) full: 已跑，喂完整压缩 diff，产出「trivial docs/version bump only，无 finding」
- R1 DeepSeek(flash) security: 已跑，「clean — no security-relevant code」
- Sonnet 执行器: 逐条核实 diff 里的三处事实性声明（排序指标改动、pin 命令、marketplace 描述准确性）均对照实际代码/已合并 commit 验证为真；额外发现 diff 未覆盖到的 `plugin.json` 自身描述同款问题（不是 R1 或本清单里列出的核对项，是通读 diff 上下文行时发现的）
- DeepSeek v4-flash 评级: 2/5 — 两遍都只给出"trivial/clean"的空判断，没有注意到 diff 里 plugin.json 那行未改的 description 上下文（虽然是 unchanged context line，但本该识别出"这个 PR 的主题是描述纠偏，为什么同类描述在旁边文件没同步改"这种跨文件一致性问题）。改进建议：docs-only PR 的 prompt 里应显式要求"检查 diff 中未修改的 context 行是否与本次修改主题矛盾"，而不是只找"新增/删除行里的 bug"。
- 与 skill 设计是否一致: 一致；未跑 Opus/Codex（2-round 无需）
