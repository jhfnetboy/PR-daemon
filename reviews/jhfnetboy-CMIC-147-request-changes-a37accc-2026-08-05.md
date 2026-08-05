## Verdict: REQUEST_CHANGES (head `a37accc`)

这个 PR 的设计判断是对的，而且比常见做法好：

- **看准了本质** —— #143 之前 chips 被前端丢弃，从没显示过；#143 让它成了「点一下就把原文当客户自己的话回传」的按钮，于是它同时是展示面和输入面。这正是 reply 有价格中和、chips 没有的那条缝。我独立核对过 #143 打开的其它路径：`reply` 走 `escapeHtml`/`addAgentSay`，`brief_patch` 走 `sanitizePatch` 且从不回传，盒型卡走本地静态数据 —— **chips 确实是唯一的新输入面**，这个 PR 找对了地方。
- **「整条丢弃」而不是像 reply 那样替换是对的**：2-4 个词的按钮标签挖掉一块会变成读不懂的碎片，代码注释里那个 `"(quote next step) foil"` 的例子说服力很强。
- **`.filter()` 挪到 `.slice(0,4)` 之前**是严格改进：被拦掉的 chip 由第 5 条往上补，而不是让整排变短。
- 负向用例挑得好：`500 units` 和 `3D preview` 都明确测了不许误伤。

我实测了 12 个用例，全部与作者意图一致：`500元`/`3 days`/`3周`/`$99 quote`/`MOQ 500`/`+1 415 555 0123`/`contact 微信 abc`/`www.foo.com`/`sales@foo.com` 拦截，`500 units`/`3D preview`/`Add a window` 放行。作者自己的测试也全绿。

**但有两条 Medium 让这道防线在服务端等于不存在，而且比 #143 之前更危险 —— 因为现在有一个「看起来像覆盖」的通过测试。**

### 🔴 Blocking

1. **[Med] `apps/api/src/chips.test.ts` — 测的是判定函数，不是守卫。变异测试证明了这一点。**
   我把 `apps/api/src/chat.ts:205` 的 `.filter((c) => c && !chipLooksUnsafe(c))` 改成 `.filter((c) => !!c)`（等于把过滤整个删掉），**整套测试依然全绿**。
   也就是说：这个 PR 存在的理由就是那一行，而那一行恰恰是唯一没有任何测试覆盖的。`grep -rn chatTurn` 只有 `chat.ts` 和 `index.ts`，零测试；`e2e/tests/07-chips.spec.ts` 把 `/chat` 整个 mock 掉，绕开了后端。
   **修复**：加一条真正驱动守卫的用例 —— 给 `chatTurn` 喂一个 stub 模型响应 `chips: ['Gold foil','$99 quote','MOQ 300','Velvet insert']`，断言结果恰好是 `['Gold foil','Velvet insert']`。这是唯一一条「有人删掉 `:205` 就会红」的断言。

2. **[Med] `.github/workflows/ci.yml` — 新守卫在 CI 里根本不跑，而且这个 PR 让 ci.yml 自己那句话变成了假的。**
   `test:chips` 加进了 `package.json` 的 `check`，但 ci.yml 是**逐条列举**每个测试（`test:redact` / `geom` / `pdf` / `insert` / `dxf` / `mailer`），**从不跑 `pnpm check`**。`grep test:chips .github/workflows/ci.yml` 零命中。
   而 ci.yml:41-43 写着：「CI 跑的命令和本地【完全一样】…本地跑 `pnpm check` 就等于把 CI 跑了一遍」。这个 PR 之后这句话不成立了 —— 恰恰是这类「文档声称的和实际跑的分叉」最难在后续 review 里被发现。
   **修复**：在其它测试步骤旁边加一条 `- name: chips 内容过滤测试 / run: pnpm test:chips`。

3. **[Med] `apps/api/src/chat.ts:119-125` — 联系方式检测是整类缺口，而且缺的正好是中文那一半。**
   规则只匹配**完整品牌词**，并要求 `+` 前缀或 `https?://`。但一个 48 字符的按钮标签里恰恰不会出现完整品牌词。我逐条跑过，以下**全部放行**：
   ```
   放行  "wx: abc123"       放行  "vx: abc"         放行  "加我 v 信"
   放行  "QQ 12345678"      放行  "t.me/foo"        放行  "wa.me/123"
   放行  "bit.ly/abc"       放行  "13800138000"     放行  "138 0013 8000"
   ```
   `微信` 和 `起订` 已经在拦截表里，说明这是面向中文市场的产品 —— 而 `加V`/`vx:` 正是中文 B2B 里最典型的站外引流写法，不带 `+` 的 11 位大陆手机号是最可能的联系方式泄漏形态。英文那半覆盖得明显更好，对这个产品来说是反的。
   **修复**：同一个文件 `:30` 已经有 `redactContact()`（email / 电话 / URL），把 `redactContact(c) !== c` 加进判定是**该做的**——它能免掉两套定义各自漂移（现在 reply 那半的价格正则已经和 `chipLooksUnsafe` 分叉了：reply 有 `元|美元` 没有 `人民币|eur|gbp`）。
   ⚠️ **但它不够**：我实测了，9 个绕过里它只关掉 1 个（裸 11 位手机号，靠 `\b\d{9,15}\b`）。`wx:` / `vx:` / `加我 v 信` / `QQ 12345678` / `t.me/foo` / `wa.me/123` / `bit.ly/abc` / `138 0013 8000` **仍然全部放行**。所以还要补：短形式 handle `\b(?:vx|wx|qq|line\s*id|ig|insta(?:gram)?)\b`、`/加\s*[vV微]/`、无 scheme 域名 `/\b[\w-]+\.(?:com|cn|net|me|ly|io|co)\b/i`。

