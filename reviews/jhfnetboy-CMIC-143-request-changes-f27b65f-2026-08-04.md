## Verdict: REQUEST_CHANGES

Solid feature with genuinely good self-caught race-condition fixes and a strong new e2e suite (8/8 passing, including a race repro that was verified to fail with the guard removed). One real gap slipped through the author's own turn-guard mechanism, plus one pre-existing backend gap that this PR newly exposes to users.

## Assumptions
- `jhfnetboy/CMIC` is in scope per `~/.config/prbot/repos.conf` (personal repo explicitly allowlisted).
- No linked issue with a formal DoD in this PR's body/title beyond its own self-described acceptance criteria (`e2e/tests/07-chips.spec.ts`, `pnpm -w run check`) — verified both pass per author's report; Issue-compliance section skipped as not applicable.
- Local checkout used: `/Users/jason/Dev/jhfnetboy/CMIC` (PR branch fetched as `pr-143-review`, matches head `f27b65f`).

## 🔴 Blocking

**[High] `apps/web/src/chat.ts:533` (`enterThread`) — the `turnSeq` guard this PR introduces only protects `addChips`, not `applyPatch`, so a stale response can still silently overwrite a newer `brief_patch`.**

`enterThread` takes a turn number (`myTurn = ++turnSeq`) *before* its `await fetch`, and unhides `$('dock')` before that await too — so the customer can type a follow-up while `enterThread`'s request is still in flight. `followUp` has no gate against `enterThread` being in-flight (`followUpBusy` only serializes followUp-vs-followUp). If `followUp` resolves first and applies its own (newer) `brief_patch`, the slower `enterThread` response then arrives and unconditionally calls `applyPatch(d.brief_patch)` — no `myTurn === turnSeq` check guards it, only the chip-rendering line 3 lines later does. `applyPatch` applies each field present in the patch (`if (p.qty) brief.qty = p.qty`, etc.) regardless of turn freshness, so a stale patch can silently revert fields (qty/product/color/etc.) the customer already corrected in a newer turn — with no error, no visual cue.

This is the exact bug **class** a pre-existing comment in the same file says was already found and fixed once (`"...否则两个回复的 brief_patch 可能乱序,旧的覆盖新的(Codex Med-4)"`) — for followUp-vs-followUp only. This PR introduces the first case where `enterThread` and `followUp` can race, and doesn't extend that same protection to it.

Independently confirmed: Opus R2 found this before reading any R1 findings; Codex R3, given the verbatim source and reachability chain, confirmed it without hedging ("the older `enterThread` response still runs `applyPatch(d.brief_patch)` unconditionally").

**Fix** (one line):
```ts
if (r.ok) { const d = await r.json() as ChatReply; if (myTurn === turnSeq) { applyPatch(d.brief_patch); firstChips = d.chips; } }
```

## Confirmed non-blocking

- **[Med] `apps/api/src/chat.ts:162`** (backend, not touched by this PR) — `reply` gets a price-neutralization regex before reaching the user; `chips` gets only type/length/count filtering, nothing content-level. This PR is what makes `chips` a live, clickable UI surface for the first time (previously discarded) — clicking a chip re-submits its exact text as the user's own message. A model output like `"$99 quote"` or `"WhatsApp +123"` fits comfortably in 48 chars / 4 items. Codex: *"the gap is integrity/social-engineering, not DOM injection."* Out of scope for this diff (requires touching `apps/api/src/chat.ts`) — flag as a fast-follow, ideally alongside T1.1.2.
- **[Med] `apps/web/src/chat.ts:537-538`** — same concurrency window also lets a stale `enterThread` unconditionally append `addThinking()` + `showBoxDirections()` after a newer `followUp` turn already rendered, so old thinking-panel/box-cards land below the new reply. **Already disclosed and explicitly deferred by the author to T1.1.2** in the PR body — not a new regression, not blocking.
- **[Low] `apps/web/src/chat.ts:550-554`** — `followUpBusy = true` is set before 4 statements that aren't wrapped in the `try`; if any threw, the busy flag would wedge permanently. In practice these are pure DOM ops on a static `#dock-go`, so not realistically reachable — downgraded from R1a's Medium. Still cheap to harden: move `followUpBusy = true` inside the `try`.
- **[Low] `apps/web/src/chat.ts:554`** — `spendChips` fires synchronously before the fetch settles; on a failed/offline request no replacement chips render, so a single network blip permanently kills the tap-to-continue affordance for that thread (falls back to manual typing, which still works).
- **[Low] `apps/web/src/chat.ts:663-671`** — `rehydrateThread` rebinds chip click handlers without re-enforcing `MAX_CHIPS`/`MAX_CHIP_LEN`. Self-XSS tier only (own localStorage) — a tampered archive could restore more/longer chips than the render path would ever produce.
- **[Low] `apps/web/src/chat.ts:564`** — the `if (myTurn === turnSeq)` guard inside `followUp` is dead code: `started` makes `enterThread` one-shot, `followUpBusy` serializes followUp calls, so nothing can advance `turnSeq` while a `followUp` await is pending. Harmless, but reads as if followUp is protected symmetrically with `enterThread` when only `enterThread` is the actual unguarded producer (see BLOCKING).
- **[Low] `apps/web/src/chat.ts:702` area (`restoreThread`)** — doesn't set `started = true`, so `enterThread`'s one-shot gate stays open after a restored session. Currently unreachable because empty-state controls stay `display:none` via `.hidden`, but that's an incidental protection, not a designed one.

