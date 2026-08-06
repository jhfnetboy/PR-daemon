#!/usr/bin/env python3
"""
deepseek_review.py — R1 of the PK pipeline. DeepSeek does the heavy lifting.

Pushes all mechanical first-pass work to DeepSeek (~$0.001/PR) so Claude only
does hard judgment. Outputs a structured, token-tight result:
  FILES / FINDINGS / TRIAGE / SKELETON

Usage:
  python3 scripts/deepseek_review.py --diff-file /tmp/pr.diff --repo OWNER/REPO --pr N
  python3 scripts/deepseek_review.py --diff-file /tmp/pr.diff --repo OWNER/REPO --pr N --output /tmp/r1.md
"""

import sys, json, time, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent

# ── Incremental re-review block (added 2026-08-06) ──────────────────────────────────────────
# Injected only when --prior-review is passed. Rationale, measured on CoLivingOS#74 + #75:
# on an incremental round the real blocking findings were BOTH residue of the previous round —
# a finding fixed in one place and missed in another. The missed place is, by definition, not in
# the new diff, so a diff-only pass cannot reach it. R1a scored 0/4 then 0/1 on those two rounds.
# This block is what makes the漏改点 class reachable at all.
PRIOR_REVIEW_BLOCK = """
════════════════════════════════════════════════════════════════════════════
THIS IS AN INCREMENTAL RE-REVIEW. The diff below is ONLY what changed since our last review.
The text below is the review WE posted last round. The author's new commits claim to address it.

⚠️ YOUR HIGHEST-VALUE JOB THIS ROUND is the FOLLOW-UP CHECK, not the diff:

For EVERY finding in the prior review, decide one of:
  · FIXED     — the new diff fully addresses it
  · PARTIAL   — addressed in one place, MISSED somewhere else  ← report this, at the ORIGINAL severity
  · NOT FIXED — untouched                                       ← report this, at the ORIGINAL severity

A PARTIAL fix is the single most common defect on an incremental round, and it is usually
INVISIBLE IN THE DIFF: the surviving wrong line was not touched by these commits, so it does not
appear below. Do NOT restrict yourself to changed lines for this check — if the prior review named
a file:line, reason about whether the fix would have had to touch OTHER places too (a summary
sentence, a second call site, a duplicated spec, a downstream doc), and say which ones to verify.
When you cannot confirm from the diff, emit an explicit VERIFY line naming the exact file and what
to grep for — a precise "check this" beats both a false CONFIRM and silence.

Report follow-up results in FINDINGS using this shape:
  [Sev] file:line — FOLLOW-UP <prior finding in <=8 words>: PARTIAL/NOT FIXED — <what survives> | fix
  [Sev] file:line — VERIFY <what to check> | <how to check it>

PRIOR REVIEW:
{prior}
════════════════════════════════════════════════════════════════════════════
"""

SECURITY_PROMPT = """You are R1b of a multi-round PK code review — security-only lens.
Examine ONLY security concerns in the diff below. Output EXACTLY these sections and NOTHING else.

FAST EXIT (check this FIRST, before anything else): if the diff has NO security-relevant surface —
no auth, crypto, signature/nonce, payment/token, permission/access-control, state persistence, or
untrusted-input handling — then output EXACTLY these two lines and STOP. Do NOT repeat, elaborate,
or add anything:

NEVER fast-exit on these, no matter how the files are named or how small the diff is:
  * any endpoint/handler that is added or modified and either reads user-controlled input, renders
    HTML, or returns identity/session information;
  * committed DATA files (JSON/YAML/SQL/fixtures) — a leak lives in the VALUES, not only in code.
    Absolute filesystem paths, hostnames, tokens, emails, internal IDs shipped in a committed
    payload are real disclosures. Read the values, not just the keys;
  * anything under a CI/workflow/deploy/hook path — those run with credentials.
Repeated misses: this pass declared "no security-relevant surface" on a diff that changed a PII
allowlist plus a quota gate, and on one that committed a maintainer's home-directory path into a
published JSON index. Both were real. Config/JSON/build-output is NOT automatically safe.
SECURITY_FINDINGS: (none — no security-relevant surface in diff)
SECURITY_TRIAGE: clean — no security-relevant code
Otherwise, produce the sections below.

SECURITY_FINDINGS:
<numbered list. each: [Critical|High|Medium|Low] file:line — issue <=15 words | fix <=12 words.
Focus: auth bypass, missing access control, reentrancy, integer overflow/underflow, signature replay,
EIP-712/EIP-191 misuse, unvalidated input from untrusted sources, hardcoded secrets/keys,
insecure randomness, payment/token flow correctness (fund-at-risk), permission escalation,
cross-contract call reentrancy, missing chainId/payer in nonce keys, approval/allowance races.
Only real issues provable from the diff. Empty list OK if none.>

EVIDENCE RULE (HARD): Every finding MUST cite the exact diff line numbers that prove it.
Counter-evidence check: scan the ENTIRE diff for code that already handles the issue. If handled, omit.

INPUT-CONTROLLABILITY RULE (HARD): before flagging SSRF/injection/untrusted-input, confirm the value
is request/attacker-controllable. A value settable ONLY via env var, deploy config, or server-side
constant is NOT attacker-controllable — do NOT flag it. (This is the #1 R1b false-positive class.)

SECURITY_TRIAGE: clean|low|medium|high|critical — <reason <=10 words>

PR: {repo}#{pr}
DIFF:
{diff}
"""

