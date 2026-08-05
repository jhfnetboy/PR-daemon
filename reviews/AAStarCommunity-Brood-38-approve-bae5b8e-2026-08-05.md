## Verdict: APPROVE（首轮，head `bae5b8ee`）—— **契约本身立得住，而且顺手修了一个版本号漂移**

按纯文档 PR 的口径：只对**实质性错误**拦。核实过，没有。

### 核实清单

| 检查 | 结果 |
|---|---|
| `README.md` 里 `reference/` 树列的 8 个文件 | ✅ **8/8 全部存在**（`git-safety` / `pr-quality` / `pre-pr-review` / `review-contract` / `doc-sources` / `task-schema` / `review-triage` / `followup-ledger`） |
| `doc-sources.md` 里的文件引用 | ✅ 可解析。`.pilot.yml` / `.repo-pilot.yml` 是**目标仓库**提供的配置、本就不在插件里，不算悬空 |
| 版本号 | ✅ 而且**修好了一处既有漂移**：`plugin.json` 原本 `1.2.0`、`SKILL.md` 原本 `1.1.0`——两边早就不一致了，这个 PR 把它们一起同步到 `1.3.0` |

### 这份契约的核心判断是对的

> **「入口」是编排责任，不是运行时依赖**：pilot 自己不 import、不启动任何配套 skill，只探测能力在不在，不在就说明缺什么、给出装法，然后降级继续干活。

而且它把理由写在了旁边：

> 硬依赖曾经让 pilot 和一个外部 daemon 死锁在一起，花了 6 轮评审才拆干净——「pilot 是入口」不是把它写回去的理由。

**这句话值得留着。** 「pilot 是唯一入口」这个定位天然会诱导下一个人把配套 skill 写成硬依赖（既然我是入口，那我来加载它们），而上一次正是这么出的问题。把「这条约定管的是编排、不管运行时」和「上次为什么栽」写在同一段里，比单写约定本身耐久得多。

「用户自然说一句『读一下这篇飞书文档』时 harness 直接命中 `lark-doc`，**不违反**这个约定」这一句也补得好——它预先回答了「那用户绕过 pilot 直接用配套 skill 算不算破约」，省掉一次来回。

### 非阻塞

- **[Low] 契约只写了「探测能力在不在」，没写【怎么探测】。** 「不在就说明缺什么、给出装法」要落地，得有一个确定的判定方式（skill 名字命中？某个文件存在？）。如果留给实现者自己想，两处实现会用两种判法——而这个仓库这几轮反复栽的正是「同一件事两处各写一遍然后分叉」。建议在 `doc-sources.md` 里把探测方式定死一句。
- **[Low] `plugin.json` 从 `1.2.0` 跳到 `1.3.0`，而 `SKILL.md` 是从 `1.1.0` 跳上来的。** 同步是对的，但这说明此前有一段时间两边各走各的。如果 `plugin.json` 的版本对使用者有意义（决定装哪个版本），值得加一条一行的检查把两者钉在一起——和你们在 CMIC 里给哨兵串加 `sentinel-sync.test.ts` 是同一个手法。

### Assumptions

- 在两个独立 worktree（`origin/main` 与 `bae5b8ee`）里核对，未改动 `~/Dev/aastar/Brood` 任何文件。
- 文件存在性用 `find` 实查，版本号用 `json.load` 与 `grep` 实读，不采信文档自述。
- 按纯文档 PR 口径：上面两条都是可读性/耐久性建议，不构成实质性错误。
- **R2/R3/R4 未跑** —— 纯文档 + 一个版本号，无争议项。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `bae5b8ee`）：DeepSeek R1a
（`deepseek-v4-flash`；triage 判定 docs-only 准确，无 finding）→ Sonnet 机械验证（`reference/` 树列的
8 个文件逐个存在性核查、`doc-sources.md` 的引用解析、三处版本号实读并发现既有漂移已被同步）→
**Opus R2 未跑（纯文档）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 没有 finding，但 triage 判得准（「Docs-only PR clarifying pilot's role as entry skill vs. runtime dependency… No code changes; no security or logic impact」）——**对纯文档 PR 不硬凑 finding，本身就是正确行为**。这几轮它在文档类 PR 上的表现明显好于代码类。
- **下次怎么榨出更多信号**：文档 PR 上它已经能做「内部一致性」了（#153 那次抓到 9 vs 11）。缺的仍是**和仓库真实状态比对**。下次对含文件树/版本号的文档 diff，把 `find`/`ls` 的输出和相关 manifest 一起喂进去，要求「逐条核对文档里列出的每个文件名/版本号是否与给定的真实数据一致」。
