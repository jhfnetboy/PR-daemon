---
name: pr-fix
description: Fix jhfnetboy's own PRs that have REQUEST_CHANGES or APPROVE+comments needing follow-up. Checks out local repo, makes code fixes, self-reviews with DeepSeek+Sonnet+Opus (4-round) or DeepSeek+Sonnet (2-round), then commits and pushes as jhfnetboy. Only handles jhfnetboy's own PRs. Triggered by "$pr-fix", "$pr-fix OWNER/REPO", or "$pr-fix OWNER/REPO#N".
origin: pr-daemon
---

<!-- INSTALL NOTE
When installed globally via install-skills.sh --global, PR_DAEMON_ROOT is patched to the absolute
path of the PR-Daemon repo. When installed directly in the project, run from the PR-Daemon root.
-->

# PR Fix Skill — Autonomous self-fix for jhfnetboy's PRs

> ⛔ **ABSOLUTE CONSTRAINT #1 — jhfnetboy PRs only**
> ONLY process PRs authored by `jhfnetboy`. Never touch other people's PRs, even if RC'd.
>
> ⛔ **ABSOLUTE CONSTRAINT #2 — No force push, no --amend to published commits**
> Always add NEW commits on top of the existing branch. Never rewrite history that's already on the remote.
>
> ⛔ **ABSOLUTE CONSTRAINT #3 — Self-review MUST pass before pushing**
> Code fixes must clear the self-review pipeline before any `git push`. A failing self-review = iterate, not push.
>
> ⛔ **ABSOLUTE CONSTRAINT #4 — Never modify other people's business logic**
> You are fixing a specific reviewed issue. Do not refactor surrounding code, rename symbols, or make "while I'm here" changes outside the scope of the review comment.
>
> ⛔ **ABSOLUTE CONSTRAINT #5 — Skip ambiguous comments, report to user**
> If a review comment is subjective, architectural, or unclear — do NOT guess. Mark it `SKIP` and report it. The user decides.

## Roles

| Role | Model | When |
|------|-------|------|
| Comment parsing + fix drafting | Sonnet (this session) | always |
| Mechanical review of fix diff | DeepSeek API | R1, both paths |
| Challenge (code/security changes) | Sonnet (this session) | R2, 4-round only |
| Final authority on fix quality | Opus subagent | 4-round only |
| PK adversary | Codex agent | 4-round only |
| Final authority (docs/simple) | Sonnet (this session) | 2-round |

## Triage: 2-round vs 4-round

**2-round** (DeepSeek R1 → Sonnet verdict): ALL of these must be true:
- Fix type is docs / typo / comment / style / formatting / dep version bump
- Does NOT touch `src/` `contracts/` `lib/` `kms/` real logic
- No new public API / schema / auth change

**4-round** (DeepSeek R1 → Sonnet R2 → Codex PK → Opus verdict): ANY of these:
- Touches source code (`*.rs`, `*.sol`, `*.ts`, `*.js` in `src/` `contracts/` `kms/`)
- Security-sensitive: auth, crypto, payment, token, permission
- Fixes a logical bug (not just formatting)
- Unclear risk → escalate to 4-round

## Step 1 — Discover PRs needing fixes

Use the automated discovery script:

```bash
# Scan all 3 orgs — finds jhfnetboy's PRs with RC or human reviewer comments
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --needs-fix-only

# Single repo
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --repo OWNER/REPO --needs-fix-only

# Single PR  (also works: $pr-fix OWNER/REPO#N)
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --repo OWNER/REPO --pr N

# JSON output for programmatic use
python3 PR_DAEMON_ROOT/scripts/poll_fix_queue.py --needs-fix-only --output json
```

The script:
- Filters out CI bots (`github-actions[bot]`, `chatgpt-codex-connector[bot]`, etc.)
- Keeps `clestons` comments (primary reviewer account)
- Returns per-PR: review bodies + inline comment text + file/line location
- Prints `🔴` for CHANGES_REQUESTED, `🟡` for APPROVED+comments, `✅` for clean

Work the queue top-to-bottom: `🔴` first (RC), then `🟡` (suggestions).

## Step 2 — Parse review comments → fix plan

For each open review comment or REQUEST_CHANGES body:

1. **Classify the comment**:
   - `MECHANICAL` — clear, code-level fix (add missing check, rename, format, fix bug per the description)
   - `DESIGN` — architectural question, requires user decision → SKIP, report
   - `QUESTION` — author asked something, not a change request → SKIP
   - `RESOLVED` — already addressed in a later commit → SKIP

2. **Build a fix plan** for MECHANICAL items only:
   ```
   Comment: "warp::path::end() missing on openapi_spec route"
   File: kms/host/src/api_server.rs
   Fix: Add .and(warp::path::end()) after warp::path("openapi.yaml")
   Risk: Low — routing only, no auth change
   Triage: 2-round (docs endpoint, no logic change)
   ```

3. If no MECHANICAL items → report to user, exit.

## Step 3 — Checkout local branch

```bash
# Resolve local path from config/repo-roots.json
python3 PR_DAEMON_ROOT/scripts/resolve_repo.py OWNER/REPO
# → /Users/jason/Dev/aastar/SuperPaymaster

# Verify git identity before touching anything
cd /path/to/repo
git config user.name    # should be jhfnetboy or Jason
git config user.email   # should match

# Fetch + checkout the PR branch
git fetch origin
git checkout -b fix/pr-N-review origin/<headRefName>
# Or if branch already exists locally:
git checkout <headRefName> && git pull --rebase origin <headRefName>

# Confirm we're on the right branch and it's clean
git status
git log --oneline -3
```

**NEVER work on main/master.** Always work on the PR's source branch.

