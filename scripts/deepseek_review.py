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

import sys, json, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent

PROMPT = """You are R1 of a multi-round PK code review. From the diff below, output EXACTLY these
sections and NOTHING else (no prose, no preamble). Be terse.

FILES:
<one line per changed file: path — what changed in <=10 words>

FINDINGS:
<numbered list. each: [Critical|High|Medium|Low] file:line — issue <=15 words | fix <=12 words.
Only real, concrete issues introduced by THIS diff. Empty list OK if none.>

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


def main():
    args = sys.argv[1:]
    diff_file = args[args.index("--diff-file") + 1]
    repo = args[args.index("--repo") + 1] if "--repo" in args else "?"
    pr = args[args.index("--pr") + 1] if "--pr" in args else "?"
    output = args[args.index("--output") + 1] if "--output" in args else None

    key = load_key()
    if not key:
        sys.stderr.write("❌ no DEEPSEEK_API_KEY\n")
        sys.exit(1)

    diff = Path(diff_file).read_text()
    prompt = PROMPT.format(repo=repo, pr=pr, diff=diff)

    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2000,
    }).encode()

    t0 = time.time()
    req = Request("https://api.deepseek.com/chat/completions", data=body,
                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        resp = json.loads(urlopen(req, timeout=120).read())
    except (HTTPError, URLError) as e:
        sys.stderr.write(f"❌ DeepSeek error: {e}\n")
        sys.exit(1)

    content = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    dt = time.time() - t0

    if output:
        Path(output).write_text(content)
    print(content)
    sys.stderr.write(
        f"[deepseek R1] {usage.get('prompt_tokens',0)} in + {usage.get('completion_tokens',0)} out "
        f"= {usage.get('total_tokens',0)} tok, {dt:.1f}s\n"
    )


if __name__ == "__main__":
    main()
