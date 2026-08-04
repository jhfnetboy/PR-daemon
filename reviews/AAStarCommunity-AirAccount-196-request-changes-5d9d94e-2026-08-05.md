## Verdict: REQUEST_CHANGES (incremental re-review, head `5d9d94e`, round 2)

**All 7 items from the last round are genuinely fixed**, and the two structural additions — the baseline read-back and the new test suite — are the right ideas:

| Prior item | Status |
|---|---|
| [High] `.notes` unvalidated → every node fail-closed | ✅ rejected at parse time, **and** independently at the jq self-check (two layers) |
| [High] `metadata_version` only from a local un-versioned file | ✅ read-back added (`:121-147`), `max(local, published)+1` |
| [High] `--dry-run` really wrote `$OUT` | ✅ exits at `:217-222` before any write |
| [Medium] manifest written before minisign/seckey checks | ✅ prerequisites first (`:106-112`), then mktemp → sign → self-verify → atomic `mv` |
| [Medium] signer/node schema drift | ✅ **T1 is a genuinely valuable regression test** — it signs a real manifest and feeds it to the node's actual `load_manifest` |
| [Low] `$PUB` missing → silent skip of self-verify | ✅ `[ -f "$PUB" ] || die` |
| [Medium] `min_version` inherited from `PREV_RELEASES[0]` | ✅ now by highest semver |

T1 is the correct structural answer to schema drift and should stay. What blocks this round is that **the new read-back introduces an unauthenticated input into the trust root**, and the new suite cannot detect it — on the target platform every dry-run-based assertion passes unconditionally.

### 🔴 Blocking

1. **[High] `release-sign.sh:218` — `--dry-run` is 100% broken on stock macOS, i.e. on the machine that holds the signing key.** The banner is `echo "── dry-run:以下为组装结果(**未写 $OUT、未签名**)──"`. macOS ships `/bin/bash` **3.2.57**, whose parameter-name scanner is not multibyte-aware, so the ideographic comma right after `$OUT` is absorbed into the variable name and `set -u` aborts.
   Reproduced independently, two ways:
   ```
   /bin/bash -c 'set -u; OUT=/tmp/x; echo "未写 $OUT、未签名"'    → OUT<bytes>: unbound variable, rc=1
   /bin/bash -c 'set -u; OUT=/tmp/x; echo "未写 ${OUT}、未签名"'  → 正常, rc=0
   ```
   and a fully legal `--dry-run --no-baseline` run exits **rc=1 with zero bytes of stdout**, dying at `:218`.
   **Fix:** `${OUT}`. Verified this is the sole instance in the tree — `LC_ALL=C grep -nE '\$[A-Za-z_][A-Za-z0-9_]*[^ -~]'` across all five updater scripts hits only `:218`. One-line fix.

2. **[High] `release-sign.sh:132-144` — the baseline read-back parses an unsigned manifest, laundering untrusted input into a signed artifact.** It does `curl -fsSL "$BASE_URL/$CHANNEL.json"` and reads `.metadata_version` with **no `.minisig` fetch and no `minisign -V`** — inside a project whose entire design is "the manifest is signed and nodes fail-closed on a bad signature".
   Demonstrated end-to-end: serving an attacker-supplied manifest with `metadata_version: 999999999` and **no `.minisig` on disk at all** produced a manifest carrying `metadata_version: 1000000000` that is **genuinely signed by the real key** (`minisign -V` passes). Nodes then persist `seen_metadata_version` (`aastar-node-updater.sh:534`, ratchets up only), so every legitimate future release is `< seen` and rejected as a rollback attack — a permanent channel brick, unrecoverable without touching every node out of band. This is the exact failure mode this PR exists to prevent, relocated one step upstream.
   **Fix:** fetch and `minisign -V` the companion `.minisig` before reading any field; fail closed on a missing or invalid signature.

3. **[High] `release-sign.sh:127-129` vs `:145-146,158-161` — the read-back supplies the counter but not the content it must stay consistent with.** `metadata_version` now comes from the network, while `releases[]`, `rollback_floor` and `min_version` still come from the local `$OUT` or hardcoded `0.28.0` fallbacks. On the *exact* scenario that motivated the read-back — fresh clone / new machine, `$OUT` absent because `channels/*.json` is not in VCS — the signed manifest advances the counter while **dropping every prior release** (`releases_count:1`) and **silently resetting `rollback_floor` to `0.28.0`**, a signed weakening of the known-vulnerable floor.
   Node-side consequences: nodes needing a mandated intermediate hop jump straight past it; `apply <dropped-version>` fails with "manifest 里没有版本"; `PIN_VERSION` nodes match nothing and **silently stop updating forever**. And it is not undoable, because the counter already ratcheted past the complete manifest.
   Worst of both worlds: the counter is trusted from the network, the safety-relevant content is not.
   **Fix:** fix #2 first, then inherit from the *verified* manifest. **Do not reorder these two** — see Suggestions.

4. **[Medium] `release-sign.sh:132-143` — read-back failure degrades to the local baseline instead of failing closed.** `curl ... || true`, then a warning and carry on. Demonstrated: fresh clone + unreachable `--base-url`, without anyone passing `--no-baseline` → rc=0 and a signed `metadata_version=1`, reproducing the original permanent-rejection bug with no opt-out involved. `--no-baseline` exists precisely so this is a deliberate choice; a transient network error should not make it silently.
   **Fix:** distinguish "fetch failed" (abort) from "404 / genuine first release" (require explicit `--no-baseline`).

