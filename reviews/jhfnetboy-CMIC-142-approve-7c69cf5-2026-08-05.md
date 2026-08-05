## Verdict: APPROVE（增量复审，head `7c69cf5b`，round 6）—— **两条阻断项都彻底修好了；剩下的四条随手带走，不再挡**

**上一轮两条 Blocking 全部真修，而且第一条是把 11 处一次补齐，不是补了几处。**

| round-5 的问题 | 现在 |
|---|---|
| `T1.2.2 → DONE` 只传播 3/11 处 | ✅ **11/11**：T1.1.2 → `PR_OPEN`（#148）；T1.2.2 证据行改成「已 APPROVED 并合入 `preview`」；计数 `DONE 2 / PR_OPEN 3 / READY 4 / BACKLOG 15 = 24`；`progress.md` 已交付补上 T1.2.2；进行中改成「T1.1.2（#148）—— #144 合入后它的唯一依赖已解除，当天开工并进 PR」；`preview` 领先改成 **2 个 commit**；剩余从「四条」改成「三条」并逐条给了正确的 PR 归属 |
| `.pilot/followups.md` 路径错 + 文件不存在 + 静默 exit 0 | ✅ `docs/agent/followups.md` **真建出来并提交了**，指针改成相对路径 `[followups.md](followups.md)` 并写明 `.pilot.yml docs_dir` 的依据。**FU-5 —— 上一轮它在任何一个分支的账本里都不存在 —— 现在有了** |
| `progress.md:39`「第二轮」（Codex 提的） | ✅ 「第五轮」 |

我逐项机器核对：24 个 `### T` 标题的标签统计与汇总表**逐格相符**，`PR_OPEN` 集合 `{T1.1.2, T1.3.1, T1.4.1}` = `{#148, #146, #145}` 对得上，`git rev-list --count origin/main..origin/preview` = **2**，`tasks.md` 里所有 markdown 链接都能解析到存在的文件。上一轮的 §8/`spec.md` 优先级问题也真关掉了——规则现在**同时**在 §8 标题下（`:615-623`）和文末附录（`:680-683`），范围双向对称，两处互相交叉引用。

我还特意查了第 5 轮 B1 会不会复发：`tasks.md:495` 规则 2 仍点名 `T1.1.2` 是「每天在漏钱的」，而标签已翻成 `PR_OPEN`。**这不算复发**——漏钱的事实在 #148 合入前确实还活着，规则自己的括号也写了「状态一律以标签为准」，标签现在是对的。

---

### 我认真考虑过要不要拦，结论是不拦

上一轮我发现的那条 `FU-1` 问题确实存在，机械后果我复现了：

```
followups.sh list --open --docs-dir docs/agent   → 不含 FU-1
followups.sh count-open --docs-dir docs/agent    → 7（不是 8）
```
而 `#147` 现在是 **OPEN 且被我 REQUEST_CHANGES**，账本表头自己定义 `- [x]` = DONE。

**但有三点让它不该由这个 PR 承担：**

1. **`#142` 在这件事上是对的。** 它自称「四个在途分支合并后的全量」，我把 8 条 FU 逐条追回来源分支（FU-1/FU-2 来自 preview 基线、FU-3/4/7 来自 #147、FU-5 来自 #145、FU-6 来自 #148、FU-8 来自 #146），**没有一条遗漏、没有一条杜撰**；而 FU-1 那一行与 `origin/fix/FU-1-chips-content-filter` 上的对应行**字节相同**。要求 `#142` 把它改成 `[ ]`，就是要求这份 union 偏离它的来源，而且 `#147` 一合会原样再破一次。
2. **缺陷的家在 `#147`**，而 `#147` 刚刚已经被挡住了。在这里再挡一次是拿同一个缺陷开第二张罚单，还把修复放进了错误的分支。
3. **7 和 8 不改变任何一个决策。** `phases/run.md` §2.5 第 1 步和 §3 停止闸都是判 `count-open == 0`，7 和 8 走完全相同的分支。真受影响的只有 `list --open` 喂出来的 cleanup PR 工作项，而那个 PR 要等主线 Task 全清才建得起来，远在 `#147` 有结果之后。

另外：`#142` 和 `#147` 无论谁后合，git 都会在 `followups.md` 上冲突（我用 `git merge-tree` 复核过），所以不会静默过去，一定有人被迫看到两个版本。

到第 6 轮，手上剩的东西性质已经变了：最重的一条不是本 PR 的错误，其余是可读性/追溯性。**这一轮该给的是 APPROVE。**

---

### 建议随手带走（不挡合并，按优先级）

- **🔻[Med] `progress.md:44` —— 这条我建议优先于其它三条，因为它的后果会落到生产成本上。** 原文：
  > ⚠️ #144 / #145 / #146 都改了根 `package.json` 的 `check` 串。#144 已合，**#145/#146 合并时各需一次 trivial 冲突解决**（三条都留，别覆盖）。

  **漏了 `#147`**——我实测 `git merge-tree`，`#147` 对 `preview` 在 `package.json` 上同样冲突。更要紧的是我把五条 `check` 串都打出来了：
  ```
  preview  ✅ 有 test:gate      ← #144 合进来的，唯一护着 GPU 花费的断言
  #145     ❌ 无 test:gate
  #146     ❌ 无 test:gate
  #147     ❌ 无 test:gate
  #148     ✅ 有 test:gate      ← 它从 #144 之后开的分支
  ```
  #145/#146/#147 都是在 #144 合入前开的分支，所以它们的 `check` 串里**没有** `test:gate`。一个照着这行指引去合 #147 的执行者，既不预期这里会冲突，也没拿到「保住 `test:gate`」这条指令——**一次 take-theirs 就把省钱闸从 `pnpm check` 里静默删掉了**。
  建议改成：「#144 / #145 / #146 / #147 **四条**都改了 `check` 串……合并时**四条都留**，且**必须保住 `preview` 上已有的 `pnpm test:gate`**（#145/#146/#147 三个分支的串里都没有它）。」
  （顺带：我在 #148 的评审里报了 `test:gate` **不在 `ci.yml`** 里——`check` 13 条，ci.yml 逐条列了 12 条独独漏它。所以这条断言目前既不在 CI、又随时可能被合并丢掉。）

