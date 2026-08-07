## ❌ REQUEST_CHANGES — `page_html` 是一条没有服务端防线的通路，而部署脚本会在第二次跑的时候炸

4-round（DeepSeek R1a/R1b → Opus R2 独立读 → Codex R3 对抗 → Opus R4 终裁）。五条 blocking，全部三方独立确认 + 我自己 grep 复核。

先说结论里最要紧的一条：**这个 PR 声称的防线「前端剥 + 服务端断言」，服务端那一半不是漏调了，是用现有工具写不出来。**

---

### 🔴 1. `assertNoCommercial` 拿到字符串是**静默空操作** —— 「服务端断言」这句话没有实现

`share.ts:159-172`：

```ts
const walk = (v, path, d) => {
  if (Array.isArray(v)) { ... return; }
  if (v && typeof v === 'object') { ...检查 key 名... }
  // ← 字符串两个分支都不进,直接返回
};
```

它测的是**对象的键名**（`COMMERCIAL_KEY.test(k)`）。传一个 HTML 字符串进去，`Array.isArray` 假、`typeof 'x' === 'object'` 假 —— `walk` 立刻返回，`bad` 为空，不抛。

所以 `schema.sql:492` 写的「真正的防线是『存进来之前就已经剥掉价格』（前端剥 + **服务端断言**）」，服务端断言这一半**没有任何一个现有 helper 能满足**。

现状是：`page_html` 只经过 `index.ts:1204` 的 `typeof === 'string' && .length <= SHARE_PAGE_MAX`，然后 `share.ts:262` 原样入库、`:292` 原样返回给匿名读。`assertNoCommercial` 在 `:245`/`:294` 只盖 `design`。

**「前端已经剥了」不成立** —— Codex 核过路由和鉴权（`index.ts:583-635,1179-1206`）：任何 `inquiry.write` 用户都能直接 `curl` 一个任意 `page_html` 上去。浏览器从来不是边界。

我认真试着推翻这条。最强的反驳是「`buildSharePage()` 克隆 `.quote-left` 一个子树，它**就是**结构白名单，和 `pickDesign` 同构」。不成立，四条：

1. **位置** —— 同一个 handler、同一个请求里，`index.ts:1201` 把 `spec: b.spec` 原样传下去、由服务端的 `pickDesign` 做白名单；紧挨着的 `pageHtml` 却直接 bind。**作者对 `design` 明确不信客户端**，这个不对称是漏，不是取舍。
2. **粒度（这条最要命）** —— `pickDesign`（`:110-121`）枚举 20 个具名键、其余全丢，`clampDepth`（`:146`）还二次筛：新加一个 spec 字段**默认是被丢掉**。`buildSharePage`（`sample.ts:492`）选中一个容器，容器内**默认是通过**。而 `sample.html:123-137` 谁都能改 —— 下一个往 `.quote-left` 里塞价格 chip 的提交就直接发出去了。**这正是 #178「黑名单只能抓到你已经知道的东西」那条教训被倒过来用了一次。**
3. 「HTML 没法白名单」被作者自己的代码否掉 —— `sample.ts:513` 已经在成品字符串上跑 `/[$￥]|\bUSD\b|\bRMB\b|\bCNY\b/` 了。字符串级反向对照写得出来，只是**写在了边界的错误一侧**。
4. 见上，断言本身不可实现。

**修法**（不是要你写个 HTML sanitizer）：把 `sample.ts:513` 那条正则搬到服务端，`INSERT` 之前跑一遍 `input.pageHtml`，红了就拒。

### 🔴 2. `schema.sql:495` 的非幂等 `ALTER` 会让**第二次部署**炸，而且它同时打生产

```sql
ALTER TABLE shares ADD COLUMN page_html TEXT;   -- schema.sql:495,可执行,不是注释
```

- base 版 `schema.sql` 的可执行 ALTER 数：**0**（`:216`/`:247`/`:326` 三处都在 `--` 注释里，而且 `:247` 正是这个仓库的既定写法 —— **ALTER 记成注释，另外单独跑**）。
- `deploy-review.sh:27` 是 `set -euo pipefail`，`:73` 的 schema apply 是**三步里的第一步** → 第二次部署在 `wrangler deploy` 之前就 abort，报 `duplicate column name: page_html`。
- **不止 review 环境**：`apps/api/package.json:9` `"db:schema": "wrangler d1 execute cmic --remote --file=schema.sql"` —— 打的是**生产库 `cmic`**。
- 而 `grep -rn migrations apps/api/package.json scripts/*.sh` → **零命中**：没有任何地方跑 `migrations/*.sql`。所以生产拿到 `page_html` 的唯一通路，就是这条被自己毒掉的命令。

