## Verdict: REQUEST_CHANGES

**Incremental re-review — 4th round on this PR today.** Previous round (head `a0f0f83`) flagged 2 blocking High findings; this review covers exactly the one new commit since then (`2cbd866`, "2nd hardening round"), which set out to fix both. `v4` pipeline: DeepSeek R1a (full) + R1b (security) in parallel → Opus R2 independent strategic review (read all 3 patched scripts end-to-end, reproduced findings live in scratch repos) → Codex R3 adversarial PK (fed verbatim source, not summaries) → Opus R4 final verdict + full-diff missed-finding sweep.

### Prior blockers — verified independently, not trusted from the commit message

- **[High] `git-guard.sh` push remote-injection → FIXED.** Traced and live-verified: `push --force origin`, `push --all origin`, `push origin main`, `push origin HEAD:main`, `push origin +refs/heads/main`, `push <url> feat`, and `push origin HEAD` while standing on `main` are all now BLOCKED. Legitimate pushes (`push origin feat/x`) still succeed — no over-blocking.
- **[High] `auto-commit.sh` secret-guard parsing → PARTIALLY-FIXED.** The parsing defect itself is genuinely fixed (`git ls-files --others -z` + basename match correctly refuses a space-in-filename PEM, an embedded-newline filename, and a nested untracked path; a tracked-modified `token.ts` no longer false-positives). But the guard's actual *coverage* still lets real secrets through (see blocking finding below), and the new hard `exit 3` failure mode is itself a fresh way to fully disable the checkpoint system.

### Blocking

1. **[Med-High] `skills/pilot/scripts/followups.sh:75`** — the stale-lock steal this commit adds has no ownership token. The `EXIT` trap unconditionally `rmdir`s the lock dir with no check that this process still holds it. If waiter W's counter crosses the 30s threshold while legitimate holder H is still working, W steals (rmdir+re-mkdir); when H later exits, its trap deletes W's freshly-reacquired lock too. **Reproduced**: two concurrent `add`s both minted `FU-5` — the exact collision this lock exists to prevent. Fix: write a `$$`+timestamp token into `$lock_dir/owner`; steal only if the token is unchanged across the full window; the `EXIT` trap removes the lock only if the token still matches.

2. **[Medium] `skills/pilot/scripts/followups.sh:78`** — new regression from this same fix: `i=0` after a steal attempt makes the wait loop unbounded if the lock dir can't actually be removed (previously `i>300` hard-failed after ~15s). **Reproduced**: unwritable `docs/agent` + a pre-existing lock dir → the script printed the steal message repeatedly and was still running when killed at 95s. A silent hang inside `pilot run`/`auto-commit-loop.sh` is worse than the hard-fail it replaced. Fix: cap steal attempts (e.g. 3), then `exit 3` with the old message.

3. **[Medium] `skills/pilot/scripts/auto-commit.sh:53`** — the prior High blocker's regex is still incomplete: `prod.env`, `config.env`, `.env-prod`, `.envrc`, `id_rsa_work`, `id_ed25519_github`, `deploy_key`, `backup.id_rsa` all slip through and get `git add -A`-committed. Fix: anchor `.env` as `(^|[._-])env($|[._-])`, prefix-match the key names (`^id_(rsa|dsa|ecdsa|ed25519)`), add `([._-]|^)key($|[._-])`.

4. **[Medium] `skills/pilot/scripts/auto-commit.sh:59`** — a single false-positive untracked file (e.g. `docs/secrets-guide.md`, `token.test.ts`) `exit 3`s the *entire* checkpoint, and `auto-commit-loop.sh` calls it `|| true` into an unread log — the safety net silently stays off indefinitely. Combined with finding 3, this is a self-inflicted denial of the exact feature the PR exists to provide. Fix: stage everything except the flagged paths and warn loudly; never hard-fail the whole checkpoint for one false positive.

5. **[Medium] `skills/pilot/scripts/followups.sh:116`** — `case "$pos" in FU-[0-9]*)` is a bash *glob*, not a regex, so metacharacters pass validation and get interpolated straight into the awk ERE. **Reproduced**: `followups.sh done 'FU-1.*' --pr 9` marked `FU-1, FU-10, FU-11, FU-12` all done in one call — silent mass-closure of an "append-only, never lose an item" ledger. Fix: `[[ "$pos" =~ ^FU-[0-9]+$ ]]`.

### Also found — missed by every prior round including this one until Opus R4's full-diff sweep

