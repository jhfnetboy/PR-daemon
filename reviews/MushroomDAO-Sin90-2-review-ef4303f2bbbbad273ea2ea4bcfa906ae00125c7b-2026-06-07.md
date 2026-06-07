## PR Review: MushroomDAO/Sin90#2 — chore: Apache 2.0 license compliance

**Verdict: COMMENT** (non-blocking — documentation PR, one security note worth mentioning)

### Findings

**[PK-added] Medium** `.github/workflows/cla.yml:29` — Action pinned to tag `@v2.6.1` instead of immutable commit SHA
- This workflow runs under `pull_request_target` with access to `secrets.CLA_TOKEN` 
- Tag references are mutable — a compromised tag could inject malicious code into a secrets-bearing job
- Fix: pin to commit SHA, e.g. `uses: contributor-assistant/github-action@<full-commit-sha>`

**[Confirmed] Low** `.github/workflows/cla.yml:5-6` — CLA_TOKEN documented as "repo scope from org admin account"
- The token has broader scope than needed for CLA signature collection
- Recommend: use a fine-grained PAT scoped to the specific repo with minimal permissions

### License Files
- `LICENSE-zh.md` — Chinese Apache 2.0 translation, proper disclaimer ✅
- `TRADEMARK-zh.md` — bilingual trademark policy, well-structured ✅
- `NOTICE` — bilingual attribution correctly updated ✅
- `README.md` — license section properly links all 5 files ✅
- `CONTRIBUTING.md` — clear CLA explanation and workflow guide ✅

### PK Summary
| Finding | Result |
|---------|--------|
| pull_request_target + write perms | Rejected — no checkout/run, risk limited to cla.json |
| CLA_TOKEN admin PAT exposure | Confirmed — real concern, document-level fix suggested |
| Tag pin supply-chain risk | PK-added — `@v2.6.1` mutable in privileged workflow |
