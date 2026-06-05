# PR-Daemon Product README

## 中文版

### 产品定位

PR-Daemon 是一个基于 Codex skill 的 PK 式 PR review 系统。核心思路是充分使用本机免费的 Apple Silicon 算力和本地常驻模型 `qwen3.6-a3b`：Rapid-MLX 负责加载模型并提供 OpenAI-compatible API，本地模型承担大量便宜但有价值的初审、归纳、反问、复核和 comment 草稿工作；Codex 只做最关键、最难、最需要资深判断的部分，并对最终 review 结论负责。

默认原则：

- 默认只 review，不修改 PR 分支代码。
- 任何时候禁止直接更改本地业务仓库代码；本地 checkout 只作为 review 上下文。
- 允许在业务仓库外写临时 diff/report；如必须在业务仓库内生成临时文件，必须放在明确的临时/ignored 路径，不能改源码、配置、测试或锁文件。
- 默认只生成本地 review 文案，不直接发 GitHub comment。
- 只有用户明确批准后，才用 review 账号发布 comment、approve 或 request changes。
- 本地模型输出是高价值假设，不是最终结论；最终结论必须由 Codex 用代码、diff、测试或可复现推理确认。

### 账号分工

- 主账号：`jhfnetboy`
  - 用于发现 `jhfnetboy` 名下仍然 open 的 PR。
  - 用于维护主仓库、查看自己的 PR 队列。
  - 默认 active account 必须保持为这个账号。
- Review 账号：`clestons`
  - 邮箱：`clestons@gmail.com`。
  - 用于发布 PR review comment、approve 或 request changes。
  - 注意：`gh auth switch --user` 需要 GitHub login，不一定能直接使用邮箱。如果实际 login 不是 `clestons`，以 GitHub login 为准。

发布任何 GitHub review 前必须检查身份；发布完成后必须切回主账号：

```bash
gh auth status
gh api user -q .login
```

恢复默认主账号：

```bash
bash scripts/ensure_main_github_account.sh
```

切到 review 账号：

```bash
gh auth switch --hostname github.com --user clestons
gh api user -q .login
```

切回主账号：

```bash
gh auth switch --hostname github.com --user jhfnetboy
gh api user -q .login
```

GitHub CLI 可以保存同一 host 的多个账号，但同一时刻只有一个 active account。登录 review 账号后用 `gh auth switch` 切换。

推荐你在普通 Terminal 里登录 `clestons`：

```bash
gh auth login --hostname github.com --web --git-protocol https
gh auth switch --hostname github.com --user clestons
gh api user -q .login
```

如果用 token，建议不要发在聊天里；在本机 Terminal 用 stdin 写入：

```bash
pbpaste | gh auth login --hostname github.com --with-token
gh auth switch --hostname github.com --user clestons
```

classic token 最少需要 `repo`, `read:org`, `gist`。fine-grained token 至少需要目标 repo 的 metadata read、contents read、pull requests read/write；如果遇到行为奇怪，优先用 `GH_TOKEN=... gh ...` 做单次命令而不是写入全局 credential store。

也可以使用本项目的 `.env`，避免每次全局切换 `gh` credential store：

```bash
cp .env.example .env
```

然后在 `.env` 里填：

```bash
PR_DAEMON_REVIEW_USER=clestons
PR_DAEMON_REVIEW_TOKEN=github_pat_xxx
```

`.env` 已被 `.gitignore` 忽略，不会提交。发布脚本会用 `GH_TOKEN=$PR_DAEMON_REVIEW_TOKEN` 单次调用 GitHub API，默认 active account 仍保持 `jhfnetboy`。

多组织 review token 规则：

- Fine-grained PAT 一次只能选择一个 resource owner，因此不适合一个 token 横跨 `AAStarCommunity`、`AuraAI`、`mycelium` 三个组织。
- 如果要一个 token 覆盖三个组织，短期可用 `clestons` 账号的 classic PAT，并确保三个组织都允许 classic PAT 访问。
- Classic PAT 权限建议：`repo`, `read:org`, `gist`。如果只做 PR review，不需要给 `admin:org`。
- 不建议为了 token 把 `clestons` 设成三个组织 admin。更合适的是把 `clestons` 加入三个组织，并给需要 review 的 repo 足够权限（通常 write/maintain 级别即可）。
- 长期更稳的是创建 GitHub App，安装到三个组织，授予 Pull requests write / Contents read / Metadata read；但这需要额外 App 私钥和 installation token 流程。

PR-Daemon 的发布脚本会自动临时切到 `clestons`，发布 review，然后切回 `jhfnetboy`：

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /path/to/review.md \
  --request-changes
