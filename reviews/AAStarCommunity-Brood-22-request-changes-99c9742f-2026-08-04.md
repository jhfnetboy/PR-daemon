# AAStarCommunity/Brood#22 — REQUEST_CHANGES (round 3, incremental)

- PR: docs(context): L0/L1 ecosystem context refresh
- Head: 99c9742f1d2b785c8e1fa0abfd3d5a6bc12f0f28 (incremental re-review; prior head c53812d, prior verdict REQUEST_CHANGES)
- Pipeline: pr-daemon-loop v4, 4-round on the incremental diff (DeepSeek R1a+R1b → Opus R2 independent → Codex R3 PK in isolated worktree at 99c9742f → Opus R4 final)
- Posted: 2026-08-04 as clestons

## Prior round's 3 blocking findings — all fixed ✅

1. **`.claude/skills/sync-progress/SKILL.md`** dedup logic — was basename-only (collapsed `AAStarCommunity/Cos72` and `MushroomDAO/Cos72` into the same slug). Now compares normalized full `owner/repo` via a new `_norm_slug()` + `ORG_ALIASES` map. Verified: distinct repos with the same basename no longer collide.
2. **`orgs/mycelium/PROFILE.md` agent-speaker-relay owner** — was fixed in only 1 file last round, 8 others still said `MushroomDAO/agent-speaker-relay`. This commit touches 6 more files (`orgs/auraai/INTERFACES.md` ×2, `orgs/auraai/PROFILE.md`, `orgs/mycelium/INTERFACES.md`, `backlog/tasks/task-11`, `task-34`, `backlog/docs/doc-7`). `git grep "MushroomDAO/agent-speaker-relay"` at the new head (excluding `dist/`) returns zero hits.
3. **Stale `MushroomDAO/Agent-WeChat-SDK`** (repo renamed+moved to `iDoris-ai/iDoris-SDK`) — fixed in all 4 locations. Remaining mentions are correctly-phrased historical notes ("前 Agent-WeChat-SDK").

## Blocking — 1 new regression introduced by this exact commit

**[Medium] `docs/ECOSYSTEM_MAP.md:120`** — in the "iDoris.ai" repo table, all 12 rows have a `本地路径` (local-path) column formatted as `auraai/<repo>`, except the `agent-speaker-relay` row, which this commit changed from `auraai/agent-speaker-relay` to `iDoris-ai/agent-speaker-relay` — writing a GitHub org slug into a column meant to hold a local filesystem path fragment.

This directly contradicts the same file's own note ~13 lines above: "本地目录仍为 `~/Dev/auraai/`（物理目录名未改，约定映射到 iDoris-ai org）". Verified on disk: `~/Dev/auraai/agent-speaker-relay` exists; `~/Dev/iDoris-ai/` does not. It's the sole outlier among 13 rows — confirmed by both an independent Opus read and an adversarial Codex pass reading the actual checked-out files, and by a repo-wide sweep for the same conflation pattern in the other 7 files this commit touches (no other instances found — this is a one-off, not systemic).

Fix: revert that one cell to `auraai/agent-speaker-relay`. (The GitHub-org info is already correctly recorded elsewhere — `orgs/auraai/INTERFACES.md` and `PROFILE.md`.)

## Non-blocking suggestions

- **[Low, unfixed 3rd round running] `docs/dashboard.html`** — 4 stale `AuraAIHQ/...` links (lines 333/344/354/364). Not a 404 (GitHub still redirects the renamed org), so below the blocking bar. Correction to how this was framed in earlier rounds: this file is **hand-maintained source** that `scripts/export-backlog.js` copies byte-for-byte into `dist/docs/` — it will not self-heal on a rebuild. Please fix in this PR or file a follow-up so it doesn't lapse a 4th time.
- **[Low, theoretical]** `sync-progress/SKILL.md`'s content-scan regex (`github\.com/([^/\s]+)/([^/\s'"]+)`) doesn't exclude trailing punctuation (`)` `,` `。`), so an inline markdown-link-style URL would miss the dedupe match. Checked: zero live instances in `backlog/tasks/*.md` today — all references use quoted/plain YAML list URLs, which this regex already handles. Robustness gap, not a live bug.
- **[Low, pre-existing, unrelated to this commit]** `docs/ECOSYSTEM_MAP.md` heading says "全部仓库（12 个）" but the table lists 13 rows — predates this commit (confirmed via `git show c53812d`), internal-precision nit only.

## R1 (DeepSeek dual-pass)

Security clean (R1b). R1a's full pass raised 2 items on the SKILL.md regex — both verified as false positives / non-issues: the flagged `_m.group()` call is inside a ternary (`X if _m else Y`), so it can't execute on a None match (this is the third time across rounds R1a has misread this exact ternary as a sequential statement); the second flagged a punctuation-in-regex concern that, per Codex's grep, has no live instance in this repo's content. R1a did not surface the round's actual blocking finding (the ECOSYSTEM_MAP.md regression) — that required cross-referencing the same file's own stated convention, outside single-hunk diff review.

## Self-assessment

