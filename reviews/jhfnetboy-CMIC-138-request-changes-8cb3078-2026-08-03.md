## 🤖 Multi-round review (DeepSeek R1 + Opus R2/R4 + Codex R3 PK)
_Incremental re-review of commit `8cb3078` (previous review was on `9448e03`). Verdict below is from the pr-daemon-loop v4 pipeline._

VERDICT: **REQUEST_CHANGES** — jhfnetboy/CMIC#138

This commit's message frames it as addressing the prior round's [High] finding ("点选后重渲开关"), but the new `RERENDER_ON_SELECT` toggle defaults to `false`, so the actual runtime logic is unchanged — the prior defect is still live. The commit also adds a new persistence path (`/save-render`) that, while well-intentioned (preserve "My History" without burning GPU), has its own correctness gaps: several of them stack with the still-open prior defect and can produce **permanent** breakage of a user's "我的出图" page, not just a transient one.

TOP FINDINGS:

1. **[High]** `apps/web/src/chat.ts:113,329` — `RERENDER_ON_SELECT = false` makes `needRender = RENDER_AVAILABLE && (RERENDER_ON_SELECT || !initialImg)` provably identical to the old `!initialImg`. The inherited-image path still skips `renderDeliveryImage` entirely, so the detail hero / sample page / proposal PDF can still show a box with no customer logo and the wrong paper color while the spec block states otherwise — the exact prior-round High finding, unchanged. Fix: either default `RERENDER_ON_SELECT = true` (restore strict color-lock), or run `renderDeliveryImage` silently in the background even when `initialImg` exists, to overwrite the hero once the locked render lands.

2. **[Medium]** `apps/api/src/index.ts:556` — `isRenderResp` (`normPath === '/render' || '/render-result' || '/render-pdf'`) is missing `/save-render` (and pre-existing `/my-renders`, `/render-finishes`). `/save-render`'s response (`{call_id, result_token}`, both `crypto.randomUUID()`-derived hex strings) goes through the fail-closed PII gate; `PHONE_RE`'s `\b\d{9,15}\b` alternative can match an all-digit UUID segment (~0.36%/call per Codex + Opus estimate). The DB `INSERT` + `persistRender()` (lines ~1011-1016) already committed *before* this PII-gated `json()` return (line ~575), so a hit returns HTTP 500 while leaving an orphaned `render_jobs` row with no token ever reaching the client — recreating the exact `has_pdf=0` bug class this PR series exists to fix.

3. **[Medium → compounds to persistent]** `apps/api/src/index.ts:951-963` (pre-existing, not touched by this commit, but directly triggered by it) — `/my-renders` is *also* missing from the `isRenderResp` whitelist and returns up to 100 rows, each carrying a `call_id`. Once one bad (all-digit-tail) row from `/save-render` exists, it sits in the table permanently — so a user's entire "我的出图" page returns 500 **every time**, not just transiently. Combined with finding #4 (no idempotency → every sample.ts reload mints a fresh row), the odds compound quickly (Opus estimate: ~7% after 20 reloads, ~30% cumulative toward the 100-row page limit). Fix together with #2: add `/save-render`, `/my-renders`, and `/render-finishes` to the `isRenderResp` whitelist (or have the PII scan skip known opaque-token fields), and consider making the `call_id`/`resultToken` format guaranteed non-numeric (e.g. a prefix segment that breaks `\b\d{9,15}\b`, not just `'chat-'` since the UUID tail after the last hyphen can still be all-digit).

4. **[Medium]** `apps/web/src/sample.ts:361-365` — the minted `{callId, resultToken}` from `saveRender()` is only assigned to the in-memory `sampleMeta`, never written back to `sessionStorage['cmic.sampleMeta']`. Every page reload / re-entry to `sample.html` while `sampleMeta` is unset (guaranteed whenever the inherited-image path was taken, since `chat.ts`'s `see3d.onclick` explicitly `removeItem`s `cmic.sampleMeta` in that branch) re-mints a brand new `render_jobs` row + a full R2 copy of the same PNG. No server-side content-hash dedup either. Fix: write the minted credentials back to `sessionStorage` on success, and/or dedup server-side per `(owner_user_id, image-hash)`.

5. **[Medium]** `apps/api/src/index.ts:998-1016` — `/save-render` has zero rate/quota check, unlike `/render` (10-min burst cap of 20 + daily cap 30/customer, 40/anon via `consume()`) and `/render-finishes` (same). Any logged-in customer session can push unbounded ~9MB writes to R2 + D1 with no cap — not GPU cost, but real storage/DB cost and, combined with #3, faster exhaustion of the 100-row `/my-renders` page.

Minor/non-blocking: `apps/api/src/index.ts:1002` PNG magic-byte check only verifies 2 of the 8 signature bytes (robustness, not security); `apps/api/src/index.ts:1013` `box_type` bypasses the `str()` length-cap helper used elsewhere (`product` already uses `.slice(0,60)`).

Rejected: R1's claim that the ">~8MB" error message is inconsistent with the 12MB check — 12MB base64 ≈ 9MB decoded, so the message describes decoded size and is roughly correct (same convention used elsewhere in this file, e.g. `/render-pdf`'s 11MB→"8MB").