```

### 本地模型常驻

目标 API model name 是：

```text
qwen3.6-a3b
```

Rapid-MLX 当前机器检查结果：

- `rapid-mlx` 已安装。
- 当前 `localhost:8000` 没有服务在监听，因此 `/docs` 和 `/v1/models` 现在不可访问。
- 当前 Rapid-MLX alias 列表里没有 `qwen3.6-a3b` 这个 loader alias。
- 当前可见的 qwen3.6 loader alias 包括 `qwen3.6-27b`、`qwen3.6-27b-8bit`、`qwen3.6-35b`、`qwen3.6-35b-6bit`、`qwen3.6-35b-8bit` 等。

因此本项目默认做法是：

- API 暴露名：`qwen3.6-a3b`
- Rapid-MLX 默认加载 alias：`qwen3.6-35b-6bit`
- 这个 alias 走 Rapid-MLX/Hugging Face cache 的原生解析能力。
- 如果要从 `~/.omlx/models` 读模型，用 `RAPID_MLX_LOAD_MODEL` 显式指定本地路径。

如果你希望在 `~/.omlx/models` 里也能看到 6bit 模型，可以把 Hugging Face cache 里的 snapshot 暴露过去。推荐软链接模式，不重复占用 27GB：

```bash
scripts/materialize_omlx_model.sh
```

这个脚本会从：

```text
~/.cache/huggingface/hub/models--mlx-community--Qwen3.6-35B-A3B-6bit/snapshots/<hash>
```

软链接到：

```text
~/.omlx/models/Qwen3.6-35B-A3B-MLX-6bit
```

并用 `rapid-mlx info` 验证本地路径可加载。注意：软链接模式依赖 HF cache，不能删除原 cache。

使用 OMLX 路径启动：

```bash
export RAPID_MLX_LOAD_MODEL="$HOME/.omlx/models/Qwen3.6-35B-A3B-MLX-6bit"
scripts/rapid_mlx_daemon.sh ensure
```

如果你想真正复制到 `~/.omlx/models`，再删除 HF cache 副本：

```bash
scripts/materialize_omlx_model.sh --copy
```

复制模式验证成功后，可以手动删除 HF cache：

```bash
rapid-mlx rm mlx-community/Qwen3.6-35B-A3B-6bit
```

如果之后 Rapid-MLX 或本地 HF cache 里已有真正的 `qwen3.6-a3b`，设置：

```bash
export RAPID_MLX_LOAD_MODEL=qwen3.6-a3b
export RAPID_MLX_MODEL=qwen3.6-a3b
```

启动或确认常驻服务：

```bash
scripts/rapid_mlx_daemon.sh ensure
```

检查状态：

```bash
scripts/rapid_mlx_daemon.sh status
scripts/rapid_mlx_daemon.sh models
scripts/rapid_mlx_daemon.sh docs
scripts/rapid_mlx_daemon.sh smoke
```

如果 Codex/headless 无法访问 Metal，请在普通 Terminal 里启动常驻模型：

```bash
scripts/start_rapid_mlx_resident.sh
```

等价的手动启动命令：

```bash
rapid-mlx serve qwen3.6-35b-6bit \
  --host 127.0.0.1 \
  --port 8000 \
  --served-model-name qwen3.6-a3b \
  --prefill-step-size 4096 \
  --gpu-memory-utilization 0.85 \
  --enable-prefix-cache
```

API 地址：

```text
Docs: http://127.0.0.1:8000/docs
Models: http://127.0.0.1:8000/v1/models
Chat completions: http://127.0.0.1:8000/v1/chat/completions
```

### 每次怎么用

进入本目录后，对 Codex 说：

```text
Use $rapid-mlx-review. Ensure the local Rapid-MLX model is available, find open PRs authored by jhfnetboy, pick the next review target, make qwen3.6-a3b do the broad first pass and challenge rounds, then Codex performs final adjudication and owns the result. Do not edit the PR branch. Generate review comments locally first; do not post unless I explicitly approve posting with clestons.
```

指定某个 PR：

```text
Use $rapid-mlx-review to review OWNER/REPO#123 in PK mode. Use qwen3.6-a3b heavily through Rapid-MLX for triage, initial findings, challenge, and comment drafting. Codex makes the final call. Do not modify code.
```

只 review 当前仓库 diff：

```text
Use $rapid-mlx-review to review this repository. Compare against origin/main, include worktree changes if relevant, run local qwen3.6-a3b first, then Codex adjudicates.
```

### Open PR 获取

不要依赖 `@me` 查队列，因为 active GitHub account 可能是 `clestons`。发现队列时显式查询 `jhfnetboy`：

```bash
python3 scripts/list_open_prs.py
python3 scripts/list_open_prs.py --repo OWNER/REPO
python3 scripts/list_open_prs.py --json
```

底层等价命令：

```bash
gh search prs \
  --author jhfnetboy \
  --state open \
  --json number,title,repository,url,updatedAt,isDraft,author \
  --limit 50
