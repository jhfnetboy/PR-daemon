## Verdict: APPROVE（增量复审，head `3af4d53`，round 6）

**round-5 的两条阻断项都修好了，而且是 fail-closed，我逐个实证：**

| round-5 阻断项 | 上一轮 `91faca9` | 现在 `3af4d53` |
|---|---|---|
| `pr-monitor.sh --pr` 无值 → 静默死循环 | 5 秒后仍在跑，零输出 | 立即退出 `--pr requires a number (got '')` |
| `--max-min` 无值 / 非数字 / 未知参数 | 静默 exit 0 或死循环 | 全部 **rc=2** 并点名参数 |
| `grade-change.sh` base 解析不了 → fail-open | 同一个改 `.github/workflows/` 的 commit：`GRADE=D / ROUNDS=0 / no changes detected` | **rc=2**，拒绝信息直接点名失败模式：「Refusing to grade against a missing base — that silently downgrades to D」 |

**快乐路径逐条重验，零回归**（这是我每次重写后都会做的一步——不假设上轮验过的不变式还成立）：

- live 打 PR#36：`verdict=PENDING  raw_decision=CHANGES_REQUESTED  head_sha=3af4d53  review_sha=91faca9  wait_min=11  age_min=954  checks=4/4 SUCCESS`
- `--wait-for-verdict --max-min 0` → rc=3 + TIMEOUT 行
- `grade-change --base main`（含无 `.pilot.yml` 默认 main）→ `GRADE=A ROUNDS=3`
- `check-task-yaml` 全绿；`npm run build` → **dist/ 零差异**；`preflight.sh run` → 3/3，戳记 `3af4d53` grade A
- 零悬空 reference/script 路径；零 `$VAR` 后紧跟中文的 bash-3.2 地雷

**新的 review-state 过滤我拿真实 REST 载荷验过**（PR#36 的 6 条 review 全是 `CHANGES_REQUESTED`：kept=6、last=`91faca9`，与旧过滤结果一致）——也就是说它关掉了 `COMMENTED`/`DISMISSED` 造成的假新鲜，**同时没有引入假阴性**。

**调用点审计**：文档里每一处调用（`README:17`、`templates/goal.md:16`、`phases/run.md:73/154`、`reference/review-contract.md:26`）都只用 bare / `--pr <n>` / `--wait-for-verdict` / `--max-min`，所以「严格拒绝未知参数」不会打断任何现有调用方。

### round-5 非阻塞项的处理情况

**本轮一并收了**：review-state 新鲜度过滤、`backlog/completed` 进 SCAN_DIRS、README 的过时节奏。
**仍开着（建议一个 follow-up task，不必再开一轮）**：

- `pr-monitor.sh:92` 没有 `python3` 存在性检查（fail-closed 到 TIMEOUT/rc=3，确实很低）
- `grade-change.sh:80-81` 的 `/tmp/pilot-graded-files.$$` 可预测路径
- `pre-pr-review.md` 三处与脚本不符（本轮未触碰该文件）：没有 `ROUNDS=0` 这一档、D 在 B 之前判、"不是 git 仓库"也会 exit 2
- `preflight.sh:77-82` 把会改文件的 `npm run build` 当检查，而 `pr-create` 只校验戳记 sha、不校验工作区干净
- `scripts/ci/check-task-yaml.py:27` — `backlog/drafts` 仍不在 SCAN_DIRS，而 `/api/drafts` 是真被 `export-backlog.js:511` 抓取并发布的端点；和 `backlog/completed` 是同一个事故类别，只是目录现在是空的
- `pr-monitor.sh:69` 的 `-h` 用 `sed -n '2,30p'` 但头部注释到 37 行，帮助信息中途截断、也没展示退出码
- `grade-change.sh:58-65` 只认分支名且硬编码 `origin`：`--base origin/preview`（很自然的手误）、tag、SHA 都会硬失败并在报错里显示 `origin/origin/preview` 这种无意义 ref；remote 叫 `upstream` 的仓库直接不可用。建议报错前加一层 `git rev-parse --verify "$base^{commit}"` 兜底，或在错误文案里写明"只接受分支名"
- `grade-change.sh:54-56` 的注释说「本仓库集成分支就是 preview，新 clone 每次都会踩」——Brood 并没有 `.pilot.yml`，自动探测会落到 `main`，触发这个 bug 需要显式传 `--base preview`（`pre-pr-review.md:20` 确实是这么教的）。修复是对的，"每次都会"说过了

### 一条不要误读的

`git-guard.sh:148` 那 5 行是**纯报告，不是门禁**：`C|D` 和 `*)` 都落到 `exec gh pr create`，没有任何 gate 行为改变。它确实比之前好（空 grade 以前什么都不打印，现在多行/垃圾值会落进严格分支），也和 `reference/pre-pr-review.md:32`「只报告,不拦截」一致——但别把它读成一个强制修复。

### 为什么这次 APPROVE

这是一个 50 行的 commit，只做了被要求的两件事、没有夹带。两条阻断项都修在正确的层次，对我扔进去的每一种畸形输入都 fail closed，快乐路径完好。剩下的全是文体、文档一致性、或单机 hygiene——属于 follow-up task，不该再开一轮。

合并后记得跑 `install.sh --copy` 重装：全局那份 `~/.claude/skills/pilot/` 目前只是被我改成「不会再拉起 daemon」，`ensure-pr-daemon.sh` 和旧的 `reference/pr-review-loop.md` 还在，`grade-change.sh` / `preflight.sh` / `review-contract.md` / `pre-pr-review.md` 都还没有——重装才算真正对齐。

### Assumptions

- 在独立 worktree（head `3af4d53`）里跑构建、preflight、对抗性探针；一次性测试仓库建在 scratchpad 下并已删除。`~/Dev/aastar/Brood` 主 checkout 未改动。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— R2 独立判定 2-round，
  两条阻断项的修复都有我自己实跑的前后对照。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `91faca9`→`3af4d53`）：DeepSeek R1a+R1b
→ Sonnet 机械验证（两条阻断项的畸形输入前后对照、live 打 PR#36、build/preflight/悬空引用/CJK lint 全量重验）
→ Opus R2（独立评审，拿真实 REST 载荷验证新过滤未引入假阴性、审计全部文档调用点确认严格拒参不破坏调用方、
并指出 `git-guard.sh` 那 5 行是报告而非门禁）→ **Codex R3 挂起未跑；R4 未跑**。*
