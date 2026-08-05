## Verdict: REQUEST_CHANGES（增量复审，head `91faca9`，round 5）—— **只剩两条，各 2-4 行，其余全部通过**

先说清楚：**我 round-4 的 5 条 blocking + 2 条历史遗留，全部真修了，而且三条最难的我用 PR#36 自己在真实数据上证明了。**

拿新的 `pr-monitor.sh` 跑这个 PR（它此刻正好带着一条钉在 `6fa670c` 的过期 review）：
```
verdict=PENDING  raw_decision=CHANGES_REQUESTED  head_sha=91faca9  review_sha=6fa670c
wait_min=10  age_min=919  mergeable=MERGEABLE  checks=SUCCESS,SUCCESS,SUCCESS,SUCCESS
```

| round-4 的问题 | 现在 |
|---|---|
| B1 过期裁决与新鲜裁决无法区分 | ✅ `head_sha`/`review_sha` 都吐出来，`verdict` 由两者是否相等推导 |
| B2 规定的 Monitor 调用产生不了那个节奏，30 分钟上限永不触发 | ✅ `--wait-for-verdict` 在 pending 时保持静默；`--max-min 0` 正确 exit 3 并打 TIMEOUT |
| B3 `age_min` 是 PR 年龄，复审轮一开始就超时 | ✅ 同一个 PR 上 `wait_min=10` vs `age_min=919`，两个字段确实各说各的事 |
| B4 两个 manifest 还在卖已删除的 daemon 集成 | ✅ 零 grep 命中 |
| B5 `goal.md` 缺 30 分钟硬上限 | ✅ 补上了，还加了「只有评审 commit == 当前 head 才算裁决」 |
| 遗留① `SCAN_DIRS` 漏 `backlog/milestones`（开了 4 轮） | ✅ 修了**并且我实证**：种一个 title 带未加引号 `:` 的 milestone，checker 抓住了 |
| 遗留② `pre-pr-review.md` 被两个脚本引为规范却不存在 | ✅ 建了，我逐条核对了它对脚本的描述（GRADE/ROUNDS 取值、恒 exit 0、戳记的 `grade=` 行、`PILOT_SKIP_PREFLIGHT` 在 `git-guard.sh:131` 的 stderr 警告）|

另外实证：`npm run build` 后 `dist/` **与提交的零差异**（可复现守卫成立）；`preflight.sh run` **3/3 通过**，戳记 HEAD `91faca9` grade A；全 skill **零悬空引用**；我那条「`$VAR` 后紧跟中文」的 bash 3.2 地雷**零命中**。`export-backlog.js` 的 `.sort()` 正确且必要。

**卡住的只有两条，而且是同一个形状：这个 PR 自己新加的守卫，在畸形输入下不是拒绝，而是「永远卡住」或「静默放行」—— 正是 `pre-pr-review.md` 自己论证的那件事。**

### 🔴 Blocking（2 条，合计约 4 行）

1. **[Med] `scripts/pr-monitor.sh:53-59` — `--pr` 或 `--max-min` 作为最后一个参数时，脚本进入静默死循环。**
   `shift 2` 在 `$#=1` 时返回非零且**什么都不 shift**；而本轮把 `:38` 从 `set -euo pipefail` 改成了 `set -uo pipefail`，于是没有任何东西中止它，`$#` 永远减不下去。
   **实测**：`pr-monitor.sh --pr` → 5 秒后仍在跑，**零输出**，进程不退。
   为什么这条要拦：`goal.md` 现在明确指示无人值守的 agent 跑 `pr-monitor.sh --pr <n> --wait-for-verdict` —— `<n>` 是个占位符，一旦模板没填上就是**通宵循环里一个静默的忙等死锁**；而且它发生在 `--max-min` 上限被读到**之前**，等于绕过了这个 PR 专门为「防永久等待」加的那道闸。
   ```bash
   --pr)      [ $# -ge 2 ] || { echo "ERROR: --pr needs a number" >&2; exit 2; }; pr="$2"; shift 2 ;;
   --max-min) [ $# -ge 2 ] || { echo "ERROR: --max-min needs a number" >&2; exit 2; }; max_min="$2"; shift 2 ;;
   *)         echo "ERROR: unknown arg $1" >&2; exit 2 ;;
   ```
   （顺带：`set -e` 是为了让 `report_one` 失败不打断轮询才去掉的，这个取舍没问题；但它意味着这个文件里**每个新循环都得自带终止性证明**，值得在文件头写一句，免得第六轮再犯。）

