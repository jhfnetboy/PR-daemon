## AAStarCommunity/Brood#22 — REQUEST_CHANGES (round 4, incremental)

- Head: `73e0437` (incremental re-review; prior head `99c9742f`, prior verdict REQUEST_CHANGES)
- Pipeline: pr-daemon-loop v4, 4-round on the incremental diff (DeepSeek R1a+R1b → Opus R2 independent → Codex R3 PK in isolated worktree at `73e0437` → Opus R4 final)

## Prior round's findings — both fixed in source ✅

1. **`docs/ECOSYSTEM_MAP.md:120`** local-path column — reverted `agent-speaker-relay` from `iDoris-ai/agent-speaker-relay` back to `auraai/agent-speaker-relay`, matching all 12 other rows' local-path convention (explicitly documented in the file's own note: "本地目录仍为 `~/Dev/auraai/`，物理目录名未改，约定映射到 iDoris-ai org"). Verified: `~/Dev/auraai/agent-speaker-relay` exists on disk.
2. **`docs/dashboard.html`** — the 4 stale `AuraAIHQ` links (iDoris, Agent24, OpenCrab, courses) now correctly point to `iDoris-ai`. Verified: all 4 new URLs resolve via `gh api repos/iDoris-ai/{iDoris,Agent24,OpenCrab,courses}`.

## Blocking — the fix doesn't reach the deployed site

**[Medium] `dist/docs/dashboard.html:333,344,354,364`** (+ `dist/api/tasks.json`, `search.json`, `statistics.json`, `docs/doc-7.json`) — this commit fixed the **source** `docs/dashboard.html` but touched **zero files under `dist/`** (`git diff --name-only 99c9742f...73e0437 -- dist/` = empty). This repo commits a generated static site and deploys it verbatim: `.github/workflows/deploy.yml` does `checkout` → `upload-pages-artifact path: dist` with no build step, and `package.json`'s `deploy:cf` script runs `wrangler pages deploy dist` — same stale copy either way. `AGENTS.md` states this explicitly: "Local build, direct push: All build computation happens locally; `dist/` is committed to git and deployed as-is."

Confirmed via diff: `docs/dashboard.html` vs `dist/docs/dashboard.html` at `73e0437` differ in **exactly** those 4 lines (858 lines each, byte-identical otherwise) — a pure stale-copy, one command fixes it. `dist/api/statistics.json` also still embeds `AuraAIHQ/Agent24` and `AuraAIHQ/agent-speaker` (missed by the first two verification passes, caught in final review).

Not a 404 — GitHub's org-rename redirect means the old links still resolve — but the PR's stated deliverable ("fix dashboard AuraAIHQ links") does not actually reach the published GitHub Pages site as committed.

**Fix:** `pnpm run build` (regenerates `dist/docs/` + `dist/api/*.json` from the already-fixed sources — verified `backlog/` has zero remaining `AuraAIHQ` refs, so a plain rebuild is sufficient) and commit the resulting `dist/` changes in this PR.

## Non-blocking suggestions

- **[Low]** `docs/ECOSYSTEM_MAP.md:104,109` — three different repo counts in the same section: this PR's own new note says "15 个子仓库", the pre-existing heading says "全部仓库（12 个）", the table has 13 rows, and live `gh api orgs/iDoris-ai/repos` returns 18 (the table omits `Self-FDE-WorkBench`, `iDoris-website`, `ai-atlas`, `MediaBot`). Pick one true number, or retitle to "主要仓库" and drop the count claim.
- **[Info]** Consider a CI guard for this bug class: a job that runs `pnpm run build` and fails on `git diff --exit-code dist/`. This is the first observed `docs/` ↔ `dist/` divergence and will recur on every future content PR while `dist/` stays hand-committed.

## R1 (DeepSeek dual-pass)

R1b: clean, no security surface. R1a raised one Low finding claiming `ECOSYSTEM_MAP.md` is inconsistent with the dashboard fix — verified as a **false positive**: it conflates the local-path column (`auraai/<repo>`, a filesystem-path convention explicitly documented in the file) with the GitHub-org column in `dashboard.html`. R1a did not surface the round's actual blocking finding (the `dist/` desync) — that required cross-referencing CI/deploy config against the diff's scope, outside single-hunk diff review.

## Self-assessment

