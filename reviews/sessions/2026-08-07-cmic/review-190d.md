## ❌ REQUEST_CHANGES（第四轮 @ `cee7513`）—— 三条 blocking 全修好了，但两处修复各自开了个同形状的小口子

### 先更正我自己上一轮的两处

**1. 上一轮我标的两条 Low，你其实都修了，是我读错了。**

- tail-drop 在 `share.ts:331-336`（`while ... kept = kept.slice(0, -1)`），我上次 `sed` 从**最后一处** `SHARE_PAGE_MAX`（`:339`）往后读，正好落在循环之外，于是得出「还是全丢」。
- 降质重试在 `shrink()` 内部 `:566-570`（`for (const q of [0.7, 0.55])`），我上次只读了函数头 7 行，截在循环之前。

两次都是我的量具窗口截短了。顺带把话收回：我在上一轮说 DeepSeek 那句「tail-drop 和 quality-retry 已解决」是编的 —— **它是对的，错的是我**。

**2. `deliveryKey` 的覆盖面我核过了**，`[type, finish, color, dims, logoText, innerColor, product]` —— 换 logo / 换内衬 / 换产品都会让 key 变，缓存会失效。这条我上一轮担心的事不成立。

---

### 三条 blocking：逐条核过，全部修好 ✅

| | 现在 |
|---|---|
| **B1** 缓存 token 递旧设计/死链接 | ✅ 缓存改存 `{token,expiresAt,cid,cardKey}`，`:485` 只在 `cid` 和 `cardKey` 都对得上时复用，对不上就 `removeItem`；`newChat()` 的清单（`chat.ts:1984`）加了 `cmic.shareToken`/`cmic.shareRef`；revoke 成功分支 `:652-653` 同时清 `sharePromise` 和 storage。旧格式的 `{token,expiresAt}` 缺 `cid` → 匹配失败 → 被清掉，不会被误用。 |
| **B2** review 库拿不到 `page_json` | ✅ `deploy-review.sh:82-92` 加了 migrations 循环，`duplicate column\|already exists` 当幂等跳过，**其他错误 `exit 1`**（没有一把梭吞掉）。注释也点明 FU-19 才是根治。 |
| **B3** 快照裸读 `lastViewUrls` | ✅ 搬来了 PDF 那条路的 settle 等待循环，出循环后同步 `const views = [...lastViewUrls]`。 |

另外 `2070d96` 你自己抓到的那条 —— 分享页把数据库主键 `157g双铜` / `哑胶` 直接渲给客户老板 —— 是这一轮**信号最强的东西**：它是从 review 环境的截图上发现的，不是读代码读出来的。

---

### 🔴 三条新的，两条正是上面那两个修复带出来的

**1 [Med-High] `sample.ts:448` —— B3 的修复让 `buildShareBlocks()` 变得会 reject，而它在 `try` 外面**

```ts
const blocks = await buildShareBlocks();   // ← :448，在 try 之外
try {
  const res = await fetch(...);
  ...
} catch (err) { console.error('[share] 预生成失败', err); return null; }
```

改之前 `buildShareBlocks()` 只是读个变量 + `shrink()`（永远 resolve），**不可能 reject**。加了 `await currentViewsReady` 之后它就继承了 `renderViews3d()` 的失败 —— 而 `new THREE.WebGLRenderer` 在 context 耗尽时会抛。

于是：`sharePromise` 变成一个 rejected promise → `$('talk').onclick` 里 `await sharePromise` 在一个**没有 catch 的事件处理器**里抛 → 「现建一次」那条兜底分支永远走不到 → **Share 按钮永久失效，且客户没有任何提示**。定时器那次还会甩一个 unhandled rejection。

对照：PDF 那条路是包在 try 里的。

**修法**：`const blocks = await buildShareBlocks().catch(() => []);`，并且 `await sharePromise` 那处包 try/catch、失败落到重建分支。

**2 [Med] `share.ts:35` —— 中文主键那条修完了，但 `paperStock` 漏了，页面上现在写着「Paper stock: kraft yellow」**

`paperStock` 在 `DESIGN_KEYS` 里（`apps/api/src/share.ts:76`），也在分享页的 `LABELS` 里（`:35` → 'Paper stock'）。但 `fmt()` 只把 `paper` / `lamination` / `finish` 三个路由到 `labels.ts`，`paperStock` 落到兜底的 `v.replace(/[-_]/g,' ')` —— `kraft-yellow` → **「kraft yellow」**。

和 `157g双铜` 是同一类：内部标识符出现在发给客户老板的页面上。人话在 `PAPER_SWATCHES[k].name`（"Kraft" / "Black board" / "White board"）。

⚠️ 根因是**修在了 `fmt()` 的字符串分支上，而不是修在标签表这一层**。所以同一类还剩两处：
- `share.ts:124` 的 `fmt('typeName', …) ?? fmt('boxType', design.boxType)` —— `typeName` 缺失时（老快照 / configure 路径），`<h1>` 里还是会出现 `lidbase`。把 `boxType` 从 `LABELS` 里拿掉只堵住了两个渲染点里的一个。
- `share.ts:32` 的 `['variationName', 'Direction']` —— `funnel.ts:113` 是 `name: m.name ?? finishLabel(m.finish)`，而没有 `MATERIALS` 行覆盖 `name`，所以页面上会**紧挨着出现两行**：「Direction: Gold foil」和「Finish: Gold foil」，同一个值、上面那个标签还是错的。

**建议**：让 `LABELS` 和 `labels.ts` 机械绑定 —— 一个没有翻译器的 key 直接让测试红，`labels.test.ts` 对 `WRAP_PAPER` 已经是这么做的。这样这一类就不用靠下次再截一张图发现。

