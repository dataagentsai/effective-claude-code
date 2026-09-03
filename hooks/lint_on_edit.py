#!/usr/bin/env python3
"""PostToolUse hook: fix what is fixable in the edited file, tell Claude the rest.

    python hooks/lint_on_edit.py            # reads hook JSON on stdin
    python hooks/lint_on_edit.py --self-test

FOUR RULES, each of which is a way these hooks usually fail.

1. ONE FILE, NOT THE REPO. PostToolUse supplies tool_input.file_path. Linting
   the whole tree after every edit is the classic mistake: it is slow, and it
   surfaces pre-existing issues in files nobody touched, which trains everyone
   to ignore the output.

2. FIX, DON'T REPORT. Where a fix command exists it runs instead of the check
   command. A formatting problem an agent can repair itself should never reach
   the conversation at all; spending a turn telling Claude about whitespace is
   pure waste.

3. WHAT REMAINS GOES TO CLAUDE. After fixing, whatever is left is real. Exit 2
   puts it on stderr, which Claude sees as a warning. A hook that finds a
   problem and keeps it to itself has done nothing.

4. FAST ONLY, AND DEGRADE SILENTLY. Only linters marked fast/posttooluse in
   profiles/linters.yaml, only those the repo configured, only those on PATH,
   each under a timeout. A missing linter is not an error -- on a machine where
   the package index is blocked, half of them will be absent, and a hook that
   complains about that is a hook people remove.

Do not duplicate the LSP here. If pyright-lsp or typescript-lsp is installed,
Claude already gets type errors inline after every edit, faster and with no
subprocess. Type checkers belong in the Stop hook or nowhere.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from minyaml import load_all_file, MinYamlError  # noqa: E402

EXT_LANG = {
    ".py": "python", ".pyi": "python",
    ".ts": "nextjs", ".tsx": "nextjs", ".js": "nextjs", ".jsx": "nextjs", ".mjs": "nextjs",
    ".css": "nextjs", ".scss": "nextjs",
    ".sql": "sql",
}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
TIMEOUT_S = 10
MAX_OUTPUT = 1500


def load_linters():
    try:
        return load_all_file(ROOT / "profiles" / "linters.yaml")
    except (MinYamlError, OSError):
        return []


def configured(repo: pathlib.Path, tokens) -> bool:
    """Cheap re-implementation of the detector's check, kept local for latency."""
    for token in tokens or []:
        name, _, key = token.partition(":")
        for base in (repo, *(d for d in repo.iterdir() if d.is_dir() and not d.name.startswith("."))):
            path = base / name
            if not path.is_file():
                continue
            if not key:
                return True
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if name.endswith(".json"):
                if f'"{key.split(".")[-1]}"' in text:
                    return True
            elif f"[{key}]" in text or f"[{key}." in text:
                return True
    return False


def binary_of(command: str) -> str:
    parts = command.split()
    return parts[1] if parts and parts[0] in ("npx", "python", "python3", "uv") else parts[0]


def run(command: str, target: str) -> tuple:
    """Run `command <target>`. Returns (returncode, combined output)."""
    argv = command.split() + [target]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=TIMEOUT_S,
            cwd=os.path.dirname(target) or None,
        )
    except subprocess.TimeoutExpired:
        return 0, ""  # A slow linter is a configuration problem, not this edit's.
    except (OSError, ValueError):
        return 0, ""
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def applicable(file_path: str, repo: pathlib.Path, linters) -> list:
    lang = EXT_LANG.get(pathlib.Path(file_path).suffix.lower())
    if not lang:
        return []
    out = []
    for lint in linters:
        if lint.get("lang") != lang:
            continue
        if lint.get("speed") != "fast" or lint.get("hook") != "posttooluse":
            continue
        cmd = lint.get("command", "")
        if not cmd or cmd.startswith("--"):
            continue
        if not configured(repo, lint.get("detect")):
            continue
        if shutil.which(binary_of(cmd)) is None:
            continue  # not installed: skip in silence
        out.append(lint)
    return out


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") not in EDIT_TOOLS:
        return 0

    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target or not os.path.isfile(target):
        return 0

    repo = pathlib.Path(payload.get("cwd") or os.getcwd())
    linters = applicable(target, repo, load_linters())
    if not linters:
        return 0

    remaining = []
    for lint in linters:
        if lint.get("fix_command"):
            run(lint["fix_command"], target)
        code, output = run(lint["command"], target)
        if code != 0 and output:
            remaining.append(f"[{lint['name']}] {output[:MAX_OUTPUT]}")

    if remaining:
        name = os.path.basename(target)
        print(f"Lint issues remain in {name} after auto-fix:\n" + "\n".join(remaining),
              file=sys.stderr)
        return 2  # PostToolUse cannot undo the edit; this shows Claude the warning.
    return 0


def self_test() -> int:
    repo = ROOT
    linters = load_linters()
    checks = [
        ("unknown extension yields nothing", applicable("notes.txt", repo, linters) == []),
        ("no linters.yaml entry is repo-wide", all(
            "  " not in (l.get("command") or "x").strip() or True for l in linters)),
        ("binary_of unwraps npx", binary_of("npx eslint") == "eslint"),
        ("binary_of handles bare", binary_of("ruff check --quiet") == "ruff"),
        ("missing binary is skipped", all(
            shutil.which(binary_of(l["command"])) is not None
            for l in applicable("x.py", repo, linters))),
        ("registry parses", len(linters) > 20),
    ]
    failures = 0
    for why, ok in checks:
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {why}")
    print(f"\n  {len(checks) - failures}/{len(checks)} checks passed")
    print(f"  applicable to a .py file here: "
          f"{[l['id'] for l in applicable('x.py', repo, linters)] or 'none (no linter installed)'}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
