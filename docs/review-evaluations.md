# PR Daemon — Review Quality Evaluations

Ongoing log of per-round evaluation: DeepSeek R1 quality, model role effectiveness, token costs.
Each entry: date · round summary · DeepSeek scores · model assessment · improvement actions taken.

---

## 2026-06-11 · Rounds 1 & 2

### Stats
| Metric | Value |
|---|---|
| PRs reviewed | 15 (今日, 不含 dependabot) |
| DeepSeek tokens | 1,065,000 (in: 809k, out: 256k) |
| DeepSeek cost | ~¥6.37 CNY / $0.47 USD |
| Cost per PR | ~$0.031 |
| DeepSeek balance remaining | ¥93.56 CNY |
| Sonnet 5h used | ~4% |
| Opus weekly used | ~7% |
| Codex 5h remaining | ~91% ✓ (之前误读为耗尽，已纠正) |
| Codex weekly remaining | ~99% ✓ |

### DeepSeek R1 分项得分（DeepSeek 4.0 Pro / deepseek-chat）

| PR | Score | FP数 | Miss数 | 备注 |
|---|---|---|---|---|
| AirAccount#44 (WebAuthn) | 9/10 | 3 | 0 | 最好；验证了 SHA-256 hash |
| launch#8 (BuyHelper) | 8/10 | 3 | 0 | balanceOf sweep 正确 |
| AirAccount#47 (RPMB) | 8/10 | 5 | 0 | crash-brick fix 验证正确 |
| agent-speaker#4 (TUI) | 8/10 | 2 | 0 | senderSK 未清零正确 |
| AirAccount#46 (backup) | 7/10 | 0 | 0 | 继承判断正确 |
| AirAccount#43 (RPMB) | 6/10 | 4 | 0 | TOCTOU 正确；过多生命周期 FP |
| AAAN#69 (BLS) | 5/10 | 0 | 0 | double-close panic 正确 |
| CometENS#4 (API) | 5/10 | 2 | 1 | nonce 对，deadline>now 漏掉 |
| CometENS#6 (refactor) | 4/10 | 3 | 0 | pragma/reentrancy 误判 (不理解 CF Workers + payable 同步修改) |
| aastar-sdk#15 (crypto) | 4/10 | 1 | 1 | F1 EIP-712 严重误判；漏 F9 nonce 跨用户 burning |
| **CometENS#5 (contracts)** | **1/10** | **22** | **2** | **最差：22个 SPDX FP，文件里全有 header，完全未验证** |
| **平均** | **5.9/10** | **~3.9 FP/PR** | | |

### 典型失败模式

#### FP-1: 表面扫描，不验证 diff 内容
- CometENS#5: 22个 "SPDX missing" — diff 里有 11 对 header，DeepSeek 猜没有
- **根因**: FINDINGS 里没有要求引用证据行号，DeepSeek 可以无根据输出

#### FP-2: 不理解 runtime/framework 约束
- CF Workers bindings 在 deploy 时验证（误报启动检查）
- CF Workers isolate 模型（误报 singleton stale state）
- OP-TEE 单实例 TA 串行化（误报 TOCTOU）
- **根因**: Prompt 没有提供 framework 上下文

#### FP-3: 安全语义深度不够
- aastar-sdk#15 F1: 把正确的 EIP-712 `\x19\x01` raw concat 当 bug（代码注释里明确写了为什么不能用 encodeAbiParameters）
- **根因**: 没有要求 DeepSeek 先阅读注释/文档再判断

#### MISS-1: Nonce 作用域分析
- aastar-sdk#15 F9: `${chainId}:${nonce}` 缺 payer address → 跨用户 nonce burning
- **根因**: Prompt 没有要求对支付代码验证 nonce key namespace 完整性

### Model 角色效果

| 模型 | 角色 | 效果评分 | 关键贡献 |
|---|---|---|---|
| DeepSeek 4.0 Pro | R1 grunt work | 5.9/10 | 初步扫描；快速便宜 |
| Sonnet (本 session) | R2 challenge / 过滤 | 9/10 | 正确拒绝 EIP-712 误判、22个 SPDX FP |
| Codex (gpt-5.5) | R3 PK adversary | 9/10 | 发现 F9 nonce burning；challenge CF Workers FP |
| Opus | final verdict | 9/10 | 精准裁决，合理降级严重性 |

**最有价值的 R3 catch（Codex）**：
- aastar-sdk#15: F9 跨用户 nonce burning（`nonceKey` 缺 `from` 字段）
- AAAN#69: `close(done)` double-close race condition
- CometENS#4: multi-PoP KV check-then-put race

### 改进措施（已实施 2026-06-11）

- [x] **DeepSeek prompt 加 evidence 硬约束** — 每条 finding 必须引用 diff 行号，无法引用则不报
- [x] **DeepSeek prompt 加 framework guard** — CF Workers isolate / OP-TEE 串行化 / EIP-712 raw concat / SPDX 验证
- [x] **DeepSeek prompt 加 nonce scope check** — 支付代码 nonce key 必须包含 chainId + payer + nonce
- [x] **Token 统计改为 round 结束后输出整体统计**（不再每 PR 打印）
- [x] **DeepSeek model 确认** — `deepseek-chat` = DeepSeek 4.0 Pro（用户已确认）

---

## Template for future entries

### YYYY-MM-DD · Round N

**Stats**: PRs N · DeepSeek tokens Xk · cost $X · Codex 5h Y% remaining

**DeepSeek highlights**: best PR (N/10) · worst PR (N/10) · avg N/10 · FP/PR avg N

**Key Codex catches**: [list]

**Key Sonnet corrections**: [list]

**New improvement actions**: [list]
