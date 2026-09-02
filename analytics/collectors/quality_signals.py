"""Hallucination-proxy signals from local transcripts.

    python analytics/collectors/quality_signals.py
    python analytics/collectors/quality_signals.py --project sentinel --json out.json

READ THIS FIRST.

Nothing in a transcript records whether the model was right. There is no
ground-truth signal to collect, and any tool claiming to measure hallucination
rate from logs alone is measuring something else and calling it that.

What this collects instead is a set of *proxies* -- events that are more common
when the model is fabricating than when it is not:

  invented_path      A Read/Edit/Glob referenced a file that does not exist.
                     The strongest single signal: the model produced a path from
                     pattern rather than from having looked.

  edit_mismatch      An Edit's old_string did not match the file. The model
                     reconstructed code it had not accurately retained.

  refusal            stop_reason came back as refusal.

  correction_turn    The user's next message rejects what just happened
                     ("no", "that's wrong", "I didn't ask"). Lagging, noisy, and
                     the closest thing to a human label available for free.

  rework_loop        The same file was read again immediately after being
                     edited -- consistent with the model not trusting its own
                     edit, though also with ordinary verification.

Each is individually explainable by innocent causes. A single elevated session
means nothing. The index is only useful as a trend across many sessions, and a
rise is a prompt to go and read some transcripts -- not a measurement.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from transcript_reader import find_sessions, transcript_root  # noqa: E402

PATH_MARKERS = (
    "no such file",
    "file does not exist",
    "does not exist",
    "cannot find",
    "enoent",
)
EDIT_MARKERS = (
    "string to replace not found",
    "could not find the string",
    "no match found",
    "old_string not found",
)
READ_FIRST_MARKERS = ("has not been read yet", "must read the file first")

CORRECTION = re.compile(
    r"^\s*(no[,.\s!]|nope|wrong|that'?s not|not what i|incorrect|you (?:mis|got it wrong)"
    r"|don'?t do that|revert|undo that|i didn'?t ask|stop[,.\s!])",
    re.IGNORECASE,
)


def _text_of(message) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _result_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts = [
            str(result.get(k, ""))
            for k in ("content", "error", "stderr", "message")
            if result.get(k)
        ]
        return " ".join(parts)
    return ""


def scan(path: pathlib.Path) -> dict:
    counts = {
        "invented_path": 0,
        "edit_mismatch": 0,
        "unread_edit": 0,
        "refusal": 0,
        "correction_turn": 0,
        "rework_loop": 0,
    }
    examples: list[dict] = []
    api_calls = 0
    prompts = 0
    edits = 0
    last_assistant_was_edit_of: str | None = None
    prev_was_assistant = False

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue

            rtype = rec.get("type")

            if rtype == "assistant":
                api_calls += 1
                msg = rec.get("message") or {}
                if msg.get("stop_reason") == "refusal":
                    counts["refusal"] += 1
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name")
                        if name in ("Edit", "Write", "NotebookEdit"):
                            edits += 1
                            inp = block.get("input") or {}
                            last_assistant_was_edit_of = inp.get("file_path")
                        elif name == "Read" and last_assistant_was_edit_of:
                            inp = block.get("input") or {}
                            if inp.get("file_path") == last_assistant_was_edit_of:
                                counts["rework_loop"] += 1
                                last_assistant_was_edit_of = None
                prev_was_assistant = True
                continue

            if rtype != "user":
                continue

            result = rec.get("toolUseResult")
            if result is not None:
                text = _result_text(result).lower()
                hit = None
                if any(m in text for m in EDIT_MARKERS):
                    hit = "edit_mismatch"
                elif any(m in text for m in READ_FIRST_MARKERS):
                    hit = "unread_edit"
                elif any(m in text for m in PATH_MARKERS):
                    hit = "invented_path"
                if hit:
                    counts[hit] += 1
                    if len(examples) < 8:
                        examples.append({"signal": hit, "excerpt": _result_text(result)[:180]})
                continue

            if rec.get("promptSource"):
                prompts += 1
                if prev_was_assistant and CORRECTION.match(_text_of(rec.get("message") or {})):
                    counts["correction_turn"] += 1
                prev_was_assistant = False

    weighted = (
        counts["invented_path"] * 3
        + counts["edit_mismatch"] * 3
        + counts["unread_edit"] * 1
        + counts["refusal"] * 2
        + counts["correction_turn"] * 4
        + counts["rework_loop"] * 1
    )
    return {
        "session_id": path.stem,
        "project": path.parent.name,
        "api_calls": api_calls,
        "prompts": prompts,
        "edits": edits,
        "counts": counts,
        # Per 100 API calls, so sessions of different lengths compare.
        "index": round(weighted / api_calls * 100, 1) if api_calls else 0.0,
        "examples": examples,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="substring filter on the project directory name")
    ap.add_argument("--limit", type=int, help="only the N most recent sessions")
    ap.add_argument("--json", metavar="PATH", help="write the full report as JSON")
    args = ap.parse_args()

    paths = find_sessions(project=args.project)
    if args.limit:
        paths = paths[: args.limit]
    if not paths:
        print(f"No sessions matched under {transcript_root()}", file=sys.stderr)
        return 2

    reports = [scan(p) for p in paths]
    active = [r for r in reports if r["api_calls"]]

    agg = {k: sum(r["counts"][k] for r in reports) for k in reports[0]["counts"]}
    calls = sum(r["api_calls"] for r in reports)
    prompts = sum(r["prompts"] for r in reports)

    print("\n  HALLUCINATION-PROXY SIGNALS")
    print(f"  {len(active)} sessions with activity, {calls:,} API calls, {prompts:,} prompts\n")

    labels = {
        "invented_path": "Invented path (read/edit target absent)",
        "edit_mismatch": "Edit old_string did not match",
        "unread_edit": "Edit attempted before read",
        "refusal": "Refusal stop_reason",
        "correction_turn": "User corrected the previous turn",
        "rework_loop": "Re-read own edit immediately",
    }
    for key, label in labels.items():
        per100 = round(agg[key] / calls * 100, 2) if calls else 0
        print(f"  {label:<42}{agg[key]:>6}   {per100:>6.2f} /100 calls")

    print("\n  WORST SESSIONS BY INDEX\n")
    print(f"  {'session':<10}{'index':>8}{'calls':>8}{'path':>7}{'edit':>7}{'corr':>7}")
    print("  " + "-" * 45)
    for r in sorted(active, key=lambda r: -r["index"])[:10]:
        c = r["counts"]
        print(
            f"  {r['session_id'][:8]:<10}{r['index']:>8}{r['api_calls']:>8}"
            f"{c['invented_path']:>7}{c['edit_mismatch']:>7}{c['correction_turn']:>7}"
        )

    print("\n  These are proxies, not measurements. A high index says 'go read this")
    print("  session', not 'the model hallucinated N times'. Track the trend; a")
    print("  single session's number is noise.\n")

    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps({"totals": agg, "api_calls": calls, "sessions": reports}, indent=2),
            encoding="utf-8",
        )
        print(f"  Wrote {args.json}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
