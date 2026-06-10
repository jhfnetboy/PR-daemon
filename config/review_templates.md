# Review Templates — token-efficient, no fluff

Concise templates for the review pipeline. Goal: push mechanical work to DeepSeek
(cheap), keep Claude rounds short, no preamble/postamble. Read the diff ONCE.

---

## R1 — DeepSeek (does the heavy lifting, ~$0.001/PR)

DeepSeek gets the compressed diff and produces ALL the mechanical work in one call:

```
PROMPT (to DeepSeek):
You are R1 of a PK review pipeline. From the diff, output EXACTLY these sections, no prose:

FILES: <one line per file: path — what changed in ≤10 words>
FINDINGS: <list. each: [Sev] file:line — issue ≤15 words | fix ≤12 words>
TRIAGE: trivial|significant — reason ≤15 words
SKELETON: <a 4-line draft review comment Claude can refine>

Diff:
<compressed diff>
```

DeepSeek output is the working base. Claude does NOT re-read the diff from scratch —
it validates DeepSeek's findings and spot-checks specific hunks only.

---

## R2 — Sonnet challenge (short, works from R1)

Do NOT re-derive everything. Take DeepSeek's FINDINGS, then output ONLY deltas:

```
CONFIRM: <finding ids that are real>
REJECT: <finding id — why, ≤12 words>
ADD: <[Sev] file:line — missed issue ≤15 words | fix ≤12 words>
```

Spot-check only the hunks tied to high-severity or security-sensitive findings.

---

## R3 — Codex PK (pass diff inline, don't re-fetch)

Give Codex the compressed diff + R2's net finding list IN THE PROMPT. Ask for:

```
Per finding: [CHALLENGE|CONFIRM|MISSED] id — reason ≤20 words
```

Do NOT tell Codex to run `gh pr diff` (wastes a round-trip). Paste the diff.

---

## Final verdict — Opus (fixed template, no essay)

Pass Opus the COMPACT round summaries (not full re-explanations). Output ONLY:

```
VERDICT: APPROVE | REQUEST_CHANGES
BLOCKING: <[Sev] file:line — issue | fix>   (empty if APPROVE)
CONFIRMED: <[Sev] file:line — issue | fix>
REJECTED: <finding — one-line reason>
SUGGESTIONS: <optional enhancements, ≤3 bullets>
```

No "Summary", no "Process note", no praise. Decision + evidence only.

---

## Posted comment — compact markdown

```markdown
## Review: OWNER/REPO#N — <title>
**Verdict: VERDICT** · <Nround> · PK: <1-line>

### Blocking  (omit if APPROVE)
- **[Sev]** `file:line` — issue. Fix: …

### Confirmed
- **[Sev]** `file:line` — issue. Fix: …

### Rejected
- finding — reason.

### Suggestions  (optional)
- …
```

Rules:
- ≤15 words per finding line. No restating the PR description.
- REQUEST_CHANGES: every blocking item needs a concrete trigger + fix.
- APPROVE: Blocking section omitted; Suggestions optional.
- Skip sections that are empty. No filler sentences.