```

`prbot` 可作为人工队列面板：

```bash
prbot all
prbot OWNER/REPO
```

但自动 review 队列以 `scripts/list_open_prs.py` 或显式 `gh search prs --author jhfnetboy` 为准。

### 本地 Repo 映射

PR review 不默认 clone 到 `/tmp`。先按组织映射解析本地 checkout：

| GitHub owner / org | Local root |
|--------------------|------------|
| `AAStarCommunity` / `aastar` | `~/Dev/aastar` |
| `AuraAI` / `auraai` | `~/Dev/auraai` |
| `mycelium` | `~/Dev/mycelium` |

配置文件：

```bash
config/repo-roots.json
```

新增或更新映射：

```bash
python3 scripts/add_repo_root.py OWNER ~/Dev/path --alias short-name
```

解析 repo：

```bash
python3 scripts/resolve_repo.py AAStarCommunity/AirAccount
```

规则：

- 如果 repo 已在对应 root 下，直接使用该本地 checkout。
- 如果没有，clone 到对应 root，例如 `~/Dev/aastar/AirAccount`。
- `/tmp` 只用于短生命周期 diff 文件，不用于常规 PR checkout。
- 注意：Codex 是否能在这些目录里 `git fetch`/checkout，取决于本次会话的 writable roots。当前会话只允许写 PR-Daemon 和 `/tmp`，所以外部 repo 只能读；要让 Codex 直接更新这些 repo，需要下次启动时把对应目录加入 workspace/writable roots。
- 即使这些目录是 writable roots，也仍然禁止修改业务代码。可写权限只用于 `git fetch`、checkout review ref、读取索引和生成临时 review 工件。

启动 Codex 时建议加入这些 workspace/writable roots：

```text
/Users/jason/Dev/tools/PR-Daemon
/Users/jason/Dev/aastar
/Users/jason/Dev/auraai
/Users/jason/Dev/mycelium
```

同样内容记录在：

```bash
config/workspace-roots.txt
```

这些 roots 需要在新会话启动时由 Codex/客户端加载；当前会话中不能动态扩展 sandbox writable roots。

如果用 Codex CLI，直接从普通 Terminal 执行：

```bash
cd /Users/jason/Dev/tools/PR-Daemon
bash scripts/start_codex_pr_daemon.sh
```

等价手动命令：

```bash
codex \
  --cd /Users/jason/Dev/tools/PR-Daemon \
  --sandbox workspace-write \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium
```

`~/.codex/config.toml` 里的 `[projects] trust_level` 只表示信任项目，不等于本次会话可写目录；真正的额外可写目录要用 `--add-dir` 或客户端启动参数传入。

### PK Review 分工

本地 `qwen3.6-a3b` 应尽量多干活：

- PR 队列摘要和优先级建议。
- diff 初审和风险点枚举。
- 按文件生成上下文摘要。
- 对可疑代码路径提出问题。
- 对 Codex finding 做反向 challenge。
- 草拟最终 review comment。
- 草拟修复建议和测试建议。

Codex 负责更难且必须兜底的工作：

- 独立阅读 diff 和关键上下文。
- 判断 local finding 是否成立。
- 找安全、并发、数据丢失、权限、供应链、API contract、CI 误配置等高风险问题。
- 判断问题严重程度、业务影响和可能损失。
- 决定最终是否 request changes。
- 对最终输出负责。

### 标准流程

1. 选 PR
   - 拉取 `jhfnetboy` authored open PR。
   - 默认跳过 draft。
   - 优先处理最近更新、风险高、影响范围大、已有 review request 的 PR。

2. 准备 diff
   - checkout 或 fetch PR。
   - 使用 PR base branch；无法确认时默认 `origin/main`。
   - 生成 merge-base diff。

3. Local Round
   - 确认 Rapid-MLX 常驻服务。
   - 用 `qwen3.6-a3b` 做初审：

```bash
python3 skills/rapid-mlx-review/scripts/local_review.py \
  --repo TARGET_REPO \
  --base origin/main \
  --target HEAD \
  --model qwen3.6-a3b \
  --output /tmp/rapid-mlx-local-review.md
```

4. Codex Deep Round
   - Codex 不先相信 local 输出。
   - 独立读 diff、相关文件、调用链和配置。
   - 运行可行的测试或静态检查。

5. Challenge Round
   - Codex 裁决 local findings。
   - 对复杂 finding，让 local 模型再 challenge 一轮。
   - 最多两轮 challenge，除非用户要求继续。

6. Final Review
   - 输出 confirmed/codex-only/rejected。
   - 给出影响、可能损失、修复建议和 PR comment 文案。
   - 默认不发布。

### 输出格式

```text
Findings

[Confirmed] High - path/to/file.py:123 - title
Evidence:
Impact:
Potential loss:
Fix:
Suggested PR comment:

[Codex-only] Medium - path/to/file.ts:45 - title
Evidence:
Impact:
Potential loss:
Fix:
Suggested PR comment:

Rejected Local Findings
- Finding title: rejected reason.

Local Model Work
- Triage:
- Useful findings:
- Missed:
- Overreached:
- Challenge result:

Verification
- Commands run:
- Tests not run:

Posting
- Current GitHub account:
- Posting status: not posted / posted by clestons
```

### 发布 Comment

默认不发布。用户明确批准后才执行：

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /tmp/pr-review-final.md \
  --comment
```

需要阻塞 PR 时：

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /tmp/pr-review-final.md \
  --request-changes
