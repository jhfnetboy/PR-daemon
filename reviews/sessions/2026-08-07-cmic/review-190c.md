## ❌ REQUEST_CHANGES（第三轮 @ `621181a`）—— 五条 blocking 全部真修好了，方案比我开的方子好；但快照有三条新的「客户看不见的错」

先把上一轮的账结清。

### 五条 blocking：逐条核过，全部修好 ✅

| # | 上轮问题 | 现在 |
|---|---|---|
| 1 | `assertNoCommercial` 走键名，喂字符串是静默空操作 → 「服务端断言」写不出来 | ✅ **结构性重做**：整段 HTML → 结构化图片块。`pickBlocks`（`share.ts:234-249`）是**默认拒绝**白名单，和 `pickDesign` 同方向；`DATA_IMG` 只认 `data:image/(png\|jpeg\|webp);base64`，**没有 svg**、不许 `http(s):`；新增 `commercialTextIn()` 补上文字级那一半，且**拒绝而不是剥离** |
| 2 | `schema.sql:495` 非幂等 ALTER | ✅ 可执行 ALTER 计数 **0**；`page_json` 进了 `CREATE TABLE`，ALTER 单独在 `migrations/0008-shares-page-json.sql`，旧的 `0008-page-html.sql` 已删 |
| 3 | `innerHTML = pageHtml` | ✅ 改成 `createElement('img')` + `im.alt` + `figcaption.textContent`，`share.ts:100` 写着「永不 `innerHTML`」；`share.html` 还加了 CSP |
| 4 | 缺 `preserveDrawingBuffer` → 空白截图 | ✅ 快照**根本不再读 `#view` 活画布**，改用离屏 renderer 的 `lastViewUrls`（那个设了标志）；`:522` 的注释把失败模式原样写下来了 |
| 5 | 512KB 上限让功能静默哑火 | ✅ 新增 `shrink()` 重编码成 JPEG（hero 1100px@0.82、视图 560px@0.8），上限改成 700KB **UTF-8 字节**、单图 260KB 前后端对齐 |

上轮非阻塞项也一并修了：双建竞态（`:478` 加了 `if (!sharePromise)`）、配额扣在校验前（`shareRef()` 返 null 就不发请求）、收件人看不到规格（规格改从 `design` 白名单渲染）、货币正则（我核过 `¥` U+00A5 和 `￥` U+FFE5 现在都在）。

**新测试是真承重的**：删掉 `pickBlocks` 里的 `!DATA_IMG.test(src)`，EVIL 数组里 svg / 外链 / `javascript:` / 空 src 四块全进去，三条断言同时红；删掉 `commercialTextIn` 那两行，六条红。和上一版那个 fixture 里压根不含目标串的装饰性测试不是一个量级。

---

### 🔴 三条新 blocking，都是「发送方永远看不见」的那一类

**1 [High] `sample.ts:474-477` —— 缓存的 `cmic.shareToken` 会把旧设计、甚至已撤销的死链接递给老板**

`cmic.shareToken` 在 `:460` 写、`:475` 读，读到就 `sharePromise = Promise.resolve(cached)`，于是 `:478` 的 `if (!sharePromise)` 定时器**永不重建**。而全 `apps/web/src` 里这个 key **零 `removeItem`**（我 grep 过）。

更要命的是**顺序**：`:474-477` 在模块求值时就读缓存，**早于 `shareRef()`（`:436-442`）被查**。所以 `goToQuote()` 刚重写的 `cmic.shareRef`（`chat.ts:933-935`，`cardKey = deliveryKey(type, dims(), v, color)` —— 颜色和变体就在 key 里）被完全忽略。**这不是竞态，是确定性地发旧 token。**

三条路径全部可达，而且都是同标签页导航（`chat.ts:941` 的 `location.href`、`sample.html:106` 的 `<a href="/chat.html">` —— sessionStorage 按规范存活）：

- **(a)** 回对话改色/换 logo → 回确认页 → 老板收到的是**旧设计**。这就是 #173「客户选了白，拿回来两张不是白的」原样重演，只是换到了分享这条路上。
- **(b)** 点「＋ New conversation」开全新方案 → 同一个旧 token。`newChat()`（`chat.ts:1982`）清了 6 个 key，`cmic.shareToken` 和 `cmic.shareRef` **都不在里面**。
- **(c) 最糟**：点「Turn off this link」，撤销在服务端成功了（`:613-619`），但既不清 sessionStorage 也不清 `sharePromise` —— 再点一次 Share，弹窗把**那个已死的 token** 递出来，还配着「Anyone with this link can see the design and specs」（`:596`）。**应用主动断言一个死链接是活的**，对方打开是 404。

我一开始把这条判成 Medium 非阻塞，理由是「要走特定导航序列」。R2 说我判宽了，R4 把我那个理由逐条拆了 —— **我认，上调 High**。尤其 (c)：它不需要重新加载，只要一次误点。

**修法两处三行**：缓存里连 ref 一起存（`{token, expiresAt, cid, cardKey}`），只有和当前 `shareRef()` 匹配才复用；`newChat()` 的清单加上 `cmic.shareToken` / `cmic.shareRef`；revoke 成功分支加 `sharePromise = null; sessionStorage.removeItem('cmic.shareToken');`

**2 [Med-High] `deploy-review.sh:73` —— review 环境永远拿不到 `page_json`，每次建链接都 500**

`CREATE TABLE IF NOT EXISTS shares` 在 `origin/preview` 的 schema.sql 里就有（我核过，第 475 行），所以 `cmic-review` 那张表**已经存在** —— 这次把 `page_json` 加进 `CREATE TABLE` 对它是 **no-op**。而 `deploy-review.sh` 只 apply schema.sql（`:73`），**没有任何 migrations 步骤**；`grep -rn migrations scripts/ apps/api/package.json .github/` 找不到任何 runner。