- 轮数: 实际跑了 4 轮 (R1a+R1b DeepSeek 并行 → Opus R2 独立读增量diff → Codex R3 隔离worktree对抗挑战真实命令 → Opus R4 最终裁决)。一致 ✅
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 在 53 行增量 diff 上跑了 R1a(全量) + R1b(安全)，R1a 给出 1 条 Low 假阳性（混淆 local-path 列与 org-slug 链接），R1b 判定 clean。
  · R2 Opus: 独立读增量 diff，交叉核对前序 2 条 finding 均已修复；额外发现本轮真正的阻塞项——`dist/docs/dashboard.html` 未跟着 `docs/dashboard.html` 一起重新生成，而 CI 部署直接吃 `dist/` 不构建；并指出了三个数字互相矛盾的仓库计数问题。
  · R3 Codex: 用 `scripts/codex_pk.sh` 直接 Bash 前台同步调用，在独立 worktree（`git worktree add /tmp/brood-pr22-wt 73e0437`，未碰主 checkout——主 checkout 当时在 main 分支上有无关的 staged 工作，中途曾误在其上跑了 grep/ls 拿到错误结果，发现后改用 `git show <sha>:<path>` 全部重新核实，未产生任何写操作）里跑真实命令逐条验证 F1/F2，全部 CONFIRM 并附具体输出。
  · R4 Opus 裁决: REQUEST_CHANGES，独立核实 dist/docs/dashboard.html 与源文件的 diff 恰好只差 4 行（纯 stale copy），额外抓到 R2/R3 都漏掉的 `dist/api/statistics.json`，并且用证据驳回了 R3 提出的一条不成立的顾虑（backlog/ 任务文件早已在上一轮清干净，非本轮遗留问题）。
- 机械证据: `git show 73e0437:docs/dashboard.html | grep AuraAIHQ` = 0 命中（源文件干净）；`diff <(git show 73e0437:docs/dashboard.html) <(git show 73e0437:dist/docs/dashboard.html)` = 恰好 4 行差异（纯未同步）；`git show 73e0437:.github/workflows/deploy.yml` 确认无构建步骤，直接 `path: dist`；`git grep -c AuraAIHQ 73e0437 -- backlog/` = 0（驳回 Codex 顾虑）；`git show 73e0437:dist/api/statistics.json | grep AuraAIHQ` = 命中 Agent24/agent-speaker（R4 补漏）；`gh api repos/iDoris-ai/{iDoris,Agent24,OpenCrab,courses}` 全部 resolve（确认新链接有效）。
- **DeepSeek flash 评级**: **2/5** — R1b 安全判断零假阳性但本身无安全面可判。R1a 唯一的 finding 是假阳性（混淆 local-path 与 org-slug 两个不同列），完全没抓住本轮真正的问题——`dist/` 部署镜像未跟着源文件重新生成。这是本轮观察到 flash 在跨文件/跨配置（这次是 diff 范围 vs CI 部署配置）一致性检查上的结构性短板，单看单个 diff hunk 看不出"这个 PR 改了 A 但没改与 A 强耦合的 B"这类问题。改进建议：给 R1 prompt 补一条"检查改动是否遗漏了同一构建产物的其他副本（如 dist/、build/、生成的 API JSON）"的显式提示，这类"半途而废的修复"是文档型仓库里重复出现的模式。
- 与 skill 设计是否一致: 基本一致。中途一次可避免的失误——在人工核实时，先在共享主 checkout（main 分支，带无关 staged 工作）上直接 grep/ls 而没有先切到 PR 分支，读到了错误的旧内容（当时 main 上的 dashboard.html 恰好还没被这次 PR 触碰过，看起来像"修复没生效"，实际只是读错了树）。发现后没有对主 checkout 做任何写操作去"纠正"它，而是改用只读的 `git show <sha>:<path>` 重新核实全部结论——这也符合"对抗性测试要用worktree不碰共享主checkout"教训的延伸：连只读探查都不该依赖共享主 checkout 当前的工作树状态。
- 改进建议: (1) 增量复审时做人工核实，一律用 `git show <sha>:<path>` 而非依赖共享主 checkout 的工作树状态（工作树可能停在任意分支/带无关改动）——这次侥幸没有产生误导性的最终结论，纯属运气，下次应从一开始就用 git show；(2) R1 prompt 补"检查是否有未同步的构建产物副本"提示，见上一条。