- 轮数: 实际跑了 4 轮 (R1a+R1b DeepSeek 并行 → Opus R2 独立读增量diff+交叉验证3条前序finding → Codex R3 隔离worktree对抗挑战 → Opus R4 最终裁决)。触发文件仍含 automation-consumed 的 SKILL.md，4-round 沿用正确，不是虚标。一致 ✅
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 先在**错误**的全量 diff 上跑了一次（session 中途丢失了"这是第3轮增量复审"的上下文，重新 fetch 了 base..head 全量 diff），发现后立刻纠正——重新拉取正确的增量 diff（c53812d..99c9742f，7 files, 3003 tokens）并在其上重跑 R1a+R1b。两次运行中 R1a 都对同一处三元表达式给出同样的假阳性 panic claim（本session内验证：写了独立 Python 脚本跑 4 组输入验证 ternary 短路正确，两轮都排除）。R1b 两次均判定 security-clean，零假阳性。
  · R2 Opus: 独立读了增量 diff（虽然由于 prompt 里模板占位符 `{INCREMENTAL_DIFF}`/`{R1_MERGED}` 未被替换成实际内容——我的失误，字符串插值没做——R2 实际是靠自己的 Bash 工具直接读了 git 对象在 99c9742f 现场核实，反而更权威）。逐条核对了前序3条 blocking finding 的修复状态，并独立发现了本轮唯一新 regression（ECOSYSTEM_MAP.md:120 路径列写错）。
  · R3 Codex: 用 `scripts/codex_pk.sh` 直接 Bash 前台同步调用（未走 Agent 转发），在独立 worktree（`git worktree add /tmp/brood-pr22-wt 99c9742f`，未碰主 checkout——主 checkout 当时仍 staged 着无关的其他工作，正确避开）里读实际文件，对 R2 的新发现 + 2 条低置信度项做了对抗挑战，三项全部 CONFIRM 并附具体命令证据（git diff/grep/rg），另加一条无关的预存在 12-vs-13 计数不一致（非本轮引入）。
  · R4 Opus 裁决: REQUEST_CHANGES，明确权衡了"3轮里因一行阻塞是否合理"——判定 wrong-path + self-contradiction 双重满足实质性错误门槛，且做了仓库范围内的同类模式排查（未发现其他实例，确认是孤立错误非系统性问题）。
- 机械证据: `git show 99c9742f:docs/ECOSYSTEM_MAP.md` + `git diff c53812d 99c9742f -- docs/ECOSYSTEM_MAP.md`（确认唯一变更行）；`git grep "MushroomDAO/agent-speaker-relay" 99c9742f -- ':!dist'` = 0 hits（确认finding#2真修复）；`git grep "Agent-WeChat-SDK" 99c9742f -- ':!dist'` 仅剩历史性表述（确认finding#3真修复）；`gh api repos/AuraAIHQ/iDoris` 确认旧 org slug 走重定向非 404（确认 dashboard.html 是 cosmetic 非 blocking）；Codex 在 worktree 内 `rg` 扫 backlog/tasks/*.md 确认 regex 边界 case 无实例；Codex 读 `scripts/export-backlog.js:510-518` 确认 dashboard.html 是逐字节 copy 非模板生成。
- **DeepSeek flash 评级**: **2/5** — R1b security-clean 判断两轮都零假阳性。R1a 在增量 diff 上依然对同一 ternary 给出假阳性 panic claim（这是跨2轮、3次同一处误判，模式很稳定，值得作为 known-issue 记录），且完全没抓住本轮真正的 blocking finding（ECOSYSTEM_MAP.md 路径列 regression）——这需要"记住同文件13行前的一条声明并核对表格里的一行是否与之矛盾"，属于跨段落一致性检查，单纯 diff-hunk 视角的 flash 结构性做不到。改进建议：ternary 误判已连续出现3次，值得在 R1 的 system prompt 里加一条"检查条件表达式`X if cond else Y`时，只有其中一个分支会被求值，不要假设两个分支都会执行"的显式提示，这是低成本、高频率复现的具体模式，直接改prompt比指望模型自己学会更可靠。
- 与 skill 设计是否一致: 基本一致，但过程中出现一次可避免的失误——中途误把"增量复审"当成"全新PR"重新拉了全量 diff 跑了一轮 R1，发现后主动核查 /tmp 里的既有产物（incremental diff、之前的 review 记录、GitHub review 历史）纠正回增量路径，没有把错误的全量结果带进后续轮次。另外 R2 prompt 的字符串插值失误（占位符未替换）侥幸没有影响结果质量（R2 靠自己的 Bash 工具重新核实了一遍，反而更扎实），但这是运气不是设计——**改进建议**：以后手写 subagent prompt 时，拼接大段 diff/context 内容必须直接嵌入实际文本，不能用 `{PLACEHOLDER}` 占位符期待"框架"会做替换（这里没有模板引擎，Agent tool 只接受纯字符串）。
- 改进建议: (1) 把"增量复审 PR 的正确姿势"更早地固化成一个显式检查清单第一步（先查 `/tmp` 有没有本 PR 号的既有 incremental diff/codex-pk 产物 + 查 GitHub review 历史里 clestons 有没有已经 CHANGES_REQUESTED 过），而不是靠中途碰巧发现遗留文件才纠正；(2) R1 prompt 补一条 ternary 短路求值的显式提示；(3) 手写 Agent prompt 时严禁用占位符字符串，必须真实拼接内容。
