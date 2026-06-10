# PR-Daemon 设计文档 — v2 架构（Max 订阅驱动 + 三轮 PK + 智能分流）

> 本文档记录 2026-06 与用户讨论确定的 v2 架构决策。是 `pr-daemon-loop` skill 的设计依据。

## 一、产品定位

PR-Daemon 是一个 **Claude Code Skill**（不是独立服务），由用户的 **Claude Code Max ($200) 订阅**驱动，24/7 自动 review 多组织 PR。核心是**三个 AI 分工的 PK 式 review** + **按风险智能分流（2 轮/4 轮）**。

**为什么不用 pr-agent 替代：**
pr-agent（The-PR-Agent/pr-agent, 11.5k⭐）是成熟的独立 Python 服务，但它是「Python 程序调 LiteLLM API」的运行模型，无法利用 Claude Code 订阅（只能按 token 付费调 Anthropic API）。我们的运行模型是「Claude Code 当 agent 编排 + shell 调 DeepSeek/Codex」。两者产品形态根本不同。
→ **决策：pr-agent 留作 submodule 参考库（不运行），只提炼它的算法与 prompt「知识」。**

## 二、核心架构

```
入口（任选其一）：
  • 你输入: 用 $pr-daemon-loop 开始   (skill 触发)
  • 你输入: /pr-daemon-loop            (slash 命令触发)
  • ./run-dpsk-claude.sh               (保留的 DeepSeek 驱动入口，可选)
    │
    └─► Claude Code (Max 订阅, Sonnet 主会话) = 编排大脑，24h 循环
         │
         poll_prs.py 增量发现 PR → 逐个处理：
         │
         ├─ R1 · DeepSeek API   干杂活(取diff+压缩) + 出【初步 review】+ 给【2轮/4轮分类提案】
         │
         ├─ 分流 · Sonnet 确认分类
         │     ├─ 命中🔴安全敏感硬规则 → 强制 4 轮
         │     ├─ 存疑（说不清重大与否） → 升级 4 轮（宁多审不漏审）
         │     └─ 确认低风险 → 2 轮
         │
         ├─ 【2 轮路径】 Sonnet 终审拍板 → verdict
         │
         └─ 【4 轮路径】 R2 Sonnet 挑战 → R3 Codex PK → Opus 子agent 拍板 → verdict
         │       (Codex 余额用尽 → Sonnet 兜底再挑战一轮)
         │
         ├─ 打分 · 给 DeepSeek 这轮工作打分 + 改进建议 → SQLite → 下轮注入 prompt
         ├─ 记录 · triage 决策（2/4 轮 + 依据）供有效性验证
         └─ 下一个 PR
```

## 三、模型分工 & 拍板权

| 角色 | 模型 | 成本 | 职责 | 能否拍板 |
|---|---|---|---|---|
| 杂活+初审 | DeepSeek API | ~$0.001/PR | 取 diff、压缩、出初审草稿、给分类提案 | ❌ 只出稿 |
| 二审挑战 | Sonnet（主会话） | 订阅内 | 挑战 R1、补漏纠错、给 DeepSeek 反馈、确认分类 | ❌ 挑战者 |
| 三审 PK | Codex Plus | $20/月 | 独立对抗 PK，**最受尊重**的资深对手 | ❌ 挑战者 |
| **最终拍板** | **Opus 子agent** | 订阅内 | 综合 R1+R2+R3，给结论 comment + verdict | ✅ **唯一拍板** |

**拍板原则：**
- 最终 verdict 永远由 **Claude Code（Opus 子 agent）** 拍板。
- 但必须**充分尊重 DeepSeek 和 Codex 的反馈**——尤其 Codex 是资深对手，它的 `[CHALLENGE]`/`[CONFIRM]`/`[MISSED]` 要**逐条回应**，非有力反证不得驳回。
- **Sonnet→Opus 实现**：主会话跑 Sonnet（省 token、干编排）；4 轮路径的拍板环节 spawn `Agent(model="opus")` 子 agent 做高风险 verdict 决策。2 轮路径由 Sonnet 直接拍板（低风险，不必动用 Opus）。

## 四、2 轮 vs 4 轮智能分流（v2 新核心能力）

**取代旧规则**：删除「100 行以上强制 double review」。行数不再是标准——一个 500 行 README 翻译该走 2 轮，一个 30 行合约改动该走 4 轮。改用**风险类型**判断。

### 走 2 轮（DeepSeek 初审 → Sonnet 拍板）—— 低风险，需**全部**满足