- **[High → 归属 `#147`] `followups.md:11`** —— 在 **`#147` 分支上**把 FU-1 改回 `- [ ]`（`followups.sh done` 的契约是 `--pr <已合并的 PR 号>`，见 `reference/followup-ledger.md:37`），等 #147 真合了再标 done，然后把 #142 的 union 重新同步一次。**不要在 #142 单独改**——那会让它不再是它自称的那份 union。

- **[Low] `followups.md:16`** —— `FU-6 · B · src=PR#T1.1.2`，`src` 放的是 Task ID 不是 PR 号（真实是 #148），而两行之上的警告说「以 `src=PR#nnn` 去重」。我读了脚本：`--source` 是自由文本、默认 `manual`、除了去换行不做格式校验，`PR#nnn` 这个形状只由账本自己那条警告提出；FU-6 只在 #148 一个分支上，按字符串精确去重照样唯一。代价只是「从 FU-6 跳不到 #148」。同样建议在 #148 分支上改。

- **[Low] `agent-interaction-v2.md:618` vs `:683`** —— 这两处互相声明「两处必须同步改」，但回顾语已经分叉了：§8 版写「评审**两轮**亲身踩到的」，附录版写「**这一轮**亲身踩到的」。规则正文两边一致，只有这句不同步。顺手统一。

### 驳回

- **R1a「`followups.md` 是新文件，`tasks.md` 的指针路径需确认」** —— 确认过了，指针是相对路径 `followups.md`、与 `.pilot.yml` 的 `docs_dir: docs/agent` 一致，文件存在。这正是上一轮阻断项 2 的修复。
- **「账本里那句『已发生两次：FU-3 撞过、FU-5 撞过』」** —— 那是历史陈述，当前分支状态既证不实也证不伪（#145 有 FU-5、#147 有 FU-3，无活跃撞号），而且它要求的动作（按 `src` 去重）本身是对的。不算发现。

### 一条留给这批 PR 落地之后的结构建议

真正的结构性风险已经不在文档措辞里，而在**四份发散的 `followups.md` 各自为政**：一个 append-only、**没有 `reopen` 子命令**的账本被四个分支并行改写，状态正确性完全靠合并顺序和人工冲突解决。FU-1 这次的错法（在源分支上提前标 done）会以别的面目重演。等这批 PR 落地后，值得让账本**只在集成分支上单点维护**，特性分支只在 PR 描述里提 follow-up，由集成分支统一入账。

### Assumptions

- 在独立 worktree（head `7c69cf5b`）里读全部 `docs/agent/*.md` 与 `docs/design/*.md`，对照真实的 `.pilot.yml`、pilot 的 `scripts/followups.sh`（含实跑 `list --open` / `count-open`）、`git rev-list`、`git merge-tree` 与 GitHub 上 #143–#148 的真实状态，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- 按纯文档 PR 的口径判：只对**实质性错误**拦。上面逐条论证了为什么剩下的都不属于——最重的一条不是本 PR 引入的、且它的家在 #147。
- **R3(Codex PK) 未跑、R4 未跑** —— 本轮是 APPROVE，且每条结论都有我自己实跑的命令输出。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `b4c8954`→`7c69cf5`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；2 条 Low，指对了区域但只说「需确认路径」，未得出结论）→ Sonnet 机械验证
（11 处传播逐项核对、24 条标签与汇总表逐格对账、`rev-list` 实测 preview 领先 2、实跑 `followups.sh
list --open` / `count-open` 复现 FU-1 的机械后果、五个分支的 `check` 串逐条打出）→ Opus R2（独立评审，
论证 FU-1 那行与 #147 字节相同因而不该由本 PR 承担、`count-open` 7 vs 8 不改变 `phases/run.md` 任何分支，
并新发现 `progress.md:44` 的冲突提醒漏了 #147 且三个分支的 `check` 串都会丢掉 `test:gate`）→
**Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 两条 Low 都**指对了区域**（`followups.md` 是新文件、`tasks.md` 的指针路径要确认 `docs_dir`）——这正是上一轮阻断项 2 所在的地方——但两条都停在「verify path matches docs_dir / confirm path resolves」，没有真去读 `.pilot.yml` 和 `followups.sh` 得出结论。这是它连续第二轮在同一个位置做同样的事：能嗅到可疑引用，不会顺着配置往下解析一步。本轮真正有价值的那条（`check` 串会丢 `test:gate`）需要跨五个分支比对，它没有那个视野。
- **下次怎么榨出更多信号**：对文档类 PR，别只喂 diff——把仓库的配置文件（`.pilot.yml` / `package.json` scripts / `.github/workflows/*.yml`）连同 diff 一起给 R1，并把要求写死成**判定句**：「逐条列出 diff 里出现的每一个文件路径和命令，各自标注『存在/不存在』和『与配置一致/不一致』」。逐项核对 flash 是可靠的，它弱的是自己想到该去核对什么、以及核对完敢下结论。
