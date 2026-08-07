PK CHALLENGE — jhfnetboy/CMIC#191. REFUTE the findings below, don't agree with them.

WORKING TREE (read-only, PR head 7a910f65):
/private/tmp/claude-502/-Users-jason-Dev-tools-PR-Daemon/76b79141-505b-4469-bd90-4a90fffe7649/scratchpad/cmic-191

SELF-CHECK (grep/sed/cat ONLY — no network, no npx/pnpm/node_modules exists; do not try to run tests):
  grep -n 'bp.render_intent === true' apps/api/src/chat.ts        # must hit ~1007
  grep -n 'if (wantRender)' apps/web/src/chat.ts                  # must hit ~1213
If either misses, say so and STOP.

CONTEXT: `render_intent` is the flag by which the CHAT MODEL asks the app to start a paid GPU render. Its instructions were mistakenly written into the `brief_patch` field list while the parser read top-level → it was ALWAYS false. This PR fixes the contract (moves it to a top-level prompt section + JSON template) and adds a fallback `obj.render_intent === true || bp.render_intent === true`.

ESTABLISHED FACTS (I verified; challenge INTERPRETATION only, do not re-derive):
- Base `origin/preview` chat.ts:995 was `const renderIntent = obj.render_intent === true;` with the instruction living at :524 inside the brief_patch list → the flag could never be true.
- `BOX_TYPES` (apps/web/src/funnel.ts:37-42) has exactly 4 entries; `renderL2` (apps/web/src/chat.ts:578) loops over all of them submitting one /render each.
- Server quota (apps/api/src/index.ts:851-862): 20 per fixed 10-minute window for ALL buckets, plus 30/day when `me.role === 'customer'`.
- I statically re-ran the new test's 3 contract assertions: at HEAD all green; applying mutation R1 (literally re-inserting the `- render_intent: set TRUE ...` line into the brief_patch list) turns EXACTLY ONE red (②b-3). So that mutation is load-bearing.

FINDINGS TO CHALLENGE:

F1 [Medium] `apps/web/src/chat.ts:1213` — I claim this PR makes the `if (wantRender)` block LIVE FOR THE FIRST TIME (it was unreachable while the flag was always false), and that the block has NO cap or cooldown on model-initiated paid renders. Its only guard is `if (inflightFinishes.size > 0)`, which blocks a CONCURRENT second batch but not a SEQUENTIAL one — once a batch finishes, `inflightFinishes` is empty and the next `render_intent:true` turn fires 4 more jobs. The dedup key `dir:${type}:${l}x${w}x${h}` (chat.ts:581) is in-flight only, with no completed-render cache. Therefore ~5 model-initiated triggers inside 10 minutes → 429, and ~7 → the customer's entire daily budget. REFUTE ME: read `photorealVerdict` / `canRenderPhotoreal` (apps/web/src/render-gate.ts) and the whole `wantRender` block, and find any cap, cooldown, sticky-false condition, or state that prevents repeat firing across turns. Is `photorealVerdict` itself a sufficient limiter (e.g. does it go false after the first render)? Answer from the source.

F2 [Medium] `apps/api/src/render-intent.test.ts` — the file's stated purpose is 「别让这个开关变松」 (don't let this switch get loose). Its `truthyTraps` table (:44-51) and `falsy` table (:52-56) both feed values through `intentOf()`, which places the value at TOP LEVEL only (`render_intent: raw` with `brief_patch: {}`, :26). The PR adds a SECOND read site (`bp.render_intent`) whose only test (②c, :110ish) passes literal `true`. I claim: mutating `bp.render_intent === true` to `!!bp.render_intent` leaves every assertion in the file green. REFUTE ME: find any existing assertion that would go red under that mutation.

F3 [Medium] `apps/api/src/render-intent.test.ts:93` — `sys.slice(sys.indexOf('capture any concrete fact'), sys.indexOf('CHIPS:'))`. I claim if the START anchor is ever reworded, `indexOf` returns -1, JS clamps a negative start to `len-1` which exceeds the end index, the slice yields `''`, and the PR's own load-bearing reverse assertion `!bpSection.includes('render_intent')` then passes VACUOUSLY. REFUTE ME: is that JS slice semantics correct, and is there anything upstream that would fail loudly first?

F4 — I judged DeepSeek's finding ("`bp.render_intent` is read but `sanitizePatch` drops it from the output patch → the fallback should also write it into the output patch") a FALSE POSITIVE, because `render_intent` is returned as a top-level field of `data` at chat.ts:1010, not via the patch. REFUTE ME: is there any path where the flag must be in `brief_patch` to reach the browser? Trace it (apps/api/src/index.ts around the chat route → apps/web/src/chat.ts:52,1176).

Per finding output ONE line: [CHALLENGE|CONFIRM|MISSED] Fn — reason ≤25 words + line numbers you actually read.
Then one final line: ANY OTHER REAL DEFECT you found that I did not list (or "NONE").
Return ONLY the structured critique.