PROMPT = """You are R1 of a multi-round PK code review. From the diff below, output EXACTLY these
sections and NOTHING else (no prose, no preamble). Be terse.

FILES:
<one line per changed file: path — what changed in <=10 words>

FINDINGS:
<numbered list. each: [Critical|High|Medium|Low] file:line — issue <=15 words | fix <=12 words.
Only real, concrete issues introduced by THIS diff. Empty list OK if none.>

Two rules that decide whether a finding is worth reporting. Roughly 40% of this pass's findings
have been rejected downstream for violating one of them:

1. PROVE IT FROM THE PASTED CODE. Report only what the diff itself demonstrates. Do not infer a
   bug from a familiar-looking pattern ("this resembles session fixation", "this looks like a
   migration") without a line that shows it. If you cannot point at the line that makes it true,
   drop it. An empty FINDINGS list is a good answer; a plausible-sounding wrong one costs three
   later rounds to disprove.

2. CHANGED LINES ONLY — distinguish them from unchanged context. A convention the repository
   already used, appearing in a context line, was NOT introduced by this PR. Before reporting,
   ask: is this line prefixed `+`? If it is untouched context, it is out of scope, unless the
   diff's own change makes it newly wrong (say so explicitly if you claim that).

EVIDENCE RULE (HARD): Every finding MUST cite the exact diff line numbers that prove it.
If you cannot point to a specific line in the diff, do NOT list the finding.
Do NOT flag issues based on what a file might look like — only what the diff shows.
Example of valid: "[High] src/foo.ts:142 — nonce key missing payer address | include `from` in key"
Example of INVALID: "[Medium] contracts/Foo.sol:1 — missing SPDX header" (unless you see the file header in diff and it is absent)

COUNTER-EVIDENCE CHECK (HARD — run before every finding):
Before reporting ANY issue, scan the ENTIRE diff for code that already handles it.
If you find any of the following, do NOT report the finding:
- "missing retry logic" → search for: loop, attempt, retry, for i in, while attempts
- "missing validation / bounds check" → search for: if len, if n !=, .len() <, checked_, ok_or
- "missing error handling" → search for: is_err(), is_ok(), match.*Err, if let Err, unwrap_or
- "undocumented behavior" → search for: comments (//), doc comments (///), or TODO near the code
- "hardcoded value is wrong" → search for: a comment explaining WHY it is hardcoded
If the fix already exists elsewhere in the diff, the finding is a FALSE POSITIVE — omit it.

RUST SAFE PATTERNS (do NOT flag these as dangerous):
- `.is_err()` / `.is_ok()` — returns bool, NEVER panics. Do NOT flag as "may panic".
- `.unwrap_or(x)` / `.unwrap_or_else(|_| x)` — safe fallback, not a panic risk.
- Only flag `.unwrap()` / `.expect()` / `panic!()` / `unreachable!()` as panic risks.
- `Result<T,E>` propagated with `?` — safe, not a panic.

DEDUPLICATION RULE (HARD): If the same issue pattern (same root cause) appears at multiple
callsites, report it EXACTLY ONCE using the first occurrence. Do NOT repeat the same finding
for every callsite. Example: if `ensure_not_frozen` is called before auth at lines 351, 360,
369 — report it once at line 351 only. A single finding with "appears at N callsites" is fine.

INTENTIONAL DESIGN RULE: If a constant, hardcoded value, or non-obvious pattern has a
comment (// or ///) explaining why it is intentional, do NOT flag it as a bug.
You may list it as [Low] with "consider making configurable" only if the comment does NOT
already address that concern.

FRAMEWORK GUARDS (check before flagging):
- Cloudflare Workers: bindings validated at deploy time, not runtime. Module-level state safe within one isolate (new deploy = new isolate). Do NOT flag "startup binding check" or "singleton stale state".
- OP-TEE single-instance TA: invocations are serialized (CFG_CONCURRENT_SINGLE_INSTANCE_TA=n). Do NOT flag TOCTOU on read-then-write within same TA session unless multi-instance is explicitly enabled.
- EIP-712 final digest: MUST use raw concat `\x19\x01 || domainSeparator || structHash`. Do NOT flag raw concat as wrong — encodeAbiParameters would pad to 32 bytes and break the digest.
- Solidity imports: before flagging a missing import/SPDX/pragma, verify the diff does NOT already contain it.

PAYMENT / NONCE SCOPE CHECK: For any code that constructs a nonce key or nonce store key,
verify the key includes ALL required namespace dimensions: chainId + payer address (from/sender) + nonce value.
A key of only `chainId:nonce` is a cross-payer nonce burning vulnerability.

INPUT-CONTROLLABILITY RULE (HARD — kills the recurring SSRF/injection false positives):
Before flagging SSRF / injection / "untrusted input", identify WHO controls the value. Only flag if
it is request/attacker-controllable (query param, request body, header, uploaded file, a URL the
user picks). A value that can ONLY be set via environment variable, build/deploy config, or a
server-side constant is NOT attacker-controllable — do NOT flag it as SSRF/injection.

CONFIG-DEFAULT RULE: Do NOT flag a config value or default as "wrong/insecure" unless the diff
ITSELF proves it wrong. If the justification would live in surrounding code/docs the diff does not
include, emit "[Low] needs-context: <value> — verify default" instead of asserting a bug.

TRIAGE: <trivial|significant> — <reason <=15 words>
(trivial = docs/chore/deps/license/format with no core-logic/security change;
 significant = feat / core logic / security-sensitive / API / migration / state)

SKELETON:
<a 4-line draft review comment the senior reviewer can refine>

PR: {repo}#{pr}
DIFF:
{diff}
"""