你在 #189 的 FU-19 里刚写过这个坑（「ALTER TABLE ADD COLUMN 不幂等，重跑报 duplicate column，所以也不能靠『每次都全跑一遍』兜底」）—— 同一天。

**修法**：删掉 `:495`，把 `page_html TEXT` 并进 `CREATE TABLE IF NOT EXISTS shares (…)` 的表体（`:477-485`），已建库靠 `migrations/0008` 单独跑，并照 `:247` 的样子在 schema.sql 里留一行注释记账。`share.test.ts:63` 是对 `:memory:` 新库 exec 整个 schema.sql，所以照样绿。

### 🔴 3. `share.ts:81` `host.innerHTML = data.pageHtml` —— 公开匿名页 + 同源会话

全树 grep 不到任何 `Content-Security-Policy`。`<script>` 的剥离在 `buildSharePage()` 里，也就是**攻击者自己的浏览器里**，`onerror`/`onload`/`<iframe>` 一个没管。

拓扑让它不只是「自己 XSS 自己」：`deploy-web.sh:44` 和 `deploy-review.sh:81` 都用 `VITE_API_URL="/api"` 构建，`_worker.template.js` 做同源代理 —— 会话 cookie 是**第一方**，且就在服务 `share.html` 的那个 origin 上。注入的脚本能带凭证打 `/api/*`。而这个应用本身在教收件人「这种链接可以放心打开」。

### 🔴 4. 快照里的 3D 图是**空白的** —— 而且这个文件自己在 85 行前就写了修法

`sample.ts:139`：
```ts
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
//                                                    ↑ 没有 preserveDrawingBuffer
```
对照：`sample.ts:224`、`funnel.ts:228`、`customer.ts:534` **三处全都有**，而 `:223` 的注释就写着「preserveDrawingBuffer：渲完立刻 toDataURL 取图（否则拿到空白）」。

`buildSharePage()`（`:500`）恰恰是在 `setTimeout` 里、rAF 循环之外，对**这个**没设标志的 canvas 调 `toDataURL`。WebGL 合成后清空 drawing buffer → 返回一张**合法但全透明**的 PNG。它**不抛异常**，所以 `:503` 的 `if (url)` 照样通过，空白图直接发走。Codex 核过 `.quote-left` 里唯一的 `<canvas>` 就是 `#view`（`sample.html:131`），四张缩略图本来就是 `<img>`。

⚠️ 顺带：1200ms 那句注释「等 3D 画完，否则快照里的 canvas 是空的」**诊断反了** —— 等得越久，空白越确定。

### 🔴 5. `sample.ts:519` 的 512KB 上限在正常页面上就会触发 —— 功能实际是哑的

`.quote-left` 里装着：hero 照片以 data URL 内联（`:277-280`），外加四张 3D 缩略图 base64 内联（`:249` `SZ=440` + `setPixelRatio(min(dpr,2))` → **880×880**，`:260` `toDataURL`，`:265` 写进 `src=`）。四张带光影的 880² PNG 光 base64 就压不到 512KB 以下。

`html.length > 512*1024 → undefined` 是**静默**的，于是 `page_html` 基本永远发不出去。而 `share.html:53-58` 新加的 CSS 正是按「有那四张图」写的。

这也顺带否掉了 `share.ts:92` 的前提（「含内联 3D 画布的 data URL **会被前端剥掉**」）—— `buildSharePage()` 正是**制造**那些 data URL 的地方。

---

### 非阻塞，但值得一起处理

- **`share.test.ts:487-490` 那条「快照也不许带商务信息」是装饰品。** 注释写着「它和 design 走的是两条路，两条都要干净」，实际：`PAGE` fixture 里一个 `$`/`USD`/`MOQ`/`unitPrice`/`12.34` 都没有，服务端也没有任何剥离 —— 把 page_html 的处理全删掉，它照样绿。
  （Codex 在这条上**挑翻了我原本的说法**，我采纳：这个循环对 `design` 通道是**真守卫**（`DIRTY_SPEC` → `pickDesign`/`assertNoCommercial` 会让它红），只对它注释点名的 `page_html` 通道是空的。所以准确说法是「一个通道真、另一个通道假，而标签写的是两个都盖」。按 `acceptance.md:135`「删了还绿的守卫等于没有」，这条比没有更糟 —— 它挂着「价格泄漏」的标签，绿在那条已经漏过三次的路上。）