2. **[Med] `scripts/grade-change.sh:40-56` — base ref 解析不了时 fail-open，A 类改动被判成 D。**
   `$base` 既不是本地分支也不是 `origin/$base` 时 `mb=""`，于是**所有已提交的改动都看不见**，只剩工作区/未跟踪文件参与判定。
   **实测**（同一个分支、同一个改 `.github/workflows/` 的 commit）：
   ```
   --base main     → GRADE=A  ROUNDS=3  REASON=touches .github/workflows/evil.yml
   --base preview  → GRADE=D  ROUNDS=0  REASON=no changes detected vs origin/preview
   ```
   而 Brood 自己的集成分支就叫 `preview` —— 新 clone、worktree、或没 fetch 到 `origin/preview` 的环境里就会踩到。这个 grade 正是 `preflight.sh` 写进戳记、`git-guard.sh pr-create` 打印出来的那个，于是 A 类改动的 3 轮自审要求**静默消失**。这正是该文件自己 header 里论证要避免的 fail-open 形状。
   **修法**：base 解析不出来时给 `GRADE=A`（或 exit 2），**绝不能**落到「no changes detected」。

### 非阻塞（建议后续，不拦合并）

- **[Med] `pr-monitor.sh` 的 python 段** — 新鲜度只按 `commit_id` 过滤，**不看 review state**。当前 head 上任何一条 `COMMENTED` 或 `DISMISSED`（加一条行内评论就会产生一条）都会让一个过期的 `CHANGES_REQUESTED` 报成新鲜 —— 就是 B1 的窄化版。修：`[-1]` 之前先过滤 `state in ("APPROVED","CHANGES_REQUESTED")`。
- **[Low] `pr-monitor.sh:135-150`** — wait 模式下，PR 号写错/已关闭与「还没裁决」不可区分：`report_one` 返回 1、`out=""`，调用方等满 30 分钟后打出 TIMEOUT 加一句自信但错误的「没有评审服务覆盖本仓库」。建议首次 `report_one` 失败就 fail fast。
- **[Low] `pr-monitor.sh:40-47`** — `python3` 没像 `gh` 那样做存在性检查；`--max-min` 非数字会在 `$(( ))` 处于 `set -u` 下杀掉 shell，**stdout 为空且 exit 0** —— 而脚本自己的退出约定把 exit 0 读成「打印了新鲜裁决」。另建议 `--wait-for-verdict` 缺 `--pr` 时报错，而不是静默退化成列全部。
  （R1a 提的「`--max-min` 未校验」方向对但抓错了点：负数/0 是良性的立即 TIMEOUT + exit 3，真正的缺陷是**非数字 → 静默 exit 0**。）
