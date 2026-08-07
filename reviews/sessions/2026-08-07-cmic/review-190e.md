## ✅ APPROVE（第五轮 @ `8307330`）—— 三条 blocking + 四条 Low 全部真修好

### 逐条核过

| | 现在 |
|---|---|
| **N1** `buildShareBlocks()` 在 try 外、变得会 reject → Share 按钮永久死 | ✅ `:454` `.catch(err => { console.error(…); return [] })`，`:512` `await sharePromise.catch(() => null)`。我把 `createShareLink()` 的每条路径都数了一遍：`!API` return / `shareRef()` 自带 try/catch / `buildShareBlocks()` 是 `async` 所以同步抛也会变成 rejection 被 `.catch` 接住 / fetch 全在 try 里 —— **现在它确实不可能 reject 了** |
| **N2** 翻译修在 `fmt()` 的字符串分支而非字段→翻译器表 | ✅ `LABELS` 改成 `Array<[string, string, Kind]>`，**`Kind` 必填** —— 「哪个字段忘了接翻译器」现在类型层面就看得出来。`stock` 分支补上，`variationName` 挪到 `finish` 之后让去重保留正确标签，`<h1>` 兜底不再用 `boxType`（`share.html:91` 本来就有真默认文案「A packaging design」） |
| **N3** migrations 循环每次部署跑一遍 `0003` 整表重建 + 错误分类靠子串 | ✅ 显式 `SKIP_MIGRATIONS="0003-…"`，grep 收窄到 `duplicate column name\|index .* already exists`，其余一律 `exit 1`（`table … already exists` 现在是致命的） |
| 四条 Low | ✅ `:495` 查 `expiresAt` / `:119` HEX 限定到 `kind === 'colour'` / 「Creating link…」提示挪到 await 之前 / `shrink()` 降质**同时**降宽（`[[0.7,0.8],[0.55,0.64]]`） |

**我特意核了一件最可能被这个修法弄坏的事**：跳过 `0003` 之后，全新的 review 库还对不对？—— **对的**。`schema.sql:356` 和 `:362` 两处 CHECK 里本来就带着 `chat_llm`，所以新库不依赖 `0003`。另外把收窄后的 grep 对着剩下七个迁移过了一遍：`0001/0005/0007/0008` 是 `ALTER … ADD COLUMN` → 重跑报 `duplicate column name` ✓ 命中；`0002/0004/0006` 全是 `IF NOT EXISTS` → 直接 exit 0 ✓。**没有哪个迁移被新判据误伤成致命。**

`labels.test.ts` 那条新断言是真会红的：`PAPER_SWATCHES` 是 `Record<PaperStock, …>`，加第四种纸样就多一个 `Object.keys` 项、`STOCK_LABEL[k]` 是 `undefined` → 失败。而且你把「为什么 `STOCK_LABEL` 故意重抄而不 import」写在了注释里（`texture.ts` 有 499KB，分享页要秒开）—— 这比我上一轮建议的「让两张表机械绑定」更好：你说明了不能绑的约束，然后用测试钉住漂移。

---

### 四条 Low（不阻塞，下次顺手）

**1. `share.ts:40` 给 `variationName` 标 `Kind='finish'`，会把一个【已经翻译过】的字符串再翻一次，于是每次打开分享页都刷一条假警报。**

`funnel.ts:95-98` 四个 `MATERIALS` 全都没写可选的 `name`，所以 `:113` 的 `name: m.name ?? finishLabel(m.finish)` 让 `variationName` 恒等于 `'Gold foil'` / `'4C print'` 这种**展示串**。而 `FINISH_LABEL` 的键是 `'foil-gold'` / `'print-black'` —— 于是 `finishLabel('Gold foil')` 落到 `fallback()`，打出 `[labels] finish 缺少英文文案：「Gold foil」—— 客户会直接看到这个中文主键`。

它既不是中文主键，也不会被客户看到（那一行被去重丢掉了）。**但它稀释了 `labels.ts` 唯一的那个铃铛** —— 而这恰好和上一个提交刚在 `labels.ts:24-28` 修掉的空键假警报是同一类。给它一个 `'text'` Kind 就行。

