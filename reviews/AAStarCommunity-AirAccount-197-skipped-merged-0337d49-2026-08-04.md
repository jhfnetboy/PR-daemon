## AAStarCommunity/AirAccount#197 — SKIPPED (merged mid-review, no GitHub review posted)

- Prior review: `f848ac6` REQUEST_CHANGES (see `AAStarCommunity-AirAccount-197-request-changes-f848ac6-2026-08-04.md`)
- This round: incremental diff `f848ac6..0337d49` (author's fix commit)
- Discovered mid-pipeline (after R1a+R1b DeepSeek + Opus R2, before Codex R3/Opus R4): `gh pr view 197` now returns `state: MERGED`, `mergedAt: 2026-08-04T11:04:11Z`, `mergeCommit: a35b876`. Merged by someone else — not by this reviewer. Step 0's initial check (start of this round) had returned `state: OPEN`; the merge landed during the review window.
- Per hard rule (merged/closed PR → skip entirely, no GitHub write), the pipeline stopped here. **No GitHub review was posted.** Codex R3 and Opus R4 were not run (would have been a no-op against a merged PR).

## What the incremental diff actually did (verified by R2 before the merge was discovered)

- `.pilot.yml`: resolved the prior Medium blocking finding via documentation only (did not change `integration_branch: main`) — explains that `git-guard.sh merge-pr` intentionally refuses trunk-target merges, so `pilot run` on this repo terminates at "PR opened, awaiting external approve." R2 verified this against `git-guard.sh` source directly (lines 148-150 hardcoded trunk refusal + live default-branch comparison) and confirmed all other `integration_branch` consumers (`run.md`, `safe-cleanup.sh`, `repo-scan.sh`) behave correctly with `main`. **Genuinely resolved**, not hand-waved.
- `kms/deploy/selfcheck.sh`: deleted from git tracking + gitignored.
- `.goutou.json`: removed dead `aliases` config; rewritten note verified accurate against goutou's actual `repoId`-only matching (`SKILL.md:55,74,136`).

## New finding surfaced by Opus R2 (not gated by this PR, follow-up needed)

**[Low] Repo-wide topology leak, now live on `main`.** The production KMS topology this PR's predecessor commit (`f848ac6`) leaked via `kms/deploy/selfcheck.sh` — and which this incremental diff "fixed" by deleting that one file — is still present, **currently, on `main`**, in at least:
- `check-all-nodes.sh` (repo root) — same DVT1/2/3 role map, `mx93b` alias, `kms1.aastar.io`, 2-of-3 threshold; publicly readable (`raw.githubusercontent.com` 200 unauthenticated)
- `kms/deploy/community.toml.example:11` — `board_ssh = "root@100.121.187.3"` (real production Tailscale IP + root login baked into what's meant to be a generic template)
- `kms/docs/MX93-FIELD-GUIDE.md:74,80,319` — same IP + board MAC (`80:a1:97:50:21:2d`) + Tailscale account email (`mushroomjiao82@...`), strictly more identifying than what was deleted
- `.gitignore:184` only ignores the one literal filename — no pattern guard against the next equivalently-named operator probe

R2's assessment: severity stays **Low** (no credentials, Tailscale CGNAT addresses require tailnet membership to exploit, and since the same data is in the *current* tree of `main` — not just old history — a history rewrite would accomplish nothing). The actionable defect is that the PR's own commit message ("移除 + gitignore") implicitly claims the topology leak is closed; it isn't, on either the history axis (old commit `f848ac6` permanently reachable via the merged PR's commit history / GitHub's retained refs) or the current-tree axis (same data lives on in ~20 other tracked files).

**Recommended follow-up (not blocking, PR already merged):** open a separate repo-hygiene issue/PR for a repo-wide sweep (not single-file), and treat the Tailscale topology as already disclosed (verify tailnet ACLs, consider rotating/hardening rather than chasing file-by-file redaction).

## Self-assessment

- 轮数: 实际跑了 3 轮(R1a+R1b DeepSeek 并行 → Opus R2 独立评审)。skill 要求(触发时): 4-round(增量涉及 `.pilot.yml` 等 automation-consumed 配置 + 安全相关拓扑)。中途发现 PR 已 MERGED,按硬规则立即停跑 Codex R3 + Opus R4,不补跑(对已合并 PR 跑 PK/裁决没有意义,也不会有任何输出目的地)。这是**合规的提前终止**,不是虚标或偷工。
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 喂了 5 个文件的完整压缩 diff(2385 tokens,无丢弃)。R1a 给了 1 条 Low(误报:声称删除 selfcheck.sh 可能有引用方,`grep -rn "selfcheck.sh"` 全仓核实零调用点,已驳回)。R1b 安全专项返回 none——本轮增量 diff 本身确实只是 config/docs 清理,无安全相关代码改动,这次的"none"是准确判断,不是盲区(与上一轮 R1 完全没扫到 .pilot.yml 耦合问题的情况不同,本轮它压根没有理由去扫别的文件,因为 diff 范围内确实干净)。
  · R2 Opus: 独立读增量 diff,PHASE1 自主发现 4 条新 Low(repo-wide 拓扑残留:`check-all-nodes.sh`/`community.toml.example`/`MX93-FIELD-GUIDE.md`/`.gitignore` 单文件规则局限),全部我事后未逐条重跑但 R2 报告了具体验证方式(`curl raw.githubusercontent.com` 200、`git branch -r --contains f848ac6`)。PHASE2 核实了我提出的"删除不等于清除历史"候选发现——**过程中順帶发现 PR 已经 MERGED**(`mergedAt: 2026-08-04T11:04:11Z`,merge commit `a35b876`),这打破了候选发现里"force-push 仍可行"的前提,我立即用 `gh pr view` 独立重新核实(非只信 R2 转述),确认属实,当场中止后续轮次。PHASE3 逐条核实了 `.pilot.yml` 文档化修复是否真解决了上一轮 Medium 阻塞项——读了 `git-guard.sh` 源码验证(非只信作者描述),确认 genuinely resolved。
  · R3 Codex: 未跑 — PR 已合并,对合并后的 PR 跑 PK 挑战没有输出目的地(不会有任何 GitHub 动作消费其结果),属于合规跳过而非配额/超时问题。
  · R4 Opus 裁决: 未跑 — 同上,合并 PR 不产出 APPROVE/REQUEST_CHANGES 结论,跳过。
- 机械证据:
  · `gh pr view 197 --json state,mergedAt,mergeCommit,headRefOid` = 独立复核确认 `state: MERGED`,而非仅信任 R2 转述的信息(R2 是在其内部工具调用里发现的,不是我喂给它的)。
  · `grep -rn "selfcheck.sh" --include=*.sh --include=*.md --include=*.yml --include=*.yaml .`(排除自身)= 0 命中,驳回 R1a 的误报。
  · `git branch -r --contains f848ac6` = `origin/chore/repo-hygiene`,`gh repo view --json visibility,isPrivate` = `PUBLIC`,共同验证"删除文件不等于清除历史"这一候选发现在数据层面成立(R2 进一步用 `curl raw.githubusercontent.com` 复核可公开访问)。
  · SQLite watcher state 更新失败(`database is locked`,大概率是并发跑的 `$start` 巡检持有写锁),已放弃强制写入——不做破坏性重试;下次巡检的 `poll_prs.py --sync` 会从 GitHub 活体状态自动拉正,且 Step 0 的 live `gh pr view` 检查本身就是权威闸门,不依赖这条陈旧 SQLite 记录。
- **DeepSeek flash 评级**: **3/5** — 本轮增量 diff 确实只是干净的 config/docs 清理,R1b 返回 "none" 是准确判断而非盲区;R1a 唯一一条 finding 是误报(想当然地假设删除脚本可能留下悬空引用,没有实际 grep 验证就下结论)。相比上一轮(2/5,完全没扫到 .pilot.yml 与 git-guard.sh 的耦合矛盾),本轮没有"完全跑题"的情况,但也没有任何真发现——R1 天然限定在本次 diff 范围内,无法发现 R2 那种需要"跳出 diff、扫全仓找同类残留"的模式,这不是本轮 R1 的失职,是其设计边界。改进建议:考虑在 R1 prompt 里加一条"若本次 diff 是在删除/gitignore 某类敏感内容,提示检查同仓库是否有同类内容残留于其他文件"——但这可能超出 R1 的经济定位(轻量单文件级扫描),更适合作为 R2 Opus 的常规检查项(本次 R2 已经在没有明确提示的情况下自主做到了)。
- 与 skill 设计是否一致: 基本一致,但暴露一个 skill 流程缺口——**增量复审(re-review of a previously-RC'd PR)没有在流程开始时重新执行 Step 0 的 merged/closed 检查**。本轮 Step 0 检查发生在 pipeline 最开始(当时确实 OPEN),但 PR 在 R1→R2 运行期间(约几分钟)被合并,而 R2 运行前没有二次核验。虽然本次是 R2 自己顺带发现的(运气好,不是流程强制的),但理论上 R2/R3/R4 都可能对着一个已经合并的 PR 徒劳跑完整个流程再在最后 Step 6 posting 时才发现失败。
- 改进建议(具体可执行): 建议在 skill 的 Step 5b(4-round 路径)里,**紧邻 Step 6(posting)之前**加一道"posting 前二次核验 PR 仍为 OPEN"的强制检查(而不仅仅依赖 Step 0 的一次性检查),尤其对耗时较长的多轮 pipeline(R1→R2→R3→R4 可能跨越数分钟到十几分钟,期间 PR 完全可能被其他 reviewer/pr-fix 循环合并掉)。这样即使 R2/R3/R4 全部跑完,也能在真正尝试 post 之前拦截,避免对已合并 PR 做无意义的 post 尝试或产生误导性的 review 记录。愿意现在就去改 SKILL.md 加这条(需要用户批准,因为有记忆铁律"只用 pr-daemon-loop 原版,禁止修改")。
