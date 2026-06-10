#!/usr/bin/env python3
"""
compress_diff.py — shrink a large PR diff to fit a token budget.

Distilled from pr-agent's algo/pr_processing.py compression strategy:
  1. Drop non-reviewable files (binary/lock/generated) via config/review_ignore.txt
  2. Rank remaining files: real code > config > docs/data
  3. When over the token budget, keep high-priority files in full, replace
     low-priority files with a one-line summary, and list omitted files.

Usage:
  gh pr diff N --repo OWNER/REPO | python3 scripts/compress_diff.py --budget 80000
  python3 scripts/compress_diff.py --file /tmp/pr.diff --budget 80000 --stats
"""

import sys, os, re, fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE_FILE = ROOT / "config" / "review_ignore.txt"
TOKENIZER_DIR = ROOT / "deepseek_v3_tokenizer"

# File-priority signals (higher = keep first when budgeting)
HIGH_PRIORITY_DIRS = ("src/", "contracts/", "lib/", "packages/", "app/", "server/", "workers/")
HIGH_PRIORITY_EXT = (".sol", ".rs", ".ts", ".tsx", ".js", ".py", ".go", ".java", ".c", ".cpp", ".sh")
LOW_PRIORITY_EXT = (".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv", ".lock")


def load_ignore_globs():
    globs = []
    if IGNORE_FILE.exists():
        for line in IGNORE_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                globs.append(line)
    return globs


def count_tokens(text):
    """Token count via local DeepSeek tokenizer, fallback to char/3."""
    try:
        import transformers
        tok = transformers.AutoTokenizer.from_pretrained(str(TOKENIZER_DIR), trust_remote_code=True)
        return len(tok.encode(text))
    except Exception:
        return len(text) // 3


def split_into_files(diff_text):
    """Split a unified diff into per-file blocks. Returns [(path, block), ...]."""
    files = []
    current_path = None
    current_lines = []
    for line in diff_text.splitlines(keepends=True):
        m = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
        if m:
            if current_path is not None:
                files.append((current_path, "".join(current_lines)))
            current_path = m.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_path is not None:
        files.append((current_path, "".join(current_lines)))
    return files


def is_ignored(path, globs):
    base = os.path.basename(path)
    for g in globs:
        if g.startswith("*."):
            if base.endswith(g[1:]):
                return True
        elif fnmatch.fnmatch(path, g) or fnmatch.fnmatch(base, g):
            return True
    return False


def priority(path):
    """Higher = more important to keep in full."""
    p = path.lower()
    if any(p.startswith(d) or f"/{d}" in p for d in HIGH_PRIORITY_DIRS) and any(p.endswith(e) for e in HIGH_PRIORITY_EXT):
        return 3
    if any(p.endswith(e) for e in HIGH_PRIORITY_EXT):
        return 2
    if any(p.endswith(e) for e in LOW_PRIORITY_EXT):
        return 1
    return 2  # unknown code-ish → medium


def summarize_block(path, block):
    """One-line summary for an omitted/low-priority file."""
    added = sum(1 for l in block.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in block.splitlines() if l.startswith("-") and not l.startswith("---"))
    return f"## File: {path}  (+{added} -{removed}, body omitted for token budget)\n"


def compress(diff_text, budget):
    globs = load_ignore_globs()
    files = split_into_files(diff_text)

    kept_full, dropped_ignored, summarized = [], [], []

    # 1. drop ignored files
    candidates = []
    for path, block in files:
        if is_ignored(path, globs):
            dropped_ignored.append(path)
        else:
            candidates.append((path, block))

    # 2. rank by priority (desc), then size (asc — cheap wins first)
    ranked = sorted(candidates, key=lambda pb: (-priority(pb[0]), count_tokens(pb[1])))

    # 3. fill budget
    used = 0
    for path, block in ranked:
        t = count_tokens(block)
        if used + t <= budget:
            kept_full.append((path, block))
            used += t
        else:
            summarized.append((path, block))

    # assemble output
    out = []
    # keep original file order for readability
    order = {path: i for i, (path, _) in enumerate(files)}
    kept_full.sort(key=lambda pb: order[pb[0]])
    for path, block in kept_full:
        out.append(block)
    if summarized:
        out.append("\n" + "=" * 60 + "\n")
        out.append("# Files summarized (insufficient token budget for full diff):\n")
        for path, block in sorted(summarized, key=lambda pb: order[pb[0]]):
            out.append(summarize_block(path, block))
    if dropped_ignored:
        out.append("\n# Files skipped (binary/lock/generated):\n")
        out.append("# " + ", ".join(dropped_ignored) + "\n")

    stats = {
        "total_files": len(files),
        "kept_full": len(kept_full),
        "summarized": len(summarized),
        "dropped_ignored": len(dropped_ignored),
        "tokens_used": used,
        "budget": budget,
    }
    return "".join(out), stats


def main():
    args = sys.argv[1:]
    budget = 80000
    stats_mode = "--stats" in args
    diff_text = ""

    if "--budget" in args:
        i = args.index("--budget")
        if i + 1 < len(args):
            budget = int(args[i + 1])
    if "--file" in args:
        i = args.index("--file")
        diff_text = Path(args[i + 1]).read_text()
    else:
        diff_text = sys.stdin.read()

    compressed, stats = compress(diff_text, budget)

    if stats_mode:
        sys.stderr.write(
            f"[compress_diff] {stats['total_files']} files → "
            f"{stats['kept_full']} full, {stats['summarized']} summarized, "
            f"{stats['dropped_ignored']} skipped | {stats['tokens_used']}/{stats['budget']} tokens\n"
        )
    print(compressed)


if __name__ == "__main__":
    main()