```

发布前必须确认：

- 当前账号是 review 账号。
- repo 和 PR number 正确。
- 用户明确允许发布。
- 最终 finding 已由 Codex 负责确认。

### 当前文件

- Skill：`skills/rapid-mlx-review/SKILL.md`
- 本地初审脚本：`skills/rapid-mlx-review/scripts/local_review.py`
- Rapid-MLX 常驻服务脚本：`scripts/rapid_mlx_daemon.sh`
- 普通 Terminal 常驻启动脚本：`scripts/start_rapid_mlx_resident.sh`
- Open PR 队列脚本：`scripts/list_open_prs.py`
- 安全发布 review 脚本：`scripts/post_pr_review.sh`
- 本地 repo 解析脚本：`scripts/resolve_repo.py`
- 本地 repo 映射新增脚本：`scripts/add_repo_root.py`
- 本地 repo 映射：`config/repo-roots.json`
- GitHub 账号配置：`config/accounts.json`
- 恢复主账号脚本：`scripts/ensure_main_github_account.sh`
- 本地模型评估 SQLite 记录脚本：`scripts/model_eval_db.py`
- 本地模型评估数据库：`reviews/model-evals/model-evals.sqlite`
- 参考工具：`prbot`

### 本地模型评估记录

每次使用 `qwen3.6-a3b` 做 PR review 后，必须同时记录两类结果：

- Markdown 记录：写入 `reviews/model-evals/`，保留人工可读的评分、贡献、误报、漏报、prompt gap、Codex adjudication。
- SQLite 记录：用 `scripts/model_eval_db.py record-run` 写入 `reviews/model-evals/model-evals.sqlite`，记录本轮 score、模型表现、上轮改进项是否真的改善、以及下一轮 prompt 改进项。

复查同一个 PR 时，`skills/rapid-mlx-review/scripts/local_review.py` 可以通过 `--eval-db reviews/model-evals/model-evals.sqlite --owner OWNER --repo-name REPO --pr-number N` 自动读取历史改进项，并把它们注入本地模型 prompt。Codex 仍然必须独立验证本地模型输出；SQL 只用于让本地模型持续改进，不替代最终 review 判断。

本地模型更适合承担这些工作：

- 批量 review 的第一轮 triage：摘要改动范围、列出风险区域、挑出值得 Codex 深挖的文件。
- 重复性检查：把上一轮 review finding、adversarial case、测试清单逐项复核。
- 安全 gate / grep / 配置类检查的候选反例生成，例如列出所有合法参数形式再做 truth table。
- Review 记录整理：把 local findings、Codex adjudication、误报、漏报、评分和下轮改进项结构化写入 SQL/Markdown。
- 非最终 comment 草稿：提供初稿，但最终结论必须由 Codex 复核后发布。

本地模型不适合单独承担最终判断，尤其是安全边界、并发/状态机、跨模块协议、链上/TEE/CI gate 这类高风险问题。Codex 必须独立看 diff、跑验证命令，并把本地模型输出标记为 confirmed、rejected、missed 或 Codex-only。

### 本地模型正循环

每次 review 后按同一套闭环推进：

1. 本地模型先做 broad pass，并自动读取 SQL 中仍需携带的改进项。
2. Codex 独立复查，验证每个 finding 和 carried-forward improvement。
3. Codex 给本地模型打 0-10 分，记录 useful findings、false positives、misses、prompt gaps。
4. 用 `scripts/model_eval_db.py record-run` 写入本次评分和下一轮改进项。
5. 用 `scripts/model_eval_db.py assess-item` 标记上一轮改进是否真的生效：
   - `effective`：本轮确实改善，停止继续携带。
   - `ineffective`：本轮没有改善，继续携带并需要更强约束。
   - `needs_followup`：部分改善，但仍需下轮验证。
   - `retired`：不再适用。
6. 下次 review 只把 `carried_to_next=1` 的改进项注入 prompt，避免越积越乱。
7. 用 `scripts/model_eval_db.py scorecard` 查看最近评分、改进项状态和未解决问题，判断模型能力是否真的提升。

有效提升的判定不是“模型说得更像”，而是可量化结果：

- 同类 miss 是否减少。
- false positive 是否减少。
- 是否遵守输出格式和 truth table 要求。
- carried-forward improvement 是否被正确执行。
- Codex-only blocker 数量是否下降。
- GitHub review 结论是否更快、更少返工。

常用命令：

```bash
python3 scripts/model_eval_db.py prior-context \
  --owner AAStarCommunity --repo AirAccount --pr-number 30

python3 scripts/model_eval_db.py scorecard \
  --owner AAStarCommunity --repo AirAccount --pr-number 30

python3 scripts/model_eval_db.py assess-item \
  --item-id 3 \
  --status ineffective \
  --evaluation "SQL context included -F examples, but the model still missed the alias."
