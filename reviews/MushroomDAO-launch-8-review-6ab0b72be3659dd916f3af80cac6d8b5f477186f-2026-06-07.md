## Review: MushroomDAO/launch#8 — feat(gasless): EOA-enhance gasless purchase spec (EIP-7702 + EIP-712)

**Date:** 2026-06-07
**Reviewer:** Claude Code (DeepSeek) + Codex PK Challenge
**Verdict: REQUEST_CHANGES**
**Score: 85/100**

### Score Breakdown

| Dimension | Score | Note |
|-----------|-------|------|
| Finding quality | 18/20 | Real design bugs caught, not style nits |
| PK resilience | 18/20 | 4/6 confirmed; 2 LOW challenged with valid reasoning |
| Coverage | 19/20 | Contract, relayer, spec, whitelist all covered; no MISSED from PK |
| Actionability | 15/20 | Fixes clear but HIGH finding may require design discussion |
| False-positive rate | 15/20 | 2 LOW findings challenged; reviewer slightly overcautious |
| **Total** | **85/100** | Strong review; challenged items were minor |

---

### Findings

**[Confirmed] HIGH — `extractTokenBuyIntent` 硬编码支付 token，与白名单规则体系断裂**
`services/relayer/src/v2/handler.ts:105-109`

```typescript
const extraction = extractTokenBuyIntent(
    body.calls,
    [SEPOLIA.USDC], // ← 硬编码
)
```

白名单 `whitelist.ts` 每个 rule 自带 `paymentTokens` 数组，spec §4 也承诺 USDT 扩展。但此处硬编码 USDC — 将来加 USDT rule 会被 extract 层拒绝，永远到不了 whitelist 匹配。

**修复方向**：从所有 enabled rules 收集 payment token 并集传入，或将 extract 逻辑移到 whitelist match 之后使用匹配 rule 的 paymentTokens。

---

**[Confirmed] MEDIUM — `onChainNonce` 读取与提交之间的 TOCTOU 竞争**
`services/relayer/src/v2/handler.ts:120-145`

并发场景：两个请求同时读到 nonce=3，都构造 nonce=3 的签名。第一个执行成功 nonce→4，第二个签名因 nonce 不匹配被链上拒绝。Relayer 白付第二笔 gas。

PK 确认 AirAccountDelegate 的 replay test (`contracts/test/AirAccountDelegate.t.sol`) 验证了签名随 nonce 推进而失效的正确行为。

**修复方向**：提交后检查 tx receipt revert 原因，若是 `InvalidSigner` 记录为 benign race 不报警；或 per-buyer 请求串行化。

---

**[Confirmed] MEDIUM — EIP-712 签名 spec 与实现严重不一致**
`docs/gasless-eoa-enhance/00-spec.md` vs 实际代码

| 项目 | Spec (§5) | 代码实现 |
|------|-----------|---------|
| Domain name | `"Mycelium Gasless Buy"` | `"AirAccountDelegate"` |
| PrimaryType | `PurchaseIntent` | `ExecuteBatch` |
| verifyingContract | `AIRACCOUNT_DELEGATE` 合约 | `body.buyer` (EOA 自己) |

Spec 在 §1 声明自己是 "源真相"，但代码走了完全不同的签名结构。前端如果对着 spec 写，签名验不过。

**修复方向**：推荐更新 spec 匹配代码实现（ExecuteBatch 结构更简洁且与链上 AirAccountDelegate 一致）。

---

**[Confirmed] LOW — 未交叉验证 EIP-712 签名者与 EIP-7702 授权签名者**
`services/relayer/src/v2/handler.ts:90-145`

EIP-712 验签确认 `recovered == buyer`，但 EIP-7702 authorization 只检查 `address` 和 `chainId`，未恢复签名者交叉验证。攻击者不能偷钱（链上最终拒绝），但 relayer 浪费 gas。

**修复方向**：off-chain 用 viem `verifyAuthorization` 恢复签名者确认 `== buyer`。

---

### PK Summary

| # | Finding | PK Result | Disposition |
|---|---------|-----------|-------------|
| 1 | Hardcoded paymentTokens | **CONFIRMED** | Accepted |
| 2 | No gas limit on Type-4 tx | **CHALLENGED** | Rejected — not established from this diff |
| 3 | TOCTOU onChainNonce | **CONFIRMED** | Accepted |
| 4 | Spec/code EIP-712 mismatch | **CONFIRMED** | Accepted |
| 5 | Broad error catching | **CHALLENGED** | Rejected — no code path proves masking |
| 6 | No cross-validation signers | **CONFIRMED** | Accepted |

**PK stats**: 6 submitted → 4 CONFIRMED (67%) · 2 CHALLENGED (33%) · 0 MISSED

### Verification

```bash
# Reviewed diff
gh pr diff 8 --repo MushroomDAO/launch  # 2,369 lines, 13 files

# Files reviewed
contracts/src/AirAccountDelegate.sol     # EIP-7702 delegation target
services/relayer/src/v2/handler.ts       # /v2/relay + /v2/revoke handlers
services/relayer/src/pipeline/extractIntent.ts  # Batch intent parser
services/relayer/src/pipeline/verify712.ts      # Off-chain EIP-712 verifier
services/relayer/src/rules/whitelist.ts         # Sponsorship rules
contracts/test/AirAccountDelegate.t.sol  # Foundry tests
docs/gasless-eoa-enhance/00-spec.md      # Design spec
```
