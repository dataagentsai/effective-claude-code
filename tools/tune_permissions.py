"""Analyse an accreted permission allowlist and propose a tiered replacement.

    python tools/tune_permissions.py
    python tools/tune_permissions.py --repo C:\\src\\thing --json perms.json

Reports duplicates, wildcard shadowing, foldable clusters and misplaced
project-specific entries. Proposes nothing destructive and writes nothing --
the output is a proposal for a human to approve.

The goal is a shorter list, not a permissive one. A list past a couple of
hundred entries is not strict, it is unread.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter, defaultdict

TOOL_CALL = re.compile(r"^(\w+)\((.*)\)$", re.DOTALL)
PROJECT_SPECIFIC = re.compile(r"(/[a-z0-9_.-]+){2,}|[A-Za-z]:\\\\|\./|scripts/|\.py\b|\.sh\b|\.ps1\b")

# Never fold these into a broader allow rule, whatever the usage looks like.
DANGEROUS = (
    "push", "--force", "-f ", "reset --hard", "clean -", "rm -rf", "rmdir",
    "publish", "deploy", "drop ", "delete", "truncate", "chmod", "sudo",
)
DENY_SEED = [
    "Read(**/.env*)", "Read(**/*.pem)", "Read(**/id_rsa*)", "Read(**/.aws/credentials)",
    "Bash(git push --force*)", "Bash(git reset --hard*)", "Bash(git clean -fd*)",
    "Bash(curl * | sh)", "Bash(curl * | bash)",
]
ASK_SEED = ["Bash(git push*)", "Bash(git commit*)", "Bash(npm publish*)", "Bash(rm *)"]


def load(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def split_rule(rule: str):
    m = TOOL_CALL.match(rule.strip())
    return (m.group(1), m.group(2)) if m else (rule.strip(), "")


def prefix_of(arg: str, words: int = 2) -> str:
    tokens = arg.replace("(", " ").split()
    return " ".join(tokens[:words]) if tokens else arg


def analyse(sources):
    rules = [(label, str(r)) for label, entries in sources for r in entries]
    flat = [r for _, r in rules]

    counts = Counter(flat)
    duplicates = {r: n for r, n in counts.items() if n > 1}
    unique = sorted(set(flat))

    shadowed = []
    for broad in unique:
        if not broad.endswith("*"):
            continue
        stem = broad[:-1]
        for narrow in unique:
            if narrow != broad and narrow.startswith(stem):
                shadowed.append((broad, narrow))

    clusters = defaultdict(list)
    for rule in unique:
        tool, arg = split_rule(rule)
        if not arg:
            clusters[(tool, "")].append(rule)
            continue
        clusters[(tool, prefix_of(arg))].append(rule)

    foldable, unsafe = {}, {}
    for (tool, prefix), members in clusters.items():
        if len(members) < 3 or not prefix:
            continue
        risky = [m for m in members if any(d in m.lower() for d in DANGEROUS)]
        target = f"{tool}({prefix} *)"
        if risky:
            unsafe[target] = {"members": members, "blocked_by": risky}
        else:
            foldable[target] = members

    misplaced = [
        r for label, r in rules
        if label.startswith("user") and PROJECT_SPECIFIC.search(r)
    ]

    folded_away = sum(len(v) for v in foldable.values())
    projected = len(unique) - folded_away + len(foldable)

    return {
        "total_entries": len(flat),
        "unique_entries": len(unique),
        "duplicates": duplicates,
        "shadowed": shadowed,
        "foldable": foldable,
        "unsafe_to_fold": unsafe,
        "project_specific_in_user_settings": misplaced,
        "projected_entry_count": projected,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config-dir", help="defaults to CLAUDE_CONFIG_DIR or ~/.claude")
    ap.add_argument("--repo", default=".", help="repo whose .claude/settings.json to include")
    ap.add_argument("--json", metavar="PATH", help="write the full proposal as JSON")
    args = ap.parse_args()

    cfg = pathlib.Path(args.config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or (pathlib.Path.home() / ".claude"))
    repo = pathlib.Path(args.repo).resolve()

    sources, existing_deny, existing_ask = [], [], []
    for label, path in (
        ("user settings.json", cfg / "settings.json"),
        ("user settings.local.json", cfg / "settings.local.json"),
        ("project settings.json", repo / ".claude" / "settings.json"),
        ("project settings.local.json", repo / ".claude" / "settings.local.json"),
    ):
        perms = (load(path) or {}).get("permissions") or {}
        if perms.get("allow"):
            sources.append((label, perms["allow"]))
        existing_deny += perms.get("deny") or []
        existing_ask += perms.get("ask") or []

    if not sources:
        print(f"No allow rules found under {cfg} or {repo}", file=sys.stderr)
        return 2

    r = analyse(sources)

    print("\n  PERMISSION TUNING\n")
    print(f"  {r['total_entries']} entries, {r['unique_entries']} unique")
    print(f"  ask tier: {len(existing_ask)}    deny tier: {len(existing_deny)}")
    if not existing_deny:
        print("\n  No deny tier. The configuration records what was convenient and")
        print("  states nothing about what must never happen (ECC-0010).")

    if r["duplicates"]:
        removed = sum(r["duplicates"].values()) - len(r["duplicates"])
        print(f"\n  DUPLICATES  -- {removed} entries removable\n")
        for rule, n in list(r["duplicates"].items())[:10]:
            print(f"    x{n}  {rule[:90]}")

    if r["shadowed"]:
        print(f"\n  SHADOWED  -- {len(r['shadowed'])} entries already covered by a wildcard\n")
        for broad, narrow in r["shadowed"][:10]:
            print(f"    {broad}\n        already covers  {narrow[:80]}")

    if r["foldable"]:
        print(f"\n  FOLDABLE  -- {len(r['foldable'])} wildcards would replace "
              f"{sum(len(v) for v in r['foldable'].values())} entries\n")
        for target, members in sorted(r["foldable"].items(), key=lambda kv: -len(kv[1]))[:12]:
            print(f"    {target}")
            print(f"        replaces {len(members)}: {', '.join(m[:40] for m in members[:3])}...")

    if r["unsafe_to_fold"]:
        print(f"\n  NOT FOLDED  -- {len(r['unsafe_to_fold'])} clusters contain destructive commands\n")
        for target, info in list(r["unsafe_to_fold"].items())[:8]:
            print(f"    {target}  blocked by: {info['blocked_by'][0][:70]}")
        print("\n    These stay as explicit entries, or move to the ask tier. Folding")
        print("    them would widen a wildcard across a destructive operation.")

    if r["project_specific_in_user_settings"]:
        n = len(r["project_specific_in_user_settings"])
        print(f"\n  MISPLACED  -- {n} user-level entries are project-specific (ECC-0012)\n")
        for rule in r["project_specific_in_user_settings"][:6]:
            print(f"    {rule[:90]}")
        print("\n    These follow you into every other project and cannot be reviewed")
        print("    by the team that owns this one. Move them into the project.")

    print(f"\n  PROJECTED  {r['unique_entries']} -> ~{r['projected_entry_count']} allow entries")

    if not existing_deny:
        print("\n  SUGGESTED DENY TIER (starting point -- review and extend)\n")
        print(json.dumps({"permissions": {"deny": DENY_SEED, "ask": ASK_SEED}}, indent=2))

    print("\n  Back up your settings before applying. Some entries are load-bearing")
    print("  in ways that are not obvious from reading them.\n")

    if args.json:
        payload = dict(r)
        payload["duplicates"] = {k: v for k, v in r["duplicates"].items()}
        payload["suggested_deny"] = DENY_SEED
        payload["suggested_ask"] = ASK_SEED
        pathlib.Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  Wrote {args.json}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
