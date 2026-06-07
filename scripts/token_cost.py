#!/usr/bin/env python3
"""Estimate DeepSeek API token cost using local V3 tokenizer (same vocab as V4)."""
import sys, os, json, subprocess
from pathlib import Path

TOKENIZER_DIR = str(Path(__file__).resolve().parent.parent / "deepseek_v3_tokenizer")

# DeepSeek V4 Pro pricing (per 1M tokens, from api-docs.deepseek.com/quick_start/pricing)
PRICING = {
    "input":         0.435,   # $/1M cache miss
    "input_cached":  0.003625, # $/1M cache hit
    "output":        0.87,     # $/1M
}

# Rough cache-hit estimate: ~30% of input tokens are cached (Claude Code prompt cache)
# This is a conservative estimate — actual hit rate varies
CACHE_HIT_RATE = 0.30


def count_tokens(text: str) -> int:
    """Count tokens using the local DeepSeek tokenizer."""
    try:
        import transformers
        tokenizer = transformers.AutoTokenizer.from_pretrained(
            TOKENIZER_DIR, trust_remote_code=True
        )
        return len(tokenizer.encode(text))
    except Exception:
        # Fallback: rough char/4 estimate for English, char/2 for CJK
        return len(text) // 3


def estimate_cost(input_tokens: int, output_tokens: int) -> dict:
    """Estimate cost in USD given token counts."""
    cached = int(input_tokens * CACHE_HIT_RATE)
    uncached = input_tokens - cached
    input_cost = (cached * PRICING["input_cached"] + uncached * PRICING["input"]) / 1_000_000
    output_cost = output_tokens * PRICING["output"] / 1_000_000
    total = input_cost + output_cost
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input": cached,
        "uncached_input": uncached,
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(total, 6),
    }


def format_cost(est: dict, label: str = "") -> str:
    """One-line cost summary."""
    total_tokens = est["input_tokens"] + est["output_tokens"]
    return (
        f"💰 {label} {total_tokens:,} tokens "
        f"(in: {est['input_tokens']:,} out: {est['output_tokens']:,}) "
        f"≈ ${est['total_cost']:.4f}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Read from stdin
        text = sys.stdin.read()
        tokens = count_tokens(text)
        est = estimate_cost(tokens, 0)
        print(format_cost(est, "stdin"))
    elif sys.argv[1] == "--text":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        tokens = count_tokens(text)
        est = estimate_cost(tokens, 0)
        print(format_cost(est, "input"))
    elif sys.argv[1] == "--file":
        path = sys.argv[2]
        text = open(path).read()
        tokens = count_tokens(text)
        est = estimate_cost(tokens, 0)
        print(format_cost(est, os.path.basename(path)))
    elif sys.argv[1] == "--manual":
        input_tokens = int(sys.argv[2])
        output_tokens = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        est = estimate_cost(input_tokens, output_tokens)
        print(format_cost(est, ""))
    elif sys.argv[1] == "--status":
        # Read cumulative.json if exists
        cum_path = Path(__file__).resolve().parent.parent / ".state" / "pr-daemon" / "token_cumulative.json"
        if cum_path.exists():
            data = json.loads(cum_path.read_text())
            total_in = data.get("total_input", 0)
            total_out = data.get("total_output", 0)
            est = estimate_cost(total_in, total_out)
            print(format_cost(est, "Cumulative"))
        else:
            print("💰 No cumulative data yet")
    elif sys.argv[1] == "--add":
        input_tokens = int(sys.argv[2])
        output_tokens = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        cum_path = Path(__file__).resolve().parent.parent / ".state" / "pr-daemon" / "token_cumulative.json"
        cum_path.parent.mkdir(parents=True, exist_ok=True)
        if cum_path.exists():
            data = json.loads(cum_path.read_text())
        else:
            data = {"total_input": 0, "total_output": 0, "reviews": 0}
        data["total_input"] += input_tokens
        data["total_output"] += output_tokens
        data["reviews"] += 1
        cum_path.write_text(json.dumps(data, indent=2))
        est = estimate_cost(data["total_input"], data["total_output"])
        print(format_cost(est, f"Cumulative ({data['reviews']} reviews)"))
    else:
        print("Usage: token_cost.py [--file PATH | --manual IN OUT | --status | --add IN OUT]")
