## Review — iDoris-ai/Self-FDE-WorkBench#85 @ d875f114

**Conclusion: REQUEST_CHANGES**

The previous `Sec-Fetch-Site` auth bypass is fixed correctly in this head: the browser console path now uses a server-signed HttpOnly/Secure/SameSite session cookie, while server-to-server callers still use `x-workbench-token` / scoped tokens. The D1 shim is also fail-closed when no store secret is configured, and the SQL paths use bound parameters plus escaped `LIKE` prefixes.

There is still one blocking persistence bug in the cold-start path.

### Blocking — D1-restored projects can still 500 on `/api/chat` after the container filesystem is lost

This PR persists `client.json` and `state.json` to D1, but the workset files remain on the container filesystem. After an ephemeral container restart, D1 can make `readProjectState(clientSlug, projectSlug)` succeed even though `clients/<client>/projects/<project>/` no longer exists locally.

The failing path is:

1. `/api/chat` reads the persisted project state and accepts the request when state exists (`fde-copilot/src/app/api/chat/route.ts:35-36`).
2. It immediately calls `appendConversation()` before `runTurn()` (`route.ts:38-44`).
3. `appendConversation()` writes `projectDir(...)/conversation.jsonl` with `fs.appendFile()` but does not recreate the parent directory (`fde-copilot/src/lib/clients.ts:263-265`).
4. `fs.appendFile()` does not create missing parent directories. I checked this mechanically with Node and it returns `ENOENT` for a missing parent directory.

That means the specific scenario this PR is trying to make survivable, "D1 has the project but the container disk is gone", still leaves a restored project unable to chat. Since chat is the path that later updates `state.usage`, this is not just a cosmetic conversation-history issue.

Suggested fix: add an explicit hydration/recovery path before fs-backed writes. Minimal version: after `readProjectState()` succeeds, ensure `projectDir()` exists and `conversation.jsonl` exists before `appendConversation()`. More complete version: persist or reconstruct the docs/conversation workset from the durable source of truth, then add a regression test for "D1 state exists, local project dir missing, `/api/chat` does not 500".

### Verified

- `pnpm --dir fde-copilot typecheck` passed.
- `pnpm --dir deploy/fde-copilot typecheck` passed.
- D1 `list` returning direct child segments matches the `MetaStore.children("")` and `MetaStore.children("<client>/projects/")` callers; caller-side sorting by `updatedAt` handles presentation order.
- R1's `uiSecret()` empty-key warning is not a real session bypass: `sessionValid()` returns false when no signing secret exists, and `/api/login` requires `WORKBENCH_UI_PASSWORD` before signing a cookie.

### Round Notes

- R1a DeepSeek full pass ran on the current 6-file diff. Its concrete findings were mostly hardening/noise: unsorted list output, no timeout/retry/error body on store calls.
- R1b DeepSeek security pass ran on the current diff. It raised store input-validation hardening and one false positive on empty session secret.
- R2 strategic review independently found the cold-start fs/D1 split-brain blocker.
- R3 Codex PK confirmed the blocker against the targeted hunks and mechanical Node evidence. External `codex exec` was unavailable in this sandbox (`failed to initialize in-process app-server client: Operation not permitted`), so this PK was performed by the current Codex session and recorded as degraded.
- Opus CLI was authenticated according to `claude auth status`, but both normal and safe-mode non-interactive Opus attempts hung without output; this review is therefore not labeled as a completed Opus 4-round.

## Self-Assessment

- Rounds: degraded 3-round run (R1 DeepSeek dual pass + R2 strategic subagent + R3 Codex/current-session PK). Skill-required triage was 4-round; Opus R2/R4 could not complete due local CLI hang, so I am not claiming a completed 4-round.
- R1 DeepSeek(flash): fed `/tmp/pr-85-compressed.diff` for head `d875f114`; produced R1a full and R1b security outputs.
- R2 strategic: read the compressed diff and R1 merged list; independently found the cold-start D1/fs split-brain blocker.
- R3 Codex: targeted hunk only, confirmed `appendConversation()` can fail `ENOENT` after D1 restores state without local project dir.
- R4 final verdict: REQUEST_CHANGES by current Codex session based on confirmed blocker; Opus R4 unavailable, explicitly recorded.
- Mechanical evidence: `pnpm --dir fde-copilot typecheck` pass; `pnpm --dir deploy/fde-copilot typecheck` pass; `fs.appendFile('/tmp/pr85-missing-parent/conversation.jsonl', ...)` returned `ENOENT`.
- **DeepSeek flash rating: 2/5** — R1a/R1b correctly classified the PR as significant and raised some useful hardening areas, but missed the real cold-start blocker that R2/Codex later confirmed; several findings were false positives or non-blocking.
- Improvement suggestion: feed R1 explicit issue/DoD context and cold-start scenario invariants, not only the diff, so it checks restored-state vs missing-filesystem flows.
- Skill consistency: partial deviation due Opus CLI unavailability; no fake Opus/4-round label used, and the posted verdict is grounded in mechanical evidence.

**Final conclusion: REQUEST_CHANGES**
