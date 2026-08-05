## Verdict: APPROVE（首轮，head `1a5cee16`）—— **「一直是死代码」这个断言我复现了，而且新开的口子是真 fail-closed**

### 断言一：`merge-pr` 此前对**每个**仓库都直接死。**成立，我实跑了。**

```
gh --version → 2.92.0（和 PR 引的一致）

旧写法  gh repo view --repo AAStarCommunity/Brood --json defaultBranchRef …
        → rc=1, captured=''            ← gh 把 help 打到 stdout 然后退出 1
新写法  gh repo view AAStarCommunity/Brood --json defaultBranchRef …
        → rc=0, captured='main'
```
而旧代码的**下一行**是
```sh
[ -n "$def_branch" ] || die "cannot resolve repo default branch — refusing merge-pr until the trunk check is verifiable"
```
所以不是「检查被静默跳过」，是**每次 `merge-pr` 都在这里 die**。这条护栏不是太严，是**根本跑不起来**。`gh repo view` 确实只接位置参数（不像 `gh pr view/merge` 有 `--repo`），改成位置参数是对的。

### 断言二：`--allow-trunk` 不是绕过。**成立，逐条实测。**

| 要求 | 实测 |
|---|---|
| 分支保护必须要求审批 | `gh api repos/…/branches/main/protection` → `required_approving_review_count: 1` ✅ |
| 读不到保护规则 → 拒绝 | 我拿一个不存在的分支试：API 把 `{"message":"Branch not found",…,"status":"404"}` 打到 **stdout**，于是 `approvals` 捕到的是那段 JSON → 命中 `''\|*[!0-9]*` → **die** ✅ 真 fail-closed |
| 保护存在但不要求审批 | `// 0` 兜底成 `0` → 数字 → 过 case → `[ 0 -ge 1 ]` 失败 → die ✅ |
| PR 必须 `APPROVED` | `reviewDecision != APPROVED` → die ✅ |
| `--admin` 仍被拒 | `--admin\|--admin=*\|--repo\|--repo=*\|-R\|-R*` 全拦，**连附值形式和 `-Ro/r` 这种粘连写法都覆盖了** ✅ |

而且 **Brood 自己就是这个 flag 的直接用户**，我核过它的前提成立：`main` 是 default branch、`required_approving_review_count: 1`、`enforce_admins: true`、**`dismiss_stale_reviews: true`**（最后这条很关键——它意味着 `reviewDecision == APPROVED` 不可能是钉在旧 commit 上的过期批准，而这个仓库我在 #36 上正好踩过一次那种情况）。

### 我认同那条设计论证

> 一个必须被绕过的护栏，比没有护栏更糟——因为它教会人绕过护栏。

这不是给放松找借口：这个口子**只放松「合到哪里」，没放松「有没有被 review」**，而且它要求的是**服务端的证据**（GitHub 分支保护）而不是本地 flag 的一面之词。用一个比脚本更强的机制去替换脚本的限制，这个方向是对的。

### 非阻塞

- **[Low] 注释里说分支保护「`enforce_admins` binds admins too」，但脚本并不校验 `enforce_admins`。** 我 grep 过：这个词在整个脚本里只出现 1 次，就在那条注释里。今天不影响正确性——脚本自己要求 `reviewDecision == APPROVED`，不依赖 `enforce_admins`；但注释把一个**没验证的属性**写成了论据的一环。要么顺手加进校验（多一个 `--jq .enforce_admins.enabled`），要么把这半句改成「（本仓库另外还开了 `enforce_admins`）」这种陈述而不是保证。
- **[Low] 保护规则读不到时 die 的措辞值得再细分一层。** 现在一条消息同时覆盖「需要 admin scope」和「分支根本没保护」两种情况，而这两种的处置完全不同（前者是换 token，后者是先去开保护）。API 返回的 body 里其实已经有 `message` 可以区分（我实测 404 会返回 `Branch not found`），打出来能省掉一次来回。
- **[Low] 拒绝 flag 的黑名单是「枚举形状」。** `--admin=*` / `-R*` 这些粘连形式已经想到了，覆盖得比多数人细；但黑名单天然追不上新 flag。如果以后 `gh pr merge` 加了别的能绕过保护的 flag，这里不会自动知道。改成**白名单**（只放行已知安全的 `--squash`/`--merge`/`--rebase`/`--delete-branch` 等）会更耐久——不过那是另一次改动，现在这样也说得通。

### Assumptions

- 在两个独立 worktree（`origin/main` 与 `1a5cee16`）里读代码，未改动 `~/Dev/aastar/Brood` 任何文件。
- **`gh` 的行为是实跑的**（本机 gh 2.92.0，和 PR 引用的版本一致），不是照着文档推的；fail-closed 那条也是拿真实 API 响应验的，不是读代码推的。
- **我没有执行 `merge-pr` 本身**——它会真的合并 PR，而我是评审方，不碰合并。上面的验证都是把它的判定逻辑拆出来单独跑。
- **R2/R3/R4 未跑** —— 两条核心断言都有我自己实跑的输出，无待判定的争议项。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `1a5cee16`）：DeepSeek R1a
（`deepseek-v4-flash`；见下方自评）→ Sonnet 机械验证（实跑新旧两种 `gh repo view` 写法对比 rc 与捕获值、
读旧版下一行确认是 die 而非静默跳过、拿不存在的分支实测 fail-closed 分支、核对 Brood main 的
`required_approving_review_count`/`enforce_admins`/`dismiss_stale_reviews`、grep 确认 `enforce_admins`
只在注释里出现）→ **Opus R2 未跑（两条断言均已实测定论）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 它的 SKELETON 判断相当准：「`--allow-trunk` 文档清楚且 fail-closed，但 `gh repo view` 的位置参数改动对含空格的仓库名可能有问题，且 `gh repo view` 的错误处理可能掩盖失败」。**「错误处理可能掩盖失败」这半句指对了要害**——旧代码正是靠 `|| true` 把 rc=1 吞掉，只是它没意识到下一行的 `[ -n … ] || die` 反而把它变成了硬失败。至于「含空格的仓库名」：GitHub 的 `owner/repo` 不允许空格，而且脚本里 `"$repo"` 是加引号的，不成立。
- **下次怎么榨出更多信号**：这个 PR 的核心是「一个外部命令的调用方式错了」。下次对改动 CLI 调用的 diff，在 prompt 里写死：「对被修改的每一条外部命令，给出新旧两种写法，并说明如何用一条命令验证哪个是对的」——把它逼到**给出可执行的判别方法**，而不是停在「可能有问题」。它这轮已经很接近了，差的就是这一步。
