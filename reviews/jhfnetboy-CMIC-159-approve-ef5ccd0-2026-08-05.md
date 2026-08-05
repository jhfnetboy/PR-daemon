## Verdict: APPROVE（首轮，head `ef5ccd0d`）—— **修得对，但有一条实质建议：别用 ADMIN_TOKEN**

`--api` 打生产每轮都 401、5/5「没连上」——这是真的堵住了 live 基线，补鉴权是对的。

### 我核实的部分

| 检查 | 结果 |
|---|---|
| token 会不会被打印/落日志 | ✅ 只打印「(带 Bearer 鉴权)」或「没给 token」的提示，**从不打印 token 本身**；错误分支也只打 `⚠️ /chat ${r.status}` |
| CLI 与环境变量的优先级 | ✅ `out.token ??= process.env.CMIC_EVAL_TOKEN` —— `??=` 只在未赋值时生效，所以 **CLI 优先于环境变量**，符合直觉 |
| 空值处理 | ✅ `--token` 不带值时 `if (!val) throw` 报错；`CMIC_EVAL_TOKEN=''` 经 `\|\| undefined` 归一成未设置 |
| 未知 flag 守卫仍生效 | ✅ `--token` 加进了 `KNOWN_FLAGS`，那条「未知 `--*` 直接报错」的守卫没被绕开 |
| 「不带 token 一律 401」这个前提 | ✅ `index.ts:570-571` 明写「其余：需鉴权」→ `authenticate(req, env)`，`/chat` 在它之后 |

而且注释里那句自省很到位：

> 好在这个工具把「没连上」当基础设施故障而不是 PASS（评审 High-1 修过），所以它不会静默给出一份漂亮报告 —— **但基线也就永远拿不到**。

**准确区分了「没有静默骗人」和「拿到了数据」是两件事。**

### 🔻 建议（不挡合并，但值得在合并前定下来）：**明确写清该用哪种 token，而且答案不是 ADMIN_TOKEN**

我查了 `POST /chat` 这个 case 分支：**`can()` 出现 0 次**——它只要求**已鉴权**，不要求任何特定权限。而 `authenticate` 认三种 Bearer：

```
ADMIN_TOKEN         → role=admin，全部权限（cost.read / inquiry.pii / user.manage …）
PUBLIC_RENDER_TOKEN → viewer, perms=['render.create']    ← 注释自述「泄漏也读不到数据(D-7 不破)」
LEDGER_INGEST_TOKEN → viewer, perms=['cost.write']
```

**三种都能过 `/chat`。** 但现在的文档只说「`--token <bearer>`」，没说哪一种——而**看起来最像答案的那个（`ADMIN_TOKEN`）恰恰是最不该用的**：它是 ops 级全权凭证，而这个 token 要贴进 shell history 或 CI secret，还要在评测机器上长期存在。

建议把用法那几行改成明确指名，例如：
```
--token <bearer>   用 PUBLIC_RENDER_TOKEN（或另发一个专用的评测 token）。
                   ⚠️ 不要用 ADMIN_TOKEN —— /chat 不需要任何特定权限，
                      给它 admin 是把一个 ops 级凭证放进 shell history / CI secret。
```
更彻底一点是在 `authenticate` 里加一个 `EVAL_TOKEN` → `viewer, perms=[]`，但那是另一个 PR；先把文档指名就能挡掉最坏的用法。

### 其余非阻塞

- **[Low] 没给 token 时的提示可以更进一步。** 现在是「⚠️ 没给 token —— 线上 /chat 会 401，只有本地 dev 才可能匿名通过」，说得准；但既然结果注定是 5/5「没连上」，可以在**跑之前**就 fail fast（`--api` 指向非 localhost 且无 token → 直接报错退出），省掉五次必然失败的往返。现在的行为不错误，只是浪费一轮等待。
- **[Low] `LIVE_OPENERS` 里仍然没有一句会让模型报价**（`'Hi'` / 「我要设计一个手表的包装盒」/ `'A gift box for a 40mm mechanical watch, 800 units'` / 「不知道，你推荐吧」/「我们是迪拜一个做定制香皂的品牌」）。这条我在 #156 里报过：鉴权补上之后 live 能跑通了，但 **A4 的价格臂仍然不会被触发**，`#156` 新教给 A4 的哨兵识别在 `--api` 下执行 **0 次**。加一句问价的开场白（`「500 个多少钱一个?」` / `'How much per box for 500?'`）才算把回路闭上。**这个 PR 打通了「连得上」，闭环还差「有东西可量」。**

### 驳回

- **R1a「应考虑 CLI token 是否该优先于环境变量，或两者都设时是否该告警」** —— 前半句已经是现状（`??=` 让 CLI 优先），后半句「两者都设时告警」我不建议加：CLI 覆盖环境变量是每个工具的通用约定，为它加一条告警会让「临时用别的 token 跑一次」这个正常用法每次都刷一行噪音。

### Assumptions

- 在两个独立 worktree（`origin/preview` 与 `ef5ccd0d`）里读代码，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件。
- **权限结论是查 `route()` 里 `case 'POST /chat'` 整个分支得出的**（`can()` 计数为 0），并对照 `authenticate` 里三种 Bearer 的实际返回值，不是照文档推的。
- **我没有真跑 `--api`** —— 那会打生产、消耗真实 token 与模型调用，超出评审该做的事。
- **R2/R3/R4 未跑** —— 单文件、职责单一，唯一需要判断的（该用哪种 token）我用代码追证定论了。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `ef5ccd0d`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；R1b 定级 low 准确，R1a 的优先级问题已是现状）→ Sonnet 机械验证
（token 打印路径全查、`??=` 优先级与空值归一、`KNOWN_FLAGS` 守卫、`case 'POST /chat'` 的 `can()`
计数为 0、`authenticate` 三种 Bearer 的权限对照）→ **Opus R2 未跑（职责单一）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** R1b 的 triage（`low — token handling adds auth surface but no direct vuln`）定级准确。R1a 唯一那条建议问的是**对的维度**（凭据优先级），只是没去看 `??=` 已经定了优先级。对一个 21 行的 diff，没有编造、没有跑偏。
- **下次怎么榨出更多信号**：这类「给某个调用补凭据」的 diff，最有价值的问题是**该用哪一级凭据**。下次在 prompt 里写死：「找出被调用的那个端点要求的最低权限，列出系统里所有能满足它的凭据，并指出文档推荐的那个是不是其中权限最小的」。这次真正的建议（别用 ADMIN_TOKEN）就是这么得出来的，而它需要跨两个文件对照——正是 flash 目前不会自己去做的那一步。
