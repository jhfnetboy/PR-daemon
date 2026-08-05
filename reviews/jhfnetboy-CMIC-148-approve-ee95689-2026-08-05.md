## Verdict: APPROVE（增量复审，head `ee956890`，round 2）—— **首轮那条 High 修得比我建议的更彻底，而且是结构性的**

**核心修复：`directionConfirmed` 不再由 `low.includes` 置位，改由 `render-gate.ts` 导出的 `statedDirection()` 判定。**

```js
- if (!brief.boxType) for (const k in BOX_HINT) if (low.includes(k)) { brief.boxType = BOX_HINT[k]; directionConfirmed = true; break; }
+ if (!brief.boxType) for (const k in BOX_HINT) if (low.includes(k)) { brief.boxType = BOX_HINT[k]; break; }
+ if (statedDirection(t)) directionConfirmed = true;
```

这正是我建议的切分——**`BOX_HINT` 继续填卡片（便宜、可逆），但不再授权花钱**——而且方向确认现在走的是闸自己那套 `clauses` / `NEGATORS` / `isQuestion`。实测：

| | 结果 |
|---|---|
| 首轮那 16 条意外置位的（`solid`/`holiday`/`valid`/`shipping`/`relationship`/`booklet`/`facebook`/`notebook`/`booking`/`slides`/`rigid?`…） | ✅ **16/16 全部不再置位** |
| 真的在说盒型的必须仍认出 | ✅ **10/10**，含 `magnetic closure box for perfume` —— 我实测过全词匹配 `\bmagnet\b` 会打断这个真客户说法，这个改法没有 |
| 否定句不得算确认 | ✅ **6/6**：`no lid needed` / `I do NOT want a book box` / `not a drawer box` /「别用抽屉盒」/「不要磁扣盒」/「以后再说盒型」 |

端到端，我首轮举的三句现在全部拒绝，而正当的那句照常放行：
```
"solid black box for a candle, 500 pcs"            dir=null   → allow=false (slots-incomplete)
"what is the shipping cost for 500 candle boxes?"  dir=null   → allow=false (slots-incomplete)
"I do NOT want a book box, 500 candles"            dir=null   → allow=false (slots-incomplete)
"magnetic closure box for perfume, 500 pcs"        dir=magnet → allow=true  (slots-complete)
```

**而且判定搬进了被测模块。** 我把首轮那批变异重跑——`statedDirection` 恒返回一个盒型 / 去掉否定词处理 / 改回子串匹配——**三个全部被杀**（首轮同类变异是 7/7 存活）。`render-gate.test.ts` 给它加了 6 条用例。

**其余每一条也都改了：**

| 首轮的问题 | 现在 |
|---|---|
| `pnpm test:gate` 不在 `ci.yml` | ✅ 加了，而且我实测 **`check` 13 条现在 13/13 全在 ci.yml**，零遗漏。注释里还写清了「7 个接线变异全部存活、实际变异得分 0/7」的原委 |
| `reuseExistingServer: true` 让 5174 的 `VITE_API_URL` 保证失效 | ✅ 5174 改成 `false`（`--strictPort` 已在，端口被占会直接报错）；5173 保持 `true` 不受影响 |
| `modelDone === false` 太窄，`null`/`0`/`""` 漏过 | ✅ 改成 `modelDone !== true`，并新加 `'model-not-ready'` reason（原来会谎报成 `'slots-incomplete'`） |
| `enterThread` 尾段无 `try/finally` | ✅ `:520` 加上了 |
| `qty >= 10` 硬编码三处 | ✅ 抽成 `MIN_STATED_QTY`，三处共用 |
| `e2e:57` 的 `.thumb.loading` 在 503 stub 下是空断言 | ✅ 改成断言 `.thumb.failed` 计数为 0 —— 这条才有判别力 |

`pnpm test:gate` 在新 head 上通过。

### 非阻塞（都不急，留给后续）

