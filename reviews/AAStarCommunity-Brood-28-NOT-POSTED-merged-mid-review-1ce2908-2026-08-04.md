# AAStarCommunity/Brood#28 — review completed but NOT posted (PR merged mid-review)

Pipeline ran to completion (R1a+R1b DeepSeek → Opus R2 → Codex R3 → Opus R4), reaching
REQUEST_CHANGES on the incremental diff `f4f507a..1ce2908`. Before posting, `gh pr view` no longer
matched the reviewed head: the PR had been self-merged by the author (jhfnetboy) at
2026-08-04T01:51:53Z, head advanced to `324adbb` (a **docs-only** commit reframing git-guard.sh as
"best-effort defense-in-depth, not a guarantee" rather than fixing the actual parser bug). GitHub
rejected the post attempt with `"Issue is locked"`.

Per pr-daemon-loop hard rule (never post to a merged/closed PR), the review below was **not posted**.
Recording here for audit trail + because the underlying bug is still live on `main` as of this write-up.

---

## Full review content (as it would have posted)

## AAStarCommunity/Brood#28 — REQUEST_CHANGES (incremental re-review, commit `f4f507a` → `1ce2908`)

v4 pipeline: DeepSeek R1a+R1b (parallel) → Opus R2 (independent read + R1 challenge) → Codex R3 (targeted PK, run in an isolated worktree at PR head against the real on-disk files) → Opus R4 (final verdict + full-diff missed scan). All four rounds ran; findings below were empirically reproduced (sed extraction re-run against the real `git-guard.sh` + `templates/pilot.example.yml`, plus live `git-guard.sh push` calls), not just reasoned about.

### What this commit correctly fixes (confirmed)
- ✅ **`heads/` push bypass closed** — `dst` now strips both `refs/heads/x` and the short `heads/x` form before the protected-branch check, so `push origin +refs/heads/x:heads/main` can no longer smuggle a trunk overwrite past the guard.
- ✅ **Fail-closed on `gh` API failure** — `merge-pr`'s `def_branch`/`head_ref` resolution now `die`s if `gh repo view`/`gh pr view` fails, instead of silently skipping the trunk/protected-head check (previous behavior was fail-open).

### Blocking (the commit's headline claim — "git-guard self-reads `.pilot.yml`" — does not work)

1. **[High] `git-guard.sh:37-39`** — the sed/tr extraction never strips a trailing `# comment`. The repo's own `templates/pilot.example.yml` puts an inline comment on every key. Reproduced end-to-end against the real files: with `base_branch: trunk  # 主干，受保护` in `.pilot.yml`, `git-guard.sh push origin trunk` **executes the push** (exit 0). The same file with comments stripped correctly `BLOCKED` (exit 3). Codex independently reproduced the same result in a separate worktree.
   *Fix: strip `#.*` before `tr`.*

2. **[High] `git-guard.sh:39`** — `protect_patterns` as a YAML block sequence (`protect_patterns:` / `  - release` / `  - hotfix` — the exact form the template ships) is never captured; the sed only reads the same line as the key, which is empty. Reproduced: pushing to a branch declared via block-form `protect_patterns` (e.g. `deploy`) is **allowed**. Only the undocumented flow form `[a, b]` works. Codex confirmed independently.
   *Fix: parse block sequences too.*

3. **[High] `skills/pilot/SKILL.md:71`** — the `doctor` bootstrap step provisions `.pilot.yml` for every new repo by **copying `templates/pilot.example.yml`** — i.e. the canonical setup path guarantees exactly the comment-laden, block-list format findings 1–2 show the parser can't handle. This isn't an edge case, it's the default.
   *Fix: fix the parser, then add a self-test asserting parser output == template's declared branches, so template and parser can't silently drift again.*