5. **[Medium] `kms/tests/updater/test-release-sign.sh:26-27,45-57` — three of the six greens cannot fail.** T2/T3/T4 assert only *that the command failed*, and finding 1 makes **every** dry-run fail on this platform. Proven decisively: T3's negative case (multiline notes) and a **perfectly valid control invocation** both return rc=1 — the assertions cannot distinguish a rejection from a crash. Separately, the `sign()` helper hardcodes `--no-baseline`, so the entire read-back path — i.e. the whole fix for last round's blocking item #2, and findings 2/3/4 above — has **zero** coverage.
   **Fix:** assert on the specific `die` message rather than on non-zero rc, add an rc=0 positive control, drop `--no-baseline` from the helper, and cover the read-back with a `file://` fixture (curl supports it — one line).

### Confirmed non-blocking

- **[Medium] `release-sign.sh:197-206` — the self-check is not the 逐字段镜像 it claims to be.** It omits the type checks the node enforces on `security`, `auto_apply_allowed` and `canary_ring`, and inherited `releases[]` entries pass through unvalidated for those fields. Demonstrated: a local `$OUT` whose prior entry carries `"security":"yes"` → **signer accepts and signs**, node **rejects** with `manifest schema 非法`. That is a live instance of the exact drift this PR claims to have closed; T1 misses it because it only ever signs from a pristine baseline. Add the three checks and extend T1 to seed a pre-existing `$OUT`.
- **[Medium] `release-sign.sh:137`** — the read-back progress line lacks `>&2` while `:139`/`:142` have it, so on the **default** (baseline-on) path stdout starts with `读回已发布 manifest(...)` instead of `{`, breaking the clean-pipeable-JSON promise the script itself makes at `:209`/`:219`.
- **[Low] `release-sign.sh:238-239`** — the two `mv -f` calls are individually but not jointly atomic; between them `$OUT` is new while `$OUT.minisig` is stale, so a reader or an upload script can observe a mismatched pair. The comment 正文与签名一起就位 overclaims. The same skew governs the upload step, which is undocumented and is where a body/signature mismatch would make every node fail-closed.

### Rejected

- **DeepSeek R1a: "`PUB` is only assigned in the non-dry-run block but used at `:234`"** — false positive. The dry-run path exits at `:221`, before `:234` is reachable.
- **DeepSeek R1b: "`--base-url` is attacker-controlled, SSRF"** — weak as stated (it is an operator flag on their own signing box). Blocking 2 is the real form of that concern, and R1 did not reach it.
- **One piece of my own evidence, withdrawn.** I first supported finding 5 with a mutation test — deleting the `--notes` validation block and observing `PASS=6 FAIL=0`. That does not isolate the cause: the jq self-check at `:205` independently rejects both notes cases, so the mutant would fail those inputs anyway. Finding 5 stands on the stronger proof above (a valid control invocation also returns rc=1). Noting it because the two-layer notes defence is real and deserves credit.

### Suggestions

- **Fix order is load-bearing: #2 before #3.** Making the signer inherit `releases[]` — tarball URLs and sha256 — from an unverified `curl` would upgrade this from permanent-DoS to *the signer notarizing attacker-chosen payload hashes with the real key*. Verify the signature first, then inherit from the verified copy; `pub_json` is already in memory.
- The two hand-written schemas will keep drifting — this round produced a fresh instance (`security`/`auto_apply_allowed`/`canary_ring`). Extracting the jq expression into one shared file both scripts read removes the class instead of re-syncing it by hand.
- Pin or gate the interpreter. The shebang is `#!/usr/bin/env bash`, but the harness invokes `bash`, so CI on bash 5 would never have caught finding 1 — and finding 1 only bites on the release manager's Mac. Add a bash-3.2 run, or lint the release path under `set -u` on macOS.
- The deeper issue behind #2/#3: the trust root's state (`metadata_version` + `releases[]` + `rollback_floor`) still has no authoritative, backed-up home, so the code reconstructs it from whichever of two unreliable sources happens to exist. Committing the signed `channels/*.json` to VCS is the structural fix; the read-back is a workaround that currently loses three fields. `SIGNING-KEY.md` documenting the backup gap honestly is good — worth closing it in code too.

### Assumptions

- Reviewed in a dedicated worktree at head `5d9d94e`; the mutation experiment ran on a throwaway copy and was deleted. Nothing in the PR branch was modified.
- Incremental scope is `b91e195..5d9d94e` (1 commit), plus the node side (`aastar-node-updater.sh`) where the signer's output must stay consistent — cross-layer consistency is in scope even when the file is not in the diff.
- No linked issue in the PR body — Issue-compliance section skipped.

---
*Reviewed by clestons (`$pr` v4, 4-round, incremental `b91e195`→`5d9d94e`): DeepSeek R1a+R1b (`deepseek-v4-flash`; 2 findings, both dead — one false positive, one weak) → Sonnet mechanical verification (ran the new suite; reproduced the bash-3.2 `set -u` abort two ways; ran a mutation test whose conclusion I later withdrew, see Rejected) → Opus R2 (independent; found the bash-3.2 break, the stdout leak and the suite's vacuity before seeing my notes, traced the node-side ratchet consequences, and supplied the fix-order constraint) → Codex R3 (`gpt-5.5`, in the worktree; CONFIRMED all six, zero challenges, added the fail-open-on-curl-failure finding) → Opus R4 (final verdict; demonstrated findings 2/3/4 end-to-end with a served attacker manifest, corrected my mutation-test reasoning, and found the `security`/`auto_apply_allowed`/`canary_ring` self-check gap that every earlier round missed).*
