## Verdict: REQUEST_CHANGES

**v4 pipeline, 4-round, incremental re-review** (R1a+R1b DeepSeek dual-pass → R2 Opus independent strategic review → R3 Codex adversarial PK → R4 Opus final verdict), against the single new commit `c0a6d13` pushed since the prior review (`806239e`), which claims to fix all 7 prior Blocking findings.

**Coverage**: full incremental diff reviewed (4 files, 254 lines, zero dropped by token budget). This remains a docs-only PR — zero application code, only planning documents for an unbuilt feature.

### Progress since last round

6 of the 7 prior Blocking findings are cleanly fixed, with good reasoning attached (not just word-swaps):
- Sampling-confirmation address now correctly routes to `sampling_requests`, not `leads`.
- All "ask for email" phrasing removed from the design doc — consistently rewritten as "never ask, already captured at invite registration."
- Forced-conversation-closure language removed; reworded to internal pacing awareness only.
- `scripts/no-real-pii.sh` added to both new-PII-table tasks' file scope.
- `T4.1.2` now explicitly requires two separate endpoints (aggregate vs. detail) with query-layer ACL, matching spec.md's hard requirement.
- `leads` gained a `UNIQUE INDEX ON (user_id) WHERE user_id IS NOT NULL` plus an explicit "look up by user_id, reuse, don't blind-INSERT" invariant — correctly justified by pointing at `users.email`'s existing unique index and `registerCustomer`'s reuse behavior.

### Blocking

1. **[Med] docs/agent/spec.md:229-230 — the fix commit's own new comment on `fee_cents` contradicts the fix commit's own new note in `tasks.md:276`.** spec.md now says "费用表里写的是 59(美元)，落库前必须 ×100 = 5900" (the fee lookup table stores dollars; the *writer* into `sampling_requests` must convert). `tasks.md` T2.3.2 (edited in this exact same commit, to fix this exact same $0.59 bug) says the opposite: "表里直接存美分（5900），不要存 59 再让调用方去 ×100" (the fee table itself must store cents; no caller ever converts). Both docs were touched in this one commit to close the same defect, and they now disagree about *who* performs the unit conversion. If both get implemented as literally written — T2.3.0 off spec.md, T2.3.2 off tasks.md — the value double-converts (5900 × 100 = 590000, reads as $5900). **Fix**: pick one owner (tasks.md's is the more airtight design — table stores cents, no caller ever multiplies) and rewrite spec.md's comment to match: "the fee table already returns cents; the write path stores it as-is; only the display layer divides by 100."
2. **[Med] docs/agent/spec.md:14 — §0 D-3 summary row still says `fee_usd`**, three lines below where the table itself was correctly renamed to `fee_cents`. This is the "read before the tables" section — an implementer skimming it first sees the old name. **Fix**: `fee_cents`.
3. **[Med] docs/agent/tasks.md:246 vs :252 — self-contradictory within one Task.** T2.3.0's 开发范围 (dev scope) line still says `fee_usd`; its own 验收命令 (acceptance criteria) six lines later already says `fee_cents`. **Fix**: `fee_cents` in the dev-scope line too.
4. **[Med] docs/design/agent-interaction-v2.md:547 and :626 — design doc still says "今天全填 59"** (store the literal dollar figure) in two separate places, directly contradicting the now-fixed `tasks.md` T2.3.2 requirement to store cents (5900). This is the exact phrase that produced the original $0.59 bug report. **Fix**: both instances → "全填 `5900`（美分）"。

*(F1-F3 independently found by Opus R2 reading the diff cold, then verbatim-fed to Codex R3, which CONFIRMED all three and additionally surfaced F4 as a MISSED item — re-verified via `git show` on both files before including it. R1a (DeepSeek) raised 3 findings in this neighborhood but all were false positives — see Rejected below — though one was pointing near where the real defect (F1-F4) turned out to be.)*

### Also found (non-blocking but worth fixing before/soon after merge)

- **[Low] docs/agent/spec.md:48 — the new UNIQUE INDEX is a partial index (`WHERE user_id IS NOT NULL`) but `user_id` itself is nullable.** A `leads` row written without a linked `user_id` bypasses dedup entirely. Since invariant 2 already states leads are only ever created via `registerCustomer` (which always has a user), `user_id TEXT NOT NULL REFERENCES users(id)` costs nothing and closes the gap.
- **[Low] docs/agent/tasks.md:315 — dedup fix pins `invited_by` to whichever sales rep registered the customer first.** If a second sales rep legitimately re-invites that same customer later, that rep's `WHERE invited_by = me.id` query returns zero rows for the lead. Worth deciding (reassign / co-owner / admin-only visibility) before T3.1.1 starts, rather than leaving it for the implementer to pick silently.
- **[Low] docs/agent/progress.md:9,17 — stale within this same commit.** Header still reads "规划完成，尚未开工" while the same commit moved T1.1.1 to `PR_OPEN`; "READY Task 数 8" doesn't match tasks.md's own updated count (7 READY + 1 PR_OPEN).
- **[Low] docs/agent/progress.md:28 — checkbox marked `[x]` "已合入 #142"**, but #142 (this PR) hasn't merged yet — it's the PR under review right now.
- **[Low] docs/agent/spec.md:44 — cross-reference says "见 §3.5 sampling_requests.ship_*"** but `sampling_requests` is actually §4 in this doc (the design doc's own :553 correctly cites §4).
- **[Low] docs/agent/spec.md:48 + tasks.md:302 — "look up then reuse" (SELECT-then-INSERT) has no upsert statement given**, and upserting against a *partial* unique index in SQLite/D1 requires the index predicate in the conflict target (`ON CONFLICT(user_id) WHERE user_id IS NOT NULL DO NOTHING`) or it errors with "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint." Worth spelling out in T3.1.1's dev scope to save the implementer a surprise.

### Suggestions

- After the F1-F4 fixes land, `git grep -n "fee_usd\|填 59\|全填 59" docs/` should return zero hits — a cheap mechanical check before closing this out.
- Consider a one-line global convention in spec.md §0 ("all money columns store the smallest currency unit; column names must carry `_cents`") to prevent this exact class of split fix from recurring.
- `progress.md`'s READY/PR_OPEN counts duplicate what `tasks.md`'s own status table already tracks — consider having `progress.md` link rather than restate the numbers, since restated counts are what went stale here.

### R1 findings not carried forward (rejected on review)

DeepSeek R1a raised 3 findings, all false positives verified against the actual repo: `git show <head>:apps/api/schema.sql` has zero hits for `leads`, `sampling_requests`, `fee_usd`, or `fee_cents` — none of these tables exist in any live schema yet, so "no migration path for existing dupes/data" doesn't apply to a table that has never been created. R1b (security-only pass) correctly fast-exited with no findings — pure planning content, no security-relevant surface.
