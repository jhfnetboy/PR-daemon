## ✅ APPROVE — 四条台账逐条核过，数字全对；两处措辞下次 append 时补

`docs/agent/followups.md` +4 行（FU-20..FU-23），纯散文台账。按纯文档 PR 的裁定线（**实质性错误**才 REQUEST_CHANGES；内部精度问题记成建议）走，结论是 APPROVE。

### 机械核验（我实跑的，不是读出来的）

| 条目 | 断言 | 核验结果 |
|---|---|---|
| FU-20 | 15 个提交 / 49 文件 / +4116 行 / 5 条 🔴 | `git diff --shortstat 327c708..b497b12` → **49 files, 4116 insertions** ✓；`git log` 该区间 **15** 个提交，**15/15 都没有 `(#N)` 后缀**，subject 带 🔴 的**正好 5 条** ✓ |
| FU-20 | 五个 hash 及其描述 | `f5d6199 / 1740232 / a04168e / 2a18547 / b3b52ab` 全部存在，subject 与描述一一对上 ✓；`git show --stat 1740232` = **689 insertions** ✓ |
| FU-21 | `DEFAULT_TOL=1.5`（`geom_guard.py:87`）、判据在 `:266` | 两处**逐字命中** ✓ |
| FU-21 | CG 5.0 / AI 2.1 → drift≈2.38x 在容差内 | `exp(\|log(2.1/5.0)\|)=2.381 ≤ 1+1.5=2.50` → **within=True** ✓ |
| FU-22 | `modal_app.py:782-783` 写 geom_guard/geom_detail/geom_mode | **逐字命中** ✓ |
| FU-22 | log-only 下证据只能靠 stderr | 追链成立：`geom_rejected_views`(:838) ← `degraded_to_cg`(:789) ← `geo["enforced"]` ← `mode=="enforce"`，而 `_mode()` 默认 return `"log"`(`geom_guard.py:166`) → **默认路径下结构上不可达** ✓ |
| FU-23 ② | restore 期间 pagehide 的 flushPersist 直接返回 | `chat.ts:1694` 早退 ✓；关键是 `addEventListener('pagehide', flushPersist)` 在 `:2026`，**在 restore 的 `.then()`(:2021-2024) 之外**——所以监听器确实已挂、确实进了函数再早退，而 observer 要到 `:2022` 才装 ✓ |
| 台账机器可读性 | 本文件被 pilot 交付闸消费（`followups.sh count-open == 0`，见 `acceptance.md:60` / `progress.md:45`） | 实跑 `followups.sh count-open`：**base=15 → head=19**，四条新行都被 `^- \[ \] FU-` 正确解析，无格式破坏 ✓（编号无碰撞，base 最大 FU-19；四条都带 `src=`，即本文件头部声明的去重键） |

### 两条建议（**非阻塞**，下次 append 时带上即可，本 PR 不必回炉）

**1. FU-22 的 `:813` 指错了结构 —— 但这条 finding 本身比你写的更强。**

`_meta.providers` 的实际组装在 **`:826-829`**（`prov_meta = {k: {provider_used, provider_requested, fallback_from}}`），包成 `_fin_meta` 在 **`:834`**。`:813` 落在 `item` 字典里（`:811-815`），那是 `usage_list` → `out["_usage"]`(`:824`)，是另一条通道。

不过 —— **`_usage` 也是 API 面向的**：`:1009-1010` 解包后在 **`:1015`** 随 `/render-result` 返回（`return {"status":"done","usage":usage,...}`），`apps/api/src/render-store.ts:10` 的 `IMG_META_KEYS` 里也带着 `'usage'`。而它的 per-finish item（`:811-820`）同样一个 `geom_*` 都没有。

所以「前端和 `/render-result` 都拿不到」在**两条 meta 通道上同时成立**，不只是 `_meta.providers` 那一条。这条你其实是**少写了一半**。

顺带对照：`render_set` 在 `:551` 是把**完整 per-view meta**（含 geom_*）整个传进 `_meta.providers` 的，finish 这边才是手挑三个字段 —— 修法就是照 `:551` 的样子把 `m` 透传，一行的事。

（说破一点：这条正是全文最扎的地方 —— 它明写「行号是核过的 —— Codex 给的 768/814 偏了几行」，而 `813` 相对真值 `826` 并不比 Codex 的 `814` 更近。骗过核对的是 `:813` 那行长得太像：`"requested_provider": ..., "actual_provider": used` —— provider 形状的文本，错误的结构里。）