（另外这条的原始问题只是被去重挡住了：一旦有人用上文档里写着的 `name?:` 覆盖，收件人就会看到「Direction: Warm kraft」，而同一个字段 `sample.ts:90` 叫它 Colour、`approve.ts:51` 把它折进 Structure。三处叫法不一致。）

**2. `sample.ts:522` 的 `const r = await sharePromise;` 没有 `.catch`，而一行之上的 `:512` 对同一个变量防了。**

今天安全，但安全的理由是传递性的（`createShareLink()` 恰好不可能 reject）。`??=` 恰恰改变了这行 await 的是谁造的 promise —— 改之前 `:521` 总是新建一个，改之后它可能 await 到 1200ms 定时器那个。**在 `createShareLink()` 里加一个第一次 await 之前的同步 throw，N1 那个失败模式就在下面一行原样复活**（按钮卡在 `Creating link…` 永久 disabled）。加个 `.catch(() => null)` 就闭合了。

**3. `sample.ts:521` 的 `??=` 会复用一个已经 resolve 成 `null` 的 promise。**

走到这一行意味着 `ready` 是假值 —— 其中一种情况是 `sharePromise` 是个 resolve 成 `null` 的 promise（预生成失败过）。`??=` 只在 nullish 时赋值，所以不会重建，`await` 立刻拿到 `null` → 直接报「Could not create the link」，**一次重试都没试**。只有那条失败分支上的 `sharePromise = null` 让**第二次**点击才真的重试。

第 2、3 两条同源，一起改：`if (!sharePromise) sharePromise = createShareLink();` 然后 `await sharePromise.catch(() => null)`。

**4. `deploy-review.sh:90` 跳过 `0003` 之后没有任何验证。** 新库没问题（见上），但一个**从来没跑过 `0003` 的既有库**从此永远不会拿到它：部署照样绿，而 `kind='chat_llm'` 的插入会撞 CHECK、掉进 outbox、chat 成本记账静默丢失。用**只读**的方式补一句就够，不用等 FU-19：循环之后 `SELECT sql FROM sqlite_master WHERE name='cost_ledger'`，不含 `chat_llm` 就 `exit 1`。

顺带：`labels.test.ts` 钉住了**键**的一致性，但**值**才是被重抄的那个。`PAPER_SWATCHES[k].name` 和 `STOCK_LABEL[k]` 目前逐字节相同 —— 在 `texture.ts` 里改个名字（它驱动聊天页的纸样 UI），分享页就悄悄留在旧措辞上，正是这条测试的注释声称要防的漂移。加一句 `ok(STOCK_LABEL[k] === PAPER_SWATCHES[k].name, …)`。

---

### 关于这五轮的一句总结

这个 PR 从「整段 HTML 塞进公开页、服务端那半道断言写不出来」，走到现在这个「只让位图过默认拒绝的白名单、Kind 必填、迁移有跳过名单和窄判据」的状态，中间每一轮都是**换表示法**而不是**加过滤器** —— 这是它能收敛的原因。

有一个形状连着出现了四轮，值得单独记一笔：**每一次修复都堵住了自己那个洞，又开了一个同形状的小口子。** 「静默给出空快照」→「静默让按钮死掉」；「静默缺一列」→「静默缺一张表」；「翻译漏一个字段」→「翻译多翻一次、假警报稀释真警报」。共同点都是**顺利路径变响了、失败路径变更哑了**。上面这四条 Low 全部属于这一类，而且都只要一两行。

<sub>Rounds — R1a(带 `--prior-review`)/R1b DeepSeek(v4-flash)：3 条，两条驳回（「rejected 的 sharePromise 会被重新抛出」—— `createShareLink()` 已经不可能 reject，我逐条数过它的每条路径；「typeName 缺失时 `<h1>` 是空的」—— `share.html:91` 有真默认文案）。第三条（shrink 两次重试后仍超限就静默丢）属实，按尽力而为接受。R2 Opus：确认全部修复，独立发现上述第 1、4 条和「值没被钉住」，并指出我上一轮的一个推理漏洞 —— 我验了 `.catch` 加在生产者身上就收工了，没有重新检查**消费者**，而 `??=` 恰恰改变了被 await 的那个 promise 的来源。R3 Codex / R4 未跑：三条 blocking 的修复都由直接文件证据判定，剩余全是 Low 且无一触及收件人页面或部署路径。按实跑轮数标 **3-round**。</sub>