- **[Low] `render-gate.ts:252`/`:318` 的 `raw.slice(-2000)`** —— R1a 提的，方向对但代价方向是安全的：截断只会**少认出**方向（漏判 = 便宜那侧），而且客户首句超过 2000 字符本身罕见。留着即可，值得在注释里写一句为什么取尾不取头。
- **[Low] `directionConfirmed` 仍不重置**（R1a 也提了）—— 在当前控制流下不影响闸：`photorealVerdict` 只有 `:642` 一个调用点，来自 `enterThread`，而 `:601` 的 `started` 守卫（以及 `:862` 的 `restoreThread`）让它每页只跑一次。如果将来 `showBoxDirections` 多一个调用点，这条就会立刻变成真问题——建议在 `directionConfirmed` 的声明处写一句「本标志位的正确性依赖 `photorealVerdict` 只在首轮调用」。
- **[Low] 仍然成立的范围事实**（不是缺陷，是值得写进文档的）：闸覆盖 3 个付费调用点里的 1 个——`showBoxDirections` 被管住了，`Vary` 和 `Sample` 两条路仍然无闸。按「明确指令压过一切禁止条件」这站得住（点击就是明确指令），但省下的量应该按这个口径说。
- **[Low] `e2e/08` 仍不在 CI**（FU-6）—— 但首轮我最担心的那件事（接线层零自动覆盖）已经解决了：判定搬进 `render-gate.ts` 并进了 CI，变异也证明钉住了。FU-6 现在是「多一层端到端保险」，不再是「唯一防线只在本地」。

### 驳回

- **R1a「`statedDirection(t)` 每轮都调用但 `directionConfirmed` 从不重置」** —— 方向值得记，但在当前控制流下不可达（见上），降级为 Low。
- **R1b「gate tightening，无直接 auth/crypto/payment 缺陷」** —— 同意，本轮无安全面。

### 一条方法上的肯定

首轮我说的是「rigor 放在了自己边界的错误一侧：一个被反复评审的纯函数守着钱，而它权限最高的输入来自另一个文件里一句没人审过的 `String.includes`」。这轮的改法不是去调那个 `includes` 的正则（我实测过三种调法都不行——前缀边界仍漏 `booklet`/`ship`，全词匹配会打断 `magnetic closure`），而是**把判定整个搬到边界的正确一侧**：搬进 `render-gate.ts`、复用它已有的否定/分句/疑问处理、加进 CI、用变异证明钉住。这是关掉一类而不是关掉一个实例。

### Assumptions

- 在独立 worktree（head `ee956890`）里跑测试、变异与探针，未改动 `~/Dev/jhfnetboy/CMIC` 任何文件；变异已还原。
- **没有跑 Playwright** —— 5173 上仍有来路不明的服务器（首轮我查出是另一个 checkout）。e2e 的改动是**静态**核对的：我确认 `.thumb.failed` 断言已加、5174 的 `reuseExistingServer` 已改 `false`。`reuseExistingServer: true` 在 5173 上保留是既有状态，不属本轮范围。
- `ci.yml` 用 `yaml.safe_load` 实际解析，并与 `package.json` 的 `check` 串逐条比对（13/13）。
- **R3(Codex PK) 未跑、R4 未跑** —— 本轮是 APPROVE，每条结论都有我自己实跑的输出（16/16 + 10/10 + 6/6 探针、端到端闸判定、三个变异全杀、CI 覆盖逐条比对）。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，increment `5d37c2c8`→`ee956890`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；2 条，均在当前控制流下不可达/代价方向安全，降级为 Low）→ Sonnet 机械验证
（首轮 16 条误置位语料 + 10 条真盒型 + 6 条否定句三向对跑、端到端闸判定、`statedDirection` 三个变异
全部被杀、`yaml.safe_load` 比对 check 13/13 全进 CI、逐条核对 reuseExistingServer/try-finally/
modelDone/MIN_STATED_QTY/thumb.failed）→ **Opus R2 未跑（本轮无待判定的争议项，首轮那条 High 的
修复我自己就能证）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 这是它这几轮里最好的一次：两条 findings **都指对了真实的代码事实**（`directionConfirmed` 确实从不重置、`slice(-2000)` 确实会截断），只是都没往下追一步看它们在当前控制流下是否可达、代价方向是否安全。没有编造，没有一眼可证伪的断言——比前几轮「`个` 不在前瞻里」「`s[i]!` 会崩」那种实质进步。
- **下次怎么榨出更多信号**：它缺的一直是**可达性判断**。下次在 prompt 里加一条硬要求：「对每一条 finding，说明触发它需要的调用路径，并指出该路径在本 diff 里是否真的存在」。这一轮它的两条如果各自加上这一句，会自己降级成 Low —— 那正是我最终给的结论。