- **配额扣在校验之前，且每次页面加载都扣。** `index.ts:1189-1191` 先 `count+1`，之后才 `id(b.conversation_id)`，失败不退。而 `sample.ts:451` 的 1.2s 预生成是**无条件**的 → 每次打开确认页花掉一个 `SHARE_CREATE_PER_DAY` 名额。
- **`cmic.shareRef` 缺失时必然 400，且是扣完配额之后的 400。** `conversation_id: ref?.conversationId ?? ''` 过不了 `id()` 的 `/^[A-Za-z0-9._-]{1,64}$/`。而 `:435` 的 `!pageHtml && !ref?.cardKey` 兜不住 —— 只要 `.quote-left` 存在，`buildSharePage()` 就是 truthy。约 50 次刷新之后，客户当天真正点「Share to my team」拿到 429。
- **没有 `GET /shares`。** 这些替客户「预生成」的 30 天公开链接，客户既列不出来也撤不掉；`cleanupShares` 要到过期后 7 天才回收（37 天地板）。
- **双建竞态**：t<1200ms 点按钮 → `:465` 赋一次 `sharePromise`，`:451` 的无条件定时器再覆盖一次 → 两行 `shares`、两个配额，弹窗显示 A 的 token 而状态里是 B。定时器需要 `if (!sharePromise)`。
- **收件人看不到任何规格。** 所有规格在 `#info`，而 `#info` 在 `.quote-right`（`sample.html:141`）里 —— 被剥掉了。`sample.ts:544` 的弹窗文案却承诺「can see the design **and specs**」。
- **`share.ts:5-13` 的文件头注释现在和代码相反了。** 它写着「不复用 `sample.ts`……这两个页面是两条数据通路」「这个文件里没有任何『价格』的概念……就算服务端哪天漏了，也没地方渲染出来」—— `:81` 恰好把这条不变量删了：`share.html` 现在是 `sample.html` DOM 的逐字渲染器。
- **`share.ts:258` 的 `Math.ceil`** 把 `imageDeath` 夹逼向上取整到下一个 UTC 午夜，链接可以比 R2 对象多活最多 24 小时 —— 正是它上面两行注释声称要防的情况。
- 剥价正则 `/[$￥]|\bUSD\b|\bRMB\b|\bCNY\b/` 里的 `￥` 是 U+FFE5（全角），`¥`(U+00A5)/`€`/`£`/`EUR` 都不匹配。目前 app 只出 USD（`sample.ts:322` `currency:'USD'`），所以**今天够用** —— 记一笔，别当成通用的货币检测。

### 三条建议

- 导出一个 `assertNoCommercialText(html)`，**写和读都调**，然后补上这个仓库自己的验收要求那种变异测试：POST 一个带 `$1,234.00` 和 `Unit price` 的 `page_html`，断言 400；把守卫删掉必须变红。
- 剥价从「选哪个子树」改成「选哪些节点」：在 `sample.html` 给可分享的块打 `data-share="1"`，`buildSharePage()` 只留这些。这样 `.quote-left` 里**新加**的元素默认被丢掉 —— 和 `DESIGN_KEYS` 的默认方向一致。
- 配额改成 `createShare` 成功之后再扣；预生成用 sessionStorage 缓存 token，刷新复用而不是重建。

### 写得比我会开的方子更好的地方

`index.ts:1201-1205`：快照超限时**降级成不传这个字段**而不是抛错，理由写在注释里 ——「守卫在下游、上游先炸 = 守卫等于不存在」。一个 reviewer 顺手开个 413 会让失败模式更糟（整个分享失败，而它本来还能靠 design 字段降级）。这个取舍是对的，我没动它。

---

<sub>Rounds — R1a/R1b DeepSeek(v4-flash)：独立命中了 ALTER 非幂等和 `page_html` 缺 `assertNoCommercial` 两条 High，是它在纯代码 diff 上表现最好的一次；「chars vs bytes bypass」那条被驳回（前后端同用 `.length`，没有安全属性挂在这个上限上）。R2 Opus：独立发现 preserveDrawingBuffer、512KB 上限、配额、规格丢失、装饰性测试五条。R3 Codex(gpt-5.5)：5 CONFIRM 1 CHALLENGE（挑翻了我对那条测试的原始说法，已采纳修正）。R4 Opus：被要求先证伪本轮最强 finding，反驳未成立，并挖出 `package.json:9` 的生产库同样中招、以及双建竞态。</sub>
