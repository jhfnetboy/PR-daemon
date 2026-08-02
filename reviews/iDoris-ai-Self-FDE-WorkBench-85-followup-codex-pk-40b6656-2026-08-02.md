## 补充：PK 轮已用真 Codex 重跑（上一条 review 里那轮是降级的）

上一条 review 我标注了「`codex exec` 两次停在 39 字节被自动 kill，PK 降级到 DeepSeek 兜底，按弱挑战者计」。那个工具故障刚定位并修好了（根因是 `codex exec` 在等一个永远不来的 stdin EOF，不是模型/配额问题），所以我用**完全相同的 prompt** 把 PK 轮重跑了一遍。**结论不变，仍是 REQUEST_CHANGES**，但有两处要更新：

### 1. DeepSeek 兜底的挑战基本是错的，真 Codex 全部 CONFIRM

| finding | DeepSeek 兜底 | 真 Codex |
|---|---|---|
| F-1 空壳水合（blocking） | CHALLENGE | **CONFIRM** |
| F-2 `/api/commit` 同洞未修 | CONFIRM | **CONFIRM** |
| F-3 `projectDir` try/catch 是死代码 | CHALLENGE | **CONFIRM** |
| F-4 `exists()`→`writeFile` TOCTOU | CHALLENGE | **CONFIRM** |
| F-5 重复 `readProjectState` | CHALLENGE | **CONFIRM** |

也就是说上一条 review 里被我按 DeepSeek 意见降级/淡化的几条（F-3/F-4/F-5），实际都是站得住的。F-3 建议直接删掉那个 try/catch，F-4 用 `{ flag: "wx" }` + 吞 EEXIST。

> 一处保持不变：`AUTO_COMMIT=false` / `AUTO_PUSH=false` 默认关是我 grep 仓库实证的，那条限界仍然成立，跟这次重跑无关。

### 2. 新增一条所有轮次都漏掉的 finding

**M-1 [Medium] `/api/chat`：客户消息在 `runTurn()` 之前就写进了 `conversation.jsonl`**

```ts
await appendConversation(clientSlug, projectSlug, { role: "customer", ... });   // ← 先落盘
let out;
try {
  out = await runTurn({ ... });
} catch (e) {
  return NextResponse.json({ error: `agent 执行失败：${...}` }, { status: 500 });  // ← 直接返回
}
```

`runTurn()` 抛错时直接 return，**已经落盘的那条 customer 消息不会回滚**，而 `writeProjectState`（`rounds + 1`）在下面根本没执行。结果是 `conversation.jsonl` 里留下一条没有对应 copilot 回复的孤儿轮次，而 D1 里的 `rounds` 没动 —— 两边对不上，且每失败一次就多一条。

这跟本 PR 的 blocking 是同一类问题（D1 与文件系统各写各的、没有一致性边界），建议一起处理：要么 customer 消息也推迟到 `runTurn` 成功之后再写，要么在 catch 里补一条 `role: "error"` 记录把这一轮显式封口。

---

<sub>🤖 PK 轮重跑说明：`codex exec` 之前会打印 `Reading additional input from stdin...` 然后无限等待——非 TTY 的 stdin 让它尝试把管道输入拼进 prompt，而后台调用下永远等不到 EOF。加上 `< /dev/null` 后，同一个 8KB prompt 19 秒返回完整结果。与模型、配额、鉴权、prompt 大小都无关。</sub>