```

### Review 完成契约

每次 PR review 必须满足三个条件才算完成：

- 有明确结论：`APPROVE`、`REQUEST_CHANGES`、或只留 `COMMENT` 的非阻塞结论。
- 必须在 GitHub PR 上留下对应 review/comment；如果发布失败，必须记录失败原因并继续修复发布流程。
- 必须更新本地记录：review 文案、local model markdown 评估、SQLite 评分与改进项都要同步更新。

### 已知问题记录

2026-06-05：在 Codex/headless 沙箱中直接启动 Rapid-MLX 失败，日志为 `No Metal device available`。这是当前进程无法访问 macOS Metal GPU，不是模型文件路径错误。

正确处理：

- 首先复用已常驻的 `http://127.0.0.1:8000/v1`。
- 如果服务未启动，从普通 macOS Terminal/user session 启动 Rapid-MLX。
- Codex 只检查 `/v1/models`、`/docs`、`/chat/completions`，不要假设自己一定能在沙箱里加载 MLX。

### 下一步产品能力

- `scripts/review_pr.py`：自动 checkout PR、跑 local review、保存 Codex 输入材料。
- `scripts/post_review.py`：只负责用 `clestons` 发布已确认文案。
- Review history：继续扩展到记录每个 PR 的最终 comment、发布时间和 GitHub review 状态；本地模型评分与改进项已先落到 SQLite。
- Local challenge API：把 Codex finding 列表交给 `qwen3.6-a3b` 做结构化反驳。

---

## English Version

### Product Positioning

PR-Daemon is a Codex skill project for PK-style pull request review. It is designed to fully use the free local Apple Silicon compute and a resident local model named `qwen3.6-a3b`. Rapid-MLX loads the model and exposes an OpenAI-compatible API. The local model handles broad, cheap, high-volume work such as first-pass review, summarization, challenge rounds, and review comment drafting. Codex handles the hard senior-review work and is accountable for the final verdict.

Default rules:

- Review only; do not modify the PR branch.
- Never directly modify local business repository code. Local checkouts are review context only.
- Temporary diff/report files are allowed outside business repos. If temporary files must be created inside a business repo, they must live under explicit temporary/ignored paths and must not modify source, config, tests, or lock files.
- Generate local review text first; do not post to GitHub by default.
- Post comments, approve, or request changes only after explicit user approval.
- Treat local model output as useful hypotheses, not final truth. Codex must verify final findings with code, diffs, tests, or reproducible reasoning.

### Account Roles

- Primary account: `jhfnetboy`
  - Discovers open PRs authored by `jhfnetboy`.
  - Maintains repositories and the main PR queue.
  - This should remain the default active account.
- Review account: `clestons`
  - Email: `clestons@gmail.com`.
  - Posts PR review comments, approvals, or request-changes reviews.
  - `gh auth switch --user` expects a GitHub login, not necessarily an email address.

Always verify identity before posting. After posting, switch back to the primary account:

```bash
gh auth status
gh api user -q .login
```

Restore the default primary account:

```bash
bash scripts/ensure_main_github_account.sh
```

Switch to the review account:

```bash
gh auth switch --hostname github.com --user clestons
gh api user -q .login
```

Switch back to the primary account:

```bash
gh auth switch --hostname github.com --user jhfnetboy
gh api user -q .login
```

GitHub CLI can store multiple accounts for the same host, but only one account is active at a time. After logging in the review account, use `gh auth switch`.

Recommended login flow in a normal Terminal:

```bash
gh auth login --hostname github.com --web --git-protocol https
gh auth switch --hostname github.com --user clestons
gh api user -q .login
```

For token login, avoid sending the token in chat. Use stdin locally:

```bash
pbpaste | gh auth login --hostname github.com --with-token
gh auth switch --hostname github.com --user clestons
```

A classic token needs at least `repo`, `read:org`, and `gist`. A fine-grained token needs metadata read, contents read, and pull requests read/write for the target repo; for automation, prefer `GH_TOKEN=... gh ...` for one command if needed.

You can also use a local `.env` file so the global `gh` credential store does not need to switch accounts every time:

```bash
cp .env.example .env
```

Then set:

```bash
PR_DAEMON_REVIEW_USER=clestons
PR_DAEMON_REVIEW_TOKEN=github_pat_xxx
```

`.env` is ignored by Git. The posting script uses `GH_TOKEN=$PR_DAEMON_REVIEW_TOKEN` for a single GitHub API command, while the default active account remains `jhfnetboy`.

Multi-organization review token rules:

- A fine-grained PAT can target only one resource owner, so it is not suitable for one token spanning `AAStarCommunity`, `AuraAI`, and `mycelium`.
- For one token across all three organizations, the short-term option is a classic PAT from `clestons`, assuming all three organizations allow classic PAT access.
- Recommended classic PAT scopes: `repo`, `read:org`, `gist`. PR review does not require `admin:org`.
- Do not make `clestons` an org admin only for token convenience. Add `clestons` to the organizations and grant sufficient repository permissions for review, usually write/maintain.
- Long-term, a GitHub App installed in all three organizations is cleaner and more auditable, with Pull requests write / Contents read / Metadata read permissions.

The PR-Daemon posting script temporarily switches to `clestons`, posts the review, and switches back to `jhfnetboy`:

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /path/to/review.md \
  --request-changes
