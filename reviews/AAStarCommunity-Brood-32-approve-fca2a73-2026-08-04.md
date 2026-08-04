## 结论：✅ APPROVE

两处独立 bug 修复,均可从 diff 直接验证,逻辑正确、影响面已核查清楚:

1. **`status.md` 补 ensure-daemon 步** — `SKILL.md` 的 `doctor` 第 6 步早已承诺「status 阶段会自动拉起 PR-Daemon」,但 `phases/status.md` 此前的步骤里确实没有任何一步执行这件事(已核对 origin/main 上的旧版本)。新增第 4 步调用的 `scripts/ensure-pr-daemon.sh ensure` 脚本**已存在**(非本 PR 新增的悬空引用,已用 `git show origin/main:...` 确认),幂等、只在未运行时拉起,用 `pgrep -f 'review_watch\.py'` 判活,对 SIGPIPE-under-pipefail 有防护。修复真实、落地正确。

2. **`repo-scan.sh` dirty 排除未跟踪** — 原先 `dirty_count` 用 `git status --porcelain`(含 `??` 未跟踪行),与 `untracked_count` 重叠,单个新文件会同时计入 dirty=1 和 untracked=1。改为 `--untracked-files=no` 后两者互斥。已核查全 `plugins/pilot/skills/pilot/` 树:没有其他文件程序化消费 `dirty_files=`/`untracked_files=` 这两个 key;`run.md` 自己的"是否有未提交改动"判断、`safe-cleanup.sh` 的脏 worktree 门禁都各自独立跑原始 `git status --porcelain`(后者保守地包含未跟踪),不依赖 repo-scan.sh 的输出,因此这次改动不会削弱现有的安全门禁。已实测验证(worktree 中跑 PR head 的 repo-scan.sh):有 remote 场景下,单个未跟踪文件从改前的 `dirty=1+untracked=1` 变为改后的 `dirty=0+untracked=1`,行为符合 PR 描述。

3. 版本号 `plugin.json`/`SKILL.md` 1.0.0→1.0.1 同步,`status.md` 步骤重编号(4→7)内部自洽,全树无「status 第 N 步」式外部引用会因重编号而失效。

## 4 轮全流程结果

- **R1a (DeepSeek-full)**: 1 条 `[Low]` — `status.md:17` 的 `<skill>` 占位符「未展开」。核查后确认是同文件既有约定(第 11/34 行未改动处同款用法),非本 PR 引入,R2/R4 均已驳回。
- **R1b (DeepSeek-security)**: 无发现,diff 无安全相关 surface(纯文档指令 + 只读 shell 计数脚本)。
- **R2 (Opus 独立战略读)**: 新增 2 条 `[Low]`:
  - `status.md:21` 括号写"根目录取 `.pilot.yml` 的 `pr_daemon_root`",但示例命令未传 `--root`,而 `ensure-pr-daemon.sh` 不解析 YAML,只认 `--root`/环境变量/默认路径 —— 配了非默认 `pr_daemon_root` 又没设环境变量的仓库,按文照做会落到默认路径导致 `exit 2 not found`,被误判为"拉起失败"。经核查,`run.md`/`SKILL.md` 里另外三处对同一脚本的调用写法完全相同,是既有约定的复制,不是本 PR 独有问题。
  - `status.md:17` status 阶段声明"只读优先",新第 4 步无条件、无 opt-out 地拉起一个跨仓库对外发 GitHub review 的常驻后台进程,副作用超出单仓库范围。可接受(README 已把外部 review 回路写成 pilot 的设计前提,脚本幂等且从不 kill),建议后续加 `.pilot.yml` 开关。
  - 战略核查:确认改动无跨文件破坏(见上文第 2 点)。
- **R3 (Codex PK)**: **跳过** — post-R2 全部为 Low,按 gate 规则直接进入 R4。
- **R4 (Opus 最终裁决 + 全量补扫)**: APPROVE。用 worktree 实测验证了改动行为、`ensure-pr-daemon.sh` 存在性、版本号无残留漂移。补扫发现一条**与本 PR 无关的既有 bug**(非阻塞,仅供参考):`repo-scan.sh:52` 的 `remote_count` 在 `set -euo pipefail` 下,若仓库无任何 remote ref,`grep -v 'HEAD$'` 无匹配返回 1 → pipefail 导致整条命令替换 rc=1 → `set -e` 直接中止脚本,status 第 2 步拿不到任何输出也看不到报错。该行本 PR 未改动,建议后续单独修:`| { grep -v 'HEAD$' || true; }`。

## Suggestions(非阻塞)

- 第 5 步"是否有未提交改动"的措辞未随 dirty 语义收窄同步更新;建议改成"未提交改动 N 个(另有未跟踪 M 个)",避免只看 `dirty_files=0` 就误报"工作区干净"。
- 长期看,第 4 步把作者本机路径 `~/Dev/tools/PR-Daemon` 钉进 pilot 的**默认** status 流程;其他安装者跑起来必然 `exit 2 not found`,建议做成 `.pilot.yml` 里的 opt-in 能力而非默认开启。
- (供后续单独 PR 参考)`repo-scan.sh:52` 无 remote 仓库场景下的 pipefail 崩溃,见上文 R4 补扫。

---
*Reviewed by clestons via PR-Daemon v4 pipeline (DeepSeek R1a+R1b dual-pass → Opus R2 independent strategic review → Codex R3 skipped post-R2-all-Low → Opus R4 final verdict + full-diff missed-finding scan with worktree-based mechanical verification).*