## Rejected

- R1b's "chips need an allowlist / injection risk" — rejected. Verified in `addChips`: `Array.isArray` + `typeof === 'string'` + trim + `slice(0,48)` + `slice(0,4)`, rendered via `textContent` (not `innerHTML`), stored in a `dataset` attribute (auto-escaped on any HTML serialization/localStorage round-trip). `e2e/tests/07-chips.spec.ts` (lines ~194-216) directly feeds `<img src=x onerror=...>` + non-string + 200-char + 7-item payloads and asserts zero `<img>` elements, no global pwn flag set, injection string rendered as plain text, length capped at 48. R1b's own security-triage note already conceded "already sanitized" — self-contradictory low-confidence finding.

## Round summary
- **R1a (DeepSeek-full):** 1 finding — `followUpBusy` not reset if `spendChips` throws (no try/finally). Right instinct, overrated severity (Medium→Low, not realistically reachable).
- **R1b (DeepSeek-sec):** 1 finding — chips missing an allowlist. Rejected (see above); self-contradictory in its own output.
- **R2 (Opus, independent read before seeing R1):** confirmed+downgraded R1a's finding, rejected R1b's; independently surfaced the High `applyPatch` race, the (author-disclosed) card-ordering issue, the backend price-filter gap, and two Low findings; flagged architectural concerns (duplicated `ChatReply` type frontend/backend, three overlapping half-guards for turn-ordering).
- **R3 (Codex-PK):** fed verbatim source (both files) + explicit reachability chain for the two Medium+ findings; confirmed both without a single challenge or miss.
- **R4 (Opus final):** independently re-verified `applyPatch`'s per-field-conditional-but-turn-unaware semantics against source, re-verified the injection-rejection chain against source + e2e, added 2 new Low misses (`followUp`'s dead-code turn guard; `restoreThread` not setting `started`).

## Suggestions (non-blocking)
- The turn-ordering logic is now three overlapping half-guards (`followUpBusy`, `turnSeq`, `started`). A single `beginTurn()`/`isCurrent(n)` checkpoint that every post-await side effect (`applyPatch`, `addAgentSay`, `addThinking`, `showBoxDirections`, `addChips`, `history.push`) goes through would close this bug class for good instead of patching call sites one at a time (T1.1.2 candidate).
- `ChatReply` is declared independently on both sides (`chips: string[]` backend vs `chips?: unknown` frontend) with no shared contract — a backend field rename would fail silently at runtime, not at build time. Frontend should keep its own `unknown`-typed runtime validation regardless (model output isn't trusted), but a shared type module would catch drift early.
- Once the BLOCKING fix lands, consider extending `07-chips.spec.ts` with a race case for `brief_patch` itself (not just chips): mock turn 1 → `{color:'red'}` (stalled), turn 2 → `{color:'navy'}`, release, assert the final `brief.color` is `navy` (indirectly observable via quote/card text).

## Coverage
No files dropped by diff compression (2 binary screenshots excluded, expected).
