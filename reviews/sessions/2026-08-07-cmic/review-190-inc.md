## ❌ REQUEST_CHANGES（增量复审 @ `19d0de7`）—— FU-18 的修复把同一个 bug 换了条路重新引入了

增量是两个提交（`23d1068` + `19d0de7`，+18/-2，`scripts/pii-guard-check.sh` + `docs/agent/followups.md`），做的是 FU-18，**和我上一轮那 5 条 blocking 无关，那 5 条一条都没动**，结论保持不变。

先说增量本身，因为它有一条新问题。

---

### 🔴 新增：启动时的「清残留」循环会删掉并发兄弟正在用的探针

```bash
for stale in apps/web/src/__pii_probe*.ts; do
  [ -e "$stale" ] || continue
  [ "$stale" = "$PROBE" ] && continue     # ← 只跳过自己
  git rm -qf --cached "$stale" >/dev/null 2>&1 || true
  rm -f "$stale"
done
```

PID 后缀解决的是**命名**冲突；这个新循环把**删除**冲突原样搬了回来 —— 而且比原来更响，因为它无条件跑在启动时，不再只跑在 cleanup 里。

**我真跑了并发，没有只读代码。** 把脚本里这个块**逐字 `sed` 抽出来**（不是我重打的）包成 harness，在一个独立 worktree 里起两个进程：

| 场景 | 结果 |
|---|---|
| **零错开**（两个同一瞬间起） | A ✅ B ✅ —— 两边的 sweep 都还没看到对方的文件 |
| **错开 0.3s** | **A ❌ 我的探针在使用中被别人删了** |
| **错开 1s** | **A ❌**，且 B 打印出 `⚠️ 清掉上次留下的探针残留：apps/web/src/__pii_probe.13931.ts` —— 它把 A 正在用的那个当成了「上次的残留」 |

所以 PR 里那句「**并发验证 A/B 双绿零残留**」我信它跑过，但它成立的**只有零错开那一种**，而那恰恰是最不现实的一种。FU-18 自己的描述是「两个 check/preflight 并发跑时」—— 两个 preflight 几乎不可能在同一毫秒启动。**只要有任何错开，原 bug 原样复现。**

顺带一条死代码：`[ "$stale" = "$PROBE" ] && continue` 这个自我保护在 sweep 时永远不成立 —— `$PROBE` 要到后面才被创建，此刻磁盘上根本没有它，glob 也就匹配不到。无害，但它给人一种「已经防了自己」的错觉。

**修法**（二选一，FU-18 原文其实已经写对了 —— 「或**加文件锁串行化**」那半没做）：
- 把 sweep 的判据从「不是我的就删」改成「**没有活着的属主**」：文件名里已经有 PID 了，`kill -0 $pid 2>/dev/null` 活着就跳过；
- 或者按 FU-18 写的加 `flock` 串行化，让两个 check 排队而不是抢文件。

⚠️ 这条值得单独说一句，因为它是**第二次**踩同一个形状：并发修复只把「协调用的那个文件」保护住了，没保护「要不要动它」这个**决策**。判据是「只要涉及并发就必须真起两个进程跑一遍」—— 顺序跑、或者同时起，都测不出来。

### FU-18 的账本标记

`docs/agent/followups.md` 把 FU-18 从 `- [ ]` 翻成 `- [x]` 并追加「✅ 2026-08-07 已做」。按上面的实测，**这条还没做完** —— 建议先翻回 `- [ ]`，或者把已做的部分（PID 后缀）和未做的部分（并发下的删除仲裁）拆成两条。这个账本是 pilot 交付闸读的（`followups.sh count-open`），标错会让闸提前放行。

（另外，这两个提交做的是 FU-18，和本 PR 的分享链接功能没有关系 —— 混在一个 PR 里会让「这个 PR 到底在等什么」变模糊。不阻塞，下次分开更好。）

---

### 上一轮那 5 条 blocking 一条都没动，逐条复核如下

| # | 位置 | 状态 |
|---|---|---|
| 1 | `share.ts:159-172` `assertNoCommercial` 传字符串是静默空操作 → 「服务端断言」没有实现 | ❌ 未动 |
| 2 | `schema.sql:495` 非幂等 ALTER（第二次部署 abort；`package.json:9` 的 `db:schema` 打的是生产 `cmic --remote`；全仓无任何地方跑 `migrations/*.sql`） | ❌ 未动 |
| 3 | `share.ts:81` `innerHTML = pageHtml`，公开匿名页 + 同源会话，无 CSP | ❌ 未动 |
| 4 | `sample.ts:139` 缺 `preserveDrawingBuffer` → 快照里的 3D 图是透明空白，且不抛异常 | ❌ 未动 |
| 5 | `sample.ts:519` 512KB 上限在正常页面就触发 → 功能静默哑火 | ❌ 未动 |

细节见上一条 review。

<sub>Rounds（增量轮）— R1a/R1b DeepSeek(v4-flash)：**R1a 独立命中了这条**（「stale cleanup deletes files matching `__pii_probe*.ts` including active probes from other concurrent runs」），是它今晚第二次在真实代码 diff 上给出站得住的 finding。R2/R3/R4 未跑 —— 增量只有 18 行、单一关注点，且结论由实跑的并发测试直接判定，不是靠推理。上一轮的 5 条 blocking 保持原判。</sub>