```

### Resident Local Model

Target API model name:

```text
qwen3.6-a3b
```

Current Rapid-MLX check on this machine:

- `rapid-mlx` is installed.
- Nothing is currently listening on `localhost:8000`, so `/docs` and `/v1/models` are not available until the server starts.
- The current Rapid-MLX alias list does not include `qwen3.6-a3b` as a loader alias.
- Available qwen3.6 loader aliases include `qwen3.6-27b`, `qwen3.6-27b-8bit`, `qwen3.6-35b`, `qwen3.6-35b-6bit`, and `qwen3.6-35b-8bit`.

Default project behavior:

- API served model name: `qwen3.6-a3b`
- Rapid-MLX default loader alias: `qwen3.6-35b-6bit`
- This alias uses Rapid-MLX/Hugging Face cache resolution.
- To load from `~/.omlx/models`, explicitly set `RAPID_MLX_LOAD_MODEL` to the local path.

If you want the 6bit model visible under `~/.omlx/models`, expose the Hugging Face cache snapshot there. Symlink mode is recommended because it does not duplicate 27GB of weights:

```bash
scripts/materialize_omlx_model.sh
```

The script copies from:

```text
~/.cache/huggingface/hub/models--mlx-community--Qwen3.6-35B-A3B-6bit/snapshots/<hash>
```

to:

```text
~/.omlx/models/Qwen3.6-35B-A3B-MLX-6bit
```

Then it validates the local path with `rapid-mlx info`. Symlink mode depends on the HF cache, so do not remove the original cache.

Start with the OMLX path:

```bash
export RAPID_MLX_LOAD_MODEL="$HOME/.omlx/models/Qwen3.6-35B-A3B-MLX-6bit"
scripts/rapid_mlx_daemon.sh ensure
```

If you want a real copy under `~/.omlx/models` and then remove the HF cache copy:

```bash
scripts/materialize_omlx_model.sh --copy
```

After copy-mode validation:

```bash
rapid-mlx rm mlx-community/Qwen3.6-35B-A3B-6bit
```

If a real `qwen3.6-a3b` alias or HF path becomes available locally:

```bash
export RAPID_MLX_LOAD_MODEL=qwen3.6-a3b
export RAPID_MLX_MODEL=qwen3.6-a3b
```

Start or ensure the resident server:

```bash
scripts/rapid_mlx_daemon.sh ensure
```

Check it:

```bash
scripts/rapid_mlx_daemon.sh status
scripts/rapid_mlx_daemon.sh models
scripts/rapid_mlx_daemon.sh docs
scripts/rapid_mlx_daemon.sh smoke
```

If Codex/headless cannot access Metal, start the resident model from a normal Terminal:

```bash
scripts/start_rapid_mlx_resident.sh
```

Equivalent manual command:

```bash
rapid-mlx serve qwen3.6-35b-6bit \
  --host 127.0.0.1 \
  --port 8000 \
  --served-model-name qwen3.6-a3b \
  --prefill-step-size 4096 \
  --gpu-memory-utilization 0.85 \
  --enable-prefix-cache
```

API endpoints:

```text
Docs: http://127.0.0.1:8000/docs
Models: http://127.0.0.1:8000/v1/models
Chat completions: http://127.0.0.1:8000/v1/chat/completions
```

### Normal Usage

Ask Codex from this directory:

```text
Use $rapid-mlx-review. Ensure the local Rapid-MLX model is available, find open PRs authored by jhfnetboy, pick the next review target, make qwen3.6-a3b do the broad first pass and challenge rounds, then Codex performs final adjudication and owns the result. Do not edit the PR branch. Generate review comments locally first; do not post unless I explicitly approve posting with clestons.
```

Review a specific PR:

```text
Use $rapid-mlx-review to review OWNER/REPO#123 in PK mode. Use qwen3.6-a3b heavily through Rapid-MLX for triage, initial findings, challenge, and comment drafting. Codex makes the final call. Do not modify code.
```

Review the current repo diff:

```text
Use $rapid-mlx-review to review this repository. Compare against origin/main, include worktree changes if relevant, run local qwen3.6-a3b first, then Codex adjudicates.
```

### Open PR Discovery

Do not rely on `@me`, because the active GitHub account may be `clestons`. Discover the queue with explicit author filtering:

```bash
python3 scripts/list_open_prs.py
python3 scripts/list_open_prs.py --repo OWNER/REPO
python3 scripts/list_open_prs.py --json
```

Underlying command:

```bash
gh search prs \
  --author jhfnetboy \
  --state open \
  --json number,title,repository,url,updatedAt,isDraft,author \
  --limit 50