- 类型：docs / chore / style / typo / 注释 / 格式
- 依赖 bump（dependabot / renovate）
- License / CODEOWNERS / README / badge
- **不**触及 `src/` `contracts/` `lib/` 核心逻辑
- **无**新增 public API / schema / migration

### 走 4 轮（DeepSeek → Sonnet → Codex → Opus拍板）—— 高风险，命中**任一**即触发

- 类型：feat（新功能）/ 重大 refactor
- 触及核心代码：`src/` `contracts/` `lib/` 下真实逻辑
- 🔴 **安全敏感硬规则**：`.sol` / auth / crypto / payment / token / permission / access-control
- 并发 / 状态机 / 数据持久化 / DB migration
- API 契约 / 接口 / schema 变更
- 删测试 / 关安全检查 / 跨多模块大改

### 判断者 + 安全偏置

```
R1 时 DeepSeek 给分类提案 (trivial / significant)
   └─► Sonnet 确认：
         ├─ 命中🔴安全敏感硬规则 → 强制 4 轮，不接受 DeepSeek 降级
         ├─ 存疑 → 一律升级 4 轮（宁多审不漏审）
         └─ 确认低风险 → 2 轮
```

### 判断标准有效性验证（闭环）

| 机制 | 做法 |
|---|---|
| 记录 | SQLite 存每个 PR 的 triage 决策（2/4 轮）+ 依据 |
| 抽样回溯 | 定期挑几个「2 轮」PR 补跑完整 4 轮，看 Codex/Opus 是否发现 2 轮漏的问题 |
| 漏判信号 | 某「2 轮 APPROVE」后被人类 request-change / 报 bug → 标记 triage 漏判 |
| 指标 | **triage 漏判率**（目标 < 5%）。偏高 → 收紧 2 轮条件，多推向 4 轮 |

## 五、从 pr-agent 提炼的「零件」（不运行其程序）

| 提炼物 | 来源 | 落地形态 |
|---|---|---|
| 大 diff 智能压缩算法 | `algo/pr_processing.py` `token_handler.py` | → `scripts/compress_diff.py` |
| 结构化 review prompt 范式 | `settings/pr_reviewer_prompts.toml` | → skill prompt（score 0-100 / key_issues / 不确定性标注） |
| 语言/文件过滤规则 | `language_extensions.toml` `file_filter.py` | → `config/review_ignore.txt` |
| self-reflection 打分范式 | `self_reflect_on_suggestions` | → DeepSeek 打分 prompt |
| polling 健壮性套路 | `servers/github_polling.py` | → `scripts/poll_prs.py`（since 增量 + async 队列 + 去重 + 重试） |

## 六、verdict 规则

- 每个 PR 必须推进状态：**APPROVE** 或 **REQUEST_CHANGES**，不留 COMMENT limbo。
- **REQUEST_CHANGES 也要给出挑战性意见**（具体问题 + 复现场景 + 修复方向）。
- 所有 verdict（含 APPROVE）都可**追加补充/完善/提升建议**。
- 永不 merge——merge 是 PR 作者/maintainer 的决定。
- 永不直接 `gh pr review`——一律走 `scripts/post_pr_review.sh`（账号切换）。

## 七、入口一览

| 入口 | 用途 |
|---|---|
| `用 $pr-daemon-loop 开始` | skill 触发（主推） |
| `/pr-daemon-loop` | slash 命令触发（等价） |
| `./run-dpsk-claude.sh` | DeepSeek 驱动 Claude Code（保留，可选） |
| `$pr-daemon-status` | 实时进度 + token 消耗看板 |
| `./balance.sh` | DeepSeek + Codex + Claude 余额/用量 |

## 八、Token 预估（Max $200 套餐）

| 项 | 每个 PR | 备注 |
|---|---|---|
| Sonnet 编排 + R2 | ~30-60k | 主消耗，套餐内轻松 |
| Opus 拍板（仅 4 轮） | ~10-20k | 低频 |
| DeepSeek API | ~$0.001 | 单独计费，几乎免费 |
| Codex | Plus 配额 | 单独 |

2 轮 PR 几乎不动用 Opus，成本更低。按用户 PR 量（一天几个到几十个），Max $200 绰绰有余。

---

*本设计文档由 v1 → v2 讨论沉淀而成。v1 是「DeepSeek 驱动 Claude Code + Codex PK 两段」，v2 升级为「Max 订阅 Sonnet 驱动 + 三轮 PK + Opus 拍板 + 2/4 轮智能分流」。*