def load_key():
    import os
    k = os.environ.get("DEEPSEEK_API_KEY", "")
    if k.startswith("sk-"):
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v.startswith("sk-"):
                    return v
    return ""


# A finding line as the model actually emits it: an optional list number, then `[Sev]`.
# The previous version guarded on `stripped.startswith("[")` and therefore matched NOTHING —
# every real line looks like `1. [High] src/x.ts:12 — …`. Measured on CoLivingOS#74: 159 emitted
# lines, 0 matched, 0 removed. The `lstrip("0123456789. ")` two lines below shows numbering was
# always intended; the guard just never let a numbered line reach it.
_FINDING_RE = re.compile(r"^\s*(?:\d+[.)]\s*)?\[", re.ASCII)
# `SECURITY_FINDINGS:` does not start with `FINDINGS:`, so R1b was never deduped either.
_FINDINGS_HEADERS = ("FINDINGS:", "SECURITY_FINDINGS:")
_FINDINGS_ENDERS = ("TRIAGE:", "SECURITY_TRIAGE:", "SKELETON:", "FILES:")
# `[Sev] path/to/file.ts:123` — the location a finding is about.
_LOC_RE = re.compile(r"\[[^\]]*\]\s*([^\s—|]+)", re.ASCII)

# Past this many findings for ONE location, the model is looping rather than reporting.
_MAX_PER_LOCATION = 6
# Past this many findings total, treat the whole response as degenerate.
_DEGENERATE_TOTAL = 40


def _dedup_findings(content: str) -> str:
    """Collapse repeated FINDINGS / SECURITY_FINDINGS lines and flag degenerate output.

    Two failure modes are handled, both observed in production:
      1. byte-identical repeats — R1b emitted the same Low six times;
      2. a repetition LOOP that cycles 3-4 near-identical variants of one claim so no two lines
         are equal — R1a on CoLivingOS#74 emitted 159 lines that collapsed to 4 distinct claims,
         all on `statements.ts:214`.

    Only duplicates are dropped: every DISTINCT claim survives, so nothing a later round could
    have acted on is lost. When the output is degenerate the response is annotated rather than
    silently cleaned — a quietly-tidied loop would enter the flash performance record looking
    like a normal round, which is exactly the comparison that record exists to support. It is
    also NOT retried here: a silent retry would hide the datapoint and double the spend.
    """
    lines = content.splitlines(keepends=True)
    in_findings = False
    seen: set[str] = set()
    per_location: dict[str, int] = {}
    raw_findings = 0
    capped_locations: set[str] = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(_FINDINGS_HEADERS):
            in_findings = True
            out.append(line)
            continue
        if in_findings and stripped.startswith(_FINDINGS_ENDERS):
            in_findings = False
        if in_findings and _FINDING_RE.match(stripped):
            raw_findings += 1
            key = stripped.lstrip("0123456789.) ").lower()
            if key[:60] in seen:
                continue
            seen.add(key[:60])
            # Distinct text, same place: after a few, this is a loop, not a finding list.
            loc = _LOC_RE.search(key)
            loc_key = loc.group(1) if loc else ""
            if loc_key:
                per_location[loc_key] = per_location.get(loc_key, 0) + 1
                if per_location[loc_key] > _MAX_PER_LOCATION:
                    capped_locations.add(loc_key)
                    continue
        out.append(line)

    result = "".join(out)
    kept = raw_findings - (len(lines) - len(out))
    degenerate = raw_findings >= _DEGENERATE_TOTAL or bool(capped_locations)
    if raw_findings != kept:
        sys.stderr.write(
            f"[deepseek R1] post-process: {raw_findings} finding line(s) -> {kept} distinct\n"
        )
    if capped_locations:
        sys.stderr.write(
            f"[deepseek R1] post-process: capped at {_MAX_PER_LOCATION}/location for "
            f"{', '.join(sorted(capped_locations))}\n"
        )
    if degenerate:
        sys.stderr.write(
            f"[deepseek R1] ⚠️  DEGENERATE OUTPUT — {raw_findings} raw findings collapsed to "
            f"{kept}. Treat this round as a tool failure, not as signal, and say so in the "
            f"self-assessment / model_eval_db record.\n"
        )
        # Machine-readable for the caller, and visible to any model handed this file.
        result += (
            f"\n<!-- R1_DEGENERATE raw={raw_findings} distinct={kept} "
            f"locations={','.join(sorted(capped_locations)) or 'n/a'} -->\n"
            f"> ⚠️ NOTE: the model emitted {raw_findings} finding lines that collapse to {kept} "
            f"distinct claims — a repetition loop. The list above is the de-duplicated set. "
            f"Record this round as degenerate.\n"
        )
    return result