```

`prbot` can be used as a human dashboard:

```bash
prbot all
prbot OWNER/REPO
```

The automated review queue should use `scripts/list_open_prs.py` or explicit `gh search prs --author jhfnetboy`.

### Local Repo Mapping

PR review should not clone to `/tmp` by default. Resolve local checkouts by organization first:

| GitHub owner / org | Local root |
|--------------------|------------|
| `AAStarCommunity` / `aastar` | `~/Dev/aastar` |
| `AuraAI` / `auraai` | `~/Dev/auraai` |
| `mycelium` | `~/Dev/mycelium` |

Config file:

```bash
config/repo-roots.json
```

Add or update a mapping:

```bash
python3 scripts/add_repo_root.py OWNER ~/Dev/path --alias short-name
```

Resolve a repo:

```bash
python3 scripts/resolve_repo.py AAStarCommunity/AirAccount
```

Rules:

- If the repo exists under the mapped root, use that checkout.
- If it is missing, clone into the mapped root, for example `~/Dev/aastar/AirAccount`.
- `/tmp` is only for short-lived diff files, not normal PR checkouts.
- Whether Codex can `git fetch`/checkout inside these roots depends on this session's writable roots. In the current session, only PR-Daemon and `/tmp` are writable, so external repos are read-only. Add those directories as workspace/writable roots in the next session if Codex should update them directly.
- Even if these directories are writable roots, modifying business code is still forbidden. Write access is only for `git fetch`, checking out review refs, reading indexes, and producing temporary review artifacts.

Recommended workspace/writable roots when starting Codex:

```text
/Users/jason/Dev/tools/PR-Daemon
/Users/jason/Dev/aastar
/Users/jason/Dev/auraai
/Users/jason/Dev/mycelium
```

The same list is recorded in:

```bash
config/workspace-roots.txt
```

These roots must be loaded by Codex/the client when starting a new session. The current session cannot dynamically expand sandbox writable roots.

If using Codex CLI, run from a normal Terminal:

```bash
cd /Users/jason/Dev/tools/PR-Daemon
bash scripts/start_codex_pr_daemon.sh
```

Equivalent manual command:

```bash
codex \
  --cd /Users/jason/Dev/tools/PR-Daemon \
  --sandbox workspace-write \
  --add-dir /Users/jason/Dev/aastar \
  --add-dir /Users/jason/Dev/auraai \
  --add-dir /Users/jason/Dev/mycelium
```

`[projects] trust_level` in `~/.codex/config.toml` means the project is trusted; it does not make the directory writable in the current session. Extra writable roots must be supplied with `--add-dir` or the client startup settings.

### PK Review Division Of Labor

The local `qwen3.6-a3b` model should do as much work as possible:

- PR queue summaries and priority suggestions.
- First-pass diff review and risk enumeration.
- Per-file context summaries.
- Questions about suspicious code paths.
- Reverse challenge against Codex findings.
- Final review comment drafts.
- Fix and test suggestions.

Codex handles the difficult and accountable work:

- Independently read the diff and critical context.
- Decide whether local findings are real.
- Find high-risk issues in security, concurrency, data loss, permissions, supply chain, API contracts, and CI configuration.
- Judge severity, business impact, and potential loss.
- Decide whether the review should request changes.
- Own the final output.

### Standard Workflow

1. Select PR
   - Fetch open PRs authored by `jhfnetboy`.
   - Skip drafts by default.
   - Prioritize recently updated, high-risk, broad-impact, or review-requested PRs.

2. Prepare diff
   - Checkout or fetch the PR.
   - Use the PR base branch; default to `origin/main` if unclear.
   - Generate a merge-base diff.

3. Local Round
   - Ensure the Rapid-MLX resident server is available.
   - Run `qwen3.6-a3b` first:

```bash
python3 skills/rapid-mlx-review/scripts/local_review.py \
  --repo TARGET_REPO \
  --base origin/main \
  --target HEAD \
  --model qwen3.6-a3b \
  --output /tmp/rapid-mlx-local-review.md
```

4. Codex Deep Round
   - Codex does not trust local output first.
   - Independently reads the diff, relevant files, call paths, and config.
   - Runs feasible tests or static checks.

5. Challenge Round
   - Codex adjudicates local findings.
   - For complex findings, ask the local model to challenge once more.
   - Stop after two challenge rounds unless the user asks for more.

6. Final Review
   - Output confirmed/codex-only/rejected findings.
   - Include impact, potential loss, fix, and PR comment text.
   - Do not post by default.

### Output Format

```text
Findings

[Confirmed] High - path/to/file.py:123 - title
Evidence:
Impact:
Potential loss:
Fix:
Suggested PR comment:

[Codex-only] Medium - path/to/file.ts:45 - title
Evidence:
Impact:
Potential loss:
Fix:
Suggested PR comment:

Rejected Local Findings
- Finding title: rejected reason.

Local Model Work
- Triage:
- Useful findings:
- Missed:
- Overreached:
- Challenge result:

Verification
- Commands run:
- Tests not run:

Posting
- Current GitHub account:
- Posting status: not posted / posted by clestons
```

### Posting Comments

Do not post by default. After explicit approval:

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /tmp/pr-review-final.md \
  --comment
```

To block the PR:

```bash
bash scripts/post_pr_review.sh \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --body-file /tmp/pr-review-final.md \
  --request-changes
```

Before posting, confirm:

