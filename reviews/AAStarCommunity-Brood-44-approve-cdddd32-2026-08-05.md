## Verdict: APPROVE（首轮，head `cdddd32a`）—— **更正比原判据强，而且它自己找出了我没想到的那一半**

我在 #42 里提的是「分支名可复用 → **误删**」。这个更正把它收了，**并且自己找出了另一个方向的错——漏删**：

> ① **漏删**（`work-pr18` / `fix-pr18-round2` / `worktree-agent-*` 的分支名从没当过 PR head，但它们的 tip 就是 PR#18/#23 的已合并 head）；
> ② **误删**（分支名可复用，同名分支删掉重开后内容全不同，旧的 MERGED PR 仍然是 MERGED）。

**「只按分支名匹配」会同时朝两个方向错——这个概括比我提的那一半准。**

### 我实测了三件事

**1. 「漏删」属实。** `work-pr18` / `fix-pr18-round2` 在全部 PR 的 `headRefName` 列表里**都查不到**——它们确实从没当过 PR head。

**2. 新判据（FU-4：本地 tip == 或是任一已合并 PR 的 `headRefOid` 的祖先）真的有效。** 我拿本地还在的分支跑了一遍：

```
✅ feat/pre-pr-mechanical-rules → 是 #42 head 的祖先        ✅ pr21-f2f829d → #21
✅ pr-21-review / pr-21-verify  → 是 #21 head 的祖先        ✅ pr22-r2 / pr22-r4 → #22
✅ pr-22-review-882f87a         → 是 #22 head 的祖先        ✅ pr28-head / pr28-review → #28
✅ pr-28-review                 → 是 #28 head 的祖先        ✅ pr18 → #18
── 12 个里认出 11 个可删
── 对照 git branch --merged main: 0 个
```
**而这 11 个的分支名没有一个当过 PR head** —— 正好把「漏删」这条完整印证了：旧判据一个都认不出来，新判据 11 个全认出来。

**3. FU-2 的前提仍然成立**：本地 23 个分支，`git branch --merged main` 返回 **0**。

### 更正写在文件头部而不是改原行，这个做法是对的

账本自述 `append-only · 永不删行`。改原行会让「当时是怎么想的」消失，而这条更正的价值恰恰在于**记录了判据是怎么从错到对的**。放在头部 + 明写「**不要照它实现**」+ 指向 FU-4，读的人不会走错。

### 驳回

- **R1a「引用了 FU-4 但本 diff 里没有定义，确认它在别处存在或补上定义」** —— **它就在同一个文件第 21 行**（`- [ ] FU-4 · B · src=PR#42 review [Low] + 2026-08-05 清理 28 个分支的实测 …`），距离这条更正 6 行。R1a 只看了 diff 没看文件。

### 非阻塞

- **[Low] 新判据要求「先 `git fetch origin pull/N/head` 把 head 抓到本地再算祖先」——这一步的成本值得写清楚。** 仓库里有 40+ 个已合并 PR 时，逐个 fetch 会很慢。实现时建议：先用 `gh pr list --state merged --json headRefOid` 拿到全部 oid，**只对本地已有的 oid 直接算**，缺的再按需 fetch；或者一次性 `git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'`。我上面那段实测就是走的「先批量拿 oid，`git cat-file -e` 过滤本地已有的」，12 个分支瞬间出结果。
- **[Low] 祖先判定对「本地分支领先于 PR head」的情况会判不可删** —— 即分支合并后本地又提交过。那是正确行为（有未合并的工作），但值得在实现里把这类单独报出来（「有本地新提交，跳过」），而不是和「压根没合并」混在一起报，否则用户看不出该不该管。

### Assumptions

- 在独立 worktree（head `cdddd32a`）里读账本，在 `~/Dev/aastar/Brood` 主 checkout 上**只读地**跑了 `git branch` / `git merge-base --is-ancestor` / `gh pr list` 来验证判据；**没有删除任何分支**，也没有改动任何文件。
- 实测用的临时引用（`_pr18chk`）已删除。
- **R2/R3/R4 未跑** —— 11 行文档，且核心判据我已实测。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `cdddd32a`）：DeepSeek R1a
（`deepseek-v4-flash`；1 条「FU-4 未定义」，实为同文件第 21 行）→ Sonnet 机械验证（`gh pr list` 全量
`headRefName` 确认「漏删」属实、用 `merge-base --is-ancestor` 在 12 个本地分支上实跑新判据得 11/12、
对照 `git branch --merged main` 为 0）→ **Opus R2 未跑；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：1/5。** 唯一一条 finding 是「引用了 FU-4 但没定义」，而 FU-4 **就在同一个文件、下方 6 行**。这是**只读 diff 不读文件**的典型失败——而这类「往已有文档里加一段」的 PR，被引用的东西**几乎必然在 diff 之外**。
- **下次怎么榨出更多信号**：这是个可以直接消除的失败模式。对文档类 diff，喂给 R1 的不应只是 diff，而应是**改动后的完整文件**（这些文件都很小）。或者在 prompt 里写死：「diff 里引用的任何标识符（FU-n / 章节号 / 文件名），在判定它『未定义』之前，必须说明你是在**哪个范围**里找过的；只在 diff 里找不到不构成 finding」。