def main():
    args = sys.argv[1:]
    diff_file = args[args.index("--diff-file") + 1]
    repo = args[args.index("--repo") + 1] if "--repo" in args else "?"
    pr = args[args.index("--pr") + 1] if "--pr" in args else "?"
    output = args[args.index("--output") + 1] if "--output" in args else None
    mode = args[args.index("--mode") + 1] if "--mode" in args else "full"
    prior_file = args[args.index("--prior-review") + 1] if "--prior-review" in args else None
    # Assemble the prompt and print it instead of calling the API. Exists so prompt assembly
    # (especially the incremental block) is testable offline, without spend.
    print_prompt = "--print-prompt" in args

    key = load_key()
    if not key and not print_prompt:
        sys.stderr.write("❌ no DEEPSEEK_API_KEY\n")
        sys.exit(1)

    diff = Path(diff_file).read_text()
    template = SECURITY_PROMPT if mode == "security" else PROMPT
    prompt = template.format(repo=repo, pr=pr, diff=diff)

    if prior_file:
        prior = Path(prior_file).read_text().strip()
        if prior:
            # Prepended, not appended: the follow-up instructions must be read BEFORE the diff,
            # and a long diff would otherwise push them past the model's attention. The prior body
            # is capped because a verbose review can dwarf the diff it is about — the findings live
            # at the top of our review bodies, so a head-cut keeps what matters.
            if len(prior) > 12000:
                prior = prior[:12000] + "\n…(prior review truncated at 12k chars)…"
            prompt = PRIOR_REVIEW_BLOCK.format(prior=prior) + prompt
            sys.stderr.write(f"[deepseek R1] incremental mode: {len(prior)} chars of prior review\n")
        else:
            sys.stderr.write(f"⚠️  --prior-review {prior_file} is empty — running as a fresh review\n")

    if print_prompt:
        sys.stdout.write(prompt)
        return

    import os
    model = os.environ.get("PR_DAEMON_FIRST_PASS_MODEL") or "deepseek-v4-flash"
    thinking_disabled = os.environ.get("PR_DAEMON_FIRST_PASS_THINKING", "disabled") == "disabled"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        # Security findings are terse; cap tighter so a degenerate repetition loop
        # (e.g. flash on a no-security-surface docs diff) can't burn the whole budget.
        "max_tokens": 3000 if mode == "security" else 6000,
        "frequency_penalty": 0.6,
        "presence_penalty": 0.3,
    }
    if thinking_disabled:
        payload["thinking"] = {"type": "disabled"}
    body = json.dumps(payload).encode()

    t0 = time.time()
    req = Request("https://api.deepseek.com/chat/completions", data=body,
                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        resp = json.loads(urlopen(req, timeout=120).read())
    except (HTTPError, URLError) as e:
        sys.stderr.write(f"❌ DeepSeek error: {e}\n")
        sys.exit(1)

    content = resp["choices"][0]["message"]["content"]
    content = _dedup_findings(content)
    usage = resp.get("usage", {})
    dt = time.time() - t0

    if output:
        Path(output).write_text(content)
    print(content)
    label = "deepseek R1b(sec)" if mode == "security" else "deepseek R1a(full)"
    sys.stderr.write(
        f"[{label}] {usage.get('prompt_tokens',0)} in + {usage.get('completion_tokens',0)} out "
        f"= {usage.get('total_tokens',0)} tok, {dt:.1f}s\n"
    )


if __name__ == "__main__":
    main()
