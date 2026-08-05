## Verdict: REQUEST_CHANGES（首轮，head `10b0946e`）—— **实现没在这个 PR 里，只推上来了 4 张截图**

这不是代码质量问题。**这个 PR 一个 commit，内容是 4 个二进制截图，`+0/-0` 行文本改动。**

```
$ git diff --name-status 057002f4 10b0946e
A	e2e/screenshots/cta-brief-filled.png
A	e2e/screenshots/cta-empty-brief-click.png
A	e2e/screenshots/cta-turn1.png
A	e2e/screenshots/cta-turn7.png
```

而 PR body 描述的东西一样都不在分支上：

| PR body 说的 | 分支上实测 |
|---|---|
| 验收命令 `npx playwright test tests/09-cta.spec.ts` → 4 passed | `e2e/tests/09-cta.spec.ts` **不存在**（`e2e/tests/` 里只有 `00`–`08` 和 `helpers.ts`） |
| 「出口从第 1 轮起就在 DOM 里，第 7 轮起点亮成主按钮」 | `apps/web/src/chat.ts` 里 `cta` / `CTA` **各 0 次命中** |
| 「点击 = `explicitAction`」 | `explicitAction` 在分支的 `chat.ts` 里 **0 次命中** |
| 「5 个变异逐条验过」 | 没有测试文件可供变异 |

`preview` 上也没有——这些符号在 `origin/preview` 的 `chat.ts` 里同样是 0 命中。所以不是「代码已经在别处合了、这个 PR 只补截图」，而是**实现根本还没进任何分支**。

**几乎可以肯定是 `git add` 漏了**：截图是 e2e 跑完落盘的产物，被 add 进去了；源文件（`apps/web/src/chat.ts` 的改动 + `e2e/tests/09-cta.spec.ts`）没有。commit message、PR body、以及这 4 张截图本身都说明**代码在你本地是跑过的、而且跑通了**——它只是没被提交。

**要做的事**：把 `apps/web/src/chat.ts` 的改动和 `e2e/tests/09-cta.spec.ts` 补 commit 上来（可能还有 `docs/agent/tasks.md` 的 T1.3.2 状态）。推上来我立刻复审，按 PR body 描述的那套逐条验：第 6/7 轮点亮的边界两侧、`explicitAction` 是否真接上 render-gate 的「明确指令压过一切」、补齐值是否真写回 `brief`（图和报价同参，D-1/D-2）、以及 disclosures 是否真的明示了补了什么。

### 一条不影响本次结论、但值得先确认的

**分支落后于 `preview` 6 行**（`.github/workflows/ci.yml`，就是 #150 补的 `pnpm test:slots` 那一步）。我核过了：**这个分支自己没碰 `ci.yml`**（`git diff --name-only 057002f4 10b0946e` 只有 4 个 png），所以三方合并会保留 `preview` 的那 6 行，**不会回退 #150**。补 commit 之前顺手 `git merge origin/preview` 一下更稳——#142 就是这么把 `check` 串对齐回去的。

### 关于 PR body 的一句话

body 写得很好，里面那两条自己抓到的空转断言（「最后一条 agent 气泡非空」被开场白顶掉、「开场白里有数字」被 `qty()` 的 500 默认值顶掉）是**真正有价值的自审**，改法也对（改成断言明示话术本身、改成点两次看第二次还有没有明示）。等代码上来我会重点看这两条现在怎么写的。

但**这些叙述目前没有代码支撑**。在一个已经因为「文档声称与实际不符」拦过好几轮的仓库里（#142 第 4 轮的 §8 决策表、#149 的 `renderL1()/renderL2()`），一个 body 详述实现、内容只有截图的 PR 是这一类的极端形态——所以这条要说清楚，不是挑刺。

### Assumptions

- 结论全部来自 `git diff --name-status` / `git cat-file -e` / `git ls-tree` / `git show <sha>:<path> | grep` 的直接输出，对 `base(057002f4)` 和 `origin/preview` 两个基准都验过，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- 没有建 worktree、没有跑测试——**没有可跑的东西**。
- **R2/R3/R4 未跑** —— 没有代码可供评审，跑它们只会消耗配额。本 review 标 **1 轮 + 机械验证**，不冒充多轮。

---
*Reviewed by clestons（`$pr` v4，**1 轮 + 机械验证**，首轮 head `10b0946e`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；见下方自评，本轮 R1 的输出是**凭空生成**的）→ Sonnet 机械验证（`git diff
--name-status` 确认 PR 只含 4 个 png、`git cat-file -e` 确认 body 声称的测试文件不存在、
`git show 10b0946e:apps/web/src/chat.ts | grep` 确认 CTA/explicitAction 零命中、对 preview 同样验过、
`git diff --name-only` 确认分支未碰 ci.yml 因而不会回退 #150）→
**Opus R2 未跑（无代码可评）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：0/5 —— 而且这是一次需要单独记下来的失败。**
  `compress_diff` 的输出是 `4 files → 0 full, 0 summarized, 4 skipped | **0/80000 tokens**`——**送进 R1 的 diff 是空的**。而 R1a 返回了：
  ```
  FILES:
  - e2e/cta.spec.ts — added CTA test with screenshots and assertions
  FINDINGS:
  [Low] e2e/cta.spec.ts:1 — test uses hardcoded selectors; brittle if UI changes | use data-testid
  ```
  `e2e/cta.spec.ts` **不存在于这个仓库的任何分支**，它也不是 PR body 里写的那个路径（body 写的是 `e2e/tests/09-cta.spec.ts`）。R1b 同样从零输入产出了「Test coverage for CTA flow added with screenshots. Selectors are hardcoded」。**两个 pass 都从 0 token 的输入里编出了一个文件名、一条 finding 和一段总结。** 这不是判断失误，是无中生有。
- **要改的是流水线，不是 prompt。** `compress_diff` 应当在**全部文件都被跳过、输出 0 token** 时直接失败退出，而不是把空文件交给 R1；`deepseek_review.py` 也应当在 diff 为空时拒绝调用。我会把这条记进 PR-Daemon 的 TODO——今晚这个案例正好是它的复现用例。在那之前，我在每次读 R1 输出前会先核对 `compress_diff` 的 token 数，为 0 就整段作废。