净结果：review 环境每个 `POST /shares` 都死在 `no such column: page_json` —— **原样复现这个 PR 要修的那个客户症状**（「Creating link… 闪一下什么都没发生」）。

生产那条路你**修对了**（schema.sql 无可执行 ALTER，checklist 也把「①迁移 → ③部署 API」排对了）。漏的只有 review 库。

⚠️ 这是 FU-19 那个洞**同一天第二次咬人**（上轮是 ALTER 放错位置，这轮是 review 库拿不到列）。加一行 `wrangler d1 execute "$REVIEW_D1" ... --file=apps/api/migrations/0008-shares-page-json.sql` 能救急，但 FU-19 里写的 `schema_migrations` 表 + 有序 runner 才是根治 —— 它现在已经是两条独立 finding 的共同根因了。

**3 [Med-High] `sample.ts:566-573` —— 快照读 `lastViewUrls` 不等它渲完；「功能实际是哑的」修了尺寸那半，没修时序那半**

同一个文件里，**PDF 那条路 230 行之前就把这件事做对了**（`:329-331`）：

```ts
let ready = currentViewsReady;
await ready;
while (ready !== currentViewsReady) { ready = currentViewsReady; await ready; }
// 注释原文:只 await 一次会绑在旧的上 → 读到过期/空 lastViewUrls(Codex High-1 残口)
```

而快照这条路（`:570`）是**裸读**：`for (let i = 0; i < lastViewUrls.length && i < 4; i++)`。

`lastViewUrls` 只在 `renderViews3d()` 全部渲完时一次性原子提交（`:271`）—— 那是 `await currentLogo()` + PMREM + 4× `buildBoxGroup` + 4× WebGL 渲染 + 4× 880×880 的 `toDataURL`。`refreshViews()` 在 `:653` 触发，定时器在 `:478` 武装。**冷加载上这套超过 1200ms，快照就带着 `lastViewUrls === []` 建出来**，只有 hero 甚至全空。

而且**缓存让它不会自愈** —— 那个残缺快照的 token 被冻在 sessionStorage 里，这个标签页的余生都用它。

修法就是把 `:329-332` 那三行搬过来。

---

### 两条 Low

- `share.ts:330-331`：总量超 `SHARE_PAGE_MAX` 时 `blocksOk = null`，**整份快照静默丢**。客户端只逐张卡 260KB、不校总量 —— hero 260KB + 4×120KB = 740KB 就触发。建议从尾部逐块丢到装得下，而不是全丢。（被上面第 1 条放大：一旦丢了，这个标签页就一直是丢的。）
- `shrink()`（`:539-557`）重编码后仍超限就返 `null`、静默丢掉那张，没有降质重试（比如退到 0.7/900px）。

### 一条既有问题（不是本轮回归，记一笔）

任何 `inquiry.write` 登录用户都能 curl 上来 8×260KB 任意位图 + 任意 `alt`/`cap` 文字，拿到一个第一方域名、匿名可达、页面自称「Someone shared this with you」的页面。`textContent` 挡住了 XSS，挡不住「用你的域名展示我的图」。低产但真实的钓鱼寄生页。功能内生，不阻塞本轮。

### 一条被驳回的

`readShare`（`:398`）重跑了 `pickBlocks` 和 `assertNoCommercial(design)`，唯独没重跑 `commercialTextIn(blocks)`。R2 提的，**Codex 挑翻了，我采纳**：写路径已经拒绝了，落库的行不可能是脏的。纯纵深，不阻塞。

---

### 写得比我开的方子更好的地方

我上一轮开的方子是「把 `sample.ts:513` 那条货币正则搬到服务端，`INSERT` 之前跑一遍」—— 那是给一段 HTML 外挂一个字符串过滤器。

**作者换的是表示法**：整段 HTML → 结构化图片块。于是白名单（`pickBlocks` 只让位图过）成了**主防线**，文字对照退成真正的反向对照 —— 这把一个**语义级**问题降维成了**格式级**问题，而后者能被 6 行正则和 6 条变异测试真正钉死，前者不能。

顺带还捡回了我上轮记成非阻塞的那条：规格改从 `design` 白名单渲染，收件人**又看得到规格了**（上一版把 `.quote-right` 整个剥掉，连规格一起弄丢）。

以及一个我没想到的细节：离屏 renderer 是 `alpha:true`，直接转 JPEG 会得到黑底 —— `shrink()` 里先 `fillRect` 铺白底再画。

<sub>Rounds — R1a（带 `--prior-review`）/R1b DeepSeek(v4-flash)：两条 finding **都不成立** —— 「`commercialTextIn` 不查 `src`」代码里明写了理由（base64 假阳性，且 `src` 已被 `DATA_IMG` 限死为位图），「正则漏 `¥`/`￥`」看反了（两个码点都在字符类里，正是上轮我提的那个 Low 已被修掉）。R2 Opus：独立发现 F2，并把我对 F1 的 Medium 判定**上调为 High**（说我判宽了）。R3 Codex(gpt-5.5)：F1/F2 CONFIRM，F3 补了一句关键的（声明 MIME 与实际内容不符也执行不了，且 CSP 是有效纵深），F4 CHALLENGE（已采纳）。R4 Opus：被要求先证伪 F1，反驳四条腿断了三条，并挖出第三条 blocking（`lastViewUrls` 时序 —— 尺寸那半修了、时序那半没修，而正确写法就在同文件 230 行之前）。</sub>
