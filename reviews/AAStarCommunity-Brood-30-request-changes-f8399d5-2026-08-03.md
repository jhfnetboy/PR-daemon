## Brood#30 — REQUEST_CHANGES

**4-round pipeline**(增量复审)· 纯 docs(backlog)PR:修复 commit `f8399d5` 补立 TASK-46/47/48 + 更新 doc-8 + 改 task-43 AC,回应上一轮 REQUEST_CHANGES。`backlog/tasks/*.md` 被 `scripts/export-backlog.js` 构建解析(automation-consumed),已在 PR head 实跑完整构建验证。

### 结论:修复 commit 自身复发了上一轮的 over-claim 类问题(F1)

上一轮 blocking 是「doc-8 声称所有可执行项已 task-ify,但 3 项无 task 文件」。本轮补立 TASK-46/47/48 **已正确解决该缺口**(见下),但在同一段新增说明里又写了一个与文件实际不符的 blanket 声明——**同类 defect 复发**:

| 文件 | 声称 | 实际 |
|---|---|---|
| `doc-8:10` | "各 task 描述首行标注「目标仓库」" | task-39..45 共 7 个文件描述首行**均无**目标标记(仅新增的 task-46/47/48 有) |
| `doc-8:10` | "多数非 Brood 本体" | task-39(修 Brood 旗舰 skill)、task-47/48(明确 `目标:Brood`)实际就是 Brood 自身 |

→ fix:给 task-39..45 描述首行补「目标仓库」标记(对齐声明),**或**改写 doc-8 该句如实描述(仅新增 task 带标记)。

### 第二处同类缺口(本轮新增文件仍未堵住)

`doc-8:20` item 2 给 `codex exec` stdin-EOF 挂死写明了可执行修法("命令补 `< /dev/null`"),但:
- TASK-39..48 **没有任何一个覆盖 codex/stdin 修复**;
- 该修复其实**已落地**在 `scripts/codex_pk.sh:56`(`< /dev/null` is THE fix),却**没列入 doc-8「已完成(本轮)」**。

于是 digest 开头"已把可执行项立成 TASK-39 ~ TASK-48"仍过度声明。→ fix:把该修复补进「已完成」段(标注 codex_pk.sh:56),或为它立 task。

### Confirmed(低危,建议一并修)

- **task-46:18** 自称 "digest item 5",但 SQLite 单写锁是 doc-8 的 **item 4**(item 5 = scan_error)→ 改回 item 4。
- **task-46:18 "56 次" vs doc-8:22 "213 次"** database-is-locked——同一事件两个数字,同 PR 双文件自相矛盾 → 对齐为 log 实测数。

### 自动化兼容性(机械证据,✅ 通过)

- PR head worktree 实跑 `node scripts/export-backlog.js`:**0 错误**,TASK-46/47/48 全部进入 `dist/api/tasks.json`,共 47 个 task,ID 无重复;doc-8 正常保存。
- 8 个文件 frontmatter 合法;TASK-46/47/48 与现有 ID 无冲突。
- task-43 AC 已指名模板位置(`.claude/skills/pilot/templates/`,作为新建目标)——上一轮 suggestion #3 已解决。

### Suggestions(非 blocking)

1. **R1a 表现**:本轮 5 条 finding 中 4 条是来源计数/link 类噪音(被 Opus R2 + Codex 一致 REJECT),但第 5 条抓到了真实的两文件数字矛盾(213-vs-56)——**值得保留**。噪音点:强求"文档引用必须有链接/测试证据"对纯 .md 聚合文档不适用,建议 R1 prompt 加一条"docs 聚合类 PR 不适用链接/测试类 finding"。
2. doc-8 与 task 文件缺单一事实源(计数、item 编号两处不一致均源于双文件独立撰写未对账)——建议把一致性检查写成可 grep 断言,恰是本 PR 自己提的 TASK-47 的活例。

---

**Rounds:** R1a(DeepSeek-full): 5 findings(4 噪音被拒 / 1 真实)· R1b(DeepSeek-sec): 0(正确,纯 .md)· R2(Opus-strategic): 独立 F1 [Med] 目标标记 over-claim + F2 [Low] item 编号错位 + 确认计数矛盾 · R3(Codex PK gpt-5.5): CONFIRM F1/F2/F3,0 CHALLENGE · R4(Opus final): REQUEST_CHANGES
