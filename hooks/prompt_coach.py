#!/usr/bin/env python3
"""UserPromptSubmit hook: flag a prompt likely to go wide, and offer plan mode.

    python hooks/prompt_coach.py            # reads hook JSON on stdin
    python hooks/prompt_coach.py --self-test

WHAT IT CANNOT DO. The UserPromptSubmit contract makes `user_input` read-only:
a hook may block a prompt, add context for Claude, or show the user a message.
It cannot rewrite the prompt. So this shows you a suggestion; it never silently
edits what you typed.

DESIGN CONSTRAINTS, all of which follow from "this runs on every single prompt":

  Deterministic only. No model call. An LLM in this hook would add latency and
  token cost to every prompt you ever type, to produce advice you can mostly
  derive from string inspection. That trade is not worth it.

  Silent by default. It speaks only when a signal actually trips, at most twice,
  and says nothing at all for continuations, slash commands and short replies.
  A hook that comments on every prompt gets disabled within a day, and then it
  protects nothing.

  Never blocks. Always exits 0. Blocking a prompt to complain about its wording
  would be an appalling trade; the worst case here is a line of text you ignore.

  Writes only `systemMessage`, which is shown to you and does not enter Claude's
  context. Injecting "the user was vague" via additionalContext would cost
  context tokens on every turn and steer the model on a heuristic's say-so.

WHAT IT CHECKS

  Wide scope     A broad verb with nothing concrete to anchor on. The docs are
                 explicit that "improve this codebase" triggers broad scanning
                 while a named function does not.
  Plan mode      Multi-file or architectural markers while not already in plan
                 mode. Plan mode is cheapest exactly when re-work would be
                 expensive.
  No target      A change request with no stated expected outcome. Verification
                 targets let Claude check itself before you have to.
  Context size   Reads the tail of the transcript for the last cache-read count.
                 A large context is re-sent on every subsequent turn.
"""

from __future__ import annotations

import json
import os
import re
import sys

MAX_SUGGESTIONS = 2

# Deliberately narrow. A false positive here is far more costly than a miss,
# because it trains you to ignore the hook.
BROAD_VERB = re.compile(
    r"\b(improve|clean\s?up|refactor|optimi[sz]e|tidy|modernis|moderniz|polish|"
    r"enhance|revamp|streamline|make\s+(it|this|the\s+code)\s+better|"
    r"look\s+(at|into|over))\b",
    re.I,
)

# Something concrete to work from: a path, a quoted symbol, or an error.
ANCHOR = re.compile(
    r"`[^`]+`"
    r"|\b[\w./\\-]+\.(py|pyi|ts|tsx|js|jsx|java|kt|go|rs|rb|php|cs|swift|c|h|cpp|"
    r"sql|json|ya?ml|toml|md|html|css|scss|sh|ps1|tf|proto)\b"
    r"|\b(error|exception|traceback|stack\s?trace|failed|failing|assertion)\b"
    r"|\b[\w]+\(\)"
    r"|\bline\s+\d+",
    re.I,
)

PLAN_MARKER = re.compile(
    r"\b(refactor|migrat|re-?design|re-?write|re-?structure|overhaul|architect|"
    r"port\s+to|upgrade\s+to|introduce|split\s+out|extract|consolidat|"
    r"across\s+(the|all)|every(where| file| module)|entire|whole\s+(codebase|repo|app)|"
    r"end.to.end|from\s+scratch)\b",
    re.I,
)

CHANGE_REQUEST = re.compile(
    r"\b(add|implement|create|build|write|change|update|fix|replace|remove|"
    r"delete|rename|wire|hook\s+up|support)\b",
    re.I,
)

VERIFY_TARGET = re.compile(
    r"\b(test|tests|expect|expected|should|verify|assert|acceptance|"
    r"so\s+that|such\s+that|output|returns?|screenshot|reproduce)\b",
    re.I,
)

# Continuations and acknowledgements. Never advise on these.
CONTINUATION = re.compile(
    r"^\s*(y(es|ep|eah)?|no(pe)?|ok(ay)?|sure|thanks?|ty|go\s?ahead|do\s+it|"
    r"proceed|continue|carry\s+on|next|again|retry|stop|wait|nice|good|"
    r"perfect|great|hmm+|k)\b[\s.!?]*$",
    re.I,
)

