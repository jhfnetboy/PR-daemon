## REQUEST_CHANGES — 增量复审 `40b6656` → `a1b1fb8`

这版方向完全对了，而且**这次是真的**：不再铺空模板冒充恢复，改成把工作集镜像进同一个 store、冷启动写回盘，恢复不出来就 409 交给用户决定。`WorksetState` 联合类型把五种情形显式区分开、`scaffoldWorkset` 用 `{ flag: "wx" }` 顺手关掉了上轮那个 TOCTOU、`/api/commit` 和项目详情 GET 都接进了同一个入口、README 也把持久化边界写清楚了。

我把 PR head clone 下来**跑了你的 `workset-e2e.mts`：17/17 全过** —— `SPEC.md` 恢复出来的是 `第 3 轮攒出来的内容` 而不是模板，402 条会话跨 5 个分块完整拼回，`无备份 + rounds>0` 确实 `lost` 且盘上一个文件都没写，`acceptLoss` 重建的模板带横幅。测试本身写得很好。

但有两条 High 我复现出来了，都是「保护算在了错误的时刻」。

---

### 🔴 Blocking 1 — `lost` 会改盘，且不幂等；第二次调用直接变 `present`，409 保护失效

`clients.ts` 的 `restoreWorkset()` 只要 store 里有**任意**一个会话分块，就会把 `conversation.jsonl` 写到盘上 —— 而这发生在 `r.docs > 0` 判定 `lost` **之前**。

我跑的是你自己场景 5 的**镜像方向**（文档备份丢、会话备份还在 —— 半失败的另一半），`rounds=9`，盘已清空：

```
PASS  第 1 次调用 -> lost（路由据此回 409）   {"kind":"lost","rounds":9}
      [!] lost 返回后盘上已有: ["conversation.jsonl"]
FAIL  ★ lost 时不应改动盘                     实际 1 个文件
FAIL  ★ 第 2 次调用仍应 lost                  {"kind":"present"}
      [!] 盘上文档数 = 0/7
```

顺着 UI 走一遍就是：用户看到 confirm 弹窗，点**取消**，然后再发一条消息 —— 这次 `exists(conversation.jsonl)` 命中，直接 `present`：

- 不再 409
- 不铺横幅、不写 `worksetLostAt`
- 因为 `ws.kind !== "reset"`，那条「无条件不 commit/push」的保护**也不生效**
- 而盘上 **0/7 个文档**，agent 在没有 SPEC 的情况下继续跑

这正好把这次改动要挡的那个结果又放回来了，只是晚一次请求。你 e2e 里 `lost 时不铺任何模板（盘上仍是空的）` 这条断言之所以过，是因为那个场景把**所有**备份都删了，`restoreWorkset` 什么都没写。

**修法**：先定状态、再写盘。把恢复出来的内容先落到 `dir.tmp/` 或内存，只有在判定为 `restored` 的分支里才 rename/写入；另外 `present` 的短路判据不该只看 `conversation.jsonl` 一个文件，否则函数对重复调用不幂等。

---

### 🔴 Blocking 2 — 「重建这轮不推」的保护只有一轮深，`worksetLostAt` 是死字段

```ts
if (ws.kind !== "reset" && process.env.AUTO_COMMIT === "true") { … commitProject(…, { push: AUTO_PUSH === "true" }) }
```

`ws.kind === "reset"` 只在**发生重建的那一个请求**里为真。**下一轮**就是 `present`，于是开了 `AUTO_COMMIT`/`AUTO_PUSH` 时，带丢失横幅的空模板会被 commit 并 push 上去覆盖仓库里已交付的 spec —— 正是这行注释声称要防的事。

而本该承担这个职责的 `worksetLostAt` 我 grep 过全仓库，**写了从来没人读**：

```
src/lib/types.ts:105:  worksetLostAt?: string;
src/lib/types.ts:106:  worksetLostAtRound?: number;
src/app/api/chat/route.ts:102:      ? { worksetLostAt: …, worksetLostAtRound: ws.rounds }
```

`/api/commit` 里也**没有任何** reset 门禁 —— 重建之后用户手动点提交，同样直接推空模板。

