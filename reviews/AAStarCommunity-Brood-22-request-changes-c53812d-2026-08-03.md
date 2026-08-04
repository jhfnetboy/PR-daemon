# AAStarCommunity/Brood#22 — REQUEST_CHANGES (incremental)

- PR: docs(context): L0/L1 ecosystem context refresh
- Head: c53812d504fa6344b92c55a1c47bf76b09e79c5a (incremental re-review; prior head 8b78874, prior verdict REQUEST_CHANGES)
- Pipeline: pr-daemon-loop v4, 4-round on the incremental diff (DeepSeek R1a+R1b → Opus R2 independent, cross-referenced against full repo not just diff → Codex R3 PK in isolated worktree at c53812d → Opus R4 final)
- Posted: 2026-08-03 as clestons

Full review body posted to GitHub — see PR comment. Summary:

The author's fix commit addressed 2 of 5 prior findings correctly (version contradiction now v1.12.0 both places; aastar capability-name mismatch resolved). The other 2 fixes are each narrower than the defect and introduce new problems, and the 5th finding was never touched:

1. **[Medium, NEW] `.claude/skills/sync-progress/SKILL.md:163-171`** — dedup fix changed from full `owner/repo` match to basename-only match, to survive org renames. This collapses distinct same-named repos across orgs (verified: `AAStarCommunity/Cos72` and `MushroomDAO/Cos72` are different real repos via `gh api`) — turns a visible/reversible duplicate-append bug into a silent/permanent skip bug.
2. **[Medium, NEW] `orgs/mycelium/PROFILE.md:27`** — this commit renamed agent-speaker-relay's owner in exactly one file; 8 other locations across the repo still disagree (mostly `MushroomDAO/agent-speaker-relay`, one `auraai/agent-speaker-relay`). Created a fresh 3-way self-contradiction.
3. **[Medium, UNFIXED] `orgs/auraai/PROFILE.md:18`** (+3 more locations) — original finding #5, never addressed. Still references `MushroomDAO/Agent-WeChat-SDK`, which no longer exists (renamed+moved to `iDoris-ai/iDoris-SDK`, confirmed via `gh api` redirect). This repo's own `protocol/ECOSYSTEM_MAP.md` and `protocol/REPO_REGISTRY.md` already document the correct rename — the `orgs/`+`backlog/` layer now contradicts the `protocol/` layer.
4. [Low] `docs/dashboard.html` (4 lines) — generated dist layer still emits stale `AuraAIHQ/...` links.

R1 (DeepSeek dual-pass): security clean; full pass found only 2 Low items, one of which was mechanically verified as a non-issue (the version bump IS correct). Missed all 3 blocking findings — they require cross-referencing files outside the diff, which R1 doesn't see.

## Self-assessment

