#!/usr/bin/env python3
"""
DeepSeek API balance bridge — query real account balance and track usage.

Usage:
  python3 scripts/deepseek_balance.py              # one-shot query
  python3 scripts/deepseek_balance.py --watch      # refresh every 30 min (default)
  python3 scripts/deepseek_balance.py --watch 10   # refresh every 10 min
  python3 scripts/deepseek_balance.py --json       # machine-readable output
  python3 scripts/deepseek_balance.py --compact    # one-line summary

Requires: DEEPSEEK_API_KEY in .env or environment.
API docs: https://api-docs.deepseek.com
"""

import os, sys, json, time, signal
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".state" / "pr-daemon" / "deepseek_balance.json"
BALANCE_URL = "https://api.deepseek.com/user/balance"

# ── Load API key ──────────────────────────────────────────────────────────────

def load_api_key() -> str:
    """Load DEEPSEEK_API_KEY from environment or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key.strip('"').strip("'")
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and not val.startswith("sk-"):
                    continue
                return val
    return ""

# ── API call ──────────────────────────────────────────────────────────────────

def fetch_balance(api_key: str) -> dict:
    """Query DeepSeek balance API. Returns raw response dict."""
    req = Request(BALANCE_URL, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

# ── State tracking ────────────────────────────────────────────────────────────

def load_state() -> dict:
    """Load previous balance snapshot from state file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {}

def save_state(snapshot: dict) -> None:
    """Save balance snapshot to state file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")

# ── Display formatting ────────────────────────────────────────────────────────

def format_readable(data: dict, prev: dict) -> str:
    """Format balance info as human-readable JSON with clear labels."""
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    local_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extract balance info
    info = data.get("balance_infos", [])
    cny = next((b for b in info if b.get("currency") == "CNY"), {})
    usd = next((b for b in info if b.get("currency") == "USD"), {})

    result = {
        "meta": {
            "queried_at_utc":             now_str,
            "queried_at_local":           local_str,
            "api_available":              data.get("is_available", False),
        },
        "balance_cny": {
            "currency":                   "CNY (人民币)",
            "total_balance":              cny.get("total_balance", "0.00"),
            "topped_up_balance":          cny.get("topped_up_balance", "0.00"),
            "granted_balance":            cny.get("granted_balance", "0.00"),
            "note":                       "total = topped_up + granted",
        },
        "balance_usd": {
            "currency":                   "USD (美元)",
            "total_balance":              usd.get("total_balance", "0.00"),
            "topped_up_balance":          usd.get("topped_up_balance", "0.00"),
            "granted_balance":            usd.get("granted_balance", "0.00"),
            "note":                       "total = topped_up + granted",
        },
    }

    # Delta from previous snapshot
    if prev:
        prev_info = prev.get("balance_infos", [])
        prev_cny = next((b for b in prev_info if b.get("currency") == "CNY"), {})
        if prev_cny and cny:
            prev_total = float(prev_cny.get("total_balance", "0"))
            curr_total = float(cny.get("total_balance", "0"))
            spent = round(prev_total - curr_total, 4)
            result["usage_delta_cny"] = {
                "previous_total_balance":    prev_total,
                "current_total_balance":     curr_total,
                "spent_since_last_check":    spent,
                "note":                      "上一轮至今消耗 (CNY)",
            }
            if spent > 0:
                # Estimate USD equivalent (rough: 1 CNY ≈ 0.14 USD)
                result["usage_delta_cny"]["estimated_spent_usd"] = round(spent * 0.14, 6)
                result["usage_delta_cny"]["estimated_spent_usd_note"] = "CNY × 0.14 ≈ USD"

    return json.dumps(result, indent=2, ensure_ascii=False)


def format_compact(data: dict, prev: dict) -> str:
    """One-line compact summary."""
    info = data.get("balance_infos", [])
    cny = next((b for b in info if b.get("currency") == "CNY"), {})
    total = cny.get("total_balance", "0.00")

    parts = [f"💰 CNY {total} left"]

    if prev:
        prev_info = prev.get("balance_infos", [])
        prev_cny = next((b for b in prev_info if b.get("currency") == "CNY"), {})
        if prev_cny:
            spent = round(float(prev_cny.get("total_balance", "0")) - float(total), 4)
            if spent > 0:
                parts.append(f"(spent {spent} CNY ≈ ${round(spent*0.14,4)} USD since last check)")

    return "  ".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = load_api_key()
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not found. Set it in .env or environment.", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    watch_mode = "--watch" in args
    json_mode = "--json" in args
    compact_mode = "--compact" in args

    # Parse watch interval
    interval_min = 30  # default 30 minutes
    if watch_mode:
        try:
            idx = args.index("--watch")
            if idx + 1 < len(args) and args[idx + 1].isdigit():
                interval_min = int(args[idx + 1])
        except (ValueError, IndexError):
            pass

    prev = load_state()

    def do_query():
        try:
            data = fetch_balance(api_key)
        except HTTPError as e:
            print(f"❌ HTTP {e.code}: {e.reason}", file=sys.stderr)
            return
        except URLError as e:
            print(f"❌ Network error: {e.reason}", file=sys.stderr)
            return
        except Exception as e:
            print(f"❌ Unexpected: {e}", file=sys.stderr)
            return

        # Save current snapshot for next run's delta
        save_state(data)

        if compact_mode:
            print(format_compact(data, prev))
        elif json_mode:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(format_readable(data, prev))
            print()  # blank line separator

    do_query()

    if watch_mode:
        print(f"🔄 Refreshing every {interval_min} minutes. Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(interval_min * 60)
                prev = load_state()  # reload state each cycle for fresh delta
                do_query()
        except KeyboardInterrupt:
            print("\n👋 Stopped.")


if __name__ == "__main__":
    main()