- **[Low] `scripts/ci/check-task-yaml.py:25-28`** — 补了 `backlog/milestones`，但仍漏 **`backlog/completed`**，而 `export-backlog.js:529-596` 会读它、用**正则**（不是 YAML）解析并合进 `dist/api/tasks.json` 和 `search.json`。那里畸形的 frontmatter 正好产出这道闸要防的「空记录 + 原始 markdown」。实测：坏文件放 `backlog/completed` → rc=0；同一个文件放 `backlog/milestones` → rc=1。目前该目录是空的所以只是潜在。而紧挨着的注释仍写着「导出器会读的每一个目录」。
- **[Low] `pre-pr-review.md` 与 `grade-change.sh` 三处描述不符**：(a) 表里没有 `ROUNDS=0` 这一档，但代码在「no changes detected」时确实输出 `GRADE=D ROUNDS=0`；(b) 文档说「取最高命中」且 B = >100 行**或** ≥3 个顶层区域，但代码先测 D 再测 B —— 实测 300 行跨 5 个顶层目录的纯 `.md` 得到 `GRADE=D ROUNDS=1` 而非 B/3；(c) 文档说「除用法错误外恒 exit 0」，代码在「不是 git 仓库」时也 exit 2。其余逐条属实。
- **[Low] `README.md:17`** — 仍写着被取代的节奏「`scripts/pr-monitor.sh`，3–5 分钟一次」，正是 B2 证明产生不了的那个调用方式；`review-contract.md`/`goal.md`/`run.md` 都改了，README 漏了。`README.md:94` 的脚本树也只列了 3 个脚本，漏了 `git-guard.sh preflight.sh grade-change.sh check-docs.sh check-hooks.sh followups.sh`。
- **[Low] `grade-change.sh:59`** — `/tmp/pilot-graded-files.$$` 是可预测路径，`>` 重定向会跟随预先放好的符号链接。`mktemp` 一行解决，而这个脚本按它自己的规则就是 A 类。
- **[Low] `preflight.sh:66-70`** — `npm run build` 被当作「检查」自动发现，但它是**会改文件**的检查（重写 `dist/`）。`pr-create` 只校验戳记的 sha、从不校验工作区干净，所以戳记可能证明「HEAD X 的检查通过了」而 build 的新产物还没提交；目前只有 CI 的 `dist-reproducible` job 兜得住。本仓库今天无害（build 后零差异），换个仓库就是潜在的。

### 驳回

- **R1a「`--max-min` 未校验会导致立即超时或算术错误」** —— 负数/0 是良性的（立即 TIMEOUT、exit 3，作为一次性探针是合理行为）。真正的缺陷是非数字 → 静默 exit 0，已改列在上面。

### 为什么是 REQUEST_CHANGES 而不是 APPROVE

这个 PR 的净改进很大，7 条历史问题全部真修且可证明。**但我的 APPROVE 会直接触发合并**（main 要求一个非作者 approve，你自己 approve 不了），所以这一票等于放行。

上面两条都是「这个 PR 新加的守卫在畸形输入下不拒绝、而是永远卡住或静默放行」——**一条就在这个 PR 自己创造的无人值守路径上，且绕过了它自己新加的超时闸；另一条让它自己新加的 3 轮自审要求静默消失**。两条合计约 4 行。

推一次就能合。改完我立刻复审，只看这两处。

### Assumptions

- 在独立 worktree（head `91faca9`）里跑构建、preflight、变异与探针；所有对抗性实验在 scratchpad 下的一次性仓库里做，已删除。`~/Dev/aastar/Brood` 主 checkout 未改动（它在 `main` 上有 60 个 staged 文件，是你在途的工作，我没碰）。
- 增量范围 `6fa670c..91faca9`（3 commit，dist/ 外 525 行）；`research/` 下的调研文档不属于 pilot 逻辑，未逐字审。
- **R3(Codex PK) 未跑** —— 本会话内它已两次零输出挂起被杀。**R4 未跑** —— 两条阻断项都有我自己实跑的
  输出（死循环 5 秒复现、grade A→D 对照）。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `6fa670c`→`91faca9`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；1 条方向对但抓错点）→ Sonnet 机械验证（拿 PR#36 自己实测 pr-monitor 的
新鲜度判定与超时、种 milestone fixture 验 SCAN_DIRS、构建验 dist 零差异、preflight 3/3、
悬空引用与 CJK lint 全量扫描、复现 `--pr` 死循环与 grade-change 的 A→D fail-open）→
Opus R2（独立评审，挖出 arg 死循环、grade-change fail-open、review-state 未过滤，以及
`backlog/completed` 仍漏扫）→ **Codex R3 挂起未跑；R4 未跑**。*