4. **[High] `skills/pilot/phases/run.md:15-21`** — this same commit **removes** the previous `--protect "$PROT"` threading (the mechanism that worked) and replaces it with the self-read parser (which doesn't), then asserts 「护栏已覆盖本仓库真实分支」. That's empirically false for any repo whose branch names aren't in the 7 hardcoded defaults (`main/master/develop/preview/integration/release/hotfix`) — a net safety regression shipped under a commit message claiming the opposite.
   *Fix: don't remove the `--protect` path until the self-read parser is actually fixed and tested.*

5. **[High, found by Opus R4's full-diff scan — missed by every prior round] `git-guard.sh:169`** — the **same broken `PROTECTED`** also feeds the `merge-pr` head-branch check. Before this commit, run.md threaded the real trunk name in via `--protect`, so a PR with `head=trunk, base=preview` was refused. After this commit, `trunk` never enters `PROTECTED` (findings 1–2), so that merge is now **allowed** — defeating the exact check whose comment says "merging/deleting a protected head is unsafe." All prior rounds (including R2/R3) framed this as a push-only regression; it isn't. Both call sites (`:118` push, `:169` merge-pr) need the fix + a test each.

6. **[Medium] `git-guard.sh:34`** — `_top` resolves the *current worktree* root. run.md mandates `git worktree add` per task, and `.pilot.yml` is **absent and untracked in Brood's own repo right now** (verified: `git ls-files` empty, file absent). So today, in this exact repo, the new self-read mechanism has nothing to read at all and silently runs on hardcoded defaults only — the feature this commit is *about* currently does nothing here.

### Also flagged (same root cause, non-blocking on their own but should land with the fix above)
- **[Medium]** No diagnostic when no config file is found, and no deprecation warning on the legacy `.repo-pilot.yml` fallback — contradicts SKILL.md's own "never silently ignore" principle.
- **[Medium]** `SKILL.md:55` documents flow-form `protect_patterns: [release, hotfix]` (parses) while `templates/pilot.example.yml` uses block-form (doesn't parse) — the two canonical docs disagree with each other.
- **[Low]** `sed … | head -1` under `set -o pipefail`: a large `.pilot.yml` → SIGPIPE → undocumented exit 141 with no output; an unreadable file leaks a raw `sed: Permission denied` with no `git-guard:` prefix.
- **[Low]** `for p in $PROTECTED` is unquoted — undergoes pathname expansion as well as comma-splitting. With a glob-ish `protect_patterns` entry and a matching filename in cwd, the iterated token becomes the filename instead of the pattern. `set -f` around the loop, or split via `while IFS=, read -r`.
- **[Low]** Stale comments at `git-guard.sh:16-20,158` still describe the caller-threaded `--protect` model this commit abolishes.

### Rejected
- R1b's "malicious repo could alter protected branches" — code-verified overstated: `PROTECTED` seeds from hardcoded defaults first, config/flags only *append*, and `is_protected` returns true on ANY match — config can only add protection, never remove it.

### Round summary
- **R1a (DeepSeek-full)**: 1 finding — same-line-only sed misses multi-line `protect_patterns`.
- **R1b (DeepSeek-sec)**: 2 findings — same area flagged independently from a security lens; 1 rejected as overstated.
- **R2 (Opus-strategic)**: escalated to High with live end-to-end reproduction (`trunk`/`deploy` pushes actually succeeding), added the doctor-bootstrap root cause, the untracked-`.pilot.yml` gap, missing diagnostics, and the doc-contradiction findings.
- **R3 (Codex-PK)**: ran in an isolated worktree at PR head against the real on-disk script + template, independent sed/`is_protected` simulation — CONFIRM on all 5 challenged findings, no dismissals.
- **R4 (Opus final)**: REQUEST_CHANGES; re-verified the parser break end-to-end; full-diff scan surfaced the merge-pr head-branch blast radius (finding 5) that all three prior rounds missed, plus the unquoted-glob issue.

Coverage: full incremental diff reviewed (117 lines, 2 files) — nothing dropped by compression.

---

## Status of the underlying bug as of the ACTUAL merged commit (`324adbb`)

`324adbb` ("docs(pilot): reframe git-guard as best-effort defense-in-depth, not the guarantee") touches
ONLY `SKILL.md` and `reference/git-safety.md` — `git-guard.sh` itself is byte-identical to what was
reviewed above. The doc change downgrades the promise from "guard covers real repo branches" to
"best-effort, not guaranteed; real enforcement should come from GitHub branch protection + a future
PreToolUse hook (TASK-40, not yet built)". This defuses the *doc-overclaim* framing of finding 4, but
findings 1/2/3/5/6 — the actual functional parser bugs and their blast radius — are unfixed and now
on `main`.