- **[Med-Low] `skills/pilot/scripts/git-guard.sh:68`** — `git remote | grep -qx -- "$remote"` uses BRE, not `-F`. This is the exact check this fix commit just added to close the exfiltration path, and it's bypassable: with a bare repo at local path `./ori.in`, `git-guard.sh push 'ori.in' feat/x'` passes the "must be a configured remote" check (regex `ori.in` matches the line `origin` — `.` matches the `g`) and git actually pushes into `./ori.in` (confirmed on disk: `* [new branch] feat/x -> feat/x`). Fix: `grep -qxF -- "$remote"`.
- **[Medium] `skills/pilot/scripts/auto-commit.sh:25-40`** — detached HEAD defeats every protection check this commit touches. `git rev-parse --abbrev-ref HEAD` returns the literal string `HEAD` when detached, matching neither the hardcoded list nor the `PILOT_PROTECTED` loop. **Reproduced**: detached at trunk, `auto-commit.sh` ran `git add -A` and committed ("✓ checkpoint committed on 'HEAD'") — a dangling commit that gets lost on the next checkout. Also fires mid-`rebase -i`/`bisect` (both leave HEAD detached). Directly contradicts the script's stated purpose ("work is NEVER lost"). Fix: `[ "$branch" = HEAD ] && { echo "...skipping"; exit 0; }`, plus bail on `.git/rebase-merge`/`rebase-apply`/`BISECT_LOG`.

### Confirmed, non-blocking (Medium/Low — should be addressed, not gating this round)

- `auto-commit.sh:27` vs `git-guard.sh`'s `is_protected()` — the hardcoded default protected-branch list still diverges from git-guard's boundary-aware prefix match in both directions (`preview.2`/`develop-x`/`main-2`/`integration/foo` checkpoint-committed despite being push-blocked; `releasenotes` checkpoint-blocked despite being push-allowed). Extract one shared `lib/protected.sh` — three hand-mirrored copies (git-guard, auto-commit, `safe-cleanup.sh --protect`) will keep drifting.
- `git-guard.sh:29` + `auto-commit.sh:35` — `PILOT_PROTECTED` split on `,` with no per-entry trim: `'trunk, staging'` silently voids the `staging` entry in both scripts. `phases/run.md:298` has the model *build* this string from `.pilot.yml`, so this isn't theoretical.
- `install.sh:20` — the `.repo-pilot.yml`→`.pilot.yml` rename has no migration/fallback: a repo with a pre-existing `.repo-pilot.yml` and a custom `integration_branch` now silently reads as "no config" and falls back to `base=main`/`integration=preview` — i.e. the rename can silently repoint the merge rail. This is the highest-consequence part of the rename and the only piece left undefended (`PILOT_PROTECTED` got a documented fallback; this didn't).
- `ensure-pr-daemon.sh` — `REPO_PILOT_PR_DAEMON_ROOT` dropped with no back-compat fallback, inconsistent with `PILOT_PROTECTED`'s own precedent.
- `followups.sh:120` — dead awk rule with an empty action block.
- `SKILL.md:9` — the new "唯一例外" note claims auto-commit has 未跟踪文件密钥防护 that rejects `.env`/key/credential; given the gaps above, the doc currently overstates the guarantee it's using to justify the `git add -A` exception.

### Rejected

- "`rm -rf "$lock_dir"` can delete an arbitrary path if lock_dir is attacker-controlled" — `lock_dir` derives from `--docs-dir`, a local toolchain CLI flag, not attacker/remote input. The `rm -rf` fallback is a real smell but the actual defect is the missing ownership token (blocking finding 1), not arbitrary deletion.
- "`known_hosts`/`authorized_keys` in `secret_re` are false positives" — these were explicitly requested by the prior review round to close a stated gap; intentional, not a bug.
- "`PILOT_PROTECTED` can be overridden by attacker-controlled environment" — whoever controls the environment already controls the shell running git; not a meaningful trust boundary.

### Rounds

- **R1a (DeepSeek full, deepseek-v4-flash)**: 2 findings — both right-line/wrong-root-cause (`rm -rf` in the lock steal, called "arbitrary deletion" rather than the actual ownership-token gap) or already-intentional (`known_hosts`/`authorized_keys`). Missed all 6 Medium+ issues R2 found.
- **R1b (DeepSeek security, deepseek-v4-flash)**: 2 findings, both rejected on inspection — same `rm -rf` claim reframed as path-traversal, plus an env-var-trust claim that isn't a real boundary. Self-triaged "low."
- **R2 (Opus, independent read)**: read all 3 patched scripts end-to-end and mechanically reproduced 10 findings in scratch repos before/independent of R1 — 6 Medium+, all later Codex-confirmed.
- **R3 (Codex, gpt-5.5, fed verbatim script source inline)**: CONFIRMED 6/6 of R2's Medium+ findings, zero challenges, zero false positives.
- **R4 (Opus, full diff + all rounds)**: confirmed R2/R3's 6 findings, rejected R1's 3 mischaracterizations, and found 2 additional issues via its own live full-diff sweep — the `grep -qx` BRE bypass of this commit's own new remote-allowlist check, and a detached-HEAD bypass of `auto-commit.sh`'s branch protection.

Coverage: all 4 changed files fit in the compressed diff (no files dropped).
