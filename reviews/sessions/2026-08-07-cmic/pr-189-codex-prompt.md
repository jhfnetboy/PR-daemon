PK CHALLENGE — jhfnetboy/CMIC#189. Pure-docs PR: 4 new entries (FU-20..FU-23) appended to a follow-up ledger `docs/agent/followups.md`. Your job is to REFUTE the findings below, not to agree with them.

WORKING TREE (read-only, already checked out at the PR head 074da710):
/private/tmp/claude-502/-Users-jason-Dev-tools-PR-Daemon/76b79141-505b-4469-bd90-4a90fffe7649/scratchpad/cmic-189

SELF-CHECK FIRST (grep/sed/cat ONLY — you have NO network and NO ability to run npx/pnpm/python; do not try):
  grep -n 'DEFAULT_TOL = 1.5' render/pipeline/geom_guard.py     # must hit line 87
  grep -n 'FU-23' docs/agent/followups.md                        # must hit
If either misses, say so and STOP — you are in the wrong tree.

ESTABLISHED FACTS (I ran these in the real environment; treat as given, do NOT try to re-run them):
- `gh api repos/jhfnetboy/CMIC/branches/main` → {"protected": false, "protection": {"enabled": false}}; same for `preview`; repo owner `.type == "User"`; `/branches/*/protection` and `/rulesets` both return HTTP 403 "Upgrade to GitHub Pro or make this repository public".
- PR #188 (which merged those 15 commits into `main`) has `reviews: []`.
- `git diff --shortstat 327c708..b497b12` = 49 files, 4116 insertions; 15 commits, none with a `(#N)` suffix; exactly 5 subjects carry 🔴.
These are network facts. Do not challenge them for lack of evidence — challenge only their INTERPRETATION.

FINDINGS TO CHALLENGE (all statically decidable from the source EXCEPT F1, which is interpretation-only):

F1 [Medium] FU-20 (interpretation only) — the entry ends "机械强制的修法:GitHub 分支保护对 preview 也要求 PR,而不是只保护 main。" I claim (a) the premise "只保护 main" is false — main is `protected: false`; and (b) the prescribed fix is not executable on this plan (403). Try to refute: is there a reading of "只保护 main" that is true and does not depend on GitHub branch protection? Search docs/ and .github/ for any documented convention. Is there any OTHER mechanism in this repo that gates pushes to main? Answer from the tree.

F2 [Low] FU-22 — the entry says "modal_app.py :813 组装 _meta.providers 时只保留 provider 那几个字段", and boasts "行号是核过的 —— Codex 给的 768/814 偏了几行". I claim :813 is the WRONG structure: it is inside the `item` dict appended to `usage_list` (which becomes `out["_usage"]`), whereas `_meta.providers` is built at `prov_meta = {...}` and wrapped as `_fin_meta = {"providers": prov_meta}`. Open render/pipeline/modal_app.py and report the EXACT line numbers of: (i) the `item = {"kind": "image_provider"...` in the FINISH-set function, (ii) `usage_list.append(item)` after it, (iii) `out["_usage"] = `, (iv) `prov_meta = {k: {`, (v) `_fin_meta = {"providers"`. Then say whether :813 can fairly be called "组装 _meta.providers". Refute me if :813 is defensible.

F3 [Low] FU-23 ① — the entry says "配额耗尽/事务 abort 时 putImages 静默 resolve … 下次 restore 取不到就把 img 和 data-real 一起移除". I claim this omits a THIRD fallback layer: `restoreImages()` in apps/web/src/chat.ts tries `fetchStoredRender` (R2, 30-day retention) BEFORE `im.remove()`. Read that function and decide: does an IndexedDB miss alone remove the img, or only after R2 also misses? Under exactly what conditions is the image truly lost? Refute me if the R2 layer does not actually gate the removal.

F4 [Info] — I claim the finish path hand-picks 3 provider fields into `_meta.providers` while the OTHER path (`render_set`) passes the full per-view meta (including geom_*) through. Verify or refute by comparing the two `prov_meta` constructions in modal_app.py; give both line numbers.

Also: FU-22 asserts the geometry evidence is unreachable by default. Trace `geom_rejected_views` ← `degraded_to_cg` ← `geo["enforced"]` ← mode, and state whether the default mode makes it structurally unreachable. Give line numbers.

Per finding output exactly one line: [CHALLENGE|CONFIRM|MISSED] Fn — reason ≤25 words + the line numbers you actually read.
Then one final line: ANY OTHER FACTUAL ERROR you found in the four entries that I did not list (or "NONE").
Return ONLY the structured critique. Do not post anywhere.