### 非阻塞

- **[Low] `apps/api/src/chat.ts:117-118` — 交期/单价同样中英不对称。** 实测放行：`15 天出货`、`0.85/pc`、`80 cents each`、`每个 8 毛`。`\d+\s*days?` 有、`\d+\s*天` 没有；`单价` 有、`/pc`、`each`、`每个` 都没有。
- **[Low] `apps/web/src/chat.ts:693-707` — 前端从 localStorage 还原 chips 的路径不过这个过滤。** 还原路径重新执行了 `MAX_CHIPS`/`MAX_CHIP_LEN`，但没有内容检查。#143 上线到 #147 上线之间写下的任何存档，里面的不安全 chip 会一直被还原成可点。只影响用户自己的存档，所以是 Low；但它和这段代码自己的注释（「同一条不变式两条路径只守一条正是本仓那类坑的形状,不留」）直接冲突。
  结构性障碍是真实的：`chipLooksUnsafe` 在 `apps/api`，`apps/web` 现在 import 不到（`packages/` 下只有 extract/geometry/quote）。**要么抽进 `packages/`，要么明确记一条 FU —— 但不该默默留着。**
- **[Info] 混淆写法与全角字符**：`w h a t s a p p`、`５００元`、`＄99`、`ＭＯＱ 500` 都放行。这一类需要模型主动规避运营方自己的过滤，威胁模型很弱，加 NFKC 归一化即可，不急。

### 另外两条（本 PR 之外，但同源）

- **[Med，pre-existing] `apps/api/src/chat.ts:189-193` — `reply` 有价格中和，却没有任何联系方式过滤。**
  `redactContact` 确实在用，但只用在**入站**（`:144` 客户回传的 history、`:153` 的 brief），**不在出站的 reply 上**。
  也就是说模型写进 `reply` 的一个 WhatsApp 号会**原样渲染给客户**，只是在下一轮从模型自己的记忆里被抹掉。
  这个 PR 用来论证 chips 需要过滤的 D-7 社工理由，对 400 token 的散文面比对 48 字符的按钮标签更成立，
  而所需的工具（`redactContact`）就在同一个函数里已经 import 好了。
- **[Low] CI 的缺口比一行大。** `apps/api/src/` 下有 8 个测试文件（auth / chat / cost / e2e / email /
  invites / render-store / routes-auth），根 `check` 只接了其中一个——正是这个 PR 新加的那个。
  `chat.test.ts` 覆盖的是**同一个模块**（`redactContact` + PR#130 的 sanitizePatch 修复），从来没在 CI 跑过。
  建议这个 PR 顺手把 `apps/api/src/*.test.ts` 整族接进 `check` 和 ci.yml，让 ci.yml:41-43 那句话重新成立。

### 一个值得单独想清楚的问题

过滤命中的是**词**，不是**值**：`Faster lead time`、`What is the MOQ?`、`2 weeks ok?` 会被拦（虽然它们没断言任何由报价引擎拥有的数字），而 `Tell me the price`、`多少钱`、`Cheaper option` 放行。

这个不一致 + 上面的中文缺口，会让「一整轮 chips 全被过滤 → `chips: []`」变成常态而不是罕见情况。而 `chips: []` 在前端有个已知副作用（见 #143 review 里那条 `addChips` 空数组提前返回、`liveChips` 不更新 → 下一轮网络抖动会复活两轮前的方向）。也就是说这个 PR 会**提高**那条 Low 的触发频率。

建议明确一下：chips 是**模型的断言**（那就拦词）还是**客户的话术**（那就只拦值）？前端 `chat.ts:164` 的语义是后者。

### 驳回的 findings

- **R1a「`500元` 是数量、被误伤」** —— `元` 是货币，`chat.ts:112` 把它和 `美元`/`人民币` 并列。拦截是正确行为。
- **R1a「`days?` 会误伤 `3D`」** —— 实测 `3D preview` 放行，而且作者自己在 `chips.test.ts:63` 就断言了这一条。
- **R1a「漏了中文语境的 wechat」** —— `/微信/` 在 `chat.ts:121`，`contact 微信 abc` 实测被拦。

### Assumptions

- 在独立 worktree（head `a37accc`）里跑测试与变异实验，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- PR body 未关联 issue，跳过 Issue-compliance 小节。
- **R3(Codex PK) 本轮未跑** —— 连续 9 分钟零输出后被我杀掉（本会话内第二次出现同样的挂起，
  `codex_pk.sh` 的 360s 上限也没生效）。所以本 review 是 **3 轮**，不是 4 轮，不冒充。
  上面每一条阻断项都有我自己实跑的机械证据（变异测试 / 绕过语料 / CI grep），不依赖 Codex 背书。

---
*Reviewed by clestons (`$pr` v4, **3-round — Codex R3 未跑**, head `a37accc`): DeepSeek R1a+R1b
(`deepseek-v4-flash`;5 条 findings,3 条被我实跑推翻,2 条并入联系方式整类) → Sonnet 机械验证
(独立 worktree 跑作者测试、对 `:205` 做变异测试证明测试不覆盖守卫、执行 13 条绕过语料、grep 证实
CI 未接该测试、实测 `redactContact` 复用只能关掉 9 条绕过里的 1 条) → Opus R2(独立评审,挖出 CI 缺口、
判定-vs-守卫的测试缺口、联系方式整类缺口、中英不对称、前端还原路径不设防) → **Codex R3 挂起未跑** →
Opus R4(终裁 + 全量补扫,发现 reply 出站零联系方式过滤、以及 api 下 8 个测试只接了 1 个)。*
