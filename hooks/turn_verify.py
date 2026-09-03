#!/usr/bin/env python3
"""Stop hook: check what Claude claimed against what the transcript shows.

    python hooks/turn_verify.py                 # reads hook JSON on stdin
    python hooks/turn_verify.py --report-only   # never block, just report
    python hooks/turn_verify.py --self-test

THE IDEA

"Did Claude hallucinate" is not a checkable question. "Did Claude do what it
said it did" is, exactly and cheaply, because the Stop hook receives both halves:
`last_assistant_message` is the claim, and `transcript_path` is the record of
what actually ran. Comparing them catches most of what people mean by
hallucination without a model, without tokens, and without running your tests.

The highest-value check by a distance is a claimed verification that never
happened -- "I ran the tests and they pass" when no test command executed in
that turn. That single mismatch accounts for a large share of confidently wrong
turns, and it is a string comparison.

WHAT IT DOES NOT DO

It does not run your test suite. That is a separate hook with a separate cost,
and conflating them means one of the two gets disabled. This checks the honesty
of the turn, not the correctness of the code -- if you want correctness, add a
test-runner hook alongside it and let this one verify the claim that it ran.

It cannot tell you whether the change does what you meant. Nothing automated
can. That is what tests and review are for.

HARD versus SOFT

HARD findings are contradictions: the message asserts something the transcript
refutes. These block the stop (exit 2), so Claude is told and corrects in the
same turn. They are deliberately few and narrow, because a false block is far
worse than a missed catch.

SOFT findings are signals worth seeing but not worth interrupting for. They are
reported and the turn ends normally.

`stop_hook_active` is honoured: it blocks at most once per turn, then lets the
turn end regardless.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

# ---------------------------------------------------------------- claim patterns

CLAIM_TESTED = re.compile(
    r"\b(ran|running|executed|re-?ran)\b[^.\n]{0,40}\b(tests?|test\s+suite|specs?|"
    r"pytest|jest|vitest|go\s+test|cargo\s+test|unittest)\b"
    r"|\b(tests?|suite|specs?)\b[^.\n]{0,30}\b(pass(ed|ing)?|green|succeed)",
    re.I,
)
CLAIM_VERIFIED = re.compile(
    r"\b(verified|confirmed|validated|double-?checked|checked that|made sure)\b", re.I
)
# Deliberately permissive: anything test-shaped counts as "tests plausibly ran".
#
# The first version listed named runners (pytest, jest, npm test...) and
# immediately produced a false block on real usage: the response said "ran its
# self-test" while the command was `python hooks/turn_verify.py --self-test`,
# which matched no runner. A missed catch here costs a warning nobody sees; a
# false block interrupts correct work and gets the hook deleted. So this errs
# hard toward not blocking, and only fires when nothing test-shaped ran at all.
TEST_COMMAND = re.compile(
    r"test|spec|pytest|jest|vitest|mocha|tox|nose|rspec|phpunit|check|lint|verify",
    re.I,
)

# "I've updated `src/foo.py`" / "created hooks/bar.py" / "added the X to Y.ts"
CLAIM_EDIT = re.compile(
    r"\b(updated|created|added|modified|changed|fixed|wrote|edited|implemented|"
    r"removed|deleted|renamed|refactored)\b[^.\n]{0,60}?"
    r"[`\"']?\b([\w./\\-]+\.(?:py|pyi|ts|tsx|js|jsx|java|kt|go|rs|rb|php|cs|swift|"
    r"c|h|cpp|sql|json|ya?ml|toml|md|html|css|scss|sh|ps1|tf|proto))[`\"']?",
    re.I,
)

# Any file-ish token in prose, for existence checking.
FILE_TOKEN = re.compile(
    r"[`\"']?((?:[\w.-]+[/\\])*[\w.-]+\.(?:py|pyi|ts|tsx|js|jsx|java|kt|go|rs|rb|"
    r"php|cs|swift|c|h|cpp|sql|json|ya?ml|toml|md|html|css|scss|sh|ps1|tf|proto))[`\"']?"
)

PLACEHOLDER = re.compile(
    r"(#|//|/\*)\s*\.\.\.\s*(rest|remaining|other|unchanged|existing)"
    r"|\.\.\.\s*(rest|remainder)\s+of\s+(the\s+)?(code|file|function)"
    r"|\b(your|the)\s+(code|implementation)\s+here\b"
    r"|\bTODO:\s*implement\b"
    r"|\braise\s+NotImplementedError\b"
    r"|\bunchanged\s*\)\s*$",
    re.I | re.M,
)

PATH_ERROR = ("no such file", "does not exist", "cannot find", "enoent")
EDIT_ERROR = ("string to replace not found", "could not find the string", "no match found")

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


# ---------------------------------------------------------------- transcript

def read_turn(transcript_path: str) -> dict:
    """Records belonging to the current turn: everything after the last human prompt."""
    turn = {"tool_uses": [], "tool_errors": [], "bash_commands": []}
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return turn

    start = 0
    for i in range(len(lines) - 1, -1, -1):
        try:
            rec = json.loads(lines[i])
        except (json.JSONDecodeError, ValueError):
            continue
        if rec.get("type") == "user" and rec.get("promptSource") and not rec.get("toolUseResult"):
            start = i
            break

    for line in lines[start:]:
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue

        if rec.get("type") == "assistant":
            for block in (rec.get("message") or {}).get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                inp = block.get("input") or {}
                turn["tool_uses"].append({"name": name, "input": inp})
                if name in ("Bash", "PowerShell"):
                    turn["bash_commands"].append(str(inp.get("command", "")))

        elif rec.get("type") == "user" and rec.get("toolUseResult") is not None:
            result = rec["toolUseResult"]
            text = result if isinstance(result, str) else json.dumps(result)
            low = text.lower()
            if any(m in low for m in EDIT_ERROR):
                turn["tool_errors"].append(("edit_mismatch", text[:160]))
            elif any(m in low for m in PATH_ERROR):
                turn["tool_errors"].append(("invented_path", text[:160]))

    return turn


def edited_paths(turn: dict) -> list:
    out = []
    for use in turn["tool_uses"]:
        if use["name"] in EDIT_TOOLS:
            p = use["input"].get("file_path") or use["input"].get("notebook_path")
            if p:
                out.append(str(p))
    return out


# ---------------------------------------------------------------- checks

def verify(message: str, turn: dict, cwd: str) -> tuple:
    hard, soft = [], []
    edits = edited_paths(turn)
    ran_tests = any(TEST_COMMAND.search(c) for c in turn["bash_commands"])

    # 1. Claimed a test run that never happened. The single most valuable check.
    if CLAIM_TESTED.search(message) and not ran_tests:
        hard.append(
            "The response claims tests were run or are passing, but no test command "
            "was executed in this turn. Either run them now, or restate what was "
            "actually verified."
        )

    # 2. Claimed to verify, with no tool call at all to verify with.
    if (
        not hard
        and CLAIM_VERIFIED.search(message)
        and not turn["tool_uses"]
    ):
        hard.append(
            "The response claims something was verified or confirmed, but no tool "
            "ran in this turn, so nothing was actually checked."
        )

    # 3. Claimed to edit a file that no edit tool touched.
    claimed_files = {m.group(2) for m in CLAIM_EDIT.finditer(message)}
    edited_names = {os.path.basename(p) for p in edits}
    edited_norm = {p.replace("\\", "/") for p in edits}
    unbacked = [
        f for f in claimed_files
        if os.path.basename(f) not in edited_names
        and not any(f.replace("\\", "/") in e for e in edited_norm)
    ]
    if unbacked:
        hard.append(
            "The response claims changes to "
            + ", ".join(sorted(unbacked)[:4])
            + " but no edit tool touched "
            + ("them" if len(unbacked) > 1 else "it")
            + " in this turn."
        )

    # 4. A file named in prose that does not exist on disk.
    #
    # Two exclusions, both learned from false positives. A file an edit tool
    # just wrote is not missing -- if the tool had failed we would have a tool
    # error instead, and the path may be rooted somewhere this check cannot
    # resolve. And a file already reported by check 3 must not be reported
    # twice; one finding per problem.
    base = pathlib.Path(cwd or ".")
    skip = set(unbacked) | edited_names | {os.path.basename(p) for p in claimed_files}.intersection(edited_names)
    missing = []
    for m in FILE_TOKEN.finditer(message):
        rel = m.group(1)
        if rel in missing or len(missing) >= 4:
            continue
        if rel in skip or os.path.basename(rel) in edited_names:
            continue
        if not (base / rel).exists() and not pathlib.Path(rel).exists():
            if "/" in rel or "\\" in rel:  # bare names are too often generic
                missing.append(rel)
    if missing:
        soft.append("Referenced but not found on disk: " + ", ".join(missing))

    # 5. Placeholder or elided code left in a file this turn edited.
    stubs = []
    for path in dict.fromkeys(edits):
        try:
            body = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if PLACEHOLDER.search(body):
            stubs.append(os.path.basename(path))
    if stubs:
        hard.append(
            "Placeholder or elided code left in " + ", ".join(stubs[:4])
            + " -- the file contains an unimplemented stub or a '...rest unchanged' marker."
        )

    # 6. Tool errors during the turn. Signal, not contradiction.
    if turn["tool_errors"]:
        kinds = {}
        for kind, _ in turn["tool_errors"]:
            kinds[kind] = kinds.get(kind, 0) + 1
        soft.append(
            "Tool errors this turn: "
            + ", ".join(f"{v}x {k}" for k, v in sorted(kinds.items()))
        )

    return hard, soft


# ---------------------------------------------------------------- main

def main() -> int:
    report_only = "--report-only" in sys.argv
    if "--self-test" in sys.argv:
        return self_test()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    message = payload.get("last_assistant_message") or ""
    cwd = payload.get("cwd") or os.getcwd()
    turn = read_turn(payload.get("transcript_path") or "")

    hard, soft = verify(message, turn, cwd)

    if not hard and not soft:
        return 0

    label = "turn-verify: "
    if hard and not report_only and not payload.get("stop_hook_active"):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "continue": True,
                "stopReason": label + " ".join(hard),
            },
            "systemMessage": label + " ".join(hard + soft),
        }))
        return 2

    print(json.dumps({"systemMessage": label + " ".join(hard + soft)}))
    return 0


# ---------------------------------------------------------------- self-test

def _turn(tools=None, bash=None, errors=None):
    return {
        "tool_uses": tools or [],
        "bash_commands": bash or [],
        "tool_errors": errors or [],
    }


def _edit(path):
    return {"name": "Edit", "input": {"file_path": path}}


CASES = [
    (
        "claims tests pass, none ran",
        "I've fixed the bug and the tests now pass.",
        _turn(tools=[_edit("a.py")]),
        1, 0,
    ),
    (
        "claims tests pass, tests actually ran",
        "I've fixed the bug and the tests now pass.",
        _turn(tools=[_edit("a.py")], bash=["python -m pytest tests/"]),
        0, 0,
    ),
    (
        "claims verified with no tool calls at all",
        "I verified the configuration is correct.",
        _turn(),
        1, 0,
    ),
    (
        "claims an edit no tool made",
        "I've updated `src/auth.py` to validate the token.",
        _turn(tools=[_edit("src/other.py")]),
        1, 0,
    ),
    (
        "claims an edit that was made",
        "I've updated `src/auth.py` to validate the token.",
        _turn(tools=[_edit("src/auth.py")]),
        0, 0,
    ),
    (
        # Regression: this exact pair produced a false block on real usage.
        "self-test counts as a test run",
        "I added the hook and ran its self-test.",
        _turn(bash=["python hooks/turn_verify.py --self-test"]),
        0, 0,
    ),
    (
        "unconventional runner still counts",
        "Tests are passing now.",
        _turn(bash=["./scripts/run_integration_checks.sh"]),
        0, 0,
    ),
    (
        "tool errors reported softly",
        "Done.",
        _turn(errors=[("invented_path", "no such file")]),
        0, 1,
    ),
    (
        "clean turn stays silent",
        "Done - see the diff above.",
        _turn(tools=[_edit("a.py")], bash=["npm test"]),
        0, 0,
    ),
]


def self_test() -> int:
    failures = 0
    for why, message, turn, want_hard, want_soft in CASES:
        hard, soft = verify(message, turn, ".")
        ok = len(hard) == want_hard and len(soft) == want_soft
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} hard {len(hard)}/{want_hard}  "
              f"soft {len(soft)}/{want_soft}   {why}")
        for h in hard:
            print(f"       BLOCK {h[:88]}")
        for s in soft:
            print(f"       note  {s[:88]}")
    print(f"\n  {len(CASES) - failures}/{len(CASES)} cases passed\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
