## Verdict: APPROVE（首轮，head `6f3da530`）—— **7 条 Low 逐条做掉，而且自己实测又挖出一条我没提的**

我在 #38–#41 里留的建议，这个 PR 逐条落地或明确记账。逐项核实：

| 我提的 | 这轮 | 实测 |
|---|---|---|
| **#38 [Low]** 版本号该有一条检查钉住两处 | 新增 `scripts/ci/check-version-sync.sh` + `verify.yml` 的 `version-sync` job | ✅ 正常态 `ok — pilot version 1.3.0 in both files` rc=0；**我把 `plugin.json` 改成 `9.9.9` 做变异 → rc=1 被杀**，报错还写明「Bump BOTH, or an installed copy will report a version it isn't.」 |
| **#40 [Low]** pin 的正则不接受小数 | `NUM = r'-?\d+(?:\.\d+)?'` | ✅ |
| **#40 [Low]** 匹配失败时看不出原因 | 加了 `near` 上下文：失败时打 `\| saw: ...averageTaskAge...`，键缺失时打「the key is absent from the committed file」 | ✅ 两种情形分开了 |
| **#39 [Low]** 注释说「`enforce_admins` binds admins too」但脚本不校验它 | **删掉了那半句**，并写明：*「这里刻意不检查 `enforce_admins`。它在这条路上不承重——下面的 `reviewDecision == APPROVED` 由这个脚本自己强制…（Brood 恰好开了它，但那是某一个仓库的属性，不是这条护栏依赖的保证。在注释里说反话，会让论证建立在一个从未验证过的东西上。）」* | ✅ **这正是我提那条的理由本身** |
| **#39 [Low]** 「读不到保护规则」的 die 该区分两种病因 | 拆成两条：`Branch not protected` / `Branch not found` → 「去开保护」；其余 → 「换个有 admin 权限的 token」，并把 GitHub 的 `message` 原样带出来 | ✅ 见下 |
| **#39 [Low]** flag 黑名单追不上新 flag，建议白名单 | 记进 `followups.md` FU-1 | ✅ 合理——我当时就说了「那是另一次改动」 |
| **#41 [Low]** 「同样的钱」在区间上界不成立 / 牌价会过期 / 92% 缓存命中是外部数据 | `cost-analysis` 改了 3 处 | ✅ |

### 新的保护规则解析我拆出来实跑了五种响应

作者把 `gh api ... --jq` 换成「先整体捕获再用 python 解析」，理由写在注释里（`--jq` 在错误响应上会静默给空，且**不能把 stderr 折进来**，否则 shell hook 的输出会污染 JSON）。五种情形：

```
有保护(Brood main)        approvals='1'  → 通过
分支不存在                 approvals=''   → die「分支没保护」✅
无保护(CMIC preview)      approvals=''   → die「读不到」并带出 GitHub 原话
                                            (Upgrade to GitHub Pro or make this repository public…) ✅
空响应                    approvals=''   → die「读不到」✅
非 JSON(<html>)          approvals=''   → die「读不到」✅
```
**全部 fail-closed，而且两种病因确实分开了**——第三行那个例子尤其好：GitHub 说的是「这个功能要 Pro」，属于「读不到」而不是「没保护」，新逻辑归类正确。

### 作者自己实测挖出来的那条，比我提的任何一条都重要

`followups.md` FU-2：

> `safe-cleanup.sh` 在 squash-merge 仓库里**永远清不掉任何分支**：本仓库 28 个本地分支，`git branch --merged main` 返回 **0** 个，因为 squash 后原 commit 不是 `main` 的祖先，而 safe-cleanup 只用 `-d` 永不 `-D`。**这是继 #39（死代码）、#40（随机红灯）之后同一家族的第三个「守卫跑不起来」。**

**把三次独立事件识别成同一个家族，这个判断比修好其中任何一条都值钱。** 而且它给的改法是对的——「用 `gh` 核实『存在 `headRefName==该分支` 且 `state==MERGED` 的 PR』作为已合并证据，再允许 `-D`；**不能简单放开 `-D`**」——先建立证据再放权，而不是为了让守卫「能跑」就把它削弱。

`doc-sources.md` 那节「探测分三层」也是同一个思路：**把「读不到」拆成①能力没装 ②凭证没有 ③目标读不到**，并指出「飞书 `identity` 显示 `bot` 不代表能读你的文档」——这正好回答了我在 #38 里提的「契约只写了探测能力在不在，没写怎么探测」。而且它自己写了「不要自己发明判据——同一件事两处各写一套判法然后分叉，是这个仓库反复栽过的坑」。

### 非阻塞

- **[Low] `check-version-sync.sh` 只比对 `plugin.json` 与 `SKILL.md`，而 `README.md` 里也印着版本相关的描述。** 今天 README 没有硬编码版本号（我核过，之前我以为有的那个 `1.1.1` 是 Task ID），所以现在没问题；但如果哪天 README 加上版本，这条守卫不会知道。值得在脚本里写一句「目前只有这两处声明版本」，把范围钉住。
- **[Low] FU-2 的改法要小心一个边界**：用「存在 `headRefName==该分支` 且 `state==MERGED` 的 PR」作证据时，**分支名可以被复用**——同名分支删掉后重开、内容完全不同，旧 PR 仍然是 MERGED。稳妥一点可以再比对 `mergeCommit` 或 PR 的 `updatedAt` 晚于该本地分支的最后一次提交。做那条的时候值得带上。

### 驳回

- **R1a / R1b 本轮无 finding**（`No concrete bugs found in the changed lines`）—— 我同意，这轮确实没有。

### Assumptions

- 在两个独立 worktree（`origin/main` 与 `6f3da530`）里跑守卫、做版本号变异、把保护规则解析逻辑拆出来对五种真实 API 响应实跑；未改动 `~/Dev/aastar/Brood` 任何文件，变异已 `git checkout --` 还原。
- **`verify.yml` 用 `yaml.safe_load` 真解析**，确认 `version-sync` 是独立 job 且确实调用了新脚本。
- **我没有执行 `merge-pr`** —— 它会真的合并 PR，我是评审方；`--allow-trunk` 的判定逻辑是拆出来单独跑的。
- **R2/R3/R4 未跑** —— 逐条对照上一轮 Low 的落地情况，无争议项，每条都有实跑输出。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `6f3da530`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；无 finding，triage 与「no concrete bugs」的判断准确）→ Sonnet 机械验证
（`check-version-sync.sh` 正常态 + 变异态各跑一次、`yaml.safe_load` 确认 job 接线、把新的 protection
解析逻辑拆出来对五种真实 API 响应分流、逐条比对上一轮 7 条 Low 的落地位置）→
**Opus R2 未跑（逐条落地核对，无争议项）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 零 finding，但**这是正确行为**——这轮确实没有可报的缺陷，它没有硬凑。而且它的 SKELETON 把改动概括得很准（「新脚本正确解析 JSON 和 frontmatter，fail closed on missing values；git-guard 的改动正确分离了错误原因并避免了 stderr 污染」），**「避免 stderr 污染」这半句抓到了这次改动里最不显眼的那个点**——那正是注释里花了 5 行论证的东西。
- **下次怎么榨出更多信号**：这类「上一轮 Low 的落地 PR」有一个天然的评审结构——**逐条对照**。下次可以把上一轮 review 的 finding 列表一起喂进 prompt，要求「对每一条，指出本 diff 在哪一行落地了它，或者说明它没被处理」。这会把它从「找新问题」切换到「核对清单」，而后者是它更擅长的模式（#153 / #158 的表现说明它做交叉比对是可靠的）。