**修法**：门禁改成读持久化的 `worksetLostAt`，`/api/chat` 与 `/api/commit` 都遵守；只有工作集重新有了真内容、用户显式确认后才清除该字段。

---

### 🟡 其余确认项

| | 位置 | 问题 |
|---|---|---|
| M-H | `clients.ts` 会话镜像 | **没有 manifest，也从不删分块**，恢复把「第一个缺失的 key」当 EOF。① 中间少一块 → 历史被静默截断，却仍报 `restored`；② `reset` 后盘上会话为空、`backupConversation` 在 `chunks.length === 0` 处提前返回，下一轮只写 chunk 0，**上一世的 chunk 1..N 留在 store 里** → 之后某次冷启会把新 chunk 0 + 陈旧尾巴拼成一段伪造的会话。建议写一个 manifest（分块数 + 条目数 + generation id），恢复时校验连续性，`reset` 时 bump generation |
| M | `clients.ts` | **没有任何按项目的锁**。两个并发轮次都读整个文件、都写同一个末块索引，备份会永久少一条；`writeProjectState({...state, rounds: state.rounds + 1})` 用的是 `runTurn` 之前捕获的 `state`，是个 lost update |
| M | `appendConversation` | 镜像挂在主写路径上且无隔离：store 客户端非 2xx 就抛，而抛出发生在 `fs.appendFile` **已经落盘之后** → 500，用户重试就多一条**重复的 customer 消息**。store 抖一下整个 chat 就挂了。建议镜像做成 best-effort |
| M | 项目详情 GET | `.catch(() => ({kind:"present"}))` 吞掉**所有**异常，包括新加的 `throw new Error("项目不存在")`（不存在的项目返回 200）和 store 5xx。而这个页面恰恰是「你的工作集丢了」最该提示的地方 |
| M | `restoreWorkset` + `scaffoldWorkset` | 文档备份只恢复出一部分（`r.docs > 0` 但不足 7）时返回 `restored`，随后 `scaffoldWorkset` 把缺的补成空模板，**没有任何提示** —— `restored` 可能意味着「真内容和模板混在一起」 |

### ✅ Rejected

| finding | 驳回理由 |
|---|---|
| `restoreWorkset` 未 mkdir | `ensureProjectWorkset` 在唯一调用点之前已经 `mkdir(recursive)` |
| 「只重写末块导致前面的块陈旧」 | 按这个说法不成立：贪心切块让已满的块在追加场景下字节不变。真正的缺陷是 `reset` 之后的孤儿尾巴（已并入上面那条） |
| `MIRROR_WORKSET` 模块级读 env | 模块初始化时 env 已就位，且与既有的 `meta` 选择逻辑一致 |
| e2e 的 HTTP fixture 无鉴权 | 测试专用、绑 localhost，无生产面 |

### 🔍 一条关于测试本身的建议（R4 全量补扫）

你这 17 条断言**每一条都只做一次冷调用**，没有任何场景连续调两次 `ensureProjectWorkset` 并断言 `kind` 稳定 —— 而这正是能抓住 Blocking 1 的那个 harness。建议给每个场景补一条「再调一次，`kind` 必须相同、盘上文件集必须相同」，再加一个跨两轮的用例断言 reset **之后那一轮**也不 commit/push（那会抓住 Blocking 2）。测试结构本身很好，扩展就够了，不用重写。

---

<sub>🤖 增量复审 `40b6656..a1b1fb8`（8 文件 +439/-48）。4-round: R1a/R1b DeepSeek v4-flash 并行 → R2 Opus 独立评审（自跑 10 次实验）→ R3 Codex PK（真 Codex，6 条全 CONFIRM 并补 2 条）→ R4 Opus 裁决 + 全量补扫。工具实证：clone PR head 用 tsx 跑通作者 e2e **17/17**；自写对抗测试复现 Blocking 1（`lost` 后盘上残留 `conversation.jsonl` → 二次调用 `present`、0/7 文档）；grep 全仓库确认 `worksetLostAt` 零读者。</sub>