## Step 4 — Apply fixes

For each MECHANICAL fix item:

1. Read the relevant file(s) in full before editing
2. Apply the minimal change that addresses the review comment — nothing more
3. Re-read the changed file to verify the edit is correct
4. If the fix requires running a test or build to verify:
   - **Rust**: `cargo build -p <crate>` or `cargo test -p <crate>` (in the repo root)
   - **Solidity**: `forge build` / `forge test`
   - **JS/TS**: `node <file>` for syntax check, or existing test scripts
   - If the test environment isn't available, document it and proceed to self-review anyway
5. After all fixes applied, do a final `git diff` to confirm exactly what changed

```bash
git diff HEAD    # always review before staging
```

If any fix produces unexpected side-effects or can't be isolated → SKIP that fix, report to user.

## Step 5 — Self-review pipeline

Get the fix diff:
```bash
git diff HEAD > /tmp/fix-pr-N.diff
# Compress if large
python3 PR_DAEMON_ROOT/scripts/compress_diff.py --file /tmp/fix-pr-N.diff --budget 60000 > /tmp/fix-pr-N-compressed.diff
```

### 2-round path (docs/simple)

**R1 — DeepSeek:**
```bash
python3 PR_DAEMON_ROOT/scripts/deepseek_review.py \
  --diff-file /tmp/fix-pr-N-compressed.diff \
  --repo OWNER/REPO --pr N --output /tmp/fix-r1-N.md
```

**Sonnet verdict (you):** Read DeepSeek's findings. If no blockers → PROCEED. If blockers → fix them and re-run R1.

### 4-round path (code/security)

**R1 — DeepSeek** (same as above)

**R2 — Sonnet challenge (you):** Work from DeepSeek's findings. Spot-check security hunks.
Output compactly: `CONFIRM <ids>` / `REJECT <id — why>` / `ADD <[Sev] file:line — issue | fix>`

**R3 — Codex PK (MANDATORY):**
```
Agent(subagent_type="codex:codex-rescue", prompt="""
PK CHALLENGE: fix for OWNER/REPO#N. Diff + R2 findings inline — do NOT re-fetch.
Per finding: [CHALLENGE|CONFIRM|MISSED] id — reason ≤20 words.
DIFF:
<paste compressed diff>
FINDINGS (post-R2):
<compact list>
Return ONLY the structured critique.
""")
```

**Opus verdict (MANDATORY for 4-round):**
```
Agent(subagent_type="general-purpose", model="opus", prompt="""
Final authority on fix for OWNER/REPO#N.
Is this fix correct, complete, and safe to push? Respect Codex point-by-point.
Output ONLY:
VERDICT: PUSH | DO_NOT_PUSH
BLOCKING: <issues if DO_NOT_PUSH>
CONFIRMED_SAFE: <items>
REJECTED_CONCERN: <concern — reason>
ROUNDS — R1(DeepSeek): <summary>  R2(Sonnet): <summary>  R3(Codex): <summary>
""")
```

**If self-review → DO_NOT_PUSH:** go back to Step 4, fix the blocking issues, re-run pipeline.
**Max 3 iterations.** If still failing after 3 → report to user, do NOT push.

## Step 6 — Commit and push

Self-review passed. Commit using the fix description:

```bash
cd /path/to/repo
git add -p    # stage only the intended changes (prefer selective staging)
git commit -m "fix: address review comments on PR #N — <summary>"

# Verify what we're about to push
git log --oneline origin/<branch>..HEAD
git diff origin/<branch>..HEAD

# Push
git push origin <branch>
```

**Commit message format:**
- `fix(scope): address review — <what was fixed>` for bug/code fixes
- `docs: address review — <what was fixed>` for docs-only
- Always reference the original PR in the body if multi-item

## Step 7 — Re-request review

After push:
```bash
# Request review from clestons (the reviewer who raised the RC)
gh pr edit N --repo OWNER/REPO --add-reviewer clestons

# Or leave a comment explaining what was fixed
gh pr comment N --repo OWNER/REPO --body "$(cat <<'EOF'
Addressed review comments:
- [list each fix]

Self-review passed (DeepSeek R1 + Sonnet [+ Opus + Codex] — no blockers).
Ready for re-review.
EOF
)"
```

## Step 8 — Report

After each PR processed:
```
🔧 OWNER/REPO#N  FIXED  [2-round/4-round]
   Fixed: <list of MECHANICAL items addressed>
   Skipped: <list of DESIGN/QUESTION items, with reason>
   Self-review: PASS (R1+R2[+R3+Opus])
   Pushed: <branch> @ <commit>
   Requested re-review from: clestons
```

## What to SKIP (report to user instead of fixing)

| Comment type | Action |
|---|---|
| "Consider using X instead of Y" without clear correctness reason | SKIP — design choice |
| "Why did you do this?" | SKIP — question, not a fix request |
| "This could be improved by..." | SKIP — suggestion, not RC |
| Multi-file architectural restructuring | SKIP — scope too large |
| Requires running tests you can't run (e.g., real hardware) | SKIP — report required test |
| Comment on someone else's code (not jhfnetboy's PR) | Never process |

## Hard Rules

- **jhfnetboy's PRs only** — never touch other authors' PRs
- **No force push** — new commits only
- **Self-review MUST pass** before push — no exceptions
- **Minimal diff** — fix only what the review comment says
- **Max 3 self-review iterations** — escalate to user if still failing
- **NEVER use `gh pr review`** for re-requesting — use `gh pr edit --add-reviewer` or a comment
- **Always verify git identity** before committing: `git config user.name` should be jhfnetboy
- **Skip + report** is always safer than a wrong fix
