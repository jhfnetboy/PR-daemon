<div align="center">

# PR-Daemon

**24/7 全自动 PK 式 PR Review 系统**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Open Source](https://img.shields.io/badge/Open%20Source-%E2%9D%A4-red)](https://github.com/jhfnetboy/PR-daemon)
[![Powered by DeepSeek](https://img.shields.io/badge/Powered%20by-DeepSeek%20API-6C4FD6)](https://api-docs.deepseek.com/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Agent-orange)](https://claude.ai/code)
[![Codex Plus](https://img.shields.io/badge/Codex-Plus%20Only-10A37F)](https://openai.com/codex)
[![24/7 Review](https://img.shields.io/badge/Mode-24%2F7%20Autonomous-success)](https://github.com/jhfnetboy/PR-daemon)
[![Review Only](https://img.shields.io/badge/Policy-Review%20Only%20%E2%9B%94%20No%20Merge-critical)](https://github.com/jhfnetboy/PR-daemon)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/jhfnetboy/PR-daemon/pulls)

[English](#english-version) · [中文](#中文版) · [快速启动](#快速启动5-步上线-24-小时-pr-review) · [截图](#实际运行截图)

</div>

---

## 中文版

### 是什么

PR-Daemon 是一套基于 **Claude Code Agent + DeepSeek API** 的 24/7 全自动 PK 式 PR review 系统。你只需要一个 DeepSeek API Key 和一个 Codex Plus 订阅，就能让 AI 持续监控你在多个组织的所有 open PR、自动深度 review、用 Codex 做对抗性挑战（PK），并以指定账号发布 review——全程无需人工干预。

**核心设计理念：挑战式 review（PK）**

不是一个 AI 自己说了算，而是两个 AI 互相对抗：
1. **Claude Code（DeepSeek 后端）** 独立深度 review diff，形成 findings
2. **Codex** 作为对手，逐条挑战每个 finding，用反向证据攻击
3. Claude Code 审阅挑战，接受合理反驳（降低误报），保留有证据支撑的 findings
4. 最终发布经过 PK 验证的 review——质量显著高于单模型

**成本极低**：DeepSeek API 约为 Claude API 的 1/10 成本，Codex Plus 每月 $20 即够用。无需昂贵的企业 API。

### 核心功能

| 功能 | 说明 |
|------|------|
| 🥊 **PK 挑战式 review** | 双模型对抗：Claude Code 初审 → Codex 逐条挑战 → 最终裁决 |
| 🔄 **24/7 全自动 Loop** | 发现 PR → 深度 review → PK 挑战 → 发布 → 循环，无需值守 |
| 💰 **超低成本** | DeepSeek API（1/10 成本）+ Codex Plus（$20/月）即可运行 |
| 🧠 **Claude Code Agent** | 原生 Claude Code 技能系统，语音/文字启动，自然语言交互 |
| 📊 **SQLite 评分追踪** | 每次 review 自动记录评分、verdict、PK 结果，可回溯 |
| ⛔ **永不 Merge** | 只 review 和 comment，merge 权限属于 PR 作者 |
| 🔌 **可安装 Skill** | 一行命令全局安装，在任何目录的 Claude Code 会话中可用 |
| 🌐 **多组织覆盖** | 同时监控 aastar / auraai / mycelium 等多个 GitHub 组织 |

### 实际运行截图

> 以下截图来自真实运行 session，本轮共处理 ~43 个 PR

**全自动 Loop 流程**

![自动Loop流程](docs/screenshots/02-auto-loop.jpg)

*运行 `./run-dpsk-claude.sh` 后，用语音说"启动 PR Daemon"，Claude Code 自动完成全部步骤*

**PK 挑战对抗结果**

![PK挑战结果](docs/screenshots/06-pk-challenge.jpg)

*Codex 以对手身份逐条挑战 findings：CONFIRMED（保留）/ CHALLENGED（提供反证）/ MISSED（发现新问题）*

**评分分布**

![评分分布](docs/screenshots/04-score-dist.jpg)

*每个 PR 独立评分（85-98 分），verdict 分 REQUEST_CHANGES / APPROVE*

**本轮最终报告**

![最终报告](docs/screenshots/07-final-report.jpg)

*一个 loop 处理 ~43 个 PR：1 深度 review+PK、3 中度 review、~39 快速 APPROVE*

**PK 质量对比分析**

![PK质量对比](docs/screenshots/08-pk-quality.jpg)

*PK 确认率：launch#8 为 67%（4/6 confirmed），aastar-sdk#42 因证据链不足仅 25%（1/4 confirmed）*

**Loop 完成总结**

![Loop完成](docs/screenshots/05-loop-complete.jpg)

*SQLite 记录 5 条评分（ID 22-26），全部 review 已发布，watcher state 已更新*

**记忆更新（session 学习）**

![记忆更新](docs/screenshots/03-memory-update.jpg)

*每轮 loop 结束后 Claude Code 自动更新记忆：auto-post、GH_TOKEN 直连、loop 全自动不中断*

**项目文件结构**

![文件结构](docs/screenshots/01-file-structure.jpg)

*清晰的分层结构：一键启动脚本 + .claude/skills/ 自动发现 + Python 辅助脚本*

---

### 架构（三层 PK）

```
./run-dpsk-claude.sh
    │
    └─► Claude Code Session（DeepSeek API 后端）
            │
            ├─ Step 1: gh search prs --author jhfnetboy  ← 发现 open PR
            ├─ Step 2: gh pr diff + git fetch            ← 获取 diff
            ├─ Step 3: 深度 review（独立形成 findings）
            │
            ├─ Step 4: Agent(codex:codex-rescue) PK      ← 强制执行，不可跳过
            │           ├─ [CHALLENGE] 提反证 → Rejected
            │           ├─ [CONFIRM]   独立确认 → Confirmed
            │           └─ [MISSED]    发现新问题 → 验证后加入
            │
            ├─ Step 5: post_pr_review.sh                 ← 以 clestons 发布
            ├─ Step 6: model_eval_db.py record-run       ← 记录评分
            └─ Step 7: loop → 下一个 PR
```

**为什么用 DeepSeek 而不是 Claude API 直连：**
DeepSeek 提供 Anthropic API 完全兼容端点（`https://api.deepseek.com/anthropic`），`run-dpsk-claude.sh` 通过 `ANTHROPIC_BASE_URL` 将 Claude Code CLI 所有请求路由到 DeepSeek，费用约为 Claude API 的 1/10，功能完全相同。

---

### 快速启动：5 步上线 24 小时 PR Review

#### 第 0 步：Clone 仓库

```bash
git clone https://github.com/jhfnetboy/PR-daemon.git
cd PR-daemon
```

#### 第 1 步：配置 .env

```bash
cp env.example .env
```

打开 `.env`，最少填这三项：

```bash
DEEPSEEK_API_KEY=sk-...             # DeepSeek API Key（主 reviewer 后端）
PR_DAEMON_REVIEW_TOKEN=ghp_...      # review 账号的 GitHub classic PAT
PR_DAEMON_REVIEW_USER=clestons      # 发布 review 的 GitHub 账号
PR_DAEMON_MAIN_USER=jhfnetboy       # 被 review 的 PR 作者账号（你自己）
```

代理（如需）：

```bash
PR_DAEMON_HTTPS_PROXY=http://127.0.0.1:7890
```

#### 第 2 步：初始化 SQLite 数据库

```bash
./scripts/bootstrap_pr_daemon.sh
```

创建两个数据库：

| 路径 | 用途 |
|------|------|
| `.state/pr-daemon/pr-watch.sqlite` | 运行时 PR 队列状态机 |
| `reviews/model-evals/model-evals.sqlite` | Review 评分历史 |

#### 第 3 步：安装 Claude Code Skills

```bash
# 全局安装（所有 Claude Code 会话可用）
./install-skills.sh --global

# 查看安装的 skill
ls ~/.claude/skills/
```

可用 skill：

| Skill | 调用方式 | 功能 |
|-------|----------|------|
| `pr-daemon-loop` | `$pr-daemon-loop` | 24/7 全自动 review loop |
| `pk-review` | `$pk-review` | 单个 PR 的完整 PK review |
| `pr-daemon-status` | `$pr-daemon-status` | 实时进度看板 |

#### 第 4 步：确认 GitHub 账号

```bash
gh api user -q .login    # 必须返回你的主账号
```

#### 第 5 步：启动！

```bash
./run-dpsk-claude.sh
```

Claude Code 启动后说（支持语音）：

```
Use $pr-daemon-loop to start reviewing all my open PRs
```

或无人值守 headless 模式：

```bash
./run-dpsk-claude.sh -p "Use pr-daemon-loop. Review all open PRs by jhfnetboy across aastar, auraai, and mycelium. Post as clestons. Run until stopped."
```

**就这样，全自动运行了。**

---

### 实时状态查看

随时输入 `$pr-daemon-status` 查看进度看板：

```
════════════════════════════════════════
  PR Daemon Status

Queue
  Total discovered : 43
  🔄 Reviewing now : 1  (launch#8)
  ⏳ Pending       : 5
  👁  Seen only     : 0

Completed Reviews
  Total posted     : 37
  ❌ REQUEST_CHANGES : 1  (avg score: 85)
  ✅ APPROVE          : 36 (avg score: 94)

PK Challenge Stats
  Confirmed rate   : 67% (launch#8) / 25% (aastar-sdk#42)
════════════════════════════════════════
```

---

### 成本说明

| 组件 | 费用 | 说明 |
|------|------|------|
| DeepSeek API | ~$1-5 / 100 个 PR | 主 reviewer 后端，Anthropic 兼容 |
| Codex Plus | $20 / 月 | PK 挑战者，只需 Plus 订阅 |
| GitHub Actions / 服务器 | $0 | 本地运行，无需云服务器 |
| **总计** | **$20-25 / 月** | 覆盖 24/7 全自动 review |

---

### 安全约束（不可妥协）

- ⛔ **永不 merge** 任何 PR，即使 verdict 是 APPROVE
- ⛔ **永不修改** 业务仓库源码、配置、测试或锁文件
- ⛔ **永不直接调用** `gh pr review`，必须通过 `scripts/post_pr_review.sh`
- ✅ 允许的 GitHub 写操作：发布 review comment / request changes / approve

---

### 账号分工

| 账号 | 用途 |
|------|------|
| `jhfnetboy`（主账号） | 发现自己名下的 open PR，保持默认 active |
| `clestons`（review 账号） | 发布 PR review，切换由 `post_pr_review.sh` 自动处理 |

发布脚本自动切换账号，发布后自动切回主账号，不污染默认 gh 配置：

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO --pr N \
  --body-file /tmp/review.md \
  --request-changes   # 或 --approve / --comment
```

---

### 多组织 Code Owner 说明

`clestons` 已配置为以下仓库的 CODEOWNER（`* @clestons`）：

- `MushroomDAO/launch`
- `MushroomDAO/mycelium-protocol`
- `MushroomDAO/Spores`
- `MushroomDAO/blog`
- `MushroomDAO/Listener`
- `MushroomDAO/All-You-Should-Know-Today`
- `MushroomDAO/YetAnotherAA`

在这些仓库中，clestons 发布的 review 会自动满足"required code owner review"条件，PR 才能 merge。

---

### 项目结构

```
PR-Daemon/
├── run-dpsk-claude.sh          ← 一键启动（DeepSeek 作为 Claude 后端）
├── install-skills.sh           ← 安装 skill 到项目或全局 ~/.claude/skills/
├── uninstall-skills.sh         ← 卸载全局安装
├── env.example                 ← 配置模板（无密钥，可安全提交）
├── .claude/skills/
│   ├── pr-daemon-loop/SKILL.md ← 24/7 全流程循环 skill
│   ├── pk-review/SKILL.md      ← 单 PR 深度 PK review skill
│   └── pr-daemon-status/SKILL.md ← 实时进度看板 skill
├── skills/pk-review/scripts/
│   └── local_review.py         ← 可选宽幅扫描脚本（DeepSeek API）
├── scripts/
│   ├── post_pr_review.sh       ← GitHub review 发布（含账号切换）
│   ├── bootstrap_pr_daemon.sh  ← 一次性初始化（创建 DB、目录）
│   ├── model_eval_db.py        ← SQLite 评分记录
│   ├── resolve_repo.py         ← org → 本地路径映射
│   └── list_open_prs.py        ← 发现 open PR
├── config/
│   ├── repo-roots.json         ← org → 本地路径配置
│   └── workspace-roots.txt     ← Claude Code --add-dir 根目录列表
└── reviews/
    ├── model-evals/            ← 评分历史 SQLite + Markdown
    └── watch-prompts/          ← dispatch prompt 归档
```

---

### Observability 命令

```bash
./watch.sh status        # watcher 状态
./watch.sh queue         # SQLite 队列（按状态分组）
./watch.sh current       # 当前正在 review 的 PR（JSON）
tail -f .state/pr-daemon/review-watch.log  # 实时日志

python3 scripts/model_eval_db.py provider-summary --limit 50
python3 scripts/model_eval_db.py scorecard --owner OWNER --repo REPO --pr-number N
```

---

## English Version

### What is PR-Daemon

PR-Daemon is a 24/7 autonomous **PK-style PR review system** powered by **Claude Code (DeepSeek backend) + Codex Plus**. It continuously monitors open PRs across multiple GitHub organizations, performs deep adversarial review, and posts findings — fully unattended.

**The PK Philosophy**: Two AI models fight each other to produce better reviews.
1. **Claude Code (DeepSeek)** independently reviews the diff and forms findings
2. **Codex** adversarially challenges each finding with counter-evidence
3. Claude Code adjudicates — accepts valid challenges (reducing false positives), keeps evidence-backed findings
4. The PK-verified review is posted — quality significantly higher than single-model review

**Cost**: DeepSeek API (~1/10 of Claude API cost) + Codex Plus ($20/month). No expensive enterprise API required.

### Features

| Feature | Description |
|---------|-------------|
| 🥊 **PK Challenge Review** | Dual-model adversarial: primary reviewer → Codex challenger → final verdict |
| 🔄 **24/7 Autonomous Loop** | Find PRs → deep review → PK challenge → post → repeat, unattended |
| 💰 **Ultra-low Cost** | DeepSeek API + Codex Plus ($20/mo) is all you need |
| 🧠 **Claude Code Agent** | Native Claude Code skill system, voice/text activation |
| 📊 **SQLite Score Tracking** | Every review recorded with score, verdict, PK stats |
| ⛔ **Never Merges** | Review and comment only — merge is the PR author's decision |
| 🔌 **Installable Skills** | One command global install; available in any Claude Code session |
| 🌐 **Multi-org Coverage** | Monitors aastar / auraai / mycelium and more simultaneously |

### Quick Start

#### Step 0: Clone

```bash
git clone https://github.com/jhfnetboy/PR-daemon.git
cd PR-daemon
```

#### Step 1: Configure .env

```bash
cp env.example .env
```

Fill in at minimum:

```bash
DEEPSEEK_API_KEY=sk-...             # Primary reviewer backend
PR_DAEMON_REVIEW_TOKEN=ghp_...      # GitHub classic PAT for review account
PR_DAEMON_REVIEW_USER=clestons      # GitHub account that posts reviews
PR_DAEMON_MAIN_USER=jhfnetboy       # Your main GitHub account (PR author)
```

#### Step 2: Initialize SQLite

```bash
./scripts/bootstrap_pr_daemon.sh
```

#### Step 3: Install Skills

```bash
./install-skills.sh --global   # Available in all Claude Code sessions
```

#### Step 4: Launch

```bash
./run-dpsk-claude.sh
```

Then say (voice or text):

```
Use $pr-daemon-loop to start reviewing all my open PRs
```

Or headless:

```bash
./run-dpsk-claude.sh -p "Use pr-daemon-loop. Review all open PRs by jhfnetboy. Post as clestons. Run until stopped."
```

### Architecture

```
./run-dpsk-claude.sh  (ANTHROPIC_BASE_URL → DeepSeek)
    │
    └─► Claude Code Session (primary reviewer, DeepSeek backend)
            │
            ├─ Discover: gh search prs --author jhfnetboy
            ├─ Diff:     gh pr diff + git fetch
            ├─ Review:   independent deep review → findings
            │
            ├─ PK:  Agent(codex:codex-rescue)  ← MANDATORY
            │         [CHALLENGE] counter-evidence → Rejected
            │         [CONFIRM]   independent proof → Confirmed
            │         [MISSED]    new issue found → verify & add
            │
            ├─ Post:   post_pr_review.sh (account-safe)
            ├─ Record: model_eval_db.py record-run
            └─ Loop → next PR
```

### Safety Constraints

- ⛔ **Never merge** any PR, even after APPROVE
- ⛔ **Never modify** business repo source, config, tests, or lock files
- ⛔ **Never call** `gh pr review` directly — always use `post_pr_review.sh`
- ✅ Allowed GitHub writes: post comment / request changes / approve

### Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| DeepSeek API | ~$1-5 / 100 PRs | Primary reviewer backend |
| Codex Plus | $20 / month | PK challenger (Plus is sufficient) |
| Server/infra | $0 | Runs locally on your machine |
| **Total** | **~$20-25/mo** | For 24/7 autonomous review |

### Account Roles

| Account | Role |
|---------|------|
| `jhfnetboy` (primary) | Discovers own PRs, stays as default active account |
| `clestons` (review) | Posts reviews; switching handled automatically by `post_pr_review.sh` |

### Skills Reference

| Skill | Invoke | Purpose |
|-------|--------|---------|
| `pr-daemon-loop` | `$pr-daemon-loop` | Full 24/7 autonomous review loop |
| `pk-review` | `$pk-review` | Single PR deep PK review |
| `pr-daemon-status` | `$pr-daemon-status` | Live dashboard: queue / verdicts / PK stats |

### Key Scripts

| Script | Purpose |
|--------|---------|
| `run-dpsk-claude.sh` | Launch Claude Code on DeepSeek API |
| `scripts/post_pr_review.sh` | Post review with safe account switching |
| `scripts/bootstrap_pr_daemon.sh` | One-time DB + directory init |
| `scripts/model_eval_db.py` | SQLite CRUD for scoring history |
| `scripts/resolve_repo.py` | org → local path resolution |
| `install-skills.sh` | Install skills globally |
| `uninstall-skills.sh` | Remove globally installed skills |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API key (required) |
| `PR_DAEMON_MAIN_USER` | `jhfnetboy` | PR author account |
| `PR_DAEMON_REVIEW_USER` | `clestons` | Account that posts reviews |
| `PR_DAEMON_REVIEW_TOKEN` | — | GitHub PAT for review account |
| `PR_DAEMON_REVIEWER_CLI` | `claude` | Primary reviewer CLI |
| `PR_DAEMON_REVIEWER_FALLBACK` | `codex` | Fallback if Claude unavailable |
| `PR_DAEMON_HTTPS_PROXY` | — | Proxy for API calls |

### Observability

```bash
./watch.sh status                          # Watcher PID, active review, loop state
./watch.sh queue                           # SQLite queue by status
./watch.sh current                         # Currently-reviewing PR (JSON)
tail -f .state/pr-daemon/review-watch.log  # Live log

python3 scripts/model_eval_db.py provider-summary --limit 50
python3 scripts/model_eval_db.py scorecard --owner OWNER --repo REPO --pr-number N
```

### Review Completion Contract

A review is complete only when ALL three are true:
1. Explicit verdict: `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`
2. Posted to GitHub PR (via `post_pr_review.sh`)
3. Recorded: Markdown artifact + SQLite score entry

**Never merge — always the PR author's or maintainer's decision.**

---

### License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

### Contributing

PRs welcome. Please ensure your PR is reviewed by PR-Daemon itself before merging.