- 轮数: 实际跑了 4 轮 (R1a+R1b DeepSeek 并行 → Opus R2 独立读全仓交叉验证 → Codex R3 隔离worktree PK → Opus R4 最终裁决)。这是原 PR 已判 4-round 的**增量复审**（触发文件仍含 automation-consumed 的 `.claude/skills/sync-progress/SKILL.md` 可执行 Python 逻辑），沿用 4-round 是正确的，不是虚标。一致 ✅
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 喂了增量 diff（compress_diff.py 压缩后的 6 文件, 4053 tokens, 无丢文件）。R1a 产出 2 条 Low；R1b 产出 security-clean 判断。
  · R2 Opus: 独立读了增量 diff **加上**主动跳出 diff 范围、交叉全仓 grep（backlog/tasks/*.md, orgs/*, docs/dashboard.html, dist/），用工具核对了上一轮 5 条 finding 逐条是否真修复；发现 finding #1 的修复本身引入新 regression（basename collision），finding #2 的修复制造了新的 8-way 矛盾，finding #5 完全没动。
  · R3 Codex: 用 `scripts/codex_pk.sh` 直接 Bash 前台同步调用（未走 Agent 转发，符合硬规则），在独立 worktree（`git worktree add /tmp/brood-pr22-worktree c53812d`，未碰主 checkout——主 checkout 当时 staged 着无关的 fast-forward 变更，正确避开了）里对 c53812d 现场读盘验证，独立复现全部 3 条 blocking finding，另加了一条 dashboard.html 遗漏项。CHALLENGE: 无（全部 CONFIRM，仅对 finding B 的文件清单做了一处小纠正：docs/REPO_STATUS.md 不算显式 owner 字符串）。
  · R4 Opus 裁决: REQUEST_CHANGES，逐条列出 blocking/confirmed/rejected，明确权衡了"文档 PR 只对实质性错误 block"的规则——判定 basename collision（自动化逻辑功能性 bug）、8-way 矛盾、finding #5 未修都够格实质性错误，不是 precision nit。
- 机械证据: `gh api repos/AAStarCommunity/Cos72` vs `repos/MushroomDAO/Cos72`（不同 repo id，证明 basename collision 真实）；`gh api repos/iDoris-ai/agent-speaker-relay` + `repos/MushroomDAO/agent-speaker-relay`（同 repo id，确认迁移）；`gh api repos/AAStarCommunity/YetAnotherAA-Validator/tags`（确认 v1.12.0 是真最新 tag）；`gh api repos/MushroomDAO/Agent-WeChat-SDK`（重定向到 iDoris-ai/iDoris-SDK，证明改名+迁移）；`git show c53812d:protocol/REPO_REGISTRY.md` 验证 protocol/ 层已有正确改名记录；python3 直接跑正则测试验证 regex 边界情况（markdown 链接/`.git`后缀截断问题，当前仓库暂无实例故降级为非独立 finding）。
- **DeepSeek flash 评级**: **2/5** — R1b 的 security-clean 判断正确（零假阳性）。R1a 的 2 条 Low 里，1 条（version bump 无说明）被机械验证为非缺陷（数值本身是对的，纯风格意见），另 1 条（regex 未限定 references 字段）虽然方向正确但被 R2/R4 判定为"从属于同址的更大 blocking 缺陷"而未独立计分。R1a 完全没抓住这轮 3 个 blocking finding 中的任何一个——全部需要跳出 diff 本身、交叉全仓其他文件才能发现（basename collision 需要知道 Cos72 在两个 org 下都是真实仓库；8-way 矛盾需要 grep 全仓 agent-speaker-relay 出现处；finding #5 未修需要记得上一轮的 5 条原始 finding 并核对是否被这次 diff 触碰）。这类"验证声称的修复是否真的修复、有没有引入新矛盾"的复审场景，本质上要求跨文件全仓上下文，纯 diff-only 的 R1 结构性做不到，不是 flash 模型能力弱，是喂给它的输入范围天然受限。建议：增量复审场景下，可以额外喂给 R1 一份"上轮 N 条原始 finding 的 file:line 清单"，让它至少能针对性核对这些具体位置是否被本次 diff 触碰到，而不是要求它自己发现要交叉全仓。
- 与 skill 设计是否一致: 一致。post-R2 severity gate 正确触发（发现 Medium+ → 跑 Codex R3）；Codex 走了 scripts/codex_pk.sh 直接 Bash 前台同步；worktree 隔离正确避开了主 checkout 的无关 staged 变更；Opus R4 最终裁决用了"docs-PR 阻塞门槛"规则做了有意识的权衡说明，不是无脑判 REQUEST_CHANGES。
- 已知缺口: `.state/pr-daemon/pr-watch.sqlite` UPDATE 因并发锁（`database is locked`）未落盘，与上一轮同样的已知问题（大概率又是并发 daemon session 占用）；GitHub review 是权威动作，已成功发出，不受影响。SQLite 应在下次 --sync 轮询时自我修正。
- 改进建议: 若 jason 之后要跑更多"增量复审已 REQUEST_CHANGES 的 PR"场景，值得考虑把"上轮 finding 清单"结构化存下来（而不是仅存在 markdown 里），方便下一轮自动 diff 出"哪些 finding 的 file:line 这次 commit 碰了/没碰"，减少人工交叉核对的工作量。