**3 [Med] `deploy-review.sh:82-92` —— 循环会把一个非幂等的破坏性重建每次部署都跑一遍，而且错误分类靠字符串匹配**

`0003-cost-ledger-chat-llm.sql` 不是 ALTER，是**整表重建**：

```sql
CREATE TABLE cost_ledger_new (...)      -- 裸 CREATE，没有 IF NOT EXISTS
INSERT INTO cost_ledger_new SELECT * FROM cost_ledger;
DROP TABLE cost_ledger;
ALTER TABLE cost_ledger_new RENAME TO cost_ledger;
```

而这个文件**自己的文件头**就写着：「幂等性：干净重跑【不报错】(会再建-拷-换名一遍,数据不丢)；只有【中断的半途】留下 `cost_ledger_new` 时,再跑才会因它已存在而报错。**建议每库只跑一次。**」外加「⚠️ 未包 BEGIN/COMMIT……DROP→RENAME 之间有极短窗口无 `cost_ledger` 表」。

新循环无差别地每次部署都跑它一遍 —— 正是文件头劝你别做的事。八个迁移里只有这一个是这种形状（其余全是 `ALTER` 或 `CREATE ... IF NOT EXISTS`），所以加一个排除名单成本很低。

**更要紧的是分类判据**：`grep -qiE "duplicate column|already exists"` 把 `table cost_ledger_new already exists` 也算成「已跑过，跳过」，部署照样绿。如果某次运行是在 `DROP TABLE` 之后、`RENAME` 之前中断的，`cost_ledger` 已经没了、`cost_ledger_new` 还在 —— 下一次部署会稳定地把这个状态判成「已跑过」，**green 着把表缺失的状态永久保留下来**。

⚠️ 我要明说一处不确定：上面这条依赖「D1 执行 `--file` 时在第一条失败语句处中止、后续语句不再执行」。我**没有验证过** D1 的这个语义（沙箱离线、没有 D1 可打），所以窗口的确切形状可能和我描述的不同。但不依赖这个假设也成立的那半是：**「已经跑过」和「跑了一半坏掉了」这两种状态，靠 stderr 子串是分不开的。**

**修法**：把 `0003` 这类整表重建排除在循环外（显式跳过名单），并把 grep 收窄到 `duplicate column name` + `index .* already exists`，让 `table … already exists` 变成致命错误。根治仍然是 FU-19 那张 `schema_migrations` 账本。

---

### 四条 Low

- `sample.ts:485` 复用缓存时没查 `expiresAt`（DeepSeek 提的，唯一站得住的一条）。标签页得开满 30 天才碰得到，而且任何设计改动已经会清缓存 —— 但补一个 `expiresAt > Date.now()` 是一行的事。
- `share.ts:112` 的 `HEX.test(text)` 作用在**每个字段**上，不只颜色字段。一个恰好是 `#` 加十六进制字符的 `logoText` / `product` 会被渲成色块而不是品牌名。建议限定到 `color` / `innerColor` / `paperColor`。
- `sample.ts:500` 定时器已到、但 3D 还没渲完时点 Share，会阻塞在整套 WebGL 渲染 + 5 次 JPEG 编码上，**而「Creating link…」那个提示只在 `sharePromise === null` 那条分支上设**。这正是这个文件的注释一直在防的「表现成卡住」。
- `shrink()` 只降质不降宽，1100px 的 hero 在 0.55 下仍可能超 260KB 而被静默丢掉；两次重试还是主线程上的同步 `toDataURL`。建议宽度也跟着降（1100→850→700）。

### 一条值得单独说的（B1 的修复是对的，但它站在两条没人守的不变量上）

`deliveryKey` 是为**出图去重**设计的，它不含 `paper` / `lamination` / `paperStock` / `variationName` / `typeName` —— 而这五个都在 `DESIGN_KEYS` 里、都会出现在分享页上。今天它够用，靠的是两条隐性前提：每个 `MATERIALS` 行的 `finish` 唯一（于是 `v.finish` 能代表 `paper`+`lamination`），以及选纸样时一定会同时改 `brief.color`（`chat.ts:1505`）。

**加第五种材质、而它复用了一个已有的 `finish`，#173 就会原样重演**，且没有任何测试会红。更耐久的做法是把 `pickDesign` 可见的那部分 `cmic.selection` 哈希进缓存键，而不是复用 `deliveryKey`。

---

### 两处修复的共同形状（值得记一笔）

B3 和 B2 各自堵住了自己那个洞，又各自开了一个**同形状**的小口子：

- B3 把「静默给出空快照」换成了「静默让按钮死掉」（失败路径没人接）
- B2 把「静默缺一列」换成了「静默缺一张表」（错误分类靠子串）

都是**顺利路径变响了、失败路径变更哑了**。

<sub>Rounds — R1a(带 `--prior-review`)/R1b DeepSeek(v4-flash)：3+2 条。一条站得住（缓存没查 expiry，但 severity 报成 High 偏高）；四条假阳性（`shareRef` 是提升的函数声明且自带 try/catch；`paperLabel` 是 `MAP[k] ?? fallback()` 返回 `string`；`style.background` 只在锚定的 `HEX` 分支内、不可能 CSS 注入）。**它草稿里那句「tail-drop 和 quality-retry 已解决」是对的，是我读错了代码**。R2 Opus：独立发现上述三条新问题，并抓到我那两处读错。R3 Codex / R4 未跑 —— 三条新发现都由直接的文件证据判定，不是推理链；而我唯一一处不确定（D1 `--file` 的中止语义）是任何离线轮次都settle不了的，所以我把它当作显式不确定写进正文，而不是假装某一轮解决了它。按「实际跑了几轮就标几轮」，这是 **3-round**。</sub>