CONTEXT_WARN_TOKENS = 250_000


def tail_context_tokens(transcript_path: str) -> int:
    """Last reported cache-read count = roughly what is re-sent each turn.

    Reads only the tail of the file. The transcript can be tens of megabytes and
    this runs on every prompt, so a full parse is not acceptable.
    """
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as fh:
            fh.seek(max(0, size - 262_144))
            chunk = fh.read().decode("utf-8", errors="replace")
    except (OSError, TypeError):
        return 0

    for line in reversed(chunk.splitlines()):
        line = line.strip()
        if not line.startswith("{") or '"usage"' not in line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = ((rec.get("message") or {}).get("usage")) or {}
        total = (
            (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
            + (usage.get("input_tokens") or 0)
        )
        if total:
            return total
    return 0


def coach(prompt: str, permission_mode: str, context_tokens: int) -> list:
    words = prompt.split()

    if not prompt.strip() or prompt.lstrip().startswith("/"):
        return []
    # "improve this codebase" is three words and is the canonical bad prompt,
    # so the short-prompt guard has to stop below it, not at it. Two words or
    # fewer is a continuation in practice ("fix it", "again").
    if CONTINUATION.match(prompt) or len(words) < 3:
        return []

    out = []
    has_anchor = bool(ANCHOR.search(prompt))

    if BROAD_VERB.search(prompt) and not has_anchor:
        out.append(
            "Wide scope: a broad verb with no file, symbol or error to anchor on. "
            "Naming the target turns a repo-wide scan into a read of two files."
        )

    if PLAN_MARKER.search(prompt) and permission_mode != "plan":
        out.append(
            "Looks multi-file. Shift+Tab for plan mode first - it explores and "
            "proposes before editing, which is cheapest exactly when re-work would "
            "be expensive."
        )

    if (
        len(out) < MAX_SUGGESTIONS
        and CHANGE_REQUEST.search(prompt)
        and not VERIFY_TARGET.search(prompt)
        and len(words) >= 8
    ):
        out.append(
            "No verification target. Saying what success looks like lets Claude "
            "check its own work before you have to."
        )

    if len(out) < MAX_SUGGESTIONS and context_tokens >= CONTEXT_WARN_TOKENS:
        out.append(
            f"Context is ~{context_tokens // 1000}K tokens and is re-sent every "
            "turn. If this is unrelated to the last task, /clear first."
        )

    return out[:MAX_SUGGESTIONS]


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # Malformed input must never interfere with the prompt.

    notes = coach(
        payload.get("user_input") or "",
        payload.get("permission_mode") or "default",
        tail_context_tokens(payload.get("transcript_path") or ""),
    )

    if notes:
        print(json.dumps({"systemMessage": "prompt-coach: " + "  ".join(notes)}))
    return 0


CASES = [
    ("improve this codebase", "default", 0, 1, "wide scope, no anchor"),
    ("clean up the auth module", "default", 0, 1, "broad verb, no concrete anchor"),
    ("fix the TypeError in src/auth.py line 42", "default", 0, 0, "anchored, specific"),
    ("refactor the billing pipeline to use the new schema", "default", 0, 2, "plan + no target"),
    # Plan mode suppresses the plan nudge, not the scope note -- an unanchored
    # prompt is just as unanchored inside plan mode.
    ("refactor the billing pipeline", "plan", 0, 1, "plan nudge suppressed, scope note stands"),
    ("fix it", "default", 0, 0, "two words, treated as a continuation"),
    ("yes", "default", 0, 0, "continuation"),
    ("go ahead", "default", 0, 0, "continuation"),
    ("/audit-claude-setup", "default", 0, 0, "slash command"),
    ("add input validation to the login function in auth.ts", "default", 0, 1, "no verify target"),
    ("add a test asserting login rejects an empty password", "default", 0, 0, "has target"),
    ("what does this function do", "default", 300_000, 1, "context warning only"),
]


def self_test() -> int:
    failures = 0
    for prompt, mode, ctx, expect, why in CASES:
        got = coach(prompt, mode, ctx)
        ok = len(got) == expect
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} [{len(got)}/{expect}] {why}")
        print(f"       {prompt!r}")
        for note in got:
            print(f"       -> {note[:96]}")
    print(f"\n  {len(CASES) - failures}/{len(CASES)} cases passed\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