### PK Summary | Verification

- **R1 DeepSeek(flash)**: R1a full pass found 3 Low findings (one later rejected as a non-issue, two confirmed minor/non-blocking). R1b security pass found nothing. Missed the entire substantive issue — the inert toggle, the PII-gate orphan bug, and the idempotency gap.
- **R2 Opus (independent strategic review)**: read the diff independently, then verified the toggle's boolean logic, traced `isRenderResp`/`PHONE_RE`/`persistRender` ordering in `index.ts`, confirmed `IMG_META_KEYS` in `render-store.ts` correctly excludes `providers` (ruled out one of its own hypotheses), and compared `/save-render` against `/render`'s real quota code. Produced 1 High + 4 Medium + 1 Low.
- **R3 Codex PK**: real `codex-cli` gpt-5.5, run in an isolated git worktree checked out at PR head `8cb3078`, read-only sandbox. Verified all 4 High/Medium findings against on-disk source — 4/4 CONFIRM, 0 CHALLENGE — and surfaced one additional pre-existing (out-of-scope) risk: `/render-finishes` also missing from `isRenderResp`.
- **R4 Opus (final verdict)**: full-diff scan surfaced the compounding `/my-renders` persistence angle (finding #3) that no earlier round caught — the difference between "occasional 500" and "permanently broken page for that user."

## 自评 — jhfnetboy/CMIC#138

- 轮数：4-round（triage 要求 4-round：改动触及 chat.ts/render.ts/sample.ts/index.ts 核心渲染与持久化逻辑，且是上一轮 [High] 的延续）。R1a+R1b 真跑 DeepSeek，R2 Opus 独立读 diff + 验证跨文件（`isRenderResp`/`PHONE_RE`/`IMG_META_KEYS`/`/render`限流），R3 Codex 真跑（独立 worktree，PR head，只读沙箱），R4 Opus 最终裁决。一致 ✅。
- 每轮每模型实际做了什么：
  · R1 DeepSeek(flash)：喂了增量 diff（111 行），R1a 出 3 条 Low（1 条后证伪），R1b 无安全发现。
  · R2 Opus：读了增量 diff + 我给的上一轮 High 原文 + chat.ts 关键上下文（`showDetail`/`see3d.onclick`/`renderDeliveryImage`），自己 grep 了 `isRenderResp`(:556)、`PHONE_RE`(:215)、`IMG_META_KEYS`(render-store.ts)、`/render` 限流代码(:770-790)，独立跑了一个 Monte Carlo 估算 PII 误撞概率。
  · R3 Codex：独立 git worktree(PR head 8cb3078)、只读沙箱，逐条 grep/nl 磁盘源码验证 4 条 finding，4/4 CONFIRM，另附 `/render-finishes` 同类风险。
  · R4 Opus 裁决：REQUEST_CHANGES，全 diff scan 挖出 `/my-renders` 持久化放大角度（finding #3），R1/R2/R3 均未提。
- 机械证据：`grep -n "isRenderResp\|PHONE_RE\|findPii"` 亲自核对 :556 白名单确实排除 `/save-render`；`sed -n '770,800p'` 核对 `/render` 真实限流代码存在而 `/save-render` 没有；`sed -n '340,375p' sample.ts` 核对 `sampleMeta` 从未回写 `sessionStorage`。
- **DeepSeek flash 评级：2/5** —— R1a 的 3 条 Low 里 1 条被证伪(8MB/12MB 文案)、2 条是真但边缘(PNG magic 部分校验、box_type 未限长)；R1b 完全 0 命中。比上一轮(1/5，纯假阳性)稍好——这次至少 2 条 Low 站住了——但仍完全没摸到本轮真正的核心问题(开关惰性、PII 闸孤儿行、幂等缺失)，这些都是 R2/R3/R4 才挖出来的。改进建议：这类"是否真的改变了运行时行为"的判断(布尔表达式化简)似乎是 flash 的系统性弱点，之前几轮也类似——建议下一轮试着把"这个改动是否只是表面修改/开关默认值是什么"作为单独一问显式塞进 R1 prompt。

## Issue compliance
No linked issue — this is a standalone follow-up commit within an existing PR review thread.
