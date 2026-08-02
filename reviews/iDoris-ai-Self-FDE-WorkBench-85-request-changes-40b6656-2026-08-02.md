## REQUEST_CHANGES — 增量复审 `d875f11` → `40b6656`

先说清楚：**上一轮那个 blocking 的直接症状确实修好了**。`/api/chat` 现在在 `readProjectState()` 之后、任何 fs 写之前调 `ensureProjectWorkset()`，`appendConversation()` 自己也补了 `fs.mkdir(dir, { recursive: true })` —— 冷启动 ENOENT 500 这条路走不通了。`appendConversation` 里那个防御性 mkdir 是这个 diff 里最扎实的一处，建议保留。

但水合的**方式**引入了一个比原问题更糟的失败模式，所以还得再挡一轮。

---

### 🔴 Blocking — 水合出的空壳与「全新项目」在字节层面无法区分

`ensureProjectWorkset()` 用 `docScaffold()` 重建 7 个文档，每个的正文都是 `_（尚未开始，等待输入）_`。它**不恢复任何内容**——文档本来就不在 D1 里（`createProject` 的注释写明「文档是每会话工作集…仍落文件系统」）。

于是冷启动后的实际时序是：

1. 容器重启，盘丢了，D1 里 `state.rounds = N`（N 轮已交付的成果）
2. 用户发一条消息 → `ensureProjectWorkset()` 静默重建 7 个空模板 + 空 `conversation.jsonl`
3. `runTurn()` 在**零上文**下跑，agent 看到的是一个刚开始的项目
4. `writeProjectState({ ...state, rounds: state.rounds + 1 })` —— 轮次继续往上加，加在一段已经被抹掉的历史上
5. 用户没有收到任何异常信号

**那个 500 是用户唯一的探测器。** 把一次响亮的失败换成一块看起来完全合理的白板，在失败场景下是严格更差的。

> 关于 auto-commit/push 那条限界，我核实过：`fde-copilot/.env.example:25` `AUTO_COMMIT=false`、`:28` `AUTO_PUSH=false`，README 的默认值表也是 false。所以「把空模板 commit/push 覆盖掉仓库里已交付的 SPEC」需要显式开开关，**默认是关的**，而且可 git revert。PK 轮挑战这一点是对的，我把这条限界从结论里降下来了。但上面 1-5 这条链**完全不依赖任何 env 开关**，它自己就是 blocking。

**修法**：把「分歧」检测出来，而不是抹平它。

- 若 `state.rounds > 0`（或 D1 里存在任何历史）而 `conversation.jsonl` 不存在 → 判定为 degraded，`/api/chat` 返回一个明确的错误/警告，scaffold 文档顶部打上「工作集已随容器重启丢失，内容未恢复」的横幅
- 该请求无条件拒绝 auto-commit/auto-push，不看 env
- 只有 D1 也说这个项目没有历史时，才允许静默铺空模板

架构上更彻底的做法：git remote 本来就是既有的持久出口（`commitProject` + push 已经在了），冷启动时从它恢复工作集，比重新铺空模板更接近「水合」的本意。

---

### 🟡 Confirmed — `/api/commit` 有同一个洞，本次没修

增量只碰了 `chat/route.ts` 和 `clients.ts`。`/api/commit` 仍是：

```ts
const state = await readProjectState(clientSlug, projectSlug);   // D1 命中
if (!state) return NextResponse.json({ error: "项目不存在" }, { status: 404 });
const r = await commitProject(clientSlug, projectSlug, ...);      // 目录不在 → throw → 500
```

R2 独立提出、PK 轮也 CONFIRM 了这条。建议把「水合 + degraded 判定」抽成一个共享 helper，所有**从 D1 state 走到磁盘**的路由都调它（`chat`、`commit`，以及以后新增的），而不是一条路由一条路由地打补丁。

（顺带：`/api/commit` 这里**不**做水合其实是有道理的——对一个空壳工作集执行 commit+push 反而会把空模板推上去。所以正确做法是 degraded 判定 + 明确报错，不是无脑加 `ensureProjectWorkset`。）

---

### ✅ Rejected（本轮驳回的 findings）

| finding | 驳回理由 |
|---|---|
| R1a: `ensureProjectWorkset` 吞掉 `projectDir` 异常，应该 404 | 不可达。`readProjectState()` 已经跑过 `assertSafe`，非法 slug 会 return null 提前退出；且两行之后 `appendConversation` 照样无保护地调 `projectDir()`，真有问题也会在那里抛。是死代码，不是漏洞——建议直接删掉这个 try/catch，别让它暗示一条其实没被守住的路径 |
| R1a: `client?.name ?? clientSlug` 兜底没做 null 检查 | 只填进一个模板 header 字符串，而这个模板本身就是空的，无行为后果 |
| R1b: `ensureProjectWorkset` 写文件前没做权限检查 | 路由在调用它之前已经过了 `originError` + `scopedAuthError`；这个 helper 不是入口点 |
| PK: F-1 整条挑战 | 只对了一半（见上文 auto-commit 那段）。失忆 + rounds 继续自增那条腿不依赖 env，仍然成立 |

### 建议

- 把「新建项目铺模板」和「已知项目盘没了」拆成两个函数——现在一个函数同时干这两件事，正是静默失败的来源。第二个函数不该有能力伪造内容。
- 在 `ensureProjectWorkset` 和 README 里写清楚：文档/会话**不在 D1**，容器重启会丢。下一个读代码的人很容易默认 D1 是整个工作集的 source of truth。
- 低优先级：`exists()` → `writeFile()` 之间有 TOCTOU 窗口，`{ flag: "wx" }` + 吞掉 EEXIST 可以零成本关掉。PK 轮说「没有并发证据」，我接受这是个降低严重度的理由，但不接受它是不值得修的理由。

---

<sub>🤖 增量复审（`d875f11..40b6656`，2 文件 +35/-3）。4-round: R1a/R1b DeepSeek v4-flash 并行 → R2 Opus 独立评审 → R3 PK → R4 Opus 裁决。R3 说明：`codex exec` 两次都在 39 字节处停住，被 `codex_pk.sh` 的停滞检测自动 kill 后降级到 DeepSeek 兜底，故 PK 轮质量按弱挑战者计。工具实证：grep 仓库 head 确认 `AUTO_COMMIT`/`AUTO_PUSH` 默认值均为 false，据此下调了 blocking 中 commit/push 那条限界的严重度。</sub>