- The current account is the review account.
- Repo and PR number are correct.
- The user explicitly allowed posting.
- Codex has verified and accepted responsibility for final findings.

### Current Files

- Skill: `skills/rapid-mlx-review/SKILL.md`
- Local first-pass script: `skills/rapid-mlx-review/scripts/local_review.py`
- Rapid-MLX resident server script: `scripts/rapid_mlx_daemon.sh`
- Normal Terminal resident start script: `scripts/start_rapid_mlx_resident.sh`
- Open PR queue script: `scripts/list_open_prs.py`
- Safe review posting script: `scripts/post_pr_review.sh`
- Local repo resolver: `scripts/resolve_repo.py`
- Local repo mapping add script: `scripts/add_repo_root.py`
- Local repo mapping: `config/repo-roots.json`
- GitHub account config: `config/accounts.json`
- Main account restore script: `scripts/ensure_main_github_account.sh`
- Local model evaluation SQLite recorder: `scripts/model_eval_db.py`
- Local model evaluation database: `reviews/model-evals/model-evals.sqlite`
- Reference tool: `prbot`

### Local Model Evaluation History

After every PR review that uses `qwen3.6-a3b`, record two outputs:

- Markdown record: save a human-readable score, contribution, false positives, misses, prompt gaps, and Codex adjudication under `reviews/model-evals/`.
- SQLite record: use `scripts/model_eval_db.py record-run` to write the score, model behavior, whether previous improvement items actually helped, and next prompt improvements into `reviews/model-evals/model-evals.sqlite`.

When re-reviewing the same PR, `skills/rapid-mlx-review/scripts/local_review.py` can load prior improvements with `--eval-db reviews/model-evals/model-evals.sqlite --owner OWNER --repo-name REPO --pr-number N` and inject them into the local-model prompt. Codex must still independently verify the local output; SQL history is for continuous local-model improvement, not final authority.

The local model is most useful for:

- First-pass triage across many PRs: summarize the diff, risk areas, and files Codex should inspect deeply.
- Repetitive checks: verify prior review findings, adversarial examples, and test checklists.
- Security gate / grep / config review hypothesis generation, especially enumerating valid input forms and producing truth tables.
- Review recordkeeping: structure local findings, Codex adjudication, false positives, misses, score, and next improvement items.
- Draft review comments that Codex rewrites or rejects before posting.

It is not trusted as the final reviewer for security boundaries, concurrency/state machines, cross-module contracts, chain/TEE behavior, or CI gate correctness. Codex must independently inspect diffs, run verification commands, and mark local output as confirmed, rejected, missed, or Codex-only.

### Local Model Feedback Loop

Every review follows the same loop:

1. The local model runs a broad pass with open SQL improvement items injected.
2. Codex independently reviews the diff and verifies each finding and carried-forward improvement.
3. Codex scores the local model from 0-10 and records useful findings, false positives, misses, and prompt gaps.
4. `scripts/model_eval_db.py record-run` stores the score and next improvement items.
5. `scripts/model_eval_db.py assess-item` marks whether previous improvements worked:
   - `effective`: it improved behavior; stop carrying it.
   - `ineffective`: it did not improve behavior; keep carrying it with stronger constraints.
   - `needs_followup`: partial improvement; verify again next run.
   - `retired`: no longer relevant.
6. The next review injects only `carried_to_next=1` items, keeping prompt history focused.
7. `scripts/model_eval_db.py scorecard` reports recent scores, item status, and open issues so improvement is measured rather than assumed.

Improvement is effective only when observable quality improves:

- Fewer repeated misses.
- Fewer false positives.
- Better compliance with required output sections and truth tables.
- Correct execution of carried-forward improvement items.
- Fewer Codex-only blockers.
- Faster final GitHub review with less rework.

### Review Completion Contract

Every PR review is complete only when all three conditions are true:

- There is an explicit conclusion: `APPROVE`, `REQUEST_CHANGES`, or a non-blocking `COMMENT`.
- The corresponding review/comment has been posted to the GitHub PR. If posting fails, record the failure reason and fix the posting path.
- Local records are updated: review body, local-model markdown evaluation, SQLite score, and improvement items.

### Known Issue Log

2026-06-05: Starting Rapid-MLX directly from the Codex/headless sandbox failed with `No Metal device available`. This means the current process cannot access the macOS Metal GPU; it is not a model path problem.

Correct handling:

- Reuse the resident `http://127.0.0.1:8000/v1` server first.
- If the server is not running, start Rapid-MLX from a normal macOS Terminal/user session.
- Codex should check `/v1/models`, `/docs`, and `/chat/completions`; it should not assume it can load MLX inside the sandbox.

### Next Product Capabilities

- `scripts/review_pr.py`: checkout PR, run local review, and save Codex input materials.
- `scripts/post_review.py`: post only confirmed review text through `clestons`.
- Review history: continue extending final comment, posting time, and GitHub review state tracking; local-model scoring and improvement items now live in SQLite.
- Local challenge API: send Codex findings back to `qwen3.6-a3b` for structured rebuttal.