**2. FU-23 ① 漏了第三层兜底，把丢图窗口说宽了。**

`restoreImages()`（`chat.ts:1780-1793`）在 `im.remove()`（`:1796`）之前还会走 `fetchStoredRender` → **R2，保留 30 天**。所以「IndexedDB 取不到 → 移除」不成立：**登录用户 + 30 天内是能捞回来的**，真正丢图还需要叠加「匿名出图不落库 / 超 30 天 / 换了账号」。

①的其余部分逐字准确 —— `chat-images.ts:79-82` 的 `t.onerror`/`t.onabort` 都是静默 `res()`，代码自己的注释 `:81` 就写着「配额满会 abort —— 静默,别抛」。

### 关于 FU-20 收尾那句「而不是只保护 main」

我一度想把它记成实质错误：以仓库 owner `jhfnetboy` 身份查，`repos/jhfnetboy/CMIC/branches/main` 返回 **`"protected": false, "protection": {"enabled": false}}`**，`preview` 同样 false，owner `.type == "User"`（不可能有 org ruleset），`/protection` 与 `/rulesets` 全部 403 `Upgrade to GitHub Pro or make this repository public`。

**PK 轮把这条打回来了，我认。** 「只保护 main」有一个成立的读法：`.github/workflows/ci.yml:16-18` 是 `on: push: branches: [main]` + `on: pull_request` —— **直推 `preview` 一条 CI 都不跑，推 `main` 会跑**。机械闸的不对称是真实存在的，这句话在这个读法下字面为真。

留一条给下次 append 的事实：**这个私有仓当前的套餐上分支保护/ruleset 都拿不到（403）**，所以 FU-20 作为 A 级项，它的修法照原样是执行不了的 —— 要么升 Pro、要么转公开、要么挪进 org。免费的部分替代是把 `preview` 加进 `ci.yml` 的 `push.branches`，但要写清楚**它不等价**：买到的是「推了会跑 CI」，不是「必须走 PR」。

另外一条可以加进 FU-20 的事实：把这 15 个提交带进 main 和生产的 **PR #188 本身 `reviews: []`** —— 一条 review 都没有。流程的洞比这条写的还宽一点。

### 写得比我会开的方子更好的地方

**FU-21 对 Codex 的那次反驳。** Codex 说「tol 从 1.5 放宽到 2.5」，作者回源码判定这是把同一个参数说成了两个数 —— 而 `geom_guard.py:73` 的文件头注释确实独立写着「默认容差 **2.5 倍**」，`:87` 又确实是 `DEFAULT_TOL = 1.5`。**两个数字真的都在仓库里，描述的是同一个参数**，这正是这条给出的结论。这一处 R3 轮的 Codex 自己也没纠正过来。

### 顺手记一条（本 PR 之外，值得单开 FU）

`geom_guard.py:112` 的 docstring 首行还写着「`enforce`(拦截并退回 CG,**默认**)」，而紧接着 `:113` 就自我更正「🔴 默认【仍然】是 log」，`:166` 也确实 `return "log"`。首行是 #165 回退后没跟着改的残留 —— 本 PR 的两条新条目对默认值的判断都是对的，stale 的是那行 docstring。

---

### Rounds

- **R1a/R1b（DeepSeek v4-flash，双通道）**：两遍都只是把四条台账原样复述成 findings（全部锚在 `followups.md:34-37`），零独立核验，**全部 rejected**。
- **R2（Opus 独立读）**：独立复核了 tol/drift/782-783/1694/2026 各处，并独立发现 FU-23 ① 漏 R2 兜底层。
- **R3（Codex gpt-5.5 对抗）**：CHALLENGE 了 FU-20 那条（ci.yml 的读法，**challenge 成立，已采纳**）；CONFIRM 了 `:813` 指错结构、FU-23 ① 漏第三层、以及 `render_set` 与 finish 两条路径的不对称。
- **R4（Opus 终裁）**：被要求先证伪本轮最强 finding —— 反例部分成立（`:813` 确实落在一条真实且 API 可见的 provider-only 投影上），据此把 F2 降到非阻塞，并顺手挖出「`_usage` 是第二条同样丢 `geom_*` 的通道」这个 FU-22 自己没写的加强项。

四条台账的**事实**部分我没找到实质性错误：所有数字精确、所有 hash 存在、所有代码锚点除 `:813` 外逐字命中、结论方向全部成立。两条建议都属于「下次 append 更准/更强」，本文件 append-only，回炉重来的代价大于收益。
