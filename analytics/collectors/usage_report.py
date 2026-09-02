"""Token and cost report from local transcripts.

    python analytics/collectors/usage_report.py
    python analytics/collectors/usage_report.py --project costlens --json out.json
    python analytics/collectors/usage_report.py --prices analytics/metrics/prices.example.json

On pricing: this tool reports *tokens*, and applies a price table only if you
supply one with --prices. Rates change and differ by plan and tier, so a number
baked into a script here would be wrong within a quarter and wrong silently.
Token counts are the durable measurement; multiply them yourself against the
rate card you are actually on.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from transcript_reader import read_all, transcript_root  # noqa: E402


def _fmt(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def summarise(sessions):
    live = [s for s in sessions if s.api_calls]
    total = {
        "sessions": len(sessions),
        "sessions_with_activity": len(live),
        "prompts": sum(s.prompts for s in sessions),
        "api_calls": sum(s.api_calls for s in sessions),
        "tool_calls": sum(s.tool_calls for s in sessions),
        "input_tokens": sum(s.input_tokens for s in sessions),
        "output_tokens": sum(s.output_tokens for s in sessions),
        "thinking_tokens": sum(s.thinking_tokens for s in sessions),
        "cache_read_tokens": sum(s.cache_read_tokens for s in sessions),
        "cache_write_tokens": sum(s.cache_write_tokens for s in sessions),
    }
    total["total_input_tokens"] = (
        total["input_tokens"] + total["cache_read_tokens"] + total["cache_write_tokens"]
    )
    total["api_calls_per_prompt"] = round(total["api_calls"] / total["prompts"], 1) if total["prompts"] else 0
    total["tool_calls_per_prompt"] = round(total["tool_calls"] / total["prompts"], 1) if total["prompts"] else 0
    total["cache_ratio"] = (
        round(total["cache_read_tokens"] / total["cache_write_tokens"], 1)
        if total["cache_write_tokens"]
        else 0
    )
    total["mean_context_per_call"] = (
        round(total["total_input_tokens"] / total["api_calls"]) if total["api_calls"] else 0
    )

    tools: dict[str, int] = {}
    for s in sessions:
        for name, count in s.tool_use.items():
            tools[name] = tools.get(name, 0) + count
    total["tool_use"] = dict(sorted(tools.items(), key=lambda kv: -kv[1]))

    dated = [s for s in sessions if s.started]
    if dated:
        total["oldest_transcript"] = min(s.started for s in dated).isoformat()
        total["newest_transcript"] = max(s.ended or s.started for s in dated).isoformat()
    return total


def price(total: dict, table: dict) -> dict:
    """Apply a user-supplied price table. Keys are USD per million tokens."""
    out = {}
    for key, rate_key in (
        ("input_tokens", "input"),
        ("output_tokens", "output"),
        ("cache_read_tokens", "cache_read"),
        ("cache_write_tokens", "cache_write"),
    ):
        rate = table.get(rate_key)
        if rate is not None:
            out[rate_key] = round(total[key] / 1_000_000 * float(rate), 2)
    out["total"] = round(sum(out.values()), 2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="substring filter on the project directory name")
    ap.add_argument("--limit", type=int, help="only the N most recent sessions")
    ap.add_argument("--json", metavar="PATH", help="write the full report as JSON")
    ap.add_argument("--prices", metavar="PATH", help="JSON price table, USD per million tokens")
    args = ap.parse_args()

    root = transcript_root()
    if not root.is_dir():
        print(f"No transcripts found at {root}", file=sys.stderr)
        print("Claude Code has not run on this machine, or CLAUDE_CONFIG_DIR points elsewhere.", file=sys.stderr)
        return 2

    sessions = read_all(project=args.project, limit=args.limit)
    if not sessions:
        print(f"No sessions matched under {root}", file=sys.stderr)
        return 2

    total = summarise(sessions)

    print(f"\n  Transcripts: {root}")
    print(f"  {total['sessions']} sessions, {total['sessions_with_activity']} with activity", end="")
    if total.get("oldest_transcript"):
        print(f", {total['oldest_transcript'][:10]} to {total['newest_transcript'][:10]}")
    else:
        print()

    print("\n  PER SESSION (most recent first)\n")
    head = f"  {'session':<10}{'start':<12}{'mins':>8}{'prompts':>9}{'api':>6}{'tools':>7}{'out':>9}{'ctx/call':>10}"
    print(head)
    print("  " + "-" * (len(head) - 2))
    for s in sessions:
        if not s.api_calls:
            continue
        start = s.started.strftime("%Y-%m-%d") if s.started else "-"
        print(
            f"  {s.session_id[:8]:<10}{start:<12}{s.duration_minutes:>8}"
            f"{s.prompts:>9}{s.api_calls:>6}{s.tool_calls:>7}"
            f"{_fmt(s.output_tokens):>9}{_fmt(s.mean_context_per_call):>10}"
        )

    print("\n  TOTALS\n")
    rows = [
        ("Prompts", f"{total['prompts']:,}"),
        ("API calls", f"{total['api_calls']:,}  ({total['api_calls_per_prompt']} per prompt)"),
        ("Tool calls", f"{total['tool_calls']:,}  ({total['tool_calls_per_prompt']} per prompt)"),
        ("Output tokens", _fmt(total["output_tokens"])),
        ("  of which thinking", _fmt(total["thinking_tokens"])),
        ("Uncached input", _fmt(total["input_tokens"])),
        ("Cache read", _fmt(total["cache_read_tokens"])),
        ("Cache write", _fmt(total["cache_write_tokens"])),
        ("Cache read:write", f"{total['cache_ratio']}:1"),
        ("Mean context per call", _fmt(total["mean_context_per_call"])),
    ]
    for label, value in rows:
        print(f"  {label:<24}{value}")

    if total["tool_use"]:
        print("\n  TOOL MIX\n")
        for name, count in list(total["tool_use"].items())[:12]:
            share = count / total["tool_calls"] * 100 if total["tool_calls"] else 0
            bar = "#" * int(share / 2)
            print(f"  {name:<20}{count:>6}  {share:>5.1f}%  {bar}")

    print("\n  READING\n")
    print("  Mean context per call is the number to watch. It is what you re-send")
    print("  on every turn, it only grows within a session, and in a cached agentic")
    print("  workflow it usually dominates the bill -- output tokens rarely do.")
    if total["cache_ratio"] and total["cache_ratio"] < 5:
        print(f"\n  Cache read:write is {total['cache_ratio']}:1, which is low. Sessions are being")
        print("  restarted or invalidated often enough that the cache is not paying off.")

    if args.prices:
        table = json.loads(pathlib.Path(args.prices).read_text(encoding="utf-8"))
        costed = price(total, table)
        print("\n  COST (from your price table -- verify against your own rate card)\n")
        for key, value in costed.items():
            print(f"  {key:<24}${value:,.2f}")
        total["cost"] = costed

    if args.json:
        payload = {
            "transcript_root": str(root),
            "totals": total,
            "sessions": [
                {
                    "session_id": s.session_id,
                    "project": s.project,
                    "started": s.started.isoformat() if s.started else None,
                    "duration_minutes": s.duration_minutes,
                    "prompts": s.prompts,
                    "api_calls": s.api_calls,
                    "tool_calls": s.tool_calls,
                    "output_tokens": s.output_tokens,
                    "thinking_tokens": s.thinking_tokens,
                    "cache_read_tokens": s.cache_read_tokens,
                    "cache_write_tokens": s.cache_write_tokens,
                    "mean_context_per_call": s.mean_context_per_call,
                    "models": sorted(s.models),
                }
                for s in sessions
            ],
        }
        pathlib.Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\n  Wrote {args.json}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
